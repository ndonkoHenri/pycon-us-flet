"""Tests for the Conference store's Developer feed URL and its reset (D-198).

The feeds, transports and fixtures are ``tests/feed_store.py``'s.
"""

import asyncio

import httpx
import pytest

from pycon_us.config import YearData
from pycon_us.core.change_batches import Batch
from pycon_us.services import changes_file
from pycon_us.services.storage import Storage
from pycon_us.state import Conference
from tests import feed_store
from tests.fakes import QueuedWrite
from tests.feed_store import (
    NETWORK_FEED,
    NOW,
    HeldFeed,
    loaded,
    serving,
)

frozen_clock, year, storage = (
    feed_store.frozen_clock,
    feed_store.year,
    feed_store.storage,
)


# ------------------------------------------------------------------ the Developer feed URL


DEV_FEED = "http://127.0.0.1:8000/conference-2026.json"
OTHER_DEV_FEED = "http://127.0.0.1:8000/conference-2025.json"


def serving_any(body: bytes) -> httpx.MockTransport:
    """A transport that answers any URL with ``body``."""
    return httpx.MockTransport(lambda request: httpx.Response(200, content=body))


def recording(urls: list[str]) -> httpx.MockTransport:
    """A transport that serves ``NETWORK_FEED`` at any URL and records each one."""

    def handle(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        return httpx.Response(200, content=NETWORK_FEED)

    return httpx.MockTransport(handle)


async def test_a_feed_url_set_in_developer_serves_the_next_refresh(
    storage: Storage, year: YearData
) -> None:
    """A Developer feed URL serves the next refresh; clearing it restores the year's."""
    conference = await loaded(storage, year)
    urls: list[str] = []
    await conference.set_feed_url(DEV_FEED, storage)
    await conference.refresh(storage, year, transport=recording(urls))
    # Reset: the year's feed again, without a restart
    await conference.set_feed_url(None, storage)
    await conference.refresh(storage, year, transport=recording(urls))
    assert urls == [DEV_FEED, "https://us.pycon.org/2026/schedule/conference.json"]
    assert conference.source == "network"


async def fill(storage: Storage) -> None:
    """Write a cache and a change log, as refreshes from the feed URL in effect would."""
    await storage.write_feed(NETWORK_FEED)
    await changes_file.write_batches(storage, [Batch(NOW, ())])


def files(storage: Storage) -> tuple[bool, bool]:
    """Whether the cache and the change log are there."""
    return storage.feed_path.exists(), changes_file.changes_path(storage).exists()


@pytest.mark.parametrize(
    ("was", "url"),
    [(None, DEV_FEED), (DEV_FEED, OTHER_DEV_FEED), (DEV_FEED, None)],
    ids=["to a feed URL", "to another", "back to the year's"],
)
async def test_any_feed_url_change_after_the_load_deletes_the_cache_and_the_log(
    storage: Storage, year: YearData, was: str | None, url: str | None
) -> None:
    """Once the feed has loaded, every feed URL change deletes the cache and the log.

    Both hold the old URL's feed: an offline start would publish it, and the next diff
    or the log would mix two feeds (D-255, amending D-244).
    """
    conference = await loaded(storage, year)
    await conference.set_feed_url(was, storage)
    await fill(storage)
    await conference.set_feed_url(was, storage)
    assert files(storage) == (True, True)  # the same URL: no change
    await conference.set_feed_url(url, storage)
    assert files(storage) == (False, False)


async def test_the_start_s_restore_of_a_stored_feed_url_deletes_nothing(
    storage: Storage, year: YearData
) -> None:
    """At a start the stored URL is set before the load, which keeps both files.

    ``bootstrap()`` restores it, then loads the cache, which is that URL's (D-255).
    """
    await fill(storage)
    conference = Conference()
    await conference.set_feed_url(DEV_FEED, storage)
    assert files(storage) == (True, True)
    await conference.load_local(storage, year)
    assert conference.source == "cache"


async def test_a_feed_url_left_while_a_log_write_is_queued_leaves_no_log(
    storage: Storage, year: YearData, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A feed URL left while a change log write waits for its lock leaves no log.

    The deletion waits for every write asked for before it, of either file, a cancelled
    caller's too, so the old URL's batches cannot land after it (D-244's order, D-255).
    """
    conference = await loaded(storage, year)
    held = QueuedWrite(monkeypatch)
    writing = asyncio.create_task(changes_file.write_batches(storage, [Batch(NOW, ())]))
    await held.queued()
    writing.cancel()  # its caller gone: the write, a task of its own, still lands
    leaving = asyncio.create_task(conference.set_feed_url(DEV_FEED, storage))
    done, _ = await asyncio.wait({leaving}, timeout=0.1)
    held.release()
    await leaving
    assert not done  # the deletion waited for the write
    assert not changes_file.changes_path(storage).exists()
    assert writing.cancelled()


@pytest.mark.parametrize("then", [None, OTHER_DEV_FEED])
async def test_a_refresh_from_a_feed_url_left_while_it_runs_writes_nothing(
    storage: Storage, year: YearData, then: str | None
) -> None:
    """A refresh from a feed URL left while it runs neither caches nor publishes.

    D-187's race: the test feed came back in the cache after Reset (D-244).
    """
    conference = await loaded(storage, year)
    await conference.set_feed_url(DEV_FEED, storage)
    held = HeldFeed()
    running = conference.start_refresh(storage, year, transport=held.transport)
    await held.arrived.wait()
    await conference.set_feed_url(then, storage)
    held.release()
    await running
    assert not storage.feed_path.exists()
    assert (conference.source, conference.version) == ("bundled", 1)  # not published
    assert conference.problem is None
    assert conference.refreshing is False


async def test_a_refresh_whose_feed_url_is_left_during_its_cache_write_publishes_nothing(
    storage: Storage, year: YearData, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A feed URL left as the cache write lands: the file goes, nothing is published."""
    conference = await loaded(storage, year)
    await conference.set_feed_url(DEV_FEED, storage)
    write = Storage.write_feed

    async def write_then_reset(self: Storage, raw: bytes) -> bool:
        written = await write(self, raw)
        await conference.set_feed_url(None, self)  # Reset, as the write lands
        return written

    monkeypatch.setattr(Storage, "write_feed", write_then_reset)  # frozen: the class
    await conference.refresh(storage, year, transport=serving_any(NETWORK_FEED))
    assert not storage.feed_path.exists()  # deleted after the write
    assert (conference.source, conference.version) == ("bundled", 1)


async def test_a_feed_url_left_before_the_write_takes_its_turn_keeps_no_cache(
    storage: Storage, year: YearData, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A feed URL left while the cache write waits for its lock leaves no cache.

    The write's worker is queued for the writers' lock when the URL is left: the
    deletion asked for after it must not take the lock first (D-244).
    """
    conference = await loaded(storage, year)
    await conference.set_feed_url(DEV_FEED, storage)
    held = QueuedWrite(monkeypatch)
    running = conference.start_refresh(
        storage, year, transport=serving_any(NETWORK_FEED)
    )
    await held.queued()
    leaving = asyncio.create_task(conference.set_feed_url(None, storage))
    done, _ = await asyncio.wait({leaving}, timeout=0.1)
    held.release()
    await asyncio.gather(leaving, running)
    assert not done  # the deletion waited for the write
    assert not storage.feed_path.exists()
    assert (conference.source, conference.version) == ("bundled", 1)


async def test_reset_during_a_queued_cache_write_keeps_no_cache(
    storage: Storage, year: YearData, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reset during a queued cache write cancels the refresh and leaves no cache.

    Reset cancels the refresh, but not its worker thread, which writes on (D-120).
    """
    conference = await loaded(storage, year)
    await conference.set_feed_url(DEV_FEED, storage)
    held = QueuedWrite(monkeypatch)
    running = conference.start_refresh(
        storage, year, transport=serving_any(NETWORK_FEED)
    )
    await held.queued()
    resetting = asyncio.create_task(conference.reset(storage, year))
    done, _ = await asyncio.wait({resetting}, timeout=0.1)
    held.release()
    assert await resetting is True
    assert not done
    assert running.cancelled()
    assert not storage.feed_path.exists()


# ------------------------------------------------------------------ reset (D-198)


async def test_reset_shows_the_bundled_snapshot_from_the_year_s_feed(
    storage: Storage, year: YearData
) -> None:
    """Reset deletes the cache, drops the feed URL and publishes the snapshot as new."""
    conference = await loaded(storage, year)
    await conference.refresh(storage, year, transport=serving(NETWORK_FEED))
    await conference.set_feed_url(DEV_FEED, storage)
    version = conference.version
    assert await conference.reset(storage, year) is True
    assert not storage.feed_path.exists()
    assert conference.source == "bundled"
    assert conference.fetched_at == year.read_snapshot().captured_at
    assert conference.version == version + 1  # every screen shows it at once
    assert conference._feed_url is None
    assert conference.refresh_due()  # as at a start: the next refresh is due


async def test_reset_cancels_a_running_refresh_before_it_writes(
    storage: Storage, year: YearData
) -> None:
    """Reset cancels a running refresh, which then neither caches nor publishes."""
    conference = await loaded(storage, year)
    held = HeldFeed()
    running = conference.start_refresh(storage, year, transport=held.transport)
    await held.arrived.wait()
    async with asyncio.timeout(5):  # without the cancel it waits for the feed forever
        await conference.reset(storage, year)
    assert running.cancelled()
    assert conference.refreshing is False  # its `finally` ran before the reset ended
    held.release()
    await asyncio.sleep(0.05)
    assert not storage.feed_path.exists()
    assert conference.source == "bundled"
