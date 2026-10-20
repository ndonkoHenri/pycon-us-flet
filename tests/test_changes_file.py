"""The change log's file, ``changes-<year>.json`` (D-47, D-120, D-255; NEW-04).

Over a real ``Storage`` in ``tmp_path`` with in-memory SharedPreferences; the batches'
JSON form itself is ``tests/test_change_batches.py``'s.
"""

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from pycon_us.core.change_batches import Batch, encode_batches
from pycon_us.core.diff import Change, ChangeKind, Listing
from pycon_us.services import storage
from pycon_us.services.changes_file import (
    changes_path,
    delete_batches,
    read_batches,
    write_batches,
)
from pycon_us.services.storage import Storage
from tests.fakes import MemoryPrefs, QueuedWrite

PACIFIC = ZoneInfo("America/Los_Angeles")
NOW = datetime(2026, 5, 16, 17, 42, tzinfo=UTC)
MOVED = Change(
    "142",
    ChangeKind.ROOM,
    Listing(
        "Python for Humans",
        datetime(2026, 5, 16, 10, 30, tzinfo=PACIFIC),
        datetime(2026, 5, 16, 11, tzinfo=PACIFIC),
        "Grand Ballroom A",
    ),
    Listing(
        "Python for Humans",
        datetime(2026, 5, 16, 10, 30, tzinfo=PACIFIC),
        datetime(2026, 5, 16, 11, tzinfo=PACIFIC),
        "Room 101B",
    ),
)
"""2026's talk 142 moved to another room."""


@pytest.fixture
def store(tmp_path: Path) -> Storage:
    """A 2026 ``Storage`` in ``tmp_path``, over in-memory SharedPreferences."""
    return Storage(prefs=MemoryPrefs(), directory=tmp_path, year=2026)


def batches(*hours_ago: int) -> list[Batch]:
    """One batch of ``MOVED`` for each of ``hours_ago``, detected that long before NOW."""
    return [Batch(NOW - timedelta(hours=hours), (MOVED,)) for hours in hours_ago]


def test_the_log_is_per_year_in_the_data_directory(store: Storage) -> None:
    """The log is ``changes-<year>.json`` beside the feed cache (section M)."""
    assert changes_path(store) == store.directory / "changes-2026.json"
    other = Storage(prefs=store.prefs, directory=store.directory, year=2025)
    assert changes_path(other).name == "changes-2025.json"


async def test_batches_written_are_read_back_after_a_relaunch(
    tmp_path: Path, store: Storage
) -> None:
    """What one session writes, a new session's storage reads back, in order."""
    written = batches(0, 5)
    assert await write_batches(store, written) is True
    relaunched = Storage(prefs=MemoryPrefs(), directory=tmp_path, year=2026)
    assert await read_batches(relaunched, PACIFIC) == written


async def test_without_a_file_there_are_no_batches(store: Storage) -> None:
    """A fresh install, or a log deleted, reads as no batches, with no warning."""
    assert await read_batches(store, PACIFIC) == []


async def test_a_corrupt_file_gives_what_can_be_read_and_a_log(
    store: Storage, caplog: pytest.LogCaptureFixture
) -> None:
    """A partly corrupt file gives its good batches; the bad one is logged."""
    entries = json.loads(encode_batches(batches(0, 2)))
    entries.insert(1, {"x": 1})  # not batches as the app writes them
    entries.append({"seen": False})
    changes_path(store).write_text(json.dumps(entries))
    with caplog.at_level(logging.WARNING):
        read = await read_batches(store, PACIFIC)
    assert read == batches(0, 2)
    assert "Skipped change batch 1 of the log" in caplog.text
    assert "Skipped change batch 3 of the log" in caplog.text


async def test_a_file_that_is_not_json_reads_as_no_batches(
    store: Storage, caplog: pytest.LogCaptureFixture
) -> None:
    """A truncated file reads as no batches, logged, and is left for the next write."""
    changes_path(store).write_bytes(encode_batches(batches(0))[:40])
    with caplog.at_level(logging.WARNING):
        assert await read_batches(store, PACIFIC) == []
    assert "The change log is not JSON" in caplog.text


async def test_an_unreadable_file_reads_as_no_batches(
    store: Storage, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A file the system cannot read reads as no batches, logged by its name (D-120)."""
    changes_path(store).write_bytes(encode_batches(batches(0)))

    def denied(self: Path) -> bytes:
        """Fail as a read the system refuses would."""
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Path, "read_bytes", denied)
    with caplog.at_level(logging.WARNING):
        assert await read_batches(store, PACIFIC) == []
    assert "Could not read the change log changes-2026.json" in caplog.text


async def test_a_failed_write_returns_false_and_keeps_the_old_file(
    store: Storage,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A write that fails says so and leaves the previous log whole (D-120)."""
    await write_batches(store, batches(0))

    def disk_full(fd: int) -> None:
        """Fail as a full disk does."""
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(storage.os, "fsync", disk_full)
    with caplog.at_level(logging.WARNING):
        assert await write_batches(store, batches(0, 1, 2)) is False
    assert await read_batches(store, PACIFIC) == batches(0)
    assert sorted(path.name for path in tmp_path.iterdir()) == ["changes-2026.json"]
    assert "Could not save changes-2026.json" in caplog.text


async def test_deleting_the_log_removes_it_and_says_why(
    store: Storage, caplog: pytest.LogCaptureFixture
) -> None:
    """Deleting removes the file and logs the reason; deleting none is fine too."""
    await write_batches(store, batches(0))
    with caplog.at_level(logging.WARNING):
        assert await delete_batches(store, "Reset app") is True
    assert not changes_path(store).exists()
    assert "Deleting changes-2026.json: Reset app" in caplog.text
    assert await delete_batches(store, "Reset app") is True  # nothing to delete


async def test_a_failed_deletion_returns_false(
    store: Storage, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A deletion the system refuses says so and is logged by the file's name."""
    await write_batches(store, batches(0))

    def refuse(path: Path) -> None:
        """Fail as a deletion the system refuses would."""
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(storage, "_unlink", refuse)
    with caplog.at_level(logging.WARNING):
        assert await delete_batches(store, "Reset app") is False
    assert "Could not delete changes-2026.json" in caplog.text


async def test_a_deletion_waits_for_a_queued_write_of_either_file(
    store: Storage, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A log deletion lets a feed write asked for before it land first, and vice versa.

    Both files' writes are kept in ``Storage._writes``, so neither deletion can be
    overtaken by a write asked for before it (D-244's order, D-255).
    """
    held = QueuedWrite(monkeypatch)
    feed = asyncio.create_task(store.write_feed(b"{}"))
    await held.queued()
    log = asyncio.create_task(write_batches(store, batches(0)))
    deleting = asyncio.create_task(delete_batches(store, "the feed URL changed"))
    done, _ = await asyncio.wait({deleting}, timeout=0.1)
    held.release()
    await asyncio.gather(feed, log, deleting)
    assert not done  # it waited for both writes
    assert not changes_path(store).exists()
    assert await store.delete_feed("the feed URL changed") is True
    assert not store.feed_path.exists()
