"""Drive the S6 reproducer on an Android emulator with adb and time each reminder.

Run from this folder with the release APK installed::

    uv run python drive_android.py <step> [<arg> ...]

Steps (each prints ``S6-DRIVE`` lines; screenshots go to ``$S6_OUT``):

- ``launch [route]``: start the app (cold if it isn't running) on route.
- ``swipe``: Home, then swipe the app away in Recents (the process dies, the
  package is not stopped). ``force-stop``: Settings' Force stop.
- ``lock`` / ``unlock``: the power key, then wake and swipe up.
- ``reboot``: reboot the emulator and wait for boot.
- ``exact allow|deny`` and ``notif allow|deny``: the two permissions.
- ``doze`` / ``undoze``: force deep idle (screen off, unplugged) and leave it.
- ``wait <id> <due epoch> [timeout s]``: poll the notification list until
  reminder ``id`` is posted; print the delay after ``due``.
- ``alarms``: the app's alarms in ``dumpsys alarm`` (when and window).
- ``shade`` / ``tap <text>``: open the notification shade; tap a node.
- ``shot <name>``: a screenshot.
- ``log``: the app's ``S6`` lines.
"""

import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ADB = str(Path.home() / "Library/Android/sdk/platform-tools/adb")
SERIAL = os.environ.get("S6_SERIAL", "emulator-5584")
OUT = Path(os.environ.get("S6_OUT", "out"))
PKG = "io.github.ndonkohenri.pyconus.s6"


def adb(*args: str, check: bool = True) -> str:
    """Run one adb command against SERIAL and return its stdout."""
    done = subprocess.run(
        [ADB, "-s", SERIAL, *args], capture_output=True, text=True, check=check
    )
    return done.stdout


def say(event: str, **values: object) -> None:
    """Print one driver line with the host's wall clock."""
    fields = " ".join(f"{key}={value}" for key, value in values.items())
    print(f"S6-DRIVE {event} host={time.time():.1f} {fields}".rstrip(), flush=True)


def device_now() -> float:
    """The emulator's clock, in epoch seconds."""
    return float(adb("shell", "date", "+%s.%N").strip()[:14])


def running() -> bool:
    """Whether the app has a process."""
    return bool(adb("shell", "pidof", PKG, check=False).strip())


def stopped() -> bool:
    """Whether the package is in the stopped state (after a force-stop)."""
    out = adb("shell", "dumpsys", "package", PKG)
    return "stopped=true" in out


def posted(rid: int) -> float | None:
    """When reminder rid was posted (its ``when``, epoch seconds), or None."""
    out = adb("shell", "dumpsys", "notification", "--noredact")
    match = re.search(
        rf"pkg={re.escape(PKG)} user=\S+ id={rid} .*?\n\s+when=(\d+)", out, re.DOTALL
    )
    return int(match[1]) / 1000 if match else None


def wait_for(rid: int, due: float, timeout: float) -> None:
    """Poll for reminder rid every 2 s; print its delay after due, or a miss.

    The delay is the notification's own ``when`` (set as the plugin posts it)
    minus due, so a late poll does not inflate it.
    """
    end = time.time() + timeout
    while time.time() < end:
        when = posted(rid)
        # A notification with this id from an earlier run is not this one.
        if when is not None and when >= due - 5:
            say("posted", id=rid, delay_s=f"{when - due:.1f}", running=running())
            return
        time.sleep(2)
    say(
        "missed",
        id=rid,
        waited_s=f"{timeout:.0f}",
        late_by_s=f"{device_now() - due:.1f}",
    )


