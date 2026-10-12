# Development, build and release

**Status:** verified guide (v3), 2026-10-12. The developer guide of D-96. P0-05 (#53) completed it from the S5 verdict ([`spikes/05-build-and-ship.md`](spikes/05-build-and-ship.md)) and checked §5.1-§5.3 from a fresh clone on the reference emulator and simulator. The test strategy is in [`testing-and-quality.md`](testing-and-quality.md) (D-76..D-80). **Binding:** [`PLAN.md`](../PLAN.md) and [`decisions.md`](decisions.md) (D-ids). Where this document applies a decision, it cites it.

**Scope.** This document covers how we build, run and distribute the app on **Android and iOS only** (D-09). There are no web, PWA or desktop targets. A desktop window is a developer convenience at most (§5.4).
- The project file, validated against the local flet-cli (§3).
- Versioning (§4).
- The development loop (§5).
- The mock API workflow (§6).
- GitHub Actions for a private repo (§7).
- Signing and internal distribution (§8).
- What a public release would need later (§9).

**Feature ids** implemented here: DEV-08, NATIVE-01, NATIVE-02, NATIVE-03, NATIVE-06 (declarations), NEW-03 (snapshot step), NEW-07 (configuration) and NEW-08 (workflow). Not built: DEV-07, LIVE-01..04, NATIVE-04/05/07/09/10 and NOTIF-12 ([`feature-matrix.md`](feature-matrix.md)).

**Path aliases.** All are inside `.flet-src`, the Flet checkout at the pin (`15854a0ac`, §2.2), unless stated. Line numbers are at that commit; re-check them when the pin moves.

| Alias | Path |
|---|---|
| `CLI/` | `sdk/python/packages/flet-cli/src/flet_cli/` |
| `TPL/` | `sdk/python/templates/build/{{cookiecutter.out_dir}}/` |
| `DOCS/` | `website/docs/` |
| `ACTION/` | the separate `flet-dev/flet-build-action` repository; tag `v1` is commit `96093619265697f7c68cef5cf18981e4be296b11` |

---

## 1. At a glance

| I want to… | Command (from the repo root) | Section |
|---|---|---|
| Set up a fresh clone | `git clone …`, the Flet checkout at `.flet-ref`, `uv sync` | §5.1 |
| Run the real app shell on an emulator, simulator or phone | `uv run flet debug android -d emulator-5554` (or `ios -d <udid>`); `-d` is required | §5.3 |
| Run the app with Python hot reload | `BROWSER=true uv run flet run -r -w -p 8550`, plus `flutter run -d <id>` in `.flet-src/client` | §5.2 |
| List devices or emulators | `uv run flet devices`, `uv run flet emulators` | §5.5 |
| Lint, type-check and test | `uv run ruff check && uv run ruff format --check && uv run pyright && uv run pytest` | §7.2 |
| Start the mock API (from P3) | `uv run python -m tools.mock_api.server --host 0.0.0.0` | §6 |
| Build an APK for the emulator | `uv run flet build apk --arch arm64-v8a --build-number $(git rev-list --count HEAD)` (D-106) | §8.1 |
| Build an AAB for Play | `uv run flet build aab --build-number $(git rev-list --count HEAD)` | §8.1 |
| Build an IPA for TestFlight | `uv run flet build ipa --ios-export-method app-store-connect --build-number $(git rev-list --count HEAD)` | §8.2 |
| Get an APK from CI | `gh workflow run build-android.yml --ref main` (or Actions › Build Android › Run workflow, or push a `v*` tag), then `gh run download <run-id>` | §7.4 |
| Refresh the bundled feed snapshot (from P0-17) | `uv run python tools/update_snapshot.py` | §8.3 |

---

## 2. Toolchain

### 2.1 Facts (verified 2026-10-12 at `15854a0ac`)

| Fact | Value | Source |
|---|---|---|
| Flet | **1.1** from flet-dev/flet's **`flet-1.1.0` branch**, pinned at `15854a0ac` (`.flet-ref`) until 1.1.0 is on PyPI, where the latest is 1.0.4. The first pin (`3710aff`, on `main`) was 1.0.4 plus fixes: its template targets iOS 13.0, which Xcode 27 rejects. `flet --version` prints `1.0.4`, the nearest tag (§2.2). | D-81, D-104; F20; S5 |
| Flutter | **3.47.7**, read from the checkout's `.fvmrc`. flet-cli uses `~/flutter/3.47.7` if it exists, else the `flutter` on `PATH` if its major.minor matches (any 3.47.x); otherwise it asks, then downloads 3.47.7 into `~/flutter/3.47.7` (about 5 minutes; `--yes` skips the question). It adds that SDK to `PATH` only for its own subprocesses, not your shell. | `flet/version.py` `get_flutter_version`; `CLI/commands/flutter_base.py:155-181, 198-227, 282-292, 427-439`; `CLI/utils/flutter.py:43-55` |
| JDK (Android builds) | **17**. flet-cli uses `JAVA_HOME`, then `/usr/libexec/java_home`, if either is a JDK 17; otherwise it downloads Temurin **17.0.13+11** into `~/java/17.0.13+11`. Either way it runs `flutter config --jdk-dir=<that JDK>`, a global Flutter setting. A newer system JDK is ignored. | `CLI/utils/jdk.py:15-18, 87-163`; `CLI/commands/flutter_base.py:328-351` |
| Android SDK | `ANDROID_HOME`, then `ANDROID_SDK_ROOT`, then Android Studio's `~/Library/Android/sdk`, then `~/Android/sdk`; if none exists, flet-cli asks and installs one into `~/Android/sdk`. | `CLI/utils/android_sdk.py:42-103, 269` |
| Python in the app | CPython **3.14.7**, chosen from `requires-python = ">=3.14,<3.15"`. The S5 screen showed "Python 3.14.7 on android" and "… on ios". | `CLI/utils/python_versions.py` `resolve_python_version`; python-build release `20260921` (`:31`) |
| Android SDK levels | **`minSdk` 24, `targetSdk` 36, `compileSdk` 36**: Flutter's defaults. We set neither `min_sdk_version` nor `target_sdk_version` (D-106). 36 meets Play's target-API rule. | `TPL/android/app/build.gradle.kts:77-86`; `aapt2 dump badging` in #125 |
| Android ABIs | `arm64-v8a`, `x86_64` and `armeabi-v7a` by default. APKs for our emulators and CI are `--arch arm64-v8a` only; AABs keep all three (D-106). | `PythonRelease.android_abis`; D-106 |
| Sizes | arm64 APK **56.2 MB** (56,208,812 bytes, #125, with Roboto). Without Roboto (S5): universal APK 142.5 MB, AAB 102.5 MB, an arm64 phone's download from Play 26.6 MB (bundletool). | #125; S5 |
| Build number | `--build-number <commit count>` becomes Android `versionCode` and iOS `CFBundleVersion`; `[project].version` becomes `versionName` and `CFBundleShortVersionString` (§4). `flet debug` passes neither, so a debug build has `versionCode` 1 and `versionName` 1.0.0. | `CLI/commands/build.py:200-209`; `CLI/commands/debug.py:144-163` |
| iOS minimum | 15.0, fixed by the template | `TPL/ios/Runner.xcodeproj/project.pbxproj:348` |
| Android release signing without a keystore | Signed with the **debug key**: it installs, but cannot go to Play | `TPL/android/app/build.gradle.kts:102-118` |
| `flet build ipa` and signing | No profile configured: `--no-codesign` and only an `.xcarchive`. A profile configured but not installed: flet-cli stops within seconds, before Xcode. Installed: a signed `.ipa` (§8.2). | `CLI/commands/build.py:184-193, 287-379` |
| What gets bundled | `[project].dependencies` (plus `[tool.flet.<platform>].dependencies`), pip-installed at build time. **`uv.lock` does not apply**, so bundled dependencies are pinned exactly in `pyproject.toml`. | `CLI/commands/build_base.py:2598-2641` |
| App metadata at runtime | The app directory is copied, not installed, so `importlib.metadata` cannot see `pycon-us` | F15 |
| Deep links on mobile | Read only from `[tool.flet.android.deep_linking]` and `[tool.flet.ios.deep_linking]`. Each needs both `scheme` and `host`. | `CLI/commands/build_base.py:1422-1427, 2970-2982`; `TPL/android/app/src/main/AndroidManifest.xml:47-56`; F16 |
| Gradle heap | The template default is `-Xmx8G`, more than a standard GitHub runner has. Our `-Xmx4G` override (`[tool.flet.android.gradle_properties]`) passed every build on the Mac; the runner is P0-06's check (#54). | `CLI/commands/build_base.py:1144-1153, 1263-1266` |
| Logs | Android: logcat tag `flet.python`. iOS: unified log, sender `dart_bridge`. Both also write `console.log`. | `DOCS/publish/android.md` and `DOCS/publish/ios.md`, "Reading your app's output" |
| flet-build-action | Runs `uv run flet --version --json`, then `flet build <target> --yes --verbose --output …`, then archives. It never signs or uploads. | `ACTION/action.yml`; `ACTION/scripts/flet_action.py:112-232` |

### 2.2 Flet from source until 1.1.0 (D-81)

**Why a plain git dependency is not enough.** Installing `flet` and `flet-cli` from a git URL into `site-packages` breaks `flet build` in three ways:

| What | Behaviour outside a source checkout | Source |
|---|---|---|
| Flutter version | Unknown (`"0"`), and `flet build` stops with "Unable to determine the required Flutter SDK version" | `flet/version.py:135`; `CLI/commands/flutter_base.py:137` |
| Build template | Downloaded from the GitHub release `v{flet_version}`, which does not exist for an unreleased commit | `CLI/commands/build_base.py:68-71, 1852-1883` |
| Dart `flet` package | Only a source checkout rewrites `pubspec.yaml` to the monorepo's `packages/flet` | `CLI/commands/build_base.py:1932-1944` |

Run from a checkout, flet-cli instead finds `sdk/python/templates/build` and the repo root (worktrees included), and uses both. Checked from a fresh clone set up as below (2026-10-12): `uv run flet --version --json` reported `"flet": "1.0.4", "flutter": "3.47.7"`, and `flet debug` built from the local template and Dart package.

**The setup.**
- `.flet-ref` (committed) holds one line: the pinned 40-character `flet-dev/flet` commit SHA. It is the single pin for development, CI and builds.
- `.flet-src` (git-ignored) is a checkout of `flet-dev/flet` at that SHA:
  - For contributors, a clone.
  - For the owner, a `git worktree` of his Flet repo. His main checkout stays free for upstream work, and the app always builds from the pin.
- `pyproject.toml` points uv at the packages in `.flet-src` (`[tool.uv.sources]`) and tells `flet build` to bundle the same `flet` (`[tool.flet.dev_packages]`, §3.1).

```bash
# Contributors: a fresh clone at the pin.
git clone --filter=blob:none https://github.com/flet-dev/flet.git .flet-src
git -C .flet-src checkout --detach "$(cat .flet-ref)"

# Owner: a worktree of an existing Flet checkout.
git -C ../../flet worktree add --detach "$PWD/.flet-src" "$(cat .flet-ref)"

# Check the pin before building anything for testers.
test "$(git -C .flet-src rev-parse HEAD)" = "$(cat .flet-ref)" && echo "Flet pin OK"
```

**Bumping the pin** happens in its own PR (`chore/<issue>-bump-flet`, D-92):
1. Check out the new SHA in `.flet-src`, and write it to `.flet-ref`.
2. Run `uv lock`, because Flet's own dependencies may have changed, then `uv sync`.
3. Delete `build/` (`rm -rf build`) on every bump. It caches Dart build-hook binaries compiled by the previous
   Flutter, which a newer Flutter refuses ("Invalid kernel binary format version"; seen in #120 going from 3.44.8 to
   3.47.7). It also caches the generated app shell, which flet-cli keys on the template path, the reported version
   and the configuration, not on the pin's SHA; the reported version stays `1.0.4` across bumps (§2.2 quirks).
4. Run the full checks, then build and smoke-test on an Android emulator (`flet build apk --arch arm64-v8a`) and an iOS simulator (`flet build ios-simulator`); the template and Dart package change with the pin. A release build on the iPhone only when the bump touches something that needs hardware (D-102).
5. In the PR body, put the compare link (`flet-dev/flet/compare/<old>...<new>`) and what changed for us.

**When 1.1.0 is on PyPI** (one PR):
- Set `flet==1.1.0`, the dev tools `==1.1.0` and the extensions `==1.1.0`.
- Delete `[tool.uv.sources]`, `[tool.flet.dev_packages]`, `.flet-ref`, the Flet checkout steps in the workflows (§7), and this subsection.
- After that, flet-cli downloads the release template and the Dart package is the published one.

**Known quirks of a source pin:**
- `.flet-src/sdk/python` is a uv workspace, so `uv.lock` also records Flet's own dev group (every extension package under `sdk/python/packages`) as editable paths. Nothing extra is installed, but `uv sync --locked` needs all those directories: a checkout must include the whole `sdk/python` tree (CI's sparse checkout of `sdk/python` does).
- With `[tool.flet.dev_packages]` set, `flet build` never reuses installed site-packages and passes `--no-cache-dir`, so every build reinstalls the bundled packages (`CLI/commands/build_base.py:2614-2638`). Slower, but expected while the pin lasts.
- `flet --version` prints the nearest git tag, for example `1.0.4`. In CI's shallow clone it prints `0.1.0`.
- Packaged apps report `flet.version.flet_version == "0.1.0"`, because a mobile build skips the git lookup (`flet/version.py:86-103`). About this app (INFO-03) shows this value as "source build".
- None of this affects the build (S5, #125).

---

## 3. `pyproject.toml`

### 3.1 The file (P0)

It contains what P0 needs and nothing more. Later phases add the blocks in §3.4.

```toml
[project]
name = "pycon-us"
version = "0.0.1"                     # == pycon_us.__version__ (unit test, D-83)
description = "A conference companion for PyCon US on Android and iOS, built with Python and Flet. Not an official PSF app."
readme = "README.md"
license = "Apache-2.0"
requires-python = ">=3.14,<3.15"      # flet build bundles CPython 3.14 (D-82, F19)
dependencies = [                      # bundled into the app by flet build: pin exactly
    "flet",                           # pinned by .flet-ref until 1.1.0 is on PyPI (D-81)
    "tzdata==2026.5",                 # zoneinfo data on phones (D-43)
]

[build-system]                        # uv sync installs pycon_us (src/pycon_us) editable on the host
requires = ["uv_build>=0.12,<0.13"]
build-backend = "uv_build"

[dependency-groups]
dev = [                               # host only, never bundled; versions in uv.lock (D-75)
    "flet-cli",                       # flet run / build / debug / devices / test
    "flet-web",                       # flet run --android/--ios serves through it
    "flet-desktop",                   # optional desktop window (D-09, development.md §5.4)
    "flet-platform-assets",           # flet-cli dependency, listed so uv takes it from .flet-src
    "flet[test]",                     # flet test flows (D-78) and pytest-asyncio
    "pytest",
    "hypothesis",
    "ruff",
    "pyright",
]

# ------------------------------------------------------------------ flet build
[tool.flet]
product = "Conf Companion"            # display name: neutral placeholder until O-4 (D-36)
bundle_id = "io.github.ndonkohenri.pyconus"   # placeholder until O-4, both platforms

[tool.flet.app]
path = "src"                          # entry point src/main.py

[tool.flet.splash]                    # SHELL-01: the same purple as BootView, so no flash
color = "#680579"
dark_color = "#680579"

[tool.flet.boot_screen.flet]          # shown while Python starts, between splash and BootView
bgcolor_light = "#680579"
bgcolor_dark = "#680579"

[tool.flet.flutter.pubspec.dependencies] # Roboto 400/500/700 (D-26, D-105); path from build/flutter/
roboto_fonts = { path = "../../flutter_packages/roboto_fonts" }

[tool.flet.android.gradle_properties] # fits a standard GitHub runner (template: -Xmx8G)
"org.gradle.jvmargs" = "-Xmx4G -XX:MaxMetaspaceSize=1G -XX:+HeapDumpOnOutOfMemoryError"

[tool.flet.ios]                       # signing (development.md §8.2); not secret (D-86)
team_id = "VF87YBAN84"
# No export_method: the default "debugging" serves flet debug ios; TestFlight builds pass
# --ios-export-method app-store-connect. No provisioning_profile yet (#121): flet build ipa
# then passes --no-codesign and produces an .xcarchive.

[tool.flet.ios.export_methods.debugging]
signing_certificate = "Apple Development"

[tool.flet.ios.export_methods."app-store-connect"]
signing_certificate = "Apple Distribution"
export_options = { manageAppVersionAndBuildNumber = false }   # Xcode must not renumber

[tool.flet.ios.info]
ITSAppUsesNonExemptEncryption = false # HTTPS only: no export-compliance prompt on upload

# ------------------------------------------------------------------ Flet from source (development.md §2.2)
# Delete both tables in the PR that pins flet==1.1.0.
[tool.uv.sources]
flet = { path = ".flet-src/sdk/python/packages/flet", editable = true }
flet-cli = { path = ".flet-src/sdk/python/packages/flet-cli", editable = true }
flet-web = { path = ".flet-src/sdk/python/packages/flet-web", editable = true }
flet-desktop = { path = ".flet-src/sdk/python/packages/flet-desktop", editable = true }
flet-platform-assets = { path = ".flet-src/sdk/python/packages/flet-platform-assets", editable = true }

[tool.flet.dev_packages]              # what flet build bundles instead of PyPI's flet
flet = ".flet-src/sdk/python/packages/flet"

# ------------------------------------------------------------------ tools
[tool.ruff]
target-version = "py314"              # ruff also skips git-ignored paths (excluded/, .flet-src)
extend-exclude = ["*.md"]             # code sketches in the docs are illustrations, not our code

[tool.ruff.lint]
extend-select = ["I", "UP", "B", "SIM", "D", "DTZ"]   # D: docstrings (D-74); DTZ: no naive datetimes (D-43)

[tool.ruff.lint.pydocstyle]
convention = "google"

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["D"]

[tool.pyright]
include = ["src", "tests", "tools"]
typeCheckingMode = "standard"

[tool.pytest.ini_options]
asyncio_mode = "auto"                 # async client tests (testing-and-quality.md §2)
testpaths = ["tests"]
pythonpath = ["."]                    # tools.mock_api; pycon_us is installed by uv sync
addopts = ["--ignore=tests/ui"]       # device flows run through flet test (D-78)
```

**Validated** on 2026-10-11 in a scratch project with `.flet-src` linked to the monorepo:
- flet-cli's own `load_pyproject_toml` read it, and every leaf key was matched to its reader (§3.2);
- `resolve_python_version` picked 3.14.7;
- `uv lock` resolved `flet` as `editable = ".flet-src/…"`;
- ruff, pyright and pytest ran under it.

S5 then built every target from this setup, and P0-04 (#52) built `apk --arch arm64-v8a`, `ios-simulator` and `ipa` from a clean `build/` with the whole file, Roboto (D-105) and the iOS signing tables (§8.2) included, at the `15854a0ac` pin.

**How `pycon_us` is importable on the host.** `[build-system]` uses uv's own backend, whose default layout is `src/pycon_us`, so `uv sync` installs the package editable. Then the tests, `tools/check_feed.py`, `tools/update_snapshot.py` and the mock server (which shares `core/signing.py`, D-52) all `import pycon_us` with no `PYTHONPATH`. Checked with uv 0.12.15 in a scratch project: `uv sync` built and installed it, and `uv run python tools/<script>.py` imported it. Without a build system, uv would treat the project as virtual and the tools would fail with `ModuleNotFoundError: pycon_us`. `flet build` is unaffected: it copies `src/` and pip-installs only `[project].dependencies`. On the phone, package metadata is still invisible (F15), so code reads `pycon_us.__version__`, never `importlib.metadata`.

### 3.2 Where each key is read

`get_platform_setting(x)` looks up `tool.flet.<platform>.x` first, then `tool.flet.x` (`CLI/commands/build_base.py:2984-3009`).

| Key | Read at | Effect |
|---|---|---|
| `project.name` | `CLI/commands/build_base.py:1053-1080` | Project slug; fallback for the artifact and product names |
| `project.version` | `CLI/commands/build.py:203-209` | `--build-name`: Android `versionName`, iOS `CFBundleShortVersionString` |
| `project.requires-python` | `CLI/utils/python_versions.py` | Bundled Python 3.14 |
| `project.dependencies` | `CLI/commands/build_base.py:2601-2604` | What is pip-installed into the app |
| `tool.flet.product` | `CLI/commands/build_base.py:1075-1080` | Launcher label and `CFBundleDisplayName` |
| `tool.flet.bundle_id` | `CLI/commands/build_base.py:1619-1621`; `templates/build/cookiecutter.json` | Android `applicationId` (`org_name_2` + `package_name`) and the iOS bundle id |
| `tool.flet.app.path` | `CLI/commands/build_base.py:1012-1015`; `CLI/commands/run.py:287-288` | `src/` holds `main.py` for both `build` and `run` |
| `tool.flet.splash.color`, `dark_color` | `CLI/commands/build_base.py:1717-1743` (`splash_setting`), `:1745-1781` (`_resolve_splash`) | Native splash background, light and dark |
| `tool.flet.boot_screen.flet` | `CLI/commands/build_base.py:1783-1827` (`_resolve_boot_screen`) | Background of Flet's boot screen while Python starts (`DOCS/publish/index.md` "Built-in `flet` boot screen") |
| `tool.flet.android.gradle_properties` | `CLI/commands/build_base.py:1263-1266` | Merged over the template defaults, so ours replaces `org.gradle.jvmargs` |
| `tool.flet.ios.info` | `CLI/commands/build_base.py:1205-1213` | Merged into `Info.plist` |
| `tool.flet.flutter.pubspec.dependencies` | `CLI/commands/build_base.py:1986-2004` | Merged into `build/flutter/pubspec.yaml`, so relative paths resolve from `build/flutter/`; adds `roboto_fonts` (D-105) |
| `tool.flet.ios.team_id`, `tool.flet.ios.export_methods.<method>` | `CLI/commands/build_base.py:1466-1501` | The method from `--ios-export-method`, else `export_method`, else `debugging` picks its table; its `provisioning_profile`, `signing_certificate` and `export_options` go into the Runner's build settings and `ios/exportOptions.plist` (§8.2) |
| `tool.flet.dev_packages` | `CLI/commands/build_base.py:2614-2638` | Rewrites `flet` to `flet @ file:///…/.flet-src/…` for the bundle; relative paths resolve from the project root |

Not set, because the default is what we want:

| Key | Why it is absent |
|---|---|
| `[tool.flet.compile]`, `[tool.flet.cleanup]` | The defaults (`.pyc` for app and packages; package cleanup on) suit us (`CLI/commands/build_base.py:2774-2810`). S1 measured `.pyc` off: Python recompiles on every start, because serious_python sets `PYTHONDONTWRITEBYTECODE=1` (F25), and cold starts reached the content 284 ms later on the emulator, so `.pyc` stays on (D-111). |
| `company`, `copyright` | Used only by the desktop templates (`TPL/macos/…/AppInfo.xcconfig`, `TPL/windows/…/Runner.rc`). |
| `min_sdk_version`, `target_sdk_version` | Flutter's defaults, 24 and 36, are what we want (D-106). |
| `[tool.flet.android.signing]`, `build_number` | Signing comes from `FLET_ANDROID_SIGNING_*` environment variables (§8.1), and the build number from `--build-number` (§4). |
| `[tool.flet.deep_linking]` (the global table) | Ignored for Android and iOS (F16). The per-platform tables arrive in P2 (§3.4). |
| `NSAppTransportSecurity` | The template already allows arbitrary loads (`TPL/ios/Runner/Info.plist:48-52`). |
| `[tool.flet.template]` | We never fork the template (D-97). `[tool.flet.flutter.pubspec]` is used only for the Roboto fonts (§3.4). |

### 3.3 Icons and splash (NATIVE-03)

`flet build` generates every icon and splash image from `src/assets/` (`DOCS/publish/index.md` "Icons", lines 802-940). Nothing is copied into the template by hand.
- **P0:** Flet's default icon. A build that has a placeholder icon is obviously a development build.
- **P0 (SHELL-01):** the splash and boot-screen colours in §3.1, `#680579` in light and dark. Native splash, Flet's boot screen and our `BootView` then share one background, so nothing flashes between them. The colours live in `pyproject.toml`, not in `--splash-color` flags, so the file stays the only configuration (§7.4).
- **When O-4 settles the identity:** add `src/assets/icon.png` (1024 × 1024, transparent background, our own mark, no PSF logo per D-36) and `[tool.flet] icon_background`.
  - If the generated framing looks wrong, add `icon_ios.png` or `icon_android.png`: artwork within the central 60 % for iOS, and within a centred circle of about 57 % for Android.
  - The splash artwork (`splash.png`, plus the same file as `splash_dark.png`, which iOS needs before it applies `dark_color`) also waits for O-4. Until then the splash falls back to the icon (`DOCS/publish/index.md` "Splash images").

### 3.4 Additions by phase

Each row lands in the PR that ships the feature, never earlier. A Flet extension from the monorepo is added three times while the source pin lasts:
- in `dependencies`, so it is bundled;
- in `[tool.uv.sources]`, so the host uses the checkout;
- in `[tool.flet.dev_packages]`, so the bundle uses the checkout.

| Phase | Feature | Addition | Exists in flet-cli today? |
|---|---|---|---|
| P2 | Deep links (NEW-07, D-21) | `[tool.flet.android.deep_linking]` and `[tool.flet.ios.deep_linking]`, each with `scheme = "<from O-4>"` and `host = "app"`. Links look like `<scheme>://app/schedule/session/42`. Both tables are needed: flet-dev/flet#6953 is not required, but it does no harm (F16). | Yes |
| P2 | Runtime permissions (D-75) | `"flet-permission-handler"` | Yes (monorepo package) |
| P2 | Reminders (E3, D-58..D-61) | The notifications extension from flet-dev/flet#6948 (its package name is set upstream), plus `[tool.flet.android.permission] "android.permission.POST_NOTIFICATIONS" = true`, plus core library desugaring in the same Flet pin (U7: `[tool.flet.android] core_library_desugaring = true`, or the template default if the Flet team enables it unconditionally). `flutter_local_notifications` needs desugaring even without scheduling, so an APK with the extension does not build without U7 ([`flet-gaps-and-extensions.md`](flet-gaps-and-extensions.md) §5.10). Do not add `SCHEDULE_EXACT_ALARM` unless S6 shows exact alarms are worth it; reminders are inexact by default (D-59). iOS needs no plist key; permission is requested through the plugin (F17). Boot receivers come from the extension's Android module, or from a `[tool.flet.android.receiver]` table (U7 scope) if S6 picks that fallback. | The permission key: yes. Desugaring: no (U7). The extension: no (E3). |
| P3 | Mock credentials (D-49) | `"flet-secure-storage"` | Yes (monorepo package) |
| P3 | Camera scanning (E1, D-65) | `[tool.flet] permissions = ["camera"]` and `[tool.flet.ios.info] NSCameraUsageDescription = "Scans attendee badges for the staff tools."`. Without our own text, Flet's default "capture photos and videos" string is used (`CLI/commands/build_base.py:254-264`). Then add the scanner extension once it is pinned. | The keys: yes. The extension: no (E1). |
| P3 | Mock server on an iPhone (§6) | `[tool.flet.ios.info] NSLocalNetworkUsageDescription = "Connects to a developer's test server on your local network."`, but only if S1 or P3 shows that iOS local-network privacy prompts for the embedded Python's sockets. **UNVERIFIED.** | Yes (`ios.info`) |
| P0 (S5) | Roboto 400/500/700 (D-26, D-105, THEME-11) | **Done in P0-04 (#52), now in §3.1.** The local font-only Flutter package `flutter_packages/roboto_fonts/` (`pubspec.yaml` declaring family `Roboto` with weights 400, 500 and 700, the three TTFs from googlefonts/roboto v2.138, its Apache-2.0 `LICENSE`, and a one-line `lib/roboto_fonts.dart`), added with `[tool.flet.flutter.pubspec.dependencies] roboto_fonts = { path = "../../flutter_packages/roboto_fonts" }`; the app sets `Theme.font_family = "packages/roboto_fonts/Roboto"`. The files stay out of `src/`, so they are not bundled twice. A `flutter.fonts` entry with assets outside `build/flutter/` renders SF Pro on iOS, so it is not used (`docs/spikes/05-build-and-ship.md`). `flet run` falls back to the system font (accepted). `page.fonts` takes one file per family (U20). | Yes (S5, P0-04) |
| P0 (S5) | iOS signing (§8.2) | **Done in P0-04 (#52), now in §3.1,** except the profile names: `[tool.flet.ios] team_id`, plus `[tool.flet.ios.export_methods.debugging]` and `[tool.flet.ios.export_methods."app-store-connect"]`. No `export_method` key, so it defaults to `debugging` and `flet debug ios` signs for development. Each table gets its `provisioning_profile` once #121 creates the profiles. | Yes |

---

## 4. Versioning (D-83)

| Item | Rule |
|---|---|
| Version | SemVer `0.y.z` until the showcase `1.0.0`. It starts at `0.0.1`. Bump the minor version at each phase exit (P0 → `0.1.0` … P3 → `0.4.0`) and the patch version for tester builds in between. `1.0.0` is the P4 exit (PLAN §7). |
| Where it lives | `[project].version` and `pycon_us.__version__`, changed together in one PR. A unit test keeps them equal. |
| Build number | `git rev-list --count HEAD` on `main`, passed as `--build-number`. Squash merges keep it monotonic, so never rewrite `main`. It becomes Android `versionCode` and iOS `CFBundleVersion`. `flet debug` passes none, so its builds are `versionCode` 1 (§5.3). |
| Tags | `vX.Y.Z` on `main` whenever a build goes to testers. The tag must equal `v` + `[project].version`, and the Android workflow checks this (§7.4). |
| Release notes | Optional: `gh release create vX.Y.Z --generate-notes` lists the merged PRs. There is no changelog file and no build ledger. |
| Builds from a branch | Fine for your own device. Never upload one to Play or TestFlight, because its build number can collide with a later one on `main`. |

```python
# src/pycon_us/__init__.py
"""PyCon US conference companion, built with Python and Flet."""

__version__ = "0.0.1"
```

```python
# tests/test_version.py
import tomllib
from pathlib import Path

import pycon_us

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def test_version_matches_pyproject():
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    assert pycon_us.__version__ == project["version"]
```

---

## 5. Development loop

### 5.1 From a clean checkout

**Prerequisites:**
- git, [uv](https://docs.astral.sh/uv/) (CI uses the 0.12 line, §7.2) and, while the repo is private, a `gh` login with access to it.
- For Android, an emulator (§5.5) or a phone with USB or wireless debugging. flet-cli finds or installs the JDK, the Android SDK and Flutter the first time a mobile command needs them, and asks before each install (§2.1).
- For iOS, a Mac with Xcode 27 and CocoaPods; export `LANG=en_US.UTF-8`, or CocoaPods warns. Simulators need no Apple account; a phone needs the signing setup of §8.2.

```bash
gh repo clone ndonkoHenri/pycon-us-flet && cd pycon-us-flet
git clone --filter=blob:none https://github.com/flet-dev/flet.git .flet-src   # §2.2
git -C .flet-src checkout --detach "$(cat .flet-ref)"
uv sync                                       # Python 3.14 and the dev tools
uv run pytest                                 # no device needed
uv run flet devices                           # the ids for -d
uv run flet debug android -d emulator-5554    # or: uv run flet debug ios -d <simulator udid> (§5.3)
```

Followed literally on 2026-10-12 in a fresh directory (Mac M4, Flutter 3.47.7 on `PATH`, JDK 17 and the Android SDK already installed, warm Gradle and pub caches): `uv sync` took under a second, 4 tests passed, `flet debug android` had the app on `emulator-5554` 70 s after the command, and `flet debug ios` had it on an iPhone 17 Pro simulator in under 3 minutes. A machine without Flutter adds about 5 minutes for its download.

`.gitignore` covers, among others:
- `.venv/`, `.flet-src`, `.flet/` (the `flet run` storage, F14), `build/`, `excluded/`;
- `*.jks`, `*.keystore`, `*.p12`, `*.p8`, `*.mobileprovision` and `.env*`, as a second line of defence for D-86.

### 5.2 Hot reload: a companion client built from the pin

The Flet companion app in the stores is built from released Flet and lacks 1.1's Dart changes, so it is not used with the pin (D-81). `uv run flet run --android|--ios` (port 8551 and a QR code for that app) waits for a 1.1 companion in the stores. Until then, Python hot reload uses a companion client built from `.flet-src/client` on an emulator or simulator:

```bash
# Terminal 1, at the repo root: serve src/main.py on port 8550; -r restarts Python on any change under src/.
BROWSER=true uv run flet run -r -w -p 8550

# Terminal 2: build and start the client (first build about 4 minutes on Android, 2 on iOS).
cd .flet-src/client && flutter run -d emulator-5554    # or -d <simulator udid>
```

- Terminal 2 needs Flutter 3.47.x on `PATH`. If flet-cli downloaded it (§2.1), first run `export PATH="$HOME/flutter/3.47.7/bin:$PATH"`.
- The client connects to `http://localhost:8550` at the root path, or `http://10.0.2.2:8550` on the Android emulator (`client/lib/main.dart:84-97`), and logs "Page URL: …". A phone cannot reach the laptop that way, so phones use `flet debug` (§5.3).
- `-r` watches `src/` recursively; without it only `src/main.py` reloads (F22). A reload restarts Python, so in-memory state resets; preferences live on the device and survive.
- `-w` also opens a browser tab; `BROWSER=true` stops that.
- An "Exception in ASGI application" traceback ending in "Web root path not found: …/flet_web/web" on any HTTP `GET /` (a browser tab, `curl`) is harmless: a source checkout has no built web client, and the native client uses only the WebSocket.
- Stopping `flet run` can leave the app's Python child listening on port 8550, and the next `flet run -p 8550` then cannot bind. `lsof -nP -iTCP:8550 -sTCP:LISTEN` names the process; kill it.
- On iOS, `flutter run` rewrites three tracked files in the Flet checkout: `client/ios/Podfile.lock`, `client/ios/Runner.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved` and `client/ios/Runner.xcworkspace/xcshareddata/swiftpm/Package.resolved`. After a session, check `git -C .flet-src status` and restore only those three with `git -C .flet-src checkout -- <path>`. In a worktree of your own Flet repo, never restore all of `client/`, which would discard your edits.
- Stop with `q` in terminal 2 and Ctrl+C in terminal 1.

What is different in the companion client:

| Aspect | Companion client (`flet run` + `client/`) | Packaged build (`flet debug` / `flet build`) |
|---|---|---|
| Where Python runs | On the laptop | On the device |
| `flet.utils.is_embedded()` | `False`, so every capability shows its interim (D-63) | `True` |
| Extensions | Flet's own extensions, including flet-permission-handler and flet-secure-storage (`client/pubspec.yaml:82-86`, `client/lib/main.dart:64-65`), but not the scanner (E1) or notifications (E3). D-63 gates on `is_embedded()`, so the app uses the interims here regardless. | Used when bundled |
| Fonts | The system font: the client bundles no `roboto_fonts` (D-26 accepts this) | Roboto (D-105) |
| Durable data directory | `<repo>/.flet/storage/data` (F14) | App-private application support (F14, D-108) |
| Developer screen | Always available (D-73) | After 7 taps on the version row in About this app |
| Network from the app's point of view | The laptop's network; the mock is at `http://localhost:8000` (§6) | The device's network |
| Bundle id, icon, permissions, deep links | The client's own | Ours |

### 5.3 Packaged builds on a device: `flet debug`

`uv run flet debug android|ios -d <device-id> [--release] [--route /schedule/session/42] [-v]` builds the real app shell and runs it with `flutter run` (`CLI/commands/debug.py`).
- `-d`/`--device-id` is required for Android and iOS: without it, `flet debug` exits before building (`CLI/commands/debug.py:127-142`). List ids with `uv run flet devices` (§5.5). `--show-devices` hits the same check first, so it also needs `-d`.
- Without `-v`, `flet debug` shows only a spinner ("Running debug version of the app on … device...") and hides `flutter run`'s output, including errors. `-v` streams it, and `-vv` adds Flutter's `--verbose` (`CLI/commands/build_base.py:3173`).
- Ctrl+C ends the session ("Debug session ended."); the app stays installed.
- The debug build has `versionCode` 1 and `versionName` 1.0.0, because `flet debug` passes no `--build-number` or `--build-name` (`CLI/commands/debug.py:144-163`).
- On an iPhone it signs with the `debugging` table (§8.2), so it needs a valid Apple Development certificate and a development profile that includes the device. The owner's Mac has neither today (its Apple Development certificate is revoked); #121 creates them. Simulators need no signing.

Use it for anything the companion client cannot show:
- extensions and runtime permissions;
- the bundle id, icon, splash, fonts and deep links;
- storage paths, cold start and offline first launch.

Notes:
- Python changes need a re-run: there is no hot reload of the bundled Python.
- `--route` opens a route directly, which is handy for drill routes and deep-link landing.
- Debug builds are slow. Judge performance only with `--release` or `flet build` (D-80).

### 5.4 Desktop window (developer convenience only)

`uv run flet run -r` opens a desktop window (D-09). Use it for quick layout iteration at a phone-sized window. The UI flows never use it: `flet test` runs in device mode (D-78), and `flet test linux` in CI is spike S9's question.
- From a source pin it needs the Flet desktop client built from `.flet-src/client`, with `FLET_VIEW_PATH` set (`CONTRIBUTING.md` in the monorepo, "FLET_VIEW_PATH").
- Never add desktop-only code paths, and never judge touch targets, safe areas or gestures there.

### 5.5 Devices, emulators and logs

**The device set (D-102, D-107).** Work happens on Android emulators and iOS simulators first. The build reference devices are the AVD `pycon_pixel6a_api36` (Pixel 6a profile, 4 GB RAM, Android 16 API 36, Google APIs arm64; `emulator-5554` when it is the only one running) and an **iPhone 17** simulator on **iOS 26.5**. On the owner's Mac the iPhone 16 family exists only on the iOS 18.6 runtime, so use the iPhone 17 family (iPhone 17, 17 Pro, 17 Pro Max, 17e) on iOS 26.5. Also available: the AVDs `Pixel_9_Pro_XL_API_35` (Google Play, API 35) and `flet_probe_api34` (Google APIs, API 34; TalkBack is preinstalled), and an iPad Pro simulator for the tablet layout. An AVD whose system image is missing fails with "Cannot find AVD system path"; install the image named by `image.sysdir.1` in its `config.ini`, e.g. `sdkmanager "system-images;android-35;google_apis_playstore;arm64-v8a"`. The owner's iPhone is used only for checks that need hardware or a release build: release-build performance, the camera, notification delivery, TestFlight installs, VoiceOver, and the release build's exit journeys at phase exits. There is no Android phone; emulator timings are a relative regression signal only ([`testing-and-quality.md`](testing-and-quality.md) §8).

| Task | Command |
|---|---|
| List connected devices | `uv run flet devices [android\|ios]` (USB and wireless; `--device-connection attached\|wireless`) |
| Android emulators | `uv run flet emulators`; `uv run flet emulators start <name> [--cold]`; `uv run flet emulators create <name>` |
| iOS simulators | `xcrun simctl list devices available` for the udids; `xcrun simctl boot <udid>` and `open -a Simulator`, then `flet debug ios -d <udid>`. A simulator that a build left shut down comes back with `xcrun simctl boot <udid>`. Simulator builds need no signing. |
| Install an APK over the previous build | `adb install -r build/apk/pycon-us.apk`, then `adb shell am force-stop io.github.ndonkohenri.pyconus` before launching, so the update is judged from a cold start: a process still running from the old build keeps its old state until it stops. On the Android 16 emulator the install ended the running app both times it was tried (#53); the force-stop makes that certain. |
| Android Python log | `adb logcat -s flet.python` (`-d` dumps the buffer, `-c` clears it) |
| iOS simulator Python log | `xcrun simctl spawn booted log stream --style compact --predicate 'sender == "dart_bridge"'` |
| iPhone Python log | Console.app › the device › filter on the app process |
| A tester's log | Developer screen › Share log, which sends `console.log` (D-72) |

Physical devices:
- **Android** (a borrowed phone): enable developer options and USB or wireless debugging (`adb pair` for wireless).
- **iPhone:** enable Developer Mode (Settings › Privacy & Security), trust the Mac, and register the device in the team (§8.2).

### 5.6 Fake clock and feed

Off-season and in demos, the Developer screen (DEV-01, D-73) sets:
- a fake "now", stored in preferences and read by `clock.now()` (D-43);
- the feed URL.

Use the 2026 feed with a fake clock inside 2026-05-13..19 to exercise Now, Jump to now and reminders, until the 2027 feed exists (PLAN §7). Environment variables do not reach packaged apps, so there are no build flavours.

---

## 6. Mock API workflow (P3, NEW-08, D-50..D-57)

The private-API features (sign-in, favourites sync, role flags and the four staff tools) only ever talk to `tools/mock_api/`.
- **The guard (D-51).** Those features stay hidden until a mock base URL is set in the Developer screen. The client also refuses any `/api/v1` request to a `*.pycon.org` host, and a unit test covers it.
- **The contract** is in `tools/mock_api/README.md`, which cites Ionic's `pycon-api.ts`.

**Run it:**

```bash
uv run python -m tools.mock_api.server --host 0.0.0.0 --port 8000
```

The final options are documented in `tools/mock_api/README.md`. The planned interface:
- **On start,** it prints its LAN URL and the seeded accounts. There is one per role, from `tests/fixtures/mock/`; the keys and secrets are fake and exist only for the mock.
- **State** is in memory, so a restart is a clean slate. This also suits demos.
- **Faults (D-57)** are selected by flag: dropped connections, timeouts, "server committed, response lost", expired auth, a skewed clock (`--skew SECONDS`), and idempotent or non-idempotent capture semantics.

**Connect the app:** Developer screen › Mock API base URL.

| Where the app runs | Base URL |
|---|---|
| Companion client (Python on the laptop) | `http://localhost:8000` |
| Android emulator, packaged build | `http://10.0.2.2:8000` |
| iOS simulator, packaged build | `http://localhost:8000` |
| Physical phone, packaged build | `http://<laptop LAN IP>:8000`, on the same Wi-Fi |

**Practical notes:**
- **Cleartext HTTP.** The client is Python `httpx` on raw sockets. Android's cleartext policy and iOS App Transport Security govern the platform HTTP stacks, not these sockets, so no manifest change is expected. The iOS template allows arbitrary loads anyway. **UNVERIFIED on devices:** the first P3 device test confirms it, and the iOS local-network prompt question (§3.4) along with it.
- **The laptop firewall.** macOS asks to allow incoming connections for Python the first time; allow it.
- **Venue or office Wi-Fi often isolates clients.** Use a phone hotspot or a travel router instead.
- **Tests** never start the server. The same pure `handle()` sits behind `httpx.MockTransport` (D-50), so the CI tests cover signing, faults and both semantics without a network.
- **Badges.** The printable sheet of mock-badge QR codes for the P3 exit test is described in the mock README.
- **Stage demos** may need an in-app backend instead of the LAN mock. That is open decision O-8, decided at the P3 exit.

---

## 7. GitHub Actions (D-84)

### 7.1 Constraints of a private repo on GitHub Free

Check the current numbers in Settings › Billing; these were the terms at the time of writing.

| Constraint | Consequence for us |
|---|---|
| Included Actions minutes are limited, and macOS minutes count about 10× Linux | Everything runs on Linux. There is no iOS job (§7.5), and Android builds run only on demand or on tags. |
| Artifact storage is small (hundreds of MB) | APK artifacts are kept for 14 days. |
| Branch protection and rulesets are not enforced on private repos | `main` is protected by convention until the repo is public (D-88): PRs only, CI green, agents merge under D-100. Creating a ruleset returns HTTP 403 (checked 2026-10-11); AGENTS.md › Branches and commits has the ruleset to add once the repo is public. |
| Environments (and their secrets and required reviewers) are unavailable for private repos | We need none: CI holds no secrets (D-86). |

Conventions in every workflow:
- `permissions: contents: read`.
- `persist-credentials: false` on checkouts.
- Third-party actions pinned to a full commit SHA, with the version as a comment. The pins were checked against their release tags on 2026-10-11 (annotated tags followed to the commit): `actions/checkout` v6.0.3 is `df4cb1c069e1874edd31b4311f1884172cec0e10`, `astral-sh/setup-uv` v8.3.2 is `11f9893b081a58869d3b5fccaea48c9e9e46f990`; checked on 2026-10-12, `actions/upload-artifact` v7.0.1 is `043fb46d1a93c77aae656e7c1c64a875d1fc6a0a`.
- actionlint and zizmor (`uvx zizmor --persona=pedantic .github/workflows/`) are clean on every workflow change.
- `pull_request`, never `pull_request_target`.
- `UV_LOCKED=1`, so every `uv` command fails if `uv.lock` is stale.

### 7.2 `.github/workflows/ci.yml`: every PR and push to `main`

[`.github/workflows/ci.yml`](../.github/workflows/ci.yml) is the source of truth; this section says what it does and why.

**Required checks (D-100).** A PR may be merged only when every check below has passed on its latest commit. A missing, pending, skipped or cancelled required check is not green. Rename a job only together with this list.

| Workflow | Job id | Check name (as GitHub shows it) |
|---|---|---|
| `CI` (`ci.yml`) | `check` | `Lint, types and tests` |

`gh pr checks <n>` lists them. GitHub does not enforce this list on a private Free repo (§7.1); agents check it before merging.

**One Linux job**, `Lint, types and tests`. Its steps, in order (the first failure fails the job):

| Step | Command | Why |
|---|---|---|
| Check out the app | `actions/checkout` | |
| Read the Flet pin, check out Flet at the pin | `actions/checkout` of `flet-dev/flet` at `.flet-ref`, sparse `sdk/python`, into `.flet-src` | `uv.lock` points at the path sources there (§2.2). Delete both steps with the 1.1.0 pin. |
| Set up uv | `astral-sh/setup-uv`, `version: "0.12.x"`, `enable-cache: true` | uv stays on the `uv_build>=0.12,<0.13` line of `pyproject.toml`; unpinned, the action installs the latest uv, which warns that `uv_build` does not match it. Bump both together. The cache holds uv's packages, keyed on `uv.lock` and the `pyproject.toml` files. `uv sync` then installs CPython 3.14 from `requires-python`. |
| Install | `uv sync --locked` | Fails if `uv.lock` is stale (D-75). |
| Lint, Check formatting | `uv run ruff check`, `uv run ruff format --check` | D-74 |
| Type-check | `uv run pyright` | D-74 |
| Test | `uv run pytest` | D-76. `--hypothesis-profile=ci` joins once `tests/conftest.py` registers it (#114). |

**Triggers and concurrency.** It runs on every `pull_request` and on every push to `main`. The concurrency group is the PR number, so a new push to a PR cancels that PR's older run. A push to `main` gets a group of its own (the run id): in a shared group a newer run would replace a pending one, even with `cancel-in-progress: false`. So every commit on `main` keeps its own result.

The target is under 2 minutes (D-84). The time-zone tests run under two machine time zones through a pytest fixture, not a CI matrix (D-43). UI flows never join this job: spike S9 tries `flet test linux`, and a green result becomes a separate workflow through a `needs-decision` issue (D-78).

### 7.3 `.github/workflows/feed-check.yml`: weekly

```yaml
name: Feed check

on:
  schedule:
    - cron: "17 6 * * 1"    # Mondays 06:17 UTC
  workflow_dispatch:

permissions:
  contents: read

env:
  UV_LOCKED: "1"

jobs:
  feed:
    name: Parse the public feed
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10 # v6.0.3
        with:
          persist-credentials: false
      - name: Read the Flet pin
        id: flet
        run: echo "ref=$(cat .flet-ref)" >> "$GITHUB_OUTPUT"
      - name: Check out Flet at the pin
        uses: actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10 # v6.0.3
        with:
          repository: flet-dev/flet
          ref: ${{ steps.flet.outputs.ref }}
          path: .flet-src
          sparse-checkout: sdk/python       # uv needs only the Python packages here
          sparse-checkout-cone-mode: true
          persist-credentials: false
      - uses: astral-sh/setup-uv@11f9893b081a58869d3b5fccaea48c9e9e46f990 # v8.3.2
        with:
          enable-cache: true
      - run: uv run python tools/check_feed.py
```

- **What it checks.** `tools/check_feed.py` fetches the feed for `config.YEAR` and runs our parser plus the invariants (D-77) over it. It also reports, without failing, whether next year's feed has appeared.
- **Notification.** A failed scheduled run emails the person who last changed the schedule. That is the alert, so there is no issue bot.
- **Why the Flet steps.** They are there only because `uv sync` needs `.flet-src` to exist; they disappear with the 1.1.0 pin. `ci.yml` and this workflow check out only `sdk/python` (sparse), which holds the five path sources, so the monorepo's Dart client and website do not eat the 2-minute budget (D-84). `build-android.yml` keeps the full checkout, because `flet build` needs the template, the Dart package and `.fvmrc`.

### 7.4 `.github/workflows/build-android.yml`: on demand and on `v*` tags

[`.github/workflows/build-android.yml`](../.github/workflows/build-android.yml) is the source of truth; this section says what it does and why. It builds a debug-signed arm64 APK (D-84, D-86, D-106). It is not a required check (§7.2).

**Run it:** Actions › Build Android › Run workflow, or `gh workflow run build-android.yml --ref main`. Pushing a `vX.Y.Z` tag runs it too (§8.3). A new run for the same branch or tag cancels the older one.

**One Linux job**, `Debug-signed APK`, with a 45-minute timeout. Its steps, in order:

| Step | Command | Why |
|---|---|---|
| Check out the app | `actions/checkout`, `fetch-depth: 0` | The build number is the commit count (§4). The build also reads `flutter_packages/roboto_fonts` (§3.1). |
| Check that the tag matches the version | Tags only: the tag must equal `v` + `[project].version`; otherwise the job fails with an error naming both | §4 |
| Read the Flet pin and the build number | `cat .flet-ref`, `git rev-list --count HEAD` | |
| Check out Flet at the pin | `actions/checkout` of `flet-dev/flet` at `.flet-ref` into `.flet-src`: the whole tree at depth 1, not sparse | `flet build` needs the template, `.fvmrc` and the Dart package `packages/flet`, which it adds to `pubspec.yaml` as a path dependency (§2.2). Delete the step with the 1.1.0 pin. |
| Set up uv | `astral-sh/setup-uv`, `version: "0.12.x"`, `enable-cache: false` | The same uv line as `ci.yml` (§7.2). No cache: a tag build starts from clean inputs, and `uv sync` takes seconds. |
| Install | `uv sync --locked` | D-75 |
| Build the APK | `uv run flet build apk --arch arm64-v8a --build-number <count> --yes -v`, with `FLET_CLI_NO_RICH_OUTPUT=1` | The command of §8.1 with D-106's ABI. `--yes` lets flet-cli download Flutter (the version in `.flet-src/.fvmrc`) into `~/flutter`; it uses the runner's JDK 17 (`JAVA_HOME`) and Android SDK (`ANDROID_HOME`). `-v` and plain output keep the log useful when a build fails. |
| Name the APK | `build/apk/pycon-us.apk` → `pycon-us-<count>-<short sha>-arm64-v8a.apk` | Downloads from different runs don't collide. |
| Upload the APK | `actions/upload-artifact`, `archive: false`, `retention-days: 14` | The APK is already compressed, so it is uploaded as-is and the artifact takes the file's name. 14 days, because artifact storage is small (§7.1). |

**Measured** on the first run ({{RUN}}, uncached, Flet `15854a0ac`):
{{MEASURED}}

**Why not `flet-dev/flet-build-action`.** It was the plan, but running the documented command directly is simpler and correct under the source pin (`ACTION/action.yml` at `v1`):
- Its own `setup-uv` step installs the latest uv, which would replace the `0.12.x` line we keep with `uv_build` (§7.2).
- Its Flet download cache is keyed on the reported Flet version, a constant `0.1.0` under the source pin (§2.2). After a pin bump it would restore the previous pin's downloads unless someone remembers to run once with `cache: false` (the S5 caveat).
- It zips the APK into `flet-apk.zip`, which saves nothing on an already-compressed file.
- P0-06 asks for the same commands as this document, and one `flet build apk` line is exactly that.

When 1.1.0 is on PyPI and the Flet checkout goes, the action is worth another look: its Flutter SDK cache would save {{FLUTTER}} per run.

**No caches.** The Flutter SDK download is the slow part of the build, but the workflow runs rarely, and a cache would be one more key to keep right across pin bumps.

**This APK is a quick look, not an install to keep.** It is signed with the runner's throwaway debug key, which differs from your machine's and can change between runs.
- Download it with `gh run download <run-id>` (or from the run page), then run `adb install pycon-us-<…>.apk`, or open the file on the phone.
- Installing over a build signed with another key fails with `INSTALL_FAILED_UPDATE_INCOMPATIBLE`. Run `adb uninstall io.github.ndonkohenri.pyconus` first, which loses the app's data.
- Builds you want to keep updating come from §8.1 instead.

### 7.5 Not in CI: iOS

iOS builds run on the owner's Mac (D-84). Signing material never enters CI (D-86).

**If that ever changes** (open a `needs-decision` issue that supersedes D-84 and D-86):
- **The cheap step** is a manual `ios-simulator` job on `macos-latest`. It needs no signing, so it is a compile check only. Each run uses a sizeable slice of the month's macOS allowance.
- **A TestFlight job** follows `DOCS/publish/ios.md` "Building and signing in CI":
  - repository secrets `IOS_CERTIFICATE_P12` and `IOS_CERTIFICATE_PASSWORD` (the owner's Apple Distribution certificate);
  - `APPLE_API_ISSUER`, `APPLE_API_KEY_ID` and `APPLE_API_KEY_P8` (an App Store Connect API key with the App Manager role, used to download the profile and to upload);
  - the variable `APPSTORE_APP_ID`;
  - `apple-actions/import-codesign-certs` and `apple-actions/download-provisioning-profiles`, then `xcrun altool --upload-package`.
- **Android Play uploads** would need the keystore (base64) and the `FLET_ANDROID_SIGNING_*` values as secrets.
- **Without environments on a private Free repo,** all of these would be plain repository secrets, readable by any workflow on any branch. That is one more reason to keep signing local.

---

## 8. Signing and distribution (D-85, prov. O-5)

The owner's own accounts are the only route, and testing is internal only. There is no public listing (D-85, D-36).

**Where secrets live (D-86):**
- in the owner's password manager, plus local files outside the repo: the keystore in `~/keys/`, the App Store Connect API key in `~/.appstoreconnect/private_keys/`, the certificates in the login keychain;
- never in the repo, CI, issues or PRs.

### 8.1 Android

| Route | Build | Signed with | Notes |
|---|---|---|---|
| Quick look | CI artifact (§7.4) or local `flet build apk --arch arm64-v8a` (D-106) | The debug key | Uninstall before switching builds |
| Owner's emulator (and a borrowed phone), kept updated | Local `flet build apk --arch arm64-v8a` | The **upload key** | Updates install in place, and data survives (the P0 exit criterion) |
| Testers | Local `flet build aab` → Play Console › **Internal testing** | The upload key; Play re-signs with its app signing key | Up to 100 testers by email list; no review. Testers install through an opt-in link. |

A device can update in place only from one signing identity: our upload key (sideload) or Play's app signing key (Play), not both. Pick one route per device. Switching means uninstalling first.

**The upload key**, created once:

```bash
mkdir -p ~/keys
keytool -genkeypair -v -keystore ~/keys/pyconus-upload.jks \
    -keyalg RSA -keysize 2048 -validity 10000 -alias upload
```

**A signed local build:**

```bash
# The values come from the password manager; nothing is written to the repo.
export FLET_ANDROID_SIGNING_KEY_STORE=~/keys/pyconus-upload.jks
export FLET_ANDROID_SIGNING_KEY_ALIAS=upload
read -rs FLET_ANDROID_SIGNING_KEY_STORE_PASSWORD && export FLET_ANDROID_SIGNING_KEY_STORE_PASSWORD
uv run flet build aab --build-number "$(git rev-list --count HEAD)"   # or: apk --arch arm64-v8a
```

- flet-cli reads these four variables (`CLI/commands/build_base.py:3118-3150`). One password fills the other, and the alias defaults to `upload`. The template switches the release build to that signing config (`TPL/android/app/build.gradle.kts:102-118`).
- **Play Console setup,** once, after O-4 settles the identity:
  - create the app under the neutral working name;
  - keep Play App Signing (the default for new apps);
  - complete the declarations Play asks for before the first internal release.
- **Target API.** Play enforces a minimum `targetSdk` on uploads; ours is 36, the latest stable level (D-106).
- **The bundle id cannot change** once an app exists in Play Console. That is why O-4 must be decided before this step.

### 8.2 iOS

| Route | Build | Needs |
|---|---|---|
| The owner's iPhone, during development | `uv run flet debug ios -d <id>` (add `--release` to judge performance) | `team_id`, an Apple Development certificate, a Development provisioning profile that includes the device, and the device registered |
| Testers | `uv run flet build ipa --ios-export-method app-store-connect` → upload → TestFlight **internal testing** | An Apple Distribution certificate, an App Store provisioning profile and an App Store Connect record |

**Why the export method is chosen per command.** `flet debug` has no export-method default of its own: like `flet build`, it takes `--ios-export-method`, then `[tool.flet.ios] export_method`, then `debugging`, and signs with that method's profile and certificate (`CLI/commands/build_base.py:1466-1501`). The template writes them into the Debug, Release and Profile configurations with Manual signing (`TPL/ios/Runner.xcodeproj/project.pbxproj:363-373, 557-567, 589-599`), so Xcode never creates a profile for us. A distribution identity and an App Store profile cannot install an app on a device. So `export_method` stays unset (`debugging`, used by `flet debug ios`), and only the TestFlight build passes `--ios-export-method app-store-connect`.

Internal TestFlight testers are members of the owner's App Store Connect team: up to 100 people, with no Beta App Review. A build expires after 90 days. **External** testing would need Beta App Review, and the store name would then be visible outside the team, so it is out of scope (D-85).

**Setup** (owner-only, #121), first with a throwaway bundle id, then with the O-4 identity. Today the Mac has a valid Apple Distribution identity, but its Apple Development certificate is revoked and no profile exists for our bundle id (S5):
1. Register an explicit App ID for the bundle id, and register the owner's devices.
2. Create an Apple Development certificate and a **Development** provisioning profile for the App ID that includes those devices (`flet debug ios` needs it; see the Flet blog post "flet debug", 2025-12-02, "Testing on a real iPhone/iPad device"). Regenerate it whenever a device is added.
3. Create an Apple Distribution certificate, and an App Store profile. Name both profiles exactly as in `pyproject.toml`.
4. Create an App Store Connect record under the neutral working name (O-4) and a SKU.
5. Commit the signing configuration. Team ids and profile names are not secrets; another contributor overrides them with `--ios-team-id` and `--ios-provisioning-profile` (`DOCS/publish/ios.md` "Resolution order"). P0-04 (#52) committed the team id and the certificate names; the two `provisioning_profile` lines follow once #121 has created the profiles.

As applied in `pyproject.toml` (§3.1), with the lines #121 adds commented out:

```toml
[tool.flet.ios]                       # signing (development.md §8.2); not secret (D-86)
team_id = "VF87YBAN84"
# No export_method: the default "debugging" serves flet debug ios; TestFlight builds pass
# --ios-export-method app-store-connect. No provisioning_profile yet (#121): flet build ipa
# then passes --no-codesign and produces an .xcarchive.

[tool.flet.ios.export_methods.debugging]
# provisioning_profile = "<development profile incl. the owner's devices>"   (#121)
signing_certificate = "Apple Development"

[tool.flet.ios.export_methods."app-store-connect"]
# provisioning_profile = "<exact profile name from the portal>"              (#121)
signing_certificate = "Apple Distribution"
export_options = { manageAppVersionAndBuildNumber = false }   # Xcode must not renumber
```

**What `flet build ipa` produces** (S5, #52):

| Signing state | Outcome |
|---|---|
| No `provisioning_profile` for the chosen method (today, until #121) | flet-cli's warning panel, a build with `--no-codesign`, and only `build/ipa/pycon-us.xcarchive` (about 240 MB; the `.app` inside is about 77 MB). No `.ipa`. |
| A profile named but not installed on the Mac | flet-cli's pre-check stops within seconds, before Xcode: "Provisioning profile '…' is not installed", followed by the installed profiles. It also checks expiry, the team and the bundle id (`CLI/commands/build.py:287-379`). |
| A matching profile installed | A signed **`build/ipa/pycon_us.ipa`** (underscore, unlike the other artifacts; 44.8 MB in S5), `Apple Distribution` authority, `codesign --verify --deep --strict` clean. |

Either way, the chosen table reaches the generated project: `CODE_SIGN_IDENTITY` and `DEVELOPMENT_TEAM` in the Runner's build settings, and `method`, `teamID`, `signingCertificate` and `manageAppVersionAndBuildNumber` in `build/flutter/ios/exportOptions.plist`. Simulator builds are signed ad hoc whatever the table says.

**Build and upload:**

```bash
uv run flet build ipa --ios-export-method app-store-connect --build-number "$(git rev-list --count HEAD)"
xcrun altool --upload-package build/ipa/*.ipa -t ios \
    --apiKey "$ASC_KEY_ID" --apiIssuer "$ASC_ISSUER_ID" --apple-id "$ASC_APP_ID"
```

The Transporter app is the no-terminal alternative (`DOCS/publish/ios.md` "Uploading app to App Store Connect for distribution"). `altool` reads `~/.appstoreconnect/private_keys/AuthKey_<KEY_ID>.p8`.

**ITMS-91053 is still open (#121).** The template ships no `PrivacyInfo.xcprivacy`, and `Python.framework` uses required-reason APIs without one (S5), so App Store Connect may report ITMS-91053 on the first upload. If it rejects the build, that becomes an upstream item (U13), not an app workaround; meanwhile testers get Android builds and the iPhone runs `flet debug ios`.

**Troubleshooting** is in `DOCS/publish/ios.md` › "Troubleshooting". The usual one: an `.xcarchive` but no `.ipa` means no provisioning profile was selected.

### 8.3 A build for testers: the checklist

There is no release train. The procedure:
1. `main` is green, and the phase status issue lists what this build is for.
2. **Snapshot PR:** run `uv run python tools/update_snapshot.py`, which refreshes `data/<year>/conference.json` (D-38, NEW-03). Review the diff, then merge.
3. **Version PR:** bump `[project].version` and `__version__` (§4), then merge.
4. **Tag** `vX.Y.Z` on `main`. `build-android.yml` builds the quick-look APK.
5. **Locally, at the same commit:**
   - check the pin (§2.2) and run `uv sync`;
   - signed AAB → Play internal testing;
   - IPA (`--ios-export-method app-store-connect`, §8.2) → TestFlight.
6. **Smoke-test** on an Android emulator (the signed APK or AAB build, installed over the previous one, then force-stopped; §5.5) and on the iPhone (the TestFlight build, installed over the previous one): airplane-mode start and the core journeys. At a phase exit, run the full device checklist (D-79, D-102).
7. **Record** in the phase status issue: the version, build number, Flet pin, devices and emulator images, cold-start times (the iPhone's against D-80; the emulator's as a relative signal, D-102) and app sizes.

---

## 9. Later: a public release

Nothing here is planned. It is the list we would work through if the owner ever chooses to publish (PLAN appendix).

| Topic | What it takes |
|---|---|
| **Trademark** | "PyCon" and the PyCon and PSF logos are PSF trademarks, and Apache-2.0 grants no trademark rights (D-36, D-87). A store listing needs either the PSF's written permission under its trademark usage policy, or a name and icon with no PSF marks. Even then the app describes an event the PSF runs, so App Review's intellectual-property rules (guideline 5.2) and Play's impersonation policy apply. "Not an official PSF app" stays wherever the app names itself. |
| Identity | The final name, icon and bundle id (O-4). The bundle id cannot change once a store record exists. |
| Accounts | Apple: individual, or organisation (needs a D-U-N-S number). Google Play: new personal accounts must run a closed test (a minimum number of testers for 14 days) before production access; check the current rules. |
| Privacy | A privacy-policy URL (both stores require one). App Privacy: "Data Not Collected", since there are no analytics, no crash service and favourites stay on the device (D-08, D-72). The Play Data safety form. |
| Private API | Public builds keep the D-51 guard: the mock-only features are invisible without the Developer screen. A real backend needs the PSF (PLAN appendix). |
| Content and licences | Review `NOTICE`, the reused Ionic assets (floor plans, D-87), sponsor logos and the bundled dependencies' licences once. |
| Signing in CI | Optional at that point: move the keys to CI secrets (§7.5), superseding D-86 by decision. |
| Store assets | Screenshots, descriptions, the age-rating questionnaires. |

---

## 10. Open items this document depends on

S5 closed the rows it answered: builds from the `.flet-src` setup (§2.2, §8), the companion client (§5.2), Roboto (§3.4, D-105), the SDK levels and sizes (§2.1, D-106) and the Gradle heap on the Mac (§2.1).

| Item | Owner of the answer | Until then |
|---|---|---|
| ITMS-91053 on the first TestFlight upload (§8.2) | #121 | Testers get Android builds; the iPhone runs `flet debug ios` once it has a development certificate |
| An iPhone development certificate and profiles; the release numbers on the iPhone | #121 | Simulators only for iOS (§5.3) |
| `build-android.yml` on a GitHub runner: the `-Xmx4G` heap, `--arch arm64-v8a`, the first run's time | P0-06 (#54) | Raise the heap, or move the override to a CI-only `~/.gradle/gradle.properties` |
| A Flet companion app in the stores that speaks 1.1 | Flet 1.1.0 release | The companion client from `.flet-src/client` (§5.2), or `flet debug` |
| App identity: name, icon, bundle id, URL scheme | O-4 | Placeholders as in §3.1 |
| Distribution routes | O-5 | Internal only (D-85) |
| Cleartext HTTP and iOS local-network behaviour with the LAN mock | The first P3 device test | Use the companion client or the emulator |
