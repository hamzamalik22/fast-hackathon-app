"""Demo data for the mobile app, recreated by every /reset. Namespaced ids (la1-*, t20-*, esp-*, pa1-*, demo-*) never
collide with grader ids and never touch the graded baseline rows (jersey stock, RBAC ids)."""
import random
from datetime import datetime, time, timedelta, timezone

from .. import db
from ..canonical import canonical, sign
from ..domain.fixtures.round_robin import circle_rounds

STAFF = [("Coach", "coach"), ("Manager", "manager"), ("Physio", "physio")]
NAMES = ["Ahmed", "Hassan", "Usman", "Saad", "Hamza", "Zain", "Faisal", "Imran", "Shoaib", "Babar", "Rizwan",
         "Haris", "Fakhar", "Imad", "Shadab", "Naseem", "Wasim", "Junaid", "Asad", "Talha", "Omar", "Danish"]
SURNAMES = ["Ali", "Khan", "Malik", "Iqbal", "Butt", "Shah", "Qureshi", "Javed", "Raza", "Akhtar", "Mirza"]

CLUB_EXTRA = {
    "club-alpha-1": ("Alpha Lions", "Lions Arena", 31.4810, 74.3030),
    "club-alpha-2": ("Alpha Falcons", "Falcon Ground", 31.5204, 74.3587),
    "club-alpha-3": ("Alpha Tigers", "Tiger Stadium", 31.4504, 74.2707),
    "club-alpha-4": ("Alpha Wolves", "Wolves Den", 31.5600, 74.3300),
    "club-beta-1": ("Beta Rangers", "Rangers Park", 24.8607, 67.0011),
    "club-beta-2": ("Beta Strikers", "Strikers Field", 24.9056, 67.0822),
}
POSITIONS = ["gk", "gk", "df", "df", "df", "df", "mf", "mf", "mf", "mf", "fw", "fw"]
ALPHA = ["club-alpha-1", "club-alpha-2", "club-alpha-3", "club-alpha-4"]
BETA = ["club-beta-1", "club-beta-2"]
DEMO_LEAGUES = [  # extra demo leagues so every seeded sport has fixtures, results and a live match
    ("league-alpha-t20", "tenant-alpha", "cricket", "Alpha T20"),
    ("league-alpha-esports", "tenant-alpha", "esports", "Alpha Esports Cup"),
]


def _person(i: int) -> str:
    return f"{NAMES[i % len(NAMES)]} {SURNAMES[(i * 7) % len(SURNAMES)]}"


# ---------------------------------------------------------------- per-sport event plans (lists of (team, event_type))
def _interleave(a: list, b: list, seed: str) -> list:
    out = a + b
    random.Random(seed).shuffle(out)
    return out


def football(h, a, gh, ga, seed):
    return _interleave([(h, "goal")] * gh, [(a, "goal")] * ga, seed)


def _baskets(team, points):
    threes = points // 7
    rest = points - 3 * threes
    twos = rest // 2
    return [(team, "three_pointer")] * threes + [(team, "two_pointer")] * twos + [(team, "free_throw")] * (rest - 2 * twos)


def basketball(h, a, ph, pa, seed):
    return _interleave(_baskets(h, ph), _baskets(a, pa), seed)


