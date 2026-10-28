"""The Account store's fixtures, for its two test modules (#684).

``test_account.py`` (restore, sign-out, reset) and ``test_account_sign_in.py`` (sign-in
against the mock) run the store over the in-memory SharedPreferences of
``tests/fakes.py`` and the keystore of ``tests/keystore.py``. A module takes the
fixtures by assigning them to its own names, as ``docs/testing-and-quality.md`` §3.1
says.
"""

import json
from pathlib import Path
from typing import Any

import flet as ft
import pytest

from pycon_us.account import Account
from pycon_us.services.credentials import API_KEY, API_SECRET, CredentialStorage
from pycon_us.services.storage import ACCOUNT, Storage
from tests.fakes import MemoryPrefs
from tests.keystore import MemoryKeystore

ALL = {"email": "all@example.com", "nickname": "Robin Everything"}
"""The seeded ``all`` account's profile, without its flags."""

EVERY_FLAG = {
    "lead_retrieval": True,
    "door_check_in": True,
    "mask_violation": True,
    "is_speaker": True,
}
"""The ``all`` account's flags, by their API names."""


@pytest.fixture
def shared() -> MemoryPrefs:
    """An empty in-memory SharedPreferences."""
    return MemoryPrefs()


@pytest.fixture
def storage(shared: MemoryPrefs, tmp_path: Path) -> Storage:
    """The 2026 storage service over ``shared``."""
    return Storage(prefs=shared, directory=tmp_path, year=2026)


@pytest.fixture
def keystore() -> MemoryKeystore:
    """An empty in-memory keystore, as a packaged build has."""
    return MemoryKeystore()


@pytest.fixture
def credentials(keystore: MemoryKeystore) -> CredentialStorage:
    """The credentials' storage over ``keystore``."""
    return CredentialStorage(secure=keystore)


def save_account(
    shared: MemoryPrefs,
    keystore: MemoryKeystore,
    *,
    profile: object = None,
    api_key: str | None = None,
    api_secret: str | None = None,
) -> None:
    """Leave on the device what an earlier session saved: any of the three parts.

    Args:
        shared: SharedPreferences, for ``pycon.account`` (JSON, as stored).
        keystore: The keystore, for the key and the secret.
        profile: The account's JSON object, a string stored as is, or None for none.
        api_key: The key, or None for none.
        api_secret: The secret, or None for none.
    """
    if profile is not None:
        stored = profile if isinstance(profile, str) else json.dumps(profile)
        shared.values[ACCOUNT.key] = stored
    if api_key is not None:
        keystore.values[API_KEY] = api_key
    if api_secret is not None:
        keystore.values[API_SECRET] = api_secret


class Changes:
    """A listener that records the fields an observable store changes, in order.

    An object the test holds: a store keeps its listeners weakly, so a local
    function would be collected before the first change.
    """

    def __init__(self) -> None:
        """Start with nothing recorded."""
        self.fields: list[str] = []

    def __call__(self, _sender: object, name: str | None) -> None:
        """Record which field changed."""
        self.fields.append(str(name))


def changes(account: Account) -> Changes:
    """Subscribe a ``Changes`` to ``account`` and return it; keep it for the test."""
    listener = Changes()
    assert isinstance(account, ft.Observable)
    account.subscribe(listener)
    return listener


def stored_account(shared: MemoryPrefs) -> dict[str, Any] | None:
    """Return ``pycon.account`` as saved, decoded, or None when it is absent."""
    value = shared.values.get(ACCOUNT.key)
    return None if value is None else json.loads(value)
