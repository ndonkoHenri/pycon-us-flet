"""Tests for the Schedule keeping each day's place across a text-size change (D-331, #337).

The Schedule renders in ``tests/schedule_view.py``'s harness: ``ListView.scroll_to`` is
recorded and a keyed scroll answered with a scroll end at 4,000 dp. The device's
reports are dispatched by hand: each slot's height (``size_change`` on its column), the
probe's widths, and scroll starts and ends. Whether the rows really stay in view is a
device check (#337's PR: Android emulator, trials against ``main``). The put-backs'
turns across two layout changes in a row (D-364) are
``tests/test_schedule_place_turns.py``'s, which imports this module's helpers.
"""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import date
from typing import cast

import flet as ft
import pytest

from pycon_us.memory import ViewMemory
from pycon_us.ui import scrolling
from tests import schedule_view
from tests.schedule_view import FRIDAY, SATURDAY, THURSDAY, Shown, inside

# The Schedule's fixtures, shared by name: pytest finds fixtures among a module's names.
now = schedule_view.now
memory = schedule_view.memory
conference = schedule_view.conference
shown = schedule_view.shown

HEIGHT = 300.0
"""Every slot's height in these tests, in dp, before the text grows."""


def _slots(schedule: Shown, day: date) -> list[tuple[str, ft.Column]]:
    """The day's slots in order: each key and the column that reports its height."""
    day_list = schedule.list_of(day)
    anchors = [
        c
        for c in schedule.find(ft.Container)
        if isinstance(c.key, ft.ScrollKey) and inside(c, day_list)
    ]
    found = [
        (str(cast(ft.ScrollKey, a.key).value), cast(ft.Column, a.parent.parent))  # pyright: ignore[reportOptionalMemberAccess]
        for a in anchors
    ]
    return sorted(found, key=lambda pair: pair[0])


async def _report(schedule: Shown, day: date, height: float) -> None:
    """Have every slot of the day report ``height``, as Flutter does after a layout."""
    for _, column in _slots(schedule, day):
        await schedule.event(column, "size_change", {"w": 400.0, "h": height})


def _probe(schedule: Shown) -> tuple[ft.Container, ft.Container]:
    """The probe's two reporting containers: the time's and the screen's."""
    outer = cast(ft.Container, cast(ft.Column, schedule.tabs.content).controls[0])
    text = cast(ft.Row, outer.content).controls[0]
    return cast(ft.Container, text), outer


async def _measure(schedule: Shown, text: float, width: float = 400.0) -> None:
    """Have the probe report the time's width and the screen's."""
    time, screen = _probe(schedule)
    await schedule.event(time, "size_change", {"w": text, "h": 20.0})
    await schedule.event(screen, "size_change", {"w": width, "h": 0.0})


async def _at_saturday_s_fourth_slot(schedule: Shown) -> str:
    """Show Saturday, measured, scrolled by hand 50 dp into its fourth slot.

    Returns:
        That slot's key.
    """
    await schedule.change_day(SATURDAY)
    await _measure(schedule, 40.0)
    await _report(schedule, SATURDAY, HEIGHT)
    await schedule.scroll_end(SATURDAY, 3 * HEIGHT + 50)
    schedule.forget()
    return _slots(schedule, SATURDAY)[3][0]


async def test_a_scroll_end_records_the_slot_at_the_top_and_how_far_in(
    shown: Callable[[], Awaitable[Shown]], memory: ViewMemory
) -> None:
    """From the heights the slots reported: three slots above, 50 dp into the fourth."""
    schedule = await shown()
    key = await _at_saturday_s_fourth_slot(schedule)
    place = memory.schedule_places[SATURDAY]
    assert (place.key, place.into, place.height, place.stale) == (
        key,
        50.0,
        HEIGHT,
        False,
    )


async def test_the_first_measurement_and_an_unchanged_one_move_nothing(
    shown: Callable[[], Awaitable[Shown]],
) -> None:
    """Every screen mounts with a probe: its first report only sets the basis."""
    schedule = await shown()
    await _at_saturday_s_fourth_slot(schedule)
    await _measure(schedule, 40.0)
    assert schedule.scrolls == []


async def test_a_text_size_change_puts_the_shown_day_s_slot_back_as_far_in(
    shown: Callable[[], Awaitable[Shown]], memory: ViewMemory
) -> None:
    """#337's steps: a keyed jump to the slot, then as far into it as its growth says.

    The slots report their new heights after the probe, as Flutter lays the probe out
    first; the distance grows with the slot (50 → 65 dp at 1.3 times the height), from
    the slot's top, one divider above its anchor.
    """
    schedule = await shown()
    key = await _at_saturday_s_fourth_slot(schedule)
    schedule.hold = asyncio.Event()
    time, _ = _probe(schedule)
    put_back = asyncio.ensure_future(
        schedule.session.dispatch_event(time._i, "size_change", {"w": 52.0, "h": 26.0})
    )
    await schedule.until(lambda: schedule.scrolls)
    await _report(schedule, SATURDAY, HEIGHT * 1.3)
    schedule.hold.set()
    await put_back
    await schedule.until(lambda: len(schedule.scrolls) == 2)
    (keyed, offset) = [kwargs for _, kwargs in schedule.scrolls]
    assert keyed["scroll_key"].value == key
    assert keyed["duration"] == 0
    assert offset == {"offset": 4000.0 - 1 + 65.0, "duration": 0}
    assert memory.schedule_offsets[SATURDAY] == 4064.0
    place = memory.schedule_places[SATURDAY]
    assert (place.key, place.into, place.pixels, place.stale) == (
        key,
        65.0,
        4064.0,
        False,
    )


