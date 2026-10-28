"""Tests for ``lead_note.py``: a lead note through the outbox and what Save says (#742).

Each test signs a real ``Account`` in to the in-process mock (``tests/sync_rig.py``),
runs a real ``SyncWorker`` loop, captures a lead as the Lead scanner does, then stores
and confirms a note as the note sheet does (LEAD-10, LEAD-11; D-56, D-407). The mock
checks every signature and records every note it applied, with its sponsor.
"""

import asyncio
from collections.abc import AsyncIterator

import pytest

from pycon_us import lead_note
from pycon_us.core.badges import Badge, ScanOutcome
from pycon_us.core.lead_notes import Interest, LeadNote, compose
from pycon_us.core.lead_sponsors import LeadSponsor
from pycon_us.core.outbox import Kind, Outcome, Status, status_text
from pycon_us.lead_capture import capture
from pycon_us.lead_note import NOTE_SAVED, WILL_SYNC, confirm, saved_note, store
from pycon_us.services.credentials import CredentialStorage
from pycon_us.services.outbox_db import OutboxDb
from pycon_us.services.storage import Storage
from pycon_us.services.sync import SyncWorker
from tests import accounts
from tests.sync_rig import Rig, outbox_db

shared, storage, keystore, credentials = (
    accounts.shared,
    accounts.storage,
    accounts.keystore,
    accounts.credentials,
)
db = outbox_db

ADA = Badge("MOCK0001", "v4l1d01", "v4l1d01")
EXAMPLE = LeadSponsor("1", "Example Corp")
SAMPLE = LeadSponsor("3", "Sample Systems")
WARM = LeadNote(Interest.WARM, ("Demo", "Hiring"), "Wants a call next week.")


class Booth:
    """The Lead scanner's side of a rig: a running worker, captures and notes.

    Attributes:
        rig: The signed-in session.
        worker: The worker, the outbox's only sender.
    """

    def __init__(self, rig: Rig) -> None:
        """Hold the rig and run its worker's loop, as ``supervise()`` does."""
        self.rig = rig
        self.worker: SyncWorker = rig.worker()
        self._task = asyncio.create_task(self.worker.run())

    async def stop(self) -> None:
        """Cancel the worker's loop and wait until it has stopped."""
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)

    async def scan(self, sponsor: LeadSponsor | None = None) -> ScanOutcome:
        """Capture Ada's badge for ``sponsor`` (None: the account's own)."""
        result = await capture(
            self.rig.db,
            self.rig.staff,
            self.worker.kick,
            ADA,
            owner=self.rig.account.owner,
            sponsor=sponsor,
            clock=self.rig.clock,
        )
        return result.outcome

    async def note(
        self, note: LeadNote = WARM, sponsor: LeadSponsor | None = None
    ) -> str:
        """Save ``note`` on Ada's lead as the sheet does; return what it says."""
        stored = store(
            self.rig.db,
            ADA.code,
            note,
            owner=self.rig.account.owner,
            sponsor=sponsor,
            clock=self.rig.clock,
        )
        assert stored is not None and stored.row is not None
        return await confirm(self.rig.db, self.rig.staff, self.worker.kick, stored.row)


@pytest.fixture
def rig(db: OutboxDb, storage: Storage, credentials: CredentialStorage) -> Rig:
    """The rig over the idempotent mock, signed out."""
    return Rig(db, storage, credentials)


@pytest.fixture
async def booth(rig: Rig) -> AsyncIterator[Booth]:
    """A booth over ``rig`` with its worker running, stopped afterwards."""
    running = Booth(rig)
    yield running
    await running.stop()


def notes(rig: Rig) -> list[tuple[int, str]]:
    """Each note the mock recorded: its sponsor id and its text."""
    return [(n.sponsor_id, n.note) for n in rig.state.notes]


