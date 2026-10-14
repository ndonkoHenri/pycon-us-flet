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
from pycon_us.feed_refresh import REFRESH_EVERY, Status
from pycon_us.services import api
from pycon_us.services.storage import Storage
from pycon_us.state import Conference
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
    """A transport that serves ``NETWORK_FEED`` once ``release()`` is called, counting requests.

    Given an ``error``, it raises that instead once released: a refresh that fails late.
    """

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
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
        if self.error is not None:
            raise self.error
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
    assert conference.version == 2  # the second brought the same feed (D-224)


async def test_refreshing_is_set_while_the_request_is_in_flight(
    storage: Storage, year: YearData
) -> None:
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


async def test_a_refresh_the_user_asked_for_outranks_the_last_problem(
    storage: Storage, year: YearData
) -> None:
    conference = await loaded(storage, year)
    await conference.refresh(
        storage, year, transport=failing(httpx.ConnectError("offline"))
    )
    feed = HeldFeed()

    asked = asyncio.create_task(
        conference.refresh(storage, year, transport=feed.transport)
    )
    await feed.arrived.wait()

    assert conference.problem == "offline"  # until the outcome
    assert conference.status(year.conference) == "refreshing"
    feed.release()
    await asked
    assert conference.status(year.conference) == "fresh"


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


async def test_no_automatic_refresh_is_due_while_one_is_in_flight(
    storage: Storage, year: YearData
) -> None:
    conference = await loaded(storage, year)
    feed = HeldFeed()
    started = conference.start_refresh(storage, year, transport=feed.transport)
    clock.set_test_now(NOW + timedelta(minutes=20))  # a refresh hung for 20 min

    assert not conference.refresh_due()
    assert conference.start_refresh_if_due(storage, year) is None
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


# ------------------------------------------------------------------ quiet automatic refreshes


class StatusLog:
    """Records ``(status(), refreshing)`` at every notification, as the strip renders.

    The test keeps it: an observable holds its listeners weakly.
    """

    def __init__(self, conference: Conference, year: YearData) -> None:
        self.conference = conference
        self.info = year.conference
        self.seen: list[tuple[Status, bool]] = []
        assert isinstance(conference, ft.Observable)
        conference.subscribe(self)

    def __call__(self, _sender: object, _name: str | None) -> None:
        self.seen.append(
            (self.conference.status(self.info), self.conference.refreshing)
        )


async def test_an_automatic_refresh_over_fresh_data_keeps_the_status_fresh(
    storage: Storage, year: YearData
) -> None:
    conference = await loaded(storage, year)
    await conference.refresh(storage, year, transport=serving(NETWORK_FEED))
    clock.set_test_now(NOW + REFRESH_EVERY)  # due, and the data is still fresh
    log = StatusLog(conference, year)
    feed = HeldFeed()

    task = conference.start_refresh_if_due(storage, year, transport=feed.transport)
    assert task is not None
    await feed.arrived.wait()
    assert conference.refreshing  # the bar's flag (D-181)
    assert conference.status(year.conference) == "fresh"  # so the strip stays hidden
    feed.release()
    await task

    assert ("fresh", True) in log.seen
    assert {status for status, _ in log.seen} == {"fresh"}  # it never said "refreshing"


async def test_an_automatic_refresh_over_stale_data_keeps_saying_stale_until_it_ends(
    storage: Storage, year: YearData
) -> None:
    conference = await loaded(storage, year)
    await conference.refresh(storage, year, transport=serving(NETWORK_FEED))
    clock.set_test_now(NOW + timedelta(hours=25))  # not a conference day: over 24 h
    assert conference.status(year.conference) == "stale"
    log = StatusLog(conference, year)
    feed = HeldFeed()

    task = conference.start_refresh_if_due(storage, year, transport=feed.transport)
    assert task is not None
    await feed.arrived.wait()
    assert conference.status(year.conference) == "stale"
    feed.release()
    await task

    assert conference.status(year.conference) == "fresh"
    assert "refreshing" not in {status for status, _ in log.seen}
    assert log.seen[0] == ("stale", True)  # the bar starts over the stale line


async def test_the_start_refresh_is_quiet_too(storage: Storage, year: YearData) -> None:
    conference = await loaded(storage, year)
    clock.set_test_now(NOW + timedelta(days=3))  # the bundled snapshot is stale
    feed = HeldFeed()

    # bootstrap()'s call, over the bundled snapshot on a first start.
    task = conference.start_refresh(storage, year, transport=feed.transport)
    await feed.arrived.wait()

    assert conference.refreshing
    assert conference.status(year.conference) == "stale"  # "Updated 3 days ago"
    feed.release()
    await task
    assert conference.status(year.conference) == "fresh"


