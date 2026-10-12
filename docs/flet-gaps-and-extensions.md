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
| 1 | **E3** | Scheduled local notifications | NOTIF-01, NOTIF-05, NOTIF-06, NOTIF-10, DEV-06, STORE-10, NATIVE-06, NEW-05 | Now's "Your next session", an in-app `Banner` while the app is open, `.ics` with `VALARM`; Settings says "Reminders aren't available in this build" (D-60) | Scheduling added to the official extension from [flet-dev/flet#6948](https://github.com/flet-dev/flet/issues/6948) (`flutter_local_notifications` 22.3.1), plus U7 and the Android receivers | P2 (spike S6 during P1) | M | #6948 is an open issue (v1 scope, no scheduling); no PR yet |
| 2 | **U1** | Pull-to-refresh | DATA-03, SCHED-13, EVT-07, SPON-08 | Status strip with Refresh, plus automatic refresh (D-32, D-40) | `ft.RefreshIndicator` | P1 | S | proposed |
| 3 | **U15** | A handler exception crashes the session | (cross-cutting) | `@report_errors` decorator (D-71) | An opt-in non-fatal mode with a Python error hook | P1–P2 | S | proposed |
| 4 | **E1** | Barcode scanning | LEAD-01, LEAD-02, DOOR-04, SHIRT-02, MASK-04, NATIVE-06 | Manual entry plus USB/Bluetooth HID scanners, which always work (D-65) | New extension over `mobile_scanner` 7.4.2 | Before P3 (spike S8) | M | proposed |
| 5 | **U4** | App version at runtime | INFO-03 | `pycon_us.__version__` plus the build number constant (D-83) | `page.get_app_info()` | P2 | XS | proposed |
| 6 | **U16** | OS text-scale factor | THEME-11 | Fluid layouts, no fixed heights (D-26) | `PageMediaData.text_scale_factor` | P2 | XS | proposed (one PR with U17) |
| 6 | **U17** | Accessibility-setting changes | THEME-09, high contrast (D-23) | Re-read `get_accessibility_features()` on start and resume (D-34) | Accessibility fields in `PageMediaData`, delivered by the existing `on_media_change` | P2 | XS | proposed (one PR with U16) |
| 6 | **U10** | `AppBar.bottom` | SCHED-01, SCHED-27 | Day tabs as the first body row | `AppBar.bottom` | later | S | proposed |
| 6 | **U2** | Sticky headers / slivers | SCHED-02, SCHED-27 | Time gutter layout (D-31) | A grouped list with pinned headers | later | M | proposed |
| 6 | **U3** | Absolute `InteractiveViewer` transform | EXPO-05 | Select and highlight the booth without moving the camera | `set_transform()` / `zoom_to_rect()` | later | S | proposed |
| 6 | **U9** | Query-string hook | ROOM-03, SPON-04, EXPO-05 | `use_query()` parses `page.route` | `ft.use_route_search()` | later | XS | proposed |
| 6 | **U18** | Back inside a modal sub-chain | NEW-02 (search, D-19) | Our own `page.on_view_pop`, set before `page.render_views(App)`, navigates to `parent_of(e.route)` (D-19) | The Router pops to the previous view entry unless the popped view is the modal itself (§5.12) | later | XS | proposed |
| later | **E4** | Native add-to-calendar | SESS-04 | `.ics` through `Share.share_files` (SESS-05, D-62) | Extension over `add_2_calendar` 3.1.1 (+ U6) | later | S | proposed |
| low | **E2** | FCM push | none: the app has no push (D-58) | n/a | `firebase_messaging` 16.7.0 (+ U5) | never, in this app | L | a Flet contribution only |

**Conditional CLI and template items.** We do these only when a feature or a spike needs them (D-98).

| Id | What | Needed by | Status |
|---|---|---|---|
| **U7** | Core library desugaring in the Android `:app` module | E3: `flutter_local_notifications` requires it **even without scheduling**, so #6948 v1 must solve it | needed (§4.1) |
| **U6** | Extra Android `<queries>` entries | E4; `can_launch_url` (INFO-14, which avoids it) | only with E4 |
| **U12** | Configurable iOS deployment target | A pod needing more than iOS 15 | **not needed**: pod minimums are 11.0–13.0 (§6) |
| **U13** | App-level `PrivacyInfo.xcprivacy` | ITMS-91053 in the S5 TestFlight upload | only if S5 reports it |

### 1.2 Deep links: no gap

