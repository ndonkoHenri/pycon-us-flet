"""Tests for the role flags' refresh and the revoked key (AUTH-04, API-03, D-54, D-57, #686).

``Account.refresh_flags`` sends ``check_features`` through the real client to the mock
(``tools/mock_api/transport.py``) and takes its flags in; the mock's faults stand for
a lost connection and a revoked key. The triggers (start and resume) are
``test_app.py``'s and ``test_app_handlers.py``'s.
"""

import asyncio

import httpx
import pytest

from pycon_us.account import Account, SignIn
from pycon_us.services.api import ApiClient
from pycon_us.services.credentials import API_KEY, API_SECRET, CredentialStorage
from pycon_us.services.storage import Storage
from tests import accounts
from tests.accounts import EVERY_FLAG, changes, stored_account
from tests.api_clients import BASE_URL, Recorder
from tests.fakes import MemoryPrefs
from tests.keystore import MemoryKeystore
from tests.mock_calls import NOW, account, state_at
from tools.mock_api.state import MockState
from tools.mock_api.transport import mock_transport

shared, storage, keystore, credentials = (
    accounts.shared,
    accounts.storage,
    accounts.keystore,
    accounts.credentials,
)

FLAG_FIELDS = ("lead_retrieval", "door_check", "mask_violation", "is_speaker")
"""The store's flag fields."""


@pytest.fixture
def state() -> MockState:
    """A fresh seeded mock, at the tests' fixed time."""
    return state_at()


