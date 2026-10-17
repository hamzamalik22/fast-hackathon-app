"""FR-2.2 roster rules: the 8 checks in spec order, loans with automatic return, deferred state, history replay."""
from datetime import date

import pytest

from app.domain import roster
from app.errors import ApiError

LEAGUE = {"league_id": "lg-r1", "tenant_id": "tenant-alpha", "window_open": date(2026, 9, 1),
          "window_close": date(2026, 9, 30), "max_squad_size": 3, "required_positions": {"gk": 1}}
SQUADS = {"sq-a": {"tenant_id": "tenant-alpha", "club_id": "c-a"}, "sq-b": {"tenant_id": "tenant-alpha", "club_id": "c-b"},
          "sq-c": {"tenant_id": "tenant-beta", "club_id": "c-c"}}


def player(pid, pos, squad, reg="registration", parent=None, loan_end=None):
    return {"player_id": pid, "league_id": "lg-r1", "position": pos, "squad_id": squad, "registration_type": reg,
            "parent_squad_id": parent, "loan_end_date": loan_end, "role": "starter"}


PLAYERS = [player("p1", "gk", "sq-a"), player("p2", "df", "sq-a"), player("p3", "mf", "sq-b"), player("p4", "fw", "sq-b")]


def req(**kw):
    body = {"request_id": "r1", "league_id": "lg-r1", "player_id": "p2", "type": "transfer", "from_squad_id": "sq-a",
            "to_squad_id": "sq-b", "effective_date": "2026-09-30", "loan_end_date": None, "reason": "why",
            "requested_by": "u1", **kw}
    return roster.validate_transfer(body)


def evaluate(r, players=PLAYERS, live=(), league=LEAGUE):
    p = next(x for x in players if x["player_id"] == r["player_id"])
    return roster.evaluate_transfer(r, league, SQUADS, p, list(players), list(live))


def code(r, **kw):
    with pytest.raises(ApiError) as e:
        evaluate(r, **kw)
    return e.value.code


def test_transfer_effect_and_deferred_state():
    out = evaluate(req(), live=[{"match_id": "m-live", "home_squad_id": "sq-a", "away_squad_id": "sq-x"}])
    assert out["state"] == "deferred_until_match_end" and out["blocking_match_id"] == "m-live"
    assert out["registration"] == {"player_id": "p2", "league_id": "lg-r1", "squad_id": "sq-b", "parent_squad_id": None,
                                   "registration_type": "transfer", "start_date": "2026-09-30", "loan_end_date": None,
                                   "role": "substitute"}
    assert out["entry"]["who"] == "u1" and out["entry"]["why"] == "why" and out["entry"]["action"] == "transfer"
    assert evaluate(req())["state"] == "active"


def test_loan_and_release_effects():
    out = evaluate(req(type="loan", effective_date="2026-09-10", loan_end_date="2026-09-20"))
    assert out["registration"]["parent_squad_id"] == "sq-a" and out["registration"]["loan_end_date"] == "2026-09-20"
    rel = evaluate(req(type="release", to_squad_id=None, effective_date="2027-03-01"))  # release ignores the window
    assert rel["registration"] is None and rel["update"]["squad_id"] is None and rel["entry"]["to_squad_id"] is None


def test_rule_order():
    assert code(req(to_squad_id="sq-c")) == "CROSS_TENANT_TRANSFER"
    assert code(req(from_squad_id="sq-b", to_squad_id="sq-a", player_id="p2")) == "NOT_IN_SQUAD"
    assert code(req(effective_date="2026-10-01")) == "TRANSFER_WINDOW_CLOSED"
    assert code(req(effective_date="2026-08-31")) == "TRANSFER_WINDOW_CLOSED"
    loaned = [player("p2", "df", "sq-a", reg="loan", parent="sq-b", loan_end=date(2026, 9, 25))] + PLAYERS[2:]
    assert code(req(), players=[PLAYERS[0]] + loaned) == "PLAYER_ON_LOAN"
    full = PLAYERS + [player("p5", "df", "sq-b")]
    assert code(req(), players=full) == "SQUAD_FULL"
    assert code(req(player_id="p1"), players=PLAYERS) == "MIN_POSITION_VIOLATION"
    assert code(req(player_id="p1", type="release", to_squad_id=None)) == "MIN_POSITION_VIOLATION"
    assert code(req(), league={**LEAGUE, "window_open": None}) == "TRANSFER_WINDOW_CLOSED"