def cricket_innings(team, runs, balls, wickets, wides, seed):
    """Ball-by-ball innings that adds up exactly to runs / legal balls / wickets."""
    n = balls - wickets
    r = runs - wides
    sixes = min(r // 6, n // 10)
    r -= 6 * sixes
    fours = min(r // 4, n // 6)
    r -= 4 * fours
    m = n - sixes - fours
    twos = min(r // 2, m // 4)
    r -= 2 * twos
    singles = r
    dots = m - twos - singles
    legal = (["six"] * sixes + ["four"] * fours + ["two"] * twos + ["single"] * singles + ["dot_ball"] * dots)
    rng = random.Random(seed)
    rng.shuffle(legal)
    for _ in range(wickets):
        legal.insert(rng.randrange(len(legal) + 1), "wicket")
    for _ in range(wides):
        legal.insert(rng.randrange(len(legal) + 1), "wide")
    return [(team, e) for e in legal]


def esports(h, a, wins, seed):
    return [(h if w == "h" else a, "round_win") for w in wins]


async def _event(conn, match_id: str, seq: int, etype: str, payload: dict) -> None:
    eid = f"demo-{match_id}-{seq}"
    req = {"event_id": eid, "match_id": match_id, "type": etype, "payload": payload}
    sig = sign(eid, payload)
    resp = {"event_id": eid, "match_id": match_id, "type": etype, "sequence": seq, "match_version": seq, "signature": sig}
    await conn.execute("INSERT INTO match_events(event_id, match_id, sequence, type, payload, signature, compensates, "
                       "request_canonical, response) VALUES (%s,%s,%s,%s,%s,%s,NULL,%s,%s)",
                       (eid, match_id, seq, etype, db.dj(payload), sig, canonical(req), db.dj(resp)))


async def _play(conn, match_id: str, plan: list, finished: bool) -> None:
    seq = 1
    await _event(conn, match_id, seq, "match_start", {})
    for team, et in plan:
        seq += 1
        await _event(conn, match_id, seq, "score", {"team_id": team, "event_type": et})
    if finished:
        await _event(conn, match_id, seq + 1, "match_end", {})


async def _fixtures(conn, league_id: str, prefix: str, sport_id: str, teams: list[str], legs: int,
                    start: datetime, results: list, live=None) -> list[str]:
    """results: event plans for the first completed matches (callable(home, away) -> plan); live: plan for the next one."""
    base = circle_rounds(teams)
    rounds = [r for _ in range(legs) for r in base]
    ids, k = [], 0
    for r_idx, pairs in enumerate(rounds):
        leg2 = r_idx >= len(base)
        for i, (h, a) in enumerate([p for p in pairs if None not in p], 1):
            if leg2:
                h, a = a, h
            mid = f"{prefix}-r{r_idx + 1}-m{i}"
            when = start + timedelta(days=3 * r_idx, hours=2 * (i - 1))
            await conn.execute("INSERT INTO matches(match_id, league_id, sport_id, home_team_id, away_team_id, "
                               "scheduled_at, venue_id, round) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                               (mid, league_id, sport_id, h, a, when, CLUB_EXTRA[h][1], r_idx + 1))
            if k < len(results):
                await _play(conn, mid, results[k](h, a, mid), True)
            elif k == len(results) and live is not None:
                await _play(conn, mid, live(h, a, mid), False)
            ids.append(mid)
            k += 1
    return ids


async def seed(conn) -> None:
    today = datetime.now(timezone.utc).date()
    start = datetime.combine(today - timedelta(days=6), time(13, 0), tzinfo=timezone.utc)
    t20_start = datetime.combine(today - timedelta(days=3), time(14, 0), tzinfo=timezone.utc)

    for cid, (name, venue, lat, lng) in CLUB_EXTRA.items():
        tenant = "tenant-beta" if "beta" in cid else "tenant-alpha"
        socials = {"x": f"@{cid.replace('-', '')}", "instagram": f"@{cid.replace('-', '_')}", "facebook": f"fb.com/{cid}"}
        staff = [{"name": _person(sum(map(ord, cid + r))), "role": r} for _, r in STAFF]
        stats = [{"season": "2025", "played": 18, "won": 9 + len(cid) % 4, "drawn": 4, "lost": 5 - len(cid) % 4},
                 {"season": "2024", "played": 18, "won": 7, "drawn": 6, "lost": 5}]
        await conn.execute("INSERT INTO clubs(club_id, tenant_id, name, logo_url, venue_name, lat, lng, socials, staff, "
                           "stats) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (club_id) DO UPDATE SET "
                           "socials=EXCLUDED.socials, staff=EXCLUDED.staff, stats=EXCLUDED.stats",
                           (cid, tenant, name, f"/static/{cid}.png", venue, lat, lng, db.dj(socials), db.dj(staff),
                            db.dj(stats)))
        await conn.execute("INSERT INTO venues(venue_id, tenant_id, name, open_hour, close_hour) VALUES (%s,%s,%s,8,23)",
                           (venue, tenant, venue))

    for lid, tenant, sport, name in DEMO_LEAGUES:
        await conn.execute("INSERT INTO leagues(league_id,tenant_id,sport_id,name,season,config) VALUES (%s,%s,%s,%s,'2026','{}')",
                           (lid, tenant, sport, name))

    def cfg(teams, spots, win=3, draw=1):
        return {"teams": teams, "points": {"win": win, "draw": draw, "loss": 0}, "tie_break_order": None,
                "qualification_spots": spots, "lots_seed": 42}
    configs = {
        "league-alpha-1": cfg(ALPHA, 2), "league-alpha-2": cfg(ALPHA, 2, win=2, draw=0),
        "league-alpha-t20": cfg(ALPHA, 2, win=2, draw=1), "league-alpha-esports": cfg(ALPHA, 2, win=3, draw=0),
        "league-beta-1": cfg(BETA, 1),
    }
    for lid, c in configs.items():
        await conn.execute("UPDATE leagues SET config=%s WHERE league_id=%s", (db.dj(c), lid))

    # Football: double round robin, 4 results + 1 live (pinned jersey)
    goals = [(2, 1), (0, 0), (1, 3), (2, 2)]
    la1 = await _fixtures(conn, "league-alpha-1", "la1", "football", ALPHA, 2, start,
                          [lambda h, a, m, g=g: football(h, a, *g, m) for g in goals],
                          live=lambda h, a, m: football(h, a, 1, 0, m))
    await conn.execute("UPDATE matches SET pinned_product_id='prod-jersey-001' WHERE match_id=%s", (la1[4],))

    # Basketball: single round robin, 3 results + 1 live
    pts = [(88, 92), (101, 95), (77, 84)]
    await _fixtures(conn, "league-alpha-2", "la2", "basketball", ALPHA, 1, start,
                    [lambda h, a, m, p=p: basketball(h, a, *p, m) for p in pts],
                    live=lambda h, a, m: basketball(h, a, 54, 49, m))

    # Cricket T20: single round robin, 3 results + 1 live chase (2nd innings)
    innings = [((176, 120, 6, 5), (151, 120, 9, 4)), ((139, 114, 10, 3), (142, 104, 5, 2)), ((188, 120, 4, 6), (160, 120, 8, 5))]
    t20 = [lambda h, a, m, x=x: cricket_innings(h, *x[0], m + "h") + cricket_innings(a, *x[1], m + "a") for x in innings]
    await _fixtures(conn, "league-alpha-t20", "t20", "cricket", ALPHA, 1, t20_start, t20,
                    live=lambda h, a, m: cricket_innings(h, 168, 120, 7, 4, m + "h") + cricket_innings(a, 142, 98, 4, 3, m + "a"))

    # Esports best of 3: single round robin, 3 results + 1 live at 1-1
    series = ["hah", "hh", "aha"]
    await _fixtures(conn, "league-alpha-esports", "esp", "esports", ALPHA, 1, start + timedelta(days=1),
                    [lambda h, a, m, s=s: esports(h, a, s, m) for s in series],
                    live=lambda h, a, m: esports(h, a, "ha", m))

    await _fixtures(conn, "league-beta-1", "lb1", "football", BETA, 2, start,
                    [lambda h, a, m: football(h, a, 1, 1, m)])

    # Roster registry for league-alpha-1: 12 players per alpha club (squad_id = club_id)
    await conn.execute("UPDATE roster_leagues SET required_positions=%s WHERE league_id='league-alpha-1'",
                       (db.dj({"gk": 1}),))
    for cid in ALPHA[2:]:
        await conn.execute("INSERT INTO squads(league_id, squad_id, club_id, tenant_id, name) VALUES "
                           "('league-alpha-1',%s,%s,'tenant-alpha',%s)", (cid, cid, CLUB_EXTRA[cid][0]))
    await conn.execute("INSERT INTO squads(league_id, squad_id, club_id, tenant_id, name) VALUES "
                       "('league-beta-1','club-beta-2','club-beta-2','tenant-beta','Beta Strikers')")
    n = 0
    for ci, cid in enumerate(ALPHA):
        for pi, pos in enumerate(POSITIONS):
            pid = f"pa{ci + 1}-{pi + 1:02d}"
            if (cid, pos, pi) in (("club-alpha-1", "fw", 10), ("club-alpha-2", "mf", 6)):
                continue  # player-alpha-1 / player-alpha-2 already fill these slots
            role = "captain" if pi == 0 else "vice_captain" if pi == 2 else "starter" if pi < 11 else "substitute"
            n += 1
            await conn.execute("INSERT INTO roster_players(player_id, league_id, name, position, squad_id, role, "
                               "registration_type, start_date, initial_squad_id) VALUES (%s,'league-alpha-1',%s,%s,%s,"
                               "%s,'registration','2026-01-01',%s)", (pid, _person(n), pos, cid, role, cid))
    await conn.execute("UPDATE roster_players SET role='starter' WHERE player_id='player-alpha-1'")

    # Store catalogue beyond the graded jersey: accessories + digital + a scheduled price change
    products = [
        ("prod-scarf-001", "club-alpha-1", "Alpha Lions Scarf", "accessories", "Knitted supporter scarf in club colours.",
         [("var-scarf-001-OS", "One size", "green", 150000, 100)]),
        ("prod-cap-001", "club-alpha-2", "Falcons Training Cap", "apparel", "Adjustable cap with embroidered crest.",
         [("var-cap-001-S", "S", "black", 220000, 50), ("var-cap-001-M", "M", "black", 220000, 50),
          ("var-cap-001-L", "L", "black", 220000, 0)]),
        ("prod-wallpaper-001", "club-alpha-1", "Matchday Wallpaper Pack", "digital", "Phone wallpapers to download.",
         [("var-wallpaper-001-D", "Digital", "n/a", 50000, 9999)]),
    ]
    for pid, club, name, cat, desc, variants in products:
        await conn.execute("INSERT INTO products VALUES (%s,'tenant-alpha',%s,%s,%s,%s,%s)",
                           (pid, club, name, cat, desc, f"/static/{pid}.png"))
        for vid, size, color, price, stock in variants:
            await conn.execute("INSERT INTO variants(variant_id, product_id, size, color, price_minor, stock, reserved) "
                               "VALUES (%s,%s,%s,%s,%s,%s,0)", (vid, pid, size, color, price, stock))
    midnight = datetime.combine(today, time(0, 0), tzinfo=timezone.utc)
    past, future = midnight - timedelta(days=1), midnight + timedelta(days=14)
    for vid in ("var-cap-001-S", "var-cap-001-M", "var-cap-001-L"):
        await conn.execute("INSERT INTO price_schedules VALUES (%s, 199000, %s), (%s, 240000, %s)", (vid, past, vid, future))
    await conn.execute("INSERT INTO products VALUES ('prod-beta-shirt-001','tenant-beta','club-beta-1',"
                       "'Beta Rangers Shirt','apparel','Home shirt.','/static/prod-jersey-001.png')")
    await conn.execute("INSERT INTO variants VALUES ('var-beta-shirt-001-M','prod-beta-shirt-001','M','green',400000,20,0)")
