# PyCon US on Flet: building, packaging, distribution and CI

Research date: 2026-10-11. Target: Flet **1.1.0** (in development; `CHANGELOG.md` top section) with
Flutter **3.47.7** (`flet.version.flutter_version`). The local SDK package still reports `1.0.4`
(`uv run --offline python -c "import flet.version as v; print(v.flet_version)"`), which is expected
for an unreleased version.

Abbreviations used for paths:

| Alias | Path |
|---|---|
| `CLI/` | `flet/sdk/python/packages/flet-cli/src/flet_cli/` |
| `TPL/` | `flet/sdk/python/templates/build/{{cookiecutter.out_dir}}/` (the `flet build` cookiecutter template) |
| `DOCS/` | `flet/website/docs/` |
| `ACTION/` | `flet-others/flet-build-action/` |
| `IONIC/` | `others/pycon-us/excluded/pycon-us-mobile/` |

Everything marked **verified** was read in local source. **GAP** = `flet build` cannot do it today.
**PLAUSIBLE** = a workaround that follows from documented Gradle/Xcode behaviour but has not been
built and run for this report.

---

## 0. Summary

* **Ship as an update to the existing store listings: technically possible.** `flet build` takes a
  separate bundle ID for each platform (`[tool.flet.android].bundle_id = "org.pycon.us"`,
  `[tool.flet.ios].bundle_id = "org.pycon.us.2023.onsite"`). The version comes from
  `[project].version` and the build number from `--build-number`, so 26.2.1 / 26022 can continue as
  27.0.0 / 27000. This only works if the PSF gives access to App Store Connect (team `BMM5U3QVKW`)
  and to the Play Console plus the upload key. Without that, the result is a new listing.
* **Version 1 needs no custom build template.** The schedule, info pages, sponsors, maps, favourites,
  the camera permission for badge scanning, splash, icons, signing, deep links (custom scheme) and the
  web build all fit in `pyproject.toml`. Section 4 has the full file. All 39 keys it sets were
  checked against flet-cli's own loader and its key set
  (`scratchpad/scripts/check_keys.py`: every key is either read by `CLI/commands/build_base.py` /
  `build.py` or rendered by the template).
* **Template-level gaps start with phase 2**, when push notifications, exact local notifications,
  password autofill and verified links arrive:
  * iOS entitlements (`aps-environment`, `associated-domains`)
  * Android `<queries>`
  * Android App Links with `autoVerify`
  * core-library desugaring for `flutter_local_notifications`
  * resource-valued `<meta-data>`
  * Firebase config files

  Each one is small (S) to add to flet-cli. Since the person asking maintains Flet, the recommended
  path is to add these upstream before the conference rather than fork the template (section 11).
* **CI:** `flet-dev/flet-build-action@v1` runs a matrix of `aab` (ubuntu), `ipa` (macos-26) and
  `web` (ubuntu). The signing steps around it are documented in `DOCS/publish/ios.md` "Building and
  signing in CI" and in the Android signing environment variables. Store upload is a separate step
  (`altool`, `r0adkll/upload-google-play`), and so is the Firebase Hosting deploy (section 5).
* **Appflow live updates have no Flet equivalent, by design.** Python ships inside the app bundle,
  and Apple guideline 2.5.2 forbids downloading code. Replace them with a server-driven
  `app-config.json` that sets the minimum and latest version and announcement banners. That file
  drives the same "New version available" banner, which opens the store page (section 8).
* **On-device development:** `flet run --ios/--android` with the Flet companion app gives hot reload
  but only Flet's built-in extensions. `flet debug ios|android` builds the real app with every
  extension but has no Python hot reload (section 7).

---

## 1. The Ionic pipeline being replaced (verified)

| Ionic piece | Value / behaviour | Source | Flet replacement |
|---|---|---|---|
| Android `applicationId` / namespace | `org.pycon.us` | `IONIC/android/app/build.gradle` | `[tool.flet.android].bundle_id = "org.pycon.us"`. The template derives namespace `org.pycon` + `.us` (`TPL/android/app/build.gradle.kts`: `namespace = "{{ org_name_2 }}.{{ package_name }}"`, `org_name_2 = bundle_id.rsplit('.',1)[0]`; `cookiecutter.json`). |
| Android version | `versionName "26.2.1"`, `versionCode 26022` | same | `[project].version = "27.0.0"` → `--build-name`; `--build-number 27000` → `versionCode` (`CLI/commands/build.py:197-209`; `build.gradle.kts` reads `flutter.versionCode`/`versionName`) |
| Android SDKs | `minSdkVersion 34` (deliberate: only OS versions that still get security updates), `compile/target 35` | `IONIC/android/variables.gradle` | `[tool.flet.android] min_sdk_version = 34`, `target_sdk_version = 36` (`TPL/android/app/build.gradle.kts` reads both through `get_pyproject`) |
| iOS bundle id | `org.pycon.us.2023.onsite`, `DEVELOPMENT_TEAM = BMM5U3QVKW` | `IONIC/ios/App/App.xcodeproj/project.pbxproj:395,406` | `[tool.flet.ios] bundle_id`, `team_id` |
| iOS version | `MARKETING_VERSION = 26.2.1`, `CURRENT_PROJECT_VERSION = 1` | pbxproj `:394,404` | `CFBundleShortVersionString = $(FLUTTER_BUILD_NAME)`, `CFBundleVersion = $(FLUTTER_BUILD_NUMBER)` (`TPL/ios/Runner/Info.plist`) |
| iOS deployment target | `18.0` | pbxproj `:323` | Fixed at **15.0** in the template (`TPL/ios/Runner.xcodeproj/project.pbxproj:348`); "can't be configured in pyproject.toml" (`DOCS/publish/ios.md` "Minimum iOS version") |
| iOS entitlements | `aps-environment`, `associated-domains = [webcredentials:us.pycon.org]` | `IONIC/ios/App/App/App.entitlements` | **GAP**: the iOS template has no `.entitlements`; only macOS has `[tool.flet.macos.entitlement]` (`CLI/commands/build_base.py:1234`) |
| iOS usage strings | Camera "Scanning Attendee badge QR codes"; `NSCalendarsUsageDescription` and `NSCalendarsWriteOnlyAccessUsageDescription` "Add PyCon US sessions to your calendar" | `research/ionic/info-notifications-native.md` §11.4 | `[tool.flet.ios.info]` (rendered by `render_dict(cookiecutter.options.info_plist)` in `TPL/ios/Runner/Info.plist`) |
| Splash | purple `#680579` (light and dark), image `Splash` | §11.4, `capacitor.config.ts` | `[tool.flet.splash] color/dark_color` plus `assets/splash.png` / `splash_dark.png` |
| `make capsync` | `ng build --configuration production` + `appflow live-update generate-manifest` + `cap sync`, then `check-no-dev-url` | `IONIC/Makefile`, `package.json` | `flet build <target>` (one step); see the guard in §5.3 |
| `check-no-dev-url` | Fails if a live-reload `server.url` was synced into the native config (the 26.2.0 white-screen incident) | `IONIC/Makefile` | That failure mode does not exist by construction. A release build only points at a dev server if someone passes `--dart-define=FLET_PAGE_URL=…` (`TPL/lib/main.dart:64-67`), and flet-cli never sets it (`grep FLET_PAGE_URL CLI/commands/*.py` → none). The release workflow still greps for it. |
| `make ios-live` / `android-live` | `ionic cap run … --livereload --external` | `IONIC/Makefile` | `flet run --ios/--android` (companion app, hot reload) or `flet debug ios/android` (real app shell), §7 |
| `make appflow-ship` | Builds the web bundle on Appflow (app `e8e09c7a`) and deploys it to channel `Production`; installed apps pick it up on next cold launch | `IONIC/Makefile`, `capacitor.config.ts` `LiveUpdates` | No OTA (by design). Use server config + store releases, §8 |
| `make pwa` + Firebase Hosting | `public: www`, rewrite `** → /index.html`, header for `ngsw-worker.js` | `IONIC/firebase.json` | `flet build web` + Firebase Hosting with the same SPA rewrite, §6 |
| Angular service worker | `ngsw-config.json`: prefetch app shell, lazy `/assets/**`, no `dataGroups` | `IONIC/ngsw-config.json` | **GAP**: Flutter 3.47's `flutter_service_worker.js` only unregisters itself (§6.4) |
| CI | PR only: `npm ci`, lint, `npm run build` on windows/macOS; no store or deploy automation | `IONIC/.github/workflows/CI.yml` | PR build plus a tag-driven release matrix with signing and uploads (§5) |
| Native plugin set | firebase analytics/messaging, mlkit barcode, local-notifications, calendar, inappbrowser, live-updates, … | §11.3 | Flet built-ins + `flet-*` extensions (§10, `research/flet/services-native-gaps.md`) |

The committed `IONIC/capacitor.config.ts` has syntax errors (missing commas after `server` and
`ios`). The synced per-platform `capacitor.config.json` files are git-ignored, and
`IONIC/capacitor.config.json` is `{}`. The real values come from `build.gradle`/`pbxproj` above, not
from the Capacitor config.

---

## 2. How `flet build` works (the parts that matter here, verified)

