"""Tests for the CoC review, `ui/coc_review.py` and its dialog, on the CoC tool (#760).

The tool runs in a real Flet session over the mock's transport, as in
`tests/test_staff_coc.py`, whose fixtures these share. A scan opens the review and
the scan screen awaits it, so each test starts the scan as a task, works the dialog
as Flutter reports it (the field's text, then the event), then awaits the scan.
Record sends exactly one forced incident (D-430); Cancel and Back send none; errors
keep the dialog and its notes (D-410); a code the directory lacks is reviewed all the
same (D-434); and the notes never reach a log (D-72).
"""

import asyncio
import logging
import time
from collections.abc import Iterator
from typing import Any, cast

import flet as ft
import pytest
from flet.utils.object_model import patch_dataclass

from pycon_us.core.badges import ScanOutcome
from pycon_us.prefs import Prefs
from pycon_us.screens.staff_coc import REVIEW_OPEN
from pycon_us.ui import coc_review, scan_screen
from pycon_us.ui.coc_review import MAYBE_RECORDED, NO_CONNECTION
from pycon_us.ui.coc_review_dialog import (
    NOT_LISTED,
    RECORD,
    RECORD_ANYWAY,
    RECORDING,
    TITLE,
)
from pycon_us.ui.scan_result import fill_of
from pycon_us.ui.scan_screen import NOT_AVAILABLE
from tests import test_staff_coc
from tests.fakes import MemorySemantics
from tests.harness import Shown
from tests.scan_rig import panel
from tests.test_high_contrast import AAA_TEXT
from tests.test_staff_coc import ATTENDEES, Show, Switch, coc
from tests.test_theme import AA_TEXT, NEUTRAL_RAMP, contrast_ratio
from tools.mock_api.state import MockState
from tools.mock_api.transport import mock_transport

show, switch, stored = test_staff_coc.show, test_staff_coc.switch, test_staff_coc.stored

CAPTURE = "/2026/api/v1/mask_violations/capture/"
GRACE = "MOCK0002:x"
NOTES = "Hall B, 10:05: shouted at a volunteer"


@pytest.fixture
def mock(switch: Switch) -> MockState:
    """The mock's state behind `switch`, so a test reads its incidents and faults."""
    state = MockState.from_seed(now=time.time)
    switch.inner = mock_transport(state)
    return state


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """The scan screen's clock, held at 100 s until a test moves it on."""
    now = [100.0]
    monkeypatch.setattr(scan_screen, "clock", lambda: now[0])
    return now


@pytest.fixture
def focused(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Counts the badge field's focus calls (the dialog's field is never focused)."""
    calls = [0]

    async def focus(_: ft.TextField) -> None:
        calls[0] += 1

    monkeypatch.setattr(ft.TextField, "focus", focus)
    return calls


def helper(shown: Shown) -> str | None:
    """The badge field's line: why scanning is paused, or None."""
    return cast(str | None, badge_field(shown).helper)


def badge_field(shown: Shown) -> ft.TextField:
    """The scan screen's badge code field (the closed dialog's field stays in the page)."""
    return cast(ft.TextField, shown.node("scan.entry").content)


async def enter(shown: Shown, text: str) -> None:
    """Type `text` in the badge field as Flutter reports it, then press Enter."""
    field = badge_field(shown)
    shown.session.apply_patch(field._i, {"value": text})
    await shown.event(field, "change", text)
    await shown.event(field, "submit", text)


def dialog(shown: Shown) -> ft.AlertDialog | None:
    """The open review dialog, or None."""
    dialogs = shown.session.page._dialogs.controls  # pyright: ignore[reportPrivateUsage]
    found = [d for d in dialogs if isinstance(d, ft.AlertDialog) and d.open]
    assert len(found) <= 1
    return found[0] if found else None


def walk(control: Any) -> Iterator[Any]:
    """Every control under `control`: its title, content, controls and actions."""
    yield control
    for name in ("title", "content"):
        child = getattr(control, name, None)
        if isinstance(child, ft.BaseControl):
            yield from walk(child)
    for name in ("controls", "actions"):
        for child in getattr(control, name, None) or ():
            if isinstance(child, ft.BaseControl):
                yield from walk(child)


