"""Tests for when the Schedule jumps and for its "Now" button (#89, D-204, D-224).

The screen renders in `tests/schedule_view.py`'s harness, with the minute tick moved
by hand (`Shown.at`) and each jump recorded (`Shown.jumps`). The jump itself is in
`test_schedule_jump.py`.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import flet as ft
import httpx
import pytest

from pycon_us import clock
from pycon_us.core.feed import process
from pycon_us.core.timeline import NOW_KEY
from pycon_us.memory import ViewMemory
from pycon_us.services.storage import Storage
from pycon_us.state import Conference
from pycon_us.ui import scrolling
from tests import schedule_view
from tests.fakes import MemoryPrefs
from tests.feeds import changed, recorded, settings
from tests.schedule_view import (
    DAYS,
    FRIDAY,
    PACIFIC,
    SATURDAY,
    TALK,
    TEN_30,
    THURSDAY,
    YEAR,
    Shown,
    _list_items,
    _spoken,
    friday_at,
)
from tests.sessions import settle
from tests.trees import texts

now = schedule_view.now
memory = schedule_view.memory
conference = schedule_view.conference
shown = schedule_view.shown


# ------------------------------------------------------------------ the jump's policy (#89)


async def test_swiping_to_today_after_opening_on_another_day_jumps_once(
    shown: Callable[[], Awaitable[Shown]], memory: ViewMemory
) -> None:
    """D-204: today's first display jumps, wherever the Schedule opened."""
    memory.schedule_day = SATURDAY
    schedule = await shown()
    assert schedule.keyed() == []  # Saturday is not today
    await schedule.change_day(FRIDAY)
    assert schedule.jumps == [(TEN_30, "landed")]
    assert memory.jumped_on == FRIDAY
    await schedule.scroll_end(FRIDAY, 2000.0)  # the user scrolls on
    await schedule.change_day(SATURDAY)
    schedule.scrolls.clear()
    await schedule.change_day(FRIDAY)
    assert schedule.keyed() == []  # the second display is put back, not moved
    ((_, kwargs),) = schedule.scrolls
    assert kwargs == {"offset": 2000.0, "duration": 0}


async def test_a_today_tap_from_another_day_is_that_day_s_one_jump(
    shown: Callable[[], Awaitable[Shown]], memory: ViewMemory
) -> None:
    """D-204: a Today tap counts as today's jump: one asked jump, none unasked after."""
    memory.schedule_day = SATURDAY  # jumped_on is None: today has not shown yet
    schedule = await shown()
    await schedule.press_now()
    await schedule.change_day(FRIDAY)  # Flutter's echo of the switch
    await schedule.until(lambda: schedule.jumps and not schedule.jumping)
    assert schedule.jumps == [(TEN_30, "landed")]  # once, not twice
    assert memory.jumped_on == FRIDAY
    await schedule.scroll_end(FRIDAY, 2000.0)
    await schedule.change_day(SATURDAY)
    schedule.scrolls.clear()
    await schedule.change_day(FRIDAY)
    assert schedule.keyed() == []  # the next display is put back, not moved


async def test_a_re_render_as_on_back_from_a_detail_never_jumps(
    shown: Callable[[], Awaitable[Shown]],
) -> None:
    """#313: a detail pushed over the Schedule keeps it mounted; Back re-renders it."""
    schedule = await shown()
    schedule.scrolls.clear()
    renders = len(schedule.retaps)  # one per Schedule render
    schedule.rerender()
    await settle()
    assert len(schedule.retaps) > renders  # it did re-render
    assert schedule.scrolls == []


async def test_a_refresh_never_jumps(
    shown: Callable[[], Awaitable[Shown]], conference: Conference
) -> None:
    """#313: a new feed version re-renders the lists, never moves them."""
    schedule = await shown()
    schedule.scrolls.clear()
    conference.data = process(recorded(2026), settings(2026))
    conference.version += 1
    await settle()
    assert schedule.scrolls == []


async def test_a_filter_change_never_jumps(
    shown: Callable[[], Awaitable[Shown]],
) -> None:
    """#313: the filter re-renders the slots it changed, never moves the list."""
    schedule = await shown()
    schedule.scrolls.clear()
    await schedule.prefs.save(schedule.storage, excluded_tracks=("Charla",))
    await settle()
    assert schedule.scrolls == []


