# Plan 1: Backend (`backend/` + root `docker-compose.yml`)

Spec: `docs/NaSCon 26 App Dev Part 1-1.pdf` (text copy: `docs/SPEC.txt`; grep it for exact JSON examples).
Worth **36 pts** (six areas × 6 pts, scored by Python scripts on ≥40 hidden vectors each), plus the script half of
offline sync (4 pts shared with mobile). Each area's score is 90% vector pass rate and 10% unit-test coverage ≥ 85%.
A vector passes only if **every** field, status code, error code and signature matches. **Literal correctness beats features.**

Contract shared with the app (`/api/v1/*`, WebSocket, demo data): see `03-integration-plan.md`.

---

## 0. Non-negotiables (these cost points even if everything else works)

| Rule | Penalty |
|---|---|
| `DAY1_SALT=<salt> docker compose up -d --build` from repo root on clean Ubuntu 22.04 (4 vCPU / 8 GB): build ≤ 10 min, `GET /health` 200 ≤ 120 s after, no manual steps, no internet at runtime | −10 |
| **No branching on a sport id or event name** anywhere in domain code (`if sport == "cricket"`, `"goal"`, `"wicket"`). Branch only on `scoring_model` (`event`/`innings`/`round`). Seed sports live in a JSON data file. | −8 |
| No Firebase/Supabase/Amplify. Mock payment gateway is our own code. | −10 |
| No third-party fixture/pairing/matching libs (no networkx). Write round-robin, Swiss, and both elimination brackets ourselves. | viva + rule |
| `DAY1_SALT` read **only** from env at startup. Never commit it, never `.strip()` it. Compose line must be exactly `DAY1_SALT: ${DAY1_SALT}`. | auto-fail of signatures |

---

## 1. Stack & layout

- **Python 3.12, FastAPI, uvicorn (1 worker), psycopg 3 + psycopg_pool, raw SQL**, PostgreSQL 16, Redis 7 (rate limit,
  pub/sub, Streams queue), MinIO (receipt PDFs), a worker container (Redis Streams consumer). Libraries: `PyJWT`, `bcrypt`, `fpdf2`, `redis`, `minio`.
- Why Python: the grader's reference signer is Python `json.dumps(sort_keys=True, separators=(",",":"), ensure_ascii=False)`,
  so our canonical JSON is byte-identical by construction.
- **Parse request bodies as raw dicts (`await request.json()`), not Pydantic models.** Pydantic coerces `"1"`→`1` and `true`→`1`
  and drops fields, which breaks idempotency comparison, signatures and `details.fields`. Write tiny validators instead.

```
docker-compose.yml               # repo root: postgres, redis, minio, api, worker
.env.example                     # every env var, NO real salt
backend/
  Dockerfile                     # python:3.12-slim, pip install, CMD uvicorn app.main:app --host 0.0.0.0 --port 8080
  requirements.txt
  app/
    main.py                      # app, middleware (body size, rate limit), error handlers, routers, startup (schema+seed)
    config.py  errors.py  validation.py  canonical.py  db.py  schema.sql
    seed/sports.json             # 4 seeded sports as DATA
    seed/baseline.py             # reset(): truncate + graded baseline
    seed/demo.py                 # extra demo data for the app (namespaced ids, see integration plan §4)
    domain/                      # PURE functions, no DB = the 6 coverage areas
      fixtures/{round_robin,swiss,single_elim,double_elim}.py
      scoring.py  standings.py  store.py  roster.py  rbac.py  sync.py  schedule.py
    services/                    # load from DB -> call domain -> persist (locks/transactions live here)
    api/audit.py                 # every /audit/v1/* route
    api/mobile.py                # /api/v1/* (integration plan §3), reuses services
    api/ws.py                    # WebSocket fan-out from Redis pub/sub
    worker.py                    # consumes Redis Stream "domain-events", writes domain_event_log, daily loan-return sweep
tests/                           # REPO ROOT (spec requires it). pytest on app/domain/*
run_tests.sh  COVERAGE.json      # repo root
```

---

## 2. Order of work (start 11:00, lock 15:00)

Each block ends with a commit and push (push windows are in the integration plan §0).

| # | Block | Target time | Notes |
|---|---|---|---|
| P0 | Skeleton: compose, Dockerfile, schema, errors, validators, canonical/sign, `/health`, `/reset` + baseline | 11:00–11:40 | Push the first commit before 11:45 |
| P1 | Sports + events + score projection | 11:40–12:20 | scoring area |
| P2 | Fixtures ×4 (pure functions) | 11:40–12:50 | a second dev can start this at 11:00 with no DB at all |
| P3 | Leagues + standings | 12:20–13:00 | |
| P4 | Checkout + inventory + PDF | 12:50–13:20 | |
| P5 | RBAC matrix + probes + rate limit + 413 + security | 13:00–13:25 | |
| P6 | Roster setup/transfer/history | 13:20–13:50 | |
| P7 | Offline sync | 13:50–14:05 | |
| P8 | `/api/v1` + WebSocket for the app | 13:00–14:15 | the app is blocked on this, so start login/fixtures/standings early |
| P9 | Tests to ≥ 85%/area, COVERAGE.json, TRACEABILITY, README | ongoing, finished by 14:30 | |

Two backend devs: **A** = P0, P1, P3, P7, P8 · **B** = P2 (from 11:00), P4, P5, P6, tests.

---

## 3. P0: Skeleton & global conventions

