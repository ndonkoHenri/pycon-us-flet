"""Drive the S7 reproducer on an Android emulator with adb (#361).

Run from this folder with the release APK installed:

    S7_SERIAL=emulator-5590 uv run python drive_android.py <step> [<arg> ...]

Steps (each prints `S7-DRIVE` lines):

- `launch`: force-stop, start the app (`am start -W`), wait 8 s.
- `tap <text>`: tap the node whose text or description starts with `<text>`.
- `mem <label>`: `dumpsys meminfo` of the app: the App Summary, Unknown's PSS
  and TOTAL PSS/RSS.
- `booths`: every `booth.*` node's bounds, in tree order (TalkBack's order).
- `tapall [limit]`: tap the centre of every booth node on screen and report
  which booth the app logged for each (tap accuracy).
- `tapsame <file>`: tap the centres saved by `booths > file` again (for the
  gesture mode, which has no booth nodes).
- `swipe <x1> <y1> <x2> <y2> [ms]`: one drag.
- `pans <n>`: n drags across the plan, left, right, up and down, between
  points inside the plan's on-screen bounds; says how many transforms the app
  logged (0 means the plan did not move, so frame numbers would mean nothing).
- `frames <seconds>`: SurfaceFlinger's present times of the app's layer while
  `pans` runs, as intervals (a relative signal on a loaded host).
- `log [since]`: the app's `S7` lines.
"""

import itertools
import json
import os
import re
import shlex
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ADB = str(Path.home() / "Library/Android/sdk/platform-tools/adb")
SERIAL = os.environ.get("S7_SERIAL", "emulator-5590")
PKG = "io.github.ndonkohenri.pyconus.s7plans"


def adb(*args: str, check: bool = True) -> str:
    """Run one adb command against SERIAL and return its stdout."""
    return subprocess.run(
        [ADB, "-s", SERIAL, *args], capture_output=True, text=True, check=check
    ).stdout


def say(event: str, **values: object) -> None:
    """Print one driver line."""
    print(
        f"S7-DRIVE {event} " + " ".join(f"{k}={v}" for k, v in values.items()),
        flush=True,
    )


