# NaSCon League: Android app (Expo SDK 54 · React Native 0.81 · TypeScript)

## Build & install

```bash
npm ci
./build-apk.sh                # -> release/app-release.apk  (add --clean after changing app.json / native modules)
adb install -r release/app-release.apk
```

The toolchain is pinned in `app.json` (`expo-build-properties`): compileSdk/targetSdk 36, build-tools 36.0.0, minSdk 24.
NDK 27.1.12297006 and CMake 3.22.1 come from the RN 0.81 defaults. Cleartext HTTP is enabled for the laptop backend.
Never upgrade the Expo SDK.

## Structure: logic is separate from UI

```
App.tsx                  providers, role-aware navigation (tabs + stack), session restore, connectivity start
src/lib/                 ALL logic (keep when replacing the UI)
  api.ts                 typed client for /api/v1 (server URL from Settings, JWT header, error -> ApiError)
  db.ts                  SQLite: kv, cache, outbox (offline queue), sync_log
  state.ts               zustand stores: useSession (token in SecureStore = Android Keystore), useNet, useCart
  sync.ts                connectivity monitor (NetInfo + /health ping), enqueue(), flush() -> /api/v1/sync
  hooks.ts               useCached (cache-first loader), useLiveChannel (WebSocket), formatters
  data.ts                screen data hooks (see below)
  actions.ts             everything a screen can do (see below)
  messages.ts            error code -> plain-language message (never show raw codes)
src/screens/             MINIMAL placeholder screens: replace these with the designed UI
```

### Data hooks (`src/lib/data.ts`): each returns `{ data, loading, error, updatedAt, fromCache, refresh }`

| Hook | Use on screen |
|---|---|
| `useLeagues()`, `useSelectedLeague(leagues)` | league picker (selection persisted) |
| `useFixtures(leagueId)` | Fixtures list (`status`, `scheduled_at`, `venue`, scores) |
| `useMatch(matchId)` | Match detail; live via WebSocket; `.pending` = queued offline events for this match |
| `useStandings(leagueId)` | Standings table (`status`: clinched / eliminated / still_possible, `team_names`) |
| `useClub(clubId)`, `useClubs()` | Club profile (venue lat/lng, socials, staff, stats, roster with `audit_count`, squads) |
| `usePlayerHistory(playerId)` | Roster audit trail |
| `useProducts()`, `useOrders()` | Store catalogue, my orders |
| `usePending(ref?)`, `useSyncLog()` | Sync screen: pending queue + last per-action results |
| `can(role, 'score' / 'roster' / 'admin')` | Role-gated UI |

All of these are cached in SQLite, so Fixtures, Standings and Club open offline.

### Actions (`src/lib/actions.ts`)

| Action | Notes |
|---|---|
| `login(email, password)`, `logout()` | Login caches leagues, fixtures, standings and the user's club for offline use |
| `scoreEvent(match, teamId, eventType)`, `startMatch`, `endMatch`, `tiebreakWinner`, `disciplinePoints`, `compensate(match, eventId, reason)` | Organizer. Always queued in the outbox in the spec 5.14 format, then synced immediately if online |
| `queueRosterAction({club, player, type, toSquadId, effectiveDate, loanEndDate, reason})` | Manager transfer / loan / release, queued the same way |
| `addPlayer(clubId, name, position)` | Online only |
| `checkout(cartLines, discountCode, 'tok_success' / 'tok_declined' / 'tok_capture_fail')` | Mock gateway. Throws `ApiError` with a plain `.message` |
| `openReceiptPdf(receipt)` | Writes the server PDF to the cache and opens the share/open sheet |

Global state: `useNet()` gives `{ online, syncing, pending, lastSync, lastResults }`. Show it always (see `SyncBar`).
`lastResults` drives the "Sync finished" dialog with applied/rejected reasons.

## Offline desk check (spec 8.4)
1. Online: open Fixtures, Standings and a Club. They are cached.
2. Airplane mode: the bar shows "Offline". Cached screens still open.
3. Organizer: score an event. Manager: transfer a player. Both show as "⏳ Waiting to sync".
4. Force-close and reopen: you stay signed in (SecureStore) and the queue is still there (SQLite).
5. Network on: sync runs automatically (or press Sync now). A dialog lists each action as applied or rejected with a plain reason, and the queue clears.