def nodes(shown: Shown, identifier: str) -> list[ft.Semantics]:
    """The open dialog's semantics nodes named `identifier`."""
    current = dialog(shown)
    assert current is not None
    return [
        c
        for c in walk(current)
        if isinstance(c, ft.Semantics) and c.identifier == identifier
    ]


def in_dialog(shown: Shown, identifier: str) -> Any:
    """The control under the open dialog's semantics node `identifier`."""
    (node,) = nodes(shown, identifier)
    return node.content


def texts(shown: Shown) -> list[str]:
    """Every text in the open dialog."""
    current = dialog(shown)
    assert current is not None
    return [str(c.value) for c in walk(current) if isinstance(c, ft.Text)]


def record_button(shown: Shown) -> ft.FilledButton:
    """The dialog's Record button."""
    button = in_dialog(shown, "coc.review.record")
    assert isinstance(button, ft.FilledButton)
    return button


def problem(shown: Shown) -> str | None:
    """The dialog's problem line, or None; it is a live region (ux.md §9)."""
    found = nodes(shown, "coc.review.problem")
    if not found:
        return None
    (node,) = found
    assert isinstance(node.content, ft.Text)
    return str(node.content.value)


async def scan(shown: Shown, text: str = GRACE) -> asyncio.Task[None]:
    """Start a scan of `text`, which waits on the review it opens, until it opens.

    It returns sooner when the scan ends without one (a dropped or held code).
    """
    task = asyncio.create_task(enter(shown, text))
    for _ in range(50):
        await shown.settle()
        if task.done() or dialog(shown) is not None:
            break
    return task


async def type_notes(shown: Shown, text: str) -> None:
    """Type the notes, as Flutter reports them."""
    field = in_dialog(shown, "coc.review.notes")
    patch_dataclass(field, {"value": text})
    await shown.event(field, "change", text)


async def tap(shown: Shown, identifier: str) -> None:
    """Tap the dialog's button `identifier`."""
    await shown.click(in_dialog(shown, identifier))


async def start(shown: Shown, identifier: str) -> asyncio.Task[None]:
    """Tap the dialog's button `identifier` as a task: its call waits on a gate."""
    task = asyncio.create_task(tap(shown, identifier))
    await shown.settle()
    return task


def notes_text(shown: Shown) -> str:
    """The notes field's text as the dialog holds it."""
    return str(in_dialog(shown, "coc.review.notes").value or "")


async def test_a_scan_opens_the_review_and_pauses_scanning(
    show: Show, mock: MockState, switch: Switch
) -> None:
    """`MOCK0002`: Grace Sample, "Badge: Grace S.", 1 incident; nothing sent yet."""
    shown = await show()
    task = await scan(shown)
    assert texts(shown)[:4] == [
        TITLE,
        "Grace Sample",
        "Badge: Grace S.",
        "1 incident on record",
    ]
    title = cast(ft.AlertDialog, dialog(shown)).title
    assert isinstance(title, ft.Semantics) and title.heading_level == 1
    current = cast(ft.AlertDialog, dialog(shown))
    assert current.modal and current.scrollable
    field = in_dialog(shown, "coc.review.notes")
    assert (field.label, field.hint_text, field.max_length) == (
        "What happened?",
        "What happened? Where? Witnesses?",
        2000,
    )
    assert field.value == "" and field.multiline
    (count,) = nodes(shown, "coc.review.count")
    assert count.label == "1 incident on record"  # one node, its icon decorative
    assert helper(shown) == REVIEW_OPEN
    assert switch.paths == [ATTENDEES]  # reviewed, not recorded
    await tap(shown, "coc.review.cancel")
    await asyncio.wait_for(task, 2)


