"""Tests for ``door_check.check_in()``: a door admission, decided on the device, queued.

Each test signs a real ``Account`` in as the mock's door staff (``tests/sync_rig.py``),
loads the session's attendee list from the mock as Door check does, and scans through
``check_in()``; a real ``SyncWorker`` sends what was queued when the test drains it.
The mock checks every signature and records every redemption, so "redeemed once" is
its own count (#766; DOOR-04, DOOR-07, STORE-12, API-07; D-56, D-57, D-410, D-441).
"""

import asyncio
import logging
from collections.abc import Iterable
from pathlib import Path

import pytest

from pycon_us import door_check
from pycon_us.core.admission import Attendee, Inventory, headcount, redeem_errors
from pycon_us.core.badges import Badge, ScanOutcome, ScanResult, Tag
from pycon_us.core.check_in import AttendeeProducts
from pycon_us.core.outbox import Kind, Status
from pycon_us.door_check import (
    ALREADY,
    ANOTHER_DEVICE,
    CANT_CHECK,
    CHECKED_IN,
    LOOKUP_FAILED,
    NO_CONNECTION,
    NOT_CHECKED_IN,
    NOT_REGISTERED,
    NOT_SAVED,
    SAVED,
    check_in,
)
from pycon_us.door_inventory import load_inventory
from pycon_us.services.api import ApiClient, ApiError
from pycon_us.services.credentials import CredentialStorage
from pycon_us.services.outbox_db import OutboxDb
from pycon_us.services.storage import Storage
from tests import accounts
from tests.sync_rig import Rig, outbox_db
from tools.mock_api.state import Redemption

shared, storage, keystore, credentials = (
    accounts.shared,
    accounts.storage,
    accounts.keystore,
    accounts.credentials,
)
db = outbox_db

ADA = Badge("MOCK0001", "v4l1d01", "v4l1d01")
GRACE = Badge("MOCK0002", "v4l1d02", "v4l1d02")
LINUS = Badge("MOCK0003", "v4l1d03", "v4l1d03")
MARGARET = Badge("MOCK0004", "v4l1d04", "v4l1d04")
DECORATORS = 10
ASYNC = 11
SUMMIT = 20
VEGETARIAN = (Tag("Vegetarian"),)
ALREADY_REDEEMED = "Wed May 13 9:00 AM - All about decorators was already redeemed."


class Door:
    """Door check's side of a rig: one visit's scans, for some products.

    Attributes:
        rig: The signed-in session.
        products: The session's products.
        inventory: The attendee list, as ``list()`` loaded it.
        session: The visit's id, part of each row's key.
        kicks: How often a scan asked the worker for a pass.
    """

    def __init__(self, rig: Rig, products: Iterable[int], session: str = "v1") -> None:
        """Hold the rig and the products; the list is empty until ``load()``."""
        self.rig = rig
        self.products = tuple(products)
        self.inventory = Inventory()
        self.session = session
        self.kicks = 0
        self.looked_up: dict[str, Attendee] = {}

    async def load(self) -> None:
        """Load the products' attendee list from the mock, as the screen does."""
        loaded = await load_inventory(self.rig.api, self.products, lambda *_: None)
        assert loaded.failed == ()
        self.inventory = loaded.inventory

    async def scan(self, badge: Badge = ADA) -> ScanResult:
        """Scan ``badge`` as the signed-in account; a kick is only counted."""

        def kick() -> None:
            """Count the request for a pass: the test drains the worker itself."""
            self.kicks += 1

        return await check_in(
            self.rig.db,
            self.rig.staff,
            kick,
            self.rig.api,
            badge,
            owner=self.rig.account.owner,
            session=self.session,
            product_ids=self.products,
            inventory=self.inventory,
            looked_up=self.looked_up,
            clock=self.rig.clock,
        )


@pytest.fixture
async def rig(db: OutboxDb, storage: Storage, credentials: CredentialStorage) -> Rig:
    """The rig over the idempotent mock, signed in as the door staff."""
    signed = Rig(db, storage, credentials)
    await signed.sign_in("staff")
    return signed


async def door(rig: Rig, *products: int) -> Door:
    """A visit for ``products`` (both tutorials by default), its list loaded."""
    visit = Door(rig, products or (DECORATORS, ASYNC))
    await visit.load()
    return visit


def redeemed(rig: Rig) -> list[tuple[str, int, int]]:
    """Each redemption the mock recorded: the code, the product and the quantity."""
    return [(r.access_code, r.product_id, r.quantity) for r in rig.state.redemptions]


