"""Tests for the Schedule's day lists: slots, rows, re-renders and empty days (#86).

The screen renders in `tests/schedule_view.py`'s harness, in a real Flet session, so
the memoised path (D-153) and the two renders (D-156) run as Flet runs them. The day
tabs, the now line and the states without data are in `test_schedule.py`.
"""

import gc
from collections.abc import Awaitable, Callable
from datetime import date, datetime, timedelta
from typing import Any, cast

import flet as ft
import pytest

from pycon_us import clock
from pycon_us.core.change_batches import Batch
from pycon_us.core.diff import Change, ChangeKind
from pycon_us.core.timeline import NOW_KEY, now_place, timeline
from pycon_us.prefs import Prefs
from pycon_us.screens import schedule as screen
from pycon_us.screens import schedule_head
from pycon_us.screens.schedule_slots import slot_keys
from pycon_us.services import api
from pycon_us.state import Conference
from pycon_us.ui import scrolling, status_strip
from tests import schedule_view, strip
from tests.feeds import processed
from tests.schedule_view import (
    BEFORE,
    DAYS,
    DURING,
    FRIDAY,
    MONDAY,
    TALK,
    THURSDAY,
    WEDNESDAY,
    Shown,
    inside,
)
from tests.sessions import find, settle
from tests.trees import only, texts

now = schedule_view.now
memory = schedule_view.memory
conference = schedule_view.conference
shown = schedule_view.shown
network, finished = strip.network, strip.finished


# ------------------------------------------------------------------ the day lists


