# S8: Does a minimal mobile_scanner extension decode reliably in release builds?

**Spike:** S8 ([#362](https://github.com/ndonkoHenri/pycon-us-flet/issues/362), roadmap `P2-02`, PLAN §8, under the E1 epic [#33](https://github.com/ndonkoHenri/pycon-us-flet/issues/33)). **Date:** 2026-10-20, about 3 hours of builds and runs on one Mac.
**Decides:** D-293 (E1 goes ahead; its API and what its Dart side must do). **Facts:** F111. **Upstream:** E1's write-up, [#520](https://github.com/ndonkoHenri/pycon-us-flet/issues/520) (a sub-issue of #33). **Held for the iPhone:** [#121](https://github.com/ndonkoHenri/pycon-us-flet/issues/121) (the list at the end).

## Question

Can a small Flet extension over `mobile_scanner` (one control, `on_detect`, a torch switch) decode a badge QR in a release build, survive a denied permission, the background and many pause/resume cycles, and pass the `material_ui` gate (`docs/flet-gaps-and-extensions.md` §3)? What does it cost in size, and what must E1 be?

## Answer: yes; E1 goes ahead, with three things its Dart side must do

- **It decodes.** The release APK on an Android 14 emulator read the mock badge `S8TEST01:7f3a9c2e` from the virtual scene camera every time it faced it: 5 of 5 cold starts, 5 of 5 turns towards it, after every resume, and after 50 pause/resume cycles. `analyze_image()` on the bundled PNG returned exactly that payload in 395 ms.
- **The `material_ui` gate passes.** The extension imports `widgets.dart` only. `mobile_scanner` itself imports `material.dart`, but with our own `placeholderBuilder` and `errorBuilder` it builds only `ValueListenableBuilder`, `LayoutBuilder`, `ClipRect`, `SizedBox`, `FittedBox`, `RotatedBox` and the platform `Texture` (its `CameraPreview`); `GestureDetector` only with `tapToFocus`, which E1 leaves off. In every reachable state (placeholder, running, paused, `permissionDenied` on both platforms, `unsupported` on the iOS simulator) no log held "No Material widget found", a `FlutterError` or a crash.
- **What E1's Dart side must do (D-293):**
  1. **Own the controller and the lifecycle.** `torch`, `paused` and `analyze_image` need a `MobileScannerController` passed in, and the widget then does no lifecycle handling of its own: the extension stops the camera on `inactive` and starts it on `resumed`, unless paused or not yet permitted. Measured: the camera client leaves `dumpsys media.camera` in the background, no detection arrives there, and scanning resumes 2.1 s after the app comes back.
  2. **Serialise `start()` and `stop()`, and catch their errors.** A resume while the first start was still running threw `MobileScannerException(controllerInitializing)` as an unhandled Dart exception, twice in the cycle runs (no crash; the camera came up anyway). E1 keeps the wanted state and applies it when the call in flight finishes, and reports a failure through `on_error`.
  3. **Fill the area in the placeholder and error states.** A bare `ColoredBox` with no child is zero wide in a `Column`: the first build showed nothing at all where the preview goes. `SizedBox.expand(child: ColoredBox(...))` fixed it on both platforms.
- **The 4 s cooldown is needed and sized right (D-65 stays).** `DetectionSpeed.normal` reports the same code 3.65 times a second (73 in 20 s; median gap 270 ms, its 250 ms timeout plus a frame), so one badge held up for a second gives about four detections. The app accepts one per code every 4 s, as D-65 says.
- **Permissions are the app's job, as D-61 says.** `mobile_scanner` asks for the camera itself when it starts. Denied, `on_error` gets `permissionDenied`; Android asks a second time at the next start, then never again (`USER_FIXED`), and the error comes at once. After the user allows it in Settings, nothing restarts on resume (the plugin and E1 both skip a start without permission), so the scan screen re-checks with `flet-permission-handler` on resume and sets `paused=False`. `on_error` cannot tell "denied" from "denied for good"; `PermissionHandler` can, for the "Open settings" row.
- **Size:** +7.3 MB on the arm64 release APK, +1.1 MB on the iOS simulator build (Vision is part of iOS). Keep the bundled ML Kit model on Android (offline at the venue).

## Method

- **Host:** Apple M4, macOS 27.0, Xcode 27.0, Android emulator 37.2.12.0, uv 0.12; other agents built and ran emulators at the same time, so timings are relative only (testing-and-quality.md §8).
- **Flet:** the pin `15854a0ac` (`.flet-ref`), Flutter 3.47.7.
- **Plugin:** `mobile_scanner` 7.4.2 (BSD-3, the latest on pub.dev on 2026-10-20), pinned exactly. Written from its pub.dev API and `flet-camera` only; the GPL `flet-barcode-scanner` was not opened (D-99).
- **Devices:**
  - `flet_probe_api34` as `emulator-5592`, my own read-only instance (Android 14, Google APIs arm64), started with `-camera-back virtualscene -virtualscene-poster wall=src/qr.png -grpc 8692`. The scene puts the wall poster at (-0.807, 0.320, 5.316) (`emulator/resources/Toren1BD.posters`); the device faces it from (-0.5, 0, 3) turned 180°, set through the emulator's gRPC `setPhysicalModel`.
  - My own iOS 26.5 simulator "362-iphone17" (iPhone 17), deleted at the end. Taps through Maestro's local CLI.
- **Builds:** release `flet build apk --arch arm64-v8a` (R8 on) and `flet build ios-simulator` (debug, D-102), from the reproducer folder with a pub cache of its own (D-176); the iOS bundle's `app/main.pyc` matched `build/python-app`. For the size, the same project without the extension (`main.py` one `Text`), built the same way.
- **Reproducer:** [`08-scanner/`](08-scanner/), its own `pyproject.toml` on `.flet-src`; not app code.
  - `s8_scanner/`: the throwaway extension. Python: `S8Scanner(ft.LayoutControl)` with `formats`, `paused`, `torch`, `on_detect` (`raw_value`, `format`), `on_error` (`code`, `message`) and `analyze_image(path)`. Dart: one `StatefulWidget` over `MobileScanner` with its own controller, lifecycle observer and builders (`lib/src/scanner.dart`). No Android or iOS module: the plugin brings its own, `CAMERA` included.
  - `src/main.py`: the scanner, Pause/Resume, Torch, Analyze image, and manual entry, which always shows (D-65); not embedded, it shows manual entry alone. Start routes `/paused`, `/cycles/<n>[/<ms>]` and `/analyze`. Each step prints an `S8 ` line (logcat tag `flet.python`).
  - `drive_android.py`: the Android checks (`cold`, `rate`, `turn`, `background`, `cycles`, `gate`), each printing an `S8-DRIVER` line.
- **Release builds silence `debugPrint`** (F111), so the Dart side's log lines never reached logcat; every number comes from the Python side's `S8` lines, logcat's own lines and `dumpsys`.

## Evidence

### Android 14 emulator, release APK

| Check | Result |
|---|---|
| Permission prompt at first start | Android's camera prompt, from the plugin's own request |
| Don't allow | `on_error` `permissionDenied`; the area stays blank (black after the fix) |
| Allowed in Settings, app resumed | nothing restarts (by design, see above); Pause then Resume starts the camera and it decodes |
| Don't allow twice | the second start asks again; after the second "Don't allow", `USER_FIXED`, and the third start errors in 0.7 s with no prompt |
| Cold start facing the QR (5 runs) | mount to first detection 7.3, 7.1, 6.3, 6.7, 6.7 s |
| Turn to the QR, camera running (5 runs) | 4.0, 3.2, 2.7, 2.7, 2.0 s |
| Facing the QR for 20 s | 73 detections, 3.65 per second, median gap 270 ms |
| Home for 10 s, then back | 0 detections while away; camera clients 1 → 0 → 1; first detection 2.1 s after the return (5.5 s in a first run) |
| 50 pause/resume cycles, 1.5 s apart | all 50 done; a camera DISCONNECT and CONNECT per cycle in `dumpsys media.camera`; PSS 157.6 MB after cycle 1, 153.6 MB after cycle 50; one cycle of 49 with no detection in its 1.5 s (six in a first run), then scanning went on |
| Torch on and off (the emulator's camera has none) | no error, scanning continued |
| `analyze_image(src/qr.png)` | `['S8TEST01:7f3a9c2e']` in 395 ms |
| Gate (the whole session's logcat, 39 000 lines) | no "No Material widget", no `FlutterError`, no `FATAL EXCEPTION`, no ANR; 2 unhandled `controllerInitializing` (see above) |

- **Why a cold start takes 6–7 s here.** CameraX validates the device's cameras at first init. This AVD has no front camera (`hw.camera.front = none`), so `CameraValidator` fails "LENS_FACING_FRONT verification" and CameraX retries every 0.5 s, 10 times, before it opens the back camera. That is the emulator's configuration, not the plugin; the iPhone gives the real number (#121).
- **The cycles without a detection** came when the camera took longer to start than the 1.5 s the reproducer leaves it running, mostly in the first run, which started its cycles while the first start's retries were still going.

### iOS 26.5 simulator, debug build

| Check | Result |
|---|---|
| Build and launch | builds with the plugin's Swift package; the black placeholder fills the area |
| Usage string | the prompt shows the `NSCameraUsageDescription` from `[tool.flet.ios.info]`, which replaced the one `permissions = ["camera"]` writes |
| Don't Allow | `on_error` `permissionDenied`; black area; manual entry works |
| Allowed (`simctl privacy grant camera`) | `on_error` `unsupported`: the simulator has no camera |
| `analyze_image()` | the plugin raises "Analyzing an image from a file is not supported on the iOS Simulator"; the unhandled `RuntimeError` in the click handler then replaced the page with "Error running app" (U15) |

### Size

| Build | Without | With | Cost |
|---|---|---|---|
| Android release APK, arm64 | 55 562 993 B | 62 876 071 B | **+7.3 MB**: `libbarhopper_v3.so` 4.9 MB, three ML Kit models 0.9 MB, `classes.dex` +3.3 MB (CameraX, ML Kit), `libapp.so` +65 kB |
| iOS simulator `.app`, debug | 286 480 kB | 287 596 kB | **+1.1 MB** (the debug dylib +0.8 MB); a release IPA's cost is for #121 |

### The companion app (D-63)

`is_embedded()` is `False` off-device even with the extension installed, so `capabilities.available()` keeps the scanner out of `flet run` and the companion app; the reproducer's not-embedded branch shows "Camera scanning isn't available in this build" and manual entry.

## Not covered

- A printed QR, daylight and dim light, the torch, release-build timings and a release IPA's size: they need the iPhone (#121).
- Accessibility of the scan screen: the reproducer's screen is throwaway. The preview gets a semantics label from the app (a `Semantics` wrapper), and the outcome panel is D-65's live region; the P3 scan screen checks them.

## Decisions changed

- **D-293:** E1 goes ahead; its API and the Dart duties above. Recorded in `docs/flet-gaps-and-extensions.md` §4.2. D-65's 4 s cooldown and D-61's primer stand, confirmed.

## Held for the iPhone (#121)

1. A printed sheet of mock badges, in daylight and in dim light: time to first detection, misreads (none expected), distance.
2. The torch on and off while scanning, and in the background (it must go off).
3. A release build's cold start to first detection, and background and resume, against the emulator's numbers.
4. The camera prompt with the scanning string, Don't Allow, then Settings and back: the scan screen restarts the camera after the app re-checks.
5. `analyze_image()` on a bundled badge PNG (the simulator cannot).
6. The release IPA's size with and without the extension.

## Fallback

If E1 is late, D-65's interim stands: manual entry of the `code:validator` payload and USB/Bluetooth HID scanners on the shared scan screen, which every staff tool already uses.
