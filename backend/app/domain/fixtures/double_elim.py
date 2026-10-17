"""Double elimination: winners bracket, losers bracket, grand final with optional reset (spec 5.7-D).

Losers routing: WR1 losers meet in LR1; WRr (r >= 2) losers drop into LR(2r-2) away slot.
"""
from ...validation import Fields
from .bracket import Bracket, new_match, next_pow2, to
from .single_elim import build_main


def generate(teams: list, params: dict) -> dict:
    f = Fields()
    reset = params.get("bracket_reset", False)
    reset = False if reset is None else reset
    if not isinstance(reset, bool):
        f.add("params.bracket_reset")
    f.check()

    size = next_pow2(len(teams))
    k = size.bit_length() - 1
    br = Bracket(teams)
    winners = build_main(br, size, "WR", "winners")

    losers = []
    for r in range(1, 2 * (k - 1) + 1):
        j = (r + 1) // 2
        losers.append([br.add(new_match(f"LR{r}M{i}", "losers", r, i)) for i in range(1, (size >> (j + 1)) + 1)])
    last_lr = 2 * (k - 1)

    gf1 = br.add(new_match("GF1", "grand_final", 1, 1))
    gf2 = None
    if reset:
        gf2 = br.add(new_match("GF2", "grand_final", 2, 1))
        gf1["winner_to"] = to("GF2", "home")
        gf1["loser_to"] = to("GF2", "away")

    # Winners bracket losers -> losers bracket; WR final -> GF1.home
    for m in winners[0]:
        m["loser_to"] = to(f"LR1M{(m['index'] + 1) // 2}", "home" if m["index"] % 2 else "away")
    for r in range(2, k + 1):
        for m in winners[r - 1]:
            m["loser_to"] = to(f"LR{2 * r - 2}M{m['index']}", "away")
    winners[k - 1][0]["winner_to"] = to("GF1", "home")

    # Losers bracket internal routing; LB final -> GF1.away
    for r in range(1, last_lr + 1):
        for m in losers[r - 1]:
            i = m["index"]
            if r == last_lr:
                m["winner_to"] = to("GF1", "away")
            elif r % 2 == 1:
                m["winner_to"] = to(f"LR{r + 1}M{i}", "home")
            else:
                m["winner_to"] = to(f"LR{r + 1}M{(i + 1) // 2}", "home" if i % 2 else "away")

    for m in br.by_id.values():
        m["conditional"] = False
        m["required"] = True
    if gf2 is not None:
        gf2["conditional"] = True
        gf2["required"] = None

    br.seed_first_round(winners[0])
    br.apply_results(params.get("results"))

    grand_final = [gf1]
    if gf2 is not None:
        if gf1["winner"] is None:
            # Before GF1 is played, GF2 carries the same two teams as GF1.
            for slot in ("home", "away"):
                gf2[slot], gf2[slot + "_seed"] = gf1[slot], gf1[slot + "_seed"]
        else:
            gf2["required"] = gf1["winner"] == gf1["away"]
        grand_final.append(gf2)

    return {"format": "double_elim", "bracket_size": size, "bracket_reset": reset,
            "winners": [{"round": r + 1, "matches": ms} for r, ms in enumerate(winners)],
            "losers": [{"round": r + 1, "matches": ms} for r, ms in enumerate(losers)],
            "grand_final": grand_final}
