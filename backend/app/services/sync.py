"""Offline action replay (spec 5.14). Each action runs through the same services as /events and /roster/transfer."""
import asyncio

from .. import db
from ..canonical import canonical
from ..domain import roster as roster_domain
from ..domain import scoring as scoring_domain
from ..domain import sync
from ..errors import ApiError
from ..validation import is_id
from . import roster as roster_svc
from . import scoring as scoring_svc

_device_locks: dict[str, asyncio.Lock] = {}


async def offline_sync(body: dict, authorize=None) -> dict:
    """authorize(kind, info) -> error code or None; used by the authenticated /api/v1/sync route."""
    env = sync.validate_envelope(body)
    device = env["device_id"]
    actions = env["actions"]
    lock = _device_locks.setdefault(device, asyncio.Lock())
    results: list[dict | None] = [None] * len(actions)
    async with lock:
        for order, i in enumerate(sync.processing_order(actions), 1):
            results[i] = await _process(device, actions[i], order, authorize)
    return {"device_id": device, "results": results, "summary": sync.summarize(results)}


async def _current_version(action: dict) -> int:
    p = action["payload"]
    async with db.tx() as conn:
        if action["type"] == "score_event":
            mid = p.get("match_id")
            return await scoring_svc.match_version(conn, mid) if is_id(mid) else 0
        pid = p.get("player_id")
        return await roster_svc.audit_count(conn, pid) if is_id(pid) else 0


async def _process(device: str, action: dict, order: int, authorize) -> dict:
    aid = action["action_id"]
    async with db.tx() as conn:
        prior = await db.fetchone(conn, "SELECT 1 FROM sync_actions WHERE device_id=%s AND action_id=%s",
                                  (device, aid))
    if prior is not None:
        return sync.duplicate(aid, order, await _current_version(action))
    if action["type"] == "score_event":
        res = await _score(action, order, authorize)
    else:
        res = await _roster(action, order, authorize)
    async with db.tx() as conn:
        await conn.execute("INSERT INTO sync_actions(device_id, action_id, result) VALUES (%s,%s,%s) "
                           "ON CONFLICT DO NOTHING", (device, aid, db.dj(res)))
    return res


async def _score(action: dict, order: int, authorize) -> dict:
    aid, p, base = action["action_id"], action["payload"], action["base_version"]
    mid = p.get("match_id")
    async with db.tx() as conn:
        match = await scoring_svc.get_match(conn, mid) if is_id(mid) else None
        version = await scoring_svc.match_version(conn, mid) if match else 0
        try:
            req = scoring_domain.validate_event_request(p)
        except ApiError as e:
            return sync.rejected(aid, e.code, order, version)
        prior = await db.fetchone(conn, "SELECT request_canonical FROM match_events WHERE event_id=%s",
                                  (req["event_id"],))
    if prior is not None:
        if prior["request_canonical"] == canonical(req):
            return sync.duplicate(aid, order, version)
        return sync.rejected(aid, "DUPLICATE_EVENT_ID", order, version)
    if match is None and req["type"] != "match_init":
        return sync.rejected(aid, "MATCH_NOT_FOUND", order, version)
    if base > version:
        return sync.rejected(aid, "INVALID_BASE_VERSION", order, version)
    if authorize is not None:
        code = await authorize("score_event", {"match_id": mid, "league_id": match["league_id"] if match else None})
        if code:
            return sync.rejected(aid, code, order, version)
    try:
        _, resp = await scoring_svc.append_event(p)
    except ApiError as e:
        return sync.rejected(aid, e.code, order, version)
    return sync.applied(aid, base, version, order, resp["match_version"], resp["signature"])


async def _roster(action: dict, order: int, authorize) -> dict:
    aid, p, base = action["action_id"], action["payload"], action["base_version"]
    pid = p.get("player_id")
    async with db.tx() as conn:
        version = await roster_svc.audit_count(conn, pid) if is_id(pid) else 0
        try:
            req = roster_domain.validate_transfer(p)
        except ApiError as e:
            return sync.rejected(aid, e.code, order, version)
        prior = await db.fetchone(conn, "SELECT request_canonical FROM roster_requests WHERE request_id=%s",
                                  (req["request_id"],))
        league = await roster_svc.load_league(conn, req["league_id"])
        player = await roster_svc.get_player(conn, req["player_id"])
        squads = await roster_svc.load_squads(conn, req["league_id"]) if league else {}
    if prior is not None:
        if prior["request_canonical"] == canonical({k: p.get(k) for k in roster_svc.TRANSFER_FIELDS}):
            return sync.duplicate(aid, order, version)
        return sync.rejected(aid, "DUPLICATE_REQUEST_ID", order, version)
    try:
        roster_domain.check_exists(req, league, player, squads)
    except ApiError as e:
        return sync.rejected(aid, e.code, order, version)
    if base > version:
        return sync.rejected(aid, "INVALID_BASE_VERSION", order, version)
    if authorize is not None:
        code = await authorize("roster_transfer", {"league_id": req["league_id"],
                                                   "club_id": squads[req["from_squad_id"]]["club_id"],
                                                   "tenant_id": league["tenant_id"]})
        if code:
            return sync.rejected(aid, code, order, version)
    try:
        await roster_svc.transfer(p)
    except ApiError as e:
        return sync.rejected(aid, e.code, order, version)
    async with db.tx() as conn:
        after = await roster_svc.audit_count(conn, pid)
    return sync.applied(aid, base, version, order, after)
