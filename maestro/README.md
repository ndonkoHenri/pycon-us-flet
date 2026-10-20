# Maestro flows

Device flows for the packaged app (`io.github.ndonkohenri.pyconus`), run with the free,
local [Maestro](https://maestro.dev) CLI on an Android emulator and an iOS simulator,
from one set of YAML files (D-252, #348). They check P1's exit journeys (PLAN §7,
criteria 1 and 2) and repeat regression trials such as #346's row D. Where Maestro fits
next to the `flet test` flows in `tests/ui/` is in
[`docs/testing-and-quality.md`](../docs/testing-and-quality.md) §5.5.

**Free only.** Use the local CLI (and its MCP tools, if you like). Never Maestro Cloud,
`maestro cloud`, `maestro login` or a paid plan.

## What is here

| Path | What it is |
|---|---|
| `config.yaml` | The workspace: `maestro test maestro` runs `journeys/*` and `regression/*` |
| `journeys/` | P1's exit journeys, tagged `journeys` (two also `smoke`) |
| `regression/` | Trials repeated N times to compare two builds, tagged `regression` |
| `subflows/` | Steps the flows share through `runFlow`; never run on their own |
| `scripts/` | JavaScript that a flow runs (`runScript`) |

| Flow | Tags | What it checks |
|---|---|---|
| `journeys/drill_back.yaml` | journeys, smoke | Now → a session happening now → its speaker → the speaker's other session; each Back leaves one View, back to Now (exit criteria 1 and 2, #279) |
| `journeys/star_undo.yaml` | journeys, smoke | Star on Now (Now shows it as "Your next session"), My schedule lists it, unstar there, "Removed from My schedule", Undo brings it back |
| `journeys/my_schedule_overlap.yaml` | journeys | Two saved sessions that overlap: each row on My schedule says which one it overlaps |
| `journeys/search_any_day.yaml` | journeys | From Friday's Schedule, search finds a Saturday session, its speaker and a room used only on Saturday; Back keeps the query and the scope |
| `journeys/filter_persists.yaml` | journeys | Hide AI: the Schedule says "Hidden: AI, Open space", the AI talk is gone; after a relaunch it still is, and the sheet still has AI off |
| `journeys/jump_to_now.yaml` | journeys | The Schedule opens with the now slot at the top; after flings, Jump to now puts it back there |
| `regression/fling_after_sheet.yaml` | regression | #346's row D: Open space shown through the sheet, then a fling right after "Show N sessions", `TRIALS` times; each trial is "moved", "short" or "none" |

Every flow starts from `subflows/start_offline.yaml`: a fresh launch (`clearState`),
airplane mode on Android, then Developer options set as `tests/ui/developer.py` does
(More › About this app › the version row 7 times › Developer options): a fake clock at
**Friday 2026-05-15 14:10** (the busiest day, during the 2:00 PM slot) and a feed URL
nothing answers at, then Refresh now must say "No answer from the feed". `NOW` and
`OFFLINE_URL` override them (`-e NOW="2026-05-16 10:00"`). On iOS Maestro cannot cut the
simulator's network, so the launch's own refresh may publish the year's live feed, which
lists the same sessions as the bundled snapshot.

## Setup (once)

- **Maestro 2.11.0**, from Maestro's own Homebrew tap: `brew install
  mobile-dev-inc/tap/maestro`. Not `brew install maestro`, which is another product. The
  tap's formula brings Homebrew's `openjdk`, the Java Maestro needs (17 or later); with
  Maestro's `curl` installer instead, install a JDK 17+ yourself. Check with
  `maestro --version`.
- To keep the CLI from sending usage data: `export MAESTRO_CLI_NO_ANALYTICS=1`.
- iOS needs Xcode and its simulators, nothing more: Maestro installs its XCTest driver on
  the simulator by itself.

## Devices: your own

The bundle id is the app's own, so a run replaces the app on the device: use an emulator
and a simulator of your own (D-102), never the owner's `emulator-5554` or a shared
simulator.

```bash
# Android: flet_probe_api34 (D-102), read-only, on an even free port in 5570..5598.
~/Library/Android/sdk/emulator/emulator -avd flet_probe_api34 -read-only -no-audio -no-boot-anim -port 5570 &
adb -s emulator-5570 wait-for-device
adb -s emulator-5570 shell settings put secure show_ime_with_hard_keyboard 0

# iOS: an iPhone 17 on iOS 26.5 of your own.
xcrun simctl create "<issue>-iphone17" "iPhone 17" com.apple.CoreSimulator.SimRuntime.iOS-26-5
xcrun simctl boot <udid>
```

If the AVD is missing ("Unknown AVD name"), make one like it in a folder of your own,
from the API 34 Google APIs image (a Pixel 7: 1080 x 2400 px, 420 dpi), with
`hw.keyboard=yes` and `hw.ramSize=4096M` in its `config.ini`:

```bash
ANDROID_AVD_HOME=<folder> avdmanager create avd -n flet_probe_api34 \
  -k "system-images;android-34;google_apis;arm64-v8a" -d pixel_7 -p <folder>/flet_probe_api34.avd
ANDROID_AVD_HOME=<folder> ~/Library/Android/sdk/emulator/emulator -avd flet_probe_api34 -read-only ...
```

Animations stay on: Maestro waits for them (`waitForAnimationToEnd`), and #346's row D
needs the sheet's exit animation. When you are done, kill the emulator
(`adb -s emulator-5570 emu kill`) and delete the simulator
(`xcrun simctl delete <udid>`).

## Build and install

From the repo root, with the worktree's own pub cache when other builds may run
([`docs/development.md`](../docs/development.md) §5.8):

```bash
# Android: a release APK (arm64)
PUB_CACHE=$PWD/build/pub-cache uv run flet build apk --arch arm64-v8a --yes
adb -s emulator-5570 install -r build/apk/pycon-us.apk

# iOS: a simulator build (debug: Flutter has no release mode for simulators, D-102)
PUB_CACHE=$PWD/build/pub-cache LANG=en_US.UTF-8 uv run flet build ios-simulator --yes
xcrun simctl install <udid> build/ios-simulator/pycon-us.app
```

Check that the build holds this tree's Python (§5.8's `diff -rq` lines) before you trust
a result.

## Run

```bash
# Every journey, on one device
maestro --device emulator-5570 test --include-tags=journeys maestro
maestro --device <udid> test --include-tags=journeys maestro

# A quick subset, or one flow
maestro --device emulator-5570 test --include-tags=smoke maestro
maestro --device <udid> test maestro/journeys/search_any_day.yaml

# The regression trials (10 by default), with the debug output in a known folder
maestro --device emulator-5570 test -e TRIALS=30 \
  --debug-output build/maestro/fling-pr --flatten-debug-output maestro/regression/fling_after_sheet.yaml
grep -h JsConsole build/maestro/fling-pr/maestro.log | sed 's/.*JsConsole: //'
```

Each flow prints its steps and ends with `[Passed]` or `[Failed]` and its time. A failed
step's screenshot and the view hierarchy are in the debug output, under
`~/.maestro/tests/<date>/` unless `--debug-output` names a folder (keep it under
`build/`, which git ignores).

**Comparing two builds** (#346's row D): install `main`'s APK, run the regression flow,
install the PR's APK, run it again with the same `TRIALS`, and compare the two summaries
(`flings after the sheet, N moved, N short, N none, of N`). The flow fails when any trial
was short or none. On Android the launcher logs every touch, so the time from the tap on
"Show N sessions" to the fling is `adb -s emulator-5570 logcat -d | grep TaplEvents`: the
`ACTION_UP` at (540, 2232), then the `ACTION_DOWN` at (540, 1800), by `eventTime` (ms).

## Writing a flow

- Find a control by its identifier, `id:` (`<screen>.<element>[.<key>]`, D-33), copied
  from `maestro hierarchy` (Android: `resource-id`; iOS: the element's id, F72). Never
  guess one. Text comes second, as the full string: Maestro's `text:` is a regular
  expression that must match the whole label, so escape `.`, `?` and `(`.
- A control with no identifier gets one in `src`, the smallest change (as `app.search`,
  D-252). The app bar's back arrow has none: use `subflows/back.yaml`, the system Back on
  Android and the button named "Back" on iOS.
- After typing, `pressKey: Enter` closes the keyboard. On Android a Back would only close
  Gboard's bar, which comes back while the field keeps the focus.
- `subflows/top_slot.yaml` reads the Schedule's top row and its start time, which is how
  a flow tells where a list rests.
- **On Android, Maestro makes the app think a screen reader is on** (F72): Flutter reports
  `accessible_navigation` once anything reads its accessibility tree. The app then keeps
  the Schedule's Now button on the now slot, and by D-184 keeps SnackBars until they are
  used, as it does for TalkBack. Check those behaviours on iOS only.
- About 0.85 s passes between two Maestro commands on the emulator (0.8 s on the
  simulator), so a step can never follow the last one faster. #346 saw its failures with
  0.33 to 0.6 s between the tap and the fling, which Maestro cannot reach (see the run
  times below).
- Each flow that runs `start_offline.yaml` turns the network back on in its
  `onFlowComplete` (`subflows/online.yaml`).

## Run times (#348)

Release APK on `flet_probe_api34` (Android 14) and an `ios-simulator` build on an
iPhone 17 simulator (iOS 26.5), Flet pin `15854a0ac`, on 2026-10-20, on a host shared
with other agents' builds and emulators. Each journey takes 1 to 1.5 minutes on a quiet
host, most of it the fresh start in Developer options; the runs while the host's load
average was in the hundreds took up to 3 minutes a journey.

| Run (the flows as merged) | Android | iOS |
|---|---|---|
| Journeys, run 1 | 6 of 6 passed, 9 min 10 s | 6 of 6 passed, 8 min 13 s |
| Journeys, run 2 | 6 of 6 passed, 7 min 55 s | 6 of 6 passed, 7 min 29 s |
| `regression`, `main`'s build (`1a2c2b5`) | `TRIALS=20`: 20 moved, 10 min 23 s; tap to fling 773-914 ms (median 870) | `TRIALS=10`: 10 moved, 5 min 5 s; tap command 0.77 s |
| `regression`, #346's build (`7ccd74f`) | `TRIALS=20`: 20 moved, 10 min 44 s; tap to fling 807-1,019 ms (median 858) | not run |

Earlier versions of the flows failed twice on iOS while the host's load average was 400
to 700: Developer's feed URL lost two characters as it was typed (F63), and the overlap
flow's star tap landed while the Schedule was still jumping to now. Both are handled now
(a field is typed until it holds the whole value; the star waits for the jump, then is
tapped again if it stayed off). At that load the regression flow also lost a fling on
`main`, with 1.3 to 3.5 s between the tap and the fling: a busy host stretches the
sheet's exit past the fling. Compare builds only on a quiet host, one right after the
other.

#346's row D failed with 0.33 to 0.6 s between the tap and the fling. Both builds ran
every fling in full at about 0.85 s, the soonest Maestro gets there, so this flow does
not reach that window: it guards the fling at Maestro's pace, and the faster window
stays with an `adb` script (`input tap`, then `input swipe`).
