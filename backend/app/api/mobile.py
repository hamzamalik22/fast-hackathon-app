"""Production API for the mobile app (/api/v1/*, rate limited, JWT + RBAC). Reuses the audit services."""
import uuid
from datetime import datetime

import bcrypt
from fastapi import APIRouter, Request

from .. import db
from ..domain import schedule, scoring
from ..domain import store as store_domain
from ..errors import ApiError, conflict, not_found, validation_error
from ..http import read_json, respond
from ..security import current_user, issue_token
from ..services import checkout as checkout_svc
from ..services import leagues as leagues_svc
from ..services import rbac as rbac_svc
from ..services import realtime
from ..services import roster as roster_svc
from ..services import scoring as scoring_svc
from ..services import sync as sync_svc
from ..validation import is_id, parse_ts

router = APIRouter(prefix="/api/v1")


def _public_user(u: dict) -> dict:
    lids = u["league_ids"] if isinstance(u["league_ids"], list) else db.lj(u["league_ids"])
    return {"user_id": u["user_id"], "email": u["email"], "name": u["name"], "role": u["role"],
            "tenant_id": u["tenant_id"], "league_ids": lids, "club_id": u["club_id"], "player_id": u["player_id"]}


async def _tenant(conn, tenant_id: str | None) -> dict:
    row = await db.fetchone(conn, "SELECT * FROM tenants WHERE tenant_id=%s", (tenant_id or "tenant-alpha",))
    return dict(row) if row else {}


async def _team_names(conn) -> dict:
    return {r["club_id"]: r["name"] for r in await db.fetchall(conn, "SELECT club_id, name FROM clubs")}


@router.get("/ping")
async def ping():
    return {"pong": True}


@router.post("/auth/login")
async def login(request: Request):
    b = await read_json(request)
    email, password = b.get("email"), b.get("password")
    if not isinstance(email, str) or not isinstance(password, str):
        raise validation_error([k for k in ("email", "password") if not isinstance(b.get(k), str)])
    async with db.tx() as conn:
        u = await db.fetchone(conn, "SELECT * FROM users WHERE lower(email)=lower(%s)", (email.strip(),))
        if u is None or not bcrypt.checkpw(password.encode(), u["password_hash"].encode()):
            raise ApiError(401, "INVALID_CREDENTIALS", "Email or password is incorrect.", {})
        tenant = await _tenant(conn, u["tenant_id"])
    token, exp = issue_token(u)
    return {"token": token, "expires_at": datetime.utcfromtimestamp(exp).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "user": _public_user(u), "tenant": tenant}


@router.get("/me")
async def me(request: Request):
    claims = current_user(request)
    async with db.tx() as conn:
        u = await db.fetchone(conn, "SELECT * FROM users WHERE user_id=%s", (claims["sub"],))
        if u is None:
            raise ApiError(401, "UNAUTHENTICATED", "Account no longer exists.", {})
        tenant = await _tenant(conn, u["tenant_id"])
    return {"user": _public_user(u), "tenant": tenant}


# ------------------------------------------------------------------ leagues, fixtures, standings
@router.get("/leagues")
async def leagues(request: Request):
    claims = current_user(request)
    async with db.tx() as conn:
        rows = await db.fetchall(conn, "SELECT l.league_id, l.name, l.season, l.sport_id, l.tenant_id, l.format, "
                                       "s.name AS sport_name, s.scoring_model FROM leagues l "
                                       "JOIN sports s ON s.sport_id = l.sport_id WHERE l.tenant_id IS NOT NULL "
                                       "AND (%s OR l.tenant_id = %s) ORDER BY l.league_id",
                                 (claims["role"] == "super_admin", claims.get("tenant_id")))
    return {"leagues": rows}


async def _league_view(claims: dict, league_id: str):
    async with db.tx() as conn:
        await rbac_svc.authorize(claims, "league.read", "league", league_id, conn=conn)
        league = await db.fetchone(conn, "SELECT * FROM leagues WHERE league_id=%s", (league_id,))
        sport = await scoring_svc.get_sport(conn, league["sport_id"])
        states = await leagues_svc.load_league_states(conn, league, sport)
        names = await _team_names(conn)
    return league, sport, states, names


