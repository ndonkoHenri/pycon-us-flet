"""Tests for room detail's day lists and "Now in this room" (#101; ROOM-03).

The page runs in `tests/room_view.py`'s harness at fixed times of the 2026 feed; rows
leave out the room's own name.
"""

from datetime import datetime
from typing import Any, cast

import flet as ft
import pytest

from pycon_us import clock
from pycon_us.screens import room as screen
from pycon_us.screens import room_days
from pycon_us.ui import status_strip
from tests import room_view
from tests.room_view import (
    HUMANS,
    LIGHTNING,
    PACIFIC,
    SATURDAY_MORNING,
    SUNDAY_TALK,
    VIEW,
    Render,
    ancestors,
    highlighted,
    phrase_of,
)
from tests.trees import descendants, texts

render = room_view.render


# ------------------------------------------------------------------ the day lists


async def test_one_tab_per_day_the_room_has_sessions_today_marked(
    render: Render,
) -> None:
    """The room has one tab per day it has sessions, and today's says "today"."""
    room = await render(VIEW)
    labels = [str(room.node(f"room.day_tab.{i}").content) for i in range(3)]
    assert len(room.nodes("room.day_tab.3")) == 0
    spoken = [
        cast(ft.Text, t).semantics_label
        for i in range(3)
        for t in descendants(room.node(f"room.day_tab.{i}"))
        if isinstance(t, ft.Text)
    ]
    assert spoken == ["Friday, May 15", "Saturday, May 16, today", "Sunday, May 17"]
    assert labels  # each tab has its label


async def test_a_picked_day_survives_a_re_render(render: Render) -> None:
    """The picked day is state that on_change sets: a star tap keeps the tab (D-194)."""
    room = await render(VIEW)
    assert room.tabs.selected_index == 1  # today, Saturday
    room.session.apply_patch(room.tabs._i, {"selected_index": 0})  # as Flutter does
    await room.session.dispatch_event(room.tabs._i, "change", 0)
    await room.settle()
    await room.favorites.toggle(room.storage, HUMANS)
    await room.settle()
    assert room.tabs.selected_index == 0


async def test_the_room_s_rows_leave_out_its_name(render: Render) -> None:
    """The page's title names the room: the rows say the time alone (#101's comment)."""
    room = await render(VIEW)
    assert room.titles[-1] == "Grand Ballroom A"
    assert phrase_of(room, HUMANS).endswith("10:30 to 11:00 AM. Justin Lee."), (
        phrase_of(room, HUMANS)
    )
    assert "Grand Ballroom A" not in phrase_of(room, HUMANS)
    row = room.node(f"room.session.{HUMANS}")
    assert "Grand Ballroom A" not in texts(row)


async def test_a_row_given_elsewhere_keeps_its_place(render: Render) -> None:
    """A row for a session given in another room still names that room."""
    room = await render(VIEW)
    assert "Pacific Ballroom - Arena" in phrase_of(room, LIGHTNING)


async def test_a_row_pushes_its_session_on_top_of_the_room(render: Render) -> None:
    """Tapping a row pushes its session's detail on top of the room's View."""
    room = await render(VIEW)
    tap = room.node(f"room.session.{HUMANS}")
    box = next(c for c in room.session.index.values() if _holds(c, tap))
    await room.session.dispatch_event(box._i, "click", None)
    await room.settle()
    assert room.went == [f"{VIEW}/session/{HUMANS}"]


def _holds(control: Any, node: ft.Semantics) -> bool:
    """Whether `control` is the tappable `Container` right around `node`."""
    return (
        isinstance(control, ft.Container)
        and control.on_click is not None
        and control.content is node
    )


# ------------------------------------------------------------------ now in this room


async def test_now_in_this_room_names_the_session_on_and_opens_it(
    render: Render,
) -> None:
    """Now in this room names the session on, with its time, and a tap opens it.

    The title wraps at three lines, and the section's heading is level 3, in the day
    beside its slots (D-211).
    """
    room = await render(VIEW, now=SATURDAY_MORNING)
    now = room.node("room.now")
    tile = cast(ft.ListTile, now.content)
    assert isinstance(tile.title, ft.Text)
    assert tile.title.value.startswith("Python for Humans")
    assert tile.title.max_lines == 3
    assert texts(cast(ft.Control, tile.subtitle)) == ["10:30–11:00\N{NO-BREAK SPACE}AM"]
    assert any(
        isinstance(c, ft.Semantics)
        and c.header
        and c.heading_level == 3  # in the day, beside its slots (D-211)
        and texts(c) == ["Now in this room"]
        for c in room.session.index.values()
    )
    tile.on_click()  # type: ignore[misc]
    assert room.went == [f"{VIEW}/session/{HUMANS}"]


