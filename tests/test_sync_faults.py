"""D-57's duplicates, detected and shown: which outbox rows the worker flags (#693).

Under non-idempotent semantics, a reply lost after the mock committed makes the resend
a second record, which no client can prevent. The outbox flags every row whose send
may have reached the server (`NetworkError.maybe_sent`, `ApiError.unreadable`, D-410),
so each duplicate the mock records belongs to a flagged row; a failure before the request
left flags nothing, nor does a refusal. The mock counts what it applied, so "a duplicate"
is the mock's own count.
"""

import asyncio
from collections import Counter
from collections.abc import Callable

import httpx
import pytest

from pycon_us.core import outbox
from pycon_us.core.outbox import NETWORK_BACKOFF, Status
from pycon_us.services.api import MAX_NESTING
from pycon_us.services.credentials import CredentialStorage
from pycon_us.services.outbox_db import OutboxDb
from pycon_us.services.storage import Storage
from tests import accounts
from tests.api_clients import ReplyReplaced, replying
from tests.small_stack import nested_objects
from tests.sync_rig import Rig, outbox_db
from tools.mock_api.faults import Fault
from tools.mock_api.state import Capture

shared, storage, keystore, credentials = (
    accounts.shared,
    accounts.storage,
    accounts.keystore,
    accounts.credentials,
)
db = outbox_db

type Act = Callable[[httpx.Request], None]
"""What a test does to one request: arm a mock fault, or raise a transport error."""

LEAD = ("lead", "MOCK0001")
"""The lead capture of `MOCK0001`, the first row a pass sends."""

DOOR = ("door", "MOCK0003")
"""`MOCK0003`'s check-in to product 10, of which they bought two: a second
redemption fits, so the non-idempotent mock records it."""


async def queued(rig: Rig, capture: Capture) -> Rig:
    """Sign in with every role and queue two leads and two check-ins, nothing sent.

    Args:
        rig: A rig over the mock, signed out.
        capture: The mock's semantics for a repeated record.
    """
    rig.state.capture = capture
    await rig.sign_in("all")
    rig.lead("MOCK0001")
    rig.lead("MOCK0002", "v4l1d02")
    rig.door("MOCK0003", validator="v4l1d03")
    rig.door("MOCK0001")
    return rig


def first_send_of(target: tuple[str, str], act: Act) -> Act:
    """Return a `Wire.before` hook that acts on the target row's first send only.

    Args:
        target: The row's kind and access code.
        act: Called with the request: arms a mock fault, or raises a transport error.
    """
    path = "lead_retrieval/capture/" if target[0] == "lead" else "redeem_products/"
    done: list[bool] = []

    def before(request: httpx.Request) -> None:
        sent = request.url.query + request.content
        if not done and request.url.path.endswith(path) and target[1].encode() in sent:
            done.append(True)
            act(request)

    return before


async def drain_twice(rig: Rig) -> None:
    """Drain, then again once the failed row is due: everything is sent by then."""
    worker = rig.worker()
    await worker.drain()
    rig.clock.at += NETWORK_BACKOFF
    await worker.drain()


def records(rig: Rig) -> Counter[tuple[str, str]]:
    """How many times the mock recorded each row, by its kind and access code."""
    leads = (("lead", lead.access_code) for lead in rig.state.leads)
    doors = (("door", r.access_code) for r in rig.state.redemptions)
    return Counter([*leads, *doors])


def flagged(rig: Rig) -> set[tuple[str, str]]:
    """The rows the outbox flags "may be recorded twice", by kind and access code."""
    return {(row.kind.value, row.key) for row in rig.rows() if row.maybe_sent}


@pytest.fixture
def rig(db: OutboxDb, storage: Storage, credentials: CredentialStorage) -> Rig:
    """A rig over the mock, signed out; `queued()` sets its semantics."""
    return Rig(db, storage, credentials)


