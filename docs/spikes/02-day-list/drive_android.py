"""Drive the S2 reproducer on an Android emulator with adb and measure each variant.

Run from this folder with the release APK installed (``flet build apk``, then
``adb install -r``)::

    uv run --group measure python drive_android.py <suite> <variant> [<variant> ...]

A variant is the launch route without its leading slash, e.g. ``memo/lazy/all``
(src/main.py). Suites:

- ``cold``: ``$S2_N`` cold starts (default 10): force-stop, then a deep link with the
  variant; the time from logcat's ``START u0`` line to the app's ``acked action=first``
  line (the S1 method, D-112), and Python's own split of it.
- ``star``: a sync keystroke, then 12 taps on one star while the screen is recorded; from
  each tap's ``star-in`` line to the frame where the star's fill changed, on the device
  clock (``star_latencies`` explains the sync).
- ``search``: types ``python`` into the day's search field one key at a time, then deletes
  it, 12 keystrokes; from the first change in the field to the first and the last change
  in the list below it.
- ``days``: 12 taps on the day tabs; from the first change in the tab bar to the first and
  the last change in the list.
- ``jump``: on a fresh launch, the two jump buttons (``scroll_to(scroll_key=...)`` and the
  two-step jump), three times each; whether the target slot's gutter is on screen after.
- ``fling``: twelve flings (six down the day, six back up); the intervals between the
  frames SurfaceFlinger presented for the app's surface (``dumpsys SurfaceFlinger
  --latency``), and the frames that took over 1.5 vsyncs (25 ms).
- ``tabframes``: the same frame intervals for 12 day-tab taps, and each tap's worst frame.
- ``all``: all of the above.

``$S2_SCALE`` sets the system font scale first (e.g. ``2.0``) and restores 1.0 after.
Every action's Python split (handler → patch sent → SharedPreferences round trip) comes
from the app's ``S2`` log lines. Results print as lines and are appended to
``$S2_OUT/results.jsonl`` (default ``./out``); recordings stay in ``$S2_OUT``.
"""

import itertools
import json
import os
import re
import statistics
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import av
import numpy as np

ADB = str(Path.home() / "Library/Android/sdk/platform-tools/adb")
SERIAL = os.environ.get("S2_SERIAL", "emulator-5554")
OUT = Path(os.environ.get("S2_OUT", "out"))
N = int(os.environ.get("S2_N", "10"))
SCALE = os.environ.get("S2_SCALE", "1.0")
PKG = "io.github.ndonkohenri.pyconus.s2"
FAVORITE = np.array([0xA1, 0x00, 0x9A])  # LIGHT_TOKENS.favorite: the filled star
GAP = 2.0  # seconds between two actions in a recording

Box = tuple[int, int, int, int]  # x1, y1, x2, y2 in screen pixels


def adb(*args: str, check: bool = True) -> str:
    """Run one adb command against SERIAL and return its stdout."""
    done = subprocess.run(
        [ADB, "-s", SERIAL, *args], capture_output=True, text=True, check=check
    )
    return done.stdout


def events() -> list[dict[str, str]]:
    """The app's ``S2`` log lines since the last ``logcat -c``, as field dicts."""
    out = adb("logcat", "-d", "-v", "epoch", "-s", "flet.python:I")
    found = []
    for raw in out.splitlines():
        match = re.search(r"S2 (\S+) (.*)$", raw)
        if match:
            fields = dict(re.findall(r"(\w+)=(\S+)", match[2]))
            fields["event"] = match[1]
            found.append(fields)
    return found


def wait_for(event: str, timeout: float = 15.0, **values: str) -> dict[str, str] | None:
    """Wait for an ``S2`` line with this event (and field values); return it or None."""
    end = time.time() + timeout
    while time.time() < end:
        for found in events():
            if found["event"] == event and all(
                found.get(k) == v for k, v in values.items()
            ):
                return found
        time.sleep(0.25)
    return None


