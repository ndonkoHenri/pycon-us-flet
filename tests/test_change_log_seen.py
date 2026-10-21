"""Tests for ``ChangeLog``'s seen marks: ``mark_seen()`` and the unseen count (ux.md §6.4).

The batches are built by hand; the log file lives in a temporary directory, and
SharedPreferences is the in-memory fake.
"""

import asyncio
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from pycon_us import clock
from pycon_us.change_log import ChangeLog
from pycon_us.core.change_batches import Batch
from pycon_us.core.diff import Change, ChangeKind, Listing
from pycon_us.services import changes_file
from pycon_us.services.storage import Storage
from tests.fakes import MemoryPrefs

LA = ZoneInfo("America/Los_Angeles")
NOW = datetime(2026, 5, 16, 17, 42, tzinfo=UTC)
START = datetime(2026, 5, 16, 10, 30, tzinfo=LA)


def moved(key: str) -> Change:
    """A room change of session ``key``."""
    old = Listing("Talk", START, START + timedelta(minutes=30), "Room 101A")
    return Change(key, ChangeKind.ROOM, old, replace(old, location="Room 102A"))


NEWEST = Batch(NOW - timedelta(minutes=5), (moved("1"), moved("2")))
"""Five minutes ago: two sessions moved."""

OLDER = Batch(NOW - timedelta(hours=3), (moved("3"),))
"""Three hours ago: one session moved."""


@pytest.fixture(autouse=True)
def frozen_clock() -> Iterator[None]:
    """Freeze ``clock.now()`` at ``NOW``, so a reload keeps the batches (14 days)."""
    clock.set_test_now(NOW)
    yield
    clock.set_test_now(None)


@pytest.fixture
def storage(tmp_path: Path) -> Storage:
    """A 2026 ``Storage`` in ``tmp_path``, over in-memory SharedPreferences."""
    return Storage(prefs=MemoryPrefs(), directory=tmp_path, year=2026)


async def test_marks_survive_a_relaunch(storage: Storage) -> None:
    """Marked batches are saved: a new store loading the file reads them seen."""
    log = ChangeLog(batches=(NEWEST, OLDER))
    write = log.mark_seen(storage, [NEWEST])
    assert write is not None and await write
    assert [batch.seen for batch in log.batches] == [True, False]
    relaunched = ChangeLog()
    await relaunched.load(storage, LA)
    assert [batch.seen for batch in relaunched.batches] == [True, False]


async def test_mark_seen_without_batches_marks_every_one(storage: Storage) -> None:
    """Mark all as seen: no batches given marks the whole log, and it notifies."""
    log = ChangeLog(batches=(NEWEST, OLDER))
    assert log.has_unseen
    write = log.mark_seen(storage)
    assert write is not None and await write
    assert not log.has_unseen


async def test_nothing_unseen_writes_nothing(storage: Storage) -> None:
    """Marking batches already seen, or gone from the log, starts no write."""
    log = ChangeLog(batches=(NEWEST,))
    write = log.mark_seen(storage)
    assert write is not None
    await write
    assert log.mark_seen(storage) is None
    assert log.mark_seen(storage, [OLDER]) is None


async def test_a_batch_recorded_before_the_write_starts_is_kept(
    storage: Storage,
) -> None:
    """The write saves the log as it is when it starts, so a newer batch is not lost."""
    log = ChangeLog(batches=(OLDER,))
    write = log.mark_seen(storage)
    log.batches = (NEWEST, *log.batches)  # recorded before the write's task ran
    assert write is not None and await write
    relaunched = ChangeLog()
    await relaunched.load(storage, LA)
    assert [batch.seen for batch in relaunched.batches] == [False, True]


async def test_a_batch_recorded_while_a_write_is_held_is_saved_after_it(
    storage: Storage, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Writes take turns in order: one held in its thread cannot land over a newer one.

    The first seen mark's write is held mid-write; a refresh then records a batch and
    a second write is asked for (``record()`` and ``mark_seen()`` share ``_save()``).
    The second must wait for the first and save the log as it is then.
    """
    real = changes_file.write_batches
    release = asyncio.Event()
    started: list[int] = []

    async def held_first(storage: Storage, batches: list[Batch]) -> bool:
        """Write ``batches``; the first call waits for the test's release first."""
        started.append(len(batches))
        if len(started) == 1:
            await release.wait()
        return await real(storage, batches)

    monkeypatch.setattr(changes_file, "write_batches", held_first)
    log = ChangeLog(batches=(OLDER,))
    first = log.mark_seen(storage)
    await asyncio.sleep(0)  # the first write starts, and is held
    log.batches = (NEWEST, *log.batches)  # a refresh records a batch meanwhile
    second = log.mark_seen(storage, [log.batches[0]])
    await asyncio.sleep(0)
    assert started == [1]  # the second waits for its turn
    release.set()
    assert first is not None and second is not None
    assert await first and await second
    assert started == [1, 2]
    relaunched = ChangeLog()
    await relaunched.load(storage, LA)
    assert len(relaunched.batches) == 2


async def test_a_delete_waits_for_the_writes_asked_before_it(
    storage: Storage, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A write still waiting for its turn lands before the delete, never after it."""
    real = changes_file.write_batches
    release = asyncio.Event()

    async def held(storage: Storage, batches: list[Batch]) -> bool:
        """Write ``batches`` once the test releases the writes."""
        await release.wait()
        return await real(storage, batches)

    monkeypatch.setattr(changes_file, "write_batches", held)
    log = ChangeLog(batches=(NEWEST, OLDER))
    writes = [
        log.mark_seen(storage, [NEWEST]),
        log.mark_seen(storage, [log.batches[1]]),  # queued behind the first
    ]
    await asyncio.sleep(0)
    delete = asyncio.create_task(log.delete(storage, "the feed URL changed"))
    await asyncio.sleep(0.05)
    release.set()
    assert await delete
    await asyncio.gather(*(write for write in writes if write is not None))
    assert not changes_file.changes_path(storage).exists()


def test_unseen_saved_counts_saved_sessions_of_unseen_recent_batches() -> None:
    """Each saved session of an unseen batch of the last 24 h counts once."""
    log = ChangeLog(batches=(NEWEST, OLDER))
    assert log.unseen_saved({"1", "3"}, NOW) == 2
    assert log.unseen_saved({"9"}, NOW) == 0
    seen = ChangeLog(batches=(Batch(NEWEST.detected_at, NEWEST.changes, seen=True),))
    assert seen.unseen_saved({"1"}, NOW) == 0
