"""DB side of roster operations: setup, transfer/loan/release, history with automatic loan return."""
from .. import db
from ..canonical import canonical
from ..domain import roster
from ..errors import not_found, validation_error
from ..validation import now_ts, parse_date, today
from .scoring import get_sport

TRANSFER_FIELDS = ("request_id", "league_id", "player_id", "type", "from_squad_id", "to_squad_id",
                   "effective_date", "loan_end_date", "reason", "requested_by")


async def load_league(conn, league_id: str) -> dict | None:
    row = await db.fetchone(conn, "SELECT * FROM roster_leagues WHERE league_id=%s", (league_id,))
    if row is not None:
        row["required_positions"] = db.lj(row["required_positions"])
    return row


async def load_squads(conn, league_id: str) -> dict:
    rows = await db.fetchall(conn, "SELECT * FROM squads WHERE league_id=%s", (league_id,))
    return {r["squad_id"]: r for r in rows}


async def load_players(conn, league_id: str) -> list[dict]:
    return await db.fetchall(conn, "SELECT * FROM roster_players WHERE league_id=%s", (league_id,))


async def get_player(conn, player_id: str) -> dict | None:
    return await db.fetchone(conn, "SELECT * FROM roster_players WHERE player_id=%s", (player_id,))


async def audit_count(conn, player_id: str) -> int:
    row = await db.fetchone(conn, "SELECT count(*) AS n FROM roster_audit WHERE player_id=%s", (player_id,))
    return row["n"]


async def _apply_update(conn, player_id: str, u: dict) -> None:
    await conn.execute("UPDATE roster_players SET squad_id=%s, role=%s, parent_squad_id=%s, registration_type=%s, "
                       "start_date=%s, loan_end_date=%s WHERE player_id=%s",
                       (u["squad_id"], u["role"], u["parent_squad_id"], u["registration_type"], u["start_date"],
                        u["loan_end_date"], player_id))


async def _append_audit(conn, entry: dict) -> dict:
    n = await db.next_counter(conn, "audit")
    full = {"audit_id": f"au-{n:04d}", **entry, "when": now_ts()}
    full = {k: full[k] for k in ("audit_id", "action", "player_id", "league_id", "from_squad_id", "to_squad_id",
                                 "effective_date", "state", "who", "when", "why")}
    await conn.execute("INSERT INTO roster_audit(audit_id, player_id, league_id, action, effective_date, entry) "
                       "VALUES (%s,%s,%s,%s,%s,%s)", (full["audit_id"], full["player_id"], full["league_id"],
                                                      full["action"], full["effective_date"], db.dj(full)))
    return full


async def _materialize_return(conn, player: dict, as_of) -> dict:
    lr = roster.loan_return(player, as_of)
    if lr is None:
        return player
    await _apply_update(conn, player["player_id"], lr["update"])
    await _append_audit(conn, lr["entry"])
    return {**player, **lr["update"]}


