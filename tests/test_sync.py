"""``SyncWorker.drain()`` against the in-process mock and its faults (#692; D-56, D-57).

Each test queues rows through ``core/outbox.py``'s rules into a real ``OutboxDb``, signs
a real ``Account`` in to the mock and drains; the mock checks every signature and counts
every lead, note and redemption it applied, so "exactly once" is the mock's own count.
"""

import asyncio
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from pycon_us.core.outbox import NETWORK_BACKOFF, RETRY_CAP, Kind, Status
from pycon_us.services.credentials import CredentialStorage
from pycon_us.services.outbox_db import OutboxDb
from pycon_us.services.storage import Storage
from tests import accounts
from tests.mock_calls import account
from tests.sync_rig import Rig

shared, storage, keystore, credentials = (
    accounts.shared,
    accounts.storage,
    accounts.keystore,
    accounts.credentials,
)

CAPTURE = "lead_retrieval/capture/"
NOTE = "lead_retrieval/MOCK0001/note/"
REDEEM = "check_in/redeem_products/"


@pytest.fixture
def db(tmp_path: Path) -> Iterator[OutboxDb]:
    """Yield an outbox in its own directory (not the storage's), closed afterwards."""
    directory = tmp_path / "outbox"
    directory.mkdir()
    database = OutboxDb(directory)
    yield database
    database.close()


@pytest.fixture
def rig(db: OutboxDb, storage: Storage, credentials: CredentialStorage) -> Rig:
    """The rig over the idempotent mock, signed out."""
    return Rig(db, storage, credentials)


def key(rig: Rig, role: str) -> str:
    """The seeded API key of ``role``, which every send of its rows must carry."""
    return account(rig.state, role).key


async def test_a_lead_its_note_and_a_check_in_sync_in_order_in_one_pass(
    rig: Rig,
) -> None:
    """Leads, then check-ins, then notes; the note goes once its lead has synced."""
    await rig.sign_in("staff")
    rig.note("Interest: hot", sponsor="2")  # queued first, sent last
    rig.door()
    rig.lead(sponsor="2")
    await rig.worker().drain()
    staff = key(rig, "staff")
    assert rig.sends() == [(CAPTURE, staff), (REDEEM, staff), (NOTE, staff)]
    assert {row.status for row in rig.rows()} == {Status.SYNCED}
    assert [lead.sponsor_id for lead in rig.state.leads] == [2]
    assert [(n.sponsor_id, n.note) for n in rig.state.notes] == [(2, "Interest: hot")]
    assert [r.product_id for r in rig.state.redemptions] == [10]
    assert (rig.staff.pending, rig.staff.synced, rig.staff.syncing) == (0, 3, False)
    assert rig.staff.last_sync_at == rig.clock()
    assert rig.staff.last_error is None


async def test_the_answer_is_kept_and_a_sponsors_own_lead_names_no_sponsor(
    rig: Rig,
) -> None:
    """A sponsor's own scan sends no ``sponsor_id``; the reply lands in the payload."""
    await rig.sign_in("sponsor")
    rig.lead()
    await rig.worker().drain()
    (sent,) = rig.wire.sent[-1:]
    assert "sponsor_id" not in sent.url.query.decode()
    (row,) = rig.rows()
    assert row.payload["result"] == {"first_name": "Ada"}
    assert [lead.sponsor_id for lead in rig.state.leads] == [1]


async def test_a_note_waits_while_its_lead_has_not_synced(rig: Rig) -> None:
    """A lead the server refuses keeps its note unsent, pass after pass."""
    await rig.sign_in("sponsor")
    rig.lead(validator="wrong")
    rig.note("Follow-up: call")
    await rig.worker().drain()
    assert rig.sends() == [(CAPTURE, key(rig, "sponsor"))]
    lead, note = rig.rows()
    assert (lead.kind, lead.tries, note.status) == (Kind.LEAD, 1, Status.PENDING)
    assert rig.state.notes == []


