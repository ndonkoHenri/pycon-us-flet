"""Tests for ``lead_capture.capture()``: a lead through the outbox, its result at once.

Each test signs a real ``Account`` in to the in-process mock (``tests/sync_rig.py``),
runs a real ``SyncWorker`` loop, and scans through ``capture()`` as the Lead scanner
does (#741; LEAD-07, LEAD-09, STORE-11; D-426). The mock checks every signature and
counts every lead it records, so "captured once" is the mock's own count.
"""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import replace

import pytest

from pycon_us import lead_capture
from pycon_us.core.badges import Badge, ScanOutcome, ScanResult
from pycon_us.core.lead_sponsors import LeadSponsor
from pycon_us.core.outbox import RETRY_CAP, Status
from pycon_us.lead_capture import (
    ALREADY,
    CAPTURED,
    MAY_BE_TWICE,
    NOT_CAPTURED,
    NOT_SAVED,
    RETRY_FROM_QUEUE,
    SAVED,
    WILL_RETRY,
    capture,
)
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
GRACE = Badge("MOCK0002", "v4l1d02", "v4l1d02")
EXAMPLE = LeadSponsor("1", "Example Corp")
SAMPLE = LeadSponsor("3", "Sample Systems")


class Scanner:
    """The Lead scanner's side of a rig: a running worker and ``capture()`` calls.

    Attributes:
        rig: The signed-in session.
        worker: The worker, the outbox's only sender; None until ``start()``.
    """

    def __init__(self, rig: Rig) -> None:
        """Hold the rig; no worker runs yet."""
        self.rig = rig
        self.worker: SyncWorker | None = None
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        """Run the worker's loop, as ``supervise()`` does for a signed-in account."""
        self.worker = self.rig.worker()
        self._task = asyncio.create_task(self.worker.run())

    async def stop(self) -> None:
        """Cancel the worker's loop and wait until it has stopped."""
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def scan(
        self, badge: Badge = ADA, sponsor: LeadSponsor | None = None
    ) -> ScanResult:
        """Scan ``badge`` as the signed-in account, for ``sponsor`` (None: its own)."""

        def kick() -> None:
            """Ask the running worker for a pass; without one, nothing listens."""
            if self.worker is not None:
                self.worker.kick()

        return await capture(
            self.rig.db,
            self.rig.staff,
            kick,
            badge,
            owner=self.rig.account.owner,
            sponsor=sponsor,
            clock=self.rig.clock,
        )


@pytest.fixture
def rig(db: OutboxDb, storage: Storage, credentials: CredentialStorage) -> Rig:
    """The rig over the idempotent mock, signed out."""
    return Rig(db, storage, credentials)


@pytest.fixture
async def scanner(rig: Rig) -> AsyncIterator[Scanner]:
    """A scanner over ``rig`` with its worker running, stopped afterwards."""
    scanning = Scanner(rig)
    scanning.start()
    yield scanning
    await scanning.stop()


def captures(rig: Rig) -> list[tuple[int, str]]:
    """Each lead the mock recorded: its sponsor id and the attendee's code."""
    return [(lead.sponsor_id, lead.access_code) for lead in rig.state.leads]


async def test_a_sponsor_s_scan_is_captured_with_the_name_then_already_in_leads(
    rig: Rig, scanner: Scanner
) -> None:
    """Online: "Lead captured · Ada"; the same badge again: "Already in your leads"."""
    await rig.sign_in("sponsor")
    result = await scanner.scan()
    assert result == ScanResult(ScanOutcome.ACCEPTED, CAPTURED, "Ada", ("MOCK0001",))
    assert rig.staff.synced == 1
    again = await scanner.scan()
    assert again == ScanResult(ScanOutcome.DUPLICATE, ALREADY, "Ada", ("MOCK0001",))
    assert captures(rig) == [(1, "MOCK0001")]  # the repeat sent nothing


async def test_a_staff_scan_goes_to_the_sponsor_picked(
    rig: Rig, scanner: Scanner
) -> None:
    """The row snapshots the sponsor, and the capture names it (STORE-11)."""
    await rig.sign_in("staff")
    result = await scanner.scan(sponsor=SAMPLE)
    assert result.outcome is ScanOutcome.ACCEPTED
    assert captures(rig) == [(3, "MOCK0001")]
    (row,) = rig.rows()
    assert (row.sponsor_id, row.sponsor_name) == ("3", "Sample Systems")


