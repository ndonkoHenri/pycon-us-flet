"""Tests for the Conference store: cache-first load and single-flight refresh (DATA-01, DATA-02).

The feed is served by an ``httpx.MockTransport``, never the network. The feed cache lives
in a temporary directory, with SharedPreferences replaced by the in-memory fake from
``tests/fakes.py``; time comes from ``clock.set_test_now()``.
"""

import asyncio
import logging
import os
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import flet as ft
import httpx
import pytest

from pycon_us import clock
from pycon_us.config import YearData, load_year
from pycon_us.core.feed import process
from pycon_us.core.models import ConferenceData
from pycon_us.services import api
from pycon_us.services.storage import Storage
from pycon_us.state import Conference, Status
from tests.fakes import MemoryPrefs
from tests.feeds import changed

NOW = datetime(2026, 10, 12, 9, 30, tzinfo=UTC)
TALK = "142"  # a 2026 talk; the variants below rename it


def renamed(name: str) -> bytes:
    """The recorded 2026 feed with talk 142 renamed, so its source shows."""

    def rename(document: dict[str, Any]) -> None:
        slot = next(s for s in document["schedule"] if s.get("conf_key") == int(TALK))
        slot["name"] = name

    return changed(2026, rename)


NETWORK_FEED = renamed("Renamed on the server")
CACHED_FEED = renamed("Renamed in the cache")


@pytest.fixture(autouse=True)
def frozen_clock() -> Iterator[None]:
    clock.set_test_now(NOW)
    yield
    clock.set_test_now(None)


@pytest.fixture(scope="module")
def year() -> YearData:
    return load_year(2026)


@pytest.fixture
def storage(tmp_path: Path) -> Storage:
    return Storage(prefs=MemoryPrefs(), directory=tmp_path, year=2026)


