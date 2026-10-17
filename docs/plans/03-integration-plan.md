# Plan 3: Integration (backend ↔ app, repo submission, verification, judging)

This plan is the **single source of truth** for everything shared between `backend/` and `mobile/`: the `/api/v1` contract, the WebSocket protocol,
demo data, offline-sync wiring, error messages. It also covers the submission package, the verification scripts and the judging runbook.
Backend internals: `01-backend-plan.md`. App internals: `02-app-plan.md`.

---

## 0. Submission rules (do these first: they are cheap points)

- [ ] **Before 11:15:** the GitHub repo `hamzamalik22/fast-hackathon-app` is **public** and its URL is **registered at the venue desk**.
- [ ] **Push checkpoints (−2 each missed, max −8):** at least one pushed commit in **each** window: 10:45–11:45 · 11:45–12:45 · 12:45–13:45 · 13:45–14:45.
      Push every ~30 min; set phone alarms at 11:30, 12:30, 13:30 and 14:30.
- [ ] The final push is **≤ 14:55** (the grader takes the last commit pushed at or before 15:05:00; Phase I locks at 15:00).
- [ ] Rename `app/` → `mobile/` (spec requires `mobile/release/app-release.apk`).
- [ ] Repo root must contain:

| Path | Owner | Content |
|---|---|---|
| `docker-compose.yml` | backend | whole stack; API on 8080; `DAY1_SALT: ${DAY1_SALT}` |
| `.env.example` | backend | **every** env var (`DAY1_SALT=replace-with-team-salt`, `JWT_SECRET`, `POSTGRES_*`, `DATABASE_URL`, `REDIS_URL`, `MINIO_*`), **never the real salt** |
| `README.md` | integration | run instructions + the 5 demo accounts table (§10) |
| `TRACEABILITY.md` | integration | every FR/NFR id → source files → tests (§10) |
| `tests/`, `run_tests.sh`, `COVERAGE.json` | backend | `run_tests.sh` regenerates COVERAGE.json (backend plan §11) |
| `mobile/` + `mobile/release/app-release.apk` | mobile | source + release APK |

- [ ] `.gitignore`: `.env`, `.venv/`, `__pycache__/`, `node_modules/`, `mobile/android/`, `mobile/ios/`, `coverage.json`
      (lowercase raw file; the root `COVERAGE.json` **is** committed), `*.keystore`. Keep the real salt in a local `.env` only.

## 1. Ambiguities: ask the organizers in writing before 13:00 (spec §9.5)

