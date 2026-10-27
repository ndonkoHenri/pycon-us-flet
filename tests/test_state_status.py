"""Tests for the Conference store's status, the data's age and its automatic refreshes.

The feeds, transports and fixtures are ``tests/feed_store.py``'s.
"""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import flet as ft
import httpx
import pytest

from pycon_us import clock
from pycon_us.config import YearData
from pycon_us.feed_refresh import REFRESH_EVERY, Status
from pycon_us.services.storage import Storage
from pycon_us.state import Conference
from tests import feed_store
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
    """Data goes stale after 6 hours on the conference's days and after 24 on others."""
    clock.set_test_now(now)
    conference = Conference(fetched_at=now - age)

    assert conference.age() == age
    assert conference.status(year.conference) == status


def test_an_age_from_a_clock_set_back_is_zero(year: YearData) -> None:
    """A fetch time after now, as from a clock set back, gives age 0 and ``fresh``."""
    conference = Conference(fetched_at=NOW + timedelta(hours=1))

    assert conference.age() == timedelta(0)
    assert conference.status(year.conference) == "fresh"


def test_without_data_the_status_is_stale(year: YearData) -> None:
    """With no fetch time, the age is None and the status ``stale``."""
    conference = Conference()

    assert conference.age() is None
    assert conference.status(year.conference) == "stale"


async def test_a_refresh_the_user_asked_for_outranks_the_last_problem(
    storage: Storage, year: YearData
) -> None:
    """While a refresh the user asked for runs, the status is ``refreshing``."""
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
    """An automatic refresh is due until ``start_refresh_if_due()`` starts one."""
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
    """A refresh is due 15 minutes after the last began, or once the clock goes back."""
    conference = await loaded(storage, year)
    await conference.refresh(storage, year, transport=serving(NETWORK_FEED))

    clock.set_test_now(NOW + later)

    assert conference.refresh_due() is due


async def test_a_failed_refresh_also_waits_15_minutes_before_the_next_try(
    storage: Storage, year: YearData
) -> None:
    """After a failed refresh, the next automatic try waits 15 minutes too."""
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
    """A Refresh on demand restarts the 15 minutes: 6 minutes later, none is due."""
    conference = await loaded(storage, year)
    await conference.refresh(storage, year, transport=serving(NETWORK_FEED))
    clock.set_test_now(NOW + timedelta(minutes=14))
    await conference.refresh(storage, year, transport=serving(NETWORK_FEED))  # Refresh

    clock.set_test_now(NOW + timedelta(minutes=20))

    assert not conference.refresh_due()


async def test_no_automatic_refresh_is_due_while_one_is_in_flight(
    storage: Storage, year: YearData
) -> None:
    """No automatic refresh is due while one is in flight, however long it hangs."""
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
    """A failed automatic refresh keeps the data and the cache; the status says why."""
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
        """Subscribe to ``conference``; its status is read against ``year``'s dates."""
        self.conference = conference
        self.info = year.conference
        self.seen: list[tuple[Status, bool]] = []
        assert isinstance(conference, ft.Observable)
        conference.subscribe(self)

    def __call__(self, _sender: object, _name: str | None) -> None:
        """Record the status and the ``refreshing`` flag at a notification."""
        self.seen.append(
            (self.conference.status(self.info), self.conference.refreshing)
        )


async def test_an_automatic_refresh_over_fresh_data_keeps_the_status_fresh(
    storage: Storage, year: YearData
) -> None:
    """Over fresh data, an automatic refresh shows the bar; the status stays fresh."""
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
    """Over stale data, an automatic refresh says ``stale`` until it ends."""
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
    """The refresh at start, over a stale snapshot, says ``stale`` while it runs."""
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
    """A refresh the user asked for says ``refreshing`` as it starts, then ``fresh``."""
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
    """An automatic refresh that fails offline again notifies only the bar's flag."""
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
    """A Refresh tap joins a quiet refresh's request, saying ``refreshing`` at once."""
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
    """After a Refresh fails offline, the next automatic one says ``offline`` too."""
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