def _match_summary(fx: dict, names: dict, sport: dict) -> dict:
    m, st = fx["match"], fx["state"]
    innings = sport["scoring_model"] == "innings"
    bpo = sport["periods"].get("balls_per_over", 6) if innings else 6

    def side(sd):
        return {"team_id": sd.team_id, "name": names.get(sd.team_id, sd.team_id), "score": sd.score,
                "wickets": sd.wickets if innings else None,
                "overs": f"{sd.balls // bpo}.{sd.balls % bpo}" if innings else None}
    return {"match_id": m["match_id"], "round": m["round"],
            "scheduled_at": m["scheduled_at"].strftime("%Y-%m-%dT%H:%M:%SZ") if m["scheduled_at"] else None,
            "venue": m["venue_id"], "status": schedule.display_status(st.status, m["admin_status"]),
            "version": len(fx["events"]), "sport_id": sport["sport_id"], "scoring_model": sport["scoring_model"],
            "home": side(st.home), "away": side(st.away)}


@router.get("/leagues/{league_id}/fixtures")
async def league_fixtures(request: Request, league_id: str):
    _, sport, states, names = await _league_view(current_user(request), league_id)
    return {"league_id": league_id, "matches": [_match_summary(fx, names, sport) for fx in states]}


@router.get("/leagues/{league_id}/standings")
async def league_standings(request: Request, league_id: str):
    _, _, _, names = await _league_view(current_user(request), league_id)
    table = await leagues_svc.get_standings(league_id)
    table["team_names"] = {r["team_id"]: names.get(r["team_id"], r["team_id"]) for r in table["table"]}
    return table


# ------------------------------------------------------------------ matches
async def _match_target(conn, claims: dict, match_id: str, action: str) -> dict:
    target = await rbac_svc.target_for(conn, "match", match_id)
    if target is None:
        raise not_found("MATCH_NOT_FOUND", f"Match {match_id} does not exist.", match_id=match_id)
    if not await rbac_svc.allowed(conn, claims, action, target):
        raise rbac_svc.forbidden()
    return target


@router.get("/matches/{match_id}")
async def match_detail(request: Request, match_id: str):
    claims = current_user(request)
    async with db.tx() as conn:
        target = await _match_target(conn, claims, match_id, "league.read")
        can_score = await rbac_svc.allowed(conn, claims, "match.score", target)
        match = await scoring_svc.get_match(conn, match_id)
        sport = await scoring_svc.get_sport(conn, match["sport_id"])
        events = await scoring_svc.load_events(conn, match_id)
        names = await _team_names(conn)
        pinned = None
        if match["pinned_product_id"]:
            pinned = await _product(conn, match["pinned_product_id"])
    proj = scoring.project(sport, match, events)
    proj["status"] = schedule.display_status(proj["status"], match["admin_status"])
    proj.update({"scheduled_at": match["scheduled_at"].strftime("%Y-%m-%dT%H:%M:%SZ") if match["scheduled_at"] else None,
                 "venue": match["venue_id"], "home_name": names.get(match["home_team_id"], match["home_team_id"]),
                 "away_name": names.get(match["away_team_id"], match["away_team_id"]),
                 "sport": {"sport_id": sport["sport_id"], "name": sport["name"], "scoring_model": sport["scoring_model"],
                           "scoring_events": sport["scoring_events"], "draw_allowed": sport["draw_allowed"]},
                 "pinned_product": pinned, "can_score": can_score})
    return proj


@router.post("/matches/{match_id}/events")
async def match_event(request: Request, match_id: str):
    claims = current_user(request)
    body = await read_json(request)
    async with db.tx() as conn:
        await _match_target(conn, claims, match_id, "match.score")
    body["match_id"] = match_id
    status, resp = await scoring_svc.append_event(body)
    return respond(status, resp)


