# S9: Can the UI flows run in CI with `flet test linux`?

**Spike:** S9 ([#363](https://github.com/ndonkoHenri/pycon-us-flet/issues/363), PLAN §8). **Date:** 2026-11-04. **Decides:** D-492. **Branch, never merged:** `test/363-flet-test-linux`.

## Answer: no for Linux; an Android emulator in Actions is the better road

`flet test linux` itself works. It provisions a host, builds it and starts the app under `xvfb` on a GitHub runner. But our app and our flows are phone-only by design, so getting them to run takes a third platform path in both, and even then 5 of 7 flows can't reach their scene. That's against AGENTS.md's principle 3 (no desktop code paths), for a host that isn't a phone.

The fallback looks far better, and needs no change to the app or the flows: `flet test android` on a KVM emulator on the same runner **passed the first flow it ran** (`drill_back`). Then the 2-vCPU, 7.9 GB private runner went away during the next flow's Gradle build, twice. A public repo's runner has 16 GB, so this is worth trying right after the flip.

**This is not the 10-run flakiness measure the issue asked for.** I was asked to start with 3 runs. No Linux run went green, so there's nothing to repeat, and flakiness is unmeasured.

## Results

**`flet test linux`, the final run** ([41859133332](https://github.com/ndonkoHenri/pycon-us-flet/actions/runs/41859133332)), with every workaround below:

| Flow | Result | Why |
|---|---|---|
| `test_shell_starts` | passed | |
| `test_snackbar_on_pushed_view` | passed | With the primer step skipped: nothing to ask on Linux |
| `test_drill_back` (F5) | failed | "About this app": 0 on screen after 15 s |
| `test_favourite_undo` (F4) | failed | The same |
| `test_search_keeps_query` (F3) | failed | The same |
| `test_start_offline` (F1) | failed | The same |
| `test_switch_days` (F2) | failed | The same |

**The fallback, `flet test android`,** API 36 Google APIs x86_64: `drill_back` passed in run [41865955349](https://github.com/ndonkoHenri/pycon-us-flet/actions/runs/41865955349). The job ended with "The runner has received a shutdown signal" during the next flow's `assembleDebug`. An earlier run ([41861200280](https://github.com/ndonkoHenri/pycon-us-flet/actions/runs/41861200280), 4 GB emulator) got the same signal during its first build. Out of memory is my inference, from a 4 GB Gradle heap beside a 2 GB emulator on 7.9 GB; the log doesn't say.

## What Linux needed, in the order each one showed

| # | Blocker | Workaround on the spike branch | Kind |
|---|---|---|---|
| 1 | `flet_permission_handler/permission_handler.py:35` raises `FletUnsupportedPlatformException` on Linux, and the app dies at start | `_permissions()` returns None on Linux | **App code path** |
| 2 | `connectivity_plus` throws `DBusServiceUnknownException`: no `org.freedesktop.NetworkManager` | Install NetworkManager, told to leave every device unmanaged | Runner setup |
| 3 | `open_about_app()` sends a deep link through `adb`, or Maestro on iOS. Linux has neither, and no link handler | Tap the row instead, which needs it on screen | **Flow code path** |
| 4 | The row is below the fold, and a flow can't scroll (U35). `setWindowSize(412, 1400)` is logged, but no new page size follows, with or without a window manager | None found: this stopped the 5 flows | **Flow code path** |
| 5 | App data outlives a flow, where a phone's install starts clean, so `welcome.start` never shows | A fixture wipes `~/.local/share/io.github.ndonkohenri.confcompanion` | **Flow code path** |
| 6 | `answer_primer_not_now()` waits for a primer that Linux never shows | Skipped on Linux | **Flow code path** |
| 7 | `screenshot()` knows `adb` and `xcrun` only | ImageMagick's `import -window root`, whose pictures came out all black, so they show nothing | **Flow code path** |

**Differences from a phone that no workaround changes:** a debug build; no Back key, so `press_system_back` can't run; no permissions to ask for; no real connectivity (NetworkManager reports `disconnected`).

## Timings and minutes

| Run | Result | Job |
|---|---|---|
| [41848893582](https://github.com/ndonkoHenri/pycon-us-flet/actions/runs/41848893582) | 7 errors, blocker 1 | 9 min 41 s |
| [41851770215](https://github.com/ndonkoHenri/pycon-us-flet/actions/runs/41851770215) | 7 errors, blocker 2 | 16 min 12 s |
| [41854800558](https://github.com/ndonkoHenri/pycon-us-flet/actions/runs/41854800558) | 7 failed, blockers 3, 5 and 6 | 11 min 29 s |
| [41857111233](https://github.com/ndonkoHenri/pycon-us-flet/actions/runs/41857111233) | 7 failed, blockers 4 and 7 | 10 min 4 s |
| [41859133332](https://github.com/ndonkoHenri/pycon-us-flet/actions/runs/41859133332) | 2 passed, 5 failed | 10 min 31 s |
| [41861200280](https://github.com/ndonkoHenri/pycon-us-flet/actions/runs/41861200280) | Android: runner lost in its first build | 13 min 20 s |
| [41865955349](https://github.com/ndonkoHenri/pycon-us-flet/actions/runs/41865955349) | Android: 1 passed, then runner lost | 16 min 58 s |

**Projected:** about 11 minutes a run on Linux, so 30 runs a month would take about 330 of a private repo's 2,000. A public repo's runners are free, so minutes don't decide this.

## Versions

Flet 1.1.0.dev4 from PyPI (D-481), Flutter 3.47.9, the app's CPython 3.14.10, `ubuntu-latest` as `ubuntu-24.04` (image 20261101.360.1), 2 vCPUs, 7.9 GB. `xvfb-run` on a 1280 × 1600 screen, `dbus-run-session`, `gnome-keyring`, `dunst`, `openbox`.

## Upstream

None opened. `PermissionHandler` refusing Linux is reasonable for an extension that doesn't support it, and this app doesn't need Linux. The gap that actually stopped the flows is U35, `RemoteTester` having no drag, already recorded.

## Fallback

The device flows stay where they are (D-102), and Maestro's smoke set now runs in Actions (D-484). A follow-up tries `flet test android` on the public runner, and runs for two weeks before D-78's `needs-decision` proposal.
