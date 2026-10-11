# PyCon US mobile → Flet: native capabilities, services and gaps

Scope: every Capacitor / native plugin used by
`/Users/ndonkohenri/PycharmProjects/flet-dev/others/pycon-us/excluded/pycon-us-mobile`
(Ionic 8 / Angular 17 / Capacitor 7, `package.json` version 26.0.0), mapped to what the
local Flet monorepo (`/Users/ndonkohenri/PycharmProjects/flet-dev/flet`, main @ `7688de3`,
1.1.0-dev) can do today. Every Flet class/method/property named below was read from the
local source; pub.dev facts were fetched on 2026-10-11. Anything not found locally is
marked **GAP**.

Abbreviations: `FLET = flet/sdk/python/packages/flet/src/flet`,
`PKGS = flet/sdk/python/packages`, `DART = flet/packages/flet/lib/src`,
`CLI = PKGS/flet-cli/src/flet_cli/commands`, `DOCS = flet/website/docs`,
`APP = excluded/pycon-us-mobile/src/app`.

---

## 0. What the app actually uses (verified by grep, not by `package.json`)

| Plugin | Where used | What it does in the app |
|---|---|---|
| `@ionic/storage-angular` (`IonicStorageModule.forRoot({name: environment.storageKey})`, default drivers, no SQLite driver) | `app.module.ts`, `providers/user-data.ts`, `pycon-api.ts`, `conference-data.ts`, `notifications.service.ts`, `check-tutorial.service.ts`, pages `map`, `door-check`, `t-shirt-redemption`, `mask-violation`, `dev-tools`, `about-pycon`, `tutorial` | KV store: login flags, `email`/`nickname`/`key`/`secret` (API credentials!), `favorite_sessions` (list), `theme`, `scheduleFilters`, `schedule-cache` (whole schedule JSON), `notification_prefs` (dict), and an **offline sync queue** keyed by prefix: `pending-scan-<code>`, `synced-scan-<code>`, `failed-scan-<code>`, `note-<code>`, `pending-note-<code>`, `pending-door-check-<code>`, `synced-door-check-<code>`; `storage.keys()` / `storage.forEach()` for prefix scans and the debug dump |
| `@capacitor/network` | `providers/pycon-api.ts:285` | `Network.getStatus().connected` gate before replaying the scan queue |
| `@capacitor/inappbrowser` | `speaker-detail.ts:44`, `account.ts:78`, `session-detail.ts:460`, `schedule-list.page.ts` | `InAppBrowser.openInWebView({url, options: DefaultWebViewOptions})` for external links / dashboard |
| `window.open(url, '_system', 'location=yes')` | ~14 pages (`sprints`, `coc`, `help`, `about-psf`, `job-listings`, `venues-hours`, `lightning-talks`, `social-media`, `sponsor-detail`, `account`, `app.component`) + `mailto:`/`tel:` in `speaker-detail.ts:93,100` + `app-settings:` in `notification-settings.page.ts:141` | open in system browser / mail / phone / iOS app settings |
| `@capacitor/share` + `@capacitor/filesystem` | `session-detail.ts:426-437` (write `.ics` to `Directory.Cache`, share URI), `about-pycon.page.ts:71-86` (write encrypted DB dump to cache, `Filesystem.getUri`, share) | share sheet with a file |
| `@ebarooni/capacitor-calendar` | `session-detail.ts:331-340` | `requestWriteOnlyCalendarAccess()` + `createEventWithPrompt({...})`, falling back to the `.ics` share above |
| `@capacitor/app` | `providers/live-update.service.ts:20,28` | `App.addListener('appStateChange', {isActive})` → check for OTA update on resume; `App.getInfo()` → version/build shown in About |
| `@capacitor/live-updates` | `live-update.service.ts`, `capacitor.config.ts` (`LiveUpdates` plugin, Appflow app `e8e09c7a`, channel `Production`, `autoUpdateMethod: 'none'`), `Makefile appflow-ship` | Appflow OTA of the web bundle |
| `@capacitor/splash-screen` | `app.component.ts:163,169`; config `launchAutoHide:false`, `backgroundColor:#680579` | keep native splash until `confData.load()` resolves, then `SplashScreen.hide()` |
| `@capacitor-mlkit/barcode-scanning` | pages `door-check`, `t-shirt-redemption`, `map` (lead retrieval), `mask-violation` | `checkPermissions/requestPermissions`, `addListener('barcodesScanned')`, `startScan({formats:[QrCode], lensFacing: Back})`, `stopScan()`, `removeAllListeners()` on `ionViewWillLeave` |
| `@capacitor-firebase/messaging` | `app.component.ts:115-160`, `notifications.service.ts` | `requestPermissions`, `getToken` (shown in a diagnostics card), `tokenReceived`, `notificationReceived` (foreground toast), `subscribeToTopic/unsubscribeFromTopic` for `emergency`, `announcements`, `schedule-changes`, `daily-digest` |
| `@capacitor-firebase/analytics` | `app.component.ts:136`, `notifications.service.ts:295-308` | `logEvent('notification_received' / 'toggle_notification' / 'toggle_all_notifications')`, `setUserProperty('notif_<cat>')`; `AndroidManifest.xml:21,55` disables ad-id collection; `patches/@capacitor-firebase+analytics+7.5.0.patch` flips the podspec default subspec `Lite`→`Analytics` |
| `@capacitor/local-notifications` | `notifications.service.ts:340-440` | 11 fixed-date reminders (`REMINDERS`, ids 8000–8010, `schedule.at`, `allowWhileIdle`), a 5-second test notification (id 8999), `checkPermissions/requestPermissions`, `cancel` |
| `@capacitor/device`, `@capacitor/haptics`, `@capacitor/keyboard`, `@capacitor/status-bar` | **no TypeScript call sites** (`Capacitor.getPlatform()` from `@capacitor/core` is used in `autofill.directive.ts:16` and `environments/environment.dev.ts:6`) | pods are linked (`ios/App/Podfile`) but only Ionic internals touch them |
| `patch-package` | `package.json postinstall` | one patch, see analytics row |
| Native config | `ios/App/App/Info.plist`: `NSCameraUsageDescription`, `NSCalendarsUsageDescription`, `NSCalendarsWriteOnlyAccessUsageDescription`, `UIViewControllerBasedStatusBarAppearance`; `GoogleService-Info.plist`; `android/app/google-services.json`, `build.gradle` applies `com.google.gms.google-services` 4.4.2; manifest permissions `INTERNET`, `CAMERA`, removes `AD_ID`; **no deep-link intent filters** (only MAIN/LAUNCHER) | |

