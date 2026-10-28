"""Tests for the storage service: the key table, preferences and clearing them (STORE-01).

The service runs over the in-memory SharedPreferences and a temporary directory, from
``tests/memory_storage.py``; the data directory and the feed cache are
``test_storage_cache.py``'s.
"""

import logging
from typing import Any

import pytest

from pycon_us.services import storage
from pycon_us.services.storage import Pref, Storage
from tests import memory_storage
from tests.fakes import MemoryPrefs

prefs, store = memory_storage.prefs, memory_storage.store


# ------------------------------------------------------------------ the key table


ALL_PREFS = [*storage.APP_PREFS, storage.favorites(2026)]


def test_every_key_is_prefixed_and_listed_once() -> None:
    """Every preference key starts with ``pycon.`` and is in the table once."""
    keys = [pref.key for pref in ALL_PREFS]
    assert all(key.startswith("pycon.") for key in keys)
    assert len(keys) == len(set(keys))


def test_app_prefs_lists_every_app_wide_key_in_the_module() -> None:
    """``APP_PREFS`` holds exactly the module's ``Pref`` constants."""
    module_prefs = {
        id(value) for value in vars(storage).values() if isinstance(value, Pref)
    }
    assert module_prefs == {id(pref) for pref in storage.APP_PREFS}


@pytest.mark.parametrize("pref", ALL_PREFS, ids=lambda pref: pref.key)
async def test_every_default_round_trips_through_shared_preferences(
    pref: Pref[Any], store: Storage, prefs: MemoryPrefs
) -> None:
    """Each default is stored as a type SharedPreferences keeps and reads back (F12)."""
    assert await store.set(pref, pref.default)
    stored = prefs.values[pref.key]
    assert isinstance(stored, str | int | float | bool | list)  # F12
    assert await store.get(pref) == pref.default


def test_favorites_are_kept_per_year() -> None:
    """The favourites key names its year, so each year keeps its own."""
    assert storage.favorites(2026).key == "pycon.2026.favorites"
    assert storage.favorites(2027).key != storage.favorites(2026).key


# ------------------------------------------------------------------ preferences


async def test_an_absent_key_reads_as_its_default(store: Storage) -> None:
    """A key never written reads as its default."""
    assert await store.get(storage.THEME) == "system"
    assert await store.get(storage.EXCLUDED_TRACKS) == ["Open Space"]


async def test_an_explicit_empty_list_is_kept_rather_than_the_default(
    store: Storage,
) -> None:
    """A stored empty list reads back empty, not as the default."""
    await store.set(storage.EXCLUDED_TRACKS, [])
    assert await store.get(storage.EXCLUDED_TRACKS) == []


async def test_a_returned_default_is_a_copy(store: Storage) -> None:
    """Changing a returned list or dict default leaves the ``Pref``'s own as it was."""
    (await store.get(storage.EXCLUDED_TRACKS)).append("Tutorials")
    (await store.get(storage.DEV))["fake_now"] = "2026-05-15T09:00"
    assert storage.EXCLUDED_TRACKS.default == ["Open Space"]
    assert storage.DEV.default == {}


async def test_dict_values_are_stored_as_json(
    store: Storage, prefs: MemoryPrefs
) -> None:
    """A dict is stored as a JSON string and read back as the dict."""
    await store.set(storage.DEV, {"feed_url": "https://example.test/feed.json"})
    assert prefs.values["pycon.dev"] == '{"feed_url": "https://example.test/feed.json"}'
    assert await store.get(storage.DEV) == {
        "feed_url": "https://example.test/feed.json"
    }


