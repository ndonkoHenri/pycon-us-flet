# Roadmap

**Status:** plan of record, 2026-10-11. It is the phase breakdown into epics and issues, and replaces v1's backlog, which stays in git history with the other v1 docs (D-96). Binding inputs: [`PLAN.md`](../PLAN.md) (phases and exit criteria in §7, spikes in §8) and [`decisions.md`](decisions.md) (D-ids). Scope per feature id: [`feature-matrix.md`](feature-matrix.md).

This file turns the plan into work:
- **P0 and P1** are broken down into PR-sized issues.
- **P2 to P4** are epics with their scope. We break each one down when its phase starts.

`issues.json` seeded GitHub once from the same content (section 10). Once seeded, **GitHub issues are the live task list**. This file keeps the phases, exit criteria, epics and the reasons behind the breakdown. It is edited by hand, only when a phase starts or when scope changes through a `needs-decision` issue.

---

## 1. Phases at a glance

Phases are milestones (D-89). Soft markers are orientation, never deadlines (D-02).

| Phase | Goal | Soft marker | Items |
|---|---|---|---|
| **P0 Foundations** | A proven toolchain, a tested data core, and an app shell as a packaged build on an Android emulator and the iPhone | early Nov 2026 | 4 epics, 27 issues, spikes S1–S5, a status issue |
| **P1 Attendee core** | Good enough to demo, and to use for a whole simulated conference day | demo slice end of Nov; exit mid-Dec 2026 | 7 epics, 36 issues, spike S6, 2 upstream issues |
| **P2 Conference companion** | Everything an attendee needs at the venue, offline, plus reminders | Feb 2027 | 9 epics, 3 upstream epics, 1 upstream issue |
| **P3 Accounts & staff tools** | The private-API features against the local mock, with the scanner as the showcase | Mar 2027 | 8 epics |
| **P4 Showcase** | Polish, publish, present | ready in Apr 2027 | 5 epics |

Upstream Flet work runs in parallel with the phases (section 8).

## 2. How to read it

**Keys.** `P0-12` is an issue, `P1-E3` an epic, `S1`..`S6` spike issues (S7..S9 open with the epics that need them) and `UP-…` upstream work. The seeder writes each key into its issue body, so the roadmap and GitHub stay traceable.

**Issue blocks.** Each block gives the labels, dependencies ("after") and feature ids, a one-paragraph description and the acceptance criteria. The GitHub issue adds the D-ids, implementation notes, the docs to read and the definition of done (D-93), which for UI work includes Android and iOS screenshots in light and dark.

**Labels (D-90).** Each item has at least one type label, exactly one area label, and optionally a status label. Upstream epics carry both `epic` and `upstream`. Spikes are `test` issues titled `Spike: …`, and their verdicts go to `docs/spikes/NN-<slug>.md` (D-91).

**Epics** are parent issues, and their issues are sub-issues. A few issues have no epic: status, phase exits, decisions and single upstream items. A spike can be a sub-issue of an upstream epic in a later milestone: S6 runs in P1 under UP-E3 (P2).

**Dependencies are hard.** Start an issue only when its dependencies are merged; for a spike, that means its verdict is merged.

**Size.** An issue is one PR of about 400 changed lines or fewer, fixtures excluded (D-92). If a PR outgrows that, split the issue; don't widen the PR.