def serving(body: bytes, status: int = 200) -> httpx.MockTransport:
    """A transport that answers the 2026 feed URL with ``body``."""

    def handle(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://us.pycon.org/2026/schedule/conference.json"
        return httpx.Response(status, content=body)

    return httpx.MockTransport(handle)


def failing(error: Exception) -> httpx.MockTransport:
    """A transport whose every request raises ``error``."""

    def handle(request: httpx.Request) -> httpx.Response:
        raise error

    return httpx.MockTransport(handle)


class HeldFeed:
    """A transport that serves ``NETWORK_FEED`` once ``release()`` is called, counting requests."""

    def __init__(self) -> None:
        self.requests = 0
        self.arrived = asyncio.Event()
        self._released = asyncio.Event()
        self.transport = httpx.MockTransport(self._handle)

    def release(self) -> None:
        self._released.set()

    async def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests += 1
        self.arrived.set()
        await self._released.wait()
        return httpx.Response(200, content=NETWORK_FEED)


def title(data: ConferenceData | None) -> str:
    assert data is not None
    return data.sessions[TALK].name


async def loaded(storage: Storage, year: YearData) -> Conference:
    conference = Conference()
    await conference.load_local(storage, year)
    return conference


# ------------------------------------------------------------------ load_local


async def test_without_a_cache_the_bundled_snapshot_is_published(
    storage: Storage, year: YearData
) -> None:
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


async def test_the_feed_cache_wins_over_the_snapshot(
    storage: Storage, year: YearData
) -> None:
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
    assert await storage.write_feed(b'{"schedule": "truncated')

    with caplog.at_level(logging.WARNING):
        conference = await loaded(storage, year)

    assert conference.source == "bundled"
    assert conference.data is not None
    assert not storage.feed_path.exists()
    assert "Deleting the cached feed feed-2026.json: it does not parse: not JSON" in (
        caplog.text
    )


async def test_a_cache_with_the_wrong_structure_is_deleted_too(
    storage: Storage, year: YearData
) -> None:
    assert await storage.write_feed(b'{"schedule": []}')  # no readable slot

    conference = await loaded(storage, year)

    assert conference.source == "bundled"
    assert not storage.feed_path.exists()


# ------------------------------------------------------------------ refresh


async def test_a_refresh_caches_the_feed_and_publishes_it(
    storage: Storage, year: YearData
) -> None:
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
    first_run = await loaded(storage, year)
    await first_run.refresh(storage, year, transport=serving(NETWORK_FEED))

    next_run = await loaded(storage, year)

    assert next_run.source == "cache"
    assert title(next_run.data) == "Renamed on the server"


async def test_two_concurrent_refreshes_make_one_request(
    storage: Storage, year: YearData
) -> None:
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
    conference = await loaded(storage, year)
    feed = HeldFeed()
    feed.release()

    await conference.refresh(storage, year, transport=feed.transport)
    await conference.refresh(storage, year, transport=feed.transport)

    assert feed.requests == 2
    assert conference.version == 3


async def test_refreshing_is_shown_while_the_request_is_in_flight(
    storage: Storage, year: YearData
) -> None:
    conference = await loaded(storage, year)
    feed = HeldFeed()

    task = conference.start_refresh(storage, year, transport=feed.transport)
    await feed.arrived.wait()
    assert conference.refreshing
    assert conference.status(year.conference) == "refreshing"
    feed.release()
    await task

    assert not conference.refreshing
    assert conference.status(year.conference) == "fresh"


async def test_cancelling_one_caller_leaves_the_shared_refresh_running(
    storage: Storage, year: YearData
) -> None:
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


FAILURES: list[tuple[str, Callable[[], httpx.MockTransport], Status]] = [
    ("no connection", lambda: failing(httpx.ConnectError("offline")), "offline"),
    ("timeout", lambda: failing(httpx.ReadTimeout("timed out")), "offline"),
    ("HTTP 500", lambda: serving(b"<h1>Server error</h1>", status=500), "problem"),
    ("HTTP 404", lambda: serving(b"", status=404), "problem"),
    ("an HTML page", lambda: serving(b"<html>Wi-Fi sign-in</html>"), "problem"),
    ("a truncated feed", lambda: serving(NETWORK_FEED[:1000]), "problem"),
    ("no schedule", lambda: serving(b'{"posters": []}'), "problem"),
]


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


async def test_a_refresh_that_ends_after_its_session_closed_writes_nothing(
    storage: Storage, year: YearData
) -> None:
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
    async def broken(
        url: str, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> bytes:
        raise RuntimeError("a bug")

    monkeypatch.setattr(api, "fetch_feed", broken)
    conference = await loaded(storage, year)

    with pytest.raises(RuntimeError, match="a bug"):
        await conference.refresh(storage, year)


# ------------------------------------------------------------------ status and age


def at(day: str, hour: int) -> datetime:
    """An instant in conference time (Pacific) on a 2026 date."""
    local = datetime.fromisoformat(f"{day}T{hour:02}:00:00-07:00")
    return local.astimezone(UTC)


@pytest.mark.parametrize(
    ("now", "age", "status"),
    [
        (at("2026-05-13", 9), timedelta(hours=5, minutes=59), "fresh"),
        (at("2026-05-13", 9), timedelta(hours=6, minutes=1), "stale"),
        (at("2026-05-19", 23), timedelta(hours=7), "stale"),  # the last sprint day
        (at("2026-05-12", 23), timedelta(hours=7), "fresh"),  # the eve of the first day
        (at("2026-05-20", 0), timedelta(hours=7), "fresh"),  # the day after
        (at("2026-10-12", 9), timedelta(hours=23, minutes=59), "fresh"),
        (at("2026-10-12", 9), timedelta(hours=24, minutes=1), "stale"),
    ],
)
def test_data_goes_stale_after_6_hours_on_conference_days_and_24_otherwise(
    machine_tz: str, year: YearData, now: datetime, age: timedelta, status: Status
) -> None:
    clock.set_test_now(now)
    conference = Conference(fetched_at=now - age)

    assert conference.age() == age
    assert conference.status(year.conference) == status


def test_an_age_from_a_clock_set_back_is_zero(year: YearData) -> None:
    conference = Conference(fetched_at=NOW + timedelta(hours=1))

    assert conference.age() == timedelta(0)
    assert conference.status(year.conference) == "fresh"


def test_without_data_the_status_is_stale(year: YearData) -> None:
    conference = Conference()

    assert conference.age() is None
    assert conference.status(year.conference) == "stale"


def test_a_running_refresh_outranks_the_last_problem(year: YearData) -> None:
    conference = Conference(fetched_at=NOW, refreshing=True, problem="offline")

    assert conference.status(year.conference) == "refreshing"


# ------------------------------------------------------------------ automatic refreshes


async def test_an_automatic_refresh_is_due_until_one_has_started(
    storage: Storage, year: YearData
) -> None:
    conference = await loaded(storage, year)
    assert conference.refresh_due()

    task = conference.start_refresh_if_due(
        storage, year, transport=serving(NETWORK_FEED)
    )

    assert task is not None
    assert not conference.refresh_due()  # running, and just started
    await task
    assert conference.source == "network"


@pytest.mark.parametrize(
    ("later", "due"),
    [
        (timedelta(minutes=14, seconds=59), False),
        (timedelta(minutes=15), True),
        (timedelta(hours=3), True),
        (-timedelta(seconds=1), True),  # a clock set back (the fake clock, D-73)
    ],
)
async def test_the_next_one_is_due_15_minutes_after_the_last_began(
    storage: Storage, year: YearData, later: timedelta, due: bool
) -> None:
    conference = await loaded(storage, year)
    await conference.refresh(storage, year, transport=serving(NETWORK_FEED))

    clock.set_test_now(NOW + later)

    assert conference.refresh_due() is due


async def test_a_failed_refresh_also_waits_15_minutes_before_the_next_try(
    storage: Storage, year: YearData
) -> None:
    conference = await loaded(storage, year)
    offline = failing(httpx.ConnectError("offline"))
    await conference.refresh(storage, year, transport=offline)

    # The data is weeks old, yet an offline phone does not retry on every check.
    clock.set_test_now(NOW + timedelta(minutes=10))
    assert conference.start_refresh_if_due(storage, year, transport=offline) is None
    assert conference.problem == "offline"

    clock.set_test_now(NOW + timedelta(minutes=15))
    task = conference.start_refresh_if_due(storage, year, transport=offline)
    assert task is not None
    await task


async def test_a_refresh_on_demand_restarts_the_interval(
    storage: Storage, year: YearData
) -> None:
    conference = await loaded(storage, year)
    await conference.refresh(storage, year, transport=serving(NETWORK_FEED))
    clock.set_test_now(NOW + timedelta(minutes=14))
    await conference.refresh(storage, year, transport=serving(NETWORK_FEED))  # Refresh

    clock.set_test_now(NOW + timedelta(minutes=20))

    assert not conference.refresh_due()


async def test_an_automatic_refresh_shares_the_one_in_flight(
    storage: Storage, year: YearData
) -> None:
    conference = await loaded(storage, year)
    feed = HeldFeed()
    started = conference.start_refresh(storage, year, transport=feed.transport)
    clock.set_test_now(NOW + timedelta(minutes=20))  # a refresh hung for 20 min

    assert conference.refresh_due()
    assert conference.start_refresh_if_due(storage, year) is started
    feed.release()
    await started
    assert feed.requests == 1


@pytest.mark.parametrize(
    ("transport", "status"),
    [(make, status) for _, make, status in FAILURES],
    ids=[name for name, _, _ in FAILURES],
)
async def test_an_automatic_refresh_that_fails_keeps_the_data_and_the_cache(
    storage: Storage,
    year: YearData,
    transport: Callable[[], httpx.MockTransport],
    status: Status,
) -> None:
    assert await storage.write_feed(CACHED_FEED)
    conference = await loaded(storage, year)
    before = (conference.data, conference.source, conference.fetched_at)

    task = conference.start_refresh_if_due(storage, year, transport=transport())
    assert task is not None
    await task

    # Never cleared, and the strip says why (P1 exit criterion 3; D-39, D-146).
    assert (conference.data, conference.source, conference.fetched_at) == before
    assert title(conference.data) == "Renamed in the cache"
    assert storage.feed_path.read_bytes() == CACHED_FEED
    assert conference.status(year.conference) == status
