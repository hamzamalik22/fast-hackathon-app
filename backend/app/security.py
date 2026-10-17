"""JWT authentication (HS256, signature + expiry verified, alg:none rejected) and /api/v1 rate limiting."""
import math
import time
from collections import deque

import jwt
from fastapi import Request
from fastapi.responses import JSONResponse

from . import config, db
from .errors import ApiError


def issue_token(user: dict) -> tuple[str, int]:
    now = int(time.time())
    exp = now + config.JWT_TTL_SECONDS
    league_ids = user["league_ids"] if isinstance(user["league_ids"], list) else db.lj(user["league_ids"])
    claims = {"sub": user["user_id"], "role": user["role"], "tenant_id": user["tenant_id"], "league_ids": league_ids,
              "club_id": user["club_id"], "player_id": user["player_id"], "iat": now, "exp": exp, "iss": "nascon"}
    return jwt.encode(claims, config.JWT_SECRET, algorithm="HS256"), exp


def unauthenticated(message: str = "Missing or invalid access token.") -> ApiError:
    return ApiError(401, "UNAUTHENTICATED", message, {}, headers={"WWW-Authenticate": "Bearer"})


def verify_token(token: str) -> dict:
    try:
        return jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"],
                          options={"require": ["exp", "sub", "role"]})
    except jwt.ExpiredSignatureError:
        raise unauthenticated("Access token has expired.")
    except jwt.PyJWTError:
        raise unauthenticated()


def current_user(request: Request) -> dict:
    auth = request.headers.get("authorization", "")
    scheme, _, token = auth.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise unauthenticated()
    return verify_token(token.strip())


# ---------------------------------------------------------------- rate limiting (/api/v1/* only)
_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
if redis.call('ZCARD', key) >= limit then
  local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
  return {0, tonumber(oldest[2])}
end
redis.call('ZADD', key, now, ARGV[4])
redis.call('PEXPIRE', key, window + 1000)
return {1, 0}
"""
_local_windows: dict[str, deque] = {}
_seq = 0


def _local_hit(ip: str, now_ms: int, window_ms: int, limit: int) -> tuple[bool, int]:
    q = _local_windows.setdefault(ip, deque())
    while q and q[0] <= now_ms - window_ms:
        q.popleft()
    if len(q) >= limit:
        return False, q[0]
    q.append(now_ms)
    return True, 0


async def rate_limit_hit(ip: str) -> tuple[bool, int]:
    """Sliding window: at most RATE_LIMIT_MAX allowed requests per rolling window. Returns (allowed, retry_after_s)."""
    global _seq
    _seq += 1
    now_ms = int(time.time() * 1000)
    window_ms = config.RATE_LIMIT_WINDOW_S * 1000
    try:
        from .services.realtime import client
        allowed, oldest = await client().eval(_LUA, 1, f"rl:{ip}", now_ms, window_ms, config.RATE_LIMIT_MAX,
                                              f"{now_ms}-{_seq}")
        allowed, oldest = bool(allowed), int(oldest)
    except Exception:  # noqa: BLE001 - Redis down: degrade to the in-process window
        allowed, oldest = _local_hit(ip, now_ms, window_ms, config.RATE_LIMIT_MAX)
    if allowed:
        return True, 0
    return False, max(1, math.ceil((oldest + window_ms - now_ms) / 1000))


class RateLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("path", "").startswith("/api/v1/"):
            ip = (scope.get("client") or ("unknown", 0))[0]
            allowed, retry = await rate_limit_hit(ip)
            if not allowed:
                resp = JSONResponse({"error": {"code": "RATE_LIMITED", "message": "Too many requests. Slow down.",
                                               "details": {"retry_after_seconds": retry}}},
                                    status_code=429, headers={"Retry-After": str(retry)})
                return await resp(scope, receive, send)
        return await self.app(scope, receive, send)


async def reset_rate_limits() -> None:
    _local_windows.clear()
    try:
        from .services.realtime import client
        keys = [k async for k in client().scan_iter("rl:*")]
        if keys:
            await client().delete(*keys)
    except Exception:  # noqa: BLE001
        pass
