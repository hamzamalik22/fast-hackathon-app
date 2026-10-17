"""Event-sourced scoring engine (FR-1.1, spec 5.9). Pure functions; the score is always folded from the log.

Branches only on the sport's scoring_model, never on a sport id or event name.
"""
from dataclasses import dataclass, field

from ..errors import ApiError, conflict, not_found, validation_error
from ..validation import Fields, is_id, is_int

EVENT_TYPES = ("match_init", "match_start", "score", "discipline", "tiebreak_winner", "match_end", "compensation")
COMPENSABLE = ("score", "discipline", "tiebreak_winner")
TEAM_EVENTS = ("score", "discipline", "tiebreak_winner")


def validate_event_request(body: dict) -> dict:
    """400-level checks for POST /events. Returns the normalized request used for idempotency."""
    f = Fields()
    if not is_id(body.get("event_id")):
        f.add("event_id")
    if not is_id(body.get("match_id")):
        f.add("match_id")
    etype = body.get("type")
    if etype not in EVENT_TYPES:
        f.add("type")
    payload = body.get("payload")
    if not isinstance(payload, dict):
        f.add("payload")
    f.check()

    if etype == "match_init":
        if not isinstance(payload.get("sport_id"), str) or not payload.get("sport_id"):
            f.add("payload.sport_id")
        h, a = payload.get("home_team_id"), payload.get("away_team_id")
        if not is_id(h):
            f.add("payload.home_team_id")
        if not is_id(a):
            f.add("payload.away_team_id")
        if is_id(h) and h == a:
            f.add("payload.away_team_id")
        if payload.get("league_id") is not None and not is_id(payload.get("league_id")):
            f.add("payload.league_id")
    elif etype in TEAM_EVENTS:
        if not is_id(payload.get("team_id")):
            f.add("payload.team_id")
        if etype == "score" and not (isinstance(payload.get("event_type"), str) and payload.get("event_type")):
            f.add("payload.event_type")
        if etype == "discipline" and not is_int(payload.get("points")):
            f.add("payload.points")
    elif etype == "compensation":
        if not is_id(payload.get("compensates")):
            f.add("payload.compensates")
        if payload.get("reason") is not None and not isinstance(payload.get("reason"), str):
            f.add("payload.reason")
    f.check()
    return {"event_id": body["event_id"], "match_id": body["match_id"], "type": etype, "payload": payload}


@dataclass
class Side:
    team_id: str
    score: int = 0
    wickets: int = 0
    balls: int = 0
    fair_play: int = 0


@dataclass
class MatchState:
    status: str
    outcome: str
    winner_team_id: str | None
    tiebreak_winner_team_id: str | None
    home: Side
    away: Side
    compensated_by: dict = field(default_factory=dict)

    def side(self, team_id: str) -> Side | None:
        if team_id == self.home.team_id:
            return self.home
        if team_id == self.away.team_id:
            return self.away
        return None


def fold(sport: dict, match: dict, events: list[dict]) -> MatchState:
    """Rebuild the match state from the append-only log. Compensated events and compensations are neutral."""
    model = sport["scoring_model"]
    scoring_events = sport["scoring_events"]
    compensated_by: dict[str, str] = {}
    for e in events:
        if e["type"] == "compensation":
            compensated_by.setdefault(e["payload"]["compensates"], e["event_id"])

    home, away = Side(match["home_team_id"]), Side(match["away_team_id"])
    sides = {home.team_id: home, away.team_id: away}
    started = ended = False
    tiebreak = None
    for e in events:
        etype, p = e["type"], e["payload"]
        if etype == "match_start":
            started = True
        elif etype == "match_end":
            ended = True
        if etype == "compensation" or e["event_id"] in compensated_by or etype not in TEAM_EVENTS:
            continue
        side = sides.get(p.get("team_id"))
        if side is None:
            continue
        if etype == "score":
            rule = scoring_events.get(p.get("event_type"))
            if rule is None:
                continue
            if model == "event":
                side.score += rule["points"]
            elif model == "innings":
                side.score += rule["runs"]
                side.balls += 1 if rule["legal_ball"] else 0
                side.wickets += 1 if rule["wicket"] else 0
            else:
                side.score += rule["rounds"]
        elif etype == "discipline":
            side.fair_play += p["points"]
        else:
            tiebreak = p["team_id"]

    status = "completed" if ended else ("in_progress" if started else "upcoming")
    if home.score > away.score:
        winner = home.team_id
    elif away.score > home.score:
        winner = away.team_id
    else:
        winner = tiebreak
    if status != "completed":
        outcome = "pending"
    elif winner == home.team_id:
        outcome = "home_win"
    elif winner == away.team_id:
        outcome = "away_win"
    elif sport["draw_allowed"]:
        outcome = "draw"
    else:
        outcome = "undecided"
    return MatchState(status, outcome, winner, tiebreak, home, away, compensated_by)


