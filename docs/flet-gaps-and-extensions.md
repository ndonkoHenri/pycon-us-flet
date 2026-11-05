# Flet gaps and upstream work

**Status:** v2, 2026-10-11. It replaces the v1 spec (PSF-oriented, kept in git history).
**Owner:** U. **Binding inputs:** [`PLAN.md`](../PLAN.md) §6 and §8, the decisions record ([`decisions.md`](decisions.md): D-58..D-65 for capabilities and notifications, D-81 for the Flet pin, D-97..D-99 for upstream work), and [`feature-matrix.md`](feature-matrix.md) for feature ids.

This doc is the register and the spec for every piece of Flet the app needs but Flet lacks. Each item gives the feature ids it serves, the interim that ships now, the upstream work (with the wrapped pub.dev package and version), a Python API sketch modelled on the existing `flet-*` extensions, platform setup, effort, the gate (a capability constant for extensions, a Flet pin bump for core items) and the upgrade steps.

Only gaps that matter to a **Material 3 app on Android and iOS** are kept. Web, PWA, desktop, Cupertino and PSF-only items are cut (§1.3).

**Conventions**
- **exists**: verified in the local monorepo (`flet-dev/flet` at `9fbe52a61`, unreleased 1.1.0) by introspection or by reading the source on 2026-10-11.
- **proposed**: does not exist yet. The names here are our proposal. The Flet team has the final say, and if they choose a different name, only the one app module that imports it changes.
- **Paths** in the monorepo:
  - `FLET` = `sdk/python/packages/flet/src/flet`
  - `CLI` = `sdk/python/packages/flet-cli/src/flet_cli/commands`
  - `TPL` = `sdk/python/templates/build/{{cookiecutter.out_dir}}`
  - `DART` = `packages/flet/lib/src`
- **Effort**: XS ≤ ½ day, S 1–2 days, M about a week, L more; each includes tests, docs and a changelog entry.
- **Phases** are the PLAN §7 milestones. No item here has a date (D-02).

---

## 1. Register

### 1.1 Priority order (D-98)

