"""Sport rule sets as data (FR-1.1). Nothing here knows any sport or event name."""
import re

from ..validation import Fields, is_int

SPORT_ID_RE = re.compile(r"[a-z0-9_-]{2,40}")
EVENT_KEY_RE = re.compile(r"[a-z0-9_]{1,40}")
MODELS = ("event", "innings", "round")
OVERTIME_POLICIES = ("none", "extra_time", "shootout", "golden_score", "super_over")
TIE_BREAK_TOKENS = ["h2h_points", "h2h_diff", "overall_diff", "scored", "fair_play", "draw_lots"]
INNINGS_PERIOD_KEYS = ("innings_per_team", "overs_per_innings", "balls_per_over", "wickets_per_innings")


def _valid_tie_break_order(v) -> bool:
    return (isinstance(v, list) and all(isinstance(t, str) and t in TIE_BREAK_TOKENS for t in v)
            and len(set(v)) == len(v))


def validate_tie_break_order(v, f: Fields, name: str = "tie_break_order") -> list | None:
    if v is None:
        return None
    if not _valid_tie_break_order(v):
        f.add(name)
        return None
    return list(v)


def effective_tie_break_order(order: list | None) -> list:
    """draw_lots is always applied last, even if omitted."""
    order = list(order) if order else list(TIE_BREAK_TOKENS)
    order = [t for t in order if t != "draw_lots"]
    return order + ["draw_lots"]


def validate_sport(b: dict) -> dict:
    """Validate a POST /sports body and return the normalized config that gets stored and echoed."""
    f = Fields()
    sid = b.get("sport_id")
    if not (isinstance(sid, str) and SPORT_ID_RE.fullmatch(sid)):
        f.add("sport_id")
    name = b.get("name")
    if not (isinstance(name, str) and 1 <= len(name) <= 80):
        f.add("name")
    model = b.get("scoring_model")
    if model not in MODELS:
        f.add("scoring_model")
        model = None

    periods_in = b.get("periods")
    periods = None
    if not isinstance(periods_in, dict):
        f.add("periods")
    elif model == "event":
        c, d = periods_in.get("count"), periods_in.get("duration_minutes")
        if not (is_int(c) and c >= 1):
            f.add("periods", "periods.count")
        if not (is_int(d) and d >= 1):
            f.add("periods", "periods.duration_minutes")
        periods = {"count": c, "duration_minutes": d}
    elif model == "innings":
        periods = {}
        for k in INNINGS_PERIOD_KEYS:
            v = periods_in.get(k)
            if not (is_int(v) and v >= 1):
                f.add("periods", f"periods.{k}")
            periods[k] = v
    elif model == "round":
        bo = periods_in.get("best_of")
        if not (is_int(bo) and bo >= 1 and bo % 2 == 1):
            f.add("periods", "periods.best_of")
        periods = {"best_of": bo}

    se_in = b.get("scoring_events")
    scoring_events = {}
    if not isinstance(se_in, dict) or not se_in:
        f.add("scoring_events")
    else:
        for key, val in se_in.items():
            path = f"scoring_events.{key}"
            if not EVENT_KEY_RE.fullmatch(key) or not isinstance(val, dict):
                f.add("scoring_events", path)
                continue
            if model == "event":
                p = val.get("points")
                if not (is_int(p) and p >= 1):
                    f.add("scoring_events", path)
                scoring_events[key] = {"points": p}
            elif model == "innings":
                r, lb, w = val.get("runs"), val.get("legal_ball"), val.get("wicket")
                if not (is_int(r) and r >= 0) or not isinstance(lb, bool) or not isinstance(w, bool):
                    f.add("scoring_events", path)
                scoring_events[key] = {"runs": r, "legal_ball": lb, "wicket": w}
            elif model == "round":
                r = val.get("rounds")
                if not (is_int(r) and r >= 1):
                    f.add("scoring_events", path)
                scoring_events[key] = {"rounds": r}

    draw = b.get("draw_allowed")
    if not isinstance(draw, bool):
        f.add("draw_allowed")

    ot_in = b.get("overtime")
    overtime = None
    if not isinstance(ot_in, dict) or ot_in.get("policy") not in OVERTIME_POLICIES:
        f.add("overtime")
    else:
        overtime = {"policy": ot_in["policy"]}
        if "duration_minutes" in ot_in and ot_in["duration_minutes"] is not None:
            dm = ot_in["duration_minutes"]
            if not (is_int(dm) and dm >= 0):
                f.add("overtime", "overtime.duration_minutes")
            overtime["duration_minutes"] = dm

    tbo = validate_tie_break_order(b.get("tie_break_order"), f)

    roster_in = b.get("roster")
    roster = None
    if not isinstance(roster_in, dict):
        f.add("roster")
    else:
        mn, mx = roster_in.get("min_squad_size"), roster_in.get("max_squad_size")
        rp = roster_in.get("required_positions", {})
        if not (is_int(mn) and mn >= 1):
            f.add("roster", "roster.min_squad_size")
        if not (is_int(mx) and mx >= 1):
            f.add("roster", "roster.max_squad_size")
        if is_int(mn) and is_int(mx) and mn > mx:
            f.add("roster", "roster.min_squad_size", "roster.max_squad_size")
        if not (isinstance(rp, dict) and all(isinstance(k, str) and k and is_int(v) and v >= 0 for k, v in rp.items())):
            f.add("roster", "roster.required_positions")
        roster = {"min_squad_size": mn, "max_squad_size": mx,
                  "required_positions": dict(rp) if isinstance(rp, dict) else {}}

    f.check()
    return {
        "sport_id": sid,
        "name": name,
        "scoring_model": model,
        "periods": periods,
        "scoring_events": scoring_events,
        "draw_allowed": draw,
        "overtime": overtime,
        "tie_break_order": tbo if tbo is not None else list(TIE_BREAK_TOKENS),
        "roster": roster,
    }
