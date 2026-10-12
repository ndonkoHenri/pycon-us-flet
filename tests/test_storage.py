"""Tests for the storage service: the key table, preferences and the feed cache (STORE-01)."""

import logging
import os
from pathlib import Path
from typing import Any

import flet as ft
import pytest

from pycon_us.services import storage
from pycon_us.services.storage import Pref, Storage


class MemoryPrefs(ft.SharedPreferences):
    """SharedPreferences backed by a dict instead of the Flutter side.

    Only the transport is replaced, so Flet's own type check in ``set`` still runs.
    """

    def init(self) -> None:
        self.values: dict[str, Any] = {}
        self.fail_writes = False

    async def _invoke_method(
        self,
        method_name: str,
        arguments: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        assert arguments is not None
        if method_name == "get":
            return self.values.get(arguments["key"])
        if method_name == "set":
            if self.fail_writes:
                return False
            self.values[arguments["key"]] = arguments["value"]
            return True
        raise AssertionError(f"unexpected call {method_name}")


@pytest.fixture
def prefs() -> MemoryPrefs:
    return MemoryPrefs()


@pytest.fixture
def store(prefs: MemoryPrefs, tmp_path: Path) -> Storage:
    return Storage(prefs=prefs, directory=tmp_path, year=2026)


# ------------------------------------------------------------------ the key table


ALL_PREFS = [*storage.APP_PREFS, storage.favorites(2026)]


def test_every_key_is_prefixed_and_listed_once() -> None:
    keys = [pref.key for pref in ALL_PREFS]
    assert all(key.startswith("pycon.") for key in keys)
    assert len(keys) == len(set(keys))


def test_app_prefs_lists_every_app_wide_key_in_the_module() -> None:
    module_prefs = {
        id(value) for value in vars(storage).values() if isinstance(value, Pref)
    }
    assert module_prefs == {id(pref) for pref in storage.APP_PREFS}


@pytest.mark.parametrize("pref", ALL_PREFS, ids=lambda pref: pref.key)
async def test_every_default_round_trips_through_shared_preferences(
    pref: Pref[Any], store: Storage, prefs: MemoryPrefs
) -> None:
    assert await store.set(pref, pref.default)
    stored = prefs.values[pref.key]
    assert isinstance(stored, str | int | float | bool | list)  # F12
    assert await store.get(pref) == pref.default


def test_favorites_are_kept_per_year() -> None:
    assert storage.favorites(2026).key == "pycon.2026.favorites"
    assert storage.favorites(2027).key != storage.favorites(2026).key


# ------------------------------------------------------------------ preferences


async def test_an_absent_key_reads_as_its_default(store: Storage) -> None:
    assert await store.get(storage.THEME) == "system"
    assert await store.get(storage.EXCLUDED_TRACKS) == ["Open Space"]


async def test_an_explicit_empty_list_is_kept_rather_than_the_default(
    store: Storage,
) -> None:
    await store.set(storage.EXCLUDED_TRACKS, [])
    assert await store.get(storage.EXCLUDED_TRACKS) == []


async def test_a_returned_default_is_a_copy(store: Storage) -> None:
    (await store.get(storage.EXCLUDED_TRACKS)).append("Tutorials")
    (await store.get(storage.DEV))["fake_now"] = "2026-05-15T09:00"
    assert storage.EXCLUDED_TRACKS.default == ["Open Space"]
    assert storage.DEV.default == {}


async def test_dict_values_are_stored_as_json(
    store: Storage, prefs: MemoryPrefs
) -> None:
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
    prefs.values[pref.key] = stored
    assert await store.get(pref) == pref.default
    assert pref.key in caplog.text


async def test_a_failed_preference_write_is_reported(
    store: Storage, prefs: MemoryPrefs, caplog: pytest.LogCaptureFixture
) -> None:
    prefs.fail_writes = True
    assert not await store.set(storage.ONBOARDED, True)
    assert "pycon.onboarded" in caplog.text


# ------------------------------------------------------------------ the data directory


def test_data_dir_comes_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path / "app" / "data"))
    assert storage.data_dir() == tmp_path / "app" / "data"
    assert (tmp_path / "app" / "data").is_dir()


