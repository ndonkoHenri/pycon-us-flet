# Backlog: PyCon US 2027 app on Flet

**Status:** companion to [`PLAN.md`](../PLAN.md), 2026-10-11. **Owner:** U. Binding inputs: PLAN.md and the decisions record ([`decisions.md`](decisions.md), D-01..D-136; D-108..D-110 record the amendments this backlog needed, section 14 notes 1, 3 and 8). Every one of the 263 ids of [`feature-matrix.md`](feature-matrix.md) appears **exactly once** in section 4, with tier, workstream, owner, estimate and dependencies; the approach and gotchas stay in the matrix (each id links to its matrix section).

**How to use it.** Work milestone by milestone (section 4). Each id is done when its named test `test_<AREA>_<NN>_<slug>` passes on `main` (D-98); that is what the weekly burn-down counts (section 12). Non-feature work has `X-` ids (or its PLAN id: spikes S1-S10, E1-E6, U1-U15, P1-P13).

Contents: 1 Totals and reconciliation · 2 Legend · 3 Capacity by milestone · 4 Milestone backlogs (M0-M5, dropped) · 5 Upstream items · 6 T3 gated items · 7 T2 and the cut order · 8 PSF asks · 9 Badge Days · 10 CFP and talk · 11 `good first issue` candidates · 12 Burn-down and triggers · 13 Conference, 27.1 and the 05-17/18 sprint · 14 Notes on the plan

---

## 1. Totals and reconciliation with PLAN 7.1

Per-id estimates were derived from the catalog complexity (1-5, +0.5 for *adapt*) and scaled so that, per workstream, **id estimates + non-id tasks = the PLAN 7.1 demand**. Duplicated Ionic rows (the same behaviour listed under two areas) carry 0.5 h for their own test only. Interim->upgrade rows carry the **interim** only; the upgrade is a separate E/U task.

| ws | PLAN 7.1 workstream | PLAN h | ids | id h | non-id tasks | task h | owner |
|---|---|---|---|---|---|---|---|
| m0 | M0 spikes, CI, devserver | 40 | 4 | 8 | X-REPO, X-DEVSERVER, spikes S1-S10 (X-FLETMAIN, X-HOSTHARNESS: 0 h here, counted in X-NIGHTLY / X-UIFLOWS) | 32 | U |
| data | Data layer and Ionic harness | 60 | 33 | 50 | X-HARNESS | 10 | U |
| core | Stores, bootstrap, caps | 30 | 16 | 16 | X-STORES, X-SAFE, X-BUILDINFO, X-CAPS, X-APPCFG | 14 | U |
| shell | Shell, routes, themes | 45 | 29 | 43 | X-DEEPLINK | 2 | U |
| sched | Schedule cluster | 55 | 27 | 51 | X-CHANGELOG | 4 | U |
| detail | Detail screens and events | 35 | 26 | 35 | - | 0 | U |
| maps | Maps | 20 | 13 | 20 | - | 0 | U |
| info | Info and notification settings (CC) | 20 | 20 | 20 | - | 0 | CC, U |
| auth | Auth and sync | 25 | 23 | 25 | - | 0 | U |
| staff | Staff tools and outbox | 60 | 48 | 55 | X-OUTBOX | 5 | U |
| e1 | E1 | 35 | 0 | 0 | E1 | 35 | U |
| ups | U1, U4, U5 | 20 | 0 | 0 | U1, U4, U5, X-POINTREL, X-FLET11 | 20 | FT+U, U |
| qa | Tests and a11y (CC + U) | 35 | 0 | 0 | 8 tasks (sections 4-10) | 35 | CC, U, U+CC |
| rel | CI and store | 30 | 5 | 6.5 | X-RELEASE, X-NIGHTLY, X-SIGNED, X-STOREFORMS, X-HOTFIX, X-DASH | 23.5 | U, U+PSF-I |
| field | Badge Days, betas, fixes | 45 | 0 | 0 | X-BD1, X-BD2, X-BETA, X-FIX, X-COMAINT | 45 | U, U+PSF-E |
| talk | Talk | 25 | 0 | 0 | 9 tasks (sections 4-10) | 25 | U |
| t2 | T2 | 92 | 19 | 71 | U3, U9, U15 | 21 | CC, U, U+PSF-I |
| t3 | T3 gated | 127 | 0 | 0 | E2, E3, U7, E4, U6, U8 | 127 | CC+U, FT+U, U |
| | **Committed (T0, T0-P, T1)** | **580** (+15 % = 667) | | | | | |

Committed hours by owner: U 523.5 h (incl. half of X-A11Y), CC 32.5 h (incl. half of X-A11Y), shared with FT/PSF 24 h. CC also owns 33 h of T2, so CC demand is 65.5 h of the 80 h CC capacity; the remaining 14.5 h is CC's share of E4 (T3) at most.

---

## 2. Legend

| Column | Meaning |
|---|---|
| id | Feature id; the link opens its section in `feature-matrix.md` (approach, gotchas, CAP/BLD rows) |
| disp | `port` / `adapt` / `i->u` (interim->upgrade) / `drop`, from the matrix |
| tier | `T0` attendee core (never cut) · `T0-P` needs P3 (login, `check_features`, `mobile_state`) · `T1` staff tools; this backlog also files Dev Tools DEV-01..06 here (M3, not attendee-blocking) · `T2` should-have, on the cut list (section 7) · `-` dropped. T3 is never a row tier: T3 is the *upgrade half* of an i->u row (column upg) |
| ws | Workstream code from section 1 (one PLAN 7.1 demand line each) |
| owner | `U` user · `CC` community contributor (U reviews) · `FT` Flet core team · `PSF-I` / `PSF-E`. `gfi` = `good first issue` candidate (section 11) |
| h | Estimate in hours (AI-assisted porting assumed, PLAN 7.1); includes the id's named test |
| depends on | Ids/tasks that must land first, then PSF items (`P3`; a parenthetical such as `P9 (2027 values only; ...)` means only that part waits for the PSF item, which may fall after the milestone exit), spikes (`spike S2`; success criteria are always written `criterion S4`, never bare). `dup of X` = same implementation as X, this row adds its own test |
| upg | Upgrade that lights up through `Caps` without screen changes (PLAN 5.7): `E1`, `U1`, `U4`, `U5` are committed; `(T2)`, `(T3)`, `(27.1)`, `(post)` as tagged |

Flet names used below were checked in the local SDK on 2026-10-11 (`ft.Router`, `ft.Route(recursive, modal)`, `page.render_views`, `ft.use_route_location`, `ft.use_view_path`, `ft.observable`, `ft.create_context`, `ft.use_memo`, `ft.use_effect`, `ft.Dismissible.confirm_dismiss`, `InteractiveViewer.zoom/pan/reset`, `ListView.scroll_to`, `ft.SharedPreferences`, `ft.Connectivity.on_change`, `ft.SemanticsService`, `ft.Banner`, `ft.UrlLauncher`, `ft.LaunchMode.IN_APP_BROWSER_VIEW`, `flet_secure_storage.SecureStorage`, `flet_permission_handler`, `flet.testing.FletTestApp`/`Tester`). **Not yet existing** and only named as upstream items: `ft.RefreshIndicator` (U1), `page.get_app_info()` (U4), `InteractiveViewer.set_transform()/zoom_to_rect()` (U3), `ft.use_route_search()` (U9), `[tool.flet.ios.entitlement]` (U5), `[tool.flet.android.queries]` (U6), `core_library_desugaring` (U7), and the E1-E6 extension APIs (D-25).

---

## 3. Capacity by milestone (check before each milestone starts)

Capacity spreads PLAN 7.1 over calendar weeks (weeks = calendar days of the milestone, both ends inclusive, / 7): U app time 15 h/week (+40 h holiday sprint in M2) minus 10 %; U Flet-work time 10 h/week minus ~25 h in Nov (M1) and ~25 h in Feb (M3); CC 80 h over Jan-Mar. Demand is this backlog's committed hours (ids + tasks) by the milestone they are filed under; the dropped DATA-27 contract test (0.5 h, section 4.6) counts in M2 next to X-CONTRACT; contingency (87 h) is not spread.

| Ms | Dates | Weeks | U app h | U Flet h | CC h | Capacity | Committed demand | T2 | T3 | Balance (committed) |
|---|---|---|---|---|---|---|---|---|---|---|
| M0 | 10-12 -> 11-13 | 4.7 | 63 | 47 | 0 | 110 | 44 | 0 | 0 | +66 (cum. +66) |
| M1 | 11-16 -> 12-06 | 3 | 40 | 5 | 0 | 45 | 125 | 0 | 0 | -80 (cum. -14) |
| M2 | 12-07 -> 01-31 | 8 | 144 | 80 | 25 | 249 | 241 (incl. DATA-27 0.5) | 0 | 17 | +8 (cum. -6) |
| M3 | 02-01 -> 03-05 | 4.7 | 63 | 22 | 35 | 120 | 87.5 | 82 | 110 | +32.5 (cum. +26.5) |
| M4 | 03-06 -> 03-31 | 3.7 | 50 | 37 | 20 | 107 | 23.5 | 10 | 0 | +83.5 (cum. +110) |
| M5 | 04-01 -> 04-30 (capacity counted to 04-16) | 2.3 | 31 | 23 | 0 | 54 | 55.5 | 0 | 0 | -1.5 (cum. +108.5) |
| M6 | 05-01 -> 05-18 | | | | | | 3.5 (X-DRYRUN) | | | |

Reading it:
- **M1 is overloaded on its own** (125 h of committed work vs ~45 h in its 3 weeks, with the Nov Flet release crunch inside it). It works only by front-loading: start the pure `core/` DATA functions and X-HARNESS in M0 as soon as spike S4 lands (10-26); M0 has the spare hours. Even then M0+M1 is ~14 h short, so these M1 rows, not needed for the differential exit or the demo video, are planned to finish in the first M2 week (12-07 → 12-13) and count against G2, not M1: SHELL-01, THEME-11, THEME-12, NATIVE-08, INFO-14, SCHED-26, SCHED-27, SCHED-28 (12 h); the rest comes out of contingency. Both balances assume pooled U hours (next bullet). Section 14, note 5.
- **The plan pools U's two buckets.** Committed upstream work (E1, U1/U4/U5) is 55 h against 220 h of Flet-work time, while committed app work exceeds app time; the PLAN 7.1 fit (667 h vs 700 h) holds only because Flet-work hours may be spent on the reference app (D-108; section 14, note 2).
- T2 (92 h) and T3 (127 h, D-112) are not in the committed column: they run only with margin (G3 rule: burn-down within 5 %).

---

## 4. Milestone backlogs

Rows are grouped by workstream, then matrix order. Non-feature tasks of the milestone come first. Dates are 2026 for M0-M1 and 2027 afterwards.

### 4.0 M0 Foundations (2026-10-12 → **11-13**)

