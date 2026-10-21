"""Tests for ``ChangeLog``'s seen marks: ``mark_seen()`` and the unseen count (ux.md §6.4).

The batches are built by hand; the log file lives in a temporary directory, and
SharedPreferences is the in-memory fake.
"""

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


def test_unseen_saved_counts_saved_sessions_of_unseen_recent_batches() -> None:
    """Each saved session of an unseen batch of the last 24 h counts once."""
    log = ChangeLog(batches=(NEWEST, OLDER))
    assert log.unseen_saved({"1", "3"}, NOW) == 2
    assert log.unseen_saved({"9"}, NOW) == 0
    seen = ChangeLog(batches=(Batch(NEWEST.detected_at, NEWEST.changes, seen=True),))
    assert seen.unseen_saved({"1"}, NOW) == 0
