"""Tests for the Account store's restore, sign-out and reset (STORE-03..05, #684).

``account.py`` restores the saved account strictly at start, removes everything but
the favourites on sign-out before it notifies, and Reset app takes the credentials too
(D-198). Sign-in against the mock is ``test_account_sign_in.py``'s.
"""

import logging

import flet as ft
import pytest

from pycon_us.account import Account, Profile
from pycon_us.services.credentials import API_KEY, API_SECRET, CredentialStorage
from pycon_us.services.storage import ACCOUNT, Storage, favorites
from tests import accounts
from tests.accounts import ALL, EVERY_FLAG, changes, save_account, stored_account
from tests.fakes import MemoryPrefs
from tests.keystore import MemoryKeystore

shared, storage, keystore, credentials = (
    accounts.shared,
    accounts.storage,
    accounts.keystore,
    accounts.credentials,
)

KEY, SECRET = "mock-key-all", "mock-secret-all"


async def test_a_saved_account_with_both_secrets_is_restored(
    shared: MemoryPrefs,
    keystore: MemoryKeystore,
    storage: Storage,
    credentials: CredentialStorage,
) -> None:
    """The preference and both secrets restore the account, its flags and its key."""
    save_account(
        shared,
        keystore,
        profile={**ALL, "features": EVERY_FLAG},
        api_key=KEY,
        api_secret=SECRET,
    )
    account = Account()
    await account.restore(storage, credentials)
    assert account.restored and account.signed_in
    assert (account.email, account.nickname) == (ALL["email"], ALL["nickname"])
    assert account.lead_retrieval and account.door_check
    assert account.mask_violation and account.is_speaker
    assert account.credentials() == (KEY, SECRET)
    assert keystore.journal == []  # a restore only reads


async def test_absent_flags_read_as_false(
    shared: MemoryPrefs,
    keystore: MemoryKeystore,
    storage: Storage,
    credentials: CredentialStorage,
) -> None:
    """A flag the account doesn't carry, or carries as no boolean, is False (STORE-05)."""
    features = {"lead_retrieval": "yes", "is_speaker": True}
    save_account(
        shared,
        keystore,
        profile={**ALL, "features": features},
        api_key=KEY,
        api_secret=SECRET,
    )
    account = Account()
    await account.restore(storage, credentials)
    assert account.signed_in and account.is_speaker
    assert not (account.lead_retrieval or account.door_check or account.mask_violation)


async def test_nothing_saved_restores_signed_out_and_writes_nothing(
    shared: MemoryPrefs,
    keystore: MemoryKeystore,
    storage: Storage,
    credentials: CredentialStorage,
) -> None:
    """A fresh install is signed out, and the restore removes nothing."""
    account = Account()
    await account.restore(storage, credentials)
    assert account.restored and not account.signed_in
    assert account.credentials() == (None, None)
    assert keystore.journal == []


@pytest.mark.parametrize(
    ("profile", "api_key", "api_secret"),
    [
        ({**ALL, "features": {}}, None, None),  # iOS kept nothing, Android a backup
        (None, KEY, SECRET),  # the keychain outlived an uninstall on iOS
        ({**ALL, "features": {}}, KEY, None),
        ({**ALL, "features": {}}, None, SECRET),
        (None, KEY, None),
        ("{not json", KEY, SECRET),
        ({"nickname": "No email", "features": {}}, KEY, SECRET),
    ],
    ids=[
        "account-only",
        "secrets-only",
        "no-secret",
        "no-key",
        "key-only",
        "unreadable-account",
        "account-without-email",
    ],
)
async def test_every_partial_state_is_cleared_and_signed_out(
    shared: MemoryPrefs,
    keystore: MemoryKeystore,
    storage: Storage,
    credentials: CredentialStorage,
    profile: object,
    api_key: str | None,
    api_secret: str | None,
) -> None:
    """Signed in only with all three parts; any part without the rest is removed."""
    save_account(
        shared, keystore, profile=profile, api_key=api_key, api_secret=api_secret
    )
    account = Account()
    await account.restore(storage, credentials)
    assert account.restored and not account.signed_in
    assert ACCOUNT.key not in shared.values
    assert keystore.values == {}


