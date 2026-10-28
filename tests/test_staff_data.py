"""Staff data's safety: account switch, sign-out and Clear staff data (#695, D-414).

No path deletes an unsynced row without naming how many, an account switch never shows
or sends the previous owner's rows as the new account's, and Clear staff data removes
every staff key of the storage table, a key added later included. The rows are in a
real ``outbox.db``; the accounts sign in to the in-process mock (``tests/sync_rig.py``).
"""

import asyncio
import contextlib
import inspect
import typing
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

from pycon_us.account import SignIn
from pycon_us.config import load_year
from pycon_us.core import outbox
from pycon_us.core.outbox import Row, Status
from pycon_us.memory import ViewMemory
from pycon_us.services import Services
from pycon_us.services import storage as storage_module
from pycon_us.services.credentials import CredentialStorage
from pycon_us.services.outbox_db import Counts, OutboxDb
from pycon_us.services.private_api import PrivateApi
from pycon_us.services.storage import STAFF_PREFIX, Pref, Storage
from pycon_us.services.sync import supervise
from pycon_us.staff import Staff
from pycon_us.staff_data import clear_staff_data, staff_counts, unsynced
from tests import accounts
from tests.api_clients import BASE_URL
from tests.fakes import (
    MemoryClipboard,
    MemoryHaptics,
    MemoryLauncher,
    MemoryPrefs,
    MemorySemantics,
)
from tests.sync_rig import Rig, outbox_db

shared, storage, keystore, credentials = (
    accounts.shared,
    accounts.storage,
    accounts.keystore,
    accounts.credentials,
)
db = outbox_db

A = "a@example.com"
B = "b@example.com"
LATER_KEYS = ("pycon.staff_sponsor", "pycon.staff_consent")
"""Staff keys #39 adds: the chosen sponsor and the scanner consent."""


@pytest.fixture
def rig(db: OutboxDb, storage: Storage, credentials: CredentialStorage) -> Rig:
    """The rig over the idempotent mock, signed out."""
    return Rig(db, storage, credentials)


def seed(db: OutboxDb, code: str, owner: str, status: Status = Status.PENDING) -> Row:
    """Store a lead row of ``owner``'s for ``code`` in ``status``."""
    decide = outbox.scan_lead
    enqueued = db.enqueue(
        code,
        lambda rows: decide(
            rows,
            owner=owner,
            code=code,
            payload={"badge_validator": "v"},
            sponsor_id=None,
            sponsor_name=None,
            now=1.0,
        ),
    )
    assert enqueued is not None and enqueued.row is not None
    row = enqueued.row
    if status is not Status.PENDING:
        row = replace(row, status=status)
        assert db.save(row)
    return row


def statuses(db: OutboxDb, owner: str) -> list[Status]:
    """The owner's rows' statuses, oldest first."""
    return [row.status for row in db.rows(owner, tuple(Status)) or []]


def table() -> list[Pref[object]]:
    """Every key of the storage table: its constants and its per-year keys (2026)."""
    found: list[Pref[object]] = []
    for value in vars(storage_module).values():
        if isinstance(value, Pref):
            found.append(value)
        elif inspect.isfunction(value) and value.__module__ == storage_module.__name__:
            returns = inspect.signature(value).return_annotation
            if typing.get_origin(returns) is Pref:
                found.append(value(2026))
    return found


# ------------------------------------------------------------------ the storage table


def test_every_staff_key_of_the_table_starts_with_the_staff_prefix() -> None:
    """A key about staff tools is named under ``STAFF_PREFIX``, so it is cleared too."""
    keys = [pref.key for pref in table()]
    assert len(keys) > 8  # the walk found the table, per-year keys included
    words = ("staff", "sponsor", "consent", "scan", "lead", "door")
    for key in keys:
        if any(word in key for word in words):
            assert key.startswith(STAFF_PREFIX), key


async def test_clear_staff_data_removes_every_staff_key_and_no_other(
    db: OutboxDb, storage: Storage, shared: MemoryPrefs
) -> None:
    """Every table key is set; the staff ones, later ones included, go; the rest stay."""
    for pref in table():
        shared.values[pref.key] = "x"
    for key in LATER_KEYS:
        shared.values[key] = "x"
    kept = {key for key in shared.values if not key.startswith(STAFF_PREFIX)}
    assert await clear_staff_data(db, storage, Staff())
    assert set(shared.values) == kept


