"""Tests for the Schedule screen: day tabs, the now line and no data (#86, #89).

The screen renders in ``tests/schedule_view.py``'s harness, in a real Flet session with
``ListView.scroll_to`` and the jumps recorded. The day lists are in
``test_schedule_lists.py``, positions and Jump to now in ``test_schedule_jump.py``, the
jump's policy and the "Now" button in ``test_schedule_button.py``. How the tabs read at
200 % and what TalkBack says are device checks (#86, #89).
"""

from collections.abc import Awaitable, Callable
from datetime import date, datetime
from typing import Any, cast

import flet as ft
import pytest

from pycon_us import clock
from pycon_us.core.timeline import NOW_KEY
from pycon_us.feed_refresh import Problem
from pycon_us.memory import ViewMemory
from pycon_us.screens import schedule as screen
from pycon_us.screens import schedule_now
from pycon_us.state import Conference
from pycon_us.ui import scrolling
from tests import schedule_view
from tests.feeds import processed
from tests.schedule_view import (
    BEFORE,
    DAYS,
    FRIDAY,
    PACIFIC,
    SATURDAY,
    TEN_30,
    Shown,
    _assert_asks,
    _list_items,
    _spoken,
    friday_at,
    inside,
)
from tests.sessions import find, settle
from tests.trees import texts

now = schedule_view.now
memory = schedule_view.memory
conference = schedule_view.conference
shown = schedule_view.shown


# ------------------------------------------------------------------ day tabs (SCHED-01)


async def test_every_conference_day_is_a_one_line_tab_read_in_full(
    shown: Callable[[], Awaitable[Shown]],
) -> None:
    """S2: a second line clipped at 200 %; the spoken label keeps the month."""
    schedule = await shown()
    assert schedule.tabs.length == len(DAYS)
    labels = [_tab_text(schedule, i) for i in range(7)]
    assert labels == [
        "Wed 13",
        "Thu 14",
        "Fri 15",
        "Sat 16",
        "Sun 17",
        "Mon 18",
        "Tue 19",
    ]
    friday = schedule.node("schedule.day_tab.2")
    assert _spoken(schedule, 2) == "Friday, May 15, today"  # after "Tab 3 of 7"
    assert friday.label is None  # merged into the tab's node with the identifier
    assert _has_dot(schedule, friday)  # today's mark
    (row,) = find(schedule.session, ft.Row, lambda c: inside(c, friday))
    assert row.vertical_alignment == ft.CrossAxisAlignment.CENTER  # at every size
    saturday = schedule.node("schedule.day_tab.3")
    assert _spoken(schedule, 3) == "Saturday, May 16"
    assert not _has_dot(schedule, saturday)
    (bar,) = find(schedule.session, ft.TabBar)
    assert bar.scrollable


async def test_today_is_selected_during_the_conference(
    shown: Callable[[], Awaitable[Shown]],
) -> None:
    """During the conference, the Schedule opens on today's tab."""
    schedule = await shown()
    assert schedule.tabs.selected_index == DAYS.index(FRIDAY)


@pytest.mark.parametrize("loaded", [True, False])
async def test_the_app_bar_has_the_schedule_changes_overflow(
    shown: Callable[[], Awaitable[Shown]], conference: Conference, loaded: bool
) -> None:
    """The overflow, "Schedule changes" (D-255), is there with data and without."""
    if not loaded:
        conference.data = None
    schedule = await shown()
    assert bool(schedule.find(ft.Tabs)) is loaded  # no day tabs without data
    assert len(schedule.nodes("schedule.overflow")) == 1


async def test_the_first_day_is_selected_outside_the_conference(
    shown: Callable[[], Awaitable[Shown]], now: list[datetime]
) -> None:
    """Before the conference, the first day is selected and no tab says "today"."""
    now[0] = BEFORE
    schedule = await shown()
    assert schedule.tabs.selected_index == 0
    assert all("today" not in _spoken(schedule, i) for i in range(len(DAYS)))


