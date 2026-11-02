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
    ALSO_FOR,
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
    assert result == ScanResult(
        ScanOutcome.ACCEPTED, CAPTURED, "Ada", ("MOCK0001",), "MOCK0001"
    )
    assert rig.staff.synced == 1
    again = await scanner.scan()
    assert again == ScanResult(
        ScanOutcome.DUPLICATE, ALREADY, "Ada", ("MOCK0001",), "MOCK0001"
    )
    assert captures(rig) == [(1, "MOCK0001")]  # the repeat sent nothing


async def test_a_staff_scan_goes_to_the_sponsor_picked(
    rig: Rig, scanner: Scanner
) -> None:
    """The row snapshots the sponsor, and the capture names it (STORE-11)."""
    await rig.sign_in("staff")
    result = await scanner.scan(sponsor=SAMPLE)
    assert result == ScanResult(
        ScanOutcome.ACCEPTED,
        CAPTURED,
        "Ada",
        ("For Sample Systems", "MOCK0001"),
        "MOCK0001",
        sponsor=SAMPLE,
    )
    assert captures(rig) == [(3, "MOCK0001")]
    (row,) = rig.rows()
    assert (row.sponsor_id, row.sponsor_name) == ("3", "Sample Systems")


async def test_the_same_sponsor_twice_says_already_and_sends_nothing(
    rig: Rig, scanner: Scanner
) -> None:
    """A repeat for the sponsor is "Already in your leads", saying which one (D-459)."""
    await rig.sign_in("staff")
    await scanner.scan(sponsor=EXAMPLE)
    sends = len(rig.sends())
    again = await scanner.scan(sponsor=EXAMPLE)
    assert again == ScanResult(
        ScanOutcome.DUPLICATE,
        ALREADY,
        "Ada",
        ("For Example Corp", "MOCK0001"),
        "MOCK0001",
        sponsor=EXAMPLE,
    )
    assert len(rig.sends()) == sends
    assert captures(rig) == [(1, "MOCK0001")]


async def test_another_sponsor_after_a_synced_row_gets_its_own_lead_and_says_so(
    rig: Rig, scanner: Scanner
) -> None:
    """A second sponsor's scan is captured, and names the first; repeats stay repeats.

    Each sponsor has the lead once, whichever is scanned for again (D-459).
    """
    await rig.sign_in("staff")
    await scanner.scan(sponsor=EXAMPLE)
    second = await scanner.scan(sponsor=SAMPLE)
    assert second == ScanResult(
        ScanOutcome.ACCEPTED,
        CAPTURED,
        "Ada",
        ("For Sample Systems", f"{ALSO_FOR} Example Corp", "MOCK0001"),
        "MOCK0001",
        sponsor=SAMPLE,
    )
    assert captures(rig) == [(1, "MOCK0001"), (3, "MOCK0001")]
    for sponsor, other in ((EXAMPLE, SAMPLE), (SAMPLE, EXAMPLE)):
        again = await scanner.scan(sponsor=sponsor)
        assert again.word == ALREADY
        assert again.details[:2] == (f"For {sponsor.name}", f"{ALSO_FOR} {other.name}")
    assert len(captures(rig)) == 2
    assert [row.sponsor_id for row in rig.rows()] == ["1", "3"]