Deep links (NEW-07, D-21) use what exists: the per-platform tables `flet build` reads for Android and iOS (`CLI/build_base.py:1422-1437`) and the template's custom-scheme intent filter (`TPL/android/app/src/main/AndroidManifest.xml:47-55`) and Info.plist entry. The owner's open PR [flet-dev/flet#6953](https://github.com/flet-dev/flet/pull/6953) (fixes #6951) makes the common `[tool.flet.deep_linking]` table a per-key fallback on Android and iOS. We configure **both per-platform tables**, so links work with or without #6953 in the pinned Flet (F16); collapsing them later is optional.

```toml
# pyproject.toml (P2). The scheme follows the app identity (O-4); "pyconus" is a placeholder.
[tool.flet.android.deep_linking]
scheme = "pyconus"
host = "app"

[tool.flet.ios.deep_linking]
scheme = "pyconus"
host = "app"
```

Reminder taps (E3) reuse the same paths, so a notification and a link both land on "root with the target pushed" (D-21).

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

**Noted, not scheduled.** These are small gaps the UX studies, the architecture and the tooling checks raised. Each has a working interim. D-98 lists seven as later candidates (U19..U25); the rest get an id only when a feature needs them, and the last four are small fixes the owner can file directly.

| Gap | Interim | Possible upstream piece |
|---|---|---|
| `Theme.platform` (U19, D-98) | Pin the iOS-adaptive defaults by hand: bundled font, `center_title=False`, Material back arrow (D-10) | `Theme.platform` |
| Contrast level / scheme variant | Hand-authored high-contrast overrides (D-23) | `Theme.contrast_level`, `color_scheme_variant` |
| `TextStyle.font_features` | Roboto, whose digits are tabular (D-26) | `font_features` |
| Bottom-sheet detents, non-modal sheet | Fixed-height `BottomSheet`; a positioned `Card` for the booth card | Detents / persistent sheet |
| Secure screen (`FLAG_SECURE`, iOS snapshot blur) for staff PII | Clear result panels when the app goes to the background (P3) | A `page` flag |
| `ft.Markdown` always adds LaTeX syntax, so `$…$`, `( … )` and `[ … ]` in text render as math (U21, D-117, F27) | Escape text with numeric character references (D-115); open-space Markdown passes through unescaped | A flag (or extension-set entry) that turns LaTeX on, off by default; `DART/controls/markdown.dart` |
| A partial `MarkdownStyleSheet` replaces the theme's text styles instead of merging; links default to `Colors.blue` (U22, D-117, F28) | One app style sheet whose text styles all name their colour (D-116) | Merge given styles over the theme-derived ones; links and block quotes from the colour scheme; `DART/utils/markdown.dart` |
| A `NavigationBar` lives on its `View`, so with one View per drill level it moves with every pushed page (U23, D-149) | The bar on tab roots only (D-144) | A shell that keeps one bar outside the `Navigator` while `manage_views` Views push and pop, like go_router's `ShellRoute`; `FLET/components/router.py` and the Dart page |
| A replaced session is closed but not unmounted: effect cleanups don't run and effect tasks keep running (U24, D-149, F30) | `page.on_close` sets `svc.closed`, which every long-running loop checks (D-147) | On close, unmount the component tree (run cleanups, cancel effect tasks) and stop rendering after `detach`; `FLET/messaging/session.py`, `flet_dart_bridge_server.py` |
| `Page.on_platform_brightness_change` hands the handler a plain `ControlEvent` (the brightness name as `data`), not the typed `PlatformBrightnessChangeEvent`; and Flet removes its boot screen when the page arrives, before `main()`'s first patch, so the default View shows for a frame (U25, D-161, F35, F36) | Read `page.platform_brightness` in the handler; `ft.run(main, before_main=...)` gives the default View the boot colour | Send `{"brightness": name}` from `flet_backend.dart`; keep the boot screen until the first patch after `main()` (`DART/flet_backend.dart`, `FLET/messaging/flet_dart_bridge_server.py`) |
| Multi-weight families in `page.fonts` (one static file per family, no weights) (U20, D-98) | Declare the Roboto 400/500/700 family through `[tool.flet.flutter.pubspec]` (F18), verified in S5 (D-26) | `page.fonts` accepting a family with weighted files; schedule it only if S5 shows the pubspec route fails |
| An `async def` `use_effect` cleanup is cancelled before it starts on a dependency change (F2) | Sync cleanups only (D-70 rule 3) | In the setup branch, cancel only the previous setup task, so async cleanups run |
| `flet debug android\|ios --show-devices` exits with "Device ID must be specified": `check_device_id()` runs before the `--show-devices` branch (flet-cli `commands/debug.py:108-110`) | `flet devices` | Run the device check after that branch |
| No public way to bind `ft.context.page` outside a session: `_context_page` (`flet/controls/context.py:212`) is private, and Flet's own pytest plugin sets it directly (#160) | `tests/fakes.py`'s `bound()` sets the private ContextVar, checked against the pin | A context manager such as `ft.context.bind_page(page)` that the pytest plugin uses too |
| `flet_app` docstring (`flet/pytest_plugin.py:132`) says the bound page is the tester session, but in device mode `flet_app.page` raises `RuntimeError` | Flows use `flet_app.tester` only ([`testing-and-quality.md`](testing-and-quality.md) §5.1) | Fix the docstring |

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


REMINDERS = available("flet_local_notifications")  # E3; module name from #6948
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
- Each item is an `upstream` issue here, linking the flet-dev issue or PR. It goes in the milestone of the phase that needs it (D-89); items whose app need is "later" or "never" have no milestone until a phase adopts them. App issues that wait on it are `blocked`, and the interim ships meanwhile (D-97). Spikes S6 and S8 are `Spike:` issues labelled `test`, with verdicts in `docs/spikes/` (D-91).

### 2.3 Developing against an unreleased piece (D-81, F18)

Until 1.1.0 is on PyPI, the app builds against the monorepo at a pinned commit: the git-ignored `.flet-src` checkout at the SHA in `.flet-ref` ([`development.md`](development.md) §2.2). A first-party extension from the monorepo is taken from that same checkout, never from a live working copy, so development and `flet build` use the matching Python and Dart code. List it in `[project].dependencies`, then add one line to each of the two **existing** tables in `pyproject.toml`:

```toml
[tool.uv.sources]   # existing table: the development venv
flet-local-notifications = { path = ".flet-src/sdk/python/packages/flet-local-notifications", editable = true }

[tool.flet.dev_packages]   # existing table: what flet build bundles
"flet-local-notifications" = ".flet-src/sdk/python/packages/flet-local-notifications"
```

- `dev_packages` only rewrites names already listed in the dependencies (`CLI/build_base.py:2616-2641`), and relative paths resolve against the project root. A missing path is passed through as `name @ path`, which pip rejects.
- Without the `[tool.uv.sources]` line, uv would resolve the unrelated PyPI `flet-local-notifications` (§6), which pins `flet==0.28.3`.
- Never add a second `dev_packages` key under `[tool.flet]`: the table already exists, and TOML forbids defining it twice.

flet-cli run from a source checkout already uses the local build template and overrides the Dart `flet` package with the monorepo path (F18). Moving the pin is its own PR (D-92).

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
| Registration | `flet build` copies each bundled `flutter/<pkg>` and adds it as a path dependency (`CLI/build_base.py:2032-2078`). The app needs no pubspec edits. |

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
| Serves | NOTIF-05 (fixed conference moments), NEW-05 (reminders before saved sessions), NOTIF-01 and STORE-10 (reminder settings), NOTIF-06 (permission in context), NOTIF-10 (the permission card), DEV-06 (test reminder), NATIVE-06 (declarations). Taps open NEW-07 paths. |
| Interim (D-60) | • Settings › Reminders shows "Reminders aren't available in this build", with no live switches.<br>• Now's "Your next session" covers the app being open, and so does an in-app `Banner` with "Open" and "Dismiss" 10 min before a saved session.<br>• `.ics` with a `VALARM`: "Remind me" on session detail and "Add all to calendar" in My schedule (`core/ics.py`, D-62). |
| Upstream | Two parts:<br>(a) The official local-notifications extension from [flet-dev/flet#6948](https://github.com/flet-dev/flet/issues/6948), opened by Feodor Fitsner on 2026-10-10. Its v1 scope is `initialize`, `request_permission`, `get_permission_status`, `show`, `cancel`, `cancel_all`, `get_launch_details` and `on_notification_tap`. **Scheduled and periodic notifications are explicitly out of v1.**<br>(b) Our follow-up PR "scheduling", built on v1. |
| Dart packages | `flutter_local_notifications` **22.3.1** (BSD-3; 2026-09-13; minSdk 24; iOS pod 13.0) with `timezone` **0.11.1**. Flet 1.1 (Flutter 3.47.7, AGP 8.13.2, default minSdk 24) meets every minimum. |
| Python package | Per #6948: dist `flet-local-notifications`, module `flet_local_notifications`, class `LocalNotifications`. **Both `flet-local-notifications` and `flet-notifications` are taken on PyPI** by unrelated projects (§6). The dist name is the Flet team's call; our code changes in `capabilities.py` and `services/reminders.py` only. |
| Ownership | The Flet team owns v1; U adds scheduling on top, with no fork or competing package (D-97, D-99). The old `ndonkoHenri/notifications` branch (`awesome_notifications`) is not a base. |
| Effort | M for scheduling (Dart service, Python API, Android module or CLI hook, tests), plus S6. U7 belongs to v1. |
| Gate | `capabilities.REMINDERS`. The dependency is added only once the pinned Flet contains the scheduling PR, in the dependency PR just before adoption, so a v1-only package never turns the capability on. |

**Python API added by the scheduling PR** (proposed; v1 members omitted):

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
```

**Semantics.**
- **Time.** A one-shot reminder needs only an instant: Dart parses the ISO string and schedules `tz.TZDateTime.from(instant, tz.UTC)`, with no device time-zone lookup. DST is resolved in Python, where `at` is built in the conference zone (D-43). Repeating schedules, which would need an IANA zone, are out of scope.
- **Ids** are deterministic 32-bit ints. A session reminder uses the numeric session id (schedule 1–1147, open spaces 9025–9177), or 1,000,000 + crc32(id) % 1,000,000 for synthetic ids (`reminder_id()`, architecture §14.1). Event reminders use 8000–8099. The test reminder (DEV-06) uses 8999, as Ionic did. A unit test checks a year's plan for collisions. Because `apply()` cancels everything, a re-plan can remove a pending test reminder; that is acceptable for a developer tool.
- **Taps.** `on_notification_tap` (v1) and `get_launch_details()` (v1, for cold start) deliver `payload`. The app puts the deep-link path there (`/my-schedule/session/<id>`) and navigates as for a link (D-21).
- **Inexact by default** (D-59). Android 14+ does not grant exact alarms to new installs, and inexact delivery is usually within minutes. Exact timing is opt-in, only if S6 shows inexact delivery is too late. In that case, declare `SCHEDULE_EXACT_ALARM` and check it with `flet_permission_handler.Permission.SCHEDULE_EXACT_ALARM` (exists), rather than adding a new API.
- **Limit.** iOS keeps 64 pending requests, so the app schedules at most the next 60 (D-59).

**App side** (`services/reminders.py`; `plan()` is pure and tested without Flet):

```python
"""Local reminders: schedule the plan with E3, or keep the interim (D-58..D-60)."""

from dataclasses import dataclass
from datetime import datetime

from pycon_us import capabilities

MAX_PENDING = 60  # iOS keeps 64 pending requests (D-59)

_service = None  # the E3 service once start() built it; None means the interim (D-60)


@dataclass(frozen=True)
class Reminder:
    """One planned notification."""

    id: int
    at: datetime  # aware, in the conference zone
    title: str
    body: str
    route: str  # deep-link path opened on tap


def start() -> bool:
    """Build the E3 service when this build has it.

    App calls this once, inside its page context. Only this module imports the
    extension (§2.1). Returns False when the interim is all there is.
    """
    global _service
    if not capabilities.REMINDERS:
        _service = None
        return False
    import flet_local_notifications as fln  # module name from #6948

    _service = fln.LocalNotifications()
    return True


async def apply(plan: list[Reminder]) -> None:
    """Cancel every pending reminder, then schedule the plan ("cancel all, reschedule")."""
    if _service is None:
        return
    await _service.cancel_all()
    for r in plan[:MAX_PENDING]:
        await _service.zoned_schedule(r.id, r.title, r.body, r.at, payload=r.route)
```

`apply(plan)` (D-59) re-runs whenever favourites, reminder settings or the feed change, so a moved session moves its reminder. App calls `reminders.start()` and `reminders.apply()` and never imports the extension.

**Platform setup.**

| Platform | Entry | How | Status |
|---|---|---|---|
| Android | Core library desugaring | `flutter_local_notifications` requires `isCoreLibraryDesugaringEnabled` and `coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.4")` in the **app** module, even when nothing is scheduled. The template sets Java 17 and no desugaring (`TPL/android/app/build.gradle.kts:65-68`), and no CLI option adds it. **U7** (§5.10) is therefore a prerequisite of #6948 v1, not only of scheduling. | missing (U7) |
| Android | Receivers and the boot permission (scheduling only) | `ScheduledNotificationReceiver`, `ScheduledNotificationBootReceiver` (boot actions `BOOT_COMPLETED`, `MY_PACKAGE_REPLACED`, `QUICKBOOT_POWERON`) and `RECEIVE_BOOT_COMPLETED`. The plugin's manifest has only `VIBRATE` and `POST_NOTIFICATIONS` (22.3.1 archive), and the template has no `<receiver>` hook. **Preferred:** the extension ships an Android library module declaring them, merged by Gradle. Flet extensions are plain Dart packages, so this needs a `flutter: plugin: platforms: android:` pubspec entry (with a no-op `pluginClass` if flutter_tools insists) and `"android/**"` in package-data. **Fallback:** a `[tool.flet.android.receiver]` table rendered like `provider` (`TPL/.../AndroidManifest.xml:67-71`). S6 decides. | missing |
| Android | `POST_NOTIFICATIONS` (API 33+) | The plugin's manifest merges it. We also declare it explicitly so the app's manifest is self-describing: `[tool.flet.android.permission] "android.permission.POST_NOTIFICATIONS" = true` (exists, `CLI/build_base.py:1259`). | exists |
| Android | Exact alarms | Not declared by default (inexact). Declare `SCHEDULE_EXACT_ALARM` only after S6; never `USE_EXACT_ALARM`, which is for alarm and calendar apps. | n/a |
| Android | R8 in release builds | The plugin serialises scheduled notifications with GSON. The template's default rules include `-keepnames class * { *; }`, and `[tool.flet.android] proguard_rules = [...]` (a list appended to the defaults; exists, `CLI/build_base.py:1267-1270`) can append GSON keep rules. `proguard_default_rules = false` drops the defaults. S6 tests a **release** build: schedule, reboot, fire. | verify in S6 |
| Android | Small icon | `@mipmap/ic_launcher` (in the template). A monochrome icon needs a drawable resource hook; later. | exists |
| iOS | Permission | Request through the extension's `request_permission()` (v1). The template's permission_handler macros have no notifications entry (F17), so not through `flet-permission-handler`. | v1 |
| iOS | Notification delegate | The plugin README requires `UNUserNotificationCenter.current().delegate = self` in `AppDelegate`, for taps and foreground presentation. The template's `AppDelegate.swift` is stock and does not set it, and the plugin does not set it either (checked in 22.3.1). **#6948 v1 must solve this** for `on_notification_tap` to work on iOS: either a template line or a delegate set from the extension's iOS side. | missing (v1) |

**Spike S6** (during P1, upstream track; PLAN §8). The question: can a release build deliver reminders reliably when the app isn't running? On the iPhone and an Android emulator (D-102): schedule 2 min ahead and kill the app; lock the screen; reboot (the emulator); deny notifications, and exact alarms (the emulator, Android 14+); tap from a cold start; plan more than 64 candidates (iPhone); move a saved session in a fixture feed and check that its reminder moves. The verdict decides the Android receiver approach, whether exact alarms are worth it, and the GSON rules.

**Tests.**
- **Extension:** `zoned_schedule` at now + 70 s appears in `get_pending`, and `cancel` removes it; a naive `at` raises `ValueError`; the instant is exact across the 2027-03-14 US DST change; scheduling works on an API 34 emulator with exact alarms denied.
- **App:** unit tests for the pure `plan()` (past instants skipped, the cap of 60, deterministic ids, lead times); `apply()` against a fake service set as `_service`; `start()` picks the interim when not embedded.

**Upgrade** (§2.4, plus):
1. After the pin PR for the Flet release, or commit, that contains #6948 v1 and the scheduling PR, a separate dependency PR adds the extension's exact pin. The adoption PR then adds `POST_NOTIFICATIONS` and anything else S6 required.
2. Settings › Reminders switches become live, and the permission card appears (NOTIF-01, NOTIF-06, NOTIF-10).
3. The in-app `Banner` stays for the foreground, and the `.ics` actions stay.
4. Run the P2 exit check: a reminder fires with the app killed (the iPhone and an Android emulator) and after a reboot of the emulator, and a tap opens the session.

### 4.2 E1: barcode scanner (priority 4; the staff showcase)

| Field | Value |
|---|---|
| Serves | LEAD-01 (the shared scan screen), LEAD-02 (camera permission), DOOR-04, SHIRT-02, MASK-04, NATIVE-06 |
| Interim (D-65) | Manual entry on the shared scan screen: a `TextField(on_submit=...)` taking the full `code:validator` payload, typed, pasted or sent by a USB/Bluetooth HID scanner, with focus kept. It **always** ships; the camera is added on top when E1 is bundled, and the companion app says "Camera scanning isn't available in this build". |
| Upstream | A new extension. Proposed dist `flet-barcode-scanner` (free on PyPI), module `flet_barcode_scanner`, control `BarcodeScanner`. |
| Dart package | `mobile_scanner` **7.4.2** (BSD-3; 2026-09-14; Dart `^3.7.0`, Flutter `>=3.29.0`; Android `minSdk 23`, CameraX and ML Kit; iOS pod 12.0, Apple Vision). |
| Gate finding | `mobile_scanner` imports `package:flutter/material.dart` in `mobile_scanner.dart` and `mobile_scanner_preview.dart`. The default error and placeholder widgets use `Colors.black`, `Icons.error`, `Icon` and `Text`. The extension must pass its own `errorBuilder` and `placeholderBuilder` (built from `widgets.dart`), so no SDK-Material widget is ever built. The §3 gate test proves it. |
| Effort | M, plus S8 |
| Gate | `capabilities.SCANNER` |

**Python API** (proposed). It is declarative: torch and pause are properties, not imperative toggles, which fits components mode.

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


@ft.control("BarcodeScanner")
class BarcodeScanner(ft.LayoutControl):
    """A live camera preview that reports detected barcodes."""

    formats: list[BarcodeFormat] = field(default_factory=lambda: [BarcodeFormat.QR_CODE])
    paused: bool = False  # True stops analysis and releases the camera
    torch: bool = False
    on_detect: Optional[ft.EventHandler[BarcodeDetectEvent]] = None
    on_error: Optional[ft.ControlEventHandler["BarcodeScanner"]] = None  # e.data is the message

    async def analyze_image(self, path: str) -> list[str]:
        """Decode the barcodes in an image file (lets device tests check decoding without pointing a camera at a badge)."""
        return await self._invoke_method("analyze_image", {"path": path})
```

**Dart side.**
- `MobileScannerController(formats:, detectionSpeed: DetectionSpeed.normal, autoStart: !paused)` is created in `initState`.
- `didUpdateWidget` maps `paused` to `stop()`/`start()`, and calls `toggleTorch()` when `torch` differs from the controller's torch state.
- `onDetect` calls `triggerEvent("detect", {"raw_value": ..., "format": ...})` for the first barcode in the capture.
- `useAppLifecycleState` stays on, so the camera is released in the background.

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
| both | Camera permission and usage string | `[tool.flet] permissions = ["camera"]` emits `NSCameraUsageDescription` and `android.permission.CAMERA` (`CLI/build_base.py:254`). Override the iOS string with staff-scanning wording in `[tool.flet.ios.info]`. |
| both | Runtime prompt in context (D-61) | `ph = fph.PermissionHandler()`, then `await ph.request(fph.Permission.CAMERA)`. If the result is `PermissionStatus.PERMANENTLY_DENIED`, show "Camera access is off" with "Open settings" (`await ph.open_app_settings()`) and "Enter codes instead". |
| both | Keep awake while scanning | `ft.Wakelock().enable()` / `disable()` (coroutines) |
| Android | ML Kit model | Keep the bundled model (+3–10 MB), so scanning works offline on first use. The unbundled variant (`[tool.flet.android.gradle_properties] "dev.steenbakker.mobile_scanner.useUnbundled" = "true"`, exists) downloads the model through Play Services, which is not wanted on conference Wi-Fi. |
| iOS | Minimum OS | Pod 12.0, below the template's 15.0, so U12 is not needed. |

**Spike S8** (before P3, upstream track). Build the smallest extension (one control, `on_detect`, torch) as release builds for Android and iOS. On the iPhone, test a printed QR in daylight and dim light, repeated detections, permission denied, background and resume. On an Android emulator, test a QR image in the virtual scene camera, repeated detections, permission denied, background and resume (no torch or lighting conditions; D-102). Test the companion app's fallback to manual entry too. The verdict decides whether E1 goes ahead and settles its API.

**Tests.**
- **Extension:** the gate test (§3); `analyze_image` on bundled PNGs of mock badges returns the exact payload; pause and resume 50 times with no camera leak (no CameraX errors in logcat, on the emulator); the torch toggles (on the iPhone; Android's torch waits for a borrowed phone, D-102); a denied permission fires `on_error` and nothing crashes.
- **App:** the P3 exit criterion, a printed sheet of mock badges scanned on the iPhone (on Android, the badge images through an emulator's virtual scene camera), including two devices checking in the same attendee (PLAN §7).

**Upgrade** (§2.4, plus):
1. Add the exact pin and `permissions = ["camera"]`.
2. The camera area appears on the scan screen. Manual entry stays reachable on every tool.

### 4.3 E4: native add-to-calendar (later)

| Field | Value |
|---|---|
| Serves | SESS-04 |
| Interim | `.ics` through `await ft.Share().share_files([ft.ShareFile.from_bytes(ics, mime_type="text/calendar", name=f"{slug}.ics")])`, for one session or all of My schedule (SESS-05, D-62). It stays as "Share as file" after the upgrade. |
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

**Upgrade** (§2.4, plus): the pinned Flet must contain U6; add the `<queries>` intent (§5.9) and the iOS usage strings to `[tool.flet.ios.info]`. Session detail's "Add to calendar" calls `add_event`, and the `.ics` action stays as "Share as file".

**Tests:** the editor opens pre-filled on an Android emulator and an iOS simulator; a cancelled editor returns False; with no calendar app it returns False and the app offers "Share as file".

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

Each is a PR to flet-dev/flet with a CHANGELOG entry, docs and integration tests, following the monorepo skills (`write-changelog-entry`, `create-flet-control-integration-tests`, `docs-conventions`).

### 5.1 U1: `ft.RefreshIndicator` (priority 2; S)

| Field | Value |
|---|---|
| Serves | DATA-03, SCHED-13, EVT-07, SPON-08 |
| Interim | The `StatusStrip` (D-32) shows Refresh while data is stale, offline or refreshing. Settings › Data and the Developer screen have "Refresh now". All call `Conference.start_refresh(svc.storage, svc.year)` (architecture §6.2, D-145), which keeps the cache on failure (D-39). Automatic refresh runs on start, on resume when the data is older than 15 min, and every 15 min while Now or Schedule is visible (D-40). |
| Today | Absent (F8). |
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

**Upgrade.** The app's list scaffold wraps its list in `RefreshIndicator(on_refresh=...)`. The StatusStrip keeps its Refresh button, because pull-to-refresh is not discoverable by screen-reader users (D-33), and Settings › Data keeps "Refresh now".

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
| Interim | `pycon_us.__version__`, kept equal to `[project].version` by a unit test, plus the build number (D-83). `importlib.metadata` cannot see the app in packaged builds (F15). |
| Today | Absent. `package_info_plus: ^9.0.0` is already in `packages/flet/pubspec.yaml`, unused (latest 10.2.2); add the case next to `get_device_info` (`DART/controls/page.dart:338`). In the companion app it would report the companion's version, so the app uses it only when `is_embedded()`. |

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

**Upgrade.** About this app reads `version` and `build_number` from `await page.get_app_info()` when embedded, and the PR deletes the build-number constant. **Test:** on the flet test host, the result equals `--build-version`/`--build-number` and the bundle id.

### 5.4 U16 + U17: text scale and accessibility changes (priority 6; XS, one PR)

| Field | Value |
|---|---|
| Serves | THEME-11 (text at 200 %), THEME-09 (reduced motion), the high-contrast switch default (D-23) |
| Interim | Fluid layouts with no fixed heights around text (D-26). Accessibility features are read with `SemanticsService.get_accessibility_features()` at start and on resume (F13, D-34). |
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

**Upgrade.** `Prefs` reads these from `page.media` at start and follows `page.on_media_change`, replacing the resume re-read, so reduced motion and the high-contrast default follow live.

**Test.** Changing the font size or "Remove animations" in the emulator's settings fires `on_media_change` with the new values.

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

- **Serves:** EXPO-05 (zoom to booth).
- **Interim:** the booth is selected and highlighted and its card shown, without moving the camera.
- **Today:** `zoom(factor)` and `pan(dx, dy, dz)` are relative, instant and clamped (`FLET/controls/core/interactive_viewer.py:230`, `:246`). Only `reset(animation_duration)` animates (`:195`). `save_state`/`restore_state` store one matrix.
- **Change:** set the `TransformationController` value directly, animating with a `Matrix4Tween` when a duration is given, as `reset` does.

```python
# Proposed on ft.InteractiveViewer:
#     async def set_transform(self, scale: ft.Number, offset: ft.OffsetValue,
#                             animation_duration: Optional[ft.DurationValue] = None) -> None: ...
#     async def zoom_to_rect(self, rect: ft.Rect, padding: ft.Number = 0,
#                            animation_duration: Optional[ft.DurationValue] = None) -> None: ...
```

`zoom_to_rect` fits a content-space rectangle in the viewport, clamped to `[min_scale, max_scale]`. **Upgrade:** the floor plan calls `zoom_to_rect(booth_rect, animation_duration=...)`, with `None` under reduced motion.

### 5.8 U9: `ft.use_route_search()` (later; XS)

- **Serves:** ROOM-03 (`?highlight=`), SPON-04 and EXPO-05 (`?booth=`).
- **Interim:** `use_query()` in `locations.py` (D-163) parses the query from `page.route` once, when its View mounts, and only for the top View (`is_top_view(page.route, ft.use_view_path())`; `use_route_location()` is the opener's location for the Views under a global modal).
- **Today:** `LocationInfo.search` is populated without the leading `?` (`FLET/components/router.py:112-123`, `:725`) but not exposed by a hook.
- **Change:** `def use_route_search() -> str`, next to `use_route_location()` (`router.py:357`), exported as `ft.use_route_search`.
- **Upgrade:** `use_query()` becomes `dict(parse_qsl(ft.use_route_search()))`. Its callers do not change.

### 5.9 U6: Android `<queries>` (only with E4; S)

- **Today:** the template has one fixed `<queries>` entry (`PROCESS_TEXT`, `TPL/android/app/src/main/AndroidManifest.xml:83-88`) and no hook.
- **Change:** render extra intents from pyproject:

```toml
[[tool.flet.android.queries.intent]]
action = "android.intent.action.INSERT"
data = { mimeType = "vnd.android.cursor.item/event" }
```

- **Test:** the manifest-merger report contains the intent. Without the table, the manifest is byte-identical to today.

### 5.10 U7: core library desugaring (with E3; S)

- **Today:** `compileOptions` sets Java 17 with no desugaring (`TPL/android/app/build.gradle.kts:65-68`). None of the existing `:app` options (`min_sdk_version`, `gradle_properties`, `proguard_rules`, signing, splits) enables it.
- **Change:** `[tool.flet.android] core_library_desugaring = true` (plus a CLI flag) renders `isCoreLibraryDesugaringEnabled = true` and `coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.4")`.
- **Alternative for the Flet team:** enable it unconditionally in the template. It is harmless for apps that don't need it, and it removes a knob.
- **Scope:** if S6 picks the fallback for E3's receivers, this PR also adds a `[tool.flet.android.receiver]` table, rendered like `provider`.
- **Test:** `flet build apk` of an app using `flutter_local_notifications` 22.3.1 fails without the setting and succeeds with it.

### 5.11 U12 and U13 (conditional)

- **U12, iOS deployment target: not needed.** The template's 15.0 floor (D-12) is above every pod we wrap: `mobile_scanner` 12.0, `flutter_local_notifications` 13.0, `add_2_calendar` 11.0 (§6). Reopen it only if a new dependency needs more.
- **U13, app privacy manifest:** only if the S5 TestFlight upload reports ITMS-91053. The change would ship `Runner/PrivacyInfo.xcprivacy` in the template, declaring the required-reason APIs that embedded CPython and `shared_preferences` use, with the reasons reviewed by the Flet team.

### 5.12 U18: Back inside a modal sub-chain (later; XS)

- **Serves:** NEW-02 (search, D-19): Back from a result pushed over the global modal `/search` must return to the results.
- **Today:** while a modal route is anywhere in the matched chain, the stock pop handler navigates to the modal's base location, even for a pop from a view pushed over the modal (`FLET/components/router.py`, modal branch of the `on_view_pop` handler; F6). An app's own `page.on_view_pop`, set before the Router mounts, receives every pop instead.
- **Interim:** `main()` sets `page.on_view_pop` to navigate to `parent_of(e.route, memory.search_base)` (architecture §5.3).
- **Change:** pop to the previous view entry's resolved pathname unless the popped view is the modal itself; only then go to the modal's base.
- **Test:** `/search` → `/search/session/42` → Back lands on `/search`; Back again lands on the base.
- **Upgrade:** after the pin bump, delete the app's `on_view_pop` handler. `parent_of()` stays for the back arrow (D-10).

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

**Flet toolchain:** Flutter 3.47.7 (`.fvmrc`), whose default Android `minSdkVersion` is 24 and `compileSdkVersion` 36; AGP 8.13.2 and Gradle 9.3.1 in the template. Every package above fits.

**PyPI names** (`pypi.org/pypi/<name>/json`):
- **Taken:**
  - `flet-local-notifications` (1.2.2, 2026-07-11, unrelated, pins `flet==0.28.3`);
  - `flet-notifications` (0.1.0, published 2026-10-11, `Nwokike/flet-notifications`).
- **Free:** `flet-barcode-scanner`, `flet-mobile-scanner`, `flet-add-to-calendar`, `flet-html`, `flet-firebase`.
- `flet` and the first-party extensions (`flet-secure-storage`, `flet-permission-handler`, `flet-camera`) are 1.0.4.

**GitHub:**
- [flet-dev/flet#6948](https://github.com/flet-dev/flet/issues/6948): an open **issue**; no implementation PR found.
- [flet-dev/flet#6953](https://github.com/flet-dev/flet/pull/6953): an open PR (branch `fix/deep-linking-fallback`, closes #6951) touching `build_base.py`, its tests and the changelog.

**Local SDK: exists** (beyond what PLAN's F-facts cover): `flet.utils.is_embedded`; `ft.Service`, `ft.LayoutControl`, `ft.control`, `ft.value`, `ft.Event` (fields `name`, `data`, `control`); `ft.PageMediaData` (six fields) and `page.on_media_change`; `ft.LocationInfo(pathname, search, hash)`; `flet_permission_handler.Permission.CAMERA`/`NOTIFICATION`/`SCHEDULE_EXACT_ALARM`; and the CLI keys `[tool.flet] permissions`, `dev_packages`, and `[tool.flet.android]` `permission`, `gradle_properties`, `proguard_rules`, `provider`.

**Local SDK: absent.**
- Core: `ft.RefreshIndicator`, `ft.use_route_search`, `ft.AppInfo`, `Page.get_app_info`, `AppBar.bottom`, any sliver or grouped list control, `ft.CarouselView`, an `Html` control, an error hook.
- `PageMediaData.text_scale_factor` and any accessibility-change event.
- Packages: any local-notifications or barcode package in `sdk/python/packages/`.
- Template and CLI: iOS entitlements, an Android `<queries>`/`<receiver>` hook, desugaring.

---

## 7. Open points

Tracked by `upstream` issues; none needs a decision here:
1. **E3 package name:** both `flet-local-notifications` (#6948's proposal) and `flet-notifications` are taken on PyPI; the Flet team picks.
2. **iOS notification delegate** is missing from the stock `AppDelegate.swift`; for #6948 v1, verified in S6.
3. **U16 and U17 as one PR** through `PageMediaData` and the existing `on_media_change`, instead of a separate `SemanticsService` event.

Resolved on 2026-10-11 and applied to PLAN, the decisions record and the matrix: U7 is needed by #6948 v1 itself (PLAN §6); D-64 now reads "replaced only after a PR bumps the pinned Flet; the swap is its own tested PR"; the Developer screen shows capability flags read-only (D-73), so there are no force-interim switches; notification permission goes through E3's `request_permission()` (D-61, NOTIF-06, NATIVE-06); NATIVE-02 no longer depends on U12; NOTIF-10 depends on E3.