async def test_offline_it_is_saved_and_syncs_once_to_its_first_sponsor(
    rig: Rig, scanner: Scanner
) -> None:
    """No connection: "Saved. Will sync."; a switch of sponsor leaves the row's own.

    The rescan for another sponsor keeps the queued row and its snapshot; once the
    mock answers again, the lead reaches the first sponsor, once.
    """
    await rig.sign_in("staff")
    rig.state.faults.inject("connect", until_cleared=True)
    result = await scanner.scan(sponsor=EXAMPLE)
    assert result == ScanResult(ScanOutcome.QUEUED, SAVED, "MOCK0001")
    assert rig.staff.offline and rig.staff.pending == 1
    again = await scanner.scan(sponsor=SAMPLE)  # switched sponsor, still offline
    assert again.outcome is ScanOutcome.QUEUED
    rig.state.faults.clear()
    rig.clock.at += 60  # the backoff's tick
    assert scanner.worker is not None
    await scanner.worker.drain()
    assert captures(rig) == [(1, "MOCK0001")]
    assert [row.status for row in rig.rows()] == [Status.SYNCED]


async def test_a_wrong_validator_is_not_captured_and_will_retry(
    rig: Rig, scanner: Scanner
) -> None:
    """The mock's 404: "Not captured", its message, and the row retries (counted)."""
    await rig.sign_in("sponsor")
    result = await scanner.scan(Badge("MOCK0001", "v4l1d01", "wrong"))
    (row,) = rig.rows()
    assert (row.status, row.tries) == (Status.PENDING, 1)
    assert row.last_error
    assert result == ScanResult(
        ScanOutcome.DENIED, NOT_CAPTURED, "MOCK0001", (row.last_error, WILL_RETRY)
    )
    assert captures(rig) == []


async def test_the_tenth_refusal_fails_the_row_and_says_retry_from_the_queue(
    rig: Rig, scanner: Scanner
) -> None:
    """A row one refusal short of the cap: this scan's refusal fails it."""
    await rig.sign_in("sponsor")
    rig.lead(validator="wrong")
    (row,) = rig.rows()
    assert rig.db.save(replace(row, tries=RETRY_CAP - 1, next_at=rig.clock() + 60))
    result = await scanner.scan(Badge("MOCK0001", "v4l1d01", "wrong"))
    (row,) = rig.rows()
    assert row.status is Status.FAILED
    assert result.outcome is ScanOutcome.DENIED
    assert result.details == (row.last_error, RETRY_FROM_QUEUE)


async def test_a_lost_answer_says_may_be_recorded_twice_and_loses_nothing(
    db: OutboxDb, storage: Storage, credentials: CredentialStorage
) -> None:
    """Non-idempotent with ``lost_response``: queued and flagged, then synced (D-57)."""
    rig = Rig(db, storage, credentials, "non_idempotent")
    scanner = Scanner(rig)
    scanner.start()
    try:
        await rig.sign_in("sponsor")
        rig.state.faults.inject("lost_response")
        result = await scanner.scan()
        assert result == ScanResult(
            ScanOutcome.QUEUED, SAVED, "MOCK0001", (MAY_BE_TWICE,)
        )
        rig.clock.at += 60  # the backoff; then the resend lands
        again = await scanner.scan()
        assert again == ScanResult(
            ScanOutcome.ACCEPTED, CAPTURED, "Ada", ("MOCK0001", MAY_BE_TWICE)
        )
        assert captures(rig) == [(1, "MOCK0001")] * 2  # both kept: none lost
    finally:
        await scanner.stop()


async def test_the_handler_never_sends_and_the_wait_ends(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no worker, nothing is sent: after the wait, "Saved. Will sync." (D-407)."""
    monkeypatch.setattr(lead_capture, "WAIT_SECONDS", 0.05)
    await rig.sign_in("sponsor")
    result = await Scanner(rig).scan(GRACE)
    assert result == ScanResult(ScanOutcome.QUEUED, SAVED, "MOCK0002")
    assert rig.sends() == []
    assert rig.staff.pending == 1  # the chip counts it at once


async def test_a_scan_the_outbox_can_t_store_says_so(rig: Rig) -> None:
    """A closed or missing outbox: "Not captured", "Couldn't save…" (D-120)."""
    await rig.sign_in("sponsor")
    rig.db.close()
    result = await Scanner(rig).scan()
    assert result == ScanResult(
        ScanOutcome.DENIED, NOT_CAPTURED, "MOCK0001", (NOT_SAVED,)
    )
    missing = await capture(
        None,
        rig.staff,
        lambda: None,
        ADA,
        owner=rig.account.owner,
        sponsor=None,
        clock=rig.clock,
    )
    assert missing == result
