"""Tests for the Schedule keeping each day's place across a filter change (D-371, #333).

The Schedule renders in ``tests/test_schedule.py``'s harness, with
``tests/test_schedule_place.py``'s helpers: a keyed scroll is answered with a scroll end
at 4,000 dp, an offset jump with one where it was asked. Saturday's first slots in the
2026 feed, with the default filter (Open space hidden): 8:00 (notices, a break and
lightning talks), 9:00, 9:25 (the keynote), 10:05 (a break), 10:30. Whether the rows
really stay in view is a device check (#333's PR).
"""

from collections.abc import Awaitable, Callable

import pytest

from pycon_us.core.timeline import NOW_KEY, Slot
from pycon_us.memory import ViewMemory
from pycon_us.screens.schedule_place import unchanged_keys
from pycon_us.ui import scrolling
from tests import test_schedule, test_schedule_place
from tests.feeds import processed
from tests.test_schedule import SATURDAY, THURSDAY, Shown
from tests.test_schedule_place import HEIGHT, _report, _slots

# The Schedule's fixtures, shared by name: pytest finds fixtures among a module's names.
now = test_schedule.now
memory = test_schedule.memory
conference = test_schedule.conference
shown = test_schedule.shown

KEYNOTE = "slot-2026-05-16T09:25:00-07:00"
BREAK = "slot-2026-05-16T10:05:00-07:00"
TALKS = "slot-2026-05-16T10:30:00-07:00"
FIRST = "slot-2026-05-16T08:00:00-07:00"


async def _at_saturday(schedule: Shown, pixels: float) -> None:
    """Show Saturday, its slots measured at ``HEIGHT``, scrolled by hand to ``pixels``."""
    await schedule.change_day(SATURDAY)
    await test_schedule_place._measure(schedule, 40.0)
    await _report(schedule, SATURDAY, HEIGHT)
    await schedule.scroll_end(SATURDAY, pixels)
    schedule.forget()


async def _hide(schedule: Shown, *tracks: str) -> None:
    """Hide ``tracks`` besides Open space, as a chip in the sheet does, and lay it out.

    The slots then report their heights, as Flutter does once it has laid the new
    list out.
    """
    await schedule.prefs.save(schedule.storage, excluded_tracks=("Open Space", *tracks))
    await schedule.settle()
    await _report(schedule, SATURDAY, HEIGHT)


async def test_hiding_a_slot_above_keeps_the_slot_at_the_top_as_far_in(
    shown: Callable[[], Awaitable[Shown]], memory: ViewMemory
) -> None:
    """#333's first step: rows above go, so the same offset would show later rows.

    The 10:05 slot, 50 dp in, has the same rows after the keynote is hidden: a keyed
    jump to it, then as far in, one divider above its anchor.
    """
    schedule = await shown()
    await _at_saturday(schedule, 3 * HEIGHT + 50)
    assert memory.schedule_places[SATURDAY].key == BREAK
    await _hide(schedule, "Keynote")
    await schedule.until(lambda: not memory.schedule_places[SATURDAY].stale)
    (keyed, offset) = [kwargs for _, kwargs in schedule.scrolls]
    assert (keyed["scroll_key"].value, keyed["duration"]) == (BREAK, 0)
    assert offset == {"offset": 4000.0 - 1 + 50.0, "duration": 0}
    place = memory.schedule_places[SATURDAY]
    assert (place.key, place.into, place.layout) == (
        BREAK,
        50.0,
        (1, ("Open Space", "Keynote")),
    )
    await schedule.until(lambda: schedule.list_of(SATURDAY).cache_extent is None)


async def test_a_hidden_slot_gives_the_next_shown_slot_from_its_top(
    shown: Callable[[], Awaitable[Shown]], memory: ViewMemory
) -> None:
    """The slot at the top is gone: the next one still shown takes its place."""
    schedule = await shown()
    await _at_saturday(schedule, 3 * HEIGHT + 50)
    await _hide(schedule, "Break")
    await schedule.until(lambda: not memory.schedule_places[SATURDAY].stale)
    assert schedule.keyed() == [TALKS]
    assert memory.schedule_places[SATURDAY].into == 0.0
    assert memory.schedule_offsets[SATURDAY] == 4000.0 - 1