def launch(variant: str) -> dict[str, float]:
    """Cold-start the variant by deep link; return its timings in ms."""
    adb("shell", "am", "force-stop", PKG)
    time.sleep(2)
    adb("logcat", "-c")
    out = adb(
        "shell", "am", "start", "-W", "-a", "android.intent.action.VIEW",
        "-d", f"s2spike://s2/{variant}", PKG,
    )  # fmt: skip
    total = float(re.search(r"TotalTime: (\d+)", out)[1])  # type: ignore[index]
    acked = wait_for("acked", action="first")
    if acked is None:
        raise RuntimeError(f"{variant}: no first render")
    system = adb("logcat", "-d", "-v", "epoch", "-s", "ActivityTaskManager:I")
    start = next(
        float(m[1])
        for m in re.finditer(r"(\d+\.\d+).*START u0.*" + re.escape(PKG), system)
    )
    by_event: dict[str, dict[str, str]] = {}
    for (
        e
    ) in events():  # the first of each: a deferred render logs a second patched/acked
        by_event.setdefault(e["event"], e)

    def at(event: str) -> float:
        return (float(by_event[event]["wall"]) - start) * 1000

    return {
        "total_time": total,
        "py_start": at("py-start"),
        "main": at("main"),
        "patched": at("patched"),
        "content": at("acked"),
        "main_to_patched": at("patched") - at("main"),
        "processed_ms": float(by_event["processed"]["ms"]),
    }


def nodes() -> list[tuple[str, str, Box]]:
    """(label, class, bounds) for every node of the accessibility tree."""
    adb("shell", "uiautomator", "dump", "/sdcard/s2.xml")
    tree = ET.fromstring(adb("exec-out", "cat", "/sdcard/s2.xml"))
    found = []
    for node in tree.iter("node"):
        label = node.get("content-desc") or node.get("text") or node.get("hint") or ""
        x1, y1, x2, y2 = map(int, re.findall(r"\d+", node.get("bounds", "")))
        found.append((label, node.get("class", ""), (x1, y1, x2, y2)))
    return found