async def test_another_sponsor_after_a_pending_row_queues_its_own_and_both_sync(
    rig: Rig, scanner: Scanner
) -> None:
    """Offline, each sponsor's scan keeps its own row; online, each reaches its sponsor.

    "Saved. Will sync." says who it is for, and a repeat leaves one row per sponsor.
    """
    await rig.sign_in("staff")
    rig.state.faults.inject("connect", until_cleared=True)
    first = await scanner.scan(sponsor=EXAMPLE)
    assert first == ScanResult(
        ScanOutcome.QUEUED,
        SAVED,
        "MOCK0001",
        ("For Example Corp",),
        "MOCK0001",
        sponsor=EXAMPLE,
    )
    assert rig.staff.offline and rig.staff.pending == 1
    second = await scanner.scan(sponsor=SAMPLE)  # switched sponsor, still offline
    assert second.outcome is ScanOutcome.QUEUED
    assert second.details == ("For Sample Systems", f"{ALSO_FOR} Example Corp")
    await scanner.scan(sponsor=SAMPLE)  # the same one again: no third row
    assert rig.staff.pending == 2
    rig.state.faults.clear()
    rig.clock.at += 60  # the backoff's tick
    assert scanner.worker is not None
    await scanner.worker.drain()
    assert captures(rig) == [(1, "MOCK0001"), (3, "MOCK0001")]
    assert [(row.sponsor_id, row.status) for row in rig.rows()] == [
        ("1", Status.SYNCED),
        ("3", Status.SYNCED),
    ]


async def test_two_sponsors_are_no_duplicate_when_the_server_isn_t_idempotent(
    db: OutboxDb, storage: Storage, credentials: CredentialStorage
) -> None:
    """Non-idempotent: one record per sponsor, and nothing flagged, or twice (D-57)."""
    rig = Rig(db, storage, credentials, "non_idempotent")
    scanner = Scanner(rig)
    scanner.start()
    try:
        await rig.sign_in("staff")
        for sponsor in (EXAMPLE, SAMPLE, EXAMPLE, SAMPLE):
            await scanner.scan(sponsor=sponsor)
        assert captures(rig) == [(1, "MOCK0001"), (3, "MOCK0001")]
        assert not any(row.maybe_sent for row in rig.rows())
    finally:
        await scanner.stop()


async def test_a_lost_answer_flags_only_that_sponsor_s_lead(
    db: OutboxDb, storage: Storage, credentials: CredentialStorage
) -> None:
    """The second sponsor's answer is lost: its row says so, the first's stays clean."""
    rig = Rig(db, storage, credentials, "non_idempotent")
    scanner = Scanner(rig)
    scanner.start()
    try:
        await rig.sign_in("staff")
        await scanner.scan(sponsor=EXAMPLE)
        rig.state.faults.inject("lost_response")
        result = await scanner.scan(sponsor=SAMPLE)
        assert result.details[-1] == MAY_BE_TWICE
        rig.clock.at += 60  # the backoff; then the resend lands
        assert scanner.worker is not None
        await scanner.worker.drain()
        assert [(row.sponsor_id, row.maybe_sent) for row in rig.rows()] == [
            ("1", False),
            ("3", True),
        ]
        assert captures(rig) == [(1, "MOCK0001"), (3, "MOCK0001"), (3, "MOCK0001")]
    finally:
        await scanner.stop()


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
        ScanOutcome.DENIED,
        NOT_CAPTURED,
        "MOCK0001",
        (row.last_error, WILL_RETRY),
        "MOCK0001",
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
            ScanOutcome.QUEUED, SAVED, "MOCK0001", (MAY_BE_TWICE,), "MOCK0001"
        )
        rig.clock.at += 60  # the backoff; then the resend lands
        again = await scanner.scan()
        assert again == ScanResult(
            ScanOutcome.ACCEPTED,
            CAPTURED,
            "Ada",
            ("MOCK0001", MAY_BE_TWICE),
            "MOCK0001",
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
    assert result == ScanResult(ScanOutcome.QUEUED, SAVED, "MOCK0002", code="MOCK0002")
    assert rig.sends() == []
    assert rig.staff.pending == 1  # the chip counts it at once


async def test_a_scan_the_outbox_can_t_store_says_so(rig: Rig) -> None:
    """A closed or missing outbox: "Not captured", "Couldn't save…" (D-120)."""
    await rig.sign_in("sponsor")
    rig.db.close()
    result = await Scanner(rig).scan()
    assert result == ScanResult(
        ScanOutcome.DENIED, NOT_CAPTURED, "MOCK0001", (NOT_SAVED,), "MOCK0001"
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
