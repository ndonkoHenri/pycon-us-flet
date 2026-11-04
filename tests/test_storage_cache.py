"""Tests for the storage service's data directory and feed cache (STORE-01).

The service runs over the in-memory SharedPreferences and a temporary directory, from
`tests/memory_storage.py`; the key table, preferences and clearing them are
`test_storage.py`'s.
"""

import asyncio
import logging
import os
import threading
from pathlib import Path

import pytest

from pycon_us.services import data_files
from pycon_us.services.storage import Storage
from tests import memory_storage
from tests.fakes import QueuedWrite

prefs, store = memory_storage.prefs, memory_storage.store


# ------------------------------------------------------------------ the data directory


def test_data_dir_comes_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`data_dir` is `FLET_APP_STORAGE_DATA`, created if it is missing."""
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path / "app" / "data"))
    assert data_files.data_dir() == tmp_path / "app" / "data"
    assert (tmp_path / "app" / "data").is_dir()


def test_data_dir_is_read_again_on_every_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-108: iOS moves the data container on an update, so the path is never kept."""
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path / "before"))
    data_files.data_dir()
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path / "after"))
    assert data_files.data_dir() == tmp_path / "after"


@pytest.mark.parametrize("value", [None, ""])
def test_data_dir_falls_back_to_the_flet_run_layout_under_the_working_directory(
    value: str | None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unset or empty, the variable gives way to `.flet/storage/data` in the cwd."""
    if value is None:
        monkeypatch.delenv("FLET_APP_STORAGE_DATA", raising=False)
    else:
        monkeypatch.setenv("FLET_APP_STORAGE_DATA", value)
    monkeypatch.chdir(tmp_path)
    path = data_files.data_dir()
    assert path.is_absolute()
    assert path.samefile(tmp_path / ".flet" / "storage" / "data")


# ------------------------------------------------------------------ the feed cache


async def test_there_is_no_cached_feed_at_first(store: Storage) -> None:
    """A new store has no cached feed."""
    assert await store.read_feed() is None


async def test_a_written_feed_reads_back_byte_for_byte_with_its_save_time(
    store: Storage, tmp_path: Path
) -> None:
    """A written feed reads back byte for byte, with the file's modification time."""
    raw = b'{"schedule": []}\n'
    assert await store.write_feed(raw)
    cached = await store.read_feed()
    assert cached is not None
    assert cached.raw == raw
    assert cached.saved_at == (tmp_path / "feed-2026.json").stat().st_mtime


async def test_the_cache_file_is_named_after_the_year(
    store: Storage, tmp_path: Path
) -> None:
    """The 2026 feed cache is a single file named `feed-2026.json`."""
    await store.write_feed(b"{}")
    assert sorted(path.name for path in tmp_path.iterdir()) == ["feed-2026.json"]


async def test_a_new_feed_replaces_the_old_one(store: Storage) -> None:
    """A written feed replaces the cached one."""
    await store.write_feed(b"old")
    await store.write_feed(b"new")
    cached = await store.read_feed()
    assert cached is not None
    assert cached.raw == b"new"


async def test_writes_go_through_a_temp_file_and_os_replace(
    store: Storage, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A feed is written to `feed-2026.json.tmp`, then moved by `os.replace`."""
    replaced: list[tuple[str, str, bytes]] = []
    real_replace = os.replace

    def spy(src: Path, dst: Path) -> None:
        replaced.append((Path(src).name, Path(dst).name, Path(src).read_bytes()))
        real_replace(src, dst)

    monkeypatch.setattr(data_files.os, "replace", spy)
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

    monkeypatch.setattr(data_files.os, "fsync", disk_full)
    assert not await store.write_feed(b"newer")
    cached = await store.read_feed()
    assert cached is not None
    assert cached.raw == b"good"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["feed-2026.json"]
    assert "Could not save feed-2026.json" in caplog.text


async def test_a_corrupt_cache_is_deleted_and_reported(
    store: Storage, caplog: pytest.LogCaptureFixture
) -> None:
    """Deleting a corrupt cache removes it and logs the file and the reason."""
    await store.write_feed(b'{"schedule": [')
    with caplog.at_level(logging.WARNING, logger="pycon_us.services.storage"):
        await store.delete_feed("it does not parse")
    assert await store.read_feed() is None
    assert "feed-2026.json: it does not parse" in caplog.text


async def test_deleting_a_missing_cache_is_harmless(store: Storage) -> None:
    """Deleting a cache that does not exist raises nothing."""
    await store.delete_feed("cleared from the Developer screen")
    assert await store.read_feed() is None


async def test_an_unreadable_cache_reads_as_none_and_is_reported(
    store: Storage, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A cache that cannot be read reads as none, and the failure is logged."""
    (tmp_path / "feed-2026.json").mkdir()  # IsADirectoryError, an OSError
    assert await store.read_feed() is None
    assert "Could not read the cached feed" in caplog.text


@pytest.mark.parametrize("failing", ["fsync", "replace"])
async def test_no_temp_file_is_left_after_a_failed_write(
    failing: str, store: Storage, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A write that fails at fsync or at the replace leaves no file behind."""

    def fail(*args: object) -> None:
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(data_files.os, failing, fail)
    assert not await store.write_feed(b"feed")
    assert list(tmp_path.iterdir()) == []


def test_a_failed_cleanup_keeps_the_original_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When removing the temp file fails too, the write raises its first error."""

    def disk_full(fd: int) -> None:
        raise OSError(28, "No space left on device")

    def read_only(self: Path, missing_ok: bool = False) -> None:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(data_files.os, "fsync", disk_full)
    monkeypatch.setattr(Path, "unlink", read_only)
    with pytest.raises(OSError, match="No space left"):
        data_files.write_atomic(tmp_path / "feed-2026.json", b"feed")


def test_overlapping_writers_take_turns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cancelled refresh can still be writing in its thread when the next one starts."""
    path = tmp_path / "feed-2026.json"
    first_is_syncing, release_first = threading.Event(), threading.Event()
    real_fsync = os.fsync
    calls: list[int] = []
    errors: list[OSError] = []

    def slow_first_fsync(fd: int) -> None:
        calls.append(fd)
        if len(calls) == 1:
            first_is_syncing.set()
            release_first.wait(5)
        real_fsync(fd)

    def write(data: bytes) -> None:
        try:
            data_files.write_atomic(path, data)
        except OSError as error:
            errors.append(error)

    monkeypatch.setattr(data_files.os, "fsync", slow_first_fsync)
    first = threading.Thread(target=write, args=(b"A" * 100_000,))
    first.start()
    assert first_is_syncing.wait(5)
    second = threading.Thread(target=write, args=(b"B" * 10,))
    second.start()
    second.join(
        0.2
    )  # without turns, the second writer replaces the first's temp file now
    release_first.set()
    first.join(5)
    second.join(5)
    assert errors == []
    assert path.read_bytes() == b"B" * 10
    assert [p.name for p in tmp_path.iterdir()] == ["feed-2026.json"]


def test_data_dir_raises_when_it_cannot_be_created(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-120's one exception: a data directory that cannot exist is a broken install."""
    (tmp_path / "taken").write_bytes(b"")
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path / "taken"))
    with pytest.raises(OSError, match="taken"):
        data_files.data_dir()


async def test_deleting_the_cache_says_whether_it_is_gone(
    store: Storage, tmp_path: Path
) -> None:
    """`delete_feed` is True once no cache is left, False when removal fails."""
    await store.write_feed(b"feed")
    assert await store.delete_feed("Clear cached feed (Developer)") is True
    assert not store.feed_path.exists()
    assert await store.delete_feed("Reset app") is True  # none left: gone all the same
    (tmp_path / "feed-2026.json").mkdir()  # IsADirectoryError, an OSError
    assert await store.delete_feed("Reset app") is False


async def test_a_deletion_waits_for_a_write_in_progress(store: Storage) -> None:
    """A deletion waits for a write that holds the writers' lock.

    A cancelled refresh's write keeps running in its thread (D-120): a deletion that
    went first would see the file come back when the write lands.
    """
    await store.write_feed(b"feed")
    with data_files.write_lock:  # a write in progress
        deleting = asyncio.create_task(store.delete_feed("Reset app"))
        await asyncio.sleep(0.05)
        assert store.feed_path.exists()
    assert await deleting is True
    assert not store.feed_path.exists()


async def test_a_deletion_waits_for_a_write_asked_for_before_it_even_a_cancelled_one(
    store: Storage, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A deletion waits for a write asked for before it, even a cancelled one.

    The lock gives the threads turns, not order: a write still queued for it, whose
    caller was cancelled (Reset app cancels a refresh, D-198), would land after the
    deletion and bring the file back (D-244).
    """
    held = QueuedWrite(monkeypatch)
    writing = asyncio.create_task(store.write_feed(b"feed"))
    await held.queued()
    writing.cancel()
    deleting = asyncio.create_task(store.delete_feed("Reset app"))
    done, _ = await asyncio.wait({deleting}, timeout=0.1)
    held.release()
    assert not done  # it waits for the write
    assert await deleting is True
    assert not store.feed_path.exists()