1. **Template**: a cookiecutter template (`TPL/`, shipped as `flet-build-template.zip` with each
   Flet release) is rendered into `<project>/build/flutter` and cached by a hash of its inputs
   (`DOCS/publish/index.md` "Build template"; `CLI/utils/template_cache.py`). The template receives:
   * curated values (`cookiecutter.options.*`: `info_plist`, `android_permissions`, `deep_linking`, …)
   * **the whole parsed `pyproject.toml`**: `cookiecutter.pyproject`, plus a `get_pyproject("a.b.c")`
     Jinja global (`templates/build/cookiecutter_extensions.py`)

   This is why `min_sdk_version`, `target_sdk_version` and `manifest_application` are read directly
   by the template. It also means **a forked template can read any new `[tool.flet.*]` key without
   touching flet-cli.**
2. **Icons and splash** are generated by **`flet-platform-assets`** (Pillow only), imported at
   `CLI/commands/build_base.py:14-29`. `flutter_launcher_icons` and `flutter_native_splash` are no
   longer used: `TPL/pubspec.yaml` has neither, and the code comment at `build_base.py:2159` says
   "flutter_launcher_icons overwrote them". The "How it works" step 2 in `DOCS/publish/index.md:177-180`
   is out of date on this point.
3. **Python packaging** goes through `serious_python package`. The requirement list is
   `[project].dependencies`, plus `[tool.flet.<platform>].dependencies` appended for that target,
   with `[tool.flet].dev_packages` rewritten to `name @ file:///abs/path` (plus `--no-cache-dir`)
   (`build_base.py:2600-2645`). **The app project itself is not pip-installed**: only its
   dependencies are, and the app directory (`[tool.flet.app].path`) is copied.
4. **Flutter extensions** are discovered rather than declared. A `flet-*` wheel ships its Dart
   package as package data under `flutter/<dart_pkg>`
   (`flet-camera/pyproject.toml [tool.setuptools.package-data] "flutter.flet_camera"`).
   serious_python copies those into `build/flutter-packages`. `register_flutter_extensions()` adds
   each one as a `path:` dependency to `pubspec.yaml`, and `TPL/lib/flet_generated.dart` imports it
   and instantiates `<dep>.Extension()` (`build_base.py:2032-2079`).
5. **Version and build number** are passed to `flutter build … --build-number N --build-name X.Y.Z`.
   Sources: `--build-number` or `[tool.flet].build_number` (global only, no per-platform key), and
   `--build-version` or `[project].version` (`CLI/commands/build.py:197-209`).
6. **Signing**:
   * Android: environment variables `FLET_ANDROID_SIGNING_KEY_STORE`, `_KEY_STORE_PASSWORD`,
     `_KEY_PASSWORD` and `_KEY_ALIAS` feed `signingConfigs.release`. Passwords are deliberately not
     readable from `pyproject.toml` (`build_base.py:3095-3130`; `TPL/android/app/build.gradle.kts:101-120`).
   * iOS: `exportOptions.plist` is rendered from `ios_export_method`, the provisioning profile, team
     and certificate, plus `export_options`. Without a profile, the build uses `--no-codesign` and
     produces only an `.xcarchive` (`CLI/commands/build.py:185-193`). The profile is checked before
     the build starts (`preflight_ios_signing`, `build.py:283+`).

---

## 3. Version and identity scheme

| | Today (Ionic) | Proposed (Flet) |
|---|---|---|
| Version string | `26.2.1` (YY.MINOR.PATCH) | `[project].version = "27.0.0"`, same YY.MINOR.PATCH scheme |
| Android `versionCode` | `26022` | `YY*1000 + MINOR*100 + PATCH*10 + RESPIN` → 27.0.0 = **27000** (> 26022, so Play accepts it as an upgrade) |
| iOS `CFBundleVersion` | `1` | Same integer as Android. Apple only requires it to increase within a version string. One number for both stores keeps support reports unambiguous. |
| Where the number comes from | Hand-edited | Computed in CI from `[project].version` plus a `respin` input (§5.2) and passed through the action's `build-number` input. No `[tool.flet].build_number` in the file, so local builds stay at the template default. |

Limits: MINOR ≤ 9, PATCH ≤ 9, RESPIN ≤ 9, which is plenty for one conference cycle per year.
`flet build` has a single `build_number` for every platform. That is not a gap here because the same
number works for both stores.

Bundle identifiers keep the store records. Android uses `org.pycon.us`. iOS uses
`org.pycon.us.2023.onsite`; the "2023" is a legacy segment that cannot change without a new App
Store record. `flet build` does not validate bundle-ID segments (`build_base.py:1635-1637`). The iOS
build only uses the iOS value. The Android Kotlin package is derived only when building for Android
(`org.pycon` / `us`), so the non-Java-safe `2023` segment never reaches Kotlin.

> If the same checkout builds `ipa` then `aab`, the different `bundle_id`s change the template inputs
> and the cached `build/flutter` project is regenerated. CI uses one runner per target, so this does
> not come up there.

---

## 4. Proposed `pyproject.toml` (all keys verified against flet-cli)

Repository layout this assumes (consistent with `research/flet/architecture-declarative-routing.md` §1):

```
pycon-us/                      # repo root = flet project root
├── pyproject.toml
├── firebase.json              # web hosting (§6)
├── src/                       # [tool.flet.app].path
│   ├── main.py
│   ├── assets/ (icon.png, splash.png, splash_dark.png, img/…)
│   └── pycon_us/ (… build_info.py is generated in CI, a dev default is committed)
├── extensions/                # local Flet extensions (Python + Dart), see §10
│   ├── flet-barcode-scanner/
│   ├── flet-local-notifications/
│   └── flet-add-to-calendar/
└── native/pycon_native_config/   # Flutter-only helper plugin: Android manifest additions (§4.4)
```

```toml
[project]
name = "pycon-us"                       # project slug -> pycon_us
version = "27.0.0"                       # -> CFBundleShortVersionString / versionName (continues 26.2.1)
description = "The official PyCon US conference app: schedule, speakers, sponsors, maps and more - built with Python."
readme = "README.md"
requires-python = ">=3.14,<3.15"         # bundles CPython 3.14.7 / Pyodide 314.0.7 (website/.crocodocs/python-versions.mdx)
authors = [{ name = "Python Software Foundation" }]
dependencies = [
    "flet==1.1.0",                       # pin exactly: the downloaded build template follows the installed flet
    "flet-permission-handler==1.1.0",
    "flet-secure-storage==1.1.0",
    "httpx>=0.28.1; platform_system != 'Emscripten'",   # same marker flet itself uses; not installed for web
]

[dependency-groups]
dev = [
    "flet-cli==1.1.0",
    "flet-desktop==1.1.0",
    "flet-web==1.1.0",
    "flet[test]==1.1.0",
    # mobile-only local extensions, so `flet run` on the laptop can import them
    "flet-barcode-scanner",
    "flet-local-notifications",
    "flet-add-to-calendar",
]

[tool.uv.sources]                        # uv / `flet run`: editable installs of the local extensions
flet-barcode-scanner = { path = "extensions/flet-barcode-scanner", editable = true }
flet-local-notifications = { path = "extensions/flet-local-notifications", editable = true }
flet-add-to-calendar = { path = "extensions/flet-add-to-calendar", editable = true }

# ------------------------------------------------------------------ flet build (all targets)
[tool.flet]
org = "org.pycon"
product = "PyCon US"                     # launcher label, CFBundleDisplayName, web <title>
company = "Python Software Foundation"
copyright = "Copyright (C) 2026 Python Software Foundation"
permissions = ["camera"]                 # bundle: NSCameraUsageDescription + CAMERA + camera features required=false
icon_background = "#ffffff"              # matches the current Android adaptive-icon background

[tool.flet.dev_packages]                 # flet build: rewrite to file:// URIs (relative to project root)
flet-barcode-scanner = "extensions/flet-barcode-scanner"
flet-local-notifications = "extensions/flet-local-notifications"
flet-add-to-calendar = "extensions/flet-add-to-calendar"

[tool.flet.app]
path = "src"
module = "main"
exclude = ["pycon_us/dev_fixtures"]      # exact relative paths, no globs

[tool.flet.compile]                      # defaults, stated explicitly: .pyc = faster cold start on mobile
app = true
packages = true

[tool.flet.cleanup]
packages = true
package_files = ["**/*.pyi"]

[tool.flet.splash]                       # native splash (Android/iOS/web), same purple as today
color = "#680579"
dark_color = "#680579"

[tool.flet.boot_screen]                  # screen between native splash and first Python frame
name = "flet"

[tool.flet.boot_screen.flet]             # mirrors the Ionic index.html app shell (purple + white ring)
theme_mode = "auto"
bgcolor_light = "#680579"
bgcolor_dark = "#680579"
spinner_size = 32
spinner_color_light = "#ffffff"
spinner_color_dark = "#ffffff"
fade_out_duration = 200

[tool.flet.deep_linking]                 # NEW capability (Ionic app has none): pyconus://app/<route>
scheme = "pyconus"
host = "app"

# Flutter-only helper plugin (no Python side). Its AndroidManifest is merged by Gradle (section 4.4).
# Path is resolved from build/flutter/pubspec.yaml, NOT from this file (DOCS/publish/index.md "Flutter dependencies").
[tool.flet.flutter.pubspec.dependencies]
pycon_native_config = { path = "../../native/pycon_native_config" }

# ------------------------------------------------------------------ Android
[tool.flet.android]
bundle_id = "org.pycon.us"               # existing Play listing
min_sdk_version = 34                     # keep the PSF policy (Flutter 3.47 default would be 24)
target_sdk_version = 36                  # = Flutter 3.47 default; stated so a Flutter bump cannot change it silently
dependencies = [                         # appended only for apk/aab
    "flet-barcode-scanner",
    "flet-local-notifications",
    "flet-add-to-calendar",
]

[tool.flet.android.permission]
"android.permission.POST_NOTIFICATIONS" = true          # API 33+ runtime prompt (always, at minSdk 34)
"android.permission.SCHEDULE_EXACT_ALARM" = true        # exact session reminders; user-granted on API 34+
"com.google.android.gms.permission.AD_ID" = false       # parity with Ionic (tools:node="remove")
"android.permission.READ_EXTERNAL_STORAGE" = false      # strip implied perms from camera plugins (android.md)
"android.permission.WRITE_EXTERNAL_STORAGE" = false

[tool.flet.android.meta_data]
"google_analytics_adid_collection_enabled" = "false"    # parity; harmless without Firebase

[tool.flet.android.signing]
key_alias = "upload"                     # key_store and passwords come from FLET_ANDROID_SIGNING_* env vars

# ------------------------------------------------------------------ iOS
[tool.flet.ios]
bundle_id = "org.pycon.us.2023.onsite"   # existing App Store record (id6446810296)
team_id = "BMM5U3QVKW"
export_method = "app-store-connect"
dependencies = [
    "flet-barcode-scanner",
    "flet-local-notifications",
    "flet-add-to-calendar",
]

[tool.flet.ios.export_methods.app-store-connect]
provisioning_profile = "PyCon US App Store"      # portal name or UUID; checked before the build
signing_certificate = "Apple Distribution"
export_options = { uploadSymbols = true, manageAppVersionAndBuildNumber = false }

[tool.flet.ios.export_methods.release-testing]
provisioning_profile = "PyCon US Ad Hoc"
signing_certificate = "Apple Distribution"

[tool.flet.ios.export_methods.debugging]
provisioning_profile = "PyCon US Development"
signing_certificate = "Apple Development"

[tool.flet.ios.info]
NSCameraUsageDescription = "PyCon US uses the camera to scan attendee badge QR codes."
NSCalendarsUsageDescription = "Add PyCon US sessions to your calendar."
NSCalendarsWriteOnlyAccessUsageDescription = "Add PyCon US sessions to your calendar."
NSContactsUsageDescription = "The calendar event editor may show contacts when you invite people to a session."
LSApplicationQueriesSchemes = ["mailto", "tel", "sms", "itms-apps"]
ITSAppUsesNonExemptEncryption = false    # HTTPS only -> no export-compliance prompt per TestFlight build (PSF to confirm)
NSAppTransportSecurity = { NSAllowsArbitraryLoads = false, NSAllowsLocalNetworking = true }
# phase 2 (FCM): UIBackgroundModes = ["remote-notification"]   (+ aps-environment entitlement = GAP, section 11)

# ------------------------------------------------------------------ Web (PWA replacement)
[tool.flet.web]
base_url = "/"                           # dedicated (sub)domain; use "/2027/app/" if mounted under us.pycon.org
route_url_strategy = "path"              # clean URLs; Firebase Hosting rewrites ** -> /index.html
renderer = "canvaskit"                   # Flet default; faster than skwasm for Flet's byte traffic
cdn = true                               # Pyodide/CanvasKit/fonts from CDN (see section 6.4 for offline)
wasm = true
pwa_short_name = "PyCon US"
pwa_background_color = "#680579"
pwa_theme_color = "#680579"              # replaces the Ionic-blue #387ef5 leftover
```

