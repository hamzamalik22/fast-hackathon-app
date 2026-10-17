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


GROUPS = [test_basics, test_scoring]

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
