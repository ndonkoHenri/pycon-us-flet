# S7: Do real floor plans with about 60 hotspots work in `InteractiveViewer` on a low-RAM phone?

**Spike:** S7, `P2-01` ([#361](https://github.com/ndonkoHenri/pycon-us-flet/issues/361), PLAN §8; opens P2-E1). **Date:** 2026-10-21, about 2 hours of builds and runs on one Mac, and 75 minutes of an Android rerun in the afternoon; a third Android run on 2026-10-29 ([#453](https://github.com/ndonkoHenri/pycon-us-flet/issues/453), 15 minutes on the device).
**Decides:** D-312 (plan images, the viewer's maximum zoom, the hotspot approach, Map without a swipeable `TabBarView`, how a pane keeps its zoom; amends ux.md §5.8, §6.1, §6.2). **Fact:** F130. **Upstream:** U110 ([#560](https://github.com/ndonkoHenri/pycon-us-flet/issues/560), `TabBarView.physics`). **Low-RAM gate: passed on the 2.5 GB AVD** in the third run (2026-10-29, below), after two attempts on 2026-10-21 that the host's full swap stopped; a real low-RAM phone (with the GPU's share) is unmeasured, and the iPhone release-build memory stays with [#121](https://github.com/ndonkoHenri/pycon-us-flet/issues/121).

## Question

Do the 2026 plans, re-encoded to 2048 px or less, with the expo's 61 booths as hit areas in an `InteractiveViewer`, stay usable and within memory on a low-RAM phone? Which image format and hotspot approach do the floor viewer (§6.1) and the expo map (§6.2) use; does a `TabBarView` pane steal the plan's pans; and can a pane keep its zoom (D-18)?

## Answer: yes on iOS and on the 2.5 GB Android AVD, with WebP at 2048 px, one `Container` per booth, and no swipeable `TabBarView`

**Low-RAM Android: the expo plan stays within memory and usable on the 2.5 GB AVD** (the third run, 2026-10-29, "Android on the 2.5 GB AVD (the third run)" below). In the reproducer's release build the expo plan and its 61 booths add **13–17 MB PSS** to the plain list's 133 MB, at 1x and at 5.23x (its maximum on that screen) and after 64 drags; 40 open/close cycles level off at **157 MB** (10 MB of growth in the first 10, none after); pans at 5.23x run at a **16.7-ms median** frame interval (p90 17 ms, none over 33 ms); all 61 booths are named nodes in the accessibility tree and **61 of 61** taps at 1x hit the right booth. The app's own release build holds **183 MB** on Now and **197–204 MB** on the expo map, zoomed, panned and after 10 open/close cycles, with 1.1–1.2 GB of the AVD still available and no process of the app killed. The first two attempts (2026-10-21) failed on the host, not on the app: its swap was 94–98 % full. Two limits stay: the emulator reports Graphics 0, so the decoded plan's texture on the GPU (11.3 MB of RGBA by arithmetic) is not in these numbers, and no real low-RAM phone has run it; the Fallback below is not needed on this evidence.

- **Images (D-312):** every plan is re-encoded by [`07-floor-plans/reencode.py`](07-floor-plans/reencode.py) to 2048 px on its longer side, as **lossy WebP, quality 80**: 110–200 KB a plan, a third of JPEG q85 (330–540 KB) and a seventh of PNG, with no loss visible at maximum zoom. The format changes the download, not the memory: every 2048-px plan decodes to the same 11.3–12.6 MB of RGBA. `Image.cache_width` is not used: it would decode the plan at screen width and lose the detail the zoom exists for, to save about 8 MB on the one plan on screen.
- **Memory (iOS 26.5 simulator, debug build):** the app's footprint is about 258 MB on a plain list, **266–270 MB** with the expo plan and its 61 booths, at 1x, at the maximum zoom and after panning, with a **peak of 281–302 MB** while the plan decodes. The 4966-px source plan peaks at **347 MB**: re-encoding saves about 50 MB of decode peak. On the 2.5 GB AVD (release builds, `dumpsys meminfo`, the third run): the reproducer's plain list is 127–133 MB PSS, the expo plan 140–150 MB, 157 MB after 40 cycles; the 4966-px source peaks at 204 MB (Native Heap +46 MB for a few seconds while it decodes), the 2048-px WebP read 139–142 MB within a second of opening (a snapshot; a shorter decode peak would not show in it).
- **Maximum zoom:** `max_scale = natural width / displayed width`, so one image pixel at most fills one logical pixel: **5.36x** for the 2048-px expo plan on the iPhone 17 (382 dp wide), where booth names and numbers read cleanly (the screenshot below); the 4966-px source would allow 13x and show nothing more that matters. On the 2.5 GB AVD's 720-px, 280-dpi screen the same rule gives **5.23x** (a 391-dp plan).
- **Hotspots (D-312):** one `Container` per booth inside `Semantics(content=..., button=True, label=..., identifier=...)`. Flutter hit-tests them, they give a screen reader 61 named buttons, and every tap landed on the right booth at 1x and at 5.36x. One `GestureDetector` hit-tested in Python was as accurate (0.02–0.10 ms a test) and no faster to build (render of the pane 47–75 ms with containers, 78 ms with one detector, on a host under load), but it gives a screen reader nothing: it loses.
- **No double-tap on the expo map:** a `GestureDetector(on_double_tap=...)` around the viewer delays **every** single tap by Flutter's double-tap timeout: tap down to tap was **326 ms** with it and **5–30 ms** without. The zoom buttons are the single-pointer path (WCAG 2.5.1); double-tap stays only on plans with nothing to tap.
- **Pan versus swipe:** a `TabBarView` pane **steals** horizontal pans. At 5.36x, a finger-speed horizontal drag (2.5 s) on the Concourse plan changed the tab instead of panning it, as it did at 1x. So the Map uses `Tabs` with a `TabBar` and **no** `TabBarView` (only the selected pane is built), and **U110** asks for `TabBarView.physics`: the only stop at the pin, `disabled`, disables every booth inside the pane too (F130).
- **Zoom across a tab switch (D-18):** a pane that leaves loses its zoom (scale 1.0 on return), and `save_state()`/`restore_state()` cannot bring it back: the saved matrix lives in the widget state that left with the pane (F130). The last `on_transform_changed` values, kept in `ViewMemory`, can: `reset()`, `zoom(scale)`, `pan(x / scale, y / scale)` put the pane back exactly (**5.361, (−321.7, −214.5)**). D-18's remembered zoom stands, with that interim until U3 (§5.7). The panes must be **keyed**: unkeyed, Plan and Expo in the one slot are the same component to Flet, which migrates one into the other with its hook state and its viewer (the first run's Concourse pane showed the Expo's selected booth); the numbers here are from the keyed rerun.

![The expo plan at its maximum zoom, 5.36x, booth 344 selected](https://github.com/ndonkoHenri/pycon-us-flet/blob/pr-assets/561/s7-expo-max-ios.png?raw=true)

## Method

- **Host:** Apple M4 (24 GB), macOS 27.0, Xcode 27.1, Android emulator 37.2.12.0, uv 0.12.15. **Other agents' builds and seven emulators ran at the same time:** load average 290–910 and 34 GB of swap in use, so every timing here is a relative signal at best, and Android could not be measured (below). **The Android rerun (12:02–13:15 the same day)** started at load 49 (1 min) and ran at 27–139, with three or four other emulators and the host's swap 94–98 % full at every reading (20.4–27.7 GB used of 21.5–28.7 GB, never more than 1.5 GB free).
- **Flet:** the pin `15854a0ac` (`.flet-ref`), Flutter 3.47.7. Images with Pillow 12.0.0.
- **Devices:**
  - iOS: my own "361-iphone17" (iPhone 17, iOS 26.5, 23F77), a debug build (`flet build ios-simulator`, D-102), deleted at the end. Taps and drags through the free local Maestro CLI; memory from the host with `footprint <pid>` (`phys_footprint` and its peak); the app's lines from the simulator's unified log.
  - Android: a new AVD **`pycon_lowram_api34`** (Pixel 6a profile with a 720 x 1600, 280 dpi screen, Android 14 Google APIs arm64, `hw.ramSize` 2048 MB). The emulator raises any API 34 image to **2560 MB** ("Increasing RAM size to 2560MB", with or without `-memory 2048`), so 2.5 GB is the smallest this image runs with. `pycon_pixel6a_api36` (D-107) no longer existed on the Mac and was recreated as D-107 describes (4 GB) for the comparison; it was not booted.
- **The third run (2026-10-29, #453):** the same Mac (Apple M4, 24 GB, macOS 27.0, emulator 37.2.12.0), the host's Android lock held, **no other emulator or simulator running**; before the boot the load was 4.7 and the swap 6.45 GB used of 8.19 GB (1.74 GB free, 68 % of memory free), and it stayed there (load 0.9–5.0, swap unchanged, 62–65 % free) to the end. The pin `08b89cce5` (Flutter 3.47.7); both release APKs (arm64) built from `main` at `49311e8b`: the reproducer (60.9 MB) and the app (61.2 MB, build 347).
- **Reproducer:** [`07-floor-plans/`](07-floor-plans/), its own `pyproject.toml` on `.flet-src`.
  - `reencode.py`: the re-encode, kept for next year (the command is in its docstring and in `pyproject.toml`). It writes the WebP and, for comparison, a JPEG of each plan, and the expo's 4966-px source, into `src/assets/plans/` (git-ignored: the plans stay PyCon's, D-87).
  - `src/booths.json`: the 61 booths of `excluded/pycon-us-mobile/src/app/expo-hall-map/` as ratios of the plan (the Ionic file gives them in a 9931 x 7021 space).
  - `src/main.py`: three tabs (Plain, Plan with the Concourse plan, Expo with the booths) and a toolbar that switches `TabBarView` or a lone pane, containers or one detector, the image, `cache_width` and a double-tap detector. The viewer's buttons zoom, pan, reset and try the three ways back to a zoom. Every event prints an `S7` line.
  - `drive_ios.py` and `drive_android.py`: the steps the runs used (taps, drags, memory, frame intervals, tap accuracy from the booth nodes' bounds).

## Evidence

### Images

`reencode.py` on the seven 2026 plans (Lanczos down to 2048 px; JPEG with 4:4:4; WebP method 6):

| Plan | Source | Fitted | Decoded | JPEG 70 | JPEG 85 | JPEG 92 | PNG | **WebP 80** | WebP lossless |
|---|---|---|---|---|---|---|---|---|---|
| Concourse (`floor-plan-1`) | 2200 x 1700 | 2048 x 1583 | 12.4 MB | 325 KB | 419 KB | 523 KB | 1150 KB | **164 KB** | 704 KB |
| Upper (`floor-plan-2`) | 2200 x 1700 | 2048 x 1583 | 12.4 MB | 256 KB | 320 KB | 391 KB | 786 KB | **109 KB** | 480 KB |
| Arena (`floor-plan-3`) | 1700 x 2200 | 1583 x 2048 | 12.4 MB | 356 KB | 468 KB | 596 KB | 1452 KB | **198 KB** | 920 KB |
| Seaside (`floor-plan-4`) | 2200 x 1700 | 2048 x 1583 | 12.4 MB | 311 KB | 395 KB | 491 KB | 974 KB | **135 KB** | 589 KB |
| Campus (`campus-map`) | 2200 x 1700 | 2048 x 1583 | 12.4 MB | 371 KB | 500 KB | 643 KB | 1595 KB | **170 KB** | 1154 KB |
| Job fair (`job-fair`) | 1700 x 2164 | 1609 x 2048 | 12.6 MB | 342 KB | 473 KB | 619 KB | 1460 KB | **152 KB** | 1122 KB |
| Expo (`pycon-us-2026-floorplan-nologo`) | 4966 x 3511 | 2048 x 1448 | 11.3 MB | 383 KB | 525 KB | 685 KB | 1408 KB | **178 KB** | 1093 KB |

- **Legibility at maximum zoom** (one image pixel to one logical pixel, scaled to the screen's 3x): booth 245's "Lerner Python Training", its logo and its number, and the Concourse plan's "ELEV." and room letter read the same in JPEG 70, JPEG 85, WebP 80 and PNG. WebP decoded and drew on iOS (the screenshot is the WebP).
- **Origins and marks, for `NOTICE` (D-87) and D-36:** all seven files are the Ionic app's (`src/assets/img/floor-plans/*.jpg` and `src/assets/img/pycon-us-2026-floorplan-nologo.jpg`, Apache-2.0). The four level plans are the venue's drawings with GES's title block ("Plan prepared by GES") and no PyCon or PSF mark. **Three carry PyCon marks:** the campus map (the "PyCon US 2026" wordmark at the top left, and the Long Beach CVB logo), the job fair plan (the PyCon US 2026 logo across the top) and the expo plan (the PyCon sun-and-palms mark at the top left, despite the file's "nologo"). The expo plan also bakes in sponsors' logos at their booths.

### Memory, iOS simulator (debug build, `phys_footprint`)

| State | Footprint | Peak |
|---|---|---|
| Plain list (after the first frame) | 258 MB | 262 MB |
| Expo, WebP 2048 px, 61 booths (first build: each booth drew an error box, F130), 1x | 266–268 MB | 295–302 MB |
| …at 5.36x | 270 MB | 295 MB |
| …after 8 drags at 5.36x | 266 MB | 295 MB |
| Expo, containers build (F130 fixed), 1x / 5.36x / after 8 drags | 259 / 254 / 265 MB | 281 / 281 / 302 MB |
| Expo, the 4966-px source JPEG (fresh start), 1x and 13x | 270 MB | **347 MB** |

A debug build runs Dart in JIT mode, so the absolute numbers are a ceiling; the differences are what count: the plan and its booths add about 10 MB in steady state and about 40 MB while decoding at 2048 px, against about 90 MB for the source plan.

### Android on the 2.5 GB AVD (the rerun, incomplete)

`pycon_lowram_api34` with `-read-only -no-audio -no-boot-anim -no-snapshot`, a release APK rebuilt from this branch's `main.py` (keyed panes, 60.4 MB, arm64), driven with `drive_android.py`; memory from `dumpsys meminfo`, which gives no Dart heap.

| Time | Step | Host load (1 min) | Result |
|---|---|---|---|
| 12:06 | First boot | 49 | booted in 25 s; the install took 4 min; a "Process system isn't responding" dialog over the app |
| 12:13 | First launch | 26 | Python's first line about 70 s after the launch; the app showed its Plain tab |
| 12:21, 12:32 | Two more launches | 37–280 | Python started (it wrote its CA file 4 and 2 min after each launch) but logged no line in 8 and 14 min, and the screen stayed white; `dumpsys meminfo`'s 10-s timeout expired, `uiautomator dump` was killed (exit 137) and `/sdcard` lost its FUSE mount; the emulator was shut down |
| 12:50 | Second boot | 52–139 | `boot_completed` after **10 min** (25 s the first time) |
| 13:02 | Launch | 32 | Python's first line after 89 s |
| 13:06–13:07 | **Plain list** | 71–121 | **PSS 120–121 MB, RSS 239–240 MB**: native heap 34 MB, code 35–36 MB, private other 37–38 MB, Java heap 1 MB, **Graphics 0** |
| 13:07–13:10 | Open Expo | 45–121 | `uiautomator dump` failed three times (`UiAutomation` connect timeout); a tap by coordinates found no `input` service |
| 13:10 | System server | 45–83 | **killed by its watchdog** ("Blocked in handler on main thread for 170 s"), taking the app with it; its successor was blocked for 90 s by 13:13; the time box ended (13:15) |

- **The baseline:** in a release build, the plain list costs about **120 MB PSS** (240 MB RSS) on Android, with 1.3 GB of the AVD's 2.5 GB available beside it (`MemAvailable`). It answers nothing about the plan.
- **What stopped it was the host's memory, not its load:** with the swap 94–98 % full, the AVD's 2.5 GB lived mostly in the host's swap (the emulators' resident sizes were 0.25–1 GB), so the guest's own start-up work (Google Play services, Search, Gmail and YouTube Music on a Google APIs image, guest load 20–43) starved the system server until its watchdog fired, as it did this morning. A load average of 30–50 does not make the host quiet; the swap must be.
- **Graphics 0:** this emulator's `dumpsys meminfo` has no GL or EGL mtrack rows, so textures on its host-side GPU do not show in the app's PSS. On an emulator the plan's cost must be read from Native Heap and Unknown, and the GPU's share is missing from it; only a phone shows all of it.
- `drive_android.py` now starts the app with `am start -W` (`monkey` exited 251 once), gives `dumpsys meminfo` 60 s (`-t 60`) and tries `uiautomator dump` three times.

### Android on the 2.5 GB AVD (the third run)

2026-10-29, 16:05–16:20 on the device. `pycon_lowram_api34` with `-read-only -no-audio -no-boot-anim -no-snapshot -port 5590`; it booted in about 20 s, each install took under a second, and Python's first line came 3 s after the launch. No dialog, watchdog, hung install or timeout. Memory from `dumpsys meminfo` (MB): PSS and RSS are the totals, Native Heap the App Summary's row, Unknown the PSS row of the detailed table (the emulator reports Graphics 0). The host's swap was 6453 MB used and 1739 MB free at every step, so the table gives the 1-min load beside it.

**The reproducer** (`drive_android.py`, keyed panes, `fixed` tabs, containers, `expo.webp`):

| Time | Step | Host load, swap free | PSS | RSS | Native Heap | Unknown |
|---|---|---|---|---|---|---|
| 16:06:40 | Plain list (3 readings) | 4.8, 1.74 GB | 127–133 | 213–220 | 33 | 35 |
| 16:07:07 | Expo, 1x, just opened (`render_ms` 30.9) | 3.9, 1.74 GB | 140 | 227–228 | 37 | 37 |
| 16:08:08 | …after tapping all 61 booths | 2.3, 1.74 GB | 147 | 236 | 36 | 44 |
| 16:08:18 | …5.23x (Max) | 2.1, 1.74 GB | 146–147 | 235–236 | 36 | 44 |
| 16:09:01 | …after 16 drags at 5.23x | 2.1, 1.74 GB | 148 | 238 | 36 | 44 |
| 16:09:24 | …after a `frames 20` (48 more drags) | 2.3, 1.74 GB | 148 | 238 | 36 | 44 |
| 16:11:39 | …after 5 taps at 5.23x | 1.6, 1.74 GB | 150 | 240 | 36 | 44 |
| 16:11:53 | Cycle 20: after 1 | 1.6, 1.74 GB | 148 | 238 | 36 | 44 |
| 16:12:11 | …after 10 | 1.6, 1.74 GB | 158 | 248 | 36 | 54 |
| 16:12:31 | …after 20 | 1.5, 1.74 GB | 156 | 247 | 36 | 52 |
| 16:12:47–16:13:30 | Cycle 20 again: after 21, 30, 40, and 5 s later | 1.4–1.6, 1.74 GB | 156–157 | 247–248 | 36 | 51–53 |
| 16:13:45 | The 4966-px source JPEG, 2 s after the switch | 1.3, 1.74 GB | **204** | 295 | **82** | 54 |
| 16:13:52 | …7 s after; then back to the WebP | 1.3, 1.74 GB | 158 | 248–249 | 36–38 | 53 |
| 16:14:12 | Fresh launch, plain list | 1.3, 1.74 GB | 131 | 217 | 37 | 35 |
| 16:14:13 | …Expo, read within 1 s of the tap | 1.3, 1.74 GB | 139–142 | 226–231 | 38 | 35–36 |

| Check | Result |
|---|---|
| `frames 20` at 5.23x, twice (Flutter's BLAST layer) | 127 frames each (SurfaceFlinger keeps the last 128), median **16.7 ms**, p90 17.0 and 17.1 ms, **0** over 33 ms; 8–9 transforms logged per 4 drags |
| `booths` at 1x | **61** nodes, 61 named `Booth <n>, <name>` with id `booth.<n>`, 61 distinct; 26–66 x 22–74 px, about 15–38 x 13–42 dp |
| `tapall` at 1x | **61 / 61** right |
| `booths` and `tapall` at 5.23x, panned | the 5 booths on screen are in the tree (off-screen ones drop out); 78–160 px wide; **5 / 5** right |

The tree's order, which is TalkBack's: 245, 344, 342, 243, 639, 638, 539, 141, 240, 140, 138, 238, 635, 734, 735, 137, 136, 237, 236, 434, 335, 732, 733, 633, 135, 234, 334, 134, 235, 630, 531, 631, 730, 427, 226, 127, 126, 629, 728, 726, 627, 122, 421, 720, 621, 119, 116, 213, 413, 613, 113, 513, 313, 713, 112, then **731, 729, 606, 407, 727, 709** last. Mostly top to bottom by each booth's top edge, but not strictly, and not in booth-number order: the List stays the screen reader's way to a booth.

**The app** (release APK, `io.github.ndonkohenri.pyconus`, fresh install; taps by `resource-id`, which is Flet's `Semantics` identifier, D-166):

| Time | Step | Host load, swap free | PSS | RSS | Native Heap | Unknown |
|---|---|---|---|---|---|---|
| 16:14:52 | Welcome (first launch) | 1.3, 1.74 GB | 173 | 265 | 50 | 58 |
| 16:15:02 | Now (2 readings) | 1.2, 1.74 GB | 183 | 275–276 | 49 | 61 |
| 16:15:13 | Map › Rooms | 1.1, 1.74 GB | 187 | 281 | 49 | 64 |
| 16:15:15 | Map › Floor plans (two thumbnails on screen) | 1.1, 1.74 GB | 187 | 281 | 49 | 64 |
| 16:15:27 | Concourse plan, 1x | 1.1, 1.74 GB | 189 | 283 | 51 | 65 |
| 16:15:57 | …maximum zoom (zoom in until disabled) | 0.9, 1.74 GB | 191 | 285 | 50 | 67 |
| 16:16:05 | …after 16 drags | 1.0, 1.74 GB | 196 | 289 | 50 | 69 |
| 16:16:56 | Map › Expo, 1x, 61 booths | 1.3, 1.74 GB | 197 | 290 | 50 | 70 |
| 16:16:59 | …maximum zoom | 1.3, 1.74 GB | 197 | 290 | 50 | 71 |
| 16:17:19 | …after 16 drags | 2.5, 1.74 GB | 198 | 291 | 50 | 71 |
| 16:17:37 | …after `frames 15` (about 36 more drags) | 2.7, 1.74 GB | 198 | 291 | 50 | 71 |
| 16:17:58–16:18:35 | Concourse plan opened and closed with Back: after 1, 5, 10 | 2.1–2.3, 1.74 GB | 199, 200, 200 | 293–294 | 50 | 73–74 |
| 16:19:01–16:19:38 | Expo tab left (Rooms) and reopened: after 1, 5, 10 | 1.7–1.9, 1.74 GB | 202, 204, 202 | 296–298 | 50–51 | 75–77 |

- **Frames in the app:** the Concourse plan and the expo map at their maximum zoom, 15 s of drags each: 127 frames, median **16.7 ms**, p90 17.1 and 17.0 ms, 0 over 33 ms. The app logs no transforms, so a screenshot before and after confirmed that the plans moved.
- **The app's tree:** 61 `expo.booth.<n>` nodes, each named (`Booth 245, Reuven Lerner — Python training`), in the reproducer's order. At the maximum zoom a tap on booth 335 opened its card (`Booth 335, Pydantic, Supporting sponsor`), and the expo pane came back at its zoom after leaving the tab (D-18).
- **The guest:** `MemAvailable` 1.39 GB of 2.48 GB after the boot, 1.13–1.21 GB during the runs. The system trimmed empty cached processes once (16:16:04, `am_kill` "empty #17–45"); it killed none of the app's processes (the only kills were the driver's force-stops), and lmkd and the watchdog logged nothing.

What it shows:

- **The plan's cost on Android is small and steady.** 13–17 MB PSS in the reproducer (133 → 146–150), mostly Unknown (+9) and Native Heap (+3–4); the zoom adds nothing; in the app the plans add 2–11 MB over Rooms (17 MB at most after the cycles). The 2048-px WebP read 142 MB at most within 1 s of the tap, a snapshot that a shorter decode peak could slip past; the 4966-px source showed one (Native Heap +46 MB for a few seconds), so the decode happens in Native Heap and is let go once the image is on the GPU: re-encoding keeps that peak small, as on iOS.
- **No leak at these counts:** the reproducer grows 10 MB over its first 10 cycles and not at all over the next 30 (156–158 MB); the app grows 1 MB over 10 plan cycles and none over 10 expo cycles.
- **Usable:** 60 frames a second while panning at the maximum zoom, and every tap on the right booth.
- **Not measured (Graphics 0):** the GPU's share. The decoded expo plan is 11.3 MB of RGBA (about 15 MB with mipmaps, by arithmetic), held by the host's GPU on the emulator, so on a phone it adds to these numbers; it does not change the verdict at 1.1 GB available.
- `drive_android.py` now reports Unknown's PSS (`mem`), and `frames` reads Flutter's BLAST layer, quoting its name for the device's shell: on Android 14 the plain `SurfaceView` layer and its "Background for" layer report only zeros, which the first try of this run returned (`count=0`).

### Taps

| Mode | Zoom | Taps | Right | Notes |
|---|---|---|---|---|
| Containers in `Semantics` | 1x | 245, 639 | 2 / 2 | Flutter's hit test |
| Containers in `Semantics` | 5.36x, panned | 245, 344 | 2 / 2 | the screenshot above |
| One `GestureDetector`, Python hit test | 1x | 245, 639 | 2 / 2 | local positions (160, 38) and (311, 58) on a 382 x 270 plan |
| One `GestureDetector`, Python hit test | 5.36x, panned | 245, 344, 243 | 3 / 3 | positions exact to 0.1 dp of the plan; two first aims at the booths' edges missed by 0.1 dp and were aimed again |

- At 1x a booth is about **18 x 12 dp** on a 382-dp plan (booth 245: 0.048 x 0.047 of the plan), below the 24-dp minimum target (WCAG 2.5.8) and far below 48 dp: a finger at 1x cannot be sure of a booth. The List (§6.2) and the zoom are the way to a booth; the map at 1x is for finding the area.
- **Double-tap delay**, one detector with `on_tap_down` and `on_tap`: tap down to tap 14–30 ms (5 ms once) without a double-tap detector, **326 ms** with one around the viewer.

### Pan versus swipe, and zoom across a tab switch

| Case | Result |
|---|---|
| `TabBarView`, Plan at 5.36x, drag right to left over 2.5 s | **tab changed** (Plan → Expo), the plan did not move |
| `TabBarView`, Expo at 1x, drag left to right over 2.5 s | tab changed (Expo → Plan) |
| `TabBarView`, Expo at 5.36x, drag over 0.4 s | the plan panned (x −228); Maestro's fast drag moves past the viewer's 36-dp pan slop in its first events, which a finger does not |
| Lone pane under a `TabBar`, 5.36x, drags in four directions | panned every way; no tab change possible |
| Keyed panes (`key="plan"`, `key="expo"`): booth 245 selected on Expo, then Plan | Plan mounts afresh (its `mounted` line) and shows no booth; unkeyed, the first run's Plan showed "booth 245" |
| Plan at 5.36x, panned to (−321.7, −214.5), `save_state()`, away to Expo and back | Plan mounts afresh |
| …`restore_state()` | **scale 1.0, (0, 0)**: the pane's state, and the saved matrix, left with it |
| …the last `on_transform_changed` (5.361, −321.7, −214.5), then `reset()`, `zoom(5.361)`, `pan(−321.7 / 5.361, −214.5 / 5.361)` | **scale 5.361, (−321.7, −214.5)**, exact |

- **Why the pages win:** the `PageView` under `TabBarView` accepts a horizontal drag after 18 dp (`kTouchSlop`); the viewer's scale recognizer after 36 dp of focal movement (`kPanSlop`, Flutter `gestures/scale.dart:746-752`, `constants.dart:65,76`). A finger crosses 18 dp first, so the page takes the drag at every zoom; only a synthetic drag that jumps past 36 dp in one event reaches the viewer first.
- **No `physics` at the pin:** Flet's `TabBarView` sets `physics: control.disabled ? NeverScrollableScrollPhysics() : null` (`DART/controls/tabs.dart:175-176`), and `disabled` is inherited by every descendant (`DART/models/control.dart:82-83`), so it would disable the booths too (F130, U110).

## Not covered

- **A real low-RAM Android phone, and the GPU's share.** The third run answered the gate on the 2.5 GB AVD (above), after two attempts on 2026-10-21 that the host's full swap stopped ("the rerun, incomplete"). The emulator reports Graphics 0, so the plan's texture is not in its numbers; a borrowed 2 GB phone would count it, and would show how lmkd treats the app beside other apps. No phone is available (D-102).
- **TalkBack over the 61 booth nodes** (spoken order and time to a booth): not run. The uiautomator check ran in the third run: all 61 are reachable and named, in an order that is mostly top to bottom but not strictly, and not booth-number order (above); the Map's List is the screen reader's way to a booth either way (§6.2: List first when `accessible_navigation`). The build issue checks the order with TalkBack.
- **20 open/close cycles on iOS:** the Maestro CLI crashed before the cycle button was tapped; not measured.
- **Frame times on iOS:** no usable numbers on this host (load 290–910). Panning at 5.36x on the simulator looked smooth in the screenshots taken, which says little. Android has them from the third run (a 16.7-ms median at 5.23x, above).
- **Release-build memory on the iPhone:** #121 (D-102), with the expo plan at 1x and 5.36x and after 20 cycles.

## Decisions changed

- **D-312** (amends ux.md §5.8, §6.1, §6.2; keeps D-18): plans as 2048-px WebP q80 from `reencode.py`, no `cache_width`; `max_scale = natural / displayed`; booths as `Container`s in `Semantics(content=...)`; no double-tap where something on the plan is tappable; Map panes under a `TabBar` without a `TabBarView`; a pane's zoom kept in `ViewMemory` and put back with `reset`, `zoom`, `pan`.
- **F130:** `ft.Semantics(x)` puts `x` in `tooltip`; `TabBarView` can only stop swiping by disabling its pages; a pane's `InteractiveViewer` state (and `save_state`'s matrix) does not survive the pane leaving.
- **U110** ([#560](https://github.com/ndonkoHenri/pycon-us-flet/issues/560)): `TabBarView.physics` (`docs/flet-gaps-and-extensions.md` §1.3).

## What the map issues must apply

- **Plans (DATA-32, MAP-07):** run `reencode.py` on each year's plans and bundle the `.webp` files; crop or cover the PyCon marks on the campus, job fair and expo plans before they ship (D-36), and credit the plans in `NOTICE` (D-87) in the same PR.
- **Floor viewer (§6.1) and expo map (§6.2):** `InteractiveViewer(min_scale=1, max_scale=natural_width / displayed_width)` around a `Stack` sized from `on_size_change`; booths as positioned `Container`s, each `Semantics(content=..., button=True, label="Booth 613, Bloomberg", identifier=...)` with `content=` by name (F130); the selection drawn on the booth's own `Container`.
- **Map (§5.8):** `Tabs` with a `TabBar` and the selected pane alone under it, each pane keyed (F130); each pane's last `on_transform_changed` in `ViewMemory`, put back after the pane is laid out with `reset()`, `zoom(s)`, `pan(x / s, y / s)` (two or three frames show the steps; U3's `set_transform` removes them).
- **The low-RAM gate (passed on the 2.5 GB AVD, 2026-10-29):** the expo map may ship on this evidence. TalkBack's spoken order and the time to reach a booth stay with #453; a real low-RAM phone, when one is borrowed, reruns `drive_android.py` and adds the GPU's share; the Fallback applies if it fails there.

## Fallback

If a plan at 2048 px proves too heavy on a real low-RAM Android phone, drop the plans to 1600 px (about 7 MB decoded, still 4.2x zoom on a 382-dp plan) before reaching for `cache_width`; if 61 `Semantics` buttons prove slow for TalkBack, keep the containers for touch and mark them `exclude_from_semantics`, leaving the List as the screen reader's path.
