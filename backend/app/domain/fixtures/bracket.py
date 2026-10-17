"""Shared elimination-bracket engine: seeding, slot routing, bye/dead-slot propagation, applying results."""
from ...validation import Fields


def next_pow2(n: int) -> int:
    b = 1
    while b < n:
        b *= 2
    return b


def seed_order(size: int) -> list[int]:
    """order(2) = [1, 2]; order(2k) = for each s in order(k): [s, 2k + 1 - s]."""
    order = [1, 2]
    while len(order) < size:
        k2 = len(order) * 2
        order = [x for s in order for x in (s, k2 + 1 - s)]
    return order


def new_match(match_id: str, bracket: str, rnd: int, index: int) -> dict:
    return {"match_id": match_id, "bracket": bracket, "round": rnd, "index": index,
            "home": None, "away": None, "home_seed": None, "away_seed": None, "bye": False,
            "winner": None, "loser": None, "winner_to": None, "loser_to": None}


def to(match_id: str, slot: str) -> dict:
    return {"match_id": match_id, "slot": slot}


class Bracket:
    def __init__(self, teams: list):
        self.team_seed = {t: i + 1 for i, t in enumerate(teams)}
        self.n = len(teams)
        self.teams = teams
        self.by_id: dict[str, dict] = {}
        self.dead: set[tuple[str, str]] = set()
        self.void: set[str] = set()

    def add(self, m: dict) -> dict:
        self.by_id[m["match_id"]] = m
        return m

    def seed_first_round(self, first_round: list[dict]) -> None:
        order = seed_order(len(first_round) * 2)
        for i, m in enumerate(first_round):
            hs, as_ = sorted((order[2 * i], order[2 * i + 1]))
            m["home"], m["home_seed"] = self.teams[hs - 1], hs
            if as_ <= self.n:
                m["away"], m["away_seed"] = self.teams[as_ - 1], as_
            else:
                m["bye"] = True
                self.decide(m, m["home"])

    def place(self, dest: dict | None, team: str) -> None:
        if dest is None:
            return
        m = self.by_id[dest["match_id"]]
        m[dest["slot"]] = team
        m[dest["slot"] + "_seed"] = self.team_seed.get(team)

    def kill(self, dest: dict | None) -> None:
        if dest is not None:
            self.dead.add((dest["match_id"], dest["slot"]))

    def decide(self, m: dict, winner: str) -> None:
        m["winner"] = winner
        loser = m["away"] if winner == m["home"] else m["home"]
        m["loser"] = loser
        self.place(m["winner_to"], winner)
        if loser is None:
            self.kill(m["loser_to"])
        else:
            self.place(m["loser_to"], loser)

    def advance_dead_slots(self) -> bool:
        progress = False
        for m in self.by_id.values():
            if m["winner"] is not None or m["match_id"] in self.void:
                continue
            hd = (m["match_id"], "home") in self.dead
            ad = (m["match_id"], "away") in self.dead
            if hd and ad:
                self.void.add(m["match_id"])
                self.kill(m["winner_to"])
                self.kill(m["loser_to"])
                progress = True
            elif ad and m["home"] is not None:
                m["bye"] = True
                self.decide(m, m["home"])
                progress = True
            elif hd and m["away"] is not None:
                m["bye"] = True
                self.decide(m, m["away"])
                progress = True
        return progress

    def apply_results(self, results) -> None:
        f = Fields()
        if results is None:
            results = []
        if not isinstance(results, list):
            f.add("params.results")
            f.check()
        pending: dict[str, str] = {}
        for r in results:
            if (not isinstance(r, dict) or r.get("match_id") not in self.by_id
                    or not isinstance(r.get("winner"), str)):
                f.add("params.results")
                continue
            pending[r["match_id"]] = r["winner"]
        f.check()
        while True:
            progress = self.advance_dead_slots()
            for mid, w in list(pending.items()):
                m = self.by_id[mid]
                if m["winner"] is not None and m["bye"]:
                    if w != m["winner"]:
                        f.add("params.results")
                        f.check("Winner is not a participant of that match.")
                    del pending[mid]
                    progress = True
                elif m["home"] is not None and m["away"] is not None:
                    if w not in (m["home"], m["away"]):
                        f.add("params.results")
                        f.check("Winner is not a participant of that match.")
                    if m["winner"] is None:
                        self.decide(m, w)
                    del pending[mid]
                    progress = True
            if not progress:
                break
        if pending:
            f.add("params.results")
            f.check("Winner is not a participant of that match.")
