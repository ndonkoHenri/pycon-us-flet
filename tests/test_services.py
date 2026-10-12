"""Tests for ``Services.run_every``: the foreground-only ticks of D-40 (#82).

The loop runs on the test's event loop with intervals of milliseconds; ``foreground``
and ``closed`` are driven as the lifecycle handler and ``page.on_close`` drive them.
"""

import asyncio
from pathlib import Path

import pytest

from pycon_us.config import load_year
from pycon_us.services import Services
from pycon_us.services.storage import Storage
from pycon_us.state import ViewMemory
from tests.fakes import MemoryPrefs, MemorySemantics

INTERVAL = 0.01
"""Seconds between two ticks in these tests."""


@pytest.fixture
def svc(tmp_path: Path) -> Services:
    storage = Storage(prefs=MemoryPrefs(), directory=tmp_path, year=2026)
    return Services(
        year=load_year(2026),
        storage=storage,
        memory=ViewMemory(),
        semantics=MemorySemantics(),
    )


class Ticks:
    """Counts the calls of ``run_every``'s action, and says when a count is reached."""

    def __init__(self) -> None:
        self.count = 0
        self._reached: dict[int, asyncio.Event] = {}

    def __call__(self) -> None:
        self.count += 1
        if (event := self._reached.get(self.count)) is not None:
            event.set()

    async def reach(self, count: int) -> None:
        if self.count >= count:
            return
        event = self._reached.setdefault(count, asyncio.Event())
        await asyncio.wait_for(event.wait(), timeout=2)


async def stopped(task: asyncio.Task[None]) -> None:
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def test_a_session_starts_in_the_foreground(svc: Services) -> None:
    assert svc.foreground.is_set()
    assert not svc.closed.is_set()


async def test_it_calls_at_once_then_after_each_interval(svc: Services) -> None:
    ticks = Ticks()
    task = asyncio.create_task(svc.run_every(INTERVAL, ticks))
    await asyncio.sleep(0)
    assert ticks.count == 1  # at once: a screen that mounts catches up
    await ticks.reach(3)
    await stopped(task)


async def test_cancelling_its_task_stops_the_calls(svc: Services) -> None:
    ticks = Ticks()
    task = asyncio.create_task(svc.run_every(INTERVAL, ticks))
    await ticks.reach(2)
    await stopped(task)  # what Flet does when the strip unmounts (F2)
    count = ticks.count
    await asyncio.sleep(INTERVAL * 5)
    assert ticks.count == count


async def test_in_the_background_it_waits_and_catches_up_on_resume(
    svc: Services,
) -> None:
    ticks = Ticks()
    task = asyncio.create_task(svc.run_every(INTERVAL, ticks))
    await ticks.reach(1)
    svc.foreground.clear()  # pause
    await asyncio.sleep(INTERVAL * 2)  # the tick in flight ends, then it waits
    count = ticks.count
    await asyncio.sleep(INTERVAL * 5)
    assert ticks.count == count  # nothing in the background (D-40)
    svc.foreground.set()  # resume
    await asyncio.sleep(0)
    assert ticks.count == count + 1  # at once, without waiting an interval
    await stopped(task)


async def test_it_returns_when_the_session_closes(svc: Services) -> None:
    ticks = Ticks()
    task = asyncio.create_task(svc.run_every(60, ticks))
    await ticks.reach(1)
    svc.close()  # D-147: a new session replaced this one
    await asyncio.wait_for(task, timeout=1)  # no 60 s wait
    assert ticks.count == 1


async def test_a_session_closed_in_the_background_ends_its_waiting_loop(
    svc: Services,
) -> None:
    ticks = Ticks()
    svc.foreground.clear()
    task = asyncio.create_task(svc.run_every(INTERVAL, ticks))
    await asyncio.sleep(INTERVAL * 2)
    svc.close()  # replaced while paused: it would never resume
    await asyncio.wait_for(task, timeout=1)
    assert ticks.count == 0