async def test_no_connection_ends_the_pass_uncounted_and_retries_after_60_s(
    rig: Rig,
) -> None:
    """``connect``: tries unchanged, the next row unsent, both sent a tick later."""
    await rig.sign_in("staff")
    rig.lead(sponsor="2")
    rig.door()
    rig.state.faults.inject("connect")
    worker = rig.worker()
    await worker.drain()
    assert rig.sends() == [(CAPTURE, key(rig, "staff"))]  # the door row never went
    assert [row.tries for row in rig.rows()] == [0, 0]
    assert rig.staff.last_error == "ConnectError: mock fault: connect"
    assert rig.staff.last_sync_at is None
    rig.clock.at += NETWORK_BACKOFF / 2
    await worker.drain()  # the lead isn't due yet; the door row is, and goes
    assert [row.status for row in rig.rows()] == [Status.PENDING, Status.SYNCED]
    rig.clock.at += NETWORK_BACKOFF / 2
    await worker.drain()
    assert {row.status for row in rig.rows()} == {Status.SYNCED}
    assert len(rig.state.leads) == len(rig.state.redemptions) == 1


async def test_ten_refusals_make_a_row_failed(rig: Rig) -> None:
    """Every ``ApiError`` counts; the tenth makes the row ``failed`` (D-56)."""
    await rig.sign_in("sponsor")
    rig.lead(validator="wrong")
    worker = rig.worker()
    for _ in range(RETRY_CAP):
        await worker.drain()
        rig.clock.at += NETWORK_BACKOFF
    (row,) = rig.rows()
    assert (row.status, row.tries) == (Status.FAILED, RETRY_CAP)
    assert row.last_error == "Wrong badge validator."
    assert rig.staff.failed == 1
    assert rig.staff.last_error == "404 Wrong badge validator."
    await worker.drain()  # a failed row waits for "Retry failed"
    assert len(rig.sends()) == RETRY_CAP


async def test_every_record_is_applied_once_despite_lost_replies_and_skew(
    rig: Rig,
) -> None:
    """Idempotent mock, a skewed clock, a refused connection, each first reply lost.

    D-57's guarantee: the mock commits each lead, check-in and note the first time it
    gets it and the reply never arrives, yet it holds one of each, and every row ends
    synced with no counted failure. The device learns the skew at sign-in (D-53).
    """
    rig.state.skew = 900
    await rig.sign_in("all")
    rig.lead()
    rig.door()
    rig.note("Interest: warm")
    seen: set[str] = set()

    def lose_first_reply(request: httpx.Request) -> None:
        """Arm ``lost_response`` for the first send to each endpoint."""
        if request.url.path not in seen:
            seen.add(request.url.path)
            rig.state.faults.inject("lost_response")

    rig.wire.before = lose_first_reply
    rig.state.faults.inject("connect")  # taken first; the lost reply waits its turn
    worker = rig.worker()
    for _ in range(5):
        await worker.drain()
        rig.clock.at += NETWORK_BACKOFF
    assert {row.status for row in rig.rows()} == {Status.SYNCED}
    assert all(row.tries == 0 for row in rig.rows())
    assert len(rig.state.leads) == len(rig.state.notes) == 1
    assert len(rig.state.redemptions) == 1
    # Each endpoint was sent its record again after the lost reply.
    paths = [path for path, _ in rig.sends()]
    assert (paths.count(CAPTURE), paths.count(REDEEM), paths.count(NOTE)) == (3, 2, 2)


async def test_each_owners_rows_go_with_its_own_key_and_sponsor(rig: Rig) -> None:
    """An account switch leaves the old owner's rows to it; each keeps its snapshot."""
    await rig.sign_in("staff")
    staff_owner = rig.account.owner
    rig.lead(sponsor="2")
    await rig.sign_out()
    await rig.sign_in("all")
    rig.lead(code="MOCK0002", validator="v4l1d02", sponsor="3")
    await rig.worker().drain()
    assert rig.sends() == [(CAPTURE, key(rig, "all"))]
    assert [row.status for row in rig.rows(staff_owner)] == [Status.PENDING]
    await rig.sign_out()
    await rig.sign_in("staff")
    await rig.worker().drain()
    assert rig.sends()[-1] == (CAPTURE, key(rig, "staff"))
    assert [(lead.sponsor_id, lead.access_code) for lead in rig.state.leads] == [
        (3, "MOCK0002"),
        (2, "MOCK0001"),
    ]


async def test_a_sign_out_mid_pass_stops_it_before_the_next_row(rig: Rig) -> None:
    """No row is sent once its owner has gone, not even with no key."""
    await rig.sign_in("staff")
    rig.lead(sponsor="2")
    rig.door()
    rig.wire.then = rig.sign_out  # right after the lead's reply
    await rig.worker().drain()
    assert rig.sends() == [(CAPTURE, key(rig, "staff"))]
    assert rig.state.redemptions == []


