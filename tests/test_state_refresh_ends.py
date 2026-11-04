"""Tests for how a Conference store refresh ends: the same feed again, a closed session, a bug.

The feeds, transports and fixtures are `tests/feed_store.py`'s.
"""

import asyncio
import logging
import os
from datetime import UTC, datetime, timedelta

import flet as ft
import httpx
import pytest

from pycon_us import clock
from pycon_us.config import YearData
from pycon_us.core.models import ConferenceData
from pycon_us.services import api
from pycon_us.services.storage import Storage
from tests import feed_store
from tests.feed_store import (
    CACHED_FEED,
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


# ------------------------------------------------------------------ the same feed again (D-224)


async def test_a_refresh_that_brings_the_shown_feed_publishes_nothing_new(
    storage: Storage, year: YearData
) -> None:
    """#290: a new version would re-render every list and bring "Now" back for nothing."""
    conference = await loaded(storage, year)
    bundled = conference.data
    changes: list[str | None] = []

    def listener(_sender: object, name: str | None) -> None:
        changes.append(name)

    assert isinstance(conference, ft.Observable)
    conference.subscribe(listener)
    clock.set_test_now(NOW + timedelta(minutes=5))

    await conference.refresh(storage, year, transport=serving(year.read_snapshot().raw))

    assert conference.data is bundled
    assert conference.version == 1
    assert "data" not in changes
    assert "version" not in changes
    # Only the freshness changed: the strip's age, and where the data came from.
    assert conference.source == "network"
    assert conference.fetched_at == NOW + timedelta(minutes=5)
    assert conference.problem is None
    # Cached all the same, so the next start reads the cache, not the snapshot (D-39).
    assert storage.feed_path.read_bytes() == year.read_snapshot().raw


async def test_the_shown_feed_is_not_processed_again(
    storage: Storage, year: YearData, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same bytes give the same data, so the 200 ms of a slow phone are saved."""
    assert await storage.write_feed(CACHED_FEED)
    conference = await loaded(storage, year)

    def unexpected(*_: object) -> ConferenceData:
        raise AssertionError("the shown feed was processed again")

    monkeypatch.setattr("pycon_us.core.feed.process", unexpected)
    await conference.refresh(storage, year, transport=serving(CACHED_FEED))

    assert conference.version == 1
    assert conference.source == "network"
    assert title(conference.data) == "Renamed in the cache"


async def test_after_the_same_feed_a_changed_one_still_publishes(
    storage: Storage, year: YearData
) -> None:
    """D-204: a changed feed brings the Schedule's button back; it needs a version."""
    assert await storage.write_feed(CACHED_FEED)
    conference = await loaded(storage, year)
    await conference.refresh(storage, year, transport=serving(CACHED_FEED))
    assert conference.version == 1

    await conference.refresh(storage, year, transport=serving(NETWORK_FEED))

    assert conference.version == 2
    assert title(conference.data) == "Renamed on the server"
    await conference.refresh(storage, year, transport=serving(NETWORK_FEED))
    assert conference.version == 2  # compared with what is shown now, not the first


async def test_the_same_feed_makes_stale_data_fresh(
    storage: Storage, year: YearData
) -> None:
    """The strip's age: "Updated 3 days ago" goes when the network confirms the data."""
    assert await storage.write_feed(CACHED_FEED)
    # The cache's age is its file's time: pinned, so the test holds on any date (#328).
    os.utime(storage.feed_path, (NOW.timestamp(), NOW.timestamp()))
    conference = await loaded(storage, year)
    clock.set_test_now(NOW + timedelta(days=3))
    assert conference.status(year.conference) == "stale"

    await conference.refresh(storage, year, transport=serving(CACHED_FEED))

    assert conference.age() == timedelta(0)
    assert conference.status(year.conference) == "fresh"
    assert conference.version == 1


async def test_the_same_feed_clears_the_last_problem(
    storage: Storage, year: YearData
) -> None:
    """The same feed after an offline failure clears the problem; no new version."""
    conference = await loaded(storage, year)
    await conference.refresh(
        storage, year, transport=failing(httpx.ConnectError("offline"))
    )
    assert conference.status(year.conference) == "offline"

    await conference.refresh(storage, year, transport=serving(year.read_snapshot().raw))

    assert conference.problem is None
    assert conference.status(year.conference) == "fresh"
    assert conference.version == 1


async def test_the_same_feed_dates_the_cache_for_the_next_start(
    storage: Storage, year: YearData
) -> None:
    """The next start's age is the cache file's mtime (D-145), so the write renews it."""
    assert await storage.write_feed(CACHED_FEED)
    long_ago = datetime(2026, 10, 1, 8, 0, tzinfo=UTC).timestamp()
    os.utime(storage.feed_path, (long_ago, long_ago))
    conference = await loaded(storage, year)

    await conference.refresh(storage, year, transport=serving(CACHED_FEED))

    assert storage.feed_path.stat().st_mtime > long_ago
    assert storage.feed_path.read_bytes() == CACHED_FEED


# ------------------------------------------------------------------ a closed session, a bug


async def test_a_refresh_that_ends_after_its_session_closed_writes_nothing(
    storage: Storage, year: YearData
) -> None:
    """A refresh that ends after its session closed changes neither store nor cache."""
    conference = await loaded(storage, year)
    closed = asyncio.Event()
    feed = HeldFeed()
    task = conference.start_refresh(
        storage, year, transport=feed.transport, closed=closed
    )
    await feed.arrived.wait()
    changes: list[str | None] = []

    def listener(_sender: object, name: str | None) -> None:
        changes.append(name)

    assert isinstance(conference, ft.Observable)
    conference.subscribe(listener)
    closed.set()  # page.on_close: a new session replaced this one (D-147)
    feed.release()
    await task

    # A store write would reach a destroyed session (F30): neither the store nor the
    # cache changes.
    assert changes == []
    assert conference.source == "bundled"
    assert not storage.feed_path.exists()


async def test_a_refresh_that_fails_after_its_session_closed_writes_nothing(
    storage: Storage, year: YearData
) -> None:
    """A refresh that fails after its session closed sets no problem."""
    conference = await loaded(storage, year)
    closed = asyncio.Event()
    closed.set()
    await conference.refresh(
        storage, year, transport=failing(httpx.ConnectError("down")), closed=closed
    )
    assert conference.problem is None


async def test_an_open_session_refreshes_as_before(
    storage: Storage, year: YearData
) -> None:
    """With `closed` given but not set, a refresh publishes and caches as usual."""
    conference = await loaded(storage, year)
    await conference.refresh(
        storage, year, transport=serving(NETWORK_FEED), closed=asyncio.Event()
    )
    assert conference.source == "network"
    assert not conference.refreshing
    assert storage.feed_path.read_bytes() == NETWORK_FEED


async def test_an_unexpected_refresh_error_is_logged_at_once(
    storage: Storage,
    year: YearData,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A bug in a refresh nobody awaits is logged as it ends; nothing is published."""

    async def broken(
        url: str, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> bytes:
        raise RuntimeError("a bug")

    monkeypatch.setattr(api, "fetch_feed", broken)
    conference = await loaded(storage, year)

    with caplog.at_level(logging.ERROR):
        task = conference.start_refresh(storage, year)
        # asyncio.wait never retrieves the error: this is the refresh nobody awaits.
        await asyncio.wait([task])

    # D-71: logged when the refresh ends, not when the finished task is collected.
    assert "Feed refresh failed unexpectedly" in caplog.text
    assert "RuntimeError: a bug" in caplog.text
    assert not conference.refreshing
    assert conference.version == 1


async def test_an_unexpected_refresh_error_reaches_refresh_callers(
    storage: Storage, year: YearData, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bug in a refresh raises to the caller that awaits `refresh()`."""

    async def broken(
        url: str, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> bytes:
        raise RuntimeError("a bug")

    monkeypatch.setattr(api, "fetch_feed", broken)
    conference = await loaded(storage, year)

    with pytest.raises(RuntimeError, match="a bug"):
        await conference.refresh(storage, year)
