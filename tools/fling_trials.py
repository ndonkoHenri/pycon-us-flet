"""Read and judge the trials of ``tools/fling_after_sheet.py``, #346's row D through adb.

What the driver computes, apart from the device: the Schedule's rows in a
``uiautomator dump``, the time from the tap to the fling in the launcher's ``TaplEvents``
log, and each trial's kind by the rules of ``maestro/scripts/record_fling.js``, plus row
D's own two: a trial counts only when it started on the now slot (``NOW_SLOT``) and its
measured tap-to-fling time is inside row D's window (``WINDOW_MS``).
"""

import re
import statistics
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass, field

ROWS = 4
"""Rows read from the top once a fling ends: two ends are near when one's top row is among the other's."""

NOW_SLOT = "2:00"
"""The now slot at the setup's fake clock, Friday 14:01: where the run and every trial start."""

WINDOW_MS = (330, 600)
"""Row D's window, both ends included: #346 lost its flings 330 to 600 ms after the tap."""

KINDS = ("moved", "short", "none", "invalid", "off window")
"""A trial's kinds, in the summary's order (``classify``)."""

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


def in_window(ms: int | None) -> bool:
    """Say whether a measured tap-to-fling time is inside row D's window; ``None`` is not."""
    return ms is not None and WINDOW_MS[0] <= ms <= WINDOW_MS[1]


def classify(
    *,
    trial_start: str,
    gap_ms: int | None,
    rows: Sequence[str],
    rest_row: str,
    controls: Sequence[Control],
) -> str:
    """Judge one trial from its start, its measured gap and its first rows.

    Returns "invalid" when the trial did not start on the now slot or no row could be
    read; "off window" when its tap-to-fling time was not measured or fell outside row
    D's window, so it says nothing about row D whatever the fling did. Otherwise, by the
    rules of ``maestro/scripts/record_fling.js``: "moved" when it is ``near`` a control;
    "none" when the rest's row is still on top, so the list did not scroll; "short"
    otherwise (rarely, past the controls).
    """
    if trial_start != NOW_SLOT or not rows:
        return "invalid"
    if not in_window(gap_ms):
        return "off window"
    if any(near(rows, c.rows) for c in controls):
        return "moved"
    if rows[0] == rest_row:
        return "none"
    return "short"


@dataclass
class Tally:
    """The trials so far: how many of each kind, missed taps, and every measured tap-to-fling time."""

    counts: dict[str, int] = field(default_factory=lambda: dict.fromkeys(KINDS, 0))
    missed: int = 0
    gaps: list[int] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """Every trial moved inside row D's window, at least one ran, and no tap missed the button."""
        others = sum(self.counts.values()) - self.counts["moved"]
        return self.counts["moved"] > 0 and others == 0 and self.missed == 0

    def summary(self) -> str:
        """One line: the Maestro flow's summary, the off-window trials, and every measured time."""
        line = ", ".join(f"{self.counts[kind]} {kind}" for kind in KINDS)
        line += f", of {sum(self.counts.values())}"
        line += f"; taps that missed the button, {self.missed}"
        if self.gaps:
            gaps = sorted(self.gaps)
            line += f"; tap to fling {gaps[0]}-{gaps[-1]} ms (median {statistics.median(gaps):.0f})"
        return line
