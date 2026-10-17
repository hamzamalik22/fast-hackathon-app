"""FR-5.1 / NFR-5: negative authorization tests for every role boundary + JWT verification."""
import base64
import json
import time

import jwt
import pytest

from app import config
from app.domain.rbac import POLICIES, ROLES, decide, policy_rows
from app.errors import ApiError
from app.security import _local_hit, issue_token, verify_token

USERS = {
    "super_admin": {"role": "super_admin", "tenant_id": None, "league_ids": [], "club_id": None, "player_id": None},
    "league_organizer": {"role": "league_organizer", "tenant_id": "tenant-alpha", "league_ids": ["league-alpha-1"],
                         "club_id": None, "player_id": None},
    "club_manager": {"role": "club_manager", "tenant_id": "tenant-alpha", "league_ids": [], "club_id": "club-alpha-1",
                     "player_id": None},
    "player": {"role": "player", "tenant_id": "tenant-alpha", "league_ids": [], "club_id": "club-alpha-1",
               "player_id": "player-alpha-1"},
    "viewer": {"role": "viewer", "tenant_id": "tenant-alpha", "league_ids": [], "club_id": None, "player_id": None},
}
OWN_LEAGUE = {"league_id": "league-alpha-1", "tenant_id": "tenant-alpha"}
OTHER_LEAGUE = {"league_id": "league-alpha-2", "tenant_id": "tenant-alpha"}
FOREIGN_LEAGUE = {"league_id": "league-beta-1", "tenant_id": "tenant-beta"}
OWN_CLUB = {"club_id": "club-alpha-1", "tenant_id": "tenant-alpha"}
OTHER_CLUB = {"club_id": "club-alpha-2", "tenant_id": "tenant-alpha"}
FOREIGN_CLUB = {"club_id": "club-beta-1", "tenant_id": "tenant-beta"}
OWN_PLAYER = {"player_id": "player-alpha-1", "club_id": "club-alpha-1", "tenant_id": "tenant-alpha"}
OTHER_PLAYER = {"player_id": "player-alpha-2", "club_id": "club-alpha-2", "tenant_id": "tenant-alpha"}
FOREIGN_PLAYER = {"player_id": "player-beta-1", "club_id": "club-beta-1", "tenant_id": "tenant-beta"}

A, D = True, False
# Spec 5.13 expected matrix: (action, target) -> [super, organizer, manager, player, viewer]
MATRIX = [
    ("tenants.create", None, [A, D, D, D, D]),
    ("league.fixtures.write", OWN_LEAGUE, [A, A, D, D, D]),
    ("league.fixtures.write", OTHER_LEAGUE, [A, D, D, D, D]),
    ("league.fixtures.write", FOREIGN_LEAGUE, [A, D, D, D, D]),
    ("club.roster.write", OWN_CLUB, [A, D, A, D, D]),
    ("club.roster.write", OTHER_CLUB, [A, D, D, D, D]),
    ("club.roster.write", FOREIGN_CLUB, [A, D, D, D, D]),
    ("club.products.write", OWN_CLUB, [A, D, A, D, D]),
    ("club.products.write", OTHER_CLUB, [A, D, D, D, D]),
    ("club.products.write", FOREIGN_CLUB, [A, D, D, D, D]),
    ("player.update", OWN_PLAYER, [A, D, A, A, D]),
    ("player.update", OTHER_PLAYER, [A, D, D, D, D]),
    ("player.update", FOREIGN_PLAYER, [A, D, D, D, D]),
    ("club.read", OWN_CLUB, [A, A, A, A, A]),
    ("club.read", OTHER_CLUB, [A, A, A, A, A]),
    ("club.read", FOREIGN_CLUB, [A, D, D, D, D]),
    ("platform.config", None, [A, D, D, D, D]),
]
CASES = [(action, target, role, exp) for action, target, row in MATRIX for role, exp in zip(ROLES, row)]


@pytest.mark.parametrize("action,target,role,expected", CASES)
def test_spec_matrix(action, target, role, expected):
    assert decide(POLICIES, USERS[role], action, target) is expected


def test_production_actions_and_unknowns():
    org = USERS["league_organizer"]
    assert decide(POLICIES, org, "match.score", OWN_LEAGUE) and not decide(POLICIES, org, "match.score", OTHER_LEAGUE)
    assert not decide(POLICIES, USERS["viewer"], "match.score", OWN_LEAGUE)
    assert decide(POLICIES, USERS["club_manager"], "roster.transfer", OWN_CLUB)
    assert not decide(POLICIES, USERS["club_manager"], "roster.transfer", FOREIGN_CLUB)
    assert not decide(POLICIES, USERS["viewer"], "no.such.action", OWN_CLUB)
    assert not decide(POLICIES, {**USERS["viewer"], "role": "hacker"}, "club.read", OWN_CLUB)
    assert not decide({"x": {"viewer": "weird"}}, USERS["viewer"], "x", OWN_CLUB)
    assert not decide(POLICIES, USERS["player"], "player.update", {"tenant_id": "tenant-alpha"})
    assert len(policy_rows()) == sum(len(v) for v in POLICIES.values())


def _user_row(role):
    u = USERS[role]
    return {"user_id": f"user-{role}", "role": role, "tenant_id": u["tenant_id"], "league_ids": json.dumps(u["league_ids"]),
            "club_id": u["club_id"], "player_id": u["player_id"]}


def test_jwt_roundtrip_and_rejections():
    token, exp = issue_token(_user_row("league_organizer"))
    claims = verify_token(token)
    assert claims["role"] == "league_organizer" and claims["league_ids"] == ["league-alpha-1"] and exp - time.time() > 3600
    head, body, sig = token.split(".")
    bad = [f"{head}.{body}.{sig[:-2]}xx", "not-a-jwt",
           base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode() + f".{body}.",
           jwt.encode({"sub": "u", "role": "super_admin", "exp": int(time.time()) - 10}, config.JWT_SECRET, algorithm="HS256"),
           jwt.encode({"sub": "u", "role": "super_admin", "exp": int(time.time()) + 99}, "wrong-secret", algorithm="HS256"),
           jwt.encode({"sub": "u", "role": "super_admin"}, config.JWT_SECRET, algorithm="HS256")]
    for t in bad:
        with pytest.raises(ApiError) as e:
            verify_token(t)
        assert e.value.status == 401 and e.value.code == "UNAUTHENTICATED"


def test_local_rate_limit_window():
    for i in range(100):
        assert _local_hit("1.2.3.4", 1000 + i, 10_000, 100)[0]
    allowed, oldest = _local_hit("1.2.3.4", 2000, 10_000, 100)
    assert not allowed and oldest == 1000
    assert _local_hit("1.2.3.4", 11_001, 10_000, 100)[0]