def centre(box: Box) -> tuple[str, str]:
    """The centre of a box, as adb input arguments."""
    return str((box[0] + box[2]) // 2), str((box[1] + box[3]) // 2)


def tap(box: Box) -> None:
    """Tap the centre of a box."""
    adb("shell", "input", "tap", *centre(box))


def record(name: str, actions: Callable[[], None]) -> Path:
    """Record the screen while actions run; return the pulled MP4."""
    OUT.mkdir(parents=True, exist_ok=True)
    adb("shell", "rm", "-f", "/sdcard/s2.mp4", check=False)
    proc = subprocess.Popen(
        [ADB, "-s", SERIAL, "shell", "screenrecord", "--bit-rate", "20000000",
         "--time-limit", "120", "/sdcard/s2.mp4"],
    )  # fmt: skip
    time.sleep(1.5)
    actions()
    time.sleep(1.5)
    adb("shell", "pkill", "-INT", "screenrecord", check=False)
    proc.wait(timeout=20)
    time.sleep(1)
    path = OUT / f"{name}.mp4"
    adb("pull", "/sdcard/s2.mp4", str(path))
    return path


def crops(
    path: Path, boxes: dict[str, Box]
) -> list[tuple[float, dict[str, np.ndarray]]]:
    """Decode the recording: (seconds, {name: RGB crop}) for every frame."""
    found = []
    with av.open(str(path)) as container:
        for frame in container.decode(video=0):
            if frame.time is None:
                continue
            image = frame.to_ndarray(format="rgb24")
            found.append(
                (
                    float(frame.time),
                    {
                        k: image[b[1] : b[3], b[0] : b[2]].astype(np.int16)
                        for k, b in boxes.items()
                    },
                )
            )
    return found


def changed(a: np.ndarray, b: np.ndarray) -> bool:
    """Whether two crops differ beyond video-compression noise."""
    return int((np.abs(a - b).max(axis=2) > 32).sum()) > 30


def change_times(
    frames: list[tuple[float, dict[str, np.ndarray]]], name: str
) -> list[float]:
    """The times of the frames where the named crop differs from the frame before."""
    times = []
    for (_, previous), (t, current) in itertools.pairwise(frames):
        if changed(previous[name], current[name]):
            times.append(t)
    return times


def triggers(times: list[float], quiet: float = 0.8) -> list[float]:
    """The first change of each burst: a change after at least ``quiet`` s of none."""
    starts, last = [], -10.0
    for t in times:
        if t < 1.4:  # the recording's first frames, before the first action
            continue
        if t - last >= quiet:
            starts.append(t)
        last = t
    return starts


def star_latencies(path: Path, star: Box, field: Box) -> list[float]:
    """Milliseconds from each star tap to the frame where the star's fill changed.

    An instant tap draws no press feedback before the star changes (the ripple shows up
    with the fill), so the recording starts with a sync keystroke instead: the frame where
    its character appears and its ``key-in`` log line map the video's clock onto the
    device clock. Each fill frame is then compared with its tap's ``star-in`` line. Both
    actions reach Python the same way, so the result is the time the star takes beyond a
    change Flutter draws on its own (about one frame).
    """
    frames = crops(path, {"star": star, "field": field})
    filled = [
        int((np.abs(c["star"] - FAVORITE).max(axis=2) < 40).sum()) > 150
        for _, c in frames
    ]
    log = events()
    key = next(e for e in log if e["event"] == "key-in")
    offset = float(key["wall"]) - triggers(change_times(frames, "field"))[0]
    fills = [
        frames[k][0] + offset
        for k in range(1, len(frames))
        if filled[k] != filled[k - 1]
    ]
    latencies = []
    for tap_wall in (float(e["wall"]) for e in log if e["event"] == "star-in"):
        after = [f for f in fills if tap_wall - 0.05 <= f < tap_wall + 1.5]
        if after:
            latencies.append((after[0] - tap_wall) * 1000)
    return latencies


def response_latencies(
    path: Path, trigger: Box, response: Box
) -> list[tuple[float, float]]:
    """Milliseconds (first, last) from each burst in trigger to the changes in response after it."""
    frames = crops(path, {"trigger": trigger, "response": response})
    starts = triggers(change_times(frames, "trigger"))
    changes = change_times(frames, "response")
    found = []
    for i, t0 in enumerate(starts):
        end = min(t0 + GAP - 0.2, starts[i + 1] if i + 1 < len(starts) else t0 + GAP)
        after = [t for t in changes if t0 <= t < end]
        if after:
            found.append(((after[0] - t0) * 1000, (after[-1] - t0) * 1000))
    return found


def python_split(action: str) -> dict[str, list[float]]:
    """Per action in the log: handler → patch sent, patch sent → round trip, rows rendered."""
    split: dict[str, list[float]] = {
        "in_to_patched": [],
        "patched_to_acked": [],
        "rows": [],
    }
    began = patched = None
    for e in events():
        if e["event"] == f"{action}-in":
            began = float(e["wall"])
        elif e["event"] == "patched" and e.get("action") == action and began:
            patched = float(e["wall"])
            split["in_to_patched"].append((patched - began) * 1000)
            split["rows"].append(float(e["rows_rendered"]))
        elif e["event"] == "acked" and e.get("action") == action and patched:
            split["patched_to_acked"].append((float(e["wall"]) - patched) * 1000)
            began = patched = None
    return split


def summary(values: list[float]) -> str:
    """Median and range of values, rounded to ms."""
    if not values:
        return "n=0"
    return f"{statistics.median(values):.0f} ({min(values):.0f}-{max(values):.0f}) n={len(values)}"


def report(suite: str, variant: str, **series: list[float]) -> None:
    """Print one result line per series and append them to results.jsonl."""
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "results.jsonl").open("a") as stream:
        for name, values in series.items():
            print(
                f"{suite} {variant} scale={SCALE} {name}: {summary(values)}", flush=True
            )
            stream.write(
                json.dumps(
                    {"suite": suite, "variant": variant, "scale": SCALE, "series": name,
                     "values": [round(v, 1) for v in values]}
                )
                + "\n"
            )  # fmt: skip


def screen_boxes() -> dict[str, Box]:
    """The boxes the suites use: a star, the search field, the tab bar and the list."""
    found = nodes()
    field = next(b for _, cls, b in found if cls == "android.widget.EditText")
    tabs = [b for label, _, b in found if "\nTab " in label and b[1] < field[1]]
    nav_top = min(b[1] for label, _, b in found if label.startswith("Now\nTab"))
    star = next(
        b
        for label, cls, b in found
        if cls == "android.widget.Button"
        and not label
        and b[0] >= 900
        and b[1] > field[3]
    )
    return {
        "star": star,
        "field": (field[0] + 120, field[1] + 20, field[2] - 20, field[3] - 20),
        "tabs": (0, min(b[1] for b in tabs), 1080, max(b[3] for b in tabs)),
        "list": (0, field[3] + 30, 1080, nav_top - 10),
        "thu": next(b for label, _, b in found if label.startswith("Thu\nMay 14")),
        "fri": next(b for label, _, b in found if label.startswith("Fri\nMay 15")),
        "sat": next(b for label, _, b in found if label.startswith("Sat\nMay 16")),
    }


