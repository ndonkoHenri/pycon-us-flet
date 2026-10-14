"""A screen's timers held by the test: its sleeps end when the test says so (#270).

A screen that waits a set time (search's debounce, the room's highlight) sleeps through
its module's ``asyncio``. A test that set that time short and then looked at the state
the wait keeps raced it: on a loaded host the timer fired first. ``HeldSleeps`` takes
the place of that one module's ``asyncio`` (never the global module, which the event
loop and Flet use too), so the state lasts until the test ``release()``s the wait,
however slow the host.
"""

import asyncio
from typing import Any


class HeldSleeps:
    """A module's ``asyncio`` whose ``sleep()`` waits for the test instead of a time.

    Install it with ``monkeypatch.setattr(module, "asyncio", HeldSleeps())``. Anything
    else the module takes from ``asyncio`` (``Event``, ``get_running_loop()``) is
    ``asyncio``'s own.
    """

    def __init__(self) -> None:
        self.asked: list[float] = []
        """The delay of each sleep the module started, in order."""
        self._held: list[asyncio.Event] = []

    def __getattr__(self, name: str) -> Any:
        return getattr(asyncio, name)

    async def sleep(self, delay: float) -> None:
        """Record ``delay``, then wait until ``release()``; a cancel ends it as usual."""
        self.asked.append(delay)
        released = asyncio.Event()
        self._held.append(released)
        try:
            await released.wait()
        finally:
            self._held.remove(released)

    @property
    def held(self) -> int:
        """How many sleeps are waiting: a cancelled one counts no more."""
        return len(self._held)

    async def release(self, *, timeout: float = 30.0) -> None:
        """End the one sleep waiting, as if its time had passed.

        It first polls until exactly one sleep waits: the screen may still be on its
        way to it (a render, an effect starting), and one that a newer sleep replaced
        may still be on its way out (cancelled). The deadline is generous: a passing
        test never reaches it.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while len(self._held) != 1:
            assert loop.time() < deadline, f"{len(self._held)} sleeps wait, not one"
            await asyncio.sleep(0.01)
        self._held[0].set()