@router.patch("/matches/{match_id}/status")
async def match_status(request: Request, match_id: str):
    claims = current_user(request)
    body = await read_json(request)
    target_status = body.get("status")
    if target_status not in ("postponed", "abandoned", "cancelled", "upcoming"):
        raise validation_error(["status"], "Use match_start/match_end events for live and completed.")
    async with db.tx() as conn:
        await _match_target(conn, claims, match_id, "match.manage")
        match = await scoring_svc.get_match(conn, match_id)
        sport = await scoring_svc.get_sport(conn, match["sport_id"])
        st = scoring.fold(sport, match, await scoring_svc.load_events(conn, match_id))
        current = schedule.display_status(st.status, match["admin_status"])
        if not schedule.can_transition(current, target_status):
            raise conflict("ILLEGAL_TRANSITION", f"Cannot move a {current} match to {target_status}.",
                           match_id=match_id, status=current)
        await conn.execute("UPDATE matches SET admin_status=%s WHERE match_id=%s",
                           (None if target_status == "upcoming" else target_status, match_id))
    await realtime.publish(f"match:{match_id}", {"type": "match_status", "match_id": match_id, "status": target_status})
    if match["league_id"]:
        await realtime.publish(f"league:{match['league_id']}", {"type": "standings_changed", "league_id": match["league_id"]})
    await realtime.emit_domain_event("match.status_changed", {"match_id": match_id, "from": current, "to": target_status})
    return {"match_id": match_id, "status": target_status}


@router.post("/matches/{match_id}/reschedule")
async def reschedule(request: Request, match_id: str):
    claims = current_user(request)
    body = await read_json(request)
    start = parse_ts(body.get("scheduled_at"))
    venue = body.get("venue_id")
    if start is None or (venue is not None and not is_id(venue)):
        raise validation_error([k for k, ok in (("scheduled_at", start is not None),
                                                ("venue_id", venue is None or is_id(venue))) if not ok])
    async with db.tx() as conn:
        await _match_target(conn, claims, match_id, "match.manage")
        match = await scoring_svc.get_match(conn, match_id)
        others = await db.fetchall(conn, "SELECT * FROM matches WHERE scheduled_at IS NOT NULL AND match_id <> %s",
                                   (match_id,))
        vrow = await db.fetchone(conn, "SELECT open_hour, close_hour FROM venues WHERE venue_id=%s", (venue,)) if venue else None
        players = await db.fetchall(conn, "SELECT player_id, squad_id FROM roster_players WHERE squad_id IS NOT NULL")
        squad_players: dict[str, set] = {}
        for p in players:
            squad_players.setdefault(p["squad_id"], set()).add(p["player_id"])
        conflicts = schedule.detect_conflicts(match, start, venue, others, squad_players=squad_players,
                                              venue_hours=(vrow["open_hour"], vrow["close_hour"]) if vrow else None)
        if conflicts:
            raise conflict("SCHEDULE_CONFLICT", "The new slot conflicts with existing fixtures.", conflicts=conflicts)
        await conn.execute("UPDATE matches SET scheduled_at=%s, venue_id=COALESCE(%s, venue_id) WHERE match_id=%s",
                           (start, venue, match_id))
    await realtime.publish(f"match:{match_id}", {"type": "match_status", "match_id": match_id, "status": "rescheduled"})
    return {"match_id": match_id, "scheduled_at": body["scheduled_at"], "venue_id": venue}


@router.post("/matches/{match_id}/pin")
async def pin_product(request: Request, match_id: str):
    claims = current_user(request)
    body = await read_json(request)
    pid = body.get("product_id")
    async with db.tx() as conn:
        await _match_target(conn, claims, match_id, "match.manage")
        product = None
        if pid is not None:
            product = await _product(conn, pid)
            if product is None:
                raise not_found("PRODUCT_NOT_FOUND", f"Product {pid} does not exist.", product_id=pid)
        await conn.execute("UPDATE matches SET pinned_product_id=%s WHERE match_id=%s", (pid, match_id))
    await realtime.publish(f"match:{match_id}", {"type": "product_pinned", "match_id": match_id, "product": product})
    return {"match_id": match_id, "pinned_product": product}


