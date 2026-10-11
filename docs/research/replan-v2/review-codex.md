# Review for the v2 re-plan

**V1 contains valuable research, but its organising premise should be replaced.** It plans an official-store migration, operational handover, and exhaustive parity programme. V2 needs a polished mobile showcase that 1–2 people can understand and maintain.

Keep the domain knowledge and failure cases. Reconsider the prescribed architecture, test machinery, dates, and release process. The binding brief overrides the “authoritative” language in `docs/decisions.md`.

## 1. What to cut—and what to preserve

| V1 area | V2 recommendation |
|---|---|
| **PSF partnership and release dependencies:** `PLAN.md` §§1–2, 7.4, 10; decisions D-01..19, D-101..107 | **Drop** P1–P13, outreach, Track/G1, Linear, PSF reviewers/secrets, official-listing continuity, adoption/rating targets, and PSF on-call. Retain one short optional future-partnership appendix. |
| **Web/PWA:** `PLAN.md` §9.5; build-and-release §§8, 14 | **Drop** Pyodide, `PyfetchTransport`, CORS work, Firebase Hosting, web CI/performance tests, service-worker work, and projector-web dependencies. Desktop remains a development/test host only. |
| **Remote configuration:** architecture §13; decisions D-63, D-74 | **Drop** polling, remote capability vetoes, minimum-version gates, hosting and `content.yml`. Keep schema-checked bundled yearly content plus configurable year/feed URL. A bundled-content correction requires a new build; accept that tradeoff explicitly. |
| **Push and reporting:** `PLAN.md` §§5.7, 8.4; testing §14 | **Drop** FCM integration from the app’s initial plan, `NullAnalytics`, Sentry/envelope reporters, release-health dashboards and crash-free percentage gates. Keep useful, redacted local logs. Prioritise local scheduled reminders. |
| **Ionic design fidelity:** decisions D-31, D-39, D-64..73; architecture §§3, 11 | **Redesign** navigation and screens. Drop legacy URL spelling, verbatim accessibility-copy checks, exact Ionic colour reproduction, Cupertino pickers, `adaptive=True` UI, and platform-specific dark palettes. |
| **263-feature enforcement:** testing §§4, 8–9; build-and-release §5 | Keep the IDs as a scope inventory, but **drop** “one named test per ID,” calendar-driven trace gates, exhaustive query equivalence and the 168-image golden programme. An ID having a test is weak evidence of usability or correctness. |
| **Store release train:** build-and-release §§3–4, 11–13, 16 | **Drop** year-based alpha/respin arithmetic, `builds.txt`, PSF submission forms, public beta, staged production rollout, migration bridge and two-hour hotfix promises. Use a simple version and monotonically increasing internal build number. |
| **Capacity model:** `PLAN.md` §7.1 | Replace precisely estimated hours and contributor assumptions with phase outcomes, a small ready backlog and observed throughput. AI-assisted mechanical work does not eliminate integration or device-testing costs. |

**Architecture should shrink with scope.** Architecture §§1–4 and 12 prescribe twelve stores, thirteen contexts, provider families and many packages before implementation evidence exists. Start with pure domain functions, a feed repository, preferences/favourites state, a few screens, and small mobile-integration adapters. Add auth, staff state and the outbox when their phase starts.

Do preserve actual Flet constraints: if separate observable stores remain, the documented subscription behaviour may require separate contexts. “Flat is better” does not justify breaking reactivity. Conversely, it does not require twelve stores.

**Keep the strongest engineering decisions:**

- Pure, Flet-independent feed/time/signing/admission logic.
- Stable session IDs, immutable data, single-flight refresh and atomic replacement of the last good feed.
- Local favourites without login.
- Secure storage for mock credentials.
- Durable scan attribution, visible failures, manual scanning fallback and explicit offline limits.
- Fixed-clock, bundled-data demos with separate storage.

Retain a **small selective Ionic reference harness** for ambiguous feed rules and request signing. Use it to establish facts, then keep focused vectors. Do not make every redesigned behaviour conform to Ionic.

For v2, every existing ID should receive the brief’s disposition vocabulary and a phase. For example: `LIVE-01 drop`; `SCHED-11 improve`; private login/sync `mock`; scanner `mock + interim`, P3; E3 `improve + interim`, P2. An interim upgrade becomes available after a tested dependency/build change—not magically when an upstream issue closes.

## 2. Highest-risk assumptions and cheap spikes

Treat “verified in the local SDK” as **API evidence, not device evidence**. Architecture’s introduction says it inspected development source; build-and-release §1 describes released and unreleased toolchains. Those are distinct compatibility claims.

Time-box each spike to roughly half a day or a day initially. Record the exact versions, device, result, smallest reproducer and fallback.