def nodes() -> list[tuple[str, tuple[int, int]]]:
    """(label, centre) for every node of the accessibility tree."""
    adb("shell", "uiautomator", "dump", "/sdcard/s6.xml")
    tree = ET.fromstring(adb("exec-out", "cat", "/sdcard/s6.xml"))
    found = []
    for node in tree.iter("node"):
        label = node.get("content-desc") or node.get("text") or ""
        x1, y1, x2, y2 = map(int, re.findall(r"\d+", node.get("bounds", "")))
        found.append((label, ((x1 + x2) // 2, (y1 + y2) // 2)))
    return found


def tap(text: str) -> None:
    """Tap the first node whose label contains text."""
    for label, (x, y) in nodes():
        if text in label:
            adb("shell", "input", "tap", str(x), str(y))
            say("tapped", label=repr(label[:40]))
            return
    raise LookupError(f"nothing labelled {text!r}")


def shot(name: str) -> None:
    """Save a screenshot as OUT/<name>.png."""
    OUT.mkdir(parents=True, exist_ok=True)
    png = subprocess.run(
        [ADB, "-s", SERIAL, "exec-out", "screencap", "-p"],
        capture_output=True,
        check=True,
    ).stdout
    (OUT / f"{name}.png").write_bytes(png)
    say("shot", file=OUT / f"{name}.png")


def wait_boot() -> None:
    """Wait for the emulator to finish booting."""
    adb("wait-for-device")
    while adb("shell", "getprop", "sys.boot_completed", check=False).strip() != "1":
        time.sleep(2)


def app_lines() -> list[str]:
    """The app's ``S6`` log lines."""
    out = adb("logcat", "-d", "-s", "flet.python:I")
    return [line for line in out.splitlines() if " S6 " in line]


def schedule(route: str, rid: int) -> tuple[float | None, str]:
    """Start the app on a scheduling route; return (due, error) from its log.

    A running activity would take the route as a new intent and ignore it, so
    the app is swiped away first (never force-stopped: that clears alarms).
    """
    if running():
        main("swipe")
    adb("logcat", "-c")
    main("launch", route)
    end = time.time() + 30
    while time.time() < end:
        for line in app_lines():
            match = re.search(
                rf"S6 scheduled .* id={rid} due=([\d.]+) .*error=(\S+)", line
            )
            if match:
                return float(match[1]), match[2]
        time.sleep(1)
    return None, "no-log"


def scenario(
    name: str, route: str, rid: int, *, then: list[str], timeout: float = 300
) -> None:
    """Schedule rid on route, run the steps in then, and wait for the reminder."""
    say("scenario", name=name, route=route)
    due, error = schedule(route, rid)
    say("scheduled", name=name, id=rid, due=due, error=error)
    for step in then:
        main(*step.split())
    if due is not None and error == "None":
        wait_for(rid, due, timeout)


def lock_screen_shot() -> None:
    """Wake the screen on the keyguard and keep a screenshot of it."""
    main("wake")
    time.sleep(2)
    shot("android-light-lock-screen")
    main("unlock")


def check_force_stop() -> None:
    """A force-stop clears the alarms; the next start shows what the plugin thinks."""
    scenario(
        "force-stopped",
        "/schedule/120/inexact/49",
        49,
        then=["force-stop"],
        timeout=270,
    )
    adb("logcat", "-c")
    main("launch")
    time.sleep(10)
    print("\n".join(app_lines()[-2:]))
    main("alarms")


def check_long_leads() -> None:
    """Inexact reminders 10 and 30 min ahead, screen off, on mains power."""
    due_10, _ = schedule("/schedule/600/inexact/61", 61)
    due_30, _ = schedule("/schedule/1800/inexact/62", 62)
    main("swipe")
    main("alarms")
    main("lock")
    if due_10 is not None and due_30 is not None:
        wait_for(61, due_10, 1200)
        wait_for(62, due_30, 2700)
    main("unlock")


def check_moved_and_warm_tap() -> None:
    """Reminder 7 moved from +2 to +4 min; the app stays in the background."""
    adb("logcat", "-c")
    if running():
        main("swipe")
    main("launch", "/move")
    time.sleep(10)
    print("\n".join(app_lines()))
    adb("shell", "input", "keyevent", "KEYCODE_HOME")
    first = [line for line in app_lines() if "id=7 due=" in line]
    dues = [float(re.search(r"due=([\d.]+)", line)[1]) for line in first]
    if len(dues) == 2:
        wait_for(7, dues[1], 420)
        say("moved", first_due_passed_by_s=f"{device_now() - dues[0]:.0f}")
    main("shade")
    shot("android-light-moved-shade")
    adb("logcat", "-c")
    tap("Reminder 7")
    time.sleep(4)
    print("\n".join(app_lines()))


def check_many() -> None:
    """70 reminders planned at once: what Android keeps."""
    adb("logcat", "-c")
    if running():
        main("swipe")
    main("launch", "/many/70/600")
    time.sleep(25)
    print("\n".join(line for line in app_lines() if "status" in line))
    main("alarms")
    main("tap", "Cancel all")
    time.sleep(2)


CHECKS = {
    "swiped": lambda: scenario(
        "swiped away", "/schedule/120/inexact/42", 42, then=["swipe"]
    ),
    "locked": lambda: scenario(
        "screen locked", "/schedule/120/inexact/43", 43, then=["swipe", "lock"]
    ),
    "lockshot": lock_screen_shot,
    "reboot": lambda: scenario(
        "reboot", "/schedule/180/inexact/44", 44, then=["swipe", "reboot"]
    ),
    "exact-denied": lambda: (
        main("exact", "deny"),
        scenario("exact, denied", "/schedule/120/exact/45", 45, then=["swipe"]),
    ),
    "exact-allowed": lambda: (
        main("exact", "allow"),
        scenario("exact, allowed", "/schedule/120/exact/46", 46, then=["swipe"]),
        main("exact", "deny"),
    ),
    "doze-inexact": lambda: (
        scenario(
            "doze, inexact",
            "/schedule/120/inexact/47",
            47,
            then=["swipe", "doze"],
            timeout=1500,
        ),
        main("undoze"),
        main("unlock"),
    ),
    "doze-exact": lambda: (
        main("exact", "allow"),
        scenario(
            "doze, exact",
            "/schedule/120/exact/48",
            48,
            then=["swipe", "doze"],
            timeout=900,
        ),
        main("undoze"),
        main("unlock"),
        main("exact", "deny"),
    ),
    "notif-denied": lambda: (
        scenario(
            "notifications denied",
            "/schedule/120/inexact/50",
            50,
            then=["notif deny"],
            timeout=270,
        ),
        main("notif", "allow"),
    ),
    "force-stop": check_force_stop,
    "long": check_long_leads,
    "moved": check_moved_and_warm_tap,
    "many": check_many,
}


def suite(*names: str) -> None:
    """Run the named checks (all of them, in order, by default)."""
    for name in names or CHECKS:
        say("check", name=name)
        CHECKS[name]()


def main(step: str, *args: str) -> None:
    """Run one step."""
    if step == "suite":
        suite(*args)
    elif step == "scenario":
        scenario(args[0], args[1], int(args[2]), then=list(args[3:]))
    elif step == "launch":
        extra = ["--es", "route", args[0]] if args else []
        adb("shell", "am", "start", "-W", "-n", f"{PKG}/.MainActivity", *extra)
        say("launched", route=args[0] if args else "/")
    elif step == "swipe":
        # Recents can take a moment to settle, so try a few times.
        for _ in range(4):
            if not running():
                break
            adb("shell", "input", "keyevent", "KEYCODE_HOME")
            time.sleep(1.5)
            adb("shell", "input", "keyevent", "KEYCODE_APP_SWITCH")
            time.sleep(2.5)
            adb("shell", "input", "swipe", "540", "1300", "540", "150", "250")
            time.sleep(2.5)
        adb("shell", "input", "keyevent", "KEYCODE_HOME")
        say("swiped", running=running(), stopped=stopped())
    elif step == "force-stop":
        adb("shell", "am", "force-stop", PKG)
        say("force-stopped", running=running(), stopped=stopped())
    elif step == "lock":
        adb("shell", "input", "keyevent", "KEYCODE_SLEEP")
        say("locked")
    elif step == "unlock":
        adb("shell", "input", "keyevent", "KEYCODE_WAKEUP")
        time.sleep(1)
        adb("shell", "wm", "dismiss-keyguard")
        say("unlocked")
    elif step == "wake":
        adb("shell", "input", "keyevent", "KEYCODE_WAKEUP")
        say("woken")
    elif step == "reboot":
        adb("reboot")
        time.sleep(5)
        wait_boot()
        say("rebooted", running=running())
    elif step == "exact":
        mode = "allow" if args[0] == "allow" else "default"
        # "default" is Android 14's state for a fresh install: denied.
        adb("shell", "appops", "set", PKG, "SCHEDULE_EXACT_ALARM", mode)
        say("exact", mode=mode)
    elif step == "notif":
        action = "grant" if args[0] == "allow" else "revoke"
        adb("shell", "pm", action, PKG, "android.permission.POST_NOTIFICATIONS")
        say("notif", action=action)
    elif step == "doze":
        adb("shell", "dumpsys", "battery", "unplug")
        adb("shell", "input", "keyevent", "KEYCODE_SLEEP")
        time.sleep(1)
        state = adb("shell", "dumpsys", "deviceidle", "force-idle").strip()
        say("doze", state=repr(state))
    elif step == "undoze":
        adb("shell", "dumpsys", "deviceidle", "unforce")
        adb("shell", "dumpsys", "battery", "reset")
        say("undoze")
    elif step == "wait":
        wait_for(int(args[0]), float(args[1]), float(args[2]) if len(args) > 2 else 600)
    elif step == "alarms":
        out = adb("shell", "dumpsys", "alarm")
        blocks = re.findall(
            rf"RTC_WAKEUP #\d+: Alarm\{{[^}}]*{re.escape(PKG)}\}}(?:\n\s{{6}}.*)+", out
        )
        for block in blocks:
            print(block)
        say("alarms", count=len(blocks))
    elif step == "shade":
        adb("shell", "cmd", "statusbar", "expand-notifications")
        time.sleep(1.5)
        say("shade")
    elif step == "tap":
        tap(args[0])
    elif step == "shot":
        shot(args[0])
    elif step == "log":
        out = adb("logcat", "-d", "-s", "flet.python:I")
        print("\n".join(line for line in out.splitlines() if " S6 " in line))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(*sys.argv[1:])
