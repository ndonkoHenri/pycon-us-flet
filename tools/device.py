"""Boot an emulator or a simulator of your own, set its text and contrast, shut it down.

Usage, from the repo's root:

    uv run python -m tools.device up android --port 5594 [--avd NAME] [--no-animations]
    uv run python -m tools.device up ios --name Claude-123-iPhone-17 [--model "iPhone 17"]
    uv run python -m tools.device prefs <device> --text 200 --bold --contrast --dark
    uv run python -m tools.device prefs <device> --reset
    uv run python -m tools.device down <device> [--delete]
    uv run python -m tools.device list

`<device>` is an emulator's serial, a simulator's udid or its name. `up` prints only the
serial or the udid, so a script can keep it (`docs/development.md` §5.5, D-102). A device
a maintainer keeps is refused everywhere: flows and installs replace the app's data.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

OWNERS_SERIAL = "emulator-5554"
OWNERS_AVD = "pycon_lowram_api34"
OWNERS_SIMULATOR = "iPhone 16"
DEFAULT_AVD = "pycon_pixel6a_api36"
DEFAULT_MODEL = "iPhone 17"
DEFAULT_RUNTIME = "com.apple.CoreSimulator.SimRuntime.iOS-26-5"

BOOT_SECONDS = 240
"""How long a boot may take. A cold boot on a busy host has taken minutes (D-102)."""

EMULATORS_BEFORE_WARNING = 2
"""How many emulators may already run before `up` warns: memory is this Mac's limit, and
with three up, Android's system server has died under its watchdog (§5.5)."""

IOS_TEXT = {
    "100": "large",
    "200": "accessibility-large",
    "max": "accessibility-extra-extra-extra-large",
}
"""`simctl ui content_size` for each text size; `large` is iOS's default."""

ANDROID_TEXT = {"100": "1.0", "200": "2.0", "max": "2.0"}
"""`font_scale` for each text size: Android's largest is 200 %."""

BOLD_WEIGHT = "300"
"""`font_weight_adjustment` that Android's Bold text switch sets."""


def is_emulator(device: str) -> bool:
    """Return whether `device` is an emulator's serial rather than a simulator's."""
    return re.fullmatch(r"emulator-\d+", device) is not None


def refuse_owners(device: str) -> None:
    """Exit if `device` is an emulator or a simulator a maintainer keeps."""
    if device in (OWNERS_SERIAL, OWNERS_SIMULATOR):
        sys.exit(f"device.py: {device} is a maintainer's: use a device of your own")


def android_prefs(
    serial: str, text: str | None, bold: bool, contrast: bool, dark: bool, reset: bool
) -> list[list[str]]:
    """Return the `adb` commands that set an emulator's text, contrast and appearance.

    Args:
        serial: The emulator.
        text: A key of `ANDROID_TEXT`, or None to leave the size.
        bold: Turn Bold text on.
        contrast: Turn Color contrast to high (F84; Android 14 and later).
        dark: Turn the dark theme on.
        reset: Return all four to their defaults; the others are ignored.
    """
    shell = ["adb", "-s", serial, "shell"]
    if reset:
        text, weight, level, night = "100", "0", "0", "no"
    else:
        weight = BOLD_WEIGHT if bold else None
        level = "1" if contrast else None
        night = "yes" if dark else None
    commands = []
    if text:
        commands.append(
            [*shell, "settings", "put", "system", "font_scale", ANDROID_TEXT[text]]
        )
    if weight:
        commands.append(
            [*shell, "settings", "put", "secure", "font_weight_adjustment", weight]
        )
    if level:
        commands.append([*shell, "settings", "put", "secure", "contrast_level", level])
    if night:
        commands.append([*shell, "cmd", "uimode", "night", night])
    return commands


