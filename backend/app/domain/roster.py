"""Roster registry rules (FR-2.2, spec 5.11): transfers, loans, releases, automatic loan return, audit history.

Pure functions over plain dicts; the service layer loads/persists and holds the league lock.
"""
from datetime import date, timedelta

from ..errors import ApiError, conflict, not_found
from ..validation import Fields, is_id, is_int, parse_date

TYPES = ("transfer", "loan", "release")
ROLES = ("captain", "vice_captain", "starter", "substitute")


def validate_setup(b: dict) -> dict:
    f = Fields()
    lg = b.get("league")
    if not isinstance(lg, dict):
        f.add("league")
        f.check()
    if not is_id(lg.get("league_id")):
        f.add("league.league_id")
    if not is_id(lg.get("tenant_id")):
        f.add("league.tenant_id")
    if not (isinstance(lg.get("sport_id"), str) and lg.get("sport_id")):
        f.add("league.sport_id")
    win = lg.get("transfer_window")
    w_open = w_close = None
    if win is not None:
        if not isinstance(win, dict):
            f.add("league.transfer_window")
        else:
            w_open, w_close = parse_date(win.get("open")), parse_date(win.get("close"))
            if w_open is None or w_close is None or w_open > w_close:
                f.add("league.transfer_window")
    mss = lg.get("max_squad_size")
    if mss is not None and not (is_int(mss) and mss >= 1):
        f.add("league.max_squad_size")
    rp = lg.get("required_positions")
    if rp is not None and not (isinstance(rp, dict) and all(isinstance(k, str) and is_int(v) and v >= 0
                                                            for k, v in rp.items())):
        f.add("league.required_positions")

    squads = b.get("squads", [])
    if not isinstance(squads, list):
        f.add("squads")
        squads = []
    sq_ids = set()
    for s in squads:
        if (not isinstance(s, dict) or not is_id(s.get("squad_id")) or s.get("squad_id") in sq_ids
                or not is_id(s.get("tenant_id")) or (s.get("club_id") is not None and not is_id(s.get("club_id")))):
            f.add("squads")
            continue
        sq_ids.add(s["squad_id"])
    players = b.get("players", [])
    if not isinstance(players, list):
        f.add("players")
        players = []
    p_ids = set()
    for p in players:
        if (not isinstance(p, dict) or not is_id(p.get("player_id")) or p.get("player_id") in p_ids
                or (p.get("squad_id") is not None and p.get("squad_id") not in sq_ids)
                or (p.get("role") is not None and p.get("role") not in ROLES)
                or (p.get("position") is not None and not isinstance(p.get("position"), str))):
            f.add("players")
            continue
        p_ids.add(p["player_id"])
    live = b.get("matches_in_progress", [])
    if live is None:
        live = []
    if not isinstance(live, list) or not all(isinstance(m, dict) and is_id(m.get("match_id")) for m in live):
        f.add("matches_in_progress")
        live = []
    f.check()
    return {"league_id": lg["league_id"], "tenant_id": lg["tenant_id"], "sport_id": lg["sport_id"],
            "window_open": w_open, "window_close": w_close, "max_squad_size": mss, "required_positions": rp,
            "squads": squads, "players": players, "matches_in_progress": live}


def validate_transfer(b: dict) -> dict:
    f = Fields()
    for k in ("request_id", "league_id", "player_id", "from_squad_id"):
        if not is_id(b.get(k)):
            f.add(k)
    t = b.get("type")
    if t not in TYPES:
        f.add("type")
    to = b.get("to_squad_id")
    if t in ("transfer", "loan") and not is_id(to):
        f.add("to_squad_id")
    if t in ("transfer", "loan") and is_id(to) and to == b.get("from_squad_id"):
        f.add("to_squad_id")
    eff = parse_date(b.get("effective_date"))
    if eff is None:
        f.add("effective_date")
    loan_end = None
    if t == "loan":
        loan_end = parse_date(b.get("loan_end_date"))
        if loan_end is None or (eff is not None and loan_end <= eff):
            f.add("loan_end_date")
    elif b.get("loan_end_date") is not None and parse_date(b.get("loan_end_date")) is None:
        f.add("loan_end_date")
    for k in ("reason", "requested_by"):
        if b.get(k) is not None and not isinstance(b.get(k), str):
            f.add(k)
    f.check()
    return {"request_id": b["request_id"], "league_id": b["league_id"], "player_id": b["player_id"], "type": t,
            "from_squad_id": b["from_squad_id"], "to_squad_id": to if t != "release" else None,
            "effective_date": eff, "loan_end_date": loan_end, "reason": b.get("reason"),
            "requested_by": b.get("requested_by")}


def check_exists(req: dict, league: dict | None, player: dict | None, squads: dict) -> None:
    if league is None:
        raise not_found("LEAGUE_NOT_FOUND", f"League {req['league_id']} does not exist.", league_id=req["league_id"])
    if player is None:
        raise not_found("PLAYER_NOT_FOUND", f"Player {req['player_id']} does not exist.", player_id=req["player_id"])
    for key in ("from_squad_id", "to_squad_id"):
        sid = req[key]
        if sid is not None and sid not in squads:
            raise not_found("SQUAD_NOT_FOUND", f"Squad {sid} does not exist in this league.", squad_id=sid)


