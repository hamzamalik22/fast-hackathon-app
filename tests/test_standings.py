"""FR-1.4 standings: points, 3-way H2H mini-league, differentials (incl. NRR), drawing of lots, qualification."""
import json
from pathlib import Path

from app.domain import scoring, standings
from app.domain.sports import validate_sport

SPORTS = {s["sport_id"]: validate_sport(s) for s in
          json.loads((Path(__file__).resolve().parent.parent / "backend/app/seed/sports.json").read_text())}


def fx(sport, home, away, scores=None, finished=True, discipline=None, tiebreak=None):
    """Fold a synthetic event log. scores: list of (team, event_type)."""
    m = {"match_id": f"{home}-{away}", "sport_id": sport["sport_id"], "home_team_id": home, "away_team_id": away}
    ev = [{"event_id": "s", "type": "match_start", "payload": {}}]
    for i, (team, et) in enumerate(scores or []):
        ev.append({"event_id": f"g{i}", "type": "score", "payload": {"team_id": team, "event_type": et}})
    for team, pts in (discipline or []):
        ev.append({"event_id": f"d{team}", "type": "discipline", "payload": {"team_id": team, "points": pts}})
    if tiebreak:
        ev.append({"event_id": "tb", "type": "tiebreak_winner", "payload": {"team_id": tiebreak}})
    if finished:
        ev.append({"event_id": "e", "type": "match_end", "payload": {}})
    return {"home": home, "away": away, "state": scoring.fold(sport, m, ev)}


def goals(home, away, gh, ga, **kw):
    return fx(SPORTS["football"], home, away, [(home, "goal")] * gh + [(away, "goal")] * ga, **kw)


def cfg(teams, spots=2, **kw):
    return {"teams": teams, "points": {"win": 3, "draw": 1, "loss": 0}, "qualification_spots": spots, **kw}


def table(league_cfg, fixtures, sport="football", league_id="lg-1"):
    return standings.compute(league_id, SPORTS[sport], league_cfg, fixtures, 42)


def test_three_way_tie_resolved_by_overall_diff():
    f = [goals("t1", "t2", 1, 0), goals("t2", "t3", 1, 0), goals("t3", "t1", 1, 0),
         goals("t1", "t4", 2, 0), goals("t2", "t4", 3, 0), goals("t3", "t4", 1, 0)]
    out = table(cfg(["t1", "t2", "t3", "t4"]), f)
    assert [(r["team_id"], r["points"], r["resolved_by"], r["status"]) for r in out["table"]] == [
        ("t2", 6, "overall_diff", "still_possible"), ("t1", 6, "overall_diff", "still_possible"),
        ("t3", 6, None, "still_possible"), ("t4", 0, None, "eliminated")]
    assert out["h2h"]["t1"]["t2"] == {"played": 1, "points": 3, "scored": 1, "conceded": 0}
    assert out["h2h"]["t4"]["t1"] == {"played": 1, "points": 0, "scored": 0, "conceded": 2}


def test_mini_league_h2h_diff_then_restart_on_split():
    # Cycle t1>t2 (1-0), t2>t3 (2-0), t3>t1 (3-0): mini-league points level (3 each). Mini-league diff:
    # t2 +1, t3 +1, t1 -2 -> {t2, t3} above t1; {t2, t3} restarts from h2h_points: t2 beat t3 directly.
    f = [goals("t1", "t2", 1, 0), goals("t2", "t3", 2, 0), goals("t3", "t1", 3, 0),
         goals("t1", "t4", 1, 0), goals("t2", "t4", 1, 0), goals("t3", "t4", 1, 0)]
    out = table(cfg(["t1", "t2", "t3", "t4"]), f)
    assert [(r["team_id"], r["points"], r["resolved_by"]) for r in out["table"]] == [
        ("t2", 6, "h2h_points"), ("t3", 6, "h2h_diff"), ("t1", 6, None), ("t4", 0, None)]