def ios_prefs(
    udid: str, text: str | None, bold: bool, contrast: bool, dark: bool, reset: bool
) -> list[list[str]]:
    """Return the `simctl` commands that set a simulator's text, contrast and appearance.

    Bold Text is read at launch, so relaunch the app after it.

    Args:
        udid: The simulator.
        text: A key of `IOS_TEXT`, or None to leave the size.
        bold: Turn Bold Text on.
        contrast: Turn Increase Contrast on.
        dark: Turn the dark appearance on.
        reset: Return all four to their defaults; the others are ignored.
    """
    ui = ["xcrun", "simctl", "ui", udid]
    if reset:
        text, legible, increase, appearance = "100", "false", "disabled", "light"
    else:
        legible = "true" if bold else None
        increase = "enabled" if contrast else None
        appearance = "dark" if dark else None
    commands = []
    if text:
        commands.append([*ui, "content_size", IOS_TEXT[text]])
    if legible:
        commands.append(
            [
                *["xcrun", "simctl", "spawn", udid, "defaults", "write"],
                *["com.apple.Accessibility", "EnhancedTextLegibilityEnabled"],
                *["-bool", legible],
            ]
        )
    if increase:
        commands.append([*ui, "increase_contrast", increase])
    if appearance:
        commands.append([*ui, "appearance", appearance])
    return commands


def emulator_command(avd: str, port: int) -> list[str]:
    """Return the line that boots `avd` on `port`, leaving the AVD's disk as it was.

    `-read-only` lets several emulators share one AVD, and `-no-snapshot` makes every
    boot the same (`docs/testing-and-quality.md` §8).
    """
    sdk = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
    root = Path(sdk) if sdk else Path.home() / "Library" / "Android" / "sdk"
    return [
        str(root / "emulator" / "emulator"),
        *["-avd", avd, "-port", str(port)],
        *["-read-only", "-no-audio", "-no-boot-anim", "-no-snapshot"],
    ]


def serial_setup(serial: str, animations: bool) -> list[list[str]]:
    """Return the `adb` commands that ready a booted emulator for flows.

    The on-screen keyboard stays down (D-223); without animations is how `flet test` flows
    run (`docs/testing-and-quality.md` §5.2), not how a recording or a measurement should.
    """
    shell = ["adb", "-s", serial, "shell", "settings", "put"]
    commands = [[*shell, "secure", "show_ime_with_hard_keyboard", "0"]]
    if not animations:
        commands.extend(
            [*shell, "global", scale, "0"]
            for scale in (
                "window_animation_scale",
                "transition_animation_scale",
                "animator_duration_scale",
            )
        )
    return commands


def _output(command: list[str]) -> str:
    """Run `command` and return its output, or an empty string if it fails."""
    done = subprocess.run(command, check=False, capture_output=True, text=True)
    return done.stdout.strip() if done.returncode == 0 else ""


def _run_all(commands: list[list[str]]) -> None:
    """Run `commands` in order, stopping at the first failure."""
    for command in commands:
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL)


def _running_emulators() -> list[str]:
    """Return the serials of the emulators `adb` can see."""
    return re.findall(r"^(emulator-\d+)\s", _output(["adb", "devices"]), re.MULTILINE)


