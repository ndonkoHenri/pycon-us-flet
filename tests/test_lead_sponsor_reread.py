"""The Lead scanner while it reads the sponsor again (#873; D-56, D-425).

Back from the picker, the sponsor shown is the old one until the read of the stored
key lands. A row keeps the sponsor it was scanned for for good (STORE-11), so a
``scans_for_sponsor()`` account's screen is paused until then. Each test holds the
read at a gate in a real Flet session (``tests/harness.py``), around the real
``capture()`` and an in-memory outbox. The location and the route are set by hand, as
``tests/test_staff_lead.py``'s and ``tests/test_scan_screen.py``'s Back tests do.
"""

import asyncio
from typing import Any

import flet as ft
import pytest

from pycon_us import lead_capture
from pycon_us.core import outbox
from pycon_us.core.lead_sponsors import LeadSponsor
from pycon_us.screens import lead_sponsor, staff_lead, staff_leads
from pycon_us.screens.staff_lead import CHECKING_SPONSOR
from pycon_us.services.outbox_db import OutboxDb
from pycon_us.services.storage import Storage
from pycon_us.staff_sponsor import read_sponsor
from tests import lead_screen
from tests.lead_screen import Show, chip_text, choose, helper, signed_in
from tests.picker_rig import Go, going
from tests.scan_rig import enter
from tests.sync_rig import outbox_db

VIEW = lead_screen.VIEW
PICKER = f"{VIEW}/{lead_sponsor.SEGMENT}"
LEADS = f"{VIEW}/{staff_leads.SEGMENT}"
OLD = LeadSponsor("1", "Old Corp")
NEW = LeadSponsor("2", "New Corp")
OWNER = "a@example.com"
db = outbox_db
stored, show = lead_screen.stored, lead_screen.show


@pytest.fixture
def gate(monkeypatch: pytest.MonkeyPatch) -> asyncio.Event:
    """An open gate the scanner's sponsor reads pass; a test clears it to hold one."""
    opened = asyncio.Event()
    opened.set()

    async def held(storage: Storage) -> LeadSponsor | None:
        """Read the stored sponsor only once the gate is open: it is current then."""
        await opened.wait()
        return await read_sponsor(storage)

    monkeypatch.setattr(staff_lead, "read_sponsor", held)
    return opened


@pytest.fixture
def go(monkeypatch: pytest.MonkeyPatch) -> Go:
    """Return a function that changes the location and the route from the scanner's."""
    return going(monkeypatch, VIEW)


@pytest.fixture
def quick_capture(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make a capture stop waiting for the worker at once: none runs here."""
    monkeypatch.setattr(lead_capture, "WAIT_SECONDS", 0.01)


def rows(db: OutboxDb) -> list[outbox.Row]:
    """The account's rows, of any status."""
    return db.rows(OWNER, list(outbox.Status)) or []


@pytest.mark.usefixtures("quick_capture")
async def test_a_scan_while_the_sponsor_is_read_again_never_takes_the_old_one(
    show: Show, stored: dict[str, Any], db: OutboxDb, gate: asyncio.Event, go: Go
) -> None:
    """A to B, Back, a scan before the read lands: no row, then the next is for B."""
    account = signed_in(door_check=True)
    choose(stored, OLD)
    shown = await show(account, outbox=db)
    assert chip_text(shown) == "For: Old Corp"
    await go(shown, account, PICKER)
    choose(stored, NEW)  # the picker saves, then goes back
    gate.clear()
    await go(shown, account, VIEW)
    await enter(shown, "MOCK0001:v4l1d01")
    assert rows(db) == []
    assert helper(shown) == CHECKING_SPONSOR  # the field says why
    gate.set()
    await shown.settle()
    assert chip_text(shown) == "For: New Corp"
    assert helper(shown) is None
    await enter(shown, "MOCK0001:v4l1d01")
    (row,) = rows(db)
    assert (row.sponsor_id, row.sponsor_name) == (NEW.id, NEW.name)


@pytest.mark.usefixtures("quick_capture")
async def test_a_return_before_any_read_landed_never_counts_the_first_read_as_current(
    show: Show, stored: dict[str, Any], db: OutboxDb, gate: asyncio.Event, go: Go
) -> None:
    """Out and back with the reads held: the read from before the picker isn't current.

    Flet cancels the picker's read as Back lands, so the state still holds that older
    read, made at the very location the scanner is back at.
    """
    account = signed_in(door_check=True)
    choose(stored, OLD)
    shown = await show(account, outbox=db)
    gate.clear()
    await go(shown, account, PICKER)
    choose(stored, NEW)  # the picker saves, then goes back
    await go(shown, account, VIEW)
    await enter(shown, "MOCK0001:v4l1d01")
    assert rows(db) == []
    assert helper(shown) == CHECKING_SPONSOR
    gate.set()
    await shown.settle()
    assert chip_text(shown) == "For: New Corp"
    assert helper(shown) is None
    await enter(shown, "MOCK0001:v4l1d01")
    (row,) = rows(db)
    assert (row.sponsor_id, row.sponsor_name) == (NEW.id, NEW.name)


async def test_the_focus_comes_back_only_when_the_read_lands(
    show: Show,
    stored: dict[str, Any],
    gate: asyncio.Event,
    go: Go,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Back alone doesn't scan yet; the pause's end puts the focus in the field (D-438)."""
    focused: list[ft.TextField] = []

    async def focus(field: ft.TextField) -> None:
        """Count the field's focus requests."""
        focused.append(field)

    monkeypatch.setattr(ft.TextField, "focus", focus)
    account = signed_in(door_check=True)
    choose(stored, OLD)
    shown = await show(account)
    await go(shown, account, PICKER)
    focused.clear()
    gate.clear()
    await go(shown, account, VIEW)
    assert focused == []
    gate.set()
    await shown.settle()
    assert len(focused) == 1


@pytest.mark.usefixtures("quick_capture")
async def test_a_sponsor_s_own_account_keeps_scanning_during_the_read(
    show: Show, stored: dict[str, Any], db: OutboxDb, gate: asyncio.Event, go: Go
) -> None:
    """It has no sponsor to read again: Back from the list pauses nothing, no flash."""
    account = signed_in(lead_retrieval=True)
    choose(stored, OLD)  # left by an earlier staff session, say
    shown = await show(account, outbox=db)
    await go(shown, account, LEADS)
    gate.clear()
    await go(shown, account, VIEW)
    assert helper(shown) is None
    await enter(shown, "MOCK0001:v4l1d01")
    (row,) = rows(db)
    assert (row.sponsor_id, row.sponsor_name) == (None, None)