**docker-compose.yml**
- `postgres:16-alpine` (healthcheck `pg_isready`), `redis:7-alpine` (healthcheck `redis-cli ping`), `minio/minio` (`server /data`),
  `api` (build `./backend`, `ports: ["8080:8080"]`, `environment: DAY1_SALT: ${DAY1_SALT}`, `JWT_SECRET`, DB/Redis/MinIO URLs,
  `depends_on: condition: service_healthy`, `restart: unless-stopped`), `worker` (same image, `command: python -m app.worker`).
- No bind mounts and no pre-created external volumes. Pin image tags. Keep the image slim so the build stays well under 10 minutes.
- Locally, run `docker compose down -v` after schema changes (the schema uses `CREATE TABLE IF NOT EXISTS` and does not migrate an old volume).

**Startup:** retry the DB connection for up to 60 s → run `schema.sql` → if not seeded, run `reset(seed=42)` → create the MinIO bucket
**best-effort** (MinIO problems must never block `/health` or checkout). Precompute the bcrypt hash of `Nascon@26` once at
process start (reset must finish in < 10 s).

**`GET /health`** → `200 {"status":"ok"}` only if `SELECT 1` works and the `meta.seeded` flag is set; otherwise 503.

**Middleware / handlers**
- Body > 1 048 576 bytes (check `Content-Length` **and** the actual bytes read) → `413 PAYLOAD_TOO_LARGE`. Runs before everything else.
- Error body for every non-2xx: `{"error":{"code","message","details":{}}}`. `details` is always an object.
  `VALIDATION_ERROR` → `details.fields` = offending field names (top-level name, plus a dotted path for nested fields, e.g. `["periods","periods.count"]`).
- Malformed JSON, or a body that is not an object → 400 `VALIDATION_ERROR`. Override FastAPI's 422 → 400. Unknown route → 404 `NOT_FOUND`.
  Catch-all → 500 `INTERNAL_ERROR` with a generic message and no stack trace (but we must never reach it on bad input).
- **Validation order everywhere: 400 schema → 404 missing referenced id → 409 business rule (402 payment). The first failure wins.**
- Validators: `req_id` (regex `^[A-Za-z0-9_.:-]{1,64}$`), `req_int` (**reject bool and float**), `req_str`, `req_enum`, `req_bool`,
  `req_date` (strict `YYYY-MM-DD`, must be a real date), `opt_*`. Unknown fields are ignored.
- Timestamps: `datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")`. Money is int minor units, currency `"PKR"`.

**`canonical.py`** (copy Appendix A literally)
```python
def canonical(o): return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
def sign(id_, payload): return hmac.new(SALT.encode(), (id_ + "|" + canonical(payload)).encode(), hashlib.sha256).hexdigest()
def lots_key(seed, league_id, team_id): return hashlib.sha256(f"{seed}|{league_id}|{team_id}".encode()).hexdigest()
```
Unit tests: vector 1 (salt `demo-salt`, `evt-1`, `{"team_id":"t1","event_type":"goal"}` → `972a8b55…c501`) and vector 2 (lots keys for t1/t2/t3).
**Compute the signature at write time from the parsed request payload and store it.** Never recompute it from JSONB.

**Schema (`schema.sql`), all wiped by reset (`TRUNCATE … RESTART IDENTITY CASCADE` in one transaction)**
```
meta(key PK, value)                          -- seeded flag, last_seed
counters(name PK, value)                     -- audit ids au-0001.., auth_N, cap_N
tenants(tenant_id PK, name, logo_url, primary_color, accent_color)
users(user_id PK, email UNIQUE, password_hash, role, tenant_id, name, league_ids JSONB, club_id, player_id)
rbac_policies(action, role, scope)           -- the policy matrix as DATA (FR-5.1)
sports(sport_id PK, name, config JSONB)
leagues(league_id PK, tenant_id NULL, sport_id, name, season, format, config JSONB)  -- teams, points, tie_break_order, spots, lots_seed
matches(match_id PK, league_id NULL, sport_id, home_team_id, away_team_id, created_by_init BOOL,
        scheduled_at NULL, venue_id NULL, round NULL, admin_status NULL, pinned_product_id NULL)
match_events(event_id PK, match_id, sequence, type, payload JSONB, signature, compensates NULL,
             request_canonical TEXT, response JSONB, created_at, UNIQUE(match_id, sequence))   -- append-only
clubs(club_id PK, tenant_id, name, venue_name, lat, lng, socials JSONB, staff JSONB, stats JSONB)
venues(venue_id PK, tenant_id, name, open_hour, close_hour)
roster_leagues(league_id PK, tenant_id, sport_id, window_open, window_close, max_squad_size, required_positions JSONB)
squads(squad_id PK, league_id, club_id, tenant_id, name)
roster_players(player_id PK, league_id, name, position, squad_id NULL, role, parent_squad_id NULL,
               registration_type, start_date, loan_end_date NULL)
roster_live_matches(league_id, match_id, home_squad_id, away_squad_id)
roster_audit(seq BIGSERIAL, audit_id UNIQUE, player_id, league_id, action, from_squad_id, to_squad_id,
             effective_date, state, who, when_ts, why, blocking_match_id)                     -- append-only
roster_requests(request_id PK, request_canonical, response JSONB)
products(product_id PK, tenant_id, club_id, name, category, description, image_url)
variants(variant_id PK, product_id, size, color, price_minor, stock INT CHECK (stock >= 0), reserved INT CHECK (reserved >= 0))
price_schedules(variant_id, price_minor, effective_from)
discount_codes(code PK, percent)
orders(order_id PK, customer_id, status, request_canonical, response JSONB, total_minor, created_at)
order_events(order_id, from_status, to_status, at)
sync_actions(device_id, action_id, result JSONB, PRIMARY KEY (device_id, action_id))
domain_event_log(id BIGSERIAL, type, payload JSONB, at)
```

