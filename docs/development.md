# Development, build and release

**Status:** verified guide (v3), 2026-10-12. The developer guide of D-96. P0-05 (#53) completed it from the S5 verdict ([`spikes/05-build-and-ship.md`](spikes/05-build-and-ship.md)) and checked §5.1-§5.3 from a fresh clone on the reference emulator and simulator. #849 rewrote §5.1 for a clean Mac on 2026-11-02; what it couldn't check is marked there, and the timed clean-machine run is #850. The test strategy is in [`testing-and-quality.md`](testing-and-quality.md) (D-76..D-80). **Binding:** [`PLAN.md`](../PLAN.md) and [`decisions.md`](decisions.md) (D-ids). Where this document applies a decision, it cites it.

**Scope.** This document covers how we build, run and distribute the app on **Android and iOS only** (D-09). There are no web, PWA or desktop targets. A desktop window is a developer convenience at most (§5.4).
- The project file, validated against the local flet-cli (§3).
- Versioning (§4).
- The development loop (§5).
- The mock API workflow (§6).
- GitHub Actions for a private repo (§7).
- Signing and internal distribution (§8).
- What a public release would need later (§9).

**Feature ids** implemented here: DEV-08, NATIVE-01, NATIVE-02, NATIVE-03, NATIVE-06 (declarations), NEW-03 (snapshot step), NEW-07 (configuration) and NEW-08 (workflow). Not built: DEV-07, LIVE-01..04, NATIVE-04/05/07/09/10 and NOTIF-12 ([`feature-matrix.md`](feature-matrix.md)).

**Path aliases.** All are inside a clone of flet-dev/flet at our version (`v1.1.0.dev4`, the commit `a9ef26fdb`; optional, §2.2), unless stated. Line numbers are at that commit, and re-checked when it moves; those into `CLI/commands/build_base.py`, which `flet-dev/flet#7036` rearranged, are at `22a6dcb16` unless a row has been redone since (#1007).

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
| Set up a fresh clone | `gh repo clone …`, `uv sync --locked` | §5.1 |
| Run the real app shell on an emulator, simulator or phone | `uv run flet debug android -d emulator-5554` (or `ios -d <udid>`); `-d` is required | §5.3 |
| Run the app with Python hot reload | `BROWSER=true uv run flet run -r -w -p 8550`, plus `flutter run -d <id>` in a Flet clone's `client` | §5.2 |
| List devices or emulators | `uv run flet devices`, `uv run flet emulators` | §5.5 |
| Lint, type-check and test | `tools/check.sh` (`ci.yml`'s steps; `--fast` skips pytest), or one step, e.g. `uv run pytest` | §7 |
| Gate PRs and merge them (D-100, D-273) | `tools/merge.sh <pr> [<pr>...]`, the PRs in merge order | §7 |
| Start the mock API (from P3) | `uv run python -m tools.mock_api.server --host 0.0.0.0` | §6 |
| Keep a mock on your checkout's own port | `uv run python -m tools.mock_api.own start`, `url android`, `stop` | §6 |
| Build an APK for the emulator | `uv run flet build apk --arch arm64-v8a --build-number $(git rev-list --count HEAD)` (D-106) | §8.1 |
| Build an AAB for Play | `uv run flet build aab --build-number $(git rev-list --count HEAD)` | §8.1 |
| Build an IPA for TestFlight | `uv run flet build ipa --ios-export-method app-store-connect --build-number $(git rev-list --count HEAD)` | §8.2 |
| Get a quick-look APK | Locally, the emulator APK above (§8.1); or a manual run, `gh workflow run build-android.yml --ref main` (or Actions › Build Android › Run workflow), then `gh run download <run-id>`. While the repo is private a `v*` tag builds nothing (D-273) | §7.4 |
| Refresh the bundled feed snapshot (from P0-17) | `uv run python tools/update_snapshot.py` | §8.3 |
| Run the UI flows on an emulator or a simulator | `uv run flet test android -d emulator-5580 --tests-dir tests/ui -v` (or `ios -d <udid>`) | §5.7 |
| Run the Maestro device journeys on a packaged build | `maestro --device emulator-5570 test --include-tags=journeys maestro` (or `--device <udid>`) | §5.9 |
| Set up a worktree of this repo | `tools/setup_worktree.sh`, then §5.0 to a device | §5.8 |
| Build, debug or test while another build may run (parallel agents) | Prefix each command with `PUB_CACHE=$PWD/build/pub-cache`, which `tools/setup_worktree.sh` made | §5.8 |
| Upload a PR's screenshots; set a board status | `tools/pr_shots.sh <pr> <shots>.png`; `tools/board.sh <n> in-progress` (or `in-review`) | AGENTS.md |
| Photograph the staff tools per text size and appearance | `uv run python -m tools.sweep --device <id> --modes default max` | `maestro/README.md` |
| Check the feature matrix after editing it (ids, vocabulary, counts; also run by `tests/test_check_matrix.py`) | `uv run python -m tools.check_matrix` (`--breakdown` for the fuller counts) | — |
| Check the live public feed (what `feed-check.yml` runs; no weekly run while the repo is private, D-273) | `uv run python -m tools.check_feed`, or `gh workflow run feed-check.yml --ref main` | §7.3 |

---

## 2. Toolchain

### 2.1 Facts (verified 2026-10-12 at `15854a0ac`; re-verified 2026-10-28 at `08b89cce5`, #445; Python again in #700; pin, Flutter and Python at `22a6dcb16` on 2026-10-30, #805, and at `a9ef26fdb` on 2026-11-03, #1005; PyPI, Flutter, JDK and the Android SDK on 2026-11-02, #849)

| Fact | Value | Source |
|---|---|---|
| Flet | **1.1.0.dev4** from PyPI, the commit `a9ef26fdb` on flet-dev/flet's `flet-1.1.0` branch (§2.2). Before it, a source checkout at `a9ef26fdb`, `22a6dcb16` (before #1005) and `08b89cce5` (before #805); the first pin (`3710aff`, on `main`) was 1.0.4 plus fixes, whose template targets iOS 13.0, which Xcode 27 rejects. PyPI's latest stable is 1.0.5. | D-81, D-104, D-479; F20; S5 |
| Flutter | **3.47.9** (3.47.8 before `a9ef26fdb`, 3.47.7 before `22a6dcb16`), written into the `flet` wheel (`flet.version.flutter_version`). flet-cli uses `~/flutter/3.47.9` if it exists, else the `flutter` on `PATH` if its major.minor matches (any 3.47.x, without a word: #1004, #1006); otherwise it asks, then downloads 3.47.9 into `~/flutter/3.47.9` (about 5 minutes; `--yes` skips the question). It adds that SDK to `PATH` only for its own subprocesses, not your shell. So keep that version in `~/flutter` (§2.2, step 3); `tools/setup_worktree.sh` says when it's missing. | `flet/version.py` `get_flutter_version`; `CLI/commands/flutter_base.py:207-234, 252-280, 334-338, 482-494`; `CLI/utils/flutter.py:43-55` |
| JDK (Android builds) | **17**. flet-cli uses `JAVA_HOME`, then `/usr/libexec/java_home`, if either is a JDK 17; otherwise it downloads Temurin **17.0.13+11** into `~/java/17.0.13+11`. Either way it runs `flutter config --jdk-dir=<that JDK>`, a global Flutter setting. A newer system JDK is ignored. | `CLI/utils/jdk.py:15-18, 87-163`; `CLI/commands/flutter_base.py:382-405` |
| Android SDK | `ANDROID_HOME`, then `ANDROID_SDK_ROOT`, then Android Studio's `~/Library/Android/sdk`, then `~/Android/sdk`; if none exists, flet-cli asks and installs one into `~/Android/sdk`. | `CLI/utils/android_sdk.py:42-103, 269` |
| Python in the app | CPython **3.14.10** on both platforms since 2026-10-27 (About this app on an iOS 26.5 simulator and an API 36 emulator, #700; again at `22a6dcb16`, #805, where flet-cli pins python-build `20261027` and the template serious_python 6.1.2, so the manifest and the bundle agree; and at `a9ef26fdb`, #1005, with serious_python 6.1.3, which changes only its command output); 3.14.8 in #445's builds, 3.14.7 before `08b89cce5` (S5). flet-cli picks only the minor, 3.14, from `requires-python = ">=3.14,<3.15"`; the patch comes from the `serious_python_*` platform packages pub resolves, which float (below). The packaging step builds site-packages and `.pyc` with 3.14.10 too. | Minor: `CLI/utils/python_versions.py:31` (python-build `20261027` at `22a6dcb16`; `20261016` at `08b89cce5`) and `CLI/commands/build_base.py:3355` (`SERIOUS_PYTHON_VERSION` only). Patch: `serious_python_darwin`/`_android` 6.1.0 `python_versions.properties:5, 10` (python-build `20261027`, 3.14.10), read by the podspec (`:49-50`) and `build.gradle.kts:44-45`. Packaging: `serious_python` 6.1.2 `lib/src/python_versions.dart:57`, used by `bin/package_command.dart:762` (`compileall` at `:331, 510`). U229 (#702) |
| Android SDK levels | **`minSdk` 24, `targetSdk` 36, `compileSdk` 36**: Flutter's defaults. We set neither `min_sdk_version` nor `target_sdk_version` (D-106). 36 meets Play's target-API rule. **Run on API 24** (§5.10); the iOS 15 floor is declared, not run (§5.10). | `TPL/android/app/build.gradle.kts:78-87`; `aapt2 dump badging` in #125 |
| Android ABIs | `arm64-v8a`, `x86_64` and `armeabi-v7a` by default. APKs for our emulators and CI are `--arch arm64-v8a` only; AABs keep all three (D-106). | `PythonRelease.android_abis`; D-106 |
| Sizes | arm64 APK **59.4 MB** at `08b89cce5` (59,393,961 bytes, #445); 56.2 MB at `15854a0ac` (56,208,812 bytes, #125, with Roboto). Without Roboto (S5): universal APK 142.5 MB, AAB 102.5 MB, an arm64 phone's download from Play 26.6 MB (bundletool). | #125; S5 |
| Build number | `--build-number <commit count>` becomes Android `versionCode` and iOS `CFBundleVersion`; `[project].version` becomes `versionName` and `CFBundleShortVersionString` (§4). `flet debug` passes neither, so a debug build has `versionCode` 1 and `versionName` 1.0.0. | `CLI/commands/build.py:211-220`; `CLI/commands/debug.py:140-159` |
| iOS minimum | 15.0, fixed by the template | `TPL/ios/Runner.xcodeproj/project.pbxproj:348` |
| Android release signing without a keystore | Signed with the **debug key**: it installs, but cannot go to Play | `TPL/android/app/build.gradle.kts:103-119` |
| `flet build ipa` and signing | No profile configured: `--no-codesign` and only an `.xcarchive`. A profile configured but not installed: flet-cli stops within seconds, before Xcode. Installed: a signed `.ipa` (§8.2). | `CLI/commands/build.py:195-204, 297-389` |
| What gets bundled | `[project].dependencies` (plus `[tool.flet.<platform>].dependencies`), pip-installed at build time. **`uv.lock` does not apply**, so bundled dependencies are pinned exactly in `pyproject.toml`, and a package the app imports is listed there itself (D-470); what those pull in is whatever pip resolves that day (§7.6). | `CLI/commands/build_base.py:2738-2780` |
| App metadata at runtime | The app directory is copied, not installed, so `importlib.metadata` cannot see `pycon-us` | F15 |
| Deep links on mobile | Each key (`scheme`, `host`) from `[tool.flet.<android\|ios>.deep_linking]`, else from the common `[tool.flet.deep_linking]` (`flet-dev/flet#6953`, in the pin since `68a4b326c`). The template registers a link when a scheme resolves (both had to until `a9ef26fdb`, `flet-dev/flet#7031`; we set both, D-269): on Android an intent filter for the scheme and host, on iOS a `CFBundleURLTypes` entry for the scheme alone (the host is its `CFBundleURLName`). A host without a scheme, or `http`/`https` without a host, stops the build. Flutter's own deep-linking flags left both files at that pin: they are on by default (`deep_links` passes, #1005). The host never reaches Python: Flet keeps only the link's path, query and fragment for `page.route`. | `CLI/commands/build_base.py:2801-2855` (`get_deep_linking`); `TPL/android/app/src/main/AndroidManifest.xml:40-48`; `TPL/ios/Runner/Info.plist:53-67`; D-269 |
| Gradle heap | The template default is `-Xmx8G`, more than a standard GitHub runner has. Our `-Xmx4G` override (`[tool.flet.android.gradle_properties]`) passed every build on the Mac and on `ubuntu-latest` (#54: at least 1 GB stayed available; §7.4). | `CLI/commands/build_base.py:1175-1184, 1290-1293` |
| Logs | Android: logcat tag `flet.python`. iOS: unified log, sender `dart_bridge`. Both also write `console.log`. | `DOCS/publish/android.md` and `DOCS/publish/ios.md`, "Reading your app's output" |
| flet-build-action | Runs `uv run flet --version --json`, then `flet build <target> --yes --verbose --output …`, then archives. It never signs or uploads. `build-android.yml` runs `flet build` directly instead (§7.4). | `ACTION/action.yml`; `ACTION/scripts/flet_action.py:112-232` |

**Why the Flet pin does not pin the Python patch (#700).** At `08b89cce5`, flet-cli and serious_python agree: flet-cli's python-build release is `20261016` (3.14 → 3.14.8), the template pins `serious_python: 6.0.1` exactly (`TPL/pubspec.yaml:26`), and serious_python 6.0.1's `lib/src/python_versions.dart:13, 56-58` says the same. But serious_python 6.0.1 asks for its platform packages with carets (`pubspec.yaml:32-36`, `^6.0.1`), so pub takes the newest 6.x, and the platform packages are what download and bundle the runtime. Since `serious_python_darwin` and `serious_python_android` 6.1.0 reached pub.dev (2026-10-27), every build gets python-build `20261027`, CPython 3.14.10 (`build/flutter/pubspec.lock`, `dist_ios/.python_build_id` `3.14.10-20261027`). Neither a stale cache nor a worktree caused it: a fresh clone of `~/.pub-cache` resolves the same. At `22a6dcb16` (#805) flet-cli pins python-build `20261027` and the template `serious_python: 6.1.2`, so the manifest says 3.14.10 too; the carets remain, so a later 6.x platform package can still move the patch. It is harmless while the minor holds (flet-cli fixes it, and cp314 wheels and `.pyc` files work on any 3.14.x), so we take the patch releases. To check which Python a build ships, read the `serious_python_*` lines of `build/flutter/pubspec.lock`, or About this app on the device. To hold a build to flet-cli's manifest, pin the platform packages in `[tool.flet.flutter.pubspec.dependency_overrides]` (`CLI/commands/build_base.py:2034-2050`). The upstream fix is U229 (#702).

### 2.2 Flet from PyPI: the prereleases, then 1.1.0 (D-81, D-479)

**What we run.** Every Flet package comes from PyPI at one exact version, `1.1.0.dev4` today, which is the commit `a9ef26fdb` on `flet-dev/flet` (tag `v1.1.0.dev4`). No checkout of Flet is needed to set up, test or build.

| Piece | Where it comes from | What pins it |
|---|---|---|
| Python, in the venv and in the app | The wheels: `flet`, `flet-cli`, `flet-web`, `flet-desktop`, `flet-platform-assets`, `flet-notifications`, `flet-permission-handler`, `flet-secure-storage` | `==` in `pyproject.toml`, all the same (`tests/test_bundled_dependencies.py`). `uv.lock` holds them for the host; `flet build` reads `pyproject.toml` (§2.1) |
| Build template | The GitHub release: `https://github.com/flet-dev/flet/releases/download/v1.1.0.dev4/flet-build-template.zip`, kept in `~/.flet/cache/build-template/v1.1.0.dev4/` (or `$FLET_CACHE_DIR`) | `flet-cli`'s version |
| Flutter | `flet.version.flutter_version`, written into the wheel: 3.47.9 | `flet-cli`'s version |
| Dart `flet` package | The template's `pubspec.yaml`: `git: {url: flet-dev/flet, ref: <40-character SHA>, path: packages/flet}`, under `dependencies` and `dependency_overrides` | The template |
| Dart extensions (`flet_notifications`, `flet_permission_handler`, `flet_secure_storage`) | The wheels' `flutter/<name>/`, copied to `build/flutter-packages/` | The Python package's version |
| `serious_python` | pub.dev, exactly as the template says (6.1.3); its platform packages float inside its caret (§2.1, #702) | The template |
| `flet_integration_test`, `flet test` only | `git` at the tag `v1.1.0.dev4`, `packages/flet_integration_test` | `flet-cli`'s version |

**Dart and prereleases: the owner's question.** Flet publishes no Dart prereleases to pub.dev, and it doesn't matter here: a prerelease's template names the Dart package by its exact commit, so pub fetches it from GitHub. The wheels' extensions say `flet: path: ../../../../../../../packages/flet`, a path that exists only in Flet's own repository; the template's `dependency_overrides` beats it. That is how a stable release works too: 1.0.5's wheels hold the same path, and its template has `flet: 1.0.5` under both keys (#1027).

The price of the git dependency: a build needs `git` and github.com, and pub keeps a mirror of Flet's repository (250 MB) and a checkout of the commit (180 MB) in the pub cache (§5.8).

**Reading Flet's source.** The Python is in `.venv/lib/python3.14/site-packages/`. The Dart is in the pub cache after a build: `build/flutter/.dart_tool/package_config.json` says where. For the rest (the client, the docs, the template as written), keep a clone if you want one; nothing needs it, and it's git-ignored at this path:

```bash
git clone --filter=blob:none --branch v1.1.0.dev4 https://github.com/flet-dev/flet.git .flet-src
```

The source paths in this document are in that tree (the aliases above). Never edit Flet's files in it: a gap is an upstream issue (D-213).

**Bumping to the next prerelease, `dev5` or later**, in its own PR (`chore/<issue>-bump-flet`, D-92):
1. Set the version on every Flet line of `pyproject.toml`, and run `uv lock`, then `uv sync`. Our `httpx` pin must stay inside Flet's range: `uv lock` stops with "No solution found" otherwise, so set the version it now needs and say so in the PR. Otherwise the pin stays, even if the lock could take a newer one (D-470).
2. Check what the release's template pins: `curl -sL https://github.com/flet-dev/flet/releases/download/v<version>/flet-build-template.zip | tar -xOf - '*/pubspec.yaml'`. `flet`'s `ref` must be the tag's commit (`git ls-remote https://github.com/flet-dev/flet.git 'refs/tags/v<version>^{}'`), and the three extensions on PyPI must exist at that version, or the bump waits.
3. If `uv run flet --version` names a new Flutter, put it in `~/flutter/<version>`, or builds quietly take any `3.47.x` on `PATH` (#1006): `cp -cR ~/fvm/versions/<version> ~/flutter/<version>` with fvm, else `git clone -b <version> --depth 1 https://github.com/flutter/flutter.git ~/flutter/<version>`. After a build, `build/flutter/.dart_tool/version` must say that version and `build/flutter/android/local.properties` that `flutter.sdk`.
4. Delete `build/` (`rm -rf build`) on every bump, then `tools/setup_worktree.sh`. Build once before starting parallel builds: two first builds of a version at once can fail on the template's download (U286; a second try works). It caches Dart build-hook binaries compiled by the previous Flutter, which a newer Flutter refuses ("Invalid kernel binary format version"; seen in #120 going from 3.44.8 to 3.47.7; since `a9ef26fdb` flet-cli clears `.dart_tool` when the Flutter version changes, `flet-dev/flet#7039`, but the rest of this step still stands), and the generated app shell.
5. Run the full checks, then build and smoke-test on an Android emulator (`flet build apk --arch arm64-v8a`; and re-run §8.1's backup and restore check, D-472) and an iOS simulator (`flet build ios-simulator`). After the build, `uv run pytest tests/test_theme.py tests/test_high_contrast.py -k flet -rs` must run the two tests that mirror Flet's Dart source and skip neither: they can't run where no build has fetched it, so neither the gate nor CI runs them. A release build on the iPhone only when the bump touches something that needs hardware (D-102). On Android, `adb shell uiautomator dump` must still show `resource-id` `app.nav.<tab>` on each bottom-bar destination's node, and `<tab>.title` on the node with the root's title text (D-170): D-166 relies on Flet's `Semantics` not forcing a node of its own for an identifier (#163).
6. In the PR body, put the compare link (`flet-dev/flet/compare/v<old>...v<new>`) and what changed for us.

**Bumping to `1.1.0`:** the same steps. What changes on the Dart side is checked, not assumed: the template should then say `flet: 1.1.0`, from pub.dev, so `build/flutter/pubspec.lock` shows `flet` as `source: hosted`, and the git mirror stops growing. Then drop "prerelease" from D-479's wording, and §5.2 can use the store's companion app once one speaks 1.1.

**When we need a fix that isn't released.** The owner sometimes merges upstream fixes between prereleases. Ask for a prerelease first: it costs one line here. If one isn't coming, use the smallest of these, in a PR that says why and which release ends it, and undo it in the bump that brings the fix:
- **A Dart-only fix:** keep the wheels, and move the Dart package to the commit. `[tool.flet.flutter.pubspec.dependency_overrides]` replaces the template's entry (`CLI/commands/build_base.py`, `pyproject_pubspec`):
  ```toml
  [tool.flet.flutter.pubspec.dependency_overrides]
  flet = { git = { url = "https://github.com/flet-dev/flet.git", ref = "<sha>", path = "packages/flet" } }
  ```
- **A fix on the Python side, or in the template or `flet-cli`:** the source pin we used until #1027. A plain git source doesn't work: installed from git, `flet` reports Flutter `"0"`, and `flet build` stops, and the template URL names a release that doesn't exist. So clone Flet at the SHA into `.flet-src`, unpin the family (`"flet"`, not `"flet==..."`), add the two tables below, `uv lock`, and in every worktree repeat the clone: a wheel builds in place there, so worktrees never share it (D-219). `flet --version` prints the nearest tag and the packaged app says `0.1.0`. The pin tests allow what `[tool.uv.sources]` names.
  ```toml
  [tool.uv.sources]
  flet = { path = ".flet-src/sdk/python/packages/flet", editable = true }
  flet-cli = { path = ".flet-src/sdk/python/packages/flet-cli", editable = true }
  flet-web = { path = ".flet-src/sdk/python/packages/flet-web", editable = true }
  flet-desktop = { path = ".flet-src/sdk/python/packages/flet-desktop", editable = true }
  flet-platform-assets = { path = ".flet-src/sdk/python/packages/flet-platform-assets", editable = true }
  flet-notifications = { path = ".flet-src/sdk/python/packages/flet-notifications", editable = true }
  flet-permission-handler = { path = ".flet-src/sdk/python/packages/flet-permission-handler", editable = true }
  flet-secure-storage = { path = ".flet-src/sdk/python/packages/flet-secure-storage", editable = true }

  [tool.flet.dev_packages]              # what flet build bundles instead of PyPI's packages
  flet = ".flet-src/sdk/python/packages/flet"
  flet-notifications = ".flet-src/sdk/python/packages/flet-notifications"
  flet-permission-handler = ".flet-src/sdk/python/packages/flet-permission-handler"
  flet-secure-storage = ".flet-src/sdk/python/packages/flet-secure-storage"
  ```

**Why the pin matters for pip.** `flet build` hands pip the lines in `[project].dependencies`, and pip and uv skip prereleases unless a requirement names one. Unpinned, `flet` would resolve to stable 1.0.5 and `flet-notifications` to the unrelated project's 0.1.x (`flet-gaps-and-extensions.md` §6).

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
    "flet==1.1.0.dev4",               # one version for the whole Flet family (§2.2)
    "httpx==0.28.1",                  # the app imports it: without this, phones get what pip finds that day (D-470)
    "tzdata==2026.5",                 # zoneinfo data on phones (D-43)
]

[build-system]                        # uv sync installs pycon_us (src/pycon_us) editable on the host
requires = ["uv_build>=0.12,<0.13"]
build-backend = "uv_build"

[dependency-groups]
dev = [                               # host only, never bundled; versions in uv.lock (D-75)
    "flet-cli==1.1.0.dev4",           # flet run / build / debug / devices / test
    "flet-web==1.1.0.dev4",           # flet run --android/--ios serves through it
    "flet-desktop==1.1.0.dev4",       # optional desktop window (D-09, development.md §5.4)
    "flet-platform-assets==1.1.0.dev4", # flet-cli's dependency, held to the family's version
    "flet[test]==1.1.0.dev4",         # flet test flows (D-78) and pytest-asyncio
    "pytest",
    "hypothesis",
    "ruff",
    "pyright",
    "segno",                          # the mock-badge sheet's QR codes (D-391); never bundled
    "icalendar",                      # reads core/ics.py's files back (D-268); never bundled
    "ical",                           # the stricter reader of the same files (D-268); never bundled
]

# ------------------------------------------------------------------ flet build
[tool.flet]
product = "Conf Companion"            # display name, neutral: no PSF mark (D-36, D-452)
bundle_id = "io.github.ndonkohenri.confcompanion"   # both platforms (D-452)
icon_background = "#680579"           # behind src/assets/icon.svg where a platform needs an opaque icon (D-452)

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

[tool.flet.android]                   # Auto Backup takes only the preferences file (D-472, §8.1)
res_dir = "android_res"               # android_res/xml/*.xml, from the project root: the backup rules

[tool.flet.android.manifest_application]
allowBackup = "true"                  # said outright, though it is Android's default
fullBackupContent = "@xml/backup_rules"                  # Android 11 and older
dataExtractionRules = "@xml/data_extraction_rules"       # Android 12 and newer

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

# ------------------------------------------------------------------ tools
[tool.ruff]
target-version = "py314"              # ruff also skips git-ignored paths (excluded/)
extend-exclude = ["*.md"]             # code sketches in the docs are illustrations, not our code

[tool.ruff.lint]
extend-select = ["I", "UP", "B", "SIM", "D", "DTZ"]   # D: docstrings (D-74); DTZ: no naive datetimes (D-43)

[tool.ruff.lint.pydocstyle]
convention = "google"

[tool.pyright]
include = ["src", "tests", "tools"]
typeCheckingMode = "standard"

[tool.pytest.ini_options]
asyncio_mode = "auto"                 # async client tests (testing-and-quality.md §2)
testpaths = ["tests"]
pythonpath = ["."]                    # tools.mock_api; pycon_us is installed by uv sync
addopts = ["--ignore=tests/ui"]       # device flows run through flet test (D-78)
```

**Validated** on 2026-10-11, then with a source checkout of Flet, in a scratch project:
- flet-cli's own `load_pyproject_toml` read it, and every leaf key was matched to its reader (§3.2);
- `resolve_python_version` picked 3.14.7;
- `uv lock` resolved `flet` as `editable = ".flet-src/…"`;
- ruff, pyright and pytest ran under it.

S5 then built every target from this setup, and P0-04 (#52) built `apk --arch arm64-v8a`, `ios-simulator` and `ipa` from a clean `build/` with the whole file, Roboto (D-105) and the iOS signing tables (§8.2) included, at the `15854a0ac` pin.

**How `pycon_us` is importable on the host.** `[build-system]` uses uv's own backend, whose default layout is `src/pycon_us`, so `uv sync` installs the package editable. Then the tests, `tools/check_feed.py`, `tools/update_snapshot.py` and the mock server (which shares `core/signing.py`, D-52) all `import pycon_us` with no `PYTHONPATH`. Checked with uv 0.12.15 in a scratch project: `uv sync` built and installed it, and `uv run python tools/<script>.py` imported it. Without a build system, uv would treat the project as virtual and the tools would fail with `ModuleNotFoundError: pycon_us`. `flet build` is unaffected: it copies `src/` and pip-installs only `[project].dependencies`. On the phone, package metadata is still invisible (F15), so code reads `pycon_us.__version__`, never `importlib.metadata`.

### 3.2 Where each key is read

`get_platform_setting(x)` looks up `tool.flet.<platform>.x` first, then `tool.flet.x` (`CLI/commands/build_base.py:3290-3315`).

| Key | Read at | Effect |
|---|---|---|
| `project.name` | `CLI/commands/build_base.py:1086-1097` | Project slug; fallback for the artifact and product names |
| `project.version` | `CLI/commands/build.py:214-220` | `--build-name`: Android `versionName`, iOS `CFBundleShortVersionString` |
| `project.requires-python` | `CLI/utils/python_versions.py` | Bundled Python 3.14 |
| `project.dependencies` | `CLI/commands/build_base.py:2701-2704` | What is pip-installed into the app |
| `tool.flet.product` | `CLI/commands/build_base.py:1093-1097` | Launcher label and `CFBundleDisplayName` |
| `tool.flet.bundle_id` | `CLI/commands/build_base.py:1651-1653`; `templates/build/cookiecutter.json` | Android `applicationId` (`org_name_2` + `package_name`) and the iOS bundle id |
| `tool.flet.app.path` | `CLI/commands/build_base.py:1045-1048`; `CLI/commands/run.py:287-288` | `src/` holds `main.py` for both `build` and `run` |
| `tool.flet.splash.color`, `dark_color` | `CLI/commands/build_base.py:1758-1784` (`splash_setting`), `:1786-1822` (`_resolve_splash`) | Native splash background, light and dark |
| `tool.flet.boot_screen.flet` | `CLI/commands/build_base.py:1824-1868` (`_resolve_boot_screen`) | Background of Flet's boot screen while Python starts (`DOCS/publish/index.md` "Built-in `flet` boot screen") |
| `tool.flet.android.gradle_properties` | `CLI/commands/build_base.py:1290-1293` | Merged over the template defaults, so ours replaces `org.gradle.jvmargs` |
| `tool.flet.android.res_dir`, `tool.flet.android.manifest_application` | `CLI/commands/build_base.py:3568-3642` (`copy_android_resources`), `:3149-3158` (`get_android_application_attributes`); `TPL/android/app/src/main/AndroidManifest.xml:13-14` | `res_dir` is a folder laid out like `res/`, relative to the project root (not to `[tool.flet.app] path`: a first build with `src/android_res` failed with "is not a directory"), copied into the generated project; each `manifest_application` key becomes an `android:<key>` attribute on `<application>`, over Flet's own of that name since `a9ef26fdb` (`flet-dev/flet#7031`). Ours: the two backup-rule files (D-472, §8.1) |
| `tool.flet.ios.info` | `CLI/commands/build_base.py:1232-1240` | Merged into `Info.plist` |
| `tool.flet.flutter.pubspec.dependencies` | `CLI/commands/build_base.py:2034-2052` | Merged into `build/flutter/pubspec.yaml`, so relative paths resolve from `build/flutter/`; adds `roboto_fonts` (D-105) |
| `tool.flet.ios.team_id`, `tool.flet.ios.export_methods.<method>` | `CLI/commands/build_base.py:1493-1528` | The method from `--ios-export-method`, else `export_method`, else `debugging` picks its table; its `provisioning_profile`, `signing_certificate` and `export_options` go into the Runner's build settings and `ios/exportOptions.plist` (§8.2) |
| `tool.flet.deep_linking` | `CLI/commands/build_base.py:2801-2855` (`get_deep_linking`) | `confcompanion://app/<route path>` on Android and iOS (D-269, §5.5); a platform table would override it per key, and we have none |
| `tool.flet.android.permission` | `CLI/commands/build_base.py:1285-1288`; `TPL/android/app/src/main/AndroidManifest.xml:3-7` | Merged over the template's `INTERNET`: one `<uses-permission>` per `true` key; adds `POST_NOTIFICATIONS` and `SCHEDULE_EXACT_ALARM` (D-221, #446) |

Not set, because the default is what we want:

| Key | Why it is absent |
|---|---|
| `[tool.flet.compile]`, `[tool.flet.cleanup]` | The defaults (`.pyc` for app and packages; package cleanup on) suit us (`CLI/commands/build_base.py:2881-2917`). S1 measured `.pyc` off: Python recompiles on every start, because serious_python sets `PYTHONDONTWRITEBYTECODE=1` (F25), and cold starts reached the content 284 ms later on the emulator, so `.pyc` stays on (D-111). |
| `company`, `copyright` | Used only by the desktop templates (`TPL/macos/…/AppInfo.xcconfig`, `TPL/windows/…/Runner.rc`). |
| `min_sdk_version`, `target_sdk_version` | Flutter's defaults, 24 and 36, are what we want (D-106). |
| `[tool.flet.android.signing]`, `build_number` | Signing comes from `FLET_ANDROID_SIGNING_*` environment variables (§8.1), and the build number from `--build-number` (§4). |
| `[tool.flet.android.deep_linking]`, `[tool.flet.ios.deep_linking]` | The common `[tool.flet.deep_linking]` serves both platforms (D-269); a platform table only if one platform ever needs another value. |
| `NSAppTransportSecurity` | The template already allows arbitrary loads (`TPL/ios/Runner/Info.plist:48-52`). |
| `[tool.flet.template]` | We never fork the template (D-97). `[tool.flet.flutter.pubspec]` is used only for the Roboto fonts (§3.4). |

### 3.3 Icons and splash (NATIVE-03)

`flet build` generates every icon and splash image from `src/assets/` (`DOCS/publish/index.md` "Icons" and "Splash screen", lines 832-1228). Nothing is copied into the template by hand.
- **P0:** Flet's default icon. A build that has a placeholder icon is obviously a development build. Since `08b89cce5` (flet-dev/flet#6973) flet-cli renders that default in every build from the Flet logo SVG that `flet-platform-assets` bundles ("Generated default app icons" in the build log) instead of keeping the template's committed rasters; on #445's builds the launcher showed the Flet mark labelled "Conf Companion" on Android 16 and iOS 26.5, as before.
- **P0 (SHELL-01):** the splash and boot-screen colours in §3.1, `#680579` in light and dark. Native splash, Flet's boot screen and our `BootView` then share one background, so nothing flashes between them. The colours live in `pyproject.toml`, not in `--splash-color` flags, so the file stays the only configuration (§7.4).
- **iOS's launch screen reads a different purple from the app (#880, U281, [#950](https://github.com/ndonkoHenri/pycon-us-flet/issues/950)).** On an iPhone 17 simulator (iOS 26.5, Xcode 27.2, pin `22a6dcb16`) the launch screen reads `#72007e` and the Flutter frames `#680579`. That is `#680579` taken as Display P3 numbers and converted to sRGB. It is not the generated PNG's missing profile: `Assets.car` already holds the swatch as sRGB, and a swatch tagged sRGB or Display P3, or a storyboard background colour with no swatch at all, reads `#72007e` too. Our configuration cannot fix it: `[tool.flet.ios.splash] color = "#5f1275"` makes the launch screen read `#680579`, but Flutter's own splash view, drawn from the same storyboard until the first frame, then reads `#5f1275` for about 0.3 s, so the shift moves and the long stage trades places with the short one. The app keeps `#680579` on both platforms; the fix needs Flet's iOS template (#950). Simulator only: the owner's iPhone (D-102) decides whether it shows there.
- **On the iOS simulator, the launch screen sometimes fades through black before the boot screen (#958).** It is not Flet's fade: the generated `main.dart`'s `_BootOverlay` fades only when `[tool.flet.boot_screen.flet] fade_out_duration` is above 0, we leave it at its default 0, and the overlay then goes in one step. The layer that dims is the launch screen's view, icon included, which `FlutterViewController` keeps over the Flutter view until the first frame and then fades out in 0.2 s (`onFirstFrameRendered`, then `SplashScreenManager.removeSplashScreen`; Flutter 3.47.7, `engine/src/flutter/shell/platform/darwin/ios/framework/Source/`). When the first Flutter frame is not on screen yet, the opaque Flutter view behind it is black, and the boot screen appears as the fade ends. Our configuration cannot change that: the fade and the view belong to the engine, and `UILaunchStoryboardName` feeds the OS launch screen too. Measured on an iPhone 17 simulator (iOS 26.5, pin `22a6dcb16`, `flet build ios-simulator`), 20 cold starts of the same install recorded with `simctl io recordVideo` and decoded with PyAV: 8 dipped to `#000000`-`#09000a` for about 0.15 s, 12 crossfaded straight from `#72007e` to `#650475` (frame means, status bar included). The simulator only builds debug (`flutter build ios --simulator --release` and `--profile` both stop with "… mode is not supported for simulators"), and the Mac's load average was 6 to 43 while agents built, so this is a debug build on a busy host. On the Android emulator (API 36) none of 4 release and 4 debug cold starts dipped. **Open:** whether a release build on an iPhone does; the check is on #121's session, and a dip there becomes an `upstream` issue with this analysis.
- **Since D-452:** our own mark, `src/assets/icon.svg`, with `[tool.flet] icon_background = "#680579"`. flet-cli renders every platform's sizes from that one file and frames it for each platform. The native splash has no artwork of its own, so it falls back to the icon on the same purple.
  - The other two drafts are in `docs/icon-options/`. To change the icon, replace `icon.svg`: an icon stays free to change.
  - If the generated framing ever looks wrong, add `icon_ios.png` or `icon_android.png`: artwork within the central 60 % for iOS, and within a centred circle of about 57 % for Android.

### 3.4 Additions by phase

Each row lands in the PR that ships the feature, never earlier. A Flet extension goes in `dependencies` at the family's exact version (§2.2).

| Phase | Feature | Addition | Exists in flet-cli today? |
|---|---|---|---|
| P2 | Deep links (NEW-07, D-21) | **Done in P2-24 (#384), now in `pyproject.toml`:** one common `[tool.flet.deep_linking]` table with `scheme = "confcompanion"` and `host = "app"` (D-269, D-452). Links look like `confcompanion://app/schedule/session/42`. `tests/test_deep_linking.py` runs flet-cli's resolver for Android and iOS. | Yes (`flet-dev/flet#6953`, in the pin) |
| P2 | Runtime permissions (D-75) | **Done in P2-86 (#446), now in `pyproject.toml`:** `"flet-permission-handler"`, added three times as above; `Services.permissions` holds its service only when `capabilities.PERMISSIONS` (architecture §4.2). | Yes (monorepo package) |
| P2 | Reminders (E3, D-58..D-61) | **Done in P2-86 (#446), now in `pyproject.toml`:** `"flet-notifications"` from the monorepo (flet-dev/flet#6999, module `flet_notifications`), added three times as above; PyPI's `flet-notifications` is an unrelated project, so the path tables stay until Flet publishes it. `[tool.flet.android.permission]` declares `POST_NOTIFICATIONS` and `SCHEDULE_EXACT_ALARM` (D-221; never `USE_EXACT_ALARM`). The rest comes with the extension: its Android manifest adds the action, scheduled and boot receivers and `RECEIVE_BOOT_COMPLETED`, its `flet-extension.toml` turns on core library desugaring (U7), and the template's `AppDelegate.swift` sets the iOS notification delegate (D-220). iOS needs no plist key; permission is requested through the extension (F17). | Yes, at `08b89cce5` (#445) |
| P3 | Mock credentials (D-49) | **Done in #684, now in `pyproject.toml`:** `"flet-secure-storage"` from the monorepo, added three times as above (the dependency, `[tool.uv.sources]` and `[tool.flet.dev_packages]`); `capabilities.SECURE_STORAGE` turns on in packaged builds, and `services/credentials.py` owns it. | Yes (monorepo package) |
| P3 | Camera scanning (E1, D-65) | `[tool.flet] permissions = ["camera"]` and `[tool.flet.ios.info] NSCameraUsageDescription = "Scans attendee badges for the staff tools."`. Without our own text, Flet's default "capture photos and videos" string is used (`CLI/commands/build_base.py:277-287`). Then add the scanner extension once it is pinned. | The keys: yes. The extension: no (E1). |
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

### 5.0 The short path: a fresh worktree to the app on a device

The Mac already has the tools (§5.1 if it doesn't). From the worktree's root:

```bash
tools/setup_worktree.sh
PUB_CACHE=$PWD/build/pub-cache uv run flet build apk --arch arm64-v8a --yes
adb -s <serial> install -r build/apk/pycon-us.apk
adb -s <serial> shell am start -W -a android.intent.action.VIEW -d confcompanion://app/now
```

On iOS, the same with `LANG=en_US.UTF-8 PUB_CACHE=$PWD/build/pub-cache uv run flet build ios-simulator --yes`, then `xcrun simctl install <udid> build/ios-simulator/pycon-us.app` and `xcrun simctl launch <udid> io.github.ndonkohenri.confcompanion`.

- Use a device of your own, never one another agent or the owner has open: an install replaces the app there (§5.5).
- A build takes minutes (§5.8). For Python hot reload instead, see §5.2.
- Drive it with Maestro (§5.9). Staff features need the mock (§6).

### 5.1 From a clean Mac

This section is for a Mac with none of the tools. The timed run on a truly clean machine is #850 and hasn't happened, so **unverified** below means nobody has run that step on a Mac without the tool.

**What you need.**

| Tool | Version | How you get it | Where the version comes from |
|---|---|---|---|
| macOS, Apple silicon | macOS 27.0 on an M4 here | | Our AVDs are arm64 (§5.5). Intel is unverified. |
| git | any | `xcode-select --install`, or Xcode | |
| Homebrew | any | [brew.sh](https://brew.sh); only for `gh` and CocoaPods | |
| Access to the repo, while it is private | `gh` 2.100.0 here | `brew install gh`, then `gh auth login` | See "What `gh` is for" below |
| uv | CI uses 0.12.x; 0.13.6 here | `curl -LsSf https://astral.sh/uv/install.sh \| sh`, then open a new terminal | `ci.yml`, and `uv_build>=0.12,<0.13` in `pyproject.toml` |
| Python on the Mac | 3.14.x (3.14.10 with uv 0.13.6) | `uv sync` downloads it | `requires-python` in `pyproject.toml`; the app's own Python is separate (§2.1) |
| Flutter | 3.47.9 | flet-cli installs it (below) | `uv run flet --version` |
| JDK, Android only | 17 (Temurin 17.0.13+11) | flet-cli installs it (below) | `CLI/utils/jdk.py:15-18` |
| Android SDK, Android only | `platform-tools`, `platforms;android-35`, `build-tools;34.0.0` | flet-cli installs them (below) | `CLI/utils/android_sdk.py:15-19` |
| Xcode, iOS only | 27 (27.2 here); no older one has been tried with this pin | App Store | §2.1, D-81 |
| CocoaPods, iOS only | 1.17.0 here | `brew install cocoapods` | Non-SPM plugins build with it (`CLI/commands/build_base.py:638-640`) |

Allow about 20 GB of disk for Android (here: Flutter 2.1 GB, Android emulator 1.2 GB, system image 4.3 GB, NDK 2.8 GB, plus the Gradle and pub caches), and more for Xcode.

**What `gh` is for.** Only for cloning this repo while it is private: any git credential with access works too. Building, running and testing never call it. People who open or merge PRs need it as well (`tools/gate.sh` posts through it). Once the repo is public (#852), clone with `git clone https://github.com/ndonkoHenri/pycon-us-flet.git` with no account; `gh` then leaves this list.

**Pasting into zsh.** The blocks in this section hold no comments on purpose. In an interactive zsh, macOS's default shell, `#` doesn't start a comment unless you run `setopt interactivecomments` first, so a pasted `uv sync   # note` passes the note as arguments. Blocks elsewhere in this guide do have comments.

**1. The checkout.**

```bash
gh repo clone ndonkoHenri/pycon-us-flet && cd pycon-us-flet
uv sync --locked
git config core.hooksPath .githooks
uv run flet --version
uv run pytest
```

- `git config` turns on the pre-push checks, once per clone (§7, D-273).
- With a uv newer than 0.12, `uv sync` prints ``warning: `build_system.requires = ["uv-build>=0.12,<0.13"]` does not contain the current uv version``. It is harmless: uv fetches the older `uv_build`. `uv.lock` also passes `uv lock --check` under uv 0.12.24.
- `flet --version` prints `Flet: 1.1.0.dev4` and `Flutter: 3.47.9`. It needs no Flutter yet.
- `pytest` needs no device and takes about 3 minutes on a quiet M4, 5 or 6 on a busy one: about 9,000 passed, 1 skipped in 2026-11. The count grows; what matters is that nothing fails. It can run in a second terminal while you go on.

**2. Android.** The first command that needs the mobile tools installs them. flet-cli asks once for Flutter and once for the Android SDK, whose yes covers the JDK too; `--yes` skips both questions. Flutter goes to `~/flutter/3.47.9`, the JDK to `~/java/17.0.13+11` and the SDK to `~/Android/sdk`, and none of them joins your shell's `PATH` (§2.1).

```bash
uv run flet emulators
```

That SDK has no emulator or system image, so add them. These commands are **unverified** on a clean Mac: only `avdmanager list device` has been run here, which lists `pixel_6a`, and the package and device names match this Mac's `pycon_pixel6a_api36` (§5.5). Android Studio's Device Manager is the other way, if you have it.

```bash
export JAVA_HOME=~/java/17.0.13+11/Contents/Home
~/Android/sdk/cmdline-tools/12.0/bin/sdkmanager --install emulator "system-images;android-36;google_apis;arm64-v8a"
~/Android/sdk/cmdline-tools/12.0/bin/avdmanager create avd -n pycon_pixel6a_api36 -d pixel_6a -k "system-images;android-36;google_apis;arm64-v8a"
uv run flet emulators start pycon_pixel6a_api36
```

When it has booted, run the app:

```bash
uv run flet devices
uv run flet debug android -d emulator-5554
```

The first build also makes Gradle fetch what is still missing (on this Mac, `platforms;android-36` and an NDK). That is **unverified** on a clean Mac: if it stops on a missing SDK package, install the package with `sdkmanager` and tell #850.

**3. iOS.** `flet devices` and `flet emulators` require the Android SDK even with `ios` (`CLI/commands/devices.py:82`, `CLI/commands/emulators.py:102`), so on an iOS-only Mac list simulators with `xcrun` instead. `flet debug ios` itself asks only for Flutter (`CLI/commands/build_base.py:938`).

```bash
sudo xcode-select --switch /Applications/Xcode.app/Contents/Developer
sudo xcodebuild -license accept
sudo xcodebuild -runFirstLaunch
xcodebuild -downloadPlatform iOS
xcrun simctl list devices available
xcrun simctl boot <simulator udid>
open -a DeviceHub
export LANG=en_US.UTF-8
uv run flet debug ios -d <simulator udid>
```

- `xcode-select` comes first because a Mac that got git from `xcode-select --install` stays on the Command Line Tools after Xcode is installed; there `xcodebuild` stops with "requires Xcode" and `xcrun` can't find `simctl`.
- The `xcode-select` line and the three `xcodebuild` lines are **unverified**: this Mac's Xcode was set up long ago. Without `LANG`, CocoaPods warns.
- Xcode 27 has Device Hub in place of the Simulator app, so `open -a` no longer finds the old name.
- A fresh Xcode downloads its own current runtime, which may not be the iOS 26.5 all our checks ran on (§5.5).
- Simulators need no Apple account; a phone needs the signing setup of §8.2.

**How long it takes.** Measured means the 2026-11-02 rehearsal below, or the source named. The rest are estimates that #850 will replace.

| Step | Measured | On a clean Mac |
|---|---|---|
| `gh repo clone` | 11 s | About the same |
| Flet clone and checkout (335 MB) | 12 s | About the same |
| `uv sync --locked`, with CPython and every package downloaded | 6 s, fast connection (25.5 MiB Python, about 250 MB of packages) | Under a minute |
| `uv run pytest` | About 3 min quiet, 5 min 35 s under load (#897, the gate on 2026-11-03) | About the same on an M4 |
| Flutter, on first use | About 5 min (S5: 305 s, with its setup) | About 5 min |
| JDK and Android SDK | Never timed | Estimate: a few minutes |
| Emulator and system image | Never timed | Estimate: 5 to 10 minutes |
| First `flet debug android` | 70 s with warm caches (2026-10-12). Pieces of a colder run: 9 to 10 min for an empty pub cache on a busy host (#176, §5.8); Gradle 167.6 s with `~/.gradle` warm (S5, an older pin) | Estimate: 10 to 20 minutes |
| Xcode and its runtime | Never timed | Depends on the connection; tens of minutes at least |
| First `flet debug ios` | Under 3 min with warm caches (2026-10-12); `flet build ios-simulator` 4 min from a cloned pub cache (#176) | Estimate: 10 to 15 minutes |

So Android from nothing, not counting `pytest`, comes to about 20 to 35 minutes, estimated. That sits right at PLAN's 30-minute exit target; #850 settles it.

**The rehearsal (#849, 2026-11-02, at `22a6dcb16`).** Step 1 was followed in a new directory, with new clones of both repos and uv's cache and Python folders empty (`UV_CACHE_DIR`, `UV_PYTHON_INSTALL_DIR`, `UV_PYTHON_PREFERENCE=only-managed`); then `uv run flet devices` ran (13 s, no devices). What wasn't clean: the owner's Mac already had Homebrew, Xcode 27.2, a logged-in `gh`, uv 0.13.6, Flutter 3.47.8 through fvm, the JDK, the Android SDK, and warm Gradle and pub caches. The Flutter, JDK and SDK installers write into the home folder, so they weren't run. Nothing was built, and no emulator or simulator was used; steps 2 and 3 were read against flet-cli's source at the pin only. This section's device steps last ran on 2026-10-12, at an older pin and with warm caches: the 70 s and 3 minutes above.

`.gitignore` covers, among others:
- `.venv/`, `.flet-src` (an optional clone of Flet, §2.2), `.flet/` (the `flet run` storage, F14), `build/`, `excluded/`;
- `*.jks`, `*.keystore`, `*.p12`, `*.p8`, `*.mobileprovision` and `.env*`, as a second line of defence for D-86.

### 5.2 Hot reload: a companion client built from a Flet clone

The Flet companion app in the stores is built from released Flet and lacks 1.1's Dart changes, so it is not used with a prerelease (D-81). `uv run flet run --android|--ios` (port 8551 and a QR code for that app) waits for a 1.1 companion in the stores. Until then, Python hot reload uses a companion client built from the `client` folder of a Flet clone at our version, on an emulator or simulator. It's the one thing in the normal path that needs the clone, and only if you want hot reload; clone it once (§2.2):

```bash
# Terminal 1, at the repo root: serve src/main.py on port 8550; -r restarts Python on any change under src/.
BROWSER=true uv run flet run -r -w -p 8550

# Terminal 2: build and start the client (first build about 4 minutes on Android, 2 on iOS).
cd .flet-src/client && flutter run -d <emulator serial>    # or -d <simulator udid>
```

- Terminal 2 needs Flutter 3.47.x on `PATH`. If flet-cli downloaded it (§2.1), first run `export PATH="$HOME/flutter/3.47.9/bin:$PATH"`.
- The client connects to `http://localhost:8550` at the root path, or `http://10.0.2.2:8550` on the Android emulator (`client/lib/main.dart:84-97`), and logs "Page URL: …". A phone cannot reach the laptop that way, so phones use `flet debug` (§5.3).
- `-r` watches `src/` recursively; without it only `src/main.py` reloads (F22). A reload restarts Python, so in-memory state resets; preferences live on the device and survive.
- **At `a9ef26fdb` a reload strands the client.** The first load works, but after Python restarts, each `SharedPreferences.get` times out in 10 s ("Timeout waiting for invoke method listener") and the client stays on the boot spinner: 5 timeouts and the same screen from a source pin and from the wheels (#1027, iPhone 17 simulator). Until that's fixed, stop and start the client after a reload.
- `-w` also opens a browser tab; `BROWSER=true` stops that.
- Stopping `flet run` can leave the app's Python child listening on port 8550, and the next `flet run -p 8550` then cannot bind. `lsof -nP -iTCP:8550 -sTCP:LISTEN` names the process; kill it.
- On iOS, `flutter run` rewrites three tracked files in the clone: `client/ios/Podfile.lock`, `client/ios/Runner.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved` and `client/ios/Runner.xcworkspace/xcshareddata/swiftpm/Package.resolved`. They matter only to `git status` there; before moving the clone to another tag, restore them with `git -C .flet-src restore --source=HEAD --worktree -- <path>`. Never restore all of `client/`.
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
- `-d`/`--device-id` is required for Android and iOS: without it, `flet debug` exits before building (`CLI/commands/debug.py:123-138`). List ids with `uv run flet devices` (§5.5). `--show-devices` hits the same check first, so it also needs `-d`.
- Without `-v`, `flet debug` shows only a spinner ("Running debug version of the app on … device...") and hides `flutter run`'s output, including errors. `-v` streams it, and `-vv` adds Flutter's `--verbose` (`CLI/commands/build_base.py:3479`).
- Ctrl+C ends the session ("Debug session ended."); the app stays installed.
- The debug build has `versionCode` 1 and `versionName` 1.0.0, because `flet debug` passes no `--build-number` or `--build-name` (`CLI/commands/debug.py:140-159`).
- When another build may run on the Mac (agents in parallel), prefix it with the worktree's own pub cache, `PUB_CACHE=$PWD/build/pub-cache uv run flet debug …`, or it may run another worktree's Python (§5.8).
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
- `flet-desktop` downloads the client from the GitHub release of its version (`flet-macos.tar.gz`) the first time.
- Never add desktop-only code paths, and never judge touch targets, safe areas or gestures there.

### 5.5 Devices, emulators and logs

**Your own device.** `tools/device.py` boots one and shuts it down, and refuses the owner's (`emulator-5554`, AVD `pycon_lowram_api34`, the `iPhone 16` simulator). `up` prints only the serial or udid, so a script can keep it.

```bash
uv run python -m tools.device up android --port 5594          # --no-animations for flet test flows, --avd for another AVD
uv run python -m tools.device up ios --name Claude-123-iPhone-17
uv run python -m tools.device prefs <device> --text 200 --bold --contrast --dark   # --text is 100, 200 or max
uv run python -m tools.device prefs <device> --reset
uv run python -m tools.device down <device>                   # --delete also deletes a simulator
```

**This Mac's limits**, learned from runs that died:
- **Memory comes first, and emulators fill it.** With 13 workflows and about 12 devices (2026-10-21), swap reached 39 of 40 GB and load about 900; with three emulators up, Android's system server died under its watchdog and APK installs hung. Boot one emulator and one simulator at a time, and shut them down when done.
- **The Mac sleeps when idle.** Keep it awake for a long run, `caffeinate -i <command>`. A run that stops overnight often just slept.
- **Emulator timing isn't reliable here.** qemu threads drop to background priority behind other windows, and load stays high while other agents run. Don't measure while builds run; compare within one window (`testing-and-quality.md` §8), and repeat timing-sensitive UI checks instead of trusting one pass.
- **Device work runs long.** Set a time budget before a device matrix: one ran 11 hours (2026-10-20).

**The device set (D-102, D-107).** Work happens on Android emulators and iOS simulators first. The build reference devices are the AVD `pycon_pixel6a_api36` (Pixel 6a profile, 4 GB RAM, Android 16 API 36, Google APIs arm64; `emulator-5554` when it is the only one running) and an **iPhone 17** simulator on **iOS 26.5**. On the owner's Mac the iPhone 16 family exists only on the iOS 18.6 runtime, so use the iPhone 17 family (iPhone 17, 17 Pro, 17 Pro Max, 17e) on iOS 26.5. Also available: the AVDs `Pixel_9_Pro_XL_API_35` (Google Play, API 35) and `flet_probe_api36` (Google APIs, API 36; TalkBack is preinstalled), and an iPad Pro simulator for the tablet layout. **The tablet AVD** is `pycon_tablet_api36` (#461): the Pixel Tablet profile (2560 x 1600 px at 320 dpi, 1280 x 800 dp; its natural orientation is landscape) on `pycon_pixel6a_api36`'s system image, made with `echo no | avdmanager create avd -n pycon_tablet_api36 -k "system-images;android-36;google_apis;arm64-v8a" -d pixel_tablet`, then `hw.ramSize=4096M` and `disk.dataPartition.size=6G` in its `config.ini` (the profile's defaults are 1536 MB and 800 MB). Boot it once without `-read-only` so the first boot writes its data, shut it down, and from then on boot it with `-read-only` like the others. Rotations: Android counts from the natural orientation, so on this tablet `adb shell settings put system user_rotation 1` (or Maestro's `LANDSCAPE_LEFT`) shows it in portrait. An AVD whose system image is missing fails with "Cannot find AVD system path"; install the image named by `image.sysdir.1` in its `config.ini`, e.g. `sdkmanager "system-images;android-35;google_apis_playstore;arm64-v8a"`. The owner's iPhone is used only for checks that need hardware or a release build: release-build performance, the camera, notification delivery, TestFlight installs, VoiceOver, and the release build's exit journeys at phase exits. There is no Android phone; emulator timings are a relative regression signal only ([`testing-and-quality.md`](testing-and-quality.md) §8).

| Task | Command |
|---|---|
| List connected devices | `uv run flet devices [android\|ios]` (USB and wireless; `--device-connection attached\|wireless`) |
| Android emulators | `uv run flet emulators`; `uv run flet emulators start <name> [--cold]`; `uv run flet emulators create <name>` |
| iOS simulators | `xcrun simctl list devices available` for the udids; `xcrun simctl boot <udid>` and `open -a DeviceHub`, then `flet debug ios -d <udid>`. A simulator that a build left shut down comes back with `xcrun simctl boot <udid>`. Simulator builds need no signing. |
| Install an APK over the previous build | `adb install -r build/apk/pycon-us.apk`, then `adb shell am force-stop io.github.ndonkohenri.confcompanion` before launching, so the update is judged from a cold start: a process still running from the old build keeps its old state until it stops. On the Android 16 emulator the install ended the running app both times it was tried (#53); the force-stop makes that certain. |
| Android Python log | `adb logcat -s flet.python` (`-d` dumps the buffer, `-c` clears it) |
| iOS simulator Python log | `xcrun simctl spawn booted log stream --style compact --predicate 'sender == "dart_bridge"'` |
| Open a route directly (a packaged build) | Android: `adb shell am start -n <package>/.MainActivity --es route /schedule/session/42` (what `flet debug --route` passes); iOS simulator: `xcrun simctl launch <udid> <bundle id> --route=/schedule/session/42`. `simctl openurl` with a custom scheme waits for a tap on the system's "Open" prompt (F31) |
| Open a deep link (a packaged build, D-269) | Android: `adb -s <serial> shell am start -W -a android.intent.action.VIEW -d 'confcompanion://app/now'` (no `-n`: the intent filter picks the app, and `-W` waits for the launch; `Activity: io.github.ndonkohenri.confcompanion/.MainActivity` says it matched, and on a busy host `Status` may read `timeout` while the app still opens). `adb shell pm query-activities -a android.intent.action.VIEW -d <link>` lists what would answer a link without opening it. iOS simulator: `xcrun simctl openurl <udid> 'confcompanion://app/now'`; the first link on a simulator stops at the system's "Open in …?" prompt, which simctl cannot answer (F31) and a Maestro `tapOn: "Open"` does; later links, even after a reinstall, open the app directly. The link's path becomes `page.route` (`/now`); iOS checks only the scheme, and the host never reaches `page.route` (D-269). |
| iPhone Python log | Console.app › the device › filter on the app process |
| A tester's log | Developer screen › Share log, which sends `console.log` (D-72) |

Physical devices:
- **Android** (a borrowed phone): enable developer options and USB or wireless debugging (`adb pair` for wireless).
- **iPhone:** enable Developer Mode (Settings › Privacy & Security), trust the Mac, and register the device in the team (§8.2).

### 5.6 Fake clock and feed

Off-season and in demos, the Developer screen (DEV-01, D-73; More › Developer, after 7 taps on About this app's version in a packaged build) sets:
- a fake "now", stored in preferences and read by `clock.now()` (D-43): type it (`2026-05-15 09:00`, conference time) or pick it, then Apply. It runs forward from there, and every start of the app begins at it again until Reset (D-187);
- the feed URL, used from the next refresh (the Schedule stub's Refresh, or the 15-min trigger), e.g. the `feed_url` fixture's server, or a closed port to test offline.

Use the 2026 feed with a fake clock inside 2026-05-13..19 to exercise Now and Jump to now, until the 2027 feed exists (PLAN §7). The OS fires reminders at real instants, which the fake clock does not move: for them, serve a copy of the snapshot shifted so a session starts in a few minutes (`uv run python -m tools.shifted_feed <session id> --in 5m`, which prints the feed URL for the emulator and the simulator; testing-and-quality.md §9.1). Environment variables do not reach packaged apps, so there are no build flavours.

### 5.7 UI flows: `flet test` (D-78, D-171)

The flows in `tests/ui/` run on an emulator or a simulator, never in CI (`addopts` keeps them out of `uv run pytest`, D-84). The strategy, the helpers and the list of flows are in [`testing-and-quality.md`](testing-and-quality.md) §5.

```bash
# Android: an emulator of your own (D-102), its animations off and its on-screen keyboard down (D-223;
# testing-and-quality.md §5.2)
uv run python -m tools.device up android --avd flet_probe_api36 --port 5580 --no-animations
uv run flet test android -d emulator-5580 --tests-dir tests/ui -v

# iOS: a booted iPhone 17 Pro Max simulator on iOS 26.5 of your own (D-107, D-223)
uv run python -m tools.device up ios --name "<issue>-iphone17promax" --model "iPhone 17 Pro Max"
LANG=en_US.UTF-8 uv run flet test ios -d <udid> --tests-dir tests/ui -v

# One flow, or the P1 flows F1-F5 only (testing-and-quality.md §5.4)
uv run flet test android -d emulator-5580 --tests-dir tests/ui -v -k drill
uv run flet test ios -d <udid> --tests-dir tests/ui -v -k "offline or switch_days or search_finds or favourite or drill"
```

- `-d` is required for both platforms, and `--tests-dir tests/ui` points `flet test` at the flows (its default is `tests`, which would collect the unit tests too). `-v` streams the Flutter test process's output; without it a failure prints only the output's tail. `-k <expression>` runs some flows only.
- `flet test` first provisions a Flutter test host in `build/flutter` through the `flet build` pipeline (1 to 2½ minutes; the app's Python is packaged again on every run), then pytest runs each flow: `flutter test` builds a debug binary, installs it, launches it and connects the tester, and the app is uninstalled when the flow ends. So every flow starts from a fresh install, with no stored settings or cache. On #78's Mac (M4), with warm Gradle and Xcode caches, the shell flow took about 3½ minutes on Android (provisioning 1 min, Gradle 45 s, install 15 s, the flow about 1 min) and about 5 minutes on iOS (provisioning 2½ min, Xcode build 67 s); a first run on a host busy with other emulators took 15 minutes on Android.
- The bundle id is the app's own (`io.github.ndonkohenri.confcompanion`), so a run on a shared emulator replaces and then removes another build of the app there: use an emulator or a simulator of your own.
- Each step's screenshot is saved under `build/ui/<platform>/` (git-ignored), and a step that times out saves `timed-out-<flow>.png` (D-223): look there first when a flow fails.
- The flows reach the laptop at `10.0.2.2` (Android emulator) or `127.0.0.1` (iOS simulator), as Flet's `FletTestApp` sets it, so they cannot run on a physical phone (testing-and-quality.md §13).
- When another build may run on the Mac, run the flows with the worktree's own pub cache (§5.8): `PUB_CACHE=$PWD/build/pub-cache uv run flet test …`.
- **Why the iOS flows run on an iPhone 17 Pro Max** (D-223, D-478): a flow cannot scroll (`RemoteTester` has no drag, U35), and the test binding drops the device's own touches (`shouldPropagateDevicePointerEvents`), so a host-side swipe doesn't reach the app either. About this app is below the fold of More on every phone, so the flows open it by its deep link: `adb` on Android, and on iOS Maestro (`maestro/subflows/open_link.yaml`), which answers the simulator's "Open" prompt, so the iOS flows need the Maestro CLI. Developer's Refresh now must then be on its first screen, which takes the Pro Max (440 x 956 pt); `flet_probe_api36` (1080 x 2400 px, 420 dpi) shows it too.
- **F1–F5 set the scene in Developer** (`tests/ui/developer.py`): each unlocks it, sets the fake clock to the day before the conference, and F2–F5 refresh from the recorded feed that the `feed_url` fixture serves from the laptop. The app fetches the year's feed at launch, so the flows need no network of their own, but a device without one only makes the first Refresh now wait for the app's 10 s feed timeout.

### 5.8 Several builds at once: a pub cache per worktree (D-176)

**Why.** The pub cache is one folder that every worktree's builds write to, and overlapping builds that share it can ship each other's Python, silently. (Until D-479 a Flet checkout per worktree was the other half of this section: pip built `flet`'s wheel inside it, D-219. A wheel from PyPI builds nothing.)

**The pub cache.** serious_python (6.1.3 at `a9ef26fdb`; 6.1.2 at `22a6dcb16`; 6.0.1 at `08b89cce5`, with its platform packages at 6.1.0 since 2026-10-27, §2.1; 5.0.0 before; #445 found the same paths and `build.gradle.kts` lines in 6.0.1), which embeds Python in the app, stages each build's Python app inside its own plugin folder in the **pub cache**, and every Flutter project on the Mac shares that folder. Two builds that overlap can ship each other's Python; nothing fails or warns, and the app runs another worktree's code. It happened three times on 2026-10-12 with agents building in parallel (#176).
- **iOS:** the packaging step copies `build/python-app/` into `<pub cache>/hosted/pub.dev/serious_python_darwin-<version>/darwin/` (`dist_ios/app`, then the Swift package's `serious_python_darwin/Sources/serious_python_darwin/Resources/app`; site-packages and the native extension frameworks go there too). Xcode copies that folder into the app's `serious_python_darwin_serious_python_darwin.bundle/app` minutes later, so a build that packages in between wins.
- **Android: the same race, with a shorter window.** The plugin's Gradle tasks write `app.zip`, `stdlib.zip` and `sitepackages.zip` to `serious_python_android-<version>/android/src/main/assets/` and the native libraries to `src/main/jniLibs/<abi>/`, paths relative to the plugin's folder in the pub cache (`build.gradle.kts:151, 423-454`); the APK takes them when Gradle merges assets later in the same run. Two Gradle builds that overlap there can package each other's `app.zip`.
- `flet debug` and `flet test` run the same pipeline (§5.3, §5.7). The companion client (§5.2) does not embed Python and is not affected.

**The rule.** When another build may run on the Mac (agents in parallel, D-102), every `flet build`, `flet debug` and `flet test` in a worktree uses a pub cache of its own under `build/`, an APFS clone of `~/.pub-cache`.

`tools/setup_worktree.sh` does it, once per worktree, and is safe to run again: it runs `uv sync --locked`, clones the pub cache if `build/pub-cache` is gone, turns on the pre-push hook, and says when Flet's Flutter isn't in `~/flutter`. Then prefix every build, debug and test command in the worktree:

```bash
PUB_CACHE=$PWD/build/pub-cache LANG=en_US.UTF-8 uv run flet build ios-simulator --yes
PUB_CACHE=$PWD/build/pub-cache uv run flet debug android -d emulator-5580
PUB_CACHE=$PWD/build/pub-cache uv run flet test ios -d <udid> --tests-dir tests/ui -v
```

**The pub cache clone.**
- **The Dart `flet` package lives here too** (§2.2): pub's mirror of Flet's repository, `git/cache/flet-<hash>`, and a checkout, `git/flet-<sha>`. A clone made after `~/.pub-cache` has them shares their blocks; one made before writes what it lacks on its first build. From an empty cache the two hold about 430 MB, hard-linked, so `du` on one alone misleads, and the whole cache 714 MB after an APK, 976 MB after an iOS build as well. With `~/.pub-cache` holding the mirror but not this commit, a new worktree's `tools/setup_worktree.sh` took 57 s and its first APK 112 s (2026-11-04, on a busy Mac).
- `cp -c` clones with `clonefile(2)` when both folders are on one APFS volume, and falls back to a plain copy otherwise (`man cp`). The clone shares its blocks with `~/.pub-cache` until one side changes. On the owner's Mac it took 6 s for the 1.0 GB cache (44,000 files), and the volume's used space grew by about 20 MB (metadata; other builds were writing at the same time). An empty `build/pub-cache` works too, but the first build then downloads every package again (9 to 10 minutes on a busy host, #176).
- The script tests for the folder first: `cp -R` into a folder that already exists copies the source *inside* it, so a second bare `cp -cR` adds a nested `build/pub-cache/.pub-cache` and leaves the cache that `PUB_CACHE` names as it was. If a clone was interrupted, `rm -rf build/pub-cache` and run the script again.
- The clone carries whatever another build last staged in the plugin folders; your build replaces it in your copy only.
- Keep the same `PUB_CACHE` for every command in the worktree: switching makes Flutter resolve the packages again. `build/` is git-ignored, so the clone goes with it: `rm -rf build` (§2.2), `flet clean` (`CLI/commands/clean.py:68`) and a build after a change of the bundled Python version (flet-cli wipes `build/` first, `CLI/commands/build_base.py:996`) all delete it. If `build/pub-cache` is missing, run the setup line again before the next build; otherwise that build quietly fills a new cache from the network (as the build that changes the Python version does anyway, since it empties `build/` itself).
- On a Mac where only one build runs at a time, the shared `~/.pub-cache` is fine.

**The check after an iOS build.** No output (exit status 0) means the bundle holds this worktree's app; the bundle's own `.keep` placeholder is the one expected difference, hence `-x .keep`:

```bash
diff -rq -x .keep build/python-app build/ios-simulator/*.app/serious_python_darwin_serious_python_darwin.bundle/app
```

For an APK, unpack its `assets/app.zip` under `build/` and compare it the same way (no output means a match):

```bash
rm -rf build/apk-app build/apk-app.zip && unzip -p build/apk/pycon-us.apk assets/app.zip > build/apk-app.zip \
  && unzip -q build/apk-app.zip -d build/apk-app && diff -rq build/python-app build/apk-app
```

The release builds of §8.3 keep the app elsewhere: an AAB under `base/assets/`, an IPA in `Payload/*.app`, and an unsigned `flet build ipa` (today, until #121; §8.2) in the `.xcarchive`'s `Products/Applications/*.app`:

```bash
# AAB (flet build aab)
rm -rf build/aab-app build/aab-app.zip && unzip -p build/aab/pycon-us.aab base/assets/app.zip > build/aab-app.zip \
  && unzip -q build/aab-app.zip -d build/aab-app && diff -rq build/python-app build/aab-app
# Signed IPA (flet build ipa with a provisioning profile)
rm -rf build/ipa-app && unzip -q build/ipa/pycon_us.ipa -d build/ipa-app && diff -rq -x .keep build/python-app \
  build/ipa-app/Payload/*.app/serious_python_darwin_serious_python_darwin.bundle/app
# Unsigned archive (flet build ipa without one)
diff -rq -x .keep build/python-app \
  build/ipa/pycon-us.xcarchive/Products/Applications/*.app/serious_python_darwin_serious_python_darwin.bundle/app
```

Checked on 2026-10-12 (#176), from a fresh clone of the cache: `flet build ios-simulator` took 4 minutes and `flet build apk --arch arm64-v8a` 2 minutes. Both staged into `build/pub-cache` (`dist_ios/app` and `assets/app.zip` written by these builds) while the copies in `~/.pub-cache` still held another worktree's app from half an hour earlier, both checks printed nothing, and the app ran on an iPhone 17 simulator (iOS 26.5). On 2026-10-13, `flet build aab` (`build/aab/pycon-us.aab`) and an unsigned `flet build ipa` (`build/ipa/pycon-us.xcarchive`) from the same clone passed the AAB and archive checks; the signed-IPA line was tried on an IPA zipped by hand from that archive's app, since no profile exists to export one yet (#121).

The upstream fix for the pub cache, staging per Flutter project instead of in the plugin's folder, is U28 (#185, flet-dev/serious-python#255; [`flet-gaps-and-extensions.md`](flet-gaps-and-extensions.md) §1.3). When a Flet bump brings it, this subsection and D-176 go.

### 5.9 Device flows: Maestro (D-252)

The flows in [`maestro/`](../maestro/README.md) drive the packaged app with the free,
local [Maestro](https://maestro.dev) CLI, on an emulator and a simulator of your own. The
README there has the whole setup, the build and install lines, every command and how to
write a flow; the strategy is [`testing-and-quality.md`](testing-and-quality.md) §5.5.

- **Install:** Maestro 2.11.0 from its own tap, `brew install mobile-dev-inc/tap/maestro`
  (plain `brew install maestro` is another product). The formula brings Homebrew's
  `openjdk`; Maestro needs Java 17 or later, so with its `curl` installer install a JDK
  yourself. `export MAESTRO_CLI_NO_ANALYTICS=1` keeps the CLI from sending usage data.
  Never `maestro login`, `maestro cloud` or a paid plan.
- **Build and install** as §5.8 says, with the worktree's own pub cache: a release APK
  (`flet build apk --arch arm64-v8a`, then `adb install -r`) and an `ios-simulator` build
  (then `xcrun simctl install <udid> build/ios-simulator/pycon-us.app`).
- **Run:** `maestro --device <id> test --include-tags=journeys maestro` (or `smoke`, or
  `regression`, or one flow's file). Each flow starts the app afresh, so a run replaces
  the app's data on that device: never use the owner's `emulator-5554` or a shared
  simulator.
- The flows need no `uv run` and no Python: Maestro reads the YAML and talks to the device. Debug output
  (screenshots, the view hierarchy, `maestro.log`) goes to `~/.maestro/tests/` unless
  `--debug-output build/maestro/<name>` names a folder.

### 5.10 The OS floors, run (#816)

Checked on 2026-11-02 at `22a6dcb16` (build 405, version 0.1.0), with `flet build apk --arch arm64-v8a` and `flet build ios-simulator`, on an emulator and a simulator (D-102), against a mock of our own on port 8816. The earlier evidence was API 34 (#140, S8), API 36 and iOS 26.5.

| Platform | Lowest run | Image | Result |
|---|---|---|---|
| Android | **API 24 (Android 7.0)** | `system-images;android-24;google_apis;arm64-v8a` (downloaded for #816, no account), AVD `Claude816_api24`, 1080x2400, 1.5 GB RAM | `aapt2 dump badging`: `minSdkVersion` 24, `targetSdkVersion` 36. The APK installs, the first cold start reaches Welcome in 5.0 s (`am start -W`), no `AndroidRuntime` error. 10 of the 13 Maestro journeys below passed in #816; the 3 that did not are explained below, and #953 and #952 fixed all three (13 of 13 now). |
| iOS | **iOS 18.6** (iPhone 16, `Claude-816-iPhone-18`) | the runtime already installed | `MinimumOSVersion` 15.0. Cold start reaches Welcome. All 12 journeys run pass, and so do the reminders primer's "deny" and "not now" answers. |

The journeys, run from `maestro/` on each image (`-e MOCK_URL=http://10.0.2.2:8816` on Android, `http://localhost:8816` on iOS):

| Step in #816 | Flow | API 24 | iOS 18.6 |
|---|---|---|---|
| Cold start | the first launch of each flow (`launch_fresh`), and a manual launch | pass | pass |
| Schedule | `search_any_day`, `jump_to_now` | pass | pass |
| A session | `drill_back` | pass | not run here |
| Star | `star_undo` | pass | pass |
| Map | `expo_map_card`, `find_room` | pass | pass |
| About | `about_app` | pass | pass |
| Reminders, granted | `reminder_settings` (switch on, lead 15, relaunch) | passes since #953: the Alarms & reminders card is checked absent (below). In #816 it failed on the card | pass |
| Reminders, denied | `reminder_primer` with `OS_ANSWER=deny`, and `PRIMER=not_now` | `reminder_primer` passes since #953: it checks that no primer or OS prompt shows (below); notifications blocked by hand as well (below) | pass, both |
| Staff tools | `coc_capture`, `lead_capture`, `door_check`, `swag_pickup` | `coc_capture`, `lead_capture` and `door_check` pass; `swag_pickup` passes since #952: below API 28 the badge field's helper text is not in the accessibility tree (below), so the flow reads the category chips' selected state there instead | all four pass |

**API 24 differs from the flows' Android assumption, and the app agrees with it, not the flows.** Notifications are allowed on Android 12 and below (there is no runtime prompt before API 33) and exact alarms need no grant before API 31, so on API 24: `reminder_primer` shows no primer (the OS already allows notifications, so there is nothing to ask) and `reminder_settings` shows no Alarms & reminders card (`exact_allowed()` is true). Both flows failed at those assertions in #816, with the app doing what `ui/reminder_primer.py` and `settings_reminders.py` say. Since #953 they ask for the level (`-e ANDROID_API=<level>`, `maestro/README.md`, "Android API levels"; `maestro/scripts/os_offers.js`) and check what the OS offers: from API 33 the primer and the OS prompt, below it neither (and no Allow notifications card in Settings); from API 34 the Alarms & reminders card, below it none. With notifications blocked in Android's own settings ("Block all"), Settings › Reminders shows "Reminders show only once you allow notifications."; the first tap on Allow notifications does nothing the user can see (Android answers without a prompt, F259), the second shows "Notifications aren't allowed. If Android shows no prompt, turn them on in system settings." with Open settings, which opens the App info page (Notifications: Blocked); after Block all is switched off the card is gone. A reminder firing on a real phone was not tried (D-102).

**What is not proven.**

- **iOS 15 to 17.** No simulator ran below iOS 18.6. Xcode 27.2's `xcodebuild -downloadPlatform iOS -buildVersion <v>` says "not available for download" for every version from 15.0 to 18.5 that was tried (15.0, 15.5, 16.0, 16.4, 17.0, 17.2, 17.5, 18.0, 18.1, 18.2, 18.3, 18.4, 18.5) and offers 26.0 and later. Apple's public runtime catalog (`devimages-cdn.apple.com/.../index2.dvtdownloadableindex`) still lists iOS 15.0 to 16.4, but marks them `maxXcodeVersion 26.99` (the 15.x ones are also the old installer-package kind), so Xcode 27.2 can't take them. Only Xcode 27.2 is on this Mac. What is proven about iOS 15 is what the build declares: `MinimumOSVersion` 15.0, and the app binary and 60 of its 61 frameworks have `minos` 15.0, the other 13.0 (`vtool -show-build`). It is not proof that the app starts on iOS 15.
- **Android 8 to 11 (API 26 to 30).** Not run. The AVD `Pixel_7_Pro_API_29_Q_-_has_Flet_App_` that #816 counted on is not usable here: its `.ini` points to an `.avd` folder that doesn't exist, and `~/Library/Android/sdk/system-images` has no `android-29`.
- **Screen readers on API 24 to 27.** TalkBack was not run: the `Claude816_api24` image has no TalkBack package, and nothing was installed from outside. What was read (#952, checked 2026-11-03 at `22a6dcb16`, build 405, API 24 and API 36 emulators, one APK): `uiautomator dump` shows every text field as an `EditText` with `text=""`, `content-desc=""` and no `hint`, where API 36 has `hint="Search sessions, speakers, places"` (Search) and the label and helper line in `hint` (the Swag pickup's Badge code field). The cause is Flutter's engine: `BaseRoleConfigurator.java:355-359` sets a text field's hint only from API 28 and gives it no content description (Flutter 3.47.8). So below API 28 a screen reader finds an unnamed edit box, and the scan screens' reasons under the field are not read; the result panel and the category chips are. That is a loss of information for a TalkBack user on Android 7.0 to 8.1, not only a Maestro limit. It is not fixed in our code (an upstream gap, U283, #968; `flet-gaps-and-extensions.md` §1.3), and `swag_pickup` asserts the helper line only where the tree has it (`maestro/README.md`, "Android API levels").
- **An outside tester's phone** (#462 criterion 6) and hardware.

---

## 6. Mock API workflow (P3, NEW-08, D-50..D-57)

The private-API features (sign-in, favourites sync, role flags and the four staff tools) only ever talk to `tools/mock_api/`.
- **The guard (D-51).** Those features stay hidden until a mock base URL is set in the Developer screen. The client also refuses any `/api/v1` request to a `*.pycon.org` host, and a unit test covers it.
- **The contract** is in [`tools/mock_api/README.md`](../tools/mock_api/README.md), which cites Ionic's `pycon-api.ts`
  by line: endpoints, signing, reply shapes, errors, what is unknown with the mock's choice for each, and the seed data.

**Run it:**

```bash
uv run python -m tools.mock_api.server                  # this machine, its simulators and emulators
uv run python -m tools.mock_api.server --host 0.0.0.0   # also phones on the same Wi-Fi
```

With other agents about, keep a mock on your checkout's own port, which outlives the command, and stop it when done. A second `start` keeps the running mock and its state; `stop` then `start` is a clean slate. Server options follow `start`:

```bash
uv run python -m tools.mock_api.own start [--fault lost_response]   # prints MOCK_URL for each platform
uv run python -m tools.mock_api.own url android                     # or ios
uv run python -m tools.mock_api.own stop
```

The options (`--host`, default `127.0.0.1`; `--port`, default `8000`; `--capture idempotent|non_idempotent`; the
faults below) are in [`tools/mock_api/README.md`](../tools/mock_api/README.md) ("Running it").
- **On start,** it prints the base URL for each kind of device (its LAN address with `--host 0.0.0.0`) and the seeded
  accounts' emails and passwords. There is one account per role, from `tests/fixtures/mock/`; the keys and secrets are
  fake and exist only for the mock, and the server never prints or logs them.
- **State** is in memory, so a restart is a clean slate. This also suits demos.
- **Faults (D-57)** replay conference Wi-Fi on a device. `--fault NAME` switches one on for the next request it
  applies to (repeat it for several; `--every-request` keeps them on until the server stops), and `--skew SECONDS`
  runs the mock's clock ahead (behind when negative):

  ```bash
  uv run python -m tools.mock_api.server --fault lost_response --skew 900
  ```

  | `--fault` | The server | The app sees |
  |---|---|---|
  | `connect` | closes the connection unanswered; nothing applied | a network error |
  | `timeout` | holds the request until the app gives up (60 s at most); nothing applied | a network error |
  | `lost_response` | applies the request, then closes the connection without the reply | a network error, though the server holds the record |
  | `revoked` | refuses a signed request with 401 (sign-in still works) | an auth error |

  The banner lists the faults and the skew that are on, and the log marks each request a fault took, e.g.
  `POST /2026/api/v1/authenticate/ 200 (lost_response fault, reply dropped)`. Tests switch the same faults on
  `MockState` (`state.faults.inject(...)`, `state.skew`); the mock README's "Faults" says what each simulates.

**Connect the app:** Developer screen › Mock API base URL.

| Where the app runs | Base URL | `--host` |
|---|---|---|
| Companion client (Python on the laptop) | `http://localhost:8000` | default |
| Android emulator, packaged build | `http://10.0.2.2:8000` (the emulator's alias for the laptop's loopback) | default |
| iOS simulator, packaged build | `http://localhost:8000` (the simulator shares the laptop's network) | default |
| Physical phone, packaged build | `http://<laptop LAN IP>:8000`, on the same Wi-Fi; the banner prints it | `0.0.0.0` |

The server answered over `localhost` and over the laptop's LAN address on 2026-10-28 (#666). The packaged builds'
rows were checked in #668 on 2026-10-28: a release APK on the Android 16 emulator reached `http://10.0.2.2:<port>`, and
an `ios-simulator` build on an iPhone 17 simulator (iOS 26.5) reached `http://localhost:<port>`. In both, Developer's Check
mock connection said "Connected to the local mock server.", in light and dark, and again after a relaunch.

**Practical notes:**
- **Cleartext HTTP.** The client is Python `httpx` on raw sockets. Android's cleartext policy and iOS App Transport Security govern the platform HTTP stacks, not these sockets, so no manifest or Info.plist change is needed. **Confirmed on 2026-10-28 (#668):** the release APK reached the mock over plain HTTP with no `usesCleartextTraffic` and no network-security config, and the simulator build did too, with no ATS error and no local-network prompt. A simulator shares the Mac's loopback, so a physical iPhone on the Wi-Fi may still ask for local-network access (§3.4); that check waits for the iPhone (#121).
- **The laptop firewall.** macOS asks to allow incoming connections for Python the first time; allow it.
- **Venue or office Wi-Fi often isolates clients.** Use a phone hotspot or a travel router instead.
- **Device flows.** `maestro --device <id> test --include-tags=staff maestro` drives the four staff tools against a running mock, signing in with the seed accounts. The Maestro README's "Staff flows and the mock" says what each run leaves in the mock's memory, and that the swag hand-out needs a mock just started.
- **Tests** drive the same pure `handle()` behind `httpx.MockTransport` (D-50), so they cover signing, faults and both semantics without a network. Only `tests/test_mock_api_server.py` starts the server, in-process on `127.0.0.1` with an ephemeral port, under the `loopback` marker (`no_network`'s one opt-out).
- **Badges.** `uv run python -m tools.mock_api.badges` writes `build/mock-badges.html`, the printable sheet of mock-badge QR codes for the P3 exit test (one card per seeded attendee, A4 or Letter; `segno`, D-391). The mock README says more.
- **Stage demos** use this LAN mock from the laptop, with no in-app backend (D-457). [`demo-script.md`](demo-script.md) runs on simulators, which use the table above, so it needs no hotspot (D-463). A phone can't reach the laptop's loopback, so with no Wi-Fi it joins a laptop hotspot, with the server on `--host 0.0.0.0`; that hasn't been tried yet, and the script lists what's unknown.

---

## 7. Checks and GitHub Actions (D-84, D-273)

**While the repo is private, the checks run locally** (D-273). A private repo on GitHub Free includes 2,000 Linux minutes a month, and by 2026-10-20 `ci.yml`, run on every PR push and every push to `main`, had used about 1,875 of them. So GitHub Actions run only by hand, and local checks replace them.

**`tools/check.sh`** runs `ci.yml`'s steps (§7.2) in the same order on your machine: `uv sync --locked`, `ruff check`, `ruff format --check`, `pyright`, `pytest --hypothesis-profile=ci`, with `UV_LOCKED=1`. `--fast` runs every step but pytest. It prints one line per step and stops at the first failure, with that step's exit status. On the owner's Mac the fast run takes about 10 s and the full one about 6 minutes (344 s in the gate of 2026-11-02, for 8,420 tests). It runs at three points:
- **The pre-push hook**, `.githooks/pre-push`, turned on once per clone with `git config core.hooksPath .githooks` (§5.1; every worktree of the clone then runs its own checkout's hook). Before each push it runs `tools/check.sh --fast`, unless the push changes only Markdown (`*.md`) or nothing: it compares a new branch with its merge base with `origin/main`, and an existing one with the remote's commit (a remote commit it doesn't have counts as code). The checks see the working tree, so it warns when that has uncommitted changes or HEAD isn't the pushed commit. `git push --no-verify` skips it once. A branch from before D-273 has no hook.
- **Before you mark a PR ready**, run the full `tools/check.sh` and list it in the PR.
- **`tools/merge.sh <pr> [<pr>...]`** gates the PRs and squash-merges them, one run at a time on the Mac. It merges only on the gate's own exit status, and only the head it read before the gate, so a push after that needs a new gate: `tools/gate.sh <pr> | tail … && gh pr merge <pr>` takes tail's status, and that merged #868 after a failed gate. Its exit status says what happened: 0 merged, with `main` at the gated tree; 1 the gate failed and nothing merged; 3 a merge didn't happen or `main`'s tree differs, so run `tools/check.sh` on `main`.
- **The merge gate**, `tools/gate.sh <pr> [<pr>...]`, runs before every merge (D-100 condition 1, D-273). It fetches `main`, creates a scratch worktree detached at `origin/main` merges each PR's head into it in the order given, and runs the full `tools/check.sh` there, into a log.
  - The scratch worktree lives in `~/Library/Caches/gate.XXXXXX` and is removed when the gate ends. Not in `$TMPDIR`: macOS's `dirhelper` sweeps that daily at 03:35, removing files older than 3 days, and uv's clones keep their old timestamps, so a sweep during a gate can take files from its fresh `.venv` and fail tests falsely (inferred from a gate log, since `dirhelper` logged nothing; #898). `$HOME` and `$TMPDIR` are on the same volume, so `cp -c` and uv's clones still work. A gate killed outright (SIGKILL, a power loss) can't remove its scratch, and nothing sweeps that folder, so each gate first removes any `gate.XXXXXX` there untouched for a day; a younger one may be another gate's, running now.
  - A PR that doesn't merge cleanly stops it: merge `main` into that PR's branch first.
  - When a check fails, it prints the end of the log, keeps the log and posts nothing.
  - When the checks pass, it posts one comment on each PR: "Local checks passed (D-273): `main` <sha> + #<pr>@<sha> … → tree `<sha>`", the steps and pytest's summary line, then `$GATE_SIGNATURE` in a paragraph of its own when that is set (agents set their signature line, AGENTS.md rule 6). It prints the merged tree's sha last, the only line on its standard output.
  - Exit status: 0 passed, 1 failed (or couldn't run), 2 usage.
  - Its result holds for the PR's head and the `main` it names: after a new push to the PR, or once `main` has moved, run it again. Gate a batch together, in merge order, and squash-merge it in that order; `main`'s tree (`git rev-parse origin/main^{tree}` after a fetch) must then equal the printed tree, or else run `tools/check.sh` on `main`.

No Linux machine runs the checks until P4 (the owner's call), so a failure that only Linux shows would surface when CI comes back. The PR that makes the repo public brings back the workflows' triggers below (`ci.yml`'s PR and `main` triggers, the feed check's schedule, `build-android.yml`'s tags), and with them §7.2's required checks.

### 7.1 Constraints of a private repo on GitHub Free

Check the current numbers in Settings › Billing; these were the terms at the time of writing.

| Constraint | Consequence for us |
|---|---|
| Included Actions minutes are limited (2,000 Linux minutes a month), and macOS minutes count about 10× Linux | Everything runs on Linux. There is no iOS job (§7.5). While the repo is private, every workflow runs only by hand and the checks run locally (§7, D-273). |
| Artifact storage is small (hundreds of MB) | APK artifacts are kept for 14 days. |
| Branch protection and rulesets are not enforced on private repos | `main` is protected by convention until the repo is public (D-88): PRs only, the merge gate passed (D-273), agents merge under D-100. Creating a ruleset returns HTTP 403 (checked 2026-10-11); AGENTS.md › Branches and commits has the ruleset to add once the repo is public. |
| Environments (and their secrets and required reviewers) are unavailable for private repos | We need none: CI holds no secrets (D-86). |

Conventions in every workflow:
- `permissions: contents: read`.
- `persist-credentials: false` on checkouts.
- Third-party actions pinned to a full commit SHA, with the version as a comment. The pins were checked against their release tags on 2026-10-11 (annotated tags followed to the commit): `actions/checkout` v6.0.3 is `df4cb1c069e1874edd31b4311f1884172cec0e10`, `astral-sh/setup-uv` v8.3.2 is `11f9893b081a58869d3b5fccaea48c9e9e46f990`; checked on 2026-10-12, `actions/upload-artifact` v7.0.1 is `043fb46d1a93c77aae656e7c1c64a875d1fc6a0a`.
- actionlint and zizmor (`uvx zizmor --persona=pedantic .github/workflows/`) are clean on every workflow change.
- `pull_request`, never `pull_request_target`.
- `UV_LOCKED=1`, so every `uv` command fails if `uv.lock` is stale.

### 7.2 `.github/workflows/ci.yml`: by hand while the repo is private

[`.github/workflows/ci.yml`](../.github/workflows/ci.yml) is the source of truth; this section says what it does and why. `tools/check.sh` runs the same steps locally (§7).

**Required checks (D-100).** While the repo is private, the required check is the merge gate's (§7, D-273): it ran the full checks on the PR merged onto the latest `main` and posted its result on the PR. When the repo is public, a PR may be merged only when every check below has passed on its latest commit. A missing, pending, skipped or cancelled required check is not green. Rename a job only together with this list.

| Workflow | Job id | Check name (as GitHub shows it) |
|---|---|---|
| `CI` (`ci.yml`) | `check` | `Lint, types and tests` |

`gh pr checks <n>` lists them. GitHub does not enforce this list on a private Free repo (§7.1); agents check it before merging.

**One Linux job**, `Lint, types and tests`. Its steps, in order (the first failure fails the job):

| Step | Command | Why |
|---|---|---|
| Check out the app | `actions/checkout` | |
| Set up uv | `astral-sh/setup-uv`, `version: "0.12.x"`, `enable-cache: true` | uv stays on the `uv_build>=0.12,<0.13` line of `pyproject.toml`; unpinned, the action installs the latest uv, which warns that `uv_build` does not match it. Bump both together. The cache holds uv's packages, keyed on `uv.lock` and the `pyproject.toml` files. `uv sync` then installs CPython 3.14 from `requires-python`. |
| Install | `uv sync --locked` | Fails if `uv.lock` is stale (D-75). |
| Lint, Check formatting | `uv run ruff check`, `uv run ruff format --check` | D-74 |
| Type-check | `uv run pyright` | D-74 |
| Test | `uv run pytest --hypothesis-profile=ci` | D-76. Hypothesis's built-in `ci` profile (derandomised, no deadline, `too_slow` suppressed), extended in `tests/conftest.py` to 200 examples per property; named explicitly rather than left to the `CI` variable (testing-and-quality.md §3.1). |

**Triggers and concurrency.** While the repo is private it runs only by hand (`workflow_dispatch`, D-273): Actions › CI › Run workflow, or `gh workflow run ci.yml --ref <branch>`; each run has a concurrency group of its own (the run id). The PR that makes the repo public brings back its triggers, every `pull_request` and every push to `main`. Then the concurrency group is the PR number, so a new push to a PR cancels that PR's older run. A push to `main` gets a group of its own (the run id): in a shared group a newer run would replace a pending one, even with `cancel-in-progress: false`. So every commit on `main` keeps its own result.

The target is under 2 minutes (D-84). The time-zone tests run under two machine time zones through a pytest fixture, not a CI matrix (D-43). UI flows never join this job: spike S9 tries `flet test linux`, and a green result becomes a separate workflow through a `needs-decision` issue (D-78). S9 needs GitHub's Linux runners, so it waits until the repo is public (D-273).

### 7.3 `.github/workflows/feed-check.yml`: by hand while the repo is private

[`.github/workflows/feed-check.yml`](../.github/workflows/feed-check.yml) is the source of truth; this section says what it does and why. It is not a required check (§7.2).

**Run it:** locally, `uv run python -m tools.check_feed` (add years, e.g. `2025 2026`, to check those instead). It runs as a module because it imports `tools.feed_invariants`. By hand on GitHub: Actions › Feed check › Run workflow, or `gh workflow run feed-check.yml --ref main`. While the repo is private there is no weekly run (D-273), so run it when the feed matters: before a snapshot PR (§8.3), and while next year's feed is expected. The PR that makes the repo public brings back its schedule, Mondays at 06:17 UTC.

**One Linux job**, `Parse the public feed`, with a 10-minute timeout and `contents: read` only. Its steps are `ci.yml`'s up to `uv sync --locked` (the same checkouts, Flet pin, uv line and cache, §7.2), then `uv run python -m tools.check_feed`. A run takes well under a minute after setup: fetching and processing the 2026 feed takes about a second.

- **What it checks.** `tools/check_feed.py` fetches the `feed_url` of `config.YEAR` and runs our parser (`feed.process`) and every invariant of `tools/feed_invariants.py` over it: the same functions `tests/test_feed_invariants.py` runs on the recorded feeds (D-77, testing-and-quality.md §3.3). It fails, exiting with 1, when the feed cannot be fetched (a 404 included), does not parse, has a record the parser skips, or breaks an invariant. The report lists the counts, each broken invariant with up to ten of its problems, and the keys the recorded feeds lack, which never fail: the parser ignores unknown keys.
- **Next year.** It also says whether next year's feed answers, at this year's `feed_url` with the next year in its path (D-05's pattern): "not published yet (HTTP 404 …)", "redirects to … not published yet" (a redirect is never taken for the new feed), or "PUBLISHED … with N slots". That line never fails the run. When it appears, record the feed (`tests/fixtures/feeds/README.md`) and add `data/<year>/` (docs/roadmap.md, the 2027 rollover).
- **Notification.** With the schedule back, a failed scheduled run emails the person who last changed the schedule. That is the alert, so there is no issue bot and no `issues: write`.
- **Concurrency.** One run at a time (group `feed-check`, `cancel-in-progress: false`): every run checks the same live feed, so a pending run may be replaced, but a running one is never cancelled.

### 7.4 `.github/workflows/build-android.yml`: on demand

[`.github/workflows/build-android.yml`](../.github/workflows/build-android.yml) is the source of truth; this section says what it does and why. It builds a debug-signed arm64 APK (D-84, D-86, D-106). It is not a required check (§7.2).

**Run it:** Actions › Build Android › Run workflow, or `gh workflow run build-android.yml --ref main` (or `--ref vX.Y.Z` for a tag). While the repo is private, pushing a `vX.Y.Z` tag no longer runs it (D-273): build the quick-look APK locally instead (§8.1, the same `flet build apk --arch arm64-v8a` command), or run the workflow by hand. The PR that makes the repo public brings back the tag trigger (§8.3). A new run for the same branch or tag cancels the older one.

**One Linux job**, `Debug-signed APK`, with a 45-minute timeout. Its steps, in order:

| Step | Command | Why |
|---|---|---|
| Check out the app | `actions/checkout`, `fetch-depth: 0` | The build number is the commit count (§4). The build also reads `flutter_packages/roboto_fonts` (§3.1). |
| Check that the tag matches the version | Tags only: the tag must equal `v` + `[project].version`; otherwise the job fails with an error naming both | §4 |
| Read the build number | `git rev-list --count HEAD` | |
| Set up uv | `astral-sh/setup-uv`, `version: "0.12.x"`, `enable-cache: false` | The same uv line as `ci.yml` (§7.2). No cache: a tag build starts from clean inputs, and `uv sync` takes seconds. |
| Install | `uv sync --locked` | D-75 |
| Free disk space | `sudo rm -rf /usr/share/dotnet /usr/local/.ghcup /opt/hostedtoolcache/CodeQL` | The build fills about 11 GB (Flutter, the NDK, Gradle's caches) and the runner starts with about 13 GB free: the first run ended with 1.9 GB left. These preinstalled toolchains are never used here. |
| Build the APK | `uv run flet build apk --arch arm64-v8a --build-number <count> --yes -v`, with `FLET_CLI_NO_RICH_OUTPUT=1` | The command of §8.1 with D-106's ABI. `--yes` lets flet-cli download Flutter (the version in the `flet` wheel) into `~/flutter`; it uses the runner's JDK 17 (`JAVA_HOME`) and Android SDK (`ANDROID_HOME`). `-v` and plain output keep the log useful when a build fails. |
| Name the APK | `build/apk/pycon-us.apk` → `pycon-us-<count>-<short sha>-arm64-v8a.apk` | Downloads from different runs don't collide. |
| Upload the APK | `actions/upload-artifact`, artifact named like the file, `compression-level: 0`, `overwrite: true`, `retention-days: 14` | Zipped (the default), because `gh run download` cannot fetch an unzipped artifact: it unzips the APK itself and fails (cli/cli#13012, seen on the first run). No compression, because an APK is already compressed. `overwrite`, because a re-run of the same run uploads the same name again. 14 days, because artifact storage is small (§7.1). |

**Measured** in #54 (two runs, no caches, Flet `15854a0ac`, `ubuntu-latest`: 2 vCPUs, 7.9 GB RAM, 3 GB swap):

| | First run | Last run, with Free disk space |
|---|---|---|
| Job | 12 min 34 s | 9 min 33 s |
| Flutter 3.47.7 download and extract | 67 s | 50 s |
| `flet build apk` in all | 12 min 5 s | 8 min 45 s, of which Gradle's `assembleRelease` 5 min 44 s (it also downloads NDK r28c and CMake 3.22.1) |
| Memory with `-Xmx4G` | at least 1,067 MB available; 45 MB of swap used | at least 1,888 MB available; 397 MB of swap used |
| Free disk | 13 GB before, 1.9 GB after | 24 GB before, 13 GB after (Free disk space took 23 s) |
| Artifact | 56,208,360 bytes (`versionCode` 14) | 56,208,552 bytes (`versionCode` 16) |

So the `-Xmx4G` heap fits the runner, with about 1 GB to spare. Both APKs installed and started on the `flet_probe_api34` emulator. The two runs signed with different debug keys, so the second installed only after `adb uninstall`.

**Why not `flet-dev/flet-build-action`.** It was the plan, but running the documented command directly is simpler (`ACTION/action.yml` at `v1`):
- Its own `setup-uv` step installs the latest uv, which would replace the `0.12.x` line we keep with `uv_build` (§7.2).
- It wraps the APK in its own `flet-apk.zip` and names it the same in every run.
- P0-06 asks for the same commands as this document, and one `flet build apk` line is exactly that.

When 1.1.0 is on PyPI and the Flet checkout goes, the action is worth another look: its Flutter SDK cache would save about a minute per run.

**No caches.** On the runner the Flutter download takes about a minute and Gradle most of the rest; the workflow runs rarely, and each cache would be one more key to keep right across pin bumps. So the S5 caveat (a cache keyed on the constant `0.1.0` needs one uncached run after a pin bump) does not apply: every run is uncached.

**This APK is a quick look, not an install to keep.** It is signed with the runner's throwaway debug key, which differs from your machine's and changes with every run.
- Download it with `gh run download <run-id>`, which unzips it into a folder named after the APK, then run `adb install <that folder>/pycon-us-<…>.apk`. The run page gives you the zip; unzip it first.
- Installing over an earlier CI build, or over a local build, therefore fails with `INSTALL_FAILED_UPDATE_INCOMPATIBLE`. Run `adb uninstall io.github.ndonkohenri.confcompanion` first, which loses the app's data.
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

### 7.6 Sweep for secrets and vulnerabilities (#847)

Everything in the repository becomes visible when it goes public, including every PR's `refs/pull/*` head, which no one can delete, and the `pr-assets` images. So this sweep runs twice: once while the repo is private, and again right before the flip (#852 needs the second result clean). The results go on #847. It's local and free, and it changes nothing on GitHub.

**Tools,** once: `brew install gitleaks trufflehog osv-scanner tesseract`. The scratch folder `build/` is git-ignored; delete `build/sweep` when you're done.

**Secrets in history.** A mirror clone is the only checkout that holds all the branches and `refs/pull/*`. The scan reads a dump of it because that also covers commit messages and deleted lines, which `gitleaks git` skips (and an agent's isolated worktree refuses `gitleaks git`). `--redact` keeps values out of the report and `--no-verification` keeps candidates on this machine: **never** let a scanner try one against a live service.

```sh
mkdir -p build/sweep/api
git clone --mirror https://github.com/ndonkoHenri/pycon-us-flet.git build/sweep/mirror.git
git -C build/sweep/mirror.git log --all --full-history -p -U0 --diff-merges=cc --format='commit %H%n%an <%ae>%n%cn <%ce>%n%B' > build/sweep/history.patch
gitleaks dir build/sweep/history.patch --redact --exit-code 0 --report-format json --report-path build/sweep/gitleaks-history.json
trufflehog filesystem build/sweep/history.patch --no-verification --no-update --json --results=verified,unknown,unverified > build/sweep/trufflehog-history.jsonl
```

A hit's `StartLine` is a line of the dump. To find its commit: `awk -v n=<line> 'NR<=n && /^commit /{c=$0} NR==n{print c; exit}' build/sweep/history.patch`.

The first sweep's only hits were 34 `generic-api-key` from gitleaks, all false positives: 28 in `tests/fixtures/ionic/signing.json` (two commits; signatures made with the fixture's own dummy secret) and 6 in `src/pycon_us/screens/track.py` (four commits; the argument name `tokens` beside an identifier). `.gitleaks.toml` allowlists exactly those two, so a scan of the tree or of a commit stays quiet about them; the default rules stay on. Anything else is new: look at it. Never paste a value. Say where it is, and mark it for the owner to rotate; rewriting history is the owner's call (D-101).

**Secrets in what people wrote** (issues, PRs, comments, reviews):

```sh
gh api 'repos/ndonkoHenri/pycon-us-flet/issues?state=all&per_page=100' --paginate > build/sweep/api/issues.json
gh api 'repos/ndonkoHenri/pycon-us-flet/issues/comments?per_page=100' --paginate > build/sweep/api/issue-comments.json
gh api 'repos/ndonkoHenri/pycon-us-flet/pulls/comments?per_page=100' --paginate > build/sweep/api/review-comments.json
gh api graphql --paginate -f query='query($endCursor:String){repository(owner:"ndonkoHenri",name:"pycon-us-flet"){pullRequests(first:100,after:$endCursor){pageInfo{hasNextPage endCursor} nodes{number reviews(first:50){nodes{body}}}}}}' > build/sweep/api/pr-reviews.json
gitleaks dir build/sweep/api --redact --exit-code 0 --report-format json --report-path build/sweep/gitleaks-github.json
trufflehog filesystem build/sweep/api --no-verification --no-update --json --results=verified,unknown,unverified > build/sweep/trufflehog-github.jsonl
```

**Personal data in the `pr-assets` images.** Read their text, scan it, and look through what's new since the last sweep (#847 names that commit; `git -C build/sweep/mirror.git diff --name-only <commit> pr-assets`):

```sh
mkdir -p build/sweep/pr-assets
git -C build/sweep/mirror.git archive --format=tar pr-assets -o ../pr-assets.tar
tar -xf build/sweep/pr-assets.tar -C build/sweep/pr-assets
find build/sweep/pr-assets \( -name '*.png' -o -name '*.jpg' \) -print0 | OMP_THREAD_LIMIT=1 xargs -0 -P 8 -I{} tesseract {} {} --psm 11
gitleaks dir build/sweep/pr-assets --redact --exit-code 0 --report-format json --report-path build/sweep/gitleaks-images.json
grep -rhoE --include='*.txt' '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}' build/sweep/pr-assets | sort | uniq -c | sort -rn
```

Only `example.com` and `example.org` sample accounts, the conference's public addresses and Mastodon handles should show. OCR misses what small text and pictures hold, so looking is still part of it.

**Personal data in the text.** Look at the commit identities (`git -C build/sweep/mirror.git log --all --format='%ae%n%ce' | sort | uniq -c`), and grep the dump and `build/sweep/api` for phone numbers, emails and `/Users/`. A phone number that isn't a `555-01xx` fake or the Code of Conduct hotline needs a look. #847's first result lists what is already known.

**Dependabot** (`.github/dependabot.yml`) keeps the Actions our workflows and `uv.lock` current, leaving out the Flet family (§2.2).

**Python dependencies on the host.** `uv.lock` is what the tools and tests run on, and nothing else:

```sh
uv export --locked --format requirements-txt --no-hashes --no-emit-project -q -o build/sweep/req.txt
uvx pip-audit -r build/sweep/req.txt --no-deps --disable-pip
osv-scanner -L uv.lock
```

Fix a hit here with `uv lock --upgrade-package <name>`, and run `tools/check.sh`. That changes nothing on a phone.

**Python dependencies on phones.** `flet build` never reads `uv.lock` (§2). pip resolves `[project].dependencies` and everything they pull in when the build runs, wheels only, from PyPI and `pypi.flet.dev`, once per architecture. So only a build can say what ships, and the next build can ship something else. An iOS build of 2026-11-02 differed from the lock on three packages: `msgpack` 1.1.2 (lock: 1.2.3), `anyio` 4.16.0 (4.15.1) and `oauthlib` 4.0.1 (4.0.0).

So audit builds, not the lock. On the day of the sweep, delete `build/site-packages`, make an Android build, and run this right after it. Then do the same with an iOS build, since each build replaces that folder:

```sh
for arch in build/site-packages/*/; do
  echo "$arch"
  find "$arch" -maxdepth 1 -name '*.dist-info' -exec basename {} .dist-info \; | sed -E 's/-([^-]+)$/==\1/' | grep -vE '^flet(_|==)' > build/sweep/req-phone.txt
  uvx pip-audit -r build/sweep/req-phone.txt --no-deps --disable-pip
done
```

The result covers those builds only. `uv tree --locked --no-default-groups` lists the names that may ship, but its versions are the lock's.

Fix a hit that ships with an exact pin in `[project].dependencies`, like `tzdata==2026.5`, then `uv lock`, or by seeing that a new build already resolves the fixed version. Either way, run the audit on a new build to confirm it. If no phone wheel has the fix, a pin would break the build, so it's an `upstream` issue here (D-213). One is known: `msgpack` 1.1.2, the newest wheel on `pypi.flet.dev`, has two advisories (#890).

**Dart dependencies.** A real build has the set that ships, with the extensions (§5.3):

```sh
osv-scanner -L build/flutter/pubspec.lock
```

The OSV database covers few Dart packages, so "no issues found" there says less than it does for Python. A vulnerable Dart package is a Flet matter: an `upstream` issue here (D-213).

**Not covered:** the Android and iOS native dependencies (Gradle, CocoaPods) of a build; commits that a force-push left unreachable from any ref (GitHub keeps them for a while, and no one can list them); old versions of edited comments; and the logs of past Actions runs, which hold no repository secrets since there are none (D-86).

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
keytool -genkeypair -v -keystore ~/keys/confcompanion-upload.jks \
    -keyalg RSA -keysize 2048 -validity 10000 -alias upload
```

**A signed local build:**

```bash
# The values come from the password manager; nothing is written to the repo.
export FLET_ANDROID_SIGNING_KEY_STORE=~/keys/confcompanion-upload.jks
export FLET_ANDROID_SIGNING_KEY_ALIAS=upload
read -rs FLET_ANDROID_SIGNING_KEY_STORE_PASSWORD && export FLET_ANDROID_SIGNING_KEY_STORE_PASSWORD
uv run flet build aab --build-number "$(git rev-list --count HEAD)"   # or: apk --arch arm64-v8a
```

- flet-cli reads these four variables (`CLI/commands/build_base.py:3424-3456`). One password fills the other, and the alias defaults to `upload`. The template switches the release build to that signing config (`TPL/android/app/build.gradle.kts:103-119`).
- **Play Console setup,** once:
  - create the app under the neutral working name;
  - keep Play App Signing (the default for new apps);
  - complete the declarations Play asks for before the first internal release.
- **Target API.** Play enforces a minimum `targetSdk` on uploads; ours is 36, the latest stable level (D-106).
- **The bundle id cannot change** once an app exists in Play Console: D-452 settled it first.

#### What Android backs up (D-472)

Auto Backup takes one file, `shared_prefs/FlutterSharedPreferences.xml`: favourites, settings and the Developer options come back on a new phone. The secure-storage files (the API key and secret, wrapped by a Keystore key that stays on the old phone) and the outbox (`outbox-<year>.db`, queued scans) never leave it, and neither does the rest of `files/` (the feed cache, and the 24 MB of Python that Flet unpacks: a cloud backup's cap is 25 MB). A restored phone starts signed out ("Clearing a partial sign-in" in the log), with its favourites and an empty outbox. The rules are `android_res/xml/backup_rules.xml` (Android 11 and older) and `data_extraction_rules.xml` (12 and newer), an allowlist because the rules take no wildcards and the outbox's name holds the year; `tests/test_android_backup_rules.py` pins them.

**Check a backup and restore** on an emulator without a Google account, with `bmgr` and its local transport. The emulator must be a `google_apis` image (`adb root`), and the app must be running, since Android skips a stopped app ("Backup is not allowed"). Sign in against the mock (§6), star a session, cut the network (`cmd connectivity airplane-mode enable`) and scan two badges, so the outbox holds two rows, then:

```bash
P=io.github.ndonkohenri.confcompanion; S=<emulator id>
adb -s $S root
adb -s $S shell "bmgr enable true; bmgr transport com.android.localtransport/.LocalTransport"
adb -s $S shell "cmd connectivity airplane-mode disable; am start -n $P/.MainActivity; sleep 5; bmgr backupnow $P"
# What went in: the transport's tar holds apps/$P/_manifest and sp/FlutterSharedPreferences.xml, and nothing else.
adb -s $S shell 'tar -tvf $(find /data/data/com.android.localtransport/files -path "*_full/'$P'")'
adb -s $S uninstall $P && adb -s $S install build/apk/pycon-us.apk   # the Keystore key goes with the uninstall
adb -s $S shell "bmgr restore 1 $P"
adb -s $S logcat -c; adb -s $S shell "am start -n $P/.MainActivity"
adb -s $S logcat -d | grep -i "unwrap\|partial sign-in"           # no unwrap failure, one partial sign-in
```

Expect: the app opens signed out; My schedule holds the starred session; `files/data/` has no `outbox-<year>.db`; the mock logs no request. Checked in #818 on an Android 16 emulator (the default rules gave a 24 MB backup, an `InvalidKeyException: Failed to unwrap key` and two restored queued scans; ours a 4 KB backup and none of those). The Android 11 file is the same include and has no emulator image here.

### 8.2 iOS

| Route | Build | Needs |
|---|---|---|
| The owner's iPhone, during development | `uv run flet debug ios -d <id>` (add `--release` to judge performance) | `team_id`, an Apple Development certificate, a Development provisioning profile that includes the device, and the device registered |
| Testers | `uv run flet build ipa --ios-export-method app-store-connect` → upload → TestFlight **internal testing** | An Apple Distribution certificate, an App Store provisioning profile and an App Store Connect record |

**Why the export method is chosen per command.** `flet debug` has no export-method default of its own: like `flet build`, it takes `--ios-export-method`, then `[tool.flet.ios] export_method`, then `debugging`, and signs with that method's profile and certificate (`CLI/commands/build_base.py:1493-1528`). The template writes them into the Debug, Release and Profile configurations with Manual signing (`TPL/ios/Runner.xcodeproj/project.pbxproj:363-373, 560-570, 595-605`), so Xcode never creates a profile for us. A distribution identity and an App Store profile cannot install an app on a device. So `export_method` stays unset (`debugging`, used by `flet debug ios`), and only the TestFlight build passes `--ios-export-method app-store-connect`.

Internal TestFlight testers are members of the owner's App Store Connect team: up to 100 people, with no Beta App Review. A build expires after 90 days. **External** testing would need Beta App Review, and the store name would then be visible outside the team, so it is out of scope (D-85).

**Setup** (owner-only, #121), with the identity in D-452. Today the Mac has a valid Apple Distribution identity, but its Apple Development certificate is revoked and no profile exists for our bundle id (S5):
1. Register an explicit App ID for the bundle id, and register the owner's devices.
2. Create an Apple Development certificate and a **Development** provisioning profile for the App ID that includes those devices (`flet debug ios` needs it; see the Flet blog post "flet debug", 2025-12-02, "Testing on a real iPhone/iPad device"). Regenerate it whenever a device is added.
3. Create an Apple Distribution certificate, and an App Store profile. Name both profiles exactly as in `pyproject.toml`.
4. Create an App Store Connect record under the name Conf Companion (D-452) and a SKU.
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
| No `provisioning_profile` for the chosen method (today, until #121) | flet-cli's warning panel, a build with `--no-codesign`, and only `build/ipa/pycon-us.xcarchive` (242 MB on disk at `22a6dcb16`; the `.app` inside is 83 MB, the dSYMs 158 MB). No `.ipa`. |
| A profile named but not installed on the Mac | flet-cli's pre-check stops within seconds, before Xcode: "Provisioning profile '…' is not installed", followed by the installed profiles. It also checks expiry, the team and the bundle id (`CLI/commands/build.py:297-389`). |
| A matching profile installed | A signed **`build/ipa/pycon_us.ipa`** (underscore, unlike the other artifacts; 44.8 MB in S5), `Apple Distribution` authority, `codesign --verify --deep --strict` clean. |

**Checked at `22a6dcb16` (#817, 2026-11-02).** An unsigned `PUB_CACHE=$PWD/build/pub-cache LANG=en_US.UTF-8 uv run flet build ipa --yes` of the real app, from a fresh worktree, Xcode 27.2 (27B52, iphoneos27.2 SDK), Flutter 3.47.7, Python 3.14.10, took 11 min 30 s (packaging 5 min, `xcodebuild archive` 6 min) while another worktree built Android, and ended with no warnings or errors. `Info.plist` of the archive reads arm64, `io.github.ndonkohenri.confcompanion`, `0.1.0` (1), `MinimumOSVersion` 15.0, URL scheme `confcompanion`; `codesign -dv` says "not signed at all". The `.app` holds the `permission_handler_apple`, `flutter_local_notifications` and `flutter_secure_storage_darwin` bundles, `Python.framework` with the 50-odd extension frameworks, and `serious_python_darwin_serious_python_darwin.bundle/app/pycon_us` and `site-packages/` with `flet_notifications`, `flet_permission_handler` and `flet_secure_storage`. It has no `NS…UsageDescription` key, and `src/` asks for no permission that needs one. Not run on hardware (#121).

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
1. `main` is green: its tree is one the merge gate passed, or `tools/check.sh` passed on it (§7, D-273; when the repo is public, `ci.yml` passed on it). The phase status issue lists what this build is for.
2. **Snapshot PR:** run `uv run python tools/update_snapshot.py`, which refreshes `data/<year>/conference.json` and its `snapshot_captured_at` in `conference.toml` (D-38, D-135, NEW-03). It refuses a feed that `feed.process` rejects, that has a record the parser skips, or whose days fall outside the conference dates, and then changes nothing (exit status 1). Otherwise it prints each count before and after (sessions, speakers, days, posters, sprints, job listings); put that in the PR body, review the diff, then merge.
3. **Version PR:** bump `[project].version` and `__version__` (§4), then merge.
4. **Tag** `vX.Y.Z` on `main`. View source links to this tag, so a build without it opens a 404 (D-461). While the repo is private the tag builds nothing (D-273): build the quick-look APK locally (§8.1), or run `build-android.yml` by hand on the tag (`gh workflow run build-android.yml --ref vX.Y.Z`, §7.4). Once the repo is public, the tag runs it.
5. **Locally, at the same commit:**
   - run `uv sync --locked`;
   - if another build may run on the Mac, build with the worktree's own pub cache and run §5.8's AAB and IPA checks before uploading;
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
| Identity | Settled by D-452. The bundle id cannot change once a build is uploaded to App Store Connect or an app exists in Play Console. |
| Accounts | Apple: individual, or organisation (needs a D-U-N-S number). Google Play: new personal accounts must run a closed test (a minimum number of testers for 14 days) before production access; check the current rules. |
| Privacy | A privacy-policy URL (both stores require one). App Privacy: "Data Not Collected", since there are no analytics, no crash service and favourites stay on the device (D-08, D-72). The Play Data safety form. |
| Private API | Public builds keep the D-51 guard: the mock-only features are invisible without the Developer screen. A real backend needs the PSF (PLAN appendix). |
| Content and licences | Settle [the licence and asset review](licence-and-assets-review.md) (#846): `NOTICE`, the reused Ionic assets (floor plans, D-87), sponsor logos and the bundled dependencies' licences. |
| Secrets and vulnerabilities | Run the sweep in §7.6 again right before the flip (#847, #852). |
| Signing in CI | Optional at that point: move the keys to CI secrets (§7.5), superseding D-86 by decision. |
| Store assets | Screenshots, descriptions, the age-rating questionnaires. |

---

## 10. Open items this document depends on

S5 closed the rows it answered: builds from a source checkout of Flet (then §2.2, §8), the companion client (§5.2), Roboto (§3.4, D-105), the SDK levels and sizes (§2.1, D-106) and the Gradle heap on the Mac (§2.1).

| Item | Owner of the answer | Until then |
|---|---|---|
| ITMS-91053 on the first TestFlight upload (§8.2) | #121 | Testers get Android builds; the iPhone runs `flet debug ios` once it has a development certificate |
| An iPhone development certificate and profiles; the release numbers on the iPhone | #121 | Simulators only for iOS (§5.3) |
| `build-android.yml` on a GitHub runner: the `-Xmx4G` heap, `--arch arm64-v8a`, the first run's time | P0-06 (#54) | **Answered** by #54: the heap fits `ubuntu-latest` (7.9 GB; at least 1 GB available, swap under 400 MB), and a clean run takes about 9.5-12.5 minutes (§7.4) |
| A Flet companion app in the stores that speaks 1.1 | Flet 1.1.0 release | The companion client from a Flet clone (§5.2), or `flet debug` |
| Distribution routes | O-5 | Internal only (D-85) |
| Cleartext HTTP and iOS local-network behaviour with the LAN mock | The first P3 device test | Use the companion client or the emulator |
| serious_python stages the app in the shared pub cache, so overlapping builds can ship each other's Python (§5.8) | U28 (#185, flet-dev/serious-python#255) | A pub cache per worktree and the bundle check (§5.8, D-176) |