def redeems(rig: Rig) -> int:
    """How many redeem POSTs were sent: the outbox's sends, never a lookup's."""
    return sum(path == "check_in/redeem_products/" for path, _ in rig.sends())


def other_device(rig: Rig, code: str = "MOCK0001", product: int = DECORATORS) -> None:
    """Record a redemption as another device's earlier check-in would have."""
    stamp = "2026-05-13T08:00:00.000Z"
    rig.state.redemptions.append(Redemption(code, product, 1, stamp))


async def test_a_known_badge_is_checked_in_at_once_and_syncs_once(rig: Rig) -> None:
    """Ada is "Checked in" without a send; the worker then redeems product 10."""
    visit = await door(rig)
    result = await visit.scan()
    assert result == ScanResult(
        ScanOutcome.ACCEPTED, CHECKED_IN, "Ada Example", (), "MOCK0001", VEGETARIAN
    )
    assert redeems(rig) == 0  # the handler never sends a row itself (D-407)
    assert (visit.kicks, rig.staff.pending) == (1, 1)
    await rig.worker().drain()
    assert redeemed(rig) == [("MOCK0001", DECORATORS, 1)]
    (row,) = rig.rows()
    assert (row.kind, row.status, redeem_errors(row)) == (Kind.DOOR, Status.SYNCED, ())


async def test_a_quantity_over_one_admits_that_many(rig: Rig) -> None:
    """Linus bought two of the decorators tutorial: "Admits 2", both redeemed."""
    visit = await door(rig)
    result = await visit.scan(LINUS)
    assert (result.word, result.title, result.details) == (
        CHECKED_IN,
        "Linus Placeholder",
        ("Admits 2",),
    )
    await rig.worker().drain()
    assert redeemed(rig) == [("MOCK0003", DECORATORS, 2)]


async def test_two_products_bought_go_in_one_row(rig: Rig) -> None:
    """Both of an attendee's products of the session are one check-in, one row."""
    rig.state.attendees["MOCK0001"].products[ASYNC] = 1
    visit = await door(rig)
    await visit.scan()
    (row,) = rig.rows()
    assert row.idem_key == "MOCK0001|10,11|v1"
    assert row.payload["product-redeem-10"] == DECORATORS
    assert row.payload["product-redeem-11"] == ASYNC
    await rig.worker().drain()
    assert sorted(redeemed(rig)) == [("MOCK0001", 10, 1), ("MOCK0001", 11, 1)]


async def test_a_rescan_says_already_checked_in_and_queues_nothing(rig: Rig) -> None:
    """Pending or synced, the row covers the product: "Already checked in" (STORE-12).

    A later visit (a relaunch) reads the same kept rows, and nothing more is sent.
    """
    visit = await door(rig)
    await visit.scan()
    pending = await visit.scan()
    assert pending == ScanResult(
        ScanOutcome.DUPLICATE, ALREADY, "Ada Example", (), "MOCK0001", VEGETARIAN
    )
    await rig.worker().drain()
    later = Door(rig, visit.products, session="v2")
    later.inventory = visit.inventory
    assert (await later.scan()).word == ALREADY
    assert len(rig.rows()) == 1
    assert visit.kicks + later.kicks == 1  # only the admission asked for a pass
    assert redeemed(rig) == [("MOCK0001", DECORATORS, 1)]


async def test_another_session_gets_its_own_row(rig: Rig) -> None:
    """Linus at the tutorial, then at the summit: two check-ins (Ionic dropped one)."""
    await (await door(rig, DECORATORS)).scan(LINUS)
    summit = await door(rig, SUMMIT)
    assert (await summit.scan(LINUS)).word == CHECKED_IN
    assert [row.idem_key for row in rig.rows()] == [
        "MOCK0003|10|v1",
        "MOCK0003|20|v1",
    ]
    await rig.worker().drain()
    assert redeemed(rig) == [("MOCK0003", 10, 2), ("MOCK0003", 20, 1)]


async def test_an_unknown_badge_is_checked_in_from_the_lookup(rig: Rig) -> None:
    """Off the list, the lookup's quantities admit them, with the lookup's name."""
    visit = Door(rig, (DECORATORS,))  # the list never loaded
    result = await visit.scan()
    assert (result.outcome, result.word, result.title) == (
        ScanOutcome.ACCEPTED,
        CHECKED_IN,
        "Ada Example",
    )
    assert redeems(rig) == 0  # a lookup, no send
    assert (await visit.scan()).word == ALREADY  # the kept row, no second lookup