**`POST /audit/v1/reset`** body optional `{seed?: int (default 42), stock?: {variant_id: int ≥ 0}}` → 200
`{"status":"reset_complete","seed":42,"sports":["football","basketball","cricket","esports"],"tenants":["tenant-alpha","tenant-beta"],"stock":{"var-jersey-001-M":1,"var-jersey-001-L":5}}`.
The returned `stock` is the defaults merged with the request. Ignore unknown variant keys; a negative or non-int value → 400.
The result must be identical every time, and counters restart.

**Baseline (exact ids):**
- Tenants: `tenant-alpha` "Alpha Sports" and `tenant-beta` "Beta Athletics" (plus branding: logo, colors).
- Product `prod-jersey-001` (tenant-alpha), variants `var-jersey-001-M` and `var-jersey-001-L`, `price_minor` 450000, PKR. Discount `WELCOME10` = 10%.
- Leagues `league-alpha-1` and `league-alpha-2` (tenant-alpha), `league-beta-1` (tenant-beta). Clubs `club-alpha-1`, `club-alpha-2`, `club-beta-1`.
  Players `player-alpha-1` (club-alpha-1), `player-alpha-2` (club-alpha-2), `player-beta-1` (club-beta-1).
- The five demo users from spec §8.3 (password `Nascon@26`): admin → super_admin, organizer → owns league-alpha-1,
  manager → owns club-alpha-1, player → player-alpha-1, viewer → tenant-alpha read-only.
- The four sports (below), then `seed/demo.py` (app demo data, integration plan §4).

**Seeded sports (`seed/sports.json`):** event keys are snake_case versions of the spec's names. Double-check these with the organizers (integration plan §1).

| sport_id | model | periods | scoring_events | draw | overtime | roster |
|---|---|---|---|---|---|---|
| football | event | `{count:2,duration_minutes:45}` | `goal:{points:1}` | true | `{policy:"none"}` | min 11, max 25, `{gk:1}` |
| basketball | event | `{count:4,duration_minutes:12}` | `free_throw:1, two_pointer:2, three_pointer:3` | false | `{policy:"extra_time",duration_minutes:5}` | 5–15, `{}` |
| cricket | innings | `{innings_per_team:1,overs_per_innings:20,balls_per_over:6,wickets_per_innings:10}` | `dot_ball{0,legal,¬w}, single{1}, two{2}, four{4}, six{6}, wide{1,¬legal}, no_ball{1,¬legal}, wicket{0,legal,wicket}` | true | `{policy:"super_over"}` | 11–18, `{wicketkeeper:1}` |
| esports | round | `{best_of:3}` | `round_win:{rounds:1}` | false | `{policy:"none"}` | 5–8, `{}` |

Every seeded sport also gets the default `tie_break_order` (the full list).

---

## 4. P1: Scoring engine (FR-1.1)

### `POST /audit/v1/sports`
Validate exactly per spec §5.6:
- `sport_id`: regex `^[a-z0-9_-]{2,40}$`, so the SQL-injection probe → 400.
- `name`: 1–80 chars. `scoring_model` ∈ event / innings / round.
- `periods` per model: event `count ≥ 1`, `duration_minutes ≥ 1`; innings: four ints ≥ 1; round: `best_of` odd ≥ 1.
- `scoring_events`: ≥ 1 key, key regex `^[a-z0-9_]{1,40}$`. Value per model: event `{points ≥ 1}`; innings `{runs ≥ 0, legal_ball: bool, wicket: bool}`; round `{rounds ≥ 1}`.
- `draw_allowed`: bool. `overtime.policy` ∈ none / extra_time / shootout / golden_score / super_over, optional `duration_minutes ≥ 0`.
- `tie_break_order`: optional; tokens from the 6, no repeats; default = the full list.
- `roster`: `min ≤ max`, ints ≥ 1, `required_positions` = map → int.

Response 201 `{"sport_id","status":"created","config":{…normalized stored config…}}`. Errors: 400 `VALIDATION_ERROR` (with fields), 409 `SPORT_EXISTS`.
The new sport must work immediately in `/events`, `/leagues`, `/standings` and `/fixtures`, so load the config from the DB on every use (no cache).

### `POST /audit/v1/events`, in this order
1. Envelope: `event_id` (id), `match_id` (id), `type` ∈ {match_init, match_start, score, discipline, tiebreak_winner, match_end, compensation},
   `payload` object → else 400. Then the per-type payload shape (400):
   - match_init: `sport_id`, `home_team_id`, `away_team_id` (ids, home ≠ away), optional `league_id`
   - score: `team_id`, `event_type`
   - discipline: `team_id`, `points` int
   - tiebreak_winner: `team_id`
   - compensation: `compensates` (id), `reason` (string)
   - match_start / match_end: `{}`
2. Take `pg_advisory_xact_lock(hashtextextended(match_id,0))` (serializes appends per match).
3. **Idempotency:** if `event_id` exists and the canonical form of `{event_id,match_id,type,payload}` equals the stored one → **200 + stored response**.
   Same id with a different body → 409 `DUPLICATE_EVENT_ID`. Event ids are globally unique.
4. match_init: unknown sport → 404 `SPORT_NOT_FOUND`; stream exists (league fixture or earlier init) → 409 `MATCH_EXISTS`.
   Any other type: no stream → 404 `MATCH_NOT_FOUND`.
