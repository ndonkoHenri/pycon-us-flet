"""Tests for ``tests/timers.py``: held sleeps end when the test releases them (#270)."""

import asyncio

import pytest

from tests.timers import HeldSleeps


async def test_a_held_sleep_lasts_until_it_is_released() -> None:
    """A held sleep waits past its delay and ends when the test releases it."""
    sleeps = HeldSleeps()
    sleeping = asyncio.create_task(sleeps.sleep(0.001))
    await asyncio.sleep(0.05)  # many times its delay: still waiting
    assert not sleeping.done()
    assert sleeps.asked == [0.001]
    await sleeps.release()
    await sleeping
    assert sleeps.held == 0


async def test_a_cancelled_sleep_is_no_longer_held() -> None:
    """A keystroke restarts the debounce: Flet cancels the wait in progress (F2)."""
    sleeps = HeldSleeps()
    first = asyncio.create_task(sleeps.sleep(1))
    second = asyncio.create_task(sleeps.sleep(1))
    await asyncio.sleep(0)
    assert sleeps.held == 2
    first.cancel()
    await sleeps.release()  # once the cancelled one is out: the other
    await second
    assert first.cancelled()
    assert sleeps.asked == [1, 1]


async def test_release_fails_when_no_sleep_waits() -> None:
    """``release`` fails its assertion when no sleep waits before the timeout."""
    with pytest.raises(AssertionError, match="0 sleeps wait"):
        await HeldSleeps().release(timeout=0.05)


def test_anything_else_is_asyncio_s_own() -> None:
    """``HeldSleeps`` passes asyncio's other names, such as ``Event``, through."""
    sleeps = HeldSleeps()
    assert sleeps.Event is asyncio.Event
    assert sleeps.get_running_loop is asyncio.get_running_loop
