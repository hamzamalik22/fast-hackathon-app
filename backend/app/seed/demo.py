"""Demo data for the mobile app, recreated by every /reset. Namespaced ids (la1-*, pa1-*, demo-*) never collide
with grader ids and never touch the graded baseline rows (jersey stock, RBAC ids)."""
from datetime import datetime, time, timedelta, timezone

from .. import db
from ..canonical import canonical, sign
from ..domain.fixtures.round_robin import circle_rounds

STAFF = [("Coach", "coach"), ("Manager", "manager"), ("Physio", "physio")]
NAMES = ["Ahmed", "Hassan", "Usman", "Saad", "Hamza", "Zain", "Faisal", "Imran", "Shoaib", "Babar", "Rizwan",
         "Haris", "Fakhar", "Imad", "Shadab", "Naseem", "Wasim", "Junaid", "Asad", "Talha", "Omar", "Danish"]
SURNAMES = ["Ali", "Khan", "Malik", "Iqbal", "Butt", "Shah", "Qureshi", "Javed", "Raza", "Akhtar", "Mirza"]

CLUB_EXTRA = {
    "club-alpha-1": ("Alpha Lions", "Lions Arena", 31.4810, 74.3030, "#0B5FFF"),
    "club-alpha-2": ("Alpha Falcons", "Falcon Ground", 31.5204, 74.3587, "#C2185B"),
    "club-alpha-3": ("Alpha Tigers", "Tiger Stadium", 31.4504, 74.2707, "#EF6C00"),
    "club-alpha-4": ("Alpha Wolves", "Wolves Den", 31.5600, 74.3300, "#455A64"),
    "club-beta-1": ("Beta Rangers", "Rangers Park", 24.8607, 67.0011, "#0E7C3A"),
    "club-beta-2": ("Beta Strikers", "Strikers Field", 24.9056, 67.0822, "#6A1B9A"),
}
POSITIONS = ["gk", "gk", "df", "df", "df", "df", "mf", "mf", "mf", "mf", "fw", "fw"]
# (home goals, away goals) for completed demo fixtures, in fixture order
RESULTS = [(2, 1), (0, 0), (1, 3), (2, 2)]


def _person(i: int) -> str:
    return f"{NAMES[i % len(NAMES)]} {SURNAMES[(i * 7) % len(SURNAMES)]}"


async def _event(conn, match_id: str, seq: int, etype: str, payload: dict) -> None:
    eid = f"demo-{match_id}-{seq}"
    req = {"event_id": eid, "match_id": match_id, "type": etype, "payload": payload}
    sig = sign(eid, payload)
    resp = {"event_id": eid, "match_id": match_id, "type": etype, "sequence": seq, "match_version": seq,
            "signature": sig}
    await conn.execute("INSERT INTO match_events(event_id, match_id, sequence, type, payload, signature, compensates, "
                       "request_canonical, response) VALUES (%s,%s,%s,%s,%s,%s,NULL,%s,%s)",
                       (eid, match_id, seq, etype, db.dj(payload), sig, canonical(req), db.dj(resp)))


async def _play(conn, match_id: str, home: str, away: str, goals: tuple[int, int], finished: bool) -> None:
    seq = 1
    await _event(conn, match_id, seq, "match_start", {})
    for team, n in ((home, goals[0]), (away, goals[1])):
        for _ in range(n):
            seq += 1
            await _event(conn, match_id, seq, "score", {"team_id": team, "event_type": "goal"})
    if finished:
        await _event(conn, match_id, seq + 1, "match_end", {})