| Assumption | Cheap spike and useful exit evidence |
|---|---|
| **The packaged Python runtime and chosen dependencies work on both OSes.** Companion success does not establish this. | Build a tiny APK and signed iOS app with `httpx`, `tzdata`, SQLite, preferences and secure storage. Fetch the public feed, persist state, kill/relaunch, then install an update. Upload an early owner-account TestFlight build if that distribution route is chosen. Flet requires suitable mobile wheels for binary dependencies: [Android packaging](https://flet.dev/docs/publish/android/), [iOS packaging](https://flet.dev/docs/publish/ios/). |
| **Declarative state, effects and navigation behave as sketched.** Architecture §§0, 3–4 document several subtle lifecycle rules. | One schedule → session → speaker → session → map journey. Test Android system Back, iOS back interaction, modal Close, repeated tab switches, refresh and background/resume. Confirm scroll/search retention and task cancellation. Compare simple explicit navigation with recursive drill URLs before committing to the latter. |
| **A full day’s schedule performs well across the Python/Flutter boundary.** Architecture §6.2 chooses eager rows partly to enable keyed scrolling. | Render the busiest recorded day on an ordinary Android and an iPhone. Measure packaged cold start, first launch, list construction, search responsiveness and scrolling at large text. Compare eager and lazy lists; test Jump to Now for an initially unbuilt row. Set budgets from evidence rather than inheriting v1’s unexplained numbers. |
| **Offline storage survives realistic lifecycle failures.** Architecture §8 uses an evictable cache directory; its SQLite connection/thread model is incomplete. | Store a last-good feed in persistent app storage; interrupt refresh and corrupt a candidate file. Kill after a queued write and reopen. For SQLite, choose and test one explicit connection/thread ownership model: an asyncio lock alone does not make arbitrary `to_thread` calls safe. Verify year namespaces and update migrations. |
| **Scheduled reminders remain useful when Python is not running.** E3 requires more than `zoned_schedule`. | In a release build, schedule shortly ahead; background/terminate, reboot Android, deny permissions/exact alarms, and tap a notification on cold launch. Change/unfavourite a session and verify cancellation/replacement. Exercise more than 64 candidates: the plugin documents an iOS pending limit, reboot setup and exact-alarm requirements. [Plugin documentation](https://pub.dev/packages/flutter_local_notifications). Use deterministic IDs and a bounded scheduling policy; report limits honestly. |
| **Camera scanning works through a packaged Flet extension.** `PLAN.md` §6.2 and architecture §10 assume pacing, pause and permission behaviour. | A scanner-only build on both phones: printed synthetic payloads, dim light, repeated detections, permission denial, background/resume and modal pause. Confirm one accepted payload per deliberate scan cycle. Separately prove the companion never receives unsupported extension controls; Python imports cannot establish client capability. |
| **Mock signing and queue tests establish faithful behaviour.** Architecture §§7, 9 risk overstating this. | Generate request-byte/signature vectors independently with the Ionic client, including Unicode, escaping, query order and timestamp rounding. Fault-inject “server committed, response lost,” auth expiry, sponsor/account switch and favourites edits during GET/PATCH. Verify ownership and durable records. **Client-local dedupe cannot prove server exactly-once effects**; keep uncertain server semantics documented and simulate both behaviours. |
| **Accessibility survives native rendering and the new information architecture.** Testing §12 mostly specifies assertions and a late audit. | Complete search → favourite → detail → map on VoiceOver and TalkBack immediately. Test maximum OS text/display sizes, focus after dialogs, selected-state labels and reduced motion. App-level doubled typography is useful but does not establish OS text-scaling support. |

Two sketch-level problems should be fixed before reuse:

- **Favourites:** architecture §7.4 makes later pulls server-authoritative. That can overwrite an unsent local edit. Define reconciliation with pending edits; logging out of a mock account should not casually erase the attendee’s local itinerary.
- **Errors:** architecture §15 wraps almost everything in `@safe`, swallowing exceptions and returning `None`. Recover at explicit operation boundaries with meaningful state. A failed prerequisites step must not silently permit dependent bootstrap steps. Preserve cancellation and make unexpected failures loud in development. Auto-hiding a banner via generic `pop_dialog()` also risks closing a newer dialog.

## 3. Material 3 improvements worth making

**Organise around attendee tasks.** Use stable primary destinations such as **Schedule, My Schedule, Map, More**. Put Now/Next prominently within Schedule; speakers remain searchable/browsable without necessarily consuming a primary tab. Login belongs in account/settings, and mock staff tools in a clearly marked staff area.

High-value improvements:

- **Schedule:** readable time groups, explicit day selection, visible active filter chips, one-tap clear, search scope shown as “Today” or “All days,” and preserved position after details/refresh. Jump to Now is deliberate, not an automatic interruption.
- **My Schedule:** chronological favourites across tracks, empty-state guidance, overlap warnings and visible reminder settings. Favourite changes get a Material snackbar with Undo; provide an accessible star button rather than relying on swipe or long press.
- **Session detail:** title, time with conference timezone, room, speakers and favourite action before the description. Make “Show room on map” direct. Clearly distinguish pre-registration requirements from favourite status.
- **Offline:** show “Last updated…” with an unobtrusive offline state. Keep cached content usable during refresh/errors. Distinguish offline availability of schedule/maps from remote images and external websites.
- **Changes:** first surface changes affecting favourites, with old/new time or room. “Removed from the latest feed” is safer than claiming cancellation from disappearance alone.
- **Map:** searchable room list plus floor selection and zoomable image. Offer text directions/location labels as the accessible alternative. Defer elaborate booth geometry until the basic map is excellent.
- **Staff tools:** show the active sponsor/session before scanning; distinguish **Queued**, **Confirmed** and **Failed**. Keep retry counts, manual entry and permission recovery visible. Use text/icon/haptic feedback together.
- **Theme:** one branded Material colour scheme for each brightness, with contrast-aware foregrounds. Use Material surface roles and typography; retain high-contrast variants if they fit cleanly. Avoid rotating sponsor chrome taking scarce phone space.

Identical Material UI still needs platform-specific integration testing for safe areas, keyboards, permissions and system navigation.

## 4. Phase order and concrete exits

| Phase | Scope | Exit criteria |
|---|---|---|
| **P0 — Prove the mobile foundation** | Brief becomes plan authority; disposition inventory; minimal structure/CI; owner-controlled packaging; highest-risk spikes. | A standalone app runs on **both physical phones**, with no host connection; fetches the public feed; saves/reopens local state; has a working Material navigation journey. Unsupported companion capabilities fall back safely. Toolchain and unresolved spike results are recorded. |
| **P1 — Attendee core worth demonstrating** | Feed processing, schedule/search/filter, details/speakers, local favourites, Now/Next, light/dark and offline persistence. | Both packaged builds complete the core journey in airplane mode after data preparation. Bad refresh preserves last-good data; Back preserves position; timezone/ID tests pass; core screen-reader journey works. A deterministic short demo can be recorded. **End-November is a soft marker.** |
| **P2 — Complete attendee experience** | Maps, bundled information/sponsors/events, favourite-change feedback, local reminders and calendar interim/upgrade. | Available yearly content is schema-checked and navigable; bundled maps work offline; reminder reconciliation and notification-open paths pass device checks—or a clearly labelled fallback remains. Denied permissions never block attendance tasks. Large-text and screen-reader checks cover new flows. |
| **P3 — Mock accounts and staff showcase** | Local signed mock server; login/roles/favourites sync; lead → door → swag → CoC; durable queue; E1 integration. | All four tools complete synthetic scenarios against the mock. Kill/restart, dropped responses, duplicate detection, account/sponsor changes and retry failures pass. Swag/CoC show explicit offline errors. Network tests reject private PSF hosts. Packaged camera and manual paths work on both OSes. |
| **P4 — Polish and internal distribution** | Integrated device checks, performance, tablets, clean-install/update checks, demo rehearsal and concise contributor/release docs. | No known data-loss or task-blocking defects; agreed accessibility/performance targets met on named devices; exact internal artifacts smoke-tested; demo works without conference Wi-Fi. Another person—or U from a clean checkout—can reproduce a build. |

Spike E1/E3 early without delaying P1 for their implementation. Bring the 2027 feed into whichever phase is active when it appears; its publication does not block progress with configured 2026 data. Unsupported gaps retain tested interims.

## 5. Lightweight GitHub workflow for humans and AI agents

Use **one private repo, protected `main`, short-lived branches and squash merges**. No release branch initially.

- **Issues:** outcome/problem, phase, relevant feature IDs, acceptance criteria, dependencies, and device evidence required. Group IDs into coherent user journeys; avoid 263 tiny issues.
- **Labels:** a small set for bug/feature/spike/upstream, blocked, and agent-ready. Use P0–P4 milestones. Optional Project: Backlog → Ready → Doing → Review → Done. Limit active implementation to one issue per person.
- **Agent-ready work:** explicit scope, allowed modules, examples and verification commands. Keep upstream extension tasks separate and link them to their app integration issues.
- **PRs:** link the issue; explain changed behaviour, checks run, screenshots/device evidence, and remaining limitations. Separate dependency/toolchain bumps from feature changes.
- **Review:** a human checks every agent-produced PR before merge. With two people, favour cross-review; solo, require a deliberate diff/evidence review rather than an impossible second-human approval.
- **CI:** fast formatting/lint/type checks and focused domain/schema/mock tests on PRs. Add a small proven UI smoke suite. Run mobile builds on main, toolchain changes or manual dispatch; use a compact device checklist at phase exits. Test evidence must identify its commit—do not merge unrelated nightly results into a current-PR quality claim.
- **Releases:** owner-controlled manual internal distribution initially; record version, monotonic build number, commit and artifacts in release notes. Automate repeated steps once exercised successfully.

`AGENTS.md` should state the binding scope, architecture conventions, commands, mock-only private API boundary, capability rules, cancellation/state requirements and definition of done. Require agents to report checks actually run and preserve unrelated work. Keep it short enough to follow.

The remaining OPEN decisions are distribution route, owner bundle ID and whether to submit a CFP proposal. None should recreate a PSF approval dependency. No files were modified.