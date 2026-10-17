"""Loads the DB policy matrix + target resources and enforces RBAC with strict tenant isolation."""
from .. import db
from ..domain import rbac
from ..errors import ApiError, not_found

NOT_FOUND = {"league": "LEAGUE_NOT_FOUND", "club": "CLUB_NOT_FOUND", "player": "PLAYER_NOT_FOUND"}


async def load_policies(conn) -> dict:
    rows = await db.fetchall(conn, "SELECT action, role, scope FROM rbac_policies")
    out: dict[str, dict[str, str]] = {}
    for r in rows:
        out.setdefault(r["action"], {})[r["role"]] = r["scope"]
    return out


async def target_for(conn, kind: str, target_id: str) -> dict | None:
    if kind == "league":
        return await db.fetchone(conn, "SELECT league_id, tenant_id FROM leagues WHERE league_id=%s", (target_id,))
    if kind == "club":
        return await db.fetchone(conn, "SELECT club_id, tenant_id FROM clubs WHERE club_id=%s", (target_id,))
    if kind == "player":
        return await db.fetchone(
            conn, "SELECT p.player_id, s.club_id, COALESCE(s.tenant_id, rl.tenant_id) AS tenant_id "
                  "FROM roster_players p LEFT JOIN squads s ON s.league_id = p.league_id AND s.squad_id = p.squad_id "
                  "LEFT JOIN roster_leagues rl ON rl.league_id = p.league_id WHERE p.player_id=%s", (target_id,))
    if kind == "match":
        return await db.fetchone(conn, "SELECT m.match_id, m.league_id, l.tenant_id FROM matches m "
                                       "LEFT JOIN leagues l ON l.league_id = m.league_id WHERE m.match_id=%s",
                                 (target_id,))
    raise ValueError(kind)


def forbidden() -> ApiError:
    return ApiError(403, "FORBIDDEN", "Your role is not allowed to perform this action.", {})


async def authorize(user: dict, action: str, kind: str | None = None, target_id: str | None = None,
                    conn=None) -> dict | None:
    async def run(c):
        policies = await load_policies(c)
        target = None
        if kind is not None:
            target = await target_for(c, kind, target_id)
            if target is None:
                raise not_found(NOT_FOUND.get(kind, "NOT_FOUND"), f"{kind.capitalize()} {target_id} does not exist.",
                                **{f"{kind}_id": target_id})
        if not rbac.decide(policies, user, action, target):
            raise forbidden()
        return target

    if conn is not None:
        return await run(conn)
    async with db.tx() as c:
        return await run(c)


async def allowed(conn, user: dict, action: str, target: dict | None) -> bool:
    return rbac.decide(await load_policies(conn), user, action, target)