# ------------------------------------------------------------------ clubs & roster
@router.get("/clubs")
async def clubs(request: Request):
    claims = current_user(request)
    async with db.tx() as conn:
        rows = await db.fetchall(conn, "SELECT club_id, name, logo_url, tenant_id FROM clubs WHERE %s OR tenant_id=%s "
                                       "ORDER BY club_id", (claims["role"] == "super_admin", claims.get("tenant_id")))
    return {"clubs": rows}


@router.get("/clubs/{club_id}")
async def club_profile(request: Request, club_id: str):
    claims = current_user(request)
    async with db.tx() as conn:
        await rbac_svc.authorize(claims, "club.read", "club", club_id, conn=conn)
        c = await db.fetchone(conn, "SELECT * FROM clubs WHERE club_id=%s", (club_id,))
        tenant = await _tenant(conn, c["tenant_id"])
        sq = await db.fetchone(conn, "SELECT league_id FROM squads WHERE club_id=%s ORDER BY league_id LIMIT 1", (club_id,))
        league_id = sq["league_id"] if sq else None
        squads = await db.fetchall(conn, "SELECT squad_id, name, club_id FROM squads WHERE league_id=%s ORDER BY squad_id",
                                   (league_id,)) if league_id else []
        players = await db.fetchall(
            conn, "SELECT p.*, (SELECT count(*) FROM roster_audit a WHERE a.player_id = p.player_id) AS audit_count "
                  "FROM roster_players p JOIN squads s ON s.league_id = p.league_id AND s.squad_id = p.squad_id "
                  "WHERE s.club_id=%s ORDER BY p.position, p.name", (club_id,))
    roster = [{"player_id": p["player_id"], "name": p["name"], "position": p["position"], "role": p["role"],
               "squad_id": p["squad_id"], "parent_squad_id": p["parent_squad_id"],
               "registration_type": p["registration_type"],
               "loan_end_date": p["loan_end_date"].isoformat() if p["loan_end_date"] else None,
               "audit_count": p["audit_count"]} for p in players]
    return {"club_id": c["club_id"], "name": c["name"], "tenant_id": c["tenant_id"], "logo_url": c["logo_url"],
            "colors": {"primary": tenant.get("primary_color"), "accent": tenant.get("accent_color")},
            "venue": {"name": c["venue_name"], "lat": c["lat"], "lng": c["lng"]}, "socials": db.lj(c["socials"]),
            "staff": db.lj(c["staff"]), "stats": db.lj(c["stats"]), "roster_league_id": league_id, "squads": squads,
            "roster": roster}


@router.post("/clubs/{club_id}/players")
async def add_player(request: Request, club_id: str):
    """Register a new player in the club's squad (manager of that club). Audited like every roster change."""
    claims = current_user(request)
    body = await read_json(request)
    name, position, role = body.get("name"), body.get("position"), body.get("role") or "substitute"
    bad = [k for k, ok in (("name", isinstance(name, str) and 1 <= len(name.strip()) <= 80),
                           ("position", isinstance(position, str) and 1 <= len(position.strip()) <= 20),
                           ("role", role in ("captain", "vice_captain", "starter", "substitute"))) if not ok]
    if bad:
        raise validation_error(bad)
    async with db.tx() as conn:
        sq = await db.fetchone(conn, "SELECT league_id, squad_id, tenant_id FROM squads WHERE club_id=%s "
                                     "ORDER BY league_id LIMIT 1", (club_id,))
        if sq is None:
            raise not_found("CLUB_NOT_FOUND", f"Club {club_id} has no squad.", club_id=club_id)
        if not await rbac_svc.allowed(conn, claims, "roster.transfer", {"tenant_id": sq["tenant_id"], "club_id": club_id}):
            raise rbac_svc.forbidden()
        await db.lock(conn, "roster:" + sq["league_id"])
        league = await roster_svc.load_league(conn, sq["league_id"])
        size = (await db.fetchone(conn, "SELECT count(*) AS n FROM roster_players WHERE league_id=%s AND squad_id=%s",
                                  (sq["league_id"], sq["squad_id"])))["n"]
        if league and size + 1 > league["max_squad_size"]:
            raise conflict("SQUAD_FULL", "The squad is full.", squad_id=sq["squad_id"])
        pid = f"pl-{uuid.uuid4().hex[:10]}"
        today = datetime.utcnow().date()
        await conn.execute("INSERT INTO roster_players(player_id, league_id, name, position, squad_id, role, "
                           "registration_type, start_date, initial_squad_id) VALUES (%s,%s,%s,%s,%s,%s,'registration',%s,NULL)",
                           (pid, sq["league_id"], name.strip(), position.strip().lower(), sq["squad_id"], role, today))
        await roster_svc._append_audit(conn, {"action": "register", "player_id": pid, "league_id": sq["league_id"],
                                              "from_squad_id": None, "to_squad_id": sq["squad_id"],
                                              "effective_date": today.isoformat(), "state": "active",
                                              "who": claims["sub"], "why": "New registration"})
    return respond(201, {"player": {"player_id": pid, "name": name.strip(), "position": position.strip().lower(),
                                    "role": role, "squad_id": sq["squad_id"], "parent_squad_id": None,
                                    "registration_type": "registration", "loan_end_date": None, "audit_count": 1}})