def test_draw_lots_vector_and_custom_order():
    out = table(cfg(["t1", "t2", "t3"], spots=1), [])
    assert [(r["team_id"], r["resolved_by"]) for r in out["table"]] == [("t1", "draw_lots"), ("t3", "draw_lots"), ("t2", None)]
    f = [goals("t1", "t2", 0, 0, discipline=[("t1", -3)]), goals("t3", "t1", 0, 0), goals("t2", "t3", 0, 0)]
    out = table(cfg(["t1", "t2", "t3"], spots=1, tie_break_order=["fair_play"]), f)
    assert [(r["team_id"], r["resolved_by"]) for r in out["table"]] == [("t3", "draw_lots"), ("t2", "fair_play"), ("t1", None)]
    assert out["table"][-1]["fair_play"] == -3


def test_qualification_status_and_undecided_counts_as_remaining():
    bb = SPORTS["basketball"]
    f = [fx(bb, "a", "b", [("a", "three_pointer")]), fx(bb, "a", "c", [("a", "free_throw")]),
         fx(bb, "b", "c", []), fx(bb, "c", "a", [], finished=False)]
    out = table(cfg(["a", "b", "c"], spots=1), f, sport="basketball")
    rows = {r["team_id"]: r for r in out["table"]}
    # c still has 2 remaining fixtures (b-c undecided + c-a unfinished): max(c) = 6 = points(a) -> not clinched yet
    assert rows["a"]["points"] == 6 and rows["a"]["status"] == "still_possible"
    assert rows["b"]["played"] == 1 and rows["c"]["played"] == 1  # b-c tied without tie-break = undecided
    assert rows["b"]["status"] == "eliminated" and rows["c"]["status"] == "still_possible"
    f[-1] = fx(bb, "c", "a", [("a", "two_pointer")])
    rows = {r["team_id"]: r for r in table(cfg(["a", "b", "c"], spots=1), f, sport="basketball")["table"]}
    assert rows["a"]["status"] == "clinched" and rows["c"]["status"] == "eliminated"


def test_tiebreak_win_counts_as_win():
    bb = SPORTS["basketball"]
    out = table(cfg(["a", "b"], spots=1), [fx(bb, "a", "b", [], tiebreak="b")], sport="basketball")
    rows = {r["team_id"]: r for r in out["table"]}
    assert rows["b"]["won"] == 1 and rows["a"]["lost"] == 1 and rows["b"]["points"] == 3


def test_cricket_net_run_rate_with_all_out():
    ck = SPORTS["cricket"]
    # h: 6 legal balls, 14 runs (1 over). a: all out (10 wickets) after 12 balls -> counts as 20 overs, 10 runs.
    h_events = [("h", "four"), ("h", "wide"), ("h", "six"), ("h", "single"), ("h", "two"), ("h", "dot_ball"), ("h", "dot_ball")]
    a_events = [("a", "four"), ("a", "six")] + [("a", "wicket")] * 10
    out = table(cfg(["h", "a"], spots=1), [fx(ck, "h", "a", h_events + a_events)], sport="cricket")
    rows = {r["team_id"]: r for r in out["table"]}
    assert rows["h"]["scored"] == 14 and rows["a"]["scored"] == 10
    assert rows["h"]["diff"] == round(14 / 1 - 10 / 20, 3) and rows["a"]["diff"] == round(10 / 20 - 14 / 1, 3)
    assert rows["h"]["won"] == 1


def test_draws_and_round_model_diff():
    es = SPORTS["esports"]
    out = table(cfg(["x", "y"], spots=1), [fx(es, "x", "y", [("x", "round_win"), ("y", "round_win"), ("x", "round_win")])],
                sport="esports")
    assert out["table"][0]["team_id"] == "x" and out["table"][0]["diff"] == 1
    out = table(cfg(["p", "q"], spots=1), [goals("p", "q", 2, 2)])
    assert all(r["drawn"] == 1 and r["points"] == 1 for r in out["table"])