How this file was checked: it was written to the scratchpad and loaded with flet-cli's own
`flet_cli.utils.pyproject_toml.load_pyproject_toml`. Each key path was then matched to the code that
reads it:
* `build_base.py` / `build.py` for most keys
* generic lookups such as `get_platform_setting("dev_packages")`, `"compile.app"` and
  `f"tool.flet.{config_platform}.bundle_id"`
* the template for `min_sdk_version` and `target_sdk_version`

Result: 39/39 keys are set and consumed. The android dependency list resolves to
`flet==1.1.0, flet-permission-handler, flet-secure-storage, httpx; platform_system != "Emscripten",
flet-add-to-calendar, flet-barcode-scanner, flet-local-notifications`.

### 4.1 Permissions: what each line produces

| Need | iOS | Android | Verified at |
|---|---|---|---|
| Camera (badge QR: lead retrieval, door check) | `permissions=["camera"]` adds a default `NSCameraUsageDescription`, overridden by `[tool.flet.ios.info]` (merge order: bundle, then `ios.info`, then `--info-plist`). The template Podfile also enables `PERMISSION_CAMERA=1` for permission_handler. | Adds `CAMERA`, plus `android.hardware.camera*` `required=false` features | `build_base.py:255-269,1186-1213`; `TPL/ios/Podfile` permission mapping |
| Notifications | No Info.plist key. The prompt comes from the notification plugin. **The template Podfile mapping has no `PERMISSION_NOTIFICATIONS`**, so use the plugin's own `requestPermissions`, not flet-permission-handler, for iOS notifications. | `POST_NOTIFICATIONS` (plus `SCHEDULE_EXACT_ALARM` for exact reminders; `RECEIVE_BOOT_COMPLETED` normally comes from the plugin's merged manifest) | `TPL/ios/Podfile` mapping; `TPL/android/app/src/main/AndroidManifest.xml` permission loop |
| Calendar | `NSCalendarsUsageDescription` + `NSCalendarsWriteOnlyAccessUsageDescription` (iOS 17+), the same strings as Ionic. The Podfile maps `NSCalendarsUsageDescription` to `PERMISSION_EVENTS`. | Nothing if the event is created through the OS editor intent (`add_2_calendar`), as Ionic does today (no calendar permission in its manifest). Silent writes would need `READ/WRITE_CALENDAR`; not recommended. | Ionic report §11.3-11.4 |
| No cross-platform bundle exists for notifications or calendar | | | Bundles are only `location`, `camera`, `microphone`, `photo_library`, `biometric` (`build_base.py:232-319`). Unknown names in `permissions` are silently ignored (`build_base.py:1186-1189`). |

Flet nits found along the way (not blockers):
* The template's `PERMISSION_EVENTS` mapping lists `NSCalendarWriteOnlyAccessUsageDescription`. Apple's
  key is `NSCalendars…` with an "s", so the write-only key alone does not enable the macro.
* The `--permissions` CLI `choices` omit `biometric` (`build_base.py:748`) even though the bundle
  exists.
* The template Info.plist ships `NSAllowsArbitraryLoads = true`. Overriding it through
  `[tool.flet.ios.info]` appends a second `NSAppTransportSecurity` key after the template's. Check
  the built plist with `plutil -p …/Runner.app/Info.plist`; the last key should win.

### 4.2 iOS usage strings (final text)

| Key | Ionic text | Proposed |
|---|---|---|
| `NSCameraUsageDescription` | "Scanning Attendee badge QR codes" | "PyCon US uses the camera to scan attendee badge QR codes." (App Review prefers a full purpose sentence) |
| `NSCalendarsUsageDescription` | "Add PyCon US sessions to your calendar" | unchanged (+ period) |
| `NSCalendarsWriteOnlyAccessUsageDescription` | same | unchanged |
| `NSContactsUsageDescription` | — | Only if the chosen calendar plugin presents `EKEventEditViewController`. The `add_2_calendar` README warns it can crash without this key (`research/flet/services-native-gaps.md` §2.13). Drop it if the spike shows it isn't needed. |

### 4.3 Deep links, associated domains, app links

| Capability | Ionic today | Flet |
|---|---|---|
| Custom scheme `pyconus://app/...` | none | **exists**: `[tool.flet.deep_linking]` emits an Android `VIEW` intent-filter plus `flutter_deeplinking_enabled`, and iOS `CFBundleURLTypes` plus `FlutterDeepLinkingEnabled` (`TPL/android/.../AndroidManifest.xml:47-56`, `TPL/ios/Runner/Info.plist:53-68`). The route arrives as `page.route` / `on_route_change`. Only one scheme+host pair is supported. |
| Android App Links (`https://us.pycon.org/...`, verified) | none (Ionic only has `asset_statements` for credential sharing) | **GAP**: the deep-link intent-filter has no `android:autoVerify="true"`. Setting `scheme="https"` would make an unverified link, which Android 12+ opens in the browser. |
| iOS Universal Links (`applinks:`) | none | **GAP**: needs the `com.apple.developer.associated-domains` entitlement, and the iOS template has no entitlements file. |
| iOS shared web credentials (`webcredentials:us.pycon.org`) | **yes** (password autofill for staff/attendee login) | **GAP** (same entitlement). A regression for login autofill until fixed. |
| Android `asset_statements` meta-data | yes (`@string/asset_statements` → `https://us.pycon.org/.well-known/assetlinks.json`) | **partial**: `[tool.flet.android.meta_data]` only renders `android:value`, and this meta-data needs `android:resource`. Workaround: the helper plugin (§4.4). |

### 4.4 Android `<queries>` and resource meta-data: helper plugin (no template fork)

The template manifest only has hooks for `<uses-permission>`, `<uses-feature>`, `<application>`
attributes, `<meta-data android:value>`, `<provider>` and the single deep-link intent-filter. Its
only `<queries>` entry is Flutter's `PROCESS_TEXT` (`TPL/android/app/src/main/AndroidManifest.xml`).
Since minSdk will be 34, Android package visibility always applies:
* `UrlLauncher.can_launch_url()` returns `false` for schemes the app has not declared.
* Custom Tabs detection for `LaunchMode.IN_APP_BROWSER_VIEW` (the `@capacitor/inappbrowser`
  replacement) needs `CustomTabsService`.
* `add_2_calendar` needs `INSERT` on `vnd.android.cursor.item/event`.

