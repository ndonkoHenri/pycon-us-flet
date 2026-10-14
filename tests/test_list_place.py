"""Tests for ``core/list_place.py``: where the reader is in today's list, and back (#333).

Small hand-made layouts, so each rule shows in the numbers: which slot is at the top,
how far into it, and the offset that puts it back once heights or slots changed (D-250).
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from pycon_us.core.list_place import (
    DIVIDER,
    Anchor,
    ListItem,
    anchor_at,
    has_divider,
    list_items,
    offset_of,
)
from pycon_us.core.timeline import NOW_KEY, timeline
from tests.feeds import processed

PACIFIC = ZoneInfo("America/Los_Angeles")
NINE = datetime(2026, 5, 15, 9, 0, tzinfo=PACIFIC)


def slot(minutes: int, *ids: str, lead: float = DIVIDER) -> ListItem:
    """A slot item ``minutes`` after nine, holding the rows ``ids``."""
    start = NINE + timedelta(minutes=minutes)
    return ListItem(f"slot-{start.isoformat()}", start, ids, lead)


def at(item: ListItem, into: float) -> Anchor:
    """The anchor a scroll end would record at ``into`` dp into the slot ``item``."""
    assert item.start is not None
    return Anchor(item.key, item.start, item.sessions, into)


LINE = ListItem(NOW_KEY, None, (), 0)
A = slot(0, "1", "2", lead=0)  # the day's first slot: no divider
B = slot(30, "3", "4")
C = slot(60, "5")
D = slot(90, "6", "7")
HEIGHTS = {A.key: 200.0, B.key: 200.0, C.key: 100.0, D.key: 200.0, NOW_KEY: 30.0}


def test_the_divider_is_above_every_slot_but_the_first_and_the_one_after_the_line() -> (
    None
):
    assert [has_divider(i, None) for i in range(3)] == [False, True, True]
    assert [has_divider(i, 2) for i in range(4)] == [False, True, False, True]
    assert [has_divider(i, 0) for i in range(2)] == [False, True]


def test_today_s_items_put_the_line_before_the_slots_still_to_start() -> None:
    slots = timeline(processed(2026), NINE.date(), ())
    items = list_items(slots, 2)
    assert [i.key for i in items[:4]] == [
        slots[0].key,
        slots[1].key,
        NOW_KEY,
        slots[2].key,
    ]
    assert [i.lead for i in items[:4]] == [0, DIVIDER, 0, 0]  # the line divides
    assert items[3].sessions == tuple(s.id for s in slots[2].sessions)
    assert NOW_KEY not in [i.key for i in list_items(slots, None)]


@pytest.mark.parametrize(
    ("pixels", "key", "into"),
    [
        (0.0, A.key, 0.0),
        (199.0, A.key, 199.0),  # a sliver of A is still in view
        (200.0, B.key, 0.0),
        (301.0, B.key, 101.0),
        (450.0, C.key, 50.0),
    ],
)
def test_the_anchor_is_the_first_slot_still_in_view(
    pixels: float, key: str, into: float
) -> None:
    anchor = anchor_at((A, B, C, D), HEIGHTS, pixels)
    assert anchor is not None
    assert (anchor.key, anchor.into) == (key, into)


def test_with_the_now_line_at_the_top_the_anchor_is_the_slot_under_it() -> None:
    anchor = anchor_at((A, B, LINE, C, D), HEIGHTS, 410.0)
    assert anchor is not None
    assert (anchor.key, anchor.into) == (C.key, -20.0)  # 20 dp of the line shows


def test_past_the_last_slot_the_anchor_is_the_last_slot() -> None:
    anchor = anchor_at((A, B, LINE), HEIGHTS, 410.0)
    assert anchor is not None
    assert (anchor.key, anchor.into) == (B.key, 210.0)


def test_an_unreported_height_above_the_top_gives_no_anchor() -> None:
    assert anchor_at((A, B, C), {A.key: 200.0}, 250.0) is None
    assert anchor_at((), HEIGHTS, 0.0) is None


def test_the_same_slot_comes_back_as_far_in_when_rows_above_it_change() -> None:
    anchor = at(C, 30.0)
    shorter = HEIGHTS | {A.key: 100.0}  # a track hidden in A
    assert offset_of((A, B, C, D), shorter, anchor) == 100 + 200 + 30
    taller = {key: height * 1.5 for key, height in HEIGHTS.items()}  # text size
    assert offset_of((A, B, C, D), taller, anchor) == 300 + 300 + 30


def test_a_slot_that_shrank_under_the_distance_comes_back_at_its_time() -> None:
    """A smaller text size: 300 dp into B would now be 100 dp into C, and C would
    become the place; B's time is at the top instead."""
    anchor = at(B, 300.0)
    tall = HEIGHTS | {B.key: 400.0}
    assert offset_of((A, B, C, D), tall, anchor) == 200 + 300
    smaller = {key: height / 2 for key, height in tall.items()}
    offset = offset_of((A, B, C, D), smaller, anchor)
    assert offset == 100 + DIVIDER
    after = anchor_at((A, B, C, D), smaller, offset)
    assert after is not None
    assert after.key == B.key


def test_a_line_that_shrank_or_went_keeps_the_slot_under_it_at_the_top() -> None:
    anchor = at(C, -30.0)  # all of the 30 dp line showed
    smaller = HEIGHTS | {NOW_KEY: 15.0}
    assert offset_of((A, B, LINE, C, D), smaller, anchor) == 400 + 15 - 15
    gone = ListItem(C.key, C.start, C.sessions, DIVIDER)  # it takes the divider back
    assert offset_of((A, B, gone, D), HEIGHTS, anchor) == 400 + DIVIDER


def test_a_slot_whose_rows_changed_comes_back_at_its_time() -> None:
    anchor = at(B, 150.0)
    fewer = ListItem(B.key, B.start, ("4",), DIVIDER)
    assert offset_of((A, fewer, C, D), HEIGHTS, anchor) == 200 + DIVIDER


def test_a_hidden_slot_gives_way_to_the_next_shown_one() -> None:
    anchor = at(B, 150.0)
    assert offset_of((A, C, D), HEIGHTS, anchor) == 200 + DIVIDER
    assert offset_of((A, D), HEIGHTS, anchor) == 200 + DIVIDER
    late = at(D, 10.0)
    assert offset_of((A, B), HEIGHTS, late) == 200 + DIVIDER  # the day's last slot


def test_a_negative_distance_keeps_the_line_in_view_and_never_goes_above_zero() -> None:
    anchor = at(C, -20.0)
    assert offset_of((A, B, LINE, C, D), HEIGHTS, anchor) == 430 - 20
    first = at(A, -20.0)
    assert offset_of((LINE, A, B), HEIGHTS, first) == 10.0
    assert offset_of((A, B), HEIGHTS, first) == 0.0


def test_an_unreported_height_above_the_target_gives_no_offset() -> None:
    anchor = at(C, 0.0)
    assert offset_of((A, B, C), {A.key: 200.0}, anchor) is None
    assert offset_of((LINE,), HEIGHTS, anchor) is None