5. Load the sport config and all events, then `project()` (below). Rules:
   - **score**: `team_id` not home/away → 400 `VALIDATION_ERROR`; `event_type` not in `scoring_events` → 400 `UNKNOWN_EVENT_TYPE`;
     status ≠ in_progress → 409 `MATCH_NOT_IN_PROGRESS`.
     Limits (active events only): innings: that team's legal balls ≥ ipt×opi×bpo, or wickets ≥ ipt×wpi → 409 `INNINGS_COMPLETE`.
     Round: either team has ≥ (best_of+1)/2 rounds → 409 `SERIES_ALREADY_DECIDED`.
   - **discipline / tiebreak_winner**: team check (400), then status must be in_progress (409 `MATCH_NOT_IN_PROGRESS`).
   - **match_start**: status must be upcoming, else 409 `ILLEGAL_TRANSITION`.
   - **match_end**: must be in_progress, else 409 `ILLEGAL_TRANSITION`. Level score, `draw_allowed=false` and no active tiebreak winner → 409 `TIE_NOT_ALLOWED`.
   - **compensation** (allowed in any status, including completed): target id doesn't exist anywhere → 404 `EVENT_NOT_FOUND`;
     target is in another match, is not score/discipline/tiebreak_winner, or is already compensated → 409 `INVALID_COMPENSATION`.
6. Append: `sequence = count + 1`, `signature = sign(event_id, payload)`. Store the payload, request_canonical and the response.
   Respond **201** `{"event_id","match_id","type","sequence","match_version": sequence,"signature"}`.
   After commit, publish to Redis `match:{id}` (best-effort).

### `project(sport, match, events)`: pure, rebuilt on every read (no counters as source of truth)
- **Neutral events:** compensated targets and the compensation events themselves.
- `status`: completed if a match_end exists; in_progress if a match_start exists; otherwise upcoming.
- **Per team:**
  - score: event model = Σ points; innings = Σ runs; round = Σ rounds
  - innings only: `wickets`, `balls` (legal only), `overs = f"{balls//bpo}.{balls%bpo}"`. Other models: all three are `null`.
  - `fair_play` = Σ active discipline points
- `tiebreak_winner_team_id`: the last active tiebreak_winner, or null.
- `winner_team_id`: the higher score; if level, the tiebreak winner; else null.
- `outcome`: `pending` until completed. Then `home_win`/`away_win` by score or tiebreak winner; level with no tiebreak →
  `draw` if `draw_allowed`, else `undecided` (e.g. after the tiebreak event was compensated).
- `GET /audit/v1/score/{match_id}` → 404 `MATCH_NOT_FOUND`, else `{match_id, sport_id, league_id, status, outcome, winner_team_id,
  tiebreak_winner_team_id, home{team_id,score,wickets,balls,overs,fair_play}, away{…}, version, events[{sequence,event_id,type,payload,signature,compensated,compensated_by}]}`
  (`version` = number of events; events include compensations).

---

## 5. P2: Fixtures (FR-1.3): `POST /audit/v1/fixtures`, pure, stores nothing
Team limits: RR 2–40, Swiss 2–64, SE 2–128, DE 3–128; teams must be unique valid ids, else 400. Array order is the seed order (index 0 = seed 1).

### A. Round robin (circle method, verified for n = 2..40 with a script)
```python
arr = teams + ([None] if n % 2 else [])          # None = bye, appended LAST
N = len(arr)
for r in range(N - 1):
    for i in range(N // 2):
        a, b = arr[i], arr[N - 1 - i]
        if i == 0: home, away = (a, b) if r % 2 == 0 else (b, a)   # fixed team alternates by round
        else:      home, away = a, b                               # other pairs: upper half is home
        # a pair containing None means the other team has a bye
    arr = [arr[0], arr[-1]] + arr[1:-1]                            # rotate
```
- This gives |home − away| ≤ 1 for even n and exact home/away equality for odd n, one bye per team per leg, and every pair exactly once.
  It reproduces the spec example (n=5, R1: t1 bye, t2–t5, t3–t4).
- Leg 2 is leg 1 with home/away swapped. Round numbers are **global** (leg 2 continues). `match_id = RR-L{leg}-R{round}-M{idx}` (idx from 1 per round).
  `byes` is `[]` for even n, exactly one team for odd n.
- Withdrawals `{team_id, after_round}` (after_round = the last global round the team still plays; 0 = never).
  - `forfeit_remaining` (default): fixtures with round > after_round → `status:"forfeit"`, `awarded_to` = the opponent.
  - `void_all`: every fixture of that team → `"voided"`, `awarded_to: null`.
  - A fixture where both teams have withdrawn (both past their after_round under forfeit) → voided. Never remove fixtures; byes are unaffected.
- 400 if: unknown withdrawal team; after_round outside `0..round_count`; legs ∉ {1,2}; bad policy.
- Response `{format,legs,team_count,round_count,rounds[{round,matches[{match_id,leg,home,away,status,awarded_to}],byes}],summary{total,scheduled,forfeit,voided}}`.

### B. Swiss (one round per call)
- Params: `total_rounds` 1..n−1 (default ⌈log2 n⌉); `round` 1..total_rounds (default 1). `history` must contain exactly rounds 1..round−1, else 400.
  Results are home / away / draw; `bye` is a team id or null; unknown teams → 400.
- **Scores**: win 1, draw 0.5, loss 0, bye 1. **Buchholz** = Σ the current scores of opponents actually played (a bye adds 0).
  `standings` (from history only): sort by score desc, buchholz desc, seed asc; `rank` 1..n. Floats are compared exactly.
