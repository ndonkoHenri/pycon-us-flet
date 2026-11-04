"""Tests for `Services`: `run_every`'s ticks (D-40, #82) and `permissions` (#446).

The loop runs on the test's event loop with intervals of milliseconds; `foreground`
and `closed` are driven as the lifecycle handler and `page.on_close` drive them.
"""

import asyncio
from dataclasses import replace
from pathlib import Path

import pytest

from pycon_us import capabilities
from pycon_us.config import load_year
from pycon_us.memory import ViewMemory
from pycon_us.services import Services
from pycon_us.services.storage import Storage
from pycon_us.ui.scan_feedback import keep_awake
from tests.fakes import (
    MemoryClipboard,
    MemoryHaptics,
    MemoryLauncher,
    MemoryPrefs,
    MemorySemantics,
    MemoryWakelock,
)

INTERVAL = 0.01
"""Seconds between two ticks in these tests."""


def memory_services(tmp_path: Path) -> Services:
    """Return a session's services with the memory fakes, storing under `tmp_path`."""
    storage = Storage(prefs=MemoryPrefs(), directory=tmp_path, year=2026)
    return Services(
        year=load_year(2026),
        storage=storage,
        memory=ViewMemory(),
        semantics=MemorySemantics(),
        haptics=MemoryHaptics(),
        launcher=MemoryLauncher(),
        clipboard=MemoryClipboard(),
    )


@pytest.fixture
def svc(tmp_path: Path) -> Services:
    """Return a session's services with the memory fakes, storing under `tmp_path`."""
    return memory_services(tmp_path)


class Ticks:
    """Counts the calls of `run_every`'s action, and says when a count is reached."""

    def __init__(self) -> None:
        """Start at no call, with no count awaited."""
        self.count = 0
        self._reached: dict[int, asyncio.Event] = {}

    def __call__(self) -> None:
        """Count one call, and wake whoever waits for this count."""
        self.count += 1
        if (event := self._reached.get(self.count)) is not None:
            event.set()

    async def reach(self, count: int) -> None:
        """Wait until the action has been called `count` times."""
        if self.count >= count:
            return
        event = self._reached.setdefault(count, asyncio.Event())
        # Generous: a passing loop gets there in a few intervals, a loaded host later.
        await asyncio.wait_for(event.wait(), timeout=30)


async def stopped(task: asyncio.Task[None]) -> None:
    """Cancel `task` and wait until it has ended cancelled."""
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def test_a_session_starts_in_the_foreground(svc: Services) -> None:
    """New services start in the foreground, not in the background, and not closed."""
    assert svc.foreground.is_set()
    assert not svc.background.is_set()
    assert not svc.closed.is_set()


async def test_a_closed_session_ends_the_wake_lock_s_loop(svc: Services) -> None:
    """`keep_awake()` lets go and returns once the session closes (D-147, #724)."""
    lock = MemoryWakelock()
    svc = replace(svc, wakelock=lock)
    task = asyncio.create_task(keep_awake(svc))
    await asyncio.sleep(0)
    assert lock.enabled
    svc.close()  # wakes its wait for the background
    await asyncio.wait_for(task, timeout=30)  # generous: it returns at once
    assert lock.calls == ["enable", "disable"]


async def test_it_calls_at_once_then_after_each_interval(svc: Services) -> None:
    """The action runs once at the start, then again after each interval."""
    ticks = Ticks()
    task = asyncio.create_task(svc.run_every(INTERVAL, ticks))
    await asyncio.sleep(0)
    assert ticks.count == 1  # at once: a screen that mounts catches up
    await ticks.reach(3)
    await stopped(task)


async def test_cancelling_its_task_stops_the_calls(svc: Services) -> None:
    """Once its task is cancelled, the action is not called again."""
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
    """In the background the action waits, and on resume it runs at once."""
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
    """Closing the session ends the loop at once, without waiting out the interval."""
    ticks = Ticks()
    task = asyncio.create_task(svc.run_every(60, ticks))
    await ticks.reach(1)
    svc.close()  # D-147: a new session replaced this one
    await asyncio.wait_for(task, timeout=30)  # no 60 s wait: it returns at once
    assert ticks.count == 1


async def test_a_session_closed_in_the_background_ends_its_waiting_loop(
    svc: Services,
) -> None:
    """Closing a session paused in the background ends its loop with no call made."""
    ticks = Ticks()
    svc.foreground.clear()
    task = asyncio.create_task(svc.run_every(INTERVAL, ticks))
    await asyncio.sleep(INTERVAL * 2)
    svc.close()  # replaced while paused: it would never resume
    await asyncio.wait_for(task, timeout=30)  # generous: it returns at once
    assert ticks.count == 0


def test_permissions_is_none_when_the_build_lacks_the_extension(svc: Services) -> None:
    """Outside a packaged build, as in the companion app, no permission service exists."""
    assert svc.permissions is None


def test_permissions_is_the_extension_when_the_build_has_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """With `capabilities.PERMISSIONS`, the session gets a `PermissionHandler` (D-61)."""
    from flet_permission_handler import PermissionHandler

    monkeypatch.setattr(capabilities, "PERMISSIONS", True)
    assert isinstance(memory_services(tmp_path).permissions, PermissionHandler)
