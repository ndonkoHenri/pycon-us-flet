"""Tests for the ``ChangeLog`` store: what a refresh that publishes records (D-47, D-255).

Each case runs a real ``Conference`` refresh over an ``httpx.MockTransport`` that serves a
copy of the recorded 2026 feed with named edits (``tests/feeds.py``), with the fixtures
and helpers of ``tests/change_log_feeds.py``: the log and the cache live in a temporary
directory, and SharedPreferences is the in-memory fake. Here, over the cache and across
feed URLs; over the bundled snapshot, and ``recent()``, in ``test_change_log_snapshot.py``.
"""

import asyncio
import logging
from datetime import timedelta

import flet as ft
import httpx
import pytest

from pycon_us import clock
from pycon_us.config import YearData
from pycon_us.core.diff import ChangeKind
from pycon_us.services.pref_keys import Pref
from pycon_us.services.storage import Storage
from tests import change_log_feeds
from tests.change_log_feeds import (
    NOW,
    TALK,
    TEST_URL,
    log_file,
    marker,
    serving,
    started,
)
from tests.feeds import add, changed, move, recorded, rename

# The harness's fixtures, under this module's names, where pytest looks them up.
frozen_clock, year, storage = (
    change_log_feeds.frozen_clock,
    change_log_feeds.year,
    change_log_feeds.storage,
)


# ------------------------------------------------------------------ over the cache


async def test_a_new_feed_over_the_cache_records_one_batch_and_writes_it(
    storage: Storage, year: YearData
) -> None:
    """A move over the cache is one batch, newest first, in memory and on file."""
    await storage.write_feed(recorded(2026))
    conference, log = await started(storage, year)

    await conference.refresh(
        storage, year, transport=serving(changed(2026, move(TALK, "Room 101B")))
    )

    [batch] = log.batches
    assert batch.detected_at == NOW
    assert [(c.id, c.kind) for c in batch.changes] == [(str(TALK), ChangeKind.ROOM)]
    assert log_file(storage).exists()
    assert await marker(storage) is True


async def test_a_relaunch_reads_the_batches_back(
    storage: Storage, year: YearData
) -> None:
    """The next start's log holds the batches the last session recorded."""
    await storage.write_feed(recorded(2026))
    conference, log = await started(storage, year)
    await conference.refresh(
        storage, year, transport=serving(changed(2026, rename(TALK, "Renamed")))
    )

    _, relaunched = await started(storage, year)

    assert relaunched.batches == log.batches
    assert len(relaunched.batches) == 1


async def test_batches_are_kept_newest_first(storage: Storage, year: YearData) -> None:
    """A second batch goes before the first."""
    await storage.write_feed(recorded(2026))
    conference, log = await started(storage, year)
    first = changed(2026, move(TALK, "Room 101B"))
    await conference.refresh(storage, year, transport=serving(first))
    clock.set_test_now(NOW + timedelta(hours=1))
    second = changed(2026, rename(TALK, "Renamed"))
    await conference.refresh(storage, year, transport=serving(second))

    assert [b.detected_at for b in log.batches] == [NOW + timedelta(hours=1), NOW]


async def test_the_store_notifies_once_per_batch(
    storage: Storage, year: YearData
) -> None:
    """A recorded batch is one notification, with the batch to announce already set."""
    await storage.write_feed(recorded(2026))
    conference, log = await started(storage, year)
    seen: list[object] = []

    def keep(_sender: object, _field: str | None) -> None:
        """Take the batch to announce, as the SnackBar will on the notification."""
        seen.append(log.take_announcement())

    assert isinstance(log, ft.Observable)
    log.subscribe(keep)

    await conference.refresh(
        storage, year, transport=serving(changed(2026, move(TALK, "Room 101B")))
    )

    assert seen == [log.batches[0]]
    assert log.take_announcement() is None  # taken once


async def test_a_batch_of_additions_only_is_recorded_but_not_announced(
    storage: Storage, year: YearData
) -> None:
    """Additions are listed in a batch, but alone they announce nothing (D-255)."""
    await storage.write_feed(recorded(2026))
    conference, log = await started(storage, year)

    edit = add(5000, like=TALK, name="A late addition")
    await conference.refresh(storage, year, transport=serving(changed(2026, edit)))

    [batch] = log.batches
    assert [c.kind for c in batch.changes] == [ChangeKind.ADDED]
    assert log.take_announcement() is None


async def test_the_same_bytes_record_nothing(storage: Storage, year: YearData) -> None:
    """A refresh that brings the published feed again publishes and records nothing."""
    await storage.write_feed(recorded(2026))
    conference, log = await started(storage, year)

    await conference.refresh(storage, year, transport=serving(recorded(2026)))

    assert log.batches == ()
    assert not log_file(storage).exists()


async def test_a_failed_refresh_records_nothing(
    storage: Storage, year: YearData
) -> None:
    """A refresh whose answer is unusable records nothing."""
    await storage.write_feed(recorded(2026))
    conference, log = await started(storage, year)

    broken = httpx.MockTransport(lambda request: httpx.Response(500))
    await conference.refresh(storage, year, transport=broken)

    assert conference.problem == "server"
    assert log.batches == ()
    assert not log_file(storage).exists()