`launch_url()` itself does not need `<queries>`.

Workaround (**PLAUSIBLE**; this is standard Gradle manifest-merger behaviour but has not been built
here): a tiny Flutter Android plugin, `native/pycon_native_config`, added through
`[tool.flet.flutter.pubspec.dependencies]`. It has no Dart API and is not a Flet extension: only
discovered `flet-*` packages get registered in `flet_generated.dart`, while pubspec-only packages are
merged into `pubspec.yaml` (`build_base.py:2002-2019`). Its library manifest is merged into the app:

```xml
<!-- native/pycon_native_config/android/src/main/AndroidManifest.xml -->
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
  <queries>
    <intent><action android:name="android.intent.action.VIEW" /><data android:scheme="https" /></intent>
    <intent><action android:name="android.intent.action.SENDTO" /><data android:scheme="mailto" /></intent>
    <intent><action android:name="android.intent.action.DIAL" /><data android:scheme="tel" /></intent>
    <intent><action android:name="android.support.customtabs.action.CustomTabsService" /></intent>
    <intent><action android:name="android.intent.action.INSERT" /><data android:mimeType="vnd.android.cursor.item/event" /></intent>
  </queries>
  <application>
    <!-- credential sharing with us.pycon.org (parity with Ionic) -->
    <meta-data android:name="asset_statements" android:resource="@string/asset_statements" />
    <!-- phase 2: FCM small icon, needs a resource reference too -->
    <!-- <meta-data android:name="com.google.firebase.messaging.default_notification_icon" android:resource="@drawable/ic_stat_pycon" /> -->
  </application>
</manifest>
```

plus `res/values/strings.xml` defining `asset_statements` and a no-op `FlutterPlugin` class so
Flutter registers the Android side. Check the result in
`build/flutter/build/app/outputs/logs/manifest-merger-release-report.txt` (`DOCS/publish/android.md`
"Finding where a permission came from").

The same library manifest *could* declare `<activity android:name="org.pycon.us.MainActivity">`
with an `autoVerify` https intent-filter, which the merger folds into the app's activity by name. That
is **PLAUSIBLE but brittle**. Prefer the upstream option in §11.

### 4.5 Icons, splash, boot screen

* `src/assets/icon.png`: export a 1024×1024 PNG from `IONIC/resources/icon.png` (2048², or the `.ai`
  source). Transparent, full-bleed artwork gets per-platform framing automatically. An opaque source
  keeps its own background (`DOCS/publish/index.md` "Icons"). Optional overrides:
  `icon_ios.png` / `icon_android.png` / `icon_web.png`.
* `src/assets/splash.png` and `splash_dark.png` come from `IONIC/resources/splash.png`. iOS needs the
  dark image to apply `dark_color`, and Android 12 needs it for `icon_dark_background`
  (`DOCS/publish/index.md:1053-1057`). The light and dark images can be the same file.
* The boot screen (purple background plus white spinner) is the closest match to the Ionic
  `index.html` app shell and to "keep the splash until data loads". The data-loading part belongs to
  the app: show a branded loading view until the cached schedule has been read.

---

## 5. CI/CD

### 5.1 What the action does (verified in `ACTION/action.yml`, `ACTION/scripts/flet_action.py`)

* Composite action: `astral-sh/setup-uv` (pinned SHA, v8.3.2), then `uv run … flet --version --json`
  to resolve Flet/Flutter, then caches `~/flutter/<ver>` and `~/.flet/cache`, then
  `flet build <target> --yes --verbose --output <dir>`, then a platform-aware archive.
* Inputs: `target`, `working-directory`, `runner-python-version`, `bundled-python-version`,
  `build-number`, `build-version`, `output-directory`, `extra-args`, `cache`,
  `install-linux-dependencies`, `archive-output`. `extra-args` rejects `-o/--output`,
  `--python-version`, `--build-number` and `--build-version`, which must go through their own inputs
  (`flet_action.py:168-190`).
* Outputs: `output-path` (raw directory, for signing or upload steps), `archive-path`
  (`flet-aab.zip`, `flet-ipa.zip` or `flet-web.zip`), `flet-version`, `flutter-version`.
* It runs `flet` through `uv run` in the project, so `flet-cli` must be in a default-synced group
  (the `dev` group above).
* It requires `pyproject.toml`; "Requirements-only projects are not yet supported"
  (`flet_action.py:120-125`).
* **It does not sign, notarize or upload.** The README points to the publish docs and the
  `output-path` output.
* The signing environment variables must be visible to the composite's `run` steps. Job-level `env`
  and `$GITHUB_ENV` are inherited; the release workflow below uses both.

The other repositories are earlier, hand-rolled versions of the same pipeline:
* `others/flet-github-action-workflows/.github/workflows/all-builds.yml`: matrix of
  `uv run flet build …` with a hard-coded Linux apt list.
* `web-build-and-gh-pages-deploy.yml`: `--base-url ${GITHUB_REPOSITORY#*/} --route-url-strategy hash`
  plus GitHub Pages.
* `others/test-flet-github-actions`: a playground (web/Pages, plus an unrelated macOS
  library-validation repro).

None of them signs or uploads. The action replaces the build part of all of them; the Pages pattern
is the fallback hosting option in §6.

### 5.2 Release workflow: `.github/workflows/release.yml` (tag `v27.0.0` → stores + hosting)

YAML-parsed, and the build-number snippet was executed against the proposed `pyproject.toml`
(27.0.0 gives 27000; respin 1 gives 27001).

```yaml
name: Release (iOS, Android, Web)

on:
  push:
    tags: ["v*"]              # v27.0.0, v27.0.1, ...
  workflow_dispatch:
    inputs:
      respin:
        description: "Re-upload the same version with a higher build number (0-9)"
        default: "0"

concurrency:
  group: release-${{ github.ref }}
  cancel-in-progress: false

permissions:
  contents: read

jobs:
  meta:
    runs-on: ubuntu-latest
    outputs:
      version: ${{ steps.v.outputs.version }}
      build-number: ${{ steps.v.outputs.build_number }}
    steps:
      - uses: actions/checkout@v6
      - id: v
        name: Derive version and build number from pyproject.toml
        env:
          RESPIN: ${{ inputs.respin || '0' }}
        run: |
          python3 - <<'PY' >> "$GITHUB_OUTPUT"
          import os, tomllib
          v = tomllib.load(open("pyproject.toml", "rb"))["project"]["version"]
          major, minor, patch = (int(x) for x in v.split("."))
          respin = int(os.environ["RESPIN"])
          assert minor <= 9 and patch <= 9 and 0 <= respin <= 9, v
          # 26.2.1 shipped as versionCode 26022; 27.0.0 -> 27000, 27.1.3 respin 1 -> 27131
          print(f"version={v}")
          print(f"build_number={major * 1000 + minor * 100 + patch * 10 + respin}")
          PY
      - name: Tag must match [project].version
        if: startsWith(github.ref, 'refs/tags/v')
        run: test "${GITHUB_REF_NAME#v}" = "${{ steps.v.outputs.version }}"
      - name: Refuse dev-server URLs in release config (26.2.0 incident guard)
        run: |
          if grep -RnE "FLET_PAGE_URL|localhost:85|10\.0\.2\.2" pyproject.toml src/; then
            echo "::error::dev URL found in release inputs"; exit 1
          fi

  build:
    needs: meta
    name: ${{ matrix.target }}
    runs-on: ${{ matrix.runner }}
    environment: release      # protected environment holding the store secrets
    strategy:
      fail-fast: false
      matrix:
        include:
          - target: aab
            runner: ubuntu-latest
          - target: ipa
            runner: macos-26
          - target: web
            runner: ubuntu-latest
    env:
      FLET_ANDROID_SIGNING_KEY_STORE_PASSWORD: ${{ secrets.ANDROID_KEYSTORE_PASSWORD }}
      FLET_ANDROID_SIGNING_KEY_PASSWORD: ${{ secrets.ANDROID_KEY_PASSWORD }}
      FLET_ANDROID_SIGNING_KEY_ALIAS: ${{ secrets.ANDROID_KEY_ALIAS }}
    steps:
      - uses: actions/checkout@v6

      - name: Bake build info into the Python app
        run: |
          cat > src/pycon_us/build_info.py <<EOF
          VERSION = "${{ needs.meta.outputs.version }}"
          BUILD_NUMBER = ${{ needs.meta.outputs.build-number }}
          GIT_SHA = "${GITHUB_SHA::7}"
          TARGET = "${{ matrix.target }}"
          EOF

      # ---------- Android signing ----------
      - name: Restore upload keystore
        if: matrix.target == 'aab'
        run: |
          printf '%s' "${{ secrets.ANDROID_UPLOAD_KEYSTORE_B64 }}" | base64 -d > "$RUNNER_TEMP/upload.jks"
          echo "FLET_ANDROID_SIGNING_KEY_STORE=$RUNNER_TEMP/upload.jks" >> "$GITHUB_ENV"

      # ---------- iOS signing (DOCS/publish/ios.md "Building and signing in CI") ----------
      - name: Import signing certificate
        if: matrix.target == 'ipa'
        uses: apple-actions/import-codesign-certs@v7
        with:
          p12-file-base64: ${{ secrets.IOS_CERTIFICATE_P12 }}
          p12-password: ${{ secrets.IOS_CERTIFICATE_PASSWORD }}
      - name: Install provisioning profile
        if: matrix.target == 'ipa'
        uses: apple-actions/download-provisioning-profiles@v6
        with:
          bundle-id: org.pycon.us.2023.onsite
          profile-type: IOS_APP_STORE
          issuer-id: ${{ secrets.APPLE_API_ISSUER }}
          api-key-id: ${{ secrets.APPLE_API_KEY_ID }}
          api-private-key: ${{ secrets.APPLE_API_KEY_P8 }}

      # ---------- Build (all targets) ----------
      - name: flet build ${{ matrix.target }}
        id: build
        uses: flet-dev/flet-build-action@v1
        with:
          target: ${{ matrix.target }}
          runner-python-version: "3.14"
          # bundled-python-version left empty: resolved from [project].requires-python
          build-number: ${{ needs.meta.outputs.build-number }}
          build-version: ${{ needs.meta.outputs.version }}

      - uses: actions/upload-artifact@v7
        with:
          name: pycon-us-${{ matrix.target }}-${{ needs.meta.outputs.version }}
          path: ${{ steps.build.outputs.archive-path }}
          archive: false
          if-no-files-found: error

      # ---------- Store / hosting uploads ----------
      - name: Upload to Google Play (internal track)
        if: matrix.target == 'aab'
        uses: r0adkll/upload-google-play@v1
        with:
          serviceAccountJsonPlainText: ${{ secrets.PLAY_SERVICE_ACCOUNT_JSON }}
          packageName: org.pycon.us
          releaseFiles: ${{ steps.build.outputs.output-path }}/*.aab
          track: internal
          status: completed

      - name: Upload to App Store Connect (TestFlight)
        if: matrix.target == 'ipa'
        env:
          OUT: ${{ steps.build.outputs.output-path }}
        run: |
          mkdir -p ~/.appstoreconnect/private_keys
          printf '%s' "${{ secrets.APPLE_API_KEY_P8 }}" \
            > ~/.appstoreconnect/private_keys/AuthKey_${{ secrets.APPLE_API_KEY_ID }}.p8
          xcrun altool --upload-package "$OUT"/*.ipa -t ios \
            --apiKey ${{ secrets.APPLE_API_KEY_ID }} \
            --apiIssuer ${{ secrets.APPLE_API_ISSUER }} \
            --apple-id 6446810296

      - name: Deploy PWA to Firebase Hosting
        if: matrix.target == 'web'
        uses: FirebaseExtended/action-hosting-deploy@v0
        with:
          repoToken: ${{ secrets.GITHUB_TOKEN }}
          firebaseServiceAccount: ${{ secrets.FIREBASE_SERVICE_ACCOUNT }}
          projectId: ${{ vars.FIREBASE_PROJECT_ID }}
          channelId: live
```

