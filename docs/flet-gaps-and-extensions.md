# Flet gaps and the extension roadmap

**Status:** companion to [`PLAN.md`](../PLAN.md) §6, 2026-10-11. **Owner:** U. **Binding inputs:** PLAN.md, the decisions record ([`decisions.md`](decisions.md), D-01..D-136; this doc implements D-23..D-29, D-67, D-74..D-79, D-89, the §O spec and the amendments D-109, D-111..D-114, D-131..D-133), [`feature-matrix.md`](feature-matrix.md) (ids).

This doc is the implementation spec for every Flet gap the 27.0 app works around: six extensions (**E1-E6**) and fifteen core/CLI items (**U1-U15**). For each one it gives the feature ids it serves, the interim that always ships, the target API, the wrapped Dart package and its exact version, platform setup, effort, owner, deadline and gate, tests, the `Caps` key and probe, and the steps to upgrade the app.

**Conventions.**
- **exists** = verified in the local monorepo (`flet-dev/flet` @ `7688de3`, 1.1.0 in development; the uv env reports `flet_version 1.0.4`) by introspection on 2026-10-11.
- **proposed (Ux/Ex)** = does not exist yet. The name is the one this doc fixes (D-25: "final names belong in the flet-gaps doc"), and `platform/caps.py` probes exactly that name.
- Dates without a year are 2026-10..12 or 2027-01..09, as in PLAN. **UNCONFIRMED** marks external dates nobody has confirmed.
- Paths: `FLET` = `sdk/python/packages/flet/src/flet`, `CLI` = `sdk/python/packages/flet-cli/src/flet_cli/commands`, `TPL` = `sdk/python/templates/build/{{cookiecutter.out_dir}}`, `DART` = `packages/flet/lib/src` (all in the monorepo).

---

## 1. Register at a glance

