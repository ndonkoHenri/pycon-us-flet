# PyCon US 2027 app on Flet: port plan

**Status:** plan of record, 2026-10-11. **Owner:** U (a Flet core maintainer).

**Angle:** become the PSF's official 2027 rewrite at full data parity and ship on time. The attendee core can't be cut, and each native upgrade has its own gate.

**Companion documents**
- [`docs/feature-matrix.md`](docs/feature-matrix.md): all 263 ids, each with its disposition, milestone, approach, dependencies and gotchas.
- [`docs/architecture.md`](docs/architecture.md): code sketches, schemas, the route tree, stores, the API client and the outbox.
- [`docs/flet-gaps-and-extensions.md`](docs/flet-gaps-and-extensions.md): specs for E1-E6 and U1-U15.
- [`docs/build-and-release.md`](docs/build-and-release.md): `pyproject.toml`, the workflows, signing, the release train and runbooks.
- [`docs/testing-and-quality.md`](docs/testing-and-quality.md): test layers, harnesses, Badge Days and the quality gates.
- [`docs/backlog.md`](docs/backlog.md): every id with tier, owner, estimate and milestone, plus capacity checks.
- [`docs/decisions.md`](docs/decisions.md): the decisions record (binding; D-numbers cited below).
- Inputs: `docs/research/`.

**Dates.** External dates are marked **confirmed** or **UNCONFIRMED**; unmarked dates are plan targets. PyCon US 2027 is May 12-18, 2027 in Long Beach, CA (confirmed: PyCon US blog, 2026-09-24). The per-day split (tutorials 05-12/13, talks 05-14..16, sprints 05-17/18) is inferred from the 2026 pattern and is UNCONFIRMED; us.pycon.org/2027 returned 404 on 2026-10-11.

**Owners**

| Code | Who |
|---|---|
| U | the user |
| FT | the Flet core team |
| PSF-I | PSF infrastructure (infrastructure@python.org; Jacob Coffee, Director of Engineering) |
| PSF-E | PSF events, registration and sponsorship staff |
| CC | community contributors |

---

## 1. Executive summary and pitch