---

## 1. Mapping table

| # | Ionic / Capacitor | Flet equivalent (verified path) | Status |
|---|---|---|---|
| 1 | `@ionic/storage` (non-secret keys) | `ft.SharedPreferences` — `FLET/controls/services/shared_preferences.py` | exists |
| 1b | `@ionic/storage` (`key`, `secret`, `email`) | `flet_secure_storage.SecureStorage` — `PKGS/flet-secure-storage/src/flet_secure_storage/secure_storage.py` | exists |
| 1c | `@ionic/storage` offline scan queue (`pending-*`/`synced-*` prefix scans) | `sqlite3` file under `FLET_APP_STORAGE_DATA` (plain Python) | exists (better fit) |
| 2 | `@capacitor/network` | `ft.Connectivity` — `FLET/controls/services/connectivity.py` | exists |
| 3 | `@capacitor/inappbrowser`, `window.open(_system)`, `mailto:`, `tel:` | `ft.UrlLauncher` + `ft.LaunchMode` — `FLET/controls/services/url_launcher.py`; `ft.OpenUrl` client action (same file) | exists |
| 3b | `window.open('app-settings:')` | `flet_permission_handler.PermissionHandler.open_app_settings()` — `PKGS/flet-permission-handler/src/flet_permission_handler/permission_handler.py` | exists |
| 3c | embedded login web view with URL interception (if wanted) | `flet_webview.WebView` — `PKGS/flet-webview/src/flet_webview/webview.py` | exists |
| 4 | `@capacitor/share` (+ `Filesystem` temp file) | `ft.Share.share_files([ft.ShareFile.from_bytes(...)])`, `ft.ShareText` — `FLET/controls/services/share.py` | exists |
| 5 | `@capacitor/haptics` | `ft.HapticFeedback` — `FLET/controls/services/haptic_feedback.py` | exists (unused by app) |
| 6 | `@capacitor/filesystem` | Python I/O + `FLET_APP_STORAGE_DATA/CACHE/TEMP` env vars; `ft.StoragePaths` — `FLET/controls/services/storage_paths.py` | exists |
| 7a | `@capacitor/app` `appStateChange` | `Page.on_app_lifecycle_state_change` → `AppLifecycleStateChangeEvent.state: AppLifecycleState` — `FLET/controls/page.py:437,630`, `FLET/controls/types.py:1106` | exists |
| 7b | `@capacitor/app` back button | `Page.on_view_pop` (`ViewPopEvent`, `page.py:643`) / `ft.Router(manage_views=True)` — `FLET/components/router.py:593` | exists |
| 7c | `@capacitor/app` deep links (`appUrlOpen`) | `[tool.flet.deep_linking] scheme/host` (`CLI/build_base.py:1421-1440`, `DOCS/publish/index.md:1365`) + `Page.on_route_change` / `page.route` | exists (app does not use deep links today) |
| 7d | `@capacitor/app` `getInfo()` version/build | no Python API found (`package_info_plus` is in `flet/packages/flet/pubspec.yaml` but nothing in `DART` or `page.py` exposes it) → read your own `pyproject` version via `importlib.metadata` | partial |
| 8a | `@capacitor/splash-screen` | `flet build` splash: `[tool.flet.splash]`, `assets/splash.png`, `--splash-color`, `--no-ios-splash` (`CLI/build_base.py:453-484,1733-1770`, `DOCS/publish/index.md:981-1178`) | exists (auto-hide semantics differ, see §2.8) |
| 8b | `@capacitor/status-bar` | `ft.Theme.system_overlay_style: ft.SystemOverlayStyle` (`FLET/controls/theme.py:3606`, fields at `:690-740`), `ft.SafeArea` (`FLET/controls/core/safe_area.py`) | exists |
| 8c | `@capacitor/keyboard` | Flutter `Scaffold` in `DART/controls/view.dart:199`; template manifest `android:windowSoftInputMode="adjustResize"`; `TextField.autofill_hints` (`FLET/controls/material/textfield.py:636`) replaces `autofill.directive.ts` | exists |
| 9 | `@capacitor-mlkit/barcode-scanning` | nothing — `flet-camera` has `start_image_stream()` but no decoder | **GAP** → new `flet-barcode-scanner` on `mobile_scanner 7.4.2` |
| 10 | `@capacitor-firebase/messaging` | nothing | **GAP** → `flet-firebase` (core+messaging+analytics) or server polling |
| 11 | `@capacitor-firebase/analytics` | nothing | **GAP** → part of `flet-firebase`, or plain HTTP events from Python |
| 12 | `@capacitor/local-notifications` | nothing | **GAP** → `flet-local-notifications` on `flutter_local_notifications 22.3.1` |
| 13 | `@ebarooni/capacitor-calendar` | nothing native; `.ics` via `ft.Share.share_files` works today | **GAP** (native prompt) → `flet-add-to-calendar` on `add_2_calendar 3.1.1` (S) |
| 14 | `@capacitor/live-updates` (Appflow OTA) | not portable: `flet build` bundles Python in the native app (`DOCS/publish/index.md:168-190`) | gap by design → alternatives in §2.14 |
| 15 | `@capacitor/device` / `Capacitor.getPlatform()` | `page.platform: ft.PagePlatform`, `page.web`, `page.pwa` (`page.py:517-596`), `await page.get_device_info()` → `ft.AndroidDeviceInfo`/`ft.IosDeviceInfo`/… (`page.py:1370`, `FLET/controls/device_info.py`) | exists |
| 16 | `patch-package` | not needed; Dart deps are pinned in each extension's `pubspec.yaml`; `[tool.flet.flutter.pubspec.dependency_overrides]` for forks (`DOCS/publish/index.md:1871-1896`) | n/a |
| 17 | permission prompts (camera, notifications, calendar) | `flet_permission_handler.PermissionHandler.get_status/request/open_app_settings` + `Permission.CAMERA/NOTIFICATION/CALENDAR_WRITE_ONLY/SCHEDULE_EXACT_ALARM`, `PermissionStatus` (`PKGS/flet-permission-handler/src/flet_permission_handler/types.py`) | exists |