- **Round 1 (exact):** m = ⌊n/2⌋. For odd n the last seed gets the bye. Pair seed i with seed i+m (lower seed is home).
- **Rounds ≥ 2:**
  - Odd n: bye candidates = teams without a previous bye, sorted by (score asc, index **desc**). Try each in turn.
  - For the remaining teams, find a **minimum Σ|score diff| perfect matching with no rematches**:
    - memoized DFS over a bitmask of remaining teams; always pair the lowest-index remaining team first;
    - try partners ordered by |diff|;
    - lower bound = Σ adjacent diffs of the remaining scores sorted (the exact unconstrained optimum); stop early when the bound is reached;
    - prune when cost + bound ≥ best.
  - **Greedy pairing fails the hidden vectors.**
  - No pairing for any candidate → 409 `NO_VALID_PAIRING`, `details: {"round": r}`.
  - `match_id = SW-R{round}-M{i}`; the better-ranked team is home (home/away is not checked).
- Response `{format,round,total_rounds,pairings[{match_id,home,away}],bye,standings[{rank,team_id,score,buchholz}]}`.

### C. Single elimination (exact)
- B = the next power of two ≥ n. `order(2)=[1,2]`; `order(2k) = [x for s in order(k) for x in (s, 2k+1-s)]` (order(8) = 1,8,4,5,2,7,3,6).
  R1 match i takes entries 2i−1 and 2i, with the lower seed home.
  Seed > n → `bye:true, away:null, away_seed:null`, winner = the present team, **propagated immediately**.
- `match_id = R{r}M{i}`; rounds = log2 B. Winner of R{r}M{i} → R{r+1}M{⌈i/2⌉}, slot `home` if i is odd, `away` if even.
  The final has `winner_to: null`; `loser_to: null` except with a third-place match.
- MATCH = `{match_id, bracket:"main", round, index, home, away, home_seed, away_seed, bye, winner, loser, winner_to:{match_id,slot}|null, loser_to}`.
  `home`/`away` are null while unknown; seeds follow the team occupying the slot.
- `third_place_match:true` adds `TP` (`bracket:"third_place"`), with both semifinals' `loser_to` → TP home/away.
  Put TP inside the **final round's** `matches` list so the rounds count stays log2 B.
- `results`: apply in round order and propagate. Unknown match_id, or a winner who isn't a participant → 400.

### D. Double elimination (counts are exact; routing is checked as a graph)
- WR = the single-elim bracket with ids `WR{r}M{i}`, `bracket:"winners"`, k = log2 B.
- LR rounds 1..2(k−1); rounds 2j−1 and 2j each have B/2^(j+1) matches; total = B−2. `GF1`, plus `GF2` only if `bracket_reset`.
- **Routing:**
  - Every WR match has `loser_to`. WR1 M(2i−1)/M(2i) losers → LR1 Mi home/away. WR r ≥ 2 losers → LR(2r−2) Mi slot away.
  - LR(2j−1) Mi winner → LR(2j) Mi home. LR(2j) Mi winner → LR(2j+1) M⌈i/2⌉ (home if i is odd).
  - WR final winner → GF1.home; WR final loser → LB final away; LB final winner → GF1.away. LR matches have `loser_to: null`.
  - With a reset: `GF1.winner_to = {GF2,home}`, `GF1.loser_to = {GF2,away}`, so every slot except WR1's has exactly one source.
- **GF2**: `conditional:true`. Before GF1 has a result, GF2's home/away mirror GF1's teams; after it, they are filled by propagation.
  `required` = null until GF1 has a result, then `true` iff `bracket_reset` and the GF1 winner is GF1.away (the LB champion), else `false`.
  Every other match: `conditional:false, required:true`.
- A slot whose source was a WR1 bye is "dead"; an LR match with one dead slot auto-advances the other team (not graded, keeps the bracket sane).
- `results`: iterate until nothing changes. Unknown match, or a winner who isn't a participant → 400.
- Response `{format,bracket_size,bracket_reset,winners[{round,matches}],losers[…],grand_final[GF1,GF2?]}`.

---

## 6. P3: Leagues & standings (FR-1.2, FR-1.4)

### `POST /audit/v1/leagues`
- 400 if: missing league_id / sport_id / teams / fixtures; teams not unique or outside 2–40; a fixture team not in teams; home = away;
  duplicate match_id inside the request; `points` not ints; bad tie-break tokens; `qualification.spots` outside 1..n.
- Then 404 `SPORT_NOT_FOUND` → 409 `LEAGUE_EXISTS` → 409 `MATCH_EXISTS`.
- Defaults: points 3/1/0; `tie_break_order` = the sport's; `lots_seed` = the last reset seed.
- Every fixture becomes a `matches` row with status upcoming and no events.
- 201 `{"league_id","status":"created","team_count","fixture_count"}`.

### `GET /audit/v1/standings/{league_id}` (404 `LEAGUE_NOT_FOUND`): recompute from the event logs on every call
- **Played** = status completed and outcome ≠ undecided. Everything else is remaining.
- **Table stats:**
  - W/D/L from the outcome (a win by tiebreak counts as a win)
  - scored/conceded = Σ score
  - `points = won×W + drawn×D + lost×L`
  - `fair_play` = Σ active discipline points over played matches
- **diff:**
  - event and round models: scored − conceded (int)
  - innings: **NRR** = runs_for/overs_faced − runs_against/overs_bowled, rounded to 3 dp.
    overs = legal balls / bpo (decimal); an all-out innings (wickets ≥ ipt×wpi) counts as the full ipt×opi overs; overs bowled = the opponent's overs faced.
    Guard against /0 (that term = 0).
