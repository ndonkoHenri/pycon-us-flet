"""Tests for the leads list, ``screens/staff_leads.py`` (#743; LEAD-06, LEAD-08, D-428).

The page runs in a real Flet session (``tests/harness.py``) over a real outbox, whose
rows ``tests/lead_rows.py`` puts in each state; no worker runs. It lists the account's
leads newest first as one node each, searches them, filters a staff account's by the
sponsor id, opens a row's note sheet, follows the outbox (``Staff.revision``), and
says when there is nothing to list or the outbox can't be read.
"""

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, cast

import flet as ft
import pytest
from flet.utils.object_model import patch_dataclass

from pycon_us import lead_capture
from pycon_us.account import Account
from pycon_us.config import YearData, load_year
from pycon_us.core import outbox
from pycon_us.core.lead_sponsors import LeadSponsor, to_stored
from pycon_us.core.outbox import Kind, Status
from pycon_us.dev_options import DEV_MOCK_API_URL
from pycon_us.memory import ViewMemory
from pycon_us.prefs import Prefs
from pycon_us.screens import staff_leads
from pycon_us.screens.staff_leads import NO_LEADS, NO_MATCH, NOT_READ, LeadsPage
from pycon_us.services import Services
from pycon_us.services.outbox_db import OutboxDb
from pycon_us.services.storage import STAFF_SPONSOR
from pycon_us.staff import Staff
from pycon_us.state import Conference
from pycon_us.ui import scan_screen
from pycon_us.ui.scan_screen import NOT_AVAILABLE
from tests import harness
from tests.api_clients import BASE_URL
from tests.fakes import MemoryPrefs
from tests.filter_sheet import descendants
from tests.harness import Shown, showing
from tests.lead_rows import OWNER, add, note
from tests.lead_screen import signed_in
from tests.sync_rig import outbox_db

db = outbox_db

VIEW = "/more/staff/lead/leads"
EXAMPLE = LeadSponsor("1", "Example Corp")

type Show = Callable[..., Awaitable[Shown]]


@pytest.fixture(autouse=True)
def quick(monkeypatch: pytest.MonkeyPatch) -> None:
    """No wait for a worker after a note's Save: none runs here."""
    monkeypatch.setattr(lead_capture, "WAIT_SECONDS", 0.01)


@pytest.fixture
async def show(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Show]:
    """Return a function that renders the page for an account over an outbox.

    ``chosen`` stores the sponsor a staff account scans for, as the picker left it;
    ``staff`` is the ``Staff`` store, which a test bumps as the worker would.
    """

    async def focus(_: ft.TextField) -> None:
        """Stand in for the client's focus: nothing to do."""

    monkeypatch.setattr(ft.TextField, "focus", focus)
    stored: dict[str, Any] = {}
    memory_services = harness.memory_services

    def sharing(
        year: YearData, directory: Path, memory: ViewMemory | None = None
    ) -> Services:
        """Return the memory services over the test's one ``stored``."""
        svc = memory_services(year, directory, memory)
        cast(MemoryPrefs, svc.storage.prefs).values = stored
        return svc

    monkeypatch.setattr(harness, "memory_services", sharing)
    async with AsyncExitStack() as stack:

        async def render(
            account: Account,
            outbox: OutboxDb,
            *,
            chosen: LeadSponsor | None = None,
            staff: Staff | None = None,
        ) -> Shown:
            """Render the page signed in as ``account``, its rows in ``outbox``."""
            if chosen is not None:
                stored[STAFF_SPONSOR.key] = json.dumps(to_stored(chosen))
            prefs = Prefs(loaded=True)
            prefs.dev = {DEV_MOCK_API_URL: BASE_URL}
            return await stack.enter_async_context(
                showing(
                    LeadsPage,
                    staff_leads,
                    scan_screen,
                    year=load_year(2026),
                    conference=Conference(),
                    tmp_path=tmp_path,
                    monkeypatch=monkeypatch,
                    view_path=VIEW,
                    route=VIEW,
                    prefs=prefs,
                    account=account,
                    outbox=outbox,
                    staff=staff,
                )
            )

        yield render


def sponsor_account() -> Account:
    """A sponsor's own lead-retrieval account, ``a@example.com``."""
    return signed_in(lead_retrieval=True)


def door_staff() -> Account:
    """Door staff, who scan for a sponsor they choose (LEAD-05)."""
    return signed_in(door_check=True)