async def test_record_sends_one_incident_with_the_notes_and_counts_it(
    show: Show, mock: MockState, switch: Switch, clock: list[float], focused: list[int]
) -> None:
    """Record: one forced incident with the notes; "2 on record"; the row follows."""
    shown = await show()
    task = await scan(shown)
    await type_notes(shown, NOTES)
    await tap(shown, "coc.review.record")
    await asyncio.wait_for(task, 2)
    assert dialog(shown) is None
    assert [(i.access_code, i.notes, i.forced) for i in mock.incidents] == [
        ("MOCK0002", NOTES, True)
    ]
    assert switch.paths.count(CAPTURE) == 1
    assert panel(shown) == "Incident recorded\nGrace Sample\n2 on record\nScan 1"
    assert helper(shown) is None and focused[0] >= 1  # back in the field
    clock[0] += 5  # past the cooldown: the same badge opens a fresh review
    task = await scan(shown)
    assert "2 incidents on record" in texts(shown)  # the directory row followed
    assert notes_text(shown) == ""  # the last notes are gone
    await tap(shown, "coc.review.cancel")
    await asyncio.wait_for(task, 2)


async def test_a_double_tap_on_record_sends_one(
    show: Show, mock: MockState, switch: Switch
) -> None:
    """While the call is out Record is disabled with "Recording…"; a second tap sends none."""
    shown = await show()
    task = await scan(shown)
    switch.gate = asyncio.Event()
    first = await start(shown, "coc.review.record")
    button = record_button(shown)
    assert button.disabled and RECORDING in texts(shown)
    assert not in_dialog(shown, "coc.review.cancel").disabled  # Cancel stays
    await shown.click(button)
    switch.gate.set()
    await asyncio.wait_for(first, 2)
    await asyncio.wait_for(task, 2)
    assert switch.paths.count(CAPTURE) == 1
    assert len(mock.incidents) == 1


@pytest.mark.parametrize("how", ["cancel", "back"])
async def test_cancel_and_back_record_nothing(
    show: Show,
    mock: MockState,
    switch: Switch,
    focused: list[int],
    how: str,
) -> None:
    """Cancel, or Back's dismissal (D-208): "Not recorded", nothing sent, focus back."""
    shown = await show()
    task = await scan(shown)
    await type_notes(shown, NOTES)
    before = focused[0]
    if how == "cancel":
        await tap(shown, "coc.review.cancel")
    else:
        await shown.event(cast(ft.AlertDialog, dialog(shown)), "dismiss")
    await asyncio.wait_for(task, 2)
    assert dialog(shown) is None
    assert panel(shown) == "Not recorded\nGrace Sample\nScan 1"
    assert switch.paths == [ATTENDEES] and mock.incidents == []
    assert helper(shown) is None and focused[0] > before


async def test_a_late_dismissal_of_the_last_dialog_leaves_the_next_open(
    show: Show, mock: MockState, clock: list[float]
) -> None:
    """A cancelled dialog's late dismissal leaves the next review open.

    Flutter reports it once Grace's route has closed, after Linus's review opened;
    only Linus's own Cancel closes his.
    """
    shown = await show()
    task = await scan(shown)
    grace = cast(ft.AlertDialog, dialog(shown))
    await tap(shown, "coc.review.cancel")
    await asyncio.wait_for(task, 2)
    clock[0] += 5
    task = await scan(shown, "MOCK0003:x")
    assert texts(shown)[1].startswith("Linus")
    await shown.event(grace, "dismiss")  # Grace's route has finished closing
    assert dialog(shown) is not None and not task.done()
    await tap(shown, "coc.review.cancel")
    await asyncio.wait_for(task, 2)
    assert panel(shown).startswith("Not recorded\nLinus")


async def test_a_held_badge_and_a_submit_while_open_open_one_review(
    show: Show, mock: MockState, switch: Switch, clock: list[float]
) -> None:
    """A submit while the review is open is dropped with its text; then the cooldown."""
    shown = await show()
    task = await scan(shown)
    await enter(shown, "MOCK0003:x")  # a HID scanner typing while the review is open
    assert badge_field(shown).value == ""  # dropped with its text (D-471)
    assert texts(shown)[1] == "Grace Sample"  # still Grace's review, one dialog
    await tap(shown, "coc.review.cancel")
    await asyncio.wait_for(task, 2)
    clock[0] += 3  # within 4 s of the accept
    await enter(shown, GRACE)  # held: cleared without a word
    assert dialog(shown) is None
    assert panel(shown).startswith("Not recorded")
    assert switch.paths == [ATTENDEES]


