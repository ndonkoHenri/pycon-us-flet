"""Tests for session detail (SESS-01, -02; ux.md §5.5): the header, When and where.

The speakers and the description are ``test_session_people.py``'s; the registration
card, the app bar, the states and the change badges ``test_session_actions.py``'s;
Share, the posters and an open space's extras ``test_session_extras.py``'s.

``SessionDetail`` runs in a real Flet session (``tests/session_detail.py``), as the
rows do in ``test_session_rows.py``. How the screen looks, at 200 % text and in dark
mode, is checked on devices (the PR); here, what it says and what a tap does.
"""

import asyncio
from collections.abc import Callable
from typing import Any, cast
from urllib.parse import quote

import flet as ft
import pytest

from pycon_us import clock
from pycon_us.prefs import Prefs
from pycon_us.services import Services
from tests import session_detail
from tests.folds import Fold, fold_named
from tests.session_detail import (
    BREAK,
    JOB_FAIR,
    LIGHTNING,
    TALK,
    TUTORIAL,
    VIEW,
    Detail,
    Render,
    at,
    words,
)
from tests.trees import descendants, texts

# The detail's fixture, shared by name: pytest finds fixtures among a module's names.
render = session_detail.render

# ------------------------------------------------------------------ header (SESS-01)


async def test_the_title_is_the_page_s_selectable_heading(render: Render) -> None:
    """The title is a selectable level-1 headline in the body; the app bar has none."""
    detail = await render(TALK)
    title = detail.node("session.title")
    assert (title.header, title.heading_level) == (True, 1)
    text = cast(ft.Text, title.content)
    assert text.value.startswith("Python for Humans")  # pyright: ignore[reportOptionalMemberAccess]
    assert (text.theme_style, text.selectable) == (
        ft.TextThemeStyle.HEADLINE_SMALL,
        True,
    )
    assert detail.titles[-1] == ""  # the heading names the page, not the app bar


async def test_at_large_text_the_title_steps_down_and_back(render: Render) -> None:
    """D-328: where a slot's time leaves the gutter, the title takes a row title's type.

    It follows a text size change while the page is open, and stays the selectable
    level-1 heading at either size.
    """
    detail = await render(TALK)

    def title() -> ft.Text:
        node = detail.node("session.title")
        assert (node.header, node.heading_level) == (True, 1)
        return cast(ft.Text, node.content)

    detail.prefs.time_above = True  # what GutterProbe measures at that size
    await detail.settle()
    assert (title().theme_style, title().selectable) == (
        ft.TextThemeStyle.TITLE_MEDIUM,
        True,
    )
    detail.prefs.time_above = False
    await detail.settle()
    assert title().theme_style == ft.TextThemeStyle.HEADLINE_SMALL


async def test_the_badges_come_before_the_title(render: Render) -> None:
    """A tutorial's badges wrap in a row above its title, in one group with it."""
    detail = await render(TUTORIAL)
    header = detail.node("session.title").parent
    assert isinstance(header, ft.Column)
    badges = header.controls[0]
    assert isinstance(badges, ft.Row) and badges.wrap
    assert texts(badges) == ["Tutorial", "Registration required"]
    assert header.spacing == 8  # one group (ux.md §3.6)


async def test_a_badge_that_repeats_the_title_is_left_out(render: Render) -> None:
    """A break's "Break" pill over its "Break" heading said nothing more."""
    detail = await render(BREAK)
    header = detail.node("session.title").parent
    assert isinstance(header, ft.Column)
    assert header.controls == [detail.node("session.title")]


async def test_the_sections_are_level_2_under_the_title(render: Render) -> None:
    """ux.md §5.5: the title is heading level 1, its sections level 2."""
    detail = await render(TALK)
    speakers = next(
        n
        for n in detail.session.index.values()
        if isinstance(n, ft.Semantics) and n.header and words(n) == ["Speakers"]
    )
    assert speakers.heading_level == 2


# ------------------------------------------------------------------ when (SESS-01)