- **h2h[a][b]** for every ordered pair (zeros if they never met): `{played, points (earned by a), scored, conceded}`.
- **Ordering (exact):**
  1. Sort by points; equal points form groups.
  2. `resolve(group)`: for each criterion in `tie_break_order` + `draw_lots` (always last, appended if missing), compute the values.
     If they are not all equal, split into sub-groups (best first) and **resolve every sub-group of size > 1 again from the first criterion**; stop.
  3. `h2h_points` / `h2h_diff` use only the matches among the **current group** (the 3-way mini-league; for innings, NRR over those matches).
     `overall_diff`, `scored` and `fair_play` use all played matches. Higher is better for all.
  4. `draw_lots`: ascending `lots_key(lots_seed, league_id, team_id)`; first = best.
- **resolved_by**: for each team, the criterion that separated it from the **next** team when that team has equal points; else null
  (the last team of a tied group gets null). Implement `resolve` returning `(order, separators[])`.
- **Qualification (exact, points only):**
  - W = win points; R(T) = remaining fixtures of T; max(T) = points(T) + W×R(T); k = spots.
  - `clinched` if fewer than k other teams have max(X) ≥ points(T).
  - `eliminated` if ≥ k other teams have points(X) > max(T).
  - else `still_possible`. Check clinched first.
- Response `{league_id,sport_id,qualification_spots,table[{rank,team_id,played,won,drawn,lost,scored,conceded,diff,points,fair_play,status,resolved_by}],h2h}`.
- **Edge case 5:** a compensation on a completed match changes everything on the next call. That works for free because nothing is cached.

**FR-1.2 (viva/traceability, thin):** `leagues.format` ∈ league / knockout / hybrid; `config.divisions[{id, promote, relegate}]`; hybrid =
group stages (round robin) → seed a single-elim bracket from the group standings. Admin route `POST /api/v1/admin/leagues` (super/organizer).

**FR-1.3 extras (viva, thin), `domain/schedule.py`:**
- Match state machine:
  - upcoming → in_progress | postponed | cancelled
  - in_progress → completed | abandoned | postponed
  - postponed → upcoming | cancelled
  - completed, abandoned and cancelled are terminal
  - illegal transition → 409 `ILLEGAL_TRANSITION`
- `detect_conflicts(slot)`: venue double-booking, team overlap, player overlap across squads, minimum rest hours, venue availability window.
  Returns `[{type, entity_ids}]` → 409 `SCHEDULE_CONFLICT` with `details.conflicts`.
- Postponing re-runs conflict detection and clears downstream bracket slots. Every status change is broadcast over WebSocket.

---

## 7. P4: Store (FR-2.3, NFR-3)

### `POST /audit/v1/checkout`
1. **400 checks:** `order_id` (id); `customer_id` (any string 1–200, **stored verbatim**, so quotes and `<script>` → still 201);
   items 1–10, `quantity` an int 1..10 (not bool), unique variant_ids; `discount_code` null or string; `payment.token` string.
2. **Idempotency:** a stored successful order with the same id and an identical canonical body → **200 + stored response** (same paid_at, signature, PDF).
   Different body → 409 `DUPLICATE_ORDER_ID`. Insert a placeholder row with `ON CONFLICT DO NOTHING` to guard concurrent duplicates.
3. Unknown variant → 404 `VARIANT_NOT_FOUND`. Then the discount code: only `WELCOME10`, else 400 `INVALID_DISCOUNT_CODE`.
4. **Reserve atomically (transaction 1):** for each item, in sorted variant_id order:
   `UPDATE variants SET stock=stock-$q, reserved=reserved+$q WHERE variant_id=$v AND stock>=$q RETURNING stock`.
   If any update returns no row → ROLLBACK (nothing reserved) → 409 `OUT_OF_STOCK`, `details.variant_id`. Commit the reservation.
5. **Mock gateway** (our code):
   - `tok_success` → `auth_N` + `cap_N`
   - `tok_declined` → release (`stock+=q, reserved-=q`) → 402 `PAYMENT_DECLINED`
   - `tok_capture_fail` → void the auth, release → 402 `PAYMENT_CAPTURE_FAILED`
   - any other token → treat as declined
6. **Success (transaction 2):** `reserved -= q`; order status `paid`; write order_events; XADD a domain event to the Redis Stream `domain-events`.
   - `subtotal = Σ unit_price × qty` (unit price = the latest `price_schedules` row ≤ now, else the base price)
   - `discount = floor(subtotal × 10 / 100)`; `total = subtotal − discount`
7. **Receipt:**
   - `payload = {order_id, customer_id, items[{variant_id,quantity,unit_price_minor}], subtotal_minor, discount_minor, total_minor, currency:"PKR", paid_at}`
   - `signature = sign(order_id, payload)`
   - PDF via **fpdf2**. Its text must contain the order_id and `f"PKR {total//100}.{total%100:02d}"` (e.g. `PKR 4500.00`).
     Sanitize the non-ASCII customer_id to latin-1 for the PDF only, or use a bundled DejaVu TTF (fpdf2 core fonts crash on unicode).
   - Return `pdf_base64`; upload a copy to MinIO best-effort.
8. Failed checkouts are not stored for idempotency (delete the placeholder); log a payment attempt.

Response 201: `{order_id,status:"paid",currency,items,subtotal_minor,discount_minor,total_minor,payment{authorization_id,capture_id,state:"captured"},receipt{payload,signature,pdf_base64}}`.

