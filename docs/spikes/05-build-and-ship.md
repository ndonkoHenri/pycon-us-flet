# S5: Can we build and ship internally from the pinned Flet 1.1?

**Spike:** S5 ([#51](https://github.com/ndonkoHenri/pycon-us-flet/issues/51), PLAN §8). **Date:** 2026-10-11/12, about 1.5 hours of builds on one Mac.
**Decides:** D-104 (pin source), D-105 (Roboto), D-106 (Android outputs), D-107 (reference devices). **Follow-ups:** [#120](https://github.com/ndonkoHenri/pycon-us-flet/issues/120) (pin bump), [#121](https://github.com/ndonkoHenri/pycon-us-flet/issues/121) (iPhone session).

## Question

Can we build Android and iOS artifacts for internal testing from the pinned Flet 1.1 source checkout (D-81), run the development loop on an emulator and a simulator, bundle Roboto 400/500/700 (D-26), and get a build to TestFlight?

## Answer: partly

- **Not from today's pin.** `.flet-ref` (`3710aff7f2a8`) is on flet-dev/flet `main`, which is still Flet 1.0.4 plus fixes. Android builds, but iOS fails on Xcode 27 because the template targets iOS 13.0 (F20). Flet 1.1 lives on the `flet-1.1.0` branch.
- **Yes from the `flet-1.1.0` branch** (`15854a0ac612`, the branch tip on 2026-10-11):
  - `flet build apk`, `aab`, `ios-simulator` and `ipa` all work. A signed `.ipa` comes out whenever an App Store profile is installed.
  - `flet debug android` and `flet debug ios` work.
  - A companion client built from `client/` talks to the pinned Python, with Python hot reload, on both the emulator and the simulator.
  - So D-104 moves the pin to that branch (#120).
- **Roboto works, but not the way D-26 described.** A `flutter.fonts` entry whose assets point outside the generated Flutter project (`../../src/assets/fonts/…`) silently falls back to SF Pro on iOS. A font-only local Flutter package added through `[tool.flet.flutter.pubspec.dependencies]` renders all three weights on iOS and Android (D-105).
- **TestFlight is not done.** No App ID, App Store profile or App Store Connect record exists for our bundle id, and creating them is owner-only (D-101). The upload, the ITMS-91053 check and the iPhone install moved to #121.

## Method

- **Host:** MacBook with Apple M4 (10 cores, 24 GB), macOS 27.0 (26A428), Xcode 27.0 (27A266a), CocoaPods 1.17.0 (it warns unless `LANG=en_US.UTF-8`), uv 0.12.15.
- **Devices (D-107):**
  - AVD `pycon_pixel6a_api36`: Pixel 6a profile, 4 GB RAM, Android 16 (API 36), Google APIs arm64, emulator 36.2.12.0, as `emulator-5554`.
  - Simulator iPhone 17 on iOS 26.5 (23F77). On this Mac the iPhone 16 family exists only on the iOS 18.6 runtime.
- **Repo:** the app at `9040d16`, with `src/` unchanged (a `Text` with the version). Build number `8` (`git rev-list --count HEAD`).
- **The 1.1 runs:** a scratch copy of the repo whose `.flet-src` was a fresh `git clone --filter=blob:none` of flet-dev/flet at `15854a0ac`. Its `uv lock` added `resvg-py` (a new flet-cli dependency).
- **The fonts reproducer:** the copy's `src/main.py` was replaced with the screen below. Nothing from either copy is committed.
- **Downloads:**
  - bundletool 1.18.3 from its GitHub release (sha256 `a099cfa1…0e29`).
  - Roboto v2.138 `roboto-unhinted.zip` from the googlefonts/roboto GitHub release (Apache-2.0, sha256 `70f64c71…a728`).
- **Not done:** no upload anywhere, and nothing created in the Apple portal or App Store Connect. Screenshots stayed in the session scratchpad, not in the repo.

## Evidence

### Toolchain

| Item | Pin `3710aff` (`main`) | Candidate `15854a0ac` (`flet-1.1.0`) |
|---|---|---|
| `uv run flet --version --json` | `"flet": "1.0.4", "flutter": "3.44.8"` | `"flet": "1.0.4", "flutter": "3.47.7"` |
| Flutter, as flet-cli gets it | `.fvmrc` 3.44.8. The `flutter` on `PATH` (fvm, 3.47.7) fails flet-cli's major.minor check, so flet-cli downloaded 3.44.8 into `~/flutter/3.44.8` (about 5 min) | `.fvmrc` 3.47.7 matches the fvm `flutter` on `PATH`, so that one is used as is |
| JDK | flet-cli's own `~/java/17.0.13+11`, set with `flutter config --jdk-dir` (a global Flutter setting); the system JDK is 25 | same |
| Android SDK | `~/Library/Android/sdk`: build-tools 34/35/36, platforms 34-36, cmdline-tools `latest`, adb 36.0.0 | same |
| Gradle, AGP, Kotlin | 8.14, 8.11.1, 2.2.20 | 9.3.1, 8.13.2, 2.3.21 |
| Python in the app | CPython **3.14.7** (`serious_python` 5.0.0, python-build `20260921`; `lib/<abi>/libpython3.14.so`) | CPython **3.14.7**, also shown on screen ("Python 3.14.7 on android", "… on ios") |
| `flet.__version__` | packaged app: `0.1.0`; host: `1.0.4` | the same, shown on screen |

### Android

| Check | Pin `3710aff` | Candidate `15854a0ac` |
|---|---|---|
| `flet build apk --build-number 8`, first run | **540 s**: Flutter download about 305 s, Gradle `assembleRelease` 167.6 s. `~/.gradle` was already warm from other work, so a fresh machine adds Gradle downloads. | 143 s (Flutter present; Gradle 105 s) |
| Same, warm | **63 s** (Gradle 15.8 s) | 70 s (after a pubspec change) |
| APK size (3 ABIs) | **140,418,054 bytes (140.4 MB)** | 142,499,081 bytes (142.5 MB) |
| APK with `--arch arm64-v8a` | **54,950,467 bytes (55.0 MB)**, 71 s | — |
| `aapt2 dump badging` (build-tools 36.0.0) | `minSdkVersion:'24'`, `targetSdkVersion:'36'`, `compileSdkVersion='36'`, `versionCode='8'`, `versionName='0.0.1'`, label `Conf Companion`, ABIs `arm64-v8a armeabi-v7a x86_64`, permissions `INTERNET`, `ACCESS_NETWORK_STATE` | `minSdkVersion:'24'`, `targetSdkVersion:'36'` |
| `adb install -r` + `am start -W` | Success; first launch `TotalTime: 8346` ms (Python unpacks on first launch) | Success (an update over the other build, same debug key); `TotalTime: 3226` ms |
| Screen | "PyCon US companion 0.0.1" on a lavender (tonal 1.0) background | "PyCon US companion 0.0.1" on white (1.1 neutral surfaces) |
| `flet build aab --build-number 8` | 58 s; **101,007,325 bytes (101.0 MB)** | 44 s; 102,463,862 bytes |
| bundletool `get-size total` on the emulator's device spec (arm64-v8a, 420 dpi, SDK 36) | **26,358,368 bytes (26.4 MB) download** | 26,600,984 bytes |
| bundletool `extract-apks` for that spec | 4 splits, 56,002,080 bytes on disk | 56,661,563 bytes |
| Gradle heap | `-Xmx4G` from `[tool.flet.android.gradle_properties]` reached `gradle.properties`; every Android build passed with it | same |

`minSdk 24` and `targetSdk 36` are Flutter's defaults (`FlutterExtension.kt`: `minSdkVersion = 24`, `targetSdkVersion = 36`) at both Flutter versions. 36 is the latest stable API level, so it meets Play's target-API rule (D-12).

### iOS

| Check | Pin `3710aff` | Candidate `15854a0ac` |
|---|---|---|
| `flet build ios-simulator --build-number 8` | **Fails** after 101 s: "Target Integrity (Xcode): The iOS Simulator deployment target 'IPHONEOS_DEPLOYMENT_TARGET' is set to 13.0, but the range of supported deployment target versions is 15.0 to 27.0.x." (Runner and Pods) | **131 s**; `pycon-us.app` 282 MB (a simulator debug build); `MinimumOSVersion` 15.0, `CFBundleVersion` 8, display name `Conf Companion` |
| `simctl install` + `launch` | — | Starts; "PyCon US companion 0.0.1" |
| `flet build ipa --build-number 8` without a profile | — | 152 s; the warning panel, then `--no-codesign`; `build/ipa/pycon-us.xcarchive` (Flutter reports 245.4 MB; the `.app` inside is 76 MB) |
| `flet build ipa --ios-export-method app-store-connect --bundle-id io.github.ndonkohenri.pyconus.spike` with `team_id = "VF87YBAN84"` and profile `PyCon US Spike App Store` | — | Stops after 9 s, before Xcode: "Provisioning profile 'PyCon US Spike App Store' is not installed — Xcode would fail once the build reaches signing." It lists the installed profiles. |
| Same, with a profile that is installed: `--ios-provisioning-profile "ITMS91065 Repro" --bundle-id com.flet.itms91065-repro` (an App Store profile for another of the owner's App IDs) | — | 144 s; **`pycon_us.ipa` 44,790,396 bytes (44.8 MB)**. `Authority=Apple Distribution: … (VF87YBAN84)`, `codesign --verify --deep --strict` OK, `CFBundleVersion` 8, `ITSAppUsesNonExemptEncryption` false. Not uploaded. |

**Signing material on the Mac:**
- Valid identities: "Apple Distribution" and "Developer ID Application" for team `VF87YBAN84`. The only "Apple Development" identity is revoked (`CSSMERR_TP_CERT_REVOKED`).
- No Apple ID is signed in to Xcode.
- For our team there is only the wildcard Xcode team profile (a development profile), and no App Store profile for any `io.github.ndonkohenri.*` id.
- An App Store Connect API key file is present.
- So:
  - a TestFlight build needs the owner steps in #121;
  - `flet debug ios` on the iPhone needs a new development certificate.

**Privacy manifest (ITMS-91053):**
- The generated Runner has no `PrivacyInfo.xcprivacy`. The template ships none (`TPL/ios/Runner/`).
- 17 manifests come from dependencies:
  - `Flutter.framework`;
  - OpenSSL's `_ssl.framework` and `_hashlib.framework` (FileTimestamp `C617.1`);
  - 14 plugin bundles (`shared_preferences_foundation`, `url_launcher_ios`, `device_info_plus`, …).
- `Python.framework` has none, although `nm -u` shows it imports these required-reason APIs:
  - `stat`, `fstat`, `fstatat`, `lstat` and `futimens` (FileTimestamp);
  - `statfs` and `fstatfs` (DiskSpace);
  - `mach_absolute_time` (SystemBootTime).
- So an ITMS-91053 report on upload is likely. Only App Store Connect can say, so the upload in #121 decides U13.
- U12 is **not** needed: the 1.1 template targets 15.0, and the pin's 13.0 is fixed by the pin bump, not by a configurable target.

### Roboto 400/500/700 (D-26)

| Route | Result |
|---|---|
| `[tool.flet.flutter.pubspec.flutter] fonts`, assets `../../src/assets/fonts/Roboto-{Regular,Medium,Bold}.ttf`. flet-cli writes `pubspec.yaml` into `build/flutter/`, so paths resolve from there. | The entry merges into `build/flutter/pubspec.yaml`, and `FontManifest.json` lists the three assets under their `../../src/…` keys. But on iOS the files land outside the bundle, in `build/ios/Debug-iphonesimulator/src/assets/fonts/`, so `flutter_assets` has none. The rows render in **SF Pro**, identical to the system rows. The TTFs are also copied a second time, into the Python app (`serious_python_darwin.bundle/app/assets/fonts/`). **Fails.** |
| A font-only Flutter package `flutter_packages/roboto_fonts/` (`pubspec.yaml` declaring family `Roboto` with the three weights, `fonts/*.ttf`, `LICENSE`, a one-line `lib/roboto_fonts.dart`), added with `[tool.flet.flutter.pubspec.dependencies] roboto_fonts = { path = "../../flutter_packages/roboto_fonts" }`. Used as `font_family="packages/roboto_fonts/Roboto"`. | `FontManifest.json`: family `packages/roboto_fonts/Roboto`, assets `packages/roboto_fonts/fonts/Roboto-*.ttf`, all three inside `flutter_assets` (APK: 349,400 + 350,864 + 351,108 bytes). iOS simulator: the Roboto rows are visibly Roboto, at three distinct weights, next to SF Pro rows. Android emulator: three distinct weights; the system font is also Roboto there. Also seen in `flet debug android` and `flet debug ios`. **Works.** |
| `page.fonts` | Not needed. It maps a family to a single file (U20), and the package route covers all three weights. |
| Companion client (`flet run`) | Falls back to the system font (SF Pro on iOS), as D-26 accepts. The client bundles no `roboto_fonts` package. |

The reproducer replaced `src/main.py` in the scratch copy (shown here with the family name as a constant and the project's line length):

```python
"""S5 reproducer: bundled Roboto 400/500/700 next to the system font."""

import platform
import sys

import flet as ft

ROBOTO = "packages/roboto_fonts/Roboto"
SAMPLE = "Rag 1Il0 Qy 0123 R"
WEIGHTS = [
    (400, ft.FontWeight.W_400),
    (500, ft.FontWeight.W_500),
    (700, ft.FontWeight.W_700),
]


def row(label: str, family: str | None, weight: ft.FontWeight) -> ft.Control:
    """One sample line in the given family and weight."""
    return ft.Text(f"{label}: {SAMPLE}", size=22, weight=weight, font_family=family)


def main(page: ft.Page) -> None:
    """Show each weight in Roboto, then in the system font, plus runtime facts."""
    page.title = "S5 fonts"
    page.scroll = ft.ScrollMode.AUTO
    controls: list[ft.Control] = [ft.Text("Roboto (bundled)", size=14)]
    controls += [row(f"R{w}", ROBOTO, fw) for w, fw in WEIGHTS]
    controls += [ft.Divider(), ft.Text("System font", size=14)]
    controls += [row(f"S{w}", None, fw) for w, fw in WEIGHTS]
    controls += [
        ft.Divider(),
        ft.Text(f"Python {platform.python_version()} on {sys.platform}", size=14),
        ft.Text(f"flet {ft.__version__}, embedded={ft.utils.is_embedded()}", size=14),
    ]
    page.add(ft.SafeArea(content=ft.Column(controls)))


ft.run(main)
```

```yaml
# flutter_packages/roboto_fonts/pubspec.yaml
name: roboto_fonts
description: Roboto 400/500/700 (Apache-2.0, googlefonts/roboto v2.138) for the app (D-26).
version: 0.0.1
publish_to: none
environment:
  sdk: ">=3.0.0 <4.0.0"
flutter:
  fonts:
    - family: Roboto
      fonts:
        - asset: fonts/Roboto-Regular.ttf
          weight: 400
        - asset: fonts/Roboto-Medium.ttf
          weight: 500
        - asset: fonts/Roboto-Bold.ttf
          weight: 700
```

### Development loop (candidate `15854a0ac`)

| Loop | Command | Result |
|---|---|---|
| Packaged debug, Android | `uv run flet debug android -d emulator-5554` | Works. It took 94 s from the command to the app on screen. The app is `DEBUGGABLE` with `versionCode=1` (no `--build-number`), and Roboto renders. |
| Packaged debug, iOS | `uv run flet debug ios -d E771E0A2-E987-4644-8B43-624EFC6D0775` | Works. It took 112 s to the app process on the simulator, and Roboto renders. |
| Companion client, Android | Terminal 1: `uv run flet run -r -w -p 8550` (repo root). Terminal 2: `flutter run -d emulator-5554` in `.flet-src/client` | Works. The first build took 230 s. The client logs "Page URL: http://10.0.2.2:8550" and shows the app: "Python 3.14.6 on darwin", `embedded=False`. An edit to `src/main.py` was on screen within 4 s (`-r` restarts Python; F22). |
| Companion client, iOS simulator | the same, with `flutter run -d E771E0A2-…` | Works. The first build took 115 s; "Page URL: http://localhost:8550"; the edit was on screen after the reload. |

Companion-client caveats:
- `flet run -w` opens a browser tab; `BROWSER=true` suppresses it.
- Any HTTP `GET /` fails with "Web root path not found: …/flet_web/web", because a source checkout has no built web client. The native client only uses the WebSocket, so this is harmless.
- Stopping `flet run` can leave the app's Python child process listening on port 8550. Check with `lsof -iTCP:8550` and kill it.
- `flutter run` in `client/` rewrites three tracked files in the Flet checkout: `client/ios/Podfile.lock` and two `Package.resolved` files. Restore them with `git -C .flet-src checkout -- client`.

### Other quirks

- `flet debug` hides `flutter run`'s output behind a spinner ("Running debug version of the app on iOS device..."), and logs nothing useful when stdout is not a terminal.
- Artifact names differ: `build/apk/pycon-us.apk`, `build/aab/pycon-us.aab` and `build/ipa/pycon-us.xcarchive`, but `build/ipa/pycon_us.ipa` (underscore).
- Each iOS build prints:
  - Flutter's "All plugins found for ios are Swift Packages, but your project still has CocoaPods integration" notice;
  - `flutter doctor` warnings about Android licences and a missing iOS 27.0 simulator runtime.

  None of them fails the build.
- After a font build, the simulator was found shut down once. `xcrun simctl boot <udid>` fixed it.
- `development.md` §2.1 recorded Flutter 3.47.7 and iOS 15 for "the pin". Those facts were checked at `9fbe52a61`, a local commit on the `flet-1.1.0` lineage that is not on GitHub, not at `.flet-ref`. They become true again with #120.

## Decisions changed

- **D-104** (amends D-81): until 1.1.0 is released, the pin is a commit on flet-dev/flet's `flet-1.1.0` branch. #120 bumps it.
- **D-105** (amends D-26 and section M's font location): Roboto ships as the local font-only Flutter package `flutter_packages/roboto_fonts/`. `Theme.font_family` is `packages/roboto_fonts/Roboto`.
- **D-106** (records values for D-12, sets the APK ABI): `minSdk` 24 and `targetSdk` 36. Sideload and CI APKs are built for `arm64-v8a` only; AABs keep all three ABIs.
- **D-107** (amends D-102's device names): the build reference devices are the AVD `pycon_pixel6a_api36` and an iPhone 17 simulator on iOS 26.5.

## What the next issues must apply

**#120, the pin bump (before #52):**
- Set `.flet-ref` to a `flet-1.1.0` commit, and run `uv lock`.
- Move the owner's `.flet-src` worktree to that commit (`git -C .flet-src checkout --detach <sha>`).
- Re-run `flet build apk` on the emulator and `flet build ios-simulator` on the simulator.

**P0-04, #52:**
- Add `flutter_packages/roboto_fonts/`: `pubspec.yaml` as above, the three TTFs from googlefonts/roboto v2.138, its `LICENSE`, and `lib/roboto_fonts.dart`. Add the `[tool.flet.flutter.pubspec.dependencies]` entry, and a Roboto line in `NOTICE`.
- Add `[tool.flet.ios] team_id = "VF87YBAN84"` and the two export-method tables (development.md §8.2). The profile names wait for the owner steps in #121.
- Leave `min_sdk_version` and `target_sdk_version` unset; the defaults are 24 and 36.
- Keep the `-Xmx4G` Gradle override. It was enough on the Mac; the runner check is P0-06's.

**P0-05, #53 (`docs/development.md`):**
- §2.1:
  - the pin's branch;
  - Flutter 3.47.7 (flet-cli takes any 3.47.x `flutter` on `PATH`, otherwise it downloads `~/flutter/<version>`);
  - JDK 17.0.13 under `~/java`;
  - minSdk 24 and targetSdk 36;
  - CPython 3.14.7.
- §3.4: replace the Roboto row with D-105's package route.
- §5.2: the exact companion-client commands, `BROWSER=true`, the "Web root path not found" message, the leftover port-8550 process, and the `git -C .flet-src checkout -- client` clean-up.
- §5.3:
  - `flet debug` shows no `flutter run` output;
  - the debug build's `versionCode` is 1;
  - on-device iOS debugging needs a valid Apple Development certificate (none on the Mac today).
- §8.2: the `.xcarchive` and `.ipa` outcomes, flet-cli's profile pre-check, and the `pycon_us.ipa` name.
- §10: close the S5 rows with these numbers.
- D-107's device names, and fix "iPhone 16 family" in §5.5.

**P0-06, #54 (`build-android.yml`):**
- `extra-args: --arch arm64-v8a` (D-106): 55 MB instead of 140 MB per artifact.
- Check that `-Xmx4G` holds on `ubuntu-latest`.
- Expect about 9 minutes when the Flutter SDK is not cached. `cache: true` keys on the constant `0.1.0`, so after a pin bump run once with `cache: false`.

## Fallback

- If the `flet-1.1.0` branch is rewritten or deleted before 1.1.0 is released, the pin SHA may become unfetchable. In that case:
  - pin the commit it merged into on `main`;
  - or, if 1.1.0 is out, pin `flet==1.1.0` (development.md §2.2).
- If App Store Connect rejects the upload for ITMS-91053:
  - file U13 upstream: a `Runner/PrivacyInfo.xcprivacy` in the template, or a manifest inside serious_python's `Python.framework`;
  - meanwhile, testers get Android builds, and the iPhone runs `flet debug ios`.
- If the font package route stops working, fall back to the system font (accepted for `flet run`), and raise U20.

---
_Written by Claude Code (AI agent)._
