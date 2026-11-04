"""Apply what U7 would render to the generated Android project (S6 only).

flutter_local_notifications needs core library desugaring in the app module,
and the build template at the pin has no option for it, so `flet build apk`
stops at `:app:checkReleaseAarMetadata`. After that first failed build, run:

    uv run python patch_desugaring.py

then `flet build apk` again: the template is re-rendered only when its inputs
change, so the patched file is kept. An iOS build in between re-renders it, so
patch again after one. This is a spike shortcut, never an app practice
(docs/spikes/06-reminders.md, U7, #293).
"""

from pathlib import Path

GRADLE = Path("build/flutter/android/app/build.gradle.kts")
JAVA_17 = "targetCompatibility = JavaVersion.VERSION_17\n"
DESUGAR = "        isCoreLibraryDesugaringEnabled = true\n"
DEPENDENCY = 'dependencies {\n    coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.4")\n}\n'


def main() -> None:
    """Add desugaring to compileOptions and the desugaring library once."""
    text = GRADLE.read_text()
    if "isCoreLibraryDesugaringEnabled" in text:
        print("already patched")
        return
    text = text.replace(JAVA_17, JAVA_17 + DESUGAR, 1)
    text = text.replace("dependencies {}\n", DEPENDENCY, 1)
    if DESUGAR not in text or "desugar_jdk_libs" not in text:
        raise SystemExit("the template changed: patch by hand")
    GRADLE.write_text(text)
    print("patched", GRADLE)


if __name__ == "__main__":
    main()
