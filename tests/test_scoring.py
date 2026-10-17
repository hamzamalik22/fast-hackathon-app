"""FR-1.1 event-sourced scoring engine + sport-as-data configuration (all three scoring models)."""
import json
from pathlib import Path

import pytest

from app.domain import scoring
from app.domain.sports import effective_tie_break_order, validate_sport
from app.errors import ApiError

SPORTS = {s["sport_id"]: validate_sport(s) for s in
          json.loads((Path(__file__).resolve().parent.parent / "backend/app/seed/sports.json").read_text())}
KABADDI = {"sport_id": "kabaddi", "name": "Kabaddi", "scoring_model": "event", "periods": {"count": 2, "duration_minutes": 20},
           "scoring_events": {"raid_point": {"points": 1}, "all_out": {"points": 2}}, "draw_allowed": False,
           "overtime": {"policy": "golden_score", "duration_minutes": 5},
           "roster": {"min_squad_size": 7, "max_squad_size": 12, "required_positions": {"raider": 2}}}
MATCH = {"match_id": "m1", "sport_id": "x", "league_id": None, "home_team_id": "h", "away_team_id": "a"}


class Log:
    def __init__(self, sport):
        self.sport, self.events = sport, []

    def add(self, etype, payload=None, eid=None):
        req = {"event_id": eid or f"e{len(self.events) + 1}", "match_id": "m1", "type": etype, "payload": payload or {}}
        req = scoring.validate_event_request(req)
        target = next((e for e in self.events if e["event_id"] == req["payload"].get("compensates")), None)
        if etype == "compensation" and target is None and req["payload"]["compensates"] == "other-match":
            target = {"event_id": "other-match", "match_id": "m2", "type": "score"}
        scoring.check_event(self.sport, MATCH, self.events, req, target)
        self.events.append({**req, "sequence": len(self.events) + 1, "signature": "s"})
        return self

    def code(self, etype, payload=None):
        with pytest.raises(ApiError) as e:
            self.add(etype, payload)
        return e.value.code

    def proj(self):
        return scoring.project(self.sport, MATCH, self.events)


def test_seed_sports_are_valid_data():
    assert set(SPORTS) == {"football", "basketball", "cricket", "esports"}
    assert SPORTS["cricket"]["scoring_events"]["wide"] == {"runs": 1, "legal_ball": False, "wicket": False}


def test_mystery_sport_and_compensation_flow():
    log = Log(validate_sport(KABADDI)).add("match_start")
    assert log.code("score", {"team_id": "h", "event_type": "goal"}) == "UNKNOWN_EVENT_TYPE"
    assert log.code("score", {"team_id": "zz", "event_type": "raid_point"}) == "VALIDATION_ERROR"
    log.add("score", {"team_id": "h", "event_type": "all_out"}, "g1").add("score", {"team_id": "a", "event_type": "raid_point"})
    log.add("discipline", {"team_id": "a", "points": -2})
    p = log.proj()
    assert (p["home"]["score"], p["away"]["score"], p["away"]["fair_play"], p["status"]) == (2, 1, -2, "in_progress")
    assert p["outcome"] == "pending" and p["home"]["wickets"] is None and p["version"] == 4
    log.add("compensation", {"compensates": "g1", "reason": "review"})
    assert log.code("compensation", {"compensates": "g1"}) == "INVALID_COMPENSATION"
    assert log.code("compensation", {"compensates": "e1"}) == "INVALID_COMPENSATION"  # match_start is not compensable
    assert log.code("compensation", {"compensates": "nope"}) == "EVENT_NOT_FOUND"
    assert log.code("compensation", {"compensates": "other-match"}) == "INVALID_COMPENSATION"
    p = log.proj()
    assert p["home"]["score"] == 0 and p["events"][1]["compensated"] and p["events"][1]["compensated_by"] == "e5"
    log.add("match_end")
    assert log.proj()["outcome"] == "away_win" and log.proj()["winner_team_id"] == "a"
    log.add("compensation", {"compensates": "e3"})
    p = log.proj()
    assert p["status"] == "completed" and p["outcome"] == "undecided" and p["winner_team_id"] is None


def test_state_machine_and_tiebreak():
    log = Log(SPORTS["basketball"])
    assert log.code("score", {"team_id": "h", "event_type": "two_pointer"}) == "MATCH_NOT_IN_PROGRESS"
    assert log.code("match_end") == "ILLEGAL_TRANSITION"
    assert log.code("tiebreak_winner", {"team_id": "h"}) == "MATCH_NOT_IN_PROGRESS"
    log.add("match_start")
    assert log.code("match_start") == "ILLEGAL_TRANSITION"
    assert log.code("match_end") == "TIE_NOT_ALLOWED"
    assert log.code("match_init", {"sport_id": "x", "home_team_id": "h", "away_team_id": "a"}) == "MATCH_EXISTS"
    log.add("tiebreak_winner", {"team_id": "a"}, "tb").add("match_end")
    p = log.proj()
    assert p["outcome"] == "away_win" and p["tiebreak_winner_team_id"] == "a"
    log.add("compensation", {"compensates": "tb"})
    assert log.proj()["outcome"] == "undecided"


def test_draw_allowed():
    log = Log(SPORTS["football"]).add("match_start").add("match_end")
    assert log.proj()["outcome"] == "draw"