- **`GET /audit/v1/inventory/{variant_id}`** → `{variant_id, stock, reserved}`; 404 `VARIANT_NOT_FOUND`. After the 20-thread burst: one 201, nineteen 409, stock 0, reserved 0.
- Order state machine (production): pending → paid → packed → shipped → delivered; pending/paid → cancelled; paid/packed/shipped/delivered → refunded
  (the mock gateway refunds, stock is restored). Every transition → `order_events` + a Redis Stream event.
- Pinning a product on a match: `POST /api/v1/matches/{id}/pin` → broadcast `product_pinned`.

---

## 8. P5: RBAC & security (FR-5.1, NFR-5)

- **`POST /audit/v1/rbac-matrix`** (no auth): issue HS256 JWTs for the 5 seeded users (exp ≥ 12 h).
  Claims: `sub, role, tenant_id, league_ids, club_id, player_id, exp, iat`.
  Return `{tokens{super_admin,league_organizer,club_manager,player,viewer}, context{…exact ids from spec §5.13…}}`.
- **Verification:** `jwt.decode(t, SECRET, algorithms=["HS256"], options={"require":["exp"]})`.
  Missing, malformed, `alg:none`, tampered or expired → 401 `UNAUTHENTICATED`. Authentication runs first, then target lookup (404 only if the id doesn't exist at all), then the policy check.
- **Policy matrix as data** (`rbac_policies`, seeded on reset; `domain/rbac.py: decide(user, action, target) -> bool`):

| action (probe) | super | organizer | club_manager | player | viewer |
|---|---|---|---|---|---|
| tenants.create (P1 `POST /audit/v1/rbac/tenants`) | any | none | none | none | none |
| league.fixtures.write (P2 `POST …/leagues/{id}/fixtures`) | any | own_league | none | none | none |
| club.roster.write (P3 `POST …/clubs/{id}/roster`) | any | none | own_club | none | none |
| club.products.write (P4 `POST …/clubs/{id}/products`) | any | none | own_club | none | none |
| player.update (P5 `PATCH …/players/{id}`) | any | none | own_club_player | self | none |
| club.read (P6 `GET …/clubs/{id}`) | any | same_tenant | same_tenant | same_tenant | same_tenant |
| platform.config (P7 `GET …/platform/config`) | any | none | none | none | none |

  Allowed → `200 {"authorized":true}`; denied → **403 `FORBIDDEN`**. Cross-tenant is always 403, never 404. The probes don't read the body.
- **Rate limit `/api/v1/*` only:** 100 requests per rolling 10 s per client IP. Use a Redis ZSET sliding window in a Lua script / MULTI; count only allowed requests.
  Over the limit → 429 `RATE_LIMITED` + `Retry-After: ceil(oldest+10−now)` (≥ 1). `GET /api/v1/ping` → `{"pong":true}` (no auth).
  `/audit/v1/*` and `/health` are **exempt** (the grader sends 200 req/s).
- **OWASP API Top 10:**
  - parameterized SQL only
  - strict validators and the 1 MB body cap
  - bcrypt password hashes
  - JWT expiry and signature checks
  - object-level authorization on every `/api/v1` route (tenant filter from the JWT)
  - no stack traces in responses
  - CORS restricted
  - security headers (`X-Content-Type-Options`, etc.)
  - login rate-limited by the same middleware

---

## 9. P6: Roster (FR-2.2)

### `POST /audit/v1/roster/setup`
- Replaces that league's whole roster state: delete its squads, players, live matches, audit entries and request ids, then insert.
- Missing `max_squad_size` / `required_positions` → defaults from the sport's roster config (404 `SPORT_NOT_FOUND` if the sport doesn't exist).
- Roles: captain / vice_captain / starter / substitute.
- 201 `{"league_id","status":"configured","squad_counts":{sq:n,…}}` (every squad listed, zeros included).

### `POST /audit/v1/roster/transfer`
Take a league advisory lock. Materialize loan returns for this player as of `effective_date` first. Then the checks, **in this exact order**:

| # | Check | Error |
|---|---|---|
| 1 | schema (request_id, league_id, player_id, type ∈ transfer/loan/release, from_squad_id, to_squad_id unless release, valid dates, loan_end_date required and > effective_date for loan) | 400 `VALIDATION_ERROR` |
| 2 | league → player → from squad → to squad exist | 404 `LEAGUE_NOT_FOUND` / `PLAYER_NOT_FOUND` / `SQUAD_NOT_FOUND` |
| 3 | from (and to) squad tenant = the league's tenant | 409 `CROSS_TENANT_TRANSFER` |
| 4 | the player's current squad in this league = from_squad_id | 409 `NOT_IN_SQUAD` |
| 5 | transfer/loan: window.open ≤ effective_date ≤ window.close (release: any date) | 409 `TRANSFER_WINDOW_CLOSED` |
| 6 | the player is not currently on loan (applies to every type) | 409 `PLAYER_ON_LOAN` |
| 7 | transfer/loan: destination count + 1 ≤ max_squad_size | 409 `SQUAD_FULL` |
| 8 | after the move, the from squad keeps ≥ required_positions[player.position] | 409 `MIN_POSITION_VIOLATION` |

- Idempotency: the same request_id with an identical body → **200 + the same body**. Rejected requests write **nothing**.
- **Effects:**
  - transfer → squad = to, role `substitute`, registration_type `transfer` (a captain/vice-captain slot left behind is vacated)
  - loan → squad = borrower, `parent_squad_id` = lender, `loan_end_date` set; the player counts toward the borrower only
  - release → squad null, registration null
- **Edge case 6:** if the player's squad (old) is home/away in any `matches_in_progress` entry → still accepted, with
  `state:"deferred_until_match_end"` and `blocking_match_id`. Otherwise `state:"active"`, `blocking_match_id:null`.