@router.post("/roster/transfer")
async def roster_transfer(request: Request):
    claims = current_user(request)
    body = await read_json(request)
    body["requested_by"] = claims["sub"]
    async with db.tx() as conn:
        sq = await db.fetchone(conn, "SELECT s.club_id, s.tenant_id FROM squads s WHERE s.league_id=%s AND s.squad_id=%s",
                               (body.get("league_id"), body.get("from_squad_id")))
        if sq is not None and not await rbac_svc.allowed(conn, claims, "roster.transfer", sq):
            raise rbac_svc.forbidden()
    status, resp = await roster_svc.transfer(body)
    await realtime.emit_domain_event("roster.changed", {"player_id": body.get("player_id"), "type": body.get("type")})
    return respond(status, resp)


@router.get("/players/{player_id}/history")
async def player_history(request: Request, player_id: str, as_of: str | None = None):
    claims = current_user(request)
    await rbac_svc.authorize(claims, "league.read", "player", player_id)
    return await roster_svc.history(player_id, as_of)


# ------------------------------------------------------------------ store
async def _product(conn, product_id: str) -> dict | None:
    p = await db.fetchone(conn, "SELECT * FROM products WHERE product_id=%s", (product_id,))
    if p is None:
        return None
    variants = await db.fetchall(
        conn, "SELECT v.variant_id, v.size, v.color, v.stock, COALESCE((SELECT ps.price_minor FROM price_schedules ps "
              "WHERE ps.variant_id = v.variant_id AND ps.effective_from <= now() ORDER BY ps.effective_from DESC "
              "LIMIT 1), v.price_minor) AS price_minor FROM variants v WHERE v.product_id=%s ORDER BY v.variant_id",
        (product_id,))
    return {**p, "variants": variants, "price_minor": min((v["price_minor"] for v in variants), default=0)}


@router.get("/store/products")
async def products(request: Request):
    claims = current_user(request)
    async with db.tx() as conn:
        ids = await db.fetchall(conn, "SELECT product_id FROM products WHERE %s OR tenant_id=%s ORDER BY product_id",
                                (claims["role"] == "super_admin", claims.get("tenant_id")))
        return {"products": [await _product(conn, r["product_id"]) for r in ids]}


@router.post("/store/checkout")
async def store_checkout(request: Request):
    claims = current_user(request)
    body = await read_json(request)
    body["customer_id"] = claims["sub"]
    status, resp = await checkout_svc.checkout(body)
    return respond(status, resp)


@router.get("/orders")
async def my_orders(request: Request):
    claims = current_user(request)
    async with db.tx() as conn:
        rows = await db.fetchall(conn, "SELECT order_id, status, total_minor, created_at FROM orders "
                                       "WHERE customer_id=%s AND response IS NOT NULL ORDER BY created_at DESC",
                                 (claims["sub"],))
    return {"orders": [{**r, "created_at": r["created_at"].strftime("%Y-%m-%dT%H:%M:%SZ")} for r in rows]}