class Held(Recorder):
    """A transport to the mock that holds each request until ``release`` is set."""

    def __init__(self, inner: httpx.AsyncBaseTransport) -> None:
        """Hold requests to ``inner``, which answers them once released."""
        super().__init__(inner)
        self.release = asyncio.Event()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Record the request, wait for ``release``, then let the mock answer."""
        self.sent.append(request)
        await self.release.wait()
        return await self.inner.handle_async_request(request)


@pytest.fixture
def held(state: MockState) -> Held:
    """A held transport to ``state``, released for sign-ins by the test."""
    return Held(mock_transport(state))


def client(transport: httpx.AsyncBaseTransport, store: Account) -> ApiClient:
    """A client over ``transport`` that signs with ``store``'s credentials, as the app's."""
    return ApiClient(
        BASE_URL, 2026, store.credentials, transport=transport, now=lambda: NOW
    )


async def signed_in(
    held: Held,
    storage: Storage,
    credentials: CredentialStorage,
    role: str = "all",
) -> tuple[Account, ApiClient]:
    """Sign a new store in as the seeded ``role`` and return it with its client.

    The transport is released for the sign-in and held again after it.
    """
    store = Account(restored=True)
    api = client(held, store)
    held.release.set()
    outcome = await store.sign_in(
        api, storage, credentials, f"{role}@example.com", f"mock-{role}"
    )
    assert outcome is SignIn.SIGNED_IN
    held.release.clear()
    held.sent.clear()
    return store, api


def flags_of(store: Account) -> tuple[bool, ...]:
    """The store's four flags, in ``FLAG_FIELDS``' order."""
    return tuple(getattr(store, name) for name in FLAG_FIELDS)


async def refreshed(
    store: Account, api: ApiClient, held: Held, storage: Storage
) -> None:
    """Run one refresh to its end, with the transport released."""
    held.release.set()
    task = store.refresh_flags(api, storage)
    assert task is not None
    await task


async def test_a_changed_role_is_taken_in_saved_and_notified(
    state: MockState,
    held: Held,
    shared: MemoryPrefs,
    storage: Storage,
    credentials: CredentialStorage,
) -> None:
    """A role taken away on the server goes from the store and ``pycon.account``."""
    store, api = await signed_in(held, storage, credentials)
    account(state, "all").features["mask_violation"] = False
    seen = changes(store)
    await refreshed(store, api, held, storage)
    assert flags_of(store) == (True, True, False, True)
    assert seen.fields == ["mask_violation"]  # only what changed notifies
    saved = stored_account(shared)
    assert saved is not None
    assert saved["features"] == {**EVERY_FLAG, "mask_violation": False}
    assert len(held.sent) == 1 and held.sent[0].url.path.endswith("check_features/")


async def test_an_absent_flag_reads_false_and_is_speaker_stays(
    state: MockState, held: Held, storage: Storage, credentials: CredentialStorage
) -> None:
    """An absent flag is False; ``is_speaker``, which only sign-in gives, stays.

    ``check_features`` leaves out a flag the account lacks, and never sends
    ``is_speaker`` (STORE-05).
    """
    store, api = await signed_in(held, storage, credentials)
    del account(state, "all").features["door_check_in"]
    await refreshed(store, api, held, storage)
    assert flags_of(store) == (True, False, True, True)


async def test_unchanged_flags_write_and_notify_nothing(
    held: Held,
    shared: MemoryPrefs,
    storage: Storage,
    credentials: CredentialStorage,
) -> None:
    """The same flags again leave the store and ``pycon.account`` as they were."""
    store, api = await signed_in(held, storage, credentials)
    shared.values.clear()  # a write would show here
    seen = changes(store)
    await refreshed(store, api, held, storage)
    assert seen.fields == [] and shared.values == {}


async def test_no_answer_keeps_the_flags_as_stored(
    state: MockState,
    held: Held,
    shared: MemoryPrefs,
    storage: Storage,
    credentials: CredentialStorage,
) -> None:
    """A dropped connection (the ``connect`` fault) changes nothing (D-57)."""
    store, api = await signed_in(held, storage, credentials)
    before = stored_account(shared)
    account(state, "all").features["lead_retrieval"] = False
    state.faults.inject("connect")
    await refreshed(store, api, held, storage)
    assert flags_of(store) == (True, True, True, True) and not store.expired
    assert stored_account(shared) == before


async def test_a_revoked_key_expires_the_account_and_keeps_everything(
    state: MockState,
    held: Held,
    shared: MemoryPrefs,
    keystore: MemoryKeystore,
    storage: Storage,
    credentials: CredentialStorage,
) -> None:
    """Refused, the account stays signed in as the owner, and asks for a sign-in.

    Nothing is deleted (D-57), and no private call follows until a sign-in.
    """
    store, api = await signed_in(held, storage, credentials)
    before = stored_account(shared)
    state.faults.inject("revoked")
    await refreshed(store, api, held, storage)
    assert store.expired and store.signed_in and store.owner == "all@example.com"
    assert flags_of(store) == (True, True, True, True)
    assert stored_account(shared) == before
    assert keystore.values == {API_KEY: "mock-key-all", API_SECRET: "mock-secret-all"}
    assert store.refresh_flags(api, storage) is None and len(held.sent) == 1


async def test_signing_in_again_clears_expired(
    state: MockState, held: Held, storage: Storage, credentials: CredentialStorage
) -> None:
    """The same email signs in again and the account is in use again."""
    store, api = await signed_in(held, storage, credentials)
    state.faults.inject("revoked")
    await refreshed(store, api, held, storage)
    assert store.expired
    outcome = await store.sign_in(
        api, storage, credentials, "all@example.com", "mock-all"
    )
    assert outcome is SignIn.SIGNED_IN and not store.expired


async def test_one_refresh_at_a_time(
    held: Held, storage: Storage, credentials: CredentialStorage
) -> None:
    """A second trigger while one is in flight joins it: one request (API-03)."""
    store, api = await signed_in(held, storage, credentials)
    first = store.refresh_flags(api, storage)
    await asyncio.sleep(0.01)
    assert store.refresh_flags(api, storage) is first
    held.release.set()
    assert first is not None
    await first
    assert len(held.sent) == 1


async def test_signed_out_or_without_a_client_nothing_is_sent(
    held: Held, storage: Storage, credentials: CredentialStorage
) -> None:
    """No account or no mock URL (D-51): no refresh starts."""
    store = Account(restored=True)
    assert store.refresh_flags(client(held, store), storage) is None
    signed, _ = await signed_in(held, storage, credentials)
    assert signed.refresh_flags(None, storage) is None
    assert held.sent == []


async def test_a_reply_after_a_sign_out_writes_nothing(
    state: MockState,
    held: Held,
    shared: MemoryPrefs,
    storage: Storage,
    credentials: CredentialStorage,
) -> None:
    """A late reply never brings back an account the user signed out of (D-198)."""
    store, api = await signed_in(held, storage, credentials)
    state.faults.inject("revoked")
    task = store.refresh_flags(api, storage)
    await asyncio.sleep(0.01)
    await store.sign_out(storage, credentials)
    held.release.set()
    assert task is not None
    await task
    assert not store.signed_in and not store.expired
    assert shared.values == {}


async def test_a_closed_session_writes_nothing(
    state: MockState,
    held: Held,
    shared: MemoryPrefs,
    storage: Storage,
    credentials: CredentialStorage,
) -> None:
    """A session replaced while the call was out leaves the store as it was (D-147)."""
    store, api = await signed_in(held, storage, credentials)
    before = stored_account(shared)
    account(state, "all").features["lead_retrieval"] = False
    closed = asyncio.Event()
    task = store.refresh_flags(api, storage, closed=closed)
    await asyncio.sleep(0.01)
    closed.set()
    held.release.set()
    assert task is not None
    await task
    assert store.lead_retrieval and stored_account(shared) == before


def saved_features(shared: MemoryPrefs) -> dict[str, bool]:
    """The flags ``pycon.account`` holds; the account must be saved."""
    saved = stored_account(shared)
    assert saved is not None
    return saved["features"]


async def test_a_failed_flag_save_is_saved_by_the_next_answer(
    state: MockState,
    held: Held,
    shared: MemoryPrefs,
    storage: Storage,
    credentials: CredentialStorage,
) -> None:
    """A revoked role whose save failed is saved by the next refresh, once (D-120).

    The store already matches the server then, so nothing notifies again, and a
    restore offline no longer brings the role back.
    """
    store, api = await signed_in(held, storage, credentials)
    account(state, "all").features["mask_violation"] = False
    shared.fail_writes = True
    await refreshed(store, api, held, storage)
    assert not store.mask_violation and saved_features(shared) == EVERY_FLAG
    shared.fail_writes = False
    seen = changes(store)
    await refreshed(store, api, held, storage)
    assert seen.fields == []
    assert saved_features(shared) == {**EVERY_FLAG, "mask_violation": False}
    restored = Account()
    await restored.restore(storage, credentials)
    assert restored.signed_in and not restored.mask_violation
    shared.values.clear()  # saved now: a further answer writes nothing
    await refreshed(store, api, held, storage)
    assert shared.values == {}