async def test_a_refresh_of_a_closed_session_records_nothing(
    storage: Storage, year: YearData
) -> None:
    """A refresh that ends after its session closed writes nothing, the log included."""
    await storage.write_feed(recorded(2026))
    conference, log = await started(storage, year)
    closed = asyncio.Event()
    closed.set()

    feed = changed(2026, move(TALK, "Room 101B"))
    await conference.refresh(storage, year, transport=serving(feed), closed=closed)

    assert log.batches == ()
    assert not log_file(storage).exists()


async def test_the_diff_time_and_count_are_logged(
    storage: Storage, year: YearData, caplog: pytest.LogCaptureFixture
) -> None:
    """The diff logs how long it took and how many changes it found."""
    await storage.write_feed(recorded(2026))
    conference, _ = await started(storage, year)

    with caplog.at_level(logging.INFO, logger="pycon_us.change_log"):
        await conference.refresh(
            storage, year, transport=serving(changed(2026, move(TALK, "Room 101B")))
        )

    assert any(
        m.startswith("Feeds diffed in ") and m.endswith(" ms: 1 changes")
        for m in caplog.messages
    )


# ------------------------------------------------------------------ feed URLs


async def test_a_feed_from_another_feed_url_is_not_diffed(
    storage: Storage, year: YearData
) -> None:
    """After a feed URL change, the next refresh publishes without a diff (D-255)."""
    await storage.write_feed(recorded(2026))
    conference, log = await started(storage, year)
    await conference.set_feed_url(TEST_URL, storage)

    feed = changed(2026, move(TALK, "Room 101B"))
    await conference.refresh(storage, year, transport=serving(feed))

    assert conference.source == "network"
    assert log.batches == ()
    # ...and the next one, from the same URL, is diffed again.
    again = changed(2026, move(TALK, "Room 101C"))
    await conference.refresh(storage, year, transport=serving(again))
    assert len(log.batches) == 1


async def test_a_new_feed_urls_same_bytes_count_as_its_feed_for_the_next_diff(
    storage: Storage, year: YearData
) -> None:
    """A new feed URL's first refresh that brings the feed shown makes it that URL's.

    It publishes nothing (D-224), but the next feed from that URL is diffed against
    it, as after a first refresh that publishes (D-255): a feed pair whose old side is
    the feed already shown keeps its change (#460).
    """
    await storage.write_feed(recorded(2026))
    conference, log = await started(storage, year)
    await conference.set_feed_url(TEST_URL, storage)

    await conference.refresh(storage, year, transport=serving(recorded(2026)))
    assert log.batches == ()
    feed = changed(2026, move(TALK, "Room 101B"))
    await conference.refresh(storage, year, transport=serving(feed))

    assert [change.kind for change in log.batches[0].changes] == [ChangeKind.ROOM]


async def test_a_feed_url_change_forgets_the_batches_in_memory(
    storage: Storage, year: YearData
) -> None:
    """The log deleted with the old URL's cache is gone from memory too (D-255)."""
    await storage.write_feed(recorded(2026))
    conference, log = await started(storage, year)
    feed = changed(2026, move(TALK, "Room 101B"))
    await conference.refresh(storage, year, transport=serving(feed))

    await conference.set_feed_url(TEST_URL, storage)

    assert log.batches == ()
    assert not log_file(storage).exists()


async def test_a_url_left_between_the_publish_and_the_log_write_records_nothing(
    storage: Storage, year: YearData, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A URL left during the hand-off's last await records nothing, though it published."""
    await storage.write_feed(recorded(2026))
    conference, log = await started(storage, year)
    save = Storage.set

    async def leave_then_save(self: Storage, pref: Pref[bool], value: bool) -> bool:
        """Leave the feed URL, then save: the marker's save, the hand-off's last await."""
        await conference.set_feed_url(TEST_URL, storage)
        return await save(self, pref, value)

    monkeypatch.setattr(Storage, "set", leave_then_save)
    feed = changed(2026, move(TALK, "Room 101B"))
    await conference.refresh(storage, year, transport=serving(feed))

    assert conference.source == "network"
    assert log.batches == ()
    assert not log_file(storage).exists()


async def test_a_session_closed_between_the_publish_and_the_log_write_records_nothing(
    storage: Storage, year: YearData, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A session closed during the hand-off's last await records nothing (F30)."""
    await storage.write_feed(recorded(2026))
    conference, log = await started(storage, year)
    closed = asyncio.Event()
    save = Storage.set

    async def close_then_save(self: Storage, pref: Pref[bool], value: bool) -> bool:
        """Close the session, then save: the marker's save, the hand-off's last await."""
        closed.set()
        return await save(self, pref, value)

    monkeypatch.setattr(Storage, "set", close_then_save)
    feed = changed(2026, move(TALK, "Room 101B"))
    await conference.refresh(storage, year, transport=serving(feed), closed=closed)

    assert log.batches == ()
    assert not log_file(storage).exists()