@router.get("/orders/{order_id}/receipt")
async def order_receipt(request: Request, order_id: str):
    claims = current_user(request)
    async with db.tx() as conn:
        row = await db.fetchone(conn, "SELECT customer_id, response FROM orders WHERE order_id=%s", (order_id,))
    if row is None or row["response"] is None:
        raise not_found("ORDER_NOT_FOUND", f"Order {order_id} does not exist.", order_id=order_id)
    if row["customer_id"] != claims["sub"] and claims["role"] != "super_admin":
        raise rbac_svc.forbidden()
    return db.lj(row["response"])["receipt"]


@router.patch("/orders/{order_id}/status")
async def order_status(request: Request, order_id: str):
    claims = current_user(request)
    body = await read_json(request)
    target = body.get("status")
    async with db.tx() as conn:
        o = await db.fetchone(conn, "SELECT o.status, p.club_id, p.tenant_id FROM orders o "
                                    "JOIN variants v ON v.variant_id = (SELECT (r->>'variant_id') FROM "
                                    "json_array_elements(o.response::json->'items') r LIMIT 1) "
                                    "JOIN products p ON p.product_id = v.product_id WHERE o.order_id=%s FOR UPDATE OF o",
                              (order_id,))
        if o is None:
            raise not_found("ORDER_NOT_FOUND", f"Order {order_id} does not exist.", order_id=order_id)
        if not await rbac_svc.allowed(conn, claims, "order.manage", o):
            raise rbac_svc.forbidden()
        if not store_domain.can_transition(o["status"], target):
            raise conflict("ILLEGAL_TRANSITION", f"Cannot move order from {o['status']} to {target}.", order_id=order_id)
        await conn.execute("UPDATE orders SET status=%s WHERE order_id=%s", (target, order_id))
        await conn.execute("INSERT INTO order_events(order_id, from_status, to_status) VALUES (%s,%s,%s)",
                           (order_id, o["status"], target))
    await realtime.emit_domain_event("order.status_changed", {"order_id": order_id, "from": o["status"], "to": target})
    return {"order_id": order_id, "status": target}


# ------------------------------------------------------------------ offline sync (same code as /audit/v1/offline-sync)
@router.post("/sync")
async def sync(request: Request):
    claims = current_user(request)
    body = await read_json(request)

    async def authorize(kind: str, info: dict) -> str | None:
        async with db.tx() as conn:
            if kind == "score_event":
                target = await rbac_svc.target_for(conn, "match", info["match_id"]) if info.get("match_id") else None
                ok = target is not None and await rbac_svc.allowed(conn, claims, "match.score", target)
            else:
                ok = await rbac_svc.allowed(conn, claims, "roster.transfer", info)
        return None if ok else "FORBIDDEN"

    for a in body.get("actions") or []:
        if isinstance(a, dict) and a.get("type") == "roster_transfer" and isinstance(a.get("payload"), dict):
            a["payload"].setdefault("requested_by", claims["sub"])
    return await sync_svc.offline_sync(body, authorize=authorize)


# ------------------------------------------------------------------ admin configuration
@router.post("/admin/sports")
async def admin_sports(request: Request):
    await rbac_svc.authorize(current_user(request), "admin.config")
    return respond(201, await scoring_svc.create_sport(await read_json(request)))


@router.post("/admin/leagues")
async def admin_leagues(request: Request):
    claims = current_user(request)
    async with db.tx() as conn:
        if not await rbac_svc.allowed(conn, claims, "league.admin", {"tenant_id": claims.get("tenant_id")}):
            raise rbac_svc.forbidden()
    body = await read_json(request)
    resp = await leagues_svc.create_league(body)
    async with db.tx() as conn:
        await conn.execute("UPDATE leagues SET tenant_id=%s, name=%s, format=%s WHERE league_id=%s",
                           (claims.get("tenant_id") or body.get("tenant_id"), body.get("name"),
                            body.get("format") or "league", body["league_id"]))
    return respond(201, resp)
