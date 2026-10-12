"""Drive the S4 reproducer on an Android emulator with adb and check each step.

Run from this folder with the APK installed (``flet build apk``, then
``adb install -r``)::

    uv run python drive_android.py <journey> [<journey> ...]

Journeys: ``drill``, ``roots``, ``retap``, ``search``, ``predictive``, ``memory``,
``lifecycle``, ``deep``, ``recreate``. Each step does one thing (a tap found in
the accessibility tree, the Back key, an edge swipe, an adb setting) and waits
for the app's ``S4 top ... route=<path>`` log line. Results print as ``PASS`` or
``FAIL`` lines; screenshots go to ``$S4_OUT`` (default ``./out``). The serial
comes from ``$S4_SERIAL`` (default ``emulator-5580``).
"""

import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ADB = str(Path.home() / "Library/Android/sdk/platform-tools/adb")
SERIAL = os.environ.get("S4_SERIAL", "emulator-5580")
OUT = Path(os.environ.get("S4_OUT", "out"))
PKG = "io.github.ndonkohenri.pyconus.s4"
RESULTS = {"PASS": 0, "FAIL": 0}
_seen = [0.0]  # epoch of the newest log line already read


def adb(*args: str, check: bool = True) -> str:
    """Run one adb command against SERIAL and return its stdout."""
    done = subprocess.run(
        [ADB, "-s", SERIAL, *args], capture_output=True, text=True, check=check
    )
    return done.stdout


def lines_since(since: float) -> list[tuple[float, str]]:
    """The app's ``S4`` log lines newer than since (device epoch seconds)."""
    out = adb("logcat", "-d", "-v", "epoch", "-s", "flet.python:I")
    found = []
    for raw in out.splitlines():
        match = re.match(r"\s*(\d+\.\d+)\s.*?(S4 .*)$", raw)
        if match and float(match[1]) > since:
            found.append((float(match[1]), match[2]))
    return found


def mark() -> float:
    """Remember the newest log line now, so waits only see what follows."""
    newest = lines_since(_seen[0])
    if newest:
        _seen[0] = newest[-1][0]
    return _seen[0]


def wait(pattern: str, since: float, timeout: float = 8.0) -> str | None:
    """Wait for an ``S4`` line matching pattern after since; return it or None."""
    end = time.time() + timeout
    while time.time() < end:
        for _, text in lines_since(since):
            if re.search(pattern, text):
                return text
        time.sleep(0.3)
    return None


def check(name: str, ok: bool, detail: str = "") -> bool:
    """Record and print one result."""
    RESULTS["PASS" if ok else "FAIL"] += 1
    print(f"{'PASS' if ok else 'FAIL'} {name} {detail}".rstrip(), flush=True)
    return ok


def expect_route(name: str, since: float, route: str, timeout: float = 8.0) -> bool:
    """Check that the top View reached route (exact path, query ignored)."""
    line = wait(rf"S4 top .* route={re.escape(route)}(\?\S*)?(\s|$)", since, timeout)
    return check(name, line is not None, f"-> {route}")


def shot(name: str) -> None:
    """Save a screenshot as OUT/<name>.png."""
    OUT.mkdir(parents=True, exist_ok=True)
    png = subprocess.run(
        [ADB, "-s", SERIAL, "exec-out", "screencap", "-p"],
        capture_output=True,
        check=True,
    ).stdout
    (OUT / f"{name}.png").write_bytes(png)