def rows(shown: Shown) -> list[str]:
    """Each lead row's phrase, in the list's order."""
    (lists,) = [v for v in shown.find(ft.ListView) if v.expand]
    return [
        str(c.label)
        for item in lists.controls
        for c in descendants(getattr(item, "_b", item))  # a row is a component
        if isinstance(c, ft.Semantics)
        and str(c.identifier).startswith("lead.leads.row.")
    ]


async def search(shown: Shown, text: str) -> None:
    """Type ``text`` in the search field, as Flutter reports it."""
    field = cast(ft.TextField, shown.node("lead.leads.search").content)
    shown.session.apply_patch(field._i, {"value": text})
    await shown.event(field, "change", text)


def sheet(shown: Shown) -> ft.BottomSheet | None:
    """The open note sheet, or None."""
    dialogs = shown.session.page._dialogs.controls  # pyright: ignore[reportPrivateUsage]
    found = [d for d in dialogs if isinstance(d, ft.BottomSheet) and d.open]
    return found[0] if found else None


async def test_every_status_shows_newest_first_with_its_words(
    show: Show, db: OutboxDb
) -> None:
    """Queued (the code only), Failed, Confirmed (the name), flagged with its icon."""
    add(db, "MOCK0004", 100.0, status=Status.SYNCED, name="Bo", flagged=True)
    add(db, "MOCK0003", 200.0, status=Status.SYNCED, name="Ada")
    add(db, "MOCK0002", 300.0, status=Status.FAILED)
    add(db, "MOCK0001", 400.0)
    shown = await show(sponsor_account(), db)
    phrases = rows(shown)
    assert [p.split(", ")[:2] for p in phrases] == [
        ["MOCK0001", "Queued"],
        ["MOCK0002", "Failed"],
        ["Ada", "Confirmed"],
        ["Bo", "Confirmed"],
    ]
    assert phrases[3].startswith("Bo, Confirmed, may be recorded twice, ")
    icons = [i.icon for i in shown.find(ft.Icon)]
    assert icons.count(ft.Icons.WARNING_AMBER) == 1  # beside the flagged row's words
    texts = shown.texts()
    assert any(t.startswith("Confirmed · may be recorded twice · ") for t in texts)
    assert shown.titles[-1] == "Leads"


async def test_search_narrows_by_name_or_code_and_says_when_nothing_matches(
    show: Show, db: OutboxDb
) -> None:
    """Searching "ada" keeps Ada, "0001" the queued code; a miss says so."""
    add(db, "MOCK0001", 100.0)
    add(db, "MOCK0003", 200.0, status=Status.SYNCED, name="Ada")
    shown = await show(sponsor_account(), db)
    await search(shown, "ada")
    assert [p.split(", ")[0] for p in rows(shown)] == ["Ada"]
    await search(shown, "0001")
    assert [p.split(", ")[0] for p in rows(shown)] == ["MOCK0001"]
    await search(shown, "zzz")
    assert rows(shown) == []
    assert shown.nodes("lead.leads.no_match")
    assert NO_MATCH in shown.texts()


async def test_staff_filter_by_the_sponsor_id_they_scan_for(
    show: Show, db: OutboxDb
) -> None:
    """The chip "Only Example Corp" keeps id 1, not a sponsor named alike."""
    add(
        db, "A1", 100.0, status=Status.SYNCED, name="Ada", sponsor=("1", "Example Corp")
    )
    add(
        db,
        "B1",
        200.0,
        status=Status.SYNCED,
        name="Bo",
        sponsor=("2", '"Example Corp"'),
    )
    shown = await show(door_staff(), db, chosen=EXAMPLE)
    assert len(rows(shown)) == 2
    assert rows(shown)[1].endswith(", Example Corp")  # the sponsor, for staff
    chip = cast(ft.Chip, shown.node("lead.leads.only_sponsor").content)
    assert chip.label == "Only Example Corp" and not chip.selected
    shown.session.apply_patch(chip._i, {"selected": True})
    await shown.event(chip, "select", True)
    assert [p.split(", ")[0] for p in rows(shown)] == ["Ada"]


async def test_a_sponsor_s_own_account_has_no_filter_chip(
    show: Show, db: OutboxDb
) -> None:
    """Only staff who scan for a sponsor get the chip (LEAD-06)."""
    add(db, "A1", 100.0)
    shown = await show(sponsor_account(), db, chosen=EXAMPLE)
    assert not shown.nodes("lead.leads.only_sponsor")