- Audit entry: `audit_id` = `au-%04d` (global counter), action, player_id, league_id, from/to, effective_date, state,
  `who` = requested_by, `when` = server time, `why` = reason.
- 201 `{request_id,status:"accepted",state,blocking_match_id,registration{player_id,league_id,squad_id,parent_squad_id,registration_type,start_date,loan_end_date,role}|null,audit_entry{…}}`.

### `GET /audit/v1/roster/history/{player_id}?as_of=YYYY-MM-DD`
Default `as_of` = today; unknown player → 404 `PLAYER_NOT_FOUND`.
- First, for every active loan with `loan_end_date < as_of`, append **once** a `loan_return` entry:
  `who:"system"`, effective_date = loan_end+1, player back to the lender, role substitute, parent null.
  Guard against duplicates with a unique (player, action, effective_date) row or by checking for an existing entry.
- `current_squad_id` = the squad on the `as_of` date (null if released). Response `{player_id,as_of,league_id,current_squad_id,parent_squad_id,history[oldest first]}`.
- The worker also runs the loan-return sweep daily (for "today").

---

## 10. P7: Offline sync (NFR-4): `POST /audit/v1/offline-sync`

- **Envelope 400:** device_id (id); actions 1–100; each has action_id, type ∈ {score_event, roster_transfer}, queued_at (ISO Z),
  base_version (int ≥ 0), payload (object). Payload contents are judged **per action**, not as an envelope error.
- **Processing:** stable-sort by `queued_at` (ties keep array order), then process sequentially against the live state using the **same service functions** as `/events` and `/roster/transfer`.
- **Per action:**
  1. `(device_id, action_id)` seen before, or the same event_id/request_id already exists with an identical body → `duplicate / skipped_duplicate / null`.
  2. Referenced match/player/squad unknown → `rejected / server_wins / *_NOT_FOUND`.
  3. Current version (score: the match's event count; roster: the player's audit-entry count); base_version > current → `rejected / server_wins / INVALID_BASE_VERSION`.
  4. The service rejects → `rejected / server_wins / <that code>` (e.g. `MATCH_NOT_IN_PROGRESS`, `DUPLICATE_EVENT_ID`, `SQUAD_FULL`).
  5. Applied → `applied / appended` if base == current, else `applied / rebased_append`.
- **Result fields:** `processed_order` (1-based, in processing order); `server_version` after processing (unchanged for rejected/duplicate);
  `signature` = the event signature for an applied score_event, else null. Store results in `sync_actions`.
  Results come back in **request order**. `summary{applied,rejected,duplicate}`. Always HTTP 200.
- Re-sending the same request → every action duplicate, nothing changes.

---

## 11. P9: Tests, coverage, docs (in the root `tests/`)

- Pure domain functions keep tests fast and DB-free. A `conftest.py` puts `backend/` on `sys.path` and sets `DAY1_SALT=test-salt`.
- **Must-have tests** (they are also the TRACEABILITY evidence):
  - `test_canonical.py`: both Appendix A vectors.
  - `test_fixtures_rr.py`: n = 2..40 × legs 1/2. Property asserts: rounds count, byes, pair counts, balance, both withdrawal policies, 400s.
  - `test_fixtures_swiss.py`: exact round 1, odd/even, a case where greedy pairing gets stuck, the bye rule, buchholz, NO_VALID_PAIRING, history 400.
  - `test_fixtures_se.py` / `test_fixtures_de.py`: n = 2..33 and 128. Assert match counts, ids, the routing graph (each non-WR1 slot fed exactly once), bye propagation, results 400, GF2 required.
  - `test_scoring.py`: all three models, a mystery sport with arbitrary event names, compensation (including after completion → undecided), every 4xx code, limits, idempotency.
  - `test_standings.py`: a 3-way tie with h2h mini-league and restart-on-split, NRR, draw_lots with vector 2, clinched/eliminated, resolved_by.
  - `test_store.py`: totals, discount floor, receipt signature, PDF starts with `%PDF` and contains `PKR 4500.00`, gateway tokens, order state machine.
  - `test_roster.py`: each of the 8 checks in order, loan → return written once, deferred state, idempotency.
  - `test_rbac.py`: **parametrize the full matrix (5 roles × every probe/target), including the negative cases**, plus 401 tampered / alg none / expired.
  - `test_sync.py`: every resolution row, ordering, re-send → all duplicate.
- **`run_tests.sh`** (root, Docker-based so judges need nothing else):
  `docker run --rm -v "$PWD":/w -w /w python:3.12-slim sh -c "pip install -q -r backend/requirements.txt -r tests/requirements.txt && DAY1_SALT=test-salt pytest tests -q --cov=backend/app/domain --cov-report=json:coverage.json && python tests/coverage_areas.py coverage.json > COVERAGE.json"`
- **`tests/coverage_areas.py`** maps each area to files: fixtures → `domain/fixtures/*`, scoring → `domain/scoring.py`, standings → `domain/standings.py`,
  store → `domain/store.py`, roster → `domain/roster.py`, rbac → `domain/rbac.py`. It writes `{"fixtures":91.2,…}`. Commit the generated file, so the declared
  numbers always equal the real ones (judges void the bonus if they're > 2 pp off).

## 12. The six hidden edge cases (§6), and where they are handled
1. RR odd n + withdrawal → §5A · 2. Swiss stuck pairing → §5B matching search · 3. DE bracket reset → §5D GF2 ·
4. 3-way tie mini-league → §6 resolve() · 5. Compensation after qualification → §4 + §6, no caching · 6. Last-day transfer during a live match → §9 deferred state.
