# Maestro flows

Device flows for the packaged app (`io.github.ndonkohenri.pyconus`), run with the free,
local [Maestro](https://maestro.dev) CLI on an Android emulator and an iOS simulator,
from one set of YAML files (D-252, #348). They check P1's exit journeys (PLAN §7,
criteria 1 and 2) and repeat regression trials such as #346's fling after the filter
sheet; row D's faster window has an `adb` driver, `tools/fling_after_sheet.py`
([below](#row-d-through-adb)). Where Maestro fits
next to the `flet test` flows in `tests/ui/` is in
[`docs/testing-and-quality.md`](../docs/testing-and-quality.md) §5.5.

**Free only.** Use the local CLI (and its MCP tools, if you like). Never Maestro Cloud,
`maestro cloud`, `maestro login` or a paid plan.

## What is here

| Path | What it is |
|---|---|
| `config.yaml` | The workspace: `maestro test maestro` runs `journeys/*` and `regression/*` |
| `journeys/` | P1's exit journeys and later screens' journeys, tagged `journeys` (two also `smoke`) |
| `regression/` | Trials repeated N times to compare two builds, tagged `regression` |
| `subflows/` | Steps the flows share through `runFlow`; never run on their own, except `fling_setup.yaml`, which `tools/fling_after_sheet.py` runs |
| `scripts/` | JavaScript that a flow runs (`runScript`) |

| Flow | Tags | What it checks |
|---|---|---|
| `journeys/drill_back.yaml` | journeys, smoke | Now → a session happening now → its speaker → the speaker's other session; each Back leaves one View, back to Now (exit criteria 1 and 2, #279) |
| `journeys/star_undo.yaml` | journeys, smoke | Star on Now (Now shows it as "Your next session"), My schedule lists it, unstar there, "Removed from My schedule", Undo brings it back |
| `journeys/my_schedule_overlap.yaml` | journeys | Two saved sessions that overlap: each row on My schedule says which one it overlaps |
| `journeys/search_any_day.yaml` | journeys | From Friday's Schedule, search finds a Saturday session, its speaker and a room used only on Saturday; Back keeps the query and the scope |
| `journeys/filter_persists.yaml` | journeys | Hide AI: the Schedule says "Hidden: AI, Open space", the AI talk is gone; after a relaunch it still is, and the sheet still has AI off |
| `journeys/jump_to_now.yaml` | journeys | The Schedule opens with the now slot at the top; after flings, Jump to now puts it back there |
| `journeys/sponsors_back.yaml` | journeys | More › Sponsors › a logo card's sponsor (Capital One) › Back: the list shows the same card again, and the sponsor's page is gone (SPON-01, #496) |
| `journeys/jobs_filter_back.yaml` | journeys | More › Job listings › filter "temporal" ("1 listing") › Temporal › Back: the same filter, count and card (SPON-06, SPON-07, #455) |
| `journeys/spotlight_back.yaml` | journeys | Now › the sponsor spotlight › the sponsor it names (read from the card, `scripts/spotlight_name.js`) › Back to Now (SHELL-08, #455) |
| `journeys/search_sponsor_back.yaml` | journeys | Now › search "bloomberg" › Bloomberg in Sponsors › Back: search keeps the query and the row (SPON-03, #455) |
| `journeys/sponsors_offline_logos.yaml` | offline_logos | Offline with no logo cache: Now's spotlight, Sponsors and Job listings say "Offline" and show initials; screenshots to look at ([below](#offline-logos), #455) |
| `journeys/sponsors_large_text.yaml` | large_text | The spotlight, Sponsors and Job listings journeys at the largest text, with no fresh start; a screenshot of each page to look at ([below](#large-text), #455) |
| `journeys/sponsor_find_booth.yaml` | journeys | A sponsor (Bloomberg) › Find booth 613 › Back: the expo hall opens at the booth with its card, and Back returns to the sponsor (SPON-04, #409) |
| `journeys/expo_list_card.yaml` | journeys, expo | More › Expo hall › List › "socal": SoCal Python's row alone; its tap shows booth 726 on the Map with its card, which lists 726's exhibitors; SoCal Python's page › Back: the hall again with the card (EXPO-03, EXPO-04, #454) |
| `journeys/expo_map_card.yaml` | journeys, expo | Map › Expo › booth 613 on the hall: its card with Sponsor details and Close; Close: the card goes, the hall stays (EXPO-01, EXPO-04, #454) |
| `journeys/job_fair_sponsor.yaml` | journeys, expo | Map › Job fair › Bloomberg's row (T2) › its page › Back: the pane with the row again (MAP-04, #454) |
| `journeys/search_booth_unplaced.yaml` | journeys, expo | Search "phemeral": "Booth 139 · Phemeral", "Not on the map yet"; its tap opens the expo's List under "Booth 139 isn't on the map yet", Phemeral in its section; Back keeps the query (EXPO-05, #406, #454) |
| `journeys/now_quick_back.yaml` | journeys | Now › each quick info button (Wi-Fi, Help & safety, Venue & hours) › Back: each page is pushed over Now, and Back returns to Now with the buttons (#419, D-338) |
| `journeys/wifi_copy.yaml` | journeys, venue | More › Wi-Fi shows the network and the password with the feed unreachable, and Copy password copies it: "Password copied" on iOS, no failure on Android, whose own overlay confirms a copy (INFO-08, #456) |
| `journeys/help_report.yaml` | journeys, venue | More › Help & safety opens on Report a concern, its email row and its Copy on screen before any scroll; Copy says "Email address copied" on iOS; the places and the Code of Conduct follow (INFO-07, #456) |
| `journeys/venue_open_now.yaml` | journeys, venue | On a conference morning (Friday 09:30, `NOW` overrides it) More › Venue & hours says Registration, the information desk and Swag pickup are open now, each until its closing time (MAP-09, #456) |
| `journeys/deep_links.yaml` | journeys, deep_links | Links land with the root below (D-291): cold, a session over the Schedule, Back to it; warm, an unknown speaker over Now, Back to Now; an unknown path, "This page isn't in the app", Back to Now; the filter sheet open when a link to Now comes closes, and Now shows. `LINK` sets the scheme and host ([below](#deep-links)) |
| `journeys/change_log.yaml` | feed_pair | P2 exit criterion 4's change log, from a served feed pair (#460): the old feed refreshed with no batch; session 123 saved; the pair swapped and refreshed: "1 saved session changed", Review, the saved move under "Affects My schedule" above "All changes" and the unsaved move (session 142), seen after 2 s on iOS, still new on Android until the list is left (a screen reader's rule, F72); My schedule's row and session detail show the change; Now has no Schedule changes card. Needs `tools.feed_pair` running ([below](#feed-pairs)) |
| `journeys/calendar_export.yaml` | journeys, calendar | Session detail's Add to calendar (session 25), then My schedule's Export to calendar (.ics) with two saved sessions, each through the system's screens and back to the app (`subflows/calendar_handoff.yaml`): iOS's calendar sheet, the one event with its Alert "10 minutes before", Add, Done, Close; Android's save dialog and "Saved <file>.ics. Open it from the Files app…" (D-272, #458) |
| `journeys/reminder_banner.yaml` | journeys, reminders | At Friday 14:38, saving a 2:45 PM session shows the Banner ("… starts in N min · Grand Ballroom B"); Back keeps it; Open lands on the session over My schedule and it goes; a second session's Banner goes with Dismiss; Settings' Reminders sentence, with the alarm on iOS only (D-60, D-272, #458) |
| `journeys/rail_tabs.yaml` | tablet | On a tablet or a phone in landscape (`ORIENTATION`): each tab root through the rail by its name, with no bar; a session pushed from Now and About this app pushed from More show no rail; the filter sheet and an Undo SnackBar on the way; a screenshot of each to look at (SHELL-14, D-277, D-305, #461) |
| `journeys/about_app.yaml` | journeys, tablet | More › About this app: Conference and Schedule's source and age (D-292); Licences › Python's text › Back › Back, one View each (D-296); Report a problem: the share sheet, dismissed with no line, or with `SHARE_FAILS=true` (an iPad, U95, #525) "Couldn't open the share sheet." (INFO-03, INFO-04, #461) |
| `regression/fling_after_sheet.yaml` | regression | Open space shown through the sheet, then a fling 0.8 to 1.0 s after "Show N sessions" (Maestro's pace, not #346's row D window), `TRIALS` times (at most about 35). Three control flings with no sheet first; each trial is "moved" (it ended within three rows of where a control ended, read from the first four rows of each; not merely in their slot), "short", "none" or "invalid" |

Every flow starts from `subflows/start_offline.yaml`: a fresh launch (`clearState`),
airplane mode on Android, Get started on the first-run Welcome (D-287), then Developer
options set as `tests/ui/developer.py` does
(More › About this app › the version row 7 times › Developer options): a fake clock at
**Friday 2026-05-15 14:10** (the busiest day, during the 2:00 PM slot) and a feed URL
nothing answers at, then Refresh now must say "Couldn't refresh: no answer from the feed". `NOW` and
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

Animations stay on: Maestro waits for them (`waitForAnimationToEnd`), and #346's fling
after the sheet needs the sheet's exit animation. When you are done, kill the emulator
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

**Comparing two builds** (the fling after the sheet, at Maestro's pace): install `main`'s
APK, run the regression flow, install the PR's APK, run it again with the same `TRIALS`,
and compare the two summaries (`flings after the sheet, N moved, N short, N none, N
invalid, of N`). First the flow runs three control flings with no sheet just before them
and keeps the first four rows each one stopped on; it fails at once unless they are near
each other (of any two, one's top row is among the other's rows: no more than three rows
apart). A trial "moved" only when it is near a control in the same way, from its own
first four rows: a full fling varies by a row or two, and the 3:00 PM slot, where it
ends, is about 20 rows deep with Open space shown, so a fling cut short by many rows can
still end in that slot. The flow
fails unless every trial moved and every tap reached the button. It starts the fake
clock at 14:01, so the now slot stays 2:00 PM for about 35 trials. On Android the
launcher logs every touch, so the time from the tap on "Show N sessions" to the fling is
`adb -s emulator-5570 logcat -d | grep TaplEvents`: the `ACTION_UP` at (540, 2232), then
the `ACTION_DOWN` at (540, 1800), by `eventTime` (ms).

### Row D through adb

#346's row D lost flings 0.33 to 0.6 s after the tap, sooner than Maestro can follow
one command with another. `tools/fling_after_sheet.py` reaches that window on an Android
emulator: it sends the tap and the fling in one `adb shell` command (`input tap`, then
`input swipe` after `--gap` seconds), reads the time between them from the launcher's
`TaplEvents` log, and judges each trial by the flow's rules (three controls, then
"moved" only within three rows of one). It runs `subflows/fling_setup.yaml` with the local
Maestro CLI first (a fresh, offline start at Friday 14:01, on the Schedule), reads the
screen with `uiautomator dump`, and turns airplane mode off at the end. Like the flow, it
refuses to run unless the Schedule starts on the now slot, 2:00 PM, `--no-setup` included.
A trial whose measured gap is missing or outside row D's window, 330 to 600 ms, is "off
window" whatever the fling did: it says nothing about row D and fails the run, and its
gap still shows in the summary. The rules are in `tools/fling_trials.py`.

```bash
uv run python -m tools.fling_after_sheet --serial emulator-5570 --trials 20
```

The default `--gap 0.5` puts the fling about 0.5 s after the tap (`input` adds about
30 ms), inside row D's window. Much sooner, the sheet is still leaving and the fling does
not scroll on any build: #346 saw that at 0.2 to 0.3 s, and on a busy host it lasts
longer. Each trial prints its kind and its measured gap; the summary
gives the counts and every measured gap's range and median, and the exit status is 1
unless every trial moved inside the window and every tap reached the button. Compare builds as with the flow: the same
`--trials` on each, one right after the other, on a quiet host.

### Deep links

`journeys/deep_links.yaml` opens each link through `subflows/open_link.yaml`, which joins
`LINK` (the scheme and host) and the route path. With no `LINK` it uses `pyconus://app`,
which must equal `[tool.flet.deep_linking]` in `pyproject.toml` (D-269):
`tests/test_deep_link_flow.py` checks it, so when O-4 (#15) renames the scheme the check
fails, not the flow. To try a build with other values before that default changes, give
them: `maestro --device <id> test -e LINK=<scheme>://<host> maestro/journeys/deep_links.yaml`.
A simulator asks "Open in …?" before the first link it opens (F31); the subflow taps
Open when it shows.

### Offline logos

`journeys/sponsors_offline_logos.yaml` checks that a fresh install with no network draws
each sponsor's initials on its logo tile. The initials are drawn, not said (the name is
said beside them), so no step can find them: the flow takes a screenshot of Now's
spotlight, the Sponsors list (its top and its logo cards) and Job listings, in the run's
`takeScreenshot/` folder (under `--test-output-dir`), and you look at them. On Android airplane mode does it. On
iOS the simulator shares the Mac's network, so the app first refreshes from the year's
snapshot with every logo pointed at a closed port, served from the Mac, then from a feed
URL nothing answers at:

```bash
mkdir -p build/no-logo-feed
sed -E 's#https://(pycon-assets\.s3\.amazonaws\.com|s3\.dualstack\.us-east-2\.amazonaws\.com)/#http://127.0.0.1:9/#g' \
  src/pycon_us/data/2026/conference.json > build/no-logo-feed/conference-2026.json
python3 -m http.server 8766 --bind 127.0.0.1 --directory build/no-logo-feed &
maestro --device <udid> test --test-output-dir build/maestro/offline-logos \
  maestro/journeys/sponsors_offline_logos.yaml
```

Its tag is `offline_logos`, not `journeys`, since on iOS it needs that server. `NO_LOGO_URL` names another URL for it. Without the server, the first refresh fails and
the flow stops there.

### Large text

A fresh start goes through Developer options, which were made for the default text size
and which the largest text pushes far below the fold (at first, About this app's version
row and Apply). So `journeys/sponsors_large_text.yaml` (tag `large_text`) starts from the data the last flow
left (no `clearState`): run a journey at the default size, set the largest text, then
run it. It walks the spotlight, Sponsors and Job listings journeys with their Backs, and
takes a screenshot of each page to look at for clipping and overlap (ux.md §9). The
relaunch may show the bundled snapshot rather than the scene's feed, whose time the
fake clock set in May, so logos may load.

```bash
# iOS: Bold Text is Settings › Accessibility › Display & Text Size › Bold Text.
xcrun simctl ui <udid> content_size accessibility-extra-extra-extra-large   # or accessibility-large, about 200 %
# Android: adb -s emulator-5570 shell settings put system font_scale 2.0
maestro --device <udid> test --test-output-dir build/maestro/large-text maestro/journeys/sponsors_large_text.yaml
```

### Feed pairs

`journeys/change_log.yaml` reads its feeds from the laptop: the recorded 2026 feed, then
a copy with sessions 123 (saved) and 142 (not saved) moved, at one feed URL (D-255;
[`docs/testing-and-quality.md`](../docs/testing-and-quality.md) §9.2). Start the server
first and keep it running; the flow resets it to the old feed at its start and swaps it
with a script (`scripts/feed_pair.js`), which posts to it from the laptop:

```bash
uv run python -m tools.feed_pair --move 123 "Room 103ABC" --move 142 "Room 101B"
maestro --device <udid> test maestro/journeys/change_log.yaml
```

Both `--move` edits are needed: without session 142's, the flow fails at its first
"All changes" check. On Android, Maestro makes the app see a screen reader (F72), so the
list runs no 2 s timer and marks its items seen when it is left (ux.md §6.4): the flow
asserts the item still reads "New: " there, and Now's missing card shows it seen.

Its tag is `feed_pair`, not `journeys`, so `--include-tags=journeys` runs without the
server. It turns no airplane mode on: that would cut the emulator's way to the laptop too.
`FEED_URL` (the feed as the device reaches it: `10.0.2.2` on the Android emulator,
`127.0.0.1` on the simulator) and `CONTROL_URL` (the server as the laptop reaches it)
default to port 8460, the server's; for another `--port`, give both, as the server
prints them. Its screenshots, one per step (`change_log-01-old-feed` …), go to the
debug output's folder.

## Writing a flow

- Find a control by its identifier, `id:` (`<screen>.<element>[.<key>]`, D-33), copied
  from `maestro hierarchy` (Android: `resource-id`; iOS: the element's id, F72). Never
  guess one. Text comes second, as the full string: Maestro's `text:` is a regular
  expression that must match the whole label, so escape `.`, `?` and `(`.
- A control with no identifier gets one in `src`, the smallest change (as `app.search`,
  D-252). The app bar's back arrow has none: use `subflows/back.yaml`, the system Back on
  Android and the button named "Back" on iOS.
- A tab goes through `subflows/tab.yaml` (`TAB: more`, `NAME: "More.*Tab 5 of 5"`):
  the bar's `app.nav.<tab>` on a phone, the destination's name on a tablet's rail,
  which has no identifiers (D-277, #163). The shared subflows and the venue flows use
  it, so they run on an iPad too; the older journeys still tap `app.nav.*`.
- After typing, `pressKey: Enter` closes the keyboard. On Android a Back would only close
  Gboard's bar, which comes back while the field keeps the focus.
- `subflows/top_slot.yaml` reads the Schedule's top row and its start time, which is how
  a flow tells where a list rests.
- **On Android, Maestro makes the app think a screen reader is on** (F72): Flutter reports
  `accessible_navigation` once anything reads its accessibility tree. The app then keeps
  the Schedule's Now button on the now slot, and by D-184 keeps SnackBars until they are
  used, as it does for TalkBack. Check those behaviours on iOS only (`jump_to_now` checks
  the button there; no flow checks a SnackBar's timeout yet).
- About 0.85 s passes between two Maestro commands on the emulator (0.8 s on the
  simulator), so a step can never follow the last one faster. #346 saw its failures with
  0.33 to 0.6 s between the tap and the fling, which Maestro cannot reach: that window is
  the `adb` driver's ([Row D through adb](#row-d-through-adb)).
- Each flow that runs `start_offline.yaml` turns the network back on in its
  `onFlowComplete` (`subflows/online.yaml`).
- Open a Map pane with `subflows/map_tab.yaml` (`env: TAB: expo`): the tab bar scrolls
  (D-312), and at the largest text only Rooms and Floor plans fit a phone, so it swipes
  the bar until the tab shows.
- The expo opens on the List under a screen reader and on the Map otherwise
  (`view_of()`), and Maestro makes Android report one (F72): a flow that needs one view
  taps its segment (`expo.view.map`, `expo.view.list`) when that view isn't showing.

## Calendar and reminders (#458)

On an iPhone 17 simulator (iOS 26.5) with an `ios-simulator` build of `main` at
`e5f2e0a` (Flet pin `15854a0ac`), on 2026-10-27, at iOS's `accessibility-large` text
size (about 200 %): `calendar_export` passed in 2 min 36 s and `reminder_banner` in
2 min 35 s, on a freshly erased simulator. What landed in the simulator's calendar was
read from its store (`data/Library/Calendar/Calendar.sqlitedb`): both events at their
UTC times (21:45 and 21:00 on May 15), each with its `UID` (`2026-<key>@…`) and an alarm
600 s before. A second run on the same simulator finds the events already there: iOS
then shows "Delete Event" (one event) or "Add (1)" (some added), and the subflow taps
Add only when it shows. At 200 % text, Developer options' rows sit below the fold, so
`open_developer.yaml` and `set_scene.yaml` scroll to each row before they tap it.
The Android half runs later (#458).

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

After P2 (#496, on 2026-10-21, `main` at `6979c0b`): every journey stopped at the launch,
because a fresh install now opens Welcome (D-287) and Refresh now's failure line was
reworded. `launch_fresh.yaml` taps Get started (`welcome.start`) until Now shows, and
`start_offline.yaml` expects the new words (#496 and #518 made the same fix). Then, on an iPhone 17 simulator (iOS 26.5), at a
load average of 40 to 300: the six journeys passed (1 min 27 s to 1 min 50 s each), and
`sponsors_back` passed.

Earlier versions of the flows failed twice on iOS while the host's load average was 400
to 700: Developer's feed URL lost two characters as it was typed (F63), and the overlap
flow's star tap landed while the Schedule was still jumping to now. Both are handled now
(a field is typed until it holds the whole value; the star waits for the jump, then is
tapped again if it stayed off). At that load the regression flow also lost a fling on
`main`, with 1.3 to 3.5 s between the tap and the fling: a busy host stretches the
sheet's exit past the fling. Compare builds only on a quiet host, one right after the
other.

`deep_links` (#518), on 2026-10-21 at a load average of 100 to 500: passed on an iPhone 17
simulator (iOS 26.5), the first link through "Open in …?". Not yet run on Android: the
emulator did not finish booting at that load. By then `main` had the first-run Welcome
(#504) and Developer's new refresh wording, which `launch_fresh.yaml` and
`start_offline.yaml` now expect, so every journey starts again.

#346's row D failed with 0.33 to 0.6 s between the tap and the fling. Both builds ran
every fling in full at about 0.85 s, the soonest Maestro gets there, so this flow does
not reach that window: it guards the fling at Maestro's pace only. The rows above were
judged by the slot alone, the rule before #484's review; the flow now judges by rows.
With rows, on #348's build (`f5785bb`) on Android: `TRIALS=5`, 5 moved, 4 min 52 s, at
a load average under 3. An earlier run, at a load average of 370, counted one fling as
short: it had stopped two rows past the rest, in the 12:30 PM slot.

**Row D through `adb`** (`tools/fling_after_sheet.py`), on the same emulator later on
2026-10-20, with the host's load average between 2 and 40 except where noted. The time
is measured on the device, from the tap's `ACTION_UP` to the fling's `ACTION_DOWN`:

| Build | `--gap 0.5`, 20 trials | `--gap 0.36`, 15 trials |
|---|---|---|
| `main` (`1a2c2b5`) | 18 moved, 1 short, 1 none; 512-666 ms (median 520) | 15 moved; 372-381 ms (median 374) |
| #346's (`7ccd74f`) | 18 moved, 2 none; 520-742 ms (median 531) | 15 moved; 372-383 ms (median 378) |

Every lost fling, on both builds, came with a slow injection (648 to 742 ms instead of
about 525) during a spike of the host's load; at a steady gap every fling ran in full on
both. These runs were counted before #484's review added the window rule: those lost
flings (and any other trial past 600 ms) fell outside row D's window, so the driver now
counts them "off window", not "short" or "none". A first #346 run stopped before its trials when one of its controls was cut short
at a load average of 550. So on this host the driver reaches row D's window, but has
not yet told #346's build from `main`: #346 lost 11 of 33 there in its own matrix. Run
both builds again, on a quiet host and with more trials, before trusting either way.
The flow and the driver read the same rest and controls on each build: `main` rests on
12:30 PM and its flings end in 3:00 PM; #346's build keeps the 2:00 PM slot, and its
flings end in 4:00 PM.

**#455** (2026-10-27, `main` at `e5f2e0a`, Flet pin `15854a0ac`), an `ios-simulator`
build on an iPhone 17 simulator (iOS 26.5), at a load average of 90 to 130:
`sponsors_back`, `jobs_filter_back`, `spotlight_back` and `search_sponsor_back` passed
(1 min 29 s to 1 min 38 s each); `sponsors_offline_logos` passed, every tile showing
initials; `sponsors_large_text` passed with Bold Text at `accessibility-large` and at
`accessibility-extra-extra-extra-large`. A second scene in one flow first failed:
Developer's feed URL kept its old tail, since the tap put the caret mid-URL, so
`set_scene.yaml` now taps and erases twice. Not yet run on Android.

**The expo flows (#454)**, on 2026-10-27, `main` at `e5f2e0a`, an `ios-simulator`
build on an iPhone 17 simulator (iOS 26.5): the four `expo` journeys passed (1 min 24 s
to 1 min 47 s each, 6 min 7 s in all). Not yet run on Android (#454's Android sweep).

## Tablets and landscape (#461)

`rail_tabs` and `about_app` (tag `tablet`) run on a tablet in both orientations and on
a phone in landscape. `ORIENTATION=LANDSCAPE` turns the device a quarter turn from its
natural orientation first (`subflows/orientation.yaml`); without it the device is put
back in its natural one. On the Pixel Tablet AVD (`pycon_tablet_api36`,
[`docs/development.md`](../docs/development.md) §5.5) the natural orientation is
landscape, so there `ORIENTATION=LANDSCAPE` is portrait. `rail_tabs` asserts that no
bar shows on a tab root, so it fails on a phone in portrait by design.

```bash
# Android: the tablet AVD (read-only after its first boot), then the Pixel 6a turned.
~/Library/Android/sdk/emulator/emulator -avd pycon_tablet_api36 -read-only -no-audio -no-boot-anim -port 5578 &
adb -s emulator-5578 install -r build/apk/pycon-us.apk
maestro --device emulator-5578 test --include-tags=tablet maestro                         # landscape
maestro --device emulator-5578 test -e ORIENTATION=LANDSCAPE --include-tags=tablet maestro  # portrait
adb -s emulator-5578 shell cmd uimode night yes   # dark; `no` for light

# iOS: an iPad of your own, where the sheet cannot open at this pin (U95), so
# SHARE_FAILS=true expects about_app's failure line; then an iPhone 17 in landscape.
xcrun simctl create "<issue>-ipadpro11" "iPad Pro 11-inch (M5)" com.apple.CoreSimulator.SimRuntime.iOS-26-5
maestro --device <udid> test -e SHARE_FAILS=true --include-tags=tablet maestro
maestro --device <udid> test -e SHARE_FAILS=true -e ORIENTATION=LANDSCAPE --include-tags=tablet maestro
maestro --device <iphone-udid> test -e ORIENTATION=LANDSCAPE --include-tags=tablet maestro
xcrun simctl ui <udid> appearance dark   # or light
```

Each step's screenshot (`rail-01-now` … `about-04-share`) lands in the run's
`takeScreenshot/` folder under `--test-output-dir`: look at them for the rail, the
content widths (D-305) and the sheets. Android saves them as shown; iOS saves a
landscape screen in portrait, so turn it a quarter clockwise to read it.

What the flows met on the way, now handled in the shared subflows:
- On an iPad in landscape the keyboard covers the middle of the screen, where a scroll
  swipes: `set_scene.yaml` closes it after the fake clock, or the feed URL stayed out
  of sight.
- On a phone in landscape About this app's version row is below the fold:
  `open_developer.yaml` waits for the push (More's row gone), then scrolls.
- On an iPad in landscape Report a problem rests on the list's end, and the line under
  it comes in below the fold: with `SHARE_FAILS=true`, `about_app` scrolls to it.
- Each run says which outcome it expects (`SHARE_FAILS`), so a share error where the
  sheet should open fails: elsewhere the flow waits for the sheet itself (Android's
  chooser list, `resolver_list`; iOS's `ShareSheet.RemoteContainerView`), and after
  the dismissal checks at the list's end that no outcome line came (D-297).
- iOS 26's share sheet lies over a dismiss region (`PopoverDismissRegion`) in both
  orientations; `subflows/dismiss_share.yaml` taps it on the right, since a tap near the
  left edge of an iPhone in landscape left the sheet open.

**Results** (2026-10-27, `main` at `e0f3c1f` plus these flows, Flet pin `15854a0ac`,
load averages 2 to 16):

| Device | Run | Result |
|---|---|---|
| iPad Pro 11-inch (M5), iOS 26.5, `ios-simulator` build | `tablet`, portrait and landscape, light | 2 of 2 passed each (4 min 25 s, 5 min 6 s) |
| same | `rail_tabs`, portrait and landscape, dark | passed |
| iPhone 17, iOS 26.5 | `tablet` in landscape; `about_app` in portrait | passed (7 min 13 s for the pair) |
| `pycon_tablet_api36`, Android 16, release APK (arm64) | `tablet`, landscape and portrait, light | 2 of 2 passed each (7 min 20 s, 6 min 18 s) |
| same | `rail_tabs`, landscape, dark | passed |
| same | `rail_tabs`, portrait, dark | stopped twice in `set_scene.yaml` while erasing the feed URL (the caret sat at the field's start, and Maestro's erase never returned), at a load average of 15; the dark portrait screenshots were taken by hand |
| `pycon_pixel6a_api36`, Android 16, release APK | `tablet` in landscape | 2 of 2 passed, 7 min 37 s; More, at the short rail's bottom edge, is reached through `tab.yaml` |

## Offline on a fresh iOS install

Maestro cannot cut a simulator's network, so the launch's refresh reaches the year's
feed. To see a fresh install start from the bundled data alone, give it Developer's
feed URL before its first launch: SharedPreferences are the app container's own
`NSUserDefaults` (`flutter.` + the key), not the simulator's global domain.

```bash
xcrun simctl install <udid> build/ios-simulator/pycon-us.app
data=$(xcrun simctl get_app_container <udid> io.github.ndonkohenri.pyconus data)
xcrun simctl spawn <udid> defaults write "$data/Library/Preferences/io.github.ndonkohenri.pyconus" \
  flutter.pycon.dev -string '{"feed_url": "http://127.0.0.1:9/conference-2026.json"}'
```

Then launch it without `clearState` (which would drop the value): its refresh finds no
feed, and Settings › Refresh now says "Bundled with the app" (#454).

## Venue pages (#456)

The three `venue` flows, on 2026-10-27, `main` at `e5f2e0a` plus the flows, an
`ios-simulator` build whose bundle matched `build/python-app`, Flet pin `15854a0ac`, at
load averages of 15 to 730:

| Device | Run | Result |
|---|---|---|
| iPhone 17, iOS 26.5 | `--include-tags=venue` | 3 of 3 passed, 4 min 12 s; `xcrun simctl pbpaste` gave the password |
| iPad Air 11-inch (M4), iOS 26.5 (the rail) | `--include-tags=venue` | 3 of 3 passed, 5 min 9 s, through `tab.yaml`; `pbpaste` gave the password |
| Android | not run yet | the Android sweep runs them, TalkBack and airplane mode included |

At 200 % text (iOS's Larger Text at `accessibility-large`) the flows cannot start:
Developer options' rows (`about_app.developer`, `developer.apply`) are below the fold,
and the shared subflows tap them without a scroll. The pages were checked at 200 % in
an app the flows had set up, after the text size changed: nothing clips, Report a
concern stays first, and both copies are confirmed; the email address breaks inside
`python.org` (#642).

A simulator cannot be put in airplane mode, so on iOS the launch's own refresh may
reach the year's live feed before Developer points the app at a feed that never
answers; a cold start with no network is checked on Android. The three pages need no
feed: they are bundled year data (`content.toml`).