def test_data_dir_is_read_again_on_every_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-108: iOS moves the data container on an update, so the path is never kept."""
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path / "before"))
    storage.data_dir()
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path / "after"))
    assert storage.data_dir() == tmp_path / "after"


@pytest.mark.parametrize("value", [None, ""])
def test_data_dir_falls_back_to_the_flet_run_layout_under_the_working_directory(
    value: str | None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if value is None:
        monkeypatch.delenv("FLET_APP_STORAGE_DATA", raising=False)
    else:
        monkeypatch.setenv("FLET_APP_STORAGE_DATA", value)
    monkeypatch.chdir(tmp_path)
    path = storage.data_dir()
    assert path.is_absolute()
    assert path.samefile(tmp_path / ".flet" / "storage" / "data")


# ------------------------------------------------------------------ the feed cache


async def test_there_is_no_cached_feed_at_first(store: Storage) -> None:
    assert await store.read_feed() is None


async def test_a_written_feed_reads_back_byte_for_byte_with_its_save_time(
    store: Storage, tmp_path: Path
) -> None:
    raw = b'{"schedule": []}\n'
    assert await store.write_feed(raw)
    cached = await store.read_feed()
    assert cached is not None
    assert cached.raw == raw
    assert cached.saved_at == os.stat(tmp_path / "feed-2026.json").st_mtime


async def test_the_cache_file_is_named_after_the_year(
    store: Storage, tmp_path: Path
) -> None:
    await store.write_feed(b"{}")
    assert sorted(path.name for path in tmp_path.iterdir()) == ["feed-2026.json"]


async def test_a_new_feed_replaces_the_old_one(store: Storage) -> None:
    await store.write_feed(b"old")
    await store.write_feed(b"new")
    cached = await store.read_feed()
    assert cached is not None
    assert cached.raw == b"new"


async def test_writes_go_through_a_temp_file_and_os_replace(
    store: Storage, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    replaced: list[tuple[str, str, bytes]] = []
    real_replace = os.replace

    def spy(src: Path, dst: Path) -> None:
        replaced.append((Path(src).name, Path(dst).name, Path(src).read_bytes()))
        real_replace(src, dst)

    monkeypatch.setattr(storage.os, "replace", spy)
    await store.write_feed(b"feed")
    assert replaced == [("feed-2026.json.tmp", "feed-2026.json", b"feed")]


async def test_a_failed_write_keeps_the_previous_cache_and_is_reported(
    store: Storage,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """D-39: a refresh never loses the last good feed."""
    await store.write_feed(b"good")

    def disk_full(fd: int) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(storage.os, "fsync", disk_full)
    assert not await store.write_feed(b"newer")
    cached = await store.read_feed()
    assert cached is not None
    assert cached.raw == b"good"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["feed-2026.json"]
    assert "Could not save the feed cache" in caplog.text


async def test_a_corrupt_cache_is_deleted_and_reported(
    store: Storage, caplog: pytest.LogCaptureFixture
) -> None:
    await store.write_feed(b'{"schedule": [')
    with caplog.at_level(logging.WARNING, logger="pycon_us.services.storage"):
        await store.delete_feed("it does not parse")
    assert await store.read_feed() is None
    assert "feed-2026.json: it does not parse" in caplog.text


async def test_deleting_a_missing_cache_is_harmless(store: Storage) -> None:
    await store.delete_feed("cleared from the Developer screen")
    assert await store.read_feed() is None


async def test_an_unreadable_cache_reads_as_none_and_is_reported(
    store: Storage, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "feed-2026.json").mkdir()  # IsADirectoryError, an OSError
    assert await store.read_feed() is None
    assert "Could not read the cached feed" in caplog.text