Secrets (in a protected `release` environment; the PSF owns all of them):

| Secret | Used by | Notes |
|---|---|---|
| `ANDROID_UPLOAD_KEYSTORE_B64`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_PASSWORD`, `ANDROID_KEY_ALIAS` | `flet build aab` via `FLET_ANDROID_SIGNING_*` | Must be the **current Play upload key** of `org.pycon.us`, or the PSF resets the upload key in Play Console (Play App Signing). |
| `PLAY_SERVICE_ACCOUNT_JSON` | `r0adkll/upload-google-play` | Service account with release rights on the app. |
| `IOS_CERTIFICATE_P12`, `IOS_CERTIFICATE_PASSWORD` | `import-codesign-certs` | "Apple Distribution" certificate of team `BMM5U3QVKW`. |
| `APPLE_API_ISSUER`, `APPLE_API_KEY_ID`, `APPLE_API_KEY_P8` | profile download + `altool` | App Store Connect API key (App Manager). |
| `FIREBASE_SERVICE_ACCOUNT` (+ var `FIREBASE_PROJECT_ID`) | hosting deploy | See §6.1. |

Notes:
* `--apple-id 6446810296` is the numeric App Store ID from the listing URL used in the app
  (`apps.apple.com/us/app/pycon-us-2023/id6446810296`).
* Android `.aab` uploads go to `internal` and are promoted to production in Play Console (staged
  rollout). iOS builds land in TestFlight and are submitted for review by hand.
* The third-party actions `r0adkll/upload-google-play@v1` and
  `FirebaseExtended/action-hosting-deploy@v0` are well known but were not inspected locally. Pin them
  to commit SHAs, as `ACTION/action.yml` does for `setup-uv`.
* The default Gradle heap is `-Xmx8G` (`build_base.py:1147-1157`). That is fine on public-repo
  `ubuntu-latest` (16 GB). On smaller runners, override it with
  `[tool.flet.android.gradle_properties] "org.gradle.jvmargs" = "-Xmx4G …"`.

### 5.3 PR workflow: `.github/workflows/ci.yml` (no secrets)

```yaml
name: CI
on: [pull_request, workflow_dispatch]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: astral-sh/setup-uv@v6
      - run: uv run ruff check . && uv run pytest tests/unit
  build:
    needs: test
    strategy:
      fail-fast: false
      matrix:
        include:
          - { target: apk, runner: ubuntu-latest }            # debug-key signed, installable for QA
          - { target: ios-simulator, runner: macos-26 }       # unsigned .app
          - { target: web, runner: ubuntu-latest }
    runs-on: ${{ matrix.runner }}
    steps:
      - uses: actions/checkout@v6
      - id: build
        uses: flet-dev/flet-build-action@v1
        with:
          target: ${{ matrix.target }}
          runner-python-version: "3.14"
          build-number: ${{ github.run_number }}               # throwaway builds only; release uses §5.2
      - uses: actions/upload-artifact@v7
        with: { path: "${{ steps.build.outputs.archive-path }}", archive: false, if-no-files-found: error }
