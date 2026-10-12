"""Drive the S4 reproducer on an iOS simulator with xcrun simctl only.

Run from this folder after ``flet build ios-simulator``::

    uv run python drive_ios.py <simulator udid>

simctl cannot tap, so the app walks its own journeys (``S4_JOURNEY=1`` reaches it
as ``SIMCTL_CHILD_S4_JOURNEY``) and this script screenshots each ``checkpoint``
line. Then it checks background and resume, a dark-mode switch and deep entry
with the ``--route`` launch argument. The edge-swipe Back needs a human finger.
Results print as ``PASS`` or ``FAIL``; screenshots, the log and a screen
recording go to ``$S4_OUT`` (default ``./out``).
"""

import os
import re
import subprocess
import sys
import time
from pathlib import Path

UDID = sys.argv[1]
OUT = Path(os.environ.get("S4_OUT", "out"))
APP_ID = "io.github.ndonkohenri.pyconus.s4"
LOG = OUT / "ios-log.txt"
RESULTS = {"PASS": 0, "FAIL": 0}


def simctl(*args: str, env: dict[str, str] | None = None) -> str:
    """Run one ``xcrun simctl`` command and return its stdout."""
    done = subprocess.run(
        ["xcrun", "simctl", *args],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, **(env or {})},
    )
    return done.stdout


def lines() -> list[str]:
    """Every ``S4`` line logged so far."""
    text = LOG.read_text(errors="replace") if LOG.exists() else ""
    return [m[1] for m in re.finditer(r"(S4 [^\n]*)", text)]


def wait(pattern: str, after: int, timeout: float = 10.0) -> str | None:
    """Wait for an ``S4`` line matching pattern among lines()[after:]."""
    end = time.time() + timeout
    while time.time() < end:
        for line in lines()[after:]:
            if re.search(pattern, line):
                return line
        time.sleep(0.3)
    return None


def check(name: str, ok: bool, detail: str = "") -> None:
    """Record and print one result."""
    RESULTS["PASS" if ok else "FAIL"] += 1
    print(f"{'PASS' if ok else 'FAIL'} {name} {detail}".rstrip(), flush=True)


def shot(name: str) -> None:
    """Save a screenshot as OUT/<name>.png."""
    simctl("io", UDID, "screenshot", str(OUT / f"{name}.png"))


def main() -> None:
    """Run the in-app journeys, then lifecycle, dark mode and deep entry."""
    OUT.mkdir(parents=True, exist_ok=True)
    LOG.unlink(missing_ok=True)
    predicate = 'sender == "dart_bridge"'
    stream = subprocess.Popen(
        [
            "xcrun",
            "simctl",
            "spawn",
            UDID,
            "log",
            "stream",
            "--style",
            "compact",
            "--predicate",
            predicate,
        ],
        stdout=LOG.open("w"),
        stderr=subprocess.DEVNULL,
    )
    video = subprocess.Popen(
        [
            "xcrun",
            "simctl",
            "io",
            UDID,
            "recordVideo",
            "--codec",
            "h264",
            "--force",
            str(OUT / "ios-journeys.mp4"),
        ],
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(2)
        subprocess.run(["xcrun", "simctl", "terminate", UDID, APP_ID], check=False)
        bar = os.environ.get("S4_BAR_ON_PUSHED", "1")  # 0: the bar on roots only
        env = {"SIMCTL_CHILD_S4_JOURNEY": "1", "SIMCTL_CHILD_S4_BAR_ON_PUSHED": bar}
        simctl("launch", UDID, APP_ID, env=env)
        seen = 0
        end = time.time() + 120
        while time.time() < end and not wait(r"S4 journey-done", 0, 0.1):
            for line in lines()[seen:]:
                if m := re.search(r"S4 checkpoint .*name=(\S+)", line):
                    time.sleep(1.2)  # let the transition settle
                    shot(f"ios-{m[1]}")
            seen = len(lines())
            time.sleep(0.3)
        for line in lines():
            if re.search(r"S4 (step|per-level|search-kept) ", line):
                ok = " ok=True" in line
                check("in-app " + line.split(" t=")[1].split(" ", 1)[1][:150], ok)
        done = wait(r"S4 journey-done", 0, 1)
        check("in-app journeys finished", done is not None, done or "")
    finally:
        video.send_signal(2)  # SIGINT finishes the file
        video.wait()

    n = len(lines())
    simctl("launch", UDID, "com.apple.Preferences")
    check(
        "background reports a lifecycle change",
        wait(r"S4 lifecycle .*state=(inactive|hide|pause)", n) is not None,
    )
    time.sleep(2)
    n = len(lines())
    simctl("launch", UDID, APP_ID)
    check("resume reports resume", wait(r"S4 lifecycle .*state=resume", n) is not None)
    check("same session after resume", wait(r"S4 main ", n, 3) is None)
    n = len(lines())
    simctl("ui", UDID, "appearance", "dark")
    check("dark mode reported", wait(r"S4 brightness .*dark=True", n) is not None)
    time.sleep(1.5)
    shot("ios-dark")
    simctl("ui", UDID, "appearance", "light")
    check("light mode reported", wait(r"S4 brightness .*dark=False", n) is not None)

    # Deep entry. `simctl openurl` with our scheme stops at the system's
    # "Open in ...?" prompt, which needs a tap (held for a human), so this uses the
    # engine's --route launch argument, as `flet debug ios --route` does.
    for name, deep, ident in (
        ("ios-deep-entry", "/map/room/hall-a/session/42/speaker/23", "23"),
        (
            "ios-deep-quoted",
            "/schedule/session/poster%20detail%2B1/speaker/%C3%A7~31",
            "ç~31",
        ),
    ):
        subprocess.run(["xcrun", "simctl", "terminate", UDID, APP_ID], check=False)
        time.sleep(1)
        n = len(lines())
        simctl("launch", UDID, APP_ID, f"--route={deep}")
        landed = wait(rf"S4 top .*route={re.escape(deep)}(\s|$)", n, 30)
        check(f"deep entry {deep}", landed is not None)
        level = wait(rf"S4 level .*kind=speaker ident='{re.escape(ident)}'", n, 5)
        check(f"the level sees its id unquoted: {ident}", level is not None)
        time.sleep(1.5)
        shot(name)
    stream.terminate()
    print(f"== {RESULTS['PASS']} passed, {RESULTS['FAIL']} failed", flush=True)


if __name__ == "__main__":
    main()
