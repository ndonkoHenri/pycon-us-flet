"""Tests for the favourites sync against the mock (API-04, AUTH-12, SCHED-12; D-55, D-406).

``FavoritesSync.run`` runs as ``App`` runs it, over the real ``Favorites`` and
``Account`` stores, in-memory storage and the real client to the mock
(``tools/mock_api/transport.py``). The reconcile itself is pinned, pure, by
``test_favorites_sync_core.py``.
"""

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest

from pycon_us.account import Account, SignIn
from pycon_us.favorites import Favorites
from pycon_us.services.api import ApiClient
from pycon_us.services.credentials import CredentialStorage
from pycon_us.services.favorites_sync import FavoritesSync
from pycon_us.services.pref_keys import favorites_sync
from pycon_us.services.private_api import PrivateApi
from pycon_us.services.storage import Storage
from tests.api_clients import BASE_URL, Recorder
from tests.fakes import MemoryPrefs
from tests.keystore import MemoryKeystore
from tests.mock_calls import NOW, account, state_at
from tools.mock_api.state import MockState
from tools.mock_api.transport import mock_transport

SEEDED = frozenset({"9001", "poster-detail-7"})
"""The seeded ``attendee`` account's favourites on the mock."""

SYNC_KEY = favorites_sync(2026).key
"""Where the sync state is saved for 2026."""


class Held(Recorder):
    """A transport to the mock that records each request and holds the chosen ones."""

    def __init__(self, inner: httpx.AsyncBaseTransport) -> None:
        """Let every request through until ``hold`` names a method."""
        super().__init__(inner)
        self.hold: str | None = None
        self.release = asyncio.Event()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Record the request, wait for ``release`` when its method is held, answer it."""
        self.sent.append(request)
        if request.method == self.hold:
            await self.release.wait()
        return await self.inner.handle_async_request(request)

    def methods(self) -> list[str]:
        """The methods of the ``mobile_state`` calls sent so far, in order."""
        return [r.method for r in self.sent if r.url.path.endswith("mobile_state/")]


@dataclass
class Rig:
    """One session's sync: its stores, storage, mock and transport, while it runs."""

    state: MockState
    shared: MemoryPrefs
    storage: Storage
    credentials: CredentialStorage
    favorites: Favorites
    account: Account
    transport: Held
    api: ApiClient
    sync: FavoritesSync
    closed: asyncio.Event
    private_api: PrivateApi
    task: asyncio.Task[None] | None = None

    def stop(self) -> None:
        """Stop the sync's loop, as a session that ends."""
        assert self.task is not None
        self.task.cancel()

    async def sign_in(self, role: str = "attendee") -> None:
        """Sign the account in as the seeded ``role``."""
        outcome = await self.account.sign_in(
            self.api,
            self.storage,
            self.credentials,
            f"{role}@example.com",
            f"mock-{role}",
        )
        assert outcome is SignIn.SIGNED_IN

    def server(self, role: str = "attendee") -> frozenset[str]:
        """The seeded ``role`` account's favourites on the mock now."""
        return frozenset(account(self.state, role).favorites)

    def saved_state(self) -> str | None:
        """The sync state as saved, None when absent (a first sync is due)."""
        return self.shared.values.get(SYNC_KEY)


async def until(check: Callable[[], bool], timeout: float = 3.0) -> None:
    """Wait until ``check()`` holds, failing the test after ``timeout`` seconds."""
    async with asyncio.timeout(timeout):
        while not check():
            await asyncio.sleep(0.01)


async def settled(rig: Rig) -> None:
    """Wait until the account has this device's list and the state says so, saved."""
    await until(
        lambda: not rig.account.favorites_dirty and rig.saved_state() == "clean"
    )


async def quiet() -> None:
    """Let the loop run for a while, longer than the tests' debounce."""
    await asyncio.sleep(0.2)


@pytest.fixture
def state() -> MockState:
    """A fresh seeded mock, at the tests' fixed time."""
    return state_at()


@pytest.fixture
def shared() -> MemoryPrefs:
    """An empty in-memory SharedPreferences, kept across a restart in a test."""
    return MemoryPrefs()


