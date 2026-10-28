"""Tests for the lead note sheet on the Lead scanner (#742; LEAD-07, LEAD-10).

The scanner runs in a real Flet session (``tests/lead_screen.py``) over a real outbox
and no worker, so a scan ends "Saved. Will sync." at once. Taps are what Flutter
reports: a segment's new selection, a chip's new state, the field's text (``reported()``),
then the event. The sheet's sends are ``tests/test_lead_note.py``'s.
"""

from functools import partial
from typing import Any, cast

import flet as ft
import pytest
from flet.utils.object_model import patch_dataclass

from pycon_us import lead_capture
from pycon_us.core import outbox
from pycon_us.core.lead_notes import Interest, LeadNote, compose
from pycon_us.lead_note import NOTHING_TO_SAVE, WILL_SYNC
from pycon_us.screens.staff_lead import NOTE_OPEN
from pycon_us.services.outbox_db import OutboxDb
from pycon_us.ui import scan_screen
from tests import lead_screen
from tests.filter_sheet import descendants
from tests.harness import Shown
from tests.lead_screen import Show, signed_in
from tests.scan_rig import panel
from tests.sync_rig import outbox_db

db = outbox_db
stored, show = lead_screen.stored, lead_screen.show

OWNER = "a@example.com"
ADA = "MOCK0001:v4l1d01"


