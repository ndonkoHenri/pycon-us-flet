"""Tests for the CoC tool's clearing and its hidden email (#762; MASK-05, O-7).

The tool runs in a real Flet session over the mock's transport, as in
``tests/test_staff_coc.py``, whose fixtures these share, with the clear's timer held
(``tests/scan_rig.py``). A result clears 15 s after the reply shows it, never counted
from the request; the background clears it and closes the name search, while an open
review keeps its notes; "Show email" reveals the reply's email outside the live region
until "Hide email", the next result or the clear; and no log line holds it (D-72).
"""

import asyncio
import logging
from typing import Any

import flet as ft
import pytest

from pycon_us.screens.staff_coc import CLEAR_AFTER
from pycon_us.services.errors import LOG_DATE_FORMAT, LOG_FORMAT, RedactingFormatter
from pycon_us.ui.coc_email import HIDE_EMAIL, SHOW_EMAIL
from pycon_us.ui.scan_result import READY, READY_BODY
from tests import scan_rig, test_coc_review, test_coc_search, test_staff_coc
from tests.harness import Shown
from tests.scan_rig import Timer, panel, pause, resume
from tests.test_coc_review import dialog, notes_text, scan, start, tap, type_notes
from tests.test_coc_search import open_find, rows, search_for, sheet, tap_row
from tests.test_staff_coc import Show, Switch

show, switch, stored = test_staff_coc.show, test_staff_coc.switch, test_staff_coc.stored
mock, clock, focused = (
    test_coc_review.mock,
    test_coc_review.clock,
    test_coc_review.focused,
)
no_wait, timer = test_coc_search.no_wait, scan_rig.timer

EMAIL = "margaret@example.com"
NOTES = "Hall B: shouted at a volunteer"
READY_PANEL = f"{READY}\n{READY_BODY}"
MARGARET = "Incident recorded\nMargaret Test\n1 on record\nScan 1"


async def record_margaret(shown: Shown) -> None:
    """Find Margaret Test by name and record an incident for her."""
    await open_find(shown)
    await search_for(shown, "mar test")
    task = await tap_row(shown, 0)
    await type_notes(shown, NOTES)
    await tap(shown, "coc.review.record")
    await asyncio.wait_for(task, 2)


def email_button(shown: Shown) -> ft.FilledTonalButton:
    """The result's "Show email" or "Hide email" button."""
    button = shown.node("coc.show_email").content
    assert isinstance(button, ft.FilledTonalButton)
    return button


def identifiers(shown: Shown) -> list[str]:
    """Every mounted semantics identifier."""
    return [str(n.identifier) for n in shown.find(ft.Semantics) if n.identifier]


async def test_a_record_clears_15_s_after_the_reply_shows_it(
    show: Show,
    switch: Switch,
    mock: Any,
    clock: list[float],
    timer: Timer,
    focused: list[int],
) -> None:
    """A reply 4 s late: the result shows when it arrives and stays a full 15 s."""
    shown = await show()
    scanning = await scan(shown)
    switch.gate = asyncio.Event()  # the capture call waits: a slow reply
    recording = await start(shown, "coc.review.record")
    clock[0] += 4
    await shown.settle()
    assert timer.waits == []  # nothing counts while the reply is out
    switch.gate.set()
    await asyncio.wait_for(recording, 2)
    await asyncio.wait_for(scanning, 2)
    assert panel(shown).startswith("Incident recorded\nGrace Sample")
    assert timer.waits == [CLEAR_AFTER] == [15]
    assert "Read just now. Clears in 15 seconds" in shown.texts()
    timer.ring()  # 15 s after the result showed
    await shown.settle()
    assert panel(shown) == READY_PANEL
    assert not shown.nodes("coc.show_email")


async def test_the_background_clears_the_result_and_closes_the_search(
    show: Show, mock: Any, timer: Timer, focused: list[int]
) -> None:
    """``pause``: the result and the open search go, the query with it."""
    shown = await show()
    await record_margaret(shown)
    assert panel(shown) == MARGARET
    await shown.click(email_button(shown))
    await open_find(shown)
    await search_for(shown, "linus")
    assert rows(shown)
    await pause(shown)
    assert panel(shown) == READY_PANEL
    assert sheet(shown) is None
    assert EMAIL not in shown.texts() and not shown.nodes("coc.email")
    await resume(shown)
    assert panel(shown) == READY_PANEL
    await open_find(shown)  # a new search starts empty
    assert rows(shown) == []