async def test_a_slot_whose_rows_changed_shows_from_its_top(
    shown: Callable[[], Awaitable[Shown]], memory: ViewMemory
) -> None:
    """Its rows moved inside it, so the distance into it says nothing of them now.

    The first slot has no divider, so the keyed jump is the whole put-back.
    """
    schedule = await shown()
    await _at_saturday(schedule, 50.0)
    await _hide(schedule, "Lightning-talks")
    await schedule.until(lambda: not memory.schedule_places[SATURDAY].stale)
    assert [kwargs["scroll_key"].value for _, kwargs in schedule.scrolls] == [FIRST]
    assert memory.schedule_places[SATURDAY].into == 0.0


async def test_the_put_back_waits_for_flutter_to_lay_the_change_out(
    shown: Callable[[], Awaitable[Shown]], memory: ViewMemory
) -> None:
    """A keyed jump reads Flutter's layout: before a report it would read the old list."""
    schedule = await shown()
    await _at_saturday(schedule, 3 * HEIGHT + 50)
    await schedule.prefs.save(
        schedule.storage, excluded_tracks=("Open Space", "Keynote")
    )
    await schedule.settle()
    assert schedule.scrolls == []
    assert memory.schedule_places[SATURDAY].stale
    _, column = _slots(schedule, SATURDAY)[0]
    await schedule.event(column, "size_change", {"w": 400.0, "h": HEIGHT})
    await schedule.until(lambda: schedule.keyed() == [BREAK])


async def test_a_scroll_of_the_user_s_stops_the_put_back_between_its_jumps(
    shown: Callable[[], Awaitable[Shown]], memory: ViewMemory
) -> None:
    """#346's risk: a put-back that fights the user's fling. The place is dropped."""
    schedule = await shown()
    await _at_saturday(schedule, 3 * HEIGHT + 50)
    await _hide(schedule, "Keynote")
    await schedule.until(lambda: memory.schedule_offsets.get(SATURDAY) == 4000.0)
    start = {
        "event_type": "start",
        "pixels": 4000.0,
        "min_scroll_extent": 0.0,
        "max_scroll_extent": 20_000.0,
        "viewport_dimension": 700.0,
    }
    await schedule.event(schedule.list_of(SATURDAY), "scroll", start)
    await schedule.until(lambda: SATURDAY not in memory.schedule_places)
    assert [kwargs.get("offset") for _, kwargs in schedule.scrolls] == [None]


async def test_another_day_s_place_is_put_back_when_it_shows_again(
    shown: Callable[[], Awaitable[Shown]], memory: ViewMemory
) -> None:
    """A change made while Thursday shows: Saturday's list, built in full, goes back."""
    schedule = await shown()
    await _at_saturday(schedule, 3 * HEIGHT + 50)
    await schedule.change_day(THURSDAY)
    await _hide(schedule, "Keynote")
    assert memory.schedule_places[SATURDAY].stale
    assert schedule.list_of(SATURDAY).cache_extent == scrolling.FULL_LIST_EXTENT
    assert schedule.scrolls == []
    await schedule.change_day(SATURDAY)
    await schedule.until(lambda: not memory.schedule_places[SATURDAY].stale)
    assert schedule.keyed() == [BREAK]
    assert memory.schedule_offsets[SATURDAY] == 4049.0


@pytest.mark.parametrize(
    ("before", "after", "same"),
    [
        # "b" went: "a" and "c" keep their rows and their dividers.
        (("a", "b", "c"), ("a", "c"), {"a", "c"}),
        # "a" went: "b" is first now, without its divider, so 1 dp shorter.
        (("a", "b", "c"), ("b", "c"), {"c"}),
        # The now line keeps its height whatever the filter.
        (("a", NOW_KEY, "c"), ("a", NOW_KEY, "c"), {"a", NOW_KEY, "c"}),
    ],
)
def test_the_heights_a_filter_change_keeps(
    before: tuple[str, ...], after: tuple[str, ...], same: set[str]
) -> None:
    """Flutter reports no size that did not change, so these heights must outlive it."""
    slots = {key: Slot(test_schedule.DURING, ()) for key in ("a", "b", "c")}
    assert unchanged_keys(before, after, slots, slots) == same


def test_a_slot_with_other_sessions_is_changed() -> None:
    """``Slot``s compare their sessions: another tuple is another height."""
    one = next(iter(processed(2026).sessions.values()))
    before = {"a": Slot(test_schedule.DURING, (one,))}
    after = {"a": Slot(test_schedule.DURING, ())}
    assert unchanged_keys(("a",), ("a",), before, after) == frozenset()
