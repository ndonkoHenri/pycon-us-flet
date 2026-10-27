"""Tests for the Conference store: cache-first load and single-flight refresh (DATA-01, DATA-02).

The feeds, transports and fixtures are ``tests/feed_store.py``'s.
"""

import asyncio
import logging
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import flet as ft
import httpx
import pytest

from pycon_us.config import YearData
from pycon_us.core.feed import process
from pycon_us.feed_refresh import Status, feed_digest
from pycon_us.services.storage import Storage
from pycon_us.state import Conference
from tests import feed_store
from tests.fakes import MemoryPrefs
from tests.feed_store import (
    CACHED_FEED,
    FAILURES,
    NETWORK_FEED,
    NOW,
    HeldFeed,
    failing,
    loaded,
    serving,
    title,
)

frozen_clock, year, storage = (
    feed_store.frozen_clock,
    feed_store.year,
    feed_store.storage,
)


# ------------------------------------------------------------------ load_local


async def test_without_a_cache_the_bundled_snapshot_is_published(
    storage: Storage, year: YearData
) -> None:
    """Without a cache, the snapshot is published as version 1, never copied to it."""
    conference = await loaded(storage, year)

    snapshot = year.read_snapshot()
    assert conference.source == "bundled"
    assert conference.fetched_at == snapshot.captured_at
    assert conference.data is not None
    expected = process(snapshot.raw, year.feed_settings)
    assert conference.data.sessions.keys() == expected.sessions.keys()
    assert conference.version == 1
    assert conference.problem is None
    assert not storage.feed_path.exists()  # the snapshot is never copied to the cache


async def test_the_digest_names_the_published_feed(
    storage: Storage, year: YearData
) -> None:
    """``digest`` is None before a publish, then the SHA-256 of the published bytes (D-271)."""
    assert Conference().digest is None
    conference = await loaded(storage, year)
    assert conference.digest == feed_digest(year.read_snapshot().raw)
    await conference.refresh(storage, year, transport=serving(NETWORK_FEED))
    assert conference.digest == feed_digest(NETWORK_FEED)


async def test_the_feed_cache_wins_over_the_snapshot(
    storage: Storage, year: YearData
) -> None:
    """The cache is published over a newer snapshot, dated by its file's time in UTC."""
    assert await storage.write_feed(CACHED_FEED)
    saved_at = datetime(
        2026, 10, 1, 8, 0, tzinfo=UTC
    )  # older than the bundled snapshot
    os.utime(storage.feed_path, (saved_at.timestamp(), saved_at.timestamp()))

    conference = await loaded(storage, year)

    assert conference.source == "cache"
    assert title(conference.data) == "Renamed in the cache"
    assert conference.fetched_at == saved_at
    assert conference.fetched_at is not None  # narrows the type for pyright
    assert conference.fetched_at.tzinfo is UTC
    # D-145: the cache wins even when an update installs a newer snapshot.
    assert saved_at < year.read_snapshot().captured_at


async def test_a_corrupt_cache_is_deleted_and_the_snapshot_published(
    storage: Storage, year: YearData, caplog: pytest.LogCaptureFixture
) -> None:
    """A cache that isn't JSON is deleted with a warning, and the snapshot published."""
    assert await storage.write_feed(b'{"schedule": "truncated')

    with caplog.at_level(logging.WARNING):
        conference = await loaded(storage, year)

    assert conference.source == "bundled"
    assert conference.data is not None
    assert not storage.feed_path.exists()
    assert "Deleting feed-2026.json: it does not parse: not JSON" in caplog.text


async def test_a_cache_with_the_wrong_structure_is_deleted_too(
    storage: Storage, year: YearData
) -> None:
    """A cache that parses but has no readable slot is deleted too, for the snapshot."""
    assert await storage.write_feed(b'{"schedule": []}')  # no readable slot

    conference = await loaded(storage, year)

    assert conference.source == "bundled"
    assert not storage.feed_path.exists()


# ------------------------------------------------------------------ refresh


async def test_a_refresh_caches_the_feed_and_publishes_it(
    storage: Storage, year: YearData
) -> None:
    """A refresh publishes the network feed as version 2 and caches its raw bytes."""
    conference = await loaded(storage, year)
    bundled = conference.data

    await conference.refresh(storage, year, transport=serving(NETWORK_FEED))

    assert conference.source == "network"
    assert conference.data is not bundled
    assert title(conference.data) == "Renamed on the server"
    assert conference.fetched_at == NOW
    assert conference.version == 2
    assert not conference.refreshing
    assert conference.problem is None
    assert storage.feed_path.read_bytes() == NETWORK_FEED  # raw bytes, unchanged


async def test_the_next_start_publishes_what_the_refresh_cached(
    storage: Storage, year: YearData
) -> None:
    """The next start publishes, from the cache, the feed the last refresh fetched."""
    first_run = await loaded(storage, year)
    await first_run.refresh(storage, year, transport=serving(NETWORK_FEED))

    next_run = await loaded(storage, year)

    assert next_run.source == "cache"
    assert title(next_run.data) == "Renamed on the server"