def _side_json(sport: dict, s: Side) -> dict:
    if sport["scoring_model"] == "innings":
        bpo = sport["periods"]["balls_per_over"]
        return {"team_id": s.team_id, "score": s.score, "wickets": s.wickets, "balls": s.balls,
                "overs": f"{s.balls // bpo}.{s.balls % bpo}", "fair_play": s.fair_play}
    return {"team_id": s.team_id, "score": s.score, "wickets": None, "balls": None, "overs": None,
            "fair_play": s.fair_play}


def project(sport: dict, match: dict, events: list[dict]) -> dict:
    st = fold(sport, match, events)
    return {
        "match_id": match["match_id"],
        "sport_id": match["sport_id"],
        "league_id": match.get("league_id"),
        "status": st.status,
        "outcome": st.outcome,
        "winner_team_id": st.winner_team_id,
        "tiebreak_winner_team_id": st.tiebreak_winner_team_id,
        "home": _side_json(sport, st.home),
        "away": _side_json(sport, st.away),
        "version": len(events),
        "events": [{
            "sequence": e["sequence"], "event_id": e["event_id"], "type": e["type"], "payload": e["payload"],
            "signature": e["signature"], "compensated": e["event_id"] in st.compensated_by,
            "compensated_by": st.compensated_by.get(e["event_id"]),
        } for e in events],
    }


def check_event(sport: dict, match: dict, events: list[dict], req: dict, target: dict | None = None) -> None:
    """Business rules for appending req to an existing stream. Raises ApiError (400 -> 404 -> 409)."""
    etype, p = req["type"], req["payload"]
    st = fold(sport, match, events)
    if etype == "match_init":
        raise conflict("MATCH_EXISTS", f"Match {match['match_id']} already exists.", match_id=match["match_id"])
    if etype in TEAM_EVENTS:
        side = st.side(p["team_id"])
        if side is None:
            raise validation_error(["payload.team_id"], "team_id must be the home or away team of this match.")
        if etype == "score" and p["event_type"] not in sport["scoring_events"]:
            raise ApiError(400, "UNKNOWN_EVENT_TYPE", f"Event type {p['event_type']} is not defined for this sport.",
                           {"event_type": p["event_type"], "sport_id": sport["sport_id"]})
        if st.status != "in_progress":
            raise conflict("MATCH_NOT_IN_PROGRESS", "The match is not in progress.",
                           match_id=match["match_id"], status=st.status)
        if etype == "score":
            _check_limits(sport, st, side, match["match_id"])
    elif etype == "match_start":
        if st.status != "upcoming":
            raise conflict("ILLEGAL_TRANSITION", f"Cannot start a match that is {st.status}.",
                           match_id=match["match_id"], status=st.status)
    elif etype == "match_end":
        if st.status != "in_progress":
            raise conflict("ILLEGAL_TRANSITION", f"Cannot end a match that is {st.status}.",
                           match_id=match["match_id"], status=st.status)
        if st.home.score == st.away.score and not sport["draw_allowed"] and st.tiebreak_winner_team_id is None:
            raise conflict("TIE_NOT_ALLOWED", "Scores are level and this sport does not allow a draw.",
                           match_id=match["match_id"])
    elif etype == "compensation":
        if target is None:
            raise not_found("EVENT_NOT_FOUND", f"Event {p['compensates']} does not exist.", event_id=p["compensates"])
        if (target["match_id"] != match["match_id"] or target["type"] not in COMPENSABLE
                or target["event_id"] in st.compensated_by):
            raise conflict("INVALID_COMPENSATION", "That event cannot be compensated.", event_id=target["event_id"])


def _check_limits(sport: dict, st: MatchState, side: Side, match_id: str) -> None:
    per = sport["periods"]
    if sport["scoring_model"] == "innings":
        ipt = per["innings_per_team"]
        if (side.balls >= ipt * per["overs_per_innings"] * per["balls_per_over"]
                or side.wickets >= ipt * per["wickets_per_innings"]):
            raise conflict("INNINGS_COMPLETE", "This team's innings is complete.", match_id=match_id,
                           team_id=side.team_id)
    elif sport["scoring_model"] == "round":
        needed = (per["best_of"] + 1) // 2
        if st.home.score >= needed or st.away.score >= needed:
            raise conflict("SERIES_ALREADY_DECIDED", "The series is already decided.", match_id=match_id)
