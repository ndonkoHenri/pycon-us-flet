"""The sync loop's life: ``SyncWorker.run()``, ``supervise()`` and its triggers (#692).

``run()`` is tested with a counting ``drain``, so only the loop's timing is under test;
``supervise()`` runs over real ``Services`` whose client reaches the in-process mock,
and checks that exactly one worker sends while one should, and none otherwise.
"""

import asyncio
import contextlib
from collections.abc import Callable, Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import flet as ft
import pytest

from pycon_us.config import load_year
from pycon_us.core.outbox import Status
from pycon_us.memory import ViewMemory
from pycon_us.services import Services, kick_on_reconnect
from pycon_us.services.credentials import CredentialStorage
from pycon_us.services.outbox_db import OutboxDb
from pycon_us.services.private_api import PrivateApi
from pycon_us.services.storage import Storage
from pycon_us.services.sync import SyncWorker, supervise
from tests import accounts
from tests.api_clients import BASE_URL
from tests.fakes import MemoryClipboard, MemoryHaptics, MemoryLauncher, MemorySemantics
from tests.sync_rig import Rig

shared, storage, keystore, credentials = (
    accounts.shared,
    accounts.storage,
    accounts.keystore,
    accounts.credentials,
)


@pytest.fixture
def db(tmp_path: Path) -> Iterator[OutboxDb]:
    """Yield an outbox in its own directory, closed afterwards."""
    directory = tmp_path / "outbox"
    directory.mkdir()
    database = OutboxDb(directory)
    yield database
    database.close()


@pytest.fixture
def rig(db: OutboxDb, storage: Storage, credentials: CredentialStorage) -> Rig:
    """The rig over the idempotent mock, signed out."""
    return Rig(db, storage, credentials)