# ------------------------------------------------------------------ Clear staff data


async def test_clear_staff_data_deletes_every_account_s_rows_and_zeros_staff(
    db: OutboxDb, storage: Storage
) -> None:
    """Pending, failed and synced rows of every owner go; ``Staff`` counts none."""
    seed(db, "A1", A)
    seed(db, "A2", A, Status.FAILED)
    seed(db, "B1", B, Status.SYNCED)
    assert staff_counts(db) == Counts(pending=1, failed=1, synced=1)
    staff = Staff(pending=1, failed=1)
    revision = staff.revision
    assert await clear_staff_data(db, storage, staff)
    assert staff_counts(db) == Counts()
    assert (staff.pending, staff.failed, staff.synced) == (0, 0, 0)
    assert staff.revision > revision  # a list of rows re-reads


async def test_clear_staff_data_never_creates_the_outbox(
    tmp_path: Path, storage: Storage
) -> None:
    """Without ``outbox.db`` there is nothing to count or delete, and none is made."""
    never = OutboxDb(tmp_path / "never")
    (tmp_path / "never").mkdir()
    assert staff_counts(never) == Counts()
    assert await clear_staff_data(never, storage, Staff())
    assert not never.path.exists()
    assert staff_counts(None) == Counts()


async def test_rows_that_can_t_be_counted_are_not_deleted(
    db: OutboxDb, storage: Storage
) -> None:
    """A failed read deletes nothing: no confirmation could name how many (D-120)."""
    seed(db, "A1", A)
    db.close()  # every later call is refused, logged
    assert staff_counts(db) is None
    assert not await clear_staff_data(db, storage, Staff())


def test_unsynced_counts_pending_and_failed() -> None:
    """Pending and failed rows haven't reached the server; synced ones have."""
    assert unsynced(Counts(pending=2, failed=1, synced=5)) == 3
    assert unsynced(Staff(pending=1, failed=0, synced=9)) == 1


# ------------------------------------------------------------------ an account switch


def test_a_switch_forgets_other_accounts_synced_rows_only(db: OutboxDb) -> None:
    """Other owners' synced rows go; pending, failed and the account's own stay.

    A synced lead whose note hasn't synced stays too, as the note waits for it.
    """
    seed(db, "A1", A, Status.SYNCED)
    seed(db, "A2", A)
    seed(db, "A3", A, Status.FAILED)
    lead = seed(db, "A4", A, Status.SYNCED)
    note = db.enqueue(
        lead.key,
        lambda rows: outbox.save_note(
            rows,
            owner=A,
            code=lead.key,
            note="Met at the booth",
            sponsor_id=None,
            sponsor_name=None,
            now=2.0,
        ),
    )
    assert note is not None
    seed(db, "B1", B, Status.SYNCED)
    assert db.forget_other_accounts(B)
    assert sorted(row.key for row in db.rows(A, tuple(Status)) or []) == [
        "A2",
        "A3",
        "A4",
        "A4",
    ]
    assert statuses(db, B) == [Status.SYNCED]


async def test_sign_out_removes_the_staff_keys_and_keeps_the_rows(
    rig: Rig, shared: MemoryPrefs
) -> None:
    """Signing out removes the sponsor and the consent; the rows keep their owner."""
    await rig.sign_in("sponsor")
    rig.lead()
    owner = rig.account.owner
    for key in LATER_KEYS:
        shared.values[key] = "x"
    await rig.sign_out()
    assert not set(LATER_KEYS) & set(shared.values)
    assert statuses(rig.db, owner) == [Status.PENDING]


@pytest.mark.parametrize(("again", "kept"), [("sponsor", True), ("all", False)])
async def test_a_sign_in_as_someone_else_removes_the_staff_keys(
    rig: Rig, shared: MemoryPrefs, again: str, kept: bool
) -> None:
    """An expired account signing in again keeps them; another account doesn't."""
    await rig.sign_in("sponsor")
    for key in LATER_KEYS:
        shared.values[key] = "x"
    rig.account.expired = True  # "Sign in again", without a sign-out
    await rig.sign_in(again)
    assert (set(LATER_KEYS) <= set(shared.values)) is kept