async def test_a_minute_never_jumps_not_even_when_a_slot_starts(
    shown: Callable[[], Awaitable[Shown]],
) -> None:
    """Minute ticks never scroll the list, not even the one at which a slot starts."""
    schedule = await shown()
    schedule.scrolls.clear()
    await schedule.at(friday_at(10, 41))
    await schedule.at(friday_at(11, 0))  # the 11:00 AM slot starts
    assert schedule.scrolls == []


async def test_each_new_today_jumps_once_by_itself(
    shown: Callable[[], Awaitable[Shown]], memory: ViewMemory
) -> None:
    """A new conference day's first display jumps, and a second one that day does not.

    D-204: a process that lives across days jumps on each conference day's first
    display, as after a fake-clock change; never twice the same day.
    """
    memory.jumped_on = THURSDAY
    schedule = await shown()
    assert schedule.jumped() == [TEN_30]
    again = await shown()  # a tab return the same day
    assert again.keyed() == [] and again.jumps == []


async def test_midnight_moves_today_s_dot_and_button_never_the_day_shown(
    shown: Callable[[], Awaitable[Shown]], now: list[datetime | None]
) -> None:
    """At midnight the shown day stays, while the dot and full list move to the new day.

    D-204: the day picked at the first display stays; the new today waits for the user,
    and jumps on its first display.
    """
    now[0] = friday_at(23, 58)
    schedule = await shown()
    assert schedule.tabs.selected_index == DAYS.index(FRIDAY)
    await schedule.scroll_away()
    schedule.forget()
    await schedule.at(datetime(2026, 5, 16, 0, 1, tzinfo=PACIFIC))
    assert schedule.tabs.selected_index == DAYS.index(FRIDAY)  # not moved
    assert _spoken(schedule, DAYS.index(SATURDAY)) == "Saturday, May 16, today"
    assert _spoken(schedule, DAYS.index(FRIDAY)) == "Friday, May 15"
    assert texts(
        cast(ft.Control, cast(ft.FloatingActionButton, schedule.fab).content)
    ) == ["Today"]
    assert schedule.list_of(SATURDAY).cache_extent == scrolling.FULL_LIST_EXTENT
    assert schedule.list_of(FRIDAY).cache_extent is None
    assert schedule.scrolls == []
    await schedule.change_day(SATURDAY)
    assert schedule.jumped() == [NOW_KEY]  # before the day's first slot: the line


# ------------------------------------------------------------------ the button (#89)


async def test_the_button_hides_within_half_a_screen_of_where_the_jump_landed(
    shown: Callable[[], Awaitable[Shown]],
) -> None:
    """D-204: within half a screen (700 px here) of where the jump landed (4,000 px)."""
    schedule = await shown()
    assert schedule.fab is None
    await schedule.scroll_end(FRIDAY, 4300.0)
    assert schedule.fab is None
    await schedule.scroll_end(FRIDAY, 3600.0)
    assert schedule.fab is not None
    await schedule.scroll_end(FRIDAY, 3800.0)  # back near the landing
    assert schedule.fab is None