def test_innings_model_limits():
    sport = validate_sport({**KABADDI, "scoring_model": "innings", "periods": {
        "innings_per_team": 1, "overs_per_innings": 1, "balls_per_over": 6, "wickets_per_innings": 2},
        "scoring_events": {"six": {"runs": 6, "legal_ball": True, "wicket": False},
                           "wd": {"runs": 1, "legal_ball": False, "wicket": False},
                           "out": {"runs": 0, "legal_ball": True, "wicket": True}}})
    log = Log(sport).add("match_start")
    for et in ["six", "wd", "six", "out"]:
        log.add("score", {"team_id": "h", "event_type": et})
    p = log.proj()["home"]
    assert (p["score"], p["balls"], p["wickets"], p["overs"]) == (13, 3, 1, "0.3")
    log.add("score", {"team_id": "h", "event_type": "out"})
    assert log.code("score", {"team_id": "h", "event_type": "six"}) == "INNINGS_COMPLETE"
    for _ in range(6):
        log.add("score", {"team_id": "a", "event_type": "six"})
    assert log.proj()["away"]["overs"] == "1.0"
    assert log.code("score", {"team_id": "a", "event_type": "wd"}) == "INNINGS_COMPLETE"


def test_round_model_series_decided():
    log = Log(SPORTS["esports"]).add("match_start")
    log.add("score", {"team_id": "h", "event_type": "round_win"}).add("score", {"team_id": "h", "event_type": "round_win"})
    assert log.code("score", {"team_id": "a", "event_type": "round_win"}) == "SERIES_ALREADY_DECIDED"
    log.add("discipline", {"team_id": "a", "points": -1}).add("match_end")
    assert log.proj()["outcome"] == "home_win" and log.proj()["home"]["score"] == 2


@pytest.mark.parametrize("body,field", [
    ({"event_id": "bad|id", "match_id": "m", "type": "score", "payload": {}}, "event_id"),
    ({"event_id": "e", "match_id": "m", "type": "nope", "payload": {}}, "type"),
    ({"event_id": "e", "match_id": "m", "type": "score", "payload": []}, "payload"),
    ({"event_id": "e", "match_id": "m", "type": "match_init", "payload": {"sport_id": "", "home_team_id": "a", "away_team_id": "a"}}, "payload.sport_id"),
    ({"event_id": "e", "match_id": "m", "type": "match_init", "payload": {"sport_id": "s", "home_team_id": "a", "away_team_id": "a"}}, "payload.away_team_id"),
    ({"event_id": "e", "match_id": "m", "type": "match_init", "payload": {"sport_id": "s", "home_team_id": "a", "away_team_id": "b", "league_id": 5}}, "payload.league_id"),
    ({"event_id": "e", "match_id": "m", "type": "score", "payload": {"team_id": "h"}}, "payload.event_type"),
    ({"event_id": "e", "match_id": "m", "type": "discipline", "payload": {"team_id": "h", "points": True}}, "payload.points"),
    ({"event_id": "e", "match_id": "m", "type": "compensation", "payload": {"compensates": 3}}, "payload.compensates"),
    ({"event_id": "e", "match_id": "m", "type": "compensation", "payload": {"compensates": "x", "reason": 1}}, "payload.reason"),
])
def test_event_validation(body, field):
    with pytest.raises(ApiError) as e:
        scoring.validate_event_request(body)
    assert e.value.status == 400 and field in e.value.details["fields"]


@pytest.mark.parametrize("patch,field", [
    ({"sport_id": "x'; DROP TABLE sports;--"}, "sport_id"), ({"name": ""}, "name"), ({"scoring_model": "goals"}, "scoring_model"),
    ({"periods": {"count": 0, "duration_minutes": 20}}, "periods.count"), ({"periods": 3}, "periods"),
    ({"periods": {"count": 1, "duration_minutes": True}}, "periods.duration_minutes"),
    ({"scoring_events": {}}, "scoring_events"), ({"scoring_events": {"Bad Key": {"points": 1}}}, "scoring_events"),
    ({"scoring_events": {"p": {"points": 0}}}, "scoring_events.p"), ({"draw_allowed": "no"}, "draw_allowed"),
    ({"overtime": {"policy": "penalties"}}, "overtime"), ({"overtime": {"policy": "none", "duration_minutes": -1}}, "overtime.duration_minutes"),
    ({"tie_break_order": ["scored", "scored"]}, "tie_break_order"), ({"tie_break_order": ["luck"]}, "tie_break_order"),
    ({"roster": {"min_squad_size": 5, "max_squad_size": 2}}, "roster.min_squad_size"), ({"roster": []}, "roster"),
    ({"roster": {"min_squad_size": 0, "max_squad_size": 0, "required_positions": {"gk": -1}}}, "roster.required_positions"),
])
def test_sport_validation(patch, field):
    with pytest.raises(ApiError) as e:
        validate_sport({**KABADDI, **patch})
    assert field in e.value.details["fields"]


def test_sport_model_specific_validation():
    with pytest.raises(ApiError) as e:
        validate_sport({**KABADDI, "scoring_model": "innings", "periods": {"innings_per_team": 1},
                        "scoring_events": {"x": {"runs": 1, "legal_ball": "y", "wicket": False}}})
    assert "periods.overs_per_innings" in e.value.details["fields"] and "scoring_events.x" in e.value.details["fields"]
    with pytest.raises(ApiError) as e:
        validate_sport({**KABADDI, "scoring_model": "round", "periods": {"best_of": 4}, "scoring_events": {"m": {"rounds": 0}}})
    assert {"periods.best_of", "scoring_events.m"} <= set(e.value.details["fields"])
    ok = validate_sport({**KABADDI, "scoring_model": "round", "periods": {"best_of": 5}, "scoring_events": {"map_win": {"rounds": 1}}})
    assert ok["tie_break_order"][-1] == "draw_lots" and ok["periods"] == {"best_of": 5}


def test_effective_tie_break_order():
    assert effective_tie_break_order(["scored"]) == ["scored", "draw_lots"]
    assert effective_tie_break_order(["draw_lots", "scored"]) == ["scored", "draw_lots"]
    assert effective_tie_break_order(None)[-1] == "draw_lots"