def test_check_exists():
    r = req()
    for args, c in [((None, PLAYERS[1], SQUADS), "LEAGUE_NOT_FOUND"), ((LEAGUE, None, SQUADS), "PLAYER_NOT_FOUND"),
                    ((LEAGUE, PLAYERS[1], {"sq-a": SQUADS["sq-a"]}), "SQUAD_NOT_FOUND")]:
        with pytest.raises(ApiError) as e:
            roster.check_exists(r, *args)
        assert e.value.code == c and e.value.status == 404
    roster.check_exists(r, LEAGUE, PLAYERS[1], SQUADS)


@pytest.mark.parametrize("patch,field", [
    ({"request_id": ""}, "request_id"), ({"type": "swap"}, "type"), ({"to_squad_id": None}, "to_squad_id"),
    ({"to_squad_id": "sq-a"}, "to_squad_id"), ({"effective_date": "2026-02-30"}, "effective_date"),
    ({"type": "loan"}, "loan_end_date"), ({"type": "loan", "loan_end_date": "2026-09-30"}, "loan_end_date"),
    ({"loan_end_date": "nope"}, "loan_end_date"), ({"reason": 5}, "reason"),
])
def test_transfer_validation(patch, field):
    with pytest.raises(ApiError) as e:
        req(**patch)
    assert e.value.status == 400 and field in e.value.details["fields"]


def test_loan_return_and_history_replay():
    p = player("p3", "mf", "sq-b", reg="loan", parent="sq-a", loan_end=date(2026, 9, 20))
    assert roster.loan_return(p, date(2026, 9, 20)) is None
    lr = roster.loan_return(p, date(2027, 1, 5))
    assert lr["update"]["squad_id"] == "sq-a" and lr["entry"]["who"] == "system" and lr["entry"]["effective_date"] == "2026-09-21"
    assert roster.loan_return(player("p1", "gk", "sq-a"), date(2027, 1, 1)) is None
    entries = [{"action": "loan", "from_squad_id": "sq-a", "to_squad_id": "sq-b", "effective_date": "2026-09-10"},
               lr["entry"], {"action": "release", "from_squad_id": "sq-a", "to_squad_id": None, "effective_date": "2026-12-01"}]
    assert roster.squad_on(date(2026, 9, 1), "sq-a", entries) == ("sq-a", None)
    assert roster.squad_on(date(2026, 9, 15), "sq-a", entries) == ("sq-b", "sq-a")
    assert roster.squad_on(date(2026, 10, 1), "sq-a", entries) == ("sq-a", None)
    assert roster.squad_on(date(2027, 1, 5), "sq-a", entries) == (None, None)
    assert roster.duplicate_request("r1").status == 409


def test_setup_validation():
    good = {"league": {"league_id": "lg", "tenant_id": "t", "sport_id": "football",
                       "transfer_window": {"open": "2026-09-01", "close": "2026-09-30"}},
            "squads": [{"squad_id": "a", "tenant_id": "t"}], "players": [{"player_id": "p", "squad_id": "a", "role": "captain"}],
            "matches_in_progress": None}
    s = roster.validate_setup(good)
    assert s["window_open"] == date(2026, 9, 1) and s["max_squad_size"] is None and s["matches_in_progress"] == []
    bad_cases = [({"league": []}, "league"),
                 ({**good, "league": {**good["league"], "transfer_window": {"open": "2026-09-30", "close": "2026-09-01"}}}, "league.transfer_window"),
                 ({**good, "league": {**good["league"], "max_squad_size": 0}}, "league.max_squad_size"),
                 ({**good, "league": {**good["league"], "required_positions": {"gk": "1"}}}, "league.required_positions"),
                 ({**good, "squads": [{"squad_id": "a", "tenant_id": "t"}, {"squad_id": "a", "tenant_id": "t"}]}, "squads"),
                 ({**good, "players": [{"player_id": "p", "squad_id": "zz"}]}, "players"),
                 ({**good, "players": [{"player_id": "p", "role": "coach"}]}, "players"),
                 ({**good, "matches_in_progress": [{"x": 1}]}, "matches_in_progress"),
                 ({**good, "squads": "x", "players": "y"}, "squads")]
    for body, field in bad_cases:
        with pytest.raises(ApiError) as e:
            roster.validate_setup(body)
        assert field in e.value.details["fields"], (body, e.value.details)