def nodes() -> list[tuple[str, tuple[int, int], bool]]:
    """(label, centre, clickable) for every node of the accessibility tree."""
    adb("shell", "uiautomator", "dump", "/sdcard/s4.xml")
    tree = ET.fromstring(adb("exec-out", "cat", "/sdcard/s4.xml"))
    found = []
    for node in tree.iter("node"):
        label = node.get("content-desc") or node.get("text") or ""
        x1, y1, x2, y2 = map(int, re.findall(r"\d+", node.get("bounds", "")))
        found.append(
            (label, ((x1 + x2) // 2, (y1 + y2) // 2), node.get("clickable") == "true")
        )
    return found


def type_into_field(text: str) -> None:
    """Focus the first text field on screen and type text."""
    adb("shell", "uiautomator", "dump", "/sdcard/s4.xml")
    tree = ET.fromstring(adb("exec-out", "cat", "/sdcard/s4.xml"))
    field = next(
        n for n in tree.iter("node") if n.get("class") == "android.widget.EditText"
    )
    x1, y1, x2, y2 = map(int, re.findall(r"\d+", field.get("bounds", "")))
    adb("shell", "input", "tap", str((x1 + x2) // 2), str((y1 + y2) // 2))
    time.sleep(0.8)
    adb("shell", "input", "text", text)
    time.sleep(1)


def status_line() -> str:
    """The status line the page handlers update (StatusLine in the app)."""
    return next((label for label, _, _ in nodes() if label.startswith("Session ")), "")


def screen_text() -> str:
    """Every label on screen, one per line, without the status line (it ticks)."""
    return "\n".join(
        label for label, _, _ in nodes() if label and not label.startswith("Session ")
    )


def tap(label: str, x_at: int | None = None) -> float:
    """Tap the node labelled label (clickable ones first); return a mark."""
    found = [(c, xy) for text, xy, c in nodes() if text.startswith(label)]
    for _, (x, y) in sorted(found, key=lambda item: not item[0]):  # clickable first
        since = mark()
        adb("shell", "input", "tap", str(x_at or x), str(y))
        return since
    raise LookupError(f"nothing clickable labelled {label!r}")


def key(code: str) -> float:
    """Press a key (BACK, HOME, ...) and return a mark taken before it."""
    since = mark()
    adb("shell", "input", "keyevent", f"KEYCODE_{code}")
    return since


def edge_swipe(name: str, *, cancel: bool = False, shot_at: int = 400) -> float:
    """A left-edge Back gesture with a screenshot mid-gesture; cancel returns home."""
    width = int(re.findall(r"\d+", adb("shell", "wm", "size"))[0])
    y = 1200
    since = mark()
    adb("shell", "input", "motionevent", "DOWN", "1", str(y))
    for x in range(40, shot_at + 1, 60):
        adb("shell", "input", "motionevent", "MOVE", str(x), str(y))
    time.sleep(0.4)
    shot(name)
    if cancel:
        for x in range(shot_at, 0, -80):
            adb("shell", "input", "motionevent", "MOVE", str(x), str(y))
    else:
        adb("shell", "input", "motionevent", "MOVE", str(width // 2), str(y))
    adb(
        "shell",
        "input",
        "motionevent",
        "UP",
        "1" if cancel else str(width // 2),
        str(y),
    )
    return since


def launch(*extra: str) -> float:
    """Start the app's activity (cold if it was stopped); return a mark."""
    since = mark()
    adb("shell", "am", "start", "-W", "-n", f"{PKG}/.MainActivity", *extra)
    return since


def cold_start(*extra: str) -> float:
    """Force-stop, then launch."""
    adb("shell", "am", "force-stop", PKG)
    time.sleep(1)
    return launch(*extra)


def resumed() -> bool:
    """Whether the app's activity is the resumed one."""
    out = adb("shell", "dumpsys", "activity", "activities")
    line = next(
        (
            x
            for x in out.splitlines()
            if "mResumedActivity" in x or "ResumedActivity:" in x
        ),
        "",
    )
    return PKG in line


def go(name: str, label: str, route: str) -> bool:
    """Tap label and expect route."""
    return expect_route(name, tap(label), route)


# ------------------------------------------------------------------ journeys
def journey_drill() -> None:
    """Now -> session -> speaker -> session -> room, system Back x4, Back on Now exits."""
    expect_route("drill: cold start on Now", cold_start(), "/now", 30)
    go("drill: session", "Keynote", "/now/session/42")
    go("drill: speaker", "Ada Lovelace", "/now/session/42/speaker/17")
    go(
        "drill: session again",
        "Typing in practice",
        "/now/session/42/speaker/17/session/99",
    )
    go(
        "drill: room",
        "Room 102A",
        "/now/session/42/speaker/17/session/99/room/room-102a",
    )
    shot("drill-room")
    text = screen_text()
    check("drill: room level sees its own params", "room 'room-102a'" in text)
    for route in (
        "/now/session/42/speaker/17/session/99",
        "/now/session/42/speaker/17",
        "/now/session/42",
        "/now",
    ):
        since = key("BACK")
        check(
            f"drill: Back pops through view-pop to {route}",
            wait(r"S4 view-pop", since) is not None,
        )
        expect_route(f"drill: Back -> {route}", since, route)
    shot("drill-back-on-now-before")
    key("BACK")
    time.sleep(1.5)
    shot("drill-back-on-now-after")
    check("drill: Back on Now leaves the app", not resumed())
    since = launch()
    time.sleep(2)
    check(
        "drill: relaunch after Back on Now starts a new session (F26)",
        wait(r"S4 main s=2", since, 5) is not None,
    )
    old_tick = wait(r"S4 tick .*own=1 ", since + 1, 20)
    check("drill: the old session's effect stopped", old_tick is None, old_tick or "")


def journey_roots() -> None:
    """D-17: Back on a non-Now root goes to Now (can_pop=False + on_confirm_pop)."""
    expect_route("roots: start", cold_start(), "/now", 30)
    for tab, root in (
        ("Schedule", "/schedule"),
        ("My schedule", "/my-schedule"),
        ("Map", "/map"),
        ("More", "/more"),
    ):
        go(f"roots: tab {tab}", tab, root)
        since = key("BACK")
        check(
            f"roots: Back on {root} asks confirm-pop",
            wait(rf"S4 confirm-pop .*view={root}\b", since) is not None,
        )
        expect_route(f"roots: Back on {root} -> /now", since, "/now")
    go("roots: tab More", "More", "/more")
    go("roots: More page", "Speakers", "/more/speakers")
    go("roots: speaker", "Ada Lovelace", "/more/speakers/speaker/17")
    expect_route("roots: Back -> Speakers", key("BACK"), "/more/speakers")
    expect_route("roots: Back -> More", key("BACK"), "/more")
    expect_route("roots: Back on More -> Now", key("BACK"), "/now")


def journey_retap() -> None:
    """Tab switches from a pushed View, and re-tapping the active tab."""
    expect_route("retap: start", cold_start(), "/now", 30)
    go("retap: tab Map", "Map", "/map")
    go("retap: room", "Hall A", "/map/room/hall-a")
    go("retap: session", "Keynote", "/map/room/hall-a/session/42")
    shot("retap-pushed-with-bar")
    since = tap("Map")
    check(
        "retap: on_change fires for the active tab",
        wait(r"S4 tab .*retap=True", since) is not None,
    )
    expect_route("retap: re-tap on a pushed View -> root", since, "/map")
    since = tap("Map")
    check(
        "retap: re-tap on the root fires too",
        wait(r"S4 tab .*retap=True", since, 3) is not None,
    )
    go("retap: switch from a pushed View", "Hall A", "/map/room/hall-a")
    go("retap: other tab", "Schedule", "/schedule")
    go("retap: back to Map shows its root", "Map", "/map")


def journey_search() -> None:
    """D-19: search over a pushed View; a result, a detail, Back to the results."""
    expect_route("search: start", cold_start(), "/now", 30)
    go("search: tab Schedule", "Schedule", "/schedule")
    go("search: a row", "Day 1 talk 03", "/schedule/session/d1-03")
    go("search: open", "Search", "/search")
    type_into_field("keynote")
    adb("shell", "input", "keyevent", "KEYCODE_ESCAPE")
    go("search: result", "Keynote", "/search/session/42")
    go("search: detail of a result", "Ada Lovelace", "/search/session/42/speaker/17")
    shot("search-detail")
    since = key("BACK")
    check(
        "search: Back from a detail goes through our view-pop",
        wait(
            r"S4 view-pop .*route=/search/session/42/speaker/17 to=/search/session/42",
            since,
        )
        is not None,
    )
    expect_route("search: Back -> result", since, "/search/session/42")
    since = key("BACK")
    expect_route("search: Back -> results", since, "/search")
    check(
        "search: query kept",
        wait(r"S4 search-render .*query='keynote'", since) is not None,
    )
    shot("search-results-after-back")
    keyboard = "mInputShown=true" in adb("shell", "dumpsys", "input_method")
    check("search: the field took focus back (keyboard up)", keyboard)
    if keyboard:  # the first Back only hides the keyboard
        since = key("BACK")
        check("search: Back hides the keyboard", wait(r"S4 view-pop", since, 2) is None)
    expect_route("search: Back -> opener", key("BACK"), "/schedule/session/d1-03")
    expect_route("search: Back -> Schedule", key("BACK"), "/schedule")
    expect_route("search: Back -> Now", key("BACK"), "/now")


def journey_predictive() -> None:
    """Predictive Back: an edge swipe on a detail, cancelled and committed; on roots."""
    if int(adb("shell", "getprop", "ro.build.version.sdk").strip()) < 35:
        adb("shell", "settings", "put", "global", "enable_back_animation", "1")  # 14
    expect_route("predictive: start", cold_start(), "/now", 30)
    go("predictive: session", "Keynote", "/now/session/42")
    since = edge_swipe("predictive-detail-cancel", cancel=True)
    time.sleep(1.5)
    check(
        "predictive: cancelled swipe stays",
        wait(r"S4 (view-pop|top)", since, 2) is None,
    )
    since = edge_swipe("predictive-detail-mid")
    expect_route("predictive: committed swipe pops", since, "/now")
    go("predictive: tab Schedule", "Schedule", "/schedule")
    since = edge_swipe("predictive-schedule-root-mid")
    check(
        "predictive: swipe on a non-Now root asks confirm-pop",
        wait(r"S4 confirm-pop", since) is not None,
    )
    expect_route("predictive: ... and lands on Now", since, "/now")
    edge_swipe("predictive-now-root-mid")
    time.sleep(1.5)
    check("predictive: swipe on Now leaves the app", not resumed())
    launch()


def journey_memory() -> None:
    """D-18: the Schedule day and offset survive a tab switch; a pushed View keeps scroll."""
    expect_route("memory: start", cold_start(), "/now", 30)
    go("memory: tab Schedule", "Schedule", "/schedule")
    tap("Day 2")
    time.sleep(1)
    adb("shell", "input", "swipe", "540", "1800", "540", "700", "600")
    time.sleep(1.5)
    shot("memory-day2-scrolled")
    before = screen_text()
    since = tap("Day 2 talk")
    pushed = wait(r"S4 top .*route=/schedule/session/d2-\d+", since)
    check("memory: push a row", pushed is not None, pushed or "")
    since = key("BACK")
    expect_route("memory: Back to Schedule", since, "/schedule")
    time.sleep(1)
    check(
        "memory: the list kept its scroll under the pushed View",
        screen_text() == before,
    )
    go("memory: tab Now", "Now", "/now")
    since = tap("Schedule")
    restored = wait(r"S4 schedule-restore .*day=2 offset=(\d+)", since)
    check(
        "memory: day 2 and its offset restored after a tab switch",
        bool(re.search(r"offset=[1-9]", restored or "")),
        restored or "",
    )
    time.sleep(1)
    shot("memory-after-tab-switch")
    check("memory: same rows on screen after the remount", screen_text() == before)


def journey_lifecycle() -> None:
    """Page handlers without page.update(): Home and resume, dark mode, no recreation."""
    expect_route("lifecycle: start", cold_start(), "/now", 30)
    go("lifecycle: session", "Keynote", "/now/session/42")
    since = key("HOME")
    check(
        "lifecycle: Home reports hide/pause",
        wait(r"S4 lifecycle .*state=(hide|pause)", since) is not None,
    )
    time.sleep(1)
    since = launch()
    check(
        "lifecycle: relaunch reports resume",
        wait(r"S4 lifecycle .*state=resume", since) is not None,
    )
    check("lifecycle: same session after resume", wait(r"S4 main", since, 2) is None)
    time.sleep(1)
    check("lifecycle: status line re-rendered", "lifecycle resume" in status_line())
    since = mark()
    adb("shell", "cmd", "uimode", "night", "yes")
    check(
        "lifecycle: dark mode reported",
        wait(r"S4 brightness .*dark=True", since) is not None,
    )
    time.sleep(1.5)
    check("lifecycle: status line says dark", "· dark (" in status_line())
    shot("lifecycle-dark")
    adb("shell", "cmd", "uimode", "night", "no")
    check(
        "lifecycle: dark mode did not recreate the activity",
        wait(r"S4 main", since, 3) is None,
    )
    since = mark()
    adb("shell", "settings", "put", "system", "font_scale", "1.3")
    time.sleep(3)
    shot("lifecycle-font-1.3")
    adb("shell", "settings", "put", "system", "font_scale", "1.0")
    check(
        "lifecycle: font scale did not recreate the activity",
        wait(r"S4 main", since, 3) is None,
    )
    since = mark()
    adb("shell", "settings", "put", "system", "accelerometer_rotation", "0")
    adb("shell", "settings", "put", "system", "user_rotation", "1")
    time.sleep(3)
    shot("lifecycle-landscape")
    adb("shell", "settings", "put", "system", "user_rotation", "0")
    check(
        "lifecycle: rotation did not recreate the activity",
        wait(r"S4 main", since, 3) is None,
    )
    expect_route("lifecycle: still on the session", key("BACK"), "/now")


def journey_deep() -> None:
    """Deep entry: the route extra (flet debug --route) and a deep link."""
    deep = "/map/room/hall-a/session/42/speaker/23"
    since = cold_start("--es", "route", deep)
    expect_route("deep: route extra opens the stack", since, deep, 30)
    shot("deep-entry")
    for route in ("/map/room/hall-a/session/42", "/map/room/hall-a", "/map", "/now"):
        expect_route(f"deep: Back -> {route}", key("BACK"), route)
    since = mark()
    adb(
        "shell",
        "am",
        "start",
        "-W",
        "-a",
        "android.intent.action.VIEW",
        "-d",
        "s4spike://s4/schedule/session/poster%20detail%2B1/speaker/%C3%A7~31",
    )
    expect_route(
        "deep: a link while running",
        since,
        "/schedule/session/poster%20detail%2B1/speaker/%C3%A7~31",
    )
    check("deep: the quoted ids reach the level", "speaker 'ç~31'" in screen_text())
    shot("deep-link-quoted")
    expect_route(
        "deep: Back -> session", key("BACK"), "/schedule/session/poster%20detail%2B1"
    )
    since = cold_start("--es", "route", "/schedule/session/nope")
    expect_route("deep: unknown id lands on its parent", since, "/schedule", 30)
    time.sleep(0.5)
    shot("deep-unknown-id")
    check("deep: with a SnackBar", "isn't in the schedule" in screen_text())


def switch_nav_mode() -> str:
    """Swap gesture and 3-button navigation, which recreates the activity (S1)."""
    overlays = adb("shell", "cmd", "overlay", "list")
    gestural = "[x] com.android.internal.systemui.navbar.gestural" in overlays
    mode = "threebutton" if gestural else "gestural"
    category = f"com.android.internal.systemui.navbar.{mode}"
    adb("shell", "cmd", "overlay", "enable-exclusive", "--category", category)
    return mode


def recreate_once(label: str, own: int, lands: str) -> None:
    """Recreate the activity on a drill View; check the new session and the old one."""
    go(f"{label}: session", "Keynote", "/now/session/42")
    go(f"{label}: speaker", "Ada Lovelace", "/now/session/42/speaker/17")
    since = mark()
    mode = switch_nav_mode()
    main = wait(r"S4 main", since, 15)
    check(
        f"{label}: a new session starts in the same process",
        main is not None,
        main or "",
    )
    landed = wait(rf"S4 top s={own + 1} .*route={re.escape(lands)}(\s|$)", since, 15)
    check(
        f"{label}: the new session lands on {lands}", landed is not None, landed or ""
    )
    time.sleep(1)
    shot(f"recreate-{label}-{mode}")
    end = wait(rf"S4 tick-end .*own={own} ", since, 20)
    check(f"{label}: how the old session's effect ended", end is not None, end or "")
    switch_nav_mode()
    time.sleep(4)


def journey_recreate() -> None:
    """F26: an activity recreation starts a new session in the same process."""
    expect_route("recreate: start", cold_start(), "/now", 30)
    recreate_once("default", 1, "/now")
    # The interim: ViewMemory per process (Start restores the last location) and
    # page.on_close stopping long-running effects. Knobs are read by main(), so
    # leave from Now and relaunch to start a session that uses them.
    expect_route("recreate: start again", cold_start(), "/now", 30)
    go("recreate: tab More", "More", "/more")
    for knob in ("ViewMemory per process", "Stop effects on close"):
        since = tap(knob, x_at=80)  # the switch itself
        check(f"recreate: knob {knob}", wait(r"S4 knob ", since) is not None)
        time.sleep(1)
    time.sleep(0.5)
    expect_route("recreate: Back on More -> Now", key("BACK"), "/now")
    key("BACK")
    time.sleep(2)
    since = launch()
    check("recreate: relaunch is session 2", wait(r"S4 main s=2", since) is not None)
    recreate_once("interim", 2, "/now/session/42/speaker/17")
    expect_route("recreate: Back after the restore", key("BACK"), "/now/session/42")


JOURNEYS = {
    name[8:]: fn for name, fn in globals().items() if name.startswith("journey_")
}

if __name__ == "__main__":
    if sys.argv[1:2] == ["do"]:  # a helper: run one adb shell command
        print(adb("shell", *sys.argv[2:], check=False), end="")
        sys.exit()
    if sys.argv[1:2] == ["install"]:
        print(adb("install", "-r", sys.argv[2]), end="")
        sys.exit()
    if sys.argv[1:2] == ["shot"]:
        shot(sys.argv[2])
        sys.exit()
    for name in sys.argv[1:] or list(JOURNEYS):
        print(f"== {name}", flush=True)
        try:
            JOURNEYS[name]()
        except (LookupError, ValueError, subprocess.CalledProcessError) as error:
            check(f"{name}: aborted", False, repr(error))
    print(f"== {RESULTS['PASS']} passed, {RESULTS['FAIL']} failed", flush=True)