async def test_a_code_not_in_the_directory_is_reviewed_and_a_404_says_so(
    show: Show, mock: MockState
) -> None:
    """D-434: the code and "Not in the loaded attendee list"; the mock's 404 in it."""
    shown = await show()
    task = await scan(shown, "NOPE0001:x")
    assert texts(shown)[1:3] == ["NOPE0001", NOT_LISTED]
    await type_notes(shown, NOTES)
    await tap(shown, "coc.review.record")
    assert problem(shown) == "Not recorded. Unknown attendee access code."
    assert notes_text(shown) == NOTES and not record_button(shown).disabled
    assert mock.incidents == []
    await tap(shown, "coc.review.cancel")
    await asyncio.wait_for(task, 2)


async def test_a_lost_reply_may_be_recorded_and_offers_record_anyway(
    show: Show, mock: MockState
) -> None:
    """`lost_response`: "may have been recorded", Record anyway; never a resend."""
    shown = await show()
    task = await scan(shown)
    await type_notes(shown, NOTES)
    mock.faults.inject("lost_response")
    await tap(shown, "coc.review.record")
    assert problem(shown) == MAYBE_RECORDED
    assert RECORD_ANYWAY in texts(shown) and RECORD not in texts(shown)
    assert notes_text(shown) == NOTES
    assert len(mock.incidents) == 1  # it did land; nothing was sent again
    await tap(shown, "coc.review.record")  # the staff member's own choice
    await asyncio.wait_for(task, 2)
    assert len(mock.incidents) == 2
    assert panel(shown).startswith("Incident recorded\nGrace Sample\n3 on record")


@pytest.mark.parametrize("then", ["no connection", "cancel"])
async def test_after_a_lost_reply_nothing_says_it_was_not_recorded(
    show: Show, mock: MockState, then: str
) -> None:
    """After a lost reply (D-410), nothing says the incident was not recorded.

    A later "no connection" keeps "may have been recorded" and Record anyway, and
    Cancel says "Not confirmed", never "Not recorded".
    """
    shown = await show()
    task = await scan(shown)
    mock.faults.inject("lost_response")
    await tap(shown, "coc.review.record")
    if then == "no connection":
        mock.faults.inject("connect")
        await tap(shown, "coc.review.record")
        assert problem(shown) == MAYBE_RECORDED
        assert RECORD_ANYWAY in texts(shown) and RECORD not in texts(shown)
    await tap(shown, "coc.review.cancel")
    await asyncio.wait_for(task, 2)
    assert len(mock.incidents) == 1
    assert panel(shown).startswith(f"Not confirmed\nGrace Sample\n{MAYBE_RECORDED}")


async def test_no_connection_records_nothing_and_keeps_the_notes(
    show: Show, mock: MockState
) -> None:
    """A refused connection: "No connection. Nothing was recorded.", Record again."""
    shown = await show()
    task = await scan(shown)
    await type_notes(shown, NOTES)
    mock.faults.inject("connect")
    await tap(shown, "coc.review.record")
    assert problem(shown) == NO_CONNECTION
    assert RECORD in texts(shown) and notes_text(shown) == NOTES
    assert mock.incidents == []
    await tap(shown, "coc.review.record")
    await asyncio.wait_for(task, 2)
    assert len(mock.incidents) == 1 and panel(shown).startswith("Incident recorded")


async def test_cancel_while_recording_says_not_confirmed_and_still_counts(
    show: Show, mock: MockState, switch: Switch, clock: list[float]
) -> None:
    """Cancel while the call is out: "Not confirmed"; the reply still sets the count."""
    shown = await show()
    task = await scan(shown)
    switch.gate = asyncio.Event()
    recording = await start(shown, "coc.review.record")
    await tap(shown, "coc.review.cancel")
    await asyncio.wait_for(task, 2)
    assert panel(shown) == f"Not confirmed\nGrace Sample\n{MAYBE_RECORDED}\nScan 1"
    switch.gate.set()
    await asyncio.wait_for(recording, 2)
    clock[0] += 5
    task = await scan(shown)
    assert "2 incidents on record" in texts(shown)
    await tap(shown, "coc.review.cancel")
    await asyncio.wait_for(task, 2)


