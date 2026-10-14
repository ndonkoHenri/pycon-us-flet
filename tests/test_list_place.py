"""Tests for where the reader is in today's Schedule list, as a key (D-250, #333).

The pure part: ``core/list_place.py`` over the 2026 feed's Friday and hand-made
heights. When the Schedule records and puts back a place is ``tests/test_schedule_place.py``.
"""

from datetime import date

from pycon_us.core.list_place import (
    Place,
    list_items,
    place_at,
    place_of,
    target_of,
    top_of,
)
from pycon_us.core.timeline import NOW_KEY, timeline
from tests.feeds import processed

FRIDAY = date(2026, 5, 15)
SLOTS = timeline(processed(2026), FRIDAY, ("Open Space",))
ITEMS = list_items(SLOTS, 2)  # the now line before the third slot
HEIGHTS = {item.key: 100.0 for item in ITEMS} | {NOW_KEY: 30.0}


def test_the_now_line_sits_before_its_slot_and_has_no_rows() -> None:
    keys = [item.key for item in ITEMS]
    assert keys[:2] == [SLOTS[0].key, SLOTS[1].key]
    assert keys[2] == NOW_KEY
    assert keys[3] == SLOTS[2].key
    assert ITEMS[2].start is None and ITEMS[2].sessions == ()
    assert ITEMS[3].sessions == tuple(s.id for s in SLOTS[2].sessions)
    assert NOW_KEY not in [item.key for item in list_items(SLOTS, None)]


def test_the_place_is_the_first_item_whose_bottom_is_below_the_top() -> None:
    assert place_at(ITEMS, HEIGHTS, 0.0) == Place(
        SLOTS[0].key, SLOTS[0].start, ITEMS[0].sessions, 0.0
    )
    place = place_at(ITEMS, HEIGHTS, 150.0)
    assert place is not None and (place.key, place.into) == (SLOTS[1].key, 50.0)
    place = place_at(ITEMS, HEIGHTS, 210.0)  # inside the now line
    assert place is not None and (place.key, place.into) == (NOW_KEY, 10.0)
    place = place_at(ITEMS, HEIGHTS, 230.0)  # the line's bottom is the slot's top
    assert place is not None and (place.key, place.into) == (SLOTS[2].key, 0.0)


def test_without_a_height_above_the_top_or_past_the_end_there_is_no_place() -> None:
    missing = {k: h for k, h in HEIGHTS.items() if k != SLOTS[1].key}
    assert place_at(ITEMS, missing, 50.0) is not None  # above the missing one
    assert place_at(ITEMS, missing, 150.0) is None
    assert place_at(ITEMS, HEIGHTS, sum(HEIGHTS.values())) is None


def test_a_jump_leaves_the_top_of_its_target() -> None:
    assert place_of(ITEMS, NOW_KEY) == Place(NOW_KEY, None, (), 0.0)
    assert place_of(ITEMS, "slot-gone") is None


def test_an_unchanged_slot_comes_back_as_far_in() -> None:
    place = Place(SLOTS[5].key, SLOTS[5].start, ITEMS[6].sessions, 42.0)
    assert target_of(ITEMS, place) == (SLOTS[5].key, 42.0)


def test_a_slot_whose_rows_changed_comes_back_at_its_time() -> None:
    place = Place(SLOTS[5].key, SLOTS[5].start, ("another",), 42.0)
    assert target_of(ITEMS, place) == (SLOTS[5].key, 0.0)


def test_a_place_within_the_divider_is_the_slot_s_top() -> None:
    """A keyed jump already leaves the 1 dp divider above the top: no second jump."""
    place = Place(SLOTS[5].key, SLOTS[5].start, ITEMS[6].sessions, 1.0)
    assert target_of(ITEMS, place) == (SLOTS[5].key, 0.0)


def test_a_hidden_slot_gives_way_to_the_next_shown_else_the_last() -> None:
    hidden = SLOTS[5]
    shown = list_items([s for s in SLOTS if s is not hidden], 2)
    place = Place(hidden.key, hidden.start, (), 42.0)
    assert target_of(shown, place) == (SLOTS[6].key, 0.0)
    last = Place("slot-late", SLOTS[-1].start.replace(hour=23), (), 0.0)
    assert target_of(shown, last) == (SLOTS[-1].key, 0.0)


def test_the_now_line_stays_the_now_line_and_an_empty_list_has_no_target() -> None:
    place = Place(NOW_KEY, None, (), 10.0)
    assert target_of(ITEMS, place) == (NOW_KEY, 10.0)
    assert target_of(list_items(SLOTS, None), place) is None
    assert target_of((), Place(SLOTS[0].key, SLOTS[0].start, (), 0.0)) is None


def test_an_item_starts_below_every_item_above_it_once_they_reported() -> None:
    assert top_of(ITEMS, HEIGHTS, SLOTS[0].key) == 0.0
    assert top_of(ITEMS, HEIGHTS, SLOTS[2].key) == 230.0  # two slots and the line
    missing = {k: h for k, h in HEIGHTS.items() if k != SLOTS[1].key}
    assert top_of(ITEMS, missing, SLOTS[2].key) is None
    assert top_of(ITEMS, HEIGHTS, "slot-gone") is None
