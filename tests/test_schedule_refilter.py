"""Tests for the Schedule keeping each day's place across a filter change (D-371, #333).

The Schedule renders in ``tests/schedule_view.py``'s harness, with
``tests/test_schedule_place.py``'s helpers: a keyed scroll is answered with a scroll end
at 4,000 dp, an offset jump with one where it was asked. Saturday's first slots in the
2026 feed, with the default filter (Open space hidden): 8:00 (notices, a break and
lightning talks), 9:00, 9:25 (the keynote), 10:05 (a break), 10:30. Whether the rows
really stay in view is a device check (#333's PR).
"""

from collections.abc import Awaitable, Callable

import pytest

from pycon_us.core.list_place import Place, carried
from pycon_us.core.timeline import NOW_KEY, Slot, timeline
from pycon_us.memory import ViewMemory
from pycon_us.screens.schedule_layout import unchanged_keys
from pycon_us.ui import scrolling
from tests import schedule_view, test_schedule_place
from tests.feeds import processed
from tests.schedule_view import FRIDAY, SATURDAY, THURSDAY, Shown
from tests.test_schedule_place import HEIGHT, _report, _slots

# The Schedule's fixtures, shared by name: pytest finds fixtures among a module's names.
now = schedule_view.now
memory = schedule_view.memory
conference = schedule_view.conference
shown = schedule_view.shown

KEYNOTE = "slot-2026-05-16T09:25:00-07:00"
BREAK = "slot-2026-05-16T10:05:00-07:00"
TALKS = "slot-2026-05-16T10:30:00-07:00"
FIRST = "slot-2026-05-16T08:00:00-07:00"
OPEN_SPACE = "slot-2026-05-16T10:00:00-07:00"


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


def _user_scroll(event_type: str, pixels: float) -> dict[str, object]:
    """A scroll event of the user's at ``pixels``, as Flutter sends it."""
    return {
        "event_type": event_type,
        "pixels": pixels,
        "min_scroll_extent": 0.0,
        "max_scroll_extent": 20_000.0,
        "viewport_dimension": 700.0,
    }


async def test_a_scroll_the_user_ends_while_the_layout_waits_drops_the_put_back(
    shown: Callable[[], Awaitable[Shown]], memory: ViewMemory
) -> None:
    """The user wins (D-371): a whole scroll before the layout's report moves nothing.

    Its end records the user's place; the old one must not come back over it.
    """
    schedule = await shown()
    await _at_saturday(schedule, 3 * HEIGHT + 50)
    await schedule.prefs.save(
        schedule.storage, excluded_tracks=("Open Space", "Keynote")
    )
    await schedule.settle()
    day_list = schedule.list_of(SATURDAY)
    await schedule.event(day_list, "scroll", _user_scroll("start", 650.0))
    await schedule.event(day_list, "scroll", _user_scroll("end", 650.0))
    await _report(schedule, SATURDAY, HEIGHT)
    await schedule.until(lambda: schedule.list_of(SATURDAY).cache_extent is None)
    assert schedule.scrolls == []
    assert not memory.schedule_places.get(SATURDAY, Place("", 0, 0, 0)).stale


async def test_a_scroll_the_user_ends_between_the_jumps_drops_the_put_back(
    shown: Callable[[], Awaitable[Shown]], memory: ViewMemory
) -> None:
    """After the keyed jump, a whole scroll of the user's stops the jump into the slot."""
    schedule = await shown()
    await _at_saturday(schedule, 3 * HEIGHT + 50)
    await _hide(schedule, "Keynote")
    await schedule.until(lambda: memory.schedule_offsets.get(SATURDAY) == 4000.0)
    day_list = schedule.list_of(SATURDAY)
    await schedule.event(day_list, "scroll", _user_scroll("start", 4000.0))
    await schedule.event(day_list, "scroll", _user_scroll("end", 650.0))
    await schedule.until(lambda: schedule.list_of(SATURDAY).cache_extent is None)
    assert [kwargs.get("offset") for _, kwargs in schedule.scrolls] == [None]
    assert not memory.schedule_places.get(SATURDAY, Place("", 0, 0, 0)).stale


def test_a_hidden_slot_gives_way_to_a_slot_the_change_reveals() -> None:
    """Reset from Open space shown and Break hidden: 10:05 follows 10:00, not 10:30.

    The 10:05 break was hidden before, so only its start says it comes first.
    """
    data = processed(2026)
    before = timeline(data, SATURDAY, ("Break",))
    after = timeline(data, SATURDAY, ("Open Space",))
    starts = {slot.key: slot.start for slot in (*before, *after)}
    place = Place(OPEN_SPACE, 10.0, 100.0, 500.0)
    moved = carried(
        place,
        [slot.key for slot in before],
        [slot.key for slot in after],
        frozenset(),
        starts,
    )
    assert moved == Place(BREAK, 0.0, 100.0, 500.0, stale=True)


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


async def test_now_on_a_list_already_there_keeps_the_place_for_a_filter_change(
    shown: Callable[..., Awaitable[Shown]],
    memory: ViewMemory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#628's Android check: "Now" on the now slot, then Open space shown, lost the place.

    The list is already there, so the jump scrolls nothing and Flutter sends no end
    to record a place. The place found before stays, and the filter change puts it
    back (the Now button always shows to a screen reader, as to Maestro on Android).
    """
    monkeypatch.setattr(scrolling, "LANDING_S", 0.01)
    schedule = await shown(screen_reader=True)  # Friday, today
    await test_schedule_place._measure(schedule, 40.0)
    await _report(schedule, FRIDAY, HEIGHT)
    await schedule.scroll_end(FRIDAY, 4000.0)  # where the first display's jump landed
    key = memory.schedule_places[FRIDAY].key
    schedule.moves = False
    schedule.forget()
    await schedule.press_now()
    await schedule.until(lambda: schedule.jumps)
    assert [ended for _, ended in schedule.jumps] == ["still"]
    schedule.moves = True
    schedule.forget()
    await schedule.prefs.save(schedule.storage, excluded_tracks=())  # Open space on
    await schedule.settle()
    await _report(schedule, FRIDAY, HEIGHT)
    await schedule.until(lambda: not memory.schedule_places[FRIDAY].stale)
    assert schedule.keyed() == [key]


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
    slots = {key: Slot(schedule_view.DURING, ()) for key in ("a", "b", "c")}
    assert unchanged_keys(before, after, slots, slots) == same


def test_a_slot_with_other_sessions_is_changed() -> None:
    """``Slot``s compare their sessions: another tuple is another height."""
    one = next(iter(processed(2026).sessions.values()))
    before = {"a": Slot(schedule_view.DURING, (one,))}
    after = {"a": Slot(schedule_view.DURING, ())}
    assert unchanged_keys(("a",), ("a",), before, after) == frozenset()