@pytest.fixture(autouse=True)
def quick(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """No wait for a worker, and a scan clock that a test moves past the cooldown."""
    monkeypatch.setattr(lead_capture, "WAIT_SECONDS", 0.01)
    now = [100.0]
    monkeypatch.setattr(scan_screen, "clock", lambda: now[0])
    return now


def reported(control: ft.BaseControl, **values: Any) -> None:
    """Set what Flutter reports on a sheet's live control, frozen or not, as Flet does.

    The session's ``apply_patch`` patches only indexed controls, and a dialog's are
    not in the test session's index.
    """
    patch_dataclass(control, values)


def sheet(shown: Shown) -> ft.BottomSheet | None:
    """The open note sheet, or None."""
    dialogs = shown.session.page._dialogs.controls  # pyright: ignore[reportPrivateUsage]
    found = [d for d in dialogs if isinstance(d, ft.BottomSheet) and d.open]
    assert len(found) <= 1
    return found[0] if found else None


def in_sheet(shown: Shown, identifier: str) -> Any:
    """The control under the open sheet's semantics node ``identifier``."""
    current = sheet(shown)
    assert current is not None
    return next(
        c.content
        for c in descendants(current)
        if isinstance(c, ft.Semantics) and c.identifier == identifier
    )


def sheet_texts(shown: Shown) -> list[str]:
    """Every text in the open sheet."""
    current = sheet(shown)
    assert current is not None
    return [str(c.value) for c in descendants(current) if isinstance(c, ft.Text)]


def helper(shown: Shown) -> str | None:
    """The scan field's helper line: why scanning is paused, or None."""
    return cast(str | None, scan_field(shown).helper)


def scan_field(shown: Shown) -> ft.TextField:
    """The scan screen's badge code field."""
    return cast(ft.TextField, shown.node("scan.entry").content)


async def scan(shown: Shown, text: str = ADA) -> None:
    """Type ``text`` in the badge field as Flutter reports it, then press Enter."""
    field = scan_field(shown)
    shown.session.apply_patch(field._i, {"value": text})
    await shown.event(field, "change", text)
    await shown.event(field, "submit", text)


async def tap(shown: Shown, identifier: str) -> None:
    """Tap the scan screen's button ``identifier``."""
    await shown.click(cast(ft.Control, shown.node(identifier).content))


async def choose_interest(shown: Shown, value: str) -> None:
    """Pick an interest segment, as Flutter reports the new selection."""
    (button,) = [
        c for c in descendants(sheet(shown)) if isinstance(c, ft.SegmentedButton)
    ]
    reported(button, selected=[value])
    await shown.event(button, "change", [value])


async def toggle(shown: Shown, key: str) -> None:
    """Tap a follow-up chip: its flipped state, then the event (chip.dart)."""
    chip = in_sheet(shown, f"lead.note.follow_up.{key}")
    selected = not chip.selected
    reported(chip, selected=selected)
    await shown.event(chip, "select", selected)


async def type_note(shown: Shown, text: str) -> None:
    """Type the free text, as Flutter reports it."""
    field = in_sheet(shown, "lead.note.text")
    reported(field, value=text)
    await shown.event(field, "change", text)


def snack(shown: Shown) -> str:
    """The last SnackBar's words."""
    bar = shown.snack_bars[-1]
    assert isinstance(bar.content, ft.Text)
    return str(bar.content.value)


def note_rows(db: OutboxDb) -> list[outbox.Row]:
    """The account's note rows."""
    rows = db.rows(OWNER, list(outbox.Status)) or []
    return [row for row in rows if row.kind is outbox.Kind.NOTE]


async def test_add_note_opens_the_sheet_pauses_scanning_and_saves_the_note(
    show: Show, db: OutboxDb
) -> None:
    """Warm, Demo and Hiring and text, then Save: the composed note is queued.

    While open, scanning says why it is paused; Save closes it and says the note
    waits for its lead ("Will sync.").
    """
    shown = await show(signed_in(lead_retrieval=True), outbox=db)
    await scan(shown)
    assert not shown.nodes("lead.open_lead")
    await tap(shown, "lead.add_note")
    assert sheet(shown) is not None
    assert helper(shown) == NOTE_OPEN
    assert "Note for MOCK0001" in sheet_texts(shown)
    await choose_interest(shown, "warm")
    await toggle(shown, "demo")
    await toggle(shown, "hiring")
    await type_note(shown, "Wants a call.")
    assert in_sheet(shown, "lead.note.text").value == "Wants a call."  # kept (D-243)
    await shown.click(in_sheet(shown, "lead.note.save"))
    assert sheet(shown) is None and helper(shown) is None
    (row,) = note_rows(db)
    assert row.payload["note"] == (
        "Interest: warm\nFollow-up: Demo, Hiring\nNotes: Wants a call."
    )
    assert snack(shown) == WILL_SYNC


async def test_open_lead_on_a_duplicate_opens_its_note_prefilled(
    show: Show, db: OutboxDb
) -> None:
    """A duplicate offers Open lead: the saved note, prefilled and ready to edit."""
    saved = LeadNote(Interest.HOT, ("Partner",), "Met at the booth.")
    lead = partial(
        outbox.scan_lead,
        owner=OWNER,
        code="MOCK0001",
        payload={"badge_validator": "v4l1d01"},
        sponsor_id=None,
        sponsor_name=None,
        now=1.0,
    )
    assert db.enqueue("MOCK0001", lead) is not None
    (row,) = db.rows(OWNER, list(outbox.Status)) or []
    assert db.save(outbox.after_success(row, {"first_name": "Ada"}))
    note = partial(
        outbox.save_note,
        owner=OWNER,
        code="MOCK0001",
        note=compose(saved),
        sponsor_id=None,
        sponsor_name=None,
        now=1.0,
    )
    assert db.enqueue("MOCK0001", note) is not None
    shown = await show(signed_in(lead_retrieval=True), outbox=db)
    await scan(shown)
    assert not shown.nodes("lead.add_note")
    await tap(shown, "lead.open_lead")
    texts = sheet_texts(shown)
    assert "Note for Ada" in texts and "MOCK0001" in texts
    current = sheet(shown)
    (button,) = [c for c in descendants(current) if isinstance(c, ft.SegmentedButton)]
    assert button.selected == ["hot"]
    assert in_sheet(shown, "lead.note.follow_up.partner").selected
    assert not in_sheet(shown, "lead.note.follow_up.demo").selected
    assert in_sheet(shown, "lead.note.text").value == "Met at the booth."
    await type_note(shown, "Met at the booth. Call Friday.")
    await shown.click(in_sheet(shown, "lead.note.save"))
    (row,) = note_rows(db)
    assert row.payload["note"].endswith("Notes: Met at the booth. Call Friday.")
    assert row.status is outbox.Status.PENDING  # edited, so sent again


async def test_a_scan_while_the_sheet_is_open_is_dropped(
    show: Show, db: OutboxDb, quick: list[float]
) -> None:
    """A HID scanner's submit under the sheet scans nothing; Cancel resumes it."""
    shown = await show(signed_in(lead_retrieval=True), outbox=db)
    await scan(shown)
    await tap(shown, "lead.add_note")
    quick[0] += 5
    await scan(shown, "MOCK0002:v4l1d02")
    assert scan_field(shown).value == "MOCK0002:v4l1d02"  # kept, not scanned
    assert len(db.rows(OWNER, list(outbox.Status)) or []) == 1
    await shown.click(in_sheet(shown, "lead.note.cancel"))
    assert sheet(shown) is None and helper(shown) is None
    assert note_rows(db) == []


async def test_an_empty_note_saves_nothing_and_says_so(
    show: Show, db: OutboxDb
) -> None:
    """Save with nothing chosen or typed: no row, "Nothing to save"."""
    shown = await show(signed_in(lead_retrieval=True), outbox=db)
    await scan(shown)
    await tap(shown, "lead.add_note")
    await shown.click(in_sheet(shown, "lead.note.save"))
    assert sheet(shown) is None
    assert note_rows(db) == []
    assert snack(shown) == NOTHING_TO_SAVE


async def test_the_action_belongs_to_the_result_shown(show: Show, db: OutboxDb) -> None:
    """The next result replaces it: after "Not a badge code", no Add note."""
    shown = await show(signed_in(lead_retrieval=True), outbox=db)
    assert not shown.nodes("lead.add_note")  # before any scan
    await scan(shown)
    assert shown.nodes("lead.add_note")
    await scan(shown, "not a badge")
    assert panel(shown).startswith("Not a badge code")
    assert not shown.nodes("lead.add_note")


async def test_a_note_the_outbox_can_t_store_keeps_the_sheet_and_says_so(
    show: Show, db: OutboxDb
) -> None:
    """A closed outbox: the sheet stays, its text kept, with the reason (D-120)."""
    shown = await show(signed_in(lead_retrieval=True), outbox=db)
    await scan(shown)
    await tap(shown, "lead.add_note")
    await type_note(shown, "Call back")
    db.close()
    await shown.click(in_sheet(shown, "lead.note.save"))
    assert sheet(shown) is not None
    assert in_sheet(shown, "lead.note.text").value == "Call back"
    problem = shown_problem(shown)
    assert problem == "Couldn't save this note on this device."


def shown_problem(shown: Shown) -> str:
    """The sheet's line saying why Save stored nothing."""
    line = in_sheet(shown, "lead.note.problem")
    assert isinstance(line, ft.Text)
    return str(line.value)