async def test_a_switch_that_can_t_remove_the_staff_keys_is_not_saved(
    rig: Rig,
    storage: Storage,
    credentials: CredentialStorage,
    shared: MemoryPrefs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The previous account stays signed in, and its keys stay with it (D-414).

    Only the staff keys' removal fails: the new account never inherits them.
    """
    await rig.sign_in("sponsor")
    for key in LATER_KEYS:
        shared.values[key] = "x"
    clear_prefs = Storage.clear_prefs

    async def refuse_staff(self: Storage, prefix: str = storage_module.PREFIX) -> bool:
        """Fail the staff keys' removal, as a failed commit does; others go."""
        return prefix != STAFF_PREFIX and await clear_prefs(self, prefix)

    monkeypatch.setattr(Storage, "clear_prefs", refuse_staff)
    outcome = await rig.account.sign_in(
        rig.api, storage, credentials, "all@example.com", "mock-all"
    )
    assert outcome is SignIn.NOT_SAVED
    assert rig.account.owner == "sponsor@example.com"
    assert set(LATER_KEYS) <= set(shared.values)


async def until(condition: Callable[[], bool]) -> None:
    """Let the loop run until ``condition`` holds, failing after a second."""
    async with asyncio.timeout(1):
        while not condition():
            await asyncio.sleep(0.001)


async def test_a_switch_never_shows_or_sends_the_previous_owner_s_rows(
    rig: Rig, storage: Storage, credentials: CredentialStorage
) -> None:
    """The new account's sync counts and sends its own rows only; the old wait.

    The old owner's synced row goes as the new account's sync starts; its pending row
    stays, unsent, until that owner signs in again.
    """
    svc = Services(
        year=load_year(2026),
        storage=storage,
        memory=ViewMemory(),
        semantics=MemorySemantics(),
        haptics=MemoryHaptics(),
        launcher=MemoryLauncher(),
        clipboard=MemoryClipboard(),
        private_api=PrivateApi(rig.wire, rig.account.credentials),
        credentials=credentials,
        outbox=rig.db,
    )
    await svc.private_api.connect(BASE_URL, 2026)
    await rig.sign_in("staff")
    old = rig.account.owner
    seed(rig.db, "OLD1", old, Status.SYNCED)
    seed(rig.db, "OLD2", old)
    await rig.sign_out()
    await rig.sign_in("sponsor")
    task = asyncio.create_task(supervise(svc, rig.account, rig.staff))
    try:
        await until(lambda: rig.staff.revision > 0)
        assert (rig.staff.pending, rig.staff.failed, rig.staff.synced) == (0, 0, 0)
        assert statuses(rig.db, old) == [Status.PENDING]
        assert rig.sends() == []
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


def test_sync_now_makes_the_owner_s_pending_rows_due_now(db: OutboxDb) -> None:
    """Rows in a backoff are due at once; failed, synced and others' rows keep theirs."""
    mine = seed(db, "A1", A)
    assert db.save(outbox.after_network_error(mine, 100.0))  # due at 160
    other = seed(db, "B1", B)
    assert db.save(outbox.after_network_error(other, 100.0))
    assert db.due_now(A, 120.0)
    assert [row.key for row in db.due_rows(A, 120.0)] == ["A1"]
    assert db.due_rows(B, 120.0) == []
    [row] = db.rows(A, (Status.PENDING,)) or []
    assert (row.tries, row.revision) == (0, mine.revision)  # an outcome still saves


async def test_clear_staff_data_during_a_send_stops_the_pass_s_later_rows(
    rig: Rig, storage: Storage
) -> None:
    """Rows deleted while the pass sends its first one are never sent (D-414)."""
    await rig.sign_in("sponsor")
    for code in ("MOCK0001", "MOCK0002", "MOCK0003"):
        rig.lead(code)

    async def clear() -> None:
        """Clear staff data right after the first send's reply."""
        assert await clear_staff_data(rig.db, storage, rig.staff)

    rig.wire.then = clear
    await rig.worker().drain()
    assert len(rig.sends()) == 1
    assert rig.db.counts(None) == Counts()