async def test_two_concurrent_refreshes_make_one_request(
    storage: Storage, year: YearData
) -> None:
    """Concurrent refreshes share one task: one request and one publish."""
    conference = await loaded(storage, year)
    feed = HeldFeed()

    first = asyncio.create_task(
        conference.refresh(storage, year, transport=feed.transport)
    )
    second = asyncio.create_task(
        conference.refresh(storage, year, transport=feed.transport)
    )
    await feed.arrived.wait()
    assert conference.start_refresh(storage, year, transport=feed.transport) is (
        conference.start_refresh(storage, year, transport=feed.transport)
    )
    feed.release()
    await asyncio.gather(first, second)

    assert feed.requests == 1
    assert conference.source == "network"
    assert conference.version == 2  # one publish


async def test_a_refresh_after_the_last_one_ended_makes_a_new_request(
    storage: Storage, year: YearData
) -> None:
    """A later refresh makes a new request; the same feed is not published again."""
    conference = await loaded(storage, year)
    feed = HeldFeed()
    feed.release()

    await conference.refresh(storage, year, transport=feed.transport)
    await conference.refresh(storage, year, transport=feed.transport)

    assert feed.requests == 2
    assert conference.version == 2  # the second brought the same feed (D-224)


async def test_refreshing_is_set_while_the_request_is_in_flight(
    storage: Storage, year: YearData
) -> None:
    """``refreshing`` is True while the request is in flight, and False after it."""
    conference = await loaded(storage, year)
    feed = HeldFeed()

    task = conference.start_refresh(storage, year, transport=feed.transport)
    await feed.arrived.wait()
    assert conference.refreshing
    feed.release()
    await task

    assert not conference.refreshing


async def test_cancelling_one_caller_leaves_the_shared_refresh_running(
    storage: Storage, year: YearData
) -> None:
    """Cancelling one caller of a shared refresh leaves it running for the other."""
    conference = await loaded(storage, year)
    feed = HeldFeed()

    leaving = asyncio.create_task(
        conference.refresh(storage, year, transport=feed.transport)
    )
    staying = asyncio.create_task(
        conference.refresh(storage, year, transport=feed.transport)
    )
    await feed.arrived.wait()
    leaving.cancel()
    with pytest.raises(asyncio.CancelledError):
        await leaving
    feed.release()
    await staying

    assert feed.requests == 1
    assert conference.source == "network"


@pytest.mark.parametrize(
    ("transport", "status"),
    [(make, status) for _, make, status in FAILURES],
    ids=[name for name, _, _ in FAILURES],
)
async def test_a_failed_refresh_keeps_the_data_and_the_cache_and_says_why(
    storage: Storage,
    year: YearData,
    transport: Callable[[], httpx.MockTransport],
    status: Status,
) -> None:
    """A failed refresh keeps the data and the cache; its problem gives the status."""
    assert await storage.write_feed(CACHED_FEED)
    conference = await loaded(storage, year)
    before = (conference.data, conference.source, conference.fetched_at)

    await conference.refresh(storage, year, transport=transport())

    assert (conference.data, conference.source, conference.fetched_at) == before
    assert conference.version == 1
    assert not conference.refreshing
    assert conference.problem == ("offline" if status == "offline" else "server")
    assert conference.status(year.conference) == status
    assert storage.feed_path.read_bytes() == CACHED_FEED


async def test_a_good_refresh_clears_the_last_problem(
    storage: Storage, year: YearData
) -> None:
    """A good refresh after a failed one clears the problem: the status is ``fresh``."""
    conference = await loaded(storage, year)
    await conference.refresh(
        storage, year, transport=failing(httpx.ConnectError("offline"))
    )
    assert conference.problem == "offline"

    await conference.refresh(storage, year, transport=serving(NETWORK_FEED))

    assert conference.problem is None
    assert conference.status(year.conference) == "fresh"


async def test_a_feed_that_cannot_be_cached_is_still_published(
    tmp_path: Path, year: YearData
) -> None:
    """A feed whose cache write fails is still published for the session."""
    storage = Storage(prefs=MemoryPrefs(), directory=tmp_path / "gone", year=2026)
    conference = await loaded(storage, year)

    await conference.refresh(storage, year, transport=serving(NETWORK_FEED))

    # D-120: the parsed data is right for the session, though it could not be saved.
    assert conference.source == "network"
    assert title(conference.data) == "Renamed on the server"
    assert not storage.feed_path.exists()


async def test_a_publish_notifies_subscribers_and_the_task_does_not(
    storage: Storage, year: YearData
) -> None:
    """Loading and refreshing notify subscribers of their fields, never of ``_task``."""
    conference = Conference()
    assert isinstance(conference, ft.Observable)
    changes: list[str | None] = []

    def listener(_sender: object, name: str | None) -> None:
        changes.append(name)

    conference.subscribe(listener)
    await conference.load_local(storage, year)
    assert {"data", "source", "fetched_at", "version"} <= set(changes)

    changes.clear()
    await conference.refresh(storage, year, transport=serving(NETWORK_FEED))
    assert changes[0] == "refreshing"
    assert "_task" not in changes
    assert changes[-1] == "refreshing"  # cleared last, after the publish
