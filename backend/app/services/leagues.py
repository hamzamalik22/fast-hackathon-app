"""POST /audit/v1/leagues and GET /audit/v1/standings/{league_id}."""
from .. import db
from ..domain import scoring, standings
from ..domain.sports import validate_tie_break_order
from ..errors import conflict, not_found
from ..validation import Fields, is_id, is_int
from .scoring import get_sport


def validate_league(b: dict) -> dict:
    f = Fields()
    if not is_id(b.get("league_id")):
        f.add("league_id")
    if not (isinstance(b.get("sport_id"), str) and b.get("sport_id")):
        f.add("sport_id")
    teams = b.get("teams")
    if (not isinstance(teams, list) or not all(is_id(t) for t in teams) or len(set(teams)) != len(teams)
            or not 2 <= len(teams) <= 40):
        f.add("teams")
        teams = None
    fixtures = b.get("fixtures")
    if not isinstance(fixtures, list):
        f.add("fixtures")
        fixtures = []
    seen = set()
    for fx in fixtures:
        if (not isinstance(fx, dict) or not is_id(fx.get("match_id")) or fx.get("match_id") in seen
                or not is_id(fx.get("home")) or not is_id(fx.get("away")) or fx.get("home") == fx.get("away")
                or (teams is not None and (fx.get("home") not in teams or fx.get("away") not in teams))):
            f.add("fixtures")
            continue
        seen.add(fx["match_id"])
    pts_in = b.get("points")
    points = {"win": 3, "draw": 1, "loss": 0}
    if pts_in is not None:
        if not isinstance(pts_in, dict):
            f.add("points")
        else:
            for k in ("win", "draw", "loss"):
                if k in pts_in and pts_in[k] is not None:
                    if not is_int(pts_in[k]):
                        f.add("points", f"points.{k}")
                    else:
                        points[k] = pts_in[k]
    tbo = validate_tie_break_order(b.get("tie_break_order"), f)
    q = b.get("qualification")
    spots = q.get("spots") if isinstance(q, dict) else None
    if not is_int(spots) or (teams is not None and not 1 <= spots <= len(teams)) or (teams is None and spots < 1):
        f.add("qualification", "qualification.spots")
    lots = b.get("lots_seed")
    if lots is not None and not is_int(lots):
        f.add("lots_seed")
    f.check()
    return {"league_id": b["league_id"], "sport_id": b["sport_id"], "teams": teams,
            "fixtures": [{"match_id": x["match_id"], "home": x["home"], "away": x["away"]} for x in fixtures],
            "points": points, "tie_break_order": tbo, "qualification_spots": spots, "lots_seed": lots}


async def create_league(body: dict) -> dict:
    lg = validate_league(body)
    async with db.tx() as conn:
        await db.lock(conn, "league:" + lg["league_id"])
        if await get_sport(conn, lg["sport_id"]) is None:
            raise not_found("SPORT_NOT_FOUND", f"Sport {lg['sport_id']} does not exist.", sport_id=lg["sport_id"])
        if await db.fetchone(conn, "SELECT 1 FROM leagues WHERE league_id=%s", (lg["league_id"],)):
            raise conflict("LEAGUE_EXISTS", f"League {lg['league_id']} already exists.", league_id=lg["league_id"])
        ids = [x["match_id"] for x in lg["fixtures"]]
        if ids:
            taken = await db.fetchone(conn, "SELECT match_id FROM matches WHERE match_id = ANY(%s) LIMIT 1", (ids,))
            if taken:
                raise conflict("MATCH_EXISTS", f"Match {taken['match_id']} already exists.",
                               match_id=taken["match_id"])
        lots_seed = lg["lots_seed"]
        if lots_seed is None:
            lots_seed = int(await db.get_meta(conn, "last_seed", "42"))
        cfg = {"teams": lg["teams"], "points": lg["points"], "tie_break_order": lg["tie_break_order"],
               "qualification_spots": lg["qualification_spots"], "lots_seed": lots_seed}
        await conn.execute("INSERT INTO leagues(league_id, sport_id, config) VALUES (%s,%s,%s)",
                           (lg["league_id"], lg["sport_id"], db.dj(cfg)))
        for i, fx in enumerate(lg["fixtures"]):
            await conn.execute("INSERT INTO matches(match_id, league_id, sport_id, home_team_id, away_team_id) "
                               "VALUES (%s,%s,%s,%s,%s)",
                               (fx["match_id"], lg["league_id"], lg["sport_id"], fx["home"], fx["away"]))
    return {"league_id": lg["league_id"], "status": "created", "team_count": len(lg["teams"]),
            "fixture_count": len(lg["fixtures"])}


async def load_league_states(conn, league: dict, sport: dict) -> list[dict]:
    """All matches of a league folded from their event logs (one query for all events)."""
    cfg = db.lj(league["config"])
    teams = set(cfg["teams"])
    matches = await db.fetchall(conn, "SELECT * FROM matches WHERE league_id=%s ORDER BY created_seq",
                                (league["league_id"],))
    rows = await db.fetchall(conn, "SELECT e.event_id, e.match_id, e.sequence, e.type, e.payload, e.signature "
                                   "FROM match_events e JOIN matches m ON m.match_id = e.match_id "
                                   "WHERE m.league_id=%s ORDER BY e.match_id, e.sequence", (league["league_id"],))
    by_match: dict[str, list] = {}
    for r in rows:
        r["payload"] = db.lj(r["payload"])
        by_match.setdefault(r["match_id"], []).append(r)
    out = []
    for m in matches:
        if m["home_team_id"] not in teams or m["away_team_id"] not in teams:
            continue
        events = by_match.get(m["match_id"], [])
        out.append({"match": m, "home": m["home_team_id"], "away": m["away_team_id"], "events": events,
                    "state": scoring.fold(sport, m, events)})
    return out


async def get_standings(league_id: str) -> dict:
    async with db.tx() as conn:
        league = await db.fetchone(conn, "SELECT * FROM leagues WHERE league_id=%s", (league_id,))
        if league is None:
            raise not_found("LEAGUE_NOT_FOUND", f"League {league_id} does not exist.", league_id=league_id)
        sport = await get_sport(conn, league["sport_id"])
        fixtures = await load_league_states(conn, league, sport)
    cfg = db.lj(league["config"])
    lots_seed = cfg.get("lots_seed")
    if lots_seed is None:
        lots_seed = 42
    return standings.compute(league_id, sport, cfg, fixtures, lots_seed)
