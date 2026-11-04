"""Tests for signing in to the mock account (STORE-04, AUTH-02, D-54, #684).

`Account.sign_in` sends `authenticate` through the real client to the mock
(`tools/mock_api/transport.py`), saves the key, the secret and the account before
`signed_in` turns True, and returns how it ended; the client then signs with the
store's key. The account outlives a mock URL that is cleared or changed (D-398).
"""

import asyncio

import flet as ft
import httpx
import pytest

from pycon_us.account import Account, SignIn
from pycon_us.services.api import ApiClient, ApiError
from pycon_us.services.credentials import API_KEY, API_SECRET, CredentialStorage
from pycon_us.services.endpoints import CHECK_FEATURES
from pycon_us.services.pref_keys import ACCOUNT
from pycon_us.services.private_api import PrivateApi
from pycon_us.services.storage import Storage
from tests import accounts
from tests.accounts import stored_account
from tests.api_clients import BASE_URL, Recorder, replying
from tests.fakes import MemoryPrefs
from tests.keystore import MemoryKeystore
from tests.mock_calls import NOW, account, state_at
from tools.mock_api.faults import Fault
from tools.mock_api.state import MockState
from tools.mock_api.transport import mock_transport

shared, storage, keystore, credentials = (
    accounts.shared,
    accounts.storage,
    accounts.keystore,
    accounts.credentials,
)

ROLES = ("attendee", "speaker", "sponsor", "staff", "coc", "all")
"""Every seeded account (`tests/fixtures/mock/seed.json`)."""


@pytest.fixture
def state() -> MockState:
    """A fresh seeded mock, at the tests' fixed time."""
    return state_at()


@pytest.fixture
def recorder(state: MockState) -> Recorder:
    """A transport to `state` that keeps every request sent through it."""
    return Recorder(mock_transport(state))


def client(transport: httpx.AsyncBaseTransport, store: Account) -> ApiClient:
    """A client over `transport` that signs with `store`'s credentials, as the app's."""
    return ApiClient(
        BASE_URL, 2026, store.credentials, transport=transport, now=lambda: NOW
    )


class Held(Recorder):
    """A transport to the mock that holds each request until `release` is set."""

    def __init__(self, inner: httpx.AsyncBaseTransport) -> None:
        """Hold requests to `inner`, which answers them once released."""
        super().__init__(inner)
        self.release = asyncio.Event()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Record the request, wait for `release`, then let the mock answer."""
        self.sent.append(request)
        await self.release.wait()
        return await self.inner.handle_async_request(request)


async def sign_in(
    store: Account,
    transport: httpx.AsyncBaseTransport,
    storage: Storage,
    credentials: CredentialStorage,
    role: str = "all",
    password: str | None = None,
) -> SignIn:
    """Sign `store` in as the seeded `role`, with its password unless one is given."""
    return await store.sign_in(
        client(transport, store),
        storage,
        credentials,
        f"{role}@example.com",
        f"mock-{role}" if password is None else password,
    )


@pytest.mark.parametrize("role", ROLES)
async def test_each_seeded_role_signs_in_with_its_flags_stored(
    role: str,
    state: MockState,
    recorder: Recorder,
    shared: MemoryPrefs,
    keystore: MemoryKeystore,
    storage: Storage,
    credentials: CredentialStorage,
) -> None:
    """Signed in: the store holds the account's flags, and the device holds all three.

    The flags are stored by their API names, an absent one as False (STORE-05).
    """
    seeded = account(state, role)
    store = Account()
    assert (
        await sign_in(store, recorder, storage, credentials, role) is SignIn.SIGNED_IN
    )
    flags = {name: seeded.features.get(name) is True for name in accounts.EVERY_FLAG}
    assert store.signed_in and store.error is None
    assert (store.email, store.nickname) == (seeded.email, seeded.nickname)
    assert (
        store.lead_retrieval,
        store.door_check,
        store.mask_violation,
        store.is_speaker,
    ) == tuple(flags.values())
    assert stored_account(shared) == {
        "email": seeded.email,
        "nickname": seeded.nickname,
        "features": flags,
    }
    assert keystore.values == {API_KEY: seeded.key, API_SECRET: seeded.secret}


async def test_the_client_then_signs_with_the_store_s_key(
    recorder: Recorder, storage: Storage, credentials: CredentialStorage
) -> None:
    """A signed call after the sign-in carries the account's key and is answered."""
    store = Account()
    api = client(recorder, store)
    await store.sign_in(api, storage, credentials, "all@example.com", "mock-all")
    reply = await api.request(CHECK_FEATURES)
    assert isinstance(reply, dict) and reply["features"]["door_check_in"] is True
    assert recorder.sent[-1].headers["X-API-Key"] == "mock-key-all"


