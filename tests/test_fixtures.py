"""FR-1.3 fixture algorithms: round robin, Swiss, single and double elimination (property-checked)."""
import math
import random

import pytest

from app.domain.fixtures import generate
from app.domain.fixtures.matching import max_weight_matching, min_cost_perfect_matching
from app.errors import ApiError


def T(n):
    return [f"t{i + 1}" for i in range(n)]


def err(body):
    with pytest.raises(ApiError) as e:
        generate(body)
    return e.value


# ------------------------------------------------------------------ round robin
@pytest.mark.parametrize("n", list(range(2, 21)) + [31, 40])
@pytest.mark.parametrize("legs", [1, 2])
def test_round_robin_properties(n, legs):
    r = generate({"format": "round_robin", "teams": T(n), "params": {"legs": legs}})
    per = n - 1 if n % 2 == 0 else n
    assert r["round_count"] == per * legs == len(r["rounds"])
    pairs, ordered = {}, set()
    for rd in r["rounds"]:
        assert len(rd["matches"]) == n // 2 and len(rd["byes"]) == n % 2
        seen = set(rd["byes"])
        for m in rd["matches"]:
            assert not {m["home"], m["away"]} & seen
            seen |= {m["home"], m["away"]}
            pairs[frozenset((m["home"], m["away"]))] = pairs.get(frozenset((m["home"], m["away"])), 0) + 1
            ordered.add((m["home"], m["away"]))
            assert m["match_id"].startswith(f"RR-L{m['leg']}-R{rd['round']}-M")
        assert seen == set(T(n))
    assert len(pairs) == n * (n - 1) // 2 and set(pairs.values()) == {legs}
    if legs == 2:
        assert len(ordered) == n * (n - 1)
    for leg in range(1, legs + 1):
        home = {t: 0 for t in T(n)}
        away = {t: 0 for t in T(n)}
        for rd in r["rounds"]:
            for m in rd["matches"]:
                if m["leg"] == leg:
                    home[m["home"]] += 1
                    away[m["away"]] += 1
        assert all(abs(home[t] - away[t]) <= 1 for t in T(n))


def test_round_robin_spec_example_and_withdrawals():
    base = {"format": "round_robin", "teams": T(5)}
    r = generate({**base, "params": {"legs": 1, "withdrawals": [{"team_id": "t3", "after_round": 2}],
                                     "withdrawal_policy": "forfeit_remaining"}})
    assert r["rounds"][0]["byes"] == ["t1"]
    assert [(m["home"], m["away"]) for m in r["rounds"][0]["matches"]] == [("t2", "t5"), ("t3", "t4")]
    assert r["summary"] == {"total": 10, "scheduled": 8, "forfeit": 2, "voided": 0}
    for rd in r["rounds"]:
        for m in rd["matches"]:
            if "t3" in (m["home"], m["away"]) and rd["round"] > 2:
                assert m["status"] == "forfeit" and m["awarded_to"] == ({m["home"], m["away"]} - {"t3"}).pop()
    v = generate({**base, "params": {"withdrawals": [{"team_id": "t3", "after_round": 2}], "withdrawal_policy": "void_all"}})
    assert v["summary"] == {"total": 10, "scheduled": 6, "forfeit": 0, "voided": 4}
    both = generate({**base, "params": {"withdrawals": [{"team_id": "t2", "after_round": 0}, {"team_id": "t5", "after_round": 0}]}})
    m = next(m for rd in both["rounds"] for m in rd["matches"] if {m["home"], m["away"]} == {"t2", "t5"})
    assert m["status"] == "voided" and m["awarded_to"] is None


@pytest.mark.parametrize("params", [{"legs": 3}, {"withdrawal_policy": "x"}, {"withdrawals": "x"},
                                    {"withdrawals": [{"team_id": "zz", "after_round": 1}]},
                                    {"withdrawals": [{"team_id": "t1", "after_round": 99}]}])
def test_round_robin_validation(params):
    assert err({"format": "round_robin", "teams": T(5), "params": params}).status == 400


@pytest.mark.parametrize("body", [{"format": "nope", "teams": T(4)}, {"format": "round_robin", "teams": ["t1"]},
                                  {"format": "round_robin", "teams": ["a", "a"]}, {"format": "swiss", "teams": "x"},
                                  {"format": "double_elim", "teams": T(2)}, {"format": "swiss", "teams": T(4), "params": 5}])
