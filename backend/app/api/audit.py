"""Mandatory autograder interface /audit/v1/* (spec section 5). Thin: parse -> service -> respond."""
import asyncio

import psycopg
from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool

from .. import db
from ..domain import fixtures
from ..http import read_json, respond
from ..seed import baseline
from ..security import current_user, issue_token, reset_rate_limits
from ..services import checkout as checkout_svc
from ..services import leagues as leagues_svc
from ..services import rbac as rbac_svc
from ..services import roster as roster_svc
from ..services import scoring as scoring_svc
from ..services import sync as sync_svc
from ..validation import Fields, is_int

router = APIRouter(prefix="/audit/v1")


@router.post("/reset")
async def reset(request: Request):
    body = await read_json(request, optional=True)
    f = Fields()
    seed = body.get("seed", 42)
    if seed is None:
        seed = 42
    if not is_int(seed):
        f.add("seed")
    stock = body.get("stock") or {}
    if not isinstance(stock, dict) or not all(is_int(v) and v >= 0 for v in stock.values()):
        f.add("stock")
    f.check()
    # TRUNCATE takes exclusive locks on every table; a concurrent reader (app, worker) can deadlock with it.
    # Postgres then aborts one side, so retry the whole (atomic) reset a few times.
    for attempt in range(8):
        try:
            async with db.tx() as conn:
                await db.lock(conn, "reset")
                result = await baseline.reset(conn, seed, stock)
            break
        except (psycopg.errors.DeadlockDetected, psycopg.errors.LockNotAvailable, psycopg.errors.SerializationFailure):
            if attempt == 7:
                raise
            await asyncio.sleep(0.05 * (attempt + 1))
    await reset_rate_limits()
    return respond(200, result)


@router.post("/sports")
async def create_sport(request: Request):
    return respond(201, await scoring_svc.create_sport(await read_json(request)))


@router.post("/events")
async def append_event(request: Request):
    status, resp = await scoring_svc.append_event(await read_json(request))
    return respond(status, resp)


@router.get("/score/{match_id}")
async def score(match_id: str):
    return respond(200, await scoring_svc.score(match_id))


@router.post("/fixtures")
async def generate_fixtures(request: Request):
    body = await read_json(request)
    return respond(200, await run_in_threadpool(fixtures.generate, body))


@router.post("/leagues")
async def create_league(request: Request):
    return respond(201, await leagues_svc.create_league(await read_json(request)))


@router.get("/standings/{league_id}")
async def standings(league_id: str):
    return respond(200, await leagues_svc.get_standings(league_id))


@router.post("/checkout")
async def checkout(request: Request):
    status, resp = await checkout_svc.checkout(await read_json(request))
    return respond(status, resp)


@router.get("/inventory/{variant_id}")
async def inventory(variant_id: str):
    return respond(200, await checkout_svc.inventory(variant_id))


# ------------------------------------------------------------------ roster (5.11)
@router.post("/roster/setup")
async def roster_setup(request: Request):
    return respond(201, await roster_svc.setup(await read_json(request)))


@router.post("/roster/transfer")
async def roster_transfer(request: Request):
    status, resp = await roster_svc.transfer(await read_json(request))
    return respond(status, resp)


@router.get("/roster/history/{player_id}")
async def roster_history(player_id: str, as_of: str | None = None):
    return respond(200, await roster_svc.history(player_id, as_of))


# ------------------------------------------------------------------ offline sync (5.14)
@router.post("/offline-sync")
async def offline_sync(request: Request):
    return respond(200, await sync_svc.offline_sync(await read_json(request)))


# ------------------------------------------------------------------ RBAC (5.13)
RBAC_CONTEXT = {
    "tenant_id": "tenant-alpha", "foreign_tenant_id": "tenant-beta",
    "own_league_id": "league-alpha-1", "other_league_id": "league-alpha-2", "foreign_league_id": "league-beta-1",
    "own_club_id": "club-alpha-1", "other_club_id": "club-alpha-2", "foreign_club_id": "club-beta-1",
    "own_player_id": "player-alpha-1", "other_player_id": "player-alpha-2", "foreign_player_id": "player-beta-1",
}
ROLE_USERS = {"super_admin": "user-admin", "league_organizer": "user-organizer", "club_manager": "user-manager",
              "player": "user-player", "viewer": "user-viewer"}


@router.post("/rbac-matrix")
async def rbac_matrix():
    async with db.tx() as conn:
        rows = await db.fetchall(conn, "SELECT * FROM users WHERE user_id = ANY(%s)", (list(ROLE_USERS.values()),))
    by_id = {r["user_id"]: r for r in rows}
    return respond(200, {"tokens": {role: issue_token(by_id[uid])[0] for role, uid in ROLE_USERS.items()},
                         "context": RBAC_CONTEXT})


async def _probe(request: Request, action: str, kind: str | None = None, target_id: str | None = None):
    user = current_user(request)  # 401 first; probes never read or validate the body
    await rbac_svc.authorize(user, action, kind, target_id)
    return respond(200, {"authorized": True})


@router.post("/rbac/tenants")
async def probe_tenants(request: Request):
    return await _probe(request, "tenants.create")


@router.post("/rbac/leagues/{league_id}/fixtures")
async def probe_league_fixtures(request: Request, league_id: str):
    return await _probe(request, "league.fixtures.write", "league", league_id)


@router.post("/rbac/clubs/{club_id}/roster")
async def probe_club_roster(request: Request, club_id: str):
    return await _probe(request, "club.roster.write", "club", club_id)


@router.post("/rbac/clubs/{club_id}/products")
async def probe_club_products(request: Request, club_id: str):
    return await _probe(request, "club.products.write", "club", club_id)


@router.patch("/rbac/players/{player_id}")
async def probe_player(request: Request, player_id: str):
    return await _probe(request, "player.update", "player", player_id)


@router.get("/rbac/clubs/{club_id}")
async def probe_club_read(request: Request, club_id: str):
    return await _probe(request, "club.read", "club", club_id)


@router.get("/rbac/platform/config")
async def probe_platform_config(request: Request):
    return await _probe(request, "platform.config")