async def test_every_write_lands_before_signed_in_turns_true(
    recorder: Recorder,
    shared: MemoryPrefs,
    keystore: MemoryKeystore,
    storage: Storage,
    credentials: CredentialStorage,
) -> None:
    """Whoever reads `signed_in` finds what a relaunch would (STORE-04, AUTH-02)."""
    store = Account()
    seen: list[tuple[list[str], bool]] = []

    def at_sign_in(_sender: object, name: str | None) -> None:
        """Record what is stored when `signed_in` changes."""
        if name == "signed_in":
            seen.append((list(keystore.journal), ACCOUNT.key in shared.values))

    assert isinstance(store, ft.Observable)
    store.subscribe(at_sign_in)
    await sign_in(store, recorder, storage, credentials)
    assert seen == [([f"set {API_KEY}", f"set {API_SECRET}"], True)]


async def test_a_wrong_password_is_wrong_credentials_and_stores_nothing(
    recorder: Recorder,
    shared: MemoryPrefs,
    keystore: MemoryKeystore,
    storage: Storage,
    credentials: CredentialStorage,
) -> None:
    """The mock's 401 is the user's mistake, kept in `error` for the screen."""
    store = Account()
    outcome = await sign_in(store, recorder, storage, credentials, password="nope")
    assert outcome is SignIn.WRONG_CREDENTIALS
    assert store.error is SignIn.WRONG_CREDENTIALS and not store.signed_in
    assert shared.values == {} and keystore.values == {}
    assert not store.signing_in


@pytest.mark.parametrize(
    ("fault", "outcome"), [("connect", SignIn.OFFLINE), ("timeout", SignIn.TIMEOUT)]
)
async def test_no_answer_says_offline_or_timeout(
    fault: Fault,
    outcome: SignIn,
    state: MockState,
    recorder: Recorder,
    storage: Storage,
    credentials: CredentialStorage,
) -> None:
    """A connection that fails and a wait that runs out are said apart (D-54)."""
    state.faults.inject(fault)
    store = Account()
    assert await sign_in(store, recorder, storage, credentials) is outcome
    assert store.error is outcome and not store.signed_in


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (500, b'{"message": "Internal error"}'),
        (200, b'{"nickname": "No key", "email": "x@example.com", "features": {}}'),
        (200, b'{"key": "k", "secret": "s"}'),
    ],
    ids=["status-500", "no-key", "no-account"],
)
async def test_a_server_error_or_a_reply_that_is_no_account_is_a_server_error(
    status: int,
    body: bytes,
    shared: MemoryPrefs,
    storage: Storage,
    credentials: CredentialStorage,
) -> None:
    """A 500, or a 200 without the key, the secret or the account, signs nobody in."""
    store = Account()
    outcome = await sign_in(store, replying(status, body), storage, credentials)
    assert outcome is SignIn.SERVER_ERROR and not store.signed_in
    assert shared.values == {}


@pytest.mark.parametrize("failing", ["keystore", "preferences"])
async def test_a_failed_write_signs_nobody_in_and_leaves_nothing(
    failing: str,
    recorder: Recorder,
    shared: MemoryPrefs,
    keystore: MemoryKeystore,
    storage: Storage,
    credentials: CredentialStorage,
) -> None:
    """Signed in on the server but not saved: signed out, said, nothing partial kept."""
    if failing == "keystore":
        keystore.failing.add("set")
    else:
        shared.fail_writes = True
    store = Account()
    assert await sign_in(store, recorder, storage, credentials) is SignIn.NOT_SAVED
    assert store.error is SignIn.NOT_SAVED and not store.signed_in
    assert store.credentials() == (None, None)
    assert keystore.values == {} and ACCOUNT.key not in shared.values


async def test_one_sign_in_at_a_time(
    state: MockState, storage: Storage, credentials: CredentialStorage
) -> None:
    """A second sign-in while one waits for the server sends nothing (AUTH-02)."""
    held = Held(mock_transport(state))
    store = Account()
    first = asyncio.create_task(sign_in(store, held, storage, credentials))
    await asyncio.sleep(0.01)
    assert store.signing_in
    assert await sign_in(store, held, storage, credentials) is SignIn.BUSY
    held.release.set()
    assert await first is SignIn.SIGNED_IN
    assert len(held.sent) == 1 and not store.signing_in


async def test_signed_out_the_client_sends_no_key(
    recorder: Recorder, storage: Storage, credentials: CredentialStorage
) -> None:
    """After a sign-out a signed call goes without `X-API-Key`, and the mock refuses it."""
    store = Account()
    api = client(recorder, store)
    await store.sign_in(api, storage, credentials, "all@example.com", "mock-all")
    await store.sign_out(storage, credentials)
    with pytest.raises(ApiError) as refused:
        await api.request(CHECK_FEATURES)
    assert refused.value.status == 401
    assert "X-API-Key" not in recorder.sent[-1].headers


