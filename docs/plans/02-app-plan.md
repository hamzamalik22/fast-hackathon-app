# Plan 2: Mobile App (`mobile/`, Android)

Worth **10 pts UI/HCI** (judge panel, spec §8.6) + **4 pts offline** (desk check §8.4 + sync script). The APK at
`mobile/release/app-release.apk` is a **required submission file**.
API, WebSocket, demo data, error-message table: `03-integration-plan.md` (§3, §5, §6). Build against the contract with
mock JSON until the backend routes land.

---

## 0. Decisions

- **Rename `app/` → `mobile/`.** Spec §1.3 requires mobile source in `mobile/` and the APK at `mobile/release/app-release.apk`.
- **React Native + Expo + TypeScript, Android only. Pin Expo SDK 54 (React Native 0.81.5).** We build the APK locally with Gradle (no EAS cloud).
  SDK 54's Android defaults match the installed toolchain exactly (checked against RN 0.81.5's `gradle/libs.versions.toml`),
  so Gradle won't download any SDK or NDK mid-build. **Don't use the `@latest` template** (Expo SDK 58 / RN 0.88 needs compileSdk 37 and build-tools 37.0.0, which aren't installed).

  | Item | Version (installed) | Where it's set |
  |---|---|---|
  | Android SDK platform (compileSdk / targetSdk) | 36 | `platforms/android-36`; RN catalog + `expo-build-properties` |
  | Build tools | 36.0.0 | `build-tools/36.0.0` |
  | NDK | 27.1.12297006 (r27b) | `ndk/27.1.12297006`; RN catalog default |
  | CMake | 3.22.1 | `cmake/3.22.1`; RN native build default |
  | Minimum SDK | 24 | platform setting (spec needs Android 10 / API 29+, so 24 is fine) |
  | JDK / Node | 17 / 22 | required by RN 0.81 (JDK 17, Node ≥ 20.19) |
- **Libraries** (install with `npx expo install` so versions match the SDK):
  - `expo-router`: stack + tabs, so back always works
  - `react-native-paper`: Material 3, consistent theming, 48 dp targets, a11y props
  - `expo-sqlite`: cache + persistent action queue (NFR-4)
  - `expo-secure-store`: JWT in **Android Keystore** (NFR-5, §8.1)
  - `@react-native-community/netinfo`: connectivity
  - `expo-file-system` + `expo-sharing`: save/open the receipt PDF
  - `expo-crypto`: UUIDs for `action_id`/`event_id`/`order_id`/`device_id`
  - `expo-build-properties`: cleartext HTTP to the laptop
  - `zustand`: small global state
  - `@expo/vector-icons`: icons (each gets a label)

## 1. Setup + de-risk the APK build (first 30 min; do it before writing screens)

```bash
npx create-expo-app@latest mobile --template blank-typescript@sdk-54   # SDK 54 pinned; the CLI may be @latest, the template must not be
cd mobile
npx expo install expo-router react-native-safe-area-context react-native-screens expo-linking expo-constants \
  expo-sqlite expo-secure-store @react-native-community/netinfo expo-file-system expo-sharing expo-crypto \
  expo-build-properties react-native-paper
npm i zustand
```
`app.json`:
- `"orientation": "default"` (rotation must work)
- `"android": {"package": "com.nascon.league"}`
- plugins: `expo-router`, `expo-sqlite`, `expo-secure-store`, and `expo-build-properties` pinned to the installed toolchain:
  ```json
  ["expo-build-properties", { "android": {
      "compileSdkVersion": 36, "targetSdkVersion": 36, "buildToolsVersion": "36.0.0", "minSdkVersion": 24,
      "usesCleartextTraffic": true } }]
  ```
  Without cleartext, every `http://` call fails on the device. NDK 27.1.12297006 and CMake 3.22.1 are already the RN 0.81 defaults, so don't set them.
- `npx expo install` picks SDK-54-compatible versions of every library. **Never run `npx expo install expo@latest` or an SDK upgrade.**
- `ANDROID_HOME=/home/hamza/Android/Sdk` is already exported, and prebuild picks it up.
  If the first Gradle run starts downloading a platform, build-tools or NDK, a version has drifted: re-check `app.json` and `android/gradle.properties`.
- SDK 54 with target 36 renders edge-to-edge (`edgeToEdgeEnabled=true`). Wrap every screen in `SafeAreaView` from `react-native-safe-area-context`,
  or headers and the SyncBar slide under the status bar (judges check "nothing overflows").

**Build a hello-world release APK right away**, so toolchain problems surface at 11:30 instead of 14:40:
```bash
npx expo prebuild -p android --clean
cd android && ./gradlew assembleRelease -PreactNativeArchitectures=arm64-v8a,x86_64   # phone + emulator ABIs only = faster, smaller
mkdir -p ../release && cp app/build/outputs/apk/release/app-release.apk ../release/app-release.apk
adb install -r ../release/app-release.apk
```
The Expo template signs release builds with the debug keystore, so the APK installs as-is. Gitignore `mobile/android/` and `mobile/ios/`,
but **commit `mobile/release/app-release.apk`** (keep it < 100 MB; the 2-ABI split does that).

## 2. Structure

```
mobile/
  app/                              # expo-router
    _layout.tsx                     # Providers: PaperProvider(tenant theme), DB init, session restore, <SyncBar/> under header
    login.tsx                       # email+password, demo-account chips, link to Settings
    settings.tsx                    # Server URL (default http://10.0.2.2:8080) + "Test connection" (GET /health)
    (tabs)/_layout.tsx              # role-aware tabs (see §4)
    (tabs)/index.tsx                # Home: role-aware dashboard (today's matches, my club, quick actions)
    (tabs)/fixtures.tsx             # league picker + match list
    (tabs)/standings.tsx            # league picker + table
    (tabs)/store.tsx                # catalogue
    (tabs)/club.tsx                 # my club / club list → club profile
    (tabs)/more.tsx                 # Profile, Sync status, Settings, Logout
    match/[id].tsx                  # live score, timeline, pinned product, organizer actions
    match/[id]/score.tsx            # scoring entry (organizer)
    club/[id].tsx                   # club profile
    roster/index.tsx                # roster management (club manager)
    roster/[playerId].tsx           # action form: transfer / loan / release + history
    product/[id].tsx                # variant picker + Add to cart
    cart.tsx  checkout.tsx  receipt/[orderId].tsx  orders.tsx
    sync.tsx                        # pending queue + last sync results
  src/
    api/client.ts                   # baseUrl from settings, Bearer token, 10 s timeout, maps error body → ApiError{code,message}
    api/endpoints.ts                # typed calls (integration plan §3)
    db/sqlite.ts                    # migrations: kv, cache, outbox, sync_log
    db/cache.ts                     # cacheFirst(key, fetcher): show cache instantly → refresh from network → write cache
    sync/outbox.ts                  # enqueue(), flush(), auto-sync
    sync/messages.ts                # error code → plain language (integration plan §6)
    realtime/ws.ts                  # reconnecting WebSocket + subscribe(channels)
    state/session.ts                # user, role, tenant, token (SecureStore)
    state/net.ts                    # status: online | offline | syncing; pendingCount
    ui/theme.ts                     # tokens: spacing 4/8/16/24, radius, type scale, tenant primary/accent
    ui/components/                  # AppHeader, SyncBar, StatusChip, ScoreBoard, EmptyState, ErrorState,
                                    # LoadingState, ConfirmDialog, PrimaryButton, Snackbar host
```

## 3. Required screens (spec §8.2): build in this order

| # | Screen | Must show / do | Who |
|---|---|---|---|
| 1 | **Login** | email + password, show/hide password, plain-language error, loading on the button, "Server settings" link, demo-account chips that fill the email | all |
| 2 | **Fixtures** | list of matches with **status chip (icon + text)**, date/time, venue, teams, score if started; pull-to-refresh; tap → Match detail; empty state "No matches yet" | all |
| 3 | **Match detail** | big **ScoreBoard** (score; wickets/overs for innings sports; rounds for round sports), status, **live updates over WebSocket**, event timeline (compensated events struck through with the label "Reversed", pending offline events greyed with "Waiting to sync"), **pinned product card** with a Buy button | all; organizer sees "Add score event" |
| 4 | **Standings** | points table (rank, team, P, W, D, L, Diff, Pts); a **qualification badge with text** ("Clinched ✓", "Eliminated ✕", "In contention"); tap a row → club; horizontal scroll for extra columns on small screens | all |
| 5 | **Club profile** | logo, name, tenant colors, home venue (name + coordinates, "Open in Maps" link), social handles, staff (coach/manager/physio), roster grouped by position with role badges, season stats | all |
| 6 | **Store** | catalogue grid/list → product → **variant picker** (size/color chips, stock shown) → cart (qty ±, remove) → checkout (discount code field, **mock card choice**: "Pay (success)", "Card declined", "Capture fails", for the demo) → **receipt view** (in-app summary + "Download / Share PDF") → My orders | all signed-in |
| 7 | **Roster management** | the manager's squad list; per player: **Transfer / Loan / Release** (form: destination squad, effective date (default today), loan end date, reason) and "Add player"; **confirm dialog** before each; history/audit trail | club_manager only |
| 8 | **Scoring entry** | team toggle (home/away) + buttons generated **from the sport's `scoring_events` config** (never hard-code "goal"); start/end match; discipline; **"Undo / Correct" = compensating event**, picked from the timeline with a confirm dialog | league_organizer (own league) |
| 9 | **Sync status** | **always-visible SyncBar** under the header on every screen: `● Online` / `⊘ Offline – changes saved on this phone` / `⟳ Syncing…`, plus "N pending" → tap opens the Sync screen (pending queue, last results, "Sync now" button) | all |
| + | Settings | server URL, test connection, app version, device id | all |

## 4. Role-aware navigation (judged area 5: "right screen for the right role")

Login → role-aware **Home** shows the tasks for that role first.

| Role | Tabs | Extra entry points |
|---|---|---|
| super_admin | Home, Fixtures, Standings, Store, More | admin overview (tenants, leagues) on Home |
| league_organizer | Home, Fixtures, Standings, Store, More | "Score a match" on Home + a button on match detail (own league only) |
| club_manager | Home, Fixtures, Standings, Store, **My Club** | Roster management from My Club + Home |
| player | Home, Fixtures, Standings, Store, My Club | own profile / history |
| viewer | Home, Fixtures, Standings, Store, Clubs | read-only, **no** edit buttons rendered at all |

Hide what a role can't do; don't show disabled buttons that produce a 403. The server still enforces everything.

## 5. Offline tolerance (NFR-4): the desk check (§8.4), step by step

**SQLite tables**
```sql
kv(key TEXT PRIMARY KEY, value TEXT)                     -- server_url, device_id, cached user/tenant JSON
cache(key TEXT PRIMARY KEY, json TEXT, updated_at TEXT)  -- 'leagues', 'fixtures:{league}', 'standings:{league}', 'club:{id}', 'match:{id}', 'products'
outbox(action_id TEXT PRIMARY KEY, type TEXT, queued_at TEXT, base_version INTEGER, payload TEXT, status TEXT)  -- status: pending|syncing
sync_log(action_id TEXT, status TEXT, resolution TEXT, error_code TEXT, message TEXT, processed_at TEXT)
```
1. **Cache:** every Fixtures / Standings / Club / Match / Store read goes through `cacheFirst`. Show the cached data immediately with
   "Last updated 10:42"; refresh when online. Pre-warm after login: leagues, fixtures + standings for the user's leagues, the own club.
2. **Offline indicator:** `online = NetInfo.isConnected && last /health ping OK` (ping every 10 s while in the foreground; `/health` is not rate-limited).
   NetInfo alone says "connected" when Wi-Fi is up but the laptop is unreachable.
3. **Queue, using exactly the format of spec §5.14:**
   ```json
   { "action_id": "<uuid>", "type": "score_event", "queued_at": "2026-10-17T11:00:00Z", "base_version": 3,
     "payload": { "event_id": "<uuid>", "match_id": "m1", "type": "score", "payload": { "team_id": "t1", "event_type": "goal" } } }
   { "action_id": "<uuid>", "type": "roster_transfer", "queued_at": "…", "base_version": 1,
     "payload": { "request_id": "<uuid>", "league_id": "…", "player_id": "…", "type": "transfer", "from_squad_id": "…",
                  "to_squad_id": "…", "effective_date": "2026-10-17", "loan_end_date": null, "reason": "…", "requested_by": "<user_id>" } }
   ```
   - `queued_at` without milliseconds (`YYYY-MM-DDTHH:MM:SSZ`). UUIDs fit the id regex (≤ 64 chars, hyphens allowed).
   - `base_version`: score = the cached match `version` (plus 1 for each earlier pending event of the same match);
     roster = the cached player `audit_count` (plus pending entries for that player).
   - **One code path:** every scoring and roster action is written to the outbox first. If online, `flush()` runs immediately;
     offline, it stays "pending". Optimistic UI: show the pending item in the timeline/roster with a "Waiting to sync" chip.
4. **Survives force-close:** the outbox is SQLite and the token is in SecureStore. On cold start: restore the session from SecureStore + the cached user,
   **skip login when offline**, show Home with cached data + the Offline bar + the pending count.
5. **Auto-sync:** on the offline→online transition, on app foreground, after enqueue when online, and via the "Sync now" button.
   - `flush()` → `POST /api/v1/sync {device_id, actions:[all pending, oldest first]}`.
   - Show a **results sheet**, per action: "Applied ✓" / "Already synced" / "Rejected ✕ – <plain message from sync/messages.ts>".
   - Then remove the actions from the outbox, write sync_log, re-fetch the affected match/club, and update the cache.
   - On network failure mid-sync, put the items back to pending.

## 6. UI/HCI checklist (the 5 judged areas; walk through it before 14:15)

1. **Navigation & ease of use**
   - Fixtures / Standings / Store / Profile are reachable from the tabs in 1 tap.
   - Buying an item takes ≤ 5 taps.
   - Android back and the header back work everywhere. No dead ends: every error state has a "Try again" button and a way back.
2. **Visual consistency & hierarchy**
   - One theme file: Paper MD3 theme from the **tenant's** primary/accent colors + logo in the header.
   - Same spacing scale, button styles and type scale on every screen.
   - The score is the largest text on Match detail (≥ 40 sp). Buy/Checkout is the only filled primary button on its screen.
3. **Feedback & errors**
   - Loading spinners/skeletons on every fetch; snackbars for success ("Order paid", "Transfer queued").
   - Errors in plain language via the code→message map, **never "Error 500" or raw codes**.
   - Confirm dialogs before: release player, transfer/loan, compensation (undo), end match, checkout/pay, logout with pending actions.
   - Online/Offline/Syncing is always visible.
4. **Readability & accessibility**
   - Body ≥ 16 sp, secondary ≥ 14 sp; contrast ≥ 4.5:1 (check the tenant color on white, fall back to a darker shade if it fails).
   - Tap targets ≥ 48 dp. `accessibilityLabel` on every icon button.
   - **Status never shown by color alone:** always icon + text (Clinched ✓, Live ●, Offline ⊘, Pending ⏳).
   - Supports system font scaling.
5. **Right screen for the role, robustness**
   - Role-gated UI (§4). Every list has an empty state ("No matches yet", "Your cart is empty", "No pending changes").
   - Test at **360×640 dp** (a small emulator profile) **and in landscape**: use FlatList/ScrollView, flexbox, no fixed heights;
     long names truncate with ellipsis; the standings table scrolls horizontally.

## 7. Rehearse the three judge tasks (§8.6) on the release APK

- **A. Standings + a match:** Standings tab → pick league-alpha-1 → table → Fixtures → open the live match → the score updates when another device posts an event.
- **B. Buy + receipt:** Store → jersey **size L** or the scarf (size M has stock 1 by default; reset before each judging slot) → variant → cart → Pay → receipt → Download PDF opens.
- **C. Roster action + offline:** log in as manager@nascon.test → My Club → player → Transfer → confirm → applied. Then airplane mode →
  repeat the action (as Organizer, also one score event) → shows Pending → force-close → reopen (still offline, pending still there) →
  network on → auto-sync → per-action results with plain reasons → queue empty.

## 8. Timeline (mobile dev)

| Time | Deliverable |
|---|---|
| 11:00–11:30 | project, deps, hello-world **release APK built and installed** |
| 11:30–12:15 | api client + mock data, theme, SyncBar, Login, Settings, tabs by role |
| 12:15–13:00 | Fixtures, Match detail (+WS), Standings, Club profile, with SQLite cache |
| 13:00–13:40 | Store → cart → checkout → receipt PDF |
| 13:40–14:10 | Roster management, Scoring entry, outbox + Sync screen, offline desk-check run |
| 14:10–14:30 | HCI pass (§6), small-screen + rotation pass, **final release APK** → `mobile/release/app-release.apk` → commit + push |
| 14:30–14:50 | rehearse tasks A/B/C on the device (no code changes except blockers) |

Push at least once in every hour window (integration plan §0). Commit the APK at every working milestone, not only at the end.
