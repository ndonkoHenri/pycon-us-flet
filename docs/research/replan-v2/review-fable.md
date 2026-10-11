# Independent review for the v2 plan (Fable 5.1, 2026-10-11)

Inputs read: the pivot brief (binding), PLAN.md in full, the headings and key sections of every `docs/*.md`, `research/flet/capability-index.md` in full, the Flet ecosystem and prior-art sections of `context-and-ecosystem.md`, the schedule-cluster and native-gaps research, `decisions.md` section N, and a few spot checks against the local Flet monorepo (`ListView`, `Markdown`, `Image`, `flet.testing`, flet-cli commands; `RefreshIndicator` still absent; `gh project` available in gh 2.100).

Framing I used throughout: the audience is Python developers at PyCon. What impresses them is not feature count. It is (a) an app that feels native and never makes them wait, (b) two or three things the official app never did, and (c) code they can read on the sprint day and contribute to. Every recommendation below is measured against those three and against the owner's "Zen of Python" rule.

---

## 1. What would make this the most delightful showcase (without bloating scope)

### 1.1 The three hero qualities

**Offline-first from the first launch.** The Ionic app shows "Fetching latest sessions..." on first run and whenever the cache is cold. Ship the current conference feed as a **bundled snapshot** (`assets/data/2027/conference.json`, refreshed by a CI job or by hand before each release) and treat the network as a background refresh. The schedule renders from the bundle in the first frame; the "Updated N h ago" chip tells the truth. This costs almost nothing (one asset, one `if cache is None: use bundle`) and gives the single best demo moment: install, airplane mode, open, everything is there.

**"Now & Next for me".** Ionic's Now page ignores favourites, ignores end times (the last slot of the day stays "Happening Now" until midnight) and has no way back to Now from a detail. A Python version can do the obviously right thing: a timeline with a live "now" line, sections "Happening now", "Your next session in 23 min (Room 104AB)", "Up next", and a quiet state outside conference hours. Pure functions over the processed feed, trivially unit-tested with a fake clock. This is the screen to open the talk with.

**My Agenda done properly.** Favourites today are a filter on the schedule list. Promote it to a first-class personal agenda: per-day plan, **overlap detection** ("conflicts with *X*" chip when two favourites overlap), "Export my agenda" as one `.ics` share (already planned per session; make it the whole agenda), and, once E3 lands, "Remind me 10 min before" per favourite. All pure Python plus one `ft.Share` call.

### 1.2 Smaller touches that read as polish