**Exit:** A written verdict per spike (spike S8 by 11-30); schedule running on 2 phones; **G1** (P1, P2). See [PLAN 7.2](../PLAN.md#72-milestones). **This backlog:** 4 ids; committed 44 h.

Non-feature tasks:

| task | what | ws | owner | h | depends on | due |
|---|---|---|---|---|---|---|
| X-REPO | Repo skeleton (`pyproject.toml`, `src/pycon_us`, uv lock, CONTRIBUTING, labels, issue templates, DCO) | m0 | U | 2 | - | 10-19 |
| X-DEVSERVER | `tools/devserver.py` + `tools/record_fixtures.py`: recorded feeds now; fake signed `/api/v1` grows with P3 (check-in, lead, CoC, `mobile_state`) | m0 | U | 6 | spike S4 | 11-13 (API part 12-19) |
| spike S1 | `flet build aab/ipa` with the PSF bundle ids (ipa unsigned via `--no-codesign` until P4) | m0 | U | 3 | X-REPO | 11-06 |
| spike S2 | `tzdata` + `zoneinfo` on iOS, Android, Pyodide | m0 | U | 2 | X-REPO | 10-30 |
| spike S3 | Parse 824 KB feed <= 400 ms and per-day list build time on a Pixel 6a (decides `build_controls_on_demand`, D-68) | m0 | U | 3 | spike S4 | 11-13 |
| spike S4 | Ionic reference JSON for the 2025/2026 feeds | m0 | U | 2 | - | 10-26 |
| spike S5 | Throwaway TestFlight upload (ITMS-91053) from U's own account and a throwaway bundle id | m0 | U | 2 | spike S1 | 11-13 |
| spike S6 | `sentry-sdk` on a device (fallback: envelope reporter) | m0 | U | 2 | spike S1 | 11-13 |
| spike S7 | Standalone extension wheel via `[tool.flet.<platform>].dependencies` + `mobile_scanner` under the material_ui gate | m0 | U | 4 | spike S1 | 11-13 |
| spike S8 | Firebase Dart-only `initializeApp(options)` (verdict due **11-30**, after M0 exit, PLAN 7.2) | m0 | U | 3 | spike S7 | 11-30 |
| spike S9 | Query string in `page.route`, recursive drill segment, global modal over a drill | m0 | U | 2 | X-REPO | 11-06 |
| spike S10 | Minimum iOS version of every wrapped pod (decides U12) | m0 | U | 1 | spike S7 | 11-13 |
| X-FLETMAIN | M0 spike for the nightly `flet-main` job (testing-and-quality.md §7, build-and-release.md §7): flet-dev/flet `main` checked out and installed **editable** (`flet`, `flet-cli`, extensions) and stamped 1.99.0, so the git-tag and `.fvmrc` lookups resolve; the checkout's `main` build template and in-repo `flet_integration_test`; `==1.1.*` dev pins relaxed (only the non-flet locked packages installed); `flet build apk` + Android smoke flows (`-m smoke`); a red run opens one `flet-main-drift` issue. Done when one run has been seen to pass | m0 | U | 0 (counted in X-NIGHTLY) | X-REPO, spike S1 | 11-13 |
| X-HOSTHARNESS | M0 spike for Linux host mode (testing-and-quality.md §2.2, §6.2): sparse flet-dev/flet checkout at the pinned tag in `.flet/` (`client/`, `packages/`, `sdk/python/packages/*/src/flutter`, `.fvmrc`), `FLET_TEST_DEVICE_MODE=0`, `FLET_TEST_DISABLE_FVM=1`, `xvfb-run` + llvmpipe on `ubuntu-latest` (fallback `macos-26`). Rule: `tests/harness/host_main.py` imports its scenario, fakes and transport from the `tests.harness.*` package only and keeps no module-level state (the plugin imports it as bare `host_main`) | m0 | U | 0 (counted in X-UIFLOWS) | X-REPO, X-DEVSERVER | 11-13 |
| X-PITCH | Proposal email to infrastructure@python.org (cc Jacob Coffee) + 90 s recording; web demo link 10-23 | talk | U | 2 | - | 10-16 |
| X-ABSTRACT | Talk + poster abstracts, accurate on both tracks (mentorship sign-up ~11-20 optional) | talk | U | 2 | - | 11-14 |

| id | feature | disp | tier | ws | owner | h | depends on | upg |
|---|---|---|---|---|---|---|---|---|
| [DEV-07](feature-matrix.md#developer-tools-dev) | Build environments (base / development / production) | adapt | T0 | m0 | U | 1.5 | X-REPO | - |
| [DEV-08](feature-matrix.md#developer-tools-dev) | Release tooling and CI | adapt | T0 | m0 | U | 4 | X-REPO | - |
| [NATIVE-02](feature-matrix.md#native-platform-native) | Platform floors and device/orientation support | adapt | T0 | m0 | U | 1 | spike S10, P6 (OD-1; ship minSdk 34 until approved) | - |
| [DATA-34](feature-matrix.md#data-layer-feed-processing-queries-data) | Build environments and year-scoped constants | adapt | T0 | m0 | U | 1.5 | - | - |

### 4.1 M1 CFP demo (11-16 → **12-06**)

**Exit:** Differential test green on the 2026 feed; demo video **12-07**; CFP **12-11**. Android + web (iOS simulator best effort). See [PLAN 7.2](../PLAN.md#72-milestones). **This backlog:** 62 ids; committed 125 h.

Non-feature tasks:

| task | what | ws | owner | h | depends on | due |
|---|---|---|---|---|---|---|
| X-HARNESS | `tools/ionic_reference/`: esbuild bundle of Ionic `processData`/`filterSession`/pipes, normaliser, differential runner on 2025 + 2026 feeds | data | U | 10 | spike S4 | 11-27 |
| X-STORES | `stores/*` + `stores/contexts.py`: one `ft.create_context` per `@ft.observable` store, typed hooks (D-44, D-45) | core | U | 3 | X-REPO | 11-20 |
| X-SAFE | `services/safe.py` (`@safe`), lint rule for unwrapped handlers, `TopToast`, `services/crash.py` (Sentry handlers, scrubbing) | core | U | 3 | spike S6 | 11-27 |
| X-BUILDINFO | `build_info.py` dev stub + CI writer (VERSION, BUILD_NUMBER, GIT_SHA, TARGET, CAPS, PYCON_ENV) | core | U | 1 | X-REPO | 11-20 |
| X-TRACE | `tools/feature_trace.py`: test-name parser (D-98), CI gate from M2 (an id past its milestone exit with no test fails); from G4 the `ci.yml` `trace` job's `--check --junit` over the merged PR + nightly junit also fails on a red or yellow required id (D-129); weekly burn-down report (section 12) | qa | U | 3 | X-REPO | 12-04 |
| X-VIDEO | 3 min demo video from M1 rows: offline schedule, dark theme, favourites, Now & Next, drill Back (SESS-12), scanner spike S7. HC theme and Jump to Now (M2 rows) only if they land early (section 14, note 5) | talk | U | 3 | SCHED-25, spike S7 | 12-07 |
| X-FLET11 | Flet **1.1.0 released** (U drives as maintainer). On the store/iOS critical path: 1.0.4 cannot build on Xcode 27 and E1 needs `flet>=1.1.0` (PLAN 7.3). Tracking only: release duty | ups | FT+U | 0 | - | target 11-30, hard 01-15 (UNCONFIRMED) |

| id | feature | disp | tier | ws | owner | h | depends on | upg |
|---|---|---|---|---|---|---|---|---|
| [DATA-01](feature-matrix.md#data-layer-feed-processing-queries-data) | Single public conference feed fetch | port | T0 | data | U | 1.5 | spike S4, X-HARNESS | - |
| [DATA-02](feature-matrix.md#data-layer-feed-processing-queries-data) | Cache-then-network load with offline fallback (schedule… | adapt | T0 | data | U | 2.5 | DATA-01, STORE-01 | - |
| [DATA-03](feature-matrix.md#data-layer-feed-processing-queries-data) | In-memory memo and manual cache invalidation / refresh | adapt | T0 | data | U | 2 | DATA-02 | - |
| [DATA-04](feature-matrix.md#data-layer-feed-processing-queries-data) | Drop non-session and cancelled slots from the feed | port | T0 | data | U | 1.5 | DATA-01 | - |
| [DATA-05](feature-matrix.md#data-layer-feed-processing-queries-data) | Open Spaces ingested as schedule sessions | port | T0 | data | U | 1.5 | DATA-04 | - |
| [DATA-06](feature-matrix.md#data-layer-feed-processing-queries-data) | Collapse poster and break slots into single timeline ro… | port | T0 | data | U | 2 | DATA-04 | - |
| [DATA-07](feature-matrix.md#data-layer-feed-processing-queries-data) | Synthetic poster-detail sessions | port | T0 | data | U | 1.5 | DATA-06 | - |
| [DATA-08](feature-matrix.md#data-layer-feed-processing-queries-data) | Session title and location cleaning | port | T0 | data | U | 2 | DATA-04 | - |
| [DATA-09](feature-matrix.md#data-layer-feed-processing-queries-data) | Pre-registration-required flag | port | T0 | data | U | 1 | DATA-08 | - |
| [DATA-10](feature-matrix.md#data-layer-feed-processing-queries-data) | Spanish-language session flag (Charlas / En Español) | port | T0 | data | U | 1 | DATA-04 | - |
| [DATA-11](feature-matrix.md#data-layer-feed-processing-queries-data) | Display-time override for Job Fair | adapt | T0 | data | U | 1 | DATA-13 (bundled default in M1; server override from M2), P9 | - |
| [DATA-12](feature-matrix.md#data-layer-feed-processing-queries-data) | Conference-timezone time labels and day bucketing | adapt | T0 | data | U | 2 | spike S2 | - |
| [DATA-13](feature-matrix.md#data-layer-feed-processing-queries-data) | Day / time-group timeline model | port | T0 | data | U | 2 | DATA-12, DATA-06 | - |
| [DATA-14](feature-matrix.md#data-layer-feed-processing-queries-data) | Track registry, icons and kind colours | port | T0 | data | U | 1.5 | DATA-04 | - |
| [DATA-15](feature-matrix.md#data-layer-feed-processing-queries-data) | Speaker registry and session linking | adapt | T0 | data | U | 2.5 | DATA-04 | - |
| [DATA-16](feature-matrix.md#data-layer-feed-processing-queries-data) | Rooms index, room links and display location | port | T0 | data | U | 2.5 | DATA-04 | - |
| [DATA-17](feature-matrix.md#data-layer-feed-processing-queries-data) | Day tabs query (getDays) | port | T0 | data | U | 1 | DATA-13 | - |
| [DATA-18](feature-matrix.md#data-layer-feed-processing-queries-data) | Timeline search, track exclusion and favourites filteri… | adapt | T0 | data | U | 2.5 | DATA-13 | - |
| [DATA-19](feature-matrix.md#data-layer-feed-processing-queries-data) | All-days search timeline | port | T0 | data | U | 1.5 | DATA-18 | - |
| [DATA-20](feature-matrix.md#data-layer-feed-processing-queries-data) | Flat filtered session list (getSessions) | port | T0 | data | U | 1 | DATA-18 | - |
| [DATA-26](feature-matrix.md#data-layer-feed-processing-queries-data) | Session id scheme and route lookups | adapt | T0 | data | U | 2 | DATA-04 | - |
| [DATA-28](feature-matrix.md#data-layer-feed-processing-queries-data) | Track display names (trackName pipe) | port | T0 | data | U | 1 | DATA-14 | - |
| [DATA-29](feature-matrix.md#data-layer-feed-processing-queries-data) | Track URL slugs | port | T0 | data | U | 1 | DATA-14 | - |
| [DATA-30](feature-matrix.md#data-layer-feed-processing-queries-data) | Session order within a time group (sessionOrder pipe) | port | T0 | data | U | 1 | DATA-13 | - |
| [ROOM-06](feature-matrix.md#rooms-room) | Room identity: slugs, name normalisation and session fa… | port | T0 | data | U | 1.5 | DATA-16 | - |
| [MAP-08](feature-matrix.md#maps-and-venue-map) | Seed sprint-only rooms into the Rooms list | port | T0 | data | U | 1 | DATA-16 | - |
| [DATA-35](feature-matrix.md#data-layer-feed-processing-queries-data) | Startup data bootstrap sequence | adapt | T0 | core | U | 1.5 | DATA-02, X-STORES | - |
| [STORE-01](feature-matrix.md#storage-store) | Key-value storage engine and namespacing | adapt | T0 | core | U | 1.5 | X-STORES | - |
| [STORE-02](feature-matrix.md#storage-store) | Local favourites store | port | T0 | core | U | 1 | STORE-01 | - |
| [STORE-09](feature-matrix.md#storage-store) | Schedule track-filter persistence | port | T0 | core | U | 0.5 | STORE-01 | - |
| [SHELL-01](feature-matrix.md#app-shell-and-navigation-shell) | Branded native splash held until first feed emission | adapt | T0 | shell | U | 2 | DATA-02 | - |
| [SHELL-04](feature-matrix.md#app-shell-and-navigation-shell) | Route map and navigation-stack model | adapt | T0 | shell | U | 2 | spike S9 | - |
| [SHELL-05](feature-matrix.md#app-shell-and-navigation-shell) | Bottom tab bar with URL-derived magenta highlight | port | T0 | shell | U | 2 | SHELL-04 | - |
| [SHELL-16](feature-matrix.md#app-shell-and-navigation-shell) | Android hardware back / back gesture | adapt | T0 | shell | U | 2 | SHELL-04 | - |
| [THEME-02](feature-matrix.md#theming-theme) | Light theme palette | port | T0 | shell | U | 1.5 | - | - |
| [THEME-03](feature-matrix.md#theming-theme) | Dark theme with platform-specific surfaces | port | T0 | shell | U | 1.5 | THEME-02 | - |
| [THEME-08](feature-matrix.md#theming-theme) | Track badge palette | port | T0 | shell | U | 1.5 | DATA-14 | - |
| [THEME-10](feature-matrix.md#theming-theme) | Fixed brand colours and forced-white header icons | port | T0 | shell | U | 1.5 | THEME-02 | - |
| [THEME-11](feature-matrix.md#theming-theme) | Typography and text behaviour | adapt | T0 | shell | U | 1 | THEME-02 | - |
| [THEME-12](feature-matrix.md#theming-theme) | Ionicons iconography incl. brand logos | adapt | T0 | shell | U | 2 | - | - |
| [NATIVE-08](feature-matrix.md#native-platform-native) | Status bar, safe areas and edge-to-edge | adapt | T0 | shell | U | 2 | - | - |
| [SESS-12](feature-matrix.md#session-detail-sess) | Back-navigation contract (prevUrl, triple mount) | adapt | T0 | shell | U | 2 | SHELL-04, spike S9 | - |
| [SCHED-01](feature-matrix.md#schedule-tracks-now-sched) | Day selector segment with today auto-selection | port | T0 | sched | U | 1.5 | DATA-17 | - |
| [SCHED-02](feature-matrix.md#schedule-tracks-now-sched) | Time-slot grouped timeline with sticky slot headers | i->u | T0 | sched | U | 2.5 | DATA-13 | U2 (27.1) |
| [SCHED-03](feature-matrix.md#schedule-tracks-now-sched) | Schedule session row (badges, time, room, speakers) | port | T0 | sched | U | 1.5 | DATA-13, THEME-08 | - |
| [SCHED-04](feature-matrix.md#schedule-tracks-now-sched) | Informational notice rows | port | T0 | sched | U | 1 | SCHED-03 | - |
| [SCHED-05](feature-matrix.md#schedule-tracks-now-sched) | Session search on the schedule (current day) | adapt | T0 | sched | U | 2 | DATA-18 | - |
| [SCHED-06](feature-matrix.md#schedule-tracks-now-sched) | 'Search all days' fallback button | port | T0 | sched | U | 1.5 | DATA-19 | - |
| [SCHED-07](feature-matrix.md#schedule-tracks-now-sched) | Favorites-only toggle on the schedule | adapt | T0 | sched | U | 1.5 | STORE-02 | - |
| [SCHED-08](feature-matrix.md#schedule-tracks-now-sched) | Favorites empty states and 'Show favorites on other day… | port | T0 | sched | U | 1.5 | SCHED-07 | - |
| [SCHED-14](feature-matrix.md#schedule-tracks-now-sched) | Offline / load-error state | adapt | T0 | sched | U | 2 | DATA-02 | - |
| [SCHED-17](feature-matrix.md#schedule-tracks-now-sched) | Session filter engine (query / track / segment semantic… | adapt | T0 | sched | U | 3 | DATA-18 | - |
| [SCHED-18](feature-matrix.md#schedule-tracks-now-sched) | Conference-local time display and day bucketing | adapt | T0 | sched | U | 2 | DATA-12, spike S2 | - |
| [SCHED-19](feature-matrix.md#schedule-tracks-now-sched) | Timeline row normalisation (collapsed, renamed and shif… | port | T0 | sched | U | 4 | DATA-06 | - |
| [SCHED-20](feature-matrix.md#schedule-tracks-now-sched) | Colour-coded track badges and track display names | port | T0 | sched | U | 1.5 | DATA-28 | - |
| [SCHED-25](feature-matrix.md#schedule-tracks-now-sched) | Now & Next page | adapt | T0 | sched | U | 2 | DATA-12, SCHED-03 | - |
| [SCHED-26](feature-matrix.md#schedule-tracks-now-sched) | Now page 60-second auto-refresh and pull-to-refresh | adapt | T0 | sched | U | 1.5 | SCHED-25 | U1 |
| [SCHED-27](feature-matrix.md#schedule-tracks-now-sched) | Branded page header with scroll-fade title and page hero | port | T0 | sched | U | 1.5 | THEME-10 | - |
| [SCHED-28](feature-matrix.md#schedule-tracks-now-sched) | Blocking loading overlays on list loads | adapt | T0 | sched | U | 1.5 | - | - |
| [SESS-01](feature-matrix.md#session-detail-sess) | Session detail hero and meta card | port | T0 | detail | U | 2 | DATA-26 | - |
| [SESS-03](feature-matrix.md#session-detail-sess) | Favorite toggle in session detail header | port | T0 | detail | U | 0.5 | STORE-02 | - |
| [INFO-14](feature-matrix.md#info-pages-info) | External link and scheme hand-off | port | T0 | info | U | 0.5 | - | - |

### 4.2 M2 Attendee alpha (12-07 → **2027-01-31**)

**Exit:** Most of the remaining T0 and T0-P (keynote enrichment, keyboard focus and permission strings follow in M3/M4). First **PSF-signed** TestFlight + Play internal builds on the real ids; E1 decodes a 2026 badge; Flet 1.1.0 pinned; **G2** (>= 85 % of M1+M2 rows green). Holiday sprint 12-21 → 01-03. See [PLAN 7.4](../PLAN.md#74-gono-go-checkpoints). **This backlog:** 109 ids; committed 240.5 h (241 h in section 3 with the DATA-27 contract test), T3 15 h.

Non-feature tasks:

| task | what | ws | owner | h | depends on | due |
|---|---|---|---|---|---|---|
| X-CAPS | `platform/caps.py`: `Caps` observable, manifest + probe, veto from app-config, provider selection, `python -m pycon_us.platform.caps`; `tools/caps_manifest.py` | core | U | 3 | X-BUILDINFO | 12-18 |
| X-APPCFG | app-config/app-content JSON Schemas (D-63), `AppConfigStore`, `ContentStore`, bundled fallback, 5 min poll + resume, staff kill switches `features.*` (D-83) | core | U | 4 | X-STORES | 12-18 |
| X-OUTBOX | `core/outbox.py` state machine + `outbox` table in `pycon.db` + the one `SyncWorker` (60 s timer, `ft.Connectivity.on_change`, resume); first kind `favorites` (API-04, AUTH-11); staff kinds added in M3 (API-10) | staff | U | 5 | X-STORES | 01-15 |
| X-DEEPLINK | Deep links (D-38, config clause superseded by D-109): `[tool.flet.android.deep_linking]` + `[tool.flet.ios.deep_linking]` with `scheme="pyconus" host="app"` (the global `[tool.flet.deep_linking]` is ignored for aab/ipa, `build-and-release.md` section 1) + `ShortLink` redirects `/s/:id`, `/p/:id`, `/r/:slug` to the canonical routes (D-33). Tests `test_deeplinks_*` (no feature id) | shell | U | 2 | SHELL-04, spike S9 | 01-24 |
| X-CHANGELOG | Change log #312 (D-54): `core/changelog.py` diff by session id after each fetch (1.5 h) + `schedule_changes` table, banner, 24 h "Changed" chip, `schedule/changes` route `ScheduleChanges` (2.5 h, the "change-log UI" of the D-17 cuts). Tests `test_changelog_*` (no feature id) | sched | U | 4 | DATA-02, SCHED-03 | 01-24 |
| X-CONTRACT | Contract tests: JSON Schemas for `conference.json` and every `/api/v1` response, nightly drift issue | qa | U | 4 | X-DEVSERVER, P3 | 12-31 |
| X-GOLDENS | Goldens: 14 screens x 5 modes x 2 widths + text scale 2.0, DEMO clock; PR subset | qa | CC | 5 | THEME-06 | 01-31 |
| X-CONTRAST | Palette contrast unit tests (>= 4.5:1, HC >= 7:1) from `Tokens` | qa | CC | 2 | THEME-06 | 01-15 |
| X-RELEASE | `release.yml`: protected `release` env, PSF-I reviewer, aab/ipa/web matrix, AAB signature check, Play internal + TestFlight + Hosting uploads, `builds.txt` ledger, `tools/check_release.py` | rel | U | 6 | DEV-08, P4 | 01-24 |
| X-NIGHTLY | `nightly.yml`: host and device UI, full goldens, fallback parity, `flet@main` build + Android smoke (spiked in M0 as X-FLETMAIN), contract vs live feed and staging, perf, burn-down | rel | U | 3 | X-CONTRACT | 01-31 |
| X-SIGNED | First PSF-signed TestFlight + Play internal builds on the real ids (G2 criterion) | rel | U+PSF-I | 4 | X-RELEASE, X-FLET11, P4 | 01-31 |
| X-CFP | Submit talk + poster | talk | U | 1 | X-ABSTRACT | 12-11 |
| E1 | E1 `flet-barcode-scanner` (mobile_scanner 7.4.2): repo, Dart control, Python `BarcodeScanner`, material_ui gate test, device tests on 2026 badges, PyPI 0.1 -> 0.2, `MobileScanner` provider in the app | e1 | U | 35 | spike S7, X-FLET11 | v0.1 on device 01-10; PyPI 0.2 02-19 |
| U1 | U1 core `ft.RefreshIndicator(content, on_refresh, adaptive)` | ups | U | 8 | - | merged 01-15 |
| U4 | U4 `page.get_app_info()` over bundled `package_info_plus` | ups | U | 4 | - | 01-15 |
| U5 | U5 `[tool.flet.ios.entitlement]` in flet-cli (mirrors macOS) | ups | U | 8 | - | merged 01-31 |
| U7 | U7 `core_library_desugaring` in flet-cli | t3 | U | 6 | - | 01-31 (only if E3) |
| U6 | U6 `[tool.flet.android.queries]` in flet-cli | t3 | U | 6 | - | 01-31 (only if E4) |
| U8 | U8 inline-table resource `meta_data` + `[tool.flet.android.string_resources]` in flet-cli (autofill upgrade, D-112) | t3 | U | 5 | - | 01-31 (only if autofill) |

| id | feature | disp | tier | ws | owner | h | depends on | upg |
|---|---|---|---|---|---|---|---|---|
| [DATA-21](feature-matrix.md#data-layer-feed-processing-queries-data) | Speaker list query | port | T0 | data | U | 1 | DATA-15 | - |
| [DATA-22](feature-matrix.md#data-layer-feed-processing-queries-data) | Sponsors by level passthrough | port | T0 | data | U | 1 | DATA-01 | - |
| [DATA-23](feature-matrix.md#data-layer-feed-processing-queries-data) | Static HTML content blocks | i->u | T0 | data | U | 1.5 | DATA-25 | E5 (27.1) |
| [DATA-24](feature-matrix.md#data-layer-feed-processing-queries-data) | Sprints, posters and job listings passthrough | port | T0 | data | U | 1 | DATA-01 | - |
| [DATA-25](feature-matrix.md#data-layer-feed-processing-queries-data) | Mixed-markup rendering and relative URL resolution | i->u | T0 | data | U | 2.5 | - | E5 (27.1) |
| [DATA-32](feature-matrix.md#data-layer-feed-processing-queries-data) | Room and venue floor-plan pin registry | adapt | T0 | data | U | 1 | X-APPCFG, P9 (2027 values only; 2026 content bundled now) | - |
| [NOTIF-04](feature-matrix.md#notifications-notif) | FCM topic subscriptions per category | i->u | T0 | core | U | 1 | X-APPCFG, NOTIF-03, P5 | E2 (T3), U5 |
| [NOTIF-08](feature-matrix.md#notifications-notif) | Foreground push shown as persistent top banner | i->u | T0 | core | U | 1.5 | NOTIF-04, X-SAFE | E2 (T3) |
| [STORE-07](feature-matrix.md#storage-store) | Tutorial-seen flag and post-tutorial routing | port | T0 | core | U | 0.5 | STORE-01 | - |
| [STORE-08](feature-matrix.md#storage-store) | Theme preference with legacy migration | adapt | T0 | core | U | 1.5 | STORE-01 | - |
| [STORE-10](feature-matrix.md#storage-store) | Notification preferences record | port | T0 | core | U | 0.5 | STORE-01 | - |
| [SHELL-02](feature-matrix.md#app-shell-and-navigation-shell) | First-run Welcome screen | port | T0 | shell | U | 0.5 | STORE-07 | - |
| [SHELL-03](feature-matrix.md#app-shell-and-navigation-shell) | Launch routing guard (Welcome vs Schedule vs Lead Scann… | port | T0 | shell | U | 1.5 | AUTH-02, STORE-07 | - |
| [SHELL-08](feature-matrix.md#app-shell-and-navigation-shell) | Rotating sponsor banner above the tab bar | port | T0 | shell | U | 1.5 | DATA-22, SHELL-05 | - |
| [SHELL-09](feature-matrix.md#app-shell-and-navigation-shell) | Sectioned side-menu drawer | port | T0 | shell | U | 2 | SHELL-04 | - |
| [SHELL-10](feature-matrix.md#app-shell-and-navigation-shell) | Collapsible drawer groups (Presentations, About PyCon U… | port | T0 | shell | U | 0.5 | SHELL-09 | - |
| [THEME-01](feature-matrix.md#theming-theme) | Four-mode in-app theme picker | adapt | T0 | shell | U | 2 | STORE-08, THEME-05 | - |
| [THEME-04](feature-matrix.md#theming-theme) | High-contrast light theme | port | T0 | shell | U | 1.5 | THEME-02 | - |
| [THEME-05](feature-matrix.md#theming-theme) | High-contrast dark theme | port | T0 | shell | U | 1.5 | THEME-03 | - |
| [THEME-06](feature-matrix.md#theming-theme) | High-contrast structural overrides | port | T0 | shell | U | 2 | THEME-04, THEME-05 | - |
| [THEME-09](feature-matrix.md#theming-theme) | Reduced-motion support | port | T0 | shell | U | 1.5 | X-STORES | - |
| [NOTIF-12](feature-matrix.md#notifications-notif) | 'Update required' banner for outdated native binaries | adapt | T0 | shell | U | 1 | X-APPCFG, X-BUILDINFO, P7 | - |
| [LIVE-02](feature-matrix.md#live-updates-live) | Global 'New version available' banner | adapt | T0 | shell | U | 2 | X-APPCFG, X-BUILDINFO, P7 | - |
| [LIVE-03](feature-matrix.md#live-updates-live) | Drawer 'Install Latest Update' card | adapt | T0 | shell | U | 1 | LIVE-02, SHELL-09 | - |
| [LIVE-04](feature-matrix.md#live-updates-live) | Pending-update dot on every hamburger button | adapt | T0 | shell | U | 1 | LIVE-02 | - |
| [SPON-11](feature-matrix.md#sponsors-and-job-listings-spon) | Rotating sponsor banner above the tab bar | port | T0 | shell | U | 0.5 | dup of SHELL-08 | - |
| [SCHED-09](feature-matrix.md#schedule-tracks-now-sched) | Track filter modal ('Filter Sessions') | port | T0 | sched | U | 1.5 | SCHED-10 | - |
| [SCHED-10](feature-matrix.md#schedule-tracks-now-sched) | Persisted excluded-tracks filter with default and funne… | port | T0 | sched | U | 1.5 | STORE-09 | - |
| [SCHED-11](feature-matrix.md#schedule-tracks-now-sched) | Swipe a schedule row to add/remove favorite | i->u | T0 | sched | U | 2.5 | STORE-02, SCHED-03 | E6 (27.1) |
| [SCHED-13](feature-matrix.md#schedule-tracks-now-sched) | Schedule pull-to-refresh | i->u | T0 | sched | U | 1 | DATA-03 | U1 |
| [SCHED-15](feature-matrix.md#schedule-tracks-now-sched) | 'Jump to Now' floating button | port | T0 | sched | U | 1.5 | SCHED-16 | - |
| [SCHED-16](feature-matrix.md#schedule-tracks-now-sched) | Auto-scroll to the current time slot | adapt | T0 | sched | U | 3.5 | spike S3, SCHED-03 | - |
| [SCHED-21](feature-matrix.md#schedule-tracks-now-sched) | Track pages: slug routing, branded header, 'New track!'… | port | T0 | sched | U | 1.5 | DATA-29 | - |
| [SCHED-22](feature-matrix.md#schedule-tracks-now-sched) | Track page: day-grouped session list with paging | adapt | T0 | sched | U | 3 | SCHED-21 | - |
| [SCHED-23](feature-matrix.md#schedule-tracks-now-sched) | Track page search | port | T0 | sched | U | 1.5 | SCHED-22 | - |
| [SCHED-24](feature-matrix.md#schedule-tracks-now-sched) | 'Favorite all <Track>' button | adapt | T0 | sched | U | 1.5 | SCHED-22, STORE-02 | - |
| [SESS-02](feature-matrix.md#session-detail-sess) | Room links from session detail | port | T0 | detail | U | 1.5 | SESS-12 | - |
| [SESS-04](feature-matrix.md#session-detail-sess) | Add session to device calendar (native prompt) | i->u | T0 | detail | U | 0.5 | SESS-05 | E4 (T3), U6 (T3) |
| [SESS-05](feature-matrix.md#session-detail-sess) | .ics calendar file export (share-sheet / web download f… | adapt | T0 | detail | U gfi | 1.5 | - | - |
| [SESS-06](feature-matrix.md#session-detail-sess) | HTML session description with in-app link interception | i->u | T0 | detail | U | 2 | DATA-25 | E5 (27.1) |
| [SESS-07](feature-matrix.md#session-detail-sess) | Speakers section linking to speaker detail | port | T0 | detail | U | 0.5 | SESS-12, DATA-15 | - |
| [SESS-09](feature-matrix.md#session-detail-sess) | Posters drill-down list | port | T0 | detail | U | 1.5 | DATA-07 | - |
| [SESS-10](feature-matrix.md#session-detail-sess) | Job Fair floor-plan card | port | T0 | detail | U | 1.5 | MAP-05 | - |
| [SESS-11](feature-matrix.md#session-detail-sess) | Open-space detail extras (image and site link) | port | T0 | detail | U | 0.5 | SESS-01 | - |
| [SPKR-01](feature-matrix.md#speakers-spkr) | Speaker directory list | adapt | T0 | detail | U | 1.5 | DATA-21 | - |
| [SPKR-02](feature-matrix.md#speakers-spkr) | Speaker search | port | T0 | detail | U gfi | 0.5 | SPKR-01 | - |
| [SPKR-03](feature-matrix.md#speakers-spkr) | Speaker detail page | port | T0 | detail | U | 1.5 | SESS-12 | - |
| [ROOM-01](feature-matrix.md#rooms-room) | Rooms list | port | T0 | detail | U | 0.5 | ROOM-06 | - |
| [ROOM-02](feature-matrix.md#rooms-room) | Room detail: sessions grouped by day | adapt | T0 | detail | U | 1.5 | ROOM-01 | - |
| [ROOM-03](feature-matrix.md#rooms-room) | Highlight and scroll to the originating session in room… | adapt | T0 | detail | U | 1.5 | ROOM-02, SCHED-16 | U9 (T2) |
| [EVT-01](feature-matrix.md#events-open-spaces-lightning-talks-sprints-evt) | Open Spaces card view | adapt | T0 | detail | U | 2.5 | DATA-05 | - |
| [EVT-02](feature-matrix.md#events-open-spaces-lightning-talks-sprints-evt) | 'Submit an Open Space' external sign-up | adapt | T0 | detail | U gfi | 1 | - | - |
| [EVT-03](feature-matrix.md#events-open-spaces-lightning-talks-sprints-evt) | Lightning Talks info page with sign-up links | adapt | T0 | detail | U | 1 | X-APPCFG, P9 (2027 values only; 2026 content bundled now) | - |
| [EVT-04](feature-matrix.md#events-open-spaces-lightning-talks-sprints-evt) | Session Types legend page | port | T0 | detail | U gfi | 0.5 | THEME-08 | - |
| [SPON-01](feature-matrix.md#sponsors-and-job-listings-spon) | Sponsors list grouped by level | port | T0 | detail | U | 1.5 | DATA-22 | - |
| [SPON-02](feature-matrix.md#sponsors-and-job-listings-spon) | Sponsor identity by name slug | port | T0 | detail | U | 1.5 | DATA-22 | - |
| [SPON-03](feature-matrix.md#sponsors-and-job-listings-spon) | Sponsor detail page | port | T0 | detail | U | 2 | SPON-02 | - |
| [SPON-05](feature-matrix.md#sponsors-and-job-listings-spon) | Open Positions card on sponsor detail | port | T0 | detail | U | 1.5 | SPON-03 | - |
| [INFO-12](feature-matrix.md#info-pages-info) | Info Desk location mini-map with pulsing pin | port | T0 | maps | U | 1.5 | DATA-33 | - |
| [INFO-13](feature-matrix.md#info-pages-info) | Full-screen pinch-zoom floor-plan modal | port | T0 | maps | U | 2 | MAP-05 | - |
| [DATA-33](feature-matrix.md#data-layer-feed-processing-queries-data) | Location-map card with pulsing pin (opens floor plan) | port | T0 | maps | U | 1.5 | DATA-32 | - |
| [ROOM-04](feature-matrix.md#rooms-room) | Room location map card with pulsing pin | port | T0 | maps | U | 2 | DATA-33 | - |
| [ROOM-05](feature-matrix.md#rooms-room) | Floor-plan zoom modal with anchored pin | port | T0 | maps | U | 2 | MAP-05 | - |
| [MAP-01](feature-matrix.md#maps-and-venue-map) | Conference Map page with view switcher and Expo Hall al… | port | T0 | maps | U | 2 | SHELL-04 | - |
| [MAP-02](feature-matrix.md#maps-and-venue-map) | Floor plan cards list | port | T0 | maps | U gfi | 0.5 | MAP-01 | - |
| [MAP-03](feature-matrix.md#maps-and-venue-map) | 3D venue tour (Concept3D) | adapt | T0 | maps | U | 1.5 | X-APPCFG, P9 (2027 values only; 2026 content bundled now) | - |
| [MAP-04](feature-matrix.md#maps-and-venue-map) | Job Fair zoomable plan segment | port | T0 | maps | U | 1.5 | MAP-05 | - |
| [MAP-05](feature-matrix.md#maps-and-venue-map) | Floor-plan modal with optional pulsing pin | port | T0 | maps | U | 2 | spike S9 | - |
| [MAP-06](feature-matrix.md#maps-and-venue-map) | Location map card (thumbnail with pin) opening the floo… | port | T0 | maps | U | 1.5 | MAP-07 | - |
| [MAP-07](feature-matrix.md#maps-and-venue-map) | Room to floor-plan pin lookup (ROOM_LOCATIONS) | adapt | T0 | maps | U | 1.5 | DATA-32, P9 (2027 values only; 2026 content bundled now) | - |
| [MAP-11](feature-matrix.md#maps-and-venue-map) | Get Directions to the Pine Ave entrance | port | T0 | maps | U gfi | 0.5 | - | - |
| [INFO-01](feature-matrix.md#info-pages-info) | Indigo hero page scaffold with scroll-revealed title | port | T0 | info | CC | 2 | THEME-10 | - |
| [INFO-02](feature-matrix.md#info-pages-info) | About PyCon US page | adapt | T0 | info | CC | 1.5 | INFO-01, DATA-23 | - |
| [INFO-03](feature-matrix.md#info-pages-info) | Developer Info panel (version, build, OTA, API host) | i->u | T0 | info | CC | 1 | X-BUILDINFO, X-CAPS | U4 |
| [INFO-05](feature-matrix.md#info-pages-info) | Feed-driven HTML content blocks with blocking loader | i->u | T0 | info | CC | 2.5 | DATA-25 | E5 (27.1) |
| [INFO-06](feature-matrix.md#info-pages-info) | About the PSF page | port | T0 | info | CC gfi | 0.5 | INFO-01 | - |
| [INFO-07](feature-matrix.md#info-pages-info) | Code of Conduct page with Report a Concern actions | port | T0 | info | CC | 0.5 | INFO-01, X-APPCFG, P9 (2027 values only; 2026 content bundled now) | - |
| [INFO-08](feature-matrix.md#info-pages-info) | Wi-Fi credentials with Copy Password | adapt | T0 | info | CC | 1 | X-APPCFG, P9 (2027 values only; 2026 content bundled now) | - |
| [INFO-09](feature-matrix.md#info-pages-info) | Wi-Fi sponsor credit card | port | T0 | info | CC gfi | 0.5 | INFO-08, DATA-22 | - |
| [INFO-10](feature-matrix.md#info-pages-info) | Social Media page | port | T0 | info | CC gfi | 0.5 | INFO-01 | - |
| [INFO-11](feature-matrix.md#info-pages-info) | Help & Safety page | port | T0 | info | CC gfi | 0.5 | INFO-01, INFO-12 | - |
| [NOTIF-01](feature-matrix.md#notifications-notif) | Notification Settings page with six category toggles | port | T0 | info | CC | 2 | STORE-10 | - |
| [NOTIF-02](feature-matrix.md#notifications-notif) | Master 'All notifications' toggle with mixed state | port | T0 | info | CC gfi | 0.5 | NOTIF-01 | - |
| [NOTIF-03](feature-matrix.md#notifications-notif) | Notification preference storage (opt-in by default) | port | T0 | info | CC | 0.5 | STORE-10 | - |
| [NOTIF-05](feature-matrix.md#notifications-notif) | Local reminder notifications at fixed conference times | i->u | T0 | info | CC | 3 | X-APPCFG, SESS-05 | E3 (T3), U7 (T3) |
| [SHELL-12](feature-matrix.md#app-shell-and-navigation-shell) | Login-aware account section of the drawer | port | T0-P | auth | U | 0.5 | STORE-04, SHELL-09 | - |
| [SHELL-13](feature-matrix.md#app-shell-and-navigation-shell) | Logout from the drawer (no confirmation) | adapt | T0-P | auth | U | 1 | AUTH-11 | - |
| [SHELL-15](feature-matrix.md#app-shell-and-navigation-shell) | Login-state and staff-capability sync | adapt | T0-P | auth | U | 1.5 | STORE-04, AUTH-04 | - |
| [NATIVE-07](feature-matrix.md#native-platform-native) | Password autofill shared with us.pycon.org | i->u | T0-P | auth | U | 1 | AUTH-01 | U5, U8 (T3) |
| [STORE-03](feature-matrix.md#storage-store) | Signed-in identity and API credentials storage | adapt | T0-P | auth | U | 1.5 | STORE-01 | - |
| [STORE-04](feature-matrix.md#storage-store) | Login/logout lifecycle and app-wide auth events | adapt | T0-P | auth | U | 1.5 | STORE-03 | - |
| [STORE-05](feature-matrix.md#storage-store) | Role / entitlement feature flags | port | T0-P | auth | U | 1 | STORE-01 | - |
| [API-01](feature-matrix.md#signed-api-client-api) | sha1 request signing for the PyCon API | port | T0-P | auth | U | 1 | P3 | - |
| [API-02](feature-matrix.md#signed-api-client-api) | Email/password authentication call | port | T0-P | auth | U | 1 | API-12, P3 | - |
| [API-03](feature-matrix.md#signed-api-client-api) | Feature-flag refresh (check_features) | adapt | T0-P | auth | U | 1 | API-01, P3 | - |
| [API-04](feature-matrix.md#signed-api-client-api) | Favourites cloud sync (mobile_state) | adapt | T0-P | auth | U | 1.5 | API-01, X-OUTBOX, P3, P6 | - |
| [API-12](feature-matrix.md#signed-api-client-api) | Per-endpoint timeouts and error conventions | adapt | T0-P | auth | U | 1 | X-DEVSERVER | - |
| [SCHED-12](feature-matrix.md#schedule-tracks-now-sched) | Favorites persistence and account sync | adapt | T0-P | auth | U | 0.5 | dup of API-04, P3 | - |
| [AUTH-01](feature-matrix.md#authentication-and-account-auth) | Login form | adapt | T0-P | auth | U | 1.5 | API-02, P3 | - |
| [AUTH-02](feature-matrix.md#authentication-and-account-auth) | Auth session persistence | adapt | T0-P | auth | U | 1.5 | STORE-03 | - |
| [AUTH-03](feature-matrix.md#authentication-and-account-auth) | sha1 request signing for the PyCon API | port | T0-P | auth | U | 0.5 | dup of API-01 | - |
| [AUTH-04](feature-matrix.md#authentication-and-account-auth) | Role feature flags and their refresh | adapt | T0-P | auth | U | 1.5 | API-03, P3 | - |
| [AUTH-07](feature-matrix.md#authentication-and-account-auth) | Login/logout state propagation | adapt | T0-P | auth | U | 0.5 | dup of STORE-04 | - |
| [AUTH-09](feature-matrix.md#authentication-and-account-auth) | Account page with Report an Issue links | port | T0-P | auth | U | 0.5 | AUTH-02 | - |
| [AUTH-10](feature-matrix.md#authentication-and-account-auth) | Speaker Discord in-app browser link | port | T0-P | auth | U gfi | 0.5 | AUTH-09 | - |
| [AUTH-11](feature-matrix.md#authentication-and-account-auth) | Logout | adapt | T0-P | auth | U | 1.5 | STORE-04, X-OUTBOX | - |
| [AUTH-12](feature-matrix.md#authentication-and-account-auth) | Favorites server sync tied to login | adapt | T0-P | auth | U | 1.5 | API-04, P3, P6 | - |
| [NATIVE-01](feature-matrix.md#native-platform-native) | App identity and store-listing continuity | port | T0 | rel | U | 1.5 | spike S1, P4 | - |
| [NATIVE-03](feature-matrix.md#native-platform-native) | App icons and brand artwork | port | T0 | rel | U | 1 | - | - |

### 4.3 M3 Staff beta + native gates (02-01 → **03-05**)

**Exit:** T1 on staging; U1/U4/U5 released (point release by 02-26); **G3 02-12**; **Badge Day 1 02-24**; **G-Staff 02-26**; last pin change **03-05**. T2 may finish by freeze. See [PLAN 7.4](../PLAN.md#74-gono-go-checkpoints). **This backlog:** 80 ids; committed 87.5 h, T2 82 h, T3 110 h.

Non-feature tasks:

| task | what | ws | owner | h | depends on | due |
|---|---|---|---|---|---|---|
| X-UIFLOWS | ~25 UI flows with `flet.testing` (`FletTestApp`, `Tester`), PR smoke + nightly | qa | U | 9 | X-TRACE | 02-26 |
| X-FALLBACK | Fallback-parity suite: every capability faked on and off; nightly `flet@main` build | qa | U | 4 | X-CAPS | 02-19 |
| X-BD1 | Badge Day 1 (02-24, staging): script, devices, printed badges, server audit vs outbox (criterion S4) | field | U+PSF-E | 8 | P3, P10, LEAD-07, DOOR-07 | 02-24 |
| X-POINTREL | 1.1.x point release carrying U1/U4/U5 (+ U6-U8 if pursued), OD-19. Tracking only: Flet release duty, outside the 220 h | ups | FT+U | 0 | U1, U4, U5 | 02-26 |
| U3 | U3 `InteractiveViewer.set_transform()/zoom_to_rect()` | t2 | U | 10 | - | 02-12 |
| U9 | U9 `ft.use_route_search()` | t2 | U | 3 | - | 02-12 |
| U15 | U15 non-fatal handler/effect errors + Python-side error hook | t2 | U | 8 | - | 02-12 |
| E2 | E2 `flet-firebase` (firebase_core 4.15.0, firebase_messaging 16.7.0 [+ the separate `flet-firebase-analytics` wheel, firebase_analytics 12.6.0, only if OD-3, D-111]) + `FirebasePush` provider | t3 | U | 50 | spike S8, U5, P5 | G3 02-12; release 03-05 |
| E3 | E3 `zoned_schedule`/`cancel` PR to flet-dev/flet#6948 (flutter_local_notifications 22.3.1 + timezone 0.11.1) + `ScheduledReminders` provider | t3 | FT+U | 40 | #6948 v1 (FT, 01-15), U7, the D-113 receivers | G3 02-12; release 03-05 |
| E4 | E4 `flet-add-to-calendar` (add_2_calendar 3.1.1) + `NativeCalendar` provider | t3 | CC+U | 20 | U6 | G3 02-12; release 03-05 |

| id | feature | disp | tier | ws | owner | h | depends on | upg |
|---|---|---|---|---|---|---|---|---|
| [INFO-04](feature-matrix.md#info-pages-info) | Share encrypted debug dump with PyCon staff | adapt | T0 | core | U | 1.5 | DEV-02, X-SAFE, P6 | - |
| [DEV-01](feature-matrix.md#developer-tools-dev) | Dev Tools page gating and Environment card | adapt | T1 | core | U | 1 | SHELL-04 | - |
| [DEV-02](feature-matrix.md#developer-tools-dev) | Storage stats and dump | adapt | T1 | core | U | 1 | DEV-01, STORE-01 | - |
| [DEV-03](feature-matrix.md#developer-tools-dev) | Clear scan data | adapt | T1 | core | U | 1 | DEV-01, API-10 | - |
| [DEV-04](feature-matrix.md#developer-tools-dev) | Invalidate schedule cache | port | T1 | core | U | 0.5 | DEV-01, DATA-02 | - |
| [DEV-05](feature-matrix.md#developer-tools-dev) | Nuke all storage and reload | port | T1 | core | U | 1 | DEV-01 | - |
| [DEV-06](feature-matrix.md#developer-tools-dev) | Per-category test notifications (fire in 5 s) | i->u | T1 | core | U | 0.5 | DEV-01, NOTIF-05 | E3 (T3) |
| [NOTIF-06](feature-matrix.md#notifications-notif) | Push permission prompt and FCM token registration | i->u | T0 | info | CC | 0.5 | NOTIF-01 | E2 (T3) |
| [NOTIF-07](feature-matrix.md#notifications-notif) | Local-notification permission gate (no re-prompt after… | i->u | T0 | info | CC | 1 | NOTIF-05 | E2 (T3), E3 (T3) |
| [NOTIF-09](feature-matrix.md#notifications-notif) | Notification analytics events and user properties | i->u | T0 | info | CC | 0.5 | X-CAPS | E2 (T3) |
| [NOTIF-10](feature-matrix.md#notifications-notif) | Permission hint with iOS 'Open PyCon US Settings' | port | T0 | info | CC gfi | 0.5 | NOTIF-01 | - |
| [NOTIF-11](feature-matrix.md#notifications-notif) | FCM token diagnostics card | i->u | T0 | info | CC | 0.5 | INFO-03 | E2 (T3) |
| [SHELL-06](feature-matrix.md#app-shell-and-navigation-shell) | Role-dependent Scanner tab | port | T1 | staff | U | 1 | AUTH-05, SHELL-05 | - |
| [SHELL-07](feature-matrix.md#app-shell-and-navigation-shell) | Staff Tools bottom sheet | adapt | T1 | staff | U | 1 | AUTH-05 | - |
| [SHELL-11](feature-matrix.md#app-shell-and-navigation-shell) | Role-gated 'Apps' section in the drawer | adapt | T1 | staff | U | 1 | AUTH-05, SHELL-09 | - |
| [DATA-31](feature-matrix.md#data-layer-feed-processing-queries-data) | Relative 'time ago' formatting (dateAgo pipe) | port | T1 | staff | U gfi | 0.5 | - | - |
| [STORE-06](feature-matrix.md#storage-store) | Lead-scanner consent flag | port | T1 | staff | U | 0.5 | STORE-01 | - |
| [STORE-11](feature-matrix.md#storage-store) | Staff sponsor selection (scan on behalf of a sponsor) | adapt | T1 | staff | U | 1 | STORE-01, API-09 | - |
| [STORE-12](feature-matrix.md#storage-store) | Door-check redemption offline records | adapt | T1 | staff | U | 0.5 | dup of DOOR-07 | - |
| [STORE-13](feature-matrix.md#storage-store) | Storage enumeration, prefix sweeps, wipe and encrypted… | adapt | T1 | staff | U | 1.5 | STORE-01, API-10 | - |
| [API-05](feature-matrix.md#signed-api-client-api) | Check-in product and attendee inventory fetch | port | T1 | staff | U | 1 | API-01, P3 | - |
| [API-06](feature-matrix.md#signed-api-client-api) | Attendee product lookup (fetch_products) | port | T1 | staff | U | 1 | API-01, P3 | - |
| [API-07](feature-matrix.md#signed-api-client-api) | Product redemption POST | port | T1 | staff | U | 1 | API-01, P3 | - |
| [API-08](feature-matrix.md#signed-api-client-api) | Code-of-conduct (mask violation) endpoints | port | T1 | staff | U | 1 | API-01, P3 | - |
| [API-09](feature-matrix.md#signed-api-client-api) | Lead-retrieval sponsor list for staff | port | T1 | staff | U | 0.5 | API-01, P3 | - |
| [API-10](feature-matrix.md#signed-api-client-api) | Offline queue for lead scans | adapt | T1 | staff | U | 2.5 | API-12, X-OUTBOX | - |
| [API-11](feature-matrix.md#signed-api-client-api) | Lead notes local store and sync | adapt | T1 | staff | U | 1 | API-10 | - |
| [AUTH-05](feature-matrix.md#authentication-and-account-auth) | Feature-gated staff entry points (menu Apps section, Sc… | port | T1 | staff | U | 1 | AUTH-04 | - |
| [AUTH-06](feature-matrix.md#authentication-and-account-auth) | Staff Tools bottom sheet | adapt | T1 | staff | U | 0.5 | dup of SHELL-07 | - |
| [AUTH-08](feature-matrix.md#authentication-and-account-auth) | Users with lead retrieval land on the Lead Scanner (pos… | port | T1 | staff | U | 1 | SHELL-03, AUTH-04 | - |
| [LEAD-01](feature-matrix.md#lead-retrieval-and-shared-scanning-lead) | Badge QR scanner surface (shared by the four staff tool… | i->u | T1 | staff | U | 3 | - | E1 |
| [LEAD-02](feature-matrix.md#lead-retrieval-and-shared-scanning-lead) | Camera permission card (shared) | port | T1 | staff | U | 1 | - | - |
| [LEAD-03](feature-matrix.md#lead-retrieval-and-shared-scanning-lead) | Badge QR payload parsing rules (shared) | port | T1 | staff | U | 0.5 | P3 | - |
| [LEAD-04](feature-matrix.md#lead-retrieval-and-shared-scanning-lead) | Lead Scanner consent gate | port | T1 | staff | U | 1 | STORE-06 | - |
| [LEAD-05](feature-matrix.md#lead-retrieval-and-shared-scanning-lead) | Staff 'scan on behalf of' sponsor selector | adapt | T1 | staff | U | 1.5 | API-09, STORE-11, P3 | - |
| [LEAD-06](feature-matrix.md#lead-retrieval-and-shared-scanning-lead) | Staff sponsor banner and sponsor filter | port | T1 | staff | U | 1 | LEAD-05 | - |
| [LEAD-07](feature-matrix.md#lead-retrieval-and-shared-scanning-lead) | Offline lead capture queue (pending -> captured/failed) | adapt | T1 | staff | U | 2.5 | API-10, LEAD-01, LEAD-03 | - |
| [LEAD-08](feature-matrix.md#lead-retrieval-and-shared-scanning-lead) | Lead scan list with status | port | T1 | staff | U | 1.5 | LEAD-07 | - |
| [LEAD-09](feature-matrix.md#lead-retrieval-and-shared-scanning-lead) | Last-scan footer bar with status polling | adapt | T1 | staff | U | 1.5 | LEAD-07 | - |
| [LEAD-10](feature-matrix.md#lead-retrieval-and-shared-scanning-lead) | Structured lead notes modal | port | T1 | staff | U | 1 | API-11 | - |
| [LEAD-11](feature-matrix.md#lead-retrieval-and-shared-scanning-lead) | Offline note sync | adapt | T1 | staff | U | 1 | API-11 | - |
| [LEAD-12](feature-matrix.md#lead-retrieval-and-shared-scanning-lead) | 60 s background sync loop (lead scans and notes) | adapt | T1 | staff | U | 1 | API-10 | - |
| [LEAD-13](feature-matrix.md#lead-retrieval-and-shared-scanning-lead) | Pull-to-refresh re-sync of pending scans | i->u | T1 | staff | U | 0.5 | LEAD-12 | U1 |
| [LEAD-14](feature-matrix.md#lead-retrieval-and-shared-scanning-lead) | Dev-only Simulate Scan | adapt | T1 | staff | U | 0.5 | LEAD-01 | - |
| [DOOR-01](feature-matrix.md#door-check-door) | Session-category chips (non-swag), single-select | port | T1 | staff | U | 1 | API-05, P3 | - |
| [DOOR-02](feature-matrix.md#door-check-door) | Session list: chronological sort, search, 'All sessions… | port | T1 | staff | U | 1 | DOOR-01 | - |
| [DOOR-03](feature-matrix.md#door-check-door) | Attendee inventory preload per session | adapt | T1 | staff | U | 1.5 | API-05, P3 | - |
| [DOOR-04](feature-matrix.md#door-check-door) | Admission decision per badge scan | i->u | T1 | staff | U | 2.5 | LEAD-03, DOOR-03, API-06, P3 | E1 |
| [DOOR-05](feature-matrix.md#door-check-door) | Check-in result card with dietary/allergy chips | port | T1 | staff | U | 1 | DOOR-04 | - |
| [DOOR-06](feature-matrix.md#door-check-door) | Live session headcount | port | T1 | staff | U | 1 | DOOR-04 | - |
| [DOOR-07](feature-matrix.md#door-check-door) | Offline check-in queue with 60 s retry | adapt | T1 | staff | U | 2.5 | API-10, DOOR-04, P3 | - |
| [SHIRT-01](feature-matrix.md#swag-pickup-shirt) | Swag category multi-select | port | T1 | staff | U | 0.5 | DOOR-01 | - |
| [SHIRT-02](feature-matrix.md#swag-pickup-shirt) | Scan a badge to fetch redeemable products | i->u | T1 | staff | U | 1.5 | LEAD-03, API-06, P3 | E1 |
| [SHIRT-03](feature-matrix.md#swag-pickup-shirt) | Redeem Products modal | port | T1 | staff | U | 1 | SHIRT-02 | - |
| [SHIRT-04](feature-matrix.md#swag-pickup-shirt) | Redeem submission with outcome toasts (online only) | port | T1 | staff | U | 1 | API-07, SHIRT-03, P3 | - |
| [MASK-01](feature-matrix.md#code-of-conduct-incident-capture-mask) | Attendee directory load | port | T1 | staff | U | 1 | API-08, P3 | - |
| [MASK-02](feature-matrix.md#code-of-conduct-incident-capture-mask) | Attendee name search | port | T1 | staff | U | 1 | MASK-01 | - |
| [MASK-03](feature-matrix.md#code-of-conduct-incident-capture-mask) | Record an incident by name with notes (force) | port | T1 | staff | U | 1 | MASK-01 | - |
| [MASK-04](feature-matrix.md#code-of-conduct-incident-capture-mask) | Badge-scan incident capture (one request per detected f… | i->u | T1 | staff | U | 1.5 | LEAD-03, API-08, P6 | E1 |
| [MASK-05](feature-matrix.md#code-of-conduct-incident-capture-mask) | Incident result card | port | T1 | staff | U | 1 | MASK-04 | - |
| [NATIVE-04](feature-matrix.md#native-platform-native) | Firebase and APNs push wiring | i->u | T0 | rel | U | 0.5 | P5 | E2 (T3), U5 |
| [NATIVE-06](feature-matrix.md#native-platform-native) | Permission declarations and usage strings | port | T0 | rel | U | 1.5 | LEAD-02 | - |
| [SHELL-14](feature-matrix.md#app-shell-and-navigation-shell) | Responsive split pane (permanent menu at >= 992 px) | adapt | T2 | t2 | CC | 5.5 | SHELL-09 | - |
| [EVT-05](feature-matrix.md#events-open-spaces-lightning-talks-sprints-evt) | Sprints project cards | port | T2 | t2 | CC | 4 | DATA-24 | - |
| [EVT-06](feature-matrix.md#events-open-spaces-lightning-talks-sprints-evt) | Sprints search (all words must match) | adapt | T2 | t2 | CC gfi | 2 | EVT-05 | - |
| [EVT-07](feature-matrix.md#events-open-spaces-lightning-talks-sprints-evt) | Sprints pull-to-refresh with full feed-cache invalidati… | i->u | T2 | t2 | CC | 1 | EVT-05 | U1 |
| [EVT-08](feature-matrix.md#events-open-spaces-lightning-talks-sprints-evt) | Sprints external links (Visit Sprints Page, Submit a Sp… | adapt | T2 | t2 | CC | 1 | EVT-05 | - |
| [SPON-04](feature-matrix.md#sponsors-and-job-listings-spon) | Booth chip deep-links to the Expo Hall map | port | T2 | t2 | U | 2 | EXPO-03 | U9 (T2) |
| [SPON-06](feature-matrix.md#sponsors-and-job-listings-spon) | Job Listings page | port | T2 | t2 | CC | 4 | DATA-24, SPON-09 | - |
| [SPON-07](feature-matrix.md#sponsors-and-job-listings-spon) | Job listings search | adapt | T2 | t2 | CC gfi | 1.5 | SPON-06 | - |
| [SPON-08](feature-matrix.md#sponsors-and-job-listings-spon) | Job listings pull-to-refresh with feed cache invalidati… | i->u | T2 | t2 | CC | 1 | SPON-06 | U1 |
| [SPON-09](feature-matrix.md#sponsors-and-job-listings-spon) | HTML job description to role rows parser (parseRoles/sh… | adapt | T2 | t2 | CC gfi | 3.5 | - | - |
| [SPON-10](feature-matrix.md#sponsors-and-job-listings-spon) | Job Fair floor-plan entry card | port | T2 | t2 | CC | 1 | MAP-05 | - |
| [EXPO-01](feature-matrix.md#expo-hall-expo) | Zoomable expo floor plan with booth hit areas | port | T2 | t2 | U | 11 | MAP-05 | - |
| [EXPO-02](feature-matrix.md#expo-hall-expo) | Booth geometry table and sponsor-feed reconciliation | adapt | T2 | t2 | U | 4 | EXPO-01, X-APPCFG, P9 (2027 booth geometry only; 2026 table bundled now) | - |
| [EXPO-03](feature-matrix.md#expo-hall-expo) | Tap a booth to highlight it and show a bottom popup | port | T2 | t2 | U | 5 | EXPO-01 | - |
| [EXPO-04](feature-matrix.md#expo-hall-expo) | Booth search overlay | port | T2 | t2 | U | 3 | EXPO-03 | - |
| [EXPO-05](feature-matrix.md#expo-hall-expo) | Deep-link zoom-to-booth (?booth=N) | i->u | T2 | t2 | U | 3 | EXPO-03 | U3 (T2) |
| [MAP-09](feature-matrix.md#maps-and-venue-map) | Venue & Hours page (CMS HTML sections with interleaved… | i->u | T2 | t2 | CC | 7 | DATA-25, MAP-06 | E5 (27.1) |
| [MAP-10](feature-matrix.md#maps-and-venue-map) | Quiet Room 'Sponsored by' card | adapt | T2 | t2 | CC | 1.5 | MAP-09, P9 (2027 values only; 2026 content bundled now) | - |

### 4.4 M4 2027 data + freeze (03-06 → **03-31**)

**Exit:** `/2027/` feed (~03-13, UNCONFIRMED) parsed; 2027 app-content by 03-20 (P9); PWA on PSF hosting; a11y audit; a co-maintainer cuts the `v27.0.0-alpha.5` freeze build (03-30, D-126); **G4** (every committed id green, contract nightly green 7 days). See [PLAN 7.4](../PLAN.md#74-gono-go-checkpoints). **This backlog:** 5 ids; committed 23.5 h, T2 10 h.

Non-feature tasks:

| task | what | ws | owner | h | depends on | due |
|---|---|---|---|---|---|---|
| X-A11Y | Scripted VoiceOver + TalkBack pass over 12 flows (U 2 h + CC 2 h) | qa | U+CC | 4 | X-UIFLOWS | 03-27 |
| X-CCAUDIT | Independent CC accessibility audit + fixes list | qa | CC | 4 | X-A11Y | 03-31 |
| X-COMAINT | Co-maintainer onboarding: they cut the `v27.0.0-alpha.5` freeze build (03-30) before 03-31 (criterion S12, D-126) | field | U | 4 | X-RELEASE | 03-31 |
| X-STOREFORMS | Support P11: review notes (camera, Guideline 2.1), demo-account script, Data Safety / App Privacy drafts for PSF | rel | U | 3 | NATIVE-05 (config part), NATIVE-06, P3 (review account roles) | 03-26 (drafts to PSF) |

| id | feature | disp | tier | ws | owner | h | depends on | upg |
|---|---|---|---|---|---|---|---|---|
| [THEME-07](feature-matrix.md#theming-theme) | Keyboard-focus affordances (skip link, focus rings) | adapt | T0 | shell | U | 2 | SHELL-09 | - |
| [SESS-08](feature-matrix.md#session-detail-sess) | Keynote and panel enrichment (hard-coded abstracts and… | adapt | T0 | detail | U | 3 | X-APPCFG, P9 | - |
| [SPKR-04](feature-matrix.md#speakers-spkr) | Keynote Speakers page | adapt | T0 | detail | U | 1.5 | X-APPCFG, P9 | - |
| [NATIVE-05](feature-matrix.md#native-platform-native) | Analytics privacy configuration | adapt | T0 | rel | U | 2 | P11 (forms only; `AD_ID` config part by 03-26 for X-STOREFORMS) | - |
| [NATIVE-09](feature-matrix.md#native-platform-native) | PWA build: boot shell, manifest, service worker, hosting | i->u | T2 | t2 | U+PSF-I | 10 | DATA-01, spike S2, P7 | U11 (post) |

### 4.5 M5 Beta + release (04-01 → **04-30**)

**Exit:** Betas 04-01 → 04-14; RC1 **04-07**; Badge Day 2 **04-09**; **G5 04-14**; submit **04-16** (fallback 04-23); hotfix rehearsal 04-20 → 04-24; release **04-27** (latest 04-30), the exact beta binary. See [PLAN 9.3](../PLAN.md#93-release-train). **This backlog:** 1 id; committed 55.5 h.

Non-feature tasks:

| task | what | ws | owner | h | depends on | due |
|---|---|---|---|---|---|---|
| X-HOTFIX | Hotfix rehearsal on newest Xcode + runner image: tag -> both stores <= 2 h (criterion S11) | rel | U+PSF-I | 4 | X-RELEASE | 04-24 |
| X-DASH | Conference-week dashboard: crash-free, adoption, outbox failures, banner delivery; runbook links | rel | U | 3.5 | X-SAFE | 04-30 |
| X-BD2 | Badge Day 2 (04-09, RC1): >= 500 scans, 30 min airplane mode, two devices on one attendee | field | U+PSF-E | 8 | X-BD1, P10 | 04-09 |
| X-BETA | Closed + public beta 04-01 -> 04-14 (TestFlight link, Play open testing), triage, RC1 04-07 | field | U | 10 | X-SIGNED | 04-14 |
| X-FIX | Parity/beta bug-fix buffer (P0/P1 from differential, goldens, Badge Days, beta); starts in M4, counted in M5 by its due date (section 12) | field | U | 15 | - | 04-14 |
| X-SPRINTFORM | Sprint form "PyCon US app + Flet extensions" | talk | U | 0.5 | - | 04-15 |
| X-SLIDES | Slides v1 + DEMO-build script + 20 s fallback clips | talk | U | 8 | LEAD-14 | 04-20 |
| X-POSTER | Poster panels (architecture, capability matrix) and print | talk | U | 4 | X-CFP | 04-30 |
| X-BLOG | Flet + PSF blog posts | talk | U | 1 | - | 04-27..30 |

| id | feature | disp | tier | ws | owner | h | depends on | upg |
|---|---|---|---|---|---|---|---|---|
| [NATIVE-10](feature-matrix.md#native-platform-native) | Upgrade continuity from Ionic Storage | adapt | T0 | auth | U | 1.5 | AUTH-12, P13? | - |

### 4.6 Dropped (no milestone)

| id | feature | disp | tier | ws | owner | h | depends on | upg |
|---|---|---|---|---|---|---|---|---|
| [LIVE-01](feature-matrix.md#live-updates-live) | Appflow OTA live updates (silent check, manual apply) | drop | - | shell | - | 0 | - | - |
| [DATA-27](feature-matrix.md#data-layer-feed-processing-queries-data) | Shared-session (slot.sessions) expansion branch | drop | - | data | U | 0.5 | X-CONTRACT | - |

LIVE-01 is replaced by server-driven content (PLAN 9.4) and needs no work. DATA-27 keeps 0.5 h for the contract test that fails if `slot.sessions` ever appears (D-08).

---

## 5. Upstream items (E1-E6, U1-U15)

Gap register: [PLAN 6.2](../PLAN.md#62-gap-register). Policy: released Flet only, exact pins, last pin change **03-05** (D-18, D-20); standalone `flet-dev` repos for E1/E2/E4 (D-23). Every row below ships its interim regardless.

| item | serves ids | interim (always ships) | owner | h | bucket | due / gate | `Caps` key |
|---|---|---|---|---|---|---|---|
| E1 | LEAD-01, DOOR-04, SHIRT-02, MASK-04 | `ManualEntryScanner` (full `code:validator`, HID wedge) | U | 35 | committed | v0.1 on device 01-10; PyPI 0.2 02-19 (criterion S10) | `scanner` |
| E2 | NOTIF-04/06/07/08/09/11, NATIVE-04 | `BannerPoller` (app-config banners) | U | 50 | T3 | spike S8 11-30; P5 01-31; **G3 02-12**; release 03-05 or 27.1 | `push`, `analytics` |
| E3 | NOTIF-05, NOTIF-07, DEV-06 | in-app reminder banners + `.ics` `VALARM` | FT (v1), U | 40 | T3 | #6948 v1 PR merged and released by 01-15 (UNCONFIRMED); G3; 03-05 or 27.1 | `local_notifications` |
| E4 | SESS-04 | `.ics` share (SESS-05) | CC/U | 20 | T3 | G3; 03-05 or 27.1 | `calendar` |
| E5 | INFO-05, DATA-23, DATA-25, SESS-06, MAP-09 | `core/html_md.py` -> `ft.Markdown` | CC | - | 27.1 | sprint 05-17/18 | `html` |
| E6 | SCHED-11 | `ft.Dismissible` + `confirm_dismiss` + long press | CC | - | 27.1 | sprint 05-17/18 | `slidable` |
| U1 | SCHED-13, SCHED-26, EVT-07, SPON-08, LEAD-13 | AppBar refresh `IconButton` + `ProgressBar` (`Refreshable`) | U | 8 | committed | merged 01-15; released by 02-26 | `refresh_indicator` |
| U2 | SCHED-02 | non-sticky dividers | FT/CC | - | 27.1 | 27.1 | `sticky_headers` |
| U3 | EXPO-05 | `reset()` -> `zoom()` -> `pan()` | U | 10 | T2 | 02-12 | `iv_set_transform` |
| U4 | INFO-03 | `build_info.py` | U | 4 | committed | 01-15 | `app_info` |
| U5 | NOTIF-04, NATIVE-04, NATIVE-07 | push off; autofill heuristics | U | 8 | committed | merged 01-31 | config |
| U6 | SESS-04 | E4 interim | U | 6 | T3 | 01-31, only if E4 | config |
| U7 | NOTIF-05 | E3 interim | U | 6 | T3 | 01-31, only if E3 | config |
| U8 | NATIVE-07 | autofill heuristics | U | 5 | T3 | 01-31, only if autofill | config |
| U9 | ROOM-03, SPON-04 | `use_query()` over `use_route_location()` + `page.route` | U | 3 | T2 | 02-12 | probe |
| U10 | SCHED (second toolbar row) | first row of `View.controls` | - | - | post | post-conference | - |
| U11 | NATIVE-09 | online-only PWA | - | - | post | post-conference | - |
| U12 | NATIVE-02 | - | U | contingency | conditional | 2026-12-15, only if spike S10 finds a pod > iOS 15 | build |
| U13 | NATIVE-01 | - | U | contingency | conditional | 2026-12-15, only if spike S5 reports ITMS-91053 | build |
| U14 | deep links | custom scheme `pyconus://app` | - | - | post | post-conference | - |
| U15 | all handlers | `@safe` (X-SAFE) | U | 8 | T2 | 02-12 | probe |

U1 + U4 + U5 = the 20 h of PLAN 7.1. The Flet 1.1.0 release (X-FLET11, on the iOS critical path) and the 1.1.x point release by **02-26** (X-POINTREL) are tracked as 0 h tasks: they are release duty, outside the 220 h. If U12/U13 trigger, they draw on the 15 % contingency.

Upgrade procedure (no screen code changes, PLAN 6.2): release upstream → bump the exact pin → add to `[tool.flet.android|ios].dependencies` → CI writes the manifest, `Caps` lights the key; the fallback-parity suite already covers both states.

---

## 6. T3 gated items (decided at G3, 2027-02-12)

Criteria are D-29 / [PLAN 7.4](../PLAN.md#74-gono-go-checkpoints). Each item is judged alone; a "no" keeps its interim and moves it to 27.1 (06-30). Push is **not** on the never-cut list (D-06).

| T3 item | tasks (h) | ids whose upgrade half it is | go if (G3) | prep due |
|---|---|---|---|---|
| Push | E2 (50) | NOTIF-04, NOTIF-06, NOTIF-07, NOTIF-08, NOTIF-09 (analytics only if OD-3), NOTIF-11, NATIVE-04 | topic round-trip on iOS + Android with the PSF config; U5 merged; burn-down within 5 %; releasable by 03-05 | spike S8 11-30, P5 01-31 |
| Scheduled reminders | E3 (40) + U7 (6) | NOTIF-05, NOTIF-07, DEV-06 | #6948 v1 merged and released by 01-15 (UNCONFIRMED) + scheduling PR (with the D-113 receivers; a release build fires a scheduled notification after a reboot) + U7 merged | #6948 v1 01-15 (FT) |
| Native calendar | E4 (20) + U6 (6) | SESS-04 | U6 merged, prompt works on both OSes | 01-31 |
| Autofill entitlement | U8 (5) (+ U5, committed) | NATIVE-07 | U5 + U8 merged; `webcredentials:us.pycon.org` accepted by PSF | 01-31 |

Total 127 h (D-112), almost all upstream (Flet-work time). Release builds add `POST_NOTIFICATIONS`, `SCHEDULE_EXACT_ALARM`, `UIBackgroundModes` and the entitlement **only** in the release that ships the matching item (D-89).

---

## 7. T2 should-haves and the cut order

T2 = 19 ids (71 h) + U3/U9/U15 (21 h) = 92 h. Ships if green at freeze (03-31). **Cut order** (D-05, amended by D-110), applied top first when the burn-down is more than 15 % behind at a milestone exit:

| step | cut | ids affected | what ships instead | h freed |
|---|---|---|---|---|
| 1 | T3 items not yet "go" | section 6 | their interims | up to 127 |
| 2 | SHELL-14 split pane | SHELL-14 | `View.drawer` at every width | 5.5 |
| 3 | EXPO-05 zoom-to-booth | EXPO-05 | highlight only (EXPO-03) | 3 |
| 4 | Sprints and Job Listings | EVT-05..08, SPON-06..10 | in-app browser (`LaunchMode.IN_APP_BROWSER_VIEW`) to us.pycon.org | 19 |
| 4b | Venue & Hours sections + Quiet Room card (D-110) | MAP-09, MAP-10 | one Markdown block without interleaved location cards, Quiet Room card dropped | 8.5 |
| 5 | EXPO-01..04 hotspots | EXPO-01..04, SPON-04 | static zoomable expo image; booth chip opens it unhighlighted | 25 |
| 6 | U3, U9, U15 to 27.1 | U3, U9, U15 | interims (section 5) | 21 |
| 7 | PWA | NATIVE-09 | no web build in 27.0 (talk demo uses the DEMO phones) | 10 |

**Never cut** (D-06): T0, the offline cache, the outbox, kill switches, the NOTIF-12 update gate, accessibility. MAP-09/MAP-10 are T2 in PLAN 4.1 ("Venue & Hours sections"); D-110 inserts them into the cut order as step 4b (section 14, note 3).

---

## 8. PSF asks (P1-P13)

Source: [PLAN 10.2](../PLAN.md#102-what-the-psf-must-provide-and-when). U prepares each ask two weeks ahead and tracks it in Linear PYMOBIL.

| # | item | owner | needed by | U prep (when) | blocks | if late |
|---|---|---|---|---|---|---|
| P1 | Agreement in principle, PSF-I contact, Linear access | PSF-I | 2026-11-13 | X-PITCH 10-16; web demo 10-23; 45 min call agenda | everything (G1) | escalate 11-16; Track 12-04 |
| P2 | Branch `flet-2027` in `PyCon/pycon-us-mobile` with Actions | PSF-I | 11-20 | repo ready to push (X-REPO) | CI on PSF repo, contributors | stay on public repo |
| P3 | Staging `/{YEAR}/api/v1`, per-role keys, sample badges, `mobile_state` PATCH and idempotency answers, code-only check-in answer | PSF-I | **12-15** | question list 12-01 | T0-P (AUTH, API-01..04), T1 (all staff ids), X-CONTRACT, X-BD1 | devserver fixtures; login hidden in alpha |
| P4 | ASC App Manager/API key, Play release manager, upload keystore in `release` env | PSF-I | **01-15** | `release.yml` unsigned dry run on the public repo (DEV-08) by 01-01; the signed run is X-RELEASE, after P4 | X-SIGNED, NATIVE-01, G2 | escalate; after 02-26 community track |
| P5 | Firebase app configs, APNs key, `test-*` topic, #300 console | PSF-I | 01-31 (push only) | spike S8 verdict 11-30 | E2 at G3 | push in 27.1 |
| P6 | Decisions OD-1, OD-3, OD-4, OD-5, OD-7, OD-9, OD-10, CORS | PSF-E/PSF-I | 01-15 | one-page decision memo 12-15 | NATIVE-02, API-04, AUTH-12, INFO-04, MASK-04 | defaults apply |
| P7 | Hosting for app-config, app-content, PWA domain | PSF-I | 01-31 | `firebase.json` + schemas (X-APPCFG) | NOTIF-12, LIVE-02, NATIVE-09, kill switches | Firebase Hosting under PSF project |
| P8 | 2027 sample feed or schema preview | PSF-I | **02-15** | contract schemas (X-CONTRACT) | M4 parser check | nightly contract catches drift ~03-13 |
| P9 | 2027 content: keynotes, booth geometry, floor plans, Wi-Fi, reminders, Concept3D id, sponsored spaces, CoC contacts | PSF-E | **03-20** | app-content template 02-20 | DATA-11, DATA-32, SESS-08, SPKR-04, INFO-07/08, EVT-03, MAP-03/07/10, EXPO-02 | ship feed-only; update content after release |
| P10 | Badge Day staff + printed badges | PSF-E | 02-24, 04-09 | Badge Day script 02-10 | X-BD1, X-BD2 (criterion S4) | G-Staff risk |
| P11 | Data Safety, App Privacy, privacy policy, age rating, export compliance, review account | PSF-I/PSF-E | **04-09** | X-STOREFORMS drafts 03-26 | submission 04-16 | slips toward 04-23 |
| P12 | Conference-week on-call partner | PSF-I | 05-05 -> 05-18 | runbooks 04-30 | hotfixes | U-only |
| P13 | (optional) Appflow access for bridge 26.3 | PSF-I | 03-15 | - | NATIVE-10 bridge only | clean slate |

---

## 9. Badge Days

| | Badge Day 1 (X-BD1) | Badge Day 2 (X-BD2) |
|---|---|---|
| Date / build | **2027-02-24**, staging build | **2027-04-09**, RC1 (04-07) |
| Needs | P3, P10; LEAD/DOOR/SHIRT/MASK ids of M3 green on staging by 02-19; E1 v0.1 (optional: manual/HID path is enough) | X-BD1 fix list closed; E1 PyPI 0.2 (02-19), unless G2/G-Staff made manual/HID primary |
| Script | >= 300 scans across the 4 tools; two devices on one attendee; queue + sync | >= 500 scans across the 4 tools; **30 min airplane mode for lead and door check** (swag and CoC are online-only and must show their explicit offline errors); two devices on one attendee; logout guard with pending rows |
| Pass (criterion S4) | 0 lost or misattributed (server audit vs device outbox); E1 >= 95 % first try (G-Staff) | 0 lost; with E1 >= 98 % first-try decode |
| If fail | fix list, retest at Badge Day 2; failing tool ships behind its kill switch with the manual path (G-Staff) | G5 decides (PLAN 7.4) |

The Badge Day protocol (script, metrics, audit query) is specified in `docs/testing-and-quality.md`.

---

## 10. CFP, talk and poster tasks

CFP expected ~2026-10-31 → ~12-18 (UNCONFIRMED); U checks `us.pycon.org/2027/` weekly from 10-20 and pulls dates forward if it opens earlier ([PLAN 11](../PLAN.md#11-the-pycon-talk-poster-and-demo-plan)).

| task | what | due | h |
|---|---|---|---|
| X-PITCH | Proposal email to infrastructure@python.org (cc Jacob Coffee) + 90 s recording; web demo link 10-23 | 10-16 | 2 |
| X-ABSTRACT | Talk + poster abstracts, accurate on both tracks (mentorship sign-up ~11-20 optional) | 11-14 | 2 |
| X-VIDEO | 3 min demo video from M1 rows: offline schedule, dark theme, favourites, Now & Next, drill Back (SESS-12), scanner spike S7. HC theme and Jump to Now (M2 rows) only if they land early (section 14, note 5) | 12-07 | 3 |
| X-CFP | Submit talk + poster | 12-11 | 1 |
| X-SPRINTFORM | Sprint form "PyCon US app + Flet extensions" | 04-15 | 0.5 |
| X-SLIDES | Slides v1 + DEMO-build script + 20 s fallback clips | 04-20 | 8 |
| X-POSTER | Poster panels (architecture, capability matrix) and print | 04-30 | 4 |
| X-BLOG | Flet + PSF blog posts | 04-27..30 | 1 |
| X-DRYRUN | Dry runs 05-01 and 05-08; Open Space "Write a Flet extension" prep | 05-08 | 3.5 |
| - | Speaker confirmation (notifications ~02-10..17, UNCONFIRMED) | ~02-25 | (in X-SLIDES) |
| - | Open Space booking (Thursday ~05-13, UNCONFIRMED); lightning-talk fallback | May | (in X-DRYRUN) |

Demo dependencies: DEMO build (`DEMO=1`: bundled feed, fixed clock, `SimulatedScanner` on a separate DB) = DATA-34 + LEAD-14 + D-84; the `scanner` veto demo needs X-CAPS + X-APPCFG.

---

## 11. `good first issue` candidates

Small, pure or isolated, off the critical path, with an obvious test. Each issue gets a screenshot or I/O spec and names its test (`test_<AREA>_<NN>_<slug>`). Label `good first issue`; extension work is labelled `flet-extension`.

| id | ms | h | why it is a good first issue |
|---|---|---|---|
| INFO-06 | M2 | 0.5 | static About the PSF page in `HeroPage`, links via `UrlLauncher` |
| INFO-09 | M2 | 0.5 | one card from app-content `wifi_sponsor_needle` |
| INFO-10 | M2 | 0.5 | static links list with bundled SVG logos |
| INFO-11 | M2 | 0.5 | static Help & Safety page |
| NOTIF-02 | M2 | 0.5 | master toggle with mixed state over six `Switch`es; pure state logic |
| NOTIF-10 | M3 | 0.5 | permission hint card + 'Open PyCon US Settings' link |
| EVT-02 | M2 | 1 | one year-scoped external sign-up link |
| EVT-04 | M2 | 0.5 | Session Types legend from the track palette tokens |
| MAP-02 | M2 | 0.5 | floor-plan cards list |
| MAP-11 | M2 | 0.5 | one external Get Directions link |
| AUTH-10 | M2 | 0.5 | one in-app browser link (`LaunchMode.IN_APP_BROWSER_VIEW`) |
| SPKR-02 | M2 | 0.5 | ANY-word name search over `core/queries.py` |
| DATA-31 | M3 | 0.5 | pure `date_ago()` with frozen-clock tests |
| SESS-05 | M2 | 1.5 | `core/ics.py` writer + escaping tests (RFC 5545 folding) |
| SPON-09 | M3 | 3.5 | `parse_roles()`/`shorten_url()` with `html.parser`; Bloomberg vector (T2) |
| SPON-07 | M3 | 1.5 | ALL-words search with debounce; reuses `core/queries.py` (T2) |
| EVT-06 | M3 | 2 | ALL-words search over text (T2) |
| X-CONTRAST | M2 | 2 | contrast-ratio unit tests from `Tokens` |

---

## 12. Weekly burn-down and triggers

**Procedure (every Monday, U, 10 min).**

1. `uv run python tools/feature_trace.py --burndown` on `main`. It collects test names matching `test_([A-Z]+)_(\d{2})_` (D-98), runs nothing itself, and reads the last nightly JUnit report to know which pass.
2. An id is **green** when at least one named test exists and passes, and **done** when green and merged. Dropped ids are excluded; LIVE-01 has no test, DATA-27 has its contract test.
3. Planned curve: each id's estimate (column h) is spread linearly over the weeks of its milestone; non-id tasks count by due date. `behind % = (planned_h - done_h) / planned_h`, over committed rows (T0, T0-P, T1) of all milestones up to today. T2 and T3 are tracked as separate lines.
4. Post the 5-bullet status in Linear PYMOBIL: behind %, ids done/planned, hours per bucket (U app, U Flet-work, CC), red PSF asks, next gate.
5. From M2 on, CI also fails when a required id (milestone exit passed) has no test (D-98), so a missing id shows up in PRs, not only in the burn-down. From G4 (03-31) the `trace` job runs `feature_trace --check --junit` over the merged PR + nightly junit and also fails when any required id is red or yellow (D-129, criterion S1).

```python
# tools/feature_trace.py (core of --burndown); backlog rows parsed from docs/backlog.md
ROW = re.compile(r"^\| \[(?P<id>[A-Z]+-\d\d)\]\(.*?\) \|.*?\| (?P<tier>T0-P|T0|T1|T2|-) \| (?P<ws>[a-z0-9]+) \| .*? \| (?P<h>[\d.]+) \|")
behind = (planned_h - done_h) / planned_h   # committed tiers only
```

**Triggers.**

| when | condition | action | source |
|---|---|---|---|
| 2026-12-15 | zero contributors recruited | U to ~19 h/week **or** zero-contributor cuts: T2, T3, change-log UI (2.5 h of X-CHANGELOG), wide goldens, devserver semantics, U1/U4 to 27.1; CC-owned `info` and `qa` rows move to U | PLAN 7.1, D-108 |
| every milestone exit | > 15 % behind | apply the cut order (section 7) top first until the projection is within 15 % | D-19, D-05, D-110 |
| G2 01-31 | > 15 % behind / > 30 % behind; < 85 % of M1+M2 rows green | cut order / the PSF chooses reduced scope or Ionic for 2027 | D-19, PLAN 7.4 |
| G2 01-31 | E1 cannot read real badges | manual/HID primary; PSF buys 4 HID scanners | PLAN 7.4 |
| 02-26 | no store roles (P4) | community track | PLAN 7.4 |
| 01-15 | Flet 1.1.0 not released (X-FLET11) | escalate the store chain; iOS builds on 1.0.4 + Xcode 26 only while Apple accepts them, E1 off (manual/HID) | R6, PLAN 7.3 |
| G3 02-12 | burn-down not within 5 % | every T3 item stays interim (27.1) | D-29 |
| G4 03-31 | any committed id not green | cut order until green | PLAN 7.4 |
| weekly | 0 contributors active for 3 weeks after 12-15 | treat as the 12-15 trigger | this doc |

Zero-contributor arithmetic (PLAN 7.1, D-108): capacity drops to 620 h against 667 h committed. 12-15 → 04-16 is ~17.4 weeks, so ~19 h/week closes the ~47 h gap; 17 h/week would close only ~31 h.

---

## 13. Conference (M6), 27.1 (M7) and the 05-17/18 sprint

**M6 (05-01 → 05-18; conference dates confirmed, day split UNCONFIRMED):** conference freeze **05-05** (P0 only, G6 crash-free >= 99.5 %); on-call with P12; kill switches and app-content fixes (< 30 min) instead of builds; dashboard (X-DASH); talk, poster, Open Space; criterion S5/S8 measured.

**M7 27.1 (05-19 → 06-30) backlog:** T3 items that missed G3 (E2, E3, E4, U8), U2 sticky headers, analytics if OD-3, extensions to 1.0, E5/E6 from the sprint, `pycon-contract` package (D-48), retro. **Handover 09-30:** docs, 30 min walkthrough, credentials matrix (all PSF), 2028 rollover drill <= 1 day without code edits (criterion S12).

**Sprint backlog, 2027-05-17/18 (day split UNCONFIRMED; form due 04-15).** Theme: "PyCon US app + Flet extensions". Prepared issues, each with a spec and a named test, ready by 05-10:

| # | item | size | prerequisite | owner/mentor |
|---|---|---|---|---|
| 1 | E5 `flet-html` v0.1 on `flutter_widget_from_html_core` behind a material_ui gate check; swap INFO-05/SESS-06/MAP-09 via `Caps.html` | M | repo scaffold from E1 template | U |
| 2 | E6 `flet-slidable` v0.1 on `flutter_slidable`; SCHED-11 revealed buttons via `Caps.slidable` | S | repo scaffold | U |
| 3 | U2 sticky/sliver section headers in core (SCHED-02) | M | design note in `docs/flet-gaps-and-extensions.md` | FT |
| 4 | U11 offline service worker for `flet build web` (NATIVE-09) | M | - | FT |
| 5 | T3 items that missed G3: finish E2/E3/E4 PRs | M-L | G3 notes | U |
| 6 | Year-rollover rehearsal: `app-content-2028.json` draft from the 2027 file | S | schemas | CC |
| 7 | First-timer issues: remaining `good first issue` rows, golden updates, translations of error copy into tests | XS-S | section 11 | CC |
| 8 | Extract `core/` as `pycon-contract` (D-48) and offer signing vectors to `pycon-site` | S | - | U |

---

## 14. Notes on the plan (discrepancies found while building this backlog)

PLAN.md was revised on 2026-10-11 while this backlog was being written (U1/U4/U5 20 h, committed 580 h + 15 % = 667 h, ~19 h/week zero-contributor trigger, spike S8 due 11-30, Flet 1.1.0 on the iOS critical path). This backlog follows the revised PLAN.

1. **Committed demand and the zero-contributor trigger (resolved).** D-108 supersedes D-17's figures: committed 580 h + 15 % = 667 h; at the 12-15 trigger U goes to ~19 h/week (12-15 → 04-16 = 17.4 weeks) or the D-17 cuts apply, matching PLAN 7.1.
2. **Pooled capacity (resolved by D-108).** PLAN 7.1 compares 667 h committed with 700 h total, but 220 h of it is "Flet-work time" for PyCon-driven upstream work, and committed upstream work is only 55 h (E1 35, U1/U4/U5 20). Committed app-side work is 525 h (604 h with contingency) against 400 h app time + 80 h CC, so ~124 h of app work must come out of the Flet-work bucket, which then has ~41 h left for T3 (127 h). D-108 records the 700 h as one pool, so Flet-work time may be spent on the reference app (PLAN 7.1, "The two U pools are mixed"). The burn-down reports hours per bucket so this stays visible.
3. **Venue & Hours in the cut order (resolved).** PLAN 4.1 lists "Venue & Hours sections" (MAP-09, MAP-10) in T2, but the D-05 cut order never cut them. D-110 amends D-05 to insert them after step 4 (one Markdown block, Quiet Room card dropped); section 7 step 4b.
4. **Duplicate Ionic rows.** The matrix keeps Ionic's duplicated features as separate ids (API-01/AUTH-03, SHELL-07/AUTH-06, SHELL-08/SPON-11, STORE-04/AUTH-07, DOOR-07/STORE-12, API-04/SCHED-12). One implementation each; the duplicate row is 0.5 h for its own named test so `feature_trace` stays complete.
5. **M1 load and the 12-07 demo video.** M1 (62 ids + its tasks) costs ~125 h in a 3-week milestone (section 3). PLAN 11 now matches: THEME-04/05/06 and SCHED-15/16 (HC theme, Jump to Now) are M2 rows, so the 12-07 video and X-VIDEO show M1 features (dark theme, Now & Next, drill Back) and add HC/Jump to Now only if they land early.
6. **Outbox before its first user.** API-04 (favourites PATCH "through the outbox", D-58) and AUTH-11 (logout guard with N unsynced) are M2, but the outbox rows (API-10, LEAD-12) are M3. This backlog adds X-OUTBOX (5 h of the staff workstream) to M2: the generic state machine and the single `SyncWorker` with the `favorites` kind; M3 adds the staff kinds.
7. **The #312 change log has no feature id.** PLAN 5.4/G-FIX and D-54 commit to it, but it is not an Ionic feature, so `feature-matrix.md` has no row and `feature_trace` cannot gate it. Filed as X-CHANGELOG (4 h out of the schedule workstream) with `test_changelog_*` tests; consider giving it an id in the matrix.
8. **Deep links have no feature id.** PLAN 7.2 puts deep links in M2 and D-38 commits to the `pyconus://app` scheme and the `ShortLink` aliases, but the Ionic app has no deep links, so the matrix has no row. Filed as X-DEEPLINK (M2, 2 h out of the shell workstream, taken as 0.5 h each from SHELL-08, THEME-04, THEME-05 and THEME-06) with `test_deeplinks_*` tests. D-38 named the global `[tool.flet.deep_linking]` table, which `flet build aab/ipa` does not read (flet-cli `build_base.py` reads `tool.flet.ios.deep_linking.*` for iOS and `tool.flet.android.deep_linking.*` for Android); D-109 supersedes that clause with the per-platform tables (the global table only for web/desktop), and PLAN 5.2/9.1 follow it.
9. **Ionic reference harness.** PLAN 7.2 lists the Ionic reference harness in M0 scope; this backlog finishes X-HARNESS in M1 (11-27) because spike S4 only lands 10-26, and starts it in M0 (section 3).

**Verify this file** (every matrix id exactly once in the backlog tables):

```bash
python3 -I -c "import re,sys; m=set(re.findall(r'^\| ([A-Z]+-\d\d) \|',open(sys.argv[1]).read(),re.M)); b=re.findall(r'^\| \[([A-Z]+-\d\d)\]',open(sys.argv[2]).read(),re.M); assert len(m)==263 and sorted(b)==sorted(m), (len(m),len(b)); print('ok', len(b))" docs/feature-matrix.md docs/backlog.md
```