async def test_the_button_waits_for_the_first_jump_on_a_list_already_in_place(
    shown: Callable[..., Awaitable[Shown]],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The button stays hidden while the first jump tries a list already in place.

    A list already in place sends no scroll end, so the jump answers only after its
    tries: the button must not show for those seconds and then vanish (D-204).
    """
    monkeypatch.setattr(scrolling, "LANDING_S", 0.02)
    asked = asyncio.Event()  # the first ask is held: the jump stays on its way (#270)
    with caplog.at_level(logging.INFO):
        schedule = await shown(moves=False, hold=asked, wait=False, reduce_motion=True)
        await schedule.until(lambda: schedule.keyed())
        assert schedule.jumping == 1
        assert schedule.fab is None  # the jump is on its way
        asked.set()
        await schedule.until(lambda: schedule.jumps)
    assert schedule.jumps == [(TEN_30, "still")]
    assert "did not move" in caplog.text
    assert len(schedule.scrolls) == scrolling.JUMP_TRIES
    assert schedule.fab is None  # "still": the place is in view
    await schedule.scroll_end(FRIDAY, 3000.0)
    assert schedule.fab is not None  # the landing was kept, so a scroll away counts


async def test_a_screen_reader_keeps_the_button_so_a_tap_never_drops_its_focus(
    shown: Callable[..., Awaitable[Shown]],
) -> None:
    """With a screen reader, the button shows after the jump and stays after a tap.

    ux.md §5.2 item 5: a control that hides under the focus sends the reader elsewhere,
    over the announcement of where the list went.
    """
    schedule = await shown(screen_reader=True, announcements=True)
    assert schedule.fab is not None  # after the first display's jump too
    await schedule.press_now()
    assert schedule.announced == ["Friday, May 15, 10:30 AM"]
    assert schedule.fab is not None


async def test_a_tap_after_a_slot_started_since_the_tick_goes_there_and_hides(
    shown: Callable[[], Awaitable[Shown]],
) -> None:
    """A tap after a slot started, before the tick, jumps there and hides the button.

    The tap reads the clock, and so does the render its landing causes: the line moves
    with the jump and the button hides at once, not at the next tick.
    """
    schedule = await shown()
    await schedule.scroll_away()
    clock.set_test_now(friday_at(11, 0))  # the 11:00 AM slot starts before the tick
    schedule.forget()
    await schedule.press_now()
    assert schedule.jumped() == ["slot-2026-05-15T11:00:00-07:00"]
    keys = _list_items(schedule, FRIDAY)
    assert keys[keys.index(NOW_KEY) - 1] == "slot-2026-05-15T11:00:00-07:00"
    assert schedule.fab is None


async def test_a_slot_starting_brings_the_button_back(
    shown: Callable[[], Awaitable[Shown]],
) -> None:
    """The list stays put; what it shows is no longer now, so "Now" offers to move."""
    schedule = await shown()
    assert schedule.fab is None
    await schedule.at(friday_at(10, 59))
    assert schedule.fab is None  # still the 10:30 AM break
    await schedule.at(friday_at(11, 0))
    assert schedule.fab is not None


@pytest.mark.parametrize("change", ["refresh", "filter"])
async def test_a_refresh_or_a_filter_change_brings_the_button_back(
    shown: Callable[[], Awaitable[Shown]], conference: Conference, change: str
) -> None:
    """Either changes the heights above the place, so its offset no longer locates it."""
    schedule = await shown()
    assert schedule.fab is None
    if change == "refresh":
        conference.data = process(recorded(2026), settings(2026))
        conference.version += 1
    else:
        await schedule.prefs.save(schedule.storage, excluded_tracks=("Charla",))
    await settle()
    assert schedule.fab is not None


async def test_a_refresh_that_brings_the_same_feed_re_renders_nothing(
    shown: Callable[[], Awaitable[Shown]], conference: Conference, tmp_path: Path
) -> None:
    """A refresh with the same feed re-renders no slot or row and keeps "Now" hidden.

    #290, D-224: the start refresh over the cache re-rendered every slot, remounting
    each `ScrollKey` box, and brought "Now" back over the now line; a changed feed
    still brings it back (D-204).
    """
    storage = Storage(prefs=MemoryPrefs(), directory=tmp_path, year=2026)
    await conference.load_local(storage, YEAR)  # the snapshot, as a first start
    schedule = await shown()
    assert schedule.jumped() == [TEN_30]
    assert schedule.fab is None
    schedule.rows.clear()
    schedule.slots.clear()

    snapshot = YEAR.read_snapshot().raw
    await conference.refresh(storage, YEAR, transport=_serving(snapshot))
    await settle()

    assert conference.source == "network"  # the refresh did end well
    assert (schedule.slots, schedule.rows) == ([], [])
    assert schedule.fab is None

    await conference.refresh(storage, YEAR, transport=_serving(changed(2026, _rename)))
    await settle()
    assert schedule.fab is not None


def _serving(body: bytes) -> httpx.MockTransport:
    """A transport that answers every request with `body`."""
    return httpx.MockTransport(lambda _: httpx.Response(200, content=body))


def _rename(document: dict[str, Any]) -> None:
    """Rename talk 142 in a feed's JSON: a feed that changed."""
    slot = next(s for s in document["schedule"] if s.get("conf_key") == int(TALK))
    slot["name"] = "Renamed on the server"


async def test_another_day_always_offers_today(
    shown: Callable[[], Awaitable[Shown]],
) -> None:
    """On a day other than today, the button shows and says "Today"."""
    schedule = await shown()
    assert schedule.fab is None
    await schedule.change_day(SATURDAY)
    assert texts(
        cast(ft.Control, cast(ft.FloatingActionButton, schedule.fab).content)
    ) == ["Today"]