- **One search box over everything** (sessions, speakers, rooms, sponsors, open spaces) with instant results. Ionic has a search bar per page, 250 ms debounce, 25-row infinite scroll. Over ~700 records, Python filtering is sub-millisecond; render the top N per category. Do it as a `SearchBar` on the Schedule and Speakers roots that opens a full-screen result list.
- **Schedule change log** (#312): keep. It is cheap (diff by id after each fetch, sqlite or JSON), unique among conference apps except EventFahrplan, and it answers a real complaint from 2026.
- **Session detail**: speaker chips with avatars, "in this room next", a floor-plan pin, share a deep link (`pyconus://session/123`), copy the Wi-Fi password from the Wi-Fi page with one tap. The room pin and the share are two lines each.
- **Accessibility as a documented deliverable**, not a checkbox: every list row and button has a `Semantics` label, the four scripted TalkBack/VoiceOver flows in the README, a screenshot set at 200 % OS text size. Flet cannot emulate the OS text scaler, so this is a manual pass on both phones; a `page.text_scale_factor` override would be a nice tiny upstream addition that makes the screenshots automatable.
- **"View source" in every screen's overflow menu** (once the repo is public): opens the Python file of that screen on GitHub. On-message, unique, ten lines of code. Pair it with Developer Info (version, Flet version, feed age, Python version).
- **Material 3 polish**: tonal surfaces from one brand seed (`#3B3EA9`) with the PyCon accents as overrides, a large-title Schedule app bar, a `SegmentedButton` day picker that highlights today, hero-less but snappy page transitions. No custom animations beyond what Material gives for free.

### 1.3 Demo moments worth designing for (7 minutes)

1. Fresh install, airplane mode, open: schedule, favourites, Now, floor plan, all instant.
2. "Now & Next for me": the countdown, the conflict chip, export agenda to the calendar app.
3. `flet run --android` companion app: edit the Now screen's Python on the laptop, hot reload on the phone in front of the room (the companion app covers every attendee screen; only extension screens need `flet debug`).
4. Staff mode against the local mock: scan a printed badge, toggle airplane mode, scan two more, go online, watch the outbox drain. Then "Scanner unavailable, enter the code" fallback.
5. "View source" on the screen you are looking at.

### 1.4 What not to build

Web/PWA, Cupertino variants, split pane, `app-config` remote gates, analytics, FCM push, the Appflow bridge, the encrypted debug dump, Dev Tools behind a 7-tap unlock, in-app talk feedback or chat, multi-event support, zoom-to-booth animation (highlight is enough), the Concept3D 3D tour (link out). Each one is either PSF-only, platform-out-of-scope, or scope that no one at the demo will notice.

---

## 2. What in v1 is over-engineered or misdirected for a 1-2 person community project

v1 is an excellent **reference** (the Flet facts in `decisions.md` §N, the capability index corrections, the feed quirks in `schedule-cluster.md`). As a **plan** it was built for a different customer. The parts to remove or shrink:

1. **Parity as a gate.** `G-PARITY`, the differential suite that bundles Ionic's `processData` into a Node harness, "every non-dropped id has a test named after it", and the `feature_trace` CI gate. The brief says this is not a 1:1 port, so byte-equality with Ionic's derived output (including its bugs: the missing `startTime` on the first group, the mutable `hide` flags) is the wrong target. Replace with: recorded 2025/2026 feeds as fixtures, snapshot tests of **our** processed model, and ten named invariants (no session lost, stable ids, placeholders filtered, Job Fair grouped at 10:00, collapsed Posters/Lunch rows, speakers linked by name). Keep `feature-catalog.json` as a checklist with a `phase` and `disposition` column; drop the gate.

2. **The capability machinery.** `Caps` as an `@ft.observable`, build-time manifest, API probes, server veto, "CI runs every capability on and off" (L5 fallback parity), capability matrix in release notes. For two or three optional extensions this is a framework. The smallest correct version: one generated `build_info.py` (CI writes `SCANNER = True` when the extension is in `[tool.flet.android|ios].dependencies`; the committed dev stub says `False`, so the companion app never receives a control it lacks) plus `try: import flet_barcode_scanner except ImportError` in one `platform/` module. No observable, no probes, no parity matrix; one unit test per interim.

3. **Routing fidelity to Ionic URLs.** Keeping `/app/tabs/...` 1:1 only mattered for web URLs. With no web target, use a flat, readable tree: `/schedule`, `/schedule/:day`, `/session/:id`, `/speakers`, `/speaker/:id`, `/rooms`, `/room/:slug`, `/map`, `/expo`, `/sponsors`, `/more/...`, `/staff/...`. Keep **one** idea from v1: the recursive drill segment so session -> speaker -> session walks back one hop at a time (that fixes #279 and is the kind of thing the Router should be shown doing). The global-modal floor plan with a `back=` query parameter is clever; a local modal route under each opener is simpler and good enough.

4. **Release engineering for a store we do not ship to.** Build-number arithmetic with a `builds.txt` ledger, `alpha.N` numbering, protected `release`/`content` environments, PSF reviewers, Play staged rollout, iOS phased release off, hotfix rehearsal on the newest Xcode, Sentry, on-call, conference freeze. Replace with one `build.yml` on tag that attaches a debug-signed APK (and, when the owner wants, an IPA built locally) to a GitHub release, plus TestFlight internal and Play internal testing on the owner's accounts when a phase exits. iOS builds in CI need macOS runners; build iOS locally and keep CI to lint, tests and an `apk`.

5. **Server-driven everything.** `app-config.json`, `app-content.json`, kill switches, version gates, banner polling every 5 minutes. The brief already replaces these with bundled, schema-checked data files per year. Do exactly that: `data/2027/{conference.json, content.toml}` validated by a pytest.

6. **Theming by exact hex.** Four hand-built `ColorScheme`s with no seed, so Ionic's colours stay exact. With Material 3 as the design language, seed from the brand purple, override primary/secondary/tertiary with the PyCon accents, test contrast of the resulting scheme. Two themes (light, dark) in P1; HC variants in P2 only if Flet's `ColorScheme` makes them a data change.

7. **`@safe` + a lint rule forbidding unwrapped handlers.** The underlying problem (a handler exception sends `SESSION_CRASHED` and shows Flet's error screen) is a Flet problem, and the owner is a Flet maintainer. Fix it upstream (v1's U15: handler/effect exceptions are logged and surfaced through an app-level hook, not fatal), then the app needs no decorator and no lint. Same reasoning for `RefreshIndicator` (U1) and `page.get_app_info()` (U4): three small core PRs in P0/P1 remove three interims.

8. **Test pyramid sized for a product team.** Nine layers, 29 UI flows in two modes, 14 x 5 x 2 goldens, nightly `flet@main`, contract tests against private staging, Badge Days. Keep: pytest on `core/` (fast, exhaustive, with the two feed fixtures), 6-10 host-mode `flet.testing` flows for the attendee core, a handful of goldens only once the UI is stable (they break on every Flutter upgrade), and a mock-server test for the staff tools. Skip goldens in P1 entirely.

9. **The capacity model, 10 spikes, 7 gates, 15 risks, 20 open decisions.** Useful once; keep the five spikes that retire real unknowns (section 3) and fold the rest into phase exit criteria.

10. **Dropped by the brief, worth restating so they do not creep back:** Ionic storage bridge (NATIVE-10), encrypted debug dump, Dev Tools page (replace with a Developer Info row and a `PYCON_FAKE_NOW` env var), the sponsor strip's `BottomAppBar` + `NavigationBar` stacking trick (a simple sponsor row at the top of the Schedule and Sponsors pages is cleaner), the PWA.

What v1 got right and v2 should keep verbatim: the pure `core/` package with no Flet import; the Flet facts in `decisions.md` §N; the data quirks list; one context per observable store; async handlers only; the staff gating truth table; the sha1 signing details; "never lose a scan" as a design rule for the outbox.

---

## 3. Riskiest technical assumptions about Flet on Android/iOS, each with a cheap spike

Each spike is a half-day to a day, produces a one-page `docs/spikes/NN-name.md` with numbers and a verdict, and is an issue with the `type:spike` label.

| # | Assumption at risk | Why it is risky | Cheap spike to retire it |
|---|---|---|---|
| S1 | **Cold start <= 2.5 s p50 on a mid-range Android, first launch <= 6 s** | A Flet mobile app = Flutter engine + embedded CPython + an unpack step on first launch ("Preparing") + Python import time (`httpx` alone is a few hundred ms) + first render. Nobody has measured this with a real dependency set | Build a release APK of a stub that imports `httpx`, `zoneinfo`, `sqlite3`, parses the 824 KB 2026 feed and renders one list. `adb shell am start -W` x 10, first launch vs warm, on the slowest device you own. Repeat with `urllib` instead of `httpx` and with `[tool.flet.compile]` on/off. Decide lazy imports and whether parsing goes to a thread |
| S2 | **A 150-row rich day list re-renders fast enough in components mode** | `ListView` is lazy on the Flutter side, but in declarative mode the Python side rebuilds and diffs the whole control tree on each state change. Toggling one favourite or typing one search character must not rebuild 150 rows x 10 controls and ship them over the channel | A 150-row list of realistic rows (title, badges, time, room, avatars) as `@ft.component` rows with `key=`; measure time from tap to visible star and search-as-you-type latency; try memoising rows on `(id, is_fav)`; try `item_extent`. Verdict decides the row architecture before any screen is written |
| S3 | **Feed HTML renders acceptably through `html.parser` -> Markdown -> `ft.Markdown`** | Descriptions, bios, sponsor blurbs and content pages are HTML; Markdown has no HTML pass-through, so unknown tags print literally | Run the converter over every HTML field in the 2025 and 2026 feeds, count unhandled tags, render 20 random results in a detail view on a phone. Half a day; also yields the fixtures for the converter's tests |
| S4 | **Floor plans and the expo map work in `InteractiveViewer` on a low-RAM phone** | Large PNGs decoded at full size, positioned hotspots inside a scaled `Stack`, hit-testing at 3x, `on_size_change` timing | Load the three real floor plans (re-encoded to <= 2048 px), add ten hotspots, zoom to max, tap, watch memory in Android Studio's profiler. Verdict: image sizes and whether hotspots are `Container`s or a `GestureDetector` with coordinate maths |
| S5 | **A barcode scanner extension over `mobile_scanner` builds and decodes in a release app on both OSes** | The one hard gap. Risks: the `material_ui` split in Flet 1.1, CameraX/iOS permission flows, extension packaging, and it cannot run in the companion app | The smallest extension: one control, one `on_detect`, torch toggle. `flet build apk` and `ipa`, decode a printed QR in daylight and under a desk. Do this at the start of P3, not P0: the attendee core does not depend on it |
| S6 | **Scheduled local reminders can be delivered reliably** | #6948 v1 excludes scheduling; Android needs manifest receivers the template cannot add, exact alarms are user-granted on API 34+, iOS needs the plugin's own permission request | One throwaway notification scheduled 2 minutes out, app killed, phone locked, on both OSes; then the same after a reboot on Android. Use inexact alarms by default. This spike sizes the upstream contribution and the pyproject hooks it needs |
| S7 | **Download size is acceptable** | A minimal Flet APK measured 55.5 MB (arm64), ~25-40 MB download; iOS is larger. Fine for a showcase, but it is the first thing a sceptic asks | Release AAB with the real dependency set -> `bundletool build-apks --device-spec` -> size; try `[tool.flet.cleanup]` and excluding tests/tools. Record the number; set the budget from reality (40 MB Play download is a sensible line) |
| S8 | **`zoneinfo` works on device** | Mobile Pythons may ship without a tz database | Bundle `tzdata`, assert `ZoneInfo("America/Los_Angeles").utcoffset(...)` in the S1 stub. Five minutes inside S1 |
| S9 | **An IPA from the chosen Flet passes App Store Connect processing** | No `PrivacyInfo.xcprivacy` for the embedded CPython; ITMS-91053 could appear; Xcode 27 rejects 1.0.4's iOS 13 target | One throwaway TestFlight internal upload of the S1 stub from the owner's account in P0. Cheap, and it retires the worst late surprise |
| S10 | **Developing on Flet 1.1.0-dev is practical** | 1.1.0 is needed anyway (iOS 15 floor, Xcode 27, `material_ui` for extensions) but is unreleased; a prerelease pin makes the template resolve the stable Dart package ("Unknown control") | Decide in week 1: develop against the monorepo with path overrides for both the Python package and the Dart package, prove `flet build apk` and `ipa` once from that setup, document the two lines in AGENTS.md. Pin a released version whenever one exists |
| S11 | **Edge-to-edge and system navigation on Android 15/16 (target 36) behave** | Target 35+ enforces edge-to-edge; #311 in the Ionic app was exactly this class of bug; Flet's `View` insets have not been checked with 3-button navigation | Part of S1's stub: a list that reaches the bottom, 3-button and gesture nav, light and dark status bar icons. Fix upstream if the template needs an inset flag |
| S12 | **Components mode and the Router are solid enough for a 25-screen app** | Both are new in 1.0; v1 already found non-obvious rules (one context per observable, async-only handlers, `manage_views` wrapping) | Not a separate spike: P1 builds the shell and three screens first and files every Router/hook bug upstream the day it is found. Budget one day a week for that in P1 |

Lifecycle (the Now page's 60 s refresh while backgrounded, resume after hours) is checked incidentally in S1 and S2 by leaving the stub in the background overnight.

---

## 4. Suggested phase order and exit criteria

Phases, not dates; the soft markers from the brief are in brackets.

**P0 Foundations** [about two weeks]
- Repo, `AGENTS.md`, `pyproject.toml`, CI (ruff, pyright, pytest), issue templates, milestones, board.
- `core/`: feed model as frozen dataclasses, `process.py` with the invariant tests on the 2025 and 2026 fixtures, `timefmt.py`, `html_md.py`.
- Spikes S1, S2, S3, S7, S8, S9, S10, S11 with written verdicts.
- Exit: `flet build apk` from CI and an IPA from the owner's Mac both run the stub on real phones; the processed feed passes its tests; the Flet version decision and the row architecture are written down; the TestFlight upload processed.

**P1 Attendee core** [demo-worthy around end of November]
- Shell (bottom navigation: Schedule, Now, Speakers, Map, More; drawer only if the More tab overflows), Schedule by day with search and track filter, Session detail, Speakers list and detail, local favourites, Now & Next for me, offline cache + bundled snapshot, light and dark theme, Developer Info.
- Upstream: `RefreshIndicator`, non-fatal handler errors, `get_app_info()` as small core PRs.
- Exit: the owner uses it for a full simulated conference day (`PYCON_FAKE_NOW`) in airplane mode on both phones; no known crash; cold start within the S1 budget; 6 host-mode UI flows green; a 2-minute screen recording exists (CFP material, if submitted).

**P2 Complete attendee app**
- Rooms + floor plans, Expo map with hotspots, Sponsors, Open Spaces, Lightning Talks, Sprints, Job Listings, info pages (About, CoC, Wi-Fi, Help & Safety, Social), Settings (theme, reminders prefs), My Agenda with conflicts and `.ics` export, change log, deep links, "View source", accessibility pass 1 (TalkBack/VoiceOver on 6 flows, 200 % text), HC themes if cheap.
- Exit: every attendee row in the catalog has a disposition and the non-dropped ones are done; the a11y checklist is in the README with screenshots; a friend who is not the owner installs via TestFlight/Play internal and uses it without instructions.

**P3 Native upgrades (upstream work)**
- `flet-barcode-scanner` (S5), scheduled reminders in the official notifications extension (S6) plus whatever flet-cli hooks they need, add-to-calendar only if trivial.
- Exit: reminders fire on both OSes with the app killed; the scanner decodes a printed badge in a release build; each extension is published or merged; the app's interims upgrade by changing `pyproject.toml` only.

**P4 Staff tools against the mock**
- Mock server reproducing `/api/v1` (sha1 signing, `authenticate`, `check_features`, `mobile_state`, capture, note, door check, redeem, CoC), login, favourites sync, role gating per the v1 truth table, Lead retrieval with the outbox, Door check, Swag, CoC.
- Exit: the airplane-mode scan -> sync test passes on both phones; the signing test vectors pass; the gating truth table is unit-tested; a wrong role cannot reach a tool.

**P5 Polish, release, presentation** [well before May]
- Performance pass with real numbers, a11y pass 2, 2027 feed and content (the feed appears around March; until then the 2026 feed with a fake clock), repo public, README/blog, talk and demo script with recorded fallbacks, tagged `v1.0.0` with artifacts.
- Exit: the demo script runs end to end twice without Wi-Fi; the README explains how to run it in ten minutes; the open issues are all `later`.

Order rationale: the attendee core first because it is the showcase and has no hard gaps; native upgrades before staff tools because the scanner is what makes staff tools worth demoing; staff tools last because they are mock-only and the most code for the least audience.

---

## 5. GitHub workflow: traceability without bureaucracy

**Repo shape.** Private, `main` protected (PR required, CI green, owner merges; no review-count requirement, since the reviewer is often a model). Squash merges; the PR title becomes the commit subject. Branches `p1/42-now-page` (phase/issue-slug). Tags `v0.N` per phase exit with the APK attached; `v1.0.0` for the conference.

**Issues.** The rule in `AGENTS.md`: *an issue exists before any work that needs a decision, touches more than one area, or will take more than one sitting; a small fix may be a PR alone.* Four templates: `feature` (what/why/acceptance/screens), `bug` (device, OS, steps, expected), `spike` (question, method, budget, verdict section filled in on close), `upstream` (link to the flet-dev PR or issue, and what in this app it unblocks). One pinned **status issue per phase** updated weekly in five bullets (done, next, blocked, decisions, numbers), so anyone can follow without reading every PR.

**Labels.** Three families, nothing else: `area:` (core, schedule, now, speakers, rooms-map, sponsors, info, staff, build, a11y, upstream, docs), `type:` (feature, bug, spike, chore, docs, upstream), `phase:` (p0..p5, later). Plus `good first issue` and `needs-decision` (the owner must answer before work continues) and `blocked`.

**Milestones = phases**, with the exit criteria from section 4 pasted into the milestone description. Milestone progress bars are the burn-down; no `feature_trace` tool needed.

**Project board.** `gh project` works (`gh auth refresh -s project` once), so one board "PyCon US on Flet" with a Status field (Todo, In progress, In review, Done) and the built-in auto-add workflow for the repo. Keep it as the owner's glance view; if it becomes a chore, milestones and the status issue are sufficient.

**PRs.** Draft early, one concern per PR, aim under ~400 changed lines (spikes and generated fixtures excepted). Body sections, always the same: *What, Why, How I tested (device, OS, Flet version), Screenshots or recording (mandatory for UI, phone-sized, light and dark), Follow-ups (issues opened)*. `Closes #N`. CI on every PR: ruff, pyright, pytest, the host-mode UI flows; the `apk` build only on `main` and on a `build` label, to keep minutes down. UI PRs are reviewed by the owner on a device, not from the diff.

**Decisions and knowledge.** `docs/decisions.md` becomes a short append-only ADR list (number, date, decision, why, what it replaces); v1's D-numbers that survive are re-listed there, the rest go to `docs/v1-archive/`. `docs/spikes/NN-name.md` per spike. `docs/architecture.md` kept to a few pages that match the code. `CHANGELOG.md` written per tag.

**AI-agent collaboration rules** (the part of `AGENTS.md` that matters most):
1. Work from an issue; open a Draft PR within the first hour; never push to `main`.
2. Verify every Flet API against the local monorepo before using it; when relying on non-obvious behaviour, cite `file:line` in the PR body (v1's §N list is the seed of a `docs/flet-notes.md` the agent keeps current).
3. Never modify the Flet or Ionic repos from this project; upstream work is its own PR in flet-dev, linked from an `upstream` issue here.
4. Run the tests and, for UI, the app on a device or the companion app before marking a PR ready; say which.
5. Second opinions (other models) are summarised as a PR review comment with the agent's response to each point; raw transcripts are not pasted.
6. Anything that changes a decision, the phase scope, or a user-visible behaviour the owner has not seen gets `needs-decision` and stops.
7. No secrets, no PSF endpoints, no telemetry; the mock server is the only backend besides the public feed.
8. Keep PRs readable by a human in ten minutes; prefer a second PR over a long one.
9. `Co-authored-by` trailers name the agent; the owner is the author of record for merges.

---

## 6. Top 12 recommendations

1. **Ship a bundled feed snapshot and render from it in the first frame.** Offline-first from the first install is the cheapest, most visible differentiator and the best demo opener.
2. **Make "Now & Next for me" and My Agenda (conflict chips, whole-agenda `.ics`, later reminders) the attendee hero features.** They are pure Python, trivially testable, and the official app never did them.
3. **Drop parity as a gate.** Replace the Ionic differential harness, the 263-named-tests rule and `feature_trace` with fixture snapshot tests of our own model plus ten invariants; keep the catalog as a checklist with phase and disposition columns.
4. **Shrink the capability machinery to one generated `build_info.py` and a try-import.** No observable `Caps`, no probes, no server veto, no all-on/all-off parity suite.
5. **Fix the three small core gaps upstream in P0/P1** (non-fatal handler errors, `RefreshIndicator`, `get_app_info()`) instead of building `@safe` + a lint rule and two interims. The owner can; it benefits every Flet app and is part of the story.
6. **Run the cheap spikes in P0 and write the numbers down**: cold start, list re-render cost, HTML conversion coverage, download size, tzdata, a throwaway TestFlight upload, edge-to-edge on Android 15+. Scanner and reminders spikes open P3.
7. **Decide the Flet version in week one**: develop against the monorepo's 1.1.0-dev with path overrides (1.1.0 is required anyway for iOS 15/Xcode 27 and `material_ui`), prove `flet build apk`/`ipa` once from that setup, pin a release as soon as one exists.
8. **Simplify routing**: drop Ionic URL compatibility, use a flat readable route tree, keep only the recursive drill segment for session -> speaker -> session back behaviour; local modals, no global modal with a `back=` parameter.
9. **Decide the list-row architecture from measurement, not taste**: per-row `@ft.component` with keys and memo on `(id, is_fav)` is the likely answer, but S2 decides before any screen is written.
10. **Phase order P0 foundations -> P1 attendee core (demo by end of November) -> P2 complete attendee app -> P3 native upgrades upstream -> P4 staff tools on the mock -> P5 polish and presentation**, each with the exit criteria in section 4 pasted into its milestone.
11. **GitHub: milestones are phases, three label families, four issue templates (including `spike` with a verdict section), Draft PRs with device screenshots, one pinned status issue per phase, a `gh project` board for the owner's glance view, and the nine agent rules in `AGENTS.md`.** The owner merges; CI builds the APK only on `main`.
12. **Add the showcase-only delights that cost almost nothing**: "View source" per screen once public, Developer Info with Flet and Python versions, an accessibility section in the README with real TalkBack/VoiceOver flows and 200 % text screenshots, and a sponsor row that does not need a `BottomAppBar` trick.
