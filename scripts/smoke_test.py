#!/usr/bin/env python3
"""Grader replica. Usage: DAY1_SALT=<salt used for compose> python3 scripts/smoke_test.py [base_url]

Stdlib only (urllib + threads) so it runs anywhere with Python 3.11+.
"""
import hashlib
import hmac
import json
import os
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
SALT = os.environ.get("DAY1_SALT", "demo-salt")
results = {"pass": 0, "fail": 0}


def canonical(o):
    return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sign(id_, payload):
    return hmac.new(SALT.encode(), (id_ + "|" + canonical(payload)).encode(), hashlib.sha256).hexdigest()


def call(method, path, body=None, headers=None, raw=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            txt = r.read().decode()
            return r.status, (json.loads(txt) if txt else None), dict(r.headers)
    except urllib.error.HTTPError as e:
        txt = e.read().decode()
        try:
            return e.code, json.loads(txt), dict(e.headers)
        except ValueError:
            return e.code, txt, dict(e.headers)


def check(name, cond, info=""):
    results["pass" if cond else "fail"] += 1
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  -> {info}"))


def code_of(body):
    return body.get("error", {}).get("code") if isinstance(body, dict) else None


def ev(eid, mid, etype, payload):
    return call("POST", "/audit/v1/events", {"event_id": eid, "match_id": mid, "type": etype, "payload": payload})


def test_basics():
    s, b, _ = call("GET", "/health")
    check("health 200", s == 200 and b == {"status": "ok"}, (s, b))
    s1, b1, _ = call("POST", "/audit/v1/reset", {})
    s2, b2, _ = call("POST", "/audit/v1/reset")
    check("reset twice identical", s1 == s2 == 200 and b1 == b2, (s1, b1, b2))
    check("reset body", b1 == {"status": "reset_complete", "seed": 42,
                               "sports": ["football", "basketball", "cricket", "esports"],
                               "tenants": ["tenant-alpha", "tenant-beta"],
                               "stock": {"var-jersey-001-M": 1, "var-jersey-001-L": 5}}, b1)
    s, b, _ = call("POST", "/audit/v1/reset", {"seed": 7, "stock": {"var-jersey-001-M": 3}})
    check("reset custom", s == 200 and b["seed"] == 7 and b["stock"]["var-jersey-001-M"] == 3, b)
    s, b, _ = call("POST", "/audit/v1/reset", raw=b"{bad json")
    check("malformed json 400", s == 400 and code_of(b) == "VALIDATION_ERROR", (s, b))
    s, b, _ = call("POST", "/audit/v1/events", raw=b"x" * (1024 * 1024 + 10))
    check("413 body too large", s == 413 and code_of(b) == "PAYLOAD_TOO_LARGE", (s, b))
    call("POST", "/audit/v1/reset", {})


def test_scoring():
    s, b, _ = call("POST", "/audit/v1/sports", {"sport_id": "x'; DROP TABLE sports;--", "name": "x"})
    check("sql-ish sport id 400", s == 400 and code_of(b) == "VALIDATION_ERROR" and "sport_id" in b["error"]["details"]["fields"], b)
    kabaddi = {"sport_id": "kabaddi", "name": "Kabaddi", "scoring_model": "event",
               "periods": {"count": 2, "duration_minutes": 20},
               "scoring_events": {"raid_point": {"points": 1}, "tackle_point": {"points": 1}, "all_out": {"points": 2}},
               "draw_allowed": False, "overtime": {"policy": "golden_score", "duration_minutes": 5},
               "tie_break_order": ["h2h_points", "h2h_diff", "overall_diff", "scored", "fair_play", "draw_lots"],
               "roster": {"min_squad_size": 7, "max_squad_size": 12, "required_positions": {"raider": 2, "defender": 3}}}
    s, b, _ = call("POST", "/audit/v1/sports", kabaddi)
    check("mystery sport 201", s == 201 and b["status"] == "created" and b["config"]["sport_id"] == "kabaddi", (s, b))
    s, b, _ = call("POST", "/audit/v1/sports", kabaddi)
    check("sport exists 409", s == 409 and code_of(b) == "SPORT_EXISTS", (s, b))

    s, b, _ = ev("k-0", "km1", "match_init", {"sport_id": "nope", "home_team_id": "a", "away_team_id": "b"})
    check("init unknown sport 404", s == 404 and code_of(b) == "SPORT_NOT_FOUND", (s, b))
    s, b, _ = ev("k-1", "km1", "match_init", {"sport_id": "kabaddi", "home_team_id": "a", "away_team_id": "b"})
    check("init 201", s == 201 and b["sequence"] == 1 and b["match_version"] == 1, (s, b))
    s, b, _ = ev("k-1b", "km1", "match_init", {"sport_id": "kabaddi", "home_team_id": "a", "away_team_id": "b"})
    check("init existing 409", s == 409 and code_of(b) == "MATCH_EXISTS", (s, b))
    s, b, _ = ev("k-2", "km1", "score", {"team_id": "a", "event_type": "raid_point"})
    check("score before start 409", s == 409 and code_of(b) == "MATCH_NOT_IN_PROGRESS", (s, b))
    s, b, _ = ev("k-2", "km1", "match_start", {})
    check("start 201", s == 201 and b["sequence"] == 2, (s, b))
    s, b, _ = ev("k-2", "km1", "match_start", {})
    check("idempotent replay 200", s == 200 and b["sequence"] == 2, (s, b))
    s, b, _ = ev("k-2", "km1", "match_end", {})
    check("duplicate event id 409", s == 409 and code_of(b) == "DUPLICATE_EVENT_ID", (s, b))
    s, b, _ = ev("k-3", "km1", "score", {"team_id": "a", "event_type": "goal"})
    check("unknown event type 400", s == 400 and code_of(b) == "UNKNOWN_EVENT_TYPE", (s, b))
    s, b, _ = ev("k-3", "km1", "score", {"team_id": "zzz", "event_type": "raid_point"})
    check("foreign team 400", s == 400, (s, b))
    s, b, _ = ev("k-3", "km1", "score", {"team_id": "a", "event_type": "all_out"})
    check("score signature", s == 201 and b["signature"] == sign("k-3", {"team_id": "a", "event_type": "all_out"}), b)
    ev("k-4", "km1", "score", {"team_id": "b", "event_type": "raid_point"})
    ev("k-5", "km1", "discipline", {"team_id": "b", "points": -1})
    s, b, _ = ev("k-6", "km1", "compensation", {"compensates": "k-3", "reason": "disallowed"})
    check("compensation 201", s == 201, (s, b))
    s, b, _ = ev("k-7", "km1", "compensation", {"compensates": "k-3", "reason": "again"})
    check("double compensation 409", s == 409 and code_of(b) == "INVALID_COMPENSATION", (s, b))
    s, b, _ = ev("k-7", "km1", "compensation", {"compensates": "k-404", "reason": "x"})
    check("compensate unknown 404", s == 404 and code_of(b) == "EVENT_NOT_FOUND", (s, b))
    s, b, _ = ev("k-7", "km1", "compensation", {"compensates": "k-2", "reason": "x"})
    check("compensate start 409", s == 409 and code_of(b) == "INVALID_COMPENSATION", (s, b))
    s, b, _ = ev("k-7", "km1", "match_end", {})
    check("end while behind ok 201", s == 201, (s, b))
    s, b, _ = call("GET", "/audit/v1/score/km1")
    check("score projection", s == 200 and b["status"] == "completed" and b["home"]["score"] == 0
          and b["away"]["score"] == 1 and b["outcome"] == "away_win" and b["winner_team_id"] == "b"
          and b["away"]["fair_play"] == -1 and b["version"] == 7 and b["events"][2]["compensated"] is True
          and b["events"][2]["compensated_by"] == "k-6" and b["home"]["wickets"] is None, b)
    # compensate the only point after completion -> level, no draw -> undecided
    ev("k-8", "km1", "compensation", {"compensates": "k-4", "reason": "VAR"})
    s, b, _ = call("GET", "/audit/v1/score/km1")
    check("undecided after compensation", b["outcome"] == "undecided" and b["winner_team_id"] is None, b)
    s, b, _ = call("GET", "/audit/v1/score/nope")
    check("score unknown 404", s == 404 and code_of(b) == "MATCH_NOT_FOUND", (s, b))

    # innings model
    ev("c-1", "cm1", "match_init", {"sport_id": "cricket", "home_team_id": "h", "away_team_id": "a"})
    ev("c-2", "cm1", "match_start", {})
    for i, et in enumerate(["four", "wide", "wicket", "six", "dot_ball", "single", "two"]):
        ev(f"c-s{i}", "cm1", "score", {"team_id": "h", "event_type": et})
    s, b, _ = call("GET", "/audit/v1/score/cm1")
    check("innings projection", b["home"]["score"] == 14 and b["home"]["wickets"] == 1 and b["home"]["balls"] == 6
          and b["home"]["overs"] == "1.0" and b["away"]["overs"] == "0.0", b["home"])
    # round model + series decided
    ev("e-1", "em1", "match_init", {"sport_id": "esports", "home_team_id": "h", "away_team_id": "a"})
    ev("e-2", "em1", "match_start", {})
    ev("e-3", "em1", "score", {"team_id": "h", "event_type": "round_win"})
    ev("e-4", "em1", "score", {"team_id": "h", "event_type": "round_win"})
    s, b, _ = ev("e-5", "em1", "score", {"team_id": "a", "event_type": "round_win"})
    check("series decided 409", s == 409 and code_of(b) == "SERIES_ALREADY_DECIDED", (s, b))
    # tie not allowed (basketball)
    ev("b-1", "bm1", "match_init", {"sport_id": "basketball", "home_team_id": "h", "away_team_id": "a"})
    ev("b-2", "bm1", "match_start", {})
    s, b, _ = ev("b-3", "bm1", "match_end", {})
    check("tie not allowed 409", s == 409 and code_of(b) == "TIE_NOT_ALLOWED", (s, b))
    ev("b-4", "bm1", "tiebreak_winner", {"team_id": "a"})
    s, b, _ = ev("b-5", "bm1", "match_end", {})
    s, b, _ = call("GET", "/audit/v1/score/bm1")
    check("tiebreak winner", b["outcome"] == "away_win" and b["tiebreak_winner_team_id"] == "a", b)
    s, b, _ = ev("b-6", "bm1", "match_start", {})
    check("illegal transition 409", s == 409 and code_of(b) == "ILLEGAL_TRANSITION", (s, b))
    s, b, _ = ev("b-7", "nope", "match_start", {})
    check("event on missing match 404", s == 404 and code_of(b) == "MATCH_NOT_FOUND", (s, b))


def test_fixtures():
    s, b, _ = call("POST", "/audit/v1/fixtures", {"format": "round_robin", "teams": ["t1", "t2", "t3", "t4", "t5"],
                                                 "params": {"legs": 1, "withdrawals": [{"team_id": "t3", "after_round": 2}],
                                                            "withdrawal_policy": "forfeit_remaining"}})
    check("rr example", s == 200 and b["round_count"] == 5 and b["rounds"][0]["byes"] == ["t1"]
          and b["summary"] == {"total": 10, "scheduled": 8, "forfeit": 2, "voided": 0}, (s, b.get("summary")))
    s, b, _ = call("POST", "/audit/v1/fixtures", {"format": "round_robin", "teams": ["t1"], "params": {}})
    check("rr 1 team 400", s == 400, (s, b))
    s, b, _ = call("POST", "/audit/v1/fixtures", {"format": "swiss", "teams": ["t1", "t2", "t3", "t4", "t5"],
                                                 "params": {"total_rounds": 3, "round": 2, "history": [
                                                     {"round": 1, "bye": "t5", "matches": [
                                                         {"home": "t1", "away": "t3", "result": "home"},
                                                         {"home": "t2", "away": "t4", "result": "draw"}]}]}})
    check("swiss example", s == 200 and b["bye"] == "t3" and [(p["home"], p["away"]) for p in b["pairings"]] ==
          [("t1", "t2"), ("t5", "t4")] and b["standings"][2] == {"rank": 3, "team_id": "t2", "score": 0.5, "buchholz": 0.5}, b)
    s, b, _ = call("POST", "/audit/v1/fixtures", {"format": "swiss", "teams": ["a", "b", "c", "d"], "params": {
        "total_rounds": 3, "round": 3, "history": [
            {"round": 1, "bye": None, "matches": [{"home": "a", "away": "b", "result": "home"}, {"home": "c", "away": "d", "result": "home"}]},
            {"round": 2, "bye": None, "matches": [{"home": "a", "away": "c", "result": "home"}, {"home": "b", "away": "d", "result": "home"}]}]}})
    check("swiss round 3 of 4", s == 200 and len(b["pairings"]) == 2, (s, b))
    s, b, _ = call("POST", "/audit/v1/fixtures", {"format": "single_elim", "teams": ["t1", "t2", "t3", "t4", "t5", "t6"],
                                                 "params": {"third_place_match": False, "results": [{"match_id": "R1M2", "winner": "t4"}]}})
    r1 = b["rounds"][0]["matches"]
    check("single elim example", s == 200 and b["bracket_size"] == 8 and r1[0]["bye"] and r1[0]["away"] is None
          and r1[1]["home"] == "t4" and r1[1]["winner"] == "t4" and b["rounds"][1]["matches"][0]["home"] == "t1"
          and b["rounds"][1]["matches"][0]["away"] == "t4" and r1[1]["winner_to"] == {"match_id": "R2M1", "slot": "away"}, r1[:2])
    s, b, _ = call("POST", "/audit/v1/fixtures", {"format": "double_elim", "teams": [f"t{i}" for i in range(1, 9)],
                                                 "params": {"bracket_reset": True, "results": [{"match_id": "WR1M1", "winner": "t1"}]}})
    lr = [m for r in b["losers"] for m in r["matches"]]
    check("double elim shape", s == 200 and len(lr) == 6 and len(b["grand_final"]) == 2
          and b["grand_final"][1]["conditional"] is True and b["grand_final"][1]["required"] is None, (s, len(lr)))


def _play(mid, goals_home, goals_away, home, away, prefix):
    ev(f"{prefix}-s", mid, "match_start", {})
    for i in range(goals_home):
        ev(f"{prefix}-h{i}", mid, "score", {"team_id": home, "event_type": "goal"})
    for i in range(goals_away):
        ev(f"{prefix}-a{i}", mid, "score", {"team_id": away, "event_type": "goal"})
    ev(f"{prefix}-e", mid, "match_end", {})


def test_standings():
    games = [("m1", "t1", "t2", 1, 0), ("m2", "t2", "t3", 1, 0), ("m3", "t3", "t1", 1, 0),
             ("m4", "t1", "t4", 2, 0), ("m5", "t2", "t4", 3, 0), ("m6", "t3", "t4", 1, 0)]
    s, b, _ = call("POST", "/audit/v1/leagues", {"league_id": "lg-1", "sport_id": "football", "teams": ["t1", "t2", "t3", "t4"],
                                                "fixtures": [{"match_id": m, "home": h, "away": a} for m, h, a, _, _ in games],
                                                "points": {"win": 3, "draw": 1, "loss": 0}, "qualification": {"spots": 2}, "lots_seed": 42})
    check("league 201", s == 201 and b == {"league_id": "lg-1", "status": "created", "team_count": 4, "fixture_count": 6}, (s, b))
    s, b, _ = call("POST", "/audit/v1/leagues", {"league_id": "lg-1", "sport_id": "football", "teams": ["t1", "t2"],
                                                "fixtures": [], "qualification": {"spots": 1}})
    check("league exists 409", s == 409 and code_of(b) == "LEAGUE_EXISTS", (s, b))
    s, b, _ = call("POST", "/audit/v1/leagues", {"league_id": "lg-x", "sport_id": "nope", "teams": ["t1", "t2"],
                                                "fixtures": [], "qualification": {"spots": 1}})
    check("league sport 404", s == 404 and code_of(b) == "SPORT_NOT_FOUND", (s, b))
    s, b, _ = call("POST", "/audit/v1/leagues", {"league_id": "lg-y", "sport_id": "football", "teams": ["t1", "t2"],
                                                "fixtures": [{"match_id": "m1", "home": "t1", "away": "t2"}], "qualification": {"spots": 1}})
    check("league match exists 409", s == 409 and code_of(b) == "MATCH_EXISTS", (s, b))
    s, b, _ = call("GET", "/audit/v1/standings/lg-1")
    check("standings before play", s == 200 and all(r["status"] == "still_possible" for r in b["table"]), b["table"])
    for m, h, a, gh, ga in games:
        _play(m, gh, ga, h, a, m)
    s, b, _ = call("GET", "/audit/v1/standings/lg-1")
    order = [(r["team_id"], r["points"], r["resolved_by"], r["status"]) for r in b["table"]]
    check("3-way tie overall_diff", order == [("t2", 6, "overall_diff", "still_possible"), ("t1", 6, "overall_diff", "still_possible"),
                                             ("t3", 6, None, "still_possible"), ("t4", 0, None, "eliminated")], order)
    check("h2h", b["h2h"]["t1"]["t2"] == {"played": 1, "points": 3, "scored": 1, "conceded": 0}
          and b["h2h"]["t2"]["t1"]["points"] == 0, b["h2h"]["t1"])
    ev("m3-comp", "m3", "compensation", {"compensates": "m3-h0", "reason": "offside"})
    s, b, _ = call("GET", "/audit/v1/standings/lg-1")
    order = [(r["team_id"], r["points"], r["status"]) for r in b["table"]]
    check("compensation after qualification", order == [("t1", 7, "clinched"), ("t2", 6, "clinched"),
                                                         ("t3", 4, "eliminated"), ("t4", 0, "eliminated")], order)
    call("POST", "/audit/v1/leagues", {"league_id": "lg-lots", "sport_id": "football", "teams": ["t1", "t2", "t3"],
                                      "fixtures": [], "qualification": {"spots": 1}, "lots_seed": 42})
    # league_id lg-1 is the vector's league; draw_lots keys depend on league id, so use a fresh reset league
    call("POST", "/audit/v1/reset", {})
    call("POST", "/audit/v1/leagues", {"league_id": "lg-1", "sport_id": "football", "teams": ["t1", "t2", "t3"],
                                      "fixtures": [], "qualification": {"spots": 1}})
    s, b, _ = call("GET", "/audit/v1/standings/lg-1")
    order = [(r["team_id"], r["resolved_by"]) for r in b["table"]]
    check("draw lots vector 2", order == [("t1", "draw_lots"), ("t3", "draw_lots"), ("t2", None)], order)
    s, b, _ = call("GET", "/audit/v1/standings/nope")
    check("standings 404", s == 404 and code_of(b) == "LEAGUE_NOT_FOUND", (s, b))


def _pdf_text(pdf_bytes):
    import re
    import zlib
    out = pdf_bytes
    for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", pdf_bytes, re.S):
        try:
            out += zlib.decompress(m.group(1))
        except zlib.error:
            pass
    return out


def test_store():
    import base64
    import threading
    call("POST", "/audit/v1/reset", {"stock": {"var-jersey-001-M": 1, "var-jersey-001-L": 5}})
    barrier = threading.Barrier(20)
    out = []

    def buy(i):
        body = {"order_id": f"ord-race-{i}", "customer_id": f"cust-{i}",
                "items": [{"variant_id": "var-jersey-001-M", "quantity": 1}], "discount_code": None,
                "payment": {"token": "tok_success"}}
        barrier.wait()
        out.append(call("POST", "/audit/v1/checkout", body) + (body,))

    ths = [threading.Thread(target=buy, args=(i,)) for i in range(20)]
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    codes = sorted(o[0] for o in out)
    check("20 buyers: one 201, nineteen 409", codes == [201] + [409] * 19, codes)
    check("409 code OUT_OF_STOCK", all(code_of(o[1]) == "OUT_OF_STOCK" for o in out if o[0] == 409))
    s, b, _ = call("GET", "/audit/v1/inventory/var-jersey-001-M")
    check("stock 0 reserved 0", b == {"variant_id": "var-jersey-001-M", "stock": 0, "reserved": 0}, b)
    win = next(o for o in out if o[0] == 201)
    body, resp = win[3], win[1]
    check("receipt signature", resp["receipt"]["signature"] == sign(body["order_id"], resp["receipt"]["payload"]), resp["receipt"]["payload"])
    pdf = base64.b64decode(resp["receipt"]["pdf_base64"])
    txt = _pdf_text(pdf)
    check("pdf valid + text", pdf.startswith(b"%PDF") and body["order_id"].encode() in txt and b"PKR 4500.00" in txt)
    s, b, _ = call("POST", "/audit/v1/checkout", body)
    check("checkout replay 200 same body", s == 200 and b == resp, s)
    s, b, _ = call("POST", "/audit/v1/checkout", {**body, "customer_id": "someone-else"})
    check("duplicate order id 409", s == 409 and code_of(b) == "DUPLICATE_ORDER_ID", (s, b))

    base = {"customer_id": "c-1", "items": [{"variant_id": "var-jersey-001-L", "quantity": 2}], "discount_code": None}
    s, b, _ = call("POST", "/audit/v1/checkout", {**base, "order_id": "o-dec", "payment": {"token": "tok_declined"}})
    check("declined 402", s == 402 and code_of(b) == "PAYMENT_DECLINED", (s, b))
    s, b, _ = call("POST", "/audit/v1/checkout", {**base, "order_id": "o-cap", "payment": {"token": "tok_capture_fail"}})
    check("capture fail 402", s == 402 and code_of(b) == "PAYMENT_CAPTURE_FAILED", (s, b))
    s, b, _ = call("GET", "/audit/v1/inventory/var-jersey-001-L")
    check("stock released after 402", b["stock"] == 5 and b["reserved"] == 0, b)
    s, b, _ = call("POST", "/audit/v1/checkout", {**base, "order_id": "o-disc", "discount_code": "WELCOME10",
                                                  "customer_id": "c'\"<script>alert(1)</script>", "payment": {"token": "tok_success"}})
    check("discount + odd customer", s == 201 and b["subtotal_minor"] == 900000 and b["discount_minor"] == 90000
          and b["total_minor"] == 810000 and b["receipt"]["payload"]["customer_id"] == "c'\"<script>alert(1)</script>", (s, b))
    s, b, _ = call("POST", "/audit/v1/checkout", {**base, "order_id": "o-bad", "discount_code": "NOPE", "payment": {"token": "tok_success"}})
    check("invalid discount 400", s == 400 and code_of(b) == "INVALID_DISCOUNT_CODE", (s, b))
    s, b, _ = call("POST", "/audit/v1/checkout", {**base, "order_id": "o-404", "items": [{"variant_id": "var-nope", "quantity": 1}],
                                                  "payment": {"token": "tok_success"}})
    check("unknown variant 404", s == 404 and code_of(b) == "VARIANT_NOT_FOUND", (s, b))
    s, b, _ = call("POST", "/audit/v1/checkout", {**base, "order_id": "o-q", "items": [{"variant_id": "var-jersey-001-L", "quantity": 11}],
                                                  "payment": {"token": "tok_success"}})
    check("quantity 11 400", s == 400 and code_of(b) == "VALIDATION_ERROR", (s, b))
    s, b, _ = call("GET", "/audit/v1/inventory/nope")
    check("inventory 404", s == 404 and code_of(b) == "VARIANT_NOT_FOUND", (s, b))


GROUPS = [test_basics, test_scoring, test_fixtures, test_standings, test_store]

if __name__ == "__main__":
    only = os.environ.get("ONLY")
    for g in GROUPS:
        if only and only not in g.__name__:
            continue
        print(f"== {g.__name__}")
        call("POST", "/audit/v1/reset", {})
        g()
    print(f"\n{results['pass']} passed, {results['fail']} failed")
    sys.exit(1 if results["fail"] else 0)
