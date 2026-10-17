# NaSCon '26: Multi-Sport League & Club Operations Platform

Multi-tenant sports league and club-operations platform: a rule-driven multi-sport league engine, fixture scheduling
(round robin, Swiss, single and double elimination), an event-sourced scoring engine with compensating events,
standings with tie-breakers, roster/transfer/loan management, a concurrency-safe merchandise store with signed PDF
receipts, 5-tier RBAC with tenant isolation, realtime updates, and an offline-first Android app.

## Run the backend (only Docker is required)

```bash
DAY1_SALT=<team-salt> docker compose up -d --build
curl http://localhost:8080/health        # {"status":"ok"} once the DB is reachable and seeded
```

- The API listens on **http://localhost:8080**. Baseline data is seeded on first start and by every `POST /audit/v1/reset`.
- `DAY1_SALT` is read only from the environment (forwarded by compose as `DAY1_SALT: ${DAY1_SALT}`). It is never committed.
  Every variable is listed in [.env.example](.env.example). Copy it to `.env` for local runs (`.env` is gitignored).
- Stop the stack: `docker compose down`. Wipe all data: `docker compose down -v`.

### Services (docker-compose.yml)

| Service | Image | Purpose |
|---|---|---|
| `api` | `./backend` (Python 3.12, FastAPI, uvicorn) | REST API `/audit/v1/*` + `/api/v1/*`, WebSocket `/api/v1/ws` |
| `worker` | `./backend` | Internal job queue consumer (Redis Stream `domain-events`): persists every domain event |
| `postgres` | `postgres:16-alpine` | System of record (append-only `match_events`, `roster_audit`) |
| `redis` | `redis:7-alpine` | Rate limiting, realtime pub/sub, domain-event stream |
| `minio` | `minio/minio` | Object store for receipt PDFs |

## Demo accounts (exist after every startup and every `/reset`)

| Role | Email | Password | Scope |
|---|---|---|---|
| Platform Super-Admin | admin@nascon.test | Nascon@26 | Platform-wide |
| League Organizer | organizer@nascon.test | Nascon@26 | Owns `league-alpha-1` |
| Club Manager | manager@nascon.test | Nascon@26 | Owns `club-alpha-1` |
| Player | player@nascon.test | Nascon@26 | `player-alpha-1` |
| General Viewer | viewer@nascon.test | Nascon@26 | Read-only inside `tenant-alpha` |

Demo data for the app: `league-alpha-1` (football, 4 clubs, double round robin with 4 completed matches, 1 live match with a
pinned jersey, the rest upcoming), club rosters (12 players each), staff, venues, and store items (jersey, scarf, cap with a
scheduled price change, digital wallpaper). The jersey size M starts with stock 1 (graded scenario), so buy size L or the scarf in demos.

## Mobile app (Android)

- Install: `adb install mobile/release/app-release.apk` (Android 10 / API 29+).
- Server address: **Settings** screen inside the app. Emulator: `http://10.0.2.2:8080`; physical phone: `http://<laptop LAN IP>:8080` on the same Wi-Fi.
- Offline: fixtures, standings, and club profiles are cached in SQLite. Scoring and roster actions are queued locally in the
  `/audit/v1/offline-sync` action format and synced automatically when the connection returns.

## Tests

```bash
./run_tests.sh            # unit tests inside the backend image + regenerates COVERAGE.json
./run_tests.sh --local    # same with the host's python3
DAY1_SALT=<salt used for compose> python3 scripts/smoke_test.py   # grader replica against the running stack
```

- `tests/`: pytest unit tests for the domain logic (fixtures, scoring, standings, store, roster, RBAC, sync, schedule).
- `COVERAGE.json`: line coverage of the six graded areas, written by `run_tests.sh` (never edited by hand).
- `scripts/smoke_test.py`: end-to-end checks against `http://localhost:8080`, including 20 concurrent buyers, the full RBAC matrix, rate limiting, roster rules, and offline sync.

## API overview

- **Autograder contract** `/audit/v1/*` (spec section 5): `reset`, `sports`, `fixtures`, `leagues`, `events`, `score/{id}`,
  `standings/{id}`, `roster/setup|transfer|history/{id}`, `checkout`, `inventory/{id}`, `rbac-matrix`, `rbac/*` probes, `offline-sync`.
- **App API** `/api/v1/*` (JWT, rate limited 100 req / 10 s per IP): `auth/login`, `me`, `ping`, `leagues`,
  `leagues/{id}/fixtures|standings`, `matches/{id}` (+ `events`, `status`, `reschedule`, `pin`), `clubs`, `clubs/{id}`,
  `roster/transfer`, `players/{id}/history`, `store/products`, `store/checkout`, `orders`, `orders/{id}/receipt`,
  `orders/{id}/status`, `sync`, `admin/sports`, `admin/leagues`.
- **Realtime** `ws://<host>:8080/api/v1/ws?token=<jwt>`: send `{"action":"subscribe","channels":["match:<id>","league:<id>"]}`.
  The server pushes `match_event` (with live score), `match_status`, `product_pinned`, and `standings_changed`.
- Interactive docs: http://localhost:8080/docs

## Architecture notes

- **Sports are data.** Scoring rules live in `backend/app/seed/sports.json` and `POST /audit/v1/sports`. The engine branches
  only on `scoring_model` (event / innings / round), never on a sport or event name.
- **Event sourcing.** `match_events` is append-only. Scores and standings are folded from the log on every read. Corrections
  are signed compensating events (HMAC-SHA256 with `DAY1_SALT`, canonical JSON per spec 5.3).
- **Concurrency.** Checkout reserves stock with a conditional `UPDATE ... WHERE stock >= q` plus a `CHECK (stock >= 0)`
  constraint, and releases the reservation on gateway failure. Per-match and per-league advisory locks serialize appends.
- **Fixtures.** All generators are our own code: circle-method round robin, Swiss with exact minimum-cost rematch-free pairing
  (Edmonds' blossom algorithm), seeded single and double elimination with byes and bracket reset.
- **RBAC.** The policy matrix is stored as data (`rbac_policies`) and evaluated by `domain/rbac.py`. Tenant isolation is
  absolute for every scoped rule. JWT HS256 tokens have their signature and expiry verified, and `alg:none` is rejected.