async def test_the_developer_fake_clock_picks_today(
    shown: Callable[[], Awaitable[Shown]], now: list[datetime | None]
) -> None:
    """D-187: the fake clock moves ``clock.now()``, and with it the Schedule's today."""
    now[0] = None  # no test override: the fake clock answers
    clock.start_fake_clock(datetime(2026, 5, 16, 23, 30, tzinfo=PACIFIC))
    try:
        schedule = await shown()
        assert schedule.tabs.selected_index == DAYS.index(SATURDAY)
        assert _spoken(schedule, DAYS.index(SATURDAY)) == "Saturday, May 16, today"
    finally:
        clock.start_fake_clock(None)


async def test_a_device_in_another_zone_gets_the_pacific_time_note(
    shown: Callable[[], Awaitable[Shown]], machine_tz: str
) -> None:
    """D-35, D-240: the times are conference time; say so only when the device differs."""
    schedule = await shown()
    notes = find(
        schedule.session,
        ft.Semantics,
        lambda c: c.identifier == "schedule.zone_note",
    )
    if machine_tz == "America/Los_Angeles":
        assert notes == []
    else:
        (note,) = notes
        assert texts(note) == ["Times are Pacific Time (PDT)"]


async def test_the_zone_note_keeps_its_place_under_the_strip_in_every_zone(
    shown: Callable[[], Awaitable[Shown]], machine_tz: str
) -> None:
    """#313: a line that comes and goes would shift the day pages and rebuild them."""
    schedule = await shown()
    column = cast(ft.Column, schedule.tabs.content)
    assert len(column.controls) == 4  # the probe (D-331), the bar, the head, the pages
    pages = cast(ft.Stack, column.controls[-1])  # the day pages over the landing note
    pulled = cast(ft.RefreshIndicator, pages.controls[-1])  # under pull-to-refresh
    assert isinstance(pulled.content, ft.TabBarView)


async def test_a_remembered_day_wins_over_today(
    shown: Callable[[], Awaitable[Shown]], memory: ViewMemory
) -> None:
    """A day remembered in ``ViewMemory`` is selected over today."""
    memory.schedule_day = SATURDAY
    schedule = await shown()
    assert schedule.tabs.selected_index == DAYS.index(SATURDAY)


def _tab_text(schedule: Shown, index: int) -> str:
    """The visible text of day tab ``index``."""
    node = schedule.node(f"schedule.day_tab.{index}")
    (text,) = find(schedule.session, ft.Text, lambda c: inside(c, node))
    return str(text.value)


def _has_dot(schedule: Shown, node: ft.Semantics) -> bool:
    """Whether the tab ``node`` holds today's mark, a dot."""
    return bool(find(schedule.session, ft.Container, lambda c: inside(c, node)))


async def test_a_day_change_is_remembered_and_its_echo_changes_nothing(
    shown: Callable[[], Awaitable[Shown]], memory: ViewMemory
) -> None:
    """A day change is kept in ``ViewMemory``; its echo re-renders no slot or row."""
    schedule = await shown()
    await schedule.change_day(SATURDAY)
    assert memory.schedule_day == SATURDAY
    assert schedule.tabs.selected_index == DAYS.index(SATURDAY)
    schedule.rows.clear()
    schedule.slots.clear()
    await schedule.change_day(SATURDAY)  # the echo of a switch set from Python
    assert (schedule.rows, schedule.slots) == ([], [])


# ------------------------------------------------------------------ the now line (#89)


def _now_line(schedule: Shown) -> ft.Semantics:
    """The now line's ``Semantics`` node."""
    return schedule.node("schedule.now_line")