async def test_the_shown_day_renders_first_and_the_others_after_a_round_trip(
    shown: Callable[[], Awaitable[Shown]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-156: the first render has one day list; the second all of them."""
    built: list[date] = []
    original = screen.DayList

    def spy(day: date, *args: Any, **kwargs: Any) -> ft.Control:
        built.append(day)
        return original(day, *args, **kwargs)

    monkeypatch.setattr(screen, "DayList", spy)
    schedule = await shown()
    (view,) = find(schedule.session, ft.TabBarView)
    pages = list(view.controls)
    assert len(pages) == len(DAYS)
    assert len(find(schedule.session, ft.ListView)) == len(DAYS)  # after the second
    # A render builds its days in order, so Friday before Wednesday is where the first
    # render ended. Later renders (the jump's landing) build them all again.
    assert built[: len(DAYS) + 1] == [FRIDAY, *DAYS]


async def test_each_slot_is_one_keyed_item_beside_its_gutter(
    shown: Callable[[], Awaitable[Shown]],
) -> None:
    """D-31, D-155: a ScrollKey per slot, the filter's slots only, in time order."""
    schedule = await shown()
    friday = schedule.list_of(FRIDAY)
    items = find(
        schedule.session,
        ft.Container,
        lambda c: (
            isinstance(c.key, ft.ScrollKey)
            and c.key != ft.ScrollKey(NOW_KEY)  # today's now line
            and inside(c, friday)
        ),
    )
    keys = sorted(str(cast(ft.ScrollKey, item.key).value) for item in items)
    # D-242: each key is on an empty anchor above its slot, so no row is under a key
    # and every row keeps its nodes, the screen reader's focus after Back (F62).
    assert all(item.content is None and item.height == 0 for item in items)
    slots = [_slot(item) for item in items]
    assert not any(
        inside(node, item)
        for node in find(schedule.session, ft.Semantics, lambda c: inside(c, friday))
        for item in items
    )
    # A jump puts the slot's time under the tab bar, not a second line (ux.md §5.2);
    # the first slot has none, and the now line stands for the next one's (D-204).
    dividers = find(
        schedule.session, ft.Divider, lambda c: c.visible and inside(c, friday)
    )
    assert len(dividers) == len(items) - 2
    assert not any(inside(d, slot) for d in dividers for slot in slots)
    expected = timeline(processed(2026), FRIDAY, Prefs().excluded_tracks)
    assert keys == sorted(slot.key for slot in expected)
    shown_ids = {
        str(node.identifier).rsplit(".", 1)[1]
        for node in find(schedule.session, ft.Semantics, lambda c: inside(c, friday))
        if node.identifier and ".session." in node.identifier
    }
    assert shown_ids  # and no open space, which the default filter hides (D-20)
    sessions = processed(2026).sessions
    assert all(sessions[i].track != "Open Space" for i in shown_ids if i in sessions)


async def test_at_the_largest_text_each_slot_puts_its_time_above_its_rows(
    shown: Callable[[], Awaitable[Shown]],
) -> None:
    """D-216: the rows get the whole width; the jump's keys stay on the slots."""
    schedule = await shown()

    def slots() -> list[ft.Container]:
        friday = schedule.list_of(FRIDAY)  # the list the last render mounted
        return find(
            schedule.session,
            ft.Container,
            lambda c: (
                isinstance(c.key, ft.ScrollKey)
                and c.key != ft.ScrollKey(NOW_KEY)
                and c.key != ft.ScrollKey(schedule_head.HEAD_KEY)  # D-345
                and inside(c, friday)
            ),
        )

    beside = {str(cast(ft.ScrollKey, c.key).value) for c in slots()}
    assert all(isinstance(_slot(c), ft.Row) for c in slots())  # the gutter
    schedule.prefs.time_above = True  # what GutterProbe measures at that size
    await settle()
    assert {str(cast(ft.ScrollKey, c.key).value) for c in slots()} == beside
    for slot in slots():
        column = _slot(slot)
        assert isinstance(column, ft.Column)
        heading = column.controls[0]
        assert isinstance(heading, ft.Semantics) and heading.header
    friday = schedule.list_of(FRIDAY)
    assert not find(  # no gutter left in the day
        schedule.session, ft.Stack, lambda c: inside(c, friday)
    )


async def test_at_the_largest_text_the_head_tops_each_day_list_and_scrolls_away(
    shown: Callable[[], Awaitable[Shown]],
) -> None:
    """D-345 (#331): the summary and the strip leave the fixed chrome for the lists.

    The column keeps its four places, so the day pages keep theirs (#313); each
    day's list gets a head of its own, as its first item; back at a smaller size
    the head is fixed again and no list has one.
    """
    schedule = await shown()
    pages = cast(ft.Column, schedule.tabs.content).controls[-1]._i  # its id
    fixed = _head_parts(schedule)
    assert fixed and not any(_in_a_list(schedule, c) for c in fixed)
    schedule.prefs.time_above = True  # what GutterProbe measures at that size
    await settle()
    column = cast(ft.Column, schedule.tabs.content)
    assert len(column.controls) == 4 and column.controls[-1]._i == pages
    assert cast(ft.Container, column.controls[2]).content is None  # a placeholder
    lists = find(schedule.session, ft.ListView, lambda c: c.key is not None)
    assert len(lists) == len(DAYS)  # the other days are rendered by now (D-156)
    for day_list in lists:
        head = day_list.controls[0]
        assert head.key == schedule_head.HEAD_KEY
        assert sum(inside(c, head) for c in _head_parts(schedule)) == 2
    assert all(_in_a_list(schedule, c) for c in _head_parts(schedule))
    schedule.prefs.time_above = False
    await settle()
    assert cast(ft.Column, schedule.tabs.content).controls[-1]._i == pages
    assert len(_head_parts(schedule)) == len(fixed)
    assert not any(_in_a_list(schedule, c) for c in _head_parts(schedule))


def test_at_the_largest_text_the_places_count_the_head_first() -> None:
    """D-345 with D-331: the head is each list's first item, before today's now line.

    A place is counted from the list's top over its items' keys, so the head, which
    reports its height as the slots do, comes first; the now line keeps its slot.
    """
    data = processed(2026)
    slots = {day: timeline(data, day, ()) for day in (THURSDAY, FRIDAY)}
    place = now_place(slots[FRIDAY], DURING)
    plain = slot_keys(slots, FRIDAY, place, head=False)
    headed = slot_keys(slots, FRIDAY, place, head=True)
    for day in slots:
        assert headed[day] == (schedule_head.HEAD_KEY, *plain[day])
    assert NOW_KEY in plain[FRIDAY]


def _head_parts(schedule: Shown) -> list[ft.BaseControl]:
    """The filter summaries' nodes and the strips' stand-ins the Schedule shows."""
    summaries = find(
        schedule.session,
        ft.Semantics,
        lambda c: c.identifier == "schedule.filter_summary",
    )
    strips = find(schedule.session, ft.Text, lambda c: c.value == "strip")
    return [*summaries, *strips]


def _in_a_list(schedule: Shown, control: ft.BaseControl) -> bool:
    """Whether `control` is in one of the day lists."""
    lists = find(schedule.session, ft.ListView, lambda c: c.key is not None)
    return any(inside(control, day_list) for day_list in lists)


def _slot(anchor: ft.Container) -> ft.Control:
    """The slot a `ScrollKey` anchor marks: the control after it (D-242)."""
    _, slot = cast(ft.Column, anchor.parent).controls
    return slot


async def test_only_today_s_list_builds_every_slot(
    shown: Callable[[], Awaitable[Shown]],
) -> None:
    """D-154: the jump's list; every other list stays lazy."""
    schedule = await shown()
    extents = {day: schedule.list_of(day).cache_extent for day in DAYS}
    assert extents.pop(FRIDAY) == scrolling.FULL_LIST_EXTENT
    assert set(extents.values()) == {None}
    assert all(not schedule.list_of(d).build_controls_on_demand is False for d in DAYS)


async def test_outside_the_conference_no_list_is_built_in_full(
    shown: Callable[[], Awaitable[Shown]], now: list[datetime]
) -> None:
    """Before the conference, every day list stays lazy."""
    now[0] = BEFORE
    schedule = await shown()
    assert {schedule.list_of(day).cache_extent for day in DAYS} == {None}


async def test_one_indicator_around_the_day_pages_runs_the_strip_s_refresh(
    shown: Callable[[], Awaitable[Shown]],
    network: strip.Network,
    finished: list[ft.RefreshIndicator],
) -> None:
    """SCHED-13, D-449: a pull on any day's list is the strip's Refresh.

    One indicator around the `TabBarView` that takes the lists' nested scrolls, so it
    stays mounted when the pulled day leaves. Flet ends its spinner once; offline, no
    slot re-renders.
    """
    schedule = await shown()
    (indicator,) = schedule.find(ft.RefreshIndicator)
    assert isinstance(indicator.content, ft.TabBarView)
    assert indicator.handle_nested_scrolls
    schedule.slots.clear()
    pulled = strip.pull(schedule, indicator)
    await network.arrived.wait()
    network.error = api.NetworkError("ConnectError: offline")
    network.released.set()
    await pulled

    assert network.requests == 1
    assert finished == schedule.find(ft.RefreshIndicator)
    assert schedule.conference.problem == "offline"
    assert schedule.slots == []


@pytest.mark.parametrize("time_above", [False, True])
async def test_a_star_tap_re_renders_one_slot_and_one_row(
    shown: Callable[..., Awaitable[Shown]], time_above: bool
) -> None:
    """D-153: the screen re-renders, but every other day, slot and row is skipped.

    At the largest text too, where every day list carries the head (D-345): its words
    are a value, equal from render to render, so they keep the lists skipped.
    """
    schedule = await shown(time_above=time_above)
    schedule.rows.clear()
    schedule.slots.clear()
    await schedule.tap_star(TALK)
    assert schedule.favorites.ids == {TALK}
    assert schedule.rows == [TALK]
    assert schedule.slots == ["10:30 AM"]


async def test_at_the_largest_text_the_screen_still_re_renders_after_a_minute_tick(
    shown: Callable[..., Awaitable[Shown]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """F150 (#586): nothing under a skipped day list re-renders on its own.

    The head's strip in each list once ticked by itself: after a re-render that skipped
    the lists, the list it was built in was gone, so its tick lost the contexts and
    raised, and Flet re-rendered nothing more in the session. With the real strip, a
    star tap (the lists skipped), a collection and a minute tick, the next star tap
    still re-renders its row.
    """
    monkeypatch.setattr(schedule_head, "strip_view", status_strip.strip_view)
    schedule = await shown(time_above=True)
    await schedule.tap_star(TALK)
    gc.collect()  # the replaced lists' components, kept until now by their cycles
    await schedule.at(DURING + timedelta(minutes=2))
    schedule.rows.clear()
    await schedule.tap_star(TALK)
    assert schedule.favorites.ids == set()
    assert schedule.rows == [TALK]


async def test_a_recorded_batch_re_renders_one_slot_and_one_row(
    shown: Callable[[], Awaitable[Shown]],
) -> None:
    """D-153, D-315: a talk's room change badges its row; no other slot or row runs."""
    schedule = await shown()
    schedule.rows.clear()
    schedule.slots.clear()
    change = Change(TALK, ChangeKind.ROOM, None, None)
    schedule.change_log.batches = (Batch(clock.now(), (change,)),)
    await settle()
    assert schedule.rows == [TALK]
    assert schedule.slots == ["10:30 AM"]
    assert "Room changed" in (schedule.node(f"schedule.session.{TALK}").label or "")


async def test_a_sprint_day_says_so_and_links_to_the_sprints(
    shown: Callable[[], Awaitable[Shown]],
) -> None:
    """Monday's list says it is a sprint day, and its button opens the Sprints page."""
    schedule = await shown()
    state = schedule.node("schedule.sprint_day.2026-05-18")
    assert texts(state)[0] == "Monday is a sprint day"
    button = only(schedule.list_of(MONDAY), ft.FilledTonalButton)
    assert button.content == "See the sprints"
    await schedule.session.dispatch_event(button._i, "click", None)
    await settle()
    assert schedule.went == ["/more/sprints"]


async def test_a_day_the_filter_empties_offers_to_clear_the_filters(
    shown: Callable[[], Awaitable[Shown]], conference: Conference
) -> None:
    """ux.md §4.6: never a blank day, and not the sprint day's state either."""
    wednesday = {
        s.track
        for slot in timeline(processed(2026), WEDNESDAY, ())
        for s in slot.sessions
    }
    schedule = await shown()
    await schedule.prefs.save(schedule.storage, excluded_tracks=tuple(wednesday))
    await settle()
    state = schedule.node("schedule.filtered_day.2026-05-13")
    assert texts(state)[0] == "No sessions on Wednesday match your filters"
    button = only(schedule.list_of(WEDNESDAY), ft.FilledTonalButton)
    assert button.content == "Clear filters"
    await schedule.session.dispatch_event(button._i, "click", None)
    await settle()
    assert schedule.prefs.excluded_tracks == ()
    assert (
        find(
            schedule.session,
            ft.Semantics,
            lambda c: c.identifier == "schedule.filtered_day.2026-05-13",
        )
        == []
    )
