# Maestro flows

Device flows for the packaged app (`io.github.ndonkohenri.confcompanion`), run with the free,
local [Maestro](https://maestro.dev) CLI on an Android emulator and an iOS simulator,
from one set of YAML files (D-252, #348). They check P1's exit journeys (PLAN §7,
criteria 1 and 2) and repeat regression trials such as #346's fling after the filter
sheet. Where Maestro fits next to the `flet test` flows in `tests/ui/` is in
[`docs/testing-and-quality.md`](../docs/testing-and-quality.md) §5.5.

**Free only.** Use the local CLI (and its MCP tools, if you like). Never Maestro Cloud,
`maestro cloud`, `maestro login` or a paid plan.

## What is here

| Path | What it is |
|---|---|
| `config.yaml` | The workspace: `maestro test maestro` runs `journeys/*` and `regression/*` |
| `journeys/` | P1's exit journeys and later screens' journeys, tagged `journeys` (two also `smoke`) |
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
| `journeys/find_room.yaml` | journeys, venue, map | Offline (bundled `map.toml`), Map › Rooms › Room 103ABC › its location card › the Concourse plan, its image named "…, Room 103 marked" and the room's label, Zoom in enabling Zoom out › Back › Back to Rooms; Floor plans › Concourse (no label) › Zoom in › Back (P2-93's find a room, one of the exit's three screen-reader flows, #462, #453) |
| `journeys/room_from_search.yaml` | journeys, venue, map | Offline, Map › Search, on Places, "104C" › Room 104C › its location card › the Concourse plan, "…, Room 104C marked" and its label › Back (the room) › Back (search, with "104C" and the row) › Back (the Map) (P2-93, #453) |
| `journeys/session_room_plan.yaml` | journeys, venue, map | Offline, Now › the panel (session 123, Grand Ballroom B) › its location card "Show Grand Ballroom B on the Upper level floor plan" › the plan, "…, Grand Ballroom B marked", Zoom in enabling Zoom out › Back to the session and its card (P2-93, #453) |
| `journeys/deep_links.yaml` | journeys, deep_links | Links land with the root below (D-291): cold, a session over the Schedule, Back to it; warm, an unknown speaker over Now, Back to Now; an unknown path, "This page isn't in the app", Back to Now; the filter sheet open when a link to Now comes closes, and Now shows. `LINK` sets the scheme and host ([below](#deep-links)) |
| `journeys/change_log.yaml` | feed_pair | P2 exit criterion 4's change log, from a served feed pair (#460): the old feed refreshed with no batch; session 123 saved; the pair swapped and refreshed: "1 saved session changed", Review, the saved move under "Affects My schedule" above "All changes" and the unsaved move (session 142), seen after 2 s on iOS, still new on Android until the list is left (a screen reader's rule, F72); My schedule's row and session detail show the change; Now has no Schedule changes card. Needs `tools.feed_pair` running ([below](#feed-pairs)) |
| `journeys/calendar_export.yaml` | journeys, calendar | Session detail's Add to calendar (session 25), then My schedule's Export to calendar (.ics) with two saved sessions, each through the system's screens and back to the app (`subflows/calendar_handoff.yaml`): iOS's calendar sheet, the one event with its Alert "10 minutes before", Add, Done, Close; Android's save dialog and "Saved <file>.ics. Open it from the Files app…" (D-272, #458) |
| `journeys/reminder_banner.yaml` | journeys, reminders | At Friday 14:38, saving a 2:45 PM session shows the Banner ("… starts in N min · Grand Ballroom B"); Back keeps it; Open lands on the session over My schedule and it goes; a second session's Banner goes with Dismiss (D-60, D-396, #458) |
| `journeys/reminder_settings.yaml` | journeys, reminders | More › Settings › Reminders in a packaged build: session reminders off; on, the lead at 10, then 15, and on Android the Alarms & reminders card (never on iOS); after a relaunch still on at 15; My schedule › More options › Reminder settings opens Settings, and Back returns to My schedule; then off again (NOTIF-01, STORE-10, D-401, #449) |
| `journeys/reminder_primer.yaml` | journeys, reminders | A fresh install launched with notifications `unset`: nothing asked at launch or on Welcome; the first star (Now, session 123) shows the reminders primer, which `PRIMER` answers (`allow` or `not_now`), then the OS prompt, which `OS_ANSWER` answers (`allow` or `deny`); the session stays saved, and a second star (Schedule, 30) shows no primer (D-61, D-395, #448). The other flows launch with every permission granted (`subflows/launch_fresh.yaml`), so no primer shows there on Android; on iOS it does ([below](#the-reminders-primer-on-ios)) |
| `journeys/rail_tabs.yaml` | tablet | On a tablet or a phone in landscape (`ORIENTATION`): each tab root through the rail by its name, with no bar; a session pushed from Now and About this app pushed from More show no rail; the filter sheet and an Undo SnackBar on the way; a screenshot of each to look at (SHELL-14, D-277, D-305, #461) |
| `journeys/about_app.yaml` | journeys, tablet | More › About this app: Conference and Schedule's source and age (D-292); Licences › Python's text › Back › Back, one View each (D-296); Report a problem: the share sheet, dismissed with no line, or with `SHARE_FAILS=true` "Couldn't open the share sheet." (an iPad needed it until the pin `08b89cce5`, F115, F263) (INFO-03, INFO-04, #461) |
| `journeys/theme_relaunch.yaml` | journeys, theme | More › Settings starts on System with High contrast following the device ("Follows your device setting", off); Dark and High contrast on; after a relaunch Dark is still chosen and the switch on with no subtitle; then High contrast off (following the device again) and System, so a second run starts the same way. The rows' states are read each platform's way (`subflows/theme_state.yaml`): Android's `checked`, iOS's `selected` radio rows and the switch's value "1" or "0" (THEME-01, STORE-08, D-286, #512) |
| `journeys/coc_capture.yaml` | staff, coc | Against the local mock ([below](#staff-flows-and-the-mock)) as `coc@example.com`: a typed badge code, the review, Record, "Incident recorded"; the line counts down and the result clears 15 s after it shows; Find by name, Record, Show email reveals `margaret@example.com`; Home and back: the result and the email are gone (MASK-05, #762). Needs the mock running; `--exclude-tags staff` leaves it out of a run without one |
| `journeys/lead_capture.yaml` | staff, lead | Against the local mock as `sponsor@example.com`: sign-in lands on the scanner's consent page, Continue disabled until the box is ticked; a typed code and a HID-style one, "Lead captured" with Add note, "Leads (2)"; the first again past the cooldown, "Already in your leads" with Open lead; "Not a badge code", the text kept; Back and in again, no consent page (LEAD-01, LEAD-04, #825). Needs the mock running |
| `journeys/door_check.yaml` | staff, door | Against the local mock as `staff@example.com`: the picker opens by itself, Tutorials › All about decorators, "Ready, works offline", 2 attendees; a typed code and a HID-style one, "Checked in" with the dietary chip and "Admits 2", "2 checked in"; the first again past the cooldown, "Already checked in", the count unchanged; off the list, "Not registered for this session"; "Not a badge code", the text kept; "All synced" (DOOR-04, #825). Needs the mock running |
| `journeys/swag_pickup.yaml` | staff, swag | Against the local mock as `staff@example.com`: paused until a category is chosen; a typed code opens the hand-out sheet, Cancel, "Ready to hand out"; a HID-style code, on a mock that hasn't seen the flow, "Hand out 3 items", "Handed out 3 items"; that badge again, "Already picked up"; nothing bought, "Nothing to pick up"; "Not a badge code", the text kept (SHIRT-02, #825). Needs the mock running, just started to check the hand-out |
| `regression/fling_after_sheet.yaml` | regression | Open space shown through the sheet, then a fling 0.8 to 1.0 s after "Show N sessions" (Maestro's pace, not #346's row D window), `TRIALS` times (at most about 35). Three control flings with no sheet first; each trial is "moved" (it ended within three rows of where a control ended, read from the first four rows of each; not merely in their slot), "short", "none" or "invalid" |

Every flow but `theme_relaunch` and `reminder_settings` (which need no clock or feed, and start with `subflows/launch_fresh.yaml`), `reminder_primer` (which launches with notifications `unset`, then runs `subflows/get_started.yaml` and the same scene) and the `staff` flows ([below](#staff-flows-and-the-mock)) starts from `subflows/start_offline.yaml`: a fresh launch (`clearState`),
airplane mode on Android, Get started on the first-run Welcome (D-287), then Developer
options set as `tests/ui/developer.py` does
(More › About this app › the version row 7 times › Developer options): a fake clock at
**Friday 2026-05-15 14:10** (the busiest day, during the 2:00 PM slot) and a feed URL
nothing answers at, then Refresh now must say "Couldn't refresh: no answer from the feed". `NOW` and
`OFFLINE_URL` override them (`-e NOW="2026-05-16 10:00"`). On iOS Maestro cannot cut the
simulator's network, so the launch's own refresh may publish the year's live feed, which
lists the same sessions as the bundled snapshot. A cold start with no network is checked
on Android, or on iOS as [below](#offline-on-a-fresh-ios-install). The venue flows don't
mind: their pages are bundled year data (`content.toml`) and need no feed.

### The reminders primer on iOS

A fresh install's first star shows the reminders primer while the OS can still ask
(D-395). `launchApp`'s grant of every permission covers notifications on Android, so
there it never shows. On the iOS simulator Maestro grants through its pinned
`applesimutils` (`~/.maestro/deps/`), and `xcrun simctl privacy` has no notifications
service; neither reaches notifications on iOS 26.5, so the app can still ask and the
primer covers the screen after the first star (#710). So every flow that stars a
session runs `subflows/primer_not_now.yaml` right after its first star: on iOS only, it
waits for the primer and answers Not now, which asks the OS nothing and leaves session
reminders off, the state Android starts in. It waits on the platform rather than on the
sheet being visible, since the sheet opens after an async status read that a "tap it if
it shows" step could look before. `reminder_primer.yaml` launches with notifications
`unset` and tests the primer itself, so it never runs the step. If a later Maestro
grants notifications on iOS, the step fails at its wait, which says it can go.

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

A journey takes one to two minutes on a quiet host, most of it the fresh start in
Developer options, and up to about three on a busy one. On a very busy host the XCTest
driver may not start in time, and an iOS run stops before any flow:
`MAESTRO_DRIVER_STARTUP_TIMEOUT=240000` (ms) gives it the time. Results go on the phase's
status issue and the PR, not here.

Maestro does not drive a screen reader: for TalkBack, see
[`docs/testing-and-quality.md`](../docs/testing-and-quality.md) §7.3.

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
the `ACTION_DOWN` at (540, 1800), by `eventTime` (ms). Compare builds only on a quiet
host, one right after the other: a busy host stretches the sheet's exit past the fling,
and `main` loses flings too.

### Deep links

`journeys/deep_links.yaml` opens each link through `subflows/open_link.yaml`, which joins
`LINK` (the scheme and host) and the route path. With no `LINK` it uses `confcompanion://app`,
which must equal `[tool.flet.deep_linking]` in `pyproject.toml` (D-269):
`tests/test_deep_link_flow.py` checks it, so if the scheme is renamed (D-452) the check
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

At iOS's `accessibility-large`, about 200 %, a fresh start does work:
`open_developer.yaml` and `set_scene.yaml` scroll to each row before they tap it. At
`accessibility-extra-extra-extra-large` the flows still cannot set their scene, so a
flow's pages are walked there after a run at the default size.

```bash
# iOS: Bold Text is Settings › Accessibility › Display & Text Size › Bold Text.
xcrun simctl ui <udid> content_size accessibility-extra-extra-extra-large   # or accessibility-large, about 200 %
# Android: adb -s emulator-5570 shell settings put system font_scale 2.0
maestro --device <udid> test --test-output-dir build/maestro/large-text maestro/journeys/sponsors_large_text.yaml
```

### Calendar

A second run of `calendar_export` on the same simulator finds the events already there:
iOS then shows "Delete Event" (one event) or "Add (1)" (some added), and
`subflows/calendar_handoff.yaml` taps Add only when it shows. To see what landed, read the
simulator's calendar store,
`~/Library/Developer/CoreSimulator/Devices/<udid>/data/Library/Calendar/Calendar.sqlitedb`:
each event has its UTC time, its `UID` (`2026-<key>@…`) and an alarm 600 s before.

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

### Staff flows and the mock

The flows tagged `staff` drive the staff tools against the local mock
([`docs/development.md`](../docs/development.md) §6), with its seed and fake data only.
Start it first and keep it running; a flow sets nothing up in it and needs no reset:

```bash
uv run python -m tools.mock_api.server
maestro --device <id> test --include-tags=staff maestro
```

Each flow runs `subflows/launch_fresh.yaml`, then `subflows/sign_in_mock.yaml`, which
sets Developer's Mock API URL and signs in with the flow's seed account
(`tests/fixtures/mock/seed.json`). The URL is `MOCK_URL`: by default port 8000 at
`10.0.2.2` on the Android emulator and at `localhost` on the simulator. For another
`--port`, give it: `-e MOCK_URL=http://10.0.2.2:8010`. The sign-in ends as its page goes,
and the flow waits for where the account lands: More, or a sponsor's Lead scanner (D-16).

The mock keeps what a run sends in memory until it restarts, and two devices on one mock
share it. `clearState` empties the app's own rows, so a rerun starts from an empty outbox
against a mock that remembers:

| Flow | Account | What a run leaves in the mock | A rerun |
|---|---|---|---|
| `coc_capture` | `coc@example.com` | Two more incidents | Passes; the counts it doesn't assert grow |
| `lead_capture` | `sponsor@example.com` | Ada's and Grace's leads for Example Corp | The same: a repeated capture answers the same and adds no lead |
| `door_check` | `staff@example.com` | Product 10 redeemed for Ada and Linus | The same on screen: the door decides on the device, and the mock's "already redeemed" still syncs the row (D-441) |
| `swag_pickup` | `staff@example.com` | Ada's shirts and bag redeemed, for good; Grace's sheet is only cancelled | **Checks less:** Ada has nothing left, so she shows "Already picked up" at once and the hand-out is skipped |

So the hand-out is checked only on a mock that hasn't seen `swag_pickup` on any device.
To check it, restart the mock first and make it mandatory, so that a wrong "Already picked
up" fails instead of passing as a rerun:

```bash
maestro --device <id> test -e HAND_OUT=required --include-tags=staff maestro
```

Without the switch, the log tells which run you had, since a run with the hand-out has one
more `POST /2026/api/v1/check_in/redeem_products/` than `door_check`'s two. The log names
each endpoint, not the badge. A run of the four sends two
`mask_violations/capture` POSTs and two `lead_retrieval/capture` GETs, whatever the mock
remembers. These counts are at the default `--capture idempotent`, the one the flows have
run against.

Two subflows are the scanner's:

- `subflows/scan.yaml` sends `CODE`, then Enter, with no tap on the field, as a USB or
  Bluetooth HID scanner does: it fails if the screen lost the focus (F274). That is
  HID-style entry only: real hardware is the owner's (#121), and the camera waits on E1
  (#520). A flow's first scan on a screen taps `scan.keyboard` first, as a person typing.
- `subflows/past_cooldown.yaml` waits until the panel's age line reads at least 5 seconds.
  A code accepted in the last 4 s is cleared without a word, so a rescan any sooner shows
  nothing, and the wait would fail on the old result. A different code goes at once.

"Not a badge code" comes last in each flow, since its text stays in the field. Offline
scans use the dedicated F8 wrapper below.

`tests/test_staff_flows.py` checks the words and identifiers of `lead_capture`,
`door_check` and `swag_pickup` against the app's code and the mock's seed, so a rewording
fails under `tools/check.sh`. A new `text:` in those flows needs its words there too.

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
  0.33 to 0.6 s between the tap and the fling, which Maestro cannot reach.
- Each flow that runs `start_offline.yaml` turns the network back on in its
  `onFlowComplete` (`subflows/online.yaml`).
- Open a Map pane with `subflows/map_tab.yaml` (`env: TAB: expo`): the tab bar scrolls
  (D-312), and at the largest text only Rooms and Floor plans fit a phone, so it swipes
  the bar until the tab shows.
- The expo opens on the List under a screen reader and on the Map otherwise
  (`view_of()`), and Maestro makes Android report one (F72): a flow that needs one view
  taps its segment (`expo.view.map`, `expo.view.list`) when that view isn't showing.
- A busy host can lose keystrokes in a controlled field (F63): type in a `retry` until the
  field shows the whole value, as `set_scene.yaml` does. On iOS a tap can put the caret
  mid-field, so it taps and erases twice. A tap on a moving list only stops it: wait for
  the animation, and tap again if the state didn't change (`my_schedule_overlap.yaml`).

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

# iOS: an iPad of your own, where the sheet opens since the pin 08b89cce5 (F263; at
# 15854a0ac it needed SHARE_FAILS=true, F115); then an iPhone 17 in landscape.
xcrun simctl create "<issue>-ipadpro11" "iPad Pro 11-inch (M5)" com.apple.CoreSimulator.SimRuntime.iOS-26-5
maestro --device <udid> test --include-tags=tablet maestro
maestro --device <udid> test -e ORIENTATION=LANDSCAPE --include-tags=tablet maestro
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
  it comes in below the fold: with `SHARE_FAILS=true`, `about_app` scrolls to it. Since
  the pin `08b89cce5` an iPad opens the sheet (F263), so it runs without it.
- Each run says which outcome it expects (`SHARE_FAILS`), so a share error where the
  sheet should open fails: elsewhere the flow waits for the sheet itself (Android's
  chooser list, `resolver_list`; iOS's `ShareSheet.RemoteContainerView`), and after
  the dismissal checks at the list's end that no outcome line came (D-297).
- iOS 26's share sheet lies over a dismiss region (`PopoverDismissRegion`) in both
  orientations; `subflows/dismiss_share.yaml` taps it on the right, since a tap near the
  left edge of an iPhone in landscape left the sheet open.

## Offline on a fresh iOS install

Maestro cannot cut a simulator's network, so the launch's refresh reaches the year's
feed. To see a fresh install start from the bundled data alone, give it Developer's
feed URL before its first launch: SharedPreferences are the app container's own
`NSUserDefaults` (`flutter.` + the key), not the simulator's global domain.

```bash
xcrun simctl install <udid> build/ios-simulator/pycon-us.app
data=$(xcrun simctl get_app_container <udid> io.github.ndonkohenri.confcompanion data)
xcrun simctl spawn <udid> defaults write "$data/Library/Preferences/io.github.ndonkohenri.confcompanion" \
  flutter.pycon.dev -string '{"feed_url": "http://127.0.0.1:9/conference-2026.json"}'
```

Then launch it without `clearState` (which would drop the value): its refresh finds no
feed, and Settings › Refresh now says "Bundled with the app" (#454).

## Offline captures (F8)

Run `uv run python -m tools.offline_scans --device <id> --platform android` (or
`--platform ios`). Build and install the packaged app first. The wrapper owns mock
port 8470 and laptop-only control port 8471 (`--port`, `--control-port` override them).
Do not start another mock on those ports. It runs `journeys/offline_scans.yaml`, which
signs in, cuts the mock listener, scans two codes, checks both Queued rows, restores
the listener and uses Sync now, then checks both Confirmed rows. The wrapper retains
the mock state across the cut and checks exactly one capture per code for sponsor 1
(Example Corp), failing on duplicates even when the UI says Confirmed. It uses
non-idempotent capture semantics so duplicate requests cannot hide behind deduplication.
Both listeners close on success or failure. This is a host connection cut on both
platforms; real Android airplane mode and killing/relaunching with queued scans are
#827's separate checks. `now_next.yaml` completes F6 alongside `star_undo.yaml`;
`session_room_plan.yaml` is F7.