@pytest.mark.parametrize(
    ("now", "label", "spoken"),
    [
        ("2026-05-16 10:05", "Starts in 25 min", "Starts in 25 minutes"),
        ("2026-05-16 08:25", "Starts in 2 h 5 min", "Starts in 2 hours 5 minutes"),
        ("2026-05-16 10:30", "Happening now", "Happening now"),
        ("2026-05-16 10:59", "Happening now", "Happening now"),
        ("2026-05-16 11:00", "Ended", "Ended"),  # at the end it is over (D-179)
        ("2026-05-18 09:00", "Ended", "Ended"),
    ],
)
async def test_the_time_tile_says_where_the_session_stands(
    render: Render, now: str, label: str, spoken: str
) -> None:
    """The When tile shows the countdown, "Happening now" or "Ended", spoken in full."""
    clock.set_test_now(at(now))
    detail = await render(TALK)
    status = [
        node
        for node in detail.session.index.values()
        if isinstance(node, ft.Text) and node.value == label
    ]
    assert [node.semantics_label for node in status] == [spoken]
    assert label in detail.text("session.when")


async def test_the_day_before_there_is_no_countdown(render: Render) -> None:
    """The day before: the date, then the range read with "to", and no countdown."""
    clock.set_test_now(at("2026-05-15 18:00"))
    detail = await render(TALK)
    lines = detail.text("session.when")
    # The date says when; the range has a line of its own, its "AM" kept to it.
    assert lines[:2] == ["Saturday, May 16", "10:30–11:00\u00a0AM"]
    assert not any(line.startswith("Starts") for line in lines)
    time = next(
        t
        for t in descendants(detail.node("session.when"))
        if isinstance(t, ft.Text) and t.value == lines[1]
    )
    assert time.semantics_label == "10:30 to 11:00 AM"  # "to", not a dash


@pytest.mark.parametrize(
    ("now", "label"),
    [("2026-05-17 09:20", "Starts in 10 min"), ("2026-05-17 09:45", "Happening now")],
)
async def test_the_status_follows_the_start_the_tile_shows(
    render: Render, now: str, label: str
) -> None:
    """The Job Fair opens at 9:30, though the Schedule groups it at 10:00 (DATA-11)."""
    clock.set_test_now(at(now))
    detail = await render(JOB_FAIR)
    lines = detail.text("session.when")
    assert lines[1].startswith("9:30")
    assert label in lines


async def test_with_nothing_to_add_the_time_tile_has_no_blank_line(
    render: Render,
) -> None:
    """Another day on Pacific time: no status, no note, so no subtitle's height."""
    clock.set_test_now(at("2026-05-15 18:00"))
    detail = await render(TALK)
    tile = next(
        n
        for n in descendants(detail.node("session.when"))
        if isinstance(n, ft.ListTile)
    )
    assert tile.subtitle is None