**Names.** Modules, stores, components and routes follow [decisions §M](decisions.md#m-naming-binding). Every Flet API named here exists in the local SDK (flet-dev/flet `9fbe52a61`), except the upstream items in section 8, which ship with an interim until they land.

## 3. P0 Foundations

**Goal.** A proven toolchain, a tested data core, and an app shell running as a packaged build on an Android emulator and the iPhone.

**Exit criteria** (PLAN §7):
1. **Packaged builds.** Builds from the pinned Flet run on an Android emulator and on the owner's iPhone, with no connection to a dev server (D-102).
   - Offline, the first launch shows the bundled schedule on the Schedule stub (days, session counts, source); online, a refresh replaces it.
   - State survives kill and relaunch, and an update install.
2. **CI.** CI is green on `main`, and the feed tests (rules, invariants, snapshot) pass on the 2025 and 2026 feeds.
3. **Shell.** The shell passes the S4 journey on an Android emulator and the iPhone with stub details, and the shell smoke flow (`test_shell_starts`, `flet test`) passes on an emulator and a simulator.
4. **Spikes.** S1–S5 have verdicts in `docs/spikes/`, and their outcomes are in `decisions.md`.

**Early spikes.** S1–S5 (epic P0-E2) run before the screens they affect are built (PLAN §8). S1 and S5 come first, because every packaged check depends on them.

**Order.** Four tracks interleave:
1. **Repo:** P0-01 (with the Flet pin, development.md §2.2), then P0-02 and P0-03. P0-04 → P0-05 and P0-06 follow S5.
2. **Data:** P0-08 → P0-09 → P0-10 → P0-11 and P0-12 → P0-13 → P0-14 and P0-07. P0-15 follows S3.
3. **Offline:** P0-16 (after S1), and P0-17 → P0-18.
4. **Shell:**
   - P0-19 early;
   - P0-20 once the store and theme exist;
   - then P0-21, P0-22 (after S4), P0-23, P0-24 and P0-25;
   - P0-27 (the `flet test` harness and the shell flow) once the tabs and More exist.

P0-26 closes the phase.

### P0-E1 · Repository, toolchain and CI

Project skeleton, CI, GitHub process files, the Flet pin and the build configuration.

#### P0-01 · Scaffold the project: pyproject, uv, layout and version

chore, area:build

Create the Python 3.14 project with uv, the flat layout of decisions §M, `__version__`, ruff, pyright, pytest, `LICENSE` and `NOTICE`.

- After the documented Flet checkout (`git clone ... .flet-src`, then `git -C .flet-src checkout --detach "$(cat .flet-ref)"`), `uv sync --locked` works; ruff, pyright and pytest pass.
- A test asserts `__version__` equals `[project].version`.
- A test fails on any `flet` import under `pycon_us/core/`.

#### P0-02 · Add the CI workflow (ci.yml)

ci, area:build · after P0-01 · DEV-08

One Linux job on every PR and push to `main`: `uv sync --locked`, `ruff check`, `ruff format --check`, `pyright`, `pytest`.

- Any failing check fails the job.
- It takes under 2 minutes on a typical PR.

#### P0-03 · Add issue and PR templates and the Project board

chore, area:build · after P0-01

Issue templates (feature, bug, spike, upstream), a PR template with the D-92 sections, the "PyCon US Flet" Project, and `main` protection.

- Templates exist in `.github/`; the spike template has a verdict section.
- The Project has Status Todo / In progress / In review / Done; agents add every issue and PR to it. Its built-in workflows (auto-add, Todo on add, Done on close or merge) are on; the owner enabled them in the web UI (#118).
- AGENTS.md says how `main` is protected (ruleset, or convention on a private Free plan).

#### P0-04 · Apply the mobile build configuration from the S5 verdict

chore, area:build · after S5, P0-01 · NATIVE-01, NATIVE-02, NATIVE-03

Turn the S5 verdict into the repo setup on top of P0-01's Flet pin: the `[tool.flet]` tables with placeholder identity, splash and boot colours, the Roboto pubspec entry, the iOS signing configuration, template device floors, and the build number from the commit count.

- `flet build apk` and `flet build ipa` succeed from a clean checkout with the documented commands.
- The device shows the placeholder name and icon, `__version__` and the build number; no PSF marks.
- Bumping the pin is a one-line change to `.flet-ref` plus `uv lock`.

#### P0-05 · Complete docs/development.md from the S5 verdict

docs, area:build · after P0-04

The contributor guide exists as a plan; turn it into verified instructions: dev loop, packaged builds, signing (never in the repo), tests, the Flet pin bump, and the open items S5 answered (Roboto fonts, companion client, sizes).

- A new contributor runs the app on a phone with the D-81 dev loop (`flet debug android|ios`, or a companion client built from `client/` at the pin) and runs the tests by following it.
- AGENTS.md's "Development setup" points to it.

#### P0-06 · Add the manual Android build workflow (build-android.yml)

ci, area:build · after P0-04 · DEV-08

On manual dispatch and `v*` tags, build a debug-signed APK with the pinned Flet and upload it as an artifact.

- Manual dispatch produces an installable APK.
- It uses the same pin and commands as development.md.

#### P0-07 · Add the weekly public-feed check (feed-check.yml)

ci, area:data · after P0-13 · DEV-08

`tools/check_feed.py` runs our decoder, processor and invariants on the live feed; a weekly workflow runs it.

- Exits 0 on today's 2026 feed and non-zero on a broken fixture.
- A 404 (next year not published yet) is reported clearly, not as a crash.

### P0-E2 · P0 spikes S1-S5

Time-boxed spikes (half a day to a day) that retire the riskiest assumptions; each closes with a verdict in `docs/spikes/` and, where it decides something, a decisions.md update.

#### S1 · Spike: does the packaged app run well on Android and iOS with our stack?

test, area:build

A release-build stub with `httpx`, `zoneinfo` + `tzdata`, `sqlite3`, SharedPreferences and SecureStorage fetches, parses and persists the 2026 feed on an Android emulator and the iPhone (D-102).

- Verdict in `docs/spikes/01-packaged-runtime.md`: cold start and first launch, `.pyc` on and off.
- `FLET_APP_STORAGE_DATA` survives kill, relaunch and an update install.
- Decides lazy imports and parsing off the UI loop; D-80 confirmed or revised from the iPhone's numbers (moved to #121 by S1), with the emulator's recorded as the Android regression baseline (D-112).

#### S2 · Spike: can the busiest day render and update fast in components mode?

test, area:schedule

Render the 2026 Friday (about 26 slots, 110 rows) with realistic rows; measure star-tap and search-as-you-type latency on release builds on the iPhone, and compare the variants on an Android emulator (relative numbers only, D-102).

- Verdict in `docs/spikes/02-day-list.md` with numbers per variant and device (done: D-153..D-159; the iPhone's release numbers in #121).
- Row architecture and `build_controls_on_demand` recorded in decisions.md.

#### S3 · Spike: is a stdlib HTML-to-Markdown converter good enough for the feed?

test, area:data

Convert every HTML field of the 2025 and 2026 feeds with an `html.parser` prototype and render 20 samples with `ft.Markdown` on a phone.

- Verdict in `docs/spikes/03-html-markdown.md` with the tag census.
- The supported tag list is decided; samples become P0-15 fixtures.

#### S4 · Spike: do the Router, the drill route and native back gestures behave?

test, area:shell

Walk Now → session → speaker → session → room through a recursive drill route with Android back, predictive back, the iOS edge swipe, tab re-taps, resume and the modal `/search`.

- Verdict in `docs/spikes/04-router-back.md` (done: D-141..D-149); per-level params confirmed or the `s~id` fallback chosen.
- `PageTransitionsTheme(android=PREDICTIVE, ios=CUPERTINO)` confirmed on devices (O-2).

#### S5 · Spike: can we build and ship internally from the pinned Flet 1.1?

test, area:build

Prove the D-81 setup: `flet build apk`, `aab` and `ipa` from a pinned flet-dev/flet commit, and one TestFlight internal upload with a throwaway bundle id, installed on the iPhone; `flet build ios-simulator` for the simulator.

- Verdict in `docs/spikes/05-build-and-ship.md` with exact commands and versions.
- TestFlight processed the build, or the blocker is filed upstream. *(Moved to the iPhone session, #121: it needs owner-only portal steps, D-101.)*
- AAB size, default minSdk, and the three Roboto weights rendering on iOS (D-26) recorded.

### P0-E3 · Data core and offline data

The pure `core/` feed pipeline with its tests, year data, time rules, and offline-first loading.

#### P0-08 · Load year data from data/<year>/conference.toml

feature, area:data · after P0-01 · DATA-34, DATA-14, DATA-28

`config.YEAR` selects `data/<year>/`; `tomllib` loads `conference.toml` into frozen dataclasses, and the loader is the schema.

- No year, date or URL is hard-coded outside the data files.
- A malformed file fails naming the file, key and problem; a test loads every year.
- `track_name(key, fmt)` covers `short`, `plural` and `long`.

#### P0-09 · Add the clock and conference-local time formatting

feature, area:data · after P0-08 · DATA-12, SCHED-18

One `clock.now()` and `core/timefmt.py`: aware datetimes in the year's zone via `zoneinfo` + `tzdata`, one `today()`, local day buckets and 12/24-hour labels.

- No fixed UTC offsets; `core` functions take `now` as an argument.
- Time tests run under `America/Los_Angeles` and `Pacific/Kiritimati` and cover DST and midnight.

#### P0-10 · Decode the feed into frozen models

feature, area:data · after P0-09 · DATA-01, DATA-13, DATA-24, DATA-26

`core/models.py` and the decode half of `core/feed.py`: raw bytes to a `Conference` of days, time groups, sessions, speakers, sprints, posters and job listings, with string ids.

- Both recorded feeds decode; ids are unique `str`s; every time group has an aware start.
- A bad slot is skipped and logged and never blanks the schedule.

#### P0-11 · Port the processing rules: filtering, open spaces, collapsed rows, poster details

feature, area:data · after P0-10 · DATA-04, DATA-05, DATA-06, DATA-07

The first half of Ionic's `processData`, one small function and one named test per rule.

- Rules: placeholder filter (posters and breaks exempt), open spaces as sessions, collapsed poster and break rows with Lunch per day, `poster-detail-<k>` sessions.
- Synthetic ids keep Ionic's shapes; display quirks are not reproduced (D-41).

#### P0-12 · Port the processing rules: names, flags, Job Fair, speakers and rooms

feature, area:data · after P0-10, P0-08 · DATA-08, DATA-09, DATA-10, DATA-11, DATA-15, DATA-16, ROOM-06

The second half: title and location cleaning, pre-registration and Spanish flags, the Job Fair override, speakers linked by name, and the rooms index.

- One named test per rule on both feeds.
- `slugify_room()` in `core/slugs.py` is the only room-slug function.

#### P0-13 · Add the days query, feed invariants and the processed-model snapshot

test, area:data · after P0-11, P0-12 · DATA-17, SCHED-19

`core/queries.days()`, about ten named invariants, and a reviewed JSON snapshot of our processed model for each recorded feed.

- Invariants pass on both feeds; snapshot diffs are readable and updated deliberately.
- The processor logs its duration.

#### P0-14 · Capture Ionic's reference output once

test, area:data · after P0-13 · SCHED-19

Run Ionic's `processData` once on both feeds, commit the outputs, and compare our model through a documented normaliser.

- Every difference is fixed or listed as intended with a feature id.
- CI and contributors need no Node.

#### P0-15 · Convert feed HTML to Markdown

feature, area:data · after S3, P0-10 · DATA-25

`core/html_md.py` on stdlib `html.parser`, limited to the S3 tag census, with absolute links, a plain-text fallback and a text-only form for search.

- Tests use real feed snippets, including unknown tags.
- No markup reaches the search text.
- No new dependency.

#### P0-16 · Add the storage service and durable feed cache

feature, area:data · after S1, P0-01 · STORE-01

`services/storage.py`: one table of `pycon.`-prefixed SharedPreferences keys, and atomic files in the durable data directory.

- Every prefs key is listed once with its type and default.
- Writes go through a temp file and `os.replace`; a corrupt cache is deleted and reported.

#### P0-17 · Bundle a feed snapshot for offline first launch

feature, area:data · after P0-10 · NEW-03

`tools/update_snapshot.py` writes `data/<year>/conference.json`; the app uses it whenever no cache exists.

- The snapshot decodes and passes the invariants in a test.
- Updating it is one documented command.

#### P0-18 · Add the Conference store: cache-first load and single-flight refresh

feature, area:data · after P0-16, P0-17, P0-13 · DATA-01, DATA-02

An `@ft.observable` `Conference` store that publishes the best local copy at once, then refreshes once with `httpx.AsyncClient` and caches only after a good parse.

- Two concurrent refreshes make one request.
- Offline, HTTP errors and corrupt payloads keep the data and set a visible error state.
- Tests use `httpx.MockTransport`, never the network.

### P0-E4 · App shell

Boot gate, theme, error boundary, routes with the drill, the tab bar, the scaffold, More and the first `flet test` flow; details are stubs.

#### P0-19 · Build the light and dark themes with brand tokens and Roboto

feature, area:theme · after P0-01 · THEME-02, THEME-03, THEME-11, THEME-12

`theme.py`: `build_theme(*, dark, high_contrast)` (architecture §15) seeded from `#3B3EA9` with brand overrides, bundled Roboto, left-aligned titles, and a frozen `Tokens` behind `use_tokens()`.

- A test checks every text/background pair in light and dark at 4.5:1 or better.
- Identical on Android and iOS; nothing sets `adaptive=True`.

#### P0-20 · Add the entry point, Prefs store and boot gate

feature, area:shell · after P0-18, P0-19 · SHELL-01, DATA-35

`src/main.py` calls `page.render_views(App)`. `App` writes out its providers and shows a boot view until `Prefs.loaded` and the first feed publish.

- No theme flash; the first frame shows cached or bundled data, never a network wait.
- Hooks are unconditional; async APIs are awaited only in `async def` (D-70).

#### P0-21 · Add the error boundary, logging and capabilities.py

feature, area:quality · after P0-20

`services/errors.py` (logging and `@report_errors`; asyncio's default exception handler is kept, D-163) and `capabilities.py` (import-time constants gated on `flet.utils.is_embedded()`).

- A raising handler logs and shows "Something went wrong" without ending the session; `CancelledError` is re-raised.
- When not embedded, every capability is `False` (unit test).

#### P0-22 · Define routes with the recursive drill and stub screens

feature, area:shell · after S4, P0-20 · SHELL-03, SHELL-04

`routes.py`: five roots, `/more/<page>`, the global modal `/search`, the recursive drill under every root, link helpers (`drill_href()`), `use_query()`, and a pure `parent_of(route, search_base="/now")` for our own `page.on_view_pop` (D-19).

- `/schedule/session/42/speaker/17/session/99` builds three views with their own params.
- `parent_of()` is unit-tested on every route shape, including a page whose parent segment is not a page (`/more/staff/lead` → `/more`); search → result → Back returns to the results (D-19).
- Unknown routes show a not-found view with a way back; quoted ids round-trip through the link helpers.
- The Schedule root stub reads the `Conference` store and lists the day names with session counts and a source label (`schedule.source`: bundled, cached or network, with `fetched_at`), so "bundled first, a refresh replaces it" is visible on a phone.

#### P0-23 · Add the bottom navigation bar and Back behaviour

feature, area:shell · after P0-22 · SHELL-05, SHELL-16

`ft.NavigationBar` with Now, Schedule, My schedule, Map and More, on tab roots only (D-144); re-tapping the active tab scrolls its root to the top; Back on a non-Now root goes to Now, and Back on Now exits.

- The bar is the same for every user and on both platforms.
- Back pops exactly one view; iOS edge swipe and Android predictive back work.

#### P0-24 · Add AppScaffold: app bars, safe areas and system bars

feature, area:shell · after P0-19, P0-22 · INFO-01, SCHED-27, THEME-10, NATIVE-08

`AppScaffold` in `ui/scaffold.py`: the bar on roots; on details a surface `AppBar` with an always-visible title and the Material back arrow; bodies in `ft.SafeArea`.

- No content under system bars with 3-button or gesture navigation (#311).
- Titles are headers for screen readers; status- and navigation-bar icons stay visible in light and dark (`Theme.system_overlay_style`, D-12).

#### P0-25 · Build the More tab as a flat sectioned list

feature, area:shell · after P0-24 · SHELL-09

One list under section headers: Programme, Expo & sponsors, At the venue, About, You (Staff tools in P3); only entries whose screens exist.

- Every row pushes a view or opens an external link; no dead rows.
- Rows are at least 48 dp; headers are headers.

#### P0-27 · Set up the flet test harness and a shell smoke flow

test, area:quality · after P0-04, P0-23, P0-25

`tests/ui/` with `conftest.py` (the `feed_url` fixture), `helpers.py` (`wait_for_id`, `wait_for_text`, `tap_id`) and one flow, `test_shell_starts`: the test build starts, the five `app.nav.*` tabs are found, and the Schedule stub shows the bundled days and its `schedule.source` label.

- The shell flow passes with `flet test` on an Android emulator and an iOS simulator; the commands are in development.md.
- `tests/ui` stays out of `ci.yml` (`--ignore=tests/ui`, D-84).

### Other issues in this milestone

#### P0-00 · P0 status

chore, area:quality

Pinned status issue, updated weekly: done, next, blocked, decisions, numbers.

- Pinned and updated weekly while P0 is active.
- Closed by P0-26, which opens the P1 status issue.

#### P0-26 · P0 exit: device check and verdicts

test, area:quality · after P0-02, P0-03, P0-04, P0-05, P0-06, P0-07, P0-14, P0-15, P0-21, P0-23, P0-25, P0-27, S1, S2, S3, S4

Run the P0 exit criteria with packaged builds on an Android emulator, an iOS simulator and the iPhone (D-102); record results in the P0 status issue.

- Every P0 exit criterion is ticked with evidence.
- The P1 status issue is opened and pinned.

## 4. P1 Attendee core

**Goal.** The attendee core is good enough to demo, and to use for a whole simulated conference day.

**Exit criteria** (PLAN §7):
1. **Core journeys in airplane mode.** On an Android emulator and the iPhone, with packaged builds:
   - open on Now, then session → speaker → session → Back;
   - star and unstar with Undo;
   - My schedule shows overlaps;
   - search finds sessions, speakers and rooms on any day;
   - filters stay visible and persist.
2. **Simulated conference day.** With the fake clock and the 2026 feed:
   - Now respects end times and shows your next session;
   - Jump to now works;
   - nothing scrolls unasked (#313), and Back pops one step (#279).
3. **Refresh and time.** A failed refresh (offline, HTTP error, corrupt payload) keeps the last good data, and the time-zone and id tests pass under two machine time zones.
4. **Accessibility.** TalkBack and VoiceOver complete search → favourite → detail. Text at 200 % clips no action, and the contrast tests are green.
5. **Performance.** Measured against D-80 and recorded; there are no known crashes.
6. **Demo.** A 2–3 minute recording of the demo slice exists.

**Early spike.** S6 (reliable local reminders) runs during P1 on the upstream track, so that E3 can land in P2.

**Order.**
1. **The building blocks** (P1-E1). Build the Developer screen with the fake clock (P1-28) early too: Now and Jump to now can only be checked on a device with it.
2. **The demo slice:**
   - Schedule (P1-07..P1-10);
   - Session detail (P1-11..P1-13);
   - My schedule and Now (P1-14..P1-16);
   - Search (P1-17, P1-18).
3. **The programme screens** (P1-E6).
4. **The quality issues and the exit** (P1-29..P1-33).

**Decisions in this milestone:**
- O-4, app identity (P1-34): before the first real TestFlight upload.
- O-6, CFP (P1-35): around 2026-11-20.
- O-1, the bottom bar (P1-36): after a week of dogfooding.

### P1-E1 · Attendee building blocks

Shared state and components that every attendee screen uses.

#### P1-01 · Add the local-first Favorites store

feature, area:schedule · after P0-16, P0-20 · STORE-02, SCHED-12

`@ft.observable Favorites` in its own context, saved per year under `pycon.<year>.favorites`, with `toggle`, `add_many` and `remove_many`, each returning what Undo needs (built as D-172: `ids` is a `frozenset[str]`).

- Favourites survive relaunch; a 2026 favourite never marks a 2027 session.
- A toggle notifies once; unit tests cover Undo and `add_many`.

#### P1-02 · Add track badges with a tested palette

feature, area:theme · after P0-19, P0-08 · THEME-08, SCHED-20

`TrackBadge` in `ui/badges.py`: a text pill with a tonal fill per track key, light and dark; "En Español" is the tonal pair `#FFD7F3` / `#5E0058`, inverted in dark (D-25).

- A test checks every badge pair at 4.5:1 or better in both themes.
- Track names come from `track_name()` everywhere.

#### P1-03 · Add SessionRow, NoticeRow, FavoriteButton and TimeGutter

feature, area:schedule · after P1-01, P1-02, S2 · SCHED-03, SCHED-04

The row family (`ui/rows.py`, `ui/badges.py`) in the architecture S2 chose (memoised rows inside memoised slots and day lists, D-153): rows read as one phrase, and a 48 dp star is a separate stop with Undo on removal.

- No fixed heights; rows reflow at 200 % text.
- Screen readers read one phrase per row plus the star's name and state.

#### P1-04 · Add the status strip and refresh triggers

feature, area:data · after P0-18, P0-24 · DATA-03, DATA-31, SCHED-13, SCHED-14

`StatusStrip` in `ui/scaffold.py` shows only while refreshing, stale or offline, with Refresh; `Conference.start_refresh()` runs on start, on stale resume, every 15 min on Now or Schedule, and on demand.

- Refresh never clears the cache; failures keep the data and say so.
- The 15-minute timer runs only while Now or Schedule is visible.

#### P1-05 · Add EmptyState, SkeletonList and LinkTile

feature, area:shell · after P0-24 · INFO-14

Shared states in `ui/states.py` (one sentence, one action; skeletons only with no data) and `LinkTile` in `ui/rows.py` with the link rule for in-app, web, app and `tel:`/`mailto:` targets.

- External rows are links for screen readers and say they open in the browser.
- Every empty state names a way out.

#### P1-06 · Honour reduced motion and re-read accessibility features on resume

feature, area:theme · after P0-20 · THEME-09

Read `SemanticsService().get_accessibility_features()` at start and on RESUME; with reduced motion, animations, shimmer and scroll jumps are instant.

- Changing the OS setting and resuming changes behaviour without a restart.

### P1-E2 · Schedule

The Schedule tab of the demo slice.

#### P1-07 · Add the schedule queries

feature, area:schedule · after P0-13 · DATA-18, DATA-20, DATA-30, SCHED-17

Pure view-model functions: a day's slots with rows ordered by start then room, track exclusion, and a sorted session list for track pages.

- Tests on both feeds cover empty days and all-excluded filters.
- My schedule, Now and Search never use the filtered query.

#### P1-08 · Build the Schedule screen: day tabs and slot list

feature, area:schedule · after P1-03, P1-07, P1-04, S2 · SCHED-01, SCHED-02

Day tabs with dates and a today badge, then one list item per time slot with the `TimeGutter`.

- Today is selected during the conference, day 1 otherwise; sprint days link to Sprints.
- Returning from a detail keeps the day and scroll position.

#### P1-09 · Add the track filter: preference, sheet and visible state

feature, area:schedule · after P1-08 · STORE-09, SCHED-09, SCHED-10

A bottom sheet of grouped filter chips with a live "Show N sessions", and a visible summary under the day tabs whenever a track is hidden, the default included (D-20).

- The default hides open spaces and says so; "Show all" restores everything.
- Chips apply immediately and persist; filters apply to Schedule only.

#### P1-10 · Add Jump to now and the one-time auto-scroll

feature, area:schedule · after P1-08, P1-28 · SCHED-15, SCHED-16

Scroll to the current slot once per app session and on a "Jump to now" button; never on Back, tab return, refresh or a filter change (#313).

- On a simulated conference day the list opens at the current slot once, then never moves unasked.

### P1-E3 · Session detail

Everything about one session, with the decision to attend first.

#### P1-11 · Build session detail: header, When and where, star

feature, area:schedule · after P1-03, P0-22 · SESS-01, SESS-02, SESS-03

Badges and a selectable title, then a "When and where" card (time with status, one room tile, Pacific Time note), registration guidance, and the star in the app bar.

- Unknown ids show an empty state with "Open schedule"; removed sessions keep content with a banner.
- The room tile pushes room detail; extra rooms sit in an `ExpansionTile`.

#### P1-12 · Show the session description and speakers

feature, area:schedule · after P1-11, P0-15 · SESS-06, SESS-07

The description as selectable Markdown with links in the in-app browser, then speakers with avatars that push speaker detail.

- Relative links open as absolute URLs; missing photos show initials.
- Screen readers announce links as links (device check).

#### P1-13 · Add Share, the posters list and open-space extras

feature, area:schedule · after P1-11 · NEW-06, SESS-09, SESS-11

Share a session's title, time, room and public URL; list posters under the Posters row; show open-space images and their site link.

- Synthetic ids share text without a URL (unit test).
- Back from a poster returns to the Posters detail.

### P1-E4 · My schedule and Now

The two hero features: a personal agenda, and a Now that answers "what next?" correctly.

#### P1-14 · Add the agenda and Now & Next logic

feature, area:schedule · after P0-13, P0-09

Pure `my_schedule()` and `now_next()` in `core/queries.py`: conference phase, happening now (`start <= now < end`), up next, your next saved session, and overlaps between saved sessions.

- Fixed-`now` tests cover before, between slots, the last slot of a day and after.
- A slot is never "happening" after its end; overlap detection is tested.

#### P1-15 · Build the My schedule tab

feature, area:schedule · after P1-14, P1-03 · NEW-01, SCHED-07, SCHED-08

Saved sessions by day in time slots, past ones collapsed, "Overlaps with ..." on both rows, removal with Undo, and a helpful empty state.

- Never filtered by Schedule filters; the overlap is part of the spoken row.

#### P1-16 · Build the Now tab

feature, area:schedule · after P1-14, P1-03, P1-04, P1-28 · SCHED-25, SCHED-26

A status header, "Your next session", Happening now with progress, Up next, and states for before, between, after the day and after the conference.

- Rows push detail and Back returns to Now.
- It recomputes every 60 s only while visible, and at once on resume.

### P1-E5 · Search

One search over sessions, speakers and rooms on all days, replacing per-page searches.

#### P1-17 · Add search folding and matching

feature, area:schedule · after P0-13, P0-15 · DATA-18, DATA-19

Pure `fold()` (NFKD plus casefold) and an index over session text, speakers and rooms with AND matching, grouped by type and day (built as D-180: the fold also folds typography and drops apostrophes; index and matching in `core/search.py`).

- "cristian" finds "Cristián"; markup never matches.
- Index build time is logged.

#### P1-18 · Build the global search screen

feature, area:schedule · after P1-17, P1-03, P0-22 · NEW-02, SCHED-05, SPKR-02

The global modal `/search?scope=`: an autofocused field, scope chips, a 250 ms debounce, grouped results that push details, and the query kept on Back.

- Back from a result returns to the results with the query intact.
- "No results" says search covers all days and ignores filters.

### P1-E6 · Programme screens

Speakers, rooms (the Map tab in P1), tracks, keynotes, open spaces, lightning talks and sprints.

#### P1-19 · Build the speakers list

feature, area:speakers · after P1-17, P0-25 · SPKR-01, DATA-21

More › Programme › Speakers: letter headers, initials avatars, first session plus "+1 more", sorted by displayed name, with an inline filter.

- No paging and no blocking loader; pseudo-speakers are excluded.

#### P1-20 · Build speaker detail and verify cross-link Back

feature, area:speakers · after P1-19, P1-12 · SPKR-03, SESS-12

Avatar and name, the speaker's sessions with stars before the bio, and a not-found state.

- session → speaker → session → room pops one step at a time on both platforms.
- Now → detail → Back returns to Now.

#### P1-21 · Show the rooms list on the Map tab

feature, area:rooms-maps · after P0-12, P0-23 · ROOM-01

In P1 the Map tab lists rooms: natural sort, session counts, "Now: <title>" on conference days, and an "Other locations" group.

- Skeleton, then content or an empty state; never loading forever.
- Rows push room detail.

#### P1-22 · Build room detail with the session highlight

feature, area:rooms-maps · after P1-21, P1-11 · ROOM-02, ROOM-03

Day tabs, "Now in this room", and sessions; opened from a session, that row is highlighted for 2 s and scrolled to once.

- The highlight compares ids as strings; returning does not re-scroll.

#### P1-23 · Build the Tracks hub, track pages and session types

feature, area:schedule · after P1-02, P1-03, P1-07 · SCHED-21, SCHED-22, EVT-04, DATA-29, SHELL-10

One hub merging the track links and the session-types legend; track pages at `/more/tracks/<slug>` list sessions by day.

- Unknown slugs show a not-found state.
- The filter sheet's "What do these mean?" opens the hub.

#### P1-24 · Add a whole track to My schedule

feature, area:schedule · after P1-23, P1-01 · SCHED-24

Track page overflow "Add all to My schedule", straight to a SnackBar "Added N sessions · Undo" (no dialog: it is reversible, D-29).

- Adds the whole track, not only what is on screen; Undo restores the previous list exactly.

#### P1-25 · Add keynotes: data, session enrichment and the Keynotes screen

feature, area:speakers · after P0-08, P1-11 · SESS-08, SPKR-04

Keynotes and panels move to `content.toml`, keyed by session id; session detail shows the enrichment, and More › Programme › Keynotes shows one card each.

- The loader fails on an unknown session id (unit test).
- No keynote text remains in code.

#### P1-26 · Build the Open spaces and Lightning talks pages

feature, area:schedule · after P1-03, P1-05, P1-23 · EVT-01, EVT-02, EVT-03

Open spaces by day with a "Propose an open space" action; one Lightning talks page merging the info copy, the sign-up link and the sessions.

- Day tabs come from the data (no "Sunday" mislabel); rows push detail.
- Lightning talks appear once in More.

#### P1-27 · Build the Sprints screen

feature, area:schedule · after P0-10, P1-05, P1-04 · EVT-05, EVT-06, EVT-07, EVT-08

Project cards with an all-words filter and links to sprint info and project submission.

- The filter ignores markup; refresh never wipes the cache.

### P1-E7 · Developer tools and P1 quality

The Developer screen and fake clock, smoke flows, accessibility and performance.

#### P1-28 · Add the Developer screen, fake clock and a minimal About this app

feature, area:quality · after P0-09, P0-25 · DEV-01

A minimal About this app with version and build; 7 taps on the version unlock the Developer screen: fake clock, feed URL, time zone and capability flags.

- Setting the fake clock changes Now and Schedule without a restart; clearing it restores real time.
- A feed URL override applies on the next refresh without a restart.
- The version row and the Developer controls carry the identifiers `about_app.version`, `developer.reset`, `developer.fake_clock`, `developer.feed_url` and `developer.apply` (naming per decisions §M); in a packaged build the screen unlocks after 7 taps on the version row.

#### P1-29 · Add developer data actions: clear cache, reset app, share log

feature, area:quality · after P1-28, P0-21 · DEV-04, DEV-05, STORE-13

"Clear cached feed", "Refresh now", a confirmed "Reset app", and "Share log".

- Destructive actions are confirmed and list what is lost.
- The log holds no secrets or emails.

#### P1-30 · Add the first UI smoke flows

test, area:quality · after P1-08, P1-15, P1-18, P1-20, P1-28, P1-29

`flet.testing.FletTestApp` flows F1–F5 on the P0-27 harness, found by semantics identifiers: offline start, day switch, search, favourite with Undo, session → speaker → session → Back.

- Five flows pass on an Android emulator and an iOS simulator; commands are in development.md.
- `open_developer()` and `fresh_start()` drive the Developer screen as a person would; F1 sets an unreachable feed URL there and sees the bundled rows and the offline strip.

#### P1-31 · Accessibility pass on the demo slice

test, area:quality · after P1-08, P1-11, P1-15, P1-16, P1-18

TalkBack (on an Android emulator) and VoiceOver (on the iPhone) complete search → favourite → session detail; check names, states, 200 % text and 48 dp targets.

- Results are recorded in the P1 status issue; every finding is fixed or filed.

#### P1-32 · Measure performance against D-80

test, area:quality · after P1-08, S2

Measure cold start, feed processing and scrolling the busiest day on release builds on the iPhone against D-80, and on an Android emulator as a relative regression signal (D-102).

- Numbers recorded with device, OS, build and Flet pin; each miss has an issue.

### Other issues in this milestone

#### P1-33 · P1 exit: simulated conference day, device checklist and demo recording

test, area:quality · after P1-06, P1-09, P1-10, P1-13, P1-22, P1-24, P1-25, P1-26, P1-27, P1-29, P1-30, P1-31, P1-32

Run the P1 exit criteria on packaged builds in airplane mode, with a fake-clock conference day and the D-79 checklist; record the demo slice.

- Every exit criterion is ticked with evidence; the recording is linked.
- The P2 status issue is opened and pinned.

#### P1-34 · Decide the app identity: bundle id, name, icon, URL scheme (O-4)

design, needs-decision, area:build

Pick an owner-controlled bundle id, a neutral name, our own icon, and the deep-link scheme and host; no PSF marks on anything that leaves our devices.

- O-4 settled in decisions.md and applied in `[tool.flet]` before the first real TestFlight upload.

#### P1-35 · Decide whether to submit a PyCon US 2027 CFP proposal (O-6)

chore, needs-decision, area:quality

Decide around 2026-11-20 from P1 progress; if yes, one talk framed as a community showcase, submitted before the expected close around 2026-12-18 (dates UNCONFIRMED).

- O-6 settled in decisions.md; a draft links the demo recording if yes.

#### P1-36 · Revisit the bottom-bar destinations after a week of dogfooding (O-1)

design, needs-decision, area:shell · after P1-15, P1-16

After a week with the P1 build, confirm Now · Schedule · My schedule · Map · More and opening on Now, or propose a change with the reason.

- O-1 settled; D-13 and D-14 lose their provisional mark or are superseded.

#### S6 · Spike: can local reminders be reliable when the app isn't running?

test, area:notifications

A release build schedules a reminder 2 minutes ahead; test it with the app killed, the phone locked, a cold-start tap and over 64 candidates on the iPhone, and with the app killed, the screen locked, a reboot, exact alarms denied and a cold-start tap on an Android emulator (D-102).

- Verdict in `docs/spikes/06-reminders.md`; the E3 scope (API, platform config, limits) is written down.
- The "at most 60 pending" policy (D-59) is confirmed or revised.

#### UP-U1 · Upstream: RefreshIndicator in Flet core (U1)

upstream, area:shell

Add `RefreshIndicator(content, on_refresh)` to flet-dev/flet; this issue links the flet-dev issue and PR.

- The flet-dev PR is merged or its status recorded; an app issue exists for the swap after a pin bump.

#### UP-U15 · Upstream: non-fatal handler and effect errors (U15)

upstream, area:quality

A non-fatal mode for handler and effect exceptions with a Python error hook in flet-dev/flet, so an unexpected exception no longer ends the session (F4).

- The flet-dev PR is merged or its status recorded; an app issue exists to delete `@report_errors`.

## 5. P2 Conference companion

**Goal.** Everything an attendee needs at the venue, offline, plus reminders.

**Exit criteria** (PLAN §7):
1. **Matrix.** Every P2 matrix row is done, or was re-dispositioned with a reason.
2. **Venue data offline.** In airplane mode, these work from bundled year data, and the loader test is green:
   - floor plans with room pins;
   - the expo map and list;
   - Wi-Fi, Help & safety and venue hours.
3. **Reminders.**
   - With E3 pinned: a reminder fires with the app killed (the iPhone and an Android emulator) and after a reboot of the emulator, the tap opens the session, and the reminder moves with the session.
   - Without E3, the interim says so.
   - A denied permission never blocks a task.
4. **Change log and links.** The change log shows a simulated change from a fixture feed pair, with saved sessions first. Deep links and reminder taps land with a back stack.
5. **Device checklist.** The D-79 checklist passes, including high contrast, tablets and screen readers on three new flows.
6. **Unaided use.** Someone other than the owner installs an internal build and, unaided, finds a room, saves a session and copies the Wi-Fi password.

**Early spikes.**
- S7 (real floor plans with about 60 hotspots in `InteractiveViewer` on a low-RAM phone: a small-RAM Android AVD and the iPhone until a real one is borrowed, D-102) opens P2-E1.
- S8 (a minimal `mobile_scanner` extension in release builds) opens UP-E1 on the upstream track, so that E1 can land before P3.
- S9 (`flet test linux` in CI) may run from P2 on; a green result is proposed as a separate workflow through `needs-decision` (D-78).

**At the start of P2:**
- split each epic into sub-issues like P0 and P1;
- open the status issue;
- move anything that slips to `later` through `needs-decision`.

### P2-E1 · Epic: map, floor plans and location cards

epic, area:rooms-maps · DATA-32, DATA-33, MAP-01, MAP-02, MAP-03, MAP-05, MAP-06, MAP-07, MAP-08, ROOM-04, ROOM-05, INFO-12, INFO-13, SESS-10

Map sub-tabs (Rooms, Floor plans, Expo, Job fair) with state in `ViewMemory` (D-18); floor plans and room pins from `map.toml`; a floor viewer with zoom buttons as well as pinch; `LocationCard` on room and session detail and info pages; Places search; sprint-only rooms; the 3D tour as a link. Spike S7 goes first.

### P2-E2 · Epic: expo hall and job fair

epic, area:rooms-maps · after P2-E1 · EXPO-01, EXPO-02, EXPO-03, EXPO-04, EXPO-05, MAP-04, SPON-10

The expo map with booth hit areas, an equal list view for screen readers, a booth card, `?booth=N` selection (no camera move until U3), honest "not on the map yet", and the job fair plan with tables.

### P2-E3 · Epic: sponsors and job listings

epic, area:sponsors · DATA-22, SHELL-08, SPON-01, SPON-02, SPON-03, SPON-04, SPON-05, SPON-06, SPON-07, SPON-08, SPON-09, SPON-11

Tiered Sponsors, sponsor detail with labelled actions, open roles from real anchors, job listings, the Now sponsor spotlight and credits from year data. No rotating strip (D-37).

### P2-E4 · Epic: info pages and venue

epic, area:info · INFO-02, INFO-05, INFO-06, INFO-07, INFO-08, INFO-09, INFO-10, INFO-11, DATA-23, MAP-09, MAP-10, MAP-11

About PyCon US, About the PSF, Help & safety (with the Code of Conduct and "Report a concern" first), Wi-Fi with Copy, Social, and Venue & hours with "Open now" and directions, all from `content.toml`.

### P2-E5 · Epic: Welcome, Settings and high-contrast themes

epic, area:theme · SHELL-02, STORE-07, STORE-08, THEME-01, THEME-04, THEME-05, THEME-06

One Welcome screen with honest attribution; Settings with Appearance and a High contrast switch; two hand-authored high-contrast schemes at 7:1 for text, with outlined badges.

### P2-E6 · Epic: reminders and calendar

epic, area:notifications · after S6 · NOTIF-01, NOTIF-03, NOTIF-05, NOTIF-06, NOTIF-07, NOTIF-10, NEW-05, STORE-10, DEV-06, NATIVE-06, SESS-04, SESS-05

Pure `plan()` and `apply()` for local reminders (saved sessions and conference moments), reminder settings, permission in context, the honest interim until E3 is pinned, and `.ics` for a session or the whole of My schedule.

### P2-E7 · Epic: schedule change log (#312)

epic, area:schedule · NEW-04

A pure `diff(old, new)` after each good refresh, stored per year; a "Changed" chip for 24 h, a Review SnackBar, a Now card, and `/schedule/changes` with saved sessions first.

### P2-E8 · Epic: deep links

epic, area:shell · after P1-34 · NEW-07

`<scheme>://<host>/<route path>` links, with scheme and host set in both per-platform `deep_linking` tables; links and reminder taps land with a back stack.

### P2-E9 · Epic: tablet layout and About this app

epic, area:shell · SHELL-14, INFO-03, INFO-04

`NavigationRail` from 600 dp; the full About this app (versions, feed age, licences, "Not an official PSF app"); Share log with plain diagnostics.

### UP-E3 · Epic (upstream): scheduled local notifications (E3)

epic, upstream, area:notifications

Scheduling in the official flet-dev/flet#6948 notifications extension, sized by S6. The app ships the D-60 interim until a pin bump brings E3 in.

### UP-SMALL · Epic (upstream): small core gaps (U16, U17, U10, U2, U3, U9, U18)

epic, upstream, area:quality

`PageMediaData.text_scale_factor`, an accessibility-features change event, `AppBar.bottom`, sticky headers, an absolute `InteractiveViewer` transform, `use_route_search`, and U18 (per-level modal pops, D-19). None blocks a phase exit.

### UP-E1 · Epic (upstream): barcode-scanner extension (E1)

epic, upstream, area:staff

Spike S8 first (a minimal `mobile_scanner` control in release builds for Android and iOS: a printed QR on the iPhone, the virtual scene camera on an Android emulator), then a clean-room extension in flet-dev using `material_ui`. The staff tools never depend on it.

### Other issues in this milestone

#### UP-U4 · Upstream: page.get_app_info() (U4)

upstream, area:build

Add `page.get_app_info()` (version, build number, package name) to Flet; the app uses `__version__` until a pin bump brings it in.

- The flet-dev PR is merged or its status recorded; an app issue exists for the swap.

## 6. P3 Accounts & staff tools

**Goal.** The private-API features, built faithfully against the local mock, with the scanner as the showcase. The app never calls private PSF endpoints (D-06, D-51).

**Exit criteria** (PLAN §7):
1. **Tools against the mock.** Every tool kept under O-7 completes scripted scenarios on an Android emulator and the iPhone, with manual and HID entry, and with the camera when E1 is bundled (the iPhone's camera, or the emulator's virtual scene camera).
2. **Offline queue.**
   - Airplane-mode scans survive kill and restart.
   - Under idempotent mock semantics each record syncs exactly once; under non-idempotent ones nothing is lost, and a duplicate occurs only after a lost response, where it is detected and shown (D-57).
   - Failures are visible, with Retry.
   - Signing out with unsynced rows asks first.
3. **Faults and roles.** Fault injection and the Ionic-derived signing vectors pass. A wrong role cannot reach a tool.
4. **PSF hosts.** A test proves the client refuses PSF hosts.
5. **Printed badges.** With E1 bundled, a printed sheet of mock badges scans on the iPhone (on Android, the badge images through an emulator's virtual scene camera), including two devices (the iPhone and an emulator) checking in the same attendee; without it, the same scenario passes with manual or HID entry.

**Early spikes.**
- S8 (a minimal `mobile_scanner` extension in release builds) runs in P2, before P3, on the upstream track (UP-E1, in the P2 milestone).
- P3-E4 relies on S1's `sqlite3` verdict; re-run it only if a Flet pin bump changed the Python build since S1.

**Decisions.**
- O-7, staff-tool depth: lead → door → swag → CoC. The last two may move to `later`.
- O-8, the stage-demo backend: decided at the exit.

### P3-E1 · Epic: mock API server and contract

epic, area:account · NEW-08, API-01, AUTH-03, API-12

`tools/mock_api/`: a pure `handle()`, a LAN server, `httpx.MockTransport` in tests, a contract README, byte-exact signing with Ionic-generated vectors, the API client, the PSF-host guard and fault injection.

### P3-E2 · Epic: sign-in, account, role flags and favourites sync

epic, area:account · after P3-E1 · AUTH-01, AUTH-02, AUTH-04, AUTH-07, AUTH-08, AUTH-09, AUTH-10, AUTH-11, AUTH-12, API-02, API-03, API-04, STORE-03, STORE-04, STORE-05, SHELL-12, SHELL-13, SHELL-15

Sign-in with autofill and distinct errors, SecureStorage credentials, the `Account` store, role flags on start and resume, the account screen, confirmed sign-out that keeps favourites, the start-destination setting, and favourites sync with a dirty flag.

### P3-E3 · Epic: staff entry points and the shared scan screen

epic, area:staff · after P3-E2 · SHELL-06, SHELL-07, SHELL-11, AUTH-05, AUTH-06, LEAD-01, LEAD-02, LEAD-03, LEAD-14

Staff tools in More and on Now from `staff_entries(flags)` (truth-table test); one scan screen with manual entry, HID input, the E1 camera when bundled, a 4 s cooldown, multi-channel outcomes, the camera permission flow and the wake lock.

### P3-E4 · Epic: offline queue (outbox and sync worker)

epic, area:staff · after P3-E1 · API-10, API-11, LEAD-12, LEAD-13, DEV-03

A sqlite outbox (`lead`, `note`, `door`) with attribution and idempotency keys, one connection on the loop thread, one retry cap, a `SyncWorker`, the queue sheet, "Clear staff data", and state-machine tests.

### P3-E5 · Epic: lead retrieval

epic, area:staff · after P3-E3, P3-E4 · LEAD-04, LEAD-05, LEAD-06, LEAD-07, LEAD-08, LEAD-09, LEAD-10, LEAD-11, STORE-06, STORE-11, API-09

Consent per account, the searchable sponsor picker, capture through the outbox with immediate results, the leads list with status words, structured notes, and duplicate feedback.

### P3-E6 · Epic: door check

epic, area:staff · after P3-E3, P3-E4 · DOOR-01, DOOR-02, DOOR-03, DOOR-04, DOOR-05, DOOR-06, DOOR-07, API-05, API-07, STORE-12

Category and session pickers, inventory preload ("works offline"), pure `core/admission.decide()`, names and dietary chips, an always-visible headcount, and queued check-ins with idempotency keys.

### P3-E7 · Epic: swag pickup

epic, area:staff · after P3-E3 · SHIRT-01, SHIRT-02, SHIRT-03, SHIRT-04, API-06

Swag categories, a scan that fetches redeemable products, a hand-out sheet with available items pre-ticked, and an online-only redeem. May move to `later` under O-7.

### P3-E8 · Epic: Code of Conduct incident capture

epic, area:staff · after P3-E3 · MASK-01, MASK-02, MASK-03, MASK-04, MASK-05, API-08

An in-memory attendee directory, name search, a review dialog before every record (scans included), neutral wording, hidden emails, and online-only errors. May move to `later` under O-7.

## 7. P4 Showcase

**Goal.** Polish, publish, present.

**Exit criteria** (PLAN §7):
1. **Quality.** There are no known data-loss or task-blocking bugs, and the performance targets are met.
2. **Clean build.** Someone else, or the owner on a clean machine, builds and runs the app from a clean checkout in 30 minutes or less, using `docs/development.md`.
3. **Demo.** The demo script runs twice end to end without Wi-Fi.
4. **Public.** The repo is public, and `v1.0.0` is tagged with internal builds for both platforms.

**Markers (UNCONFIRMED):**
- the CFP opens around 2026-10-31 and closes around 2026-12-18 (O-6);
- PyCon US 2027 runs May 12–18 in Long Beach.

### P4-E1 · Epic: performance, accessibility audit and goldens

epic, area:quality

A performance pass against D-80, a full accessibility audit (every flow, 200 % text, four schemes, reduced motion), and a handful of goldens once the UI is stable.

### P4-E2 · Epic: 2027 conference data

epic, area:data

When the 2027 feed appears (expected around March, UNCONFIRMED): `data/2027/`, `config.YEAR`, the invariants and Ionic-difference list re-run, safety contacts re-verified. Joins whichever phase is active.

### P4-E3 · Epic: View source on every screen

epic, area:shell · NEW-09

An overflow item on each screen opening its module on GitHub in the in-app browser, once the repo is public.

### P4-E4 · Epic: going public

epic, area:build

README with screenshots and an accessibility section, CONTRIBUTING, `good first issue` labels, a licence, asset and trademark review, then the public repo and `v1.0.0` with internal builds for both platforms.

### P4-E5 · Epic: talk and demo

epic, area:quality

The demo script (offline start, Now & Next for me, My schedule, live edit in the companion app, a staff scan against the mock, View source), recorded fallbacks, O-8, and whether to approach the PSF.

## 8. Upstream track

Upstream work happens in flet-dev repositories. Each item is tracked here by an issue labelled `upstream` that links the flet-dev issue or PR (D-97). App issues that wait on one are labelled `blocked`, and the interim ships meanwhile. A core gap is upgraded only by a PR that bumps the pinned Flet (D-64). An extension is enabled by a PR that adds its pinned package, and the interim stays the fallback whenever its capability constant is false (D-63).

| D-98 | Item | Key | Interim in the app | App swap |
|---|---|---|---|---|
| 1 | E3 scheduled notifications (flet-dev/flet#6948) | UP-E3, S6 | Now's next-session card, in-app Banner, `.ics` alarms, honest settings (D-60) | P2-E6, after a pin bump |
| 2 | U1 `RefreshIndicator` | UP-U1 | status-strip Refresh and auto-refresh (P1-04) | new issue after the bump |
| 3 | U15 non-fatal handler errors | UP-U15 | `@report_errors` (P0-21) | delete the decorator |
| 4 | E1 barcode scanner, after S8 | UP-E1 | manual and HID entry | P3-E3 |
| 5 | U4 `page.get_app_info()` | UP-U4 | `__version__` | P2-E9 or later |
| 6 | U16 `PageMediaData.text_scale_factor`, U17 accessibility-change event, U10 `AppBar.bottom`, U2 sticky headers, U3 absolute `InteractiveViewer` transform, U9 `use_route_search`, U18 Router Back inside a modal sub-chain | UP-SMALL | fluid layouts, re-read on resume, tabs as a body row, time gutter, select without a camera move, `use_query()`; own `on_view_pop` | one issue each |

**Not tracked here:**
- **Later or low (D-98):** E4, E5, E2, U19 (pinning platform adaptations, D-10; interim: accepted residuals) and U20 (multi-weight `page.fonts`, D-26; interim: pubspec fonts); U6, U7, U12 and U13 only when a feature or spike needs them.
- **flet-dev/flet#6953** is not required, because P2-E8 configures both per-platform deep-link tables (D-21).

## 9. Checks

This catalogue and `issues.json` were generated once from one data file and checked:
- every P0 and P1 feature id of the matrix is covered by a concrete issue;
- every P2–P4 id belongs to an epic;
- every label is in the D-90 set;
- every dependency exists, and dependencies come before the issues that use them.

The generator is not kept: after seeding, this file is edited by hand (only at phase starts and on scope changes), and GitHub holds the issues.

To find an id's issue, search this file for it.

## 10. Seeding GitHub

`issues.json` is used once: it is committed at the repo root in the seeding PR and deleted once GitHub holds the issues. It holds:
- `milestones`: `title` and a `description` with the goal and exit criteria;
- `labels`: the D-90 set;
- `issues`: `key`, `title`, a Markdown `body`, `labels`, `milestone`, `depends_on` (keys) and `epic` (a key or `null`).

Every epic and dependency comes before the issues that point to it, so one pass creates everything.

Before seeding:
1. Create the labels with `gh label create --force`, and remove GitHub's default labels that are not in D-90.
2. For the Project (D-94), run `gh auth refresh -s project` first.

```python
"""Seed milestones and issues from issues.json with the gh CLI (run once, from the repo root)."""

import json
import subprocess


def gh(*args: str) -> str:
    """Run one gh command and return its standard output."""
    result = subprocess.run(["gh", *args], check=True, capture_output=True, text=True)
    return result.stdout.strip()


with open("issues.json", encoding="utf-8") as f:
    seed = json.load(f)

for milestone in seed["milestones"]:
    gh("api", "repos/{owner}/{repo}/milestones",
       "-f", f"title={milestone['title']}", "-f", f"description={milestone['description']}")

numbers: dict[str, int] = {}  # roadmap key -> issue number
for issue in seed["issues"]:  # epics and dependencies come first
    body = issue["body"]
    if issue["depends_on"]:
        body += "\nDepends on " + ", ".join(f"#{numbers[key]}" for key in issue["depends_on"]) + "\n"
    args = ["issue", "create", "--title", issue["title"], "--body", body,
            "--milestone", issue["milestone"], "--label", ",".join(issue["labels"])]
    if issue["epic"]:
        args += ["--parent", str(numbers[issue["epic"]])]
    url = gh(*args)
    numbers[issue["key"]] = int(url.rsplit("/", 1)[-1])
```

After seeding, pin the P0 status issue (`P0-00`). Mark `good first issue` candidates as they appear; none are pre-assigned while the repo is private.