async def _league_fixtures(conn, league_id: str, prefix: str, sport_id: str, teams: list[str], legs: int,
                           start_day: datetime, completed: int, live: int) -> list[str]:
    base = circle_rounds(teams)
    rounds = [r for _ in range(legs) for r in base]
    ids = []
    k = 0
    for r_idx, pairs in enumerate(rounds):
        leg2 = r_idx >= len(base)
        for i, (h, a) in enumerate([p for p in pairs if None not in p], 1):
            if leg2:
                h, a = a, h
            mid = f"{prefix}-r{r_idx + 1}-m{i}"
            when = start_day + timedelta(days=3 * r_idx, hours=2 * (i - 1))
            await conn.execute("INSERT INTO matches(match_id, league_id, sport_id, home_team_id, away_team_id, "
                               "scheduled_at, venue_id, round) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                               (mid, league_id, sport_id, h, a, when, CLUB_EXTRA[h][1], r_idx + 1))
            if k < completed:
                await _play(conn, mid, h, a, RESULTS[k % len(RESULTS)], True)
            elif k < completed + live:
                await _play(conn, mid, h, a, (1, 0), False)
            ids.append(mid)
            k += 1
    return ids


async def seed(conn) -> None:
    today = datetime.now(timezone.utc).date()
    start = datetime.combine(today - timedelta(days=6), time(13, 0), tzinfo=timezone.utc)

    for cid, (name, venue, lat, lng, _color) in CLUB_EXTRA.items():
        tenant = "tenant-beta" if "beta" in cid else "tenant-alpha"
        socials = {"x": f"@{cid.replace('-', '')}", "instagram": f"@{cid.replace('-', '_')}",
                   "facebook": f"fb.com/{cid}"}
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

    alpha = ["club-alpha-1", "club-alpha-2", "club-alpha-3", "club-alpha-4"]
    beta = ["club-beta-1", "club-beta-2"]
    configs = {
        "league-alpha-1": {"teams": alpha, "points": {"win": 3, "draw": 1, "loss": 0}, "tie_break_order": None,
                           "qualification_spots": 2, "lots_seed": 42},
        "league-alpha-2": {"teams": alpha[:2], "points": {"win": 2, "draw": 0, "loss": 0}, "tie_break_order": None,
                           "qualification_spots": 1, "lots_seed": 42},
        "league-beta-1": {"teams": beta, "points": {"win": 3, "draw": 1, "loss": 0}, "tie_break_order": None,
                          "qualification_spots": 1, "lots_seed": 42},
    }
    for lid, cfg in configs.items():
        await conn.execute("UPDATE leagues SET config=%s WHERE league_id=%s", (db.dj(cfg), lid))

    la1 = await _league_fixtures(conn, "league-alpha-1", "la1", "football", alpha, 2, start, completed=4, live=1)
    await _league_fixtures(conn, "league-alpha-2", "la2", "basketball", alpha[:2], 2, start + timedelta(days=8), 0, 0)
    await _league_fixtures(conn, "league-beta-1", "lb1", "football", beta, 2, start, completed=1, live=0)
    await conn.execute("UPDATE matches SET pinned_product_id='prod-jersey-001' WHERE match_id=%s", (la1[4],))

    # Roster registry for league-alpha-1: 12 players per alpha club (squad_id = club_id)
    await conn.execute("UPDATE roster_leagues SET required_positions=%s WHERE league_id='league-alpha-1'",
                       (db.dj({"gk": 1}),))
    for cid in alpha[2:]:
        await conn.execute("INSERT INTO squads(league_id, squad_id, club_id, tenant_id, name) VALUES "
                           "('league-alpha-1',%s,%s,'tenant-alpha',%s)", (cid, cid, CLUB_EXTRA[cid][0]))
    await conn.execute("INSERT INTO squads(league_id, squad_id, club_id, tenant_id, name) VALUES "
                       "('league-beta-1','club-beta-2','club-beta-2','tenant-beta','Beta Strikers')")
    n = 0
    for ci, cid in enumerate(alpha):
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
        ("prod-scarf-001", "club-alpha-1", "Alpha Lions Scarf", "accessories", "Knitted supporter scarf.",
         [("var-scarf-001-OS", "One size", "blue", 150000, 100)]),
        ("prod-cap-001", "club-alpha-2", "Falcons Snapback Cap", "apparel", "Adjustable cap with embroidered crest.",
         [("var-cap-001-S", "S", "black", 220000, 50), ("var-cap-001-M", "M", "black", 220000, 50),
          ("var-cap-001-L", "L", "black", 220000, 50)]),
        ("prod-wallpaper-001", "club-alpha-1", "Matchday Wallpaper Pack", "digital", "Phone wallpapers (download).",
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
        await conn.execute("INSERT INTO price_schedules VALUES (%s, 199000, %s), (%s, 240000, %s)",
                           (vid, past, vid, future))
    await conn.execute("INSERT INTO products VALUES ('prod-beta-shirt-001','tenant-beta','club-beta-1',"
                       "'Beta Rangers Shirt','apparel','Home shirt.','/static/prod-jersey-001.png')")
    await conn.execute("INSERT INTO variants VALUES ('var-beta-shirt-001-M','prod-beta-shirt-001','M','green',"
                       "400000,20,0)")