def suite_cold(variant: str) -> None:
    """Cold starts to the rendered day."""
    runs = [launch(variant) for _ in range(N)]
    report(
        "cold",
        variant,
        **{key: [r[key] for r in runs] for key in runs[0]},
    )


def suite_star(variant: str) -> None:
    """Star-tap latency."""
    launch(variant)
    time.sleep(1)
    boxes = screen_boxes()
    tap(boxes["field"])  # focus first, so the sync keystroke moves nothing else
    time.sleep(2)
    adb("logcat", "-c")

    def taps() -> None:
        adb("shell", "input", "text", "a")  # the sync mark; every row matches "a"
        time.sleep(GAP)
        for _ in range(12):
            tap(boxes["star"])
            time.sleep(GAP)

    path = record(f"star-{variant.replace('/', '-')}-{SCALE}", taps)
    adb("shell", "input", "keyevent", "4")  # close the keyboard
    split = python_split("star")
    screen = star_latencies(path, boxes["star"], boxes["field"])
    report("star", variant, screen=screen, **split)


def suite_search(variant: str) -> None:
    """Search-as-you-type latency."""
    launch(variant)
    time.sleep(1)
    boxes = screen_boxes()
    tap(boxes["field"])
    time.sleep(2)  # the keyboard opens and the list shrinks
    response = (0, boxes["list"][1], 1080, boxes["list"][1] + 500)
    adb("logcat", "-c")

    def keys() -> None:
        for char in "python":
            adb("shell", "input", "text", char)
            time.sleep(GAP)
        for _ in "python":
            adb("shell", "input", "keyevent", "67")  # Backspace
            time.sleep(GAP)

    path = record(f"search-{variant.replace('/', '-')}-{SCALE}", keys)
    adb("shell", "input", "keyevent", "4")  # close the keyboard
    pairs = response_latencies(path, boxes["field"], response)
    split = python_split("key")
    report(
        "search",
        variant,
        first=[p[0] for p in pairs],
        settled=[p[1] for p in pairs],
        **split,
    )


def suite_days(variant: str) -> None:
    """Day-switch latency."""
    launch(variant)
    time.sleep(1)
    boxes = screen_boxes()
    adb("logcat", "-c")
    order = ["thu", "fri", "sat", "fri"] * 3

    def taps() -> None:
        for name in order:
            tap(boxes[name])
            time.sleep(GAP)

    path = record(f"days-{variant.replace('/', '-')}-{SCALE}", taps)
    pairs = response_latencies(path, boxes["tabs"], boxes["list"])
    split = python_split("day")
    report(
        "days",
        variant,
        first=[p[0] for p in pairs],
        settled=[p[1] for p in pairs],
        **split,
    )


def suite_jump(variant: str) -> None:
    """Whether each jump reaches the target slot, built or not."""
    OUT.mkdir(parents=True, exist_ok=True)
    for button in ("Jump to slot", "Jump in two steps"):
        reached = []
        for attempt in range(3):
            launch(variant)
            time.sleep(1)
            box = next(b for label, _, b in nodes() if label == button)
            adb("logcat", "-c")
            tap(box)
            done = wait_for("jump-done") or wait_for("jump2-done")
            time.sleep(1.5)
            key = (done or {}).get("key", "")
            target = datetime.fromisoformat(key.removeprefix("slot-"))
            label = f"{target.hour % 12 or 12}:{target.minute:02d} {'AM' if target.hour < 12 else 'PM'}"
            # The gutter reads as its time alone (exclude_semantics); before that change
            # its texts followed on new lines.
            visible = any(
                text == label or text.startswith(label + "\n") for text, _, _ in nodes()
            )
            scrolled = [e for e in events() if e["event"] == "scrolled"]
            reached.append(1.0 if visible else 0.0)
            print(
                f"jump {variant} scale={SCALE} {button!r} #{attempt + 1}: target {label} "
                f"{'ON SCREEN' if visible else 'not reached'}; scroll ends "
                f"{[e['pixels'] for e in scrolled]}",
                flush=True,
            )
            shot = subprocess.run(
                [ADB, "-s", SERIAL, "exec-out", "screencap", "-p"],
                capture_output=True,
                check=True,
            ).stdout
            name = f"jump-{button.split()[-1]}-{variant.replace('/', '-')}-{SCALE}-{attempt}"
            (OUT / f"{name}.png").write_bytes(shot)
        report("jump", variant, **{button.replace(" ", "_"): reached})


