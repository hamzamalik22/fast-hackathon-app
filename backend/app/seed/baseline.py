"""POST /audit/v1/reset: wipe everything and recreate the exact baseline of spec 5.5 (deterministic)."""
import json
from pathlib import Path

import bcrypt

from .. import config, db
from ..domain import rbac
from ..domain.sports import validate_sport
from . import demo

TABLES = [
    "meta", "counters", "tenants", "users", "rbac_policies", "sports", "leagues", "matches", "match_events",
    "clubs", "venues", "roster_leagues", "squads", "roster_players", "roster_live_matches", "roster_audit",
    "roster_requests", "products", "variants", "price_schedules", "discount_codes", "orders", "order_events",
    "payments", "sync_actions", "domain_event_log",
]
SEED_SPORTS = [validate_sport(s) for s in json.loads((Path(__file__).parent / "sports.json").read_text())]
DEFAULT_STOCK = {"var-jersey-001-M": 1, "var-jersey-001-L": 5}
# Hashed once per process so /reset stays fast.
PASSWORD_HASH = bcrypt.hashpw(config.DEMO_PASSWORD.encode(), bcrypt.gensalt(rounds=10)).decode()

TENANTS = [
    ("tenant-alpha", "Alpha Sports", "/static/tenant-alpha.png", "#0B5FFF", "#FFB800"),
    ("tenant-beta", "Beta Athletics", "/static/tenant-beta.png", "#0E7C3A", "#F2F2F2"),
]
USERS = [
    # user_id, email, role, tenant_id, name, league_ids, club_id, player_id
    ("user-admin", "admin@nascon.test", "super_admin", None, "Ayesha Khan", [], None, None),
    ("user-organizer", "organizer@nascon.test", "league_organizer", "tenant-alpha", "Bilal Hussain",
     ["league-alpha-1", "league-alpha-t20", "league-alpha-esports"], None, None),
    ("user-manager", "manager@nascon.test", "club_manager", "tenant-alpha", "Mariam Iqbal", [], "club-alpha-1", None),
    ("user-player", "player@nascon.test", "player", "tenant-alpha", "Hamza Siddiqui", [], "club-alpha-1", "player-alpha-1"),
    ("user-viewer", "viewer@nascon.test", "viewer", "tenant-alpha", "Sara Ahmed", [], None, None),
]
LEAGUES = [
    ("league-alpha-1", "tenant-alpha", "football", "Alpha Premier League"),
    ("league-alpha-2", "tenant-alpha", "basketball", "Alpha Basketball Cup"),
    ("league-beta-1", "tenant-beta", "football", "Beta Super League"),
]
CLUBS = [
    ("club-alpha-1", "tenant-alpha", "Alpha Lions", "Lions Arena", 31.4810, 74.3030),
    ("club-alpha-2", "tenant-alpha", "Alpha Falcons", "Falcon Ground", 31.5204, 74.3587),
    ("club-beta-1", "tenant-beta", "Beta Rangers", "Rangers Park", 24.8607, 67.0011),
]
PLAYERS = [
    ("player-alpha-1", "league-alpha-1", "Hamza Siddiqui", "fw", "club-alpha-1", "captain"),
    ("player-alpha-2", "league-alpha-1", "Bilal Khan", "mf", "club-alpha-2", "starter"),
    ("player-beta-1", "league-beta-1", "Daniyal Shah", "df", "club-beta-1", "starter"),
]


def league_config(teams=(), points=None, tie_break_order=None, spots=1, lots_seed=None) -> dict:
    return {"teams": list(teams), "points": points or {"win": 3, "draw": 1, "loss": 0},
            "tie_break_order": tie_break_order, "qualification_spots": spots, "lots_seed": lots_seed}