```

Optional: Firebase Hosting preview channels for the `web` artifact on PRs (`channelId: pr-<n>`), which
is the closest thing to Appflow's "try this build" link.

### 5.4 Makefile replacement

```make
run:          ; uv run flet run                         # desktop window, hot reload
web:          ; uv run flet run --web                   # server-driven web, hot reload
ios-live:     ; uv run flet run --ios                   # QR -> Flet companion app (built-in extensions only)
android-live: ; uv run flet run --android
ios-dev:      ; uv run flet debug ios                   # real app shell + all extensions (flet devices to list)
android-dev:  ; uv run flet debug android
sim:          ; uv run flet build ios-simulator
pwa:          ; uv run flet build web && uv run flet serve
apk:          ; uv run flet build apk
test:         ; uv run pytest && uv run flet test
clean:        ; uv run flet clean
```

`capsync`, `check-no-dev-url` and `appflow-ship` have no equivalent and are not needed.

---

## 6. Web build as the PWA replacement

### 6.1 Hosting choice

`flet build web` produces a static SPA: Flutter web plus Python running in the browser via Pyodide
in a Web Worker (`TPL/web/python-worker.js`). Any static host works.
* **Recommended: Firebase Hosting**, which keeps the operational model the PSF already has
  (`IONIC/firebase.json`).
* The repo's `.firebaserc` points to `ionic-ng-conf-app`, a leftover from the Ionic template, and
  the live PWA domain is not recorded anywhere in the repo, so the PSF has to confirm the Firebase
  project and domain.
* Fallback: GitHub Pages using the documented workflow (`DOCS/publish/web/static-website/hosting/github-pages.md`),
  which requires `--route-url-strategy hash` and `--base-url /<repo>/`.
* Cloudflare Pages: direct upload (`…/hosting/cloudflare.md`).

`firebase.json` for the Flet build:

```json
{
  "hosting": {
    "public": "build/web",
    "ignore": ["firebase.json"],
    "rewrites": [{ "source": "**", "destination": "/index.html" }],
    "headers": [
      { "source": "**", "headers": [{ "key": "Cache-Control", "value": "no-cache" }] }
    ]
  }
}
```

* `rewrites` is required for `route_url_strategy = "path"`: deep paths such as `/schedule/session/123`
  must return `index.html`. This is the same rule the Ionic hosting already uses.
* `no-cache` everywhere means revalidate with ETag. This matters because the Python app is fetched
  as `assets/app/app.zip` with no content hash (`TPL/web/index.html:70` `appPackageUrl`). With
  Firebase's default `max-age=3600`, a deploy could pair a new `main.dart.js` with a stale `app.zip`
  for up to an hour. Pyodide and CanvasKit come from versioned CDN URLs when `cdn = true`, so
  revalidating the small local files costs little.
* Do not copy Ionic's `"**/.*"` ignore if `.well-known/funding-manifest-urls` should keep being
  served. Put it in `src/assets/.well-known/`; the web build copies `assets/` into the output root
  (`DOCS/publish/index.md` "Output directory").
* The stale HTTP/2 `Link:` preload header and `generate-h2-push.js` are dropped.

### 6.2 Route URL strategy and base path

* **Dedicated host** (for example `app.us.pycon.org`, or the existing PWA domain): `base_url = "/"`
  and `route_url_strategy = "path"`. URLs stay clean and shareable, and they match the routes that
  deep links use.
* **Mounted under the website** (`us.pycon.org/2027/app/`): `base_url = "/2027/app/"`. Flet
  normalises it to `/<value>/` (`DOCS/publish/web/static-website/index.md` "Base URL"). The website
  then needs an equivalent fallback rewrite for `/2027/app/**`. If it cannot provide one, use
  `route_url_strategy = "hash"`. Flet 1.1.0 fixed hash-strategy apps returning `200 index.html` for
  unknown paths (`CHANGELOG.md` 1.1.0).
* Renderer: keep `canvaskit`. The docs explain that `skwasm` pays a WASM boundary cost on every byte
  buffer, which Flet exchanges on every update (`…/static-website/index.md` "Web renderer"). This also
  means no cross-origin-isolation (COOP/COEP) headers are needed.

### 6.3 Web-specific app constraints

* `httpx` is not installed on web (marker above; `flet` itself declares
  `httpx; platform_system != 'Emscripten'` in `sdk/python/packages/flet/pyproject.toml`). The data
  layer needs a small transport abstraction: `httpx.AsyncClient` on native, `pyodide.http.pyfetch` on
  Emscripten. This is a hard requirement for the web build; see `research/ionic/data-layer.md` for
  the endpoints.
* Mobile-only extensions are only in `[tool.flet.android|ios].dependencies`, so they are absent on
  web. Guard their imports (`try: import flet_barcode_scanner …`). The architecture report's
  `Protocol` plus no-op fallbacks already fit this.
* Expect a slower first load than the Angular PWA: Pyodide plus the app's wheels. `flet build web`
  installs dependencies at build time, which is faster to load than `flet publish`
  (`…/static-website/index.md` "Differences").

### 6.4 Offline / service worker: GAP

The Ionic PWA prefetches its shell through `@angular/service-worker` (`ngsw-config.json`). In Flutter
3.47, `flutter build web` emits a `flutter_service_worker.js` whose `activate` handler **unregisters
itself** and reloads clients. Verified in the local Flutter 3.47.6 SDK at
`packages/flutter_tools/lib/src/web/file_generators/js/flutter_service_worker.js`. The `--pwa-strategy`
choices are `offline-first` and `none`, but the generated worker is still the stub. Flet's
`flutter_bootstrap.js` registers whatever Flutter emits. Pyodide and CanvasKit also come from CDNs by
default.

Workarounds, in order of preference:
1. **Accept online-only for the web build.** The mobile apps are the offline experience: the cached
   schedule lives in app storage, per the data-layer report. The PWA becomes the no-install fallback.
2. Post-build offline: `flet build web --no-cdn` (self-hosts Pyodide, CanvasKit and fonts) plus a
   Workbox `generateSW` step in CI over `build/web`. Add a small registration snippet to `index.html`
   with a post-build `sed`, because there is no `index.html` hook. Budget for large caches: Pyodide
   plus the stdlib is tens of MB, so precache only the shell and runtime-cache the rest.
3. Upstream: a Flet-generated service worker. This is not on any roadmap seen locally.

---

## 7. Running on devices during development (replaces `make ios-live` / `android-live`)

| Mode | Command | What runs where | Extensions available | Hot reload |
|---|---|---|---|---|
| Desktop window | `uv run flet run` | Python and UI on the laptop | Flet built-ins plus anything with a desktop implementation | yes (file watcher) |
| Phone, companion app | `uv run flet run --ios` / `--android`: QR code; LAN URL on port **8551** (`CLI/commands/run.py:282-284`); iOS QR `flet://flet-host/<url>`, Android QR `https://android.flet.dev/<host:port>` (`run.py:663-702`) | Python on the laptop (web server mode); UI in the **Flet app** from the App Store (`id1624979699`) or Google Play (`com.appveyor.flet`) | Only what the companion app bundles. The iOS companion shares bundle id `com.appveyor.flet` with `flet/client`, whose `pubspec.yaml` lists `flet_camera`, `flet_permission_handler`, `flet_secure_storage`, `flet_geolocator`, `flet_webview`, `flet_map`, … — **not** the custom barcode, notification or calendar extensions. | **yes**, instant on save |
| Real app shell | `uv run flet debug ios` / `android` (`--device-id`, `--show-devices`, `--release`); `flet devices`, `flet emulators` | Packaged Python inside a debug build of *this* app, via `flutter run` (`CLI/commands/debug.py:153-157`) | **all** (real bundle id, permissions, plist, manifest) | Dart hot reload only. Python changes need a re-run. |
| iOS simulator binary | `uv run flet build ios-simulator` | Unsigned `.app` | all | no |

Recommended loop:
1. Build screens with `flet run` on desktop, then on the phone with `flet run --ios/--android` (fast
   UI iteration with real touch and safe areas).
2. Use `flet debug` for anything that touches badge scanning, notifications, calendar or
   permissions.

The companion app makes any `import flet_barcode_scanner` fail, so the fallback implementations
(manual code entry, no-op notifications) are what developers see there. That is intended.

**PLAUSIBLE (spike, S):** a "PyCon dev client" that combines both. Build the real shell with
`flet debug android -- --dart-define=FLET_PAGE_URL=http://<lan-ip>:8551` and run `flet run --android`
on the laptop. `TPL/lib/main.dart:64-67` passes `FLET_PAGE_URL` and `--debug` to the client, which
then connects to the dev server instead of the bundled Python. That would give hot reload together
with every custom extension, which is what `ionic cap run --livereload` provides today. It is also
exactly the mechanism behind the 26.2.0 incident, so the release workflow refuses any
`FLET_PAGE_URL` in its inputs (§5.2).

Logs:
* Android: `adb logcat -s flet.python`
* iOS simulator: `xcrun simctl spawn booted log stream --style compact --predicate 'sender == "dart_bridge"'`
* iOS device: Console.app
* In-app: `sys.exit(100)` shows the console log in a scrollable window

Sources: `DOCS/publish/android.md` and `ios.md` "Reading your app's output"; `DOCS/publish/index.md`
"Console output".

---

## 8. Replacing Appflow live updates and the "New version available" banner

**Why there is no OTA.** In Ionic, Appflow swaps the web bundle inside the native shell
(`LiveUpdates.sync()` / `reload()`). A `flet build` app runs Python that is packaged into the native
bundle at build time (§2). There is no runtime that fetches a new `app.zip`. Downloading new Python
code would also run into App Store guideline 2.5.2. Shorebird-style code push patches Dart AOT code
only, so it would not cover the Python app either, and it was not evaluated further. **Not porting
OTA is a decision, not a TODO.**

What Appflow was used for (`research/ionic/info-notifications-native.md` §10), and what replaces it:

| Ionic behaviour | Replacement |
|---|---|
| Content fixes between store releases | **Server-driven content.** Schedule, speakers, sponsors and info pages already come from `/{year}/schedule/conference.json`, so they update without a release. Make anything else that can change at the conference (feature flags, staff-tool toggles, Wi-Fi text, map URLs, emergency banners) server-driven too. |
| `checkForUpdate()` on start / resume, plus the banner | Fetch `app-config.json` on start and on `page.on_app_lifecycle_state_change` (resume) (`flet/controls/page.py:630`). Compare it with the baked-in `build_info` (§5.2). |
| `performAutomaticUpdate()` → `LiveUpdates.reload()` | "Update" opens the store page. iOS: `https://apps.apple.com/app/id6446810296` (or `itms-apps://`). Android: `https://play.google.com/store/apps/details?id=org.pycon.us`. Use `ft.UrlLauncher().launch_url(...)` or a client action `ft.OpenUrl(...)`. Web: reload the page (the `no-cache` headers make the next load current). |
| `build`, `snapshot.buildId`, `channel` on About → Developer Info | `build_info.VERSION`, `BUILD_NUMBER` and `GIT_SHA`, generated in CI; the target (`aab`/`ipa`/`web`) replaces "channel". |

Proposed `app-config.json`, served with `Cache-Control: no-cache` from the same Firebase Hosting site
or from `us.pycon.org/2027/mobile/`:

```json
{
  "schema": 1,
  "latest":        { "version": "27.0.2", "build": 27020 },
  "min_supported": { "ios": 27000, "android": 27000, "web": 27000 },
  "store_urls": {
    "ios": "https://apps.apple.com/app/id6446810296",
    "android": "https://play.google.com/store/apps/details?id=org.pycon.us"
  },
  "banners": [ { "id": "2027-05-15-wifi", "severity": "info", "text": "…", "url": "…" } ],
  "features": { "lead_retrieval": true, "door_check": true },
  "feed_url": "https://us.pycon.org/2027/schedule/conference.json"
}
```

Client rules:
* `BUILD_NUMBER < min_supported[platform]`: blocking "Update required" dialog with the store button.
* `latest.build > BUILD_NUMBER`: the non-blocking gradient "New version available - Tap to update"
  banner, as in `app.component.html`.
* Fetch failure: ignore silently (offline at the venue is normal).

Release cadence that makes this work:
* CI uploads every tag to TestFlight and the Play internal track (§5.2).
* Play staged rollout; Apple expedited review requested for conference-week fixes.
* The PWA deploys instantly from the same tag.
* Android in-app updates (Play Core `in_app_update`) would be a nice extension later; iOS has no
  equivalent API.

---

## 9. Store submission notes

| Topic | Value | Source / note |
|---|---|---|
| iOS minimum | **iOS/iPadOS 15** (template `IPHONEOS_DEPLOYMENT_TARGET = 15.0`; Podfile `platform :ios`). Not configurable. | `CHANGELOG.md` 1.1.0 ("iOS apps require iOS 15 or later", Xcode 27 rejects lower); `DOCS/publish/ios.md` "Minimum iOS version"; `TPL/ios/Runner.xcodeproj/project.pbxproj:348`. Ionic shipped **18.0**, so this *widens* the device range. If the PSF wants to keep 18 as policy, that needs a template fork (minor **GAP**). Alternatively, warn below 18 at runtime. |
| iPad | `TARGETED_DEVICE_FAMILY = "1,2"`; orientations iPhone P/LL/LR, iPad all four | `TPL/ios/...pbxproj:352`, `TPL/ios/Runner/Info.plist`. These are identical to Ionic, so no App Store device-support regression. |
| Android minSdk | Template default `flutter.minSdkVersion` = **24** (Flutter 3.47.x `FlutterExtension.kt`; checked in the local 3.47.5 and 3.47.6 SDKs). Proposed: **34** to keep the PSF policy. | `TPL/android/app/build.gradle.kts:80-85` |
| Android targetSdk / compileSdk | `flutter.targetSdkVersion` = **36**, `compileSdk` = **36**, NDK `28.2.13676358` (Flutter 3.47.x). Gradle 9.3.1 / AGP 8.13.2 / Kotlin 2.3.21 (`CHANGELOG.md` 1.1.0). | 36 is above Ionic's 35 and satisfies Play's annual target-API requirement for 2026-27. Re-check against the Play Console deadline (usually 31 August) before each release. |
| 16 KB page size (Play, Android 15+) | Flet's default "modern" packaging stores `.so` files uncompressed and page-aligned and maps them from the APK (`DOCS/publish/android.md` "Native library packaging"). The Ionic project pinned CameraX 1.4.2 for the same reason. | Verify that every native wheel (pypi.flet.dev) and plugin is 16 KB-aligned with Play Console pre-launch checks. Do not enable `legacy_packaging`. |
| App size (Python app) | Local data point: a minimal Flet 1.x app APK (`flet/playground/issue-4734/build/apk/issue4734.apk`, arm64-v8a only) is **55.5 MB**. Native libs total 46.3 MB: `libapp.so` 15.5, `libflutter.so` 11.6, `libpython3.14.so` 5.8, `libcrypto_python.so` 4.5. Assets total 18.5 MB uncompressed, including `stdlib.zip` 10.9 and `sitepackages.zip` 5.3. iOS: an older `flet-studio` `.ipa` is 37 MB. | **Estimate:** 25–40 MB Play download per device from the AAB (store compression is more effective on uncompressed `.so` files; `android.md` quotes the AGP notes), 60–80 MB installed. iOS similar. That is several times a Capacitor app. Keep `compile`/`cleanup` on, don't add heavy wheels, and use the AAB, not a fat APK. Confirm with Play Console "App size" and App Store Connect "App Store File Sizes" after the first upload. |
| Startup | `.pyc` compilation is on by default ("significant startup win on mobile", `DOCS/publish/index.md` "Compilation and cleanup"). On first launch Android copies the stdlib and site-packages zips to private storage ("Preparing" boot stage, Android only). | The boot screen covers it; measure cold start on a low-end supported device (API 34). |
| Export compliance | `ITSAppUsesNonExemptEncryption = false` (HTTPS only; the bundled OpenSSL is used for TLS) | PSF to confirm. Avoids the per-build compliance question in TestFlight. |
| ATS | Template default `NSAllowsArbitraryLoads = true`; proposed override `false` plus `NSAllowsLocalNetworking` | Verify the built plist (duplicate-key note in §4.1) and run a smoke test on device. The embedded app talks to Python over an FFI bridge, not HTTP (`TPL/lib/main.dart` `nrt.initBridges`). |
| Privacy manifest | No `PrivacyInfo.xcprivacy` for the app target or for the embedded Python runtime: none in `TPL/ios/Runner`, and the macOS sample bundle `serious_python_darwin_serious_python_darwin.bundle` contains only `app/ site-packages/ stdlib/`. Flutter and the plugins ship their own. | **Risk / possible GAP.** CPython uses file-timestamp and disk-space APIs that are on Apple's required-reason list. If App Store Connect reports ITMS-91053 on the first TestFlight upload, an app-level `PrivacyInfo.xcprivacy` is needed (template fork or upstream). Find out early with a throwaway TestFlight upload. |
| Data safety / privacy labels | Without Firebase Analytics or FCM in v1 the declarations shrink: no advertising ID (AD_ID removed), no analytics SDK. | Update both store forms; keep the `AD_ID` removal. |
| Review notes | Staff tools need a demo account; camera usage must be visible in the review flow. | As with the Ionic app. |
| Signing continuity | The Android update must be signed with the same upload key, or after a Play upload-key reset. iOS must use team `BMM5U3QVKW` and the same bundle ID. | The only hard blocker. It depends on the PSF. |

---

## 10. Flutter extension packages in `flet build`

### 10.1 First-party and PyPI `flet-*` extensions

Add them to `[project].dependencies`, or to `[tool.flet.<platform>].dependencies` for mobile-only
ones. `flet build` installs the wheel, discovers its bundled Dart package and registers it
automatically (§2, step 4). Nothing goes in `pubspec`. Examples:

* `flet-permission-handler`: wraps `permission_handler 12.0.1`
* `flet-secure-storage`
* `flet-camera`
* `flet-webview`: the `load_html` fallback for HTML content

Pin them to the same version as `flet`, because extensions and the template are released together.

### 10.2 Extensions written for this app (barcode scanning, local notifications, FCM, calendar)

1. Scaffold: `uv run flet create --template extension --project-name flet-barcode-scanner` inside
   `extensions/`. The template layout is `src/<py_pkg>`, `src/flutter/<dart_pkg>` (pubspec `flet: ^1.1.0`,
   `material_ui: ^1.6.0`, `flutter: ">=3.47.0"`) and
   `[tool.setuptools.package-data] "flutter.<dart_pkg>" = ["**/*"]`
   (`templates/app/extension/{{cookiecutter.out_dir}}/`).