async def test_an_open_review_keeps_its_notes_in_the_background(
    show: Show, mock: Any, timer: Timer, focused: list[int]
) -> None:
    """Losing a half-written report is worse: the dialog and its notes stay."""
    shown = await show()
    scanning = await scan(shown)
    await type_notes(shown, NOTES)
    await pause(shown)
    await resume(shown)
    assert dialog(shown) is not None and notes_text(shown) == NOTES
    await tap(shown, "coc.review.record")
    await asyncio.wait_for(scanning, 2)
    assert panel(shown).startswith("Incident recorded")
    assert [i.notes for i in mock.incidents] == [NOTES]


async def test_show_email_reveals_it_outside_the_live_region_until_hidden(
    show: Show, mock: Any, timer: Timer, focused: list[int]
) -> None:
    """Hidden at first; Show email reveals it on its own node; Hide email hides it."""
    shown = await show()
    await record_margaret(shown)
    assert panel(shown) == MARGARET  # the email is never in the spoken words
    assert email_button(shown).content == SHOW_EMAIL
    assert EMAIL not in shown.texts()
    await shown.click(email_button(shown))
    assert email_button(shown).content == HIDE_EMAIL
    assert EMAIL in shown.texts()
    line = shown.node("coc.email")
    assert line.label == f"Email {EMAIL}" and not line.live_region
    assert EMAIL not in panel(shown)
    assert not any(EMAIL in i or "margaret" in i for i in identifiers(shown))
    await shown.click(email_button(shown))
    assert email_button(shown).content == SHOW_EMAIL
    assert EMAIL not in shown.texts() and not shown.nodes("coc.email")


async def test_the_clear_and_the_next_result_take_the_email_away(
    show: Show, mock: Any, timer: Timer, focused: list[int]
) -> None:
    """The reveal belongs to its result: the next one starts hidden, the clear drops it."""
    shown = await show()
    await record_margaret(shown)
    await shown.click(email_button(shown))
    scanning = await scan(shown)  # Grace Sample, from her badge
    await tap(shown, "coc.review.record")
    await asyncio.wait_for(scanning, 2)
    assert EMAIL not in shown.texts()
    assert email_button(shown).content == SHOW_EMAIL  # Grace's, hidden
    await shown.click(email_button(shown))
    assert "grace@example.com" in shown.texts()
    timer.ring()
    await shown.settle()
    assert panel(shown) == READY_PANEL
    assert not shown.nodes("coc.show_email") and not shown.nodes("coc.email")
    assert not any("@" in t for t in shown.texts())


async def test_not_recorded_has_no_email_button(
    show: Show, mock: Any, timer: Timer, focused: list[int]
) -> None:
    """Cancel: "Not recorded" carries no email, so there is nothing to show."""
    shown = await show()
    scanning = await scan(shown)
    await tap(shown, "coc.review.cancel")
    await asyncio.wait_for(scanning, 2)
    assert panel(shown).startswith("Not recorded")
    assert not shown.nodes("coc.show_email")


async def test_no_log_line_holds_the_email_or_the_code(
    show: Show,
    mock: Any,
    timer: Timer,
    focused: list[int],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """D-72: recording, revealing and clearing log nothing of the attendee."""
    caplog.set_level(logging.DEBUG, logger="pycon_us")
    shown = await show()
    await record_margaret(shown)
    await shown.click(email_button(shown))
    await pause(shown)
    await resume(shown)
    formatter = RedactingFormatter(LOG_FORMAT, LOG_DATE_FORMAT)
    lines = [formatter.format(r) for r in caplog.records]
    for text in (caplog.text, *lines):
        assert EMAIL not in text and "MOCK0004" not in text
        assert "margaret" not in text.lower() and NOTES not in text
    assert EMAIL not in str(shown.storage.prefs.values)  # pyright: ignore[reportAttributeAccessIssue]
