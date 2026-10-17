"""DB side of the scoring engine: locking, idempotency, append-only writes, projections."""
from .. import db
from ..canonical import canonical, sign
from ..domain import scoring
from ..domain.sports import validate_sport
from ..errors import conflict, not_found
from . import realtime


async def get_sport(conn, sport_id: str) -> dict | None:
    row = await db.fetchone(conn, "SELECT config FROM sports WHERE sport_id=%s", (sport_id,))
    return None if row is None else db.lj(row["config"])


async def get_match(conn, match_id: str) -> dict | None:
    return await db.fetchone(conn, "SELECT * FROM matches WHERE match_id=%s", (match_id,))


async def load_events(conn, match_id: str) -> list[dict]:
    rows = await db.fetchall(conn, "SELECT event_id, match_id, sequence, type, payload, signature FROM match_events "
                                   "WHERE match_id=%s ORDER BY sequence", (match_id,))
    for r in rows:
        r["payload"] = db.lj(r["payload"])
    return rows


async def create_sport(body: dict) -> dict:
    cfg = validate_sport(body)
    async with db.tx() as conn:
        await db.lock(conn, "sport:" + cfg["sport_id"])
        if await get_sport(conn, cfg["sport_id"]) is not None:
            raise conflict("SPORT_EXISTS", f"Sport {cfg['sport_id']} already exists.", sport_id=cfg["sport_id"])
        await conn.execute("INSERT INTO sports(sport_id,name,scoring_model,config) VALUES (%s,%s,%s,%s)",
                           (cfg["sport_id"], cfg["name"], cfg["scoring_model"], db.dj(cfg)))
    return {"sport_id": cfg["sport_id"], "status": "created", "config": cfg}


async def append_event(body: dict, conn=None) -> tuple[int, dict]:
    """POST /audit/v1/events. Returns (http_status, response). Shared by /api/v1 and offline sync."""
    req = scoring.validate_event_request(body)
    if conn is None:
        async with db.tx() as c:
            status, resp = await _append(c, req)
    else:
        status, resp = await _append(conn, req)
    if status == 201:
        await realtime.publish(f"match:{req['match_id']}", {"type": "match_event", "match_id": req["match_id"],
                                                             "event": {k: resp[k] for k in ("event_id", "type", "sequence")}})
    return status, resp


async def _append(conn, req: dict) -> tuple[int, dict]:
    canon = canonical(req)
    await db.lock(conn, "match:" + req["match_id"])
    await db.lock(conn, "event:" + req["event_id"])
    prior = await db.fetchone(conn, "SELECT request_canonical, response FROM match_events WHERE event_id=%s",
                              (req["event_id"],))
    if prior is not None:
        if prior["request_canonical"] == canon:
            return 200, db.lj(prior["response"])
        raise conflict("DUPLICATE_EVENT_ID", f"Event id {req['event_id']} was already used with a different body.",
                       event_id=req["event_id"])

    match = await get_match(conn, req["match_id"])
    p = req["payload"]
    if req["type"] == "match_init":
        if await get_sport(conn, p["sport_id"]) is None:
            raise not_found("SPORT_NOT_FOUND", f"Sport {p['sport_id']} does not exist.", sport_id=p["sport_id"])
        if match is not None:
            raise conflict("MATCH_EXISTS", f"Match {req['match_id']} already exists.", match_id=req["match_id"])
        await conn.execute("INSERT INTO matches(match_id, league_id, sport_id, home_team_id, away_team_id, "
                           "created_by_init) VALUES (%s,%s,%s,%s,%s,TRUE)",
                           (req["match_id"], p.get("league_id"), p["sport_id"], p["home_team_id"], p["away_team_id"]))
        events = []
    else:
        if match is None:
            raise not_found("MATCH_NOT_FOUND", f"Match {req['match_id']} does not exist.", match_id=req["match_id"])
        sport = await get_sport(conn, match["sport_id"])
        events = await load_events(conn, req["match_id"])
        target = None
        if req["type"] == "compensation":
            target = await db.fetchone(conn, "SELECT event_id, match_id, type FROM match_events WHERE event_id=%s",
                                       (p["compensates"],))
        scoring.check_event(sport, match, events, req, target)

    sequence = len(events) + 1
    signature = sign(req["event_id"], p)
    resp = {"event_id": req["event_id"], "match_id": req["match_id"], "type": req["type"],
            "sequence": sequence, "match_version": sequence, "signature": signature}
    await conn.execute(
        "INSERT INTO match_events(event_id, match_id, sequence, type, payload, signature, compensates, "
        "request_canonical, response) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (req["event_id"], req["match_id"], sequence, req["type"], db.dj(p), signature,
         p.get("compensates") if req["type"] == "compensation" else None, canon, db.dj(resp)))
    return 201, resp


async def match_version(conn, match_id: str) -> int:
    row = await db.fetchone(conn, "SELECT count(*) AS n FROM match_events WHERE match_id=%s", (match_id,))
    return row["n"]


async def score(match_id: str) -> dict:
    async with db.tx() as conn:
        match = await get_match(conn, match_id)
        if match is None:
            raise not_found("MATCH_NOT_FOUND", f"Match {match_id} does not exist.", match_id=match_id)
        sport = await get_sport(conn, match["sport_id"])
        events = await load_events(conn, match_id)
    return scoring.project(sport, match, events)