2. Wire into the app. The extension template's own example app uses exactly this pattern:
   * `dependencies`: the package name, in the mobile platform lists
   * `[tool.uv.sources] … = { path = "extensions/…", editable = true }` so `uv run flet run` imports
     it
   * `[tool.flet.dev_packages] … = "extensions/…"` so `flet build` installs it from the local path
     (`file://` URI plus `--no-cache-dir`, `build_base.py:2616-2641`)
3. Dart changes need a rebuild (`flet build` / `flet debug`). Python-only changes don't
   (`DOCS/extend/user-extensions.md` "Change Python files").
4. Shared or remote extensions: `"flet-barcode-scanner @ git+https://github.com/<org>/flet-barcode-scanner.git@<sha>"`.
   Pin to a SHA for reproducible store builds. Publish to PyPI once stable, so the wider Flet
   community gets them too, which fits the "evolves with the ecosystem" goal.
5. Constraints for 1.1.0 extensions:
   * Use `material_ui` / `cupertino_ui`, not `package:flutter/material.dart` (breaking change in 1.1.0).
   * Plugins still on `jcenter()` or other APIs removed in Gradle 9 will not build.
   * Duplicate `libc++_shared.so` is already handled with `pickFirsts`
     (`TPL/android/app/build.gradle.kts:40`).

### 10.3 Flutter-only dependencies and overrides

`[tool.flet.flutter.pubspec.dependencies]` / `dependency_overrides` add or force packages in the
generated `pubspec.yaml`. Each entry replaces the template's entry for that package; other keys are
deep-merged (`build_base.py:2002-2019`). Paths are relative to `build/flutter/`. Use this for:
* the helper plugin in §4.4
* pinning a transitive plugin version (the Flet equivalent of the Ionic `patch-package` podspec fix)
* `flet = { git = … }` when building against an unreleased Flet (`DOCS/publish/index.md` "Prerelease compatibility")

### 10.4 What each planned extension needs from the build (and whether a custom template is needed)

| Extension | Dart package (from `services-native-gaps.md`) | Build-level needs | `pyproject` today? | Template fork needed? |
|---|---|---|---|---|
| `flet-barcode-scanner` | `mobile_scanner` | Camera usage string + `CAMERA` | yes (`permissions=["camera"]`) | **No** |
| `flet-add-to-calendar` | `add_2_calendar` | iOS calendar (+ contacts) strings; Android `<queries>` `INSERT` | strings yes; `<queries>` via helper plugin (§4.4) | **No** (helper plugin) |
| `flet-local-notifications` | `flutter_local_notifications` (+ `timezone`) | `POST_NOTIFICATIONS`, `SCHEDULE_EXACT_ALARM`; plugin-manifest receivers merge automatically; **core library desugaring in `:app`** | permissions yes; **desugaring no** | Upstream flag (S) or **PLAUSIBLE** Gradle init script (below); otherwise fork |
| `flet-firebase` (messaging, analytics) | `firebase_core`, `firebase_messaging`, `firebase_analytics` | iOS `aps-environment` entitlement; `UIBackgroundModes`; config: `google-services.json` / `GoogleService-Info.plist`, or Dart-only `FirebaseOptions`; Android FCM default icon (resource meta-data) | `UIBackgroundModes` yes; **entitlement no**; config files no (use Dart-only init); icon via helper plugin | **Yes** for iOS push unless `[tool.flet.ios.entitlement]` lands upstream |

**Gradle init script (PLAUSIBLE) for desugaring.** No flet-cli or template hook exists, but Gradle
applies `~/.gradle/init.d/*.gradle(.kts)` to every build. In CI, and documented for developers, drop:

```kotlin
// ~/.gradle/init.d/pycon-desugaring.gradle.kts
allprojects {
    afterEvaluate {
        if (name == "app") {
            extensions.findByName("android")?.let { ext ->
                (ext as com.android.build.gradle.BaseExtension).compileOptions.isCoreLibraryDesugaringEnabled = true
            }
            dependencies.add("coreLibraryDesugaring", "com.android.tools:desugar_jdk_libs:2.1.4")
        }
    }
}
```

This keeps the stock template, but it lives outside the repo's build definition. Prefer the upstream
flag (§11).

