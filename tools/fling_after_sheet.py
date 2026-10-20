"""Repeat #346's row D on an Android emulator: a fling 0.33 to 0.6 s after the sheet closes.

``maestro/regression/fling_after_sheet.yaml`` cannot fling sooner than about 0.85 s after
tapping "Show N sessions" (one Maestro command after another), and at that pace both
``main`` and #346's build ran every fling in full. #346 lost its flings 0.33 to 0.6 s after
the tap. This driver sends the tap and the fling in one ``adb shell`` command, ``input tap``
then ``input swipe`` after ``--gap`` seconds (``GAP`` by default), so the fling lands
inside that window, and measures the real time from the tap to the fling on the device
(the launcher's ``TaplEvents`` log). It reaches row D's window; the Maestro flow covers
the same fling at Maestro's pace (``maestro/README.md``).

From the repo root, with the app installed on your own emulator (``maestro/README.md``)::

    uv run python -m tools.fling_after_sheet --serial emulator-5570 --trials 20

First it runs ``maestro/subflows/fling_setup.yaml`` with the local Maestro CLI: a fresh,
offline start with the fake clock at Friday 2026-05-15 14:01, on the Schedule
(``--no-setup`` skips it when the app is already there). Then, like the Maestro flow, it
reads the rest (where "Show N sessions" leaves the list, with no fling), runs three
control flings from there with no sheet just before them, and runs the trials: each one
starts on the now slot, shows Open space through the sheet, taps "Show N sessions" and
flings ``--gap`` seconds later. A trial is "moved" when it ended within three rows of
where a control ended (``near``, ``classify``), as in ``maestro/scripts/record_fling.js``. It
prints each trial and a summary, turns airplane mode off, and exits with 1 unless every
trial moved and every tap reached the button.

The screen is read with ``uiautomator dump``. Like Maestro, that makes Flutter report a
screen reader (F72), as it did in #346's own matrix.
"""

import argparse
import re
import statistics
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

ROWS = 4
"""Rows read from the top once a fling ends: two ends are near when one's top row is among the other's."""

CONTROLS = 3
"""Control flings before the trials, from the same rest."""

GAP = 0.5
"""Seconds between the tap and the fling: inside row D's 0.33 to 0.6 s.

``input`` itself adds only about 30 ms. Sooner than about 0.35 s the sheet is still
leaving and the fling does not scroll on any build (#346), later still on a busy host.
"""

SWIPE_MS = 80
"""The fling: an 80 ms swipe from 75 % to 25 % of the screen's height, as row D and the flow."""

SETUP_FLOW = (
    Path(__file__).resolve().parent.parent / "maestro" / "subflows" / "fling_setup.yaml"
)

SESSION_ID = re.compile(r"^schedule\.session\.")
SLOT = re.compile(r"(\d{1,2}:\d{2}) to ")
BOUNDS = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")
TOUCH = re.compile(
    r"(ACTION_DOWN|ACTION_UP).*?x\[0\]=([\d.]+), y\[0\]=([\d.]+).*?eventTime=(\d+)"
)


# ------------------------------------------------------------------ reading the screen


@dataclass(frozen=True)
class Node:
    """One element of a ``uiautomator dump``: its identifier, its label and its bounds."""

    ident: str
    label: str
    bounds: tuple[int, int, int, int]

    @property
    def center(self) -> tuple[int, int]:
        """The point a tap on this element goes to."""
        x1, y1, x2, y2 = self.bounds
        return (x1 + x2) // 2, (y1 + y2) // 2


def parse_nodes(xml: str) -> list[Node]:
    """Return the dump's elements that carry an identifier and show on screen."""
    nodes = []
    for element in ET.fromstring(xml).iter("node"):
        ident = element.get("resource-id", "")
        match = BOUNDS.match(element.get("bounds", ""))
        if not ident or not match or element.get("visible-to-user", "true") != "true":
            continue
        x1, y1, x2, y2 = map(int, match.groups())
        if x2 <= x1 or y2 <= y1:
            continue
        label = element.get("content-desc") or element.get("text") or ""
        nodes.append(Node(ident, label, (x1, y1, x2, y2)))
    return nodes


