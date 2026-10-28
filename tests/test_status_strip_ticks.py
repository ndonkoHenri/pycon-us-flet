"""Tests for the status strip's minute tick and ``use_minute()`` (D-200, D-175, D-40).

The strip's body runs outside a renderer, with the fixtures of ``tests/strip.py`` and
``tests/chrome.py``, and ``Services.run_every`` records each loop instead of running
it, so a test moves the clock and calls the tick by hand. The strip's line, layout
and refreshes are ``test_status_strip.py``'s.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import pytest

from pycon_us import clock
from pycon_us.services import Services
from pycon_us.state import Conference
from pycon_us.ui import status_strip
from tests import chrome, strip
from tests.fake_page import FakePage, Hooks
from tests.strip import PACIFIC, Network, render_strip, strip_parts

# The harness's fixtures, under this module's names, where pytest looks them up.
year, svc, page, conference = chrome.year, chrome.svc, chrome.page, chrome.conference
hooks, network = strip.hooks, strip.network


@dataclass
class Clock:
    """``clock.now()`` for a test, moved by hand."""

    now: datetime

    def move(self, delta: timedelta) -> None:
        """Move the clock on by ``delta``."""
        self.now += delta


@pytest.fixture
def moving_clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    """A ``Clock`` at 12:00:30 PM Pacific on May 11, 2026, which ``clock.now`` reads."""
    fake = Clock(datetime(2026, 5, 11, 12, 0, 30, tzinfo=PACIFIC))
    monkeypatch.setattr(clock, "now", lambda: fake.now)
    return fake


@dataclass
class Loops:
    """Stands in for ``Services.run_every``: records each loop instead of running it."""

    started: list[tuple[float, Callable[[], object]]] = field(default_factory=list)

    async def run_every(self, seconds: float, action: Callable[[], object]) -> None:
        """Record the loop's period and action instead of running it.

        A bound method set on the class is not bound again: no ``self`` of Services.
        """
        self.started.append((seconds, action))


@pytest.fixture
def loops(monkeypatch: pytest.MonkeyPatch) -> Loops:
    """A ``Loops`` in place of ``Services.run_every``."""
    fake = Loops()
    monkeypatch.setattr(Services, "run_every", fake.run_every)
    return fake


async def mounted_strip(
    hooks: Hooks, loops: Loops, **kwargs: Any
) -> Callable[[], object]:
    """Render the strip and run its effect as a mount does; return the tick."""
    render_strip(**kwargs)
    setup, _ = hooks.effects[-1]
    await setup()
    ((seconds, tick),) = loops.started
    assert seconds == status_strip.TICK_SECONDS == 60
    return tick


def test_the_ticks_depend_on_auto_refresh_alone(hooks: Hooks, page: FakePage) -> None:
    """The strip's effect re-runs only for ``auto_refresh``, and has no cleanup.

    None is needed: Flet cancels the running loop on unmount (F2, D-387), which
    ``tests/test_flet_effects.py`` pins and ``tests/test_session.py`` sees on a screen.
    """
    render_strip(auto_refresh=True)
    (_, dependencies), cleanup = hooks.effects[-1], hooks.cleanups[-1]
    assert dependencies == [True]
    assert cleanup is None


async def test_a_tick_re_renders_the_strip_only_when_the_minute_changed(
    hooks: Hooks, page: FakePage, loops: Loops, moving_clock: Clock
) -> None:
    """A tick in the render's minute re-renders nothing; a minute later, one does."""
    tick = await mounted_strip(hooks, loops)
    tick()  # at mount: the same minute as the render
    assert hooks.renders == 0
    moving_clock.move(timedelta(seconds=60))
    tick()
    assert hooks.renders == 1


async def test_a_tick_shows_the_strip_once_the_data_turns_stale(
    hooks: Hooks,
    page: FakePage,
    conference: Conference,
    loops: Loops,
    moving_clock: Clock,
) -> None:
    """A tick that ages the feed past a day re-renders the strip, now shown as stale."""
    conference.fetched_at = moving_clock.now - timedelta(
        hours=23, minutes=59, seconds=30
    )
    tick = await mounted_strip(hooks, loops)
    assert render_strip().visible is False
    moving_clock.move(timedelta(seconds=60))
    tick()
    assert hooks.renders == 1
    strip = render_strip()  # the re-render the tick asked for
    text, _, _ = strip_parts(strip)
    assert strip.visible is True
    assert text.value == "Updated 1 day ago"


async def test_use_minute_re_renders_its_component_only_when_the_minute_changes(
    hooks: Hooks, page: FakePage, loops: Loops, moving_clock: Clock
) -> None:
    """The Map's "Now:" lines keep up on the strip's loop (#100, D-175)."""
    assert status_strip.use_minute() == status_strip.current_minute()
    (setup, dependencies), cleanup = hooks.effects[-1], hooks.cleanups[-1]
    assert dependencies == []
    assert cleanup is None  # Flet cancels the loop on unmount (F2)
    await setup()
    ((seconds, tick),) = loops.started
    assert seconds == status_strip.TICK_SECONDS
    tick()  # at mount: the same minute as the render
    assert hooks.renders == 0
    moving_clock.move(timedelta(seconds=60))
    tick()
    assert hooks.renders == 1
    assert hooks.state == status_strip.current_minute()


async def test_on_now_and_schedule_a_tick_starts_a_refresh_when_one_is_due(
    hooks: Hooks,
    page: FakePage,
    conference: Conference,
    loops: Loops,
    moving_clock: Clock,
    network: Network,
) -> None:
    """With ``auto_refresh``, a tick refreshes at once, then only 15 minutes on."""
    tick = await mounted_strip(hooks, loops, auto_refresh=True)
    tick()  # nothing has started in this session yet
    first = conference._task
    assert first is not None
    network.released.set()
    await first
    assert network.requests == 1

    moving_clock.move(timedelta(minutes=14, seconds=59))
    tick()
    assert conference._task is first  # not yet due

    moving_clock.move(timedelta(seconds=1))  # 15 min after it began (D-40)
    tick()
    second = conference._task
    assert second is not None and second is not first
    await second
    assert network.requests == 2


async def test_elsewhere_a_tick_never_refreshes(
    hooks: Hooks,
    page: FakePage,
    conference: Conference,
    loops: Loops,
    moving_clock: Clock,
) -> None:
    """Without ``auto_refresh``, ticks over two hours start no refresh."""
    tick = await mounted_strip(hooks, loops)  # My schedule's strip
    tick()
    moving_clock.move(timedelta(hours=2))
    tick()
    assert conference._task is None


# Now, the Schedule and My schedule each check their own strip (test_now_card.py,
# test_schedule.py, test_my_schedule.py; D-40).
