# S2: Can the busiest day render and update fast in components mode?

**Spike:** S2 ([#63](https://github.com/ndonkoHenri/pycon-us-flet/issues/63), PLAN §8). **Date:** 2026-10-12, about 5 hours of builds and runs on one Mac.
**Decides:** D-153 (row architecture: memoise the whole path), D-154 (lazy day lists; today's list builds every slot; `build_controls_on_demand` is not the answer), D-155 (Jump to now is one keyed `scroll_to`), D-156 (the shown day renders first, the other days in a second render), D-157 (controlled text fields, amends D-70), D-158 (a time gutter that grows with the text, amends ux.md §3.9), D-159 (how interaction latency is measured, and the emulator baseline). **Facts:** F32..F34. **Follow-ups:** [#121](https://github.com/ndonkoHenri/pycon-us-flet/issues/121) (iPhone release numbers), [#81](https://github.com/ndonkoHenri/pycon-us-flet/issues/81), [#86](https://github.com/ndonkoHenri/pycon-us-flet/issues/86).

## Question

Can the busiest day of the 2026 schedule render, and react to a star tap, a keystroke in a search field and a day switch, fast enough in components mode, with rows as the Schedule will draw them? Which row architecture and which list should the Schedule use, and how does "Jump to now" reach a slot that has not been built yet (F7)? Does any of it change at 200 % text?

## Answer: yes, if the whole path is memoised; the jump needs a fully built list

- **The busiest day** is Friday 15 May 2026: 26 time slots and 111 rows (50 open spaces, 24 talks, 8 AI, 8 charlas, 12 notices and breaks, 9 others). Every number below is that day, drawn as ux.md §3.9 and §5.2 describe it, on the reference emulator (D-102: relative numbers).
- **Row architecture** (D-153): memoising the rows alone is not enough. A star tap still made the parents rebuild and diff every slot of every day: **38 ms** of Python per tap with memoised rows, against **145 ms** with plain rows and **158 ms** with unmemoised row components. Memoising the path, day list → slot → row, each level given only the favourites under it, brings it to **3 ms** (2-4): one row re-rendered, and the star changes in the same frame as a change Flutter draws on its own. A search keystroke: 120 → 34 → **3 ms**; a day switch: 139 → 40 → **2 ms**.
- **`build_controls_on_demand=False` does not help** (F32): Flet then gives Flutter a `ListView(children: ...)`, which still builds only what is near the viewport. `scroll_to(scroll_key=...)` reached the 4:30 PM slot in 0 of 3 tries in either mode, at 100 % and 200 % text, and the flag changed no other number.
- **Only a fully built list reaches the slot** (D-154, D-155): a `Column(scroll=AUTO)`, or a `ListView` whose `cache_extent` is larger than the day, 3 of 3 at both text sizes, on Android and on the iOS simulator. A two-step jump (an estimated offset, then the key) worked at 100 % and failed at 200 % (it landed on 1:30 PM). Building the whole day has a price on the emulator, though:
  - each day switch drops about two frames as the new page builds every slot: the worst frame of a switch was a median 49 ms (up to 50 ms with a `ListView`, 70 ms with a `Column`), against at most 24 ms for a lazy list;
  - a filter keystroke's list change shows 0-82 ms after the key, against 0-16 ms lazy (Python's share is the same 3 ms);
  - a `Column` also stalls for about 220 ms when a fling hits either end of the day (Android's stretch overscroll on one huge child); the fully built `ListView` does not.
  
  So day lists stay lazy `ListView`s, and only today's list, the one the jump targets, gets a `cache_extent` that builds the whole day (D-154).
- **Cold start** (D-156): rendering all five days in the first render costs **150 ms** more than the shown day alone: the cached content appeared at 970 ms against 815 ms (log proxy, D-112), and Python's first render took 245 ms against 105 ms. Rendering the other days in a second pass after the first one has been applied keeps the short start (815 ms, 865 at 200 %) and leaves no empty page when swiping to another day.
- **Scrolling** (D-80): flinging through the day showed no jank in any lazy or fully built `ListView`: 0-4 of about 890 frames over 25 ms, none over 36 ms.
- **200 % text** changes no Python timing (star 3 ms, keystroke 3 ms). It broke the layout in two places: the 64 dp gutter split "7:30" over two lines (fixed here, D-158), and the two-line day tabs are clipped (#86).
- **Two Flet traps** found on the way: a `TextField` without `value=` is wiped by the next re-render of its component (D-157, F33), and `ft.memo` only skips its own body, so a memoised row under a parent that rebuilds still costs the parent's work (F34).

## Method

- **Host:** Apple M4 (10 cores, 24 GB), macOS 27.0, uv 0.12.15. A stuck `fvm global` process kept one core busy the whole session (it was not ours; left alone).
- **Flet:** the pin `15854a0ac` (`.flet-ref`), Flutter 3.47.7, CPython 3.14.7 in the app.
- **Android:** `pycon_pixel6a_api36` as `emulator-5554` (D-107): Android 16, Google APIs arm64, 1080 × 2400 at 420 dpi, Impeller on OpenGL ES. Release APKs: `uv run flet build apk --arch arm64-v8a` (D-106), about 50 s per rebuild.
- **iOS:** the iPhone 17 simulator on iOS 26.5 (23F77), a debug build (`flet build ios-simulator`, D-102): a functional check only. Release numbers on the iPhone are #121's.
- **Reproducer:** [`02-day-list/`](02-day-list/), with its own `pyproject.toml` on `.flet-src` (development.md §3.4).
  - `src/main.py` imports the real `pycon_us`: a copy of the repo's `src/pycon_us` next to `main.py`, made by `rsync` before each build, because the package's data files must sit on disk as they do in the app (as a wheel they ended up inside `sitepackages.zip`). It processes the bundled 2026 snapshot with `feed.process`, builds one frozen `RowView` per session (badge, title, "time · room", speakers, search text) and a `SlotView` per time group, and draws the Schedule root: `AppBar`, `NavigationBar` (roots have the bar, D-144), `Tabs` with five two-line day tabs, a search field that filters the shown day, and a `TabBarView` of day lists. A slot item is a `Container(key=ft.ScrollKey("slot-<iso>"))` holding a divider, the time gutter and the slot's rows; session rows have a track badge (ux.md §3.4 colours), the title (`TITLE_MEDIUM`, 3 lines), the meta line, speakers and a 48 dp `IconButton` star; notices and breaks are compact rows without a star. Themes come from `pycon_us.theme.build_theme`.
  - The launch route picks the variant, `s2spike://s2/<rows>/<list>/<days>`:
    - rows: `plain` (plain controls rebuilt by the day list), `component` (each row an `@ft.component` keyed by session id), `memo` (the same, wrapped in `ft.memo`, so it re-renders only when `(row, is_fav)` changes) or `tree` (memoised rows inside memoised slot components inside memoised day lists, each given only the favourites under it);
    - list: `lazy` (`ListView`, the default `build_controls_on_demand=True`), `eager` (`build_controls_on_demand=False`), `column` (`Column(scroll=AUTO)`) or `cache` (`ListView(cache_extent=100_000)`, on every day);
    - days: `all` (every day's list in the first render), `visited` (a day renders when its tab is first shown) or `deferred` (the shown day first, the others in a second render once the first has been applied).
  - Two app-bar buttons jump to the 21st slot (4:30 PM): `scroll_to(scroll_key=...)`, and a two-step jump (an offset estimated from 120 dp per session row and 48 dp per notice, then the key).
  - `drive_android.py` drives it with adb: `cold`, `star`, `search`, `days`, `jump`, `fling` and `tabframes` suites (its docstring has the details), and writes `out/results.jsonl`.
- **Timing, in the app.** Every handler logs `<action>-in`; an effect logs `patched` when the re-render has been sent to Flutter (the session's scheduler runs effects after the patch), with the number of row bodies that ran; then `acked` when a SharedPreferences round trip returns (the S1 proxy: Flutter has applied the patch, but no frame is guaranteed). "Handler → patch" is therefore all of Python's work for the action.
- **Timing, on screen.** `adb shell screenrecord` at 20 Mbit/s, frames decoded with PyAV:
  - **Search:** from the first frame where the typed character shows in the field (Flutter draws it on its own, before Python hears of it; the field's cursor is off so it cannot blink) to the first and the last frame where the list below changed. Only keystrokes that change the list count, so n=4-6.
  - **Day switch:** from the first change in the tab bar (the indicator moves on its own) to the first and the last change in the list.
  - **Star:** an instant tap draws no press feedback before the star changes (the ripple appears with the fill, even for a 145 ms answer), so there is no on-screen start mark. Each recording starts with one keystroke instead: its character's frame and its `key-in` line map the video clock onto the device clock, and each fill frame is then compared with its tap's `star-in` line. Both actions reach Python the same way, so the result is the time the star takes beyond a change Flutter draws itself, give or take the mapping's error of about 10 ms (one build reads -9 to +12 ms across recordings).
  - **Fling and day-switch frames:** `dumpsys SurfaceFlinger --latency` for the app's `SurfaceView` layer, cleared before each gesture: the intervals between presented frames; a frame over 25 ms (1.5 vsyncs) counts as janky. The first runs left out every interval over 200 ms as the list at rest, which could hide a long stall; the last runs (marked) keep every interval within 1.5 s of the gesture's first frame instead, a Codex review finding.
- **Runs:** cold starts n=10; star taps and keystrokes n=12 per variant (the keystrokes are `python` typed and deleted); day switches n=12; jumps 3 per button; flings 12 per variant (six down, six up). 200 % text is `adb shell settings put system font_scale 2.0`, restored to 1.0 after every run.
- **Changes between runs:** the first runs (05:45-06:30) had the fixed 64 dp gutter; the 200 % runs and later the growing gutter of D-158 (one more invisible text per slot). The `deferred` mode came at 06:55, `?auto=1` (for the simulator) after the Android runs.
- **Two slowdowns, discarded.** Twice (about 07:02-07:45 and from about 08:02) everything inside the emulator became about 3-4.4× slower: feed processing 66 → 200-290 ms, cold start 1.0 → 3.4-4.4 s. The host was unaffected (the same processing took 42 ms on it throughout), and every qemu thread showed `PRI 4`, a background priority: macOS throttled the emulator, each time some 20-30 minutes after the host's user went idle, until a few minutes after they came back. An agent cannot lift it (`taskpolicy -B` had no effect; bringing the window forward needs Apple-events access). Runs in those windows are left out, except functional results (jumps); the numbers below are from 05:45-07:01 and 07:50-08:02. testing-and-quality.md §8 now checks for it before measuring.

## Evidence

### 100 % text (median and range, ms)

"Cold" is the cached-content log line minus logcat's `START u0` line (D-112), n=10. "Py" is handler → patch sent. "Screen" is the synced recording (star) or the first list change after the keystroke (search). "Settled" is the median last change in the list after a day-tab tap. Star, keystroke and day switch are n=12.

| Rows / list / days | Cold | First render (py) | Star py | Star screen | Rows per tap | Keystroke py | Keystroke screen | Day switch py | Day settled | `scroll_to(key)` | Two-step |
|---|---|---|---|---|---|---|---|---|---|---|---|
| plain / lazy / all | 952 (938-1045) | 221 | 144 (134-190) | 144 (130-188) | 320 | 120 (113-141) | 116 (0-132) | 139 (128-163) | 183 | 0/3 | 3/3 |
| component / lazy / all | 956 (922-1007) | 228 | 158 (146-256) | 140 (137-239) | 320 | 120 (117-141) | 118 (0-133) | 143 (135-155) | 183 | 0/3 | 3/3 |
| memo / lazy / all | 976 (946-1019) | 226 | 38 (32-46) | 35 (21-44) | 1 | 34 (31-54) | 32 (0-51) | 40 (35-47) | 183 | 0/3 | 3/3 |
| **tree** / lazy / all | 1008 (948-1119) | 232 | **3 (2-4)** | -5 (-9-6) | 1 | **2 (1-28)** | 7 (0-16) | **2 (1-3)** | 183 | 0/3 | 3/3 |
| plain / eager / all | 943 (927-1017) | 221 | 140 (133-163) | 133 (129-154) | 320 | 117 (111-145) | 116 (0-132) | 138 (134-144) | 183 | 0/3 | 3/3 |
| memo / eager / all | 996 (948-1175) | 228 | 38 (35-47) | 39 (29-45) | 1 | 32 (30-54) | 16 (0-52) | 39 (35-44) | 183 | 0/3 | 3/3 |
| tree / eager / all | 961 (947-1069) | 230 | 3 (2-3) | -5 (-8 to -3) | 1 | 2 (2-31) | 0 (0-32) | 1 (1-3) | 183 | 0/3 | 3/3 |
| tree / column / all | 960 (947-1006) | 228 | 3 (2-5) | 8 (-3-12) | 1 | 2 (1-27) | 0 (0-83) | 2 (1-5) | 58 | **3/3** | 3/3 |
| tree / cache / all | 956 (947-1007) | 230 | 3 (2-4) | -6 (-10 to -3) | 1 | 3 (2-30) | 0 (0-83) | 2 (1-5) | 66 | **3/3** | 3/3 |
| tree / lazy / visited | **810** (798-914) | **102** | 3 (2-4) | 12 (-2-14) | 1 | 3 (1-27) | 0 (0-34) | 2 (1-69) | 183 | 0/3 | 3/3 |
| tree / column / deferred (07:50) | 815 (802-891) | 105 | 3 (2-4) | 1 (-6-7) | 1 | 3 (2-29) | 25 (0-66) | 2 (1-6) | 58 | 3/3 | 3/3 |

Reading it:
- **Where the time goes.** A plain row tree rebuilds all 320 rows of the five days for any change: 140-160 ms of Python, and the screen waits exactly that long (star screen ≈ star py). Memoised rows re-render one row, but the parent still rebuilds the 88 slot containers of the five days, runs 320 memo checks and diffs it all: 35-40 ms. Only memoising the day lists and the slots as well removes the parent's work (F34).
- **"Screen" around 0** means the star filled in the same frame (±10 ms of mapping error) as a change Flutter draws itself; Python's 3 ms disappear in the frame.
- **The keystroke's 17-33 ms maxima** in the tree variants are the keystrokes that bring rows back: deleting "py" to "p" restored 37 rows, whose components had unmounted when they were filtered out, so they render again. A keystroke that only hides rows re-renders the slots that changed and no row body (each remaining row's `(row, is_fav)` is unchanged): 1-4 ms.
- **Keystroke screen** with a fully built list (`column`, `cache`) reached 66-83 ms although Python took 3 ms: Flutter lays out every slot of the day again.
- **Day switch.** With all days rendered, Python only echoes the index (2 ms in tree); the time on screen is the `TabBarView` slide. The last list change came 183 ms after the tab with lazy lists and 58-66 ms with fully built ones.
- **Python's split of a cold start** (tree / lazy / all): Python starts 472 ms after the intent; `main()` at 744 ms (imports 120 ms, `feed.process` 66 ms, the row views 2 ms); the first render 232 ms; the patch applied 28 ms later. `feed.process` of the real 2026 snapshot took a median **66 ms** over the 200 cold starts in the good windows, under D-109's 150 ms.

### First render: all days, visited, deferred (07:50-08:00, `column`, n=10)

| Days | Cold, 100 % | First render (py) | Cold, 200 % |
|---|---|---|---|
| all | 970 (964-1033) | 245 | 1037 (984-1170) |
| visited | 849 (819-872) | 106 | 891 (818-1091) |
| deferred | **815** (802-891) | 105 | **865** (814-885) |

The deferred pass starts once the first render's round trip has returned, so it never delays the first content. `visited` starts the same, but swiping to a day not yet shown slides in an empty page.

### Frames: flings and day switches (100 %)

Twelve flings per variant (six down the day, six back up, `input swipe` over 1,100 px in 120 ms) and twelve day-tab taps, SurfaceFlinger's presented frames:

| Variant | Fling frames | Over 25 ms | Worst | Day-switch worst frame per tap |
|---|---|---|---|---|
| tree / lazy / all | 893 | 0 | 24.7 | |
| tree / cache / all | 890 | 0 | 24.3 | |
| tree / column / all | 1121 | 1 | 25.2 | |
| tree / eager / all, plain / lazy / all, memo / lazy / all | 890-895 | 0-1 | 25.4 | |
| tree / lazy / visited | 892 | 4 | 26.7 | |
| tree / lazy / all, every interval (08:00) | 888 | 3 | 35.4 | **18-24** (no frame over 25) |
| tree / cache / all, every interval (08:00) | 888 | 1 | 25.2 | 19-50, median 49 (12 frames over 25) |
| tree / column / deferred, every interval (07:55) | 916 | 4 | **227** | 19-70, median 49 (13 frames over 25) |

- Scrolling never janks in a lazy or fully built `ListView`: Python takes no part in a fling.
- The `Column`'s two 220-227 ms frames came at the turnarounds, where the fling hits the end and the top of the day and Android's stretch overscroll transforms the whole day as one child. The earlier `column` run hid them (its intervals over 200 ms were left out).
- A day switch to a fully built list drops about two frames as the page builds all its slots; a lazy list builds a screenful.
- At 200 %, the valid day-switch runs are `cache/all` and `cache/visited` (06:56): worst frame per switch 18-66 ms, median 49. The lazy and `Column` runs at 200 % fell in a slowdown.

### 200 % text

| Rows / list / days | Cold | First render (py) | Star py | Star screen | Keystroke py | Keystroke screen | Day settled | `scroll_to(key)` | Two-step | Fling over 25 ms |
|---|---|---|---|---|---|---|---|---|---|---|
| plain / lazy / all | 965 (946-1019) | 236 | 150 (140-169) | 141 (132-159) | 122 (119-148) | 58 (0-149) | 166 | 0/3 | 0/3 | 2 of 915 |
| tree / lazy / all | 981 (963-1069) | 246 | 3 (2-5) | 5 (-3-12) | 3 (1-30) | 7 (0-17) | 166 | 0/3 | 0/3 | 0 of 915 |
| tree / cache / all | 1028 (970-1095) | 250 | 3 (2-6) | -1 (-8-8) | 3 (2-31) | 0 (0-65) | 131 | **3/3** | 0/3 | 2 of 912 |
| tree / lazy / visited | 828 (806-861) | 107 | 3 (3-5) | 2 (-6-7) | 3 (1-28) | 7 (0-16) | 166 | 0/3 | 0/3 | 0 of 913 |
| tree / column / deferred (08:00) | 865 (814-885) | 105 | 3 (2-5) | 5 (0-14) | 3 (2-33) | 48 (0-82) | 132 | **3/3** | **3/3** | |

- Python's timings do not move with the text size.
- **The two-step jump fails at 200 %** with a lazy list: the estimate (120 dp per row) is half the real height, so the first jump lands near 1:30 PM, where the 4:30 PM slot is not built, and the key does nothing (screenshot `jump-steps-tree-lazy-all-2.0`). With the whole day built, the key alone lands on 4:30 PM at offset 21,234 px (10,068 at 100 %), and so does the two-step jump.
- **Layout:**
  - **Gutter:** a fixed 64 dp broke "7:30" into "7:3 / 0 / AM". The gutter now has no fixed width: an invisible "10:00 AM" in a `Stack` sets it, so it grows with the text, is the same for every slot and keeps one left edge for the rows (D-158). At 100 % it is as wide as before.
  - **Day tabs:** the fixed-height `TabBar` clips the second line of "Fri / May 15" at 200 % (only "Fri" shows). For #86.
  - **Navigation bar:** "My schedule" wraps onto two lines and crowds its icon. For the shell's own 200 % check.
  - **Rows** reflow without clipping: three-line titles, meta and speakers wrap, the star stays top-right.

### `scroll_to` and F7 (D-154, D-155, F32)

- The slot items carry `key=ft.ScrollKey("slot-<iso>")`. Flutter's `ScrollableControl.scroll_to` looks the key's `GlobalKey` up and calls `Scrollable.ensureVisible` on its context; Flet registers the `GlobalKey` only in `ControlWidget.build` (`control_widget.dart`), so an item Flutter has not built has no context and the call does nothing, silently.
- `build_controls_on_demand=False` gives Flutter's `ListView(children: [...])` (`list_view.dart`): the widgets are created up front, but a sliver list still builds (mounts) only the children inside the viewport and its cache extent (250 px by default). So the eager flag does not make far items reachable, and it changed no measured number. ux.md §5.2 and §5.6 assumed it did.
- Built in full (`Column(scroll=AUTO)`, or a `ListView` whose `cache_extent` covers the day), one `scroll_to(scroll_key=...)` landed on the slot every time: `column` and `cache` with all days at 100 %, `cache` at 200 %, and `cache/visited`, `cache/deferred`, `column/visited` and `column/deferred` at both sizes (3/3 each; some of these ran in a slowdown, which does not change whether the slot is reached).
- `on_scroll` (`ScrollType.END`) reported the landing offset, so a test or a log can confirm a jump.

### Search field (D-157, F33)

The first build passed `TextField(on_change=...)` with no `value`. Typing "p" logged `key-in q='p'`, the list filtered, and the field showed its hint again: the component's next render created the field with `value=""`, the diff compared it with the old control, whose `value` the event had set to "p", and sent `""` to Flutter. With `value=query` (the state the handler sets) the diff finds nothing to send and the text stays.

### Accessibility notes for #81

`uiautomator dump` (the tree TalkBack reads) showed:
- the star `IconButton` as a nameless `Button` (its tooltip is not its `content-desc`) and without a selected state, so #81 should give `FavoriteButton` an explicit `Semantics(label=..., button=True, toggled=...)` rather than rely on the tooltip (D-33);
- the gutter's `Semantics(header=True, label="7:30 AM")` read as "7:30 AM, 7:30, AM" until `exclude_semantics=True`, and the slot's notice rows merged into that header node: `NoticeRow` needs its own `MergeSemantics`;
- each session row's text as one node ("Open space, GeoData Show & Tell / Meetup, 8:00–9:00 AM · Room 102C"), as D-33 wants.

### iOS simulator (debug build, iPhone 17, iOS 26.5)

`flet build ios-simulator` (debug), installed with `simctl install`, launched with `--route=/tree/column/deferred?auto=1` (F31). The simulator could not be tapped from here (the simulator control waits for the owner's permission, and the owner was away), so `?auto=1` makes the app drive itself through the same handlers: the jump, four star toggles, "python" typed and cleared, then three day switches. It was added after the Android runs and does nothing without the flag.

| Step | Result (debug build, so timings are not release numbers) |
|---|---|
| Start | `feed.process` 52 ms; first render of Friday 83 ms of Python, 111 rows; the other four days in the deferred pass: 112 ms of Python, 209 rows, applied by Flutter 470 ms later (debug Flutter) |
| Jump | `scroll_to(scroll_key=...)` on the `Column` landed on 4:30 PM (`scrolled pixels=10094 max=12314`), screenshot `ios-jump` |
| Star | 4 toggles, 7-9 ms handler → patch, one row each; the star filled in the tertiary colour |
| Keystrokes | 5-26 ms for "p" .. "python", 37 ms for clearing it (42 rows back); the field kept the text (D-157) and the list kept its position |
| Day switch | 5 ms; each `Tabs` change made from Python also comes back as an `on_change` (logged twice), which the handler must tolerate |
| Screen | Roboto, the badges, the gutter and the two-line day tabs render as on Android |

## Decisions changed

- **D-153:** the Schedule memoises the path: memoised day lists given only their day's favourites, memoised slot items given only their slot's favourites, and memoised rows keyed by session id on `(row view, is_favorite)`; view models are built once per feed version and callbacks are stable (`use_callback`). Settles ux.md §3.9's "decided by spike S2" and architecture §6.4's "unless S2 decides otherwise".
- **D-154:** day lists are lazy `ListView`s (the default `build_controls_on_demand=True`); today's list gets `cache_extent` large enough to build the whole day, so its slots are reachable; never `build_controls_on_demand=False` for reachability (F32), never a `Column` for a day. Replaces ux.md §5.2's and §5.6's `build_controls_on_demand=False`.
- **D-155:** "Jump to now" (and the first display of today, D-18) is one `await today_list.scroll_to(scroll_key=ft.ScrollKey(slot_key), duration=...)`; never an offset estimate.
- **D-156:** the Schedule renders the shown day first and the other days in a second render once the first has been applied.
- **D-157** (amends D-70): rule 9, a text field in a component is controlled.
- **D-158** (amends ux.md §3.9): the time gutter has no fixed width.
- **D-159** (records for D-80 and D-102): the interaction-latency method and the emulator baseline.

## Follow-ups

- **#121** (comment added): on the iPhone, a release build of this reproducer: star taps, keystrokes and day switches with a screen recording, the first content time, and the jump at the largest text size.
- **#81** (row family): D-153's memo shape and the accessibility notes above; a check that a star tap re-renders one row (the reproducer's render counter shows how).
- **#86** (Schedule screen): D-154..D-156 and D-158; the day tabs clip at 200 % (two-line labels in a fixed-height `TabBar`): try one-line labels in a scrollable bar, or a taller `Tab(height=...)`, and check with TalkBack.
- **Testing (§8):** the latency row now names the method and the baseline (D-159), and an emulator run starts by checking for the slowdown.

## Fallback

- If today's fully built list shows a hitch on the iPhone when its tab comes in, or a day grows much longer, keep today lazy too and jump in two steps with the estimate taken from the list's own `max_scroll_extent` (`on_scroll` reports it after the first jump), repeated until the key's slot is on screen.
- If Flet registers scroll keys for unbuilt items (a `ListView.scroll_to(index=...)` upstream would do it), today's list goes lazy like the others; nothing else changes.
- If the deferred render of the other days ever shows as a hitch, render each day on its first visit instead (`visited` starts as fast; its cost is an empty page while swiping to a day not yet shown).

---
_Written by Claude Code (AI agent)._