def test_envelope_validation(body):
    assert err(body).code == "VALIDATION_ERROR"


# ------------------------------------------------------------------ swiss
def test_swiss_spec_example():
    r = generate({"format": "swiss", "teams": T(5), "params": {"total_rounds": 3, "round": 2, "history": [
        {"round": 1, "bye": "t5", "matches": [{"home": "t1", "away": "t3", "result": "home"},
                                              {"home": "t2", "away": "t4", "result": "draw"}]}]}})
    assert r["bye"] == "t3"
    assert [(p["match_id"], p["home"], p["away"]) for p in r["pairings"]] == [("SW-R2-M1", "t1", "t2"), ("SW-R2-M2", "t5", "t4")]
    assert r["standings"][:3] == [{"rank": 1, "team_id": "t1", "score": 1.0, "buchholz": 0.0},
                                  {"rank": 2, "team_id": "t5", "score": 1.0, "buchholz": 0.0},
                                  {"rank": 3, "team_id": "t2", "score": 0.5, "buchholz": 0.5}]


@pytest.mark.parametrize("n", [2, 5, 6, 9])
def test_swiss_round_one_exact(n):
    r = generate({"format": "swiss", "teams": T(n)})
    m = n // 2
    assert r["total_rounds"] == max(1, math.ceil(math.log2(n)))
    assert [(p["home"], p["away"]) for p in r["pairings"]] == [(f"t{i}", f"t{i + m}") for i in range(1, m + 1)]
    assert r["bye"] == (f"t{n}" if n % 2 else None)


def _brute(players, score, played):
    best = None

    def rec(rem, c):
        nonlocal best
        if not rem:
            best = c if best is None or c < best else best
            return
        for b in rem[1:]:
            if frozenset((rem[0], b)) not in played:
                rec([x for x in rem if x not in (rem[0], b)], c + abs(score[rem[0]] - score[b]))
    rec(players, 0)
    return best


def test_swiss_simulation_optimal_and_rematch_free():
    rng = random.Random(11)
    no_pairing = 0
    for _ in range(60):
        n = rng.choice([4, 5, 6, 7, 8, 9])
        teams, hist = T(n), []
        for rnd in range(1, n):
            try:
                r = generate({"format": "swiss", "teams": teams, "params": {"total_rounds": n - 1, "round": rnd, "history": hist}})
            except ApiError as e:
                assert e.status == 409 and e.code == "NO_VALID_PAIRING" and e.details == {"round": rnd}
                no_pairing += 1
                break
            played = {frozenset((m["home"], m["away"])) for h in hist for m in h["matches"]}
            score = {s["team_id"]: s["score"] for s in r["standings"]}
            used = [x for p in r["pairings"] for x in (p["home"], p["away"])] + ([r["bye"]] if r["bye"] else [])
            assert sorted(used) == sorted(teams)
            assert all(frozenset((p["home"], p["away"])) not in played for p in r["pairings"])
            if rnd > 1:
                rest = [t for t in teams if t != r["bye"]]
                got = sum(abs(score[p["home"]] - score[p["away"]]) for p in r["pairings"])
                assert got == _brute(rest, score, played)
                if r["bye"]:
                    byes = {h["bye"] for h in hist}
                    assert r["bye"] not in byes or byes >= set(teams)
            hist.append({"round": rnd, "bye": r["bye"], "matches": [
                {"home": p["home"], "away": p["away"], "result": rng.choice(["home", "away", "draw"])} for p in r["pairings"]]})
    assert no_pairing > 0


def test_swiss_large_field_is_fast():
    rng = random.Random(5)
    teams, hist = T(64), []
    for rnd in range(1, 7):
        r = generate({"format": "swiss", "teams": teams, "params": {"round": rnd, "history": hist}})
        hist.append({"round": rnd, "bye": r["bye"], "matches": [
            {"home": p["home"], "away": p["away"], "result": rng.choice(["home", "away", "draw"])} for p in r["pairings"]]})
    assert r["total_rounds"] == 6 and len(r["pairings"]) == 32


@pytest.mark.parametrize("params", [{"total_rounds": 9}, {"round": 0}, {"round": 2, "history": []}, {"history": "x"},
                                    {"round": 2, "history": [{"round": 1, "matches": [{"home": "t1", "away": "zz", "result": "home"}]}]},
                                    {"round": 2, "history": [{"round": 1, "bye": "zz", "matches": []}]},
                                    {"round": 2, "history": [{"round": "1"}]}])