async def reset(conn, seed: int = 42, stock: dict | None = None) -> dict:
    stock_levels = {**DEFAULT_STOCK, **{k: v for k, v in (stock or {}).items() if k in DEFAULT_STOCK}}
    await conn.execute("TRUNCATE " + ", ".join(TABLES) + " RESTART IDENTITY")
    await conn.execute("INSERT INTO meta(key, value) VALUES ('last_seed', %s)", (str(seed),))

    for t in TENANTS:
        await conn.execute("INSERT INTO tenants VALUES (%s,%s,%s,%s,%s)", t)
    for uid, email, role, tenant, name, leagues, club, player in USERS:
        await conn.execute(
            "INSERT INTO users(user_id,email,password_hash,role,tenant_id,name,league_ids,club_id,player_id) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (uid, email, PASSWORD_HASH, role, tenant, name, db.dj(leagues), club, player))
    async with conn.cursor() as cur:
        await cur.executemany("INSERT INTO rbac_policies(action, role, scope) VALUES (%s,%s,%s)", rbac.policy_rows())

    for s in SEED_SPORTS:
        await conn.execute("INSERT INTO sports(sport_id,name,scoring_model,config) VALUES (%s,%s,%s,%s)",
                           (s["sport_id"], s["name"], s["scoring_model"], db.dj(s)))
    for lid, tenant, sport, name in LEAGUES:
        await conn.execute("INSERT INTO leagues(league_id,tenant_id,sport_id,name,season,config) "
                           "VALUES (%s,%s,%s,%s,'2026',%s)", (lid, tenant, sport, name, db.dj(league_config())))
    for cid, tenant, name, venue, lat, lng in CLUBS:
        await conn.execute("INSERT INTO clubs(club_id,tenant_id,name,logo_url,venue_name,lat,lng) "
                           "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                           (cid, tenant, name, f"/static/{cid}.png", venue, lat, lng))

    # Roster registry for the RBAC scenario players (squad_id = club_id)
    for lid, tenant, sport, _ in LEAGUES:
        await conn.execute("INSERT INTO roster_leagues(league_id,tenant_id,sport_id,window_open,window_close,"
                           "max_squad_size,required_positions) VALUES (%s,%s,%s,'2026-10-01','2026-10-31',25,'{}')",
                           (lid, tenant, sport))
    for cid, tenant, name, *_ in CLUBS:
        lid = "league-beta-1" if tenant == "tenant-beta" else "league-alpha-1"
        await conn.execute("INSERT INTO squads(league_id,squad_id,club_id,tenant_id,name) VALUES (%s,%s,%s,%s,%s)",
                           (lid, cid, cid, tenant, name))
    for pid, lid, name, pos, squad, role in PLAYERS:
        await conn.execute("INSERT INTO roster_players(player_id,league_id,name,position,squad_id,role,"
                           "registration_type,start_date,initial_squad_id) VALUES (%s,%s,%s,%s,%s,%s,'registration',"
                           "'2026-01-01',%s)", (pid, lid, name, pos, squad, role, squad))

    # Store baseline
    await conn.execute("INSERT INTO products VALUES ('prod-jersey-001','tenant-alpha','club-alpha-1',"
                       "'Alpha Lions Home Jersey 2026','apparel','Official home jersey.','/static/prod-jersey-001.png')")
    for vid, size in (("var-jersey-001-M", "M"), ("var-jersey-001-L", "L")):
        await conn.execute("INSERT INTO variants(variant_id,product_id,size,color,price_minor,stock,reserved) "
                           "VALUES (%s,'prod-jersey-001',%s,'green',450000,%s,0)", (vid, size, stock_levels[vid]))
    await conn.execute("INSERT INTO discount_codes(code, percent) VALUES ('WELCOME10', 10)")

    await demo.seed(conn)  # extra demo data for the mobile app (namespaced ids)

    await conn.execute("INSERT INTO meta(key, value) VALUES ('seeded', '1')")
    return {
        "status": "reset_complete",
        "seed": seed,
        "sports": [s["sport_id"] for s in SEED_SPORTS],
        "tenants": [t[0] for t in TENANTS],
        "stock": stock_levels,
    }


async def ensure_seeded() -> None:
    async with db.tx() as conn:
        await db.lock(conn, "reset")
        if await db.get_meta(conn, "seeded") is None:
            await reset(conn, 42, None)
