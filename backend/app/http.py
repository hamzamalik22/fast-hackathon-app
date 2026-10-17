"""Request parsing helpers and the body-size guard."""
import json

from fastapi import Request
from fastapi.responses import JSONResponse

from . import config
from .errors import ApiError, validation_error


def _reject_constant(c):
    raise ValueError(f"invalid JSON constant {c}")


async def read_json(request: Request, optional: bool = False) -> dict:
    raw = await request.body()
    if len(raw) > config.MAX_BODY_BYTES:
        raise too_large()
    if not raw.strip():
        if optional:
            return {}
        raise validation_error(["body"], "Request body is required.")
    try:
        obj = json.loads(raw.decode("utf-8"), parse_constant=_reject_constant)
    except (ValueError, UnicodeDecodeError):
        raise ApiError(400, "VALIDATION_ERROR", "Malformed JSON body.", {"fields": ["body"]})
    if not isinstance(obj, dict):
        raise validation_error(["body"], "Request body must be a JSON object.")
    return obj


def too_large() -> ApiError:
    return ApiError(413, "PAYLOAD_TOO_LARGE", "Request body exceeds 1 MB.", {"max_bytes": config.MAX_BODY_BYTES})


def respond(status: int, body) -> JSONResponse:
    return JSONResponse(body, status_code=status)


class BodyLimitMiddleware:
    """Rejects bodies > 1 MB with 413 before routing (so it also applies to auth-only probe routes).

    The body is drained before answering so clients that are still uploading read a clean 413.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        length = None
        for k, v in scope.get("headers", []):
            if k == b"content-length":
                try:
                    length = int(v)
                except ValueError:
                    length = None
        if length is not None and length > config.MAX_BODY_BYTES:
            drained = 0
            more = True
            while more and drained < 64 * config.MAX_BODY_BYTES:
                msg = await receive()
                if msg["type"] != "http.request":
                    break
                drained += len(msg.get("body", b""))
                more = msg.get("more_body", False)
            resp = JSONResponse(too_large().body(), status_code=413)
            return await resp(scope, receive, send)
        return await self.app(scope, receive, send)