class HeldPrefs(MemoryPrefs):
    """In-memory SharedPreferences that can hold the writes of one key."""

    def init(self) -> None:
        """Start empty, holding nothing."""
        super().init()
        self.hold: str | None = None
        self.release = asyncio.Event()

    async def _invoke_method(
        self,
        method_name: str,
        arguments: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        """Wait for ``release`` before a ``set`` of the held key, then answer it."""
        if method_name == "set" and arguments and arguments["key"] == self.hold:
            await self.release.wait()
        return await super()._invoke_method(method_name, arguments, timeout)


@pytest.fixture
def keystore() -> MemoryKeystore:
    """An empty in-memory keystore, kept across a restart in a test."""
    return MemoryKeystore()


async def start(
    state: MockState,
    shared: MemoryPrefs,
    keystore: MemoryKeystore,
    tmp_path: Path,
    delay: float = 0.05,
) -> Rig:
    """Start a session as ``bootstrap()`` does: load and restore, then run the sync.

    ``delay`` is the debounce: the tests' short one unless a test needs it long.
    """
    storage = Storage(prefs=shared, directory=tmp_path, year=2026)
    credentials = CredentialStorage(secure=keystore)
    store = Account()
    favorites = Favorites()
    await favorites.load(storage)
    await store.restore(storage, credentials)
    transport = Held(mock_transport(state))
    api = ApiClient(
        BASE_URL, 2026, store.credentials, transport=transport, now=lambda: NOW
    )
    private_api = PrivateApi()
    private_api.client = api
    sync = FavoritesSync(delay=delay)
    closed = asyncio.Event()
    rig = Rig(
        state,
        shared,
        storage,
        credentials,
        favorites,
        store,
        transport,
        api,
        sync,
        closed,
        private_api,
    )
    rig.task = asyncio.create_task(
        sync.run(private_api, storage, favorites, store, closed)
    )
    await asyncio.sleep(0)
    return rig


@pytest.fixture
async def rig(
    state: MockState, shared: MemoryPrefs, keystore: MemoryKeystore, tmp_path: Path
) -> AsyncIterator[Rig]:
    """A running session, signed out, with no favourites yet; stopped after the test."""
    rig = await start(state, shared, keystore, tmp_path)
    yield rig
    rig.stop()


async def synced(rig: Rig) -> None:
    """Sign in as the attendee and wait for the first sync to finish."""
    await rig.sign_in()
    await settled(rig)
    rig.transport.sent.clear()


async def test_signed_out_nothing_is_sent(rig: Rig) -> None:
    """Signed out, a star stays on the device: no request and no saved state (D-48)."""
    await rig.favorites.toggle(rig.storage, "1")
    await quiet()
    assert rig.transport.sent == []
    assert rig.saved_state() is None and not rig.account.favorites_dirty


async def test_sign_in_takes_the_union_and_sends_it(rig: Rig) -> None:
    """Favourites starred signed out survive the sign-in and reach the account."""
    await rig.favorites.add_many(rig.storage, ["1", "2"])
    await rig.sign_in()
    union = SEEDED | {"1", "2"}
    await settled(rig)
    assert rig.favorites.ids == union and rig.server() == union
    assert rig.transport.methods() == ["GET", "PATCH"]
    assert not rig.account.favorites_dirty


async def test_a_first_sync_the_server_covers_sends_nothing(rig: Rig) -> None:
    """With nothing new on the device, the first sync only takes the server's list in."""
    await rig.sign_in()
    await settled(rig)
    assert rig.favorites.ids == SEEDED
    assert rig.transport.methods() == ["GET"]


async def test_quick_stars_send_one_patch(rig: Rig) -> None:
    """Five stars within the debounce send one full-list PATCH, with all five."""
    await synced(rig)
    for session_id in "abcde":
        await rig.favorites.toggle(rig.storage, session_id)
    assert rig.account.favorites_dirty
    await settled(rig)
    assert rig.transport.methods() == ["PATCH"]
    assert rig.server() == SEEDED | set("abcde")
    assert not rig.account.favorites_dirty


async def test_a_failed_patch_stays_dirty_and_the_resume_sends_it(rig: Rig) -> None:
    """No answer keeps the edit dirty, saved; the next resume's pull pushes it."""
    await synced(rig)
    rig.state.faults.inject("connect", until_cleared=True)
    await rig.favorites.toggle(rig.storage, "x")
    await until(lambda: rig.transport.methods() == ["PATCH"])
    await quiet()
    assert rig.saved_state() == "dirty" and rig.account.favorites_dirty
    assert "x" not in rig.server()
    rig.state.faults.clear()
    rig.sync.request()  # what app.on_resume() asks
    await settled(rig)
    assert rig.server() == SEEDED | {"x"} and rig.favorites.ids == SEEDED | {"x"}


async def test_an_unsent_edit_is_sent_at_the_next_start(
    state: MockState, shared: MemoryPrefs, keystore: MemoryKeystore, tmp_path: Path
) -> None:
    """An edit that never left (the app was killed) is pushed by the next start.

    The server's list changed meanwhile; the saved dirty state keeps the local one.
    """
    first = await start(state, shared, keystore, tmp_path)
    await synced(first)
    state.faults.inject("connect", until_cleared=True)
    await first.favorites.toggle(first.storage, "y")
    await until(lambda: first.saved_state() == "dirty")
    first.stop()
    state.faults.clear()
    account(state, "attendee").favorites = ["9001"]
    second = await start(state, shared, keystore, tmp_path)
    await settled(second)
    assert second.server() == SEEDED | {"y"} == second.favorites.ids
    assert second.transport.methods() == ["GET", "PATCH"]
    second.stop()


async def test_a_clean_list_adopts_the_server_s_empty_list(rig: Rig) -> None:
    """After the first sync, a server ``[]`` is a removal made elsewhere: adopted."""
    await synced(rig)
    account(rig.state, "attendee").favorites = []
    rig.sync.request()
    await until(lambda: rig.favorites.ids == frozenset())
    assert rig.transport.methods() == ["GET"]
    assert rig.shared.values["pycon.2026.favorites"] == []


async def test_ints_from_the_server_become_strings(rig: Rig) -> None:
    """A server list with integer ids is kept as their decimal strings."""
    await synced(rig)
    account(rig.state, "attendee").favorites = [42, "poster-detail-7"]  # type: ignore[list-item]
    rig.sync.request()
    await until(lambda: rig.favorites.ids == {"42", "poster-detail-7"})


async def test_an_edit_during_a_pull_is_kept_and_sent(rig: Rig) -> None:
    """A star tapped while a pull is out is not overwritten by its reply."""
    await synced(rig)
    account(rig.state, "attendee").favorites = []
    rig.transport.hold = "GET"
    rig.transport.release.clear()
    rig.sync.request()
    await until(lambda: rig.transport.methods() == ["GET"])
    await rig.favorites.toggle(rig.storage, "z")
    rig.transport.release.set()
    await settled(rig)
    assert rig.favorites.ids == SEEDED | {"z"} and rig.server() == SEEDED | {"z"}


async def test_a_resume_during_a_patch_waits_and_adopts_nothing_stale(rig: Rig) -> None:
    """A pull asked for while a PATCH is out goes after it, and reads the new list."""
    await synced(rig)
    rig.transport.hold = "PATCH"
    rig.transport.release.clear()
    await rig.favorites.toggle(rig.storage, "9001")  # a removal
    await until(lambda: rig.transport.methods() == ["PATCH"])
    rig.sync.request()
    await quiet()
    assert rig.transport.methods() == ["PATCH"]  # one request at a time
    rig.transport.release.set()
    await until(lambda: rig.transport.methods() == ["PATCH", "GET"])
    await settled(rig)
    assert rig.favorites.ids == {"poster-detail-7"} == rig.server()


async def test_an_edit_during_a_patch_is_sent_after_it(rig: Rig) -> None:
    """A star tapped while a PATCH is out leaves the list dirty and sends again."""
    await synced(rig)
    rig.transport.hold = "PATCH"
    rig.transport.release.clear()
    await rig.favorites.toggle(rig.storage, "p")
    await until(lambda: rig.transport.methods() == ["PATCH"])
    await rig.favorites.toggle(rig.storage, "q")
    rig.transport.release.set()
    await until(lambda: rig.transport.methods() == ["PATCH", "PATCH"])
    await settled(rig)
    assert rig.server() == SEEDED | {"p", "q"}


async def test_sign_out_stops_the_sync_and_keeps_the_list(rig: Rig) -> None:
    """A sign-out forgets the sync state; the favourites stay and nothing is sent."""
    await synced(rig)
    await rig.account.sign_out(rig.storage, rig.credentials)
    await until(lambda: rig.saved_state() is None)
    await rig.favorites.toggle(rig.storage, "w")
    await quiet()
    assert rig.transport.sent == []
    assert rig.favorites.ids == SEEDED | {"w"} and not rig.account.favorites_dirty


async def test_an_expired_account_sends_nothing(rig: Rig) -> None:
    """While the key is refused (``expired``) an edit waits, dirty, and nothing is sent."""
    await synced(rig)
    rig.account.expired = True
    await rig.favorites.toggle(rig.storage, "e")
    await quiet()
    assert rig.transport.sent == []
    assert rig.saved_state() == "dirty" and rig.account.favorites_dirty


async def test_a_close_during_a_pull_adopts_and_saves_nothing(rig: Rig) -> None:
    """A reply that arrives after the session closed changes nothing (D-147)."""
    await synced(rig)
    account(rig.state, "attendee").favorites = []
    rig.transport.hold = "GET"
    rig.transport.release.clear()
    rig.sync.request()
    await until(lambda: rig.transport.methods() == ["GET"])
    rig.closed.set()
    before = dict(rig.shared.values)
    rig.transport.release.set()
    assert rig.task is not None
    await asyncio.wait_for(rig.task, 3.0)
    assert rig.favorites.ids == SEEDED and rig.shared.values == before
    assert rig.transport.methods() == ["GET"]


async def test_an_account_switch_during_the_union_s_save_sends_nothing_stale(
    state: MockState, keystore: MemoryKeystore, tmp_path: Path
) -> None:
    """A first sync whose save outlives its account never PATCHes the next account.

    The next account's own sign-in pull takes the union, so its favourite stays.
    """
    shared = HeldPrefs()
    rig = await start(state, shared, keystore, tmp_path)
    account(state, "speaker").favorites = ["speaker-only"]
    await rig.favorites.add_many(rig.storage, ["1"])
    shared.hold = "pycon.2026.favorites"
    await rig.sign_in()
    await until(lambda: rig.favorites.ids == SEEDED | {"1"})  # assigned, not saved
    await rig.account.sign_out(rig.storage, rig.credentials)
    await rig.sign_in("speaker")
    shared.release.set()
    await until(lambda: "PATCH" in rig.transport.methods())
    await settled(rig)
    assert rig.server("speaker") == SEEDED | {"1", "speaker-only"}
    assert rig.server() == SEEDED  # the attendee's PATCH was never sent
    rig.stop()


async def test_an_edit_during_a_pull_survives_a_kill(
    state: MockState, shared: MemoryPrefs, keystore: MemoryKeystore, tmp_path: Path
) -> None:
    """A star tapped while a pull is out is saved dirty at once, so a kill keeps it."""
    first = await start(state, shared, keystore, tmp_path)
    await synced(first)
    first.transport.hold = "GET"
    first.transport.release.clear()
    first.sync.request()
    await until(lambda: first.transport.methods() == ["GET"])
    await first.favorites.toggle(first.storage, "unsent")
    await quiet()
    first.stop()  # killed with the pull still out
    second = await start(state, shared, keystore, tmp_path)
    await settled(second)
    assert "unsent" in second.favorites.ids and "unsent" in second.server()
    second.stop()


async def test_a_removal_during_the_first_patch_is_not_merged_back(rig: Rig) -> None:
    """An id removed while the first sync's PATCH is out is sent removed, not unioned."""
    await rig.favorites.add_many(rig.storage, ["1"])
    rig.transport.hold = "PATCH"
    rig.transport.release.clear()
    await rig.sign_in()
    await until(lambda: rig.transport.methods() == ["GET", "PATCH"])
    await rig.favorites.toggle(rig.storage, "9001")  # a removal
    rig.transport.release.set()
    await settled(rig)
    assert rig.favorites.ids == {"1", "poster-detail-7"} == rig.server()
    assert rig.transport.methods() == ["GET", "PATCH", "PATCH"]


# ------------------------------------------------------------------ flush (D-411)


def private_api_of(rig: Rig) -> PrivateApi:
    """A ``PrivateApi`` holding the rig's client, as ``Services.private_api`` does."""
    private_api = PrivateApi()
    private_api.client = rig.api
    return private_api


async def flush(rig: Rig) -> bool:
    """Ask the rig's sync to send what waits now, as the Account page's Sign out does."""
    return await rig.sync.flush(
        private_api_of(rig), rig.storage, rig.favorites, rig.account, rig.closed
    )


async def test_flush_sends_a_waiting_edit_before_its_debounce(
    state: MockState, shared: MemoryPrefs, keystore: MemoryKeystore, tmp_path: Path
) -> None:
    """A sign-out does not wait for the debounce: the edit reaches the account now."""
    rig = await start(state, shared, keystore, tmp_path, delay=60)
    try:
        await synced(rig)
        await rig.favorites.toggle(rig.storage, "x")
        assert rig.account.favorites_dirty
        assert await flush(rig)
        assert "x" in rig.server() and not rig.account.favorites_dirty
        assert rig.saved_state() == "clean"
    finally:
        rig.stop()


async def test_flush_with_nothing_waiting_sends_nothing(rig: Rig) -> None:
    """Synced, a sign-out's try is a no-op that says the account is up to date."""
    await synced(rig)
    assert await flush(rig)
    assert rig.transport.sent == []


async def test_a_flush_that_gets_no_answer_says_so_and_keeps_the_edit(
    state: MockState, shared: MemoryPrefs, keystore: MemoryKeystore, tmp_path: Path
) -> None:
    """No answer: False, so the dialog says it; the edit stays dirty, saved."""
    rig = await start(state, shared, keystore, tmp_path, delay=60)
    try:
        await synced(rig)
        rig.state.faults.inject("connect", until_cleared=True)
        await rig.favorites.toggle(rig.storage, "x")
        assert not await flush(rig)
        assert rig.account.favorites_dirty and rig.saved_state() == "dirty"
        assert "x" in rig.favorites.ids
    finally:
        rig.stop()


async def flush_held(rig: Rig) -> asyncio.Task[bool]:
    """Start a sign-out's flush of a new edit and hold its PATCH, with a pull queued.

    The loop is left waiting for the request lock that the flush holds.
    """
    await synced(rig)
    rig.transport.hold = "PATCH"
    rig.transport.release.clear()
    await rig.favorites.toggle(rig.storage, "x")
    task = asyncio.create_task(
        rig.sync.flush(
            rig.private_api, rig.storage, rig.favorites, rig.account, rig.closed
        )
    )
    await until(lambda: rig.transport.methods() == ["PATCH"])
    rig.sync.request()
    await quiet()
    return task


async def test_a_pull_behind_a_flush_uses_the_client_that_replaced_the_closed_one(
    state: MockState, shared: MemoryPrefs, keystore: MemoryKeystore, tmp_path: Path
) -> None:
    """A URL changed during a flush: the queued pull uses the new client, and lives on.

    Read before the wait, the closed client would raise and end the sync for good.
    """
    rig = await start(state, shared, keystore, tmp_path, delay=60)
    try:
        flushing = await flush_held(rig)
        replacement = Held(mock_transport(state))
        rig.private_api.client = ApiClient(
            BASE_URL,
            2026,
            rig.account.credentials,
            transport=replacement,
            now=lambda: NOW,
        )
        await rig.api.aclose()
        rig.transport.release.set()
        assert await flushing
        await until(lambda: replacement.methods() == ["GET"])
        await rig.favorites.toggle(rig.storage, "y")
        assert await rig.sync.flush(
            rig.private_api, rig.storage, rig.favorites, rig.account, rig.closed
        )
        assert rig.task is not None and not rig.task.done()
        assert {"x", "y"} <= rig.server()
    finally:
        rig.stop()


async def test_a_pull_behind_a_flush_is_not_sent_once_the_session_closed(
    state: MockState, shared: MemoryPrefs, keystore: MemoryKeystore, tmp_path: Path
) -> None:
    """A session closed while the loop waits for a flush sends nothing more (D-147)."""
    rig = await start(state, shared, keystore, tmp_path, delay=60)
    try:
        flushing = await flush_held(rig)
        rig.closed.set()
        rig.transport.release.set()
        await flushing
        assert rig.task is not None
        await asyncio.wait_for(rig.task, 3.0)
        assert rig.transport.methods() == ["PATCH"]
    finally:
        rig.stop()