def evaluate_transfer(req: dict, league: dict, squads: dict, player: dict, league_players: list[dict],
                      live_matches: list[dict]) -> dict:
    """Rule checks 3..8 in the exact spec order, then the effect. Raises ApiError on the first failure."""
    t, frm, to = req["type"], req["from_squad_id"], req["to_squad_id"]
    for sid in (frm, to):
        if sid is not None and squads[sid]["tenant_id"] != league["tenant_id"]:
            raise conflict("CROSS_TENANT_TRANSFER", "Both squads must belong to the league's tenant.", squad_id=sid)
    if player["league_id"] != league["league_id"] or player["squad_id"] != frm:
        raise conflict("NOT_IN_SQUAD", f"Player {player['player_id']} is not in squad {frm}.",
                       player_id=player["player_id"], squad_id=frm)
    if t in ("transfer", "loan"):
        eff = req["effective_date"]
        if league["window_open"] is None or not league["window_open"] <= eff <= league["window_close"]:
            raise conflict("TRANSFER_WINDOW_CLOSED", "The transfer window is closed on that date.",
                           effective_date=eff.isoformat())
    if player["registration_type"] == "loan":
        raise conflict("PLAYER_ON_LOAN", f"Player {player['player_id']} is currently on loan.",
                       player_id=player["player_id"])
    if t in ("transfer", "loan"):
        size = sum(1 for p in league_players if p["squad_id"] == to)
        if size + 1 > league["max_squad_size"]:
            raise conflict("SQUAD_FULL", f"Squad {to} is full.", squad_id=to, max_squad_size=league["max_squad_size"])
    need = (league["required_positions"] or {}).get(player["position"])
    if need:
        left = sum(1 for p in league_players if p["squad_id"] == frm and p["position"] == player["position"]) - 1
        if left < need:
            raise conflict("MIN_POSITION_VIOLATION", f"Squad {frm} needs at least {need} {player['position']}.",
                           squad_id=frm, position=player["position"], required=need)

    blocking = next((m["match_id"] for m in live_matches if frm in (m.get("home_squad_id"), m.get("away_squad_id"))),
                    None)
    state = "deferred_until_match_end" if blocking else "active"
    eff = req["effective_date"]
    if t == "release":
        update = {"squad_id": None, "role": None, "parent_squad_id": None, "registration_type": "released",
                  "start_date": eff, "loan_end_date": None}
        registration = None
    else:
        update = {"squad_id": to, "role": "substitute", "parent_squad_id": frm if t == "loan" else None,
                  "registration_type": t, "start_date": eff, "loan_end_date": req["loan_end_date"]}
        registration = {"player_id": player["player_id"], "league_id": league["league_id"], "squad_id": to,
                        "parent_squad_id": update["parent_squad_id"], "registration_type": t,
                        "start_date": eff.isoformat(),
                        "loan_end_date": req["loan_end_date"].isoformat() if req["loan_end_date"] else None,
                        "role": "substitute"}
    entry = {"action": t, "player_id": player["player_id"], "league_id": league["league_id"], "from_squad_id": frm,
             "to_squad_id": to, "effective_date": eff.isoformat(), "state": state,
             "who": req["requested_by"], "why": req["reason"]}
    return {"update": update, "registration": registration, "entry": entry, "state": state,
            "blocking_match_id": blocking}


def loan_return(player: dict, as_of: date) -> dict | None:
    """The day after loan_end_date the player is back with the lender (role substitute)."""
    if player["registration_type"] != "loan" or player["loan_end_date"] is None or as_of <= player["loan_end_date"]:
        return None
    back = player["loan_end_date"] + timedelta(days=1)
    update = {"squad_id": player["parent_squad_id"], "role": "substitute", "parent_squad_id": None,
              "registration_type": "loan_return", "start_date": back, "loan_end_date": None}
    entry = {"action": "loan_return", "player_id": player["player_id"], "league_id": player["league_id"],
             "from_squad_id": player["squad_id"], "to_squad_id": player["parent_squad_id"],
             "effective_date": back.isoformat(), "state": "active", "who": "system", "why": "Loan period ended"}
    return {"update": update, "entry": entry}


def squad_on(as_of: date, initial_squad: str | None, entries: list[dict]) -> tuple[str | None, str | None]:
    """Replay the audit trail up to as_of: (current_squad_id, parent_squad_id) on that date."""
    squad, parent = initial_squad, None
    for e in entries:
        if date.fromisoformat(e["effective_date"]) > as_of:
            continue
        if e["action"] == "release":
            squad, parent = None, None
        elif e["action"] == "loan":
            squad, parent = e["to_squad_id"], e["from_squad_id"]
        else:
            squad, parent = e["to_squad_id"], None
    return squad, parent


def duplicate_request(request_id: str) -> ApiError:
    return ApiError(409, "DUPLICATE_REQUEST_ID", f"Request id {request_id} was already used with a different body.",
                    {"request_id": request_id})