@pytest.mark.parametrize("target", [LEAD, DOOR], ids=["lead", "door"])
@pytest.mark.parametrize(
    ("capture", "copies"), [("non_idempotent", 2), ("idempotent", 1)]
)
async def test_a_lost_reply_flags_exactly_its_row_and_any_duplicate_is_flagged(
    rig: Rig, target: tuple[str, str], capture: Capture, copies: int
) -> None:
    """The mock commits, the reply is lost, the resend lands: that row alone is flagged.

    Non-idempotent, the mock holds the record twice; idempotent, once. The client
    cannot tell which, so the row is flagged either way and the words say "may".
    No record is lost, and every row recorded twice is a flagged one.
    """
    await queued(rig, capture)
    rig.wire.before = first_send_of(
        target, lambda _: rig.state.faults.inject("lost_response")
    )
    await drain_twice(rig)
    assert {row.status for row in rig.rows()} == {Status.SYNCED}
    counts = records(rig)
    assert set(counts) == {LEAD, ("lead", "MOCK0002"), DOOR, ("door", "MOCK0001")}
    assert counts[target] == copies
    assert {row for row, n in counts.items() if n > 1} <= flagged(rig) == {target}
    words = {(r.kind.value, r.key): outbox.status_text(r) for r in rig.rows()}
    assert words.pop(target) == "Confirmed · may be recorded twice"
    assert set(words.values()) == {"Confirmed"}


@pytest.mark.parametrize(
    ("target", "body"),
    [
        (LEAD, b"<html>ok</html>"),
        (LEAD, b'{"code": 200}'),
        (LEAD, b'{"code": 200, "data": %b}' % nested_objects(MAX_NESTING)),
        (DOOR, b"<html>ok</html>"),
    ],
    ids=["lead-not-json", "lead-no-envelope", "lead-too-deep", "door-not-json"],
)
@pytest.mark.parametrize(
    ("capture", "copies"), [("non_idempotent", 2), ("idempotent", 1)]
)
async def test_an_unreadable_reply_flags_its_row_and_any_duplicate_is_flagged(
    rig: Rig, target: tuple[str, str], body: bytes, capture: Capture, copies: int
) -> None:
    """The mock commits, the reply can't be read, the resend lands: flagged, counted.

    An answer came, so the failure counts towards the cap (a server that always answers
    so must not be resent to for ever), and the pass goes on (#874). Like a lost reply,
    it may have been applied, so the resend may be a second record, and the row says so.
    """
    rig.state.capture = capture
    await rig.sign_in("all")
    if target == LEAD:
        rig.lead(target[1])
    else:
        rig.door(target[1], validator="v4l1d03")
    committing = rig.wire.inner
    rig.wire.inner = ReplyReplaced(committing, body)
    worker = rig.worker()
    await worker.drain()
    (row,) = rig.rows()
    assert (row.status, row.tries, row.maybe_sent) == (Status.PENDING, 1, True)
    assert outbox.status_text(row) == "Queued · may be recorded twice"
    assert row.last_error
    assert records(rig)[target] == 1
    assert rig.staff.offline is False
    rig.wire.inner = committing
    rig.clock.at += NETWORK_BACKOFF
    await worker.drain()
    (row,) = rig.rows()
    assert (row.status, row.maybe_sent) == (Status.SYNCED, True)
    assert records(rig)[target] == copies
    assert outbox.status_text(row) == "Confirmed · may be recorded twice"


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (200, b'{"code": 500, "error": "Boom."}'),
        (500, b'{"code": 500, "error": "Boom."}'),
        (502, b"<html>bad gateway</html>"),
    ],
    ids=["error-envelope-under-200", "error-status", "error-status-not-json"],
)
async def test_a_refusal_counts_without_a_flag(
    rig: Rig, status: int, body: bytes
) -> None:
    """A real refusal, under any status, is counted and says nothing of duplicates."""
    await queued(rig, "non_idempotent")
    rig.wire.inner = replying(status, body)
    await rig.worker().drain()
    assert {(row.tries, row.maybe_sent) for row in rig.rows()} == {(1, False)}