@pytest.mark.parametrize(
    ("pref", "stored"),
    [
        (storage.ONBOARDED, "yes"),
        (storage.ONBOARDED, 1),
        (storage.THEME, True),
        (storage.EXCLUDED_TRACKS, "Open Space"),
        (storage.DEV, "{not json"),
        (storage.DEV, '["a", "list"]'),
        (storage.DEV, 3),
    ],
)
async def test_an_unreadable_value_reads_as_the_default_and_is_logged(
    pref: Pref[Any],
    stored: Any,
    store: Storage,
    prefs: MemoryPrefs,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A wrongly typed value or bad JSON reads as the default, and its key is logged."""
    prefs.values[pref.key] = stored
    assert await store.get(pref) == pref.default
    assert pref.key in caplog.text


async def test_a_failed_preference_write_is_reported(
    store: Storage, prefs: MemoryPrefs, caplog: pytest.LogCaptureFixture
) -> None:
    """A write SharedPreferences refuses returns False, and its key is logged."""
    prefs.fail_writes = True
    assert not await store.set(storage.ONBOARDED, True)
    assert "pycon.onboarded" in caplog.text


@pytest.mark.parametrize(
    "error", [TimeoutError(), RuntimeError("client error")], ids=["timeout", "client"]
)
async def test_a_failing_shared_preferences_call_is_reported_not_raised(
    error: Exception,
    store: Storage,
    prefs: MemoryPrefs,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """D-120: the app keeps going on defaults instead of ending the session."""
    prefs.error = error
    assert await store.get(storage.EXCLUDED_TRACKS) == ["Open Space"]
    assert not await store.set(storage.EXCLUDED_TRACKS, [])
    assert caplog.text.count("pycon.excluded_tracks") == 2


@pytest.mark.parametrize(
    "error", [TimeoutError(), RuntimeError("client error")], ids=["timeout", "client"]
)
async def test_read_raises_a_failing_call_that_get_turns_into_the_default(
    error: Exception, store: Storage, prefs: MemoryPrefs
) -> None:
    """D-172: the favourites must tell a failed read from an empty list."""
    prefs.values["pycon.2026.favorites"] = ["42"]
    prefs.error = error
    with pytest.raises(type(error)):
        await store.read(storage.favorites(2026))
    assert await store.get(storage.favorites(2026)) == []


async def test_read_gives_the_default_for_an_absent_or_unreadable_value(
    store: Storage, prefs: MemoryPrefs
) -> None:
    """``read`` gives the default for an absent key or a value of the wrong type."""
    assert await store.read(storage.favorites(2026)) == []
    prefs.values["pycon.2026.favorites"] = "42"
    assert await store.read(storage.favorites(2026)) == []


# ------------------------------------------------------------------ clearing preferences


async def test_clearing_removes_every_key_of_the_app_and_only_those(
    store: Storage, prefs: MemoryPrefs
) -> None:
    """``clear_prefs`` removes every ``pycon.`` key, of every year, and no other."""
    prefs.values.update(
        {
            "pycon.theme": "dark",
            "pycon.dev": '{"unlocked": true}',
            "pycon.2026.favorites": ["1"],
            "pycon.2025.favorites": ["9"],
            "another.key": "not ours",
        }
    )
    assert await store.clear_prefs() is True
    assert prefs.values == {"another.key": "not ours"}


async def test_a_key_that_cannot_be_removed_is_reported_by_name_only(
    store: Storage, prefs: MemoryPrefs, caplog: pytest.LogCaptureFixture
) -> None:
    """A key that cannot be removed is logged by name, never by value."""
    prefs.values["pycon.2026.favorites"] = ["secret-session-id"]
    prefs.fail_removes = True
    with caplog.at_level(logging.WARNING):
        assert await store.clear_prefs() is False
    assert "Could not remove preference pycon.2026.favorites" in caplog.text
    assert "secret-session-id" not in caplog.text


async def test_preferences_that_cannot_be_listed_are_not_cleared(
    store: Storage, prefs: MemoryPrefs
) -> None:
    """When the keys cannot be listed, ``clear_prefs`` returns False."""
    prefs.values["pycon.theme"] = "dark"
    prefs.error = TimeoutError("get_keys")
    assert await store.clear_prefs() is False


async def test_remove_takes_one_key_and_counts_an_absent_one_as_gone(
    store: Storage, prefs: MemoryPrefs
) -> None:
    """``remove`` deletes its key only; one that isn't there is already gone (#684)."""
    prefs.values.update({"pycon.account": "{}", "pycon.theme": "dark"})
    assert await store.remove(storage.ACCOUNT) is True
    assert prefs.values == {"pycon.theme": "dark"}
    assert await store.remove(storage.ACCOUNT) is True


@pytest.mark.parametrize("failure", ["refused", "error"])
async def test_a_key_that_cannot_be_removed_alone_is_reported(
    store: Storage, prefs: MemoryPrefs, failure: str, caplog: pytest.LogCaptureFixture
) -> None:
    """A removal refused or failing returns False and logs the key, never the value."""
    prefs.values["pycon.account"] = '{"email": "secret@example.com"}'
    if failure == "refused":
        prefs.fail_removes = True
    else:
        prefs.error = TimeoutError("remove")
    with caplog.at_level(logging.WARNING):
        assert await store.remove(storage.ACCOUNT) is False
    assert "Could not remove preference pycon.account" in caplog.text
    assert "secret@example.com" not in caplog.text


async def test_a_failed_write_logs_neither_the_value_nor_the_error_s_message(
    store: Storage, prefs: MemoryPrefs, caplog: pytest.LogCaptureFixture
) -> None:
    """D-72: Flet's timeout repeats the call's arguments, here the account's email."""
    account = {"email": "all@example.com", "nickname": "Robin", "features": {}}
    prefs.error = TimeoutError(
        "Timeout waiting for invokeMethod set("
        f"{{'key': 'pycon.account', 'value': {account!r}}}) call"
    )
    assert not await store.set(storage.ACCOUNT, account)
    assert "pycon.account" in caplog.text and "TimeoutError" in caplog.text
    assert "all@example.com" not in caplog.text
