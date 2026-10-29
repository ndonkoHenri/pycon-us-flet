"""Tests for the scan screen's clearing, ``ui/scan_clear.py`` (#762; MASK-05, O-7).

The screen runs around the rig's recording handler (``tests/scan_rig.py``) with its
clock and the clear's timer held. A tool that asks for it has its result cleared
``clear_after`` seconds after the result shows and when the app goes to the
background; the panel then says "Ready to scan" as no live region, so the clear is
not said. A tool that asks for neither keeps its result as before.
"""

import asyncio

import flet as ft
import pytest

from pycon_us.core.badges import ScanOutcome, ScanResult
from pycon_us.ui.scan_result import READY, READY_BODY, age_line, post
from tests import harness, scan_rig
from tests.scan_rig import Rig, Show, Timer, enter, panel, pause, resume

rig, show, timer = scan_rig.rig, scan_rig.show, scan_rig.timer

READY_PANEL = f"{READY}\n{READY_BODY}"


def ages(shown: harness.Shown) -> list[str]:
    """The age lines on screen: "Read 3 seconds ago…"."""
    return [t for t in shown.texts() if t.startswith("Read ")]


async def test_the_timer_starts_when_the_result_shows_not_when_the_scan_leaves(
    show: Show, rig: Rig, timer: Timer
) -> None:
    """A reply 4 s late: nothing counts while it is out; then 15 s from the result."""
    rig.clear_after = 15
    rig.gate = asyncio.Event()
    shown = await show()
    scanning = asyncio.create_task(enter(shown, "MOCK0001:v1"))
    await shown.settle()
    rig.now += 4  # the handler's reply takes 4 s
    await shown.settle()
    assert timer.waits == []  # no result yet, so nothing to clear
    rig.gate.set()
    await asyncio.wait_for(scanning, 2)
    assert panel(shown) == "Checked in\nAda Lovelace\nScan 1"
    assert timer.waits == [15]
    assert ages(shown) == ["Read just now. Clears in 15 seconds"]
    timer.ring()  # 15 s after the result showed
    await shown.settle()
    assert panel(shown) == READY_PANEL
    assert ages(shown) == []


async def test_a_new_result_restarts_the_timer(
    show: Show, rig: Rig, timer: Timer
) -> None:
    """Each result gets its own 15 s, and the serials go on counting after a clear."""
    rig.clear_after = 15
    shown = await show()
    await enter(shown, "MOCK0001:v1")
    rig.result = ScanResult(ScanOutcome.ACCEPTED, "Checked in", "Grace Hopper")
    await enter(shown, "MOCK0002:v2")
    assert timer.waits == [15, 15]
    assert panel(shown) == "Checked in\nGrace Hopper\nScan 2"
    timer.ring()
    await shown.settle()
    assert panel(shown) == READY_PANEL
    await enter(shown, "MOCK0003:v3")  # a serial is never reused after a clear
    assert panel(shown) == "Checked in\nGrace Hopper\nScan 3"


async def test_the_background_clears_the_result(
    show: Show, rig: Rig, timer: Timer
) -> None:
    """``pause`` clears at once; the resume shows "Ready to scan"; scanning goes on."""
    rig.clear_in_background = True
    shown = await show()
    await enter(shown, "MOCK0001:v1")
    await pause(shown)
    assert panel(shown) == READY_PANEL
    await resume(shown)
    assert panel(shown) == READY_PANEL
    rig.now += 5
    await enter(shown, "MOCK0002:v2")
    assert panel(shown) == "Checked in\nAda Lovelace\nScan 2"
    await pause(shown)  # and again on the next pause
    assert panel(shown) == READY_PANEL
    assert timer.waits == []  # no clear_after: no timer


async def test_a_tool_that_asks_for_neither_keeps_its_result(
    show: Show, rig: Rig, timer: Timer
) -> None:
    """The other tools' panels are unchanged: no timer, nothing cleared on pause."""
    shown = await show()
    await enter(shown, "MOCK0001:v1")
    await pause(shown)
    await resume(shown)
    assert panel(shown) == "Checked in\nAda Lovelace\nScan 1"
    assert timer.waits == []
    assert ages(shown) == ["Read just now"]


@pytest.mark.parametrize(
    ("age", "words"),
    [
        (0, "Read just now. Clears in 15 seconds"),
        (14.2, "Read 14 seconds ago. Clears in 1 second"),
        (15, "Read 15 seconds ago. Clears in 0 seconds"),
    ],
)
def test_the_countdown_is_in_words(age: float, words: str) -> None:
    """The countdown is words in the age line, never colour or motion alone."""
    line = age_line(age, 15)
    assert isinstance(line, ft.Semantics) and isinstance(line.content, ft.Text)
    assert line.content.value == words


def test_a_posted_result_is_handed_over_once() -> None:
    """The screen takes a posted result, so the tool's state keeps no copy."""
    result = ScanResult(ScanOutcome.RECORDED, "Incident recorded", email="a@b.example")
    posted = post(None, result)
    assert posted.serial == 1 and post(posted, result).serial == 2
    assert posted.take() is result
    assert posted.take() is None