async def test_today_s_now_line_sits_after_the_last_slot_that_started(
    shown: Callable[[], Awaitable[Shown]],
) -> None:
    """ux.md §5.2 item 4: a 2 dp primary line, "Now · 10:40 AM", read "Current time"."""
    schedule = await shown()
    now_key = ft.ScrollKey(NOW_KEY)
    keys = _list_items(schedule, FRIDAY)
    line = keys.index(NOW_KEY)
    assert keys[line - 1] == TEN_30
    assert keys[line + 1] == "slot-2026-05-15T11:00:00-07:00"
    node = _now_line(schedule)
    assert node.label == "Current time 10:40 AM"
    assert node.exclude_semantics and not node.live_region
    assert texts(node) == ["Now · 10:40 AM"]
    (anchor,) = find(schedule.session, ft.Container, lambda c: c.key == now_key)
    assert anchor.content is None and not inside(node, anchor)  # D-242
    (bar,) = find(schedule.session, ft.Container, lambda c: inside(c, node))
    assert (bar.height, bar.bgcolor) == (schedule_now.NOW_LINE, ft.Colors.PRIMARY)
    assert NOW_KEY not in _list_items(schedule, SATURDAY)  # today's list only


async def test_a_minute_re_renders_the_line_alone_and_a_slot_start_moves_it(
    shown: Callable[[], Awaitable[Shown]],
) -> None:
    """A minute re-renders the now line alone; a slot start moves it below that slot.

    D-153: no row re-renders; a move re-renders only the two slots whose divider the
    line takes or gives back.
    """
    schedule = await shown()
    schedule.rows.clear()
    schedule.slots.clear()
    await schedule.at(friday_at(10, 41))
    assert texts(_now_line(schedule)) == ["Now · 10:41 AM"]
    assert (schedule.rows, schedule.slots) == ([], [])
    await schedule.at(friday_at(11, 0))
    keys = _list_items(schedule, FRIDAY)
    assert keys[keys.index(NOW_KEY) - 1] == "slot-2026-05-15T11:00:00-07:00"
    assert schedule.rows == []
    assert sorted(schedule.slots) == ["11:00 AM", "11:30 AM"]


async def test_between_slots_the_jump_lands_on_the_now_line(
    shown: Callable[..., Awaitable[Shown]], now: list[datetime | None]
) -> None:
    """Between slots, the jump lands on the now line and a tap announces the time.

    D-204: at 2:35 PM nothing is on; the line sits above 2:45 PM's slot, and a screen
    reader hears the time, as the line itself says it.
    """
    now[0] = friday_at(14, 35)
    schedule = await shown(screen_reader=True, announcements=True)
    assert schedule.jumped() == [NOW_KEY]
    keys = _list_items(schedule, FRIDAY)
    assert keys[keys.index(NOW_KEY) + 1] == "slot-2026-05-15T14:45:00-07:00"
    await schedule.scroll_away()
    await schedule.press_now()
    assert schedule.announced == ["Friday, May 15, current time 2:35 PM"]


async def test_after_the_day_the_line_ends_the_list_and_now_goes_there(
    shown: Callable[[], Awaitable[Shown]], now: list[datetime | None]
) -> None:
    """The button keeps its label: the line at the end shows now is past the day."""
    now[0] = friday_at(21, 0)
    schedule = await shown()
    assert _list_items(schedule, FRIDAY)[-1] == NOW_KEY
    assert schedule.jumped() == [NOW_KEY]
    await schedule.scroll_away()
    assert texts(
        cast(ft.Control, cast(ft.FloatingActionButton, schedule.fab).content)
    ) == ["Now"]


# ------------------------------------------------------------------ without data (D-32)


async def test_the_strip_refreshes_every_15_minutes_with_or_without_data(
    shown: Callable[[], Awaitable[Shown]], conference: Conference
) -> None:
    """D-40, D-175: Now and Schedule pass auto_refresh=True."""
    schedule = await shown()
    assert schedule.strips and set(schedule.strips) == {True}
    conference.data = None
    conference.version += 1
    await settle()
    assert set(schedule.strips) == {True}