async def test_a_divider_closes_now_in_this_room(render: Render) -> None:
    """Now in this room ends with a divider, inside today's list.

    Else the day's first slot reads as the section's second item (D-194).
    """
    room = await render(VIEW, now=SATURDAY_MORNING)
    today = room.day_lists()[1]
    # The columns between the tile and today's list: the list's head (the location
    # card, then Now) outermost, NowInRoom's own inside it.
    columns: list[ft.Column] = []
    parent = room.node("room.now").parent
    while parent is not None and parent is not today:
        if isinstance(parent, ft.Column):
            columns.append(parent)
        parent = parent.parent
    assert parent is today
    assert isinstance(columns[-2].controls[-1], ft.Divider)


async def test_now_in_this_room_says_where_a_streamed_session_is_given(
    render: Render,
) -> None:
    """For a streamed session, Now in this room says the room it is given in.

    Time and place are two texts in a wrapping row, as a row's meta (D-184), spoken as
    one phrase.
    """
    room = await render(VIEW, now=datetime(2026, 5, 16, 8, 30, tzinfo=PACIFIC))
    tile = cast(ft.ListTile, room.node("room.now").content)
    subtitle = cast(ft.Control, tile.subtitle)
    assert texts(subtitle) == [
        "8:00–9:00\N{NO-BREAK SPACE}AM\N{NO-BREAK SPACE}·",
        "Pacific Ballroom - Arena",
    ]
    (line,) = [c for c in descendants(subtitle) if isinstance(c, ft.Row)]
    assert line.wrap
    time, place = cast(list[ft.Text], line.controls)
    spoken = [time.semantics_label, place.semantics_label or place.value]
    assert " ".join(spoken) == "8:00 to 9:00 AM, Pacific Ballroom - Arena"


async def test_with_several_on_the_latest_is_named_and_the_rest_counted(
    render: Render,
) -> None:
    """With two sessions on, Now in this room names the latest and counts the other."""
    room = await render(
        "/map/room/room-102c",
        slug="room-102c",
        now=datetime(2026, 5, 16, 16, 30, tzinfo=PACIFIC),
    )
    tile = cast(ft.ListTile, room.node("room.now").content)
    assert cast(ft.Text, tile.title).value == "Organizing IRL meetups"
    assert texts(cast(ft.Control, tile.subtitle)) == [
        "4:00–5:00\N{NO-BREAK SPACE}PM",
        "and 1\N{NO-BREAK SPACE}more",
    ]


async def test_now_in_this_room_heads_today_s_list_only(render: Render) -> None:
    """Now in this room heads today's list only, whichever day shows.

    It scrolls away with today's slots, so at large text they keep the screen.
    """
    room = await render(highlighted(SUNDAY_TALK))  # Sunday shows; today is Saturday
    (now,) = room.nodes("room.now")
    lists = room.day_lists()
    assert [lst in ancestors(now) for lst in lists] == [False, True, False]


async def test_now_in_this_room_follows_the_clock_on_the_minute_tick(
    render: Render, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On the minute tick, Now in this room goes when a talk ends, then names the next.

    The Developer fake clock moves it, with no touch (D-175, D-187).
    """
    monkeypatch.setattr(status_strip, "TICK_SECONDS", 0.01)
    room = await render(VIEW, now=SATURDAY_MORNING)
    assert len(room.nodes("room.now")) == 1
    clock.set_test_now(datetime(2026, 5, 16, 11, 5, tzinfo=PACIFIC))  # talk over
    await room.until(lambda: room.nodes("room.now") == [])
    clock.set_test_now(datetime(2026, 5, 16, 11, 20, tzinfo=PACIFIC))  # the next one
    await room.until(lambda: len(room.nodes("room.now")) == 1)
    tile = cast(ft.ListTile, room.node("room.now").content)
    assert cast(ft.Text, tile.title).value.startswith("Don’t Write Polars Code")


async def test_the_minute_tick_re_renders_only_now_in_this_room(
    render: Render, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A minute tick re-renders Now in this room without building the day lists again.

    It is a leaf component on `use_minute()` (D-194).
    """
    monkeypatch.setattr(status_strip, "TICK_SECONDS", 0.01)
    built: list[int] = []
    original = room_days.day_list

    def counted(*args: Any, **kwargs: Any) -> ft.ListView:
        built.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(screen, "day_list", counted)  # room.py imports the name
    room = await render(VIEW, now=SATURDAY_MORNING)
    before = len(built)
    assert before == 3  # one per day
    clock.set_test_now(datetime(2026, 5, 16, 11, 5, tzinfo=PACIFIC))  # talk over
    await room.until(lambda: room.nodes("room.now") == [])
    assert len(built) == before


@pytest.mark.parametrize(
    "now",
    [
        datetime(2026, 5, 16, 11, 5, tzinfo=PACIFIC),  # between two talks
        datetime(2026, 5, 12, 12, tzinfo=PACIFIC),  # before the conference
        datetime(2026, 10, 13, 12, tzinfo=PACIFIC),  # off season
    ],
)
async def test_with_nothing_on_there_is_no_now_section(
    render: Render, now: datetime
) -> None:
    """Between talks, before the conference and off season, there is no Now section."""
    room = await render(VIEW, now=now)
    assert room.nodes("room.now") == []
    assert not any(
        isinstance(c, ft.Text) and c.value == "Now in this room"
        for c in room.session.index.values()
    )