| # | Id | Gap | Feature ids | Interim (ships now) | Upstream piece | App needs it | Effort | Status |
|---|---|---|---|---|---|---|---|---|
| 1 | **E3** | Scheduled local notifications | NOTIF-01, NOTIF-05, NOTIF-06, NOTIF-10, DEV-06, STORE-10, NATIVE-06, NEW-05 | Now's "Your next session", an in-app `Banner` while the app is open, `.ics` with `VALARM`; Settings says "Reminders aren't available in this build" (D-60) | Scheduling added to the official extension from [flet-dev/flet#6948](https://github.com/flet-dev/flet/issues/6948) (`flutter_local_notifications` 22.3.1), plus U7; the receivers, the icon and the iOS delegate ship in the extension (D-220) | P2 (spike S6 during P1: [verdict](spikes/06-reminders.md)) | M | **adopted**: landed at the pin `08b89cce5` (#445) as `flet-notifications`, [flet-dev/flet#6999](https://github.com/flet-dev/flet/pull/6999) (fixes #6948), with scheduling and D-220's platform setup (§4.1); the app reminds through it (#446..#449, D-401), and the interim stays for a build without it, the companion app included (D-60, D-63) |
| 2 | **U1** | Pull-to-refresh | DATA-03, SCHED-13, EVT-07, SPON-08 | Status strip with Refresh, plus automatic refresh (D-32, D-40) | `ft.RefreshIndicator` | P1 | S | **adopted** (D-449, [#806](https://github.com/ndonkoHenri/pycon-us-flet/issues/806)): landed at the pin `22a6dcb16` (#805), [flet-dev/flet#6997](https://github.com/flet-dev/flet/pull/6997); the Schedule's day lists, Sprints and Job listings pull to refresh, the strip keeps Refresh |
| 3 | **U15** | A handler exception crashes the session | (cross-cutting) | `@report_errors` decorator (D-71) | An opt-in non-fatal mode with a Python error hook | P1–P2 | S | proposed |
| 4 | **E1** | Barcode scanning | LEAD-01, LEAD-02, DOOR-04, SHIRT-02, MASK-04, NATIVE-06 | Manual entry plus USB/Bluetooth HID scanners, which always work (D-65) | New extension over `mobile_scanner` 7.4.2; API and Dart duties in D-293 | Before P3 (spike S8: [verdict](spikes/08-scanner.md)) | M | goes ahead (D-293); S8 ran the API through a throwaway extension; the write-up is [#520](https://github.com/ndonkoHenri/pycon-us-flet/issues/520) |
| 5 | **U4** | App version at runtime | INFO-03 | `pycon_us.__version__` alone: no build number (D-83, D-187) | `page.get_app_info()`; landed as `Page.get_package_info()` (`PackageInfo`: `app_name`, `package_name`, `version`, `build_number`, …) | P2 | XS | **landed** at the pin `08b89cce5` (#445): [flet-dev/flet#6972](https://github.com/flet-dev/flet/pull/6972); adopted by #452 (D-386): About this app shows the build number from it |
| 6 | **U16** | OS text-scale factor | THEME-11 | Fluid layouts, no fixed heights (D-26) | `PageMediaData.text_scale_factor` | P2 | XS | proposed (one PR with U17) |
| 6 | **U17** | Accessibility-setting changes | THEME-09, high contrast (D-23) | Re-read `get_accessibility_features()` on start and resume (D-34); on Android a change made in the background applies at the following resume (D-183); a SnackBar a screen reader keeps reads them every 2 s and closes once none is on (D-356) | Accessibility fields in `PageMediaData`, delivered by the existing `on_media_change` | P1: #178's late Android resume (D-183) | XS | proposed (one PR with U16); #183 |
| 6 | **U10** | `AppBar.bottom` | SCHED-01, SCHED-27 | Day tabs as the first body row | `AppBar.bottom` | later | S | proposed |
| 6 | **U2** | Sticky headers / slivers | SCHED-02, SCHED-27 | Time gutter layout (D-31) | A grouped list with pinned headers | later | M | proposed |
| 6 | **U3** | Absolute `InteractiveViewer` transform | EXPO-05; D-18's remembered map zoom | Select and highlight the booth, brought above its card with `reset()`, `zoom()` and `pan()` (D-377); a remembered zoom put back with `reset()`, `zoom()` and `pan()` if S7 keeps it | `set_transform()` / `zoom_to_rect()` | later | S | proposed; the analysis, a repro and a draft diff in [#368](https://github.com/ndonkoHenri/pycon-us-flet/issues/368) |
| 6 | **U9** | Query-string hook | NEW-02, ROOM-03, ROOM-05, MAP-05, SPON-04, EXPO-05 | `use_query()` parses `page.route`, once, for the top View only (D-164) | `ft.use_route_search()` | later | XS | proposed; [#369](https://github.com/ndonkoHenri/pycon-us-flet/issues/369) |
| 6 | **U18** | Back inside a modal sub-chain | NEW-02 (search, D-19) | Our own `page.on_view_pop`, set before `page.render_views(App)`, navigates to `parent_of(e.route)` (D-19) | The Router pops to the previous view entry unless the popped view is the modal itself (§5.12) | later | XS | proposed; [#370](https://github.com/ndonkoHenri/pycon-us-flet/issues/370) |
| 6 | **U95** | Share sheet origin with a size | NEW-06, INFO-04 (D-206, D-297) | None needed since the pin `08b89cce5`: share_plus 13.3.1 points an empty origin from the view's centre, so the sheet opens on an iPad (F263; at `15854a0ac` a share there failed and said "Couldn't open the share sheet", F115) | `share_position_origin` that carries a size, or a non-empty default size on the Dart side | P2 (tablets) | XS | proposed; [#525](https://github.com/ndonkoHenri/pycon-us-flet/issues/525); now only for a popover that points from the row, not the centre (F263) |
| 6 | **U182** | `focus()` on `ListTile` and `PopupMenuButton` | Focus order after another app's window (ux.md §9, D-372) | Buttons get the focus back after the browser or the share sheet they opened; a row or an overflow menu item leaves it on no node (D-372) | A `FocusNode` and a `focus` method, as `IconButton` has | P2 | XS | proposed; [#625](https://github.com/ndonkoHenri/pycon-us-flet/issues/625) |
| later | **E4** | Native add-to-calendar | SESS-04 | `.ics` from `core/ics.py` (SESS-05, D-62): on iOS served on `127.0.0.1` and opened in the in-app browser, whose calendar sheet adds it; on Android saved with the system save dialog, to open from Files; never the share sheet, which reaches no calendar (D-272, [P2-04](spikes/10-ics-share.md)) | Extension over `add_2_calendar` 3.1.1 (+ U6) | later | S | proposed |
| low | **E2** | FCM push | none: the app has no push (D-58) | n/a | `firebase_messaging` 16.7.0 (+ U5) | never, in this app | L | a Flet contribution only |

**Conditional CLI and template items.** We do these only when a feature or a spike needs them (D-98).

| Id | What | Needed by | Status |
|---|---|---|---|
| **U7** | Core library desugaring in the Android `:app` module | E3: `flutter_local_notifications` requires it **even without scheduling**, so #6948 v1 must solve it | **landed** at the pin `08b89cce5` (#445) with E3: an extension's `flet-extension.toml` sets `[android] gradle_dependencies` and `[android.compile_options]`, and `flet-notifications` turns desugaring on ([flet-dev/flet#6999](https://github.com/flet-dev/flet/pull/6999); §4.1, §5.10, [#293](https://github.com/ndonkoHenri/pycon-us-flet/issues/293)); no interim existed, since nothing ships the plugin before #446 |
| **U6** | Extra Android `<queries>` entries | E4; `can_launch_url` (INFO-14, which avoids it) | **landed** at the pin `a9ef26fdb` (#1005): `[tool.flet.android.queries]`, [flet-dev/flet#7031](https://github.com/flet-dev/flet/pull/7031). The app uses it only with E4 |
| **U12** | Configurable iOS deployment target | A pod needing more than iOS 15 | **not needed**: pod minimums are 11.0–13.0 (§6) |
| **U13** | App-level `PrivacyInfo.xcprivacy` | ITMS-91053 in the S5 TestFlight upload | only if S5 reports it |

### 1.2 Deep links: no gap

Deep links (NEW-07, D-21) use what exists: the common `[tool.flet.deep_linking]` table, which `flet build` resolves per key for Android and iOS after any per-platform table (`get_deep_linking()`, `CLI/commands/build_base.py:2801-2855`; `flet-dev/flet#6953`, fixing `flet-dev/flet#6951`, merged into `flet-1.1.0` and in the pin since `68a4b326c`), and the template's custom-scheme intent filter (`TPL/android/app/src/main/AndroidManifest.xml:40-48`) and `CFBundleURLTypes` entry (`TPL/ios/Runner/Info.plist:74-88`). Both register nothing unless `scheme` resolves (`scheme` and `host` until `a9ef26fdb`, `flet-dev/flet#7031`); iOS registers the scheme alone, with the host as the entry's `CFBundleURLName`. We set **one common table** (D-269):

```toml
# pyproject.toml (P2-24, #384). The values are the app identity's (D-452).
[tool.flet.deep_linking]
scheme = "confcompanion"
host = "app"
```

Reminder taps (E3) reuse the same paths, so a notification and a link both land on "root with the target pushed" (D-21); E3 hands over the launch tap before its first answer, given an `on_tap` set in the constructor (F246, D-396). Landing itself needs nothing new; what was open when a warm link comes is U89 (#516): the app closes dialogs and sheets first (D-291).

### 1.3 Cut or noted

**Cut** (D-98), each with the reason:

| Id | Item | Why cut |
|---|---|---|
| E5 | HTML rendering control | S3 showed `core/html_md.py` → `ft.Markdown` covers both feeds with no text change (D-114, D-117); §4.4 stays as a record |
| E6 | `flet-slidable` | Swipe-to-favourite is dropped (SCHED-11); a visible star replaces it (D-30) |
| U5 | `[tool.flet.ios.entitlement]` | It served push (`aps-environment`) and PSF credential sharing. Local notifications need no entitlement |
| U8 | Android meta-data / string resources | It served `asset_statements` for us.pycon.org credential sharing (NATIVE-07, dropped) |
| U11 | Offline service worker for `flet build web` | No web target (D-08) |
| U14 | Verified App Links / universal links | They need the PSF domain (D-21) |

**Noted, not scheduled.** These are small gaps the UX studies, the architecture and the tooling checks raised. Each has a working interim. D-98 lists seven as later candidates (U19..U25); the rest get an id only when a feature needs them, and the last five are small fixes the owner can file directly.

| Gap | Interim | Possible upstream piece |
|---|---|---|
| `Theme.platform` (U19, D-98) | Pin the iOS-adaptive defaults by hand: bundled font, `center_title=False`, Material back arrow (D-10) | `Theme.platform` |
| Contrast level / scheme variant | Hand-authored high-contrast overrides (D-23) | `Theme.contrast_level`, `color_scheme_variant` |
| `Theme.color_scheme` overrides reach `ThemeData.colorScheme` but nothing derived from it: `parseTheme` builds `ThemeData` from the seeded scheme and applies the overrides with `copyWith`, and parses `system_overlay_style` and the sub-themes against the seeded scheme, so the page stayed white under HC's cream bars (U64, D-265, #483) | `build_theme()` names `scaffold_bgcolor`, `canvas_color`, `card_bgcolor` and `divider_color` from the scheme, and HC's overlay names its navigation-bar hex | Build `ThemeData` from the final scheme (`DART/utils/theme.dart`, `parseTheme`) |
| A View without an `AppBar` takes the theme's status-bar style, and neither `View` nor `AppBar` has a `system_overlay_style` of its own, so a brand-coloured screen in a light scheme gets dark status-bar icons, 1.9:1 on Welcome's purple (U85, F105, D-287, [#509](https://github.com/ndonkoHenri/pycon-us-flet/issues/509)) | Welcome's `status_bar()`: a toolbar-less `AppBar` under a `Container` whose theme holds only a white style, the frontmost region at the status bar's middle | `View.system_overlay_style` (and `AppBar`'s) |
| `TextStyle.font_features` | Roboto, whose digits are tabular (D-26) | `font_features` |
| Bottom-sheet detents, non-modal sheet | Fixed-height `BottomSheet`; a positioned `Card` for the booth card | Detents / persistent sheet |
| Secure screen (`FLAG_SECURE`, iOS snapshot blur) for staff PII (U270, [#786](https://github.com/ndonkoHenri/pycon-us-flet/issues/786)) | `ScanScreen(clear_after=, clear_in_background=)`: the CoC result clears 15 s after it shows and on `pause`, its email hidden until revealed (#762); the clear may land after the OS snapshot | A `page` flag, applied natively (Android `FLAG_SECURE`, an iOS cover while inactive) |
| `RefreshIndicator`'s `finish_refresh` times out, with an exception no handler can catch and the full-screen error, when the indicator is in Python's index but its widget is disposed, as on a `TabBarView` page that has left (U285, F299, [#1020](https://github.com/ndonkoHenri/pycon-us-flet/issues/1020)) | One indicator around the `TabBarView`, `handle_nested_scrolls=True`, which stays mounted (`pullable(..., nested=True)`, D-449) | Don't raise when the widget isn't mounted: its `dispose` already ended the refresh |
| `ft.Markdown` always adds LaTeX syntax, so `$…$`, `( … )` and `[ … ]` in text render as math (U21, D-117, F27) | Escape text with numeric character references (D-115); open-space Markdown passes through unescaped | A flag (or extension-set entry) that turns LaTeX on, off by default; `DART/controls/markdown.dart` |
| A partial `MarkdownStyleSheet` replaces the theme's text styles instead of merging; links default to `Colors.blue` (U22, D-117, F28) | One app style sheet whose text styles all name their colour (D-116) | Merge given styles over the theme-derived ones; links and block quotes from the colour scheme; `DART/utils/markdown.dart` |
| A `NavigationBar` lives on its `View`, so with one View per drill level it moves with every pushed page (U23, D-149) | The bar on tab roots only (D-144) | A shell that keeps one bar outside the `Navigator` while `manage_views` Views push and pop, like go_router's `ShellRoute`; `FLET/components/router.py` and the Dart page |
| A replaced session is closed but not unmounted: effect cleanups don't run and effect tasks keep running (U24, D-149, F30) | `page.on_close` sets `svc.closed`, which every long-running loop checks (D-147) | On close, unmount the component tree (run cleanups, cancel effect tasks) and stop rendering after `detach`; `FLET/messaging/session.py`, `flet_dart_bridge_server.py` |
| `Page.on_platform_brightness_change` hands the handler a plain `ControlEvent` (the brightness name as `data`), not the typed `PlatformBrightnessChangeEvent`; and Flet removes its boot screen when the page arrives, before `main()`'s first patch, so the default View shows for a frame (U25, D-161, F35, F36) | Read `page.platform_brightness` in the handler; `ft.run(main, before_main=...)` gives the default View the boot colour | Send `{"brightness": name}` from `flet_backend.dart`; keep the boot screen until the first patch after `main()` (`DART/flet_backend.dart`, `FLET/messaging/flet_dart_bridge_server.py`) |
| `NavigationBarDestination.label` is a plain string: a label that wraps at large text (Flutter clamps labels at 1.3x) is start-aligned and raises its icon; no identifier on the destination either (D-167, #163, #164) | Keep the label; accept the wrap, which never clips (D-167) | A label control or `label_text_align`/`max_lines`, and an identifier, on `NavigationBarDestination` (#163) |
| iOS Reduce Motion does not shorten Flutter's own animations: Flutter runs `AnimationController`s at 5 % only under `disable_animations`, which Android's Remove animations sets and iOS never does, so Material's 200 ms text-style tween, radios, ripples and the Cupertino page slide keep their length (U26, D-173, #179) | The app's own durations go through `prefs.motion_ms()`, and the theme crossfade stays so that text and surface change together (D-173); the rest is short and user-triggered | Apply Flutter's reduced-motion behaviour on iOS too: a page option (or Flutter reading `reduceMotion` beside `disableAnimations`) so `AnimationBehavior.normal` controllers shorten there as well |
| serious_python (5.0.0; 6.0.1 at the pin `08b89cce5`, same paths, #445) stages each build's Python app inside its plugin folder in the shared pub cache (iOS `dist_ios/app` and the Swift package's `Resources/app`; Android `src/main/assets/app.zip`), so two builds that overlap on one Mac can ship each other's Python, silently (U28, D-176, #176, #185) | Every `flet build`, `flet debug` and `flet test` that may overlap another runs with `PUB_CACHE=$PWD/build/pub-cache`, an APFS clone of `~/.pub-cache`, and each build is checked against `build/python-app` ([`development.md`](development.md) §5.8) | Stage per Flutter project: Android under the plugin's Gradle build directory, iOS outside the plugin package or in a per-project copy; at least fail the build when the bundle differs ([flet-dev/serious-python#255](https://github.com/flet-dev/serious-python/issues/255)) |
| A Flet pin does not pin the bundled CPython patch: flet-cli passes only `SERIOUS_PYTHON_VERSION` (the minor), and serious_python 6.0.1 takes its platform packages with carets, so builds at `08b89cce5` ship whatever the newest `serious_python_*` 6.x says (6.1.0: python-build `20261027`, CPython 3.14.10, where flet-cli's manifest says 3.14.8) (U229, #700, #702). At `22a6dcb16` (#805) flet-cli's manifest and serious_python 6.1.2 agree again on `20261027` (3.14.10), and at `a9ef26fdb` with 6.1.3 (#1005), but the carets remain | We take the patch releases; the minor holds and the ABI is the same. `build/flutter/pubspec.lock` and About this app show what a build ships ([`development.md`](development.md) §2.1) | serious_python pins its platform packages exactly, or flet-cli passes `SERIOUS_PYTHON_FULL_VERSION` and `SERIOUS_PYTHON_BUILD_DATE` from its manifest (#702) |
| A scrollable that leaves the tree loses its offset: `TabBarView` keeps nothing of a page it no longer shows, and Flet's `ScrollableControl` keys its widget with a `ValueKey`, not a `PageStorageKey`, so a day list swiped back to starts at the top (U29, D-192, #86) | The Schedule keeps each day's scroll end in `ViewMemory` and puts it back with `scroll_to(offset=..., duration=0)` once the switch has settled; the day slides in at its top, then jumps (D-192) | A `PageStorageKey` from the control id on scrollables (`DART/controls/scrollable_control.dart`, `list_view.dart`), so Flutter's page storage restores the offset; or a `keep_alive` on `TabBarView` pages |
| `TextField` had no `text_input_action`, so the keyboard's action key was always Done (Android ✓, read "Done" by TalkBack) and a search field could not show Search (U30, D-193, #221) | None since #807 (D-450): `SearchField` passes `TextInputAction.SEARCH` whenever it has an `on_submit` (search), filters keep the default Done, and Sign in's email field shows Next | `TextField.text_input_action` (Flutter `TextInputAction`), with its parser in `DART/utils/form_field.dart`: [flet-dev/flet#6962](https://github.com/flet-dev/flet/issues/6962). **Landed** at the pin `22a6dcb16` (#805) as `TextField.text_input_action: Optional[TextInputAction]` ([flet-dev/flet#7021](https://github.com/flet-dev/flet/pull/7021); `FLET/controls/material/textfield.py:842`); adopted by [#807](https://github.com/ndonkoHenri/pycon-us-flet/issues/807) (D-450) |
| A `TextField` cannot keep the focus on submit on iOS: Flet passes no `onEditingComplete`, so Flutter unfocuses it on every Enter, and only Android has a `text_input_action` that stops it (U254, F274, #749) | The scan field sets `TextInputAction.UNSPECIFIED` (#830): on Android the focus and the soft keyboard stay across submits. iOS still unfocuses, so the scan screen keeps its refocus calls (D-416) and typing and HID scanning go on, with the keyboard dipping and coming back within about 0.4 s. After a pin with the property, the scan field keeps its focus on both and can drop the refocus calls. |
| On iOS, `SemanticsService.announce_message()` never returns while VoiceOver (or any accessibility client, such as a UI test) is on: Flet awaits the reply of `SystemChannels.accessibility.send()` with no timeout, and iOS's accessibility bridge never replies (U256, F276, #741, #753) | `ui/semantics.py`'s `announce()`, which every announcement goes through, waits for the answer at most `ANNOUNCE_WAIT_S` (0.5 s), so the scan screen's next scan is not blocked and no caller parks; each unanswered call leaves one pending entry in the session's method calls | The Dart side returns at once after `sendAnnouncement()` is started (not awaited), or `announce_message()` takes a `timeout`; then the bounded wait goes |
| No Flet scrollable can be as tall as its content in a bounded space: a scrolling `Column` is at least as tall as the room it is given (the `_InnerConstraintsEnforcer` of #6450, `DART/controls/scrollable_control.dart`), and a `ListView` shrink-wraps only when its height is unbounded (`DART/controls/list_view.dart`), so a `BottomSheet(scrollable=True)` whose content scrolls takes the screen's height (U32, D-195, #238) | The Schedule's filter sheet takes the screen's height, its title on top and its button pinned at the bottom, the chips scrolling between them (D-195) | A `shrink_wrap` on `ListView` and a scrolling `Column` that does not enforce the parent's height as its minimum (or an option for it) |
| Flet takes a system pop (the Android Back, and VoiceOver's escape on iOS, both `popRoute`) before Flutter's Navigator and pops a top View that can pop and has no `on_confirm_pop` by itself, so one Back closes a dialog, picker, sheet or menu open over the View **and** pops the View (U33, F46, D-208, #235, #259) | Every pushed View declares an `on_confirm_pop` that confirms (`AppScaffold`'s `let_pop`): with a handler, Flet leaves Back to `Navigator.maybePop()`, which closes the topmost route first (D-208) | Return `null` from `_handleSystemPopRoute()` while the Navigator's top route is not a page (`DART/controls/page.dart`); the analysis and a minimal repro in #259, and [flet-dev/flet#6964](https://github.com/flet-dev/flet/issues/6964) |
| A route change leaves the dialogs, sheets, pickers and menus open over the old top View open over the new one; a dialog or sheet drawn again in the new View has lost its route, so a close after the change closes nothing; pickers only open; a popup menu has no close; no public list of a page's dialogs (U89, F109, D-291, #516) | `ui/modals.py` closes the open dialogs and sheets in `page._dialogs` before the Router sees the change and waits for their dismissal; SnackBars and Banners stay; pickers and menus stay for Back (D-291) | Pop the Navigator's pageless routes when a new route comes (`_routeChanged()` in `DART/controls/page.dart`), or keep each dialog's route on its control, give the pickers a close branch and `PopupMenuButton` a `close()`, and a public `page.dialogs`; the analysis, a repro and a draft in #516 |
| Flet's `Semantics` has no `names_route`, so only an `AppBar` title can name a route (Android only), and a detail page whose level-1 heading is in the body has none; at the pin TalkBack said no route name for a titled bar either, on a push or a link (U108, F128, D-310, #538) | The page reads as Flutter builds it: focus on Back, then the bar's actions, then the heading, one Headings-navigation gesture away (ux.md §9) | `Semantics.names_route` passed as Flutter's `namesRoute` (`DART/controls/semantics.dart`, `FLET/controls/core/semantics.py`), and why a named route is not said in a Flet app; then each detail heading sets it |
| `TabBarView` has no `physics`: its only way to stop swiping is `disabled`, which every page's controls inherit, and its `PageView` takes a horizontal drag before an `InteractiveViewer` does, so a zoomed plan in a page loses its horizontal pans to the swipe (U110, F130, D-312, #560) | The Map's panes sit under a `TabBar` with no `TabBarView`: the selected pane alone, nothing to swipe (D-312) | `TabBarView.physics` (`ScrollPhysics`), mapped to Flutter's `TabBarView.physics`; `disabled` keeps its meaning |
| A component under a skipped memoised component keeps a dead `_parent_component`, so when it re-renders by itself (state, an effect, a store) it finds no context; and `Session.__updates_scheduler()` does not catch an update's exception, so one failed render stops every later re-render of the session, silently (U111, F150, #597) | Under a memoised component, values only: no component there holds state, runs an effect or subscribes to a store. The Schedule calls `use_strip()` itself and its day lists draw the `Strip` value (D-345) | Re-point the reused output's `_parent_component` when a memo is skipped (or resolve contexts through the migrated state's owner); catch and report an exception per control in the updates loop |
| A toggle whose state Python sets (`Semantics.toggled`, `IconButton.selected`, `Chip.selected`) changes only after the round trip, while Flutter's tap feedback sends Android's `TYPE_VIEW_CLICKED` at once, so TalkBack can say the old state after a tap; `Switch` and `Checkbox` flip on the client and are not affected (U153 #605, F173, D-355, #342) | The star sets `enable_feedback=False` (no click event) and, with a screen reader on, the favourites SnackBar says "Added to My schedule" or "Removed from My schedule" | An opt-in client-side flip of `IconButton.selected` (or `Semantics.toggled`) at the tap, as `Switch` flips its value |
| `scroll_interval` throttles a list's scroll start and end as well as its updates, so an end within the interval of the one before never reaches Python and a jump that moved the list says nothing (U162 #619, F182, D-364, #600) | The Schedule's put-back waits `END_GAP_S` after the list's last end before each jump (`PlaceKeeper.ended_apart()`) | Throttle only `update` and `overscroll`; always send `start`, `end` and `user` |
| Multi-weight families in `page.fonts` (one static file per family, no weights) (U20, D-98) | Declare the Roboto 400/500/700 family through `[tool.flet.flutter.pubspec]` (F18), verified in S5 (D-26) | `page.fonts` accepting a family with weighted files; schedule it only if S5 shows the pubspec route fails |
| A cleanup returned by a sync `use_effect` setup is replaced by `None` at the component's next render, so it never runs, and an async setup's task is not cancelled on unmount without a `cleanup=` (U27, F39, #182) | None since [#672](https://github.com/ndonkoHenri/pycon-us-flet/issues/672) (D-387): the no-op cleanups that made Flet cancel a task (`stop_ticks` and the screens' own) are gone, and a sync setup may return its cleanup; `tests/test_flet_effects.py` pins both | Keep the returned cleanup apart from the `cleanup=` argument (`FLET/components/hooks/use_effect.py`, `FLET/messaging/session.py`); [flet-dev/flet#6963](https://github.com/flet-dev/flet/issues/6963). **Landed** at the pin `08b89cce5` (#445): [flet-dev/flet#6983](https://github.com/flet-dev/flet/pull/6983) keeps the returned cleanup, and [flet-dev/flet#7005](https://github.com/flet-dev/flet/pull/7005) runs it and `cleanup=` both and cancels a running async setup on unmount without either (`EffectHook.has_lifecycle_work()`). Adopted by [#672](https://github.com/ndonkoHenri/pycon-us-flet/issues/672) |
| An `async def` `use_effect` cleanup is cancelled before it starts on a dependency change (F2) | None since [#672](https://github.com/ndonkoHenri/pycon-us-flet/issues/672): a cleanup may be `async` (D-70 rule 3 as amended by D-387) | In the setup branch, cancel only the previous setup task, so async cleanups run. **Landed** at the pin `08b89cce5` (#445): [flet-dev/flet#7005](https://github.com/flet-dev/flet/pull/7005) cancels only a still-running setup task and finishes every cleanup, async ones included, before the setup runs again. D-387 relaxes D-70 rule 3 |
| `flet debug android\|ios --show-devices` exits with "Device ID must be specified": `check_device_id()` runs before the `--show-devices` branch (flet-cli `commands/debug.py:108-110`) | `flet devices` | Run the device check after that branch |
| No public way to bind `ft.context.page` outside a session: `_context_page` (`flet/controls/context.py:212`) is private, and Flet's own pytest plugin sets it directly (#160) | `tests/fake_page.py`'s `bound()` sets the private ContextVar, checked against the pin | A context manager such as `ft.context.bind_page(page)` that the pytest plugin uses too |
| `flet_app` docstring (`flet/pytest_plugin.py:132`) says the bound page is the tester session, but in device mode `flet_app.page` raises `RuntimeError` | Flows use `flet_app.tester` only ([`testing-and-quality.md`](testing-and-quality.md) §5.1) | Fix the docstring |
| `NavigationBarDestination` has no identifier; and the `Semantics.identifier` docstring (`flet/controls/core/semantics.py:42-43`) says it forces its own node, which the Dart control does not do (#163) | Each destination's icon is an unlabelled `Semantics(identifier=...)` that Flutter merges into the destination's node (D-166); pin bumps re-check it ([`development.md`](development.md) §2.2) | An `identifier` on the destination (and the rail's); align the docstring with the Dart |
| Flet's `Semantics` has no `link_url`, and Flutter's text spans carry none, so TalkBack calls every link a button: link rows (`Semantics(link=True)`) and Markdown links alike (U31, F41, D-197, #230) | Each link is its own named, operable node; rows say "Opens in browser" (D-182) | `Semantics.link_url` (Flutter's `SemanticsProperties.linkUrl`) for rows; for Markdown links, a URL on Flutter's text-span semantics (a Flutter change) |
| Flet's `Semantics` always sets Flutter's `enabled` (`DART/controls/semantics.dart:23`), so in a `MergeSemantics` around a disabled control the merged node reads as enabled, and a bare identifier around a `TextField` is an empty node of its own (U34, F42, F50, D-214, #273) | `named()` gives its `Semantics` the control's `disabled`; identifiers on buttons and fields are merged; the fake clock field, whose picker a merge would swallow, keeps a bare identifier (D-214), and the folds carry theirs on their merged headers, not around them (D-354); a decoration leaves itself out (`Image(exclude_from_semantics=True)`, `Text(semantics_label="")`) rather than sit in a `Semantics(exclude_semantics=True)`, which is an empty, focusable node (F81, D-262) | `enabled: control.disabled ? false : null`, so a `Semantics` claims an enabled state only when it is disabled |
| `RemoteTester`, the device tester of `flet test`, cannot drag (so a UI flow cannot scroll) and cannot press the keyboard's action key (so it cannot close the keyboard that `enter_text` opens): the host `Tester` has `drag` and `drag_from` and `flet_integration_test`'s `FlutterTester` implements both, but `RemoteWidgetTester._handleCommand` routes neither (`packages/flet_integration_test/lib/src/remote_widget_tester.dart:114-165`), `RemoteTester` has no method to send them, and no command reaches Flutter's `TestTextInput.receiveAction` (U35, F21, D-223, #288) | Flows tap rows near the top of a list and reach the rest through day tabs, search's scopes and search; About this app opens by its deep link, and the iOS flows run on an iPhone 17 Pro Max simulator, whose Developer screen shows Refresh now (D-478); the Android AVD keeps its on-screen keyboard down; Developer's feed URL field keeps Apply in sight above the keyboard (D-223) | Route `drag` and `drag_from` in the device protocol; add `scroll_until_visible(finder, ...)` over Flutter's `WidgetTester.scrollUntilVisible`, so a flow names the row it wants rather than a pixel; add `receive_action(action)` over `TestTextInput.receiveAction` |
| `RemoteTester.take_screenshot` works once per launch on Android: `FlutterWidgetTester.takeScreenshot` converts the Flutter surface to an image on every call (`packages/flet_integration_test/lib/src/flutter_tester.dart:85`), and Flutter's debug-only assert stops the second conversion in a test ("Surface already converted to an image") (U280, F300, [#884](https://github.com/ndonkoHenri/pycon-us-flet/issues/884)) | Android goldens feed `adb exec-out screencap -p` bytes into `assert_screenshot`, with the status bar frozen by SystemUI demo mode; iOS keeps `take_screenshot`: both ran on devices in #840 (testing-and-quality.md §6, D-495) | Convert once per tester, then pump before each capture; the analysis, a repro and a draft diff in #884 |
| iOS's launch screen draws the `LaunchBackground` swatch as if its sRGB numbers were Display P3 (`#680579` reads `#72007e`), while Flutter's in-app splash view, built from the same storyboard until the first frame, and every Flutter frame read it right; one swatch cannot satisfy both, so `[tool.flet.ios.splash]` only moves the shift (`flet_platform_assets/_splash.py:228-263`, U281, #880, [#950](https://github.com/ndonkoHenri/pycon-us-flet/issues/950)) | None: both platforms keep `#680579`; the launch screen reads `#72007e` on an iPhone 17 simulator, unchecked on a device (development.md §3.3) | A template that shows the launch screen or the Flutter frames only, not both renderings of the swatch |
| When a patch adds controls, `DiffBuilder._configure_dataclass` makes one generator call per field of each new control, scalars and `None` included (`FLET/controls/object_patch.py:1597`), about 75 calls a control (U282, [#966](https://github.com/ndonkoHenri/pycon-us-flet/issues/966)) | None needed: the cold start's cost is recorded (D-474) | Skipping a scalar field before the call, measured from a check-only monkeypatch: 33 % off the Schedule's two renders on the host; the emulator's first rows did not move |
| A `PopupMenuItem` with an `icon` and a text `content` lays them out as `Row([icon, SizedBox(width: 8), content])` with no `Flexible` (`DART/utils/popup_menu.dart:31-36`), inside a menu at most 280 dp wide, so at large text the label runs off the menu's edge instead of wrapping (U36, F47, D-233, #260, #308) | Every overflow item is `ui/menus.py`'s `menu_item()`: no `icon=`, a `ListTile` (the icon as `leading`, the label as the wrapping `title`) as the item's content (D-233) | `Flexible(child: itemContent)` in that `Row`; the analysis, a repro and a draft diff in #308 |
| Flet's `Semantics` has no `accessibility_focus_block_type` (Flutter's `accessibilityFocusBlockType`, `semantics.dart:127` at the pin's Flutter), so a live region that holds words is a stop in TalkBack's linear navigation (U41, D-241, F61, #322) | The Schedule's landing note empties 5 s after it spoke (`SAID_S`, D-241) | Pass `accessibilityFocusBlockType` through `SemanticsControl` (`DART/controls/semantics.dart`) with a Python enum field |
| A control with an `ft.ScrollKey` gets a new `GlobalKey` at each build (`DART/controls/control_widget.dart:34-38`), so Flutter mounts it and everything under it again whenever an ancestor rebuilds, with new semantics nodes: a row under a keyed box lost the screen reader's focus after Back from a pushed View (U42, F62, D-242, #303, #321) | `ui.scrolling.anchored()` puts every `ScrollKey` on an empty 0 dp anchor above its item, so only the anchor is mounted again (D-242) | Keep one `GlobalKey` per control for its `ControlWidget`'s lifetime (a `State` that owns it), and make a new one only when the scroll key's value changes |
| Flet applies a button's `tooltip` around the whole button (`_tooltip()` in `DART/controls/base_controls.dart`), outside the button's own semantics node, where Flutter's `IconButton(tooltip:)` puts it inside: the tooltip is a node of its own and the button under it is unnamed, read "Button" by TalkBack; the same for `FloatingActionButton`, `Button` and `PopupMenuButton` (U37, F55, D-234, #274, #317) | Every button whose tooltip is said is merged with it: `merged()` (`ui/semantics.py`) or, with an identifier, `named()`; the Schedule's "Now" button, which a View takes bare, keeps its tooltip out of the semantics and says it in its label's `semantics_label`; `tests/test_tooltips.py` scans for a button left out (D-234) | In each button control, apply the tooltip inside a `MergeSemantics` of the button (as Flutter's buttons do) and skip it in `LayoutControl`; the analysis and a draft diff in #317 |
| A controlled `TextField` has no guard against an echo: a keystroke's re-render that runs after the next keystroke's report sends the older text, and Flutter puts it in the field; nothing tells an echo apart from a change the program made (U43, F63, D-243, #319) | `use_field_query()` builds the field from what Flutter last reported, through one `Ref` kept for the screen's life, so typing sends nothing; only the initial text and a Clear are sent. Keys reported between a Clear's tap and Flutter's answer to the focus request that follows the Clear's render are dropped, and the empty text is sent again (D-243). Still open: a key typed in the one frame before Flutter applies the empty text | An edit count that Flutter sends with each report and Python returns with each `value`, so Flutter drops an older edit's echo (`DART/controls/textfield.dart`, `FLET/messaging/session.py`) |
| Flet exposes neither Flutter's `LicenseRegistry` nor `showLicensePage` (nothing in `DART` or `FLET` at the pin), so an app cannot show the notices Flutter bundles from every Dart package, plugin and the engine (`NOTICES.Z`: 1,646 entries over 205 names in our iOS build); that registry has nothing of the Python side (CPython, the app's Python packages) either (U51, INFO-03, #371) | About this app's Licences page lists the app and its direct components, each opening its full text offline (#442) | `await page.show_license_page(application_name=..., application_version=..., application_legalese=..., licenses=[...])`, a case beside `get_device_info` in `DART/controls/page.dart` that calls `material_ui`'s `showLicensePage` with Flet's Navigator; the optional `licenses` are Python-side entries served by one `LicenseRegistry.addLicense` collector; the analysis, a repro and a draft diff in #371 |
| `InteractiveViewer.zoom()` scales about the content's top-left corner, not the viewport's centre as a pinch does, and never re-clamps the translation, so a zoom-out after a pan can leave the viewport blank; `pan()` moves in content units, though its docstring says logical pixels (`DART/controls/interactive_viewer.dart:150-169`, `:370-422`; U56, F76, #472) | The zoom buttons pan back to the centre after each `zoom()`: `get_transform()`, then `pan()` by the difference in content units, which `pan()` clamps (#388; S7, #361, checks the frame in between). A resize (a rotation) re-clamps nothing either, so `use_zoom()` zooms down to the new maximum and pans back inside the new bounds (`into_bounds()`, #588) | Translate after the scale so the viewport centre's scene point stays put, through the clamping `_matrixTranslate()`, as Flutter's pinch and wheel do; fix `pan()`'s docstring. The analysis, a repro and a draft diff in #472 |
| `ft.Image` with an SVG asset file ignores `exclude_from_semantics`: `buildImage()` calls `getSvgPictureFromFile()`, which takes no such parameter (`DART/utils/images.dart:197`, `DART/utils/images_io.dart:36-52`), so flutter_svg wraps the picture in `Semantics(image: true)`, whose flag merges into the enclosing node: a link row with a brand mark read as an `ImageView`, not a button (U63, F83, D-264, #475) | `ui/brands.py`'s `brand_icon()` sends the bundled SVG's bytes, whose branch passes `excludeFromSemantics` (D-264) | Pass `excludeFromSemantics` through `getSvgPictureFromFile()` (and its web stub); the analysis, a repro and a draft diff in #475 |
| A Flet app cannot open a file it made in the app that handles its type: `UrlLauncher.launch_url` of a `file://` URL raises `FileUriExposedException` on Android (url_launcher sends `ACTION_VIEW` with the URI and no grant) and opens nothing on iOS, a `data:` URL opens nothing, and `Share.share_files` sends `ACTION_SEND`, which Google Calendar does not take, so no Flet call reaches Calendar's `.ics` import (U71, F91, D-272, #364, #487) | Android saves the file with `FilePicker.save_file` and says to open it from Files; iOS reaches its calendar sheet through a loopback server and the in-app browser (D-272) | An `open_file(ShareFile)` (on `Share`, which already writes bytes to a file): on Android `ACTION_VIEW` with `setDataAndType()` on a `FileProvider` URI (share_plus's `ShareFileProvider`, `${applicationId}.flutter.share_provider`, already in every app) and `FLAG_GRANT_READ_URI_PERMISSION`; on iOS `UIDocumentInteractionController`; the analysis in #487 |
| `UrlLauncher.launch_url` never says whether anything opened: url_launcher's `launchUrl()` returns `false` when no app takes the link (url_launcher_ios's `.failure`), and Flet's `openWebBrowser()` awaits it and drops the result (`DART/utils/launch_url.dart:29-48`, `DART/services/url_launcher.dart:28-35`), so a `tel:` or `mailto:` tap on an iOS simulator or an iPad opens nothing and raises nothing (U79, D-182, D-281, #498) | Copy beside every phone and email row (`copy_contact()`, D-182); "Couldn't open the link" only when the launch raises | Return the `bool` from `openWebBrowser()` and from Python's `launch_url()`; the analysis in #498 |
| `flet-permission-handler` has no `should_show_request_rationale()`, so on Android a `DENIED` notification status can't be told from "off in system settings": `permission_handler_android` reads `PERMANENTLY_DENIED` only after two refusals of the app's prompt (U239, F259, #715) | `Scheduler.request_permission(asked=...)`: a refusal after an earlier request that still reads `DENIED` reads `refused` for the session, so Settings offers Open settings beside Allow notifications after one tap (#712) | The service's `should_show_request_rationale(permission)`, `permission_handler`'s `Permission.shouldShowRequestRationale` |
| A `ListView` keeps its pixel offset when its `controls` change, not the rows in view: its `ListView.builder` passes no `findChildIndexCallback` (`DART/controls/list_view.dart:138`), so a keyed item at a new index takes that index's old offset, and Python gets neither the first visible item nor an event when the content's extent changes (U50, F70, [#345](https://github.com/ndonkoHenri/pycon-us-flet/issues/345)) | The Schedule measures its day lists and puts each one's place back by key after a text-size or filter change (`screens/schedule_place.py`, `core/list_place.py`; D-331, D-371); the app's other lists keep the offset | `findChildIndexCallback` from the items' keys, and an opt-in scroll anchor (for example `ListView(keep_place=True)`), or at least the first visible item's key with each scroll end; the anchor would let both modules go |
| A frozen diff mixes up retained controls, the instances a hook keeps or a parent passes down: an unkeyed one is paired by position (`("pos", n)`, `FLET/controls/object_patch.py:897`), and `dst._migrate_state(src)` (`:1159`) gives another live control its id, or two components one state; a retained child in a single-child field is skipped (`if old is new`, `:1380`) and keeps a dead `_parent`, so its `.page` raises (U163, [#622](https://github.com/ndonkoHenri/pycon-us-flet/issues/622)) | No `use_memo` or `use_ref` in `src/` holds a control or a component, and that stays so; the scan tools' buttons, which a parent builds and passes down, carry a `key` (`ui/tool_controls.py`, #770) | Match retained items by identity, never migrate state into another live control, and re-stamp a retained child's parent (the draft in #622) |
| An open `BottomSheet` can't be locked: `dismissible` is read once, as `showModalBottomSheet` runs (`DART/controls/bottom_sheet.dart:72`), so a later `dismissible=False` leaves the scrim and Back dismissing it; `AlertDialog`'s `modal` has the same shape (`DART/controls/alert_dialog.dart:113`) ([#782](https://github.com/ndonkoHenri/pycon-us-flet/issues/782)) | Swag pickup's sheet (`ui/swag_sheet.py`, #781) ignores a dismissal that arrives while it sends: the hand-out stays in progress and scanning stays paused until the answer settles it | A route whose barrier follows the control's current `dismissible`, and a `PopScope(canPop: dismissible)` around the content |
| Below Android 15 a packaged app is drawn under the status bar but not under the navigation bar: Android enforces edge-to-edge only from API 35, and the template's `MainActivity` is a bare `FlutterFragmentActivity` (`TPL/android/app/src/main/kotlin/{{ cookiecutter.kotlin_dir }}/MainActivity.kt`), so a transparent bar shows the window background, which a live dark-mode switch leaves in the old mode (F26, D-151, [#140](https://github.com/ndonkoHenri/pycon-us-flet/issues/140)) | The navigation bar takes the `NavigationBar`'s colour (`theme.py`'s `overlay_style()`, D-151), which Android 15 and later ignore | `enableEdgeToEdge()` in the template on every API level, once its effect on existing apps' insets is checked; then the bar goes back to transparent |
| Five `ft.Semantics` properties reach Flutter under names the Dart control never reads, so they do nothing: `on_tap` (its event is `tap`; Dart asks for `click`), `hint_text` (`hint`), `on_tap_hint_text` (`on_tap_hint`), `textfield` (`text_field`) and `focus` (`focused`) (`DART/controls/semantics.dart:31-55`, `FLET/controls/core/semantics.py`; [#187](https://github.com/ndonkoHenri/pycon-us-flet/issues/187)) | Nothing relies on them: a row keeps the tap action of the control under its label (`MergeSemantics`, #81), and a link's `OPEN_IN_NEW` icon says "Opens in browser" inside the merged node (#83) | One name on each side; Dart reading the Python names keeps the Python API |
| Flutter's Android bridge gives a text field no name below API 28: `BaseRoleConfigurator.configureLabelAndValue()` passes its label and hint only to `setHintText()`, behind `SDK_INT >= API_28` (`engine/.../io/flutter/view/BaseRoleConfigurator.java:355-359` in Flutter 3.47.8), and sets no content description on a text field, so on Android 7.0 to 8.1 every field of the app (Search, the staff tools' Badge code field, sign-in) reaches TalkBack as an unnamed edit box and its helper line ("Choose what to hand out") is not in the tree; seen with `uiautomator dump` on API 24, TalkBack itself not run, and flutter/flutter#194112 reports it (U283, #952, [#968](https://github.com/ndonkoHenri/pycon-us-flet/issues/968)) | None in the code: a label-only node beside each field would read the name twice from API 28, and needs the API level first. The scan screens' result panel (a live region) and Swag's named category chips still speak. `swag_pickup` asserts the helper line from API 28 and the chips' own state below it (`maestro/scripts/os_offers.js`) | Export the label on API 26 and later through `setHintText()`, the AndroidX compat path on 24 and 25, or the content description (flutter/flutter#194112) |
| Two `flet build`s starting at once with no cached template for their version can fail: `get_cached_template_zip()` downloads to one fixed `flet-build-template.zip.tmp`, so the second `os.replace` raises `FileNotFoundError` (`CLI/utils/template_cache.py:35-42`; two processes on one empty cache: 3 failures in 12 calls; U286, #1027) | After a bump, build once before parallel builds, or try again ([`development.md`](development.md) §2.2) | A temporary file of the process's own in that folder (`tempfile.mkstemp`) |
| `flet build` uses another patch of Flutter without a word: `find_flutter_batch()` falls back to the `flutter` on `PATH`, and `flutter_version_valid()` compares only major and minor (`CLI/commands/flutter_base.py:252-280, 482-494`), so every build asking for 3.47.8 ran on fvm's 3.47.7 (U284, #1004, [#1006](https://github.com/ndonkoHenri/pycon-us-flet/issues/1006)) | Flet's Flutter in `~/flutter` ([`development.md`](development.md) §2.2, step 3); `tools/setup_worktree.sh` says when it's missing | A line in `flet build`'s and `flet test`'s output when the patch differs |
| A service loses its listener when a client that stays open reconnects to a new server process and the service's id repeats: the new session's page is merged onto the old tree (`flet_backend.dart:415`), and `ServiceRegistry` compares ids only (`services/service_registry.dart:28`), so each call times out in 10 s and an app that awaits one at startup stays on the boot spinner (U287, #1038, [#1044](https://github.com/ndonkoHenri/pycon-us-flet/issues/1044)) | `R` in `flutter run` before each save, or to recover from the spinner ([`development.md`](development.md) §5.2, [`demo-script.md`](demo-script.md) beat 4) | Bind a service by the identity of its control as well as its id |

---

## 2. How the app lives with a gap

### 2.1 Capability constants (D-63)

An **extension** is used only when the app runs as a packaged build **and** the extension is bundled. `flet run --android/--ios` runs Python on the laptop with the companion app. The companion bundles only the first-party extensions registered in the monorepo's `client/lib/main.dart` (camera, permission_handler, secure_storage and others), so those work under `flet run`. It has none of the extensions this doc proposes, so it must never receive an E1/E3/E4/E5 control. The packaged build template sets `FLET_PLATFORM`, and `flet.utils.is_embedded()` checks that variable (`FLET/utils/platform_utils.py:70`, exists; F14). The companion app is therefore never "embedded", which gives exactly that. If the Flet team later adds the #6948 extension to the companion, the gate stays conservative but still correct.

```python
"""Optional extensions this build can use (D-63).

A capability is on only in a packaged build that bundles the extension.
The `flet run` companion app is never embedded, so it always gets the interim.
"""

import importlib.util

from flet.utils import is_embedded


def available(module: str) -> bool:
    """Return True when running packaged and `module` is importable."""
    return is_embedded() and importlib.util.find_spec(module) is not None


REMINDERS = available("flet_notifications")  # E3: the monorepo's flet-notifications (#6999), bundled since #446
SCANNER = available("flet_barcode_scanner")  # E1; proposed name
```

Rules:
- One `services/` module per capability imports the extension and owns its fallback: `services/reminders.py` (E3) and `services/scanner.py` (E1). Screens never import an extension.
- The extension is listed in `[project].dependencies` with an exact pin, in a dependency PR of its own (D-92) merged just before the PR that adopts it. `uv sync` installs it in the development venv too, which is harmless: under `flet run`, `is_embedded()` is False, so the capability stays off.
- The Developer screen (D-73) shows the constants read-only; nothing changes them at runtime. Interims are exercised in the companion app (never embedded) and by the unit tests.
- Each capability module has one unit test: when not embedded, it chooses the interim.

**Core gaps (U-items) get no runtime detection** (D-64). The app pins one Flet version (D-81). After the PR that pins a release with the piece, one PR swaps the interim for the real thing and deletes the interim (D-92).

### 2.2 Interims and tracking

- Every interim is usable, tested and honest, with no controls that do nothing. A missing capability is said in plain words, e.g. "Reminders aren't available in this build" (D-60). An interim is removed only by a tested dependency or pin change here, never because an upstream issue closed (D-64).
- Each item is an `upstream` issue here with the full analysis (what happens, the Flet source at the pin, a repro, the suggested fix). Agents never post in flet-dev or any other repository; the owner decides whether to take an item to Flet, and the issue links the flet-dev issue or PR once the owner has opened one (D-212). It goes in the milestone of the phase that needs it (D-89); items whose app need is "later" or "never" have no milestone until a phase adopts them. App issues that wait on it are `blocked`, and the interim ships meanwhile (D-97). Spikes S6 and S8 are `Spike:` issues labelled `test`, with verdicts in `docs/spikes/` (D-91).

### 2.3 Developing against an unreleased piece (D-81, F18)

The app takes Flet from PyPI at one exact version, so a piece is available once it's in a release, or a prerelease we move to ([`development.md`](development.md) §2.2, D-481). A first-party extension from the monorepo is listed in `[project].dependencies` at the family's version, and its Dart package comes in its wheel. Moving the version is its own PR (D-92).

A piece that isn't released yet takes the temporary route of §2.2, "When we need a fix that isn't released", and only with a release in sight.

- Listed without its version, `flet-notifications` now resolves to Flet's newest release (1.1.0 or later), which may not be the family's version, so it is pinned with the rest. While we pinned a prerelease it resolved to the unrelated PyPI `flet-notifications` 0.1.x (§6), because pip and uv skip prereleases unless the requirement names one (#6999 took that name at `08b89cce5`).

### 2.4 Generic upgrade steps (every item)

1. The piece is merged in flet-dev and in the Flet commit or release we pin. A separate PR bumps the pin (D-81, D-92) and says why. The swap follows in its own PR.
2. **Extensions:** a dependency PR adds the exact pin to `[project].dependencies` (§2.1); the adoption PR then adds the item's platform setup (its section below) and runs the item's device checks. The capability constant turns on by itself in packaged builds.
3. **Core items:** replace the interim at its call sites, delete the interim code and its tests, add tests for the new path.
4. Update this register (status), `PLAN.md` §6 if the priority table changes, and the matrix rows the item serves.
5. Close the `upstream` issue and unblock the app issues.

---

## 3. Rules for the new extensions (E1, E3 scheduling, E4, E5)

| Rule | Value |
|---|---|
| Home | The Flet team decides; likely next to the existing `flet-*` packages in the monorepo (D-99). First-party extensions are released with Flet and share its version (`flet-secure-storage`, `flet-permission-handler` and `flet-camera` are 1.0.4 on PyPI, like `flet`). |
| Clean room | Written from the wrapped package's pub.dev docs and Flet's own extensions. The GPL-3.0 `AyberkA0/flet-barcode-scanner` is never opened, and PRs say so (D-99). |
| Licences | All wrapped packages are BSD or MIT; re-check at every bump. |
| Dart pin | Exact (`mobile_scanner: 7.4.2`, not `^7.4.2`), as `flet-secure-storage` does with `flutter_secure_storage: 10.3.1`. |
| UI imports | `package:flutter/widgets.dart`, plus `package:material_ui/material_ui.dart` when Material is needed, with the same constraint as `packages/flet/pubspec.yaml` (`material_ui: ^1.6.0`). Never `package:flutter/material.dart` (monorepo skill `implement-flet-extension`, "Third-party Dependency Gate"). |
| Packaging | `[tool.setuptools.package-data] "flutter.<dart_pkg>" = ["pubspec.yaml", "lib/**"]`, as in `flet-secure-storage`. Add `"android/**"` only if the package must carry an Android module (§4.1). |
| Registration | `flet build` copies each bundled `flutter/<pkg>` and adds it as a path dependency (`CLI/build_base.py:2080-2175`). The app needs no pubspec edits. |

**Python patterns (exists).** Services (E3, E4) are `@ft.control("Name") class Name(ft.Service)`; visual controls (E1, E5) subclass `ft.LayoutControl`, like `flet_camera.Camera`. Events are `on_x: Optional[ft.EventHandler[XEvent]]` with `@dataclass class XEvent(ft.Event["Name"])`; payload fields must not reuse `ft.Event`'s `name`, `data` or `control`. Methods are `async def` wrappers over `self._invoke_method(...)`, so callers are `async def` (F1). Enum values are the Dart enum's `.name`. On the Dart side every `control.getX("prop", default)` repeats the Python default, which is never sent over the wire.

**The material_ui gate** applies to visual extensions (E1, E5):
1. Static: `lib/` imports no `package:flutter/material.dart`, and a reviewed list names the upstream widgets we instantiate.
2. Runtime: render the control in a plain Flet page on the emulator and the simulator, in every state reachable without hardware. The log must contain no "No Material widget found" and no `FlutterError`.
3. Upgrade guard: the resolved upstream version equals the pin (`pubspec.lock`).

**Tests, in the extension:** Python unit tests (defaults, serialisation, enums, `_invoke_method` mocked); integration with `flet test android|ios --device-id …` and `flet.testing.FletTestApp` (exists, F21); a short scripted device check for camera, alarms and reboot.

---

## 4. Extensions

### 4.1 E3: scheduled local notifications (priority 1)

| Field | Value |
|---|---|
| **Landed** | At the pin `08b89cce5` (#445): the `flet-notifications` extension, [flet-dev/flet#6999](https://github.com/flet-dev/flet/pull/6999), which fixes #6948 and holds both parts below. Dist `flet-notifications`, module `flet_notifications`, `@ft.control("Notifications") class Notifications(ft.Service)` with `show`, `schedule`, `periodically_show`, `cancel`, `cancel_all`, `cancel_all_pending`, `get_pending`, `can_schedule_exact_alarms`, `request_exact_alarm_permission` and `request_permissions` (`sdk/python/packages/flet-notifications/src/flet_notifications/notifications.py`), over `flutter_local_notifications` ^22.3.1 and `timezone` ^0.11.0. The platform setup D-220 asked for ships with it: the receivers and `RECEIVE_BOOT_COMPLETED` in the extension's Android manifest, U7's desugaring in its `flet-extension.toml`, and the iOS delegate in the template's `AppDelegate.swift` (under `#if canImport(flutter_local_notifications)`). #446 added it to the build, and `capabilities.REMINDERS` now probes `flet_notifications` (it probed #6948's proposed `flet_local_notifications`); #447 schedules with it, which ends the interim below in packaged builds. The companion app keeps the interim (D-63). |
| Serves | NOTIF-05 (fixed conference moments), NEW-05 (reminders before saved sessions), NOTIF-01 and STORE-10 (reminder settings), NOTIF-06 (permission in context), NOTIF-10 (the permission card), DEV-06 (test reminder), NATIVE-06 (declarations). Taps open NEW-07 paths. |
| Interim (D-60) | • Settings › Reminders shows "Reminders aren't available in this build", with no live switches.<br>• Now's "Your next session" covers the app being open, and so does an in-app `Banner` with "Open" and "Dismiss" 10 min before a saved session.<br>• `.ics` with a `VALARM`: "Remind me" on session detail and "Add all to calendar" in My schedule (`core/ics.py`, D-62). |
| Upstream | Two parts:<br>(a) The official local-notifications extension from [flet-dev/flet#6948](https://github.com/flet-dev/flet/issues/6948), opened by Feodor Fitsner on 2026-10-10. Its v1 scope is `initialize`, `request_permission`, `get_permission_status`, `show`, `cancel`, `cancel_all`, `get_launch_details` and `on_notification_tap`. **Scheduled and periodic notifications are explicitly out of v1.**<br>(b) Our follow-up PR "scheduling", built on v1.<br>(c) Spike S6 ran the scheduling part of this scope and v1's initialize, permission, launch-details and tap members (not `show` or `cancel`), Android and iOS setup included, through a throwaway extension over the same plugin (`docs/spikes/06-reminders/`); D-220 records what it must carry. Written up for the owner in [#294](https://github.com/ndonkoHenri/pycon-us-flet/issues/294) (D-212). |
| Dart packages | `flutter_local_notifications` **22.3.1** (BSD-3; 2026-09-13; minSdk 24; iOS pod 13.0) with `timezone` **0.11.1**. Flet 1.1 (Flutter 3.47.9, AGP 8.13.2, default minSdk 24) meets every minimum. |
| Python package | Dist `flet-notifications`, module `flet_notifications`, class `Notifications` (#6999; #6948 had proposed `flet-local-notifications`). **On PyPI the name holds another author's 0.1.x and Flet's `1.1.0.dev*` and `1.1.0`, and `flet-local-notifications` is an unrelated project** (§6), so the requirement names the family's exact version (development.md §2.2, D-481). Our code imports it in `services/reminders.py` only. |
| Ownership | The Flet team owns v1; U adds scheduling on top, with no fork or competing package (D-97, D-99). The old `ndonkoHenri/notifications` branch (`awesome_notifications`) is not a base. |
| Effort | M for scheduling (Dart service, Python API, an Android library module and a Swift plugin class, tests). U7 belongs to v1. S6 is done. |
| Gate | `capabilities.REMINDERS`, which finds `flet_notifications`. #446 added the dependency once the pin held scheduling (`08b89cce5`), just before adoption (#447), so a v1-only package never turned the capability on. Screens follow it too since #449, which made Settings › Reminders live and removed `capabilities.REMINDERS_LIVE`, the flag that kept Settings' interim and Welcome's promise off while nothing scheduled (#446 to #449; D-60, D-287, D-401). |
| Not pinned by the P2 exit | D-256: the rows with no interim (NOTIF-06, NOTIF-07, NOTIF-10, DEV-06 and NATIVE-06) move to `later`, and the open E3 issues (#445..#451, #459) move to P4 Showcase. They stay open and `blocked`, and P2 closes on the interim above. |

**Python API added by the scheduling PR** (proposed before #6999; kept as a record, the landed API is in the table above; v1 members omitted):

```python
from datetime import datetime
from enum import Enum

import flet as ft
from flet.utils import from_dict


class AndroidScheduleMode(Enum):
    """How Android fires a scheduled notification (Dart `AndroidScheduleMode.name`)."""

    INEXACT_ALLOW_WHILE_IDLE = "inexactAllowWhileIdle"
    EXACT_ALLOW_WHILE_IDLE = "exactAllowWhileIdle"


@ft.value
class PendingNotification:
    """A notification the OS will show later."""

    id: int
    title: str | None = None
    body: str | None = None
    payload: str | None = None


@ft.control("LocalNotifications")
class LocalNotifications(ft.Service):
    """The v1 service from #6948; scheduling adds the methods below."""

    async def zoned_schedule(
        self,
        id: int,
        title: str,
        body: str,
        at: datetime,
        *,
        payload: str | None = None,
        android_schedule_mode: AndroidScheduleMode = AndroidScheduleMode.INEXACT_ALLOW_WHILE_IDLE,
    ) -> None:
        """Show a notification at the aware instant `at`, even if the app is not running."""
        if at.tzinfo is None:
            raise ValueError("at must be timezone-aware")
        args = {"id": id, "title": title, "body": body, "at": at.isoformat(),
                "payload": payload, "android_schedule_mode": android_schedule_mode}
        await self._invoke_method("zoned_schedule", args)

    async def get_pending(self) -> list[PendingNotification]:
        """Return the notifications scheduled but not yet shown."""
        pending = await self._invoke_method("get_pending")  # a list of dicts on the wire
        return [from_dict(PendingNotification, p) for p in pending or []]

    async def cancel_all_pending(self) -> None:
        """Cancel every scheduled notification, leaving the ones already shown (D-222)."""
        await self._invoke_method("cancel_all_pending")
```

`zoned_schedule` with `EXACT_ALLOW_WHILE_IDLE` while Android denies exact alarms raises the plugin's `exact_alarms_not_permitted` (S6). At the pin, `schedule()` raises `NotificationPermissionException` for it; `apply()` reads `can_schedule_exact_alarms()` before each apply and checks that `flet_permission_handler.Permission.SCHEDULE_EXACT_ALARM` agrees (D-221, D-389).

**Semantics.**
- **Time.** A one-shot reminder needs only an instant: Dart parses the ISO string and schedules `tz.TZDateTime.from(instant, tz.UTC)`, with no device time-zone lookup. DST is resolved in Python, where `at` is built in the conference zone (D-43). Repeating schedules, which would need an IANA zone, are out of scope.
- **Ids** are deterministic 32-bit ints. A session reminder uses the numeric session id (schedule 1–1147, open spaces 9025–9177), or 1,000,000 + crc32(id) % 1,000,000 for synthetic ids (`reminder_id()`, architecture §14.1). Event reminders use 8000–8099 (8000–8049 written by hand, 8050–8099 derived from the keynotes, D-274). The test reminder (DEV-06) uses 8999, as Ionic did. A unit test checks a year's plan for collisions. Because `apply()` cancels every pending reminder, a re-plan can remove a pending test reminder; that is acceptable for a developer tool.
- **Taps.** `on_notification_tap` (v1) and `get_launch_details()` (v1, for cold start) deliver `payload`. The app puts the deep-link path there (`/my-schedule/session/<id>`) and navigates as for a link (D-21). On iOS both need the notification delegate (Platform setup, F53).
- **Exact when allowed** (D-221, amends D-59's inexact default). Android 14 gives an inexact alarm a window of 75 % of the time left and delivers it anywhere in it, at its end when nothing else wakes the device (S6: +90 s on 2 min, +180 s on 4 min, +80 s on 10 min, +370 s on 30 min). Outside forced Doze, exact alarms fired within seconds (+0.3 s to +5.4 s over three runs); in forced deep Doze an exact one came +59.3 s late (inexact: +90.1 s), so exact is sooner, not guaranteed on time. Android 14 denies exact alarms to new installs, so the app declares `SCHEDULE_EXACT_ALARM`, asks in context through `flet_permission_handler.Permission.SCHEDULE_EXACT_ALARM` (exists), and falls back to inexact with honest copy.
- **Limit.** iOS keeps 64 pending requests and, on the simulator, dropped the **soonest** six of 70 (the first added), so `plan()` returns at most the next 60, soonest first (D-222). Android kept all 70.

**App side** (`services/reminders.py`, #447, D-389; `plan()` is pure and tested without Flet). The landed API differs from the sketch above: `schedule(id, *, when, title, body, payload, schedule_mode)` stands for `zoned_schedule`, `schedule_mode` (`AndroidScheduleMode.EXACT_ALLOW_WHILE_IDLE` or `INEXACT_ALLOW_WHILE_IDLE`) for the `exact` flag, and the exact-alarm state is the extension's own `can_schedule_exact_alarms()`; `cancel_all_pending()` and `get_pending()` kept their names.

```python
# src/pycon_us/services/reminders.py (excerpt)
def start(permissions: PermissionHandler | None) -> Scheduler | None:
    """The session's Scheduler when the build has E3, else None: the interim (D-63)."""
    if not capabilities.REMINDERS:
        return None
    from flet_notifications import Notifications

    return Scheduler(Notifications(), permissions, android=page.platform == ANDROID)


class Scheduler:
    def request(self) -> None: ...      # a newer request supersedes an apply in flight
    async def keep_applied(self, planner, closed) -> None: ...  # App's effect: one at a time
    async def exact_allowed(self) -> bool: ...  # the plugin's; warns if the permission disagrees

    async def apply(self, plan: Sequence[Reminder], *, exact: bool) -> bool:
        await self.notifications.cancel_all_pending()  # never the shown ones (D-222)
        for r in plan:
            if self._wanted.is_set():
                return False  # superseded: the loop applies the newer plan
            await self.notifications.schedule(
                r.id, when=r.at, title=r.title, body=r.body, payload=r.route,
                schedule_mode=EXACT_ALLOW_WHILE_IDLE if exact else INEXACT_ALLOW_WHILE_IDLE,
            )  # each failure logged, never raised; an exact one refused goes inexact
```

`Services.create()` calls `start()` (`Services.reminders`); `reminder_schedule.use_reminder_schedule()`, `App`'s hook, asks for an apply once the start has loaded and at each change of the favourites, the reminder settings, the feed or the change log, and `on_resume()` asks too, which brings back alarms a force-stop cleared (D-222; S6: the same id rescheduled fired once, at the new time). The plan is made at `clock.real_now()`, never the fake clock. App code never imports the extension elsewhere.

**Platform setup.**

| Platform | Entry | How | Status |
|---|---|---|---|
| Android | Core library desugaring | `flutter_local_notifications` requires `isCoreLibraryDesugaringEnabled` and `coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.4")` in the **app** module, even when nothing is scheduled. The template sets Java 17 and no desugaring (`TPL/android/app/build.gradle.kts:65-68`), and no CLI option adds it. **U7** (§5.10) is therefore a prerequisite of #6948 v1, not only of scheduling. | landed at `08b89cce5`: the extension's `flet-extension.toml` adds both, through the template's new `compile_options` and `dependencies` hooks (U7, #6999) |
| Android | Receivers and the boot permission (scheduling only) | `ScheduledNotificationReceiver`, `ScheduledNotificationBootReceiver` (boot actions `BOOT_COMPLETED`, `MY_PACKAGE_REPLACED`, `QUICKBOOT_POWERON`) and `RECEIVE_BOOT_COMPLETED`. The plugin's manifest has only `VIBRATE` and `POST_NOTIFICATIONS` (22.3.1 archive), and the template has no `<receiver>` hook. **Preferred:** the extension ships an Android library module declaring them, merged by Gradle. Flet extensions are plain Dart packages, so this needs a `flutter: plugin: platforms: android:` pubspec entry (with a no-op `pluginClass` if flutter_tools insists) and `"android/**"` in package-data. **Fallback:** a `[tool.flet.android.receiver]` table rendered like `provider` (`TPL/.../AndroidManifest.xml:67-71`). **S6 chose the preferred way** (D-220, F52): a Java no-op `pluginClass` (flutter_tools builds a plugin's `android/` only when it names one) and package-data `"**/*"`; the receivers reached the release APK's merged manifest and delivered after a reboot. | in the extension (D-220); landed at `08b89cce5` (#6999's `android/src/main/AndroidManifest.xml`) |
| Android | `POST_NOTIFICATIONS` (API 33+) | The plugin's manifest merges it. We also declare it explicitly so the app's manifest is self-describing: `[tool.flet.android.permission] "android.permission.POST_NOTIFICATIONS" = true` (`CLI/commands/build_base.py:1285-1288`). | declared in `pyproject.toml` (#446) |
| Android | Exact alarms | Declare `SCHEDULE_EXACT_ALARM` (`[tool.flet.android.permission]`, exists) and ask in context (D-221); never `USE_EXACT_ALARM`, which is for alarm and calendar apps. The extension also checks and requests the access itself (`can_schedule_exact_alarms()`, `request_exact_alarm_permission()`). | declared in `pyproject.toml` (#446, D-221) |
| Android | R8 in release builds | The plugin serialises scheduled notifications with GSON. The template's default rules include `-keepnames class * { *; }`, and `[tool.flet.android] proguard_rules = [...]` (a list appended to the defaults; exists, `CLI/build_base.py:1294-1297`) can append GSON keep rules. `proguard_default_rules = false` drops the defaults. **S6:** with the default rules the R8 mapping keeps the plugin's model names, and a release APK delivered, rebooted and delivered again; no extra rules while the defaults stay on. | exists (S6) |
| Android | Small icon | `@mipmap/ic_launcher` (in the template) is drawn as a plain disc in the status bar and the shade (S6). The extension ships a monochrome vector drawable in its Android module, with a `res/raw/*_keep.xml` (`tools:keep`) because the plugin finds it by name; S6 saw it survive R8 and show in light and dark. An app that wants its own icon names it in `initialize` (a drawable resource hook for apps is later). | in the extension (D-220); landed at `08b89cce5` (`res/drawable/flet_notifications_icon.xml` with `res/raw/flet_notifications_keep.xml`; `Notifications.android_default_icon`) |
| iOS | Permission | Request through the extension's `request_permission()` (v1). The template's permission_handler macros have no notifications entry (F17), so not through `flet-permission-handler`. | landed as `request_permissions()` (#6999) |
| iOS | Notification delegate | The plugin README requires `UNUserNotificationCenter.current().delegate = self` in `AppDelegate`, for taps and foreground presentation. The template's `AppDelegate.swift` is stock and does not set it, and the plugin does not set it either (checked in 22.3.1). **#6948 v1 must solve this** for `on_notification_tap` to work on iOS. **S6:** with the stock template the simulator delivered reminders but reported no tap, cold or warm; a Swift plugin class in the extension that sets the delegate fixed both, so no template line is needed (D-220, F53). | landed at `08b89cce5` in the template instead: `AppDelegate.swift` sets the delegate when the app links `flutter_local_notifications` (#6999) |

**Spike S6** (done 2026-10-14, [verdict](spikes/06-reminders.md)): yes on both platforms, with the receivers, the icon and the iOS delegate in the extension, U7 in Flet, exact alarms when allowed (D-221) and the cap of 60 in `plan()` (D-222). The release-build checks on the iPhone (locked phone, more than 64, Focus) are held for #121.

**Tests.**
- **Extension:** `zoned_schedule` at now + 70 s appears in `get_pending`, and `cancel` removes it; a naive `at` raises `ValueError`; the instant is exact across the 2027-03-14 US DST change; scheduling works on an API 34 emulator with exact alarms denied; exact scheduling with them denied raises `exact_alarms_not_permitted`; `cancel_all_pending` leaves a shown notification in place; on iOS a cold-start tap carries its payload (the delegate).
- **App:** unit tests for the pure `plan()` (past instants skipped, the cap of 60 keeping the soonest, deterministic ids, lead times); the `Scheduler` against a fake service (`tests/test_reminder_scheduler.py`: cancel pending then schedule, exact only when allowed, idempotent, newer wins); the hook's triggers (`tests/test_reminder_schedule.py`); `start()` picks the interim when not embedded.

**Upgrade** (§2.4, plus):
1. *Done in #446*, after the pin PR #445: the dependency (pinned by `.flet-ref`, from `.flet-src`), `flet-permission-handler`, `POST_NOTIFICATIONS` and `SCHEDULE_EXACT_ALARM` (D-221); the receivers, the boot permission, the icon, desugaring and the iOS delegate came with the extension and the template (D-220). #447 then schedules with it.
2. Settings › Reminders switches become live, and the permission card appears (NOTIF-01, NOTIF-06, NOTIF-10).
3. The in-app `Banner` stays for the foreground, and the `.ics` actions stay.
4. Run the P2 exit check: a reminder fires with the app killed (the iPhone and an Android emulator) and after a reboot of the emulator, and a tap opens the session.

### 4.2 E1: barcode scanner (priority 4; the staff showcase)

| Field | Value |
|---|---|
| Serves | LEAD-01 (the shared scan screen), LEAD-02 (camera permission), DOOR-04, SHIRT-02, MASK-04, NATIVE-06 |
| Interim (D-65) | Manual entry on the shared scan screen: a `TextField(on_submit=...)` taking the full `code:validator` payload, typed, pasted or sent by a USB/Bluetooth HID scanner, with focus kept. It **always** ships; the camera is added on top when E1 is bundled, and the companion app says "This app can't scan with the camera yet" and how to type or use a scanner. |
| Upstream | A new extension. Proposed dist `flet-barcode-scanner` (free on PyPI), module `flet_barcode_scanner`, control `BarcodeScanner`. |
| Dart package | `mobile_scanner` **7.4.2** (BSD-3; 2026-09-14; Dart `^3.7.0`, Flutter `>=3.29.0`; Android `minSdk 23`, CameraX and ML Kit; iOS pod 12.0, Apple Vision). |
| Gate finding | `mobile_scanner` imports `package:flutter/material.dart` in `mobile_scanner.dart` and `mobile_scanner_preview.dart`. The default error and placeholder widgets use `Colors.black`, `Icons.error`, `Icon` and `Text`. The extension passes its own `errorBuilder` and `placeholderBuilder` (built from `widgets.dart`), so no SDK-Material widget is ever built. S8 passed the §3 gate on Android and the iOS simulator: with those builders the plugin builds only `ValueListenableBuilder`, `LayoutBuilder`, `ClipRect`, `SizedBox`, `FittedBox`, `RotatedBox` and a `Texture` (`GestureDetector` only with `tapToFocus`, which E1 leaves off). |
| Effort | M, plus S8 |
| Gate | `capabilities.SCANNER` |

**Python API** (settled by D-293; S8 ran it as `S8Scanner`). It is declarative: torch and pause are properties, not imperative toggles, which fits components mode.

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import flet as ft


class BarcodeFormat(Enum):
    """Dart `BarcodeFormat.name` values; QR is all the app needs."""

    QR_CODE = "qrCode"
    ALL = "all"


@dataclass
class BarcodeDetectEvent(ft.Event["BarcodeScanner"]):
    raw_value: Optional[str] = None
    format: Optional[BarcodeFormat] = None


@dataclass
class BarcodeErrorEvent(ft.Event["BarcodeScanner"]):
    code: Optional[str] = None  # "permissionDenied", "unsupported", ...
    message: Optional[str] = None


@ft.control("BarcodeScanner")
class BarcodeScanner(ft.LayoutControl):
    """A live camera preview that reports detected barcodes."""

    formats: list[BarcodeFormat] = field(default_factory=lambda: [BarcodeFormat.QR_CODE])
    paused: bool = False  # True stops analysis and releases the camera
    torch: bool = False
    on_detect: Optional[ft.EventHandler[BarcodeDetectEvent]] = None
    on_error: Optional[ft.EventHandler[BarcodeErrorEvent]] = None  # code (MobileScannerErrorCode name), message

    async def analyze_image(self, path: str) -> list[str]:
        """Decode the barcodes in an image file (lets device tests check decoding without pointing a camera at a badge).

        mobile_scanner raises on the iOS simulator, so iOS checks run on a device.
        """
        return await self._invoke_method("analyze_image", {"path": path})
```

**Dart side** (D-293; S8's `docs/spikes/08-scanner/s8_scanner/` is a working sketch).
- `MobileScannerController(formats:, detectionSpeed: DetectionSpeed.normal, autoStart: !paused, torchEnabled: torch)` is created in `initState` and passed to `MobileScanner`.
- A controller passed in gets no lifecycle handling from the widget (`useAppLifecycleState` applies only to one it creates), so the state is a `WidgetsBindingObserver`: `stop()` on `inactive`, `start()` on `resumed` unless paused or without camera permission. S8: no camera client and no detection in the background, the first detection 2.1 s after the return.
- `didUpdateWidget` maps `paused` to `stop()`/`start()` (stop releases the camera; S8 saw a disconnect per cycle over 50 cycles, with no PSS growth), and calls `toggleTorch()` when `torch` differs from the torch state and a torch exists.
- `start()` and `stop()` are serialised: the wanted state is applied when the call in flight finishes, and a `MobileScannerException` goes to `on_error`. S8's unserialised sketch left `controllerInitializing` unhandled when a resume came during the first start.
- A change of `MobileScannerState.error` triggers `error` with the code's `.name` and the message.
- `onDetect` calls `triggerEvent("detect", {"raw_value": ..., "format": ...})` for each barcode in the capture; `DetectionSpeed.normal` repeats a held code about every 270 ms, so the app's per-code cooldown is what dedupes.
- `placeholderBuilder` and `errorBuilder` return `SizedBox.expand(child: ColoredBox(...))`: a bare `ColoredBox` is zero wide in a `Column`.
- Release builds silence `debugPrint` (F111): report through events, not logs.

**App side** (`services/scanner.py`). The app owns cooldowns and feedback, not the extension:

```python
"""Camera scanning when E1 is bundled; manual and HID entry always (D-65)."""

from collections.abc import Callable
from typing import Optional

import flet as ft

from pycon_us.capabilities import SCANNER


def camera_view(on_code: Callable[[str], None], paused: bool) -> Optional[ft.Control]:
    """Return the camera preview, or None when this build has no scanner."""
    if not SCANNER:
        return None
    import flet_barcode_scanner as fbs  # only this module imports the extension

    def detected(e: fbs.BarcodeDetectEvent) -> None:
        if e.raw_value:
            on_code(e.raw_value)

    return fbs.BarcodeScanner(paused=paused, on_detect=detected, expand=True)
```

The scan screen applies the 4 s per-code cooldown and pauses while a dialog or sheet is open (MASK-04, SHIRT-02). It shows outcomes as colour, icon, word, haptics and a live region, and keeps `ft.Wakelock` enabled while it is mounted (D-65).

**Platform setup.**

| Platform | Entry | How (exists today) |
|---|---|---|
| both | Camera permission and usage string | `[tool.flet] permissions = ["camera"]` emits `NSCameraUsageDescription` and `android.permission.CAMERA` (`CLI/build_base.py:278`). Override the iOS string with staff-scanning wording in `[tool.flet.ios.info]`. |
| both | Runtime prompt in context (D-61) | `ph = fph.PermissionHandler()`, then `await ph.request(fph.Permission.CAMERA)` before the preview mounts: `mobile_scanner` asks on its own at start otherwise. If the result is `PermissionStatus.PERMANENTLY_DENIED`, show "Camera access is off" with "Open settings" (`await ph.open_app_settings()`) and "Enter codes instead"; `on_error`'s `permissionDenied` cannot tell the two apart. After Settings, re-check on resume and set `paused=False`: nothing restarts the camera by itself (S8). |
| both | Keep awake while scanning | `ft.Wakelock().enable()` / `disable()` (coroutines) |
| Android | ML Kit model | Keep the bundled model (S8: +7.3 MB on the arm64 release APK, of which `libbarhopper_v3.so` 4.9 MB and the models 0.9 MB), so scanning works offline on first use. The unbundled variant (`[tool.flet.android.gradle_properties] "dev.steenbakker.mobile_scanner.useUnbundled" = "true"`, exists) downloads the model through Play Services, which is not wanted on conference Wi-Fi. |
| iOS | Minimum OS | Pod 12.0, below the template's 15.0, so U12 is not needed. |

**Spike S8: done** ([verdict](spikes/08-scanner.md), 2026-10-20). A throwaway extension with this API decoded the badge QR from an Android 14 emulator's virtual scene camera in a release APK on every cold start, turn, resume and after 50 pause/resume cycles, released the camera in the background, and passed the §3 gate there and on the iOS 26.5 simulator (prompt, `permissionDenied`, and `unsupported`, since the simulator has no camera). E1 goes ahead (D-293). The printed QR in daylight and dim light, the torch and release timings wait for the iPhone (#121).

**Tests.**
- **Extension:** the gate test (§3); `analyze_image` on bundled PNGs of mock badges returns the exact payload (Android and the iPhone; it raises on the iOS simulator); pause and resume 50 times with no camera leak (a camera disconnect per pause in `dumpsys media.camera`, no PSS growth, no unhandled exception, on the emulator); the torch toggles (on the iPhone; Android's torch waits for a borrowed phone, D-102); a denied permission fires `on_error` and nothing crashes.
- **App:** the P3 exit criterion, a printed sheet of mock badges scanned on the iPhone (on Android, the badge images through an emulator's virtual scene camera), including two devices checking in the same attendee (PLAN §7).

**Upgrade** (§2.4, plus):
1. Add the exact pin and `permissions = ["camera"]`.
2. The camera area appears on the scan screen. Manual entry stays reachable on every tool.

### 4.3 E4: native add-to-calendar (later)

| Field | Value |
|---|---|
| Serves | SESS-04 |
| Interim | `.ics` from `core/ics.py` for one session or all of My schedule (SESS-05, D-62), handed to the calendar by D-272: on iOS a loopback server and `launch_url(..., mode=IN_APP_BROWSER_VIEW)`, whose calendar sheet adds the events with their alarm; on Android a file saved with `FilePicker.save_file`, opened from Files (Google Calendar's import drops the alarm), until U71 opens it in one tap. The share sheet reaches no calendar on either platform ([P2-04](spikes/10-ics-share.md)). |
| Dart package | `add_2_calendar` **3.1.1** (MIT; 2026-06-15; Dart `^3.11.0`, Flutter `>=3.41.0`; iOS pod 11.0). It opens the OS calendar editor pre-filled, with no silent writes. |
| Setup | • Android 11+: a `<queries>` intent for `INSERT` on `vnd.android.cursor.item/event`, which needs **U6**.<br>• iOS: `NSCalendarsUsageDescription`, `NSCalendarsWriteOnlyAccessUsageDescription` (iOS 17+) and `NSContactsUsageDescription` (the package README warns of a crash without it), set in `[tool.flet.ios.info]`. |
| Effort / gate | S plus U6 / `capabilities.CALENDAR` |

```python
# Proposed (E4): a Service, like flet-secure-storage.
@ft.control("AddToCalendar")
class AddToCalendar(ft.Service):
    async def add_event(self, title: str, start: datetime, end: datetime,
                        location: str | None = None, description: str | None = None,
                        url: str | None = None) -> bool:
        """Open the OS calendar editor; False if the user cancelled or no calendar app exists."""
```

**Upgrade** (§2.4, plus): the pinned Flet must contain U6; add the `<queries>` intent (§5.9) and the iOS usage strings to `[tool.flet.ios.info]`. Session detail's "Add to calendar" calls `add_event`; My schedule's export keeps D-272's `.ics` route, which adds a whole agenda at once.

**Tests:** the editor opens pre-filled on an Android emulator and an iOS simulator; a cancelled editor returns False; with no calendar app it returns False and the app falls back to D-272's `.ics` route.

### 4.4 E5: HTML rendering (cut by D-117 after S3; kept as a record)

| Field | Value |
|---|---|
| Serves | DATA-23, DATA-25, SESS-06, INFO-05, MAP-09 |
| Interim | `core/html_md.py` (stdlib `html.parser`, absolute links, text fallback for unknown tags) → `ft.Markdown(selectable=True, on_tap_link=...)` (D-44). Spike S3 measures coverage over every HTML field in the 2025 and 2026 feeds. If coverage is good, E5 may never be needed. |
| Dart package | `flutter_widget_from_html_core` **0.17.4** (MIT; 2026-09-08; depends only on `csslib`, `html` and `logging`). Run the gate (§3) **before any code**: if the widgets it builds for selection or links use SDK Material, drop E5. |
| Setup | None: the package is pure Dart and needs no permissions or usage strings. |
| Effort / gate | M / `capabilities.HTML`: the companion app lacks its Dart code, so `html_md` → `Markdown` stays the fallback (one helper chooses). |

```python
@ft.control("Html")
class Html(ft.LayoutControl):
    value: str = ""
    base_url: Optional[str] = None  # resolves /2027/... links
    selectable: bool = False
    on_tap_link: Optional[ft.ControlEventHandler["Html"]] = None  # e.data is the absolute URL
```

**Upgrade** (§2.4, plus): one helper picks `Html` when `capabilities.HTML`, else `html_md` → `Markdown`; search keeps matching the converted text.

**Tests:** the §3 gate; link taps yield absolute URLs; every HTML field in the 2025 and 2026 feeds renders with no `FlutterError`.

### 4.5 E2: FCM push (low; not used by the app)

The app has no push (D-58): there is no sender, and the PSF's Firebase project is not ours; NOTIF-04 and NATIVE-04 are `drop`. A `flet-firebase` extension stays a possible Flet contribution with no app integration: `firebase_core` **4.15.0** and `firebase_messaging` **16.7.0** (BSD-3; 2026-09-14), Dart-only `Firebase.initializeApp(options)` (no hook exists for `google-services.json`/`GoogleService-Info.plist`), and the iOS `aps-environment` entitlement, which needs the cut U5.

---

## 5. Core and CLI items

Each becomes a PR to flet-dev/flet **by the owner** (D-212), with a CHANGELOG entry, docs and integration tests following the monorepo skills (`write-changelog-entry`, `create-flet-control-integration-tests`, `docs-conventions`). The `upstream` issue here carries the analysis that PR needs.

### 5.1 U1: `ft.RefreshIndicator` (priority 2; S)

| Field | Value |
|---|---|
| Serves | DATA-03, SCHED-13, EVT-07, SPON-08 |
| Interim | The `StatusStrip` (D-32) shows Refresh while data is stale, offline or refreshing at the user's request. Settings › Data and the Developer screen have "Refresh now". All call `Conference.refresh(svc.storage, svc.year)` (architecture §6.2, D-145), which keeps the cache on failure (D-39) and shows "Updating the schedule…" (D-181). Automatic refresh runs on start, on resume and every 15 min while Now or Schedule is visible, once the last one began 15 min ago (D-40, D-175), and is quiet: only the strip's 2 dp bar shows it (D-181). Pull-to-refresh is a refresh the user asks for. |
| Today | **Landed** at the pin `22a6dcb16` (#805): [flet-dev/flet#6997](https://github.com/flet-dev/flet/pull/6997), `FLET/controls/material/refresh_indicator.py:33`, with `content`, `on_refresh`, `color`, `bgcolor`, `displacement`, `edge_offset`, `stroke_width` (2.0), `elevation`, `trigger_mode`, `handle_nested_scrolls`, `semantics_label` and `semantics_value`. Absent before it (F8). **Adopted** by D-449 ([#806](https://github.com/ndonkoHenri/pycon-us-flet/issues/806)): `ui/scrolling.py`'s `pullable()`. Its spinner never ended after a re-render until U279's fix, at the pin `a9ef26fdb` (F299, [#809](https://github.com/ndonkoHenri/pycon-us-flet/issues/809), [flet-dev/flet#7027](https://github.com/flet-dev/flet/pull/7027)). The proposal below is kept as written. |
| Dart | Flutter's `RefreshIndicator` from `material_ui`; no new dependency. |

```python
@ft.control("RefreshIndicator")
class RefreshIndicator(ft.LayoutControl):
    """Pull-to-refresh around a scrollable control (proposed, U1)."""

    content: ft.Control  # a ListView, or a Column/Row with scroll set
    on_refresh: Optional[ft.ControlEventHandler["RefreshIndicator"]] = None
    color: Optional[ft.ColorValue] = None
    bgcolor: Optional[ft.ColorValue] = None
    displacement: ft.Number = 40.0
    edge_offset: ft.Number = 0.0
    stroke_width: ft.Number = 2.5
```

**Completion contract.** Flutter's `onRefresh` must return a `Future`. Follow `Dismissible` (exists, `DART/controls/dismissible.dart:82-91`):
1. Dart stores a `Completer` and triggers `refresh`.
2. Python awaits the user's handler, sync or async, then **always** calls `_invoke_method("end_refresh")` in a `finally`, which completes the `Completer`.
3. A Dart-side timeout completes it if Python never answers, so the spinner can never hang (Ionic's SPON-08 bug).

**Tests.** Drag, then the handler runs, then the spinner disappears. A handler that raises still ends the spinner. Updating `content` keeps the scroll offset.

**Upgrade** (done, D-449). `pullable(list, on_refresh)` wraps the Schedule's day lists, Sprints' and Job listings' lists in `RefreshIndicator`, whose `on_refresh` awaits the strip's refresh. The StatusStrip keeps its Refresh button, because pull-to-refresh is not discoverable by screen-reader users (D-33), and Settings › Data keeps "Refresh now".

### 5.2 U15: non-fatal handler and effect errors (priority 3; S)

| Field | Value |
|---|---|
| Serves | Cross-cutting (D-71) |
| Interim | `@report_errors` on handlers and effects: it logs the traceback, shows "Something went wrong" (with the exception text in developer mode), and re-raises `CancelledError`. Expected failures are still handled at their own boundaries. |
| Today | • An event-handler exception is logged, then `session.error()` sends `SESSION_CRASHED` (`FLET/messaging/session.py:459-464`, `:592-600`).<br>• A sync effect setup does the same (`:746-748`).<br>• Async effect tasks fail silently into asyncio (F4), which reports the exception only when the task is released, so a mounted effect's never (F37).<br>• `page.on_error` exists, but it carries Flutter-side errors. |
| Change | One opt-in page event. When set, it receives every unhandled exception from event handlers and effects, sync or async, and the session stays alive. When it is unset, behaviour is unchanged. |

```python
@dataclass
class UnhandledErrorEvent(ft.Event["Page"]):
    """An exception no handler caught (proposed, U15)."""

    error: Optional[BaseException] = None
    source: str = ""  # e.g. "on_click handler of Button(12)" or "effect in Schedule"


# Proposed new field on ft.Page:
#     on_unhandled_error: Optional[ft.EventHandler[UnhandledErrorEvent]] = None
```

The Flet team decides the final shape. A page event keeps it per session, discoverable and opt-in.

**Tests.** With the hook set, a raising click handler, sync effect or async effect task sends no `SESSION_CRASHED`, the page stays interactive, and the hook receives the exception and its source. Without the hook, behaviour is unchanged.

**Upgrade.** `main.py` sets `page.on_unhandled_error` to log and show the SnackBar. The PR deletes `@report_errors` and its uses (D-71).

### 5.3 U4: `page.get_app_info()` (priority 5; XS)

| Field | Value |
|---|---|
| Serves | INFO-03 (About this app) |
| Interim | `pycon_us.__version__`, kept equal to `[project].version` by a unit test (D-83), and no build number (D-187): `flet build` passes `--build-number` only to Flutter (Android `versionCode`, iOS `CFBundleVersion`), the template puts nothing about it in the app's environment, and `importlib.metadata` cannot see the app in packaged builds (F15). About this app shows the version alone. |
| Today | **Landed** at the pin `08b89cce5` (#445) as `async Page.get_package_info() -> PackageInfo` ([flet-dev/flet#6972](https://github.com/flet-dev/flet/pull/6972); `FLET/controls/page.py:1509`, `FLET/controls/package_info.py`): `app_name`, `package_name`, `version`, `build_number`, `build_signature`, and the optional `installer_store`, `install_time` and `update_time`. For a `flet build` app it is the built app's own metadata; otherwise it describes the Flet client, so in the companion app it reports the companion's version and the app uses it only when `is_embedded()`. #452 adopted it in place of the proposed `get_app_info()` and ended the interim (`services/build.py`, D-386). Before the pin: absent (`package_info_plus` in `packages/flet/pubspec.yaml`, unused). |

```python
@ft.value
class AppInfo:
    """What the OS knows about the running app (proposed, U4)."""

    app_name: str
    package_name: str
    version: str
    build_number: str
    installer_store: Optional[str] = None


# Proposed on ft.Page, next to get_device_info():
#     async def get_app_info(self) -> AppInfo: ...
```

**Upgrade (done, #452, D-386).** About this app reads `version` and `build_number` from `await page.get_package_info()` when embedded, and shows the build number beside the version; the diagnostics text names it on a Build line. **Test:** on the flet test host, the result equals `--build-version`/`--build-number` and the bundle id.

### 5.4 U16 + U17: text scale and accessibility changes (priority 6; XS, one PR)

| Field | Value |
|---|---|
| Serves | THEME-11 (text at 200 %), THEME-09 (reduced motion), the high-contrast switch default (D-23) |
| Interim | Fluid layouts with no fixed heights around text (D-26). The one layout that must change with the size, a slot's time beside or above its rows, measures an invisible copy of the widest gutter against the body with `on_size_change` (`GutterProbe`, D-216, F51); detail pages' titles step down at the same answer (D-328), and the Schedule's head (D-345), Job listings' strip and filter, Now's spotlight and the Sponsors' logo cards change their layout at it (#649). Accessibility features are read with `SemanticsService.get_accessibility_features()` at start and on resume (F13, D-34). On Android a change made while the app is in the background often reaches Flutter seconds after that read, so the app's own durations follow only at the following resume (#178, accepted until U17 by D-183). |
| Today | `PageMediaData` has `padding`, `view_padding`, `view_insets`, `device_pixel_ratio`, `orientation` and `always_use_24_hour_format`. Its Dart builder (`DART/widgets/page_media.dart:56-64`) already sends a `media_change` event whenever these change, and `page.on_media_change` receives the new `PageMediaData` (exists). |
| Change | Add five fields, read in the same Dart builder:<br>• `text_scale_factor` from `MediaQuery.textScalerOf(context)`;<br>• `disable_animations`, `high_contrast`, `bold_text` and `accessible_navigation` from `MediaQuery`.<br>Reading them makes the builder depend on them, so the **existing** `on_media_change` becomes the change event. That covers U17 with no new event type. |

```python
# Proposed additions to ft.PageMediaData (all read-only):
#     text_scale_factor: float = 1.0
#     disable_animations: bool = False
#     high_contrast: bool = False
#     bold_text: bool = False
#     accessible_navigation: bool = False
```

**Upgrade.** `Prefs` reads these from `page.media` at start and follows `page.on_media_change`, replacing the resume re-read, so reduced motion and the high-contrast default follow live. `GutterProbe` stays: the share of the width the gutter takes depends on the font and the width as well as on the factor, and measuring it is exact. So do detail pages' titles, which step down at the probe's answer (D-328): whether a long word fits depends on the width too. With the factor, a title could instead grow less than body text, as iOS's own headings do, by a `size` divided by the factor (Flutter scales every size again); a refinement, which no title needs today.

**Test.** Changing the font size or "Remove animations" in the emulator's settings fires `on_media_change` with the new values, also when the change was made with the app in the background and reaches Flutter seconds after the return (#178's case, D-183; tracked by #183).

### 5.5 U10: `AppBar.bottom` (later; S)

- **Serves:** SCHED-01 (day tabs), SCHED-27.
- **Interim:** the `TabBar` is the first row of the view's body.
- **Today:** `ft.AppBar` has no `bottom` field.
- **Change:** `bottom: Optional[ft.Control] = None`, wrapped in a `PreferredSize` whose height the Dart side measures, or a `bottom_height: ft.Number = 48.0` if measuring proves awkward. A good PyCon sprint candidate.
- **Upgrade:** Schedule moves its `TabBar` into `AppBar(bottom=...)`. No other screen changes.

### 5.6 U2: grouped list with pinned headers (later; M)

- **Serves:** SCHED-02, SCHED-27.
- **Interim:** each time slot is one item of the day's `ListView` with its time in a left gutter (D-31), which also gives `scroll_to` slot-sized keys; today's list builds every slot (`cache_extent`), so its keys are always reachable (D-154, F7, F32).
- **Design:** a `CustomScrollView` with one `SliverMainAxisGroup` per group, whose first sliver is a `PinnedHeaderSliver`. These are framework widgets, so no Material and no new dependency.

```python
# Proposed (U2): scroll_to(...) mirrors ListView.scroll_to, including scroll_key.
@ft.control("ListGroup")
class ListGroup(ft.Control):
    header: ft.Control
    controls: list[ft.Control] = field(default_factory=list)


@ft.control("GroupedListView")
class GroupedListView(ft.LayoutControl):
    groups: list[ListGroup] = field(default_factory=list)
    sticky_headers: bool = True
```

**Upgrade.** The schedule may keep the gutter layout. Adopt U2 only if pinned slot headers test better on devices than the gutter.

### 5.7 U3: absolute `InteractiveViewer` transform (later; S)

- **Serves:** EXPO-05 (zoom to booth) and D-18's remembered map zoom (MAP-01, MAP-04).
- **Interim:** the booth is selected and highlighted and its card shown; one picked from a link or a List row that sits under its card is brought into view above it at the least zoom, with `reset()`, `zoom(s)` and `pan(t / s)` once the card is measured (D-377, `screens/expo_camera.py`), so two or three frames show the steps. A remembered zoom can be put back with `reset()`, `zoom(s)` and `pan(t / s)` once the viewer is laid out, which S7 confirmed exactly (5.361, −321.7, −214.5), so a Map pane keeps its zoom that way (D-312, F130: the pane's own state and `save_state`'s matrix do not survive it leaving).
- **Today** (at `15854a0ac`; unchanged at `08b89cce5`): `zoom(factor)` and `pan(dx, dy, dz)` are relative, instant and clamped (`FLET/controls/core/interactive_viewer.py:314`, `:330`; `DART/controls/interactive_viewer.dart:150-169`). `get_transform()` (`:360`) reads the transform but nothing sets one. Only `reset(animation_duration)` animates (`:279`; a `Matrix4Tween`, `DART/controls/interactive_viewer.dart:170-185`). `save_state`/`restore_state` store one matrix on the Dart side. `zoom()` scales about the content's top-left corner and `pan()` moves in content units (U56, F76).
- **Change:** set the `TransformationController` value directly, clamped as gestures are, animating with a `Matrix4Tween` when a duration is given, as `reset` does. The analysis, a repro on both platforms, a draft diff and its widget tests are in [#368](https://github.com/ndonkoHenri/pycon-us-flet/issues/368).

```python
# Proposed on ft.InteractiveViewer:
#     async def set_transform(self, scale: ft.Number, offset: ft.OffsetValue = (0, 0),
#                             animation_duration: Optional[ft.DurationValue] = None) -> None: ...
#     async def zoom_to_rect(self, rect: ft.Rect, padding: ft.Number = 0,
#                            animation_duration: Optional[ft.DurationValue] = None) -> None: ...
```

`set_transform` is the inverse of `get_transform()` (the same matrix, so a round trip is exact): the content's scale and, with no `alignment` set (the default), its top-left corner at `offset` in the viewer, in logical pixels. `alignment` makes Flutter's `Transform` apply the matrix about that point (Flutter `interactive_viewer.dart:1061`, `:1076`); these offsets and `zoom_to_rect`'s centring ignore it, as the existing clamps and Flutter's gestures do. `zoom_to_rect` fits a rectangle of the content (in its laid-out coordinates) in the viewport less `padding`, centred at the scale it ends at. Both clamp the scale to `[min_scale, max_scale]` and the covering scale, and the translation to the boundary. **Upgrade:** the expo map calls `zoom_to_rect(booth_rect, animation_duration=prefs.motion_ms(...))`, which jumps under reduced motion (D-173), and a pane restores its remembered view with `set_transform()`.

### 5.8 U9: `ft.use_route_search()` (later; XS; [#369](https://github.com/ndonkoHenri/pycon-us-flet/issues/369))

- **Serves:** NEW-02 (`?scope=`), ROOM-03 (`?highlight=`), ROOM-05 and MAP-05 (`?pin=`), SPON-04 and EXPO-05 (`?booth=`).
- **Interim:** `use_query()` in `locations.py` (D-164) parses the query from `page.route` once, when its View mounts, and only for the top View (`is_top_view(page.route, ft.use_view_path())`; `use_route_location()` is the opener's location for the Views under a global modal).
- **Today:** the Router parses the query into `LocationInfo.search`, without the leading `?` (`FLET/components/router.py:111-123`, `:723-726`, `:808`). It hands the query to every View through its location context (`:887-898`); the Views under a global modal get their opener's (`:842-850`). No hook returns it: `use_route_location()` returns the pathname only (`:357-370`). `page.query` (`FLET/controls/query_string.py:72-83`) is no substitute, for three reasons: it parses `page.route`, which under a modal is the modal's location; it is not a hook; and it drops blank values.
- **Change:** `def use_route_search() -> str`, next to `use_route_location()`. It returns the same location's `search` (`""` outside a Router) and is exported as `ft.use_route_search`. #369 holds the draft diff, a repro and the open questions.
- **Upgrade:** `use_query()` takes the query from `ft.use_route_search()` instead of `page.route`. It keeps its two rules:
  - only the top View reads it, because every View of a stack sees the same value;
  - it reads it once, when the View mounts.

  It also keeps blank values (`parse_qsl(..., keep_blank_values=True)`). Its callers do not change.

### 5.9 U6: Android `<queries>` (only with E4; S)

- **Landed** at the pin `a9ef26fdb` (#1005, [flet-dev/flet#7031](https://github.com/flet-dev/flet/pull/7031)), as `[tool.flet.android.queries]` with `packages`, `intents` and `providers` (`TPL/android/app/src/main/AndroidManifest.xml:102-114`). Nothing here uses it until E4.
- **Asked for:** extra intents from pyproject:

```toml
[[tool.flet.android.queries.intent]]
action = "android.intent.action.INSERT"
data = { mimeType = "vnd.android.cursor.item/event" }
```

- **Test:** the manifest-merger report contains the intent. Without the table, the manifest is byte-identical to today.

### 5.10 U7: core library desugaring (with E3; S)

- **Landed** at the pin `08b89cce5` (#445), in a third shape: the extension declares what it needs. A `flet-extension.toml` in the extension's Flutter package sets `[android] gradle_dependencies` and `[android.compile_options]` (`CLI/utils/extension_settings.py`); the template renders them into `compileOptions` and `dependencies` (`TPL/android/app/build.gradle.kts:65-69`, `:134-139`), next to the Java 17 defaults (`CLI/commands/build_base.py:90-91`); and `flet-notifications` ships `isCoreLibraryDesugaringEnabled = "true"` with `desugar_jdk_libs:2.1.4` ([flet-dev/flet#6999](https://github.com/flet-dev/flet/pull/6999)). An app sets nothing. #446's `flet build apk` with the extension is the test below.
- **Before the pin:** `compileOptions` set Java 17 with no desugaring, and none of the `:app` options (`min_sdk_version`, `gradle_properties`, `proguard_rules`, signing, splits) enabled it.
- **Change:** `[tool.flet.android] core_library_desugaring = true` (plus a CLI flag) renders `isCoreLibraryDesugaringEnabled = true` and `coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.4")`.
- **Alternative for the Flet team:** enable it unconditionally in the template. It is harmless for apps that don't need it, and it removes a knob.
- **Scope:** desugaring only. S6 put E3's receivers in the extension's Android module (D-220), so no `[tool.flet.android.receiver]` table is needed.
- **Issue:** [#293](https://github.com/ndonkoHenri/pycon-us-flet/issues/293), with S6's failing build and the draft diff.
- **Test:** `flet build apk` of an app using `flutter_local_notifications` 22.3.1 fails without the setting and succeeds with it. *Passed in #446* (2026-10-28): `flet build apk --arch arm64-v8a` logged "Applied build settings from flet-notifications 0.1.0: android.gradle_dependencies, android.compile_options.isCoreLibraryDesugaringEnabled" and built; `aapt2 dump xmltree` of the release APK showed `POST_NOTIFICATIONS`, `SCHEDULE_EXACT_ALARM`, `RECEIVE_BOOT_COMPLETED` and `VIBRATE`, and the plugin's `ActionBroadcastReceiver`, `ScheduledNotificationReceiver` and `ScheduledNotificationBootReceiver` (boot, quick boot, package replaced), all `exported=false`.

### 5.11 U12 and U13 (conditional)

- **U12, iOS deployment target: not needed.** The template's 15.0 floor (D-12) is above every pod we wrap: `mobile_scanner` 12.0, `flutter_local_notifications` 13.0, `add_2_calendar` 11.0 (§6). Reopen it only if a new dependency needs more.
- **U13, app privacy manifest:** only if the S5 TestFlight upload reports ITMS-91053. The change would ship `Runner/PrivacyInfo.xcprivacy` in the template, declaring the required-reason APIs that embedded CPython and `shared_preferences` use, with the reasons reviewed by the Flet team.

### 5.12 U18: Back inside a modal sub-chain (later; XS)

- **Serves:** NEW-02 (search, D-19): Back from a result pushed over the global modal `/search` must return to the results.
- **Today:** while a modal route is anywhere in the matched chain, the stock pop handler navigates to the modal's base location, even for a pop from a view pushed over the modal (`FLET/components/router.py:682-687` at `15854a0ac`, unchanged at `08b89cce5`, whose `current_modal_pop_to_ref` is set for the whole chain at `:782-794`; F6). An app's own `page.on_view_pop`, set before the Router mounts, receives every pop instead (`:677-680`).
- **Interim:** `main()` sets `page.on_view_pop` to navigate to `parent_of(e.route, memory.search_base)` (architecture §5.3).
- **Change:** pop to the previous view entry's resolved pathname within the modal's own sub-chain (split at the modal, as the Views are, `:835`) unless the popped view is the modal itself; only then go to the modal's base. Global and local modals alike.
- **Issue:** [#370](https://github.com/ndonkoHenri/pycon-us-flet/issues/370), with the analysis, a repro run on the iOS 26.5 simulator, a draft diff and the open questions (the base's query on close).
- **Test:** `/search` → `/search/session/42` → Back lands on `/search`; Back again lands on the base.
- **Upgrade:** after the pin bump, delete the app's `on_view_pop` handler, but only if the stock handler then matches every Back test: it drops the opener's query on closing `/search` (our `search_base` keeps it), and a Router that never saw the opener (a deep link straight to `/search`) closes it to `/`, where `Start` goes on to `start_target()` (D-143). If either differs in a way users see, the app keeps its handler. `parent_of()` stays for the back arrow (D-10).

---

## 6. Verification log (2026-10-11)

**pub.dev** (`https://pub.dev/api/packages/<name>`, latest versions; minimums from the published archives):

| Package | Latest | Published | Constraints and facts used here |
|---|---|---|---|
| `flutter_local_notifications` | 22.3.1 | 2026-09-13 | Dart `^3.10.0`, Flutter `>=3.38.1`; minSdk 24; iOS pod 13.0; desugaring, receivers and the iOS delegate line are the app's job (§4.1) |
| `timezone` | 0.11.1 | 2026-06-29 | Dart `^3.10.0` |
| `mobile_scanner` | 7.4.2 | 2026-09-14 | Dart `^3.7.0`, Flutter `>=3.29.0`; minSdk 23; iOS pod 12.0; SDK `material.dart` in default builders (§4.2) |
| `add_2_calendar` | 3.1.1 | 2026-06-15 | Dart `^3.11.0`, Flutter `>=3.41.0`; iOS pod 11.0 |
| `flutter_widget_from_html_core` | 0.17.4 | 2026-09-08 | Flutter `>=3.32.0`; deps `csslib`, `html`, `logging` |
| `firebase_core` / `firebase_messaging` | 4.15.0 / 16.7.0 | 2026-09-14 | Flutter `>=3.27.0` |
| `package_info_plus` | 10.2.2 | 2026-10-01 | Flet's pubspec has `^9.0.0` |

**Flet toolchain:** Flutter 3.47.9 (`.fvmrc`), whose default Android `minSdkVersion` is 24 and `compileSdkVersion` 36; AGP 8.13.2 and Gradle 9.3.1 in the template. Every package above fits.

**PyPI names** (`pypi.org/pypi/<name>/json`):
- **Taken:**
  - `flet-local-notifications` (1.2.2, 2026-07-11, unrelated, pins `flet==0.28.3`);
  - `flet-notifications` (0.1.0, published 2026-10-11, `Nwokike/flet-notifications`).
- **Free:** `flet-barcode-scanner`, `flet-mobile-scanner`, `flet-add-to-calendar`, `flet-html`, `flet-firebase`.
- `flet` and the first-party extensions (`flet-secure-storage`, `flet-permission-handler`, `flet-camera`) are 1.0.4.

**GitHub:**
- [flet-dev/flet#6948](https://github.com/flet-dev/flet/issues/6948): an open **issue**; no implementation PR found.
- `flet-dev/flet#6953`: the deep-link config fallback (closes `flet-dev/flet#6951`), merged into `flet-1.1.0` on 2026-10-11 and in the pin (`68a4b326c`); D-269 relies on it.

**Local SDK: exists** (beyond what PLAN's F-facts cover): `flet.utils.is_embedded`; `ft.Service`, `ft.LayoutControl`, `ft.control`, `ft.value`, `ft.Event` (fields `name`, `data`, `control`); `ft.PageMediaData` (six fields) and `page.on_media_change`; `ft.LocationInfo(pathname, search, hash)`; `flet_permission_handler.Permission.CAMERA`/`NOTIFICATION`/`SCHEDULE_EXACT_ALARM`; and the CLI keys `[tool.flet] permissions`, `dev_packages`, and `[tool.flet.android]` `permission`, `gradle_properties`, `proguard_rules`, `provider`.

**Local SDK: absent.**
- Core: `ft.RefreshIndicator`, `ft.use_route_search`, `ft.AppInfo`, `Page.get_app_info`, `AppBar.bottom`, any sliver or grouped list control, `ft.CarouselView`, an `Html` control, an error hook.
- `PageMediaData.text_scale_factor` and any accessibility-change event.
- Packages: any local-notifications or barcode package in `sdk/python/packages/`.
- Template and CLI: iOS entitlements, an Android `<receiver>` hook, desugaring; the `<queries>` hook is in the pin since `a9ef26fdb`.

---

## 7. Open points

Tracked by `upstream` issues; none needs a decision here:
1. **E3 package name:** both `flet-local-notifications` (#6948's proposal) and `flet-notifications` are taken on PyPI; the Flet team picks. *Settled at the pin `08b89cce5`: `flet-notifications`, module `flet_notifications` (flet-dev/flet#6999); until Flet publishes it, the `.flet-src` path tables keep the unrelated PyPI project out (§2.3).*
2. **iOS notification delegate** is missing from the stock `AppDelegate.swift`; S6 showed the extension can set it (D-220, F53), which E3's write-up ([#294](https://github.com/ndonkoHenri/pycon-us-flet/issues/294)) asks of `flet-dev/flet#6948` v1. *Settled at the pin `08b89cce5`: the template's `AppDelegate.swift` sets it when the app links the plugin (flet-dev/flet#6999).*
3. **U16 and U17 as one PR** through `PageMediaData` and the existing `on_media_change`, instead of a separate `SemanticsService` event.

Resolved on 2026-10-11 and applied to PLAN, the decisions record and the matrix: U7 is needed by #6948 v1 itself (PLAN §6); D-64 now reads "replaced only after a PR bumps the pinned Flet; the swap is its own tested PR"; the Developer screen shows capability flags read-only (D-73), so there are no force-interim switches; notification permission goes through E3's `request_permission()` (D-61, NOTIF-06, NATIVE-06); NATIVE-02 no longer depends on U12; NOTIF-10 depends on E3.