**Verdict on custom templates:** v1 needs **none**. Phase 2 needs iOS entitlements, plus desugaring
if the init script is rejected. The template already receives the whole `pyproject`, so a fork's diff
would be small: a `Runner.entitlements` rendered from a new `[tool.flet.ios.entitlement]` table, plus
`CODE_SIGN_ENTITLEMENTS`. But a fork has to be rebased on every Flet release, because the cookiecutter
variables change and the template is versioned with Flet (`[tool.flet.template] url/ref/dir`,
`DOCS/publish/index.md` "Build template"). **Adding these hooks upstream in Flet is cheaper than
maintaining a fork through a conference cycle.**

---

## 11. GAP register: what `flet build` cannot do today

| # | Gap | Impact for PyCon | Workaround now | Upstream fix (size) |
|---|---|---|---|---|
| G1 | No iOS entitlements (`[tool.flet.macos.entitlement]` only; iOS template has no `.entitlements`) | Push (`aps-environment`), `webcredentials:` autofill (regression), Universal Links | Template fork rendering `get_pyproject("tool.flet.ios.entitlement")` + `CODE_SIGN_ENTITLEMENTS`; or ship v1 without push and autofill | `[tool.flet.ios.entitlement]` / `--ios-entitlements` mirroring macOS (`build_base.py:705,1234`): **S** |
| G2 | No Android `<queries>` hook | `can_launch_url`, Custom Tabs detection, calendar INSERT intent on API 30+ | Helper plugin manifest (§4.4, PLAUSIBLE); avoid `can_launch_url` | `[tool.flet.android.queries]`: **S** |
| G3 | Deep-link intent-filter has no `autoVerify`; one scheme/host only | No verified App Links (https) | Custom scheme only; helper-plugin activity merge (PLAUSIBLE, brittle) | `[tool.flet.android.deep_linking] auto_verify`, `path_prefix`, multiple hosts: **S** |
| G4 | `meta_data` only emits `android:value` | `asset_statements`, FCM default icon/colour | Helper plugin manifest | Allow inline tables → attributes (as `provider.meta_data` already does): **XS** |
| G5 | No core-library-desugaring / Gradle snippet hook | `flutter_local_notifications` will not build | Gradle init script (PLAUSIBLE) or fork | `[tool.flet.android] core_library_desugaring = true` or a `gradle_snippets` hook: **S** |
| G6 | No hook to place `google-services.json` / `GoogleService-Info.plist` or apply the google-services plugin | FlutterFire native config | Dart-only `Firebase.initializeApp(options=…)` inside the extension | Generic "copy files into the Flutter project" table: **M** |
| G7 | No runtime API for app version/build | About page, update check | CI writes `src/pycon_us/build_info.py` (§5.2) | `page.get_app_info()` over the already-bundled `package_info_plus ^9.0.0` (`TPL/pubspec.yaml`), or have the template export `FLET_APP_VERSION`/`FLET_APP_BUILD_NUMBER` env vars to Python (`TPL/lib/main.dart:375-398` already sets `FLET_*`): **S** |
| G8 | No offline service worker for web (Flutter 3.47 SW is a self-unregistering stub) | No offline PWA | Online-only PWA; or `--no-cdn` + Workbox post-build | Flet-generated SW: **M** |
| G9 | iOS deployment target fixed at 15 | Can't encode the PSF "iOS 18+" policy | Runtime notice, or fork | `[tool.flet.ios] deployment_target`: **S** |
| G10 | No app-level `PrivacyInfo.xcprivacy` | Possible ITMS-91053 on upload | Fork adds the file to Runner | Ship one in the template, covering the CPython required-reason APIs: **S** (verify first) |
| G11 | No OTA | — | Server-driven config + store releases (§8) | Not planned (policy) |
| G12 | Store upload is not part of `flet build` / flet-build-action | — | `altool`, `r0adkll/upload-google-play` | Optional `upload` inputs in the action: **M** |
| G13 | Companion app lacks custom extensions | No hot reload for scanner/notification screens | `flet debug`; PLAUSIBLE dev client via `FLET_PAGE_URL` (§7) | Documented "custom dev client" recipe: **S** |

---

## 12. Corrections to other reports

1. `research/flet/services-native-gaps.md` §2.7 (table row 7d and the bullet "App.getInfo()"): the
   suggestion `importlib.metadata.version("pycon_us")` ("project version is set from
   `[project].version` by flet build") **does not work**. `flet build` installs only the
   dependencies; the app directory is copied, not pip-installed (`build_base.py:2600-2645`), so there
   is no distribution metadata. `[project].version` is only passed to `flutter build --build-name`
   (`build.py:203-209`), which sets `CFBundleShortVersionString`/`versionName`. Python never sees it
   (no version env var in `TPL/lib/main.dart:375-398`). Use a CI-generated `build_info.py`, or the
   upstream `get_app_info()` (G7).
2. `research/flet/services-native-gaps.md` §2.8 ("Splash: `flutter_native_splash` generated by `flet
   build`") and the Flet docs `DOCS/publish/index.md:177-180`: icons and splash screens are generated
   by **`flet-platform-assets`** (`build_base.py:14-29`, `customize_icons`/`customize_splash_images`).
   Neither `flutter_launcher_icons` nor `flutter_native_splash` is in `TPL/pubspec.yaml` any more. The
   configuration keys quoted are correct; only the generator name is wrong.
3. `research/flet/services-native-gaps.md` §2.11 / §3 (permission_handler: "the template `Podfile`
   turns the plist keys into `PERMISSION_*` macros automatically — no Podfile editing needed for
   camera, calendar or notifications"): **not true for notifications.**
   * The mapping in `TPL/ios/Podfile` has no `PERMISSION_NOTIFICATIONS` entry; notifications have no
     Info.plist key to derive it from.
   * So `flet-permission-handler`'s `Permission.NOTIFICATION` is not compiled in on iOS. Request it
     through the notification plugin instead, and verify on device.
   * The `PERMISSION_EVENTS` mapping also misspells the write-only key
     (`NSCalendarWriteOnlyAccessUsageDescription`). It still works when `NSCalendarsUsageDescription`
     is also set, as proposed here.
4. `research/flet/architecture-declarative-routing.md` §"Mobile deep links" ("**GAP** — no Flet API
   registers app links/intent filters"): custom-scheme deep links **are** supported by
   `[tool.flet.deep_linking]` and `[tool.flet.<platform>.deep_linking]` (Android `VIEW` intent-filter
   plus iOS `CFBundleURLTypes`; `TPL/android/app/src/main/AndroidManifest.xml:47-56`,
   `TPL/ios/Runner/Info.plist:53-68`). The real gaps are verified https App Links (`autoVerify`) and
   iOS Universal Links (associated-domains entitlement). `services-native-gaps.md` row 7c already says
   "exists".
5. `research/flet/architecture-declarative-routing.md` capability table row "Service worker / PWA —
   `flet build web` … exists": the manifest and installability exist, but **offline support does
   not**. Flutter 3.47's generated `flutter_service_worker.js` unregisters itself, and Pyodide and
   CanvasKit load from CDNs by default. Parity with the Ionic `ngsw` prefetching is a GAP (G8).

---

## 13. Risks

* **Store ownership:** shipping as an update needs the PSF to provide App Store Connect access for
  team `BMM5U3QVKW` and the Play Console plus upload key for `org.pycon.us`. Without it, the result is
  a new listing, which loses reviews and installs, means a new bundle ID, and leaves two "PyCon US"
  apps in the stores.
* **Prerelease Flet:** building on a Flet dev version makes the template resolve the latest
  *stable* `flet` Dart package, which can mismatch at runtime with "Unknown control"
  (`DOCS/publish/index.md` "Prerelease compatibility"). Ship on a released Flet (1.1.x) and pin it
  exactly.
* **Template-level gaps** (G1, G2, G5) block push, exact notifications and autofill. They need either
  upstream flet-cli work before roughly March 2027 or a fork that must be maintained.
* **Size and startup:** the app will be several times larger than the Capacitor app (§9), and the
  first Android launch has an extra "Preparing" stage. Users on conference Wi-Fi feel this.
* **Web (Pyodide):** slower first load, no `httpx`, no offline. The data layer needs a transport
  abstraction, or the PWA breaks.
* **Privacy manifest (ITMS-91053)** for the embedded CPython: unverified. Do a throwaway TestFlight
  upload early.
* **ATS override** (`NSAllowsArbitraryLoads = false`) and the duplicate-key behaviour in the
  generated Info.plist: verify on the built bundle.
* **Platform deadlines:** around May each year, App Store submissions require the Xcode version Apple
  currently mandates. Flet 1.1.0 already fixed Xcode 27 builds. Play's target-API deadline is around
  August. Both can force a Flet upgrade shortly before PyCon.
* **Composite-action secret propagation:** the Android signing environment variables must reach
  flet-build-action's inner `run` steps. Job-level `env` and `$GITHUB_ENV` are used for that. Confirm
  in the first release run that the AAB is signed with the upload key (`jarsigner -verify` /
  `apksigner`), not the debug key. Without a key store, Flet falls back to the debug key
  (`DOCS/publish/android.md` "Signing").
* **Exact-alarm policy:** Play restricts `USE_EXACT_ALARM`; `SCHEDULE_EXACT_ALARM` is user-granted
  and off by default on API 34+. Session reminders need an inexact fallback.
* **Helper plugin and init script** are PLAUSIBLE workarounds that have not been built. Spike them
  before relying on them.
* **Dev-client footgun:** the `FLET_PAGE_URL` dev client (§7) recreates the 26.2.0 incident class if
  someone releases with it. The release workflow guard must stay.