---

## 2. Per-capability detail

### 2.1 `@ionic/storage` → `ft.SharedPreferences` (+ `SecureStorage`, + sqlite)

**Flet API** (`FLET/controls/services/shared_preferences.py`): `@control("SharedPreferences") class SharedPreferences(Service)` with
`async set(key, value) -> bool`, `async get(key)`, `async contains_key(key)`, `async remove(key) -> bool`,
`async get_keys(key_prefix) -> list[str]`, `async clear() -> bool`.
`SharedPreferencesValueType = Union[str, int, float, bool, list[str]]`; `set()` raises `ValueError` for anything else.
Dart side `DART/services/shared_preferences.dart` uses `shared_preferences ^2.5.3` (`flet/packages/flet/pubspec.yaml`) → `NSUserDefaults` on iOS, `SharedPreferences` on Android, `localStorage` on web. Services auto-register with the current page on construction (`Service.__post_init__` → `page._services.register_service(self)`, `FLET/controls/services/service.py`).

**Port notes**
- Ionic stores arbitrary JSON (dicts for scans, `notification_prefs`, lists of favorites). Wrap with `json.dumps/loads` in a tiny `Prefs` helper; keep the app's key namespace (`environment.storageKey = "__pycon_us_mobile_base_2026"`) as a key prefix so `get_keys("__pycon_us_mobile_base_2026:pending-scan-")` reproduces `storage.keys()` filtering.
- `storage.forEach` (debug dump in `about-pycon.page.ts:62`) → `get_keys("")` then `get` each.
- `schedule-cache` (the whole schedule JSON) should **not** go to SharedPreferences (NSUserDefaults is loaded in memory, and Android has a 1 MB-ish practical limit per preference). Write it as a file under `FLET_APP_STORAGE_CACHE` (see 2.6).
- The offline **scan queue** (`pending-scan-*`, `synced-scan-*`, `failed-scan-*`, `note-*`, door-check equivalents in `pycon-api.ts:274-430`, `door-check.page.ts:166-250`) is a relational problem: use `sqlite3` (stdlib) in `FLET_APP_STORAGE_DATA` with a `scans(access_code PK, scan_data, sponsor_id, note, state, synced_at)` table. This removes the prefix-scan hacks and makes the "Share debug records" dump a single `SELECT`.
- **Secrets** (`key`, `secret` = API credentials, `user-data.ts:236-252`): use `flet_secure_storage.SecureStorage` (`flutter_secure_storage 10.3.1`, Keychain / Android Keystore): `async set(key, value, *, ios=..., android=...)`, `get(key) -> Optional[str]`, `get_all()`, `contains_key`, `remove`, `clear`; options dataclasses `IOSOptions(accessibility=KeychainAccessibility.UNLOCKED, ...)`, `AndroidOptions(...)`. Set `KeychainAccessibility.FIRST_UNLOCK_THIS_DEVICE` so background sync after reboot still works and keys do not migrate via iCloud backup.
- Declarative style: create services once (e.g. in `main()` or a top-level `@ft.component App()` with `ft.use_memo(lambda: ft.SharedPreferences(), [])`) and hand them down with `ft.use_context`/`ft.observable` stores (`FLET/components/observable.py: observable(cls)`, `class Observable.subscribe/notify`).

### 2.2 `@capacitor/network` → `ft.Connectivity`

`FLET/controls/services/connectivity.py`: `class Connectivity(Service)` with `on_change: EventHandler[ConnectivityChangeEvent]` (`.connectivity: list[ConnectivityType]`) and `async get_connectivity() -> list[ConnectivityType]`; enum values `BLUETOOTH, ETHERNET, MOBILE, NONE, OTHER, VPN, WIFI`. Dart: `connectivity_plus ^7.0.0`.

Port: `pycon-api.ts:285` becomes `if ConnectivityType.NONE in await conn.get_connectivity(): return`. Better: subscribe `on_change` once and flush the sqlite queue when connectivity returns (the Ionic app only retries on the next scan). Connectivity ≠ reachability: still wrap `httpx` calls in `try/except httpx.TransportError`.

### 2.3 In-app browser / `window.open` → `ft.UrlLauncher`

`FLET/controls/services/url_launcher.py`: `async launch_url(url, *, mode: LaunchMode = PLATFORM_DEFAULT, web_view_configuration: WebViewConfiguration | None, browser_configuration: BrowserConfiguration | None, web_only_window_name)`, `can_launch_url`, `close_in_app_web_view`, `open_window` (web popups), `supports_launch_mode`, `supports_close_for_launch_mode`. `LaunchMode`: `PLATFORM_DEFAULT, IN_APP_WEB_VIEW, IN_APP_BROWSER_VIEW, EXTERNAL_APPLICATION, EXTERNAL_NON_BROWSER_APPLICATION`. Dart: `url_launcher ^6.3.2`.