async def test_a_pause_mid_pass_stops_it_before_the_next_row(rig: Rig) -> None:
    """Paused during the first of two sends, the second waits for the resume (D-407)."""
    await rig.sign_in("staff")
    rig.lead(sponsor="2")
    rig.door()
    foreground = asyncio.Event()
    foreground.set()

    async def pause() -> None:
        """Send the app to the background, as ``on_pause()`` does."""
        foreground.clear()

    rig.wire.then = pause  # right after the lead's reply
    await rig.worker(foreground).drain()
    assert rig.sends() == [(CAPTURE, key(rig, "staff"))]
    assert [row.status for row in rig.rows()] == [Status.SYNCED, Status.PENDING]
    foreground.set()
    await rig.worker(foreground).drain()
    assert [row.status for row in rig.rows()] == [Status.SYNCED, Status.SYNCED]


async def test_a_skew_retry_keeps_its_key_through_an_account_switch(rig: Rig) -> None:
    """The clock-corrected second attempt signs with the first one's key (D-56).

    The account changes while the skew-refused capture is in flight; the retry still
    carries the row owner's key, never the new account's.
    """
    await rig.sign_in("staff")
    rig.lead(sponsor="2")
    rig.state.skew = 900  # the client learnt none at sign-in: the capture is refused

    async def switch() -> None:
        """Sign out and in as another account while the 403 is on its way back."""
        await rig.sign_out()
        await rig.sign_in("all")

    rig.wire.then = switch
    await rig.worker().drain()
    assert rig.sends() == [(CAPTURE, key(rig, "staff"))] * 2
    assert len(rig.state.leads) == 1


async def test_a_refused_key_stops_the_pass_uncounted_and_says_so(rig: Rig) -> None:
    """``revoked``: the row waits with its tries, and the account's flags are asked."""
    await rig.sign_in("sponsor")
    rig.lead()
    rig.lead(code="MOCK0002", validator="v4l1d02")
    rig.state.faults.inject("revoked")
    await rig.worker().drain()
    assert len(rig.sends()) == 1
    assert [row.tries for row in rig.rows()] == [0, 0]
    assert rig.refused == 1
    assert rig.staff.last_error == "401 API key revoked."


async def test_an_expired_account_sends_nothing(rig: Rig) -> None:
    """While ``expired`` no private call is made (D-403)."""
    await rig.sign_in("sponsor")
    rig.lead()
    rig.account.expired = True
    await rig.worker().drain()
    assert rig.sends() == []
    assert rig.staff.syncing is False


async def test_one_pass_at_a_time(rig: Rig) -> None:
    """Two drains at once send each row once: the second sees the first under way."""
    await rig.sign_in("sponsor")
    rig.lead()
    worker = rig.worker()
    await asyncio.gather(worker.drain(), worker.drain(), rig.worker().drain())
    assert len(rig.sends()) == 1


async def test_a_cancelled_pass_leaves_its_row_whole_and_due(rig: Rig) -> None:
    """Cancelled mid-send, the row is as it was, and the next pass sends it."""
    await rig.sign_in("sponsor")
    rig.lead()
    gate = asyncio.Event()
    rig.wire.gate = gate.wait()
    task = asyncio.create_task(rig.worker().drain())
    while not rig.sends():
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    rig.wire.gate = None
    (row,) = rig.rows()
    assert (row.status, row.tries, row.next_at) == (Status.PENDING, 0, rig.clock())
    assert rig.staff.syncing is False
    await rig.worker().drain()
    assert [row.status for row in rig.rows()] == [Status.SYNCED]


async def test_a_note_edited_while_sent_is_sent_again_in_the_same_pass(
    rig: Rig,
) -> None:
    """The edit's revision is new, so the pass sends the new text too (D-56)."""
    await rig.sign_in("sponsor")
    rig.lead()
    await rig.worker().drain()
    rig.note("first")

    async def edit() -> None:
        rig.note("second")

    rig.wire.then = edit
    await rig.worker().drain()
    assert [n.note for n in rig.state.notes] == ["first", "second"]
    assert [row.status for row in rig.rows()] == [Status.SYNCED, Status.SYNCED]
