# Build and release: PyCon US 2027 on Flet

**Status:** companion to [`PLAN.md`](../PLAN.md) §9, written 2026-10-11. **Owner:** U. Binding inputs: PLAN.md and the decisions record ([`decisions.md`](decisions.md), D-01..D-136; the amendments this document needed are D-109, D-125..D-127 and D-134). Where this document has to differ from either, it says so in place and in [§17](#17-discrepancies-with-planmd-and-the-decisions-record).

**Scope:** the complete `pyproject.toml` (checked key by key against the local flet-cli), versioning and the build ledger, full workflow YAML, secrets and signing, the store checklist, release train and rollout, runbooks, hosting for `app-config`/`app-content` and the PWA, the dev loop, and the optional Appflow bridge.

Feature ids refer to [`docs/feature-matrix.md`](feature-matrix.md). The rows this document implements are DEV-07, DEV-08, NATIVE-01..07, NATIVE-09, NATIVE-10 (NATIVE-03 in §2.5), LIVE-01..04, NOTIF-12 and INFO-03 (build side). NATIVE-08 (status bar, safe areas, edge-to-edge) is a UI row with no build content and is not covered here.

**Path aliases** (`CLI/`, `TPL/` and `DOCS/` are inside the local monorepo `flet-dev/flet`, 1.1.0 in development; `ACTION/` is the sibling checkout `flet-dev/flet-others/flet-build-action/`):

| Alias | Path |
|---|---|
| `CLI/` | `sdk/python/packages/flet-cli/src/flet_cli/` |
| `TPL/` | `sdk/python/templates/build/{{cookiecutter.out_dir}}/` |
| `DOCS/` | `website/docs/publish/` |
| `ACTION/` | `flet-dev/flet-others/flet-build-action/` (sibling checkout, not in the monorepo; tag `v1` = `v1.0.0`) |

---

## 1. Toolchain facts (verified 2026-10-11 in local source)

| Fact | Value | Source |
|---|---|---|
| Flet on PyPI | 1.0.4 (latest release); 1.1.0 unreleased | PLAN §3; `flet.version.flet_version` → `1.0.4` |
| Flutter used by `flet build` | 3.47.7 from 1.1.0 (1.0.4: **3.44.8**) | `flet.version.flutter_version` → `3.47.7` (read from the checkout's `.fvmrc`, which pins 3.47.7); `git show v1.0.4:.fvmrc` → 3.44.8; CHANGELOG 1.1.0 "Bump the bundled Flutter to 3.47.7 (from 3.44.8)" |
| Python bundled by `flet build` | **CPython 3.14.7**; web: **Pyodide 314.0.7** | `CLI/utils/python_versions.py:31` pins python-build `20260921`; manifest `default_python_version = 3.14`; `website/.crocodocs/python-versions.mdx:3`. Identical in tag `v1.0.4`. |
| How it is chosen | `--python-version`, then `[project].requires-python` (highest *stable* supported line that matches), then the manifest default | `CLI/utils/python_versions.py:139-213` |
| → `requires-python` | **`>=3.14,<3.15`** resolves to 3.14 (checked by loading the file below through `resolve_python_version`). Host tests also run on 3.14, so tests and the bundle use the same interpreter line. | as above |
| iOS minimum | 15.0 from 1.1.0 (#6874); **13.0 in 1.0.4**; fixed by the template, not configurable | `TPL/ios/Runner.xcodeproj/project.pbxproj:348`, `TPL/ios/Podfile:2`; `v1.0.4` has `platform :ios, '13.0'` and `IPHONEOS_DEPLOYMENT_TARGET = 13.0` |
| Android SDK defaults | `minSdk = flutter.minSdkVersion` (24), `targetSdk = flutter.targetSdkVersion` (36) unless set | `TPL/android/app/build.gradle.kts:72-80` |
| Release signing without a keystore | **debug key** (the build succeeds, the upload fails) | `TPL/android/app/build.gradle.kts` `android_signing`; `DOCS/android.md` "Signing" |
| iOS without a profile | `--no-codesign`, `.xcarchive` only | `CLI/commands/build.py:185-193` |
| App packaging | Only dependencies are pip-installed; the app dir is copied, so `importlib.metadata` cannot see `pycon-us` | `CLI/commands/build_base.py:2600-2645` |
| **Deep linking** | For `aab`/`apk` only `[tool.flet.android.deep_linking]` is read; for `ipa`/`ios-simulator` only `[tool.flet.ios.deep_linking]`. The global `[tool.flet.deep_linking]` is used **only for other targets**, although `DOCS/index.md:1391-1394` documents it as a fallback. | `CLI/commands/build_base.py:1421-1443` (**upstream bug**, fix in open PR [flet-dev/flet#6953](https://github.com/flet-dev/flet/pull/6953); §17) |
| flet-build-action | Runs `uv run … flet --version --json`, then `flet build <target> --yes --verbose --output …`; never signs or uploads | `ACTION/action.yml`, `ACTION/scripts/flet_action.py:112-160, 193-218` |

---

## 2. `pyproject.toml`

### 2.1 The file (state at M2 exit: Flet 1.1.0 pinned, E1 not yet on PyPI)

```toml
[project]
name = "pycon-us"
version = "27.0.0"                       # D-89/D-90; tag must equal it (§3)
description = "The official PyCon US conference app: schedule, speakers, sponsors, maps and staff tools. Built with Python."
readme = "README.md"
license = "Apache-2.0"
requires-python = ">=3.14,<3.15"         # flet build bundles CPython 3.14.7 / Pyodide 314.0.7 (§1)
authors = [{ name = "Python Software Foundation" }]
dependencies = [                          # bundled into every target; exact pins only (D-20, D-89)
    "flet==1.1.0",
    "flet-permission-handler==1.1.0",
    "flet-secure-storage==1.1.0",
    "httpx==0.28.1; platform_system != 'Emscripten'",       # web uses pyfetch (D-93)
    "tzdata==2026.5",                                        # spike S2; re-pin at M0
    "sentry-sdk==2.71.0; platform_system != 'Emscripten'",   # spike S6; crash.py no-ops on web
]

[dependency-groups]
dev = [                                   # host only, never bundled; uv.lock pins the rest
    "flet[all,test]==1.1.0",              # flet-cli (flet-build-action runs it), desktop, web, test
    "pytest", "pytest-asyncio", "hypothesis", "jsonschema",
    "ruff", "pyright", "zizmor",
]

# ------------------------------------------------------------------ flet build: all targets
[tool.flet]
product = "PyCon US"                      # launcher label, CFBundleDisplayName, web <title>
company = "Python Software Foundation"
copyright = "Copyright (C) 2027 Python Software Foundation"
permissions = ["camera"]                  # NSCameraUsageDescription + CAMERA + camera features required=false
icon_background = "#ffffff"

[tool.flet.app]
path = "src"
module = "main"                           # src/main.py: ft.run(lambda page: page.render_views(App))

[tool.flet.compile]                       # .pyc for cold start (PLAN §8.3)
app = true
packages = true

[tool.flet.cleanup]
packages = true
package_files = ["**/*.pyi"]

[tool.flet.splash]                        # same purple as Ionic (SHELL-01); dark default would be #121212
color = "#680579"
dark_color = "#680579"

[tool.flet.boot_screen]
name = "flet"

[tool.flet.boot_screen.flet]
theme_mode = "auto"
bgcolor_light = "#680579"
bgcolor_dark = "#680579"
spinner_size = 32
spinner_color_light = "#ffffff"
spinner_color_dark = "#ffffff"
fade_out_duration = 200

# ------------------------------------------------------------------ Android
[tool.flet.android]
bundle_id = "org.pycon.us"                # existing Play listing (NATIVE-01)
min_sdk_version = 34                      # PSF policy; 26 only with OD-1 (#307)
target_sdk_version = 36                   # Play requirement since 2026-08-31; pinned so a Flutter bump cannot move it
dependencies = [                          # mobile-only extensions (§2.3, §2.4)
    "flet-barcode-scanner @ git+https://github.com/flet-dev/flet-barcode-scanner@<40-hex-sha>",  # alpha only; 0.2.0 from 02-19
]

[tool.flet.android.deep_linking]          # pyconus://app/<route> (D-38). Must be per platform, see §1
scheme = "pyconus"
host = "app"

[tool.flet.android.permission]            # false -> tools:node="remove"
"com.google.android.gms.permission.AD_ID" = false        # NATIVE-05, D-79
"android.permission.READ_EXTERNAL_STORAGE" = false       # implied by CameraX plugins (DOCS/android.md)
"android.permission.WRITE_EXTERNAL_STORAGE" = false

# ------------------------------------------------------------------ iOS
[tool.flet.ios]
bundle_id = "org.pycon.us.2023.onsite"    # App Store id 6446810296
team_id = "BMM5U3QVKW"
export_method = "app-store-connect"
dependencies = [
    "flet-barcode-scanner @ git+https://github.com/flet-dev/flet-barcode-scanner@<40-hex-sha>",
]

[tool.flet.ios.deep_linking]
scheme = "pyconus"
host = "app"

[tool.flet.ios.export_methods.app-store-connect]          # release.yml
provisioning_profile = "PyCon US App Store"                 # exact portal name, confirmed with P4
signing_certificate = "Apple Distribution"
export_options = { uploadSymbols = true, manageAppVersionAndBuildNumber = false }

[tool.flet.ios.export_methods.release-testing]             # DEMO stage phones only (§6, demo job)
provisioning_profile = "PyCon US Ad Hoc"
signing_certificate = "Apple Distribution"

[tool.flet.ios.info]                       # merged after the permission bundle (build_base.py:1205-1212)
NSCameraUsageDescription = "PyCon US uses the camera to scan attendee badge QR codes for lead retrieval, door check, swag pickup and Code of Conduct reports. Staff and sponsors only."
NSCalendarsWriteOnlyAccessUsageDescription = "Add PyCon US sessions to your calendar."   # E4 adds NSCalendarsUsageDescription + NSContactsUsageDescription (§2.4, D-114)
ITSAppUsesNonExemptEncryption = false     # HTTPS only; PSF confirms (P11)

# ------------------------------------------------------------------ Web (PWA, T2, D-93)
[tool.flet.web]
base_url = "/"                            # dedicated host; "/2027/app/" if mounted under us.pycon.org
route_url_strategy = "path"               # Firebase rewrite ** -> /index.html (§8)
pwa_short_name = "PyCon US"
pwa_background_color = "#680579"
pwa_theme_color = "#680579"               # NATIVE-09: replaces Ionic's #387ef5
```

Things that are **absent on purpose**, each enforced by `check_release.py guards` (§9):

| Absent | Why |
|---|---|
| `[tool.flet].build_number` | CI passes `--build-number` (`CLI/commands/build.py:197-201`) |
| `[tool.flet.android.signing]` | Keystore, alias and passwords come from `FLET_ANDROID_SIGNING_*` env vars (§10.1) |
| `[tool.flet.deep_linking]` (global) | Ignored for Android and iOS (§1). |
| `[tool.flet.template]`, `[tool.flet.flutter.pubspec]` | No custom template, helper plugin or overrides (D-28). |
| `[tool.flet.dev_packages]`, path/editable `[tool.uv.sources]` | Not in releases (D-89); only `nightly.yml` appends `dev_packages` in its throwaway checkout |
| `NSAppTransportSecurity` override | The template already emits `NSAllowsArbitraryLoads=true` (`TPL/ios/Runner/Info.plist`); an `ios.info` entry would append a **second** key, so the default stays (upstream nit) |
| `POST_NOTIFICATIONS`, `SCHEDULE_EXACT_ALARM`, `UIBackgroundModes`, entitlements | Only in the release that ships E2/E3/autofill (D-89; §2.4). |
| `LSApplicationQueriesSchemes`, `NSCalendarsUsageDescription`, `NSContactsUsageDescription` | Only `launch_url` is used (no `can_launch_url`); the two usage strings come with E4, which needs both (D-114; §2.4) |

### 2.2 Key provenance (every key above, in the local flet-cli / template)

Validation method: the file was loaded with flet-cli's own `CLI/utils/pyproject_toml.py:load_pyproject_toml`. That printed 51 leaf keys, and each one was matched to the code that reads it. `get_platform_setting(x)` looks up `tool.flet.<platform>.x` first, then `tool.flet.x` (`CLI/commands/build_base.py:2963-2990`).

| Key | Read at | Effect |
|---|---|---|
| `project.name` | `CLI/commands/build_base.py:1054`, `:1064`, `:1078` | Project slug, artifact and product fallbacks |
| `project.version` | `CLI/commands/build.py:203-209` | `flutter build --build-name`. The action passes the same value as `--build-version`. |
| `project.description` | `CLI/commands/build_base.py:1537` | pubspec / desktop metadata |
| `project.requires-python` | `CLI/utils/python_versions.py:165` | Selects 3.14 |
| `project.dependencies` | `CLI/commands/build_base.py:2606` | Bundled requirements |
| `tool.flet.product` | `CLI/commands/build_base.py:1076` | Display name |
| `tool.flet.company`, `tool.flet.copyright` | `CLI/commands/build_base.py:1639`, `:1642` | Metadata |
| `tool.flet.permissions` | `CLI/commands/build_base.py:1183-1202` (bundle at `:254-269`) | Camera plist string, `CAMERA`, features |
| `tool.flet.icon_background` | `CLI/commands/build_base.py:2232-2234`, `:1685-1690` | Icon and adaptive-icon background |
| `tool.flet.app.path`, `.module` | `CLI/commands/build_base.py:1012-1021` | App dir and entry point |
| `tool.flet.compile.app`, `.packages` | `CLI/commands/build_base.py:2777-2782` | `.pyc` compilation |
| `tool.flet.cleanup.packages`, `.package_files` | `CLI/commands/build_base.py:2788-2790`, `:2808-2811` | site-packages cleanup |
| `tool.flet.splash.color`, `.dark_color` | `CLI/commands/build_base.py:1754-1756`, `:1793-1796` | Native splash colours |
| `tool.flet.boot_screen.name` | `CLI/commands/build_base.py:1829-1833` | Selects the built-in `flet` screen |
| `tool.flet.boot_screen.flet.*` (7 keys) | `CLI/commands/build_base.py:1833`; `TPL/lib/main.dart:263` (`fade_out_duration`); `packages/flet/lib/src/widgets/flet_boot_screen.dart:32, 54-57` (`theme_mode`, `bgcolor_*`, `spinner_color_*`, `spinner_size`) | Boot screen |
| `tool.flet.android.bundle_id`, `tool.flet.ios.bundle_id` | `CLI/commands/build_base.py:1635-1637` | Store identity. Android package = `org.pycon` + `us` (`templates/build/cookiecutter.json` `org_name_2`/`package_name`) |
| `tool.flet.android.min_sdk_version`, `.target_sdk_version` | `TPL/android/app/build.gradle.kts:72-80` | `minSdk`/`targetSdk` |
| `tool.flet.android.dependencies`, `tool.flet.ios.dependencies` | `CLI/commands/build_base.py:2610-2613` | Appended for that target only |
| `tool.flet.android.deep_linking.*`, `tool.flet.ios.deep_linking.*` | `CLI/commands/build_base.py:1421-1438`; `TPL/android/app/src/main/AndroidManifest.xml:47-56`, `TPL/ios/Runner/Info.plist:53-68` | `VIEW` intent-filter / `CFBundleURLTypes` |
| `tool.flet.android.permission` | `CLI/commands/build_base.py:1257-1260`; `TPL/android/app/src/main/AndroidManifest.xml:3-7` | `false` → `tools:node="remove"` |
| `tool.flet.ios.team_id` | `CLI/commands/build_base.py:1514-1517` | `teamID` in `exportOptions.plist` |
| `tool.flet.ios.export_method` | `CLI/commands/build_base.py:1483-1487` | `method` |
| `tool.flet.ios.export_methods.<m>.{provisioning_profile, signing_certificate, export_options}` | `CLI/commands/build_base.py:1489-1511`; `TPL/ios/exportOptions.plist` | Per-method signing |
| `tool.flet.ios.info` | `CLI/commands/build_base.py:1205-1212` | Merged into Info.plist |
| `tool.flet.web.base_url` | `CLI/commands/build_base.py:1043-1050` | Web base path |
| `tool.flet.web.route_url_strategy` | `CLI/commands/build_base.py:1562-1567` | `path` |
| `tool.flet.web.pwa_background_color`, `.pwa_theme_color`, `.pwa_short_name` | `CLI/commands/build_base.py:1579-1599` | Manifest |

### 2.3 Pin timeline (D-18, D-20, D-21)

| From | `flet`, `flet-permission-handler`, `flet-secure-storage`, `flet[all,test]` | `flet-barcode-scanner` (E1) | Notes |
|---|---|---|---|
| 2026-10-12 (M0) | `==1.0.4` | — | Spikes S1, S2, S5 and S6 run on 1.0.4. It bundles the same 3.14.7 (`v1.0.4:CLI/utils/python_versions.py:31`), but builds with **Flutter 3.44.8 and an iOS 13.0 deployment target** (§1), so the S5 result (App Store upload, ITMS-91053) must be re-checked on the first 1.1.0 build. |
| 1.1.0 release (target 11-30, hard 01-15) | `==1.1.0` | — | G2 requires it. One commit bumps all four pins and `uv.lock`. |
| 2027-01-10 | — | `@ git+…@<sha>` (alpha tags only) | E1 v0.1 on device |
| 02-19 | — | `==0.2.0` (PyPI) | From here no VCS pins at all |
| ≤ 02-26 | `==1.1.N` (the U1/U4/U5 point release, OD-19) | — | Caps light up through probes (D-74) |
| **03-05** | last change | last change | `check_release.py tag` refuses a pin change after 03-05 on `v27.0.*` (compares with the `v27.0.0-alpha.3` pins) |

### 2.4 Release-conditional blocks (added only in the release that ships the upgrade)

| Upgrade (gate) | Add to `pyproject.toml` | Exists today? |
|---|---|---|
| E2 push (G3) | `"flet-firebase==0.x.y"` in both `dependencies`; `[tool.flet.android.permission] "android.permission.POST_NOTIFICATIONS" = true`; `[tool.flet.ios.info] UIBackgroundModes = ["remote-notification"]`; `[tool.flet.ios.entitlement] "aps-environment" = "production"`. Only if OD-3 says yes: `"flet-firebase-analytics==0.x.y"` too (D-111) | Permission and plist keys: yes. **Entitlement: no** (U5; interim: push off). |
| E3 reminders (G3) | `"flet-notifications==<pinned flet version>"` (monorepo, lockstep with `flet`, D-20, D-24; OD-15); `"android.permission.SCHEDULE_EXACT_ALARM" = true`, `POST_NOTIFICATIONS`; `[tool.flet.android] core_library_desugaring = true`. The two `<receiver>` entries and `RECEIVE_BOOT_COMPLETED` come from the #6948 package's own manifest (D-113; fallback: a `[tool.flet.android.receiver]` table on U7) | Permissions: yes. **Desugaring and receivers: no** (U7, D-113). |
| E4 calendar (G3) | `"flet-add-to-calendar==0.x.y"`; `[tool.flet.android.queries]` INSERT `vnd.android.cursor.item/event`; `[tool.flet.ios.info]` `NSCalendarsUsageDescription` and `NSContactsUsageDescription` next to `NSCalendarsWriteOnlyAccessUsageDescription` (D-114) | Plist keys: yes. **Queries: no** (U6) |
| Autofill (T3) | `[tool.flet.ios.entitlement] "com.apple.developer.associated-domains" = ["webcredentials:us.pycon.org"]`; `[tool.flet.android.string_resources] asset_statements = '<JSON>'` plus `[tool.flet.android.meta_data] asset_statements = { resource = "@string/asset_statements" }` (D-112) | **No** (U5, U8). PSF updates AASA/assetlinks (NATIVE-07). |

U5-U8 key names are the planned upstream names (D-26). If an item misses its 1.1.x point release (OD-19), its row is not added and the interim ships.

### 2.5 Icons and splash images (NATIVE-03, BLD-05)

`flet build` generates every platform icon and splash from files in `src/assets/` (`DOCS/index.md` "Icons" and "Splash screen", lines 802-1172). Nothing is hand-copied into the template.

| File (in `src/assets/`) | Content | Notes |
|---|---|---|
| `icon.png` | **Square master**, 1024 × 1024, transparent background, PyCon US mark | Made from the Ionic 2048 × 2048 `resources/icon.png`, **not** `assets/img/appicon.png` (300 × 249, non-square). Transparent artwork is framed per platform; `icon_background = "#ffffff"` (§2.1) fills the iOS icon, the Android adaptive background and opaque web icons, matching Ionic's `#FFFFFF` adaptive background. |
| `icon_ios.png`, `icon_android.png`, `icon_web.png` (optional) | Per-platform overrides, 1024 × 1024 | Only if the generated framing looks wrong. They take precedence over `icon.png` for that platform; artwork must sit in the central 60 % (iOS), a centred circle of about 57 % (Android) or 80 % (maskable web). |
| `splash.png`, `splash_dark.png` | Splash artwork, transparent | Over `[tool.flet.splash]` `#680579` (§2.1, SHELL-01). Without them Flet falls back to `icon.png`. Android 12+ fits the image into its circular splash icon, so keep the mark centred. |

Generation runs through `flet-platform-assets` (Pillow) **from 1.1.0**. In 1.0.4 it ran through `flutter_launcher_icons` / `flutter_native_splash`, which left the iOS launch image and the Android < 12 splash broken (CHANGELOG 1.1.0), so store screenshots and the S5 upload judge icons and splash only on 1.1.0 builds. The 512 × 512 Play listing icon is a Play Console upload (PSF, §12), cut from the same master; the App Store icon comes from the bundle's 1024 × 1024 asset.

---

## 3. Versioning, tags and the build ledger

### 3.1 Scheme (D-90, plus one addition)

| Item | Rule |
|---|---|
| `[project].version` | `YY.MINOR.PATCH`, e.g. `27.0.0` (MINOR, PATCH ≤ 9) |
| Build number (store) | `YY*1000 + MINOR*100 + PATCH*10 + RESPIN`. Used for both Android `versionCode` and iOS `CFBundleVersion`. |
| **Alpha block (addition)** | `v27.0.0-alpha.N` → build **`(YY-1)*1000 + 900 + N`** = 26900..26999. Internal track and TestFlight internal only, **never promoted** (§17 #1). |
| Respin | `v27.0.0-rN` (N = 1..9) → `27000 + N`. Same version, new binary. |
| Tag grammar | `^v(\d+\.\d+\.\d+)(?:-alpha\.(\d{1,2})|-r([1-9]))?$`. The version part **must equal** `[project].version` at the tagged commit. |
| `PYCON_ENV` | From the ledger row: alpha rows may say `staging` or `prod`; every other tag must be `prod`. |
| Alpha block lifetime | Only for `x.0.0`. Point releases (27.1, 27.0.1) use respins. |

Why not `importlib.metadata`: the app is copied, not installed (§1). INFO-03, LIVE-02..04 and NOTIF-12 read `build_info.py`.

### 3.2 `builds.txt` (committed at repo root; one row per store upload)

```
# build  tag                 version  env      date        purpose
26900    v27.0.0-alpha.0     27.0.0   staging  2027-01-29  M2 exit, first PSF-signed builds (G2)
26901    v27.0.0-alpha.1     27.0.0   staging  2027-02-11  G3 evidence
26902    v27.0.0-alpha.2     27.0.0   staging  2027-02-19  Badge Day 1 build, E1 0.2.0
26903    v27.0.0-alpha.3     27.0.0   staging  2027-03-05  last pin change
26904    v27.0.0-alpha.4     27.0.0   prod     2027-03-19  2027 feed
26905    v27.0.0-alpha.5     27.0.0   prod     2027-03-30  freeze build (co-maintainer)
27000    v27.0.0             27.0.0   prod     2027-04-01  beta 1 (public beta)
```

`check_release.py tag` enforces:
1. Exactly one row matches the tag, and it is the **last** row.
2. Build numbers strictly increase down the file.
3. The computed number equals the row's number, and every number is greater than 26022.

The row is added in the release PR, which is merged before tagging. The stores reject a reused number anyway; the ledger catches it before a 40-minute build.

### 3.3 `build_info.py` (generated by `tools/caps_manifest.py`; the dev stub is committed)

```python
# src/pycon_us/build_info.py — GENERATED by tools/caps_manifest.py; the committed copy is the dev stub
VERSION = "27.0.0"
BUILD_NUMBER = 27001
GIT_SHA = "3f2c9e1"
TARGET = "aab"              # aab | ipa | web | apk | ios-simulator | linux | dev
PYCON_ENV = "prod"          # dev | staging | prod   (DEV-07)
YEAR = 2027                 # from config/conference.json (D-125); settings reads these three
CONF_TZ = "America/Los_Angeles"
SITE_URL = "https://us.pycon.org"
CAPS = ("scanner",)         # bundled-capability manifest (D-74); empty in the dev stub (flet run)
DEMO = False                # stage-phone builds (D-125) (D-84, PLAN §11); env vars do not reach packaged apps
CAPS_OVERRIDE = None        # (D-125) "all-on" | "all-off" in fallback-parity test hosts only
```

`tools/caps_manifest.py --target T --env E [--build-number N (default 0)] [--version V (default [project].version)] [--sha S (default git HEAD, or "dev")] [--demo] [--caps-override on|off] --out PATH` runs in the project env (`uv run`; it imports `flet` only for the core probes). It reads `[tool.flet.android].dependencies` for `aab`/`apk`, `[tool.flet.ios].dependencies` for `ipa`/`ios-simulator`, nothing for `web`/`linux`, and maps:

| Package (exact name) | Cap key(s) |
|---|---|
| `flet-barcode-scanner` | `scanner` |
| `flet-firebase` | `push` |
| `flet-firebase-analytics` (bundled only if OD-3 says yes; D-111) | `analytics` |
| `flet-notifications` (OD-15) | `local_notifications` |
| `flet-add-to-calendar` | `calendar` |
| `flet-html` / `flet-slidable` | `html` / `slidable` (27.1) |
| core probes against the pinned `flet` | `refresh_indicator` (`hasattr(ft, "RefreshIndicator")`, U1), `app_info` (`hasattr(ft.Page, "get_app_info")`, U4), `iv_set_transform` (`hasattr(ft.InteractiveViewer, "set_transform")`, U3), `sticky_headers` (U2, name TBD) |

All core probes are **False today** (none of these APIs exist in the local SDK, 2026-10-11). `caps_manifest.py` only writes `build_info.py`; the release-notes matrix is printed by `python -m pycon_us.platform.caps` against the written file (D-74, §6 `notes`).

---

## 4. Secrets, variables and environments (all PSF-held; D-91, PLAN §10.3)

Secrets are held by PSF-I; variables are repo-level.

| Name | Kind / env | Used by |
|---|---|---|
| `ANDROID_UPLOAD_KEYSTORE_B64` | secret / `release` | Decoded to `$RUNNER_TEMP` → `FLET_ANDROID_SIGNING_KEY_STORE`. Must be the **current Play upload key** of `org.pycon.us`, or the PSF resets it in Play App Signing (P4). |
| `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_PASSWORD`, `ANDROID_KEY_ALIAS` | secret / `release` | `FLET_ANDROID_SIGNING_KEY_STORE_PASSWORD` / `_KEY_PASSWORD` / `_KEY_ALIAS` |
| `PLAY_SERVICE_ACCOUNT_JSON` | secret / `release` | `r0adkll/upload-google-play` (release manager on the app) |
| `IOS_CERTIFICATE_P12`, `IOS_CERTIFICATE_PASSWORD` | secret / `release` | "Apple Distribution", team `BMM5U3QVKW` |
| `APPLE_API_ISSUER`, `APPLE_API_KEY_ID`, `APPLE_API_KEY_P8` | secret / `release` | Profile download and `altool` (ASC API key, App Manager) |
| `FIREBASE_SERVICE_ACCOUNT` | secret / `release`, `content` | Hosting deploy, `hosting:clone` |
| `STAGING_KEYS_JSON` | secret / `staging` | Nightly contract: per-role `{key, secret}` (attendee, lead, door, swag, mask, speaker; P3) |
| `ANDROID_UPLOAD_CERT_SHA256` | variable | AAB signer check (`keytool` format `AB:CD:…`) |
| `APPSTORE_APP_ID` = `6446810296` | variable | `altool --apple-id` |
| `FIREBASE_PROJECT_ID` | variable | Assumed `pycon-us-2023-mobile`; P7 confirms |
| `FIREBASE_TOOLS_VERSION`, `BUNDLETOOL_VERSION`, `BUNDLETOOL_SHA256` | variable | Pinned at M0 |
| `PWA_ENABLED` | variable | T2 web deploys (the D-98 trace gate needs no variable: `feature_trace.py --check` ramps by milestone exit date itself, §5 `trace`) |

The Sentry DSN is public by design and is committed per env in `settings.py` (OD-4).

| Environment | Protection |
|---|---|
| `release` | Required reviewer **PSF-I** (one of 2 named people); tags `v*` only |
| `content` | Required reviewer PSF-I or the PSF-E on-call (P12); `main` only |
| `staging` | No reviewer; `main` and scheduled runs only |

CODEOWNERS (PLAN §10.1): `release.yml`, `content.yml`, `pyproject.toml`, `config/conference.json` and `config/*.schema.json` → `@PyCon/infrastructure` plus U. `ci.yml` gets **no** secrets and uses `pull_request`, never `pull_request_target`, so fork PRs are safe.

---

## 5. `.github/workflows/ci.yml` (PR and main; no secrets)

Action versions below are major tags. **Before the first release run, pin every `uses:` to a full commit SHA**, as `ACTION/action.yml` does; `zizmor` in the lint job flags unpinned ones.

```yaml
name: CI

on:
  pull_request:
  push:
    branches: [main, "release/**"]
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

env:
  UV_LOCKED: "1"                  # uv run inside flet-build-action must not rewrite uv.lock
  PYTHONUTF8: "1"
  FLET_CLI_NO_RICH_OUTPUT: "1"

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
        with: { persist-credentials: false }
      - uses: astral-sh/setup-uv@v8.2.0
        with: { python-version: "3.14" }
      - run: uv sync
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run pyright
      - name: Release guards (no flet in core, exact pins, no dev URLs/LAN hosts/literal years)
        run: uv run python tools/check_release.py guards
      - name: Workflow security lint
        run: uv run zizmor --min-severity medium .github/workflows

  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
        with: { persist-credentials: false }
      - uses: astral-sh/setup-uv@v8.2.0
        with: { python-version: "3.14" }
      - uses: actions/setup-node@v4
        with: { node-version: "22", cache: npm, cache-dependency-path: tools/ionic_reference/package-lock.json }
      - run: npm ci --prefix tools/ionic_reference
      - run: uv sync
      - name: Unit (core, hypothesis) under two device time zones (D-52; labels and day buckets must not change)
        run: |
          TZ=America/Los_Angeles uv run pytest tests/unit -q --junitxml build/junit/unit-la.xml
          TZ=Pacific/Kiritimati uv run pytest tests/unit -q --junitxml build/junit/unit-kiritimati.xml
      - name: Differential (Ionic processData/filterSession/pipes vs Python, 2025 + 2026 feeds)
        run: |
          node tools/ionic_reference/run.mjs --feeds tests/fixtures/feeds --out "$RUNNER_TEMP/ionic-ref"
          uv run pytest tests/differential -q --ionic-ref "$RUNNER_TEMP/ionic-ref" --junitxml build/junit/differential.xml
      - name: Contract (recorded fixtures only)
        run: uv run pytest tests/contract -q -m "not live" --junitxml build/junit/contract.xml
      - name: app-config / app-content schemas (incl. bundled fallback)
        run: uv run python tools/check_release.py content
      - if: ${{ !cancelled() }}
        uses: actions/upload-artifact@v7
        with: { name: junit-test, path: build/junit/, if-no-files-found: ignore }

  licences:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
        with: { persist-credentials: false }
      - uses: astral-sh/setup-uv@v8.2.0
        with: { python-version: "3.14" }
      - name: Runtime + mobile-extension closure, licence allowlist (D-27)
        run: |
          uv export --no-dev --no-hashes --format requirements-txt > "$RUNNER_TEMP/req.txt"
          uv run --no-project python tools/check_release.py platform-deps >> "$RUNNER_TEMP/req.txt"
          uv venv "$RUNNER_TEMP/lic" --python 3.14
          uv pip install --python "$RUNNER_TEMP/lic" -r "$RUNNER_TEMP/req.txt" pip-licenses
          "$RUNNER_TEMP/lic/bin/pip-licenses" --partial-match \
            --ignore-packages pip-licenses prettytable wcwidth \
            --allow-only "Apache;MIT;BSD;PSF;Python Software Foundation;ISC;Mozilla Public License 2.0;MPL-2.0"

  ui-smoke:                       # host mode (testing-and-quality.md §6.2): app in the pytest process, fakes, no extensions
    needs: test
    runs-on: ubuntu-latest
    timeout-minutes: 45
    steps:
      - uses: actions/checkout@v6
        with: { persist-credentials: false }
      - uses: astral-sh/setup-uv@v8.2.0
        with: { python-version: "3.14" }
      - run: uv sync
      - name: Pinned flet version
        id: flet
        run: echo "version=$(uv run python -c 'import importlib.metadata as m; print(m.version("flet"))')" >> "$GITHUB_OUTPUT"
      - name: Cache the host client (whole sparse tree, incl. its Flutter build output)
        id: host-cache
        uses: actions/cache@v4
        with: { path: .flet, key: "flet-host-linux-${{ steps.flet.outputs.version }}" }
      - name: Sparse flet-dev/flet checkout at the pinned tag
        if: steps.host-cache.outputs.cache-hit != 'true'
        uses: actions/checkout@v6
        with:
          repository: flet-dev/flet
          ref: v${{ steps.flet.outputs.version }}
          path: .flet
          persist-credentials: false
          sparse-checkout-cone-mode: false
          sparse-checkout: |          # client/pubspec.yaml reaches these through ../ path dependencies; leading / anchors each pattern
            /client/
            /packages/
            /sdk/python/packages/*/src/flutter/
            /.fvmrc
      - name: Flutter from the checkout's .fvmrc (host mode runs `flutter test` itself)
        uses: kuhnroyal/flutter-fvm-config-action/setup@v3
        with: { path: .flet/.fvmrc, cache: true }
      - name: Linux test-host dependencies (reported by flet)
        run: |
          sudo apt-get update --allow-releaseinfo-change
          deps="$(uv run flet --version --json | jq -r '.linux_dependencies | join(" ")')"
          sudo apt-get install -y --no-install-recommends $deps xvfb libgl1-mesa-dri
      - name: UI smoke (host mode, -m smoke)
        env:
          FLET_TEST_DEVICE_MODE: "0"              # the plugin defaults to device mode
          FLET_TEST_DISABLE_FVM: "1"              # `flutter` from the step above
          FLET_TEST_FLUTTER_APP_DIR: ${{ github.workspace }}/.flet/client
          FLET_TEST_APP_PATH: tests/harness
          FLET_TEST_APP_MODULE: host_main
          LIBGL_ALWAYS_SOFTWARE: "true"
          GALLIUM_DRIVER: llvmpipe
        run: xvfb-run -a uv run pytest tests/ui -m smoke --junitxml build/junit/ui-smoke.xml
      - if: ${{ !cancelled() }}
        uses: actions/upload-artifact@v7
        with: { name: junit-ui-smoke, path: build/junit/, if-no-files-found: ignore }

  golden-subset:                  # device mode, Android emulator (testing-and-quality.md §9.1 PR subset)
    needs: test
    runs-on: ubuntu-latest
    timeout-minutes: 60
    steps:
      - uses: actions/checkout@v6
        with: { persist-credentials: false }
      - uses: astral-sh/setup-uv@v8.2.0
        with: { python-version: "3.14" }
      - run: uv sync
      - name: Enable KVM
        run: |
          echo 'KERNEL=="kvm", GROUP="kvm", MODE="0666", OPTIONS+="static_node=kvm"' | sudo tee /etc/udev/rules.d/99-kvm4all.rules
          sudo udevadm control --reload-rules
          sudo udevadm trigger --name-match=kvm
      - name: Dev build_info (devserver scenarios drive clock and data, so not --demo)
        run: uv run python tools/caps_manifest.py --target apk --env dev --out src/pycon_us/build_info.py
      - name: Devserver (the emulator reaches it at 10.0.2.2:8765)
        run: nohup uv run python tools/devserver.py --port 8765 --fixtures tests/fixtures > "$RUNNER_TEMP/devserver.log" 2>&1 &
      - name: PR golden subset
        uses: reactivecircus/android-emulator-runner@v2
        with:
          api-level: 35
          arch: x86_64
          target: google_apis
          disable-animations: true
          emulator-options: -no-snapshot -no-window -gpu swiftshader_indirect -noaudio -no-boot-anim
          script: >-
            adb logcat -c || true ;
            trap 'adb logcat -d -v time flet.python:V python:V AndroidRuntime:E "*:S" > "$RUNNER_TEMP/logcat.txt" 2>&1 || true' EXIT ;
            uv run flet test android -d emulator-5554 --tests-dir tests/golden -k golden_pr_subset --yes -v
            -- --junitxml "$GITHUB_WORKSPACE/build/junit/golden-subset.xml"
      - if: ${{ !cancelled() }}
        uses: actions/upload-artifact@v7
        with: { name: junit-golden-subset, path: build/junit/, if-no-files-found: ignore }
      - if: failure()
        uses: actions/upload-artifact@v7
        with:
          name: golden-subset-failures
          path: |                     # FletTestApp writes <module>_<name>_actual.png beside the golden
            tests/golden/golden/**/*_actual.*
            ${{ runner.temp }}/logcat.txt
            ${{ runner.temp }}/devserver.log
          if-no-files-found: ignore

  trace:                          # D-98 gate over PR junit + the latest nightly junit (testing-and-quality.md §8)
    needs: [test, ui-smoke, golden-subset]
    if: ${{ !cancelled() }}       # a red PR job still yields junit; the gate reads it
    runs-on: ubuntu-latest
    permissions:
      contents: read
      actions: read               # gh run download from nightly.yml
    steps:
      - uses: actions/checkout@v6
        with: { persist-credentials: false }
      - uses: astral-sh/setup-uv@v8.2.0
        with: { python-version: "3.14" }
      - uses: actions/download-artifact@v8
        with: { pattern: junit-*, path: build/junit, merge-multiple: true }
      - name: Latest completed nightly junit on main (device, host, golden, fallback and contract-live results)
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          run="$(gh run list --workflow nightly.yml --branch main --status completed --limit 1 --json databaseId -q '.[0].databaseId')"
          if [ -n "$run" ]; then gh run download "$run" --pattern 'junit-*' --dir "$RUNNER_TEMP/nightly" || true; fi
          mkdir -p build/junit
          if [ -d "$RUNNER_TEMP/nightly" ]; then find "$RUNNER_TEMP/nightly" -name 'nightly-*.xml' -exec cp {} build/junit/ \; ; fi
      - name: Feature trace gate (exit 1 on a required id with no test; from G4 also on a red or yellow one)
        run: uv run python tools/feature_trace.py --check --junit build/junit/*.xml

  build:
    needs: [lint, test]
    name: build ${{ matrix.target }}
    runs-on: ${{ matrix.runner }}
    timeout-minutes: 60
    strategy:
      fail-fast: false
      matrix:
        include:
          - { target: apk, runner: ubuntu-latest }            # debug-key signed: installable for QA, not uploadable
          - { target: ios-simulator, runner: macos-26 }       # unsigned .app
          - { target: web, runner: ubuntu-latest }
    steps:
      - uses: actions/checkout@v6
        with: { persist-credentials: false }
      - uses: astral-sh/setup-uv@v8.2.0
      - name: Dev build_info (manifest = bundled extensions for this target)
        run: >-
          uv run python tools/caps_manifest.py
          --target ${{ matrix.target }} --env dev --build-number 1 --version 27.0.0
          --sha "$GITHUB_SHA" --out src/pycon_us/build_info.py
      - name: flet build ${{ matrix.target }}
        id: build
        uses: flet-dev/flet-build-action@v1
        with:
          target: ${{ matrix.target }}
          runner-python-version: "3.14"
          build-number: "1"
      - uses: actions/upload-artifact@v7
        with:
          name: pycon-us-${{ matrix.target }}-pr${{ github.event.number || github.run_number }}
          path: ${{ steps.build.outputs.archive-path }}
          archive: false
          retention-days: 7
          if-no-files-found: error
```

`UV_LOCKED` reaches the action's inner `uv run` steps (composite steps inherit workflow env), so a stale `uv.lock` fails the build instead of being rewritten.

- **Host client.** `ui-smoke` (and nightly `ui-host`/`fallback-parity`) check out flet-dev/flet at the pinned tag into `.flet/`, sparse as in testing-and-quality.md §6.2; `client/` alone fails at `pub get`. The whole tree is cached per Flet version, so a pin bump re-clones once. `.flet/` is git-ignored and excluded from ruff and pyright.
- **Trace.** `trace` merges the PR jobs' junit with the newest completed `nightly.yml` run on `main` (artifacts `junit-*`, files `nightly-*.xml`), because device flows, the full goldens and `contract-live` run only there. `feature_trace.py --check` applies the ramp itself (testing-and-quality.md §8): before 12-07 it only reports; from M2 a required id with no test fails; from G4 (2027-03-31) a required id that is red (failed or no test) or yellow (only skipped) in the merged junit also fails. Mark `trace` as a required status check from 12-07.

---

## 6. `.github/workflows/release.yml` (tags; protected `release` environment)

```yaml
name: Release

on:
  push:
    tags: ["v2[0-9].*"]                 # v27.0.0-alpha.N, v27.0.0, v27.0.0-rN, v27.0.1 ...
  workflow_dispatch:
    inputs:
      action:
        description: "promote-web: clone a preview channel to live | demo: DEMO apk + ad hoc ipa from this tag"
        type: choice
        options: [promote-web, demo]
      web_channel:
        description: "Preview channel to promote (e.g. b27001)"
        required: false
        default: ""

permissions:
  contents: read

concurrency:
  group: release-${{ github.ref }}
  cancel-in-progress: false

env:
  UV_LOCKED: "1"
  PYTHONUTF8: "1"
  FLET_CLI_NO_RICH_OUTPUT: "1"

jobs:
  meta:
    if: github.event_name == 'push' || inputs.action == 'demo'
    runs-on: ubuntu-latest
    outputs:
      version: ${{ steps.m.outputs.version }}
      build-number: ${{ steps.m.outputs.build_number }}
      pycon-env: ${{ steps.m.outputs.pycon_env }}
      kind: ${{ steps.m.outputs.kind }}                 # alpha | release | respin
    steps:
      - uses: actions/checkout@v6
        with: { persist-credentials: false, fetch-depth: 0 }
      - name: Tag, version, ledger, pins, guards (stdlib only)
        id: m
        env:
          REF_TYPE: ${{ github.ref_type }}
        run: |
          test "$REF_TYPE" = "tag" || { echo "::error::run release.yml on a tag"; exit 1; }
          # demo: grammar and version checks only (DEMO uses build 1, never uploaded, so any older tag is fine)
          python3 tools/check_release.py tag "$GITHUB_REF_NAME" ${{ inputs.action == 'demo' && '--no-ledger' || '' }} >> "$GITHUB_OUTPUT"
          python3 tools/check_release.py guards --release

  build:
    if: github.event_name == 'push'
    needs: meta
    name: ${{ matrix.target }} ${{ needs.meta.outputs.version }} (${{ needs.meta.outputs.build-number }})
    runs-on: ${{ matrix.runner }}
    environment: release
    timeout-minutes: 90
    strategy:
      fail-fast: false
      matrix:
        include:
          - { target: aab, runner: ubuntu-latest }
          - { target: ipa, runner: macos-26 }
          - { target: web, runner: ubuntu-latest }
    env:
      VERSION: ${{ needs.meta.outputs.version }}
      BUILD: ${{ needs.meta.outputs.build-number }}
      PYCON_ENV: ${{ needs.meta.outputs.pycon-env }}
    steps:
      - uses: actions/checkout@v6
        with: { persist-credentials: false }
      - uses: astral-sh/setup-uv@v8.2.0

      - name: build_info.py + caps manifest
        run: >-
          uv run python tools/caps_manifest.py
          --target ${{ matrix.target }} --env "$PYCON_ENV" --version "$VERSION"
          --build-number "$BUILD" --sha "$GITHUB_SHA" --out src/pycon_us/build_info.py

      # ---------- Android signing (env must reach the composite action: use GITHUB_ENV) ----------
      - name: Android upload key
        if: matrix.target == 'aab'
        env:
          KEYSTORE_B64: ${{ secrets.ANDROID_UPLOAD_KEYSTORE_B64 }}
          KS_PASS: ${{ secrets.ANDROID_KEYSTORE_PASSWORD }}
          KEY_PASS: ${{ secrets.ANDROID_KEY_PASSWORD }}
          KEY_ALIAS: ${{ secrets.ANDROID_KEY_ALIAS }}
        run: |
          printf '%s' "$KEYSTORE_B64" | base64 -d > "$RUNNER_TEMP/upload.jks"
          {
            echo "FLET_ANDROID_SIGNING_KEY_STORE=$RUNNER_TEMP/upload.jks"
            echo "FLET_ANDROID_SIGNING_KEY_STORE_PASSWORD=$KS_PASS"
            echo "FLET_ANDROID_SIGNING_KEY_PASSWORD=$KEY_PASS"
            echo "FLET_ANDROID_SIGNING_KEY_ALIAS=$KEY_ALIAS"
          } >> "$GITHUB_ENV"

      # ---------- iOS signing (DOCS/ios.md "Building and signing in CI") ----------
      - name: Import Apple Distribution certificate
        if: matrix.target == 'ipa'
        uses: apple-actions/import-codesign-certs@v7
        with:
          p12-file-base64: ${{ secrets.IOS_CERTIFICATE_P12 }}
          p12-password: ${{ secrets.IOS_CERTIFICATE_PASSWORD }}
      - name: Download App Store profile
        if: matrix.target == 'ipa'
        uses: apple-actions/download-provisioning-profiles@v6
        with:
          bundle-id: org.pycon.us.2023.onsite
          profile-type: IOS_APP_STORE
          issuer-id: ${{ secrets.APPLE_API_ISSUER }}
          api-key-id: ${{ secrets.APPLE_API_KEY_ID }}
          api-private-key: ${{ secrets.APPLE_API_KEY_P8 }}

      - name: flet build ${{ matrix.target }}
        id: build
        uses: flet-dev/flet-build-action@v1
        with:
          target: ${{ matrix.target }}
          runner-python-version: "3.14"     # bundled version comes from requires-python (3.14)
          build-number: ${{ needs.meta.outputs.build-number }}
          build-version: ${{ needs.meta.outputs.version }}

      # ---------- Artifact checks ----------
      - name: Verify AAB (PSF upload key, versionCode, manifest)
        if: matrix.target == 'aab'
        env:
          OUT: ${{ steps.build.outputs.output-path }}
          EXPECTED_SHA256: ${{ vars.ANDROID_UPLOAD_CERT_SHA256 }}
          BT_VERSION: ${{ vars.BUNDLETOOL_VERSION }}
          BT_SHA256: ${{ vars.BUNDLETOOL_SHA256 }}
        run: |
          aab="$(ls "$OUT"/*.aab)"
          keytool -printcert -jarfile "$aab" > "$RUNNER_TEMP/cert.txt"
          if grep -q "CN=Android Debug" "$RUNNER_TEMP/cert.txt"; then echo "::error::AAB is debug-signed"; exit 1; fi
          grep -qF "SHA256: $EXPECTED_SHA256" "$RUNNER_TEMP/cert.txt" || { echo "::error::AAB not signed with the PSF upload key"; exit 1; }
          curl -fsSLo "$RUNNER_TEMP/bundletool.jar" \
            "https://github.com/google/bundletool/releases/download/$BT_VERSION/bundletool-all-$BT_VERSION.jar"
          echo "$BT_SHA256  $RUNNER_TEMP/bundletool.jar" | sha256sum -c -
          java -jar "$RUNNER_TEMP/bundletool.jar" dump manifest --bundle "$aab" > "$RUNNER_TEMP/AndroidManifest.xml"
          python3 tools/check_release.py android-manifest "$RUNNER_TEMP/AndroidManifest.xml" --build "$BUILD" --version "$VERSION"

      - name: Verify IPA (team, bundle id, versions, plist)
        if: matrix.target == 'ipa'
        env:
          OUT: ${{ steps.build.outputs.output-path }}
        run: |
          ipa="$(ls "$OUT"/*.ipa)"
          unzip -q "$ipa" -d "$RUNNER_TEMP/ipa"
          app="$(ls -d "$RUNNER_TEMP"/ipa/Payload/*.app)"
          codesign -dv --verbose=2 "$app" 2>&1 | grep -q "TeamIdentifier=BMM5U3QVKW"
          python3 tools/check_release.py ios-plist "$app/Info.plist" --build "$BUILD" --version "$VERSION"

      - uses: actions/upload-artifact@v7
        with:
          name: pycon-us-${{ matrix.target }}-${{ needs.meta.outputs.version }}-${{ needs.meta.outputs.build-number }}
          path: ${{ steps.build.outputs.archive-path }}
          archive: false
          retention-days: 90
          if-no-files-found: error

      # ---------- Uploads ----------
      - name: Google Play internal track
        if: matrix.target == 'aab'
        uses: r0adkll/upload-google-play@v1
        with:
          serviceAccountJsonPlainText: ${{ secrets.PLAY_SERVICE_ACCOUNT_JSON }}
          packageName: org.pycon.us
          releaseFiles: ${{ steps.build.outputs.output-path }}/*.aab
          releaseName: ${{ needs.meta.outputs.version }} (${{ needs.meta.outputs.build-number }})
          track: internal
          status: completed
          whatsNewDirectory: distribution/whatsnew

      - name: App Store Connect (TestFlight)
        if: matrix.target == 'ipa'
        env:
          OUT: ${{ steps.build.outputs.output-path }}
          KEY_ID: ${{ secrets.APPLE_API_KEY_ID }}
          ISSUER: ${{ secrets.APPLE_API_ISSUER }}
          KEY_P8: ${{ secrets.APPLE_API_KEY_P8 }}
          APP_ID: ${{ vars.APPSTORE_APP_ID }}
        run: |
          mkdir -p ~/.appstoreconnect/private_keys
          printf '%s' "$KEY_P8" > ~/.appstoreconnect/private_keys/AuthKey_${KEY_ID}.p8
          xcrun altool --upload-package "$OUT"/*.ipa -t ios \
            --apiKey "$KEY_ID" --apiIssuer "$ISSUER" --apple-id "$APP_ID"

      - name: PWA to a Firebase preview channel (promoted later, exact files)
        if: matrix.target == 'web' && vars.PWA_ENABLED == 'true'
        uses: FirebaseExtended/action-hosting-deploy@v0
        with:
          repoToken: ${{ secrets.GITHUB_TOKEN }}
          firebaseServiceAccount: ${{ secrets.FIREBASE_SERVICE_ACCOUNT }}
          projectId: ${{ vars.FIREBASE_PROJECT_ID }}
          target: app
          channelId: b${{ needs.meta.outputs.build-number }}
          expires: 30d

  notes:
    if: github.event_name == 'push'
    needs: [meta, build]
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v6
        with: { persist-credentials: false }
      - uses: astral-sh/setup-uv@v8.2.0
      - name: Draft GitHub release with the caps matrix
        env:
          GH_TOKEN: ${{ github.token }}
          TAG: ${{ github.ref_name }}
          BUILD: ${{ needs.meta.outputs.build-number }}
          KIND: ${{ needs.meta.outputs.kind }}
          VERSION: ${{ needs.meta.outputs.version }}
          PYCON_ENV: ${{ needs.meta.outputs.pycon-env }}
        run: |
          {
            echo "Build $BUILD from $GITHUB_SHA"
            echo
            for t in aab ipa web; do
              # caps_manifest.py only writes build_info; the matrix comes from the app module (D-74)
              uv run python tools/caps_manifest.py --target "$t" --env "$PYCON_ENV" --version "$VERSION" \
                --build-number "$BUILD" --sha "$GITHUB_SHA" --out src/pycon_us/build_info.py
              echo "### $t"
              uv run python -m pycon_us.platform.caps
            done
          } > "$RUNNER_TEMP/notes.md"
          pre=""
          if [ "$KIND" = "alpha" ]; then pre="--prerelease"; fi
          gh release create "$TAG" --draft --verify-tag $pre --title "$TAG ($BUILD)" --notes-file "$RUNNER_TEMP/notes.md"

  promote-web:
    if: github.event_name == 'workflow_dispatch' && inputs.action == 'promote-web'
    runs-on: ubuntu-latest
    environment: release
    steps:
      - uses: actions/checkout@v6
        with: { persist-credentials: false }
      - uses: actions/setup-node@v4
        with: { node-version: "22" }
      - name: Clone the tested preview channel to live (no rebuild)
        env:
          SA: ${{ secrets.FIREBASE_SERVICE_ACCOUNT }}
          PROJECT: ${{ vars.FIREBASE_PROJECT_ID }}
          CHANNEL: ${{ inputs.web_channel }}
          FT_VERSION: ${{ vars.FIREBASE_TOOLS_VERSION }}
        run: |
          printf '%s' "$SA" > "$RUNNER_TEMP/sa.json"
          export GOOGLE_APPLICATION_CREDENTIALS="$RUNNER_TEMP/sa.json"
          site="$(python3 -c 'import json;print(json.load(open(".firebaserc"))["targets"]["'"$PROJECT"'"]["hosting"]["app"][0])')"
          npx --yes "firebase-tools@$FT_VERSION" hosting:clone "$site:$CHANNEL" "$site:live" --project "$PROJECT"

  demo:
    if: github.event_name == 'workflow_dispatch' && inputs.action == 'demo'
    needs: meta
    name: DEMO ${{ matrix.target }}
    runs-on: ${{ matrix.runner }}
    environment: release
    timeout-minutes: 90
    strategy:
      fail-fast: false
      matrix:
        include:
          - { target: apk, runner: ubuntu-latest }
          - { target: ipa, runner: macos-26 }
    steps:
      - uses: actions/checkout@v6
        with: { persist-credentials: false }
      - uses: astral-sh/setup-uv@v8.2.0
      - name: DEMO build_info (bundled feed, fixed clock, SimulatedScanner, separate DB; D-84)
        # staging env: stage phones poll the staging app-config (PLAN §11 demo step 3 vetoes `scanner` there)
        # and simulated scans never reach the prod API
        run: >-
          uv run python tools/caps_manifest.py --target ${{ matrix.target }}
          --env staging --demo --version "${{ needs.meta.outputs.version }}" --build-number 1
          --sha "$GITHUB_SHA" --out src/pycon_us/build_info.py
      - name: Ad hoc signing (registered stage phones)
        if: matrix.target == 'ipa'
        uses: apple-actions/import-codesign-certs@v7
        with:
          p12-file-base64: ${{ secrets.IOS_CERTIFICATE_P12 }}
          p12-password: ${{ secrets.IOS_CERTIFICATE_PASSWORD }}
      - if: matrix.target == 'ipa'
        uses: apple-actions/download-provisioning-profiles@v6
        with:
          bundle-id: org.pycon.us.2023.onsite
          profile-type: IOS_APP_ADHOC
          issuer-id: ${{ secrets.APPLE_API_ISSUER }}
          api-key-id: ${{ secrets.APPLE_API_KEY_ID }}
          api-private-key: ${{ secrets.APPLE_API_KEY_P8 }}
      - id: build
        uses: flet-dev/flet-build-action@v1
        with:
          target: ${{ matrix.target }}
          runner-python-version: "3.14"
          build-number: "1"
          extra-args: ${{ matrix.target == 'ipa' && '--ios-export-method release-testing' || '' }}
      - uses: actions/upload-artifact@v7
        with:
          name: pycon-us-DEMO-${{ matrix.target }}
          path: ${{ steps.build.outputs.archive-path }}
          archive: false
          retention-days: 60
          if-no-files-found: error
```

Notes:
- **What triggers what.** A tag push builds, verifies and uploads to Play internal, TestFlight and a hosting preview channel. Moving a build to beta or production happens in the store consoles (§11), so the binary that ships is the one that was tested (D-92). The PWA is promoted with `promote-web` (`hosting:clone`, no rebuild).
- **Signing env.** The Android signing variables go through `$GITHUB_ENV` in the `aab` job only. The iOS job never sees them.
- **First run.** Confirm by hand that the AAB check really rejects a debug-signed bundle: run once with the keystore step disabled on a scratch tag.
- **DEMO APK.** The DEMO APK is debug-signed (no keystore step), with build number 1. It is sideloaded onto dedicated stage phones and is never uploaded.
- **Gradle heap.** `org.gradle.jvmargs` defaults to `-Xmx8G` (`CLI/commands/build_base.py:1147-1157`). That is fine on public-repo `ubuntu-latest` (16 GB).
- **altool.** It needs `--apple-id` with the numeric app id (`DOCS/ios.md:780-806`). Spike S5 runs the same command against a throwaway app in U's own account, because P4 only lands on 01-15.

---

## 7. `.github/workflows/nightly.yml`

Job names and commands follow testing-and-quality.md §15. `ui-host` and `fallback-parity` share one step list through a YAML anchor (`&host-steps`), and `ui-device-android` and `golden-full` share `&android-steps`. GitHub Actions accepts anchors and aliases, but not `<<:` merge keys, so the per-job differences are job-level `env`.

```yaml
name: Nightly

on:
  schedule:
    - cron: "17 6 * * *"        # 06:17 UTC (late night US Pacific)
  workflow_dispatch:
    inputs:
      update_goldens:
        description: "golden-full: 'failed' rewrites only missing or changed goldens and opens a goldens/<branch> PR"
        type: choice
        options: [compare, failed]
        default: compare

permissions:
  contents: read
  issues: write

env:
  PYTHONUTF8: "1"
  FLET_CLI_NO_RICH_OUTPUT: "1"

jobs:
  ui-host:                        # every H flow (testing-and-quality.md §6.4), host mode
    runs-on: ubuntu-latest
    env: { UV_LOCKED: "1", TESTS: tests/ui }   # UV_LOCKED is not workflow-wide: flet-main edits pyproject
    timeout-minutes: 60
    steps: &host-steps
      - uses: actions/checkout@v6
        with: { persist-credentials: false }
      - uses: astral-sh/setup-uv@v8.2.0
        with: { python-version: "3.14" }
      - run: uv sync
      - name: Pinned flet version
        id: flet
        run: echo "version=$(uv run python -c 'import importlib.metadata as m; print(m.version("flet"))')" >> "$GITHUB_OUTPUT"
      - name: Cache the host client (same key as ci.yml ui-smoke)
        id: host-cache
        uses: actions/cache@v4
        with: { path: .flet, key: "flet-host-linux-${{ steps.flet.outputs.version }}" }
      - name: Sparse flet-dev/flet checkout at the pinned tag
        if: steps.host-cache.outputs.cache-hit != 'true'
        uses: actions/checkout@v6
        with:
          repository: flet-dev/flet
          ref: v${{ steps.flet.outputs.version }}
          path: .flet
          persist-credentials: false
          sparse-checkout-cone-mode: false
          sparse-checkout: |
            /client/
            /packages/
            /sdk/python/packages/*/src/flutter/
            /.fvmrc
      - uses: kuhnroyal/flutter-fvm-config-action/setup@v3
        with: { path: .flet/.fvmrc, cache: true }
      - name: Linux test-host dependencies (reported by flet)
        run: |
          sudo apt-get update --allow-releaseinfo-change
          deps="$(uv run flet --version --json | jq -r '.linux_dependencies | join(" ")')"
          sudo apt-get install -y --no-install-recommends $deps xvfb libgl1-mesa-dri
      - name: Host-mode suite (${{ github.job }})
        env:
          FLET_TEST_DEVICE_MODE: "0"
          FLET_TEST_DISABLE_FVM: "1"
          FLET_TEST_FLUTTER_APP_DIR: ${{ github.workspace }}/.flet/client
          FLET_TEST_APP_PATH: tests/harness
          FLET_TEST_APP_MODULE: host_main
          LIBGL_ALWAYS_SOFTWARE: "true"
          GALLIUM_DRIVER: llvmpipe
        run: xvfb-run -a uv run pytest "$TESTS" --junitxml "build/junit/nightly-$GITHUB_JOB.xml"
      - if: ${{ !cancelled() }}
        uses: actions/upload-artifact@v7
        with: { name: "junit-${{ github.job }}", path: build/junit/, if-no-files-found: ignore }

  fallback-parity:                # L5: all_off, all_on and each single-key veto (testing-and-quality.md §7)
    runs-on: ubuntu-latest
    env: { UV_LOCKED: "1", TESTS: tests/fallback }
    timeout-minutes: 60
    steps: *host-steps

  ui-device-android:              # every D flow on the API 35 emulator (about 45 min)
    runs-on: ubuntu-latest
    env: { UV_LOCKED: "1", TESTS: tests/ui, FLET_TEST_ARGS: "" }
    timeout-minutes: 120
    steps: &android-steps
      - uses: actions/checkout@v6
        with: { persist-credentials: false }
      - uses: astral-sh/setup-uv@v8.2.0
        with: { python-version: "3.14" }
      - run: uv sync
      - name: Enable KVM
        run: |
          echo 'KERNEL=="kvm", GROUP="kvm", MODE="0666", OPTIONS+="static_node=kvm"' | sudo tee /etc/udev/rules.d/99-kvm4all.rules
          sudo udevadm control --reload-rules
          sudo udevadm trigger --name-match=kvm
      - name: Dev build_info (devserver scenarios drive clock and data, so not --demo)
        run: uv run python tools/caps_manifest.py --target apk --env dev --out src/pycon_us/build_info.py
      - name: Devserver (the emulator reaches it at 10.0.2.2:8765)
        run: nohup uv run python tools/devserver.py --port 8765 --fixtures tests/fixtures > "$RUNNER_TEMP/devserver.log" 2>&1 &
      - name: Device-mode suite (${{ github.job }})
        uses: reactivecircus/android-emulator-runner@v2
        with:
          api-level: 35
          arch: x86_64
          target: google_apis
          disable-animations: true
          emulator-options: -no-snapshot -no-window -gpu swiftshader_indirect -noaudio -no-boot-anim
          script: >-
            adb logcat -G 16M || true ;
            adb logcat -c || true ;
            trap 'adb logcat -d -v time flet.python:V python:V AndroidRuntime:E "*:S" > "$RUNNER_TEMP/logcat.txt" 2>&1 || true' EXIT ;
            uv run flet test android -d emulator-5554 --tests-dir "$TESTS" --yes -v $FLET_TEST_ARGS
            -- --junitxml "$GITHUB_WORKSPACE/build/junit/nightly-$GITHUB_JOB.xml"
      - if: ${{ !cancelled() }}
        uses: actions/upload-artifact@v7
        with: { name: "junit-${{ github.job }}", path: build/junit/, if-no-files-found: ignore }
      - if: failure()
        uses: actions/upload-artifact@v7
        with:
          name: "${{ github.job }}-failures"
          path: |                     # FletTestApp writes <module>_<name>_actual.png beside the golden
            tests/golden/golden/**/*_actual.*
            ${{ runner.temp }}/logcat.txt
            ${{ runner.temp }}/devserver.log
          if-no-files-found: ignore
      - name: Open the goldens PR (golden-full with update_goldens=failed only)
        if: github.job == 'golden-full' && inputs.update_goldens == 'failed'
        uses: peter-evans/create-pull-request@v7
        with:
          branch: goldens/${{ github.ref_name }}
          add-paths: tests/golden/golden/**/*.png
          title: "Goldens: re-record failed images (${{ github.ref_name }})"
          body: "List each changed image with the feature id that changed it; merge needs `goldens-approved` (testing-and-quality.md §9.4)."

  golden-full:                    # 140 + 14 text-scale goldens on the reference AVD (testing-and-quality.md §9.1)
    runs-on: ubuntu-latest
    permissions: { contents: write, pull-requests: write }   # only the goldens PR step writes
    env:
      UV_LOCKED: "1"
      TESTS: tests/golden
      FLET_TEST_ARGS: ${{ inputs.update_goldens == 'failed' && '--update-failed-goldens' || '' }}
    timeout-minutes: 120
    steps: *android-steps

  ui-device-ios:                  # the 6 starred flows + iOS dark-surface goldens (THEME-03), iOS 26 simulator
    runs-on: macos-26
    env:
      UV_LOCKED: "1"
      STAR_FLOWS: >-
        test_SHELL_02_first_run_welcome_to_schedule or test_SCHED_05_live_search_all_days or
        test_SCHED_16_jump_to_now_and_back_no_rescroll or test_DATA_02_offline_cold_start_from_cache or
        test_AUTH_08_login_lands_on_lead_scanner or test_DOOR_04_admission_outcomes
    timeout-minutes: 120
    steps:
      - uses: actions/checkout@v6
        with: { persist-credentials: false }
      - uses: astral-sh/setup-uv@v8.2.0
        with: { python-version: "3.14" }
      - run: uv sync
      - run: uv run python tools/caps_manifest.py --target ios-simulator --env dev --out src/pycon_us/build_info.py
      - name: Boot an iPhone 16 simulator
        run: |
          udid="$(xcrun simctl list devices available -j | jq -r '[.devices[][] | select(.name == "iPhone 16")][0].udid')"
          test -n "$udid" && test "$udid" != null || { xcrun simctl list devices available; exit 1; }
          xcrun simctl boot "$udid" || true
          xcrun simctl bootstatus "$udid" -b
          echo "IOS_UDID=$udid" >> "$GITHUB_ENV"
      - name: Devserver (the simulator reaches it at 127.0.0.1:8765)
        run: nohup uv run python tools/devserver.py --port 8765 --fixtures tests/fixtures > "$RUNNER_TEMP/devserver.log" 2>&1 &
      - name: Starred flows, then the 14 dark goldens at 390
        run: |
          uv run flet test ios -d "$IOS_UDID" --tests-dir tests/ui -k "$STAR_FLOWS" --yes -v \
            -- --junitxml "$GITHUB_WORKSPACE/build/junit/nightly-ui-device-ios.xml"
          uv run flet test ios -d "$IOS_UDID" --tests-dir tests/golden -k "golden_screens and dark and not contrast and 390" --yes -v \
            -- --junitxml "$GITHUB_WORKSPACE/build/junit/nightly-golden-ios.xml"
      - if: ${{ !cancelled() }}
        uses: actions/upload-artifact@v7
        with: { name: junit-ui-device-ios, path: build/junit/, if-no-files-found: ignore }
      - if: failure()
        uses: actions/upload-artifact@v7
        with: { name: ui-device-ios-failures, path: "tests/golden/golden/**/*_actual.*", if-no-files-found: ignore }

  contract-live:
    runs-on: ubuntu-latest
    env: { UV_LOCKED: "1" }
    environment: staging
    steps:
      - uses: actions/checkout@v6
        with: { persist-credentials: false }
      - uses: astral-sh/setup-uv@v8.2.0
        with: { python-version: "3.14" }
      - run: uv sync
      - name: Live feed + staging /api/v1 against JSON Schemas (DATA-27 sentinel included)
        id: contract
        env:
          PYCON_STAGING_KEYS: ${{ secrets.STAGING_KEYS_JSON }}
        run: uv run pytest tests/contract -q -m live --junitxml build/junit/nightly-contract-live.xml --report "$RUNNER_TEMP/drift.md"
      - if: ${{ !cancelled() }}
        uses: actions/upload-artifact@v7
        with: { name: junit-contract-live, path: build/junit/, if-no-files-found: ignore }
      - name: Open or update the drift issue
        if: failure() && steps.contract.outcome == 'failure'
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          n="$(gh issue list --label contract-drift --state open --json number -q '.[0].number')"
          if [ -n "$n" ]; then gh issue comment "$n" --body-file "$RUNNER_TEMP/drift.md"
          else gh issue create --title "Contract drift $(date -u +%F)" --label contract-drift --body-file "$RUNNER_TEMP/drift.md"; fi

  perf-web:                       # web first load <= 8 s on the 4G profile (testing-and-quality.md §13)
    runs-on: ubuntu-latest
    env: { UV_LOCKED: "1" }
    timeout-minutes: 60
    steps:
      - uses: actions/checkout@v6
        with: { persist-credentials: false }
      - uses: astral-sh/setup-uv@v8.2.0
        with: { python-version: "3.14" }
      - run: uv sync
      - run: uv run python tools/caps_manifest.py --target web --env prod --out src/pycon_us/build_info.py
      - run: uv run flet build web --yes
      - run: uv run playwright install --with-deps chromium
      - name: 5 cold loads under CDP throttling; p50 of the first_schedule_rows mark
        run: |
          nohup python3 -m http.server 8080 --directory build/web > /dev/null 2>&1 &
          uv run pytest tests/perf -k web_first_load --web-url http://127.0.0.1:8080/ \
            --junitxml build/junit/nightly-perf-web.xml

  tripwires:                      # non-gating trend checks (testing-and-quality.md §13)
    runs-on: ubuntu-latest
    env: { UV_LOCKED: "1" }
    continue-on-error: true
    steps:
      - uses: actions/checkout@v6
        with: { persist-credentials: false }
      - uses: astral-sh/setup-uv@v8.2.0
        with: { python-version: "3.14" }
      - run: uv run pytest tests/perf --junitxml build/junit/nightly-tripwires.xml   # skips web_first_load without --web-url

  burndown:                       # Mondays: feature_trace --burndown into the job summary (backlog §12)
    needs: [ui-host, fallback-parity, ui-device-android, golden-full, ui-device-ios, contract-live]
    if: ${{ !cancelled() }}
    runs-on: ubuntu-latest
    env: { UV_LOCKED: "1" }
    steps:
      - uses: actions/checkout@v6
        with: { persist-credentials: false }
      - uses: astral-sh/setup-uv@v8.2.0
        with: { python-version: "3.14" }
      - uses: actions/download-artifact@v8
        with: { pattern: junit-*, path: build/junit, merge-multiple: true }
      - name: Burn-down (Mondays UTC only)
        run: |
          if [ "$(date -u +%u)" = 1 ]; then
            uv run python tools/feature_trace.py --burndown --junit build/junit/*.xml >> "$GITHUB_STEP_SUMMARY"
          fi

  flet-main:                      # flet-dev/flet main: build + Android smoke; feeds D-23, never blocks a release
    runs-on: ubuntu-latest
    timeout-minutes: 120
    steps:
      - uses: actions/checkout@v6
        with: { persist-credentials: false }
      - uses: actions/checkout@v6
        with:
          repository: flet-dev/flet
          ref: main
          path: _flet
          persist-credentials: false
      - uses: astral-sh/setup-uv@v8.2.0
        with: { python-version: "3.14" }
      - name: Stamp the checkout as 1.99.0 (extensions require flet>=1.1.0,<2)
        env:
          ROOT: ${{ github.workspace }}/_flet
          SDK_PYTHON: ${{ github.workspace }}/_flet/sdk/python
          SCRIPTS: ${{ github.workspace }}/_flet/.github/scripts
          PYPI_VER: "1.99.0"
        run: bash -c 'source "$SCRIPTS/common.sh" && patch_python_package_versions'
      - name: Host env from the checkout (editable, so git-tag and .fvmrc lookups hit the Flet repo); relaxed pins
        run: |
          # every locked dev/runtime package except the flet* ones: this drops the ==1.1.* pins (testing-and-quality.md §7)
          uv export --no-hashes --format requirements-txt --no-emit-project \
            --no-emit-package flet --no-emit-package flet-cli --no-emit-package flet-desktop \
            --no-emit-package flet-web --no-emit-package flet-platform-assets \
            --no-emit-package flet-permission-handler --no-emit-package flet-secure-storage > "$RUNNER_TEMP/rest.txt"
          uv venv .venv --python 3.14
          uv pip install --python .venv -r "$RUNNER_TEMP/rest.txt" \
            -e "_flet/sdk/python/packages/flet[test]" -e _flet/sdk/python/packages/flet-cli \
            -e _flet/sdk/python/packages/flet-platform-assets
          cat >> pyproject.toml <<'EOF'

          [tool.flet.dev_packages]
          flet = "_flet/sdk/python/packages/flet"
          flet-permission-handler = "_flet/sdk/python/packages/flet-permission-handler"
          flet-secure-storage = "_flet/sdk/python/packages/flet-secure-storage"
          EOF
          .venv/bin/python tools/caps_manifest.py --target apk --env dev --build-number 1 --version 27.0.0 \
            --sha "$GITHUB_SHA" --out src/pycon_us/build_info.py
      - name: flet build apk against flet@main (main template + Dart path override are automatic)
        id: build
        run: .venv/bin/flet build apk --yes -v --build-number 1
      - name: Enable KVM
        run: |
          echo 'KERNEL=="kvm", GROUP="kvm", MODE="0666", OPTIONS+="static_node=kvm"' | sudo tee /etc/udev/rules.d/99-kvm4all.rules
          sudo udevadm control --reload-rules
          sudo udevadm trigger --name-match=kvm
      - name: Devserver (10.0.2.2:8765 from the emulator)
        run: nohup .venv/bin/python tools/devserver.py --port 8765 --fixtures tests/fixtures > "$RUNNER_TEMP/devserver.log" 2>&1 &
      - name: Android smoke flows against flet@main
        id: smoke
        uses: reactivecircus/android-emulator-runner@v2
        with:
          api-level: 35
          arch: x86_64
          target: google_apis
          disable-animations: true
          emulator-options: -no-snapshot -no-window -gpu swiftshader_indirect -noaudio -no-boot-anim
          script: >-
            adb logcat -c || true ;
            trap 'adb logcat -d -v time flet.python:V python:V AndroidRuntime:E "*:S" > "$RUNNER_TEMP/logcat.txt" 2>&1 || true' EXIT ;
            .venv/bin/flet test android -d emulator-5554 --tests-dir tests/ui --yes -v -- -m smoke
      - if: failure()
        uses: actions/upload-artifact@v7
        with:
          name: flet-main-logs
          path: |
            ${{ runner.temp }}/logcat.txt
            ${{ runner.temp }}/devserver.log
          if-no-files-found: ignore
      - name: Open or update the flet-main-drift issue
        if: failure()
        env:
          GH_TOKEN: ${{ github.token }}
          BUILD: ${{ steps.build.outcome }}
          SMOKE: ${{ steps.smoke.outcome }}
        run: |
          sha="$(git -C _flet rev-parse --short HEAD)"
          n="$(gh issue list --label flet-main-drift --state open --json number -q '.[0].number')"
          body="flet@main $sha: build $BUILD, Android smoke $SMOKE: $GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID"
          if [ -n "$n" ]; then gh issue comment "$n" --body "$body"
          else gh issue create --title "flet@main drift ($sha)" --label flet-main-drift --body "$body"; fi
```

Notes:
- **Host vs device.** `ui-host` and `fallback-parity` are host mode: the app runs in the pytest process against fakes, so they need the sparse `.flet/` client and `flutter` on `PATH`, not a packaged build. Nightly fallback parity selects its states with scenario `caps` (testing-and-quality.md §7); `build_info.CAPS_OVERRIDE` (D-125) remains for an all-on or all-off device test host built by hand. The device jobs build a dev-env test host (`PYCON_ENV="dev"`, no `--demo`) and read their scenario from the devserver (testing-and-quality.md §2.2). `conftest.py` skips `device_only` tests in host mode and `host_only` tests in device mode, so one `tests/ui` tree serves both.
- **Goldens PR.** `golden-full` with `update_goldens=failed` runs `flet test … --update-failed-goldens` (= `FLET_TEST_GOLDEN=failed`) and opens `goldens/<branch>` with only the changed PNGs. A PR opened with `GITHUB_TOKEN` does not trigger `ci.yml`; push an empty commit or re-run CI on it before review.
- **Junit.** Every test job uploads `junit-<job>` with `nightly-*.xml` files. `ci.yml` `trace` downloads the newest completed run's set, and `burndown` reads this run's set.
- With an editable flet-cli installed from a checkout, `flet build` and `flet test` use the checkout's template and point the Dart `flet` package at `packages/flet` (`CLI/commands/build_base.py:1884-1891, 1950-1960`).
- `dev_packages` rewrites the app's `flet*` requirements to `file://` URLs (`CLI/commands/build_base.py:2617-2645`). So the bundled Python side is `main` too, never a mix with 1.1.x. The Dart side comes from the local template's path override (`CLI/commands/build_base.py:1950-1960`), so neither half resolves from PyPI or pub.dev (cf. the Python/Dart mismatch hazard in `DOCS/index.md` "Prerelease compatibility").
- The `flet-main` job runs the Android smoke flows (`-m smoke`; `host_only` smoke flows skip in device mode) after the build, and a red build or smoke opens or updates one `flet-main-drift` issue. It feeds the E1-E4 compatibility policy (D-23) and never blocks a release. It stays an M0 spike item until a run has been seen to pass (backlog §4.0).

---

## 8. Server-driven content and the PWA: hosting and deploy

### 8.1 Layout

```
config/
  conference.json                     # YEAR, CONF_TZ, SITE_URL -> build_info (D-125)
  app-config.schema.json              # schema 1 (D-63); PSF-I in CODEOWNERS
  app-content.schema.json
  2027/prod/app-config.json
  2027/prod/app-content.json
  2027/staging/app-config.json        # demo step 3: veto `scanner` here
  2027/staging/app-content.json
src/pycon_us/assets/app-content.json  # bundled fallback = copy of 2027/prod at build time (D-63, D-88)
```

Served URLs (`no-cache`, fetched on start, on resume and every 5 min; failures are silent):
- `https://<config-site>/2027/mobile/app-config.json`
- `https://<config-site>/2027/mobile/app-content.json`
- `https://<config-site>/2027/mobile/staging/…`

P7 decides between `<config-site>` = a Firebase Hosting site under the PSF project (default here) and `us.pycon.org/{YEAR}/mobile/`. If it is `us.pycon.org`, `content.yml` instead opens a PR on `pycon-site`, and the 30-minute content SLA (criterion S11) needs PSF-I on hand.

### 8.2 `firebase.json` and `.firebaserc`

```json
{
  "hosting": [
    {
      "target": "app",
      "public": "build/web",
      "ignore": ["firebase.json"],
      "rewrites": [{ "source": "**", "destination": "/index.html" }],
      "headers": [
        { "source": "**", "headers": [{ "key": "Cache-Control", "value": "no-cache" }] }
      ]
    },
    {
      "target": "config",
      "public": "build/config",
      "headers": [
        {
          "source": "**/*.json",
          "headers": [
            { "key": "Cache-Control", "value": "no-cache" },
            { "key": "Access-Control-Allow-Origin", "value": "*" },
            { "key": "Content-Type", "value": "application/json; charset=utf-8" }
          ]
        }
      ]
    }
  ]
}
```

```json
{
  "projects": { "default": "pycon-us-2023-mobile" },
  "targets": {
    "pycon-us-2023-mobile": {
      "hosting": { "app": ["pycon-us-app"], "config": ["pycon-us-config"] }
    }
  }
}
```

- The rewrite makes `route_url_strategy = "path"` work for deep paths. This is the same rule as Ionic's `firebase.json`.
- **`no-cache` is required.** The Python app ships as `assets/app/app.zip` with no content hash. With the default `max-age=3600`, a new `main.dart.js` could pair with a stale zip for up to an hour.
- `"ignore": ["firebase.json"]` (without `**/.*`) keeps `.well-known/` from `src/assets/` served.
- CORS `*` on the config site lets the PWA (another origin) read the JSON. The files hold no secrets.
- The project id and site ids are placeholders until P7 (2027-01-31). Ionic's `.firebaserc` names `ionic-ng-conf-app`, a template leftover, so the live PWA domain must be confirmed with the PSF before the Flet PWA replaces it.

### 8.3 `.github/workflows/content.yml` (addition; see §17 #4)

```yaml
name: Content

on:
  pull_request:
    paths: ["config/**"]
  push:
    branches: [main]
    paths: ["config/**"]
  workflow_dispatch:

permissions:
  contents: read

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
        with: { persist-credentials: false, fetch-depth: 2 }
      - uses: astral-sh/setup-uv@v8.2.0
        with: { python-version: "3.14" }
      - run: uv sync --locked
      - name: Schema + semantic checks, human diff in the job summary
        run: uv run python tools/check_release.py content --diff-base HEAD~1 >> "$GITHUB_STEP_SUMMARY"

  deploy:
    if: github.event_name != 'pull_request'
    needs: validate
    runs-on: ubuntu-latest
    environment: content
    steps:
      - uses: actions/checkout@v6
        with: { persist-credentials: false }
      - name: Stage files under /<year>/mobile/
        run: |
          rm -rf build/config
          for d in config/20*/; do
            y="$(basename "$d")"
            mkdir -p "build/config/$y/mobile/staging"
            cp "$d"prod/*.json "build/config/$y/mobile/"
            cp "$d"staging/*.json "build/config/$y/mobile/staging/"
          done
      - uses: FirebaseExtended/action-hosting-deploy@v0
        with:
          repoToken: ${{ secrets.GITHUB_TOKEN }}
          firebaseServiceAccount: ${{ secrets.FIREBASE_SERVICE_ACCOUNT }}
          projectId: ${{ vars.FIREBASE_PROJECT_ID }}
          target: config
          channelId: live
```

`check_release.py content` checks, beyond the JSON Schemas (D-63):
- reminder ids are ≥ 8000 and unique;
- every instant is ISO 8601 with an offset;
- `starts_at < ends_at`;
- `latest.build >= max(min_supported.*)`;
- `min_supported` never exceeds the highest ledger build (that would lock everyone out);
- `features` keys come from the known set (staff kill switches from D-83 plus capability keys from D-74);
- `feed_url`/`content_url` are `https` on an allowlisted host;
- the booth ratios lie in [0, 1].

The bundled fallback has to pass the same checks, or CI fails (D-88).

---

## 9. `tools/check_release.py` (one entry point for every gate; stdlib only except `content`, which uses `jsonschema`)

| Subcommand | Checks | Used in |
|---|---|---|
| `tag <name> [--no-ledger]` | Tag grammar (§3.1); version == `[project].version`; ledger row (§3.2; skipped with `--no-ledger`, used only for DEMO builds); `kind`; `pycon_env` (non-alpha ⇒ `prod`); pins unchanged after 03-05 for every `v27.0.*` tag after `v27.0.0-alpha.3`, alphas included (compared with the `alpha.3` pins). Prints `key=value` lines for `$GITHUB_OUTPUT`. | release `meta` |
| `guards [--release]` | `src/pycon_us/core/**` imports no `flet` (D-48). No `FLET_PAGE_URL` in `pyproject.toml`, `src/` or `.github/` (26.2.0 incident class). No `localhost`, `127.0.0.1`, `10.0.2.2`, `192.168.`, `:8551` or `.local` in `src/` outside the `# dev-hosts` block of `settings.py`. No literal years `20[2-3]\d` in `src/pycon_us/` outside `settings.py`, `assets/` and comments. Runtime deps are `==` exact with no pre/dev/rc (D-20). All `flet*` pins from the monorepo (`flet`, `flet-permission-handler`, `flet-secure-storage` and, when added, `flet-notifications`) are equal. No `dev_packages`, path/editable `uv.sources`, `[tool.flet].build_number`, `[tool.flet.template]` or `[tool.flet.flutter.pubspec]`. Both per-platform `deep_linking` tables are set. With `--release` also: no VCS pins unless the tag is alpha; notification permissions only if E2/E3 are in the deps. | ci `lint`, release `meta` |
| `content [--diff-base REF]` | §8.3 | ci `test`, content |
| `platform-deps` | Prints the union of the android and ios `dependencies` | ci `licences` |
| `android-manifest <xml> --build N --version V` | `package="org.pycon.us"`; `versionCode=N`; `versionName=V`; `minSdkVersion=34` (26 if OD-1); `targetSdkVersion=36`. Permissions ⊆ {INTERNET, CAMERA, ACCESS_NETWORK_STATE, …allowlist} with no `AD_ID`, `READ/WRITE_EXTERNAL_STORAGE`, `POST_NOTIFICATIONS` (unless E2/E3) or `USE_EXACT_ALARM` (Play-restricted). Intent filter `pyconus://app` present. | release `build` |
| `ios-plist <plist> --build N --version V` | `CFBundleIdentifier`, `CFBundleVersion=N`, `CFBundleShortVersionString=V`; camera string equals pyproject; `ITSAppUsesNonExemptEncryption=false`; `CFBundleURLSchemes ∋ pyconus`; no `UIBackgroundModes` unless E2 | release `build` |

The permission allowlist starts from the merged-manifest report of the first PSF-signed build (`build/flutter/build/app/outputs/logs/manifest-merger-release-report.txt`, `DOCS/android.md` "Finding where a permission came from") and is then frozen.

---

## 10. Signing details

### 10.1 Android

| Item | Value |
|---|---|
| Key | **Upload key** of `org.pycon.us` (Play App Signing holds the app key). If the PSF lost it: Play Console → App integrity → "Request upload key reset" (takes days; deadline P4 01-15). |
| Delivery | `FLET_ANDROID_SIGNING_KEY_STORE`, `_KEY_STORE_PASSWORD`, `_KEY_PASSWORD`, `_KEY_ALIAS` (`CLI/commands/build_base.py:3098-3127`; one password fills the other; alias default `upload`), read by `signingConfigs.release` in `TPL/android/app/build.gradle.kts` |
| Check | `keytool -printcert -jarfile` SHA-256 = `vars.ANDROID_UPLOAD_CERT_SHA256`, no `CN=Android Debug` (§6) |
| 16 KB pages | Default "modern" packaging is page-aligned (`DOCS/android.md`); never set `legacy_packaging`; check the pre-launch report on alpha.0 |

### 10.2 iOS

| Item | Value |
|---|---|
| Certificate | "Apple Distribution", team `BMM5U3QVKW` |
| Profiles | App Store (name in `export_methods.app-store-connect`) and Ad Hoc for registered stage phones (`release-testing`), downloaded every run with the ASC key (`DOCS/ios.md:770-776`). Development profiles stay local (`flet debug ios`). |
| Export options | `method=app-store-connect`, `teamID`, `signingCertificate`, `uploadSymbols=true`, `manageAppVersionAndBuildNumber=false` (Xcode must not renumber) |
| Preflight | Profile name/UUID, expiry, team and bundle id checked before building (`CLI/commands/build.py:287+`); the name must match the portal exactly |
| Toolchain | `macos-26` (Xcode 26 SDK required since 2026-04-28); rehearsal on the newest image 04-20 → 04-24 (D-16); Flet 1.1 builds with Xcode 27 (#6874) |
| Privacy manifest | Spike S5 uploads once (own account, throwaway bundle id) to see whether ITMS-91053 fires for embedded CPython; if so, U13 |

---

## 11. Release train and staged rollout (D-15, D-92, PLAN §9.3)

| Date | Tag → build | Env | Distribution | Purpose / gate |
|---|---|---|---|---|
| 2027-01-29 | `v27.0.0-alpha.0` → 26900 | staging | Play internal, TestFlight internal | First PSF-signed builds on real ids (M2 exit, G2 01-31) |
| 02-11 | `alpha.1` → 26901 | staging | same | G3 evidence (02-12) |
| 02-19 | `alpha.2` → 26902 | staging | same (Play internal + TestFlight internal; Badge Day staff and sponsor testers added as internal testers) | Badge Day 1 (02-24); E1 0.2.0 |
| 03-05 | `alpha.3` → 26903 | staging | same | **Last pin change** (D-18) |
| 03-19 | `alpha.4` → 26904 | prod | same | 2027 feed (~03-13, UNCONFIRMED) |
| 03-30 | `alpha.5` → 26905 | prod | same | Freeze build, **cut by a co-maintainer** (criterion S12, D-107 as amended by D-126; §17 #9) |
| 04-01 | `v27.0.0` → 27000 | prod | **Play open testing + TestFlight public link** (first external build needs Beta App Review, about 1 day) | Public beta 04-01 → 04-14 |
| 04-07 | `v27.0.0-r1` → 27001 | prod | same | **RC1**; Badge Day 2 (04-09) |
| 04-13 | `v27.0.0-r2` → 27002 (only if needed) | prod | same | RC2 |
| 04-14 | — | — | — | **G5** names the build (crash-free ≥ 99.5 %, 0 P0) |
| 04-16 | the G5 build, no rebuild | prod | App Store: "Submit for review", **manual release**, phased release **off**. Play: promote open testing → production with **managed publishing on**. | Submission (fallback 04-23) |
| 04-20 → 04-24 | rehearsal tag `v27.0.1` → 27010 (the lowest number of the next version), **not** uploaded past internal; the first real hotfix is then `v27.0.1-r1` (27011) or `v27.0.2` (27020). Never an `-rN` tag above a later real build: the ledger and App Store Connect reject lower numbers. | — | — | Hotfix rehearsal on newest Xcode / runner (criterion S11) |
| **04-27** (latest 04-30) | — | — | PSF presses **Release** (iOS) and **Publish** (Play, 20 %); PWA `promote-web` with the same build's channel | Release (G-SHIP) |
| 04-28 / 04-30 | — | — | Play 20 % → 50 % → 100 % | Halt if crash-free < 99.5 % or any P0 (Play "Halt rollout"; iOS: remove from sale only for a data-loss P0) |

Rules:
- Only builds ≥ 27000 may be promoted beyond internal or closed testing. Alpha builds (269xx) stay internal.
- A version string can't move backwards after 27.0.0 is approved, so 27.0.x fixes are `v27.0.N`.
- Hotfixes in conference week: Play production at 100 % right away, after a 30-minute smoke on 2 devices. Apple: request expedited review (D-92).
- Every build is copied to `builds.txt` **before** tagging (§3.2).

---

## 12. Store submission checklist (D-95; PSF owns the forms, P11 by **04-09**)

| # | Item | Owner | Due |
|---|---|---|---|
| 1 | Version 27.0.0 on app 6446810296; Play `org.pycon.us` production track | PSF-I | 04-01 |
| 2 | **Review demo account** with server features `lead_retrieval`, `door_check_in`, `mask_violation` on the prod API (must survive `staff_data_purge_after`) | PSF-E | 04-09 |
| 3 | Review notes: path to Staff Tools, camera use, printable sample-badge QR PDF, manual entry (Guideline 2.1) | U drafts, PSF-E owns | 04-09 |
| 4 | iOS purpose strings as in §2.1, explaining staff scanning (5.1.1) | U drafts, PSF-I approves (P11) | G4 |
| 5 | App Privacy / Data Safety: email linked to account; Sentry crash data not linked, no tracking (OD-4); no analytics, ads or advertising id (OD-3, `AD_ID` removed); staff PII in memory only (OD-9); deletion URL | PSF-I | 04-09 |
| 6 | Age rating (Apple's new questionnaire, required since 2026-01-31) and Play content rating | PSF-E | 04-09 |
| 7 | Export compliance `ITSAppUsesNonExemptEncryption=false` confirmed | PSF-I | 01-31 |
| 8 | Privacy policy updated (Sentry, staff data) | PSF-E | 04-09 |
| 9 | Play: target API 36; pre-launch report clean (16 KB alignment); exact-alarm declaration **only** if E3 ships | U (+ PSF-I) | 04-01 / G3 |
| 10 | Screenshots (6.9", 6.5", iPad 13"; Play phone + tablet) from the DEMO build | U / CC | 04-09 |
| 11 | "What's New" (`distribution/whatsnew/`, ASC) naming #279, #310-#313 | U | 04-14 |
| 12 | Spike S5 / ITMS-91053 result recorded; U13 if needed | U | 12-15 |
| 13 | Review contact on call 04-16 → 04-27 | PSF-E | 04-16 |

---

## 13. Runbooks

### 13.1 Hotfix (criterion S11: tag → Play production at 100 % and App Store expedited review submitted in ≤ 2 h)

| Step | Who | Time |
|---|---|---|
| 1. Decide: can `app-content`, `app-config`, a kill switch or a banner fix it? If yes, use 13.2 instead. | on-call | 0-10 min |
| 2. `git switch -c hotfix/<next> <tag of the build live in the stores>` (e.g. `v27.0.0-r1` if G5 named RC1; never `v27.0.0`, which is beta 1 and lacks the RC fixes), cherry-pick the fix, set the next unused version and add its ledger row: the first hotfix after the 04-20 rehearsal (§11, which already used `v27.0.1` / 27010) is `v27.0.2` (27020) or `v27.0.1-r1` (27011); after that `v27.0.(N+1)` → `27.0.(N+1)` × 10. Open a PR to `release/27.0` | U | 10-25 |
| 3. CI green (lint, unit, differential, smoke); 1 approval | U + CC/PSF-I | 25-45 |
| 4. Tag the name chosen in step 2 (e.g. `v27.0.2`); PSF-I approves the `release` environment | PSF-I | 45-50 |
| 5. `release.yml`: aab about 20 min, ipa about 30 min, then uploads and processing | CI | 50-100 |
| 6. Smoke on 2 devices from internal / TestFlight internal: launch, cached schedule, the fixed flow | on-call | 100-110 |
| 7. Play: promote to production at 100 %. ASC: new version (the step-2 version), submit, request expedited review | PSF-I | 110-120 |
| 8. app-config `latest` → the new build (non-blocking banner). Raise `min_supported` only for a data-loss bug. Merge the fix to `main`. | on-call | after release |

### 13.2 Conference week (M6, 05-01 → 05-18; conference 05-12 → 05-18 confirmed, per-day split UNCONFIRMED)

**Freeze 05-05 (G6):** P0 fixes only; no pin changes; content PRs still allowed. **On call:** U primary, P12 PSF partner secondary (store, Firebase and hosting rights).

| Symptom (all via `content.yml` unless noted) | First lever | Time |
|---|---|---|
| Wrong room, time, Wi-Fi, booth or URL | Edit `config/2027/prod/app-content.json` | < 30 min (clients poll every 5 min) |
| Feed moved or broken | `app-config.feed_url` | < 15 min |
| Staff tool misbehaving | `app-config.features.{lead_retrieval, door_check, swag, coc} = false`. The tool falls back to "not available"; manual or paper process. | < 15 min |
| Native capability misbehaving | `features.<cap> = false` (`scanner`, `push`, `local_notifications`, `calendar`, …) vetoes it back to the interim (D-74) | < 15 min |
| Announcement or emergency | `app-config.banners[]` (`severity`, `starts_at`, `ends_at`). Emergency banners always show in-app (OD-18); PSF also uses email/Discord. | < 10 min |
| Native app broken for a flow | Banner linking the PWA (`promote-web` already live) | < 15 min |
| Crash or data loss | Hotfix (13.1, `release.yml`); halt the Play rollout if staged | ≤ 2 h |

Daily at 08:00 conference time: Sentry crash-free rate (≥ 99.5 %), Play vitals, outbox `failed` counts (staff dashboard), feed age, banner delivery and adoption (criterion S8). Log the result in Linear PYMOBIL.

### 13.3 Year rollover (2028 = config; criterion S12 dry run by **09-30**, ≤ 1 day, no code edits)

1. Copy `config/2027/` to `config/2028/` and set the year, time zone and site URL in `config/conference.json` (they reach `settings` through `build_info`, D-125). Set `app-content.year=2028` and fill in conference name, dates, venue, keynotes, reminders (ids ≥ 8000), Wi-Fi, booths, room pins, URLs and CoC contacts.
2. `app-config`: `feed_url` → `/2028/schedule/conference.json`; reset `banners`; set `staff_data_purge_after`; `min_supported` stays.
3. Bump `[project].version = "28.0.0"`, add ledger row `28000`, and replace the bundled `src/pycon_us/assets/app-content.json` with the 2028 prod file. These are data files; no Python changes.
4. Run nightly `contract-live` against the 2028 sample feed (P8 equivalent) and fix the schema, not the code.
5. Release with tags `v28.0.0-alpha.N` (27900-block) → `v28.0.0`.

Pre-condition to verify during the dry run: `settings.YEAR`, `settings.CONF_TZ` and `settings.SITE_URL` come from `config/conference.json` through `build_info` (D-125), and the API base `{site}/{YEAR}/api/v1` and the feed URL derive from them and app-config. A non-Pacific 2028 venue is therefore a config change (§17 #5).

---

## 14. PWA / web (T2, D-93, NATIVE-09)

- **Build:** `web` leg of `release.yml`; Pyodide 314.0.7, canvaskit (flet-cli default, `CLI/commands/build_base.py:1569-1577`), CDN on. Path routing with the `** → /index.html` rewrite (§8.2).
- **Runtime:** `pyfetch` transport (no httpx on Emscripten); `sentry-sdk` skipped by marker. Browse only: no staff tools, sqlite, push or reminders; login only if the PSF enables CORS on `/api/v1`.
- **Offline:** none (Flutter 3.47's service worker unregisters itself; U11 after the conference).
- **Budget:** first load ≤ 8 s on 4G (D-99), else it becomes an "Install the app" page.
- **Deploy:** every tag → preview channel `b<build>`; `promote-web` at release. It doubles as incident fallback (13.2) and projector demo (PLAN §11).

---

## 15. Dev loop (D-94, PLAN §9.5)

| Task | Command | Notes |
|---|---|---|
| Desktop / web, hot reload | `uv run flet run -r` / `uv run flet run -r --web` (from the repo root; `[tool.flet.app].path = "src"` resolves `src/main.py`) | Without `-r` only `src/main.py` is watched, so edits under `src/pycon_us/` do not reload; hot reload restarts the Python process (PLAN §9.5). Dev stub `build_info.py` has `CAPS=()`: every capability shows its interim |
| Phone, companion app | `uv run flet run --ios` / `--android` | QR, LAN port 8551; only the companion's built-in extensions |
| Real shell, all extensions | `uv run flet debug ios\|android` (`--device-id`, `--show-devices`; `flet devices`) | Real bundle id, plist, permissions, E1; Python changes need a re-run |
| Tests | Host mode: `FLET_TEST_DEVICE_MODE=0 FLET_TEST_DISABLE_FVM=1 FLET_TEST_FLUTTER_APP_DIR=.flet/client FLET_TEST_APP_PATH=tests/harness FLET_TEST_APP_MODULE=host_main uv run pytest tests/ui -m smoke`; device mode: `uv run flet test android -d emulator-5554 --tests-dir tests/ui --yes [-k …]` (`--update-failed-goldens`, `FLET_TEST_GOLDEN`) | Same as CI `ui-smoke` / nightly `ui-device-android` (testing-and-quality.md §6.2) |
| Fake backend | `uv run python tools/devserver.py --port 8000 --fixtures tests/fixtures` | Recorded feeds + fake signed `/api/v1` (check-in, lead, CoC, `mobile_state`); emulator host `10.0.2.2` (dev only, guarded) |
| Fixtures | `uv run python tools/record_fixtures.py --env staging` | Needs P3 keys locally; committed scrubbed |

Env vars (`flet run` only; packaged builds use `build_info`): `PYCON_ENV=dev|staging|prod` (base URLs, `pycon.<env>.` prefix, D-60), `PYCON_FAKE_NOW=<ISO with offset>` (D-52), `DEMO=1` (bundled feed, fixed clock, `SimulatedScanner`, separate DB). **No `FLET_PAGE_URL` dev client** (26.2.0 incident class; guarded). Logs: `adb logcat -s flet.python`; simulator: `xcrun simctl spawn booted log stream --predicate 'sender == "dart_bridge"'`.

---

## 16. Optional Appflow bridge 26.3 (D-96, OD-8; NATIVE-10)

Default: **skip.** Ships only if the PSF grants Appflow access by **03-15** (P13); no gate depends on it.

| Item | Spec |
|---|---|
| Vehicle | Ionic 26.3.0 **web bundle** via Appflow live update (channel `Production`). The 26.2.1 binary already has `@capacitor/filesystem`; users get it after a background `sync()`, either on a later cold start (Ionic Makefile note) or only when they tap "Install Latest Update" (LIVE-01, `autoUpdateMethod: 'none'`); which one applies is **UNVERIFIED** (add it to the per-OS spike below), so coverage is partial. |
| Export | Once on boot: `Filesystem.writeFile({directory: Directory.Data})` → `pycon-bridge-v1.json` = `{schema: 1, exported_at, did_tutorial (ion_did_tutorial), theme, schedule_filters (Ionic `scheduleFilters`; null ≠ []), notification_prefs, favorite_sessions: [str]}`; `theme`, `notification_prefs` and `favorite_sessions` keep their Ionic key names |
| Never exported | `key`, `secret`, `email`, `nickname`, role flags, consent, staff sponsor, any scan or note record |
| Import | `services/bridge_import.py`, bootstrap step 2 (D-46): Android `await StoragePaths().get_application_support_directory()` (= `getFilesDir()`, Capacitor `Data`); iOS `await StoragePaths().get_application_documents_directory()` (Capacitor `Data` = Documents). Both coroutines exist (SDK, 2026-10-11). **Path mapping UNVERIFIED: spike one device per OS before asking P13.** |
| Rules | Once (`bridge_imported_at` unset); validate; write `pycon.prod.*` prefs; delete the file even on failure; never block boot; favourites then union-merge at login (OD-5). Unsynced 26.x scans are lost either way. |

---

## 17. Discrepancies with PLAN.md and the decisions record

All rows are resolved: each names the section P entry of [`decisions.md`](decisions.md) that records it, and PLAN.md follows.

| # | Where | Issue | This document |
|---|---|---|---|
| 1 | D-90, PLAN §9.2 ("27.0.0 → 27000-27009") | Ten numbers per version can't hold the 2-weekly internal builds from M2 (D-92) plus beta, RCs and failed uploads (about 10 before G5, zero margin); the release would silently become 27.0.1. | **Resolved by D-126.** **Alpha block** `v27.0.0-alpha.N` → `26900+N`, internal only; formula and `version = 27.0.0` unchanged for promotable builds. |
| 2 | D-38, PLAN §5.2/§9.1 (`[tool.flet.deep_linking]`) | flet-cli reads only `[tool.flet.android.deep_linking]` / `[tool.flet.ios.deep_linking]` for mobile targets (`CLI/commands/build_base.py:1421-1438`), contrary to `DOCS/index.md:1391-1394`. As written, **no deep links on mobile**. | **Resolved by D-109.** Per-platform tables, enforced by `guards`. **Upstream bug**, fixed in open PR [flet-dev/flet#6953](https://github.com/flet-dev/flet/pull/6953). |
| 3 | D-90 `build_info.py` fields | Packaged apps can't read `DEMO=1` or test env vars; DEMO builds (D-84) and fallback-parity hosts (D-97) need build-time flags. | **Resolved by D-125.** Adds `DEMO`, `CAPS_OVERRIDE`; store tags require `False`/`None`. |
| 4 | Section M (three workflows) | Content deploy needs its own trigger and a lighter approval than `release` for the 30-minute SLA (criterion S11). | **Resolved by D-127.** Adds `content.yml` + `content` environment. |
| 5 | PLAN §5.4 `settings.CONF_TZ` vs criterion S12 | Time zone is code; a non-Pacific 2028 venue needs a code edit. | **Resolved by D-125.** `CONF_TZ` (with `YEAR`, `SITE_URL`) comes from `config/conference.json` through `build_info`, so a new venue is a config change (runbook 13.3). |
| 6 | D-91 "unsigned `apk`" | Without a keystore `flet build apk` is **debug-signed**. | **Resolved by D-126.** Wording only. |
| 7 | PLAN §9.2 release uploads to Firebase Hosting | Deploying every tag live would publish alphas/betas and break "ship the tested build" (D-92). | **Resolved by D-127.** Tags → preview channels; `promote-web` clones the G5 channel to live. |
| 8 | D-91, PLAN §9.2 (`release.yml` on tag `v27.*`) | A `v27.*` filter would need a workflow edit for the 2028 rollover (criterion S12: no code edits). | **Resolved by D-126.** Trigger `v2[0-9].*` so the same workflow serves 28.x (runbook 13.3); `check_release.py tag` still enforces the grammar and the ledger. |
| 9 | Criterion S12, D-107 (co-maintainer "cuts a beta before 03-31") | Under the alpha block (#1) every build before 03-31 is an internal alpha, never promoted; the first beta is `v27.0.0` on 04-01. | **Resolved by D-126.** S12's "beta" before 03-31 is met by the co-maintainer cutting the internal freeze build `alpha.5` (03-30) end to end. |
