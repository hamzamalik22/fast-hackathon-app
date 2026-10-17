"""Swiss-system pairing, one round per call (spec 5.7-B).

Rounds >= 2 use an exact minimum-cost rematch-free perfect matching (Edmonds' blossom algorithm),
so the sum of |score difference| is globally minimal; greedy pairing is never used.
"""
from ...errors import conflict
from ...validation import Fields, is_int
from .matching import min_cost_perfect_matching

RESULTS = ("home", "away", "draw")


def generate(teams: list, params: dict) -> dict:
    n = len(teams)
    idx = {t: i for i, t in enumerate(teams)}
    f = Fields()
    total = params.get("total_rounds")
    if total is None:
        total = max(1, (n - 1).bit_length())  # ceil(log2 n)
    if not is_int(total) or not 1 <= total <= n - 1:
        f.add("params.total_rounds")
    rnd = params.get("round")
    rnd = 1 if rnd is None else rnd
    if not is_int(rnd) or rnd < 1 or (is_int(total) and rnd > total):
        f.add("params.round")
    history = params.get("history")
    history = [] if history is None else history
    if not isinstance(history, list):
        f.add("params.history")
    f.check()

    seen_rounds = []
    for h in history:
        if not isinstance(h, dict) or not is_int(h.get("round")) or not isinstance(h.get("matches", []), list):
            f.add("params.history")
            continue
        seen_rounds.append(h["round"])
        if h.get("bye") is not None and h.get("bye") not in idx:
            f.add("params.history")
        for m in h.get("matches", []):
            if (not isinstance(m, dict) or m.get("home") not in idx or m.get("away") not in idx
                    or m.get("home") == m.get("away") or m.get("result") not in RESULTS):
                f.add("params.history")
    if sorted(seen_rounds) != list(range(1, rnd)):
        f.add("params.history")
    f.check()

    score = {t: 0.0 for t in teams}
    opponents = {t: [] for t in teams}
    played = set()
    had_bye = set()
    for h in history:
        if h.get("bye") is not None:
            score[h["bye"]] += 1.0
            had_bye.add(h["bye"])
        for m in h.get("matches", []):
            a, b = m["home"], m["away"]
            opponents[a].append(b)
            opponents[b].append(a)
            played.add(frozenset((a, b)))
            if m["result"] == "home":
                score[a] += 1.0
            elif m["result"] == "away":
                score[b] += 1.0
            else:
                score[a] += 0.5
                score[b] += 0.5
    buchholz = {t: float(sum(score[o] for o in opponents[t])) for t in teams}
    order = sorted(teams, key=lambda t: (-score[t], -buchholz[t], idx[t]))
    standings = [{"rank": i + 1, "team_id": t, "score": score[t], "buchholz": buchholz[t]}
                 for i, t in enumerate(order)]

    if rnd == 1:
        m = n // 2
        pairs = [(teams[i], teams[i + m]) for i in range(m)]
        bye = teams[n - 1] if n % 2 else None
    else:
        pairs, bye = None, None
        if n % 2:
            candidates = [t for t in teams if t not in had_bye] or list(teams)
            candidates.sort(key=lambda t: (score[t], -idx[t]))
            for c in candidates:
                res = min_pairing([t for t in order if t != c], score, played)
                if res is not None:
                    pairs, bye = res, c
                    break
        else:
            pairs = min_pairing(order, score, played)
        if pairs is None:
            raise conflict("NO_VALID_PAIRING", f"No rematch-free pairing exists for round {rnd}.", round=rnd)
        rank = {t: i for i, t in enumerate(order)}
        pairs = sorted(((a, b) if rank[a] < rank[b] else (b, a) for a, b in pairs), key=lambda p: rank[p[0]])

    return {"format": "swiss", "round": rnd, "total_rounds": total,
            "pairings": [{"match_id": f"SW-R{rnd}-M{i + 1}", "home": a, "away": b} for i, (a, b) in enumerate(pairs)],
            "bye": bye, "standings": standings}


def min_pairing(players: list, score: dict, played: set) -> list[tuple] | None:
    """Minimum sum of |score diff| over rematch-free perfect pairings (exact, blossom matching), or None."""
    n = len(players)
    if n % 2:
        return None
    # Scores are multiples of 0.5, so 2*|diff| is an exact integer cost.
    cost = {(i, j): round(2 * abs(score[players[i]] - score[players[j]]))
            for i in range(n) for j in range(i + 1, n)
            if frozenset((players[i], players[j])) not in played}
    res = min_cost_perfect_matching(n, cost)
    if res is None:
        return None
    return [(players[i], players[j]) for i, j in res]