async def test_leaving_the_tool_with_the_review_open_ends_the_scan(
    show: Show, mock: MockState
) -> None:
    """The flag revoked under the dialog: it closes, and the waiting scan ends."""
    account = coc()
    shown = await show(account)
    task = await scan(shown)
    account.mask_violation = False
    await shown.settle()
    await asyncio.wait_for(task, 1)
    assert dialog(shown) is None
    assert NOT_AVAILABLE in shown.texts()
    assert mock.incidents == []


async def test_the_problem_is_announced_where_there_are_no_live_regions(
    show: Show, mock: MockState, monkeypatch: pytest.MonkeyPatch
) -> None:
    """iOS: the problem line is announced, and is no live region (said once)."""

    def announcing(**kw):
        return Prefs(announcements=True, **kw)

    monkeypatch.setattr(test_staff_coc, "Prefs", announcing)
    shown = await show()
    task = await scan(shown)
    mock.faults.inject("connect")
    await tap(shown, "coc.review.record")
    said = cast(MemorySemantics, shown.services.semantics).announced
    assert NO_CONNECTION in said
    (node,) = nodes(shown, "coc.review.problem")
    assert not node.live_region
    await tap(shown, "coc.review.cancel")
    await asyncio.wait_for(task, 2)


async def test_the_notes_never_reach_a_log(
    show: Show, mock: MockState, caplog: pytest.LogCaptureFixture
) -> None:
    """D-72: recording, failing and recording again log no notes, name or code.

    At the app's level, INFO (`setup_logging()`), and the app's own loggers at DEBUG;
    Flet's DEBUG lines echo every event's data, typed text included, only under
    `flet run -vv`.
    """
    caplog.set_level(logging.INFO)
    caplog.set_level(logging.DEBUG, logger="pycon_us")
    shown = await show()
    task = await scan(shown)
    await type_notes(shown, NOTES)
    mock.faults.inject("lost_response")
    await tap(shown, "coc.review.record")
    await tap(shown, "coc.review.record")
    await asyncio.wait_for(task, 2)
    logged = caplog.text
    assert NOTES not in logged and "Grace" not in logged and "MOCK0002" not in logged


def test_the_new_outcomes_are_neutral_and_read_in_every_scheme() -> None:
    """Recorded and Not recorded take the neutral pair: AA in light and dark, 7:1 in HC."""
    from pycon_us.theme_hc import HC_DARK, HC_LIGHT

    for outcome in (ScanOutcome.RECORDED, ScanOutcome.NOT_RECORDED):
        for high_contrast in (False, True):
            assert fill_of(outcome, high_contrast=high_contrast, dimmed=False) == (
                ft.Colors.ON_SURFACE,
                ft.Colors.SURFACE_CONTAINER_HIGHEST,
            )
    for ramp in NEUTRAL_RAMP.values():
        assert contrast_ratio(ramp["onSurface"], ramp["surfaceContainerHighest"]) >= (
            AA_TEXT
        )
    for scheme in (HC_LIGHT, HC_DARK):
        ink, fill = str(scheme.on_surface), str(scheme.surface_container_highest)
        assert contrast_ratio(ink, fill) >= AAA_TEXT


def test_problem_words_follow_the_error() -> None:
    """A refusal names the server's reason; an unreadable reply may have landed."""
    from pycon_us.services.api import ApiError, NetworkError

    assert coc_review.problem_of(ApiError(404, "Unknown attendee access code.")) == (
        "Not recorded. Unknown attendee access code.",
        False,
    )
    assert coc_review.problem_of(ApiError(None, "unreadable")) == (MAYBE_RECORDED, True)
    assert coc_review.problem_of(NetworkError("x", maybe_sent=True)) == (
        MAYBE_RECORDED,
        True,
    )
    assert coc_review.problem_of(NetworkError("x")) == (NO_CONNECTION, False)
