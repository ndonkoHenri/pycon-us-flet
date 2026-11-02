"""Tests for where the mock account's key and secret are kept (D-49, D-63, #684).

``services/credentials.py`` keeps them in the platform keystore when the build has
``flet-secure-storage``, else in memory for the session; its failures are logged and
returned (D-120), and its logs never carry a secret (D-72).
"""

import logging

import pytest
from flet_secure_storage import KeychainAccessibility, SecureStorage

from pycon_us import capabilities
from pycon_us.services.credentials import (
    API_KEY,
    API_SECRET,
    CredentialStorage,
    secure_storage,
)
from tests.keystore import MemoryKeystore


@pytest.fixture
def keystore() -> MemoryKeystore:
    """An empty in-memory keystore."""
    return MemoryKeystore()


def test_without_the_extension_there_is_no_keystore() -> None:
    """Outside a packaged build (the companion app, pytest) no ``SecureStorage`` is made."""
    assert capabilities.SECURE_STORAGE is False
    assert secure_storage() is None
    assert CredentialStorage().secure is None


def test_a_packaged_build_keeps_them_after_the_first_unlock_on_this_device_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With the extension, the keychain items are readable after the first unlock.

    ``FIRST_UNLOCK_THIS_DEVICE``: a start in the background can read them, and a
    backup restored on another phone carries none.
    """
    monkeypatch.setattr(capabilities, "SECURE_STORAGE", True)
    service = secure_storage()
    assert isinstance(service, SecureStorage)
    assert (
        service.ios_options.accessibility
        is KeychainAccessibility.FIRST_UNLOCK_THIS_DEVICE
    )
    assert service.ios_options.synchronizable is False


async def test_in_memory_they_last_for_the_session_only() -> None:
    """The interim keeps them in this object: a new session's storage has none."""
    stored = CredentialStorage(secure=None)
    assert await stored.read() == (None, None)
    assert await stored.write("mock-key-all", "mock-secret-all") is True
    assert await stored.read() == ("mock-key-all", "mock-secret-all")
    assert await CredentialStorage(secure=None).read() == (None, None)
    assert await stored.remove() is True
    assert await stored.read() == (None, None)


async def test_the_keystore_holds_both_under_their_own_keys(
    keystore: MemoryKeystore,
) -> None:
    """Write, read and remove go to ``pycon.api_key`` and ``pycon.api_secret``."""
    stored = CredentialStorage(secure=keystore)
    assert await stored.write("mock-key-all", "mock-secret-all") is True
    assert keystore.values == {API_KEY: "mock-key-all", API_SECRET: "mock-secret-all"}
    assert await stored.read() == ("mock-key-all", "mock-secret-all")
    assert await stored.remove() is True
    assert keystore.values == {}
    assert keystore.journal == [
        f"set {API_KEY}",
        f"set {API_SECRET}",
        f"remove {API_KEY}",
        f"remove {API_SECRET}",
    ]


async def test_one_stored_without_the_other_reads_as_absent_parts(
    keystore: MemoryKeystore,
) -> None:
    """A lone key reads as the key and no secret, for ``Account.restore`` to clear."""
    keystore.values[API_KEY] = "mock-key-all"
    assert await CredentialStorage(secure=keystore).read() == ("mock-key-all", None)


@pytest.mark.parametrize("method", ["get", "set", "remove"])
async def test_a_keystore_failure_is_returned_and_logged_without_the_secret(
    keystore: MemoryKeystore, method: str, caplog: pytest.LogCaptureFixture
) -> None:
    """A failing read is None, a write or removal False; the log names the key only.

    The platform's error repeats the call's arguments, the secret among them, so
    the log keeps only its class (D-72).
    """
    stored = CredentialStorage(secure=keystore)
    keystore.values[API_KEY] = "mock-key-all"
    keystore.failing.add(method)
    with caplog.at_level(logging.WARNING):
        if method == "get":
            assert await stored.read() is None
        elif method == "set":
            assert await stored.write("mock-key-all", "mock-secret-all") is False
        else:
            assert await stored.remove() is False
    assert API_KEY in caplog.text and "RuntimeError" in caplog.text
    assert "mock-secret-all" not in caplog.text
    assert "mock-key-all" not in caplog.text


async def test_a_removal_tries_both_keys_when_the_first_fails() -> None:
    """Sign-out removes what it can: one failure doesn't keep the other secret."""

    class FirstRemovalFails(MemoryKeystore):
        """Fails to remove the key, and only the key."""

        async def remove(self, key: str, **_: object) -> None:
            """Raise for ``pycon.api_key``, remove anything else."""
            if key == API_KEY:
                raise TimeoutError
            self.values.pop(key, None)

    store = FirstRemovalFails()
    store.values.update({API_KEY: "k", API_SECRET: "s"})
    assert await CredentialStorage(secure=store).remove() is False
    assert store.values == {API_KEY: "k"}