**What.** Rewrite the official PyCon US app (Ionic 8 / Angular 17 / Capacitor 7) in Python with Flet. Ship it as **version 27.0.0 of the PSF's existing store listings**:
- iOS: `org.pycon.us.2023.onsite`, App Store id 6446810296, team `BMM5U3QVKW`.
- Android: `org.pycon.us`, build 27000 (above today's 26022).

It keeps the Firebase project `pycon-us-2023-mobile` and its FCM topics, the signed `/api/v1` contract, `mobile_state` favourites sync and the four staff tools (lead retrieval, door check, swag pickup, CoC incident capture).

**Dates.** Feature freeze 2027-03-31. Store submission 2027-04-16. Public release 2027-04-27 (target), 2027-04-30 at the latest. That is two weeks before tutorials; the 2026 app's final releases landed in the week before them: 26.2.0 (~05-08) white-screened (#308), and the fix 26.2.1 shipped 05-10, 3 days before tutorials, with some users still affected on 05-12.

**Why now.**
- The PSF said publicly that it will rewrite the app for 2027 and asked for help (README banner, commit `fb7482f`, 2026-04-10, confirmed).
- Ionic stopped selling Appflow on 2025-02-11 (confirmed), and Appflow, Live Updates included, sunsets on **2027-12-31** (confirmed).
- To reach the April store window, the rewrite has to start in Q4 2026.

**Why Flet.**
- The backend (`PyCon/pycon-site`) and the planned push console (#300) are Django. A Flet app keeps the whole stack in one language: Python.
- 232 of the 263 features (88 %) port or adapt to Flet controls and services that exist today.
- The hardest logic (feed normalisation, time zones, sha1 signing, offline queues) becomes testable Python that Django developers can read.
- To our knowledge, this would be the first Python-built official PyCon US app and the first Flet conference app shipped on both stores. Earlier Python efforts exist, such as PyCon India's Kivy app (`pythonindia/PyCon-Mobile-App`).

**Why it is safe for the PSF.**
- The PSF can stop at every gate (7.4).
- The Ionic 26.x app plus Appflow keeps working until 2027-12-31.
- Release secrets stay with the PSF, and PSF-I is a required reviewer on releases.

**Why it is good for Flet.** Each gap becomes public Apache-2.0 work:
- A new official `flet-barcode-scanner`.
- Gated: `flet-firebase` push, scheduled reminders on the official flet-dev/flet#6948 extension, and `flet-add-to-calendar`.
- About eight core and CLI improvements.

The app is **capability-gated**: every gap has a tested interim, and a capability turns on when its extension or core feature is released and bundled, with no screen-code change. That is how it improves as Flet evolves.

| Who | What they get in 27.0 |
|---|---|
| Attendees | Parity, plus fixes for real Back (#279), no forced jump to now (#313), visible system nav (#311), a change log (#312), a stale-data chip, "Match system", and Android 8+ if the PSF agrees (#307) |
| Sponsors | Lead Scanner stays the landing screen, now after a fully awaited login with no stale flags (#310); an offline queue that never misattributes a scan; retry for failed scans; structured notes |
| PSF staff | Same rules for Door, Swag and CoC; data-loss and capture-flood fixes; manual and HID entry without a camera |
| PSF infra | A Python codebase in the PSF org; differential and contract tests; `app-config`/`app-content` replace Appflow; 2028 is a config change; co-maintainers |
| Community | Apache-2.0 extensions, a reference declarative Flet app, a talk, a poster and a sprint |

---

## 2. Goals, non-goals, measurable success criteria

**Goals.**
1. **G-SHIP:** 27.0.x is live on both PSF listings as an update by 2027-04-30, built from a tag by PSF-held CI.
2. **G-PARITY:** all 263 ids are dispositioned (2 dropped), and data semantics are proven identical by differential tests.
3. **G-STAFF:** the four staff tools work on printed badges by Badge Day 2 (04-09), with the camera or with manual/HID entry; lead and door check are offline-tolerant (outbox), and swag and CoC show explicit offline errors.
4. **G-FIX:** close #279, #311, #312, #313 and #310; also #307 if the PSF approves.
5. **G-UPSTREAM:** every native gap is closed upstream, with no template fork.
6. **G-DEMO:** a talk and a poster at PyCon US 2027, with a demo that does not depend on Wi-Fi.
7. **G-HANDOVER:** PSF volunteers can release, hotfix and roll the year over without U.

**Non-goals (27.0).**
- Python OTA. Flet has no OTA mechanism, and App Store 2.5.2 / DPLA 3.3.2 restrict downloaded code to non-feature-changing interpreted updates, which is not worth the review risk. Server-driven content replaces it (9.4).
- A new listing, push provider or analytics vendor.
- Backend changes beyond requests to the PSF.
- An offline PWA, staff tools on web, desktop store apps or a kiosk.
- A custom build template.
- Features beyond the issue fixes above.

| # | Success criterion | Target (how measured) | Date |
|---|---|---|---|
| S1 | Coverage | Every non-dropped id has a test named after it (`feature_trace` CI gate); 0 open P0/P1 parity bugs | 2027-03-31 |
| S2 | Data parity | Processed 2025 and 2026 feeds equal Ionic's reference output (differential suite) | 2027-01-31 |
| S3 | Store continuity | 27.0.x live on both listings as an update | 2027-04-30 |
| S4 | Staff reliability | Badge Day 1: >= 300 scans, 0 lost or misattributed. Badge Day 2: >= 500 scans across 4 tools, including 30 min in airplane mode for lead and door check, 0 lost. With E1, >= 95 % first-try decode at Badge Day 1 and >= 98 % at Badge Day 2. Checked against the server audit | 02-24 / 04-09 |
| S5 | Stability | Crash-free sessions >= 99.5 % in beta and in conference week (Sentry, Play vitals, Xcode Organizer) | 04-14 / 05-18 |
| S6 | Performance | Cold start to cached schedule p50 <= 2.5 s on a Pixel 6a and <= 2.0 s on an iPhone 12. First Android launch <= 6 s. Play download <= 40 MB arm64; iOS <= 60 MB | 2027-04-14 |
| S7 | Accessibility | 12 scripted flows completed with VoiceOver and TalkBack; 200 % text without clipped actions (manual device passes at max OS font size, plus app-level `text_scale` emulation goldens, 8.2); contrast >= 4.5:1 (>= 7:1 HC), unit-tested | 2027-03-31 |
| S8 | Adoption | >= 90 % of devices active in conference week run 27.x | 2027-05-16 |
| S9 | Rating | iOS >= 4.5 (today 4.63 from 8 ratings, confirmed 2026-10-11) | 2027-06-30 |
| S10 | Upstream | E1 on PyPI; U1, U4 and U5 released before the last pin change; E2-E4 in 27.0 or by 27.1 | 03-05 / 06-30 |
| S11 | Hotfix readiness | Tag to both stores in <= 2 h, rehearsed on the newest Xcode; content fixes in < 30 min | 2027-04-24 |
| S12 | Handover | >= 1 co-maintainer has cut a release build (the `v27.0.0-alpha.5` freeze build, 9.2); 2028 rollover dry run takes <= 1 day with no code edits | 03-31 / 09-30 |

---

## 3. Guiding principles

1. **Ship on released Flet, pinned exactly.** 27.0 needs no unreleased Flet (PyPI has 1.0.4, released 2026-10-08, confirmed 2026-10-11; 1.1.0 is unreleased). Flet 1.1.0 must, however, be *released* in time: it is on the store/iOS critical path (7.3), because 1.0.4 cannot build iOS on Xcode 27 and E1 needs `flet>=1.1.0`. A prerelease would make the template resolve the stable Dart package ("Unknown control"). New extensions E1, E2 and E4 are standalone wheels built against the released 1.1 API; E3 is contributed to the official #6948 extension in the flet-dev/flet monorepo (6.1).
2. **Capability-gated progressive enhancement.**
   - Every gap has an interim that always ships and is always tested.
   - A build-time manifest and API probes decide what is available.
   - The server can veto a capability, but can never enable one.
   - CI runs every capability both on and off (5.7).
3. **Server-driven everything that changes per year or during the conference.** `conference.json`, `app-config.json` and `app-content.json`. This replaces Appflow, and 2028 becomes a config change.
4. **Parity of data semantics, not of bugs.** `processData` is ported rule by rule and checked against Ionic's own code on two years of feeds. Every deliberate fix is an *adapt* row with a test named after its id.
5. **Pure core, thin UI.** `pycon_us/core` imports nothing from Flet.
6. **Declarative and safe by rule.**
   - No conditional hooks.
   - Async Flet methods are called only from `async def` code.
   - One context per observable store.
   - `@safe` on every handler and effect.
   - No timers used as synchronisation.
7. **Never lose a scan.**
   - One outbox, one `SyncWorker`.
   - Attribution is snapshotted per record.
   - Failures stay visible.
   - Logout is guarded.
8. **Upstream first, fork never.** If an upstream item is late, the interim ships.
9. **Stage-safe by construction.** The `DEMO` build has a bundled feed, a fixed clock and a simulated scanner.
10. **Permissive, boring dependencies.**
    - Pure-Python wheels plus `tzdata`, with exact pins.
    - A CI licence gate.
    - Nothing GPL, which rules out the third-party `AyberkA0/flet-barcode-scanner`.

---

## 4. Scope tiers and feature dispositions

The full table, one row per id, is in **[`docs/feature-matrix.md`](docs/feature-matrix.md)**. It is the source of truth for dispositions, edited directly and re-checked by script against the canonical index of 263 ids (D-130).

**Counts:**

| Disposition | Count |
|---|---|
| port | 137 |
| adapt | 95 |
| interim->upgrade | 29 |
| defer | 0 |
| drop | 2 |
| **Total** | **263** |

**By milestone:** M0 4, M1 62, M2 109, M3 80, M4 5, M5 1, plus 2 dropped. Every non-dropped id ships something in 27.0. Whether each "upgrade" half lands in 27.0 or in 27.1 is decided by the gates in 7.4.

### 4.1 Tiers

| Tier | Contents | Release rule | If it slips |
|---|---|---|---|
| **T0** Attendee core | Shell, themes, onboarding, schedule, filters, favourites, search, Now, detail screens, tracks, events, info/safety pages, maps, sponsors, notification settings, app-config gates, offline cache | Blocks 27.0; no cuts; existing Flet only | - |
| **T0-P** PSF-dependent | Login, `check_features`, `mobile_state` sync (P3 by 12-15) | Ships if P3 is on time | Local favourites, login hidden; sync in 27.0.x |
| **T1** Staff tools | LEAD/DOOR/SHIRT/MASK, Staff sheet, outbox | Blocks staff use, **not** the attendee release; kill switch per tool | Manual or HID-wedge entry of the full `code:validator` payload |
| **T2** Should-have | Expo booth map, Job Listings, Sprints, Venue & Hours sections, split pane, PWA, U3/U9/U15 | Ships if green at freeze (03-31) | Cut order |
| **T3** Gated | E2 push, E3 scheduled reminders, E4 native calendar, autofill entitlement | Each decided at G3 (02-12) | Interim ships; 27.1 (06-30) |

**Cut order**, applied top first when the burn-down is more than 15 % behind at a milestone exit:
1. T3 items that are not "go".
2. SHELL-14 split pane.
3. EXPO-05 zoom-to-booth (highlight only).
4. Sprints and Job Listings (in-app browser to us.pycon.org instead).
   - 4b. Venue & Hours sections and the Quiet Room card (MAP-09, MAP-10): one Markdown block without interleaved location cards, Quiet Room card dropped (D-110).
5. EXPO-01..04 hotspots (static zoomable expo image instead).
6. U3, U9 and U15 move to 27.1.
7. The PWA.

**Never cut:** T0, the offline cache, the outbox, kill switches, the update gate (NOTIF-12) and accessibility.

### 4.2 Notable drops, interims and deliberate changes

**Dropped.**
- LIVE-01 (Appflow OTA): out of scope for bundled Python (Flet has no OTA mechanism, and App Store 2.5.2 / DPLA 3.3.2 restrict downloaded code); replaced by server-driven content.
- DATA-27 (`slot.sessions`): absent from both the 2025 and 2026 feeds. A contract test fails if it ever appears.

**Badge scanning** (LEAD-01, DOOR-04, SHIRT-02, MASK-04) is the largest interim.
- Until the E1 camera scanner lands, `ManualEntryScanner` accepts the full badge payload (typed, pasted or from an HID scanner) and runs `parse_badge`.
- Validator-bearing endpoints therefore keep working.
- P3 asks the PSF whether a code-only manual check-in is acceptable.

**Notifications.**
- The 27.0 baseline is:
  - polled `app-config` banners;
  - in-app reminder banners;
  - an "Add reminders to calendar" `.ics` with `VALARM`, for best-effort alerts outside the app;
  - the PSF's own email and Discord for emergencies.
- E2 push and E3 OS-scheduled reminders are upgrades decided at G3. **Push is not on the never-cut list.**

**Other interims** are listed with their upgrades in 6.2. Examples: refresh button → U1, dividers → U2, Markdown → E5, swipe + long press → E6, `.ics` → E4, `build_info` → U4, autofill heuristics → U5/U8, online-only PWA.

**Adapt highlights**, each covered by a test:

| Area | Change |
|---|---|
| Navigation | A real view stack replaces `prevUrl` |
| Search | Live (250 ms) over text instead of raw HTML |
| Favourites | Favourites view ignores the track filter; "Favorite all" covers the whole track, with Undo; login merges favourites |
| Now/Next | Respects end times |
| Staff scanning | Scan attribution snapshotted when queued; a second pending check-in is no longer lost; 3 s CoC cooldown |
| Data | Cache swapped only after a successful fetch; year tables moved to `app-content` |

**NATIVE-10.**
- The Ionic storage can't be read, so users start fresh. Favourites return from `mobile_state` at login, and a "Welcome back" card explains the reset.
- An optional bridge release (non-secret prefs only) is offered to the PSF. No gate depends on it (OD-8).

---

## 5. Architecture

This section records decisions only. Code sketches and schemas go in `docs/architecture.md`. Every Flet API named here was introspected in the local SDK on 2026-10-11, or is marked "exists" in the capability index.

### 5.1 Project layout

```
pyproject.toml  firebase.json  config/ (app-config + app-content schemas, per-env/year files)
src/main.py                      # ft.run(lambda page: page.render_views(App))
src/pycon_us/  app.py routes.py settings.py build_info.py (CI: VERSION, BUILD_NUMBER, GIT_SHA, TARGET, CAPS, PYCON_ENV, DEMO, CAPS_OVERRIDE; YEAR, CONF_TZ, SITE_URL from config/conference.json)
  core/      no flet import: parse/process, queries, timefmt, slugs, html_md, ics, badges, signing, admission, outbox, changelog
  api/ stores/ (one context per store) services/ (storage, bootstrap, sync_worker, safe, crash, bridge_import)
  platform/  caps + protocols (scanner, push, reminders, calendar, analytics, app_info)
  ui/ (shell_view, components, theme)  screens/ (one package per area; staff/{lead,door,swag,coc})  assets/
tests/ unit differential contract ui golden fallback     tools/ devserver ionic_reference feature_trace record_fixtures check_release caps_manifest
```

Extensions are not vendored. E1, E2 and E4 are standalone `flet-dev` repos pinned from PyPI; E3 is contributed to the official #6948 extension in the flet-dev/flet monorepo (6.1). The repo is branch `flet-2027` of `PyCon/pycon-us-mobile`.

### 5.2 Routing and navigation

- **Router.** `page.render_views(App)` with `ft.Router(ROUTES, not_found=NotFound, manage_views=True)`. With `manage_views=True` the Router wraps the `not_found` result in a bare `View(route=pathname, controls=[not_found()])`, so `NotFound` returns plain content (not `shell_view`/`ft.View`) with its own "Go to Schedule" button. If the 404 page needs the app chrome, a catch-all `Route(path=":rest*", component=NotFoundScreen)` returning a `shell_view` View is used instead.
- **URLs.**
  - Ionic paths (`/app/tabs/...`) are kept 1:1, so web URLs and the new `pyconus://app/...` deep links address the same screens. Deep links are configured in `[tool.flet.android.deep_linking]` and `[tool.flet.ios.deep_linking]` (`scheme="pyconus" host="app"`, D-109); flet-cli ignores the global `[tool.flet.deep_linking]` for Android and iOS builds (`build_base.py`), so that table alone would ship no deep links.
  - The short aliases `/s/`, `/p/` and `/r/` redirect, and so do Ionic's top-level `/login` and `/account`.
- **No outlet layout.**
  - Each view-level screen returns its own `ft.View` through `shell_view(...)` with `route=ft.use_view_path()`. There is no View inside a View, and every screen has its own title and actions.
  - The hamburger shows only on stack roots; details get the implicit back arrow.
  - Redirects return a minimal boot View and navigate from a mount effect.
- **Real stack.**
  - Details are child routes of the list that opened them.
  - Cross-links (session → speaker → session → room) use one **recursive drill segment**, `Route(path=":ref", recursive=True)`, with URL-encoded refs `s~`, `p~` and `r~`. Back walks one hop at a time.
  - Drawer destinations replace the stack.
- **Modals.**
  - The floor plan is a **global** modal declared at the top level, so its base stack is rebuilt from the last non-modal location. Entry points open it with `back=<opener path>` in the query; system Back pops through the Router, and the explicit "Close floor plan" button navigates to `back` (the Conference Map for a deep link without one), never reading `page.views`.
  - The filter, lead note and swag redeem are **local** modals (`Route(modal=True)` + `View(fullscreen_dialog=True)`).
- **Query strings.** `use_query()` calls `use_route_location()` and parses `page.route`, until U9 ships.
- **Chrome.**
  - The sponsor strip and `NavigationBar` share `View.bottom_appbar`, with an explicit `height`.
  - Banner rotation is **one** app-level task.
  - The active tab and drawer item come from **one** `use_route_location()` plus prefix checks. `is_route_active` is a hook, so it is never called in role-conditional sections.

Route table. Relative paths sit under the componentless group `app/tabs`.

| Path | Component | Kind | Tab lit | Gate | Ids |
|---|---|---|---|---|---|
| `/`, `app/tabs` index | `IndexRedirect` | redirect View | - | - | SHELL-03, AUTH-08 |
| `/tutorial` | `Welcome` | no shell, `can_pop=False` | - | - | SHELL-02 |
| `/floor-plan/:plan?pin=&back=` | `FloorPlanModal` | **global** modal | - | - | INFO-13, ROOM-05, MAP-05 |
| `/s/:id`, `/p/:id`, `/r/:slug` | `ShortLink` | redirect | - | - | deep links |
| `/login`, `/account` (top level, as Ionic `app-routing`) | `ShortLink` | redirect to `app/tabs/login` / `app/tabs/account` | - | the target's own | AUTH |
| `schedule` (+ `filter` modal, `changes`, `session/:session_id` + drill) | `Schedule` | root/child | Schedule | - | SCHED, SESS, #312 |
| `now` (+ session + drill) | `NowNext` | root/child | Now | - | SCHED-25/26 |
| `speakers` (+ `speaker-details/:speaker_id`, session, + drill) | `Speakers` | root/child | Speakers | - | SPKR |
| `keynote-speakers`, `tracks/:track_slug` (+ session + drill) | ... | root/child | - | - | SPKR-04, SCHED-21..24, EVT-01 |
| `rooms` (+ `room-detail/:room_slug`, session, + drill) | `Rooms` | root/child | - | - | ROOM |
| `conference-map`, `expo-hall?booth=N` | `ConferenceMap(initial_view)` | root | Map (conference-map only) | - | MAP-01, EXPO |
| `sponsors` (+ `sponsor-detail/:sponsor_id`) | ... | root/child | - | - | SPON-01..05 |
| `job-listings` | `JobListings` | root | - | - | SPON-06..10 |
| `sprints` | `Sprints` | root | - | - | EVT-05..08 |
| `venues-hours` | `VenuesHours` | root | - | - | MAP-09..11 |
| `lightning-talks`, `session-types`, `about-pycon`, `about-psf`, `coc`, `wifi`, `social-media`, `help` | info screens | root | - | - | INFO, EVT-03/04 |
| `login` | ... | root | Login (only while logged out) | - | AUTH |
| `notifications`, `account` | ... | root | - (none; transparent indicator, D-39) | `account`: logged in | NOTIF, AUTH |
| `lead-retrieval` (+ `note/:code` modal) | `LeadScanner` | root | **Scanner** | `lead_retrieval or door_check` | LEAD |
| `door-check`, `t-shirt-redemption` (+ `redeem` modal) | `DoorCheck`, `SwagPickup` | root | - | `door_check` | DOOR, SHIRT |
| `mask-violation` | `CocIncident` | root | - | `mask_violation` | MASK |
| `dev-tools` | `DevTools` | root | - | `settings.DEV` or 7-tap unlock | DEV |

**Staff gating truth table.** This is the exact Ionic behaviour (`tabs-page.html`, `map.ts`). It gets a unit test.

| Entry point | Rule |
|---|---|
| Scanner tab opens the Staff sheet | `door_check or mask_violation`; lit only while on `lead-retrieval` |
| Scanner tab goes straight to `lead-retrieval` | `lead_retrieval and not door_check and not mask_violation` |
| Door Check and Swag (sheet, drawer) | `door_check` |
| Lead Scanner (sheet, drawer) | `lead_retrieval or door_check` |
| CoC Incident | `mask_violation` |
| "Scan on behalf of" sponsor picker | `door_check and not lead_retrieval` |
| Launch and post-login redirect to Lead Scanner | `lead_retrieval` **only**; door-check-only staff land on Schedule |

### 5.3 State model

`ft.use_context` subscribes a component only when the provided value *is* an Observable, and Observables do not propagate changes from nested observable fields. A single context holding a container of stores would render once and never update. So **each `@ft.observable` store gets its own context**, read through typed hooks such as `use_feed()` and `use_auth()`.

Stores are created once in `App` with `ft.use_memo`, inside the page context, so services register with the page. Derived data is memoised on `(feed.version, inputs)` and never stored.

```python
@ft.component
def App():
    s = ft.use_memo(lambda: Stores.create(ft.context.page), [])
    prefs, _ = ft.use_state(s.prefs)  # subscribes App to the Prefs observable; reading s.prefs.loaded directly would never re-render
    ft.use_effect(s.bootstrap, [], cleanup=s.shutdown)  # async bound method -> runs as a task; cleanup also lets unmount cancel it
    if not prefs.loaded:             # hooks above stay unconditional; only the returned tree is gated
        return [ft.View(route="/", bgcolor="#680579", controls=[Boot()])]
    return provide_stores(s, lambda: ft.Router(ROUTES, not_found=NotFound, manage_views=True))
```

Effects run only after the first render is sent, and `SharedPreferences` reads are coroutines, so prefs cannot be applied before the first render. `Prefs.loaded` is a field on the observable `Prefs` store, and `App` subscribes to that store through `ft.use_state(s.prefs)`. `App` shows the boot screen (same `#680579` as the splash) until bootstrap step 1 sets `loaded`, which it does only after the theme is applied, so the default theme and filters never flash.

Two SDK rules shape the stores and effects. An async effect task is cancelled on unmount only when the effect has a `cleanup`, so long-running effects pass one (`App` passes `s.shutdown`). Assigning an observable field compares `old == new` first, so the feed lives in `eq=False` containers that reference other objects by id; speaker↔session object cycles would make that comparison very slow.

Stores and what they hold:

| Store | Holds |
|---|---|
| `FeedStore` | `conf`, `status`, `version` |
| `AppConfigStore` | gates, banners, kill switches, feed URL |
| `ContentStore` | yearly content |
| `AuthStore` | login state; secrets stay in SecureStorage |
| `Features` | role flags and consent |
| `Prefs` | theme, excluded tracks (`None` vs `[]`), notification prefs, tutorial flag |
| `Favorites` | `list[str]` |
| `StaffStore`, `OutboxStore` | staff-tool state, outbox counters |
| `BannerStore` | top banners and sponsor rotation |
| `ChangeLog` | schedule changes |
| `Caps` | capability flags |

**Bootstrap order** (replaces Ionic's 200/300 ms flag timers and the 5 s deferred init):
1. Prefs (theme and filters applied before the first themed render; only then sets `Prefs.loaded`, which releases the boot screen).
2. Optional bridge import.
3. Auth restore.
4. Cached feed, then network feed.
5. `check_features` and `mobile_state`, once.
6. app-config and app-content.
7. Start `SyncWorker` and the banner task.

### 5.4 Data layer

**Fetch**
- Source: `GET {site}/{YEAR}/schedule/conference.json` (about 824 KB, 10 s timeout). app-config can override the URL.
- Transport: `httpx` on native, `pyfetch` on web, where httpx is absent.

**Single flight**
- One `asyncio.Task` publishes the cached copy first, then the network result.
- The cache is replaced atomically, and only after a successful parse.
- `refresh(force=True)` really refetches.

**Processing**
- A rule-by-rule port of `processData` into frozen dataclasses.
- Ids are `str`, and synthetic ids are stable: `conf_key+9000`, `poster-detail-N`, and Ionic's collapsed-row id `{kind}-{room}-{start}` (e.g. `break--2026-05-13T12:30:00-07:00`), which server-side favourites already hold. `kind-day-name[-start]` (`-start` only on non-lunch breaks) is only the key that groups slots into a collapsed row, never a session id.
- Named tests cover:
  - the placeholder filter exempting poster/break;
  - generic Break rows with no location;
  - the Job Fair row labelled 9:30 but grouped at 10:00;
  - speakers linked by name.
- Parsing moves to a thread only if spike S3 measures more than 150 ms.
- A bad slot is skipped and reported; it never blanks the schedule.

**Queries**
- Pure functions return view models and never mutate shared data.
- Match rules:
  - schedule and tracks: ANY word in the name, description text or speaker names;
  - speakers: ANY word in the name;
  - sprints and jobs: ALL words.

**Time**
- `zoneinfo.ZoneInfo(settings.CONF_TZ)` plus bundled `tzdata` (spike S2).
- One `conf_now()`, overridable by `PYCON_FAKE_NOW` or DEMO.
- The day bucket is the conference-local date.
- Labels are en-US (`9:25 am`, `Wed`).

**Markup, change log and offline**
- `core/html_md.py` (stdlib `html.parser`) converts HTML to Markdown and resolves relative links.
- Change log (#312): sessions are diffed by id after each fetch (start, end, room and title, plus added and removed sessions) and stored in sqlite. `cancelled` is not diffed: it is always `false` in the feed, and cancellations arrive as placeholder slots, so they show up as removed. The diff feeds a banner, a "Changed" chip (24 h) and `schedule/changes`, with no backend change.
- The app always renders from cache and shows an "Updated N h ago" chip. Ionic's error copy appears only on a cold start with no cache.

### 5.5 API client, auth, outbox

**Signing**
- `core.signing.sign(secret, ts, METHOD, full_path, body)` = `sha1(secret + ts + METHOD + full_path + body)` in hex. Plain SHA-1, not HMAC, with no separators.
- Bodies are `json.dumps(obj, separators=(",", ":"), ensure_ascii=False)`, serialised **once** and sent as exactly those bytes.
- The `fetch_products` query is built by hand and is **not** URL-encoded; `capture` **is** encoded (as Ionic does).
- Test vectors: the 2019 `docs/api.rst` example plus staging captures.

**Requests**
- `api.request()` holds Ionic's per-endpoint timeouts (2/3/5/10/15/20 s) and typed errors. Following `pycon-api.ts`: lead capture, lead note, `mobile_state` (GET and PATCH), `check_features`, `redeemable` and `attendees_by_product` use 2 s; authenticate 3 s; lead sponsors and CoC capture 5 s; `fetch_products` and `redeem_products` 10 s; CoC attendees 15 s; the quantity inventory 20 s.
- A clock-skew offset comes from the `Date` header, with one retry on a skew 403. The 2019 server allowed 600 s; the current window is UNCONFIRMED.

**Auth**
- Login is an unsigned, single-flight `POST /{YEAR}/api/v1/authenticate/`.
- Key and secret go to `flet_secure_storage.SecureStorage`; everything else to prefs.
- `check_features` runs on start, on resume and when Account opens.
- Favourites: one `mobile_state` GET after login, a union merge on the first sync (OD-5), then debounced full-list PATCHes through the outbox.

**Outbox** (sqlite `pycon.db`)
- Columns: kind, payload, sponsor snapshot, owner, status, tries, next_at. The server response (e.g. the lead's first name) is merged into the payload JSON; there is no separate column.
- One `SyncWorker` drains it every 60 s, on `ft.Connectivity.on_change` and on resume.
- Retry caps:

  | Kind | Cap | Notes |
  |---|---|---|
  | Lead scans | `tries > 10`: failed on the 11th failure (parity) | "Retry failed" list |
  | Notes | 20 tries | Waits for its capture |
  | Door check-ins | 30 tries | Idempotency key: code + product + session |

- Synced rows are kept, because lead dedupe and "Already checked in" depend on them.
- Swag stays online-only (parity), with an explicit offline message. CoC capture has no outbox kind either (online-only); a failed capture shows its error (MASK-03).

### 5.6 Storage, staff-data privacy, theming

**Storage**

| What | Where |
|---|---|
| Prefs, flags, favourites (JSON-encoded, prefix `pycon.<env>.`) | `ft.SharedPreferences` |
| API key and secret | `SecureStorage` |
| Feed cache (`conference-{YEAR}.json`) and last good `app-content-{YEAR}.json` | file in the cache dir; on web the feed cache is the SharedPreferences key `feed_cache` |
| Outbox and change log | sqlite (not on web, so staff tools are mobile-only) |

**Staff PII (OD-9)**
- Door inventories (with dietary and allergy data) and the CoC directory are kept **in memory only**.
- Synced staff rows are purged at `app-config.staff_data_purge_after` (default: conference end + 7 days) and when a different account logs in.
- Lists show only the current account's rows.
- Logout clears credentials, favourites, flags, consent and the staff sponsor. It asks "Sync now / Log out anyway (N unsynced)" if rows are pending.
- This is declared in Data Safety and App Privacy.

**Theming**
- Four explicit `ColorScheme` themes with no seed, so Ionic's hex values stay exact:
  - light;
  - dark: iOS `#000`, Android `#121212`;
  - HC-light: `#4a0072`;
  - HC-dark: `#ffd60a` on `#0b0f17`.
- They are swapped into `page.theme`, `page.dark_theme` and `page.theme_mode`.
- `Tokens` carries the semantic colours Material lacks (favorite `#69bb7b` for the swipe/option colour, HC = primary; favorite_star `#fbbf24` for the gold star, kept in HC modes too, where it is 5.1:1 on the fixed `#3B3EA9` header; track palette), the `hc` flag (outlined pills, full-contrast text) and a `text_scale` factor applied to `Theme.text_theme` sizes (1.0 in the app; the golden suite sets 2.0 as an emulation of OS text scale, which Flet cannot set).
- Brand colours (`#3B3EA9`, `#DD04D2`, `#680579`, `#FFD779`) never change.
- "Match system" is the default (OD-6) and also follows OS high contrast (`(await SemanticsService().get_accessibility_features()).high_contrast`, read at bootstrap and on resume). On Android below API 34, OS high contrast is not detectable (`high_contrast` is always False there), so users pick HC manually in Settings; a unit test checks that the HC theme picker stays reachable when `high_contrast` is False.
- Repeating animations are gated on `f.reduce_motion or f.disable_animations` (`f = await SemanticsService().get_accessibility_features()`, read at bootstrap and on resume like `high_contrast`). `reduce_motion` alone is reported only on iOS.

### 5.7 Platform and capability abstraction

| Protocol | Interim (always shipped and tested) | Target | Capability |
|---|---|---|---|
| `BadgeScanner` | `ManualEntryScanner` (full payload, HID wedge); `SimulatedScanner` in DEMO | E1 camera | `scanner` |
| `PushService` | `BannerPoller` (app-config banners) | E2 topics + `on_message` | `push` |
| `Reminders` | in-app reminder banners + `.ics` `VALARM` | E3 `zoned_schedule` | `local_notifications` |
| `Calendar` / `Analytics` | `.ics` share / `NullAnalytics` | E4 prompt / a separate `flet-firebase-analytics` wheel (E2) if OD-3 | `calendar` / `analytics` |
| `Refreshable`, `AppInfo`, booth zoom | button / `build_info` / reset-zoom-pan | U1 / U4 / U3 | probes |
| `use_query()`, `@safe` | `page.route` parsing / app-side error toast | U9 / U15 | no `Caps` key: an import or `hasattr` check inside the helper |

**How `Caps` works.**
- `Caps` is an `@ft.observable`, derived at bootstrap from two sources:
  - `build_info.CAPS`, a manifest CI writes from the `[tool.flet.<platform>].dependencies` that were actually bundled.
  - API probes such as `hasattr(ft, "RefreshIndicator")`.
- `flet run` uses an empty manifest, so the companion app never receives controls it lacks.
- `Caps` is re-derived on every app-config change. Remote features can only veto.
- Screens never import an extension.
- Release notes print the matrix.

**Interim notification channels:**

| Toggle | 27.0 in-app | With E2 | With E3 |
|---|---|---|---|
| announcements | banners + keynote reminders | topic `announcements` | keynote reminders |
| scheduleChanges / dailyDigest | change-log banner + banners / banners | `schedule-changes` / `daily-digest` | - |
| emergency | banners, **always shown in-app** (OD-18) | `emergency` | - |
| lightning / openSpace | reminder rows (in-app, `.ics`) | - | ids 8000+ |

### 5.8 Error handling

**Current Flet behaviour.**
- An exception in a handler or sync effect calls `session.error()`. The client receives `SESSION_CRASHED` and shows its error screen.
- An exception in an async effect task reaches only the asyncio handler.
- `page.on_error` is a Flutter-side event, and `sys.excepthook` never fires.

**What the app does.**
- `@safe` wraps every handler and effect. It reports the error and shows a non-blocking top toast (`ft.Banner` via `page.show_dialog()`, since `SnackBar` is bottom-only). `Banner` requires at least one visible action and has no duration, so the toast is `page.show_dialog(ft.Banner(content=..., actions=[ft.TextButton("Dismiss", on_click=lambda e: page.pop_dialog())]))` plus an app-level auto-hide task that calls `page.pop_dialog()` after N seconds (UI timing, not synchronisation).
- A lint rule rejects unwrapped handlers and lambdas that call async APIs.
- A `logging.Handler` on the `flet` logger plus an asyncio handler feed Sentry (OD-4). Events are PII-scrubbed and tagged with build and caps.
- A corrupt cache is deleted at bootstrap.
- Kill switches turn features off.
- U15 makes such errors non-fatal upstream.

---

## 6. Flet gaps and the extension roadmap

### 6.1 Release and compatibility policy (27.0 does not depend on Flet 1.2)

- **Pin.** 27.0 pins the newest *released* Flet 1.1.x or 1.2.x that exists on **2027-03-05**, the last pin change.
- **Extensions E1, E2 and E4** live in standalone Apache-2.0 repos in the `flet-dev` org; **E3** is contributed to the official #6948 extension in the flet-dev/flet monorepo.
  - Versioning: independent 0.x versions, requiring `flet>=1.1.0,<2` and Dart `flet: ^1.1.0`.
  - Built against the released 1.1 API with `material_ui`.
  - Tested on 1.1.x, plus a nightly run on `flet@main`.
  - They can move into the monorepo after the conference (OD-14).
  - Spike S7 proves that such a wheel builds via `[tool.flet.<platform>].dependencies`.
- **flet-cli hooks U5-U8** ship in a **1.1.x point release by 2027-02-26** (OD-19). If a hook slips, the features that need it keep their interim.
- **No template fork.** The helper-plugin and Gradle-init workarounds are documented only.

### 6.2 Gap register

| # | Gap (ids) | Interim | Target: upstream work (pub.dev package) | Effort | Owner | Deadline | Upgrade trigger |
|---|---|---|---|---|---|---|---|
| E1 | QR scanning (LEAD-01, DOOR-04, SHIRT-02, MASK-04) | manual or HID `code:validator` entry | `flet-barcode-scanner` on **mobile_scanner 7.4.2** (exact pin): QR, back lens, start/stop/torch, `on_detect`. Clean-room, with a `material_ui` gate test | M, 35 h | U | v0.1 on device 01-10; PyPI 0.2 by 02-19 | manifest |
| E2 | FCM push (NOTIF-04/06/07/08/09/11, NATIVE-04) | polled banners | `flet-firebase` on **firebase_core 4.15.0 + firebase_messaging 16.7.0**; firebase_analytics 12.6.0 only if OD-3, and then as a separate `flet-firebase-analytics` wheel (one wheel has one fixed `pubspec.yaml`, so analytics cannot be optional inside `flet-firebase`, and 27.0 links no analytics SDK). Dart-only `initializeApp(options)`; needs U5 | L, 50 h | U | spike S8 2026-11-30; **G3 02-12**; release 03-05 or 27.1 | manifest |
| E3 | Scheduled reminders (NOTIF-05/07, DEV-06) | in-app banners + `.ics` with `VALARM` | `zoned_schedule`/`cancel` contributed to the official **#6948** extension (**flutter_local_notifications 22.3.1 + timezone 0.11.1**; IANA tz passed from Python); #6948 is an open feature-request issue whose v1 lists scheduled notifications as out of scope; needs U7. Desugaring alone is not enough: the app manifest also needs the `ScheduledNotificationReceiver` and `ScheduledNotificationBootReceiver` `<receiver>` entries and `RECEIVE_BOOT_COMPLETED`, which the plugin's own manifest omits and the template cannot add. The #6948 package carries them in its own Android library manifest (merged by Gradle), which needs a `flutter: plugin: platforms: android: package:` entry in its `pubspec.yaml` and `"android/**"` in its package-data (the monorepo default is `["pubspec.yaml", "lib/**"]`); fallback: U7 grows a `[tool.flet.android.receiver]` table. PyPI name clash: OD-15 | M, 40 h | FT (v1), U | the PR implementing #6948 v1 merged and released by **01-15** (UNCONFIRMED), else 27.1 | manifest |
| E4 | Native calendar (SESS-04) | `.ics` share | `flet-add-to-calendar` on **add_2_calendar 3.1.1**; needs U6 | S, 20 h | CC/U | G3; 03-05 or 27.1 | manifest |
| E5/E6 | HTML (INFO-05 etc.) / revealed swipe buttons (SCHED-11) | Markdown conversion / `Dismissible` + long press | `flet-html` (flutter_widget_from_html_core) / `flet-slidable` (flutter_slidable) | M / S | CC | 27.1 sprint | manifest |
| U1 | Pull-to-refresh (SCHED-13, SCHED-26, EVT-07, SPON-08, LEAD-13) | refresh button | core `ft.RefreshIndicator(content, on_refresh, adaptive)` | S, 8 h | U | merged 01-15 | probe |
| U2 / U3 | Sticky headers (SCHED-02) / booth zoom (EXPO-05) | dividers / reset→zoom→pan | sliver sticky header / `InteractiveViewer.set_transform()`/`zoom_to_rect()` | M / S, 10 h | FT/CC / U | 27.1 / 02-12 (T2) | probe |
| U4 | Version at runtime (INFO-03) | `build_info.py` | `page.get_app_info()` over the bundled `package_info_plus` | S, 4 h | U | 01-15 | probe |
| U5 | iOS entitlements (push, `webcredentials:us.pycon.org`) | push off, autofill heuristics | `[tool.flet.ios.entitlement]`, mirroring macOS | S, 8 h | U | merged 01-31 | config |
| U6-U8 | Android `<queries>`, desugaring, resource `meta_data` | E4/E3/autofill interims | `[tool.flet.android.queries]`, `core_library_desugaring`, inline-table `meta_data` + `[tool.flet.android.string_resources]` (U8 needs both: `asset_statements` must point at a `@string` resource, which the template cannot add; D-109) | S, 17 h (U8 5 h after D-109) | U | 01-31, only if needed | config |
| U9 / U15 | Query hook (ROOM-03, SPON-04) / non-fatal handler errors | `use_query()` / `@safe` | `ft.use_route_search()` / Flet option + Python-side error hook | XS / S | U | 02-12 (T2) | probe inside the helper (no `Caps` key) |
| U12 / U13 | Pod iOS minimum / privacy manifest | - | `[tool.flet.ios] deployment_target` **only if** spike S10 finds a pod needing more than iOS 15; template `PrivacyInfo.xcprivacy` **only if** spike S5 hits ITMS-91053 | S | U | 2026-12-15, conditional | build |

**After the conference:** U10 `AppBar.bottom`, U11 offline service worker, U14 App Links `autoVerify` and multiple hosts; sheet detents (no U-id yet). In 27.0 their interims are the first row of `View.controls`, an online PWA, the custom scheme and a fixed sheet. OTA stays replaced by server content, and top toasts use `ft.Banner`.

**Upgrade procedure.** No screen code changes:
1. The upstream release ships.
2. Bump the exact pin.
3. Add the extension to `[tool.flet.android|ios].dependencies`.
4. CI writes the manifest and `Caps` lights the capability. The fallback-parity "all on" suite already covers it.

---

## 7. Milestones and timeline (2026-10-11 → 2027-09-30)

### 7.1 Capacity (explicit) and demand

**Capacity**

| Who | Commitment | Hours to 04-16 |
|---|---|---|
| U, app time | 15 h/week × 27 weeks + 40 h holiday sprint (12-21 → 01-03) − 10 % illness/travel | **400** |
| U, Flet-work time | Paid maintainer hours on PyCon-driven upstream work: 10 h/week − ~50 h for Flet release duty and triage crunches (Nov, Feb) | **220** |
| CC | 2 contributors recruited by 2026-12-15, ~40 h each (Jan–Mar), off the critical path | **80** |
| FT / PSF | #6948 v1, reviews within 3 working days, releases / P-table, Badge Day staff | not counted |
| **Total** | **700 h** base; **620 h** with zero contributors | |

**Demand**

| Workstream | Hours |
|---|---|
| M0 spikes, CI, devserver | 40 |
| Data layer and Ionic harness | 60 |
| Stores, bootstrap, caps | 30 |
| Shell, routes, themes | 45 |
| Schedule cluster | 55 |
| Detail screens and events | 35 |
| Maps | 20 |
| Info and notification settings (CC) | 20 |
| Auth and sync | 25 |
| Staff tools and outbox | 60 |
| E1 | 35 |
| U1, U4, U5 | 20 |
| Tests and a11y (CC + U) | 35 |
| CI and store | 30 |
| Badge Days, betas, fixes | 45 |
| Talk | 25 |
| **Committed total (T0, T0-P, T1)** | **580 + 15 % contingency = 667** (D-108) |
| T2 | 92 |
| T3 gated: E2 50, E3+U7 46, E4+U6 26, U8 5 (D-109) | 127 |

**Fit.**
- **Base case.** Committed work fits with about 5 % margin. Adding T2 puts the plan about 8 % over, which the cut order (4.1) absorbs. T3 goes ahead at G3 only if the burn-down shows margin.
- **The two U pools are mixed.** Committed app work (580 h less E1 and U1/U4/U5 = 525 h, ~604 h with contingency) exceeds U app time plus CC (480 h), so about 124 h of it comes out of the 220 h Flet-work time. After E1 and U1/U4/U5 (55 h), that leaves only about 41 h of Flet-work time toward T3's 127 h; the rest of T3 needs burn-down margin (`docs/backlog.md`).
- **Trigger: zero contributors on 2026-12-15** (D-108). Either raise U to ~19 h/week (12-15 → 04-16 is about 17.4 weeks; that closes the ~47 h gap between 620 h and the committed 667 h, while 17 h/week would close only ~31 h), or cut T2, T3, the change-log UI, wide goldens, devserver semantics, and U1/U4 to 27.1.
- **Assumptions.** Estimates assume AI-assisted mechanical porting. Talk prep follows submission.
- **Tracking.** `tools/feature_trace.py` reports the weekly burn-down over the 263 ids.

### 7.2 Milestones

| Ms | Dates | Scope | Exit |
|---|---|---|---|
| **M0** Foundations | 2026-10-12 → **11-13** | Proposal email **10-16**; repo, CI and `settings`; Ionic reference harness; ten spikes (listed below this table); the pure `core/` data port starts here as soon as spike S4 lands, because M1 holds ~125 h of work in 3 weeks | A written verdict per spike (spike S8 by 11-30); schedule running on 2 phones; **G1** |
| **M1** CFP demo | 11-16 → **12-06** | 62 rows: data pipeline, schedule, session detail, Now, light and dark themes, offline cache; Android + web (iOS simulator best effort) | Differential test green on the 2026 feed; demo video **12-07**; CFP **12-11** |
| **M2** Attendee alpha | 12-07 → **01-31** | 109 rows: most of the remaining T0 and T0-P (keynote enrichment, keyboard focus and permission strings follow in M3/M4), including HC themes, update gates, change log, deep links, login/sync on staging, and the outbox core (the favourites PATCH and the logout guard need it; staff kinds follow in M3) | First **PSF-signed** TestFlight and Play internal builds on the real ids; E1 decodes a 2026 badge; Flet 1.1.0 pinned; **G2** |
| **M3** Staff beta + native gates | 02-01 → **03-05** | 80 rows: T1 on staging, outbox, Dev Tools, T2 (may finish by freeze); U1/U4/U5 released; **G3 02-12**; **Badge Day 1 02-24**; last pin change **03-05** | **G-Staff 02-26** |
| **M4** 2027 data + freeze | 03-06 → **03-31** | `/2027/` feed (~03-13, UNCONFIRMED) and API; 2027 app-content by 03-20; PWA on PSF hosting; a11y audit; a co-maintainer cuts the `v27.0.0-alpha.5` freeze build (03-30) | **G4** |
| **M5** Beta + release | 04-01 → **04-30** | Closed beta + public beta 04-01 → 04-14; RC1 **04-07**; **Badge Day 2 04-09**; **G5 04-14**; submit **04-16** (fallback 04-23); hotfix rehearsal on the newest Xcode **04-20 → 04-24**; release **04-27** (latest 04-30), shipping the exact beta binary | criteria S3, S4, S6 |
| **M6** Conference | 05-01 → 05-18 | Freeze **05-05** (P0 only); on-call; talk, poster, Open Space, sprints | criteria S5, S8 |
| **M7** 27.1 + handover | 05-19 → **06-30**; handover **09-30** | Missed upgrades (E2-E4, U2, analytics), extensions to 1.0, E5/E6 at the sprint, retro, 2028 rollover drill | criteria S9, S12 |

**M0 spikes**

| Spike | What it checks |
|---|---|
| S1 | `flet build aab/ipa` with the PSF bundle ids |
| S2 | `tzdata` on iOS, Android and Pyodide |
| S3 | parsing the 824 KB feed in <= 400 ms, and per-day list build time, on a Pixel 6a |
| S4 | the Ionic reference JSON |
| S5 | a throwaway TestFlight upload (ITMS-91053) |
| S6 | `sentry-sdk` on a device |
| S7 | a standalone extension wheel, plus `mobile_scanner` under the material_ui gate; the AAB size (arm64 download) with and without `flet-barcode-scanner`, against the criterion S6 budget; and the E3-style check that a monorepo extension's `android/` library manifest reaches the wheel (`"android/**"` package-data) and merges into the app (`manifest-merger-release-report.txt`) |
| S8 | Firebase Dart-only initialisation |
| S9 | routing: the query string in `page.route`, the drill segment, a global modal over a drill |
| S10 | the minimum iOS version of each wrapped pod |

### 7.3 Critical path

1. **Store chain** (slack about 2 weeks, plus the 04-23 fallback):
   G1 11-13 → track decision **12-04** → P4 store roles and secrets in the PSF `release` environment **01-15** → first signed builds 01-31 → beta 04-01 → submit 04-16 → release.
2. **Staff chain** (slack about 1 week; the manual/HID path does not depend on E1):
   P3 staging, keys and badges **12-15** → E1 v0.1 01-10 → staff tools on staging 02-19 → Badge Day 1 02-24 → RC1 → Badge Day 2 04-09.
3. **2027 data chain** (slack about 2 weeks; outside our control; content stays server-driven after release):
   P8 sample feed **02-15** → live feed ~03-13 (UNCONFIRMED) → contract diff → P9 content 03-20 → freeze.
4. **Flet chain** (1.1.0 itself is on the store/iOS critical path; the point-release hooks are not, and a miss there only keeps an interim):
   1.1.0 (target 11-30, hard 01-15, UNCONFIRMED) → U1/U4/U5 by 02-26 → pin 03-05.
   - Released 1.0.4 builds iOS for 13.0 and cannot build on Xcode 27, which rejects targets below iOS 15 (fixed in 1.1.0, #6874). So 1.0.4 is an iOS fallback only while Apple still accepts Xcode 26 builds, and the newest-Xcode hotfix rehearsal (04-20 → 04-24) needs 1.1.x.
   - E1 requires `flet>=1.1.0` and the `material_ui` Dart API, so it cannot ship on 1.0.4; the manual/HID path can.

### 7.4 Go/no-go checkpoints

Every "if NO" branch leaves the PSF free to keep the Ionic 26.x app plus Appflow, which works until 2027-12-31.

| Gate | Date | Go if | If NO |
|---|---|---|---|
| **G1** | 2026-11-13 | Written agreement in principle, a named PSF-I contact, a repo (P1, P2) | Escalate on 11-16 via Jacob Coffee and the PyCon chairs; keep building |
| **Track** | **2026-12-04** | Written PSF yes to the store track | **Community track.** Open-source reference app on the public feed, an *unofficial* PWA demo on a Flet domain, internal testing only, no listing using PSF marks, re-offer for 2028. The CFP abstract is worded to fit both tracks |
| **G2** | 2027-01-31 | >= 85 % of M1+M2 rows green; PSF-signed internal builds; E1 reads real badges; 1.1.0 pinned | More than 15 % behind: cut order. More than 30 % behind: the PSF chooses reduced scope or Ionic for 2027. No store roles by **02-26**: community track. E1 failing: manual/HID becomes primary and the PSF buys 4 HID scanners (~$30 each) |
| **G3** | 2027-02-12 | Per item. **E2**: topic round-trip on iOS and Android with the PSF config (P5 by 01-31) and U5 merged. **E3**: the PR implementing #6948 (v1) merged and released by 01-15 (UNCONFIRMED; the issue, owned by FeodorFitsner, has no milestone) and the scheduling PR (with the D-113 receivers: a release build fires a scheduled notification after a reboot) + U7 merged. **E4**: U6 merged and the prompt works. Burn-down within 5 %; each "go" item released by 03-05 (last pin change) | That item's interim ships; it moves to 27.1 |
| **G-Staff** | 02-26 | Badge Day 1: >= 300 scans, 0 lost or misattributed, E1 >= 95 % first try | Fix list and retest at Badge Day 2; a failing tool ships behind its kill switch with the manual path |
| **G4** | 03-31 | Every committed id green; 2027 feed parsed; contract nightly green for 7 days | Cut order until green |
| **G5** | 04-14 | Beta crash-free >= 99.5 %; 0 open P0; Badge Day 2 passed; budgets met; P11 forms and review demo account ready | Submit by 04-23 if only server-mitigable P1s remain; otherwise the PSF decides (Ionic + an Appflow content update) |
| **G6** | 05-05 | Crash-free >= 99.5 % | Freeze on the last good build; kill switches |

---

## 8. Quality

### 8.1 Testing

| Layer | What | Gate |
|---|---|---|
| Unit (pytest + hypothesis) | signing vectors, `parse_badge`, door admission table, outbox state machine, slugs (`qube-research--technologies`), `.ics` escaping, DST/device TZ, placeholder filter, search rules, change-log diff, staff gating truth table | PR |
| Differential | Ionic's own `processData`/`filterSession`/pipes bundled into a Node harness (`tools/ionic_reference/`) on the 2025/2026 feeds; Python output must match | PR |
| Contract | JSON Schemas for `conference.json` and every `/api/v1` response (recorded from staging); nightly run against the live feed and staging opens an issue on drift; schemas offered to `pycon-site` | PR + nightly |
| UI flows | ~25 `flet_app`/Tester flows: swipe (host mode only: the on-device `RemoteTester` has no `drag`/`drag_from`/`tap_at`) and long-press favourite, filter, search all days, Jump to Now + Back (#313), drill Back (#279), login, logout guard, offline lead scan, door check, swag, CoC cooldown | PR smoke, nightly |
| Fallback parity | UI suite with all capabilities faked on and off; nightly build against `flet@main` | nightly |
| Feature trace / goldens | every non-dropped id has a named test (from M2 the gate checks the ids of each milestone once it exits, and every non-dropped id from G4; work without a feature id, such as the #312 change log and deep links, is traced as `X-` ids from `docs/backlog.md`) / 14 screens × 5 modes × 2 widths + app-level `Tokens.text_scale` 2.0 (emulation; Flet cannot set the OS text scaler), DEMO clock | PR from M2 / nightly + PR subset |
| Devices | Pixel 6a, low-RAM Android (API 34), Pixel 9 (API 36, 3-button nav for #311), API 26 only if OD-1; iPhone SE 2 (iOS 15/16), 12 (18), 16 (26), iPad | per RC |
| Field | Badge Day 1 (02-24, staging) and Badge Day 2 (04-09, RC1) with PSF-E and printed badges: two devices on one attendee, 30 min airplane mode, server audit vs outbox | G-Staff, G5 |

### 8.2 Accessibility

- **Contrast and targets.** Palette contrast is unit-tested at >= 4.5:1, and >= 7:1 for HC text. The one exception is the gold `favorite_star` icon, which keeps `#fbbf24` in HC (5.1:1 on the header). Touch targets are >= 48 dp.
- **Labels.** Ionic aria strings are kept verbatim, for example "Show booth N on the Expo Hall map", "Close floor plan" and "Total checked in for this session".
- **Non-gesture paths.** Long press or the star replaces swipe-to-favourite; manual entry replaces the camera.
- **Motion and text size.** Repeating animations stop when `reduce_motion or disable_animations` is set (5.6). 200 % text is covered by manual device passes at the maximum OS font size in the M4 audit, plus goldens at the app-level `Tokens.text_scale` 2.0, which emulates OS text scale. Flet has no API to set or emulate the OS text scaler, so the goldens are not OS text-scale coverage; an upstream text-scaler override would close that gap.
- **Shared identifiers.** `Semantics(label=<Ionic aria string>, identifier=<stable test id>)`: the label serves screen readers and the identifier serves tests (`Tester.find_by_semantics_identifier`, Appium/XCUITest). The identifier is never announced.
- **Scan feedback.** Every outcome is rendered in a status line wrapped in `ft.Semantics(live_region=True, ...)`, with a distinct haptic pattern. `await svc.announce_message(...)` is called only when `features.supports_announcements` is True (iOS, web), because Android discourages direct announcements and may ignore them. The outcomes are Checked in, Already, Entry not permitted, Invalid QR and Captured. The TalkBack scripted flows cover the live-region path.
- **Audits.** At M4, a scripted VoiceOver and TalkBack pass over 12 flows, plus a CC audit.

### 8.3 Performance budgets

These budgets come on top of the criterion S6 start and size targets.

| Area | Budget |
|---|---|
| Feed processing (824 KB) | <= 400 ms on a Pixel 6a (spike S3), with version-keyed memos |
| Scrolling | <= 1 % janky frames |
| Memory at max expo zoom | <= 300 MB on the low-RAM device |
| Web, Pyodide first load | <= 8 s on 4G; if missed, the web build becomes an "install the app" page |

Levers:
- `.pyc` compilation, lazy imports, and rendering from cache first.
- AAB with `[tool.flet.cleanup]`.
- No heavy wheels (bs4, cryptography, pydantic).
- Re-encoded floor plans.

### 8.4 Observability

- **Crash reporting.**
  - Sentry in the PSF org, via the logging and asyncio handlers, PII-scrubbed, opt-out, tagged `27.0.0+<build>` and caps.
  - Spike S6 verifies the SDK on device; the fallback is an envelope reporter.
  - Play vitals and the Xcode Organizer cover native crashes.
- **No analytics** (OD-3).
- **Operational visibility.**
  - Outbox counters on staff screens.
  - Developer Info: version, build, sha, API host, feed age, caps, FCM token.
  - A redacted diagnostics share.
  - A conference-week dashboard: crash-free rate, adoption, outbox failures, banner delivery.

---

## 9. Build, release, distribution, OTA replacement, PWA/web, dev loop

### 9.1 `pyproject.toml` (deltas to `docs/research/flet/build-packaging-ci.md` §4)

- **Pins.** `flet==<newest released 1.1.x or 1.2.x on 2027-03-05>` exact (one bump at most, by 03-05). `flet-permission-handler` and `flet-secure-storage` at the same version. `httpx` with the `platform_system != 'Emscripten'` marker. `tzdata` and `sentry-sdk` exact (M0). `requires-python = ">=3.14,<3.15"`.
- **Identity.** Android: `bundle_id="org.pycon.us"`, `min_sdk_version=34` (26 only with OD-1), `target_sdk_version=36`. iOS: `bundle_id="org.pycon.us.2023.onsite"`, `team_id="BMM5U3QVKW"`, `export_method="app-store-connect"`.
- **Extensions.** Only in `[tool.flet.android|ios].dependencies`, pinned exactly. E1 is always there; E2-E4 only after their gate. Release builds have no editable `[tool.uv.sources]`.
- **Permissions.**
  - `permissions=["camera"]`, with usage strings that explain staff scanning (review 5.1.1).
  - `NSCalendarsWriteOnlyAccessUsageDescription` (Apple's spelling). In the release that ships E4, also `NSCalendarsUsageDescription` (iOS 15/16) and `NSContactsUsageDescription` (the `add_2_calendar` README warns of a crash without it).
  - `ITSAppUsesNonExemptEncryption=false` (PSF to confirm).
  - `AD_ID` removed.
  - Only in the release that ships E2/E3 or the autofill upgrade: `POST_NOTIFICATIONS`, `SCHEDULE_EXACT_ALARM`, `UIBackgroundModes` and `[tool.flet.ios.entitlement]`.
- **Other.** `[tool.flet.android.deep_linking]` and `[tool.flet.ios.deep_linking]`, each `scheme="pyconus" host="app"` (D-109; flet-cli ignores the global `[tool.flet.deep_linking]` for Android and iOS until [flet-dev/flet#6953](https://github.com/flet-dev/flet/pull/6953) lands). Splash and boot screen `#680579`. No custom template, helper plugin or Gradle init script.

### 9.2 Versioning and CI/CD

**Versioning**
- `[project].version = 27.MINOR.PATCH`.
- The build number is computed in CI as `YY*1000 + MINOR*100 + PATCH*10 + RESPIN`. For 27.0.0 that gives 27000-27009, all above 26022.
- Ten numbers cannot hold the 2-weekly internal builds from M2 plus beta and RCs, so internal-only `v27.0.0-alpha.N` tags take `(YY-1)*1000 + 900 + N` (26900+N). They go to Play internal and TestFlight internal only and are never promoted; `alpha.5` (03-30) is the freeze build.
- A `builds.txt` ledger refuses reused numbers, and the tag must equal the version.

**`ci.yml`** (PR, no secrets)
- ruff, pyright and a lint that keeps Flet out of core.
- Unit, differential, contract, UI smoke and a golden subset.
- Debug-signed `apk` (no release keystore), `ios-simulator` and `web` builds via `flet-dev/flet-build-action@v1`.
- Licence gate.
- A guard against `FLET_PAGE_URL`, LAN hosts, prerelease pins and literal years (the class of the 26.2.0 incident).

**`release.yml`** (tag `v2[0-9].*`, so the 2028 rollover needs no workflow edit; `tools/check_release.py` enforces the tag grammar and the ledger; protected `release` environment; PSF-I is a required reviewer; secrets are PSF-held)
1. Write `build_info.py` and the caps manifest.
2. Build `aab` (ubuntu), `ipa` (macos-26) and `web`.
3. Verify the AAB is signed with the upload key.
4. Upload to the Play internal track (`r0adkll/upload-google-play`), TestFlight (`xcrun altool` with an App Store Connect API key) and a Firebase Hosting **preview channel**. A tag never deploys the PWA live: a manual `promote-web` job clones the G5-tested channel to live at release, with no rebuild.
5. Print the caps matrix into the release notes.

**`content.yml`** (its own `content` environment, lighter approval than `release`): validates and deploys `app-config`/`app-content`, so content fixes meet the 30-minute target (criterion S11).

**`nightly.yml`**
- Full UI and golden suites.
- Fallback parity.
- A `flet@main` build.
- Contract checks against the live feed and staging.

### 9.3 Release train

- **Builds.** Internal builds (`v27.0.0-alpha.N`) every 2 weeks from M2, on the real ids once P4 lands. Closed and public beta from 04-01.
- **Promotion.** The release promotes **the exact beta binary that passed G5**, with no rebuild.
- **Rollout.** Play rollout goes 20 % → 100 % over 3 days. iOS phased release is **off**.
- **Review.** Submission includes a review demo account with staff roles and notes on camera use (P11).
- **Hotfixes.**
  - Path: branch from the tag → `v27.0.N` → both stores within 2 h of CI. Expedited review in conference week only.
  - The path is rehearsed **04-20 → 04-24 on the newest Xcode and runner image**, because Apple may raise its minimum in late April 2027 (UNCONFIRMED).
- **Conference freeze:** 05-05.

### 9.4 OTA replacement (Appflow sunset)

| Appflow use | Replacement |
|---|---|
| Content fixes | `conference.json` + **`app-content.json`** (keynotes, reminders, Wi-Fi, booths, pins, overrides, URLs, sponsored spaces, tour id), as schema-validated PRs in a PSF repo, deployed in < 5 min |
| Emergency off | **`app-config.json`** `features.*` vetoes switch any staff tool or native capability back to its interim |
| Update banners | `latest`/`min_supported` vs `BUILD_NUMBER` drives the banner, drawer card and hamburger dot (LIVE-02..04), plus a blocking dialog (NOTIF-12) |
| Announcements | app-config `banners[]` (category, severity, start and end time), plus FCM if E2 ships |
| Instant fix for all | The PWA redeploys from the same tag in minutes and is linked from a banner if the native app breaks |

Both files:
- are served `no-cache` from `us.pycon.org/{YEAR}/mobile/` or PSF Firebase Hosting (P7);
- are fetched on start, on resume and every 5 min;
- fail silently when unreachable.

`app-content` also ships as a bundled fallback.

### 9.5 PWA/web (T2) and dev loop

**PWA**
- `flet build web` (Pyodide, canvaskit, path URLs) on PSF Firebase Hosting with a `** -> /index.html` rewrite and `no-cache`.
- Online- and browse-only, using `pyfetch`. No staff tools, sqlite, push or reminders.
- Login only with CORS.
- Also serves as the incident fallback and the projector demo.

**Dev loop**
- `uv run flet run -r` (optionally `--ignore-dirs tests,tools`) on desktop with hot reload. Without `-r`, only `src/main.py` is watched, so edits under `src/pycon_us/` would not reload. Hot reload restarts the Python process, so state resets; `DEMO` and `PYCON_FAKE_NOW` keep the restart deterministic.
- `flet run --ios/--android` on the companion app, which has an empty manifest and so shows the interims.
- `flet debug ios|android` for native features.
- `tools/devserver.py` serves recorded feeds and a fake signed `/api/v1` (check-in, lead, CoC and `mobile_state` from fixtures), so contributors need no PSF credentials.
- `PYCON_FAKE_NOW` sets the clock. `DEMO=1` gives the bundled feed, a fixed clock and the simulated scanner on a separate DB.
- No `FLET_PAGE_URL` dev client (that is the 26.2.0 incident class).

---

## 10. Partnership and community

### 10.1 Engagement steps

1. **2026-10-16** (U): email infrastructure@python.org, cc Jacob Coffee. Include the section 1 pitch, a 90-second recording of the schedule running on the 2026 feed, and the P-table. The offer: "27.x of your listings, your keys, your CI, your repo; we do the work and the Flet upstream; stop at any gate."
2. **10-23**: send a live web demo link.
3. **By 11-13 (G1)**: a 45-minute call to agree criteria S1-S12, the gates and the repo.
4. After G1: a weekly 5-bullet status in Linear PYMOBIL and a demo at each milestone exit.
5. **12-04**: written track decision.
6. The PSF holds the release button. PSF-I is a required reviewer on the `release` environment and co-owns the release workflow, the signing config and the app-config schema in CODEOWNERS.

### 10.2 What the PSF must provide, and when

| # | Item | Needed by | Unblocks | If late |
|---|---|---|---|---|
| P1 | Agreement in principle, PSF-I contact, Linear PYMOBIL access | 2026-11-13 | everything | escalate; track decision 12-04 |
| P2 | Branch `flet-2027` in `PyCon/pycon-us-mobile` (or a new repo) with Actions | 2026-11-20 | CI, contributors | keep the public repo, transfer later |
| P3 | Staging `/{YEAR}/api/v1`; per-role test `APIAuth` keys (attendee, lead-retrieval, door-check, swag, mask-violation, speaker); sample badges; `mobile_state` PATCH semantics; idempotency of `capture`/`redeem_products`; whether manual check-in may omit the validator | **2026-12-15** | T0-P, T1 | devserver fixtures; login hidden in alpha; staff chain slips |
| P4 | App Store Connect App Manager or API key (app 6446810296); Play release manager (`org.pycon.us`); upload keystore in the PSF `release` environment | **2027-01-15** | signed builds (M2) | escalate; after **02-26**, community track |
| P5 | Firebase `pycon-us-2023-mobile` app configs, APNs key, a `test-*` topic, access to the #300 console | **2027-01-31**, only for push | E2 at G3 | push in 27.1 |
| P6 | Decisions: OD-1, OD-3, OD-4, OD-5, OD-7, OD-9, OD-10, CORS | 2027-01-15 | details | defaults apply |
| P7 | Hosting for app-config, app-content and the PWA domain | 2027-01-31 | gates, kill switches | Firebase Hosting under the PSF project |
| P8 | 2027 sample feed or schema preview | **2027-02-15** | parser | the nightly contract catches drift after ~03-13 |
| P9 | 2027 content: keynotes, booth geometry (booths 139 and 336 have no geometry today; 59 of 61 match), floor plans, Wi-Fi, reminders, Concept3D id, sponsored spaces, CoC contacts | **2027-03-20** | M4 | feed only; update content after release |
| P10 | Badge Day staff and printed badges; a server export of the test-badge records within 24 h of each Badge Day (for the audit); whether Badge Day 2 may run on production with test badges | 02-24, 04-09 | criterion S4 | G-Staff risk |
| P11 | Data Safety, App Privacy labels, privacy policy, age rating, export compliance; review demo account with staff roles | **2027-04-09** | submission | slips toward 04-23 |
| P12 | Conference-week on-call partner with store, Firebase and hosting rights | 05-05 → 05-18 | hotfixes | U-only, slower |
| P13 | (Optional) Appflow access for bridge 26.3 | 2027-03-15 | NATIVE-10 bridge | clean slate |

### 10.3 Licensing, repo, contributors, bus factor

- **Licensing.**
  - The app is Apache-2.0 with DCO sign-off; the PSF uses its own marks in its own app.
  - Extensions are Apache-2.0 in `flet-dev`, written clean-room.
  - A CI licence gate allows Apache, MIT, BSD, PSF, ISC and MPL-2.0; anything GPL fails.
- **Repo.**
  - Public at `github.com/<U>/pycon-us-flet` until G1.
  - Then branch `flet-2027` in `PyCon/pycon-us-mobile`, which becomes `main` at 27.0.0. The Ionic tree moves to `ionic-2026` (tag `v26.2.1`).
  - The PRs that fix #279, #311, #312, #313 and #310 close those issues.
- **Contributors.** `good first issue` and `flet-extension` labels with screenshot specs; a CONTRIBUTING guide (pure core, async handlers, feature-trace tests); a Flet Discord channel. Goal: 2 named contributors by 2026-12-15.
- **Bus factor.** Secrets are PSF-held. At least one co-maintainer (ideally PSF-nominated) cuts a release build before 03-31: the `v27.0.0-alpha.5` freeze build (every earlier build is an internal alpha; the first beta is `v27.0.0` on 04-01). Runbooks cover conference week, hotfixes and year rollover.
- **Sprints** (2027-05-17/18; the day split is UNCONFIRMED): "PyCon US app + Flet extensions".
  - Targets: E5, E6, U2, U11, the T3 items that missed, and first-timer issues.
  - The sprint form is due **2027-04-15**.
- **Handover (09-30).** Docs, a 30-minute walkthrough, a credentials matrix (all PSF) and a rollover drill.

---

## 11. The PyCon talk, poster and demo plan

The CFP is expected ~2026-10-31 → ~2026-12-18 (UNCONFIRMED), with at most 3 proposals per person. U checks `us.pycon.org/2027/` weekly from 10-20 and pulls the dates below forward if needed.

| What | Content | Deadline |
|---|---|---|
| **Talk** (30 min): "The PyCon US app, rewritten in Python" | Why the PSF rewrote (Appflow); declarative Flet architecture; 263 features ported with differential tests; offline staff tools; capability-gated upgrades ("the app got better as Flet evolved"); shipping without OTA; live demo; how to contribute. Accurate on either track | abstract 11-14; mentorship ~11-20 (optional, UNCONFIRMED); **submit 2026-12-11** |
| **Poster**: "Scan, sync, survive offline: conference staff tools in pure Python" | Architecture and capability-matrix panels; phones, sample badges, airplane-mode toggle | submit 12-11; print by 04-30 |
| Demo video | 3 min, from M1 rows: offline schedule, dark theme, favourites, Now & Next, drill Back, scanner spike; HC theme and Jump to Now (M2 rows) only if they land early | **2026-12-07** |
| Not submitted | Tutorial, Charla (capacity, OD-16) | - |
| After acceptance | Speaker confirmation (notifications ~02-10..17, UNCONFIRMED); slides v1 **04-20**; dry runs 05-01 and 05-08; Flet and PSF blog posts 04-27..30 | ~02-25 onward |
| On site | Open Space "Write a Flet extension" (book Thursday ~05-13, UNCONFIRMED); lightning talk as fallback or "N thousand badge scans in Python"; sprint (form by 04-15) | May |

**Demo script** (7 min; DEMO-build phones on wired USB-C capture). Packaged apps cannot read `DEMO=1`, so the stage phones run a DEMO build from the `release.yml` demo job, with `DEMO` and `PYCON_ENV=staging` baked into `build_info`: it polls the staging `app-config`, so the veto in step 3 takes effect, and simulated scans never reach the production API.
1. Store QR: "the app you used this morning is Python".
2. Airplane mode → schedule from cache → Now & Next, HC-dark, swipe-favourite, floor-plan pinch zoom.
3. Scan a sample badge: PENDING → SYNCED. Then veto `scanner` in a staging `app-config` and show the manual fallback.
4. Hot-reload a 20-line `@ft.component` in the laptop's desktop window (`flet run -r`; a process restart, so the `DEMO` clock keeps it deterministic). The phone companion app would need the LAN, so it is not used for this step.
5. The same code as the web build.

Every step has a 20-second recorded fallback clip.

---

## 12. Risks and mitigations

| # | Risk | Trigger | Mitigation | Owner |
|---|---|---|---|---|
| R1 | The PSF chose another team or doesn't answer | No reply by 11-07; no written yes by 12-04 | Escalate through Jacob Coffee and the chairs; community track keeps talk, poster and extensions; never a competing listing | U |
| R2 | P3 (staging, keys, badges) late | 12-15 missed | Devserver fixtures; login hidden in the alpha; staff chain has 1 week of slack | PSF-I |
| R3 | P4 (store, signing) late | 01-15 missed | PSF runs `release.yml` itself; hard stop 02-26, then community track | U + PSF-I |
| R4 | E1 late or unreliable (focus, low light, CameraX, material_ui) | No decode by 01-31; < 95 % at Badge Day 1 | Manual/HID path from day one; HID scanners; exact pin; kill switch | U |
| R5 | Firebase Dart-only init or U5 fails | spike S8 negative (11-30); G3 no | Push moves to 27.1; banners + PSF email/Discord | U |
| R6 | Flet 1.1.0 or the point release slips | 1.1.0 not out by 01-15; hooks not out by 02-26 | 1.1.0 late: escalate the store chain (it is on the iOS critical path, 7.3); maintainer prioritises it; iOS builds on 1.0.4 + Xcode 26 only while Apple accepts them, with E1 off (manual/HID). Hooks late: interims stay. No prerelease, no fork | U / FT |
| R7 | Capacity (solo maintainer, Flet duties, no contributors) | Burn-down > 15 % behind; 0 contributors on 12-15 | Cut order; zero-contributor variant; T3 only with margin | U |
| R8 | 2027 feed/API changes late | No P8 by 02-15; contract red after ~03-13 | Tolerant parser; feed URL and base path in app-config; server content | U + PSF-I |
| R9 | Store rejection (2.1 demo account, 5.1.1 strings, ITMS-91053) | Rejection after 04-16; spike S5 warning | Early throwaway upload; U13; P11 review account; 04-23 fallback | U + PSF-I |
| R10 | Apple raises the Xcode minimum in late April (UNCONFIRMED) | Apple notice | Submit 04-16; hotfix rehearsal on newest Xcode; Flet 1.1.0 (required; 1.0.4 cannot build on Xcode 27) builds with Xcode 27 | U / FT |
| R11 | Conference P0 with no OTA | Crash-free < 99 % or broken flow | Kill switches, `@safe`, bootstrap guard, PWA, 2 h hotfix lane, on-call (P12) | U + PSF-I |
| R12 | Staff data loss, duplicates, misattribution | Any Badge Day mismatch | Outbox snapshots + idempotency keys; synced rows kept; server audit | U |
| R13 | Performance or size over budget | Start > 3 s or download > 45 MB at M2 | Cached view models, trimmed wheels/assets, lazy imports | U |
| R14 | Users lose local state on upgrade | Support reports | Release 2+ weeks early; favourites from `mobile_state`; explainer; optional bridge | U |
| R15 | Live demo fails | Rehearsal failure 05-01/05-08 | DEMO build, wired capture, recorded clips | U |

---

## 13. Open decisions for the user (each with a recommendation)

| # | Decision | Recommendation |
|---|---|---|
| OD-1 | Android minSdk (#307) | **Propose 26 to the PSF; ship 34 until they approve.** iOS minimum is 15 from Flet 1.1.0 (1.0.4 builds for 13.0), which is already wider than Ionic's 18. On Android below API 34, OS high contrast is not detectable; users pick HC manually in Settings. |
| OD-2 | Push in 27.0 | **Attempt it, gated at G3.** Polled banners plus email/Discord are the committed baseline. |
| OD-3 | Analytics | **None in 27.0.** Firebase parity only if the PSF reads the data and E2 ships. |
| OD-4 | Crash reporting | **Sentry in the PSF org**, PII-scrubbed, opt-out and disclosed. |
| OD-5 | Favourites at login | **Union on the first sync, then server-authoritative** (the PSF confirms PATCH semantics). |
| OD-6 | Default theme | **"Match system" for new installs**, also following the OS high-contrast setting. |
| OD-7 | Encrypted debug dump | **Redacted diagnostics.** The CryptoJS format with Ionic key names only if a PSF decrypt tool exists. |
| OD-8 | Appflow bridge 26.3 | **Skip** unless the PSF offers capacity by 03-15. If it ships, it carries non-secret prefs only and is deleted after import. |
| OD-9 | Staff data retention | **Inventories and directories stay in memory only.** Purge synced rows 7 days after the conference and on account switch. |
| OD-10 | CoC capture pacing | **3 s per-code cooldown**; ask whether the server dedupes. |
| OD-11 / OD-12 / OD-13 | "Favorite all" scope / Now page / favourites view vs filter | **Whole track with Undo / respect end times, no track filter / show every favourite** |
| OD-14 | Where new extensions live | **Standalone `flet-dev` repos now, the monorepo after the conference.** |
| OD-15 | Name for the #6948 package (`flet-local-notifications` is taken) | **`flet-notifications`** (free on 2026-10-11), agreed with the #6948 owner. |
| OD-16 / OD-17 | CFP proposals / repo | **Talk + Poster only / branch `flet-2027` in `PyCon/pycon-us-mobile`** |
| OD-18 | In-app emergency banners vs the toggle | **Always show in-app**; the toggle governs OS notifications only. |
| OD-19 | Where the flet-cli hooks ship | **A 1.1.x point release by 2027-02-26.** |
| OD-20 | Branding | **"Built with Python" on Welcome and About; "Made with Flet" only in Developer Info.** |
