"""Single elimination with seeded placement, byes, optional third-place match (spec 5.7-C)."""
from ...validation import Fields
from .bracket import Bracket, new_match, next_pow2, to


def build_main(br: Bracket, size: int, prefix: str, bracket_name: str) -> list[list[dict]]:
    k = size.bit_length() - 1
    rounds = []
    for r in range(1, k + 1):
        ms = []
        for i in range(1, (size >> r) + 1):
            m = br.add(new_match(f"{prefix}{r}M{i}", bracket_name, r, i))
            if r < k:
                m["winner_to"] = to(f"{prefix}{r + 1}M{(i + 1) // 2}", "home" if i % 2 else "away")
            ms.append(m)
        rounds.append(ms)
    return rounds


def generate(teams: list, params: dict) -> dict:
    f = Fields()
    tp = params.get("third_place_match", False)
    tp = False if tp is None else tp
    if not isinstance(tp, bool):
        f.add("params.third_place_match")
    f.check()
    size = next_pow2(len(teams))
    br = Bracket(teams)
    rounds = build_main(br, size, "R", "main")
    k = len(rounds)
    if tp and k >= 2:
        third = br.add(new_match("TP", "third_place", k, 2))
        third["bracket"] = "third_place"
        for m in rounds[k - 2]:
            m["loser_to"] = to("TP", "home" if m["index"] == 1 else "away")
        rounds[k - 1].append(third)
    br.seed_first_round(rounds[0])
    br.apply_results(params.get("results"))
    return {"format": "single_elim", "bracket_size": size,
            "rounds": [{"round": r + 1, "matches": ms} for r, ms in enumerate(rounds)]}