async def test_the_account_outlives_a_mock_url_cleared_or_changed(
    state: MockState, storage: Storage, credentials: CredentialStorage
) -> None:
    """D-398: with no URL nothing can be sent; with another, the same account signs.

    The mock's keys are fixed seed values, so a server at the new address takes them.
    """
    store = Account()
    private_api = PrivateApi(mock_transport(state), credentials=store.credentials)
    await private_api.connect("http://10.0.2.2:8000", 2026)
    first = private_api.client
    assert first is not None
    await store.sign_in(first, storage, credentials, "all@example.com", "mock-all")
    await private_api.connect(None, 2026)
    assert private_api.base_url is None and store.signed_in
    await private_api.connect("http://192.168.1.20:8000", 2026)
    changed = private_api.client
    assert changed is not None and changed is not first
    reply = await changed.request(CHECK_FEATURES)
    assert isinstance(reply, dict) and "features" in reply


@pytest.mark.parametrize("ending", ["sign-out", "reset"])
async def test_a_late_sign_in_reply_does_not_undo_a_sign_out_or_reset(
    ending: str,
    state: MockState,
    shared: MemoryPrefs,
    keystore: MemoryKeystore,
    storage: Storage,
    credentials: CredentialStorage,
) -> None:
    """A sign-out or Reset app waits for the sign-in under way, then removes it (D-198).

    So a reply that arrives after the user signed out or reset leaves nothing stored,
    and the store ends signed out.
    """
    held = Held(mock_transport(state))
    store = Account()
    pending = asyncio.create_task(sign_in(store, held, storage, credentials))
    await asyncio.sleep(0.01)
    if ending == "sign-out":
        ended = asyncio.create_task(store.sign_out(storage, credentials))
    else:  # as reset_app: the preferences first, then the account
        await storage.clear_prefs()
        ended = asyncio.create_task(store.reset(storage, credentials))
    await asyncio.sleep(0.01)
    held.release.set()
    await pending
    assert await ended is True
    assert not store.signed_in and store.credentials() == (None, None)
    assert keystore.values == {} and ACCOUNT.key not in shared.values


@pytest.mark.parametrize("restore_failed", [False, True], ids=["restored", "unread"])
async def test_a_sign_in_killed_mid_write_never_pairs_two_accounts(
    restore_failed: bool,
    recorder: Recorder,
    shared: MemoryPrefs,
    keystore: MemoryKeystore,
    storage: Storage,
    credentials: CredentialStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The old profile goes before the new secrets come, so a relaunch is signed out.

    `all` is saved, restored or not (a failed read keeps it stored); a sign-in as
    `attendee` dies after its secrets are written but before its profile is.
    """
    accounts.save_account(
        shared,
        keystore,
        profile={**accounts.ALL, "features": accounts.EVERY_FLAG},
        api_key="mock-key-all",
        api_secret="mock-secret-all",
    )
    store = Account()
    shared.error = TimeoutError() if restore_failed else None
    await store.restore(storage, credentials)
    shared.error = None
    assert store.signed_in is not restore_failed

    async def killed(*_args: object) -> bool:
        """Stand for the app dying while `pycon.account` is written."""
        raise asyncio.CancelledError

    monkeypatch.setattr(Storage, "set", killed)  # Storage is frozen
    with pytest.raises(asyncio.CancelledError):
        await sign_in(store, recorder, storage, credentials, "attendee")
    assert keystore.values[API_KEY] == "mock-key-attendee"
    relaunched = Account()
    await relaunched.restore(storage, credentials)
    assert not relaunched.signed_in and relaunched.email == ""
    assert keystore.values == {} and ACCOUNT.key not in shared.values


async def test_an_old_profile_that_cannot_be_removed_stops_the_sign_in(
    recorder: Recorder,
    shared: MemoryPrefs,
    keystore: MemoryKeystore,
    storage: Storage,
    credentials: CredentialStorage,
) -> None:
    """Not saved, and the old account's secrets are not overwritten (STORE-03)."""
    old = {**accounts.ALL, "features": {}}
    accounts.save_account(
        shared, keystore, profile=old, api_key="old-key", api_secret="old-secret"
    )
    shared.fail_removes = True
    store = Account()
    outcome = await sign_in(store, recorder, storage, credentials, "attendee")
    assert outcome is SignIn.NOT_SAVED
    assert keystore.values == {API_KEY: "old-key", API_SECRET: "old-secret"}
    assert stored_account(shared) == old
