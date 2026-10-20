# P2-04: Does a shared .ics file reach the phone's calendar on Android and iOS?

**Spike:** P2-04 ([#364](https://github.com/ndonkoHenri/pycon-us-flet/issues/364), under the reminders and calendar epic [#27](https://github.com/ndonkoHenri/pycon-us-flet/issues/27); no S-number, docs/roadmap.md §5). **Date:** 2026-10-20, about 3 hours of builds and runs on one Mac.
**Decides:** D-272 (how Add to calendar reaches the calendar on each platform; amends D-62 and D-60). **Fact:** F91. **Upstream:** U71 ([#487](https://github.com/ndonkoHenri/pycon-us-flet/issues/487)). **Gates:** [#425](https://github.com/ndonkoHenri/pycon-us-flet/issues/425) (Add to calendar on session detail) and [#426](https://github.com/ndonkoHenri/pycon-us-flet/issues/426) (export My schedule). **Held for the iPhone:** [#121](https://github.com/ndonkoHenri/pycon-us-flet/issues/121) (the list at the end).

## Question

D-60's interim and SESS-04 hand an `.ics` to the share sheet (D-62: `ft.Share().share_files([ft.ShareFile.from_bytes(..., mime_type="text/calendar")])`) and expect it to end up in the calendar. Does it, on each platform? If not, which path does, at what cost, and do the events keep their time zone and alarm?

## Answer: the share sheet reaches no calendar on either platform; two other paths do

- **Android: no.** Google Calendar takes an `.ics` only through `ACTION_VIEW`; the share sheet sends `ACTION_SEND`, so its chooser lists Nearby Share, Drive, Messages, Bluetooth and Gmail, and no calendar (`pm query-activities`: Calendar's `ICalLauncher` filters `text/calendar`, `application/ics` and `*.ics` for `VIEW` only).
- **iOS: no.** The sheet offers Copy and Save to Files; its More list of apps is **empty** (Calendar has no share extension). A file saved to Files opens in Quick Look as a list of the events with no add action.
- **What reaches the calendar:**
  - **iOS, one tap from the app:** the app serves the file itself on `http://127.0.0.1:<port>/<slug>.ics` (a stdlib `http.server` on a daemon thread) and opens that URL with `UrlLauncher.launch_url(..., mode=LaunchMode.IN_APP_BROWSER_VIEW)`. SFSafariViewController hands the `text/calendar` response to iOS's own sheet, "2 Events" with **Add All**; the events land with the right time, the **alarm** and the `UID`, and opening the same file again offers no Add All (already added). Cost: about 30 lines of stdlib code, three taps in the system's sheets (Add All, Done, then the close button of the empty browser view that stays behind), and a `launch_url` that raises although it worked (F91), so success is the server's GET.
  - **Android, by the Files app:** `FilePicker.save_file(src_bytes=...)` saves the file (Downloads by default); opening it from Files sends `ACTION_VIEW` to Calendar, whose import screen lists the events with **Add all**. The events land with the right time but **without the alarm**: Google Calendar 2023.18.3's import drops the `VALARM`. Cost: the user leaves the app and finds the file (about five taps), and Calendar needs a calendar account to add to (it sends an emulator without one to Google's sign-in).
- **Nothing else at the pin works** (F91): a `file://` URL raises `FileUriExposedException` on Android and opens nothing on iOS; a `data:` URL opens nothing on either; the same loopback URL in the **external** browser on iOS opens Calendar's "Add Subscription Calendar" for a URL that stops answering, which is wrong. Opening a local file in the app that handles its type is a Flet gap (U71, #487): with it, Android would reach Calendar's import screen in one tap.
- **So (D-272):** Add to calendar never uses the share sheet. iOS uses the loopback and the in-app browser; Android saves the file and says how to open it, and its copy promises no alarm, until U71 (or E4) is pinned. `core/ics.py` (#380) is unchanged.

## Method

- **Host:** Apple M4, macOS 27.0, Xcode 27.1, Android emulator 37.2.12.0, uv 0.12.15. Other agents built and ran emulators at the same time; one ANR dialog ("System UI isn't responding") at the first launch came from that load.
- **Flet:** the pin `15854a0ac` (`.flet-ref`), Flutter 3.47.7; resolved plugins share_plus 12.0.2, url_launcher_android 6.3.33, url_launcher_ios 6.4.2, file_picker 11.0.3.
- **Devices:**
  - Android: `flet_probe_api34` as `emulator-5588`, my own read-only instance (Android 14, Google APIs arm64, `UE1A.230829.050`), time zone set to `America/Los_Angeles`. Calendar apps on the image: **Google Calendar 2023.18.3** (`com.google.android.calendar`) and the calendar provider; no AOSP Calendar. Files is DocumentsUI 14; Chrome 113. The image has no Google account, so for the import checks a local calendar was created in the provider with `adb shell content insert` (account type `LOCAL`); no account was added.
  - iOS: my own "364-iphone17" (iPhone 17, iOS 26.5, 23F77), booted for this spike and deleted at the end; it takes the Mac's zone (CEST, UTC+2). Built-in Calendar and Files; Mail is not on the simulator. Taps through the free local Maestro CLI (`maestro --device <udid> test <flow>`), screenshots through `simctl io`.
- **Builds:** release `flet build apk --arch arm64-v8a` and debug `flet build ios-simulator` (D-102) from the reproducer folder, with a pub cache of the worktree's own (D-176); the iOS bundle's `app/` matched `build/python-app` (apart from serious_python's `.keep`).
- **Reproducer:** [`10-ics-share/`](10-ics-share/), its own `pyproject.toml` on `.flet-src`.
  - `src/ics_sample.py`: the hand-written file, 834 bytes: two events on 2026-10-22 in UTC (`17:30Z`–`18:00Z` with a `VALARM` `TRIGGER:-PT10M`, and `19:00Z`–`19:45Z` without one), CRLF, escaped `\,` `\;` `\n`, a description folded at 75 octets, a `URL`, stable `UID`s. `check_ics.py` checks those properties on the host.
  - `src/main.py`: one screen with seven buttons, one per route out of the app: Share file (bytes), D-62 as written; Share file (path); Save to a folder (`FilePicker.save_file`); Open file URL; Open data URL; Serve, in-app browser; Serve, browser. Each result prints an `ICS ` line (logcat `flet.python`, iOS unified log `dart_bridge`) and shows on the screen.
- **Where an event landed:** Android's calendar provider (`content query --uri content://com.android.calendar/events`, and `/reminders`), iOS's `Calendar.sqlitedb` in the simulator's data folder (read-only `sqlite3`: `CalendarItem` and `Alarm`), and each calendar's event screen.

## Evidence

### Android 14 emulator, release APK

| Route | What happened | In the calendar |
|---|---|---|
| Share file (bytes): `share_files([ShareFile.from_bytes(..., mime_type="text/calendar", name="spike-364.ics")])` | System chooser "Sharing 1 file", `spike-364.ics`; targets **Nearby Share, Drive, Messages, Bluetooth, Gmail** (the whole list, expanded); dismissed → `DISMISSED` | nothing: Calendar is not offered |
| Share file (path): `ShareFile.from_path` | the same chooser and targets | nothing |
| Save to a folder: `FilePicker.save_file(file_name=..., src_bytes=...)` | DocumentsUI's save dialog in Downloads, one tap on SAVE; returns `/document/12`; `/sdcard/Download/spike-364.ics`, 834 bytes | — |
| …then Files › Downloads › tap the file | `ACTION_VIEW` `typ=text/calendar` content URI → `com.google.android.calendar/.ICalLauncher`. With no account: Calendar's welcome slides, then Google's **Sign in** (backed out; Calendar closed). With a local calendar: "ICS file", Oct 22, both events, **ADD ALL** | talk **10:30–11:00 AM**, break 12:00–12:45 PM (PDT): provider `dtstart` 17:30:00Z and 19:00:00Z exactly, `eventTimezone` America/Los_Angeles; title, location (`Grand Ballroom A; Long Beach Convention Center`) and the two-line description unescaped and unfolded correctly; **`hasAlarm=0`, no row in `/reminders`**, and the event screen has no notification line: **the alarm is dropped** |
| …the same file imported twice more | ADD ALL each time | still **two** events: no duplicates |
| Open file URL: `launch_url("file:///data/user/0/…/app_flutter/spike-364.ics", EXTERNAL_APPLICATION)` | `RuntimeError: PlatformException(FileUriExposedException, … exposed beyond app through Intent.getData())` | nothing |
| Open data URL: `launch_url("data:text/calendar;base64,…")` | `PlatformException(ACTIVITY_NOT_FOUND, No Activity found to handle intent …)` | nothing |
| Serve, in-app browser: `launch_url("http://127.0.0.1:41755/spike-364.ics", IN_APP_BROWSER_VIEW)` | a Custom Tab in Chrome, which first shows its own first run ("By continuing, you agree to the Terms of Service"). **Not accepted** by an agent; backed out. Not evaluated | — |

- **Intent resolution** (`pm query-activities`): `SEND` `text/calendar` → Drive, Messages, Gmail, two Nearby Share activities; `VIEW` `text/calendar` (content or file) → `ICalLauncher` only. An untyped `VIEW` of `http://…/x.ics` resolves to `ICalLauncher` and Chrome, and Chrome takes it (the default); with url_launcher's non-browser flag (`EXTERNAL_NON_BROWSER_APPLICATION`) nothing resolves. So no URL the app can launch reaches Calendar.
- **Taps, Save then Files:** SAVE, leave the app and open Files (Downloads was its first screen here), the file, ADD ALL: four plus finding the file, and a calendar account must exist.

### iOS 26.5 simulator, debug build

| Route | What happened | In the calendar |
|---|---|---|
| Share file (bytes) | share sheet: "ICS · 834 bytes", **More**, **Copy**, **Save to Files**; More opens "Apps", **empty** | nothing: Calendar is not offered |
| …Save to Files, then Files › On My iPhone › the file | Quick Look: "Thursday, Oct 22", both events at 7:30 and 9:00 PM (CEST), the location cut at its `;`; its share button offers More, Copy and Save to Files again. **No add action** | nothing |
| Open file URL (`file://…/Documents/spike-364.ics`) | `can_launch_url` True, `launch_url` returns; **nothing opens** | nothing |
| Open data URL | `can_launch_url` False, `launch_url` returns; nothing opens | nothing |
| **Serve, in-app browser:** `launch_url("http://127.0.0.1:59711/spike-364.ics", IN_APP_BROWSER_VIEW)` | the server logs `GET /spike-364.ics 200`; SFSafariViewController shows iOS's sheet **"2 Events" · Add All**, both events at 7:30–8:00 and 9:00–9:45 PM; `launch_url` raises `RuntimeError: PlatformException(Error, Error while launching …)` (F91). **Add All**, then the sheet's ✓; an empty browser view stays, closed with its ✕ | talk **7:30–8 PM** (CEST): `Calendar.sqlitedb` `start_date` **17:30:00Z**, `start_tz` GMT, `unique_identifier` `spike-364-talk@pycon-us-flet.invalid`, **one `Alarm` with `trigger_interval` −600**; the event screen says **Alert: 10 minutes before**, shows the URL as a link "us.pycon.org", the location as two lines (split at the `;`) and the description unfolded; the break has **no alarm** |
| …the same file opened again | "2 Events" with **no Add All**: iOS knows both `UID`s | no duplicates |
| Serve, browser (`EXTERNAL_APPLICATION`) | iOS opens **Calendar's "Add Subscription Calendar"** with the `127.0.0.1` URL (and Calendar's first-run location and notification prompts, both declined); cancelled | nothing (a subscription would point at a server that stops) |

- **No permission and no Info.plist key.** The app asked for no calendar access and needed no `NSCalendars…UsageDescription` (iOS's sheet adds the events, not the app), and SFSafariViewController loaded `http://127.0.0.1` without any App Transport Security exception.
- **Taps, loopback:** Add All, ✓, ✕: three after the app's own item. `UrlLauncher.close_in_app_web_view()` might close the empty view for the user; not tried (the app cannot tell when the sheet is done).
- **The calendar's notifications.** On this fresh simulator, Calendar asked for notification permission the first time it was opened; the alert of an added event is Calendar's to deliver, so it depends on Calendar being allowed to notify (on a phone in use, it nearly always is). Delivery is an iPhone check (#121).

## Not covered

- **Other Android calendars.** The image has Google Calendar only, an old build (2023.18.3), and no Google account. Whether a newer Google Calendar keeps a `VALARM`, and what Samsung Calendar or another calendar does with `ACTION_SEND` or `ACTION_VIEW`, waits for a borrowed Android phone (D-102). Gmail's own "Add to calendar" for an attached invitation needs an account and was not tried.
- **Android's in-app browser route.** Chrome's first run needs the Terms of Service accepted, which an agent does not do. A Custom Tab given a `text/calendar` response is expected to download it, which would end in the same Files step as Save; not verified.
- **Offline on iOS.** The loopback needs no network, but airplane mode on the iPhone is checked in #121.
- **Accessibility.** The sheets are the system's; VoiceOver on iOS's "Add All" sheet goes to #121, TalkBack on Android's save dialog and Calendar's import screen to #425's own checks. The reproducer's screen (no identifiers, headings or live regions) is throwaway.

## Decisions changed

- **D-272** (amends D-62's share call and D-60's third bullet; SESS-04, SESS-05): Add to calendar on iOS serves the file on the loopback and opens it in the in-app browser; on Android it saves the file and tells the user where it went and how to open it, with no promise of an alarm, until U71 (or E4). The share sheet is not a calendar route.
- **F91:** what each `UrlLauncher` route does with a calendar file, and that a successful in-app load of a `text/calendar` response on iOS raises.

## What #425 and #426 must apply

- One module for the calendar route, outside the screens (D-66), used by session detail (#425) and My schedule (#426): `core/ics.py`'s bytes in, the platform's path out, every failure caught at that boundary (D-71) and said in place (D-210), logged by class only (D-72).
- **iOS:** a `ThreadingHTTPServer` bound to `127.0.0.1` on port 0, serving only `/<slug>.ics` with `Content-Type: text/calendar; charset=utf-8` (the spike also sent `Content-Disposition: inline; filename="<slug>.ics"`), started per tap and shut down after its first GET (or 60 s); then `launch_url(url, mode=IN_APP_BROWSER_VIEW)`. The `RuntimeError` it raises is success when the GET came (F91); without a GET, say "Couldn't open the calendar file". Never `EXTERNAL_APPLICATION` (a subscription).
- **Android:** `FilePicker.save_file(dialog_title=..., file_name=f"{slug}.ics", src_bytes=...)`; `None` means cancelled and says nothing; otherwise a SnackBar "Saved. Open it from Files › Downloads to add it to your calendar." No `share_files` for calendars.
- **Copy:** an alarm is promised on iOS only (ux.md §6.9's interim line and the items' wording).
- **Tablet:** the in-app browser and the save dialog need no `share_position_origin`.
- **One event:** the spike's file held two events ("2 Events", Add All); #425 checks what iOS's sheet shows for a single session.

## Held for the iPhone (#121)

1. From a **release** build (TestFlight): Add to calendar on a session through the loopback and SFSafariViewController shows "Add All"; the event lands in the iPhone's default calendar (iCloud) at the right time with "Alert: 10 minutes before", and **the alert fires** at its time, with the app killed.
2. The same in **airplane mode** (the loopback needs no network).
3. Opening the same file twice offers no Add All (no duplicates), and an export of My schedule with 20 or more sessions adds them all.
4. VoiceOver reads iOS's "Add All" sheet and returns to the app's overflow after the empty browser view closes.

## Fallback

If the loopback route stops working on a later iOS, Add to calendar on iOS falls back to Save to Files with the same honest SnackBar as Android, or waits for E4 (native add, `docs/flet-gaps-and-extensions.md` §4.3); reminders inside the app (D-60's Now card and Banner) are unaffected.