def connect_timeout(request: httpx.Request) -> None:
    """Fail the request as a connect timeout: it never left the device."""
    raise httpx.ConnectTimeout("no route in time", request=request)


@pytest.mark.parametrize(
    ("fail", "maybe_sent"),
    [
        ("connect", False),
        (connect_timeout, False),
        ("timeout", True),  # a read timeout: the server may have had it
    ],
    ids=["connect", "connect-timeout", "read-timeout"],
)
async def test_a_failure_before_the_mock_ran_records_once(
    rig: Rig, fail: Fault | Act, maybe_sent: bool
) -> None:
    """No connection flags nothing; a read timeout flags its row though it was once.

    Non-idempotent, and still one record each: the mock never ran the failed send.
    A read timeout cannot say so, so its row is flagged; a connection that was never
    made, refused or timed out, surely sent nothing.
    """
    await queued(rig, "non_idempotent")
    if callable(fail):
        rig.wire.before = first_send_of(LEAD, fail)
    else:
        rig.wire.before = first_send_of(LEAD, lambda _: rig.state.faults.inject(fail))
    await drain_twice(rig)
    assert {row.status for row in rig.rows()} == {Status.SYNCED}
    assert set(records(rig).values()) == {1}
    assert flagged(rig) == ({LEAD} if maybe_sent else set())


async def test_a_lost_reply_to_a_row_rescanned_while_sent_still_flags_it(
    rig: Rig,
) -> None:
    """A rescan during the send drops its outcome (D-56), never the flag (D-410).

    The lost reply's outcome is saved over the rescan, which changed only when the
    row is due; the resend is a second record, and the row says it may be.
    """
    await queued(rig, "non_idempotent")

    def rescan_then_lose(_: httpx.Request) -> None:
        rig.lead("MOCK0001")
        rig.state.faults.inject("lost_response")

    rig.wire.before = first_send_of(LEAD, rescan_then_lose)
    await drain_twice(rig)
    assert {row.status for row in rig.rows()} == {Status.SYNCED}
    assert records(rig)[LEAD] == 2
    assert flagged(rig) == {LEAD}


async def test_a_rescan_while_sent_keeps_the_success_and_sends_once(rig: Rig) -> None:
    """A rescan during a send that succeeds never resends the lead (D-57).

    The rescan only makes the pending row due now, so the reply's outcome is saved:
    the non-idempotent mock records one lead, and the synced row is not flagged.
    """
    await queued(rig, "non_idempotent")
    rig.wire.before = first_send_of(LEAD, lambda _: rig.lead("MOCK0001"))
    await drain_twice(rig)
    assert {row.status for row in rig.rows()} == {Status.SYNCED}
    assert records(rig)[LEAD] == 1
    assert flagged(rig) == set()


async def test_a_pass_cancelled_after_the_mock_committed_flags_its_row(
    rig: Rig,
) -> None:
    """Cancelled while the reply is on its way, the row stays due, untried, flagged.

    D-407 cancels the worker on an account or client change; the server may have had
    the send, so the resend may be a second record, and the row says so.
    """
    await queued(rig, "non_idempotent")
    held = asyncio.Event()

    async def hold() -> None:
        await held.wait()

    rig.wire.then = hold
    task = asyncio.create_task(rig.worker().drain())
    while not records(rig):
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    lead = next(row for row in rig.rows() if (row.kind.value, row.key) == LEAD)
    assert (lead.status, lead.tries, lead.maybe_sent) == (Status.PENDING, 0, True)
    await rig.worker().drain()
    assert {row.status for row in rig.rows()} == {Status.SYNCED}
    assert records(rig)[LEAD] == 2
    assert flagged(rig) == {LEAD}