async def test_nothing_is_put_back_while_the_list_scrolls(
    shown: Callable[[], Awaitable[Shown]], memory: ViewMemory
) -> None:
    """A put-back would fight the user's own scroll: the place is forgotten instead."""
    schedule = await shown()
    await _at_saturday_s_fourth_slot(schedule)
    start = {
        "event_type": "start",
        "pixels": 1000.0,
        "min_scroll_extent": 0.0,
        "max_scroll_extent": 20_000.0,
        "viewport_dimension": 700.0,
    }
    await schedule.event(schedule.list_of(SATURDAY), "scroll", start)
    await _measure(schedule, 52.0)
    assert schedule.scrolls == []
    assert SATURDAY not in memory.schedule_places


async def test_another_day_is_built_in_full_and_put_back_by_key_when_it_shows(
    shown: Callable[[], Awaitable[Shown]], memory: ViewMemory
) -> None:
    """A lazy day's slot must be built for the keyed jump (F7): until it is put back."""
    schedule = await shown()
    key = await _at_saturday_s_fourth_slot(schedule)
    await schedule.change_day(THURSDAY)
    assert schedule.list_of(SATURDAY).cache_extent is None
    await _measure(schedule, 52.0)
    assert memory.schedule_places[SATURDAY].stale
    assert schedule.list_of(SATURDAY).cache_extent == scrolling.FULL_LIST_EXTENT
    # An end before the put-back counts nothing: the new heights may be on their way.
    await schedule.scroll_end(SATURDAY, 10.0)
    assert memory.schedule_places[SATURDAY].key == key
    assert memory.schedule_places[SATURDAY].stale
    schedule.forget()
    await schedule.change_day(SATURDAY)
    await schedule.until(lambda: not memory.schedule_places[SATURDAY].stale)
    assert schedule.keyed() == [key]  # not the stale offset
    assert schedule.list_of(SATURDAY).cache_extent is None
    assert schedule.list_of(FRIDAY).cache_extent == scrolling.FULL_LIST_EXTENT


async def test_a_rotation_puts_the_place_back_too(
    shown: Callable[[], Awaitable[Shown]],
) -> None:
    """A new width relays the rows out as a new text size does: the same put-back."""
    schedule = await shown()
    key = await _at_saturday_s_fourth_slot(schedule)
    await _measure(schedule, 40.0, 700.0)
    assert schedule.keyed() == [key]


async def test_a_slot_that_left_the_built_range_is_reached_from_its_old_offset(
    shown: Callable[..., Awaitable[Shown]],
    memory: ViewMemory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Text that shrank can leave the slot out of the built range: its old top is near.

    No keyed jump moves (F7), so the list jumps to the slot's old top and asks again;
    with still no end, the place is forgotten rather than guessed.
    """
    monkeypatch.setattr(scrolling, "LANDING_S", 0.01)  # no end ever comes here
    schedule = await shown(moves=False)
    key = await _at_saturday_s_fourth_slot(schedule)
    await _measure(schedule, 30.0)
    asks = [kwargs for _, kwargs in schedule.scrolls]
    assert asks[0]["scroll_key"].value == key
    assert asks[1] == {"offset": 3 * HEIGHT, "duration": 0}
    assert {a["scroll_key"].value for a in asks[2:]} == {key}
    assert SATURDAY not in memory.schedule_places


async def test_today_s_jump_to_now_drops_a_stale_place_so_later_ends_count(
    shown: Callable[[], Awaitable[Shown]], memory: ViewMemory
) -> None:
    """Codex's #572 review: "Today" from another day supersedes today's put-back.

    Today's place went stale while Saturday showed; the jump to now moves the list
    elsewhere, so a later scroll end records the user's place, not the old one.
    """
    schedule = await shown()  # Friday, today, jumped to now
    await _measure(schedule, 40.0)
    await _report(schedule, FRIDAY, HEIGHT)
    await schedule.scroll_end(FRIDAY, 3 * HEIGHT + 50)
    await schedule.change_day(SATURDAY)
    await _measure(schedule, 52.0)
    assert memory.schedule_places[FRIDAY].stale
    schedule.forget()
    await schedule.press_now()
    await schedule.change_day(FRIDAY)  # Flutter's echo of the switch
    await schedule.until(lambda: schedule.jumps)
    await _report(schedule, FRIDAY, HEIGHT * 1.3)
    await schedule.scroll_end(FRIDAY, 6000.0)
    place = memory.schedule_places[FRIDAY]
    assert (place.pixels, place.stale) == (6000.0, False)
