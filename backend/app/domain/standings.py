"""Standings engine (FR-1.4, spec 5.10). Recomputed from scratch from folded match states on every call."""
from dataclasses import dataclass

from ..canonical import lots_key
from .sports import effective_tie_break_order


@dataclass
class Played:
    """One completed league match whose outcome is decided (counts as played)."""
    home: str
    away: str
    home_score: int
    away_score: int
    outcome: str  # home_win | away_win | draw
    home_balls: int = 0
    away_balls: int = 0
    home_wickets: int = 0
    away_wickets: int = 0
    home_fp: int = 0
    away_fp: int = 0


class Ctx:
    def __init__(self, sport: dict, points: dict):
        self.sport = sport
        self.model = sport["scoring_model"]
        self.points = points

    def overs(self, balls: int, wickets: int) -> float:
        per = self.sport["periods"]
        if wickets >= per["innings_per_team"] * per["wickets_per_innings"]:
            return float(per["innings_per_team"] * per["overs_per_innings"])  # all out = full quota
        return balls / per["balls_per_over"]

    def match_points(self, m: Played, team: str) -> int:
        if m.outcome == "draw":
            return self.points["draw"]
        won = (m.outcome == "home_win") == (team == m.home)
        return self.points["win"] if won else self.points["loss"]

    def diff(self, matches: list[Played], team: str):
        """Event/round: scored - conceded. Innings: net run rate (3 dp)."""
        scored = conceded = 0
        faced = bowled = 0.0
        for m in matches:
            if team == m.home:
                scored += m.home_score
                conceded += m.away_score
                faced += self.overs(m.home_balls, m.home_wickets) if self.model == "innings" else 0
                bowled += self.overs(m.away_balls, m.away_wickets) if self.model == "innings" else 0
            elif team == m.away:
                scored += m.away_score
                conceded += m.home_score
                faced += self.overs(m.away_balls, m.away_wickets) if self.model == "innings" else 0
                bowled += self.overs(m.home_balls, m.home_wickets) if self.model == "innings" else 0
        if self.model != "innings":
            return scored - conceded
        rate_for = scored / faced if faced else 0.0
        rate_against = conceded / bowled if bowled else 0.0
        return round(rate_for - rate_against, 3)


def compute(league_id: str, sport: dict, cfg: dict, fixtures: list[dict], lots_seed: int) -> dict:
    """fixtures: [{home, away, state}] where state is a scoring.MatchState (all league matches)."""
    teams = list(cfg["teams"])
    points = {"win": 3, "draw": 1, "loss": 0, **(cfg.get("points") or {})}
    ctx = Ctx(sport, points)
    order = effective_tie_break_order(cfg.get("tie_break_order") or sport.get("tie_break_order"))
    spots = cfg.get("qualification_spots", 1)

    played: list[Played] = []
    remaining = {t: 0 for t in teams}
    for fx in fixtures:
        st = fx["state"]
        if st.status == "completed" and st.outcome != "undecided":
            played.append(Played(fx["home"], fx["away"], st.home.score, st.away.score, st.outcome,
                                 st.home.balls, st.away.balls, st.home.wickets, st.away.wickets,
                                 st.home.fair_play, st.away.fair_play))
        else:
            for t in (fx["home"], fx["away"]):
                if t in remaining:
                    remaining[t] += 1

    row = {t: {"played": 0, "won": 0, "drawn": 0, "lost": 0, "scored": 0, "conceded": 0, "points": 0,
               "fair_play": 0} for t in teams}
    h2h = {a: {b: {"played": 0, "points": 0, "scored": 0, "conceded": 0} for b in teams if b != a} for a in teams}
    for m in played:
        for team, opp, sc, cc, fp in ((m.home, m.away, m.home_score, m.away_score, m.home_fp),
                                      (m.away, m.home, m.away_score, m.home_score, m.away_fp)):
            if team not in row:
                continue
            r = row[team]
            pts = ctx.match_points(m, team)
            r["played"] += 1
            r["scored"] += sc
            r["conceded"] += cc
            r["points"] += pts
            r["fair_play"] += fp
            if m.outcome == "draw":
                r["drawn"] += 1
            elif (m.outcome == "home_win") == (team == m.home):
                r["won"] += 1
            else:
                r["lost"] += 1
            if opp in h2h.get(team, {}):
                cell = h2h[team][opp]
                cell["played"] += 1
                cell["points"] += pts
                cell["scored"] += sc
                cell["conceded"] += cc
    for t in teams:
        row[t]["diff"] = ctx.diff(played, t)

    lots = {t: lots_key(lots_seed, league_id, t) for t in teams}

    def criterion(name: str, team: str, group: list[str]):
        if name in ("h2h_points", "h2h_diff"):
            gs = set(group)
            mini = [m for m in played if m.home in gs and m.away in gs]
            if name == "h2h_points":
                return sum(ctx.match_points(m, team) for m in mini if team in (m.home, m.away))
            return ctx.diff(mini, team)
        if name == "overall_diff":
            return row[team]["diff"]
        if name == "scored":
            return row[team]["scored"]
        if name == "fair_play":
            return row[team]["fair_play"]
        raise ValueError(name)

    def resolve(group: list[str]) -> tuple[list[str], list[str]]:
        """Returns (ordered teams, separator criterion between each adjacent pair)."""
        if len(group) == 1:
            return group, []
        for crit in order:
            if crit == "draw_lots":
                return sorted(group, key=lambda t: lots[t]), ["draw_lots"] * (len(group) - 1)
            vals = {t: criterion(crit, t, group) for t in group}
            distinct = sorted(set(vals.values()), reverse=True)
            if len(distinct) == 1:
                continue
            out, seps = [], []
            for v in distinct:
                sub = [t for t in group if vals[t] == v]
                o, s = resolve(sub)
                if out:
                    seps.append(crit)
                out += o
                seps += s
            return out, seps
        return group, [None] * (len(group) - 1)

    final, resolved_by = [], {}
    for p in sorted({row[t]["points"] for t in teams}, reverse=True):
        group = [t for t in teams if row[t]["points"] == p]
        o, seps = resolve(group)
        for i, t in enumerate(o):
            resolved_by[t] = seps[i] if i < len(seps) else None
        final += o

    w = points["win"]
    max_pts = {t: row[t]["points"] + w * remaining[t] for t in teams}

    def status(t: str) -> str:
        others = [x for x in teams if x != t]
        if sum(1 for x in others if max_pts[x] >= row[t]["points"]) < spots:
            return "clinched"
        if sum(1 for x in others if row[x]["points"] > max_pts[t]) >= spots:
            return "eliminated"
        return "still_possible"

    table = []
    for rank, t in enumerate(final, 1):
        r = row[t]
        table.append({"rank": rank, "team_id": t, "played": r["played"], "won": r["won"], "drawn": r["drawn"],
                      "lost": r["lost"], "scored": r["scored"], "conceded": r["conceded"], "diff": r["diff"],
                      "points": r["points"], "fair_play": r["fair_play"], "status": status(t),
                      "resolved_by": resolved_by[t]})
    return {"league_id": league_id, "sport_id": sport["sport_id"], "qualification_spots": spots,
            "table": table, "h2h": h2h}