def up_android(avd: str, port: int, animations: bool) -> str:
    """Boot an emulator of your own and return its serial; one already there is reused."""
    serial = f"emulator-{port}"
    refuse_owners(serial)
    if avd == OWNERS_AVD:
        sys.exit(f"device.py: {avd} is a maintainer's: use another AVD")
    running = _running_emulators()
    if serial not in running:
        if len(running) > EMULATORS_BEFORE_WARNING:
            print(
                f"device.py: {len(running)} emulators are running; memory is this "
                "Mac's limit (development.md §5.5)",
                file=sys.stderr,
            )
        log = Path("build/device") / f"{serial}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("w") as out:
            # Its own session, so it outlives this command.
            subprocess.Popen(
                emulator_command(avd, port),
                stdout=out,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        deadline = time.monotonic() + BOOT_SECONDS
        getprop = ["adb", "-s", serial, "shell", "getprop", "sys.boot_completed"]
        while _output(getprop) != "1":
            if time.monotonic() > deadline:
                sys.exit(f"device.py: {serial} didn't boot in time; see {log}")
            time.sleep(3)
    _run_all(serial_setup(serial, animations))
    return serial


def _simulators() -> list[dict[str, str]]:
    """Return every available simulator, as `simctl` lists it."""
    listed = json.loads(
        _output(["xcrun", "simctl", "list", "devices", "available", "-j"]) or "{}"
    )
    return [sim for sims in listed.get("devices", {}).values() for sim in sims]


def udid_of(name: str) -> str | None:
    """Return the udid of the simulator called `name`, or of the udid itself, else None."""
    for sim in _simulators():
        if name in (sim["name"], sim["udid"]):
            refuse_owners(sim["name"])
            return sim["udid"]
    return None


def up_ios(name: str, model: str, runtime: str) -> str:
    """Boot a simulator of your own, creating it if needed, and return its udid."""
    refuse_owners(name)
    udid = udid_of(name) or _output(["xcrun", "simctl", "create", name, model, runtime])
    if not udid:
        sys.exit(f"device.py: couldn't create {model} on {runtime}")
    # -b boots it if it isn't booted, and waits until it has.
    subprocess.run(
        ["xcrun", "simctl", "bootstatus", udid, "-b"],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    return udid


def down(device: str, delete: bool) -> None:
    """Shut `device` down; a simulator can also be deleted."""
    refuse_owners(device)
    if is_emulator(device):
        subprocess.run(["adb", "-s", device, "emu", "kill"], check=True)
        return
    udid = _resolved(device)
    subprocess.run(["xcrun", "simctl", "shutdown", udid], check=False)
    if delete:
        subprocess.run(["xcrun", "simctl", "delete", udid], check=True)


def _resolved(device: str) -> str:
    """Return the udid of a simulator named by name or udid, or exit if there is none."""
    udid = udid_of(device)
    if udid is None:
        sys.exit(f"device.py: no simulator called {device}")
    return udid


def _parser() -> argparse.ArgumentParser:
    """Return the command line's parser."""
    parser = argparse.ArgumentParser(prog="tools.device", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    up = commands.add_parser("up", help="boot a device of your own; prints its id")
    platforms = up.add_subparsers(dest="platform", required=True)
    android = platforms.add_parser("android")
    android.add_argument("--port", type=int, required=True, help="even; never 5554")
    android.add_argument("--avd", default=DEFAULT_AVD)
    android.add_argument(
        "--no-animations",
        action="store_true",
        help="for flet test flows; not for a recording or a measurement",
    )
    ios = platforms.add_parser("ios")
    ios.add_argument("--name", required=True, help="made if it doesn't exist")
    ios.add_argument("--model", default=DEFAULT_MODEL)
    ios.add_argument("--runtime", default=DEFAULT_RUNTIME)
    prefs = commands.add_parser("prefs", help="set text, contrast and appearance")
    prefs.add_argument("device")
    prefs.add_argument("--text", choices=sorted(IOS_TEXT))
    prefs.add_argument("--bold", action="store_true")
    prefs.add_argument("--contrast", action="store_true")
    prefs.add_argument("--dark", action="store_true")
    prefs.add_argument("--reset", action="store_true", help="back to the defaults")
    stop = commands.add_parser("down", help="shut a device down")
    stop.add_argument("device")
    stop.add_argument("--delete", action="store_true", help="simulators only")
    commands.add_parser("list", help="the emulators and simulators that are up")
    return parser


def main(argv: list[str] | None = None) -> None:
    """Run the command line."""
    args = _parser().parse_args(argv)
    if args.command == "up":
        if args.platform == "android":
            print(up_android(args.avd, args.port, not args.no_animations))
        else:
            print(up_ios(args.name, args.model, args.runtime))
    elif args.command == "prefs":
        refuse_owners(args.device)
        chosen = (args.text, args.bold, args.contrast, args.dark, args.reset)
        if is_emulator(args.device):
            _run_all(android_prefs(args.device, *chosen))
        else:
            _run_all(ios_prefs(_resolved(args.device), *chosen))
    elif args.command == "down":
        down(args.device, args.delete)
    else:
        for serial in _running_emulators():
            print(serial)
        for sim in _simulators():
            if sim["state"] == "Booted":
                print(sim["udid"], sim["name"])


if __name__ == "__main__":
    main()