@pytest.mark.parametrize("failing", ["preferences", "keystore"])
async def test_a_failed_read_signs_out_for_the_session_and_removes_nothing(
    shared: MemoryPrefs,
    keystore: MemoryKeystore,
    storage: Storage,
    credentials: CredentialStorage,
    failing: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A read that fails says nothing about what is stored, so it is all kept (D-120)."""
    save_account(
        shared,
        keystore,
        profile={**ALL, "features": {}},
        api_key=KEY,
        api_secret=SECRET,
    )
    if failing == "preferences":
        shared.error = TimeoutError("no answer")
    else:
        keystore.failing.add("get")
    account = Account()
    with caplog.at_level(logging.WARNING):
        await account.restore(storage, credentials)
    assert account.restored and not account.signed_in
    shared.error = None
    assert ACCOUNT.key in shared.values
    assert keystore.values == {API_KEY: KEY, API_SECRET: SECRET}
    assert "signed out" in caplog.text and SECRET not in caplog.text


async def test_sign_out_removes_everything_but_the_favourites_before_it_notifies(
    shared: MemoryPrefs,
    keystore: MemoryKeystore,
    storage: Storage,
    credentials: CredentialStorage,
) -> None:
    """The key, the secret and the account are gone when ``signed_in`` turns False.

    The favourites stay (D-48), and so does what the session set.
    """
    save_account(
        shared,
        keystore,
        profile={**ALL, "features": EVERY_FLAG},
        api_key=KEY,
        api_secret=SECRET,
    )
    shared.values[favorites(2026).key] = ["9001"]
    account = Account()
    await account.restore(storage, credentials)
    seen: list[tuple[bool, bool]] = []

    def at_sign_out(_sender: object, name: str | None) -> None:
        """Record, when ``signed_in`` changes, whether the account is still stored."""
        if name == "signed_in":
            seen.append((ACCOUNT.key in shared.values, bool(keystore.values)))

    assert isinstance(account, ft.Observable)
    account.subscribe(at_sign_out)
    assert await account.sign_out(storage, credentials) is True
    assert seen == [(False, False)]
    assert not account.signed_in and account.credentials() == (None, None)
    assert (account.email, account.nickname, account.lead_retrieval) == ("", "", False)
    assert shared.values == {favorites(2026).key: ["9001"]}


async def test_a_sign_out_that_cannot_remove_everything_says_so(
    shared: MemoryPrefs,
    keystore: MemoryKeystore,
    storage: Storage,
    credentials: CredentialStorage,
) -> None:
    """A failed removal returns False; the session is signed out all the same."""
    save_account(
        shared,
        keystore,
        profile={**ALL, "features": {}},
        api_key=KEY,
        api_secret=SECRET,
    )
    account = Account()
    await account.restore(storage, credentials)
    keystore.failing.add("remove")
    assert await account.sign_out(storage, credentials) is False
    assert not account.signed_in
    assert ACCOUNT.key not in shared.values  # the next start clears the rest


async def test_reset_removes_the_credentials_and_signs_out(
    shared: MemoryPrefs,
    keystore: MemoryKeystore,
    storage: Storage,
    credentials: CredentialStorage,
) -> None:
    """Reset app's part: the key and the secret, which are no preferences (D-198)."""
    save_account(
        shared,
        keystore,
        profile={**ALL, "features": {}},
        api_key=KEY,
        api_secret=SECRET,
    )
    account = Account()
    await account.restore(storage, credentials)
    names = changes(account)
    assert await account.reset(credentials) is True
    assert keystore.values == {}
    assert not account.signed_in and account.restored
    assert names.fields[0] == "signed_in"  # first: nothing reads a half-cleared account


def test_the_owner_is_the_lower_cased_email() -> None:
    """What staff scans are recorded under: the email, whatever its case."""
    assert Account(email="Robin@Example.COM").owner == "robin@example.com"


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        {"email": "", "nickname": "N", "features": {}},
        {"email": "a@example.com", "nickname": 3, "features": {}},
        {"email": "a@example.com", "nickname": "N", "features": []},
    ],
)
def test_what_is_no_account_is_refused(value: object) -> None:
    """A profile needs an email, a nickname and a ``features`` object."""
    assert Profile.parse(value) is None


async def test_in_memory_the_sign_in_ends_with_the_session(
    shared: MemoryPrefs, storage: Storage
) -> None:
    """Without the extension the secrets die with the session (D-63).

    The next start finds the account without its secrets, a partial state, and
    clears it.
    """
    session = CredentialStorage(secure=None)
    await session.write(KEY, SECRET)
    await storage.set(ACCOUNT, {**ALL, "features": {}})
    account = Account()
    await account.restore(storage, session)
    assert account.signed_in
    later = Account()
    await later.restore(storage, CredentialStorage(secure=None))
    assert not later.signed_in
    assert stored_account(shared) is None