Mapping:
- `InAppBrowser.openInWebView(...)` → `LaunchMode.IN_APP_BROWSER_VIEW` (SFSafariViewController / Chrome Custom Tabs; keeps the user's us.pycon.org session cookies and password manager — what the dashboard/account links want) or `IN_APP_WEB_VIEW` (bare WKWebView/WebView, closable with `close_in_app_web_view()`).
- `window.open(url, '_system')` → `LaunchMode.EXTERNAL_APPLICATION`.
- `mailto:` / `tel:` → `launch_url("mailto:...")` with default mode (`can_launch_url` returns `False` on iOS/Android unless `LSApplicationQueriesSchemes`/`<queries>` are declared, so do not gate on it).
- `app-settings:` → `PermissionHandler.open_app_settings()` (cross-platform; the Ionic page is iOS-only).
- For buttons/list tiles that only open a link, prefer the client action `action=ft.OpenUrl(url, target=ft.UrlTarget.BLANK)` so the PWA build is not blocked by iOS Safari popup rules (`ClientAction` docstring, `FLET/controls/client_action.py`).
- If the account page must intercept the post-login redirect, embed `flet_webview.WebView(url=..., on_url_change=..., prevent_links=[...])` (`webview_flutter ^4.13.1`; mobile + macOS + web).

### 2.4 `@capacitor/share` (+ `Filesystem` temp files) → `ft.Share`

`FLET/controls/services/share.py`: `async share_text(text, *, title, subject, ...) -> ShareResult`, `async share_uri(uri)`, `async share_files(files: list[ShareFile], *, title, text, subject, ...) -> ShareResult`; `ShareFile.from_path(path)` / `ShareFile.from_bytes(data, mime_type=, name=)`; `ShareResult(status: ShareResultStatus{SUCCESS, DISMISSED, UNAVAILABLE}, raw)`; `ft.ShareText` client action. Dart: `share_plus ^12.0.1`.

Port: both app call sites write to `Directory.Cache` then share a URI. In Flet share bytes directly:
`await share.share_files([ft.ShareFile.from_bytes(ics.encode(), mime_type="text/calendar", name=f"{slug}.ics")], title=session.name)`.
The `.ics` builder (`session-detail.ts:361-420`) ports 1:1 to Python (`\r\n`, escaping, UTC stamps). The encrypted debug dump (`crypto-js AES` + base64, `about-pycon.page.ts:56-70`) → `cryptography.fernet` or `AES-CBC` via `cryptography` (pure-Python wheels exist on pypi.flet.dev for iOS/Android; verify with `flet build` before committing to it) — or simply share the sqlite file with `ShareFile.from_path`.

### 2.5 `@capacitor/haptics` → `ft.HapticFeedback`

`FLET/controls/services/haptic_feedback.py`: `heavy_impact()`, `medium_impact()`, `light_impact()`, `vibrate()`, `selection_click()`. The Ionic app never calls the plugin from TS (only Ionic components use it internally). Optional nicety: `light_impact()` on a successful scan.

### 2.6 `@capacitor/filesystem` → Python I/O + storage paths

- `FLET_APP_STORAGE_DATA` (durable, app-private, backed up; also the CWD), `FLET_APP_STORAGE_CACHE`, `FLET_APP_STORAGE_TEMP` env vars (`DOCS/reference/environment-variables.md:124`, `DOCS/cookbook/read-and-write-files.md`).
- `ft.StoragePaths` (`FLET/controls/services/storage_paths.py`): `get_application_cache_directory()`, `get_application_documents_directory()`, `get_application_support_directory()`, `get_temporary_directory()`, `get_downloads_directory()`, Android-only `get_external_storage_directory()`/`get_external_cache_directories()`/`get_external_storage_directories()`, Apple-only `get_library_directory()`, `get_console_log_filename()`. Each raises `FletUnsupportedPlatformException` on web (`if self.page.web`).
- Capacitor `Directory.Cache` ≡ `FLET_APP_STORAGE_CACHE`; `Directory.Data`/`Documents` ≡ `FLET_APP_STORAGE_DATA`. Where an app can write on iOS/Android: only inside its sandbox (these dirs); nothing else without the picker.
- Web/PWA build: no filesystem → share bytes (2.4) and keep caches in memory / `SharedPreferences` (localStorage).

### 2.7 `@capacitor/app` → page lifecycle, back navigation, deep links, app info

- `Page.on_app_lifecycle_state_change: EventHandler[AppLifecycleStateChangeEvent]` (`page.py:630`), `e.state` ∈ `AppLifecycleState.{SHOW, RESUME, HIDE, INACTIVE, PAUSE, DETACH, RESTART}` (`types.py:1106`). `appStateChange isActive=true` ≡ `RESUME`. Also `page.app_visible` / `await page.wait_until_visible()` (`page.py:899-909`).
- Back button / swipe-back: `Page.on_view_pop` (`ViewPopEvent(route, view)`, `page.py:643`), `Page.on_views_pop_until`, `await page.push_route(route)`, `page.navigate(route)`, `await page.pop_views_until(route, result)` (`page.py:1013-1108`). In declarative mode `ft.Router(routes, not_found=, manage_views=True)` + `page.render_views(...)` gives system back, swipe-back and the `AppBar` implicit back button for free (docstring at `router.py:593-650`); `ft.Route(path, index, component, children, loader, outlet, modal, recursive)`; hooks `use_route_params()`, `use_route_location()`, `use_route_outlet()`, `use_route_loader_data()`, `is_route_active()`.
- Deep links: the Ionic manifest has **none**; if added later: `[tool.flet.deep_linking] scheme="https" host="mobile.us.pycon.org"` (`build_base.py:1421`, template `Info.plist` `CFBundleURLTypes` + manifest `<data android:scheme>`), then handle `page.route` on start and `Page.on_route_change` (`RouteChangeEvent.route`).
- `App.getInfo()` version/build: **partial** — no Python accessor. Options: `importlib.metadata.version("pycon_us")` (project version is set from `[project].version` by `flet build`), or add a tiny `page.get_app_info()` to core (Dart already depends on `package_info_plus ^9.0.0`) — nice first-party improvement, S.

### 2.8 Splash screen, status bar, keyboard → `flet build` + theme

- Splash: `flutter_native_splash` generated by `flet build` from `assets/splash.png`, `splash_dark.png`, per-platform `splash_<platform>.png`; colours `[tool.flet.splash] color = "#680579"`, `dark_color`, Android-12 `icon_background`; disable with `--no-ios-splash` etc. (`DOCS/publish/index.md:981-1176`). Difference: Capacitor keeps the splash until `SplashScreen.hide()` after data load. Flutter's native splash disappears at first frame; Flet then shows its own boot screen while Python starts (`DOCS/publish/index.md:1178 "Boot screen"`). To reproduce "splash until schedule loaded", render a branded loading `View` (same `#680579`) until the cached schedule is read — reading the local cache first makes this sub-second.
- Status bar: `ft.Theme(system_overlay_style=ft.SystemOverlayStyle(status_bar_color=, status_bar_brightness=, status_bar_icon_brightness=, system_navigation_bar_color=, ...))` (`theme.py:690-740, 3606`) + `ft.SafeArea`. No `@capacitor/status-bar` call sites exist in the app anyway.
- Keyboard: handled by the Material `Scaffold` (`DART/controls/view.dart:199`) and `android:windowSoftInputMode="adjustResize"` in the template manifest; `TextField(autofill_hints=ft.AutofillHint.EMAIL/PASSWORD)` replaces `autofill.directive.ts`.

### 2.9 **GAP** — barcode / QR scanning (`@capacitor-mlkit/barcode-scanning`)

**What exists:** `flet_camera.Camera(ft.LayoutControl)` (`PKGS/flet-camera/src/flet_camera/camera.py`, Flutter `camera ^0.12.0`): `initialize()`, `take_picture() -> bytes`, `start_image_stream()`/`stop_image_stream()` with `CameraImageEvent`, zoom/flash/focus. **No barcode detection anywhere in the repo** (`grep -ril barcode|mobile_scanner|firebase` over `.py/.dart/.md/.yaml/.toml` → nothing). Decoding frames in Python (pyzbar/opencv) is not viable: frames cross the Dart→Python bridge as bytes, and `pyzbar`/`opencv` need native libs that are not on pypi.flet.dev.

**Research (pub.dev, 2026-10-11):**
- `mobile_scanner` **7.4.2** (BSD-3) — camera preview + ML Kit (Android) / AVFoundation (iOS) / web. Android: bundled ML Kit model (+3–10 MB) by default; unbundled (+600 KB, Play-Services download) via `dev.steenbakker.mobile_scanner.useUnbundled=true` in `android/gradle.properties` (not settable from `pyproject` → accept bundled, or template fork). iOS: `NSCameraUsageDescription`. `MobileScannerController(formats: [BarcodeFormat.qrCode], facing: CameraFacing.back, torchEnabled, detectionSpeed, detectionTimeoutMs)`; widget params `controller, onDetect(BarcodeCapture), fit, errorBuilder, placeholderBuilder, overlayBuilder, scanWindow, useAppLifecycleState, tapToFocus`.
- material_ui gate (`.agents/skills/implement-flet-extension/SKILL.md` §3): `lib/src/mobile_scanner.dart` imports `package:flutter/material.dart` but its `build()` only instantiates `ValueListenableBuilder, ColoredBox, Center, Column, Padding, Icon, Text, LayoutBuilder, SizedBox, ClipRect, FittedBox, Stack, IgnorePointer, GestureDetector` plus `Icons.error`/`Colors.*` constants — no `Material`/`Scaffold`/`InkWell`/`ThemeData`. It renders fine under `material_ui`; still pass our own `errorBuilder`/`placeholderBuilder` built from `package:material_ui` so no SDK-Material text styling leaks in.
- `google_mlkit_barcode_scanning` 0.16.1 (MIT): decoder only, no preview; would need `camera` + frame plumbing in Dart — more work, no benefit here.
- Decision: **`mobile_scanner`**.

**Extension plan — `flet-barcode-scanner`** (`PKGS/flet-barcode-scanner`, Python `flet_barcode_scanner`, Dart `flet_barcode_scanner`), effort **M** (~2–3 days incl. docs/tests):
1. `pubspec.yaml`: `mobile_scanner: 7.4.2`, `material_ui` (same constraint as `flet/packages/flet/pubspec.yaml`), `flet: path ...`.
2. Python (`LayoutControl`, since it is a visual preview):
   ```python
   @ft.control("BarcodeScanner")
   class BarcodeScanner(ft.LayoutControl):
       formats: list[BarcodeFormat] = field(default_factory=lambda: [BarcodeFormat.ALL])
       facing: CameraFacing = CameraFacing.BACK
       torch: bool = False
       detection_speed: DetectionSpeed = DetectionSpeed.NORMAL   # noDuplicates / normal / unrestricted
       detection_timeout: ft.DurationValue = 250ms
       fit: ft.BoxFit = ft.BoxFit.COVER
       scan_window: Optional[ft.Rect] = None
       auto_start: bool = True
       on_detect: Optional[ft.EventHandler[BarcodeDetectEvent]] = None   # .barcodes: list[Barcode]
       on_error: Optional[ft.EventHandler[BarcodeScannerErrorEvent]] = None
       async def start(self) / stop(self) / toggle_torch(self) / switch_camera(self)
       async def analyze_image(self, data: bytes) -> list[Barcode]   # optional
   @ft.value class Barcode: raw_value: str | None; display_value; format: BarcodeFormat; corners: list[ft.Offset]
   ```
   Dart: `MobileScannerController` created in `initState` from control props, `onDetect` → `control.triggerEvent("detect", {...})`, methods via `control.addInvokeMethodListener`; parse enums with `parseEnum(BarcodeFormat.values, ...)`; match every Python default on the Dart side (skill "Default Value Matching").
3. Permissions: `[tool.flet] permissions = ["camera"]` expands to `NSCameraUsageDescription` + `android.permission.CAMERA` (+ optional camera features `false`) — `CLI/build_base.py` `cross_platform_permissions["camera"]`; the template `Podfile` auto-derives `PERMISSION_CAMERA=1` for `permission_handler` from that plist key (seen in cached `build-template v1.0.4 ios/Podfile:41-62`). Runtime prompt before showing the control: `await ph.request(Permission.CAMERA)`; `PERMANENTLY_DENIED` → `ph.open_app_settings()` (mirrors `show_permissions_error` in `door-check.page.ts`).
4. Register in `client/pubspec.yaml` + `client/lib/main.dart`, `sdk/python/pyproject.toml` (deps + `[tool.uv.sources]`), `packages/flet/pyproject.toml` extensions group, `flet_build_test/pyproject.toml`, `tools/crocodocs/pyproject.toml`, CI `PACKAGES` + publish loop; docs `DOCS/controls/barcodescanner/`; example `sdk/python/examples/extensions/barcode_scanner/`; integration tests under `packages/flet/integration_tests/extensions/barcode_scanner/` (no real camera in CI → test control construction/props; mark device tests manual).
5. App usage: one `@ft.component Scanner(on_code)` reused by door-check, T-shirt, lead-retrieval and mask-violation pages; `ft.use_effect(lambda: scanner.stop, [])` for `ionViewWillLeave`; debounce identical codes for 3 s like `scan_timeout`.

### 2.10 **GAP** — push notifications & analytics (`@capacitor-firebase/messaging`, `@capacitor-firebase/analytics`)

**Research (pub.dev):** `firebase_core` **4.15.0**, `firebase_messaging` **16.7.0** (needs `firebase_core ^4.14.0`), `firebase_analytics` **12.6.0** (same), all BSD-3. FlutterFire requires iOS 15 and Android 7.0 / API 24 — compatible with Flet 1.1.0 (iOS 15 minimum per `CHANGELOG.md` 1.1.0; template `minSdk = flutter.minSdkVersion` unless `min_sdk_version` is set).

**What FlutterFire needs vs what `flet build` offers today** (checked in `CLI/build_base.py`, `DOCS/publish/*.md` and the cached `build-template v1.0.4` zip):

| Requirement | `flet build` support |
|---|---|
| Firebase config (`google-services.json`, `GoogleService-Info.plist`) | No file-drop hook. Alternative: `flutterfire configure` output is just `FirebaseOptions` (apiKey, appId, messagingSenderId, projectId, storageBucket, iosBundleId) → pass them **from Python** into a `FirebaseCore(Service)` and call `Firebase.initializeApp(options: FirebaseOptions(...))` in Dart. This avoids both native files for Dart-only initialization. **Unverified** whether Analytics/Messaging on Android work without the `com.google.gms.google-services` Gradle plugin (FlutterFire docs confirm the CLI "adds the required product-specific Gradle plugins" only for Crashlytics/Performance). Prototype on Android first. |
| Android Gradle plugin `com.google.gms.google-services` | Not configurable (`app/build.gradle.kts` / `settings.gradle.kts` have no `pyproject` hooks) → template fork (`[tool.flet.template] url/ref/dir`, `DOCS/publish/index.md "Build template"`) if the Dart-only path fails. |
| Android `POST_NOTIFICATIONS` (API 33+) | `[tool.flet.android.permission] "android.permission.POST_NOTIFICATIONS" = true` + runtime `PermissionHandler.request(Permission.NOTIFICATION)`. |
| iOS `aps-environment` entitlement (Push Notifications capability) | **No iOS entitlements option** — only `--macos-entitlements` / `[tool.flet.macos.entitlement]` (`build_base.py:705,1234`); the iOS template has no `Runner.entitlements`. → flet-cli feature request `[tool.flet.ios.entitlement]` (S), or template fork, or post-build patch of `build/flutter/ios/Runner/` before archiving. |
| iOS `UIBackgroundModes = ["remote-notification"]` | `[tool.flet.ios.info] UIBackgroundModes = ["remote-notification"]` (`DOCS/publish/ios.md:546`). |
| APNs auth key in Firebase console | manual, same as today. |
| `AppDelegate` changes (`FLTFirebaseMessagingPlugin.configureNotificationCenterDelegate()` for UIScene apps) | template `AppDelegate.swift` is stock `FlutterAppDelegate` → fork only if needed (Flet's template does not use UIScene, so probably not). |
| Background handler = top-level Dart fn with `@pragma('vm:entry-point')` | Possible in the extension's Dart code, but **Python is not running in that isolate**: data-only background messages cannot reach Python. Design for *notification* messages (OS displays them) and surface taps via `getInitialMessage()`/`onMessageOpenedApp` once Python is up. Fits the app: all four topics are display notifications. |

**Extension plan — `flet-firebase`** (one Python package, three services), effort **L** (1–2 weeks incl. the build-tooling work):
```python
class FirebaseCore(ft.Service):   # ios/android/web FirebaseOptions as @ft.value dataclasses
    options: FirebaseOptions | None; android_options; ios_options; web_options
class FirebaseMessaging(ft.Service):
    on_token_refresh: EventHandler[TokenEvent]; on_message: EventHandler[RemoteMessageEvent]  # foreground
    on_message_opened_app: EventHandler[RemoteMessageEvent]
    async request_permission(alert=True, badge=True, sound=True, provisional=False) -> AuthorizationStatus
    async get_token() -> str | None; async get_apns_token(); async subscribe_to_topic(topic); async unsubscribe_from_topic(topic)
    async get_initial_message() -> RemoteMessage | None; async set_foreground_presentation_options(...)
class FirebaseAnalytics(ft.Service):
    async log_event(name, params: dict | None); async set_user_property(name, value); async set_user_id(id)
    async set_analytics_collection_enabled(bool); async set_consent(...)
```
Dart: `firebase_core: 4.15.0`, `firebase_messaging: 16.7.0`, `firebase_analytics: 12.6.0`; services only, no widgets, so the material_ui gate is moot. Mirror the app's `TOPIC_BY_CATEGORY` logic in Python unchanged. Note `firebase_messaging` deprecates `getToken()/onTokenRefresh` in favour of FID `register()/onRegistered` — expose the new API.

**Simplest alternative (recommended for the first release):** server-driven announcements. The app already talks to `us.pycon.org/2026/api/v1/...`; add `GET /api/v1/announcements?since=<ts>&topics=emergency,announcements,...` and poll it on `AppLifecycleState.RESUME` + every N minutes while visible (`page.run_task` + `asyncio.sleep`), showing a `ft.SnackBar`/banner — identical UX to the current foreground toast; what is lost is the OS-level notification when the app is closed. Web push for the PWA build: **GAP** (no Flet support). OneSignal (`onesignal_flutter`) needs the same APNs entitlement/AppDelegate work — no gain over FCM. Analytics: post events from Python with `httpx` to Plausible/Matomo/GA4 Measurement Protocol — trivial, and privacy-friendlier than the SDK (the Ionic app already strips `AD_ID`).

### 2.11 **GAP** — local notifications (`@capacitor/local-notifications`)

**Research:** `flutter_local_notifications` **22.3.1** (BSD-3; `timezone ^0.11.0` for `zonedSchedule(TZDateTime)`, `AndroidScheduleMode.exactAllowWhileIdle` ≡ `allowWhileIdle`), `flutter_timezone` 5.1.1 (`FlutterTimezone.getLocalTimezone()`), Apache-2.0. Android needs: core-library desugaring (`desugar_jdk_libs 2.1.4`), Java 17 (template already has `JavaVersion.VERSION_17`, **no desugaring** in `app/build.gradle.kts` → template fork or upstream template change), `RECEIVE_BOOT_COMPLETED` + `SCHEDULE_EXACT_ALARM`/`USE_EXACT_ALARM` permissions (`[tool.flet.android.permission]` handles these), `<receiver>` entries for `ScheduledNotificationReceiver`/`ScheduledNotificationBootReceiver` (the template manifest only supports `<uses-permission>`, `<uses-feature>`, `<meta-data>`, `<provider>`, deep-link `<data>` — **no `<receiver>`** → template fork unless the plugin's own merged manifest suffices; verify with the manifest merger report, `DOCS/publish/android.md:831-880`). iOS: `UNUserNotificationCenter.current().delegate = self` in `AppDelegate` (only for foreground presentation; template `AppDelegate.swift` is stock) and runtime `requestPermissions(alert:badge:sound:)`.

**Extension plan — `flet-local-notifications`** (Service), effort **M–L** (plugin ~2 days; the Android/iOS template plumbing is the real cost):
```python
class LocalNotifications(ft.Service):
    on_tap: EventHandler[NotificationTapEvent]   # payload
    async request_permissions(alert=True, badge=True, sound=True) -> bool
    async schedule(id: int, title, body, at: datetime, *, payload=None, android: AndroidNotificationDetails|None, ios: DarwinNotificationDetails|None, schedule_mode=AndroidScheduleMode.EXACT_ALLOW_WHILE_IDLE)
    async show(id, title, body, payload=None); async cancel(id); async cancel_all(); async get_pending() -> list[PendingNotification]
    async get_launch_details() -> NotificationLaunchDetails | None
```
Dart converts the tz-aware `datetime` (serialize as ISO-8601 with offset) to `TZDateTime` after `tz.setLocalLocation(tz.getLocation(await FlutterTimezone.getLocalTimezone()))`; ids stay 32-bit ints (app uses 8000–8010, 8999). Permissions: `Permission.NOTIFICATION`, `Permission.SCHEDULE_EXACT_ALARM` via `PermissionHandler`.

**Defer?** Yes. The 11 reminders are hard-coded conference dates; for 2026 they can be (a) server pushes (2.10) or (b) "Add to calendar" with alarms (2.12), or (c) in-app banners computed from the same table while the app is open. Ship the extension for the following year.

### 2.12 **GAP** — add to calendar (`@ebarooni/capacitor-calendar`)

**Research:** `add_2_calendar` **3.1.1** (MIT, ~3 months old, unverified publisher) opens the OS calendar editor pre-filled (`Add2Calendar.addEvent2Cal(Event(title, description, location, startDate, endDate, iosParams: IOSParams(reminder, url), androidParams))`) — the same UX as `createEventWithPrompt`; **no runtime permission** on either platform for the prompt path; iOS needs `NSCalendarsUsageDescription` (+ `NSContactsUsageDescription`, the README warns of a crash without it); Android API 30+ needs a `<queries>` block for `android.intent.action.INSERT` / `vnd.android.cursor.item/event` — the template manifest has **no `<queries>` hook** (another small flet-cli feature: `[tool.flet.android.queries]`). `device_calendar` 4.3.3 (2 years old, silent writes, full calendar permission) — reject.

**Zero-extension path that works today:** port `buildIcs()` to Python and `ft.Share.share_files([ShareFile.from_bytes(ics, mime_type="text/calendar", name=...)])` — the Ionic app already uses exactly this as its fallback, and on iOS the share sheet offers Calendar/Mail, on Android any calendar app registered for `text/calendar`. Ship this; add `flet-add-to-calendar` (Service with one `add_event(...)` method, effort **S**, ½ day + docs) when the `<queries>` hook exists.

### 2.13 `@capacitor/device` → `page.platform` / `page.get_device_info()`

`page.platform: PagePlatform` (`page.py:596`), `page.web`, `page.pwa`, `page.platform_brightness`, `page.client_ip`; `await page.get_device_info()` returns `WebDeviceInfo`/`AndroidDeviceInfo`/`IosDeviceInfo`/`MacOsDeviceInfo`/`LinuxDeviceInfo`/`WindowsDeviceInfo` (`page.py:1370-1393`, `FLET/controls/device_info.py`; Dart `device_info_plus ^12.3.0`). Replaces `Capacitor.getPlatform()` in `autofill.directive.ts` and `environment.dev.ts` (`10.0.2.2` vs `127.0.0.1` dev host → `page.platform == PagePlatform.ANDROID`).

### 2.14 `@capacitor/live-updates` (Appflow OTA) — why Flet cannot do this, and what to do instead

- Capacitor apps are a native shell around a web bundle; Appflow swaps the bundle at cold start (`LiveUpdates.sync()`/`reload()` in `live-update.service.ts`). A Flet app built with `flet build` is a Flutter app whose **Python app is packaged by `serious_python` into the Flutter assets** and unpacked read-only at first run (`DOCS/publish/index.md:168-190` "How it works", `DOCS/updates/breaking-changes/v0-86-0/app-files-unpacked-read-only-bundle.md`). There is no runtime that re-fetches that asset; swapping `.py`/`.pyc` files and re-importing a running app is not supported, and Apple's Guideline 2.5.2 forbids downloading interpreted code that changes app behaviour — do not build a home-grown Python OTA.
- Shorebird (`shorebird_code_push` 2.0.7): patches **Dart code only**; "does not support changing native code", and asset diffs are blocked/warned (`--allow-asset-diffs` "strongly discouraged") — the Python bundle is an asset, so Shorebird cannot update it.
- Alternatives, in order:
  1. **Server-driven content** — the schedule, speakers, sponsors, rooms, features flags (`fetchFeatures`), menu copy, reminder table and announcement texts all come (or can come) from the us.pycon.org API; keep the Python side a thin renderer with a versioned JSON cache under `FLET_APP_STORAGE_DATA`. This removes most reasons the Ionic app needed OTA.
  2. **Fast store releases** — `flet build ipa` + TestFlight / `flet build aab` + internal testing track from CI (`DOCS/publish/ios.md` export methods `app-store-connect`, `release-testing`); Apple expedited review for conference week.
  3. **Web/PWA** build (`flet build web`, Pyodide) for instant updates to a browser audience; note `mobile_scanner` supports web, `SecureStorage` has `WebOptions`, but notifications/filesystem do not exist there. The app already ships a PWA (`ngsw-config.json`, Firebase Hosting) so this keeps parity.
- Drop `LiveUpdateService`, the "pending update" banner (`has-pending-update`), and `make appflow-ship`.

### 2.15 `patch-package`

The single patch only changes a CocoaPods subspec of a Capacitor plugin. In Flet the Dart dependency graph is owned by the extension's `pubspec.yaml`; forks are expressed with `[tool.flet.flutter.pubspec.dependency_overrides]` (`DOCS/publish/index.md:1871-1896`). Nothing to port.

### 2.16 `flet-permission-handler` (cross-cutting)

`PermissionHandler(ft.Service)` (`permission_handler 12.0.1`): `async get_status(permission) -> PermissionStatus | None`, `async request(permission) -> PermissionStatus | None`, `async open_app_settings() -> bool`; `before_update()` raises `FletUnsupportedPlatformException` outside Android/iOS/Windows/web. Enums: `Permission.CAMERA`, `NOTIFICATION`, `CALENDAR_WRITE_ONLY`, `CALENDAR_FULL_ACCESS`, `SCHEDULE_EXACT_ALARM`, `CRITICAL_ALERTS` (iOS), …; `PermissionStatus.GRANTED/DENIED/PERMANENTLY_DENIED/LIMITED/PROVISIONAL/RESTRICTED`. Declaration side: `[tool.flet].permissions = ["camera"]` bundle or explicit `[tool.flet.ios.info]` / `[tool.flet.android.permission]` tables (`DOCS/publish/index.md:1658-1700`, `ios.md:479`, `android.md:740`); the template `Podfile` turns the plist keys into `permission_handler`'s `PERMISSION_*` macros automatically (cached template `ios/Podfile:41-62`) — no Podfile editing needed for camera, calendar or notifications.

---

## 3. Extensions the port requires vs can defer

**Required for feature parity on day one**
1. **`flet-barcode-scanner`** (`mobile_scanner 7.4.2`) — **M**. Lead retrieval, door check, T-shirt redemption and mask-violation pages are unusable without it; no workaround exists.
2. **flet-cli: iOS entitlements option** (`[tool.flet.ios.entitlement]` / `--ios-entitlements`, mirroring the macOS one in `build_base.py:705,1234`) — **S**. Blocks any push-notification extension (FCM or OneSignal) from building without a template fork.

**Required only if real push is a day-one requirement (otherwise phase 2)**
3. **`flet-firebase`** (core + messaging + analytics) — **L**. Prototype Dart-only `FirebaseOptions` initialization first; if Android needs the google-services Gradle plugin, add a `[tool.flet.android.gradle_plugins]`-style hook or ship a documented template fork. Interim: polled announcements endpoint + `httpx` analytics events (**S**, no extension).

**Can defer (shippable without them)**
4. **`flet-add-to-calendar`** (`add_2_calendar 3.1.1`) — **S**; needs a `[tool.flet.android.queries]` manifest hook (**S**). Day one: `.ics` via `ft.Share.share_files`.
5. **`flet-local-notifications`** (`flutter_local_notifications 22.3.1` + `timezone` + `flutter_timezone`) — **M–L** because of desugaring/receivers/AppDelegate template work. Day one: calendar export or server push for the 11 fixed reminders.
6. **`page.get_app_info()`** in core (expose `package_info_plus`) — **S**, cosmetic (About page version string).

**Nothing to build** for storage (SharedPreferences + SecureStorage + sqlite), network, URL launching / in-app browser, share, haptics, filesystem, lifecycle/back/deep links, splash/status bar/keyboard, device info, permissions.

---

## 4. Risks

- **Template-level customisation is the recurring blocker**: iOS entitlements, `AppDelegate`, Gradle plugins (`google-services`, desugaring), manifest `<receiver>`/`<queries>` have no `pyproject` hooks today; each push/notification/calendar extension needs either flet-cli features or a forked `flet-build-template` pinned per Flet version (`[tool.flet.template] url/ref`), which is a maintenance liability right before a conference.
- **Push in the background cannot run Python** — FCM data-only messages and local-notification actions can only be processed when the app is foregrounded; design around notification-type messages.
- **Firebase Dart-only init on Android is unverified** for Analytics/Messaging without the Gradle plugin; budget a spike.
- **`mobile_scanner` pulls `package:flutter/material.dart`**; it currently builds only widgets-layer widgets, but an upstream minor could add a Material widget — pin `7.4.2` exactly and cover with an integration test (skill "Upgrade and Compatibility Guardrails"). Bundled ML Kit adds 3–10 MB to the APK (unbundled needs `gradle.properties`, i.e. a template change).
- **No OTA**: any copy/schedule-logic bug found during the conference needs a store release unless the content is server-driven; move all conference-specific tables (reminders, menus, feature flags) to the API.
- **Secrets migration**: Ionic kept API `key`/`secret` in IndexedDB; the Flet app is a new bundle/app-id, so users must log in again anyway — use `SecureStorage` from the start.
- **Web/PWA parity**: `StoragePaths`/filesystem, local notifications and push are unavailable on web; `SharedPreferences` is `localStorage` (size-limited) — keep the PWA scope to schedule/browse features.
- **Minimums**: Flet 1.1.0 requires iOS 15; FlutterFire requires iOS 15 / Android 7.0 (API 24); `mobile_scanner`/`permission_handler` are fine with that. `flet build` 1.1.0 uses Flutter 3.47.7 / Gradle 9.3.1 / AGP 8.13.2 — any plugin still on `jcenter()` will not build (`CHANGELOG.md` 1.1.0); all packages chosen above are actively maintained (≤ 3 months old) except `device_calendar` (rejected).