@pytest.fixture
def svc(rig: Rig, storage: Storage, credentials: CredentialStorage) -> Services:
    """Services whose private-API client reaches the rig's mock with the rig's account."""
    return Services(
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


async def until(condition: Callable[[], bool]) -> None:
    """Let the loop run until ``condition`` holds, failing after a second."""
    async with asyncio.timeout(1):
        while not condition():
            await asyncio.sleep(0.001)


def workers() -> list[asyncio.Task[object]]:
    """Every running ``SyncWorker.run()`` task."""
    return [
        task
        for task in asyncio.all_tasks()
        if getattr(task.get_coro(), "__qualname__", "") == "SyncWorker.run"
        and not task.done()
    ]


class Counted:
    """A worker whose ``drain`` only counts, so the loop's timing is what is tested."""

    def __init__(
        self,
        rig: Rig,
        *,
        foreground: asyncio.Event | None = None,
        closed: asyncio.Event | None = None,
        wake: asyncio.Event | None = None,
    ) -> None:
        """Build the worker over the rig with these events, and count its passes."""
        self.passes = 0
        self.worker = SyncWorker(
            rig.db,
            rig.api,
            rig.account,
            rig.staff,
            wake=wake,
            foreground=foreground,
            closed=closed,
        )

        async def drain() -> None:
            self.passes += 1

        self.worker.drain = drain  # pyright: ignore[reportAttributeAccessIssue]


async def test_run_passes_at_once_then_on_each_kick_and_each_tick(rig: Rig) -> None:
    """One pass at the start, one per kick, and one per tick without a kick."""
    counted = Counted(rig)
    task = asyncio.create_task(counted.worker.run(tick=3600))
    await until(lambda: counted.passes == 1)
    counted.worker.kick()
    await until(lambda: counted.passes == 2)
    task.cancel()
    ticking = Counted(rig)
    task = asyncio.create_task(ticking.worker.run(tick=0.005))
    await until(lambda: ticking.passes >= 3)
    task.cancel()


async def test_run_waits_in_the_background_and_returns_when_closed(rig: Rig) -> None:
    """Paused, a kick waits for the resume; a closed session ends the loop (D-147)."""
    foreground, closed, wake = asyncio.Event(), asyncio.Event(), asyncio.Event()
    counted = Counted(rig, foreground=foreground, closed=closed, wake=wake)
    task = asyncio.create_task(counted.worker.run(tick=3600))
    counted.worker.kick()
    await asyncio.sleep(0.01)
    assert counted.passes == 0
    foreground.set()
    await until(lambda: counted.passes == 1)
    closed.set()
    wake.set()  # as Services.close() does
    async with asyncio.timeout(1):
        await task
    assert counted.passes == 1


async def test_one_worker_sends_while_signed_in_and_none_after_sign_out(
    rig: Rig, svc: Services
) -> None:
    """The supervisor starts one worker, stops it on sign-out and clears ``Staff``."""
    await svc.private_api.connect(BASE_URL, 2026)
    await rig.sign_in("sponsor")
    rig.lead()
    task = asyncio.create_task(supervise(svc, rig.account, rig.staff))
    await until(lambda: rig.staff.synced == 1)
    assert len(workers()) == 1
    for _ in range(3):  # kicks never start a second loop
        svc.kick_sync()
    await rig.sign_out()
    await until(lambda: not workers())
    assert rig.staff.synced == 0
    assert len(rig.state.leads) == 1  # sent once (its first try refused for the skew)
    await rig.sign_in("all")
    await until(lambda: len(workers()) == 1)
    svc.close()
    async with asyncio.timeout(1):
        await task
    assert not workers()


async def test_a_new_account_gets_a_new_worker_for_its_own_rows(
    rig: Rig, svc: Services
) -> None:
    """After a switch the old owner's rows wait; the new owner's are sent at once."""
    await svc.private_api.connect(BASE_URL, 2026)
    await rig.sign_in("staff")
    rig.lead(sponsor="2")
    staff_owner = rig.account.owner
    await rig.sign_out()
    await rig.sign_in("sponsor")
    rig.lead(code="MOCK0002", validator="v4l1d02")
    task = asyncio.create_task(supervise(svc, rig.account, rig.staff))
    await until(lambda: rig.staff.synced == 1)
    assert [row.status for row in rig.rows(staff_owner)] == [Status.PENDING]
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    assert not workers()


async def test_no_worker_without_a_client_or_while_expired(
    rig: Rig, svc: Services
) -> None:
    """No mock URL, or a refused key: no loop and no private call (D-51, D-403)."""
    await rig.sign_in("sponsor")
    rig.lead()
    sent = len(rig.wire.sent)
    task = asyncio.create_task(supervise(svc, rig.account, rig.staff))
    await asyncio.sleep(0.01)
    assert not workers()
    await svc.private_api.connect(BASE_URL, 2026)  # Developer saves a URL
    svc.kick_sync()
    rig.account.expired = True  # notifies: checked again, still nothing to run
    await asyncio.sleep(0.01)
    assert not workers()
    assert len(rig.wire.sent) == sent
    rig.account.expired = False  # a sign-in again clears it
    await until(lambda: rig.staff.synced == 1)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


def test_a_reconnection_wakes_the_loop_and_no_connection_does_not() -> None:
    """Any connectivity but ``NONE`` sets the wake; ``NONE`` alone leaves it."""
    wake = asyncio.Event()
    on_change = kick_on_reconnect(wake)

    def change(*kinds: ft.ConnectivityType) -> ft.ConnectivityChangeEvent:
        """A connectivity event with these kinds."""
        return cast(ft.ConnectivityChangeEvent, SimpleNamespace(connectivity=kinds))

    on_change(change(ft.ConnectivityType.NONE))
    assert not wake.is_set()
    on_change(change(ft.ConnectivityType.WIFI))
    assert wake.is_set()


def test_closing_the_session_wakes_the_sync_loop(svc: Services) -> None:
    """``Services.close()`` sets the wake, so a waiting loop sees ``closed`` (D-147)."""
    svc.close()
    assert svc.sync_wake.is_set() and svc.closed.is_set()
