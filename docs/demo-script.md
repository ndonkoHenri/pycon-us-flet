# Demo script

> **Draft until the UI freezes.** Every word on screen below comes from the code at `675172a7`, and none of this has
> been run from top to bottom yet: the timings are plans, not measurements. The freeze is noted on #855 once
> the UI is stable, and the recordings (#856) wait for it. Anything marked **Not tried** is unknown, not just unchecked.

The script for P4's exit 3 (`PLAN.md` §7): six beats on stage, with the laptop's Wi-Fi off. It answers the conflicts
with "no Wi-Fi" in D-463; the mock's place in it is D-457.

## At a glance

| # | Beat | Time | Device | What it needs | Fallback |
|---|---|---|---|---|---|
| 1 | Offline start | 0:45 | Simulator A | Nothing | Relaunch, then the spare, then a recording |
| 2 | Now and Next for me | 1:00 | Simulator A | The fake clock, the stars | Relaunch, then a recording |
| 3 | My schedule | 0:45 | Simulator A | The stars | Star two sessions live, then a recording |
| 4 | Live edit | 1:15 | Simulator B | `flet run` and the client on loopback | A recording |
| 5 | Staff scan | 1:45 | Simulator A | The mock on loopback | Restart the mock, then a recording |
| 6 | View source | 0:30 | Laptop browser | A page opened before Wi-Fi went off | The editor, or a recording |
| | **Total** | **6:00** | | | |

**The one rule on stage:** one retry, 20 seconds at most, then the fallback. Nobody debugs in front of the room.

**If you run late, cut in this order:** the Undo in beat 3, "Show room" in beat 2, the last two scans in beat 5, then
beat 6 down to a sentence. If you know beforehand that time is short, sign in during setup and drop beat 5's typing; Now
then shows its Scan badges card from the start.

## How each conflict with "no Wi-Fi" is settled (D-463)

| Conflict | Answer |
|---|---|
| **What counts as a run** | The laptop has no internet: its Wi-Fi is off (on the phone route, it serves only the hotspot), with no cable or tether. For exit 3, a run counts only if all six beats happen live; a beat that falls back to a recording fails that run. The page opened beforehand in beat 6 counts as live. |
| **The stage device** | Two iPhone simulators on the laptop, with an Android emulator as the spare. Beats 1 to 5 work on them over loopback, so the default rig needs no hotspot at all. A phone is an upgrade, taken only after it has been rehearsed ([below](#a-phone-instead-of-a-simulator-not-tried)). |
| **The staff scan** | The mock runs on the laptop (D-457). A simulator reaches it at `http://localhost:8000`, the emulator at `http://10.0.2.2:8000`. A phone joins a laptop hotspot, with the server on `--host 0.0.0.0`: **not tried.** |
| **The camera scan** | Manual entry until E1 (#520, #726), and the scan screen says so. A simulator has no camera anyway, so a camera scan on stage also means a phone. |
| **Live edit** | On a simulator over loopback only. A phone can't reach `localhost:8550`, and no 1.1 companion is in the stores (`development.md` §5.2, §10). |
| **View source** | Stage never opens GitHub from the app. The item is shown, not tapped, and the laptop's browser shows the same file from a page opened before the Wi-Fi went off. Fallbacks: the file in the editor, then a recording. |
| **O-8, an in-app backend** | Not reopened: no beat needs one. It reopens if the owner wants a demo with no laptop, or wants a phone on stage and the hotspot fails (D-457). |

## What has been tried

| Piece | Status |
|---|---|
| The whole script, top to bottom | **Not tried.** See the [dry run log](#dry-run-log). |
| The laptop's Wi-Fi off, for anything | **Not tried.** Earlier offline runs used airplane mode on the Android emulator, or a dead feed URL on the iOS simulator, whose network Maestro can't cut (`maestro/README.md`). |
| A cold start from bundled data | Tried: the journeys' `start_offline` subflow, and flow F1. |
| The fake clock on a conference day | Tried at Friday 14:10 by the journeys. **The 10:48 moment and these stars have only been computed:** `core/agenda.py` and `now_header.py` over the bundled snapshot, in Python, on 2026-11-02. |
| Overlaps; a star with Undo | Tried: `maestro/journeys/my_schedule_overlap.yaml`, `star_undo.yaml`. |
| The offline strip's words | Computed in Python with a refused connection, on 2026-11-02. Not seen on a device with the Wi-Fi off. |
| Hot reload in the companion client | Tried at `1.1.0.dev4` with the network on, on an iPhone 17 simulator, pressing `R` before each save because of U287 (#1038, #1044; `development.md` §5.2). **Not tried** at this version on an emulator, with the Wi-Fi off, or on a second simulator beside the packaged build. |
| The mock over loopback from a packaged build | Tried with the network on (#668, on both platforms). **Not tried** with the Wi-Fi off; `10.0.2.2` is the one most worth checking. |
| Door check, its words and its queue | The UI was tried at `08b89cce5` (#784), and #827 is the rerun at the current pin. The words below came from the real client and the real server over loopback, in a Python script with no UI, on 2026-11-02. |
| A phone on a laptop hotspot | **Never tried** (D-457). |
| View source | **Not built** (#834), and it needs the public repo (#835). |
| Any timing in this file | **Not measured.** |

## The rig

- **Simulator A:** an iPhone 17 on iOS 26.5, running the packaged build from `flet build ios-simulator`. Flutter has no
  release mode for simulators (D-102), so judge smoothness in the dry run.
- **Simulator B:** an iPhone 17 Pro on iOS 26.5, running the companion client from a Flet clone (`development.md` §5.2). Python runs on
  the laptop, so its font is the system's (D-26) and its capabilities are the interims (D-63). A second simulator
  means no app switch on stage, and a broken reload can't touch A.
- **The spare:** the AVD `pycon_pixel6a_api36` with a release APK, set up as A is, with `http://10.0.2.2:8000` as the
  mock's URL. Run it only if the laptop stays smooth with it up, and bring its window to the front before using it:
  an emulator behind other windows can run slowly.
- **Terminals:** T1 the mock, T2 `flet run`, T3 `flutter run`.
- **Editor:** `src/pycon_us/screens/now_card.py` and `now.py`, open in tabs.
- **Browser:** the page for beat 6, in a window of its own.
- **Recordings:** one per beat, reachable offline on the laptop. #856 owns them and picks their home. Until then the
  only one is the P1 slice (`pr-assets/14/demo-slice.mp4`, at an old pin), which would have to be downloaded first and
  covers parts of beats 1 to 3.

## Before the talk

The order matters: what needs a network comes first, and the app's first launch comes after the Wi-Fi goes off, so the
schedule on screen is the bundled one. The blocks here hold no comments, because in an interactive zsh `#` doesn't
start one without `setopt interactivecomments` (`development.md` §5.1).

**With the network on:**

1. Build from a clean checkout at the commit you are showing (`development.md` §5.8):

   ```bash
   PUB_CACHE=$PWD/build/pub-cache LANG=en_US.UTF-8 uv run flet build ios-simulator --yes
   PUB_CACHE=$PWD/build/pub-cache uv run flet build apk --arch arm64-v8a
   ```

2. Boot both simulators (`xcrun simctl list devices available` gives the udids; `xcrun simctl boot <udid>`;
   `open -a Simulator`). In Simulator's menu, turn on I/O › Keyboard › Connect Hardware Keyboard.
3. Start the companion (`development.md` §5.2), leaving both running: the first command in T2, at the repo root, and
   the second in T3, about 2 minutes the first time. **Not tried:** whether they survive the Wi-Fi going off.

   ```bash
   BROWSER=true uv run flet run -r -w -p 8550
   cd .flet-src/client && flutter run -d <simulator B udid>
   ```

4. Open beat 6's page in a private window, so no GitHub session or notification shows, and never reload it:
   `<SOURCE_URL>/blob/<ref>/src/pycon_us/screens/now.py`, with the ref #834 settles. **Until the repo is public it
   would 404 there,** so beat 6 uses the editor.
5. Copy the recordings to the laptop.

**Turn the network off, then check it:**

6. `networksetup -setairportpower en0 off` (`networksetup -listallhardwareports` names the Wi-Fi port), and unplug any
   cable or tether. `curl --max-time 3 https://github.com` must now fail.

**With the network off:**

7. Start the mock in T1. Loopback only needs no firewall prompt and no hotspot. The `curl` answers 401,
   "Unknown API key."

   ```bash
   uv run python -m tools.mock_api.server
   curl -s http://localhost:8000/2026/api/v1/user/check_features/
   ```

8. Install on A from nothing. The first launch unpacks Python, so give it time.

   ```bash
   xcrun simctl uninstall <simulator A udid> io.github.ndonkohenri.confcompanion
   xcrun simctl install <simulator A udid> build/ios-simulator/pycon-us.app
   ```

9. On A, open the app: Welcome › **Get started**.
10. More › About this app › tap the version row 7 times. Then More › Developer options:
    - **Fake clock:** `2026-05-15 10:48`, then **Apply**. Every start of the app begins at it again (D-187), so each
      run opens on the same moment.
    - **Mock API base URL:** `http://localhost:8000`, then **Save**. **Check mock connection** must say "Connected to
      the local mock server."
11. On the Schedule tab, Friday, star these five. Answer the reminders primer with **Not now**, so it never shows on
    stage:

    | Time | Session | Id |
    |---|---|---|
    | 9:45 AM | Lin Qiao (keynote) | 153 |
    | 11:00 AM | The Art of Extending Python with other languages | 4 |
    | 11:00 AM | Mind the gap! Why static typing requires more than just adding annotations | 15 |
    | 11:45 AM | PEP 750 - T-strings: safer and smarter string processing | 70 |
    | 12:30 PM | What's so hard about writing a type checker? A tour of ty | 143 |

12. On B: **Get started**, then the same fake clock and the same five stars, with no mock URL (Developer options is
    always there on B). The spare gets what A got, from `adb install -r build/apk/pycon-us.apk` (`development.md` §5.5).
13. Quit A, so that beat 1 is a cold start: `xcrun simctl terminate <simulator A udid> io.github.ndonkohenri.confcompanion`.
14. On the laptop: Do Not Disturb on, the Dock hidden, windows placed, large fonts in the terminals and the editor.
    `git status` must be clean.

## The beats

### 1. Offline start (0:45, simulator A)

**The point:** the app is complete on the device. No network, and nothing is missing.

1. Show the laptop's Wi-Fi menu, off.
2. Tap the app's icon on A.

**On screen:** the purple splash, then Now, with "Day 3 of 5 · Friday" and "Up next at 11:00 AM" in the header. Once the
launch's refresh has failed, the strip under it says "Offline · schedule from Sun, Oct 11, 5:56 PM", with Refresh. That
date is the snapshot's capture (`snapshot_captured_at`, `conference.toml`), so #44's refresh of the snapshot changes
it. Don't tap Refresh. If the laptop's zone isn't Pacific, the header also says "Times are Pacific Time (PDT)".

**Fallback:** nothing after about 20 seconds: terminate it and tap again. Then the spare, then the recording.

**Not tried:** how long the cold start takes here, and how soon the strip appears with the Wi-Fi off.

### 2. Now and Next for me (1:00, simulator A)

**The point:** it answers "what should I do next?", for you, from the stars on this device.

1. Point at **Your next session**.
2. Scroll down through Happening now and Up next.
3. Scroll back and tap **Show room**, show the room's day, then Back. Optional if late.

**On screen:**

- **Your next session:** a card with "The Art of Extending Python with other languages", Grand Ballroom B, its star on,
  "Starts in 12 min" (fewer if you lingered: the fake clock runs on) and **Show room**.
- **Happening now:** a dot, then CTF for fun and profit and Web Scraping with their elapsed bars, and the Break.
- **Up next · 11:00 AM:** "Starts in 12 min", then your other saved session first (Mind the gap!), three others, and
  **Show all 9 sessions**.
- **Show room:** a page titled Grand Ballroom B, on Friday, with this session lit up for a moment.

**Fallback:** the card is missing or says "Happening now": the fake clock has run on or the stars are gone. Terminate
and relaunch, which restarts it at 10:48. If the stars are gone, star one in Up next: the card appears at once. Then
the recording.

### 3. My schedule (0:45, simulator A)

**The point:** a personal agenda that warns about clashes while they can still change a plan, offline.

1. Tap the **My schedule** tab.
2. Point at the two 11:00 AM rows.
3. On Mind the gap!, tap the star.
4. Tap **Undo**. The first thing to cut if late.

**On screen:** "Friday, May 15", then the fold "Earlier today (1 session)", which holds the keynote. Then 11:00 AM with
both sessions, each with an amber "Overlaps with “…”" naming the other; 11:45 AM, PEP 750; 12:30 PM, the tour of ty. The
star tap removes the row and the other row's warning, with "Removed from My schedule" and Undo at the bottom. Undo brings
both back.

**Fallback:** "Nothing saved yet": tap **Browse the schedule**, star sessions 4 and 15 on Friday's 11:00 AM slot, and
come back; the overlap shows just the same. Then the recording.

### 4. Live edit in the companion app (1:15, simulator B)

**The point:** this is Python. Save the file and the app changes. The packaged app on A doesn't, because its Python is
on the device; here Python is on the laptop.

**Interim:** a companion client built from the pin, on a simulator (`development.md` §5.2), until a 1.1 companion is in
the stores (D-81).

Until Flet fixes U287 (#1044), a save can leave B on the boot spinner, so press `R` in T3 before each save
(`development.md` §5.2).

1. Put B beside the editor, on Now.
2. Press `R` in T3 and wait for Now to come back.
3. In `now_card.py`, change `HEADING = "Your next session"` to `HEADING = "Next for you"`, and save.
4. Press `R` in T3 again and wait for Now, then undo and save, so the audience sees it go back.

**On screen:** T2 restarts Python, B reconnects, and within seconds (4 in the one timed run) the card's heading reads "Next for you",
still on Now. A reload resets what is in memory, not the stars or the fake clock (`development.md` §5.2). The countdown
goes back to 12 min, since the clock starts again.

**Fallback:** B on the purple spinner after a save: press `R` in T3, and the edit shows. No change 20 seconds after
that: go to the recording and tell the room what it would have done. A stuck port is
`lsof -nP -iTCP:8550 -sTCP:LISTEN`, for after the talk. Either way, leave the file as it was:
`git restore src/pycon_us/screens/now_card.py`.

**Tried** (#1038, on 2026-11-04): these steps on an iPhone 17 on iOS 26.5, at 10:48 with one star, session 4, waiting 8
seconds after each `R`. **Not tried:** the reload with the Wi-Fi off, a shorter wait after `R`, and simulator B's iPhone
17 Pro beside the packaged build.

### 5. A staff scan against the mock (1:45, simulator A)

**The point:** the staff tools are the same app, and hidden until an account has them. A door keeps moving when the
network doesn't.

**Interim:** manual entry, typed on the laptop's keyboard, until E1 (#520, #726). The mock's badges are made up.

1. Show T1: the mock, on this laptop, is the only backend the staff tools ever talk to (D-51).
2. On A: **More**, then **Sign in**, the first row. Enter `staff@example.com` and `mock-staff`, then **Sign in**.
3. Under Staff tools, tap **Door check**. The session picker opens by itself.
4. Tap the **Tutorials** chip, then **All about decorators**.
5. In **Badge code**, type each of these and press Return, watching the panel. A code repeated within 4 seconds is
   dropped as a held badge, so take a breath before the third.

   | Type | The panel says | Under it |
   |---|---|---|
   | `MOCK0001:v4l1d01` | Checked in, Ada Example | The chip Vegetarian |
   | `MOCK0003:v4l1d03` | Checked in, Linus Placeholder | "Admits 2"; the warning chip Allergy, and Vegan |
   | `MOCK0001:v4l1d01` | Already checked in, Ada Example | The count stays |
   | `MOCK0004:v4l1d04` | Not registered for this session, MOCK0004 | The one scan that asks the server |

**On screen:**

- **Sign in:** "Connected to the local mock server" over the form, then "Signed in as Dana Door". More now starts with
  Dana Door and Staff tools: Lead scanner, Door check, Swag pickup.
- **Door check:** "This app can't scan with the camera yet. Type the badge code, or use a Bluetooth or USB scanner.", the chip "All about decorators · Wed 9:00 AM",
  "0 checked in" and "Ready, works offline · 2 attendees". The count reaches "2 checked in".
- **T1:** a line per request, among them `GET /2026/api/v1/check_in/attendees_by_product_with_quantity/10/ 200`, then the
  redeem POSTs as the queue syncs. It never logs a key, a query or a body.

**Fallback, in order:**

1. "You're offline. Connect and try again." at sign-in, or "Couldn't load sessions": the mock is down. In T1, press Up
   and Return, then try again or tap **Retry**. Accounts come from the seed, so nothing else changes.
2. The mock dies after the list has loaded: keep scanning, because this is the feature. Badges on the list are still
   admitted from the device. The chip goes to "Offline · 1 queued" after the failed sync, and the next admission adds
   "Saved. Will sync." Restart the mock and tap the chip, then Sync now. A badge not on the list says "Can't check
   this badge".
3. The recording.

**Not tried:** the sign-in and the picker with the Wi-Fi off; the sync with the Wi-Fi off, though nothing in the code
gates on connectivity (D-56's worker just tries); and whether iOS offers to save the password after the sign-in, which
the form allows (`sign_in.py`). If it does, answer it in rehearsal, so it doesn't come up on stage.

### 6. View source (0:30, laptop browser)

**The point:** a screen is one tap from its Python, and here is the one you just saw.

1. On A, go to the **Now** tab and open the app bar's overflow menu. Point at **View source**. Don't tap it: it needs
   GitHub, and #834 settles what it says offline.
2. Close the menu and switch to the browser window.

**On screen:** `src/pycon_us/screens/now.py` on GitHub, in the page opened before the Wi-Fi went off.

**Not built:** View source doesn't exist yet (#834), and turns on with the public repo (#835). Until then, step 1 is a
sentence and step 2 is the editor. About this app has no Source code row either, while `SOURCE_URL` is `None`.

**Fallback:** the page went blank or tries to reload: the same file in the editor needs no network. Then the recording.

**Not tried:** whether a tab stays rendered through a whole talk with the Wi-Fi off. Browsers may discard a tab under
memory pressure, so check it again just before going on.

## Between runs

Exit 3 asks for two runs, and door check-ins outlive a restart, so a second run would say "Already checked in":

1. On A: Developer options › **Clear staff data**, confirm. This also clears the session chosen.
2. More › Dana Door › **Sign out**. "Your saved sessions stay on this device."
3. Ctrl-C the mock in T1 and start it again: its state is in memory, so that's a clean slate.
4. Confirm the five stars on My schedule, and that `git status` is clean.
5. Terminate the app on A.

After the talk, reset the
fake clock if the simulators stay in use.

## A phone instead of a simulator (not tried)

Beats 1, 2, 3 and 5 would move to a phone. Beats 4 and 6 stay on the laptop. Take this route only after two rehearsals
on the phone that will be on stage. Until then the simulators are the plan. It would be the owner's iPhone: there is
no Android phone (#841), and the iPhone can't take a development build until #121 gives it a certificate.

1. **The hotspot.** macOS Internet Sharing, with a network name and password. **Not tried:** it asks for a connection
   to share, and may refuse to start with nothing to share. If so, a travel router with no uplink gives the same LAN, and so does the
   phone's own hotspot with the laptop joined to it (`development.md` §6). Buying a router is the owner's call.
2. **The server.** `uv run python -m tools.mock_api.server --host 0.0.0.0`, with the firewall prompt answered in
   rehearsal, never on stage (`development.md` §6).
3. **The address.** **Don't count on the banner:** `lan_addresses()` finds it by asking for a route to the internet,
   and a hotspot with no upstream may have none, so the "phones on the Wi-Fi" line may not print. Read it with
   `ifconfig` instead: the bridge interface Internet Sharing makes (usually `bridge100`, not checked here).
4. **The phone.** Airplane mode, then Wi-Fi on and joined to the hotspot, so that the offline strip tells the truth.
   Mock API base URL: `http://<that address>:8000`. **Check mock connection** must say "Connected to the local mock
   server."
5. **Still open:**
   - Whether iOS asks for local-network access for the embedded Python's sockets (`development.md` §3.4, §6, §10; #121).
   - Whether iOS keeps a network with no internet, or warns and drops it.
   - How the phone's screen reaches the projector with no network.

If this fails and a phone is still wanted, O-8 reopens (D-457).

## What changes before the freeze

- **#834, #835:** View source becomes real; beat 6 stops being a sentence.
- **#44, the 2027 feed:** the snapshot's date in beat 1, and if the 2027 feed replaces 2026, the fake clock, the session
  ids and every session name above.
- **#520, #726:** a camera scan, on a phone only.
- **A 1.1 companion in the stores:** live edit could use `flet run --ios` and a QR code, over the same hotspot.
- **#856:** where the recordings live. Fill in each fallback.

## Dry run log

Fill in one row per run. Turn off the laptop's Wi-Fi and run from [beat 1](#1-offline-start-045-simulator-a), once on
the simulators and once on the spare. The spare needs its own companion (`flutter run -d emulator-5554`, reached at
`10.0.2.2:8550`) for beat 4. A beat is `live`, `fallback` or `failed`, with its time.

| Date | Commit, Flet pin | Device | 1 | 2 | 3 | 4 | 5 | 6 | Total | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| | | | | | | | | | | |