def session_rows(nodes: Sequence[Node]) -> list[str]:
    """Return the Schedule's session rows on screen, from the top, as their phrases (D-190)."""
    rows = sorted(
        (n for n in nodes if SESSION_ID.match(n.ident)), key=lambda n: n.bounds[1]
    )
    return [n.label for n in rows]


def slot_of(row: str) -> str:
    """Return a row's start time, the phrase's first "H:MM to" ("2:00"), or "" without one."""
    match = SLOT.search(row)
    return match.group(1) if match else ""


def tap_to_fling_ms(
    log: str, tap: tuple[int, int], fling: tuple[int, int]
) -> int | None:
    """Return the ms from the tap's ACTION_UP to the fling's ACTION_DOWN in ``TaplEvents`` lines.

    The launcher logs each touch with its point and ``eventTime``; the last tap at ``tap``
    followed by a touch down at ``fling`` is the pair. ``None`` when the log lacks either.
    """
    up = None
    gap = None
    for match in TOUCH.finditer(log):
        action, x, y, when = match.groups()
        point = (round(float(x)), round(float(y)))
        if action == "ACTION_UP" and point == tap:
            up = int(when)
        elif action == "ACTION_DOWN" and point == fling and up is not None:
            gap = int(when) - up
            up = None
    return gap


# ------------------------------------------------------------------ judging a fling


@dataclass(frozen=True)
class Control:
    """One control fling: the rest it started from, and the first rows once it ended."""

    rest: str
    rows: tuple[str, ...]

    @property
    def top(self) -> str:
        """The row on top once the fling ended ("" when none could be read)."""
        return self.rows[0] if self.rows else ""


def near(a: Sequence[str], b: Sequence[str]) -> bool:
    """Say whether two lists of first rows ended near each other.

    One's top row must be among the other's rows: with ``ROWS`` rows read, the two ends
    are no more than three rows apart, either way. The rows, not their slot: 3:00 PM,
    where a full fling ends, is about 20 rows deep with Open space shown.
    """
    return bool(a) and bool(b) and (a[0] in b or b[0] in a)


def controls_agree(controls: Sequence[Control]) -> bool:
    """Say whether the controls measure a full fling, as ``record_control.js`` does.

    Each must start from the first one's rest and leave it, and any two must be ``near``.
    """
    if not controls:
        return False
    for i, c in enumerate(controls):
        if not c.top or c.rest != controls[0].rest or c.rest in c.rows:
            return False
        if not all(near(c.rows, d.rows) for d in controls[:i]):
            return False
    return True


def classify(
    *,
    start_slot: str,
    trial_start: str,
    rows: Sequence[str],
    rest_row: str,
    controls: Sequence[Control],
) -> str:
    """Judge one trial from its first rows, by the rules of ``maestro/scripts/record_fling.js``.

    Returns "invalid" when the trial did not start on the now slot or no row could be
    read; "moved" when it is ``near`` a control; "none" when the rest's row is still on
    top, so the list did not scroll; "short" otherwise (rarely, past the controls).
    """
    if trial_start != start_slot or not rows:
        return "invalid"
    if any(near(rows, c.rows) for c in controls):
        return "moved"
    if rows[0] == rest_row:
        return "none"
    return "short"


@dataclass
class Tally:
    """The trials so far: how many of each kind, missed taps, and tap-to-fling times."""

    counts: dict[str, int] = field(
        default_factory=lambda: dict.fromkeys(("moved", "short", "none", "invalid"), 0)
    )
    missed: int = 0
    gaps: list[int] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """Every trial moved, at least one ran, and no tap missed the button."""
        lost = self.counts["short"] + self.counts["none"] + self.counts["invalid"]
        return self.counts["moved"] > 0 and lost == 0 and self.missed == 0

    def summary(self) -> str:
        """One line, the Maestro flow's summary plus the measured tap-to-fling times."""
        c = self.counts
        line = f"{c['moved']} moved, {c['short']} short, {c['none']} none, {c['invalid']} invalid, of {sum(c.values())}"
        line += f"; taps that missed the button, {self.missed}"
        if self.gaps:
            gaps = sorted(self.gaps)
            line += f"; tap to fling {gaps[0]}-{gaps[-1]} ms (median {statistics.median(gaps):.0f})"
        return line


