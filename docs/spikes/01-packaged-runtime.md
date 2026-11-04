# S1: Does the packaged app run well on Android and iOS with our stack?

**Spike:** S1 ([#62](https://github.com/ndonkoHenri/pycon-us-flet/issues/62), PLAN §8). **Date:** 2026-10-12, about 2 hours of builds and runs on one Mac.
**Decides:** D-108 (data path), D-109 (parsing on the loop), D-110 (no lazy imports), D-111 (`.pyc` kept), D-112 (emulator baseline and method), D-113 (system overlay style, amends D-12). **Facts:** F25, F26. **Follow-ups:** [#121](https://github.com/ndonkoHenri/pycon-us-flet/issues/121) (iPhone release numbers).

## Question

Does a packaged release build with our runtime stack (`httpx`, `zoneinfo` + `tzdata`, `sqlite3`, SharedPreferences, SecureStorage) start fast enough, keep its data across kills, relaunches and updates, parse the feed without blocking, and draw edge-to-edge with readable system bars on Android and iOS?

## Answer: yes on the emulator and the simulator; the iPhone's release numbers are pending

- **Storage:** `FLET_APP_STORAGE_DATA` is durable. The cached feed, a sqlite3 table, SharedPreferences and SecureStorage all survived force-stop and relaunch, an `adb install -r` with a higher build number (twice), and on the simulator two update installs (D-108).
- **Speed (emulator, release APK):** a cold start reaches the cached content in a median of **760 ms** after the launch intent. This comes from the app's log line, which screen recordings show is late by 0.2-0.3 s, never early. Python takes 220 ms of that, from the top of `main.py` to the first rendered frame. That is the regression baseline (D-112). Absolute numbers, on the iPhone against D-80, wait for #121.
- **Parsing:** `json.loads` of the 822 KB feed plus a processing stand-in takes **3-4 ms** (52 ms at worst, the first launch after an update). That is far under the 150 ms threshold, so parsing stays on the event loop (D-109). For this workload, `asyncio.to_thread` stalled the loop just as long, because the C JSON decoder holds the GIL. Pure-Python processing would behave differently, so the real processor gets its own measurement if it ever nears the threshold.
- **Imports:** all of them take about **56 ms** (`httpx` 24 ms), so lazy imports are not needed (D-110).
- **`.pyc`:** keep the default. Without it, Python recompiles on every start, because serious_python sets `PYTHONDONTWRITEBYTECODE=1` (F25). The first frame then comes 280 ms later, and the APK is only 0.8 MB smaller (D-111).
- **`is_embedded()`:** `True` in the packaged app on both platforms; `False` under `flet run`.
- **System bars:** with an `AppBar` and no `system_overlay_style`, 3-button navigation in the light theme shows grey icons on a dark scrim, at **2.3:1**. That is the #311 class of bug. Enforcing navigation-bar contrast gives the same result. A transparent bar with icon brightness set per theme and contrast **not** enforced gives 5.1:1, and the `NavigationBar` colour runs under the buttons (D-113, which amends D-12's "enforced navigation-bar contrast").

## Method

- **Host:** Apple M4 (10 cores, 24 GB), macOS 27.0 (26A428), Xcode 27.0 (27A266a), uv 0.12.15.
- **Flet:** the `flet-1.1.0` candidate `15854a0ac` (D-104, #120), Flutter 3.47.7, CPython 3.14.7 in the app (shown on screen). The repo's current pin (`3710aff`) cannot build iOS on Xcode 27 (S5), so both platforms used the candidate. The build ran in S5's scratch copy, whose `.flet-src` is a clone at that commit; the stub's relative paths resolve the same way there.
- **Android:** AVD `pycon_pixel6a_api36` as `emulator-5554` (D-107): Android 16 (API 36), Google APIs arm64, 1080 × 2400 at 420 dpi, emulator 36.2.12.0. Release APKs: `uv run flet build apk --arch arm64-v8a --build-number N` (D-106), signed with the debug key.
- **iOS:** an iPhone 17 simulator on iOS 26.5 (23F77), the D-107 device; the iPhone 16 runtime on this Mac is iOS 18.6. `flet build ios-simulator` is a debug build (D-102), so its timings are not release numbers.
- **Reproducer:** [`01-packaged-runtime/`](01-packaged-runtime/), a stub app with its own `pyproject.toml`.
  - Dependencies: `flet`, `flet-secure-storage`, `httpx==0.28.1` and `tzdata==2026.5`, wired to `.flet-src` through `[tool.uv.sources]` and `[tool.flet.dev_packages]` (development.md §3.4).
  - The stub is declarative: `page.render_views(App)` and one `View` with an `AppBar` and a `NavigationBar`, like the app's roots.
  - On start it reads `feed-2026.json` from `FLET_APP_STORAGE_DATA`, parses and shows it, and only then fetches `https://us.pycon.org/2026/schedule/conference.json` with `httpx.AsyncClient(timeout=10)`. After a good parse it writes the feed back through a temp file, `fsync` and `os.replace` (D-39).
  - It also counts launches in SharedPreferences and in a sqlite3 table, round-trips a SecureStorage value, and formats a 2026 session time in `America/Los_Angeles`.
  - Every step prints a line `S1 <event> wall=<epoch> py_ms=<since main.py>`. Android routes it to logcat (tag `flet.python`), iOS to the unified log (sender `dart_bridge`).
- **Timing:** "first frame" and "cached content" are logged when a SharedPreferences call made after the render returns. The Dart side handles messages in order, so the patch has been applied by then, but the reply does not wait for a frame. The line is therefore a proxy, which the screen recordings below show to be **late, not early**. Times "from start" subtract logcat's `ActivityTaskManager: START u0` timestamp from the event's wall clock (both device clock).
  - A scratch script ran `adb shell am force-stop`, waited 2 s, cleared logcat, ran `adb shell am start -W -n <pkg>/.MainActivity` and waited for the network refresh, ten times per build.
  - First launches: `adb uninstall`, `adb install`, then the same, three times per build.
  - The first rounds ran right after two Gradle builds and were noisy, so both cold starts were measured again on a quiet host ("round b").
- **Not done here:** release numbers and VoiceOver on the iPhone (#121); a `pm clear` first launch with the bundled snapshot (the app's P0-16 owns the snapshot); `page.on_*` handlers without `page.update()` (S4 has the same check).

## Evidence

### Android cold start and first launch (emulator, release APK, ms)

Medians, with min-max in brackets. "Start" is the launch intent; `TotalTime` is what `am start -W` reports.

| Build | Launch | n | `TotalTime` | Python starts | First frame | Cached content | Python start → first frame |
|---|---|---|---|---|---|---|---|
| `.pyc` on (default) | cold, round b | 10 | **426** (400-507) | 516 (494-627) | 734 (721-883) | **760** (741-919) | **220** (202-277) |
| `.pyc` on | cold, round a (busy host) | 10 | 598 (417-910) | 700 (503-1048) | 918 (714-1341) | 942 (735-1403) | 242 (211-351) |
| `.pyc` on | first after fresh install | 3 | 441 (421-453) | 559 (541-574) | 770 (754-796) | no cache: 986 | 213 (211-223) |
| `.pyc` on | first after fresh install, busy host | 3 | 1382 (1263-1436) | 1691 (1587-1723) | 2169 (2076-2197) | no cache: 2434 | 478 (474-489) |
| `.pyc` off | cold, round b | 10 | 424 (403-648) | 512 (489-741) | 1022 (984-1233) | **1044** (1006-1258) | **498** (487-595) |
| `.pyc` off | cold, round a | 10 | 576 (411-761) | 696 (499-857) | 1284 (1000-1505) | 1324 (1020-1556) | 576 (501-669) |
| `.pyc` off | first after fresh install | 3 | 578 (557-606) | 730 (725-796) | 1281 (1270-1335) | no cache: 1454 | 541 (539-557) |
| `.pyc` off over `.pyc` on | first after `adb install -r` (build 2 over 1) | 1 | 748 | — | — | — | 534 |
| `.pyc` on over `.pyc` on | first after `adb install -r` (build 3 over 1, then 4 over 3) | 2 | 2875, 2467 | — | — | — | storage step at 1383, 1225 |

Reading it:
- The first launch after an update of the `.pyc` build was the slowest case seen (about 2.5-2.9 s to Flutter's first frame, n=2). The `.pyc`-off update was not, so the cause is not settled; the iPhone's update check in #121 records the same step.
- `am start -W` stops at Flutter's first frame, which is Flet's boot screen, not our content. Python starts about 90 ms after it, and our cached content appears about 330 ms later. A content-to-content comparison needs the app's own log line (D-112).
- **The log line against the screen** (`adb shell screenrecord`, three cold starts, frames decoded with PyAV):
  - Recording loads the emulator, so these starts were slower: `Displayed` at +2.3-2.8 s.
  - Taking the frame where the splash fades into Flet's boot screen as `Displayed`, the first content frame came 2.05 s (run 1) and 1.67 s (run 2) after it.
  - The "first frame" line came 2.28 s and 1.98 s after `Displayed`, so it lagged the pixels by 0.2-0.3 s. Run 3's frames could not be told apart.
  - So the proxy overstates the time to content and never understates it. It is consistent build to build, which is what a regression baseline needs.
- Round a against round b shows how much a busy host moves the numbers: about 25 %, more than D-80's 20 % regression line. Measure on a quiet host and repeat before calling a regression.

**Import times** (ms, medians, `.pyc` on, round b; `.pyc` off in brackets):
- stdlib group (`asyncio`, `json`, `sqlite3`, `zoneinfo`, …): 19 (18);
- `httpx`: 24 (112);
- `flet`: 6 (20);
- `flet_secure_storage`: 7 (33).

The total is 56 ms, against 183 ms without `.pyc`. On the simulator the total was 42-115 ms.

**Sizes:**
- APK with `.pyc`: 55,846,650 bytes; without: 55,014,574 bytes. `assets/sitepackages.zip` is 6,369,069 and 5,608,302 bytes; the first holds 512 `.pyc` and 1 `.py`, the second 0 and 513.
- Simulator `.app`: 283 MB (a debug build).

**Build times:**
- First `flet build apk` of the stub: 74 s.
- Warm rebuilds: 24 s with `.pyc`, 48 s without.
- `flet build ios-simulator`: 131 s, then 99 s.

### Feed parsing (D-80, D-109)

| Where | Feed | `json.loads` | Processing stand-in | Loop stall, parse on the loop | Loop stall, `asyncio.to_thread` |
|---|---|---|---|---|---|
| Emulator, cold cache read (10 launches) | 822,356 bytes, 728 schedule items | 3 ms (3-8) | 1 ms | — | — |
| Emulator, "Parse benchmark" button ×3 (5 rounds each) | same | 3-4 ms total | | 6-9 ms | 7-8 ms |
| Emulator, first launch after an update | same | 46 ms | 6 ms | — | — |
| Simulator (debug), 5 relaunches | same | 4-5 ms | 0 ms | — | — |
| Host (M4) | same | 2 ms | 1.4 ms | 5 ms | 5 ms |

- The processing stand-in localises every `start` to `America/Los_Angeles`, groups the items by day and sorts them. It is lighter than the real D-41 processing, which P0's `feed processed in N ms` log will measure against the 400 ms budget.
- The heartbeat in the stub sleeps 4 ms, so a stall of 6-9 ms means the loop was blocked for 2-5 ms.
- The fetch took a median of 204 ms on the emulator (170-559).

### Persistence (D-39, D-108)

| Step | Android (`emulator-5554`) | iOS simulator |
|---|---|---|
| `FLET_APP_STORAGE_DATA` | `/data/user/0/io.github.ndonkohenri.pyconus.s1/files/data` | `…/Containers/Data/Application/<UUID>/Library/Application Support/data` |
| Files written | `feed-2026.json` (822,356 bytes), `s1.db` | the same, listed with `simctl get_app_container … data` |
| Kill and relaunch | ~30 force-stops: launches and sqlite rows went up by one each time, cache read on every start, SecureStorage `kept` | `simctl terminate` + `launch` ×5: the same |
| Update install | `adb install -r`: build 1 → 2 (`versionCode=2`, `firstInstallTime` unchanged): launches 11 → 12, rows 12, secure `kept`, cache 822,356 bytes. Build 2 → 1 (`-d`) and 1 → 3: launches 30, rows 30, secure `kept` | `simctl install` of the same app with `CFBundleVersion` 2, then a rebuild with build number 3: launches 7, 8, 9, rows match, secure `kept`, cache read |
| Container path after an update | unchanged | **changed**: the data container's UUID changed from `F6EB4DC3…` to `7F83D89E…`, with the files moved across |
| `zoneinfo` source | the `tzdata` wheel (no `America/Los_Angeles` file on `zoneinfo.TZPATH`) | the system zoneinfo on the simulator |
| Session time | "Fri 15 May 2026, 09:30 PDT" | the same |

A force-stop during a network refresh never left a broken cache. Every launch's read parsed, because the write is a temp file plus `os.replace`.

**Re-check after the pin bump to `08b89cce5` (#673), for the outbox (#691, 2026-10-28).** The bump changed the bundled Python, so roadmap §6 asks for S1's `sqlite3` result again. The reproducer, built at the new pin with `flet build ios-simulator` (a scratch copy whose `record_launch()` also opened `outbox.db` with `isolation_level=None`, set `PRAGMA journal_mode=WAL` and ran a `BEGIN IMMEDIATE` script that created a table, inserted a row and set `user_version`, as `services/outbox_db.py` does), ran on a fresh iPhone 17 simulator (iOS 26.5). It logged `mode=wal rows=1 user_version=1 sqlite=3.51.0 python=3.14.10`, and `rows=2` after `simctl terminate` and `launch`; `outbox.db`, `-wal` and `-shm` were in `Library/Application Support/data`. Android was not re-run: the change is the Python build, and S1's two platforms agreed.

### `is_embedded()`

| Runtime | Result |
|---|---|
| Packaged APK, Android | `True`, `sys.platform` `android` |
| Packaged simulator app, iOS | `True`, `sys.platform` `ios` |
| `uv run flet run -w -p 8561 check.py` (host) | `False`; `FLET_PLATFORM` unset; `FLET_APP_STORAGE_DATA` and the working directory are `<script dir>/.flet/storage/data` (F14) |

### Edge-to-edge and system bars (Android 16, D-12, D-113)

Twelve screenshots: gesture and 3-button navigation, light and dark (`cmd uimode night`), each with three styles.
- **No style:** no `system_overlay_style`.
- **Icons:** `SystemOverlayStyle(status_bar_color=TRANSPARENT, system_navigation_bar_color=TRANSPARENT, status_bar_icon_brightness` and `system_navigation_bar_icon_brightness` = DARK in light and LIGHT in dark, `status_bar_brightness` = the theme's, `enforce_system_navigation_bar_contrast=False)`.
- **Icons+scrim:** the same with `enforce_system_navigation_bar_contrast=True`.

The contrast ratios use WCAG luminance on the screenshot pixels: the darkest or lightest icon pixel against the bar behind it.

| Navigation | Theme | No style | Icons | Icons+scrim |
|---|---|---|---|---|
| Gesture | light | handle 5.5:1, status 5.7:1 | same | same |
| Gesture | dark | handle 14.0:1, status 18.7:1 | same | same |
| 3-button | light | **grey icons on a dark scrim, 2.3:1** | **dark icons on the `NavigationBar` colour, 5.1:1** | grey on a dark scrim, 2.3:1 |
| 3-button | dark | white on near-black, 20.3:1 | white on the `NavigationBar` colour, 16.3:1 | 20.3:1 |

- Status-bar icons followed the theme in every case.
- Without an `AppBar`, "No style" in 3-button light already gave dark icons on a transparent bar. So the bad case comes with the `AppBar`: Flet passes the theme's style to it (or none, and Flutter then uses the `AppBar`'s default), and its navigation-bar part evidently reached the system bar although the `AppBar` covers only the top. Every root in our app has an `AppBar`.
- **Landscape, 3-button:** the system buttons sit on the right edge, over the app. `ListTile`s inset themselves (Flutter wraps them in a `SafeArea`), but a `SegmentedButton` placed directly in the `ListView` ran to the right edge under the buttons. So bodies need a horizontal `SafeArea` (D-12 already says so; architecture §5.5).
- Switching the navigation mode recreated the Android activity. Flet then started a **new session in the same Python process**: `main()` ran again and the component state reset (`S1 main` at `py_ms=244804`, the same PID). Module-level state stayed (F26). A dark-mode switch did not recreate it.

### iOS simulator (debug build, iPhone 17, iOS 26.5)

| Step | Result |
|---|---|
| Launch to Python start (from `simctl launch`) | 1121-1230 ms over 5 relaunches |
| Python start → first frame | 357-475 ms (debug Flutter; the Android release build takes 220 ms) |
| Python start → cached content | 416-571 ms |
| Imports | stdlib 18-42, `httpx` 16-53, `flet` 3-8, `flet_secure_storage` 5-12 ms |
| Network | 822,356 bytes in 195 ms |
| Screen | Everything rendered; the iOS `AppBar` title was centred (D-10 pins `center_title=False` in the real app) |

## Decisions changed

- **D-108** (confirms D-39 and F14): the feed cache, `changes-<year>.json` and `outbox.db` live in `FLET_APP_STORAGE_DATA`. It is read from the environment on every start and never stored as an absolute path, because iOS moves the container on an update.
- **D-109** (settles architecture §6.2's "if S1 measures over 150 ms"): `feed.process` runs on the event loop as the initial choice. If the logged processing time on the iPhone ever exceeds 150 ms, benchmark the real processor on and off the loop before choosing; the `to_thread` result here holds only for the C JSON decoder.
- **D-110:** no lazy imports. Modules import at the top. Revisit if Python start → first frame on the emulator grows by more than 100 ms over this baseline.
- **D-111:** keep `[tool.flet.compile]` at its defaults, `.pyc` for the app and packages; never turn it off for a tester build.
- **D-112** (records for D-80 and D-102): the emulator regression baseline, and a log-based method that measures to the content rather than to `am start -W`'s boot-screen frame. The log line is a late proxy; screen recordings stay the method for numbers held against D-80.
- **D-113** (amends D-12): each colour scheme's `system_overlay_style` has transparent bars, icon brightness opposite to the scheme, and `enforce_system_navigation_bar_contrast=False`.

D-80's targets are unchanged: the emulator numbers are a regression signal (D-102), and the iPhone's release numbers in #121 confirm or revise them.

## Follow-ups

- **#121** (comment added): on the iPhone, a release build of this stub. Ten cold starts to cached content with the content-based method, first launch after a fresh install, an update install over the previous build, `is_embedded()` and the parse benchmark. These confirm or revise D-80, D-109 and D-110.
- **P0-16 (offline data):** apply D-108 and D-109; log `feed processed in N ms`.
- **P0 theme work (`theme.py`):** apply D-113; check 3-button light again once the real `AppBar` and `NavigationBar` are in.
- **S4:** `page.on_*` handlers without `page.update()` (architecture §4.3), and a session restart after an activity recreation (F26). Both touch the boot gate.

## Fallback

- If the iPhone's processing time on the real feed exceeds 150 ms:
  - profile `feed.process` first;
  - then benchmark the real function on the loop, in `asyncio.to_thread` (pure-Python code releases the GIL every few milliseconds, unlike `json.loads`) and in `concurrent.futures.InterpreterPoolExecutor` (Python 3.14 subinterpreters, no shared GIL), and pick by the measured loop stall.
  - The cache read stays first, so the screen never waits on processing a fresh download.
- If imports grow (P1 adds screens): move the `httpx` import into the refresh path (24 ms on the emulator) before reaching for anything more general.
- If a future template or Flutter change breaks D-113's style: drop the `AppBar`'s influence by wrapping each root in a Flet-provided annotated region (upstream), and meanwhile keep `enforce_system_navigation_bar_contrast=False` with an explicit `system_navigation_bar_color` equal to the `NavigationBar`'s surface.
- If `FLET_APP_STORAGE_DATA` ever changed meaning (a template change, say), not everything in it is equal:
  - the feed cache is rebuilt from the bundled snapshot on the next start (D-39);
  - `changes-<year>.json` loses only the change history;
  - `outbox.db` (P3) can hold unsynced staff actions (D-56).

  So a pin bump that moves the directory needs a migration that finds the old location and moves the outbox before anything writes the new one. The bump's smoke test (development.md §2.2) installs over the previous build and checks that the launch counter, the cache and the outbox survive.

---
_Written by Claude Code (AI agent)._