async def test_the_status_follows_the_clock_on_the_minute_tick(
    render: Render, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-40: the line re-renders itself as time passes, under the fake clock too."""
    clock.set_test_now(at("2026-05-16 10:29"))
    ticks: list[Callable[[], object]] = []

    async def run_every(self: Services, seconds: float, action: Callable[[], object]):
        ticks.append(action)
        action()

    monkeypatch.setattr(Services, "run_every", run_every)
    detail = await render(TALK)
    assert "Starts in 1 min" in detail.text("session.when")
    clock.set_test_now(at("2026-05-16 10:31"))
    for tick in ticks:  # the status line's, and the Changed badges' (D-315)
        tick()
    await detail.settle()
    assert "Happening now" in detail.text("session.when")


async def test_leaving_the_detail_stops_its_minute_ticks(
    render: Render, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F2: leaving the detail cancels its ticking loops, with no cleanup (D-387)."""
    loops: list[asyncio.Task[Any]] = []

    async def run_every(self: Services, seconds: float, action: Callable[[], object]):
        loops.append(cast(asyncio.Task[Any], asyncio.current_task()))
        await asyncio.Event().wait()  # until cancelled

    monkeypatch.setattr(Services, "run_every", run_every)
    detail = await render(TALK)
    assert loops  # the status line's, and the Changed badges' (D-315)
    assert not any(loop.done() for loop in loops)
    await detail.show(None)
    assert all(loop.cancelled() for loop in loops)


async def test_a_device_in_another_zone_gets_the_pacific_time_note(
    render: Render, machine_tz: str
) -> None:
    """D-35: say the times are conference time when the device's clock differs."""
    detail = await render(TALK)
    note = "Times are Pacific Time (PDT)"
    expected = machine_tz != "America/Los_Angeles"
    assert (note in detail.text("session.when")) is expected


# ------------------------------------------------------------------ where (SESS-02)


async def test_the_room_tile_pushes_the_room_with_the_session_highlighted(
    render: Render,
) -> None:
    """The room tile pushes room detail highlighting the session; one room, no fold."""
    detail = await render(TALK)
    room = detail.node("session.room")
    assert words(room) == ["Grand Ballroom A"]
    tile = next(n for n in descendants(room) if isinstance(n, ft.ListTile))
    await detail.click(tile)
    assert detail.pushed == [f"{VIEW}/room/grand-ballroom-a?highlight={TALK}"]
    assert detail.nodes("session.other_rooms") == []  # one room, nothing folded


def other_rooms(detail: Detail) -> Fold:
    """Return the fold of the detail's other rooms, ``session.other_rooms``."""
    return fold_named(detail.find(ft.Container), "session.other_rooms")


async def test_a_streamed_session_folds_its_other_rooms(render: Render) -> None:
    """A streamed session shows its main room and folds the four others.

    The first folded room is a link to its room detail, highlighting the session.
    """
    detail = await render(LIGHTNING)
    assert words(detail.node("session.room")) == ["Pacific Ballroom - Arena"]
    folded = other_rooms(detail)
    assert cast(ft.Text, folded.title).value == "+4 more rooms"
    assert folded.said == "Collapsed"
    rooms = folded.controls
    assert [words(room) for room in rooms] == [
        ["Room 103ABC"],
        ["Room 104AB"],
        ["Grand Ballroom A"],
        ["Grand Ballroom B"],
    ]
    tile = next(n for n in descendants(rooms[0]) if isinstance(n, ft.ListTile))
    await detail.click(tile)
    assert detail.pushed == [f"{VIEW}/room/room-103abc?highlight={LIGHTNING}"]


async def test_the_folded_rooms_stay_open_once_opened(render: Render) -> None:
    """Coming back from a room's detail re-rendered the tile folded (iOS simulator)."""
    detail = await render(LIGHTNING)
    folded = other_rooms(detail)
    assert folded.expanded is False
    await detail.click(folded.header)
    folded = other_rooms(detail)
    assert folded.expanded is True
    assert folded.said == "Expanded"


async def test_a_break_in_many_rooms_lists_them_without_one_place(
    render: Render,
) -> None:
    """A break has no main room: "In 5 rooms" folds them.

    The first folded room's link quotes the break's id.
    """
    detail = await render(BREAK)
    assert detail.nodes("session.room") == []
    folded = other_rooms(detail)
    assert cast(ft.Text, folded.title).value == "In 5 rooms"
    first = folded.controls[0]
    await detail.click(
        next(n for n in descendants(first) if isinstance(n, ft.ListTile))
    )
    # Its id holds spaces, commas and colons: quoted, so room detail reads it whole.
    assert detail.pushed == [
        f"{VIEW}/room/room-103abc?highlight={quote(BREAK, safe='')}"
    ]


async def test_reduced_motion_opens_the_rooms_without_animation(
    render: Render, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With reduced motion, the folded rooms open with a 0 ms animation."""
    monkeypatch.setattr(Prefs, "motion_ms", lambda self, ms: 0)
    detail = await render(LIGHTNING)
    assert other_rooms(detail).animation.duration == 0