def nodes() -> list[dict]:
    """Return every node of the screen's accessibility tree, in tree order."""
    # Up to three tries: on the 2.5 GB AVD, UiAutomation's connect times out
    # now and then while the system server is busy.
    for _ in range(3):
        adb("shell", "rm", "-f", "/sdcard/s7.xml", check=False)
        adb("shell", "uiautomator", "dump", "/sdcard/s7.xml", check=False)
        xml = adb("shell", "cat", "/sdcard/s7.xml", check=False)
        if xml.strip():
            break
    root = ET.fromstring(xml)
    out = []
    for node in root.iter("node"):
        x1, y1, x2, y2 = map(int, re.findall(r"\d+", node.get("bounds", "[0,0][0,0]")))
        out.append(
            {
                "text": node.get("text", ""),
                "desc": node.get("content-desc", ""),
                "id": node.get("resource-id", ""),
                "bounds": (x1, y1, x2, y2),
                "centre": ((x1 + x2) // 2, (y1 + y2) // 2),
            }
        )
    return out


def tap_text(text: str) -> None:
    """Tap the first node whose text or description starts with text."""
    for node in nodes():
        if node["text"].startswith(text) or node["desc"].startswith(text):
            adb("shell", "input", "tap", *map(str, node["centre"]))
            say("tap", text=repr(text), at=node["centre"])
            return
    say("missing", text=repr(text))


def app_log(since: str = "") -> list[str]:
    """Return the app's S7 lines from logcat."""
    args = ["logcat", "-d", "-v", "time"] + (["-T", since] if since else [])
    return [line for line in adb(*args).splitlines() if " S7 " in line]


def mem(label: str) -> None:
    """Print the app's memory: the App Summary rows and the totals."""
    # -t 60: on the 2.5 GB AVD the default 10-s dump timeout expires.
    out = adb("shell", "dumpsys", "-t", "60", "meminfo", PKG)
    rows = {}
    for key in (
        "Java Heap",
        "Native Heap",
        "Code",
        "Stack",
        "Graphics",
        "Private Other",
        "System",
    ):
        match = re.search(rf"^\s+{key}:\s+(\d+)", out, re.MULTILINE)
        rows[key.replace(" ", "")] = int(match[1]) // 1024 if match else None
    pss = re.search(r"TOTAL PSS:\s+(\d+)", out)
    rss = re.search(r"TOTAL RSS:\s+(\d+)", out)
    # The emulator reports Graphics 0, so a decoded plan shows up here and in the
    # Native Heap: Unknown's PSS (the first column of the detailed table).
    unknown = re.search(r"^\s+Unknown\s+(\d+)", out, re.MULTILINE)
    gl = re.search(r"^\s+GL mtrack\s+(\d+)", out, re.MULTILINE)
    egl = re.search(r"^\s+EGL mtrack\s+(\d+)", out, re.MULTILINE)
    say(
        "mem",
        label=label,
        pss_mb=int(pss[1]) // 1024 if pss else None,
        rss_mb=int(rss[1]) // 1024 if rss else None,
        gl_mb=int(gl[1]) // 1024 if gl else 0,
        egl_mb=int(egl[1]) // 1024 if egl else 0,
        **{f"{k}_mb": v for k, v in rows.items()},
        Unknown_mb=int(unknown[1]) // 1024 if unknown else None,
    )


def booths() -> list[dict]:
    """Return the booth nodes in tree order, with their bounds."""
    return [
        n
        for n in nodes()
        if n["id"].startswith("booth.") or n["desc"].startswith("Booth ")
    ]


def tap_points(points: list[tuple[str, tuple[int, int]]]) -> None:
    """Tap each point and compare the booth the app logged with the expected one."""
    adb("logcat", "-c")
    for _, (x, y) in points:
        adb("shell", "input", "tap", str(x), str(y))
        time.sleep(0.45)
    time.sleep(1.0)
    hits = [re.search(r"booth=(\w+)", line)[1] for line in app_log() if " tap " in line]
    expected = [booth for booth, _ in points]
    right = sum(1 for a, b in zip(expected, hits, strict=False) if a == b)
    say("accuracy", taps=len(points), logged=len(hits), right=right)
    for a, b in zip(expected, hits, strict=False):
        if a != b:
            say("wrong", expected=a, got=b)


def plan_box() -> tuple[int, int, int, int]:
    """Return the on-screen bounds of the plan's image, clipped to the display.

    The image's semantics label ends in " plan" (main.py); without it, the
    whole display.
    """
    width, height = map(int, re.findall(r"\d+", adb("shell", "wm", "size"))[-2:])
    for node in nodes():
        if node["desc"].endswith(" plan"):
            x1, y1, x2, y2 = node["bounds"]
            return max(x1, 0), max(y1, 0), min(x2, width), min(y2, height)
    return 0, 0, width, height


def pan_moves() -> list[tuple[int, int, int, int]]:
    """Return four drags, left, right, up and down, kept inside the plan.

    Each drag runs between points 20% in from the plan's edges, so both ends
    stay on the plan whatever the display or the zoom.
    """
    x1, y1, x2, y2 = plan_box()
    dx, dy = (x2 - x1) // 5, (y2 - y1) // 5
    left, right, top, bottom = x1 + dx, x2 - dx, y1 + dy, y2 - dy
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    return [
        (right, cy, left, cy),
        (left, cy, right, cy),
        (cx, bottom, cx, top),
        (cx, top, cx, bottom),
    ]


def pans(n: int, moves: list[tuple[int, int, int, int]] | None = None) -> None:
    """Drag across the plan n times, in four directions, and say if it moved.

    Args:
        n: The number of drags.
        moves: The four drags; measured from the plan's bounds when None.
    """
    moves = moves or pan_moves()
    adb("logcat", "-c")
    for i in range(n):
        x1, y1, x2, y2 = moves[i % 4]
        adb("shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), "400")
    moved = sum(1 for line in app_log() if " transform " in line)
    say("pans", drags=n, transforms=moved, moves=moves)


def frames(seconds: float) -> None:
    """Print the app layer's frame intervals from SurfaceFlinger while panning."""
    layers = adb("shell", "dumpsys", "SurfaceFlinger", "--list").splitlines()
    # On Android 14 Flutter's frames land on the SurfaceView's BLAST layer; the
    # plain SurfaceView layer and its "Background for" layer report only zeros.
    surfaces = [
        name for name in layers if name.startswith("SurfaceView[") and PKG in name
    ]
    layer = next((name for name in surfaces if "(BLAST)" in name), None)
    layer = layer or next(iter(surfaces), None)
    layer = layer or next((name for name in layers if PKG in name), "")
    adb("shell", "dumpsys", "SurfaceFlinger", "--latency-clear")
    moves = pan_moves()
    end = time.time() + seconds
    while time.time() < end:
        pans(4, moves)
    # adb shell hands its arguments to the device's shell: quote the brackets.
    out = adb(
        "shell", "dumpsys", "SurfaceFlinger", "--latency", shlex.quote(layer)
    ).split()
    stamps = [
        int(out[i + 1])
        for i in range(1, len(out) - 2, 3)
        if int(out[i + 1]) not in (0, 2**63 - 1)
    ]
    stamps.sort()
    gaps = [(b - a) / 1e6 for a, b in itertools.pairwise(stamps) if b - a < 1e9]
    if not gaps:
        say("frames", layer=repr(layer), count=0)
        return
    gaps.sort()
    say(
        "frames",
        layer=repr(layer[:60]),
        count=len(gaps) + 1,
        median_ms=round(gaps[len(gaps) // 2], 1),
        p90_ms=round(gaps[int(len(gaps) * 0.9)], 1),
        over_33ms=sum(1 for g in gaps if g > 33.4),
    )


def main() -> None:
    """Run the step named on the command line."""
    step, args = sys.argv[1], sys.argv[2:]
    if step == "launch":
        adb("shell", "am", "force-stop", PKG)
        adb("logcat", "-c")
        # am start, not monkey: monkey exited 251 once on the 2.5 GB AVD.
        out = adb("shell", "am", "start", "-W", "-n", f"{PKG}/.MainActivity")
        total = re.search(r"TotalTime:\s+(\d+)", out)
        time.sleep(8)
        say("launched", total_ms=total[1] if total else None)
    elif step == "tap":
        tap_text(" ".join(args))
    elif step == "mem":
        mem(args[0] if args else "now")
    elif step == "booths":
        found = booths()
        print(
            json.dumps(
                [
                    {
                        "desc": b["desc"],
                        "id": b["id"],
                        "centre": b["centre"],
                        "bounds": b["bounds"],
                    }
                    for b in found
                ]
            )
        )
    elif step == "tapall":
        found = [b for b in booths() if b["bounds"][2] > b["bounds"][0]]
        limit = int(args[0]) if args else len(found)
        tap_points(
            [
                (re.search(r"Booth (\w+)", b["desc"])[1], b["centre"])
                for b in found[:limit]
            ]
        )
    elif step == "tapsame":
        saved = json.loads(Path(args[0]).read_text())
        tap_points(
            [
                (re.search(r"Booth (\w+)", b["desc"])[1], tuple(b["centre"]))
                for b in saved
            ]
        )
    elif step == "swipe":
        adb("shell", "input", "swipe", *args)
    elif step == "pans":
        pans(int(args[0]))
    elif step == "frames":
        frames(float(args[0]))
    elif step == "log":
        print("\n".join(app_log(args[0] if args else "")))


if __name__ == "__main__":
    main()