def test_swiss_validation(params):
    assert err({"format": "swiss", "teams": T(4), "params": params}).status == 400


def test_matching_against_brute_force():
    rng = random.Random(3)
    for _ in range(400):
        n = rng.choice([2, 4, 6, 8])
        cost = {(i, j): rng.choice([0, 1, 2, 4]) for i in range(n) for j in range(i + 1, n) if rng.random() < 0.6}
        res = min_cost_perfect_matching(n, cost)

        def brute(rem):
            if not rem:
                return 0
            best = None
            for b in rem[1:]:
                k = (rem[0], b)
                if k in cost:
                    sub = brute([x for x in rem if x not in k])
                    if sub is not None and (best is None or cost[k] + sub < best):
                        best = cost[k] + sub
            return best
        expected = brute(list(range(n)))
        assert (None if res is None else sum(cost[(min(a, b), max(a, b))] for a, b in res)) == expected
    assert min_cost_perfect_matching(0, {}) == [] and min_cost_perfect_matching(3, {(0, 1): 1}) is None
    assert max_weight_matching([]) == []
    assert max_weight_matching([(0, 1, 5), (1, 2, 6), (2, 3, 5)]) == [1, 0, 3, 2]
    assert max_weight_matching([(0, 1, 1), (1, 2, 9)]) == [-1, 2, 1]


# ------------------------------------------------------------------ single elimination
@pytest.mark.parametrize("n", list(range(2, 18)) + [33, 128])
def test_single_elim_structure(n):
    r = generate({"format": "single_elim", "teams": T(n), "params": {"third_place_match": True}})
    size = r["bracket_size"]
    assert size >= n > size // 2 and len(r["rounds"]) == int(math.log2(size))
    feeds = {}
    for rd in r["rounds"]:
        for m in rd["matches"]:
            for d in (m["winner_to"], m["loser_to"]):
                if d:
                    feeds[(d["match_id"], d["slot"])] = feeds.get((d["match_id"], d["slot"]), 0) + 1
    assert set(feeds.values()) <= {1}
    byes = [m for m in r["rounds"][0]["matches"] if m["bye"]]
    assert len(byes) == size - n and all(m["away"] is None and m["winner"] == m["home"] for m in byes)


def test_single_elim_spec_example_and_results():
    r = generate({"format": "single_elim", "teams": T(6), "params": {"results": [{"match_id": "R1M2", "winner": "t4"}]}})
    r1 = r["rounds"][0]["matches"]
    assert [(m["home"], m["away"], m["home_seed"], m["away_seed"], m["bye"]) for m in r1] == [
        ("t1", None, 1, None, True), ("t4", "t5", 4, 5, False), ("t2", None, 2, None, True), ("t3", "t6", 3, 6, False)]
    assert r1[1]["winner"] == "t4" and r1[1]["loser"] == "t5" and r1[1]["winner_to"] == {"match_id": "R2M1", "slot": "away"}
    r2 = r["rounds"][1]["matches"]
    assert (r2[0]["home"], r2[0]["away"], r2[1]["home"]) == ("t1", "t4", "t2")
    full = generate({"format": "single_elim", "teams": T(4), "params": {"third_place_match": True, "results": [
        {"match_id": "R1M1", "winner": "t1"}, {"match_id": "R1M2", "winner": "t3"}, {"match_id": "TP", "winner": "t4"},
        {"match_id": "R2M1", "winner": "t3"}]}})
    final, tp = full["rounds"][1]["matches"]
    assert final["winner"] == "t3" and final["winner_to"] is None
    assert tp["match_id"] == "TP" and tp["bracket"] == "third_place" and (tp["home"], tp["away"], tp["winner"]) == ("t4", "t2", "t4")


@pytest.mark.parametrize("results", [[{"match_id": "R9M9", "winner": "t1"}], [{"match_id": "R1M2", "winner": "t1"}],
                                     [{"match_id": "R2M1", "winner": "t1"}], [{"match_id": "R1M1", "winner": "t8"}], "x",
                                     [{"match_id": "R1M1"}]])
def test_single_elim_bad_results(results):
    assert err({"format": "single_elim", "teams": T(6), "params": {"results": results}}).status == 400