Send these early. Until they answer, use the default in brackets (already built into the backend plan).
1. Seeded event keys: `free_throw`, `two_pointer`, `three_pointer`, `dot_ball`, `single`, `two`, `four`, `six`, `wide`, `no_ball`, `wicket`, `round_win`, `goal`? [yes, snake_case]
2. Single-elim `TP` placement in the response? [inside the final round's `matches`]
3. `resolved_by` for the last team of a tied group? [null]
4. Does a `match_init` with `league_id` count in that league's standings? [yes, if both teams belong to the league]
5. Swiss with odd n when every team has already had a bye? [all teams become bye candidates, same ordering]
6. Checkout replay of a failed (402/409) order_id? [re-evaluated, not stored]

## 2. Shared conventions

- Base URL is configurable in the app (default `http://10.0.2.2:8080`). Everything is JSON UTF-8.
  The error body is identical to the audit one: `{"error":{"code","message","details"}}`.
- Auth: `Authorization: Bearer <jwt>` on every `/api/v1/*` route except `auth/login` and `ping`. Role strings:
  `super_admin | league_organizer | club_manager | player | viewer`.
- **Rate limit: 100 req / 10 s per IP on `/api/v1/*`.** The app must not poll `/api/v1`. Use the WebSocket for live data and `GET /health` (exempt) for reachability.
  On a 429, the app waits `Retry-After` and shows "Busy, retrying…".
- Ids, timestamps and money follow spec §5.2. The app generates UUIDs for `order_id`, `event_id`, `request_id`, `action_id`, `device_id`.
- **Same code path rule:** every `/api/v1` mutation calls the same service function as the matching `/audit/v1` route, with an RBAC check (`domain/rbac.py`) in front and the tenant taken from the JWT.

## 3. `/api/v1` contract

| Method & path | Auth / RBAC | Request | Response 2xx |
|---|---|---|---|
| `POST /api/v1/auth/login` | none | `{email, password}` | `{token, expires_at, user{user_id,email,name,role,tenant_id,league_ids[],club_id,player_id}, tenant{tenant_id,name,logo_url,primary_color,accent_color}}`; bad credentials → 401 `INVALID_CREDENTIALS` |
| `GET /api/v1/me` | any | – | same as login, without the token |
| `GET /api/v1/ping` | none | – | `{"pong":true}` (rate-limit probe) |
| `GET /api/v1/leagues` | any; own tenant (super: all) | – | `{leagues:[{league_id,name,season,sport_id,sport_name,scoring_model,tenant_id,format}]}` |
| `GET /api/v1/leagues/{id}/fixtures` | same tenant | – | `{league_id, matches:[{match_id,round,scheduled_at,venue,status,version,home{team_id,name,score},away{…}}]}`; `status` ∈ upcoming, in_progress, completed, postponed, abandoned, cancelled |
| `GET /api/v1/leagues/{id}/standings` | same tenant | – | the audit standings object + `team_names{team_id:name}` |
| `GET /api/v1/matches/{id}` | same tenant | – | the audit score projection + `scheduled_at, venue, home_name, away_name, sport{sport_id,name,scoring_model,scoring_events{key:{…}}}, pinned_product{product_id,name,image_url,price_minor}\|null, can_score` |
| `POST /api/v1/matches/{id}/events` | organizer of the match's league, or super | audit `/events` body | audit event response |
| `PATCH /api/v1/matches/{id}/status` | organizer (own) / super | `{status, reason?}` | `{match_id,status}`; 409 `ILLEGAL_TRANSITION` |
| `POST /api/v1/matches/{id}/reschedule` | organizer (own) / super | `{scheduled_at, venue_id}` | `{match_id,scheduled_at,venue_id}`; 409 `SCHEDULE_CONFLICT` with `details.conflicts[{type,entity_ids}]` |
| `POST /api/v1/matches/{id}/pin` | organizer (own) / club_manager (own product) / super | `{product_id\|null}` | `{match_id,pinned_product}` + WS broadcast |
| `GET /api/v1/clubs` | same tenant | – | `{clubs:[{club_id,name,logo_url}]}` |
| `GET /api/v1/clubs/{id}` | same tenant (P6 rule) | – | `{club_id,name,tenant_id,logo_url,colors{primary,accent},venue{name,lat,lng},socials{x,instagram,…},staff[{name,role}],stats[{season,played,won,drawn,lost}],roster_league_id,squads[{squad_id,name,club_id}],roster[{player_id,name,position,role,squad_id,parent_squad_id,registration_type,loan_end_date,audit_count}]}` |
| `POST /api/v1/clubs/{id}/players` | club_manager (own) / super | `{player_id?,name,position,role}` | `{player}`; writes an audit entry |
| `POST /api/v1/roster/transfer` | club_manager whose club owns `from_squad_id` / super | audit `/roster/transfer` body (`requested_by` = JWT sub, set by the server) | audit transfer response |
| `GET /api/v1/players/{id}/history` | same tenant | `?as_of=` | audit history response |
| `GET /api/v1/store/products` | any (own tenant) | – | `{products:[{product_id,name,category,description,image_url,variants:[{variant_id,size,color,price_minor,stock}]}]}` |
| `POST /api/v1/store/checkout` | any signed-in | `{order_id, items, discount_code, payment{token}}` (the server sets `customer_id` = JWT sub) | audit checkout response |
| `GET /api/v1/orders` | own | – | `{orders:[{order_id,status,total_minor,created_at}]}` |
| `GET /api/v1/orders/{id}/receipt` | own / super | – | `{payload,signature,pdf_base64}` |
| `PATCH /api/v1/orders/{id}/status` | club_manager (own) / super | `{status}` | order state machine + domain event |
| `POST /api/v1/sync` | any signed-in | **exact** audit `/offline-sync` body | audit offline-sync response. Per-action RBAC: score_event needs the organizer of that league; roster_transfer needs the manager of the from-squad's club. Not allowed → that action is `rejected / server_wins / FORBIDDEN` |
| `GET /static/{file}` | none | – | tenant logos and product images, baked into the image (no MinIO dependency) |
| `POST /api/v1/admin/sports`, `/admin/leagues` | super (leagues: super/organizer) | audit bodies | the audit responses (the "admin configuration endpoints" of spec §1) |

## 4. Demo seed data (created by `/reset` and on first boot, see backend `seed/demo.py`)

Never reuse or alter the graded baseline ids. Demo ids must not look like grader ids (avoid `m1`, `lg-1`, `t1`).
- **Branding:** tenant-alpha "Alpha Sports", primary `#0B5FFF`, accent `#FFB800`, logo `/static/tenant-alpha.png`;
  tenant-beta "Beta Athletics", primary `#0E7C3A`, accent `#F2F2F2`, logo `/static/tenant-beta.png`.
- **Clubs (tenant-alpha):** club-alpha-1 "Alpha Lions", club-alpha-2 "Alpha Falcons", plus demo clubs club-alpha-3 and club-alpha-4.
  Each has a venue (name + lat/lng), socials, staff (coach / manager / physio) and 2 seasons of stats. club-beta-1 lives in tenant-beta.
- **league-alpha-1** (football, season 2026, organizer-owned): the 4 alpha clubs (team_id = club_id), double round robin from our own
  generator, match ids `la1-RR-L1-R1-M1`… Seed events so that 4 matches are completed, **1 is in_progress** (pin `prod-jersey-001` on it) and the rest are upcoming,
  with `scheduled_at` relative to the reset date. league-alpha-2 (basketball, not owned by the organizer) has a few fixtures;
  league-beta-1 (tenant-beta) is there to show isolation.
- **Roster league** `league-alpha-1`: squad_id = club_id; window `2026-10-01`..`2026-10-31` (covers judging day); max 25;
  12 players per alpha club with positions (≥ 2 `gk` each, so a gk transfer doesn't trip MIN_POSITION). Includes `player-alpha-1` (club-alpha-1)
  and `player-alpha-2` (club-alpha-2).
- **Store:** `prod-jersey-001` (M stock from reset, L stock from reset), plus `prod-scarf-001` (one size, stock 100), `prod-cap-001` (S/M/L, 50 each),
  `prod-wallpaper-001` (digital, stock 9999), and one scheduled price change on the cap. Judges should buy **L / scarf / cap**; M has stock 1.

## 5. Realtime (WebSocket)

- **Endpoint:** `GET /api/v1/ws?token=<jwt>` (an invalid token closes with 4401). The client sends `{"action":"subscribe","channels":["match:<id>","league:<id>"]}`.
- **Server → client:**
  - `{"type":"match_event","match_id","event":{sequence,event_id,type,payload},"score":<projection home/away/status/outcome/version>}`
  - `{"type":"match_status","match_id","status"}`
  - `{"type":"product_pinned","match_id","product":{…}|null}`
  - `{"type":"standings_changed","league_id"}`
- **Wiring:** after each DB commit, the service publishes JSON on Redis channel `match:{id}` / `league:{id}`.
  `api/ws.py` runs one Redis pub/sub listener and fans out to subscribed sockets. Publishing is fire-and-forget: it never fails the HTTP request.
- **App:** connect when the match screen opens; exponential backoff reconnect (1, 2, 4… max 15 s); after a reconnect, re-fetch `GET /matches/{id}` once.
  WebSocket traffic does not count toward the rate limit.

## 6. Offline sync end-to-end

`mobile outbox (SQLite)` → `POST /api/v1/sync` → `domain/sync.py` (the same code as `/audit/v1/offline-sync`) → results → app clears the outbox.
- Action format: backend plan §10 / app plan §5 (spec §5.14 exactly). `device_id` = a UUID created at first launch and stored in `kv`.
- Versions: `GET /matches/{id}` returns `version`; `GET /clubs/{id}` returns each player's `audit_count`. The app caches both and uses them as `base_version`.
- **Error code → plain message** (`mobile/src/sync/messages.ts`; also used for every online error):

| Code | Message shown to the user |
|---|---|
| VALIDATION_ERROR | "Some details are missing or invalid. Please check the form." |
| UNKNOWN_EVENT_TYPE | "That scoring action isn't part of this sport." |
| INVALID_DISCOUNT_CODE | "That discount code isn't valid." |
| UNAUTHENTICATED / INVALID_CREDENTIALS | "Please sign in again." / "Email or password is incorrect." |
| FORBIDDEN | "Your account isn't allowed to do this." |
| PAYMENT_DECLINED | "Your card was declined. No money was taken." |
| PAYMENT_CAPTURE_FAILED | "The payment couldn't be completed. No money was taken." |
| *_NOT_FOUND | "We couldn't find that match/player/squad/item. It may have been removed." |
| SPORT_EXISTS / LEAGUE_EXISTS / MATCH_EXISTS | "This already exists." |
| DUPLICATE_EVENT_ID / DUPLICATE_ORDER_ID | "This was already sent with different details." |
| ILLEGAL_TRANSITION | "The match can't move to that status from its current state." |
| MATCH_NOT_IN_PROGRESS | "Scores can only be added while the match is live." |
| TIE_NOT_ALLOWED | "This sport can't end in a draw. Record a tie-break winner first." |
| INNINGS_COMPLETE | "This team's innings is over (all overs bowled or all out)." |
| SERIES_ALREADY_DECIDED | "The series is already decided." |
| INVALID_COMPENSATION | "That event can't be reversed (already reversed or not reversible)." |
| OUT_OF_STOCK | "Sorry, that item just sold out." |
| CROSS_TENANT_TRANSFER | "Players can only move between clubs in the same organisation." |
| NOT_IN_SQUAD | "This player is no longer in that squad. Someone else changed it first." |
| TRANSFER_WINDOW_CLOSED | "The transfer window is closed for that date." |
| PLAYER_ON_LOAN | "This player is on loan and can't be moved until the loan ends." |
| SQUAD_FULL | "The destination squad is full." |
| MIN_POSITION_VIOLATION | "This would leave the squad without enough players in that position." |
| INVALID_BASE_VERSION | "Your copy of this data is out of date. Refresh and try again." |
| RATE_LIMITED | "Too many requests. Retrying in a moment…" |
| network / timeout | "Can't reach the server. Your change is saved and will sync when you're back online." |
| anything else | "Something went wrong on our side. Please try again." |

## 7. Networking & devices

- Compose publishes `8080:8080` on all interfaces. Emulator: `http://10.0.2.2:8080`. Phone: `http://<laptop LAN IP>:8080` (`hostname -I`),
  on the same Wi-Fi; open the firewall with `sudo ufw allow 8080/tcp`.
- If the venue Wi-Fi isolates clients, put the laptop on the **phone's hotspot**.
  (`adb reverse tcp:8080 tcp:8080` + `http://localhost:8080` works for development, but **not for the airplane-mode check**: USB keeps the link alive.)
- Cleartext HTTP is enabled in the app via `expo-build-properties`. Test with the **release** APK, not only the dev build.

## 8. Grader replica: `scripts/smoke_test.py` (Python 3.11, `requests` + threads), run after every backend push

Each check prints PASS/FAIL:
1. Poll `GET /health` until 200 (≤ 120 s).
2. `POST /reset` twice → identical responses; the 5 demo logins work.
3. Signature: recompute with `DAY1_SALT` for one `/events` response and one `/checkout` receipt (Appendix A code).
4. Mystery sport (kabaddi example) → league → events → score → standings, including a compensation after `match_end`.
5. Fixtures: RR n=5 with a withdrawal, Swiss rounds 1–3, SE n=6, DE n=8 with bracket_reset + results.
6. **Concurrency:** reset with M stock 1, 20 threads behind a `threading.Barrier` POST checkout with different order_ids →
   exactly one 201, nineteen 409, then inventory `stock 0, reserved 0`; replay the winner → 200 with the same body.
7. RBAC: the full matrix from spec §5.13 (every A/D cell), no token → 401, tampered signature → 401, `alg:none` token → 401.
8. Rate limit: 150 × `GET /api/v1/ping` in < 5 s → ≥ 40 × 429 with `Retry-After`; sleep 11 s → 200.
9. A 2 MB body → 413. `sport_id = "x'; DROP TABLE sports;--"` → 400. A customer_id with `"<script>` → 201, stored verbatim.
10. Roster: setup → last-window-day transfer with a live match → `deferred_until_match_end`; loan → history `as_of` after the end → one `loan_return`, still one after calling again.
11. Offline sync: the spec example → re-send → all `duplicate`.

## 9. Clean-machine reproducibility drill (13:45 and 14:35)

```bash
docker compose down -v --remove-orphans
rm -rf /tmp/clonetest && git clone https://github.com/hamzamalik22/fast-hackathon-app /tmp/clonetest && cd /tmp/clonetest
time DAY1_SALT=drill-salt docker compose up -d --build     # must be < 10 min
python3 scripts/smoke_test.py                              # health ≤ 120 s, then all checks
./run_tests.sh && git diff --stat COVERAGE.json            # declared numbers must match the real ones
```
This catches files that were never committed, `.env` dependencies, and stale-volume luck.

## 10. Docs (write them as you go, finalize by 14:30)

- **README.md:**
  - Prerequisites (Docker only).
  - `DAY1_SALT=<salt> docker compose up -d --build`, then `curl localhost:8080/health`.
  - The **5 demo accounts table**: admin@ / organizer@ / manager@ / player@ / viewer@nascon.test, password `Nascon@26`, with role and scope.
  - Architecture diagram (api, worker, postgres, redis, minio).
  - How to run tests; how to install the APK (`adb install mobile/release/app-release.apk`) and set the server URL.
- **TRACEABILITY.md:** one row per id:

| ID | Source files | Tests |
|---|---|---|
| FR-1.1 | backend/app/domain/scoring.py, seed/sports.json, api/audit.py (sports, events, score) | tests/test_scoring.py, test_canonical.py |
| FR-1.2 | domain/leagues.py, api/mobile.py (admin/leagues) | tests/test_leagues.py |
| FR-1.3 | domain/fixtures/*.py, domain/schedule.py | tests/test_fixtures_*.py, test_schedule.py |
| FR-1.4 | domain/standings.py | tests/test_standings.py |
| FR-2.1 | services/clubs.py, api/mobile.py; mobile/app/club/[id].tsx | tests/test_rbac.py (tenant isolation) |
| FR-2.2 | domain/roster.py, services/roster.py; mobile/app/roster/* | tests/test_roster.py |
| FR-2.3 | domain/store.py, services/checkout.py, worker.py; mobile/app/(tabs)/store.tsx, checkout.tsx, receipt/* | tests/test_store.py, scripts/smoke_test.py #6 |
| FR-5.1 | domain/rbac.py, rbac_policies table, api/audit.py (probes) | tests/test_rbac.py |
| NFR-3 | services/checkout.py (conditional UPDATE + CHECK constraints) | scripts/smoke_test.py #6 |
| NFR-4 | domain/sync.py; mobile/src/db/*, src/sync/* | tests/test_sync.py, desk check |
| NFR-5 | main.py middleware (rate limit, 413), validation.py, rbac.py; mobile SecureStore | tests/test_rbac.py, test_security.py |
| NFR-7 | docker-compose.yml, seed/* | scripts/smoke_test.py #1–2, §9 drill |

- **COVERAGE.json:** produced by `run_tests.sh` (backend plan §11). Commit the regenerated file at the end.

## 11. Master timeline (all owners)

| Time | Backend | Mobile | Integration owner (or whoever is free) |
|---|---|---|---|
| 11:00–11:15 | P0 start | rename `app/`→`mobile/`, scaffold | **make repo public, register URL, first push**, send §1 questions |
| 11:15–11:45 | P0 done: health + reset (**push**) | hello-world release APK | `.gitignore`, `.env.example`, README skeleton |
| 11:45–12:45 | P1 scoring, P2 fixtures (**push**) | client, theme, login, tabs, SyncBar | `/api/v1` auth + leagues/fixtures/standings stubs so mobile can switch off mocks |
| 12:45–13:45 | P3 standings, P4 store, P5 RBAC (**push**) | screens + cache, store flow | `scripts/smoke_test.py`, WS fan-out, demo seed |
| 13:45–14:45 | P6 roster, P7 sync, P9 tests (**push**) | roster/scoring/outbox, HCI pass, **final APK 14:30** | §9 drill at 13:45 and 14:35, TRACEABILITY, COVERAGE |
| 14:45–14:55 | bug fixes only | APK committed | **final push ≤ 14:55**, verify on GitHub that the files are there |

**Priority if time runs out** (by points): any graded `/audit/v1` area > offline sync + desk check > UI polish > `/api/v1` niceties > FR-1.2/1.3 extras.
Never drop: compose reproducibility, the APK file, push windows, COVERAGE.json, README demo accounts.

## 12. Judging slot runbook (from 15:15; one 10-minute slot; judges don't help)

- [ ] 10 min before: `docker compose up -d`, then `curl -X POST localhost:8080/audit/v1/reset` (restores stock and demo state).
- [ ] Phone charged, on the same Wi-Fi as the laptop (or the laptop on the phone hotspot), release APK installed, server URL set and tested, **logged out**.
- [ ] Backup: emulator running with the same APK.
- [ ] Hand the judges a card with the 5 demo accounts.
- [ ] Flow: Task A (standings → match, live score) → Task B (buy L jersey/scarf → receipt PDF) → Task C (manager transfer → airplane mode →
      repeat + organizer score event → force-close/reopen → network on → sync results).
- [ ] Reset between judges if anything was bought or transferred.
