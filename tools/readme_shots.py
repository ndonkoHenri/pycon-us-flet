"""Photograph the README's screenshots on an emulator and a simulator of your own.

Usage, from the repo's root (uv fetches Pillow, which nothing else needs):

    uv run --with pillow python -m tools.readme_shots android emulator-5594
    uv run --with pillow python -m tools.readme_shots ios <udid>
        [--out docs/images] [--raw build/readme_shots]

The build on the device must hold this tree's Python (`docs/development.md` §5.8): a
release APK on Android, the simulator build on iOS. For each appearance (light, then dark),
the tool starts the app afresh on Friday 2026-05-15 11:04, a live moment, runs
`maestro/demo/readme_shots.yaml` and keeps its six screenshots: full size in `--raw`, and
shrunk (`SHOT_WIDTH` px wide, WebP) in `--out`, named `<platform>-<appearance>-<n>-<screen>.webp`.

Nothing of the developer's setup shows. The fake clock is written straight into the app's
stored preferences with no `unlocked` key, so More has no Developer row, and the system's
status bar is set to the fake clock's minute, a full battery and full bars while the flow runs.
Android is written as root, which a Google APIs emulator image allows (`adb root`); the Play
images don't. Look at every image before it is committed: the feed is public, but a stray
notification or a real badge is not.
"""

import argparse
import json
import os
import plistlib
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from pycon_us.dev_options import DEV_FAKE_NOW
from pycon_us.services.pref_keys import DEV, ONBOARDED, REMINDERS
from tools.demo_videos import BOOT_LAG

ROOT = Path(__file__).resolve().parents[1]
FLOW = ROOT / "maestro" / "demo" / "readme_shots.yaml"
BUNDLE = "io.github.ndonkohenri.confcompanion"
ACTIVITY = f"{BUNDLE}/.MainActivity"

CLOCK_START = datetime.fromisoformat("2026-05-15T11:04:00-07:00")
"""Friday, in the 11:00 slot: Now has sessions on, and the next slot at 11:30."""

APPEARANCES = ("light", "dark")
SHOT_WIDTH = 432
"""How wide the committed images are, in px: the README shows them about 150 px wide, and
a click opens them as they are."""

STATUS_BAR = (
    "--batteryState discharging --batteryLevel 100 --cellularBars 4 --wifiBars 3"
)
"""What an iOS status bar shows besides its time: full battery, not charging, full bars."""

WARM_UP_SECONDS = 25.0
"""A first launch stays up this long so the live feed and the logos are cached."""


def app_prefs() -> dict[str, Any]:
    """Return the stored preferences, as `SharedPreferences` keys, of a seen Welcome.

    The reminders primer is answered, the fake clock is set and nothing else is: with no
    `unlocked` key, there is no Developer row in More.
    """
    dev = {DEV_FAKE_NOW: CLOCK_START.isoformat()}
    return {
        f"flutter.{ONBOARDED.key}": True,
        f"flutter.{REMINDERS.key}": json.dumps({"primer": "not_now"}),
        f"flutter.{DEV.key}": json.dumps(dev),
    }


def shot_name(platform: str, appearance: str, raw: str) -> str:
    """Return the committed name of a raw shot like `3-session.png`.

    Args:
        platform: `android` or `ios`.
        appearance: `light` or `dark`.
        raw: The flow's file name, `<n>-<screen>.png`.
    """
    return f"{platform}-{appearance}-{Path(raw).stem}.webp"


def status_minute(elapsed: float) -> tuple[int, int]:
    """Return the fake clock's hour and minute `elapsed` s after the app's clock started."""
    moment = CLOCK_START + timedelta(seconds=max(elapsed, 0.0))
    return moment.hour, moment.minute