async def setup(body: dict) -> dict:
    s = roster.validate_setup(body)
    lid = s["league_id"]
    async with db.tx() as conn:
        await db.lock(conn, "roster:" + lid)
        sport = await get_sport(conn, s["sport_id"])
        if sport is None:
            raise not_found("SPORT_NOT_FOUND", f"Sport {s['sport_id']} does not exist.", sport_id=s["sport_id"])
        max_size = s["max_squad_size"] or sport["roster"]["max_squad_size"]
        req_pos = s["required_positions"] if s["required_positions"] is not None else sport["roster"]["required_positions"]
        for table in ("roster_leagues", "squads", "roster_players", "roster_live_matches", "roster_audit",
                      "roster_requests"):
            await conn.execute(f"DELETE FROM {table} WHERE league_id=%s", (lid,))
        ids = [p["player_id"] for p in s["players"]]
        if ids:
            await conn.execute("DELETE FROM roster_players WHERE player_id = ANY(%s)", (ids,))
        await conn.execute("INSERT INTO roster_leagues(league_id, tenant_id, sport_id, window_open, window_close, "
                           "max_squad_size, required_positions) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                           (lid, s["tenant_id"], s["sport_id"], s["window_open"], s["window_close"], max_size,
                            db.dj(req_pos)))
        counts = {}
        for sq in s["squads"]:
            await conn.execute("INSERT INTO squads(league_id, squad_id, club_id, tenant_id, name) VALUES (%s,%s,%s,%s,%s)",
                               (lid, sq["squad_id"], sq.get("club_id"), sq["tenant_id"], sq.get("name")))
            counts[sq["squad_id"]] = 0
        for p in s["players"]:
            await conn.execute("INSERT INTO roster_players(player_id, league_id, name, position, squad_id, role, "
                               "registration_type, start_date, initial_squad_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                               (p["player_id"], lid, p.get("name"), p.get("position"), p.get("squad_id"),
                                p.get("role") or "substitute", "registration", s["window_open"] or today(),
                                p.get("squad_id")))
            if p.get("squad_id") is not None:
                counts[p["squad_id"]] += 1
        for m in s["matches_in_progress"]:
            await conn.execute("INSERT INTO roster_live_matches(league_id, match_id, home_squad_id, away_squad_id) "
                               "VALUES (%s,%s,%s,%s)", (lid, m["match_id"], m.get("home_squad_id"), m.get("away_squad_id")))
    return {"league_id": lid, "status": "configured", "squad_counts": counts}


async def transfer(body: dict) -> tuple[int, dict]:
    req = roster.validate_transfer(body)
    canon = canonical({k: body.get(k) for k in TRANSFER_FIELDS})
    async with db.tx() as conn:
        await db.lock(conn, "roster:" + req["league_id"])
        prior = await db.fetchone(conn, "SELECT request_canonical, response FROM roster_requests WHERE request_id=%s",
                                  (req["request_id"],))
        if prior is not None:
            if prior["request_canonical"] == canon:
                return 200, db.lj(prior["response"])
            raise roster.duplicate_request(req["request_id"])
        league = await load_league(conn, req["league_id"])
        player = await get_player(conn, req["player_id"])
        squads = await load_squads(conn, req["league_id"]) if league else {}
        roster.check_exists(req, league, player, squads)
        if player["league_id"] == league["league_id"]:
            player = await _materialize_return(conn, player, req["effective_date"])
        league_players = await load_players(conn, league["league_id"])
        live = await db.fetchall(conn, "SELECT * FROM roster_live_matches WHERE league_id=%s", (league["league_id"],))
        result = roster.evaluate_transfer(req, league, squads, player, league_players, live)
        await _apply_update(conn, player["player_id"], result["update"])
        entry = await _append_audit(conn, result["entry"])
        resp = {"request_id": req["request_id"], "status": "accepted", "state": result["state"],
                "blocking_match_id": result["blocking_match_id"], "registration": result["registration"],
                "audit_entry": entry}
        await conn.execute("INSERT INTO roster_requests(request_id, league_id, request_canonical, response) "
                           "VALUES (%s,%s,%s,%s)", (req["request_id"], req["league_id"], canon, db.dj(resp)))
    return 201, resp


async def history(player_id: str, as_of_raw: str | None) -> dict:
    as_of = today() if as_of_raw is None else parse_date(as_of_raw)
    if as_of is None:
        raise validation_error(["as_of"], "as_of must be a date YYYY-MM-DD.")
    async with db.tx() as conn:
        player = await get_player(conn, player_id)
        if player is None:
            raise not_found("PLAYER_NOT_FOUND", f"Player {player_id} does not exist.", player_id=player_id)
        await db.lock(conn, "roster:" + player["league_id"])
        player = await get_player(conn, player_id)
        player = await _materialize_return(conn, player, as_of)
        rows = await db.fetchall(conn, "SELECT entry FROM roster_audit WHERE player_id=%s ORDER BY seq", (player_id,))
    entries = [db.lj(r["entry"]) for r in rows]
    current, parent = roster.squad_on(as_of, player["initial_squad_id"], entries)
    return {"player_id": player_id, "as_of": as_of.isoformat(), "league_id": player["league_id"],
            "current_squad_id": current, "parent_squad_id": parent, "history": entries}