def flutter_layer() -> str:
    """The SurfaceFlinger layer that Flutter draws the app into."""
    listing = adb("shell", "dumpsys", "SurfaceFlinger", "--list")
    return next(
        line.split("{", 1)[1].split(" parentId")[0].strip("}")
        for line in listing.splitlines()
        if "SurfaceView[" + PKG in line and "(BLAST)" in line
    )


def motion_intervals(presents: list[float], window: float = 1500.0) -> list[float]:
    """Intervals between the frames presented within ``window`` ms of the gesture's first.

    The window covers a fling or a tab slide, so a stall inside it counts, however
    long; the frames after it (a ripple fading, the list at rest) are left out.
    """
    if not presents:
        return []
    inside = [t for t in presents if t <= presents[0] + window]
    return [b - a for a, b in itertools.pairwise(inside)]


def suite_fling(variant: str) -> None:
    """Frame pacing while flinging through the day: down six times, then back up."""
    launch(variant)
    time.sleep(1)
    layer = flutter_layer()
    intervals: list[float] = []
    for direction in ["down"] * 6 + ["up"] * 6:
        adb("shell", "dumpsys", "SurfaceFlinger", "--latency-clear", check=False)
        y1, y2 = (1800, 700) if direction == "down" else (700, 1800)
        adb("shell", "input", "swipe", "540", str(y1), "540", str(y2), "120")
        time.sleep(2.5)
        out = adb("shell", f"dumpsys SurfaceFlinger --latency '{layer}'")
        presents = [
            int(cols[1]) / 1e6
            for cols in (line.split() for line in out.splitlines()[1:])
            if len(cols) == 3 and int(cols[1]) > 0 and int(cols[1]) < 2**62
        ]
        intervals += motion_intervals(presents)
    janky = [i for i in intervals if i > 1.5 * 1000 / 60]
    report(
        "fling",
        variant,
        frame_ms=intervals,
        janky_frames=[float(len(janky))],
        janky_share_pct=[100 * len(janky) / max(1, len(intervals))],
    )


def suite_tabframes(variant: str) -> None:
    """Frame pacing while switching days: the frames of each tab tap's slide."""
    launch(variant)
    time.sleep(1)
    layer = flutter_layer()
    boxes = screen_boxes()
    intervals: list[float] = []
    worst: list[float] = []
    for name in ["thu", "fri", "sat", "fri"] * 3:
        adb("shell", "dumpsys", "SurfaceFlinger", "--latency-clear", check=False)
        tap(boxes[name])
        time.sleep(GAP)
        out = adb("shell", f"dumpsys SurfaceFlinger --latency '{layer}'")
        presents = [
            int(cols[1]) / 1e6
            for cols in (line.split() for line in out.splitlines()[1:])
            if len(cols) == 3 and 0 < int(cols[1]) < 2**62
        ]
        tap_frames = motion_intervals(presents)
        intervals += tap_frames
        worst.append(max(tap_frames, default=0.0))
    janky = [i for i in intervals if i > 1.5 * 1000 / 60]
    report(
        "tabframes",
        variant,
        frame_ms=intervals,
        worst_frame_ms=worst,
        janky_frames=[float(len(janky))],
    )


SUITES = {
    "cold": suite_cold,
    "star": suite_star,
    "search": suite_search,
    "days": suite_days,
    "jump": suite_jump,
    "fling": suite_fling,
    "tabframes": suite_tabframes,
}


def main() -> None:
    """Run the suites named on the command line for each variant."""
    suite, variants = sys.argv[1], sys.argv[2:]
    names = list(SUITES) if suite == "all" else suite.split(",")
    adb("shell", "settings", "put", "system", "font_scale", SCALE)
    try:
        for variant in variants:
            for name in names:
                SUITES[name](variant)
    finally:
        adb("shell", "settings", "put", "system", "font_scale", "1.0")
        adb("shell", "am", "force-stop", PKG)


if __name__ == "__main__":
    main()