async def test_without_data_the_skeleton_shows_until_the_first_fetch_ends(
    shown: Callable[[], Awaitable[Shown]], conference: Conference
) -> None:
    """Without data, the Schedule shows the loading skeleton and no day tabs."""
    conference.data, conference.source = None, "none"
    schedule = await shown()
    assert find(schedule.session, ft.Semantics, lambda c: c.label == "Loading schedule")
    assert find(schedule.session, ft.Tabs) == []


async def test_the_first_data_is_the_first_display_it_renders_today_first_and_jumps(
    shown: Callable[[], Awaitable[Shown]],
    conference: Conference,
    memory: ViewMemory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """NEW-03, then the first fetch: D-156's two renders and the one jump still hold."""
    lists: list[date] = []
    spy = screen.DayList

    def counted(day: date, *args: Any, **kwargs: Any) -> ft.Control:
        lists.append(day)
        return spy(day, *args, **kwargs)

    monkeypatch.setattr(screen, "DayList", counted)
    conference.data, conference.source = None, "none"
    schedule = await shown()
    assert schedule.scrolls == [] and memory.jumped_on is None

    conference.data, conference.source = processed(2026), "network"
    conference.version += 1
    await schedule.until(lambda: schedule.jumps and not schedule.jumping)
    assert lists[0] == FRIDAY and set(lists) == set(DAYS)  # today alone, then the rest
    assert schedule.jumps == [(TEN_30, "landed")]  # one jump, through both renders
    _assert_asks(schedule, FRIDAY, TEN_30, scrolling.JUMP_MS)
    assert memory.jumped_on == FRIDAY  # so a tab return does not jump (SCHED-16)


@pytest.mark.parametrize(
    ("problem", "body"),
    [
        ("offline", "Connect to the internet and try again."),
        ("server", "The schedule couldn't be read. Try again in a few minutes."),
    ],
)
async def test_a_failed_first_fetch_says_so_and_offers_try_again(
    shown: Callable[[], Awaitable[Shown]],
    conference: Conference,
    monkeypatch: pytest.MonkeyPatch,
    problem: Problem,
    body: str,
) -> None:
    """A failed first fetch says why; "Try again" starts a refresh, and so does a pull.

    The state's list is under pull-to-refresh too (D-449).
    """
    refreshes: list[str] = []

    async def refresh(*_: Any, **__: Any) -> None:
        refreshes.append("refresh")

    # On the class: assigning to the store would notify, also when the patch is undone.
    monkeypatch.setattr(Conference, "refresh", refresh)
    conference.data, conference.problem = None, problem
    schedule = await shown()
    state = schedule.node("schedule.no_data")
    assert texts(state) == ["Can't load the schedule", body]
    (button,) = find(schedule.session, ft.FilledTonalButton)
    assert button.content == "Try again" and not button.disabled
    await schedule.session.dispatch_event(button._i, "click", None)
    await settle()
    assert refreshes == ["refresh"]
    (indicator,) = find(schedule.session, ft.RefreshIndicator)
    monkeypatch.setattr(ft.RefreshIndicator, "_invoke_method", _told)
    await schedule.session.dispatch_event(indicator._i, "refresh", None)
    await settle()
    assert refreshes == ["refresh", "refresh"]


@pytest.mark.parametrize(("asked", "disabled"), [(False, False), (True, True)])
async def test_try_again_is_disabled_only_while_the_user_s_refresh_runs(
    shown: Callable[[], Awaitable[Shown]],
    conference: Conference,
    asked: bool,
    disabled: bool,
) -> None:
    """D-181: a quiet refresh leaves it enabled, so a tap joins it."""
    conference.data, conference.problem, conference.refreshing = None, "offline", True
    conference._asked = asked
    schedule = await shown()
    (button,) = find(schedule.session, ft.FilledTonalButton)
    assert button.disabled is disabled
    assert texts(schedule.node("schedule.no_data"))[0] == "Can't load the schedule"


async def _told(*_: Any) -> None:
    """Stand in for ``RefreshIndicator``'s ``finish_refresh``: no Flutter to tell here."""