def count_lookups(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Count the door lookups: each call's code is appended to the returned list."""
    calls: list[str] = []
    fetch = door_check.fetch_attendee_products

    async def counted(
        api: ApiClient, code: str, ids: Iterable[int], *, door: bool
    ) -> AttendeeProducts:
        """Record the lookup, then answer as the mock does."""
        calls.append(code)
        return await fetch(api, code, ids, door=door)

    monkeypatch.setattr(door_check, "fetch_attendee_products", counted)
    return calls


async def test_an_off_list_rescan_keeps_the_lookups_allergy(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The list failed to load: Grace's rescan still shows her name and allergy.

    The lookup's attendee is kept in memory, so the rescan asks nothing, queues
    nothing and leaves the headcount at 1 (DOOR-05, D-442).
    """
    lookups = count_lookups(monkeypatch)
    visit = Door(rig, (ASYNC,))  # the list never loaded
    assert (await visit.scan(GRACE)).word == CHECKED_IN
    again = await visit.scan(GRACE)
    assert (again.outcome, again.word, again.title, again.tags) == (
        ScanOutcome.DUPLICATE,
        ALREADY,
        "Grace Sample",
        (Tag("Allergy: peanuts", warning=True),),
    )
    assert "Allergy: peanuts." in again.spoken
    assert lookups == ["MOCK0002"]
    assert len(rig.rows()) == 1
    assert headcount(rig.rows(), (ASYNC,)) == 1


async def test_an_off_list_rescan_after_a_relaunch_asks_for_the_details(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A kept row with nothing in memory: the lookup names Grace, nothing is queued."""
    await Door(rig, (ASYNC,)).scan(GRACE)
    lookups = count_lookups(monkeypatch)
    relaunched = Door(rig, (ASYNC,), session="v2")
    again = await relaunched.scan(GRACE)
    assert (again.word, again.title, again.tags) == (
        ALREADY,
        "Grace Sample",
        (Tag("Allergy: peanuts", warning=True),),
    )
    assert lookups == ["MOCK0002"]
    assert (len(rig.rows()), relaunched.kicks) == (1, 0)


async def test_overlapping_lookups_of_two_visits_check_in_once(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two visits whose lookups overlap admit the badge once: one row, one kick.

    The first visit left while its lookup was pending (Flet doesn't cancel the
    handler); the second scanned the badge before either lookup answered.
    """
    started = 0
    both = asyncio.Event()
    fetch = door_check.fetch_attendee_products

    async def gated(
        api: ApiClient, code: str, ids: Iterable[int], *, door: bool
    ) -> AttendeeProducts:
        """Hold each lookup until both have started, then answer as the mock does."""
        nonlocal started
        started += 1
        if started == 2:
            both.set()
        await both.wait()
        return await fetch(api, code, ids, door=door)

    monkeypatch.setattr(door_check, "fetch_attendee_products", gated)
    before, after = (Door(rig, (DECORATORS,), session=s) for s in ("v1", "v2"))
    results = await asyncio.gather(before.scan(), after.scan())
    assert sorted(result.word for result in results) == [ALREADY, CHECKED_IN]
    assert len(rig.rows()) == 1
    assert before.kicks + after.kicks == 1


async def test_an_unknown_badge_with_none_left_was_checked_in_elsewhere(
    rig: Rig,
) -> None:
    """Bought, but the lookup shows none left: "Checked in on another device"."""
    other_device(rig)
    result = await Door(rig, (DECORATORS,)).scan()
    assert result == ScanResult(
        ScanOutcome.DUPLICATE,
        ALREADY,
        "Ada Example",
        (ANOTHER_DEVICE,),
        "MOCK0001",
        VEGETARIAN,
    )
    assert rig.rows() == []


@pytest.mark.parametrize("badge", [MARGARET, Badge("NOPE0000", "x", "x")])
async def test_nothing_bought_or_unknown_is_not_registered(
    rig: Rig, badge: Badge
) -> None:
    """Margaret has no tutorial; the server doesn't know NOPE0000 (404)."""
    result = await (await door(rig)).scan(badge)
    assert result == ScanResult(
        ScanOutcome.DENIED, NOT_REGISTERED, badge.code, (), badge.code
    )
    assert rig.rows() == []


@pytest.mark.parametrize("status", [500, None])
async def test_a_refused_lookup_logs_its_status_and_none_of_the_server_s_text(
    rig: Rig,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    status: int | None,
) -> None:
    """The log holds the status alone, though the server's text repeats the code (D-72).

    Staff see the same result as ever: "Can't check this badge", the lookup failed.
    """

    async def refuse(*_args: object, **_kwargs: object) -> AttendeeProducts:
        """Refuse the lookup with a message that holds the badge's code."""
        raise ApiError(status, "no badge MOCK0001")

    monkeypatch.setattr(door_check, "fetch_attendee_products", refuse)
    with caplog.at_level(logging.DEBUG, logger=door_check.__name__):
        result = await door_check.look_up(rig.api, "MOCK0001", (DECORATORS,))
    assert result == ScanResult(
        ScanOutcome.DENIED, CANT_CHECK, "MOCK0001", (LOOKUP_FAILED,), "MOCK0001"
    )
    logged = [r for r in caplog.records if r.name == door_check.__name__]
    assert [r.getMessage() for r in logged] == [f"door lookup refused: {status}"]


async def test_offline_known_badges_queue_and_sync_once_after_a_relaunch(
    rig: Rig, tmp_path: Path
) -> None:
    """No connection: the list admits ("Saved. Will sync."), a stranger can't be checked.

    After a kill and a relaunch with the mock back, each check-in is redeemed once.
    """
    visit = await door(rig)
    rig.state.faults.inject("connect", until_cleared=True)
    assert (await visit.scan()).details == ()  # no pass has ended offline yet
    await rig.worker().drain()
    assert rig.staff.offline
    linus = await visit.scan(LINUS)
    assert (linus.word, linus.details) == (CHECKED_IN, ("Admits 2", SAVED))
    stranger = await Door(rig, (SUMMIT,)).scan(ADA)  # not on that (empty) list
    assert stranger == ScanResult(
        ScanOutcome.DENIED, CANT_CHECK, "MOCK0001", (NO_CONNECTION,), "MOCK0001"
    )
    rig.db.close()  # the kill
    rig.state.faults.clear()
    rig.db = OutboxDb(tmp_path / "outbox", 2026)  # the relaunch
    rig.clock.at += 60
    await rig.worker().drain()
    assert redeemed(rig) == [("MOCK0001", 10, 1), ("MOCK0003", 10, 2)]
    assert [row.status for row in rig.rows()] == [Status.SYNCED] * 2
    rig.db.close()


async def test_a_reply_with_errors_syncs_the_row_and_keeps_the_message(
    rig: Rig,
) -> None:
    """Already redeemed on another device after the list loaded: synced, kept (D-441).

    The person is in; resending can't change the server's answer, so it isn't retried.
    """
    visit = await door(rig)
    other_device(rig)
    assert (await visit.scan()).word == CHECKED_IN
    await rig.worker().drain()
    (row,) = rig.rows()
    assert (row.status, row.tries) == (Status.SYNCED, 0)
    assert redeem_errors(row) == (ALREADY_REDEEMED,)
    assert redeems(rig) == 1


async def test_a_lost_answer_flags_the_row_and_loses_nothing(
    db: OutboxDb, storage: Storage, credentials: CredentialStorage
) -> None:
    """Non-idempotent with ``lost_response``: flagged, then synced once (D-57, D-410)."""
    rig = Rig(db, storage, credentials, "non_idempotent")
    await rig.sign_in("staff")
    visit = await door(rig)
    rig.state.faults.inject("lost_response")
    assert (await visit.scan()).word == CHECKED_IN
    worker = rig.worker()
    await worker.drain()
    (row,) = rig.rows()
    assert (row.status, row.maybe_sent) == (Status.PENDING, True)
    rig.clock.at += 60
    await worker.drain()
    (row,) = rig.rows()
    assert (row.status, row.maybe_sent) == (Status.SYNCED, True)
    assert redeemed(rig) == [("MOCK0001", DECORATORS, 1)]  # the first send's
    assert redeem_errors(row) == (ALREADY_REDEEMED,)  # the resend's answer


async def test_a_check_in_the_outbox_can_t_store_says_so(rig: Rig) -> None:
    """A closed or missing outbox: "Not checked in", "Couldn't save…" (D-120)."""
    visit = await door(rig)
    rig.db.close()
    result = await visit.scan()
    assert result == ScanResult(
        ScanOutcome.DENIED, NOT_CHECKED_IN, "MOCK0001", (NOT_SAVED,), "MOCK0001"
    )
    missing = await check_in(
        None,
        rig.staff,
        lambda: None,
        rig.api,
        ADA,
        owner=rig.account.owner,
        session="v1",
        product_ids=(DECORATORS,),
        inventory=visit.inventory,
        looked_up={},
    )
    assert missing == result
    assert visit.kicks == 0