async def test_a_note_shows_and_a_tap_opens_the_sheet_whose_save_updates_the_row(
    show: Show, db: OutboxDb
) -> None:
    """A noted row says so; a tap opens "Note for Ada"; Save adds the note to its row."""
    add(db, "MOCK0001", 100.0, status=Status.SYNCED, name="Ada")
    add(db, "MOCK0002", 200.0)
    note(db, "MOCK0002", "Notes: Call back.")
    staff = Staff()
    shown = await show(sponsor_account(), db, staff=staff)
    assert rows(shown)[0].endswith(", has a note")
    assert not rows(shown)[1].endswith(", has a note")
    row = shown.node("lead.leads.row.MOCK0001")
    await shown.click(cast(ft.Container, row.parent))
    opened = sheet(shown)
    assert opened is not None
    texts = [str(c.value) for c in descendants(opened) if isinstance(c, ft.Text)]
    assert "Note for Ada" in texts
    field = next(c for c in descendants(opened) if isinstance(c, ft.TextField))
    patch_dataclass(field, {"value": "Wants a demo."})  # as Flutter reports it
    await shown.event(field, "change", "Wants a demo.")
    save = next(
        c.content
        for c in descendants(opened)
        if isinstance(c, ft.Semantics) and c.identifier == "lead.note.save"
    )
    await shown.click(cast(ft.Button, save))
    assert sheet(shown) is None
    notes = [r for r in db.rows(OWNER, list(Status)) or [] if r.kind is Kind.NOTE]
    assert {r.key: r.payload["note"] for r in notes}["MOCK0001"] == (
        "Notes: Wants a demo."
    )
    assert rows(shown)[1].startswith("Ada, Confirmed, ")
    assert rows(shown)[1].endswith(", has a note")


async def test_the_list_follows_the_outbox_while_open(show: Show, db: OutboxDb) -> None:
    """A row synced by the worker turns Confirmed once ``Staff.revision`` moves (D-69)."""
    queued = add(db, "MOCK0001", 100.0)
    staff = Staff()
    shown = await show(sponsor_account(), db, staff=staff)
    assert rows(shown)[0].startswith("MOCK0001, Queued, ")
    assert db.save(outbox.after_success(queued, {"first_name": "Ada"}))
    add(db, "MOCK0002", 200.0)
    staff.update_counts(db.counts(OWNER))
    await shown.settle()
    assert [p.split(", ")[:2] for p in rows(shown)] == [
        ["MOCK0002", "Queued"],
        ["Ada", "Confirmed"],
    ]


async def test_no_leads_yet_and_an_unreadable_outbox_say_so(
    show: Show, db: OutboxDb, tmp_path: Path
) -> None:
    """An empty outbox: "No leads yet"; a closed one: the D-120 line, never empty."""
    shown = await show(sponsor_account(), db)
    assert NO_LEADS in shown.texts()
    assert not shown.nodes("lead.leads.search")
    closed = OutboxDb(tmp_path)
    closed.close()
    failed = await show(sponsor_account(), closed)
    assert NOT_READ in failed.texts()
    assert NO_LEADS not in failed.texts()


async def test_a_thousand_leads_all_list_lazily(show: Show, db: OutboxDb) -> None:
    """No 50-row cap: 1,000 rows, in a ``ListView`` Flutter builds on demand."""
    for n in range(1000):
        add(db, f"C{n:04d}", float(n))
    shown = await show(sponsor_account(), db)
    (lists,) = [v for v in shown.find(ft.ListView) if v.expand]
    assert lists.build_controls_on_demand
    assert len(rows(shown)) == 1000
    assert rows(shown)[0].startswith("C0999, ")


async def test_another_account_s_leads_never_show(show: Show, db: OutboxDb) -> None:
    """Only the signed-in account's rows list (D-414)."""
    add(db, "MINE", 100.0)
    add(db, "THEIRS", 200.0, owner="b@example.com")
    shown = await show(sponsor_account(), db)
    assert [p.split(", ")[0] for p in rows(shown)] == ["MINE"]
    assert all(row.kind is Kind.LEAD for row in db.rows(OWNER, list(Status)) or [])


async def test_an_account_without_the_scanner_is_refused(
    show: Show, db: OutboxDb
) -> None:
    """A deep link without lead retrieval or door check lands on "Not available"."""
    add(db, "MINE", 100.0)
    shown = await show(signed_in(), db)
    assert NOT_AVAILABLE in shown.texts()
    assert rows(shown) == []