async def test_a_refresh_the_user_asked_for_says_refreshing_until_it_ends(
    storage: Storage, year: YearData
) -> None:
    conference = await loaded(storage, year)
    clock.set_test_now(NOW + timedelta(days=3))
    log = StatusLog(conference, year)
    feed = HeldFeed()

    asked = asyncio.create_task(
        conference.refresh(storage, year, transport=feed.transport)
    )
    await feed.arrived.wait()

    assert log.seen == [("refreshing", True)]  # announced as it starts
    feed.release()
    await asked
    assert conference.status(year.conference) == "fresh"
    assert log.seen[-1] == ("fresh", False)


async def test_an_automatic_refresh_that_fails_offline_again_changes_no_status(
    storage: Storage, year: YearData
) -> None:
    conference = await loaded(storage, year)
    await conference.refresh(
        storage, year, transport=failing(httpx.ConnectError("offline"))
    )
    clock.set_test_now(NOW + REFRESH_EVERY)
    log = StatusLog(conference, year)
    feed = HeldFeed(error=httpx.ConnectError("still offline"))

    task = conference.start_refresh_if_due(storage, year, transport=feed.transport)
    assert task is not None
    await feed.arrived.wait()
    assert conference.status(year.conference) == "offline"
    feed.release()
    await task

    # Only the bar came and went: `problem` was set to what it was (no notification,
    # F5), so the strip's live region has nothing new to announce.
    assert log.seen == [("offline", True), ("offline", False)]


async def test_refresh_during_a_quiet_refresh_joins_it_and_says_so_at_once(
    storage: Storage, year: YearData
) -> None:
    conference = await loaded(storage, year)
    clock.set_test_now(NOW + timedelta(days=3))
    feed = HeldFeed()
    quiet = conference.start_refresh_if_due(storage, year, transport=feed.transport)
    assert quiet is not None
    await feed.arrived.wait()
    assert conference.status(year.conference) == "stale"
    log = StatusLog(conference, year)

    asked = asyncio.create_task(
        conference.refresh(storage, year, transport=feed.transport)
    )
    await asyncio.sleep(0)  # the tap's handler runs up to its wait

    assert log.seen == [("refreshing", True)]  # the strip changes on the tap
    assert conference._task is quiet  # single flight: the same request
    feed.release()
    await asked
    assert feed.requests == 1
    assert conference.status(year.conference) == "fresh"


async def test_after_a_refresh_the_user_asked_for_the_next_automatic_one_is_quiet(
    storage: Storage, year: YearData
) -> None:
    conference = await loaded(storage, year)
    offline = failing(httpx.ConnectError("offline"))
    await conference.refresh(storage, year, transport=offline)  # Refresh, offline
    clock.set_test_now(NOW + REFRESH_EVERY)
    feed = HeldFeed(error=httpx.ConnectError("still offline"))

    task = conference.start_refresh_if_due(storage, year, transport=feed.transport)
    assert task is not None
    await feed.arrived.wait()

    assert conference.status(year.conference) == "offline"
    feed.release()
    await task


# ------------------------------------------------------------------ the Developer feed URL


def recording(urls: list[str]) -> httpx.MockTransport:
    """A transport that serves ``NETWORK_FEED`` at any URL and records each one."""

    def handle(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        return httpx.Response(200, content=NETWORK_FEED)

    return httpx.MockTransport(handle)


async def test_a_feed_url_set_in_developer_serves_the_next_refresh(
    storage: Storage, year: YearData
) -> None:
    conference = await loaded(storage, year)
    urls: list[str] = []
    conference.set_feed_url("http://127.0.0.1:8000/conference-2026.json")
    await conference.refresh(storage, year, transport=recording(urls))
    conference.set_feed_url(None)  # Reset: the year's feed again, without a restart
    await conference.refresh(storage, year, transport=recording(urls))
    assert urls == [
        "http://127.0.0.1:8000/conference-2026.json",
        "https://us.pycon.org/2026/schedule/conference.json",
    ]
    assert conference.source == "network"


# ------------------------------------------------------------------ reset (D-198)


async def test_reset_shows_the_bundled_snapshot_from_the_year_s_feed(
    storage: Storage, year: YearData
) -> None:
    conference = await loaded(storage, year)
    await conference.refresh(storage, year, transport=serving(NETWORK_FEED))
    conference.set_feed_url("http://127.0.0.1:8000/conference-2026.json")
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
