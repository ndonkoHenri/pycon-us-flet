# S4: Do the Router, the drill route and native back gestures behave?

**Spike:** S4 ([#65](https://github.com/ndonkoHenri/pycon-us-flet/issues/65), PLAN §8). **Date:** 2026-10-12, about 1.5 hours of builds and runs on one Mac.
**Decides:** D-141 (route shape and Back through `on_view_pop`), D-142 (D-17's root rule and one root View key), D-143 (`ViewMemory` per process, amends D-18 and D-19), D-144 (the bar on roots only, amends D-17; #149), D-147 (page handlers, and a replaced session stops its work; amends D-70), D-148 (per-platform transitions, settles O-2), D-149 (U23, U24; amends D-98). D-140, D-145 and D-146 were taken on `main` meanwhile, so the S4 range has seven decisions. **Facts:** F29..F31. **Held for a human:** the iOS edge swipe and an iOS deep link's "Open" prompt ([#121](https://github.com/ndonkoHenri/pycon-us-flet/issues/121)).

## Question

Can the shell the decisions prescribe (D-13..D-21, D-69, section M) work as designed on Android and iOS: five tab roots with a `NavigationBar`, a recursive drill (`session/<id>/speaker/<id>/session/<id>/room/<slug>`) whose levels each see their own params, a global modal `/search` whose results push details, D-17's Back rule (Back on a non-Now root goes to Now, Back on Now exits), native Back (the Android key, predictive back, the iOS edge swipe), tab switches and re-taps, resume, deep entry, and, from S1, page handlers without `page.update()` and the boot gate across a new session (F26)?

## Answer: yes, with four changes

- **The route shape stands** (D-141): one recursive `:kind(...)/:ident` child under every root, More page and `/search`. Each level sees its own `kind` and `ident`, even for ids with `:`, `+`, a space, `~` and `ç`, on Android and iOS; deep entry builds the whole stack. No `s~id` fallback.
- **Back works everywhere** (D-141, D-142): our `page.on_view_pop` (D-19) receives the Android Back key and committed predictive gestures; search → result → detail → Back → Back returns to the results with the query kept; Back on a non-Now root goes to Now through `can_pop=False` and `on_confirm_pop`; Back on Now leaves the app.
- **Tab switches must not animate as pushes** (D-142): root Views share one `View.route` key, otherwise a tab switch slides in like a detail.
- **Change 1, the bar** (D-144, #149): on pushed Views the `NavigationBar` travels with the page (iOS) or doubles (Android) in every transition, so it moves to tab roots only.
- **Change 2, `ViewMemory`** (D-143): on Android a new session starts in the same process not only after an activity recreation (F26) but also after Back on Now and a relaunch (F29). Keeping `ViewMemory` per process lets the start route return the user to where they were.
- **Change 3, a replaced session** (D-147): Flet closes the old session but does not unmount it, so its effects keep running until they touch a store (F30). The app stops its own work from `page.on_close`.
- **Change 4, page handlers** (D-147): `page.on_platform_brightness_change` and `page.on_app_lifecycle_state_change` fire and re-render through store writes with no `page.update()`, on both platforms; this is a confirmation, not a change in code, but it settles the lifecycle sequence the app relies on.
- **Transitions** (D-148, O-2): `PREDICTIVE` gives the predictive page animation on Android 14 (developer flag) and 16 (default); `CUPERTINO` slides on iOS. The edge swipe itself needs a finger (#121).

## Method

- **Host:** Apple M4, macOS 27.0, Xcode 27.0 (27A266a), Android emulator 36.2.12.0, uv 0.12.
- **Flet:** the pin `15854a0ac` (`.flet-ref`, the `flet-1.1.0` branch), Flutter 3.47.7.
- **Devices:**
  - `flet_probe_api34` as `emulator-5580` (my own read-only instance): Android 14, Google APIs arm64, 1080 × 2400, gesture navigation. Predictive animations need `settings put global enable_back_animation 1` on 14 (the driver sets it).
  - `pycon_pixel6a_api36` as `emulator-5554` (shared): Android 16, where predictive back is the default. Only the predictive, drill and roots journeys ran there, with my own package; the other agent's app was brought back to the front afterwards.
  - An iOS 26.5 (23F77) simulator created for this spike ("S4 iPhone 17 Pro"), deleted afterwards.
- **Builds:** release `flet build apk --arch arm64-v8a` (D-106) and `flet build ios-simulator` (a debug build, D-102), from the reproducer folder.
- **Reproducer:** [`04-router-back/`](04-router-back/), its own `pyproject.toml` on `.flet-src` (development.md §3.4).
  - `src/main.py`: the shell in components mode. `main()` sets `page.on_view_pop` (navigates to `parent_of(e.route, memory.search_base)`) before `page.render_views(App, memory)`. `App` has a boot gate on an observable `Device` store (opened after a SharedPreferences read), sets the page handlers in its start effect, and provides `ViewMemory` and `Device` through contexts around `ft.Router(ROUTES, manage_views=True)`. `scaffold()` builds every View: the `AppBar` with the Material back arrow on pushed Views (D-10), the bar, and D-17's `can_pop=False` + `on_confirm_pop` on non-Now roots. Stub screens: Now, Schedule (three days of 40 rows, day and offsets in `ViewMemory`), My schedule, Map, More (plus `/more/speakers`), Search, and `Drill` → `Detail` for sessions, speakers and rooms. A 15 s ticking effect shows whether an old session's work outlives it. More has switches for the knobs this verdict compares (shared root key, bar on pushed Views, `ViewMemory` per process, stop effects on close).
  - `src/routes.py`: the pure helpers `drill_href()`, `tab_of()`, `parent_of()` and `stack_depth()`.
  - `check_routes.py`: host checks of per-level params with the Router's own matcher, Back targets and stack depths.
  - `drive_android.py`: ten adb journeys. Each step is one tap (found in `uiautomator dump`), the Back key, an edge swipe (`input motionevent`, with a screenshot mid-gesture) or an adb setting, and waits for the app's `S4 top ... route=<path>` log line.
  - `drive_ios.py`: simctl cannot tap, so the app walks its own journeys (`S4_JOURNEY=1` via `SIMCTL_CHILD_`) and checks each step's top route and View count against `stack_depth()`; the script screenshots each checkpoint, records the screen, then checks background and resume, dark mode and deep entry.
- **Frames:** screen recordings (`adb shell screenrecord`, `simctl io recordVideo`) decoded with PyAV, keeping the frames that changed.

## Evidence

### Results

| Run | Device | Result |
|---|---|---|
| `uv run python check_routes.py` | host | all checks pass: per-level params of 5 locations, 8 Back targets, 5 stack depths, 2 non-matches |
| `drive_android.py` (all ten journeys) | Android 14 | **130 / 130**: drill 17, roots 19, retap 10, retap-top 5, search 15, predictive 8, memory 8, lifecycle 12, deep 10, recreate 26 |
| in-app journeys ("Run journeys" in More) | Android 14 | 38 / 38 steps |
| `drive_android.py predictive drill roots` | Android 16 | 44 / 44 (the build before the review fixes, which changed no route code) |
| `drive_ios.py`, bar on every View | iOS 26.5 | **51 / 51** (42 in-app checks, 9 from the host) |
| `drive_ios.py`, `S4_BAR_ON_PUSHED=0` | iOS 26.5 | 50 / 50 (the build before the review fixes) |

### Route shape and per-level params (D-141)

- `/now/session/42/speaker/17/session/99/room/room-102a` gives five Views; the levels log `session '42'`, `speaker '17'`, `session '99'`, `room 'room-102a'`, each from its own `use_route_params()`.
- Quoted ids survive Flutter's route information on both platforms: `/now/session/poster%20detail%2B1/speaker/%C3%A7~31/session/7` reaches each level as `poster detail+1`, `ç~31` and `7` after `unquote`, by tap, by the Android `route` extra and by the iOS `--route` argument. The Router's matcher escapes the consumed prefix before matching the next level (`repath`), so `.`, `+` and `%` in an id never act as regex syntax.
- Deep entry builds the stack at once (`/map/room/hall-a/session/42/speaker/23` → four Views, Back × 4 → `/map` → Now).
- An unknown id (`/schedule/session/nope`): the reproducer renders the level once, then its effect navigates to `parent_of()` and shows a SnackBar, which appears on the parent on both platforms (the in-app check also confirms the unknown level rendered first). That is the mechanism only: what the app does for an unknown id is not settled here, because the docs disagree (D-21: land on the root; architecture §5.3: the parent; ux.md's states table and P1-11: an empty state). #90 decides it.

### Back (D-141, D-142)

- **Back key (Android 14 and 16):** each press on a drill level produced one `S4 view-pop route=<level> to=<parent>` and the parent became the top; Views below stayed mounted (their scroll held, below).
- **Search:** Now › Schedule › a row › Search (base `/schedule/session/d1-03`) › type "keynote" › result › its speaker. Back → the result, Back → the results with `query='keynote'`, Back → the opener, Back → Schedule, Back → Now. The Router alone would have popped every View of the modal chain to its base (F6); our handler made each Back one step.
- **Focus on return:** when the results come back, Flutter gives the search field its focus back and the keyboard reopens, so the first Back on Android only closes the keyboard. Flet has no `blur()`; P1's search handles it (follow-ups).
- **D-17's root rule:** Back (key or gesture) on Schedule, My schedule, Map and More logged `confirm-pop` and landed on Now; More › Speakers › a speaker unwound one step at a time to More, then Now.
- **Back on Now leaves the app:** lifecycle `inactive, hide, pause, detach`; the activity finishes. A relaunch is a **new session in the same process**: `S4 main s=2`, same pid, `route=/` (F29). This is the template's documented "process reuse" path (`lib/main.dart`, `runPythonApp`).

### Predictive back and transitions (D-148)

- **Android 14 (developer flag on) and 16:** an edge swipe on a detail shows Flutter's predictive page animation (the page shrinks and moves with the finger, the page below shows at the edge); a cancelled swipe left the route unchanged, a committed one popped through `view-pop`. On a non-Now root (`can_pop=False`) there is no page animation, only the system's back arrow, then `confirm-pop` → Now. On Now the system's back-to-home animation runs (the window shrinks onto the launcher or the previous app).
- **iOS:** `CUPERTINO` slides a pushed page in from the right and out on pop (recording). simctl cannot drag, so the edge swipe is held for #121.

### The bar on pushed Views (D-144, #149)

- With the bar on every View (D-17 as written):
  - iOS: the pushed page slides in **with its own bar**, so two bars sit side by side mid-push and the bar travels across the screen.
  - Android: a push or pop cross-fades whole pages, so both bars ghost for a few frames; during a predictive gesture the shrinking page's bar sits over the bar of the page below for the whole gesture.
- With the bar on roots only: on iOS the barless detail slides over the root and covers its bar (as `hidesBottomBarWhenPushed` does); on Android the root's bar fades out under the incoming page, and a predictive gesture shows one bar. Both runs passed the same journeys.
- Re-tap: Flutter's `NavigationBar` calls `onDestinationSelected` for the selected destination too, so `on_change` fires on a re-tap (`retap=True` logged) on a root and on a pushed View. With the bar on roots, the scaffold hands a root's re-tap to the screen's `on_retap`: on a scrolled Schedule it ran `await ListView.scroll_to(offset=0, duration=300)` and the first row came back on screen.

### Tab switches and the root View key (D-142)

- With one shared key (`View.route="/"` on every root), a tab switch swaps the page with no transition: only the bar's indicator animates (frames over about 100 ms).
- With a key per root, the same switch ran the page transition (about 400 ms of a slide and fade), as for a pushed detail.
- The stock pop handler and ours work with shared keys: pushed Views keep their resolved path as key, and `e.route` of a pop is always a detail's path.

### ViewMemory (D-18, D-143)

- **Under a pushed View:** Schedule › Day 2 › scrolled › a row › Back: the same rows on screen (the View stayed mounted and kept its scroll).
- **After a tab switch** (Schedule unmounts): the remount read `schedule_day=2` and `offset=515` from `ViewMemory`, and `await ListView.scroll_to(offset=..., duration=0)` in its mount effect put the same rows on screen. Writing the offset from `on_scroll` re-rendered nothing (`renders=1`).
- **Search:** the query and the opener location came back from `ViewMemory` (above).
- **Across a new session:** see the next section. A location under `/search` cannot be restored as is: a fresh Router puts a global modal over its last non-modal location, which is `/` (the start route), so `Start` restores the search's opener (`search_base`) instead.

### A new session in the same process (F26, F29, F30; D-143, D-147)

Recreation by switching gesture and 3-button navigation (S1's trigger), on `/now/session/42/speaker/17`:

| | `ViewMemory` per session (as designed) | `ViewMemory` per process + `page.on_close` stops the work |
|---|---|---|
| New session | `S4 main s=2`, same pid, `route=/` | the same |
| Boot gate | ran again: BootView, then the Router at `/` | the same |
| Where it lands | `/` → Start → **`/now`** (the drill is lost) | Start → `memory.last_location` → **`/now/session/42/speaker/17`**, three Views; Back → `/now/session/42`. From a search result (`/search/speaker/17`, opened on `/now/session/42`) it lands on the opener, `/now/session/42` |
| The old session | `page.on_close` fired; its 15 s ticking effect kept running and died at its next store write with `RuntimeError('An attempt to fetch destroyed session.')`, seen only by asyncio | `on_close` set the effect's stop event; the loop ended cleanly (`error=none`), and nothing from the old session ran afterwards |

- Without a store write in the loop (an earlier build), the old effect kept ticking next to the new session's (two cycles seen) and would have run indefinitely.
- After `detach`, a re-render triggered by the lifecycle handler fails to send (`dart_bridge.send_bytes failed ... Dart_PostCObject_DL failed`, logged once per patch): harmless, since that client is gone.
- What does **not** recreate the activity (no new `main`): dark mode (`cmd uimode night`), a font-scale change (1.3) and rotation. They are in the template's `android:configChanges`. A navigation-mode change does, and so would other changes outside that list (on Android 12+, wallpaper colours change `assetsPaths`).
- "Don't keep activities" set through `settings put global always_finish_activities 1` did not take effect without the Settings app's own call, so it is not part of the evidence.
- iOS has no activity recreation; a background and return kept the session (`same session after resume`).

### Page handlers without `page.update()` (D-147)

- Both handlers are assigned in `App`'s start effect, after the first render, and only write the observable `Device` store; the `StatusLine` component subscribed through its context showed every change.
- **Android:** Home → `inactive, hide, pause`; relaunch → `restart, show, resume` (same session); `cmd uimode night yes` → `brightness dark=True` and the status line read "dark".
- **iOS:** `simctl launch` of Settings → `inactive, hide, pause`; relaunch → `restart, show, resume`; `simctl ui appearance dark/light` → `dark=True`, `dark=False`.

### Deep entry (D-21 groundwork)

- **Android:** `am start ... --es route <path>` (what `flet debug --route` passes) on a cold start, and a `VIEW` intent with `s4spike://s4/<path>` while running: both landed on the path with the stack built.
- **iOS:** `simctl launch <udid> <bundle> --route=<path>` (the engine's route switch; `flet debug ios --route` uses it) landed on the path with the stack built, quoted ids included (F31). `simctl openurl` with the custom scheme stops at the system's "Open in “S4 Router”?" prompt, which needs a tap: held (#121). The pending prompt survived until the simulator was rebooted.

## Decisions changed

- **D-141:** the drill route shape of §M and architecture §5.3 stands (no `s~id` fallback), and `page.on_view_pop` with `parent_of()` (D-19) handles every pop, Search's return to its results included.
- **D-142:** D-17's Back rule on roots confirmed (Back on Now finishes the Android activity, F29); root Views share one `View.route` key, `"/"`.
- **D-143** (amends D-18 and D-19): `ViewMemory` lives per process, and the start route returns a new session to the last location.
- **D-144** (amends D-17, settles UQ-1 through #149): the bar on tab roots only.
- **D-147** (amends D-70 rule 3): the page handlers and the lifecycle sequence the app relies on; `bootstrap()` stops long-running work from `page.on_close` until U24.
- **D-148** (settles O-2): `PageTransitionsTheme(android=PREDICTIVE, ios=CUPERTINO)`; the iOS edge swipe is checked on the iPhone (#121).
- **D-149** (amends D-98): U23 (a shell bar outside the Navigator) and U24 (closing a session unmounts it) are later candidates.

## Follow-ups

- **#121 (iPhone session), held items:** the iOS edge-swipe Back on a drill level (it should go through `view-pop` like Android's gesture) and on a root (nothing to pop); a deep link through `s4spike://` after tapping "Open". Both need a finger; the simulator could not be tapped in this session.
- **The P0 shell issue** (`routes.py`, `app.py`, `ui/scaffold.py`): apply D-141..D-147 and port `check_routes.py`'s cases to `tests/test_routes.py`.
- **P1 search:** the field regains focus when the results come back (Flutter restores a route's focus), so the first Android Back closes the keyboard. Decide there whether that is acceptable or the results take the focus.
- **Upstream (maintainers' track):** U23 and U24 (D-149), filed in flet-dev/flet when a maintainer schedules them.

## Fallback

- If a feed id ever breaks per-level matching (a `/` inside an id would, but `quote(safe="")` encodes it), switch the drill to one segment per level, `session~42` (`:pair` with `kind, _, ident = pair.partition("~")`); `parent_of()` then drops one segment.
- If the shared root key hides a needed tab animation, give roots their own keys and set `PageTransitionTheme.NONE` for tab switches only once Flet can pick a transition per navigation (it cannot today).
- If restoring the last location after a new session ever surprises users (e.g. a session that ends while a sheet is open), Start falls back to Now and keeps only positions.
- If U24 lands, `page.on_close` stops being needed: effects' own cleanups run on close.

---
_Written by Claude Code (AI agent)._