| Id | Gap | Feature ids | Interim (always shipped, always tested) | Target | Caps key | Effort | Owner | Deadline / gate | Tier |
|---|---|---|---|---|---|---|---|---|---|
| **E1** | QR badge scanning | LEAD-01, DOOR-04, SHIRT-02, MASK-04 | `ManualEntryScanner` (typed, pasted or HID-wedge `code:validator`) | `flet-barcode-scanner` on `mobile_scanner` 7.4.2 | `scanner` | M, 35 h | U | v0.1 on device 01-10; PyPI 0.2 by 02-19; G2 01-31; G-Staff 02-26 | T1 |
| **E2** | FCM push (+ optional analytics) | NOTIF-01, 04, 06, 07, 08, 09, 11; NATIVE-04, 05, 06 | `BannerPoller` (app-config `banners[]`), PSF email/Discord | `flet-firebase` on `firebase_core` 4.15.0 + `firebase_messaging` 16.7.0 (+ `firebase_analytics` 12.6.0 only if OD-3, in the separate `flet-firebase-analytics` wheel, D-111) | `push`, `analytics` | L, 50 h | U | spike S8 by 11-30; **G3 02-12**; release by 03-05, else 27.1 | T3 |
| **E3** | OS-scheduled reminders | NOTIF-05, NOTIF-07, DEV-06, NATIVE-06 | in-app reminder banners + `.ics` with `VALARM` | `zoned_schedule`/`cancel` added to the official flet-dev/flet#6948 package (`flutter_local_notifications` 22.3.1 + `timezone` 0.11.1) | `local_notifications` | M, 40 h (+U7 6 h) | FT (v1), U (scheduling) | #6948 v1 merged and released by 01-15 (UNCONFIRMED, FT); **G3 02-12**; scheduling in the Flet 1.1.x point release by 02-26; else 27.1 | T3 |
| **E4** | Native add-to-calendar | SESS-04 | `.ics` via `ft.Share.share_files` (SESS-05) | `flet-add-to-calendar` on `add_2_calendar` 3.1.1 | `calendar` | S, 20 h (+U6 6 h) | CC/U | **G3 02-12**; 03-05 or 27.1 | T3 |
| **E5** | HTML rendering | INFO-05, DATA-23, DATA-25, SESS-06, MAP-09 | `core/html_md.py` → `ft.Markdown(on_tap_link)` | `flet-html` on `flutter_widget_from_html_core` (0.17.4 today) | `html` | M | CC | 27.1 sprint (05-17/18, UNCONFIRMED) | post |
| **E6** | Revealed swipe buttons | SCHED-11 | `ft.Dismissible` + `await confirm_dismiss(False)` + long press + star | `flet-slidable` on `flutter_slidable` (4.0.3 today) | `slidable` | S | CC | 27.1 sprint | post |
| **U1** | Pull-to-refresh | SCHED-13, SCHED-26, EVT-07, SPON-08, LEAD-13 | AppBar refresh `IconButton` + `ProgressBar` (D-67) | `ft.RefreshIndicator` | `refresh_indicator` | S, 8 h | U | merged 01-15 | T0 upgrade |
| **U2** | Sticky slot headers | SCHED-02 | non-sticky dividers (D-71) | `ft.GroupedListView` + `ft.ListGroup` | `sticky_headers` | M | FT/CC | 27.1 | post |
| **U3** | Animated booth zoom | EXPO-05 | `reset()` → `zoom(6)` → `pan(dx,dy)` on an `InteractiveViewer(max_scale=8)` (default 2.5 clamps) | `InteractiveViewer.set_transform()` / `zoom_to_rect()` | `iv_set_transform` | S, 10 h | U | 02-12 | T2 |
| **U4** | App version at runtime | INFO-03 | CI-written `build_info.py` | `page.get_app_info()` → `ft.AppInfo` | `app_info` | S, 4 h | U | merged 01-15 | T0 upgrade |
| **U5** | iOS entitlements | NOTIF-04, NATIVE-04, NATIVE-07 | push off; autofill by OS heuristics | `[tool.flet.ios.entitlement]` + `--ios-entitlements` | config | S, 8 h | U | merged 01-31; released by 02-26 | gates E2 |
| **U6** | Android `<queries>` | SESS-04, INFO-14 | never call `can_launch_url`; `.ics` | `[tool.flet.android.queries]` | config | S, 6 h | U | 01-31, only if E4 pursued | gates E4 |
| **U7** | Core library desugaring | NOTIF-05 | E3 interim | `[tool.flet.android] core_library_desugaring = true` | config | S, 6 h | U | 01-31, only if E3 pursued | gates E3 |
| **U8** | Resource meta-data | NATIVE-07 | autofill heuristics | inline-table `[tool.flet.android.meta_data]` + `[tool.flet.android.string_resources]` (part 2 added by D-112) | config | S, 5 h (D-112) | U | 01-31, only for the autofill upgrade | T3 |
| **U9** | Query-string hook | ROOM-03, SPON-04 | `use_query()` parses `page.route` (D-37) | `ft.use_route_search()` | helper probe | XS | U | 02-12 | T2 |
| **U10** | `AppBar.bottom` | SCHED-01 | day selector as first row of `View.controls` | `AppBar.bottom` + `bottom_height` | - | S | CC (PyCon sprint candidate, U reviews) | post-conference | post |
| **U11** | Offline PWA | NATIVE-09 | online-only PWA (D-93) | Flet-generated service worker | - | M | FT | post-conference | post |
| **U12** | iOS deployment target | NATIVE-02 | iOS 15 floor (template) | `[tool.flet.ios] deployment_target` | build | S | U | 12-15, **only if** spike S10 finds a pod needing > iOS 15 | conditional |
| **U13** | App privacy manifest | (store; R9) | none needed unless ITMS-91053 | template `ios/Runner/PrivacyInfo.xcprivacy` | build | S | U | 12-15, **only if** spike S5 reports ITMS-91053 | conditional |
| **U14** | Verified App Links | (deep links, D-38) | custom scheme `pyconus://app` | `[tool.flet.android.deep_linking] auto_verify`, multiple hosts | - | S | U (reuses U5's entitlement plumbing) | post-conference | post |
| **U15** | Non-fatal handler errors | (cross-cutting; PLAN §5.8, D-85) | `@safe` on every handler and effect | `ft.set_error_handler()` + `fatal_errors` option | helper probe | S | U | 02-12 | T2 |

**Release vehicles.**
- E1, E2 and E4 (and E5/E6) are standalone PyPI wheels (§2.6). E3 ships inside the flet-dev/flet monorepo with a Flet release, at Flet's version (PLAN §6.1, D-20): the scheduling PR rides the 1.1.x point release by 02-26, or a 1.2 released before the 03-05 pin.
- U5-U8 ship in a **1.1.x point release by 02-26** (D-22, OD-19).
- U1, U3, U4, U9 and U15 target the same point release. If FT policy puts new core API in 1.2 instead, they light up only if 1.2 is released before the **03-05** pin (D-21); otherwise their interim ships. No 27.0 feature needs them.
- U2, U10, U11 and U14 are 27.1 or later.

**Probe vs config vs build.**
- Probe items light up through `Caps`.
- Config items (U5-U8) need no app code: they are `pyproject` tables added in the release that ships the dependent feature (D-89).
- Build items (U12, U13) change the template and are invisible to the app.

---

## 2. Rules common to every extension (E1-E6)

### 2.1 Compatibility policy (D-20, D-23)

| Rule | Value |
|---|---|
| Home | Standalone Apache-2.0 repos in the `flet-dev` org: `flet-dev/flet-barcode-scanner`, `flet-dev/flet-firebase`, `flet-dev/flet-add-to-calendar` (E5/E6 likewise, at the sprint). E3 lives where #6948 lives (§4). Moving into the monorepo is a post-conference option (OD-14), using the integration checklist in `.agents/skills/implement-flet-extension/SKILL.md`. |
| Python | `requires-python = ">=3.10"`, `dependencies = ["flet>=1.1.0,<2"]`; independent `0.x` versions; pure `py3-none-any` wheel carrying the Dart package as package data |
| Dart | `flet: ^1.1.0`, `flutter: ">=3.47.0"`, `sdk: '>=3.3.0 <4.0.0'` (from the `flet create --template extension` scaffold). The wrapped package is pinned **exactly** (`mobile_scanner: 7.4.2`, not `^7.4.2`) |
| UI imports | `package:flutter/widgets.dart`, plus `package:material_ui/material_ui.dart` / `package:cupertino_ui/cupertino_ui.dart` where needed, with `material_ui: ^1.6.0` (same constraint as `packages/flet/pubspec.yaml`). **Never** `package:flutter/material.dart` or `cupertino.dart` |
| CI | Every PR: build and test against the newest released Flet 1.1.x. Nightly: build against `flet@main`, with `[tool.flet.flutter.pubspec.dependency_overrides] flet = { git = ... }` in the example app ("Prerelease compatibility" in `website/docs/publish/index.md`) |
| App side | Exact pin in `[tool.flet.android].dependencies` / `[tool.flet.ios].dependencies` only (D-89). Never `[project].dependencies`, because the web build and `flet run` must not see them. No editable `[tool.uv.sources]` in release builds |
| Spike | **S7** (M0, by 11-13): a standalone wheel builds and registers through `[tool.flet.<platform>].dependencies`, and `mobile_scanner` renders under the material_ui gate |

How the build picks an extension up: `flet build` installs the platform dependencies into site-packages and finds every `flutter/<dart_pkg>/pubspec.yaml`. It adds each one as a path dependency (`CLI/build_base.py` "Registering Flutter user extensions") and generates the `Extension()` registration. No `pubspec` editing is needed in the app.

### 2.2 Python patterns (from `flet-geolocator`, `flet-permission-handler`, `flet-secure-storage`, `flet-camera`)

| Element | Pattern (exists) |
|---|---|
| Non-visual | `@ft.control("Name") class Name(ft.Service)`. Construction registers the service with the current page (`Service._auto_register = True`). Set client props and handlers in `init()`; `self.page` is not attached yet inside `init()` |
| Visual | `@ft.control("Name") class Name(ft.LayoutControl)`; Dart wraps the widget in `LayoutControl(control:, child:)` |
| Props | dataclass fields with defaults. Value types use `@ft.value`. Enums are `Enum` with the **Dart enum `.name` as value** (`QR_CODE = "qrCode"`) so Dart can `parseEnum(...)` |
| Events | `on_<name>: Optional[ft.EventHandler[XEvent]] = None`, where `@dataclass class XEvent(ft.Event["Name"])` adds payload fields. Dart calls `control.triggerEvent("<name>", {...})`, and `BaseControl._trigger_event` builds `XEvent` from the dict (`from_dict(XEvent, {control, name, **payload})`). **Never name a payload field `data`, `name` or `control`**: they are base `ft.Event` fields, and redeclaring `data` (a kw-only default on the base) raises `TypeError` at class definition |
| Methods | `async def m(self, ...) -> T: return await self._invoke_method("m", {...}, timeout=...)`. Always coroutines: callers must be `async def` (decisions §N.1) |
| Platform guard | `if self.page.web: raise ft.FletUnsupportedPlatformException(...)` (the geolocator pattern), or a `before_update()` check (the permission_handler pattern) |
| Packaging | Standalone extensions (E1, E2, E4-E6; the `flet create --template extension` form): `[tool.setuptools.package-data] "flutter.<dart_pkg>" = ["**/*"]`. Monorepo first-party extensions (E3's #6948 package) use `["pubspec.yaml", "lib/**"]` (`flet-geolocator`, `flet-camera`), so an `android/` dir does not reach their wheel unless `"android/**"` is added (§E3) |

### 2.3 Dart patterns

```dart
// lib/<pkg>.dart
library flet_barcode_scanner;
export "src/extension.dart" show Extension;

// lib/src/extension.dart
class Extension extends FletExtension {
  @override
  Widget? createWidget(Key? key, Control control) =>            // visual (E1, E5, E6)
      control.type == "BarcodeScanner" ? BarcodeScannerControl(key: key, control: control) : null;
  @override
  FletService? createService(Control control) =>                 // services (E2-E4)
      control.type == "AddToCalendar" ? AddToCalendarService(control: control) : null;
}
```

- Services extend `FletService`. They register `control.addInvokeMethodListener(_invoke)` in `init()`, (re)subscribe streams in `update()` only when `control.hasEventHandler("x")`, and cancel everything in `dispose()` (the `GeolocatorService` pattern).
- Widgets are `StatefulWidget`s. They own the controller in `initState`, react in `didUpdateWidget`, and remove the listener in `dispose` (the `CameraControl` pattern).
- **Default value matching (critical).** Every `control.getX("prop", default)` repeats the Python default, because defaults are not sent over the wire.
- Throw a small exception class from `_invoke` to surface errors to Python (the `_GeolocatorException` pattern).

### 2.4 The material_ui gate test (SKILL.md §"Third-party Dependency Gate")

This test is required for every **visual** extension (E1, E5, E6). Services (E2-E4) build no widgets, so for them it is moot.
1. **Static.** A CI step fails if `lib/` contains `package:flutter/material.dart` or `cupertino.dart`. A reviewed allowlist names the upstream widgets we instantiate.
2. **Runtime.** An integration test renders the control inside a plain Flet page on the iOS simulator and the Android emulator, in every state reachable without hardware: placeholder, error ("no camera" on the simulator), `paused=True`. It asserts there is no `No Material widget found` / `FlutterError` in the log, and takes a golden of the error state.
3. **Upgrade guard.** A test asserts the resolved upstream version equals the pin (`pubspec.lock`), so a transitive bump cannot slip in.

### 2.5 Integration-test plan (shared shape)

| Layer | Where | How |
|---|---|---|
| Python unit | `tests/` in the extension repo | Construct the control or service; check default serialisation; mock `_invoke_method`; check enum round-trips |
| Integration (emulator/simulator) | `examples/<pkg>_example/` + `tests/` | `flet test android --device-id <emu>` / `flet test ios --device-id <sim>` (**exists**: `CLI/test.py` provisions a test host with the extension registered and drives `flet.testing.FletTestApp`). Covers the gate test (§2.4), method calls, event delivery and permission-denied paths |
| Device (manual, scripted) | checklist in the repo | Real camera, push, alarms and calendar UI on the PLAN §8.1 device lab before each extension release |
| App side | `pycon-us` `tests/fallback` | The fallback-parity suite runs each capability faked on and off (D-97). The extension itself is never imported in app tests |

### 2.6 Release process (standalone E items: E1, E2, E4, E5, E6)

E3 is excluded: the #6948 package lives in the monorepo, is released with Flet and versioned with it (official extensions are at 1.0.4, the same version as `flet`), and the app pins it to the same version as `flet` (D-20).

1. The version lives in `pyproject.toml` and `pubspec.yaml` (kept equal); a `CHANGELOG.md` entry per release.
2. Tag `vX.Y.Z` → GitHub Actions: lint, unit, `flet test` on the Android emulator, then build the wheel and sdist and publish with **PyPI trusted publishing** (OIDC; no token in the repo).
3. Version line: `0.1.0` (first device build) → `0.2.0` (first PyPI release the app pins) → `0.x` fixes → `1.0.0` after the conference (M7, "extensions to 1.0").
4. The app bumps the exact pin only on or before **03-05** (D-18). After that, only a P0 fix moves a pin, through the hotfix lane.
5. Docs: `README.md` plus the template's `docs/` (mkdocs) in the repo. Flet website pages come with the monorepo move.

### 2.7 Clean-room statement (D-27, D-102)

- All extensions are written from the wrapped packages' public pub.dev documentation and API, and from Flet's own first-party extensions.
- The GPL-3.0 `AyberkA0/flet-barcode-scanner` is **never opened** by anyone writing E1. PR descriptions say so, and reviewers check it.
- Permissive third-party wrappers (e.g. MIT `flet-android-notifications`, `Nwokike/flet-notifications`) may be read for API ideas. No code is copied.
- Licence: Apache-2.0, with DCO sign-off. All wrapped packages are permissive: `mobile_scanner` BSD-3, FlutterFire BSD-3, `flutter_local_notifications` BSD-3, `timezone` BSD-2, `add_2_calendar` MIT, `flutter_widget_from_html_core` MIT, `flutter_slidable` MIT. Re-check each at bump time.

---

## 3. `Caps`: keys, probes and the upgrade path (D-74, D-75, PLAN [§5.7](../PLAN.md#57-platform-and-capability-abstraction))

A capability is **on** only when both (a) `build_info.CAPS` lists it, and (b) the runtime probe succeeds. `tools/caps_manifest.py` writes (a) in CI from the dependencies actually bundled for the target platform, plus the core probes evaluated in the build venv (pinned Flet). `flet run` and the companion app get an empty manifest. Remote `features.*` in app-config can only veto.

| Key | Manifest source | Runtime probe (exact name) | Provider when on / off |
|---|---|---|---|
| `scanner` | `flet-barcode-scanner` | `flet_barcode_scanner.BarcodeScanner.toggle_torch` | `MobileScanner` / `ManualEntryScanner` (`SimulatedScanner` in DEMO) |
| `push` | `flet-firebase` | `flet_firebase.FirebaseMessaging.subscribe_to_topic` | `FirebasePush` / `BannerPoller` |
| `analytics` | `flet-firebase-analytics` (only if OD-3; D-111) | `flet_firebase_analytics.FirebaseAnalytics.log_event` | `FirebaseAnalytics` / `NullAnalytics` |
| `local_notifications` | `flet-notifications` (OD-15) | `flet_notifications.LocalNotifications.zoned_schedule` | `ScheduledReminders` / `InAppReminders` + `IcsReminderPack` |
| `calendar` | `flet-add-to-calendar` | `flet_add_to_calendar.AddToCalendar.add_event` | `NativeCalendar` / `IcsShare` |
| `html` | `flet-html` | `flet_html.Html` | `Html` / `ft.Markdown` over `html_md` |
| `slidable` | `flet-slidable` | `flet_slidable.Slidable` | `Slidable` row / `Dismissible` row |
| `refresh_indicator` | core probe at build | `ft.RefreshIndicator` | `Refreshable` returns it / button + `ProgressBar` |
| `app_info` | core probe at build | `ft.Page.get_app_info` | `PageAppInfo` / `BuildInfoAppInfo` |
| `iv_set_transform` | core probe at build | `ft.InteractiveViewer.set_transform` | animated zoom / reset→zoom→pan |
| `sticky_headers` | core probe at build | `ft.GroupedListView` | sticky groups / dividers |

U9 and U15 have no `Caps` key (D-74 does not list them). Their helpers probe once at import: `use_query()` uses `ft.use_route_search` when `hasattr(ft, "use_route_search")`, and `services/safe.py` registers `ft.set_error_handler` when present. Both are pure-Python, so the manifest adds nothing.

Probes import extensions lazily inside `platform/caps.py` (`importlib.util.find_spec` and then `getattr`). **Screens never import an extension** (D-74).

```python
# src/pycon_us/platform/caps.py (sketch; the `Caps` holder itself is an @ft.observable class per D-74, not shown)
import importlib
import importlib.util

PROBES = {
    "scanner": ("flet_barcode_scanner", "BarcodeScanner.toggle_torch"),
    "refresh_indicator": ("flet", "RefreshIndicator"),
    # ... one row per key in the table above
}
def probe(module: str, attr: str) -> bool:
    if importlib.util.find_spec(module) is None:
        return False
    obj = importlib.import_module(module)
    for part in attr.split("."):
        obj = getattr(obj, part, None)
        if obj is None:
            return False
    return True
```

**Upgrade procedure (identical for every E/U probe item; PLAN §6.2).**
1. The upstream release ships (a PyPI wheel, or a Flet point release).
2. Bump the exact pin in `pyproject.toml` (by **03-05**).
3. For E items, add the dist to `[tool.flet.android].dependencies` and `[tool.flet.ios].dependencies`, plus the item's platform setup (each section's "App upgrade" row).
4. CI writes the manifest; `Caps` lights the key. The "all on" fallback-parity suite already covers the path, so no screen code changes.
5. The release notes print `python -m pycon_us.platform.caps`.

---

## 4. Extensions

### E1 `flet-barcode-scanner` (T1; the largest interim)

| Field | Value |
|---|---|
| Serves | LEAD-01 (shared scanner surface), DOOR-04, SHIRT-02, MASK-04; PLAN §4.2 "Badge scanning" |
| Interim | `ManualEntryScanner`: one `TextField` (autofocus, `on_submit`) that accepts the **full `code:validator` payload**, typed, pasted, or typed by a USB/BT HID wedge scanner, and passes it to `core.badges.parse_badge` (D-80, D-81). DEMO uses `SimulatedScanner` (D-84). Fallback hardware: 4 HID scanners (~$30 each) if E1 fails at G2 |
| Dart package | **`mobile_scanner` 7.4.2** (exact; BSD-3; published 2026-09-14; Dart `^3.7.0`, Flutter `>=3.29.0`; checked 2026-10-11). Android: CameraX + ML Kit; iOS: Apple Vision/AVFoundation |
| Kind | `LayoutControl` (camera preview) with async methods |
| Effort / owner | M, 35 h / U |
| Deadlines | Spike S7 (M0) → v0.1 on device **01-10** → reads real 2026 badges at **G2 01-31** → PyPI **0.2 by 02-19** → Badge Day 1 **02-24** (>= 95 % first-try decode, G-Staff 02-26) → Badge Day 2 04-09 (criterion S4: >= 98 %). Released on PyPI before 03-05 (criterion S10) |
| Caps | `scanner`; kill switch `features.lead_retrieval/door_check/swag/coc` vetoes per tool (D-83) |

**Python API** (proposed, E1; D-25 names):

```python
class BarcodeFormat(Enum):          # values = mobile_scanner BarcodeFormat.name
    QR_CODE = "qrCode"; ALL = "all"  # (+ others later; QR only in 0.x)
class CameraFacing(Enum):
    BACK = "back"; FRONT = "front"

@dataclass
class BarcodeDetectEvent(ft.Event["BarcodeScanner"]):
    format: BarcodeFormat
    raw_value: Optional[str] = None  # first barcode in the capture; default so a payload omitting a null key still deserialises
    barcodes: list[dict] = field(default_factory=list)   # every barcode: raw_value, format, corners

@ft.control("BarcodeScanner")
class BarcodeScanner(ft.LayoutControl):
    formats: list[BarcodeFormat] = field(default_factory=lambda: [BarcodeFormat.QR_CODE])
    facing: CameraFacing = CameraFacing.BACK
    paused: bool = False             # True stops analysis and releases the camera
    detection_timeout: ft.DurationValue = field(default_factory=lambda: ft.Duration(milliseconds=250))
    fit: ft.BoxFit = ft.BoxFit.COVER
    on_detect: Optional[ft.EventHandler[BarcodeDetectEvent]] = None
    on_error: Optional[ft.ControlEventHandler["BarcodeScanner"]] = None   # e.data = message

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def toggle_torch(self) -> None: ...
    async def analyze_image(self, path: str) -> list[dict]: ...   # CI decode tests; verify 7.4.2 signature
```

**Dart side.**
- `BarcodeScannerControl` creates `MobileScannerController(formats:, facing:, detectionSpeed: DetectionSpeed.normal, detectionTimeoutMs:, autoStart: !paused)` in `initState`. `didUpdateWidget` maps `paused` to `stop()`/`start()`.
- `onDetect: (capture) => control.triggerEvent("detect", {...})`. Methods go through `addInvokeMethodListener`.
- Pass our own `errorBuilder` and `placeholderBuilder`, built from `widgets.dart`, so no SDK-Material text styling leaks in (gate §2.4).
- `useAppLifecycleState` stays on: the camera is released on background.

**Platform setup.**

| Platform | Entry | How (exists today) |
|---|---|---|
| both | camera permission + usage string | `[tool.flet] permissions = ["camera"]` emits `NSCameraUsageDescription` + `android.permission.CAMERA`. Override the iOS string in `[tool.flet.ios.info]` with staff-scanning wording (review 5.1.1, D-89) |
| both | runtime prompt | `status = await ph.request(fph.Permission.CAMERA)` (with `ph = fph.PermissionHandler()`); if `status == fph.PermissionStatus.PERMANENTLY_DENIED`: `await ph.open_app_settings()` (coroutines; the caller must be `async def`) (NOTIF-10 hint component, shared with LEAD-02) |
| both | keep awake while scanning | `ft.Wakelock().enable()` / `disable()` (coroutines) |
| Android | ML Kit model | **Keep the bundled model** (the default). It works offline on first launch, which matters on conference Wi-Fi. Cost: +3-10 MB, inside the 40 MB budget (criterion S6); spike S7 measures it (AAB size with and without `flet-barcode-scanner`). The unbundled variant is now settable without a fork via `[tool.flet.android.gradle_properties] "dev.steenbakker.mobile_scanner.useUnbundled" = "true"` (exists; research said otherwise), but it downloads the model through Play Services on first use, so we don't use it |
| iOS | min version | spike S10 confirms the pod minimum is <= 15 (else U12) |

**Tests.**
- The gate test (§2.4).
- `analyze_image` on bundled PNGs of the 2026 sample badges (P3), on the emulator and simulator. Asserts the exact `raw_value` and that `parse_badge` round-trips.
- Pause/resume 50× without a camera leak (Android logcat `CameraX` errors = fail).
- Torch toggles twice.
- Permission denied → `on_error` fires and nothing crashes.
- A manual device script on the PLAN §8.1 lab: low light, glossy badges, 3 s per-code CoC cooldown (D-82, the app's responsibility).

**App upgrade.**
1. Add `flet-barcode-scanner==0.2.x` to both platform dependency lists (PLAN §9.1: "E1 is always there" from the first build that has it; D-89 for the dependency-list rule).
2. `MobileScanner` implements `BadgeScanner` and owns `paused` per tool cadence: lead re-arms after 500 ms, door after 250 ms, swag pauses until its modal closes, CoC has a 3 s per-code cooldown (D-82).
3. The header and footer stay tappable over the preview (LEAD-01 gotcha). Manual entry remains reachable from every scanner screen.

**Risks.**
- An upstream minor could add a Material widget. Mitigations: the exact pin plus gate test.
- Focus and low light. Mitigations: tap-to-focus is upstream default; the HID fallback stays.
- Size (spike S7; criterion S6 at G5).

---

### E2 `flet-firebase` (+ `flet-firebase-analytics`) (T3, gated at G3)

| Field | Value |
|---|---|
| Serves | NOTIF-04 (topics), NOTIF-06 (prompt + token), NOTIF-07 (shared `PermissionGate`), NOTIF-08 (foreground `on_message` → `TopToast`), NOTIF-11 (token card), NOTIF-01 (toggles drive topics), NOTIF-09 + NATIVE-05 (analytics, only if OD-3), NATIVE-04 (wiring), NATIVE-06 (permissions) |
| Interim | `BannerPoller`: app-config `banners[]` fetched on start, on resume and every 5 min, filtered by category toggles; emergency banners always shown in-app (OD-18). Plus PSF email/Discord for emergencies (PLAN §4.2) |
| Dart packages | **`firebase_core` 4.15.0**, **`firebase_messaging` 16.7.0** (needs `firebase_core ^4.14.0`; Dart `^3.6.0`, Flutter `>=3.27.0`). **`firebase_analytics` 12.6.0** only if OD-3 (D-111: a separate wheel **`flet-firebase-analytics`**, superseding the analytics part of D-24). All published 2026-09-14, BSD-3, checked 2026-10-11 |
| Kind | Services only (no widgets; gate moot) |
| Effort / owner | L, 50 h / U |
| Deadlines | **Spike S8** (Dart-only `Firebase.initializeApp(options)` on Android and iOS, topic round-trip) verdict by **11-30**; P5 (Firebase app configs, APNs key, `test-*` topic) by **01-31**; **U5 merged by 01-31**; **G3 02-12**: topic round-trip on both OSes with the PSF config and U5 merged; released by **03-05**, else 27.1 (06-30) |
| Caps | `push`, `analytics` |

**Why analytics is a separate wheel.** One wheel has one fixed `pubspec.yaml`, so `firebase_analytics` cannot be optional inside `flet-firebase`. Bundling it unconditionally would link the Analytics SDK into 27.0. That contradicts D-79 ("No analytics SDK in 27.0") and NATIVE-05, and changes the Data Safety form. So `FirebaseAnalytics` ships (D-111) as `flet_firebase_analytics.FirebaseAnalytics` in the same repo, and the app bundles it only after an OD-3 "yes". The §3 probe row uses these names. (D-24/D-25 listed `firebase_analytics`/`FirebaseAnalytics` under E2 `flet-firebase`; D-111 supersedes that analytics part. Only the dist and module change; class and method names stay as D-25.)

**Python API** (proposed, E2):

```python
@ft.value
class FirebaseOptions:            # values from the PSF Firebase console (P5); not secrets
    api_key: str; app_id: str; messaging_sender_id: str; project_id: str
    ios_bundle_id: Optional[str] = None; storage_bucket: Optional[str] = None

@ft.control("FirebaseApp")
class FirebaseApp(ft.Service):
    options: Optional[FirebaseOptions] = None        # per-platform options picked by the app
    async def initialize(self) -> None: ...          # Dart: Firebase.initializeApp(options: ...)

@dataclass
class RemoteMessageEvent(ft.Event["FirebaseMessaging"]):
    message_id: Optional[str] = None; title: Optional[str] = None; body: Optional[str] = None
    payload: dict[str, str] = field(default_factory=dict); from_topic: Optional[str] = None
    # Dart sends {"payload": message.data, ...}; never `data` (§2.2). Defaults are required: `_trigger_event` builds the
    # event with from_dict(), so an Optional field without a default is still required and a data-only message
    # (no title/body key) would raise TypeError in dispatch

class AuthorizationStatus(Enum):
    AUTHORIZED = "authorized"; DENIED = "denied"; NOT_DETERMINED = "notDetermined"; PROVISIONAL = "provisional"

@ft.control("FirebaseMessaging")
class FirebaseMessaging(ft.Service):
    on_message: Optional[ft.EventHandler[RemoteMessageEvent]] = None              # foreground only
    on_message_opened_app: Optional[ft.EventHandler[RemoteMessageEvent]] = None
    on_token_refresh: Optional[ft.ControlEventHandler["FirebaseMessaging"]] = None   # e.data = token
    async def request_permission(self, alert=True, badge=True, sound=True, provisional=False) -> AuthorizationStatus: ...
    async def get_token(self) -> Optional[str]: ...
    async def subscribe_to_topic(self, topic: str) -> None: ...
    async def unsubscribe_from_topic(self, topic: str) -> None: ...
    async def get_initial_message(self) -> Optional[dict]: ...   # tap that cold-started the app

# lives in flet_firebase_analytics (separate wheel, D-111), not in flet_firebase
@ft.control("FirebaseAnalytics")
class FirebaseAnalytics(ft.Service):
    async def log_event(self, name: str, parameters: Optional[dict] = None) -> None: ...
    async def set_user_property(self, name: str, value: Optional[str]) -> None: ...
    async def set_analytics_collection_enabled(self, enabled: bool) -> None: ...
```

**Design constraints.**
- **Initialisation is Dart-only, with no `google-services.json` or `GoogleService-Info.plist`** (D-24; there is no flet build hook for them).
- `FirebaseApp.initialize()` must complete before any messaging call. The Dart services queue calls until `Firebase.apps` is non-empty.
- **Background messages run no Python.** The four topics carry *notification* payloads that the OS displays. Taps surface through `get_initial_message()` (cold start) and `on_message_opened_app` (warm) once Python is up.
- `getToken`/`onTokenRefresh` are kept for D-25 parity. If 16.7.0 marks them deprecated, the Dart side maps them to the replacement API without changing Python names.
- Topic names are exact: `announcements`, `schedule-changes`, `emergency`, `daily-digest`, in project `pycon-us-2023-mobile` (D-76). They are re-asserted on start and on every toggle change.
- Prompt timing (D-78): end of Welcome or first visit to Notifications. Never at boot, never on web. Permission goes through `request_permission()`, never `flet_permission_handler` (it has no iOS notification macro; decisions §N.11).

**Platform setup** (only in the release that ships E2; D-89):

| Platform | Entry | How |
|---|---|---|
| iOS | `aps-environment` entitlement | **U5** `[tool.flet.ios.entitlement] "aps-environment" = "production"`. Also needs the Push capability on App ID `org.pycon.us.2023.onsite` and a profile that includes it (PSF, P4/P5) |
| iOS | background mode | `[tool.flet.ios.info] UIBackgroundModes = ["remote-notification"]` (exists) |
| iOS | APNs key | uploaded to Firebase by the PSF (P5) |
| Android | `POST_NOTIFICATIONS` (API 33+) | `[tool.flet.android.permission] "android.permission.POST_NOTIFICATIONS" = true` (exists) |
| Android | default channel | none (Ionic parity, NATIVE-04: no default channel). FCM uses its own fallback channel; a `default_notification_channel_id` meta-data would have no effect because no E2/E3 v1 API creates the channel |
| Android | small icon | none: FCM falls back to the launcher icon. A monochrome `@drawable` needs an app resource the template cannot add, so it waits for 27.1 (U8 covers strings, not drawables) |
| Analytics (if OD-3) | ad-id off | `[tool.flet.android.meta_data] "google_analytics_adid_collection_enabled" = "false"`; `AD_ID` stays removed (`[tool.flet.android.permission] "com.google.android.gms.permission.AD_ID" = false`) |

**Tests.**
- Integration: `initialize` with the staging options; `subscribe_to_topic("test-<run>")`; a CI job sends to that topic via the FCM HTTP v1 API (service account held as a PSF secret in the nightly environment only) and asserts `on_message` in the foreground.
- Manual device script: background display, tap → `on_message_opened_app`, cold-start tap → `get_initial_message`, permission denied path (NOTIF-07: never re-prompt), token rotation.
- Fallback parity: `push` off, so banners still deliver every category.

**App upgrade.**
1. Add `flet-firebase==0.x` to the platform lists, plus the setup rows above.
2. `FirebasePush` replaces `BannerPoller` as the `PushService`. `BannerPoller` keeps running for in-app emergency banners (OD-18).
3. The Developer Info FCM token card appears (NOTIF-11, `caps.push`).

---

### E3 Scheduled reminders in the official #6948 package (T3, gated at G3)

| Field | Value |
|---|---|
| Serves | NOTIF-05 (fixed reminders, ids 8000+ from app-content), NOTIF-07 (shared `PermissionGate`), DEV-06 (test notification, id 8999), NATIVE-06 |
| Interim | `InAppReminders`: time-windowed in-app banners from `app-content.reminders[]`. Plus `IcsReminderPack`: "Add reminders to calendar" as an `.ics` with `VALARM`, best effort (D-77) |
| Dart packages | **`flutter_local_notifications` 22.3.1** (published 2026-09-13; needs `timezone ^0.11.0`, Dart `^3.10.0`, Flutter `>=3.38.1`, AGP >= 8.11.1, compileSdk >= 35) + **`timezone` 0.11.1** (2026-06-29). **No `flutter_timezone`**: the IANA zone comes from `settings.CONF_TZ` (D-24) |
| Package | PyPI **`flet-notifications`** (OD-15; PyPI 404 = free, re-checked 2026-10-11), import `flet_notifications` |
| Effort / owner | M, 40 h for scheduling (U) + U7 6 h; #6948 v1 is FT-owned |
| Deadlines | #6948 v1 merged and released by **01-15** (UNCONFIRMED, FT); scheduling PR + U7 merged by **G3 02-12**; released with the Flet 1.1.x point release by **02-26** (or a 1.2 released before **03-05**), else 27.1 |
| Caps | `local_notifications` |

**Coordination with flet-dev/flet#6948.**
- **Status.** The issue "New extension: flet-local-notifications (flutter_local_notifications)" was opened by Feodor Fitsner on 2026-10-10. v1 scope: Android, iOS, macOS, Windows, Linux and web; `show`, `cancel`, permission, `on_notification_tap`. **Scheduled and periodic notifications are explicitly out of v1.**
- **Ownership split.** FT owns v1. U contributes one follow-up PR, "scheduling", on top of v1. U does not fork it and does not ship a competing package. If v1 is not merged by 01-15, E3 goes to 27.1 (D-29); U does not take over v1 under deadline pressure.
- **PyPI name clash (OD-15).** `flet-local-notifications` on PyPI belongs to an unrelated project (1.2.2, 2026-07-11, pins `flet==0.28.3`). Proposal to the #6948 owner: publish as **`flet-notifications`**, still free on PyPI. A GitHub repo `Nwokike/flet-notifications` (MIT) uses the same name but is not on PyPI; mention it in the README to avoid confusion. A PEP 541 claim on the taken name is optional and not on the critical path.
- **Class name.** D-25 fixes `LocalNotifications`. If v1 names it differently, amend D-25 (decisions-record rule) and change one probe row in `platform/caps.py`.
- **Prior art.** U's own `ndonkoHenri/notifications` branch (March 2025) is a pre-1.0 `awesome_notifications` prototype in `flet/core`. It is not a base for this work.

**Python API added by the scheduling PR** (proposed, E3; D-25):

```python
class ScheduleMode(Enum):          # Dart AndroidScheduleMode.name
    EXACT_ALLOW_WHILE_IDLE = "exactAllowWhileIdle"
    INEXACT_ALLOW_WHILE_IDLE = "inexactAllowWhileIdle"

# added to the v1 service class
class LocalNotifications(ft.Service):
    async def zoned_schedule(self, id: int, title: str, body: str, at: datetime, tz: str,
                             mode: ScheduleMode = ScheduleMode.EXACT_ALLOW_WHILE_IDLE,
                             payload: Optional[str] = None) -> None: ...
    async def cancel(self, ids: int | list[int]) -> None: ...     # extends v1 cancel(id)
    async def can_schedule_exact(self) -> bool: ...               # Android 12+; True elsewhere
    async def request_permission(self) -> bool: ...               # v1; listed for completeness
    async def get_pending_ids(self) -> list[int]: ...             # tests + Developer Info
```

**Semantics.**
- `at` must be timezone-aware. Python sends `at.astimezone(ZoneInfo(tz)).isoformat()` plus `tz`. Dart calls `tz.initializeTimeZones()` once, then `TZDateTime.from(DateTime.parse(iso), tz.getLocation(tz))`, so the instant is exact and DST-correct.
- Ids are 32-bit ints: the app uses 8000-80xx for reminders and 8999 for DEV-06.
- App algorithm (D-77): cancel 8000-80xx, then schedule every enabled future reminder; past instants are skipped. If `can_schedule_exact()` is False (Android 14+ denies `SCHEDULE_EXACT_ALARM` by default), use `INEXACT_ALLOW_WHILE_IDLE`.

**Platform setup.**

| Platform | Entry | How |
|---|---|---|
| Android | desugaring | **U7** `[tool.flet.android] core_library_desugaring = true` (`isCoreLibraryDesugaringEnabled` + `desugar_jdk_libs:2.1.4` in `:app`). The template has Java 17 already |
| Android | **receivers** | `ScheduledNotificationReceiver` and `ScheduledNotificationBootReceiver` (`exported="false"`; the boot receiver with `BOOT_COMPLETED`, `MY_PACKAGE_REPLACED`, `QUICKBOOT_POWERON`) plus `RECEIVE_BOOT_COMPLETED`. The plugin's own manifest declares only `VIBRATE` and `POST_NOTIFICATIONS` (verified 2026-10-11), and the template has no `<receiver>` hook. **Resolution:** the #6948 Dart package ships an `android/` module whose library `AndroidManifest.xml` declares both receivers and the permission, and Gradle's manifest merger adds them to the app with no CLI change. Two requirements: (1) the package's `pubspec.yaml` must declare `flutter: plugin: platforms: android: package: <java.package>` (`pluginClass` may be omitted), because flutter_tools registers only packages with a `flutter: plugin:` key (`flutter_plugins.dart`), and Flet extensions, including the `flet create` extension scaffold, are plain Dart packages without one, so a bare `android/` folder would be ignored; (2) its pyproject package-data must add `"android/**"`, a departure from the monorepo convention `["pubspec.yaml", "lib/**"]` (§2.2). Verify both in the S7-style spike: the wheel contains `android/src/main/AndroidManifest.xml`, and `manifest-merger-release-report.txt` shows the receivers. Fallback: extend U7 with `[tool.flet.android.receiver]`. **This is not in PLAN §6.2**; see "Discrepancies" at the end |
| Android | permissions | `[tool.flet.android.permission] "android.permission.POST_NOTIFICATIONS" = true`, `"android.permission.SCHEDULE_EXACT_ALARM" = true` (not `USE_EXACT_ALARM`, which Play reviews as calendar/alarm-app only) |
| Android | small icon | `@mipmap/ic_launcher` (exists in the template). A monochrome drawable waits for 27.1 |
| iOS | prompt | `request_permission()` at the D-78 moment, shared with E2 through `PermissionGate` |
| iOS | foreground presentation | The template `AppDelegate.swift` is stock and sets no `UNUserNotificationCenter` delegate. Foreground presentation is not needed: in the foreground the app shows in-app banners. Background delivery is unaffected. No template change |

**Tests.**
- Integration on the emulator: `zoned_schedule` at now + 70 s → `get_pending_ids` contains the id → `cancel` → gone.
- DST: schedule across the 2027-03-14 US transition; the asserted UTC instant must be exact.
- Reboot test (manual, on device): pending reminders survive.
- Exact-alarm denied → inexact path.
- iOS simulator: pending request count.

**App upgrade.**
1. Add `flet-notifications==<the pinned Flet version>` (same version as `flet`, D-20) plus the setup rows.
2. `ScheduledReminders` becomes the `Reminders` provider. In-app banners stay for foreground use.
3. DEV-06 fires an OS notification with id 8999.

---

### E4 `flet-add-to-calendar` (T3, gated at G3)

| Field | Value |
|---|---|
| Serves | SESS-04 |
| Interim | `IcsShare`: `await ft.Share().share_files([ft.ShareFile.from_bytes(ics, mime_type="text/calendar", name=f"{slug}.ics")])`. This is Ionic's own fallback (SESS-05) |
| Dart package | **`add_2_calendar` 3.1.1** (MIT; published 2026-06-15; Dart `^3.11.0`, Flutter `>=3.41.0`; checked 2026-10-11). Opens the OS calendar editor pre-filled; no silent writes. `device_calendar` is rejected (stale, full calendar access) |
| Effort / owner | S, 20 h (+U6 6 h) / CC with U review |
| Deadlines | **U6 merged by 01-31**; G3 **02-12**: U6 merged and the prompt works on both OSes; released by 03-05, else 27.1 |
| Caps | `calendar` |

**Python API** (proposed, E4; D-25):

```python
@ft.control("AddToCalendar")
class AddToCalendar(ft.Service):
    async def add_event(self, title: str, start: datetime, end: datetime,
                        location: Optional[str] = None, description: Optional[str] = None,
                        url: Optional[str] = None,
                        ios_reminder: Optional[ft.DurationValue] = None) -> bool: ...
        # False = user cancelled or no calendar app; raises FletUnsupportedPlatformException on web/desktop
```

`start` and `end` are aware datetimes, sent as ISO strings. `url` maps to `IOSParams.url` on iOS and is appended to the description on Android. The app passes exactly the title, location (empty string when absent), description and URL of SESS-04. Synthetic ids link to the schedule page; a bad time yields "Couldn't read this session's time".

**Platform setup** (only in the release that ships E4):

| Platform | Entry | How |
|---|---|---|
| Android 11+ | `<queries>` `INSERT` on `vnd.android.cursor.item/event` | **U6** `[tool.flet.android.queries]` (§5 U6) |
| Android | permissions | none (prompt path) |
| iOS | `NSCalendarsUsageDescription` (iOS 15/16 and the README), `NSCalendarsWriteOnlyAccessUsageDescription` (iOS 17+; D-89 spelling) and `NSContactsUsageDescription` (the README warns of a crash without it, from location autocomplete in Apple's editor) | `[tool.flet.ios.info]` (exists). The Ionic plist had both calendar keys. D-89 lists only the write-only key today; the other two need a D-89 amendment before the E4 release (§9 #4) |

**Tests.**
- Integration: on the Android emulator, `add_event` launches the INSERT intent. The test asserts the result returns, then backs out.
- iOS simulator: the editor presents and cancelling returns False.
- Unit: datetime serialisation round-trip.
- Manual: the event lands with the correct local time on both OSes.

**App upgrade.**
1. Add `flet-add-to-calendar==0.x` plus U6 queries plus the plist keys.
2. `NativeCalendar` replaces `IcsShare` for SESS-04. The `.ics` share stays available as "Share as file".

---

### E5 `flet-html` (27.1 sprint)

| Field | Value |
|---|---|
| Serves | INFO-05, DATA-23, DATA-25, SESS-06, MAP-09 |
| Interim | `core/html_md.py` (stdlib `html.parser`; links absolutised; D-53) → `ft.Markdown(value, on_tap_link=...)` (exists). Tables degrade to text |
| Dart package | `flutter_widget_from_html_core` **0.17.4** today (MIT; 2026-09-08; deps `csslib`, `html`, `logging` only; checked 2026-10-11). Re-verify and pin exactly at the sprint |
| Gate | **Required before any code** (D-24): find out whether the widgets `HtmlWidget` builds (text selection, links) use SDK Material. If they do, wrap only the `widgets.dart` paths, or drop E5 and keep Markdown |
| Effort / owner / date | M / CC / 27.1 sprint 2027-05-17/18 (UNCONFIRMED) |
| Caps | `html` |

```python
@ft.control("Html")
class Html(ft.LayoutControl):          # proposed (E5)
    value: str = ""
    base_url: Optional[str] = None      # resolves /2027/... links (DATA-25)
    text_style: Optional[ft.TextStyle] = None
    selectable: bool = False
    on_tap_link: Optional[ft.ControlEventHandler["Html"]] = None   # e.data = absolute URL
```

**Platform setup:** none (no permissions, plist keys or manifest entries). Images load over HTTPS like any `ft.Image`.

**Tests.**
- The gate test (§2.4): static grep of `lib/`; runtime render of `Html` with links, a table, an image and `selectable=True` text on the Android emulator and the iOS simulator, with no `No Material widget found` / `FlutterError` in the log.
- `on_tap_link` delivers an absolute URL for a `/2027/...` href when `base_url` is set, and the href unchanged when it is already absolute.
- Goldens of INFO-05 and MAP-09 content rendered by `Html` stay within threshold of the Markdown (`html_md`) path.
- The upgrade guard: the resolved `flutter_widget_from_html_core` version equals the pin in `pubspec.lock`.

**App upgrade.** Wherever the app renders feed HTML (INFO-05, DATA-23, DATA-25, SESS-06, MAP-09), it uses `Html` when `caps.html` is set; otherwise `Markdown(html_md(...))`. The goldens for INFO and MAP-09 must stay within threshold.

### E6 `flet-slidable` (27.1 sprint)

| Field | Value |
|---|---|
| Serves | SCHED-11 |
| Interim | `ft.Dismissible` one-shot swipe + `await confirm_dismiss(False)` snap-back + SnackBar with Ionic copy; long-press menu and star as non-gesture paths (D-72) |
| Dart package | `flutter_slidable` **4.0.3** today (MIT; 2025-09-27; Flutter `>=3.27.0`; checked 2026-10-11) |
| Gate | Upstream `SlidableAction` is likely built from SDK Material buttons. Expose actions only through `CustomSlidableAction` with a Flet-built child, so only `Slidable`/`ActionPane` (widgets layer) are used. The gate test proves it |
| Effort / owner / date | S / CC / 27.1 sprint |
| Caps | `slidable` |

```python
@ft.control("Slidable")
class Slidable(ft.LayoutControl):      # proposed (E6)
    content: ft.Control
    start_actions: list[ft.Control] = field(default_factory=list)   # rendered as CustomSlidableAction children
    end_actions: list[ft.Control] = field(default_factory=list)
    extent_ratio: ft.Number = 0.25
    close_on_action: bool = True
    async def close(self) -> None: ...
```

**Platform setup:** none (no permissions, plist keys or manifest entries).

**Tests.**
- The gate test (§2.4) with only `CustomSlidableAction` children (no upstream `SlidableAction`): static grep plus a runtime render on the emulator and the simulator with no `No Material widget found` in the log.
- A swipe on `content` reveals the start/end actions (golden of the open state).
- `close()` returns the row to closed; with `close_on_action=True` an action tap closes it, with `False` it stays open.
- Tapping an action fires that action control's own handler exactly once.
- The upgrade guard: the resolved `flutter_slidable` version equals the pin in `pubspec.lock`.

**App upgrade.** `SessionRow` wraps itself in `Slidable` with "Favorite" (`#69bb7b`) / "Remove" (danger) actions when `caps.slidable` is set. Informational rows stay non-swipeable.

---

## 5. Core and CLI items (U1-U15)

Each item is a PR to `flet-dev/flet`, with a CHANGELOG entry, docs and integration tests per the monorepo skills (`write-changelog-entry`, `create-flet-control-integration-tests`, `docs-conventions`). CLI items also update `website/docs/publish/{index,android,ios}.md` and the `flet_build_test` example.

### U1 `ft.RefreshIndicator` (S, 8 h; U; merged 01-15)

| Field | Value |
|---|---|
| Ids | SCHED-13, SCHED-26, EVT-07, SPON-08, LEAD-13 |
| Interim | `Refreshable` renders an AppBar refresh `IconButton` + `ProgressBar` that calls `FeedStore.refresh(force=True)`, which keeps the cache on failure (D-67). LEAD-13: "Sync now" button |
| Dart | `RefreshIndicator` / `RefreshIndicator.adaptive` from `material_ui` (no new dependency; `cupertino_ui` sliver variant not needed) |
| Probe | `refresh_indicator` = `hasattr(ft, "RefreshIndicator")` |

```python
@ft.control("RefreshIndicator")
class RefreshIndicator(ft.LayoutControl):      # proposed (U1)
    content: ft.Control                        # must be scrollable (ListView/Column(scroll=...))
    on_refresh: Optional[ft.ControlEventHandler["RefreshIndicator"]] = None   # sync or async
    color: Optional[ft.ColorValue] = None
    bgcolor: Optional[ft.ColorValue] = None
    displacement: ft.Number = 40.0             # Flutter default
    edge_offset: ft.Number = 0.0
    stroke_width: ft.Number = 2.5              # RefreshProgressIndicator.defaultStrokeWidth
    adaptive: bool = False
```

**Completion contract.** Flutter's `onRefresh` needs a `Future`. Mirror `Dismissible` (`DART/controls/dismissible.dart`): `onRefresh` creates a `Completer` and triggers `refresh`. The Python class overrides `_trigger_event` for `refresh`: it awaits the user handler, then always calls `await self._invoke_method("end_refresh")` in a `finally`, which completes the `Completer`. A Dart-side 60 s timeout completes it if Python never answers, so the spinner can never hang (the SPON-08 Ionic bug).

**Tests.** Drag gesture → handler runs → spinner disappears after the handler returns. A handler that raises still ends the spinner. Adaptive on iOS shows the Cupertino style (golden).

**App upgrade.** `Refreshable` branches on `caps.refresh_indicator` by value, never with a conditional hook (D-67).

### U2 Sticky group headers (M; FT/CC; 27.1)

| Field | Value |
|---|---|
| Ids | SCHED-02 |
| Interim | `ListView` of non-sticky slot dividers ("Sat - 9:25 am") + rows (D-71) |
| Design | A `CustomScrollView` with one `SliverMainAxisGroup` per group, whose first sliver is a `PinnedHeaderSliver`. These are framework widgets, so no new dependency and no Material |
| Probe | `sticky_headers` = `hasattr(ft, "GroupedListView")` |

```python
@ft.control("ListGroup")
class ListGroup(ft.Control):                   # proposed (U2), sub-control
    header: ft.Control
    controls: list[ft.Control] = field(default_factory=list)

@ft.control("GroupedListView")
class GroupedListView(ft.LayoutControl):       # proposed (U2)
    groups: list[ListGroup] = field(default_factory=list)
    sticky_headers: bool = True
    async def scroll_to(self, offset: Optional[float] = None, delta: Optional[float] = None,
                        scroll_key=None, duration: ft.DurationValue = 0,
                        curve: ft.AnimationCurve = ft.AnimationCurve.EASE) -> None: ...
        # same signature and scroll_key semantics as ListView.scroll_to (decisions §N.5)
```

SCHED-16's scroll-to-slot uses the same key contract as `ListView.scroll_to` (decisions §N.5). Ships in 27.1 (D-26; feature-matrix SCHED-02).

**Tests.**
- Integration (`create-flet-control-integration-tests`): three groups, scrolled past the first header. The header stays pinned at the top and the next header pushes it out (golden at two scroll offsets). With `sticky_headers=False`, headers scroll with their rows.
- `scroll_to(scroll_key=...)` on a row in a later group lands it directly below the pinned header; `offset`/`delta` behave as in `ListView`.
- Adding a group in an update re-renders without resetting the scroll offset.
- The log has no `No Material widget found` (framework widgets only; checked like §2.4 step 2).

**App upgrade.** The schedule list branches on `caps.sticky_headers`: a `GroupedListView` with one `ListGroup` per slot (header = the existing divider text), or the D-71 divider `ListView`. SCHED-16 calls the same `scroll_to(scroll_key=...)` on either.

### U3 `InteractiveViewer.set_transform()` / `zoom_to_rect()` (S, 10 h; U; 02-12; T2)

| Field | Value |
|---|---|
| Ids | EXPO-05 (T2; third on the cut order) |
| Interim | `await iv.reset()` → `await iv.zoom(6)` → `await iv.pan(dx, dy)`, on an `ft.InteractiveViewer(max_scale=8, boundary_margin=ft.Margin.all(...), ...)`: `zoom(factor)` clamps the total scale to `max_scale`, which defaults to 2.5, so any `max_scale >= 6` is required or `zoom(6)` silently stops at 2.5×; popup after 250 ms. The existing `zoom(factor)` and `pan(dx, dy, dz)` are relative, instant and clamped. `reset(animation_duration)` goes back to identity and is the only one that animates (a `Matrix4Tween`, `DART/controls/interactive_viewer.dart`). `save_state`/`restore_state` store and restore one matrix |
| Dart | Set `TransformationController.value` directly. Animate with a `Matrix4Tween` when a duration is given, reusing the existing `reset` code path |
| Probe | `iv_set_transform` = `hasattr(ft.InteractiveViewer, "set_transform")` |

```python
# added to ft.InteractiveViewer (proposed, U3)
async def set_transform(self, scale: ft.Number, offset: ft.OffsetValue,
                        animation_duration: Optional[ft.DurationValue] = None) -> None: ...
async def zoom_to_rect(self, rect: ft.Rect, padding: ft.Number = 0,
                       animation_duration: Optional[ft.DurationValue] = None) -> None: ...
```

`zoom_to_rect` computes the scale that fits `rect` (in content coordinates; booths are 9931×7021 ratios in app-content) inside the viewport, clamps it to `[min_scale, max_scale]` and centres it. That is exactly "zoom to booth N". The same id twice re-centres. `reduce_motion` passes `animation_duration=None`.

**Tests.**
- Integration: `set_transform(scale=2, offset=...)` on a gridded test image lands the expected `TransformationController` matrix (golden of the viewport; `save_state` → `restore_state` round-trips it).
- `zoom_to_rect` on a rect so small that fitting it would exceed `max_scale` clamps to `max_scale`; a rect too large to fit at `min_scale` clamps to `min_scale`; calling it twice with the same rect gives the same golden.
- With `animation_duration`, a frame pumped halfway differs from both the start and the end; without it, the first frame is final.

**App upgrade.** `FloorPlan` branches on `caps.iv_set_transform`: `zoom_to_rect(booth_rect, animation_duration=...)` (`None` under `reduce_motion`) replaces reset → zoom → pan. The popup still opens 250 ms after the call returns.

### U4 `page.get_app_info()` (S, 4 h; U; merged 01-15)

| Field | Value |
|---|---|
| Ids | INFO-03 |
| Interim | `build_info.py` written by CI (VERSION, BUILD_NUMBER, GIT_SHA, TARGET, CAPS, PYCON_ENV; D-90). `importlib.metadata` does not work in packaged apps (decisions §N.10) |
| Dart | `package_info_plus ^9.0.0` is already a dependency of `packages/flet/pubspec.yaml`, but nothing uses it. Add a `get_app_info` case next to `get_device_info` in `DART/controls/page.dart` |
| Probe | `app_info` = `hasattr(ft.Page, "get_app_info")`. The manifest gate matters: in the companion app this would report the companion's own version, so `PageAppInfo` is used only from a built app |

```python
@ft.value
class AppInfo:                                  # proposed (U4)
    app_name: str; package_name: str; version: str; build_number: str
    installer_store: Optional[str] = None

# ft.Page (proposed, U4)
async def get_app_info(self) -> AppInfo: ...
```

**App upgrade.** `PageAppInfo` supplies version and build. `GIT_SHA`, `TARGET` and `CAPS` still come from `build_info.py`.

**Tests.**
- Integration on the flet test host (`flet test android` / `flet test ios`): `get_app_info()` returns the `version` and `build_number` the host was built with (`--build-version` / `--build-number`), and `package_name` equals its bundle id.
- Unit: `AppInfo` deserialisation, including `installer_store=None`.
- App side: the fallback-parity suite runs `app_info` on and off; INFO-03 shows the same version string either way.

### U5 `[tool.flet.ios.entitlement]` (S, 8 h; U; merged 01-31, released by 02-26)

| Field | Value |
|---|---|
| Ids | NOTIF-04, NATIVE-04 (push), NATIVE-07 (`webcredentials:us.pycon.org` autofill) |
| Interim | push off; autofill through `ft.AutofillGroup` + `TextField(autofill_hints=[...])` OS heuristics |
| Today | Only `[tool.flet.macos.entitlement]` / `--macos-entitlements` exist (`CLI/build_base.py`, rendered by `render_dict` into `TPL/macos/Runner/*.entitlements`). `TPL/ios/Runner` has no `.entitlements` file and the pbxproj has no `CODE_SIGN_ENTITLEMENTS` |
| Change | (1) A CLI option `--ios-entitlements key=value` plus the pyproject table, merged like the macOS one (`merge_dict` + `parse_cli_plist_value`). (2) Template: add `ios/Runner/Runner.entitlements` rendered with `render_dict(cookiecutter.options.ios_entitlements)`, emitted only when non-empty, and `CODE_SIGN_ENTITLEMENTS = Runner/Runner.entitlements` in the three Runner build configurations, conditionally. (3) Docs in `publish/ios.md` |

```toml
# app pyproject, only in the release that ships E2 / the autofill upgrade (D-89)
[tool.flet.ios.entitlement]
"aps-environment" = "production"
"com.apple.developer.associated-domains" = ["webcredentials:us.pycon.org"]
```

**Tests.**
- Unit: rendering with an empty table produces no file and no build setting, so existing builds are byte-identical.
- `flet build ipa` on CI: `codesign -d --entitlements - Runner.app` shows the keys.
- PSF prerequisites: the App ID capabilities, and an AASA file on us.pycon.org with team `BMM5U3QVKW` (NATIVE-07 gotcha).

### U6 `[tool.flet.android.queries]` (S, 6 h; U; 01-31, only if E4)

| Field | Value |
|---|---|
| Ids | SESS-04 (calendar INSERT), INFO-14 (would allow `can_launch_url`; the app still avoids it) |
| Today | `TPL/android/app/src/main/AndroidManifest.xml` has one fixed `<queries>` (`PROCESS_TEXT`) and no hook |
| Change | Render extra `<intent>` and `<package>` entries inside the existing `<queries>` |

```toml
[[tool.flet.android.queries.intent]]
action = "android.intent.action.INSERT"
data = { mimeType = "vnd.android.cursor.item/event" }   # attributes rendered as android:<k>
[[tool.flet.android.queries.intent]]
action = "android.support.customtabs.action.CustomTabsService"
```

**Test.** The manifest-merger report contains the intents. On an API 34 emulator, E4's `add_event` resolves the activity.

### U7 `core_library_desugaring` (S, 6 h; U; 01-31, only if E3)

| Field | Value |
|---|---|
| Ids | NOTIF-05 |
| Today | `TPL/android/app/build.gradle.kts` has `compileOptions { sourceCompatibility/targetCompatibility = JavaVersion.VERSION_17 }` and no desugaring. The CLI has no arbitrary Gradle snippet hook. The `:app` Gradle knobs are `legacy_packaging`, `excluded_abis`, `min_sdk_version`/`target_sdk_version`, `target_arch`/split-per-ABI and signing, plus `gradle_properties` and ProGuard rules. None of them enables desugaring |
| Change | `[tool.flet.android] core_library_desugaring = true` (+ `--android-core-library-desugaring`) renders `isCoreLibraryDesugaringEnabled = true` and `dependencies { coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.4") }` |
| Scope note | If the #6948 package cannot carry the receivers in its own library manifest (§E3), U7 grows a `[tool.flet.android.receiver]` table rendered like `provider` (name + attributes + `intent_filter` actions) |

**Test.** `flet build apk` of an app using `flutter_local_notifications` 22.3.1 succeeds with the flag and fails without it (a regression guard that the flag is wired).

### U8 Resource meta-data and string resources (S, 5 h per D-112; U; 01-31, only for the autofill upgrade)

| Field | Value |
|---|---|
| Ids | NATIVE-07 (Android credential sharing with us.pycon.org) |
| Today | `[tool.flet.android.meta_data]` renders only `android:value`. `provider.meta_data` already accepts inline tables of attributes (`CLI/build_base.py`). The template has **no app string resource** to point at |
| Change | (1) Accept inline tables in `[tool.flet.android.meta_data]`, rendered as attributes, reusing the provider code path. (2) Add `[tool.flet.android.string_resources]`, rendered into `res/values/flet_strings.xml` as `<string name="..." translatable="false">` with Android string-resource escaping: XML-escape `&` and `<`; backslash-escape `"`, `'` and `\`, a leading `@` or `?`, and newlines (`\n`). XML escaping alone is not enough: aapt strips unescaped double quotes as quoting delimiters (and `&quot;` is a raw `"` after parsing), so the `asset_statements` JSON would reach the app without its quotes. Ionic's working `strings.xml` uses `\"` for this reason. **Without (2), (1) cannot express `asset_statements`**, because `@string/asset_statements` must exist |

```toml
[tool.flet.android.string_resources]
asset_statements = '[{"include": "https://us.pycon.org/.well-known/assetlinks.json"}]'
[tool.flet.android.meta_data]
asset_statements = { resource = "@string/asset_statements" }
```

PSF prerequisite: `assetlinks.json` with the upload and app-signing certificate fingerprints.

**Scope note.** Part (2) widens D-26 U8 ("inline-table resource `meta_data`") and the estimate moves from 3 h to 5 h. Both are recorded in D-112 (§9 #2).

**Tests.**
- Unit: with both tables empty the rendered manifest is byte-identical to today and no `flet_strings.xml` is written. A value containing `&`, `<`, `"`, `'`, `\`, a leading `@` and a newline is rendered with the escaping above and `translatable="false"`. An inline table renders as attributes (`android:resource="@string/asset_statements"`).
- `flet build apk` on CI: the manifest-merger report contains the `asset_statements` meta-data, and the **compiled** `asset_statements` resource (read back with `aapt2 dump resources` on the APK, or `getString` on the emulator) equals the exact JSON input, quotes included.
- Device (manual): once the PSF's `assetlinks.json` is live, the Android password manager offers us.pycon.org credentials in the login form.

**App upgrade.** Only in the release that ships the autofill upgrade (D-89): add the two tables above (with U5's `webcredentials:` entitlement on iOS). No app code changes; `ft.AutofillGroup` is already in place.

### U9 `ft.use_route_search()` (XS; U; 02-12; T2)

| Field | Value |
|---|---|
| Ids | ROOM-03 (`?session=` highlight), SPON-04 (`expo-hall?booth=N`) |
| Interim | `use_query()` calls `ft.use_route_location()`, which subscribes and returns the pathname only, then parses `page.route` (D-37; spike S9 verifies `page.route` carries the query) |
| Today | `LocationInfo.search` is already populated in `FLET/components/router.py` (`search = parsed.query or ""`, line ~725), without the leading `?`. It is just not exposed by a hook |
| Change | `def use_route_search() -> str`, next to `use_route_location()` in `router.py`, returning the location's `search` (no `?`) and subscribing the same way. Export as `ft.use_route_search` |
| Probe | the helper: `use_query()` returns `dict(parse_qsl(ft.use_route_search()))` when available. One branch at import, never a conditional hook |

**Tests.**
- Component test under `ft.Router`: `use_route_search()` returns `"session=42"` (no `?`) for `/rooms/a?session=42`, `""` without a query, and never includes a `#` fragment.
- After `page.navigate("/expo-hall", booth=7)` (kwargs become query parameters), the subscribed component re-renders and returns `"booth=7"`.

**App upgrade.** None beyond the Flet pin: `use_query()` switches branch at import. The ROOM-03 and SPON-04 tests run against both branches (fallback parity).

### U10 `AppBar.bottom` (S; post-conference)

- **Ids:** SCHED-01.
- **Interim:** the day selector (`SegmentedButton` / `CupertinoSlidingSegmentedButton` / scrollable `TabBar`) is the first row of `View.controls`.
- **Today:** `ft.AppBar` has no `bottom` field (decisions §N.8).
- **Change:** add `bottom: Optional[ft.Control]` and `bottom_height: ft.Number = 48.0`, wrapped in `PreferredSize`.
- **Owner:** CC (PyCon sprint candidate), reviewed by U.
- **Tests:** integration: `AppBar(bottom=..., bottom_height=48)` renders the control below the toolbar (golden), the bar's preferred height is toolbar + `bottom_height`, and updating `bottom` re-renders it. `bottom=None` leaves the layout unchanged (regression golden).
- **App upgrade (27.1):** a helper-level probe (`"bottom" in [f.name for f in dataclasses.fields(ft.AppBar)]`, like U9/U15; no `Caps` key). The schedule view moves the day selector from the first row of `View.controls` into `AppBar.bottom`. No other screen changes.

### U11 Offline service worker for `flet build web` (M; post-conference)

- **Ids:** NATIVE-09.
- **Interim:** an online-only PWA on PSF Firebase Hosting (D-93).
- **Today:** Flutter 3.47's `flutter_service_worker.js` unregisters itself, and Pyodide and CanvasKit load from CDNs.
- **Change:** a Flet-generated SW precaching `app.zip`, Pyodide and CanvasKit (`--no-cdn`), with versioned cache names.
- **Owner:** FT.
- **Tests:** CI `flet build web --no-cdn`, then headless Chromium: load once online, switch the network off, reload, and the app boots from cache. A new build changes the cache names and the old caches are deleted on `activate`.
- **App upgrade (27.1):** rebuild the PWA on the new Flet pin with `--no-cdn`, and serve the service-worker file with `no-cache` on Firebase Hosting (D-93 otherwise unchanged). The shell then boots offline; feed data still needs the network (the web build has no sqlite cache, D-93).

### U12 `[tool.flet.ios] deployment_target` (S; U; conditional, 12-15)

- **Ids:** NATIVE-02.
- **Today:** the target is fixed at 15.0 in three places in `TPL/ios/Runner.xcodeproj/project.pbxproj` and in `Podfile` (`platform :ios, '15.0'`). Xcode 27 rejects anything lower.
- **Change:** render all four from one option, rejecting values below 15.
- **Do it only if spike S10** finds a wrapped pod (E1-E4) whose minimum is above 15. Otherwise close it as not needed.
- **Tests:** unit: no option keeps `15.0` in all four places (byte-identical template); `deployment_target = "16.0"` rewrites the three pbxproj entries and the Podfile; `"14.0"` is rejected with a clear error. CI `flet build ipa` with `16.0`: `xcodebuild -showBuildSettings` reports `IPHONEOS_DEPLOYMENT_TARGET = 16.0` and `pod install` succeeds.
- **App upgrade:** set `[tool.flet.ios] deployment_target` to the pod's minimum, only in the release that ships the extension needing it.

### U13 Template `PrivacyInfo.xcprivacy` (S; U; conditional, 12-15)

- **Context:** store submission risk R9.
- **Today:** there is no app-level privacy manifest in `TPL/ios/Runner`.
- **Do it only if spike S5** (a throwaway TestFlight upload) reports ITMS-91053.
- **Change:** ship `Runner/PrivacyInfo.xcprivacy` in the Runner target's resources. It declares the required-reason APIs that the embedded CPython uses (file timestamp, disk space, system boot time; `UserDefaults` for `shared_preferences`), with reasons chosen from Apple's list and reviewed by FT.
- **Tests:** CI `flet build ipa`: the `.app` contains `PrivacyInfo.xcprivacy` and `plutil -lint` passes. A TestFlight upload of that IPA (the S5 check, rerun) reports no ITMS-91053.
- **App upgrade:** none; the template change arrives with the Flet pin.

### U14 Verified App Links and multiple hosts (S; post-conference)

- **Context:** deep links (D-38).
- **Interim:** the custom scheme `pyconus://app/...` (exists: `[tool.flet.android.deep_linking]` / `[tool.flet.ios.deep_linking]` `scheme`/`host`, one pair each; the global `[tool.flet.deep_linking]` is ignored for Android and iOS builds, D-109).
- **Change:** `[tool.flet.android.deep_linking] auto_verify = true`, `hosts = [...]` and `path_prefix`. iOS Universal Links reuse U5 (`applinks:`).
- **Note:** sheet detents (SHELL-07: `BottomSheet` has no detents, decisions §N.12) are a separate post-conference control gap with no U-id yet (PLAN §6.2). In 27.0 it is a fixed-height sheet.
- **Tests:** unit: `auto_verify = true` renders `android:autoVerify="true"` on the intent filter, with one `<data>` per host plus `path_prefix`; without the table the manifest is byte-identical. Device: `adb shell pm get-app-links org.pycon.us` reports `verified` for us.pycon.org once `assetlinks.json` is live, and an `https://us.pycon.org/...` link opens the app. iOS: the `applinks:` entitlement (through U5) and the AASA file open the app from Safari.
- **App upgrade (27.1):** add the table with `hosts = ["us.pycon.org"]`, and `applinks:us.pycon.org` to the U5 entitlement table. The PSF publishes `assetlinks.json` (`delegate_permission/common.handle_all_urls`) and the AASA `applinks` section. The router maps the https paths to the same canonical routes as the custom-scheme aliases (D-38); the custom scheme stays.

### U15 Non-fatal handler/effect errors (S; U; 02-12; T2)

| Field | Value |
|---|---|
| Context | PLAN [§5.8](../PLAN.md#58-error-handling), D-85, D-86 |
| Interim | `@safe` on every handler and effect, plus a lint rule |
| Today | Handler exceptions call `session.error(...)` (`FLET/messaging/session.py`, event dispatch), and so do sync-effect exceptions ("Exception in effect"). Both send `SESSION_CRASHED`. `page.on_error` exists but is the Flutter-side event |
| Change | (1) `ft.set_error_handler(handler)`: called with `(exc, where)` before `session.error`; returning `True` marks the error handled, so there is no crash screen. (2) An app option `fatal_errors: bool = True` (default unchanged) to keep sessions alive. Both are opt-in, so existing apps behave identically |
| Probe | `services/safe.py` registers the hook when `hasattr(ft, "set_error_handler")`. `@safe` stays as defence in depth |

**Tests.**
- Integration (Python side, `FletTestApp`): a click handler that raises, with `set_error_handler` returning `True`, sends no `SESSION_CRASHED` and the page stays interactive. The hook receives the exception and a `where` naming the handler.
- The same for a sync effect that raises.
- A hook returning `False`/`None` keeps today's crash behaviour; `fatal_errors=False` keeps the session alive without a hook; with neither, behaviour is unchanged (regression).

**App upgrade.** None beyond the Flet pin: `services/safe.py` registers the hook at import when present; `@safe` stays.

---

## 6. Timeline and gates (extract of PLAN [§7](../PLAN.md#72-milestones) for this doc)

| When | What | Item |
|---|---|---|
| by 11-13 (M0, G1) | Spike **S7**: a standalone wheel via `[tool.flet.<platform>].dependencies` + `mobile_scanner` under the gate. Spike **S10**: pod minimums. Spike **S5**: TestFlight upload (decides U13) | E1, U12, U13 |
| by 11-30 | Spike **S8**: Dart-only Firebase init + topic round-trip | E2 |
| 12-15 | U12/U13 done only if their spike tripped; contributors recruited (E4-E6 owners) | U12, U13 |
| 01-10 | E1 v0.1 on device | E1 |
| 01-15 | U1 and U4 merged; #6948 v1 merged and released (UNCONFIRMED, FT) | U1, U4, E3 |
| 01-31 (G2) | U5 merged (U6-U8 if pursued); E1 reads real badges; P5 Firebase config | U5-U8, E1, E2 |
| **02-12 (G3)** | Per item, go or 27.1: E2, E3 (+U7), E4 (+U6), the autofill entitlement (U5/U8). U3, U9, U15 merged (T2) | T3, T2 |
| 02-19 | E1 0.2 on PyPI | E1 |
| 02-24 / 02-26 | Badge Day 1 / G-Staff (E1 >= 95 % first try). Flet 1.1.x point release with U5-U8 (+U1/U3/U4/U9/U15) and, if E3 is "go" at G3, the #6948 scheduling PR (else a 1.2 released before 03-05) | E1, E3, U* |
| **03-05** | Last pin change: every "go" item released and pinned | all |
| 05-17/18 (UNCONFIRMED) | Sprint: E5, E6, U2, U11, the T3 items that missed | post |
| 06-30 (M7) | 27.1: missed upgrades; extensions to 1.0 | all |

If any item misses its date, its interim ships. That is the whole contingency (D-10, PLAN principle 8).

---

## 7. Documented-only workarounds (**not used in 27.0**; D-28)

These are recorded so nobody rediscovers them under pressure. None is a late switch. The rule is: upstream first, never a fork.

| Workaround | What it would do | Why not |
|---|---|---|
| Helper plugin `native/pycon_native_config` (a Flutter-only Android plugin added through `[tool.flet.flutter.pubspec.dependencies]`) | Its library manifest adds `<queries>`, `asset_statements` (with its own `strings.xml`), a drawable for the FCM icon, and could even merge an `autoVerify` intent-filter into `MainActivity` | Status **PLAUSIBLE**: built only on paper. It is native code living in the app repo, which U6/U8/U14 replace upstream. The `autoVerify` merge is brittle |
| Gradle init script `~/.gradle/init.d/pycon-desugaring.gradle.kts` | Enables desugaring in `:app` without a template change | Status **PLAUSIBLE**. It lives outside the repo's build definition (CI-only magic); U7 replaces it |
| Custom build template (`[tool.flet.template] url/ref`) | Entitlements, AppDelegate, Gradle edits | **Never** (D-28, PLAN §2 non-goals): it needs a rebase on every Flet release, right before a conference |
| Unbundled ML Kit (`[tool.flet.android.gradle_properties]`) | A smaller APK for E1 | Exists and is supported, but rejected: the model downloads on first use (§E1) |

---

## 8. Verification log (2026-10-11)

**pub.dev** (`https://pub.dev/api/packages/<name>`, fetched 2026-10-11).

| Package | Latest | Published | Constraints noted |
|---|---|---|---|
| mobile_scanner | 7.4.2 | 2026-09-14 | Dart ^3.7.0, Flutter >=3.29.0 |
| firebase_core | 4.15.0 | 2026-09-14 | - |
| firebase_messaging | 16.7.0 | 2026-09-14 | firebase_core ^4.14.0; Dart ^3.6.0; Flutter >=3.27.0 |
| firebase_analytics | 12.6.0 | 2026-09-14 | - |
| flutter_local_notifications | 22.3.1 | 2026-09-13 | timezone ^0.11.0; Dart ^3.10.0; Flutter >=3.38.1; Android: receivers + desugaring (`desugar_jdk_libs` 2.1.4) + AGP >= 8.11.1 |
| timezone | 0.11.1 | 2026-06-29 | - |
| add_2_calendar | 3.1.1 | 2026-06-15 | Dart ^3.11.0; Flutter >=3.41.0; iOS calendar + contacts keys; Android `<queries>` |
| flutter_widget_from_html_core | 0.17.4 | 2026-09-08 | no Material package dependency (gate still required) |
| flutter_slidable | 4.0.3 | 2025-09-27 | Flutter >=3.27.0 |

All Flutter minimums are at or below the extension template's `flutter: ">=3.47.0"` (Flet 1.1 uses Flutter 3.47).

**PyPI names** (HTTP status of `pypi.org/pypi/<name>/json`).
- 404 (free): `flet-barcode-scanner`, `flet-firebase`, `flet-firebase-analytics`, `flet-add-to-calendar`, `flet-notifications`, `flet-html`, `flet-slidable`.
- 200 (taken): `flet-local-notifications`.

**Local SDK** (exists; introspected 2026-10-11).
- Base classes and helpers: `ft.Service` (`_auto_register`, `_invoke_method(method_name, arguments, timeout)`), `ft.LayoutControl`, `ft.control`, `ft.value`, `ft.Event`, `ft.EventHandler`, `ft.ControlEventHandler`, `ft.FletUnsupportedPlatformException`.
- `ft.InteractiveViewer.zoom/pan/reset/save_state/restore_state` (coroutines), `ft.Dismissible.confirm_dismiss` (coroutine), `ft.ListView.scroll_to(offset, delta, scroll_key, duration, curve)`.
- `ft.Markdown.on_tap_link`, `ft.Share.share_files/share_text/share_uri`, `ft.ShareFile`, `ft.UrlLauncher` + `ft.LaunchMode.IN_APP_BROWSER_VIEW`, `ft.Wakelock.enable/disable/is_enabled`.
- `ft.SemanticsService.announce_message/get_accessibility_features`, `ft.Page.get_device_info`, `ft.Page.on_error`, `ft.Router(routes, not_found, manage_views)`, `ft.Route(path, index, component, children, loader, outlet, modal, recursive)`, `ft.use_route_location`, `ft.LocationInfo`.
- `ft.Matrix4`, `ft.Rect(left, top, right, bottom)`, `ft.AutofillGroup`, `ft.Banner` (a `DialogControl`).
- Extensions: `flet_permission_handler.PermissionHandler` + `Permission.CAMERA/NOTIFICATION/CALENDAR_WRITE_ONLY/SCHEDULE_EXACT_ALARM`; `flet_secure_storage.SecureStorage`.
- CLI: `flet test <platform> --device-id` (`CLI/test.py`).

**Confirmed absent** (the items above): `ft.RefreshIndicator`, `ft.use_route_search`, `ft.Page.get_app_info`, `ft.AppInfo`, `ft.AppBar.bottom`, `InteractiveViewer.set_transform`, any sliver or sticky control, an iOS entitlements option, an Android `<queries>` hook, desugaring, `<receiver>` and string-resource hooks.

**Corrections to `docs/research/flet/*`.**
1. Android `gradle.properties` **is** configurable: `[tool.flet.android.gradle_properties]` (exists), so `mobile_scanner`'s unbundled flag needs no fork.
2. `flutter_local_notifications` does **not** merge its receivers from the plugin manifest. Its manifest declares only `VIBRATE` and `POST_NOTIFICATIONS`, so scheduling needs the receivers declared elsewhere (§E3).
3. The first-party service extensions (`flet-geolocator`, `flet-secure-storage`, `flet-permission-handler`) list no `material_ui` in their pubspecs. Only packages that build Material widgets need it, so E2-E4 do not.

---

## 9. Discrepancies with PLAN.md and the decisions record (all resolved 2026-10-11)

Each row below is now recorded in the decisions record and followed by PLAN.md: #1 by D-113, #2 by D-112, #3 by D-111, #4 by D-114, #5 by D-132.

| # | Where | Issue | This doc |
|---|---|---|---|
| 1 | PLAN §6.2 E3; D-26 U7 | Scheduled notifications need two `<receiver>` entries + `RECEIVE_BOOT_COMPLETED` in the app manifest; U7 (desugaring) alone is not enough, and the template has no receiver hook | Receivers ship in the #6948 package's Android library manifest. This needs a `flutter: plugin: platforms: android: package:` entry in its pubspec (manifest-only plugin, no `pluginClass`) and `"android/**"` in its package-data (§E3); fallback: U7 gains `[tool.flet.android.receiver]` |
| 2 | PLAN §6.2 U8; D-26 U8 | Inline-table `meta_data` cannot express `asset_statements` without a `@string` resource, which the template cannot add | U8 = inline-table meta-data **+** `[tool.flet.android.string_resources]`, re-estimated S, 5 h (was 3 h); recorded as D-112 (amends D-26 U8 and the D-17 hours; PLAN §6.2 U6-U8 17 h, §7.1 T3 127 h) |
| 3 | D-24/D-25 E2 | `firebase_analytics` cannot be optional inside one `flet-firebase` wheel; bundling it contradicts D-79 / NATIVE-05 | Separate wheel `flet-firebase-analytics` (`flet_firebase_analytics.FirebaseAnalytics`); recorded as D-111 (supersedes the analytics part of D-24/D-25); the feature-matrix `E2` legend, the §3 probe row and the register use the new names |
| 4 | D-89; PLAN §9.1 | E4 (`add_2_calendar`) also needs `NSCalendarsUsageDescription` (iOS 15/16) and `NSContactsUsageDescription` (README: crash otherwise) | All three keys in the E4 release; recorded as D-114 (amends D-89) |
| 5 | D-74 vs PLAN §6.2 | U9/U15 trigger is "probe", but D-74 defines no `Caps` key for them | Helper-level import probes (§3) |
