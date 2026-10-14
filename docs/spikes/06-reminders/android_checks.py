"""The S6 checks on an Android emulator: schedule, disturb, time each reminder.

Each check schedules through one of the app's start routes, then runs device
steps from ``drive_android.py`` (swipe, lock, reboot, Doze, permissions) and
waits for the reminder. Run from this folder with the release APK installed::

    uv run python android_checks.py [<check> ...]
    uv run python android_checks.py scenario <name> <route> <id> [<step> ...]

With no check named, all of them run in order (``CHECKS``). The steps import
nothing from here, so the two modules import one way only.
"""

import re
import sys
import time

from drive_android import (
    adb,
    app_lines,
    device_now,
    running,
    say,
    shot,
    step,
    tap,
    wait_for,
)


def schedule(route: str, rid: int) -> tuple[float | None, str]:
    """Start the app on a scheduling route; return (due, error) from its log.

    A running activity would take the route as a new intent and ignore it, so
    the app is swiped away first (never force-stopped: that clears alarms).
    """
    if running():
        step("swipe")
    adb("logcat", "-c")
    step("launch", route)
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
    for command in then:
        step(*command.split())
    if due is not None and error == "None":
        wait_for(rid, due, timeout)


def lock_screen_shot() -> None:
    """Wake the screen on the keyguard and keep a screenshot of it."""
    step("wake")
    time.sleep(2)
    shot("android-light-lock-screen")
    step("unlock")


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
    step("launch")
    time.sleep(10)
    print("\n".join(app_lines()[-2:]))
    step("alarms")


def check_long_leads() -> None:
    """Inexact reminders 10 and 30 min ahead, screen off, on mains power."""
    due_10, _ = schedule("/schedule/600/inexact/61", 61)
    due_30, _ = schedule("/schedule/1800/inexact/62", 62)
    step("swipe")
    step("alarms")
    step("lock")
    if due_10 is not None and due_30 is not None:
        wait_for(61, due_10, 1200)
        wait_for(62, due_30, 2700)
    step("unlock")


def check_moved_and_warm_tap() -> None:
    """Reminder 7 moved from +2 to +4 min; the app stays in the background."""
    adb("logcat", "-c")
    if running():
        step("swipe")
    step("launch", "/move")
    time.sleep(10)
    print("\n".join(app_lines()))
    adb("shell", "input", "keyevent", "KEYCODE_HOME")
    first = [line for line in app_lines() if "id=7 due=" in line]
    dues = [float(re.search(r"due=([\d.]+)", line)[1]) for line in first]
    if len(dues) == 2:
        wait_for(7, dues[1], 420)
        say("moved", first_due_passed_by_s=f"{device_now() - dues[0]:.0f}")
    step("shade")
    shot("android-light-moved-shade")
    adb("logcat", "-c")
    tap("Reminder 7")
    time.sleep(4)
    print("\n".join(app_lines()))


def check_many() -> None:
    """70 reminders planned at once: what Android keeps."""
    adb("logcat", "-c")
    if running():
        step("swipe")
    step("launch", "/many/70/600")
    time.sleep(25)
    print("\n".join(line for line in app_lines() if "status" in line))
    step("alarms")
    step("tap", "Cancel all")
    time.sleep(2)


def check_keep_shown() -> None:
    """D-222: cancel_all_pending() leaves a shown reminder in the shade."""
    adb("logcat", "-c")
    if running():
        step("swipe")
    step("exact", "allow")
    step("launch", "/keep-shown/60/exact")
    end = time.time() + 240
    while time.time() < end and not any("cancelled-pending" in x for x in app_lines()):
        time.sleep(3)
    print("\n".join(app_lines()))
    step("exact", "deny")
    step("shade")
    shot("android-light-kept-shade")


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
        step("exact", "deny"),
        scenario("exact, denied", "/schedule/120/exact/45", 45, then=["swipe"]),
    ),
    "exact-allowed": lambda: (
        step("exact", "allow"),
        scenario("exact, allowed", "/schedule/120/exact/46", 46, then=["swipe"]),
        step("exact", "deny"),
    ),
    "doze-inexact": lambda: (
        scenario(
            "doze, inexact",
            "/schedule/120/inexact/47",
            47,
            then=["swipe", "doze"],
            timeout=1500,
        ),
        step("undoze"),
        step("unlock"),
    ),
    "doze-exact": lambda: (
        step("exact", "allow"),
        scenario(
            "doze, exact",
            "/schedule/120/exact/48",
            48,
            then=["swipe", "doze"],
            timeout=900,
        ),
        step("undoze"),
        step("unlock"),
        step("exact", "deny"),
    ),
    "notif-denied": lambda: (
        scenario(
            "notifications denied",
            "/schedule/120/inexact/50",
            50,
            then=["notif deny"],
            timeout=270,
        ),
        step("notif", "allow"),
    ),
    "force-stop": check_force_stop,
    "long": check_long_leads,
    "moved": check_moved_and_warm_tap,
    "many": check_many,
    "keep-shown": check_keep_shown,
}


def suite(*names: str) -> None:
    """Run the named checks (all of them, in order, by default)."""
    for name in names or CHECKS:
        say("check", name=name)
        CHECKS[name]()


def main(*args: str) -> None:
    """Run one scenario, or the named checks (all of them by default)."""
    if args and args[0] == "scenario":
        scenario(args[1], args[2], int(args[3]), then=list(args[4:]))
    else:
        unknown = [name for name in args if name not in CHECKS]
        if unknown:
            raise SystemExit(f"unknown checks {unknown}; known: {list(CHECKS)}")
        suite(*args)


if __name__ == "__main__":
    main(*sys.argv[1:])
