# S6: Can local reminders be reliable when the app isn't running?

**Spike:** S6 ([#111](https://github.com/ndonkoHenri/pycon-us-flet/issues/111), PLAN §8, under the E3 epic [#19](https://github.com/ndonkoHenri/pycon-us-flet/issues/19)). **Date:** 2026-10-14, about 4 hours of builds and runs on one Mac.
**Decides:** D-220 (E3's scope: API, platform setup, limits), D-221 (exact timing on Android when allowed; amends D-59 and ux.md §6.9), D-222 (the plan's cap and how `apply()` cancels; amends D-59). **Facts:** F52, F53. **Upstream:** U7 ([#293](https://github.com/ndonkoHenri/pycon-us-flet/issues/293)), E3 scheduling ([#294](https://github.com/ndonkoHenri/pycon-us-flet/issues/294)). **Held for the iPhone:** [#121](https://github.com/ndonkoHenri/pycon-us-flet/issues/121) (the list at the end).

## Question

Can a release build deliver a reminder scheduled ahead when the app isn't running: killed, behind a locked screen, across a reboot, with exact alarms denied, and can a tap on it open the app at the right place from a cold start? And what does E3 (scheduled local notifications, `docs/flet-gaps-and-extensions.md` §4.1) need to be, so that it can?

## Answer: yes on both platforms, with four things E3 must carry and three changes to D-59

- **Nothing usable exists at the pin.** `.flet-src` at `15854a0ac` has no local-notifications package (`sdk/python/packages/` has none; no `flutter_local_notifications` anywhere in the client or the packages), so the official extension of `flet-dev/flet#6948` cannot be used yet, and nothing of E3 can be adopted. S6 therefore tested the **same plugin** (`flutter_local_notifications` 22.3.1) through a throwaway extension of its own with E3's proposed API (`docs/spikes/06-reminders/`, not app code).
- **Delivery with the app not running works** on the Android 14 emulator (release APK) and the iOS 26.5 simulator (debug build): swiped away from Recents, screen off and on the keyguard, across a reboot, in forced Doze, and moved (the same id rescheduled later fires once, at the new time). A tap opens the app with the reminder's payload, from a cold start and while running.
- **What E3 must carry (D-220):**
  1. **Android receivers from the extension itself.** An extension whose pubspec declares an Android plugin class gets an Android library module, and Gradle merges its manifest into the app's (F52). The plugin's two receivers and `RECEIVE_BOOT_COMPLETED` go there, so the build template needs **no** `<receiver>` hook (the gaps doc's "preferred" approach works; no fallback table, no new U-item).
  2. **Core library desugaring in the app module (U7).** Without it `flet build apk` stops at `:app:checkReleaseAarMetadata`; there is no option for it at the pin. This is a template change only Flet can make: [#293](https://github.com/ndonkoHenri/pycon-us-flet/issues/293).
  3. **The iOS notification delegate, set from the extension's iOS side.** With the stock template, iOS delivers the reminder but **never tells the plugin about a tap**: a cold-start tap opened the app with no launch details, and a tap while running sent no event. A Swift plugin class in the extension that makes the app delegate `UNUserNotificationCenter`'s delegate fixes both (F53); no template change is needed.
  4. **A monochrome small icon.** The launcher icon is drawn as a plain disc in the status bar and the shade. A vector drawable in the extension's Android module, with a `tools:keep` rule (the plugin looks the icon up by name, which resource shrinking cannot see), survived R8 and showed as a bell in light and dark.
- **D-59 changes (D-221, D-222):**
  - **Inexact is too late for "10 minutes before" on Android.** An inexact alarm's window is 75 % of the time left when it is scheduled (`dumpsys alarm`), and Android 14 delivers it anywhere in that window: at its end when nothing else wakes the device (+90 s on a 2-minute lead, +180 s on 4 minutes), earlier when another alarm wakes it first (+80 s on 10 minutes, and still +6 min 10 s on 30 minutes). A plan applied in the morning for an afternoon session could fire hours late. Exact alarms fired within a second. So reminders use **exact alarms when the user allows them** ("Alarms & reminders", denied by default on Android 14), asked in context, and fall back to inexact with honest copy (D-221).
  - **iOS keeps only 64, and not the soonest.** Planning 70 reminders left 64 pending and **dropped the six soonest** (the first six added). The cap must be the app's: at most the next 60, soonest first, which D-59 already says; S6 confirms it and makes it a rule of `plan()` rather than of `apply()` (D-222). Android kept all 70.
  - **Cancel pending only.** The plugin's `cancelAll()` also removes reminders already shown, so a re-plan after a favourite would wipe a delivered reminder from the shade (seen). `apply()` uses `cancelAllPendingNotifications()` (D-222).
  - **Apply on every start.** A force-stop cleared the app's alarm: the reminder never came, and at the next start `dumpsys alarm` had none while the plugin's `pendingNotificationRequests()` still listed it (it reads its own cache). The next install of the APK brought it back (the package-replaced receiver reschedules from that cache) and it fired at once, about 6 minutes late; an app update would do the same. So `get_pending()` cannot say what Android will deliver, and `apply()` runs at every start and resume (D-222).

## Method

- **Host:** Apple M4, macOS 27.0, Xcode 27.0, Android emulator 36.2.12.0, uv 0.12. Other agents built and ran emulators at the same time, so timings carry some noise.
- **Flet:** the pin `15854a0ac` (`.flet-ref`), Flutter 3.47.7, AGP 8.13.2.
- **Plugin:** `flutter_local_notifications` 22.3.1 and `timezone` 0.11.1 (the versions the gaps doc §6 records).
- **Devices:**
  - `flet_probe_api34` as `emulator-5584`, my own read-only instance: Android 14, Google APIs arm64, gesture navigation; its keyguard (swipe, no PIN) enabled for the lock checks.
  - iOS 26.5 (23F77): the shared "PyCon iPhone 17" simulator, for the permission prompt and the taps (simctl cannot tap), under its lock, with the app removed afterwards. A simulator of my own ("111-iphone17") was booted in case the shared one stayed locked; it was not needed and was deleted at the end.
- **Builds:** release `flet build apk --arch arm64-v8a` (R8 on, the template's default rules) and `flet build ios-simulator` (debug, D-102), from the reproducer folder, each with a pub cache of its own (D-176); the iOS bundle was checked against `build/python-app`.
- **Reproducer:** [`06-reminders/`](06-reminders/), its own `pyproject.toml` on `.flet-src`.
  - `s6_reminders/`: the throwaway extension. Python: `S6Reminders(ft.Service)` with `initialize()` (returns the launch details), `request_permission()`, `permission_status()`, `request_exact()`, `zoned_schedule(id, title, body, at, *, payload, exact)`, `get_pending()`, `cancel_all()` and `on_tap`. Dart: a `FletService` over the plugin; `zoned_schedule` sends one ISO instant and schedules it as `TZDateTime.from(instant, tz.UTC)`, with no time-zone database. `android/`: a Java no-op plugin class, the manifest with the receivers, a vector icon and its keep rule. `ios/`: a Swift package whose plugin class sets the notification delegate (the second iOS build; the first had no iOS side).
  - `src/main.py`: one screen of buttons, and start routes for what simctl cannot tap: `/schedule/<seconds>[/<exact|inexact>[/<id>]]`, `/many/<count>/<seconds>` and `/move`. A reminder's payload is `/opened/<id>`. Each step prints an `S6 ` line.
  - `patch_desugaring.py`: the two lines U7 would render, applied to the generated Gradle file after the first build fails (a spike shortcut).
  - `drive_android.py`: the Android checks. It schedules through a start route, then swipes the app away in Recents (the process dies, the package is not stopped), locks, reboots, forces Doze or changes a permission, and polls `dumpsys notification` for the reminder. **The delay is the notification's own `when`** (set as the plugin posts it) minus the scheduled instant, so a late poll does not inflate it.

## Evidence

### Android 14 emulator, release APK

| Check | Lead | Result |
|---|---|---|
| Swiped away from Recents, inexact | 2 min | delivered, **+91.4 s** and **+91.5 s** (two runs; the window was 89 s) |
| Screen off (no keyguard), inexact | 2 min | delivered, +99.1 s |
| On the keyguard, screen off, inexact | 2 min | delivered, +26.3 s: another reminder's window ended then, and Android delivered both |
| Reboot (swiped, then `adb reboot` at once; the boot took about 2 min) | 3 min | delivered **+35 s** after due, by the boot receiver's reschedule; the plugin's GSON cache read back fine under R8 |
| Exact, permission denied (Android 14's default) | 2 min | `zonedSchedule` throws `exact_alarms_not_permitted`; nothing scheduled |
| Exact, permission allowed (`appops ... allow`) | 2 min | delivered **+0.7 s** |
| Forced deep Doze, exact allowed | 2 min | delivered +59.3 s |
| Forced deep Doze, inexact | 2 min | delivered +90.1 s (the window's end) |
| Notifications denied (`pm revoke POST_NOTIFICATIONS`) | 2 min | scheduling succeeds, nothing is shown; `areNotificationsEnabled()` is false |
| Moved: id 7 at +2 min, then cancelled and set to +4 min | 4 min | one notification, at the new time (+179.8 s, the window's end); nothing at the old time |
| 10 min ahead, screen off | 10 min | delivered +79.6 s (window 7 min 29 s) |
| 30 min ahead, screen off | 30 min | delivered **+369.6 s**, over 6 minutes late (window 22 min 29 s) |
| 70 planned | 10–79 min | 70 pending, 70 alarms in `dumpsys alarm` |
| Status-bar icon | — | the launcher icon shows as a disc; the extension's vector drawable as a bell, in light and dark |
| Force-stopped (`am force-stop`, Settings' Force stop) | 2 min | **never delivered**; at the next start no alarm in `dumpsys alarm`, but `get_pending()` still listed it; the next APK install rescheduled it and it fired at once |
| Cold-start tap (process dead) | — | the app starts; `getNotificationAppLaunchDetails()` gives `didNotificationLaunchApp` and the payload `/opened/42` |
| Tap with the app in the background | — | `on_tap` fires with the payload `/opened/7` |

- **The window.** `dumpsys alarm` shows each inexact reminder with `window` = 75 % of the lead (89 s for 2 min, 7 min 29 s for 10 min, 22 min 29 s for 30 min, 16 min 29 s for the 25th of the 70). Android 14 delivers an inexact alarm somewhere between its time and the end of its window; with nothing else due, at the end. That is AOSP's `setAndAllowWhileIdle()` for an app targeting API 34, not the plugin.
- **Permissions.** The release build asks for `POST_NOTIFICATIONS` through the plugin's `requestNotificationsPermission()` (Android's own prompt). `SCHEDULE_EXACT_ALARM` was declared in the reproducer only to compare the modes; `canScheduleExactNotifications()` reported it correctly in both states.
- **R8.** The plugin stores scheduled notifications as GSON JSON. With the template's default rules (`-keepnames class * { *; }`), the mapping keeps the plugin's model names, and every delivery (which parses that JSON) and the reboot (which reloads the cache) worked. No extra GSON rules are needed while the default rules stay on.

### iOS 26.5 simulator, debug build

| Check | Stock template | With the extension's delegate |
|---|---|---|
| Permission | `requestPermissions()` shows iOS's prompt; Allow → granted | same |
| Killed (`simctl terminate`), 2 min ahead | delivered on time (banner) | delivered on time |
| Foreground | not checked | presented as a banner over the app |
| Cold-start tap on the banner | the app opens, **launch details empty** | `didNotificationLaunchApp` with the payload `/opened/45` |
| Tap with the app in the background | the app comes forward, **no event** | `on_tap` with `/opened/47` |
| 70 planned (soonest first) | 64 pending, the **six soonest dropped** | 64 pending: ids 1006–1069, so 1000–1005 dropped |

- **Why taps were lost.** Flutter 3.47.7 migrates the generated iOS project to the UIScene life cycle at build time ("Finished migration to UIScene lifecycle"): `AppDelegate` becomes a `FlutterImplicitEngineDelegate` that registers plugins in `didInitializeImplicitFlutterEngine`. Nobody sets `UNUserNotificationCenter.current().delegate`, and the plugin does not either (it only adds itself as an application delegate, `FlutterLocalNotificationsPlugin.m:155`), so iOS has no one to tell. `FlutterAppDelegate` forwards the center's callbacks to plugins once it is the delegate, so one line in any plugin's `register(with:)` is enough, and it still runs early enough for a cold-start tap (F53).

## Decisions changed

- **D-220:** E3's scope, from what S6 ran. Recorded in `docs/flet-gaps-and-extensions.md` §4.1 (API, platform setup, tests).
- **D-221:** exact timing on Android when the user allows it; amends D-59's "inexact timing by default", ux.md §6.9's reminder section and NATIVE-06.
- **D-222:** the cap of 60 is confirmed and lives in `plan()`; `apply()` cancels pending reminders only and also runs on every start; amends D-59.

## What E3's adoption must apply (P2, after the pin bump)

- `[tool.flet.android.permission] "android.permission.POST_NOTIFICATIONS" = true` and `"android.permission.SCHEDULE_EXACT_ALARM" = true` (never `USE_EXACT_ALARM`).
- Nothing for receivers, the boot permission, the icon or the iOS delegate: the extension brings them.
- Desugaring comes with the Flet pin that has U7.
- `services/reminders.py`: `plan()` caps at 60, soonest first; `apply()` cancels pending only, schedules exact when `Permission.SCHEDULE_EXACT_ALARM` is granted and inexact otherwise, and runs on start, resume and every re-plan.

## Held for the iPhone (#121)

S6 could not show these on a simulator or emulator:
1. A reminder on the **locked iPhone**, with the app killed, from a **release** build (TestFlight), at 2 min and at 30 min.
2. **More than 64**: which 64 a real device keeps, planned soonest first and also latest first (the simulator dropped the first six added).
3. The **cold-start tap** on the device with the extension's delegate, from the lock screen (which asks for Face ID first).
4. **Focus and the scheduled summary**: a reminder is a time-sensitive notification for an attendee. Check whether a default reminder is held back by a Focus or the summary; a `timeSensitive` interruption level needs the Time Sensitive Notifications capability, which Flet's template cannot add today (no entitlements hook, U5).
5. Delivery after a phone restart before the first unlock.

## Fallback

If E3 is late, the D-60 interim stands: Now's next-session card and the in-app Banner while the app is open, and `.ics` exports with an alarm, which the calendar delivers reliably on both platforms.
