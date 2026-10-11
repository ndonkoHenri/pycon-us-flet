# PyCon US app on Flet: plan (v2)

**Status:** plan of record, 2026-10-11. This v2 replaces the PSF-oriented v1, which stays in git history (the repository's first commit) and is not binding.
**Owner:** U, a Flet core maintainer.
**Binding decisions:** [`docs/decisions.md`](docs/decisions.md) (D-nn, cited below).
**How we work:** [`AGENTS.md`](AGENTS.md).

We are rebuilding the PyCon US mobile app in Python with [Flet](https://flet.dev), for Android and iOS, as a community showcase of what Python and Flet can do.
- **The reference.** The official Ionic app is our functional reference and our quality bar. It is not a spec, and the PSF is not a dependency.
- **The design.** We keep the app's data semantics, improve its user experience, and build one Material 3 UI that is identical on both platforms.
- **The data.** Real data comes from the public conference feed. Features that need the PSF's private API run against a local mock server.
- **The pace.** The work is ordered in five phases, each with exit criteria. Presenting the app at PyCon US 2027 (Long Beach, CA, May 12–18) is the objective, not a deadline.

---

## 1. Vision and audience

**Who uses the app.**
- **Attendees** come first: plan the conference, know what is on now, find rooms, get reminders, and do it all offline.
- **Sponsors and staff** come in P3, through the staff tools (lead retrieval, door check, swag pickup, Code of Conduct capture), built against the mock.

**Who we build it for.** The Flet and Python communities:
- developers at PyCon who want to see a polished Python mobile app;
- Flet users looking for a reference app;
- sprinters and contributors who want readable code to build on.

**What success looks like.**
1. Attendees would pick this app over the official one for a conference day, because it is faster, works offline from the first launch, and is easier to use.
2. A Python developer can read any screen's code in a few minutes and contribute in an afternoon.
3. The app is accessible: TalkBack and VoiceOver flows work, text works at 200 %, and contrast meets WCAG AA (AAA for text in high contrast).
4. Flet gains the missing pieces upstream along the way (reminders, pull-to-refresh, a barcode scanner, non-fatal handler errors).
5. A live demo works on stage without Wi-Fi.

**Three hero qualities**, the things the official app never did:
- **Offline from the first install.** A feed snapshot is bundled, and data freshness is always shown honestly.
- **"Now & Next for me" and My schedule.** Your next session, what is happening now, conflicts between saved sessions, and reminders.
- **It behaves.** Back always pops one step, screens never jump by themselves, and nothing is a dead control.

## 2. Principles

From the owner's direction:
1. **Showcase, not a dependency.** The official app sets our quality bar. We don't contact the PSF now, and we never call its private endpoints (D-01, D-06).
2. **Mobile only.** Android and iOS. A desktop window is a developer convenience, never a target (D-09).
3. **Material 3 only, identical on both platforms.** No Cupertino or adaptive variants. The one deliberate difference is native back gestures (D-10, D-11).
4. **Better, not 1:1.** Wherever the original's UX, information architecture, visuals, accessibility or offline behaviour can improve, it does (D-03).
5. **Phases, not deadlines.** Step by step, each step finished, as fast as quality allows (D-02).
6. **In the open.** Work is tracked in GitHub issues and PRs, and every decision is written down (D-88..D-96).

From the Zen of Python (D-66):
- *Simple is better than complex.* Build what the current phase needs: no protocol with one implementation, no codegen, no registries.
- *Explicit is better than implicit.* State lives in a few named stores, and capabilities are plain constants.
- *Flat is better than nested.* A flat `screens/` package and a flat More list instead of a drawer with accordions.
- *Errors should never pass silently.* Failures become visible state, never a swallowed `None`.
- *If the implementation is hard to explain, it's a bad idea.* That rule cut v1's capability framework and remote config.
- *Readability counts.* Docstrings on every module and public function, small modules, descriptive tests (D-74).

## 3. Scope summary

The full table, one row per feature with its approach, UX change, dependencies and notes, is [`docs/feature-matrix.md`](docs/feature-matrix.md), the source of truth for scope. It covers all **263** features catalogued from the Ionic app, plus **9** new ones.

**By disposition**, catalog ids only (the 9 `NEW-*` rows are `new`, and NEW-05 is also `interim`), counting each tag in a combination such as `improve+mock`. The matrix's [Counts](docs/feature-matrix.md#counts) section is authoritative; `tools/check_matrix.py` keeps it current.

| improve | mock | redesign | keep | drop | interim | later |
|---|---|---|---|---|---|---|
| 121 | 65 | 58 | 37 | 23 | 18 | 1 |

**By phase**, catalog ids plus `NEW-*`:

| P0 | P1 | P2 | P3 | P4 | dropped |
|---|---|---|---|---|---|
| 45 | 66 | 69 | 68 | 1 | 23 |

**New features:**
- **P0:** a bundled feed snapshot.
- **P1:** My schedule (a personal agenda with overlap warnings and Undo); global search across all days; sharing a session.
- **P2:** the schedule change log (#312); reminders before saved sessions; deep links.
- **P3:** the local mock PyCon API server.
- **P4:** "View source" on each screen, once the repo is public.

**Dropped (23):**
- Appflow over-the-air updates.
- Push notifications and analytics.
- Web and PWA, and features that need the PSF domain (shared credentials) or Ionic's storage.
- Features replaced by better designs: per-page searches, swipe-to-favourite, blocking loaders, the notification master toggle.
- Developer leftovers.

**The main improvements, area by area,** are listed in [`docs/ux.md`](docs/ux.md) and in each matrix row.

## 4. UX direction in brief

The full spec is [`docs/ux.md`](docs/ux.md), which consolidates three UX studies; the decisions are in sections C and D of the record.

- **Navigation.** A Material 3 bottom bar with five fixed tabs, **Now · Schedule · My schedule · Map · More**, the same for every user (D-13). The app opens on Now. More is a flat sectioned list, with no drawer. Staff tools are a More section and a Now card, not a tab (D-15, D-16). On tablets the bar becomes a navigation rail.
- **Back and position.** Every detail chain is a real back stack, so session → speaker → session pops one step at a time (#279). Screens keep their day, filters and scroll position, and never move by themselves (#313) (D-17, D-18).
- **Schedule.** Day tabs with dates. Each time slot is one block, with its time in a left gutter (Flet has no sticky headers). A 48 dp star on every row. Filters in a bottom sheet of chips with a live count, with active filters always visible (D-20, D-30, D-31).
- **Now.** A home dashboard:
  - before the conference, a countdown and "build your schedule";
  - during it, **your next session**, what is happening now (start ≤ now < end, which fixes Ionic's "until midnight" bug) and what is up next;
  - afterwards, a wrap-up.
- **My schedule.** Saved sessions by day, with overlap warnings and Undo on removal; in P2, `.ics` export and reminders.
- **One search** over sessions, speakers and rooms on all days, accent-insensitive, requiring all words to match (D-19, D-46).
- **Session detail.** "When and where" first, with Share and Add to calendar. Feed HTML is rendered as Markdown, and links open in the in-app browser.
- **Map.** Rooms, floor plans with pins, an expo map with a list alternative, and the job fair. Zoom buttons as well as pinch.
- **Look.** M3 seeded from PyCon indigo `#3B3EA9` with brand overrides, neutral surfaces, and light, dark and high-contrast schemes. Roboto bundled so iOS matches Android. Quiet chrome: brand colour only at identity moments (D-22..D-28).
- **Honest states.**
  - A status strip appears only when data is stale, offline or refreshing.
  - Skeletons appear only when there is no data at all, and there are never blocking loaders.
  - A SnackBar with Undo confirms quick actions, a Banner flags conditions that need action, and a dialog appears only before something destructive (D-29, D-32).
  - Permissions are asked in context, never at launch (D-61).
- **Accessible by construction.** Labels and states, merged row semantics, 48 dp targets, 200 % text, reduced motion, and contrast checked by a test (D-33).

## 5. Architecture in brief

The full design is in [`docs/architecture.md`](docs/architecture.md); the names are in [decisions §M](docs/decisions.md#m-naming-binding).

```
src/main.py ── App (boot gate, providers, Router)
src/pycon_us/
  core/        pure Python, no Flet: feed decode + processData rules, models, queries,
               time formatting, slugs, HTML→Markdown, diff, .ics, signing, outbox state
  services/    I/O at explicit boundaries: storage, feed fetch (P0) and API client (P3), sync worker (P3),
               reminders, scanner; the @report_errors last-resort net
  state.py     3 observable stores (Conference, Prefs, Favorites) + Account, Staff in P3,
               one context each; ViewMemory, a plain holder for positions (D-18)
  screens/     one @ft.component module per screen;  ui/  shared components
  routes.py    five tab roots + More pages + global-modal search + recursive drill
  data/<year>/ conference.toml, content.toml, map.toml, conference.json (snapshot)
tools/mock_api/  pure handle() → LAN server for phones, httpx.MockTransport in tests
```

- **Data flow.**
  1. On start, the app renders the cached feed, or the bundled snapshot if there is no cache.
  2. A single-flight refresh fetches the public feed.
  3. Only after a good parse does it write the raw bytes to the durable app data directory (D-38, D-39).
  4. Views are pure queries over frozen models, memoised on the feed version.
- **Year content** (Wi-Fi, safety contacts, keynotes, booths, pins, reminder times, URLs) is bundled TOML loaded with stdlib `tomllib`, and the loader is the schema (D-45). There is no remote config.
- **Capabilities** are import-time constants: an extension is used only when the app is a packaged build *and* the extension is bundled. The `flet run` companion app therefore always gets the interim (D-63).
- **Private API.**
  - The mock implements the `/api/v1` contract as inferred from Ionic's client (`pycon-api.ts`); request signing is byte-exact with Ionic and checked against vectors generated by Ionic's own code (D-52).
  - The client refuses PSF hosts outright (D-50..D-53).
  - Staff scans go through a sqlite outbox, and a scan is never lost or misattributed (D-56).
- **Flet rules we live by** (D-70): async handlers for coroutine APIs, `async def` effects with sync cleanups, one context per observable, unconditional hooks, `eq=False` frozen values, never `adaptive=True`.

## 6. Flet gaps and upstream work

Specs and status are in [`docs/flet-gaps-and-extensions.md`](docs/flet-gaps-and-extensions.md). Upstream work runs as a **parallel track** of `upstream` issues (D-97). Each gap ships a tested interim now. A core gap (U-items) is upgraded only after a PR bumps the pinned Flet, and the swap is its own PR, never runtime detection (D-64). An extension (E-items) is enabled by a PR that adds its pinned package, and its interim stays the fallback whenever the import-time capability constant is false, e.g. in the companion app (D-63).

| Gap | Interim (ships now) | Upstream piece | Priority |
|---|---|---|---|
| Scheduled local notifications | Now's "Your next session", an in-app Banner, `.ics` alarms; the settings say "not in this build" | **E3**: scheduling in the official flet-dev/flet#6948 extension (+ U7, which #6948 itself needs, and Android receivers) | 1 (spike S6 during P1; app in P2) |
| Pull-to-refresh | Status-strip Refresh + automatic refresh | **U1** `RefreshIndicator` | 2 (P1) |
| Handler exceptions crash the session | `@report_errors` decorator | **U15** non-fatal mode + Python error hook | 3 (P1–P2) |
| Barcode scanning | Manual + USB/Bluetooth HID entry | **E1** extension over `mobile_scanner` | 4 (spike S8; before P3) |
| App version at runtime | `__version__` constant | **U4** `page.get_app_info()` | 5 (P2) |
| OS text scale; accessibility-setting changes | Fluid layouts; re-read on resume | **U16** `PageMediaData.text_scale_factor`; **U17** change event | 6 (P2) |
| Sticky headers, `AppBar.bottom` | Time gutter; tabs as the first body row | **U2**, **U10** | 6 (app: later) |
| Zoom-to-booth | Select + highlight, no camera move | **U3** absolute `InteractiveViewer` transform | 6 (app: later) |
| Query-string hook | `use_query()` | **U9** `use_route_search()` | 6 (app: later) |
| Back from a result pushed over the modal search | Our `page.on_view_pop` with `parent_of()` (D-19) | **U18** per-level pops inside a modal sub-chain | 6 (app: later) |
| iOS adaptations Flet cannot pin; weights in `page.fonts` | Accepted residuals (D-10); Roboto through the pubspec (D-26) | **U19** `Theme.platform`; **U20** multi-weight `page.fonts` | later |
| HTML, native calendar | HTML→Markdown; `.ics` share | **E5**, **E4** | later |

FCM push (E2) is not needed by the app; it is a low-priority Flet contribution. The owner's open flet-dev/flet#6953 (deep-link config fallback) is not required, because we configure both per-platform tables (D-21).

## 7. Phases

Phases are GitHub milestones (D-89). Each milestone description carries its goal and exit criteria, and a pinned status issue is updated weekly. The breakdown into epics and issues is [`docs/roadmap.md`](docs/roadmap.md); GitHub issues are the live task list. **Soft markers are orientation, not deadlines.** The 2027 feed is expected around March (UNCONFIRMED). It joins whichever phase is active when it appears; until then we use the 2026 feed with the Developer fake clock.

### P0 Foundations (soft marker: early November 2026)

**Goal:** a proven toolchain, a tested data core, and an app shell running as a packaged build on an Android emulator and the iPhone.

**Scope:**
- **Repo and process:** the repo, AGENTS.md, CI, labels, milestones and Project board.
- **Toolchain:** the Flet 1.1 pin and dev setup (D-81).
- **Spikes S1–S5.**
- **Data core** in `core/`: the feed pipeline with named rule tests, invariants and a snapshot on the 2025 and 2026 feeds; a one-off capture of Ionic's reference output (D-77).
- **Offline data:** the bundled snapshot and the durable cache.
- **App shell:** five tabs, routes with the recursive drill, light and dark themes, Roboto and the boot gate.

**Exit criteria:**
1. Packaged builds from the pinned Flet run on an Android emulator and on the owner's iPhone, with no connection to a dev server (D-102). On first launch offline they show the bundled schedule on the Schedule stub (days, session counts and source); online, a refresh replaces it. State survives kill and relaunch, and an update install.
2. CI is green on `main`. The feed tests (rules, invariants, snapshot) pass on the 2025 and 2026 feeds.
3. The shell passes the S4 navigation journey on an Android emulator and the iPhone, using stub detail screens. The shell smoke flow (`test_shell_starts`, `flet test`) passes on an emulator and a simulator.
4. Spikes S1–S5 are closed with written verdicts in `docs/spikes/`. Their outcomes are recorded in the decisions record: the Flet pin mechanics, the list-row architecture, the route shape and the performance targets.

### P1 Attendee core (soft markers: demo slice end of November 2026; exit mid-December)

**Goal:** the attendee core is good enough to demo, and to use for a whole simulated conference day.

**Scope, in this order:**
1. **The demo slice:** Schedule (day tabs, slot layout, filter sheet, Jump to now), session detail (When and where, speakers, description, Share), My schedule, Now, global search.
2. **The rest of P1:** Speakers, rooms and room detail, tracks and session types, keynotes, open spaces, lightning talks and sprints.
3. **Throughout:** the status strip, the Developer screen with fake clock, and the accessibility baseline.

In parallel upstream: U1, U15 and spike S6.

**Exit criteria:**
1. On an Android emulator and the iPhone, with packaged builds in airplane mode, the core journeys work:
   - open on Now, then session → speaker → session → Back;
   - star and unstar with Undo;
   - My schedule shows overlaps;
   - search finds sessions, speakers and rooms on any day;
   - filters stay visible and persist.
2. A simulated conference day (fake clock, 2026 feed) behaves:
   - Now respects end times and shows your next session;
   - Jump to now works;
   - nothing scrolls unasked (#313);
   - Back pops one step (#279).
3. A failed refresh (offline, HTTP error, corrupt payload) keeps the last good data. The time-zone and id tests pass under two machine time zones.
4. TalkBack and VoiceOver complete search → favourite → session detail. Text at 200 % clips no action, and the contrast tests are green.
5. Performance against D-80 is measured and recorded, and there are no known crashes.
6. A 2–3 minute recording of the demo slice exists (CFP material if O-6 is a yes).

### P2 Conference companion (soft marker: February 2027)

**Goal:** everything an attendee needs at the venue, offline, plus reminders.

**Scope:**
- **Map:** floor plans with pins, an expo map plus list, the job fair (spike S7 first).
- **Sponsors:** a tiered list, sponsor detail, the Now spotlight and credits; job listings.
- **Info pages:** About PyCon US, About the PSF, Help & safety, Wi-Fi, Social, Venue & hours.
- **Welcome and Settings:** appearance, high contrast and reminders.
- **Reminders and calendar:** local reminders (E3 if pinned, otherwise the interim) and `.ics`.
- **Also:** the schedule change log (#312), deep links, the tablet rail, the high-contrast schemes and About this app.

**Exit criteria:**
1. Every P2 row of the matrix is done, or was explicitly re-dispositioned with a reason.
2. In airplane mode, floor plans with room pins, the expo map and list, Wi-Fi, Help & safety and venue hours work from bundled year data, and the loader test is green.
3. Reminders:
   - With E3 pinned, a saved session's reminder fires with the app killed on the iPhone and on an Android emulator, and after a reboot of the emulator (D-102). Tapping it opens the session, and the reminder moves when the session moves.
   - Without E3, the interim says so honestly.
   - A denied permission never blocks a task.
4. The change log shows a simulated change from a fixture feed pair, with saved sessions first. Deep links and reminder taps land with a back stack.
5. The device checklist passes (D-79), including high contrast, the tablet layout and TalkBack and VoiceOver on three new flows.
6. Someone other than the owner installs an internal build and, unaided, finds a room, saves a session and copies the Wi-Fi password.

### P3 Accounts & staff tools (soft marker: March 2027)

**Goal:** the private-API features, built faithfully against the mock, with the scanner as the showcase.

**Scope:**
- **The mock and its contract:** the mock server, contract README and signing vectors.
- **Account:** sign-in, the account screen, role flags and favourites sync.
- **Staff tools:** the staff section and the shared scan screen, then the tools in the order lead retrieval (consent, sponsor picker, notes) → door check → swag → CoC (O-7).
- **Offline queue:** the outbox and the sync worker.
- **Scanner:** E1 integration once the extension is pinned (spike S8 runs earlier, on the upstream track).

**Exit criteria:**
1. Every tool kept under O-7 completes scripted scenarios against the mock on an Android emulator and the iPhone, with manual and HID entry, and with the camera when E1 is bundled (the iPhone's camera, or the emulator's virtual scene camera on Android, D-102); otherwise the scan screen shows the interim honestly.
2. The offline queue holds:
   - Scans made in airplane mode queue and survive kill and restart.
   - Under idempotent mock semantics each record syncs exactly once; under non-idempotent semantics no record is lost, and a duplicate occurs only after a lost response, where it is detected and shown (D-57).
   - Failures are visible, with Retry.
   - Signing out with unsynced rows asks first.
3. The fault-injection scenarios (dropped responses, expired auth, skewed clock, account and sponsor switch) and the Ionic-derived signing vectors pass. A wrong role cannot reach a tool (truth table).
4. A test proves the client refuses PSF hosts.
5. If E1 is bundled, a printed sheet of mock badges scans on the iPhone (on Android, the badge images through an emulator's virtual scene camera), including two devices (the iPhone and an emulator) checking in the same attendee; otherwise the same scenario passes with manual or HID entry.

### P4 Showcase (soft marker: ready in April 2027, well before PyCon US, May 12–18)

**Goal:** polish, publish, present.

**Scope:**
- A performance pass and an accessibility audit.
- A few goldens.
- The 2027 data, if published.
- "View source" on each screen.
- The README, with screenshots and an accessibility section, plus CONTRIBUTING and good first issues.
- A licence, asset and trademark review, then making the repo public.
- The talk and demo script, with recorded fallbacks.
- The decision on whether to approach the PSF (appendix).

**Exit criteria:**
1. There are no known data-loss or task-blocking bugs, and the performance targets are met on the iPhone and on a borrowed mid-range Android phone; if none was borrowed, the P4 status issue says that Android was measured on the emulator only (D-102).
2. Someone else, or the owner on a clean machine, builds and runs the app from a clean checkout in 30 minutes or less, following `docs/development.md`.
3. The demo script runs end to end twice without Wi-Fi.
4. The repo is public, and `v1.0.0` is tagged with internal builds for both platforms.

**Optional and objective markers.**
- **PyCon US 2027 CFP** (O-6): expected to open around 2026-10-31, mentorship sign-up around 11-20, closing around 12-18 (all UNCONFIRMED). The P1 demo slice is the material.
- **PyCon US 2027** (May 12–18, Long Beach; dates confirmed, day split UNCONFIRMED): the talk or demo, an Open Space, and a sprint on the app and Flet extensions.

## 8. Early spikes

Each spike is an issue titled `Spike: …` (label `test`, D-91), time-boxed to half a day to a day. Its verdict goes to `docs/spikes/NN-<slug>.md`: versions, devices, numbers, the smallest reproducer, and the fallback. S1–S5 run in P0, before the screens they affect are built. The others run when their phase needs them, or earlier on the upstream track.

| # | Question | Method | When | Decides |
|---|---|---|---|---|
| S1 | Does the packaged app run well on Android and iOS with our stack? | A stub with `httpx`, `zoneinfo` + `tzdata`, `sqlite3`, SharedPreferences and SecureStorage. Fetch, parse and persist the 2026 feed, then kill, relaunch and install an update. `adb shell am start -W` ×10 for cold start and first launch, with `.pyc` compile on and off. Check `is_embedded()`. Edge-to-edge with 3-button and gesture navigation; status- and navigation-bar icons visible in light and dark (`Theme.system_overlay_style`, D-12). On an Android emulator and the iPhone; the emulator's timings are a baseline for regressions, not the targets (D-102). | P0, first | Storage paths, performance targets, lazy imports, parsing off-thread or not |
| S2 | Can the busiest day (2026 Friday: about 26 slots and 110 rows, open spaces included) render and update fast in components mode? | Per-row `@ft.component` with keys and memo on `(id, is_fav)`. Measure star-tap latency and search-as-you-type latency; compare eager and lazy lists; `scroll_to` an unbuilt slot; 200 % text. Numbers from release builds on the iPhone; an Android emulator for relative comparisons between variants (D-102). | P0 | Row architecture, `build_controls_on_demand` |
| S3 | Is a stdlib HTML→Markdown converter good enough for the feed? | Convert every HTML field in the 2025 and 2026 feeds, count unhandled tags, and render 20 samples on a phone. | P0 | Converter scope; test fixtures |
| S4 | Do the Router, the drill route and native back gestures behave? | Now → session → speaker → session → room, with Android back and predictive back, iOS edge swipe, tab switches and re-taps, background and resume, and per-level drill params. Search → result → Back returns to the results through our `page.on_view_pop` (D-19), with the query preserved; Back on a non-Now root goes to Now through `can_pop=False` and `confirm_pop` (D-17). | P0 | Route shape (or the `s~id` fallback) |
| S5 | Can we build and ship internally from the pinned Flet 1.1? | Dev setup per D-81, including a companion client built from `client/` at the pin talking to the pinned Python. `flet build apk`, `aab` and `ipa`. The `flutter.fonts` entry for Roboto 400/500/700 resolves, and the three weights render on iOS (D-26). One TestFlight internal upload (privacy manifest, ITMS-91053), installed on the iPhone. `flet build ios-simulator` for the simulator. AAB download size via bundletool. The default Android `minSdk`. | P0 | Flet pin mechanics, `docs/development.md`, whether U13 is needed |
| S6 | Can local reminders be reliable when the app isn't running? | A release build schedules a reminder 2 minutes ahead. Test with the app killed, the phone locked, a tap from cold start and more than 64 candidates on the iPhone; with the app killed, a reboot, exact alarms denied and a cold-start tap on an Android emulator (D-102). | During P1 (upstream track) | E3 scope; U7 and Android receivers |
| S7 | Do real floor plans with ~60 hotspots work in `InteractiveViewer` on a low-RAM phone? | Plans re-encoded to ≤ 2048 px. Maximum zoom, tap accuracy, a memory profile, and booth select + highlight with the zoom buttons (reset, zoom in, zoom out). | Start of P2 | Image sizes; hotspot approach |
| S8 | Does a minimal `mobile_scanner` extension decode reliably in release builds? | One control with `on_detect` and a torch toggle; release builds for Android and iOS. On the iPhone: a printed QR in daylight and dim light, repeated detections, permission denied, background and resume. On an Android emulator: a QR image in the virtual scene camera, permission denied, background and resume (no torch or lighting conditions). The companion app falls back to manual entry. | Before P3 (upstream track) | Whether E1 goes ahead, and its API |
| S9 | Can the UI flows run in CI with `flet test linux`? | `flet test linux` on `ubuntu-latest` under `xvfb-run` with a phone-sized window, run alongside the local flows. | P2 at the earliest | A separate workflow proposed through `needs-decision` once green for two weeks, never in `ci.yml` (D-78, D-84) |

## 9. Quality bar

- **Correct.** Feed rules, time zones, ids, signing and the outbox have tests that protect them (D-76, D-77). Times are right in any device time zone, and no scan is lost or misattributed.
- **Offline-first.** Every attendee screen works in airplane mode from the first launch.
- **Honest.**
  - No dead controls and no blocking loaders.
  - Data freshness is always visible.
  - Every error state names a way out.
- **Accessible.**
  - Every control has a name, role and state; targets are at least 48 dp.
  - Contrast meets AA (AAA for text in high contrast), and a test enforces it.
  - Text works at 200 %, and reduced motion is honoured.
  - TalkBack and VoiceOver flows are checked at every phase exit (D-33, D-79).
- **Fast.** Cold start to the cached schedule in 2.5 s or less, feed processing in 400 ms or less, and no visible jank. The targets are written for a mid-range Android phone; until one is borrowed they are measured on the iPhone, and Android emulator numbers only flag regressions (D-80, D-102). Numbers are set from spike evidence.
- **Consistent.** Identical Material 3 on Android and iOS, with native back gestures.
- **Readable.** Zen-style code: docstrings, modules under about 400 lines, descriptive tests, ruff and pyright clean (D-66, D-74).
- **Verified on devices.** UI PRs carry screenshots from an Android emulator and an iOS simulator, and each phase exit runs the device checklist and smoke flows there, with the iPhone for hardware checks (D-78, D-79, D-102).

## 10. How we work

The workflow is written down in [`AGENTS.md`](AGENTS.md), the operating manual for humans and agents, which is maintained separately. The work itself is broken down in [`docs/roadmap.md`](docs/roadmap.md); GitHub issues are the live task list. In brief (D-88..D-96):

- **Issues first.** One private GitHub repo (public in P4). Every change starts from an issue, except trivial chores; an issue describes a journey or a mechanism, with feature ids, D-ids, acceptance criteria and the device evidence needed.
- **One issue, one PR.** A `<type>/<issue>-<slug>` branch and an early draft PR of about 400 changed lines or fewer, with screenshots for UI. CI must be green. Agents squash-merge their own PRs under the merge conditions of D-100; the owner watches and can step in, but is never a blocker.
- **Milestones are the phases**, with the labels in D-90, a "PyCon US Flet" Project board and a weekly status issue per phase.
- **Decisions change only through a `needs-decision` issue** and a PR that edits [`docs/decisions.md`](docs/decisions.md). Reversible choices are decided by agents and recorded; only hard-to-reverse or outward-facing ones wait for the owner (D-101). Docs change in the same PR as the behaviour.
- **Second opinions** (Claude Fable, Codex) are summarised as PR comments, and PRs that change code or configuration also get a GitHub Copilot review (D-103). **Upstream work** lives in flet-dev, tracked here by `upstream` issues.

## 11. Risks

| Risk | Signal | Mitigation |
|---|---|---|
| Flet 1.1.0 stays unreleased and `main` churns | Builds break after a pin bump | Pin a commit and bump it deliberately in its own PR (D-81). The owner fixes issues upstream, and S5 documents the setup. |
| Packaged performance (cold start, list rendering in components mode) | S1 or S2 misses the targets | Measure first; then lazy imports, `.pyc`, rendering from cache first, memoised rows, simpler rows, and upstream fixes. |
| Scheduled notifications are harder than expected (receivers, exact alarms, iOS limits) | S6 fails a case | An honest interim (D-60), a bounded plan, inexact alarms by default. Ship E3 only when it is solid. |
| The scanner extension is unreliable (camera, permissions, `material_ui`) | S8 shows decode or permission issues | Manual and HID entry are first-class, so the staff tools never depend on E1. |
| Device coverage: one iPhone, no Android hardware (D-102) | Bugs reported on real Android devices; Android performance known only relative to the emulator | Android emulators and iOS simulators for every functional check, the iPhone for hardware checks. Borrow a mid-range Android phone before P4 for absolute numbers, TalkBack, the camera and reminders on hardware (a friend, the Flet community or a tester); buying one is the owner's call (D-101). |
| Trademark and identity: PSF marks leave our devices | Any build shared outside the team | Attribution, our own icon, no public listing (D-36, D-85, O-4). |
| 2027 data arrives late or changes format | `feed-check.yml` fails, or the feed returns 404 | Tolerant parser guards, a weekly feed check, and the 2026 data with the fake clock meanwhile. |
| The mock drifts from the real API | Cannot be detected without the PSF | A contract README citing Ionic's code, never a claim of compatibility, and the PSF appendix. |
| Scope and complexity creep | Large PRs, new abstractions | The Zen rules (D-66), phase exit criteria, the `needs-decision` gate, and the matrix as an inventory. |
| Solo capacity alongside Flet duties | A phase overruns its soft marker | Phases, not deadlines; a parallel upstream track; agents for mechanical work. Cut scope by phase, never quality. |
| The live demo fails | A rehearsal fails | An offline-first app, the fake clock, the demo-backend choice (O-8), and recorded fallbacks. |

## 12. Open decisions

The full list, each with a recommendation, is in [`docs/decisions.md` › Open decisions](docs/decisions.md#open-decisions); provisional decisions apply until they are settled under D-101 (owner-only ones by the owner). **O-1** the tabs and start screen (recommended: Now · Schedule · My schedule · Map · More, opening on Now); **O-2** per-platform page transitions (yes); **O-3** the font (Roboto); **O-4** app identity, bundle id and icon (no PSF marks on anything that leaves our devices); **O-5** distribution (internal only); **O-6** a CFP proposal (decide around 2026-11-20); **O-7** staff-tool depth (all four, ordered so the last two can slip); **O-8** a stage-demo backend (decide at the P3 exit).

---

## Appendix: if we later approach the PSF

This applies only if the owner is satisfied with the app and chooses to; nothing here is a dependency.

**What we would offer:**
- the Apache-2.0 source and the Flet extensions;
- help moving the app to the PSF's own store listings (`org.pycon.us`, `org.pycon.us.2023.onsite`) under the PSF's keys and CI;
- the API contract documentation and signing test vectors from the mock;
- the accessibility and offline work, and a maintainer handover.

**What we would need:**
- permission to use the PyCon US name and marks;
- a staging `/api/v1` with test keys per role, and sample badges;
- answers on API semantics: `mobile_state` PATCH, idempotency of capture and redeem, and whether manual entry may omit the validator;
- yearly content (keynotes, floor plans, booth geometry, Wi-Fi, safety contacts);
- a contact person, and, if they want push, their Firebase project.
