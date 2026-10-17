"""Five-tier RBAC (FR-5.1). The matrix is data (seeded into rbac_policies); decide() is the only evaluator."""

ROLES = ("super_admin", "league_organizer", "club_manager", "player", "viewer")

ALL_SAME_TENANT = {r: "same_tenant" for r in ROLES if r != "super_admin"}

# action -> role -> scope. A role missing from an action is denied.
POLICIES: dict[str, dict[str, str]] = {
    # Probe routes of spec 5.13
    "tenants.create": {"super_admin": "any"},
    "league.fixtures.write": {"super_admin": "any", "league_organizer": "own_league"},
    "club.roster.write": {"super_admin": "any", "club_manager": "own_club"},
    "club.products.write": {"super_admin": "any", "club_manager": "own_club"},
    "player.update": {"super_admin": "any", "club_manager": "own_club_player", "player": "self"},
    "club.read": {"super_admin": "any", **ALL_SAME_TENANT},
    "platform.config": {"super_admin": "any"},
    # Production /api/v1 actions
    "league.read": {"super_admin": "any", **ALL_SAME_TENANT},
    "match.score": {"super_admin": "any", "league_organizer": "own_league"},
    "match.manage": {"super_admin": "any", "league_organizer": "own_league"},
    "roster.transfer": {"super_admin": "any", "club_manager": "own_club"},
    "store.buy": {"super_admin": "any", **ALL_SAME_TENANT},
    "order.manage": {"super_admin": "any", "club_manager": "own_club"},
    "admin.config": {"super_admin": "any"},
    "league.admin": {"super_admin": "any", "league_organizer": "same_tenant"},
}


def policy_rows() -> list[tuple[str, str, str]]:
    return [(action, role, scope) for action, roles in POLICIES.items() for role, scope in roles.items()]


def decide(policies: dict, user: dict, action: str, target: dict | None = None) -> bool:
    """policies: action -> role -> scope (loaded from the DB). target: tenant_id/league_id/club_id/player_id."""
    scope = policies.get(action, {}).get(user.get("role"))
    if scope is None:
        return False
    if scope == "any":
        return True
    target = target or {}
    if target.get("tenant_id") is None or target.get("tenant_id") != user.get("tenant_id"):
        return False  # tenant isolation is absolute for every scoped rule
    if scope == "same_tenant":
        return True
    if scope == "own_league":
        return target.get("league_id") is not None and target.get("league_id") in (user.get("league_ids") or [])
    if scope in ("own_club", "own_club_player"):
        return target.get("club_id") is not None and target.get("club_id") == user.get("club_id")
    if scope == "self":
        return target.get("player_id") is not None and target.get("player_id") == user.get("player_id")
    return False