# ------------------------------------------------------------------ the device


class Device:
    """An Android emulator driven through ``adb``."""

    def __init__(self, serial: str) -> None:
        """Talk to the device ``serial`` (``emulator-5570``)."""
        self.serial = serial
        size = self.shell("wm size").rsplit(" ", 1)[-1]
        self.width, self.height = map(int, size.split("x"))

    def shell(self, command: str) -> str:
        """Run ``command`` in the device's shell and return what it printed."""
        result = subprocess.run(
            ["adb", "-s", self.serial, "shell", command],
            capture_output=True,
            text=True,
            check=True,
            timeout=120,
        )
        return result.stdout.strip()

    def nodes(self) -> list[Node]:
        """Read the screen with ``uiautomator dump``, which fails now and then on a busy emulator.

        The first read after a pause can come back without the app's elements, while
        Flutter builds its accessibility tree: callers wait for what they need.
        """
        for attempt in range(3):
            try:
                self.shell("uiautomator dump /sdcard/fling.xml > /dev/null")
                return parse_nodes(self.shell("cat /sdcard/fling.xml"))
            except subprocess.CalledProcessError, ET.ParseError:
                if attempt == 2:
                    raise
                time.sleep(1)
        return []

    def find(self, ident: str, timeout: float = 30) -> Node | None:
        """Wait up to ``timeout`` seconds for the element ``ident``; ``None`` if it never shows."""
        deadline = time.monotonic() + timeout
        while True:
            for node in self.nodes():
                if node.ident == ident:
                    return node
            if time.monotonic() > deadline:
                return None
            time.sleep(0.5)

    def tap(self, ident: str) -> None:
        """Tap the element ``ident`` once it shows."""
        node = self.find(ident)
        if node is None:
            raise RuntimeError(f"{ident} never showed")
        self.shell("input tap {} {}".format(*node.center))

    def gone(self, ident: str, timeout: float = 30) -> bool:
        """Wait up to ``timeout`` seconds for the element ``ident`` to leave the screen."""
        deadline = time.monotonic() + timeout
        while any(n.ident == ident for n in self.nodes()):
            if time.monotonic() > deadline:
                return False
            time.sleep(0.5)
        return True

    def rows_when_still(self) -> list[str]:
        """Read the session rows once two reads in a row agree: the list has stopped."""
        rows = session_rows(self.nodes())
        for _ in range(10):
            time.sleep(0.5)
            again = session_rows(self.nodes())
            if again == rows:
                return rows
            rows = again
        return rows

    @property
    def fling_points(self) -> tuple[tuple[int, int], tuple[int, int]]:
        """The fling's start and end: from 75 % to 25 % of the height, mid-width."""
        x = self.width // 2
        return (x, self.height * 3 // 4), (x, self.height // 4)


# ------------------------------------------------------------------ the steps


def to_now(device: Device) -> None:
    """Put the Schedule back on the now slot: tap the Now button when it shows (D-192)."""
    if any(n.ident == "schedule.jump_now" for n in device.nodes()):
        device.tap("schedule.jump_now")
        time.sleep(1.5)


def open_sheet_with_open_space(device: Device) -> Node:
    """Open the filter sheet, tap the Open space chip, and return "Show N sessions" at rest."""
    device.tap("schedule.filter")
    device.tap("schedule.filter.open-space")
    if device.find("schedule.filter.show") is None:
        raise RuntimeError('"Show N sessions" never showed')
    time.sleep(1.0)  # the tap goes to a place: the sheet must have finished sliding in
    show = device.find("schedule.filter.show")
    if show is None:
        raise RuntimeError('"Show N sessions" left before the tap')
    return show


def toggle_open_space(device: Device) -> None:
    """Show or hide Open space through the sheet, as ``subflows/toggle_open_space.yaml``."""
    open_sheet_with_open_space(device)
    device.tap("schedule.filter.show")
    if not device.gone("schedule.filter.show"):
        raise RuntimeError("the filter sheet did not close")
    time.sleep(1.5)


def fling(device: Device) -> None:
    """The control's fling, alone."""
    (x1, y1), (x2, y2) = device.fling_points
    device.shell(f"input swipe {x1} {y1} {x2} {y2} {SWIPE_MS}")


def tap_then_fling(device: Device, show: Node, gap: float) -> None:
    """Tap "Show N sessions", then fling ``gap`` seconds later, in one shell command."""
    (x1, y1), (x2, y2) = device.fling_points
    x, y = show.center
    device.shell(
        f"input tap {x} {y}; sleep {gap}; input swipe {x1} {y1} {x2} {y2} {SWIPE_MS}"
    )


def run(device: Device, trials: int, gap: float) -> Tally:
    """Read the start, the rest and the controls, then run the trials and tally them."""
    if device.find("schedule.filter", timeout=60) is None:
        raise RuntimeError("the Schedule is not on screen")
    start_rows = device.rows_when_still()
    start_slot = slot_of(start_rows[0]) if start_rows else ""
    print(f"start: the now slot, {start_slot or '-'}")

    controls: list[Control] = []
    for _ in range(CONTROLS):
        to_now(device)
        toggle_open_space(device)
        rest = device.rows_when_still()
        # The control flings a while after the sheet has gone, never right after it.
        time.sleep(2.0)
        fling(device)
        time.sleep(2.0)
        control = Control(
            rest[0] if rest else "", tuple(device.rows_when_still()[:ROWS])
        )
        controls.append(control)
        print(
            f'control {len(controls)}: from "{control.rest}" to "{control.top or "-"}"'
        )
        toggle_open_space(device)
    if not controls_agree(controls):
        raise RuntimeError(
            "the controls disagree, or one did not move: nothing to hold the trials to"
        )
    rest_row = controls[0].rest

    tally = Tally()
    for trial in range(1, trials + 1):
        to_now(device)
        start = device.rows_when_still()
        trial_start = slot_of(start[0]) if start else ""
        show = open_sheet_with_open_space(device)
        device.shell("logcat -c")
        tap_then_fling(device, show, gap)
        time.sleep(2.0)
        if not device.gone("schedule.filter.show", timeout=5):
            tally.missed += 1
            print(f"trial {trial}: the tap missed the button")
            device.tap("schedule.filter.show")
            device.gone("schedule.filter.show")
            toggle_open_space(device)
            continue
        rows = device.rows_when_still()[:ROWS]
        top_row = rows[0] if rows else ""
        kind = classify(
            start_slot=start_slot,
            trial_start=trial_start,
            rows=rows,
            rest_row=rest_row,
            controls=controls,
        )
        tally.counts[kind] += 1
        ms = tap_to_fling_ms(
            device.shell("logcat -d -s TaplEvents"), show.center, device.fling_points[0]
        )
        if ms is not None:
            tally.gaps.append(ms)
        print(
            f'trial {trial}: {kind} (tap to fling {ms if ms is not None else "?"} ms; top row "{top_row or "-"}")'
        )
        toggle_open_space(device)
    return tally


def main(argv: Sequence[str] | None = None) -> int:
    """Run the trials on one device; return 0 when every fling ran in full, else 1."""
    parser = argparse.ArgumentParser(description="Repeat #346's row D through adb.")
    parser.add_argument(
        "--serial", required=True, help="your own emulator, e.g. emulator-5570"
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=20,
        help="flings after the sheet (default 20, at most about 30)",
    )
    parser.add_argument(
        "--gap",
        type=float,
        default=GAP,
        help=f"seconds slept between the tap and the fling (default {GAP})",
    )
    parser.add_argument(
        "--no-setup",
        action="store_true",
        help="the app is already on the Schedule at 14:01",
    )
    args = parser.parse_args(argv)

    device = Device(args.serial)
    try:
        if not args.no_setup:
            subprocess.run(
                ["maestro", "--device", args.serial, "test", str(SETUP_FLOW)],
                check=True,
            )
        tally = run(device, args.trials, args.gap)
    finally:
        device.shell("cmd connectivity airplane-mode disable")
    print(f"flings after the sheet, {tally.summary()}")
    return 0 if tally.passed else 1


if __name__ == "__main__":
    sys.exit(main())