async def test_a_note_on_a_captured_lead_is_sent_and_confirmed(
    rig: Rig, booth: Booth
) -> None:
    """Warm, Demo and Hiring and text: the mock gets Ionic's three lines; "Note saved".

    The queue sheet says the row Confirmed, and the sheet opens it again prefilled.
    """
    await rig.sign_in("sponsor")
    assert await booth.scan() is ScanOutcome.ACCEPTED
    assert await booth.note() == NOTE_SAVED
    text = "Interest: warm\nFollow-up: Demo, Hiring\nNotes: Wants a call next week."
    assert notes(rig) == [(1, text)]
    note_row = next(row for row in rig.rows() if row.kind is Kind.NOTE)
    assert status_text(note_row) == "Confirmed"
    assert rig.staff.pending == 0
    assert saved_note(rig.db, rig.account.owner, ADA.code) == WARM


async def test_offline_a_note_waits_for_its_lead_then_follows_it_to_its_sponsor(
    rig: Rig, booth: Booth
) -> None:
    """Queued lead, then a note: "Will sync." at once; back online, lead then note.

    A staff account switched sponsor between the scan and the note: both still reach
    the scan-time sponsor (STORE-11).
    """
    await rig.sign_in("staff")
    rig.state.faults.inject("connect", until_cleared=True)
    assert await booth.scan(SAMPLE) is ScanOutcome.QUEUED
    assert await booth.note(sponsor=EXAMPLE) == WILL_SYNC
    assert rig.staff.pending == 2 and notes(rig) == []
    rig.state.faults.clear()
    rig.clock.at += 60  # the backoff's tick
    await booth.worker.drain()
    # The offline try at the capture is on the wire too; the note only after it.
    sent = [path for path, _ in rig.sends()]
    note = "lead_retrieval/MOCK0001/note/"
    assert sent[-2:] == ["lead_retrieval/capture/", note] and sent.count(note) == 1
    assert notes(rig) == [(3, compose(WARM))]
    assert [(row.kind, row.status) for row in rig.rows()] == [
        (Kind.LEAD, Status.SYNCED),
        (Kind.NOTE, Status.SYNCED),
    ]


async def test_an_edited_note_is_sent_again(rig: Rig, booth: Booth) -> None:
    """A synced note saved with new text is sent again, and prefills with the new."""
    await rig.sign_in("sponsor")
    await booth.scan()
    assert await booth.note() == NOTE_SAVED
    hot = LeadNote(Interest.HOT, ("Partner",))
    assert await booth.note(hot) == NOTE_SAVED
    assert [text for _, text in notes(rig)] == [
        compose(WARM),
        "Interest: hot\nFollow-up: Partner",
    ]
    assert saved_note(rig.db, rig.account.owner, ADA.code) == hot


async def test_the_same_note_twice_records_once_under_idempotent_capture(
    rig: Rig, booth: Booth
) -> None:
    """Saved twice unchanged, it is sent twice and the mock keeps one (D-407)."""
    await rig.sign_in("sponsor")
    await booth.scan()
    assert await booth.note() == NOTE_SAVED
    assert await booth.note() == NOTE_SAVED
    assert sum(path.endswith("/note/") for path, _ in rig.sends()) == 2
    assert notes(rig) == [(1, compose(WARM))]


async def test_an_empty_note_stores_nothing(rig: Rig) -> None:
    """Nothing chosen and no text: ignored, no row (the sheet says "Nothing to save")."""
    await rig.sign_in("sponsor")
    stored = store(
        rig.db, ADA.code, LeadNote(text="  "), owner=rig.account.owner, sponsor=None
    )
    assert stored is not None and stored.outcome is Outcome.IGNORED
    assert rig.rows() == []


async def test_a_note_the_outbox_can_t_store_says_so(rig: Rig) -> None:
    """No outbox, or a closed one: None, so the sheet keeps the text (D-120)."""
    await rig.sign_in("sponsor")
    owner = rig.account.owner
    assert store(None, ADA.code, WARM, owner=owner, sponsor=None) is None
    rig.db.close()
    assert store(rig.db, ADA.code, WARM, owner=owner, sponsor=None) is None
    assert saved_note(rig.db, owner, ADA.code) == LeadNote()


def test_without_a_saved_note_the_sheet_starts_empty(db: OutboxDb) -> None:
    """No row for the lead (or no outbox): an empty note."""
    assert saved_note(db, "a@example.com", "MOCK0001") == LeadNote()
    assert lead_note.saved_note(None, "a@example.com", "MOCK0001") == LeadNote()
