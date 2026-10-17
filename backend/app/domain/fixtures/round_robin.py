"""Round robin by the circle method (single/double legs, byes, withdrawals). Spec 5.7-A.

Orientation rule (verified for n = 2..40): the fixed team alternates home/away by round; in every other
pair the upper-half team is home. Gives |home-away| <= 1 per team per leg (exact balance for odd n).
"""
from ...validation import Fields, is_int

POLICIES = ("void_all", "forfeit_remaining")


def circle_rounds(teams: list) -> list[list[tuple]]:
    arr = list(teams) + ([None] if len(teams) % 2 else [])
    n = len(arr)
    rounds = []
    for r in range(n - 1):
        pairs = []
        for i in range(n // 2):
            a, b = arr[i], arr[n - 1 - i]
            if i == 0:
                pairs.append((a, b) if r % 2 == 0 else (b, a))
            else:
                pairs.append((a, b))
        rounds.append(pairs)
        arr = [arr[0], arr[-1]] + arr[1:-1]
    return rounds


def generate(teams: list, params: dict) -> dict:
    f = Fields()
    legs = params.get("legs", 1)
    legs = 1 if legs is None else legs
    if not is_int(legs) or legs not in (1, 2):
        f.add("params.legs")
    policy = params.get("withdrawal_policy") or "forfeit_remaining"
    if policy not in POLICIES:
        f.add("params.withdrawal_policy")
    withdrawals = params.get("withdrawals")
    withdrawals = [] if withdrawals is None else withdrawals
    if not isinstance(withdrawals, list):
        f.add("params.withdrawals")
    f.check()

    n = len(teams)
    per_leg = n - 1 if n % 2 == 0 else n
    round_count = per_leg * legs
    out_after: dict[str, int] = {}
    for w in withdrawals:
        if (not isinstance(w, dict) or w.get("team_id") not in teams or not is_int(w.get("after_round"))
                or not 0 <= w["after_round"] <= round_count):
            f.add("params.withdrawals")
            continue
        out_after[w["team_id"]] = w["after_round"]
    f.check()

    base = circle_rounds(teams)
    rounds = []
    summary = {"total": 0, "scheduled": 0, "forfeit": 0, "voided": 0}
    for leg in range(1, legs + 1):
        for r_idx, pairs in enumerate(base):
            rnd = (leg - 1) * per_leg + r_idx + 1
            matches, byes, idx = [], [], 0
            for h, a in pairs:
                if h is None or a is None:
                    byes.append(h if a is None else a)
                    continue
                if leg == 2:
                    h, a = a, h
                idx += 1
                status, awarded = _status(h, a, rnd, policy, out_after)
                matches.append({"match_id": f"RR-L{leg}-R{rnd}-M{idx}", "leg": leg, "home": h, "away": a,
                                "status": status, "awarded_to": awarded})
                summary["total"] += 1
                summary[status] += 1
            rounds.append({"round": rnd, "matches": matches, "byes": byes})
    return {"format": "round_robin", "legs": legs, "team_count": n, "round_count": round_count,
            "rounds": rounds, "summary": summary}


def _status(h: str, a: str, rnd: int, policy: str, out_after: dict) -> tuple[str, str | None]:
    if policy == "void_all":
        return ("voided", None) if (h in out_after or a in out_after) else ("scheduled", None)
    h_out = h in out_after and rnd > out_after[h]
    a_out = a in out_after and rnd > out_after[a]
    if h_out and a_out:
        return "voided", None
    if h_out:
        return "forfeit", a
    if a_out:
        return "forfeit", h
    return "scheduled", None