def test_single_elim_bad_flag():
    assert err({"format": "single_elim", "teams": T(6), "params": {"third_place_match": "yes"}}).status == 400


# ------------------------------------------------------------------ double elimination
@pytest.mark.parametrize("n", list(range(3, 18)) + [33, 128])
@pytest.mark.parametrize("reset", [True, False])
def test_double_elim_structure(n, reset):
    r = generate({"format": "double_elim", "teams": T(n), "params": {"bracket_reset": reset}})
    size, k = r["bracket_size"], int(math.log2(r["bracket_size"]))
    losers = [m for rd in r["losers"] for m in rd["matches"]]
    assert len(losers) == size - 2 and len(r["losers"]) == 2 * (k - 1)
    for j in range(1, k):
        assert len(r["losers"][2 * j - 2]["matches"]) == len(r["losers"][2 * j - 1]["matches"]) == size // 2 ** (j + 1)
    allm = [m for rd in r["winners"] for m in rd["matches"]] + losers + r["grand_final"]
    assert [m["match_id"] for m in r["grand_final"]] == (["GF1", "GF2"] if reset else ["GF1"])
    feeds = {}
    for m in allm:
        assert (m["loser_to"] is not None) == (m["bracket"] == "winners" or (m["match_id"] == "GF1" and reset))
        for d in (m["winner_to"], m["loser_to"]):
            if d:
                feeds[(d["match_id"], d["slot"])] = feeds.get((d["match_id"], d["slot"]), 0) + 1
    slots = {(m["match_id"], s) for m in allm if not (m["bracket"] == "winners" and m["round"] == 1) for s in ("home", "away")}
    assert set(feeds) == slots and set(feeds.values()) == {1}
    wr_final = r["winners"][-1]["matches"][0]
    assert wr_final["winner_to"] == {"match_id": "GF1", "slot": "home"}
    assert wr_final["loser_to"] == {"match_id": f"LR{2 * k - 2}M1", "slot": "away"}
    assert r["losers"][-1]["matches"][0]["winner_to"] == {"match_id": "GF1", "slot": "away"}


def test_double_elim_bracket_reset_logic():
    res = [{"match_id": "WR1M1", "winner": "t1"}, {"match_id": "WR1M2", "winner": "t2"}, {"match_id": "WR2M1", "winner": "t1"},
           {"match_id": "LR1M1", "winner": "t3"}, {"match_id": "LR2M1", "winner": "t3"}]
    before = generate({"format": "double_elim", "teams": T(4), "params": {"bracket_reset": True, "results": res}})
    gf1, gf2 = before["grand_final"]
    assert (gf1["home"], gf1["away"]) == ("t1", "t3") and gf2["conditional"] is True and gf2["required"] is None
    assert {gf2["home"], gf2["away"]} == {"t1", "t3"}
    lb_wins = generate({"format": "double_elim", "teams": T(4), "params": {"bracket_reset": True,
                                                                           "results": res + [{"match_id": "GF1", "winner": "t3"}]}})
    assert lb_wins["grand_final"][1]["required"] is True
    wb_wins = generate({"format": "double_elim", "teams": T(4), "params": {"bracket_reset": True,
                                                                           "results": res + [{"match_id": "GF1", "winner": "t1"}]}})
    assert wb_wins["grand_final"][1]["required"] is False
    no_reset = generate({"format": "double_elim", "teams": T(4), "params": {"results": res + [{"match_id": "GF1", "winner": "t1"}]}})
    assert len(no_reset["grand_final"]) == 1 and no_reset["grand_final"][0]["winner_to"] is None


def test_double_elim_byes_propagate_into_losers_bracket():
    r = generate({"format": "double_elim", "teams": T(5), "params": {"results": [
        {"match_id": "WR1M2", "winner": "t4"}, {"match_id": "LR1M1", "winner": "t5"}]}})
    lr1 = r["losers"][0]["matches"]
    assert lr1[0]["away"] == "t5" or lr1[0]["home"] == "t5"


def test_double_elim_validation():
    assert err({"format": "double_elim", "teams": T(4), "params": {"bracket_reset": 1}}).status == 400
    assert err({"format": "double_elim", "teams": T(4), "params": {"results": [{"match_id": "GF1", "winner": "t1"}]}}).status == 400