def run(*command: str, check: bool = True) -> str:
    """Run a command; return what it printed."""
    done = subprocess.run(
        command,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    return done.stdout.strip()


class Device:
    """What differs between an emulator and a simulator: starting the app, the status bar."""

    def __init__(self, serial: str) -> None:
        """Keep the emulator's serial or the simulator's udid."""
        self.serial = serial

    def set_appearance(self, appearance: str) -> None:
        """Switch the system to light or dark."""
        raise NotImplementedError

    def start(self) -> None:
        """Store the preferences on clean data and start the app."""
        raise NotImplementedError

    def set_clock(self, hour: int, minute: int) -> None:
        """Show `hour:minute` in the status bar, with a full battery and bars."""
        raise NotImplementedError

    def finish(self) -> None:
        """Give the system its own status bar and appearance back."""
        raise NotImplementedError


class Android(Device):
    """An emulator with a Google APIs image, written as root."""

    def adb(self, *args: str) -> str:
        """Run `adb -s <serial>` with `args`."""
        return run("adb", "-s", self.serial, *args)

    def set_appearance(self, appearance: str) -> None:
        """Set the night mode."""
        self.adb(
            "shell", "cmd", "uimode", "night", "yes" if appearance == "dark" else "no"
        )

    def start(self) -> None:
        """Clear the app, write its preferences as root, and launch it."""
        self.adb("root")
        self.adb("wait-for-device")
        data = f"/data/data/{BUNDLE}"
        self.adb("shell", "pm", "clear", BUNDLE)
        self.adb("shell", "am", "start", "-W", "-n", ACTIVITY)  # creates its folders
        time.sleep(3)
        self.adb("shell", "am", "force-stop", BUNDLE)
        self.adb(
            "shell", "pm", "grant", BUNDLE, "android.permission.POST_NOTIFICATIONS"
        )
        owner = self.adb("shell", "stat", "-c", "%u", data)
        xml = "\n".join(
            [
                "<?xml version='1.0' encoding='utf-8' standalone='yes' ?>",
                "<map>",
                *(_xml_entry(k, v) for k, v in app_prefs().items()),
                "</map>",
            ]
        )
        local = ROOT / "build" / "readme_shots" / "FlutterSharedPreferences.xml"
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_text(xml, encoding="utf-8")
        target = f"{data}/shared_prefs/FlutterSharedPreferences.xml"
        self.adb("shell", "mkdir", "-p", f"{data}/shared_prefs")
        self.adb("push", str(local), target)
        self.adb(
            "shell",
            f"chown {owner}:{owner} {target}; chmod 660 {target}; restorecon {target}",
        )
        self.adb("shell", "am", "start", "-W", "-n", ACTIVITY)

    def _demo(self, command: str, *extras: str) -> None:
        """Send a command to the system UI's demo mode."""
        self.adb(
            "shell",
            "am",
            "broadcast",
            "-a",
            "com.android.systemui.demo",
            "-e",
            "command",
            command,
            *extras,
        )

    def set_clock(self, hour: int, minute: int) -> None:
        """Enter demo mode and set its clock, battery, Wi-Fi and quiet notifications."""
        self.adb("shell", "settings", "put", "global", "sysui_demo_allowed", "1")
        self._demo("enter")
        self._demo("clock", "-e", "hhmm", f"{hour:02d}{minute:02d}")
        self._demo("battery", "-e", "level", "100", "-e", "plugged", "false")
        self._demo(
            "network", "-e", "wifi", "show", "-e", "level", "4", "-e", "fully", "true"
        )
        self._demo(
            "network", "-e", "mobile", "hide"
        )  # a Wi-Fi phone: no stray "3G" in one run
        self._demo("notifications", "-e", "visible", "false")

    def finish(self) -> None:
        """Leave demo mode and the night mode."""
        self._demo("exit")
        self.adb("shell", "cmd", "uimode", "night", "no")


def _xml_entry(key: str, value: Any) -> str:
    """Return one `SharedPreferences` XML line: a boolean or a string."""
    if isinstance(value, bool):
        return f'    <boolean name="{key}" value="{str(value).lower()}" />'
    text = str(value).replace("&", "&amp;").replace("<", "&lt;")
    return f'    <string name="{key}">{text}</string>'


class IOS(Device):
    """A simulator: preferences are a plist in the app's container."""

    def simctl(self, *args: str) -> str:
        """Run `xcrun simctl` with `args`."""
        return run("xcrun", "simctl", *args)

    def set_appearance(self, appearance: str) -> None:
        """Reboot the simulator, set the interface style, and give the system a moment.

        A simulator that has been up a while keeps its style whatever `simctl ui` is told, with
        the app in front or not (seen on iOS 26.5, both directions); the first change after a
        boot has always taken, so each appearance gets a boot of its own.
        """
        run("xcrun", "simctl", "shutdown", self.serial, check=False)
        self.simctl("boot", self.serial)
        self.simctl("bootstatus", self.serial, "-b")
        self.simctl("ui", self.serial, "appearance", appearance)
        time.sleep(3)

    def start(self) -> None:
        """Clear the app's preferences, store ours and launch it."""
        run("xcrun", "simctl", "terminate", self.serial, BUNDLE, check=False)
        data = Path(self.simctl("get_app_container", self.serial, BUNDLE, "data"))
        path = data / "Library" / "Preferences" / f"{BUNDLE}.plist"
        path.parent.mkdir(parents=True, exist_ok=True)
        stored = plistlib.loads(path.read_bytes()) if path.exists() else {}
        kept = {k: v for k, v in stored.items() if not k.startswith("flutter.pycon.")}
        path.write_bytes(plistlib.dumps(kept | app_prefs()))
        # The daemon holds the old values; restarted, it reads the file again.
        self.simctl(
            "spawn",
            self.serial,
            "launchctl",
            "kickstart",
            "-k",
            "user/foreground/com.apple.cfprefsd.xpc.daemon",
        )
        self.simctl("launch", self.serial, BUNDLE)

    def set_clock(self, hour: int, minute: int) -> None:
        """Override the status bar's time, battery and bars."""
        self.simctl(
            "status_bar",
            self.serial,
            "override",
            "--time",
            f"{hour}:{minute:02d}",
            *STATUS_BAR.split(),
        )

    def finish(self) -> None:
        """Clear the status bar's override; the appearance goes back to light."""
        self.simctl("status_bar", self.serial, "clear")
        self.simctl("ui", self.serial, "appearance", "light")


def follow_clock(device: Device, started: float, stop: threading.Event) -> None:
    """Keep the status bar at the app's fake clock's minute until `stop` is set."""
    shown = None
    while not stop.is_set():
        now = status_minute(time.monotonic() - started)
        if now != shown:
            try:
                device.set_clock(*now)
                shown = now
            except subprocess.CalledProcessError as failure:
                print(f"status bar not set to {now}: {failure}", flush=True)
        stop.wait(1.0)


def shoot(device: Device, appearance: str, raw: Path) -> list[Path]:
    """Run the flow once in `appearance`; return its screenshots, in the flow's order.

    Args:
        device: The emulator or simulator.
        appearance: `light` or `dark`.
        raw: The folder for this run's full-size shots.
    """
    folder = raw / appearance
    shutil.rmtree(folder, ignore_errors=True)  # no shots of an earlier run
    device.set_appearance(appearance)
    device.start()
    started = (
        time.monotonic() + BOOT_LAG
    )  # the app's clock starts once its Python has booted
    device.set_clock(*status_minute(0))
    stop = threading.Event()
    follower = threading.Thread(
        target=follow_clock, args=(device, started, stop), daemon=True
    )
    follower.start()
    try:
        command = [
            "maestro",
            "--device",
            device.serial,
            "test",
            "--test-output-dir",
            str(folder),
            str(FLOW),
        ]
        subprocess.run(
            command, check=True, env=os.environ | {"MAESTRO_CLI_NO_ANALYTICS": "1"}
        )
    finally:
        stop.set()
        follower.join(timeout=10)
    return sorted(folder.rglob("takeScreenshot/*.png"), key=lambda p: p.name)


def is_dark(shot: Path) -> bool:
    """Return whether a screenshot's pixels are mostly dark: the system took the appearance."""
    from PIL import Image, ImageStat  # pyright: ignore[reportMissingImports]

    with Image.open(shot) as image:
        return ImageStat.Stat(image.convert("L")).mean[0] < 128


def shrink(source: Path, target: Path) -> int:
    """Write `source` as a `SHOT_WIDTH`-px-wide WebP at `target`; return its size in bytes."""
    from PIL import Image  # pyright: ignore[reportMissingImports]

    with Image.open(source) as image:
        rgb = image.convert("RGB")
    height = round(rgb.height * SHOT_WIDTH / rgb.width)
    rgb.resize((SHOT_WIDTH, height), Image.Resampling.LANCZOS).save(
        target, "WEBP", quality=80, method=6
    )
    return target.stat().st_size


def main(argv: list[str] | None = None) -> None:
    """Parse the command line and photograph one device, in both appearances."""
    parser = argparse.ArgumentParser(description="Photograph the README's screenshots.")
    parser.add_argument("platform", choices=("android", "ios"))
    parser.add_argument("device", help="an emulator's serial or a simulator's udid")
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "images")
    parser.add_argument("--raw", type=Path, default=ROOT / "build" / "readme_shots")
    args = parser.parse_args(argv)
    device: Device = (
        Android(args.device) if args.platform == "android" else IOS(args.device)
    )
    args.out.mkdir(parents=True, exist_ok=True)
    total = 0
    try:
        device.start()  # a warm-up: the feed and the logos are cached before the first shot
        time.sleep(WARM_UP_SECONDS)
        for appearance in APPEARANCES:
            shots = shoot(device, appearance, args.raw / args.platform)
            if len(shots) != 6:
                sys.exit(f"readme_shots: {appearance} took {len(shots)} shots, not 6")
            if is_dark(shots[0]) != (appearance == "dark"):
                sys.exit(
                    f"readme_shots: the {appearance} run came out {'light' if appearance == 'dark' else 'dark'}"
                )
            for shot in shots:
                total += shrink(
                    shot, args.out / shot_name(args.platform, appearance, shot.name)
                )
    finally:
        device.finish()
    print(f"{args.platform}: 12 images, {total / 1024:.0f} KB in {args.out}")


if __name__ == "__main__":
    main()
