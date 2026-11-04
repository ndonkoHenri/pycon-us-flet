"""Tests for the sections the Now tab shows in each season (#95; D-14, ux.md §5.1).

The screen runs in `tests/now_view.py`'s harness at fixed times of the 2026 feed.
"""

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from typing import Any

import flet as ft

from pycon_us.core.agenda import Phase, now_next
from pycon_us.core.models import ConferenceData
from pycon_us.prefs import Prefs
from pycon_us.state import Conference
from pycon_us.ui.buttons import LABEL_PADDING
from tests import now_view
from tests.now_view import (
    FIRST_AT_11,
    OPEN_SPACE,
    PACIFIC,
    TALK,
    _texts,
    _walk,
    header,
    may,
)

data, render = (now_view.data, now_view.render)


async def test_before_the_conference_it_counts_down_and_lists_the_key_dates(
    render: Callable[..., Any],
) -> None:
    """Weeks before, Now counts down, lists the key dates and links the Schedule."""
    shown = await render(datetime(2026, 4, 20, 9, tzinfo=PACIFIC))
    assert header(shown).startswith("PyCon US 2026. Starts in 23 days.")
    assert shown.headings() == ["Key dates"]
    texts = shown.texts()
    for line in (
        "Tutorials and talks",
        "Wed, May 13 – Sun, May 17",
        "Sprints",
        "Mon, May 18 – Tue, May 19",
        "Long Beach Convention Center",
        "Long Beach, CA",
    ):
        assert line in texts
    assert shown.listed() == []  # nothing is on or next for weeks
    button = shown.node("now.build_schedule").content
    assert isinstance(button, ft.FilledTonalButton)
    assert button.style is not None  # its sides stay 24 dp at large text (D-344)
    assert button.style.padding == LABEL_PADDING
    assert button.elevation == 0  # flat, as M3's tonal button
    await shown.click(button)
    assert shown.went == ["/schedule"]


async def test_the_header_is_the_first_heading_under_the_page_s_title(
    render: Callable[..., Any],
) -> None:
    """The header is the body's first control: a level-2 heading, read once."""
    shown = await render(may(15, 11, 10))
    node = shown.node("now.header")
    # Level 2: the bar's "Now" is the page's one level-1 heading (F40, D-211).
    assert node.header is True and node.heading_level == 2
    assert node.exclude_semantics is True  # read once, as its phrase
    assert shown.body.controls[0] is node


async def test_on_a_conference_day_it_shows_what_is_on_then_what_is_next(
    render: Callable[..., Any],
) -> None:
    """On a conference day, Now shows your next session, what is on, then Up next."""
    shown = await render(may(15, 11, 10))
    assert shown.headings() == [
        "Your next session",
        "Happening now",
        "Up next · 11:30 AM",
    ]
    assert shown.listed() == [*FIRST_AT_11, "27"]  # folded at a peak (D-327)
    assert "Starts in 20 min" in shown.texts()
    assert "See the rest of today in Schedule" in shown.texts()


async def test_up_next_s_heading_reads_its_dot_as_a_pause(
    render: Callable[..., Any],
) -> None:
    """Up next's heading reads "Up next, 11:30 AM" to a screen reader."""
    shown = await render(may(15, 11, 10))
    (heading,) = [
        c
        for c in shown.all()
        if isinstance(c, ft.Text) and c.value == "Up next · 11:30 AM"
    ]
    assert heading.semantics_label == "Up next, 11:30 AM"


async def test_happening_now_ignores_the_schedule_s_filters(
    render: Callable[..., Any],
) -> None:
    """Open spaces are hidden on the Schedule by default (D-20), never here."""
    shown = await render(may(15, 11, 10))
    assert "Open Space" in Prefs().excluded_tracks
    await shown.show_all()
    assert OPEN_SPACE in shown.listed()


async def test_saved_sessions_come_first_in_happening_now(
    render: Callable[..., Any],
) -> None:
    """Of two saved sessions on, one is the card's and the other leads Happening now."""
    shown = await render(may(15, 11, 10), saved=(OPEN_SPACE, "9072"))
    (mine,) = shown.listed("now.next.session.")  # one of the two, in the card
    (other,) = {OPEN_SPACE, "9072"} - {mine}
    # The saved one, then the first three others (D-327).
    assert shown.listed()[:4] == [other, *FIRST_AT_11]


async def test_each_session_on_shows_and_says_how_much_has_passed(
    render: Callable[..., Any],
) -> None:
    """Each session on has a bar and says the percent elapsed; Up next has neither."""
    shown = await render(may(15, 11, 10))
    await shown.show_all()
    talk = shown.node("now.session.4")  # 11:00-11:30: 10 of 30 minutes
    assert str(talk.label).endswith(" 33 percent elapsed.")
    bars = [c for c in _walk(talk) if isinstance(c, ft.ProgressBar)]
    assert [bar.value for bar in bars] == [0.33]
    assert bars[0].bar_height == 3
    open_space = shown.node(f"now.session.{OPEN_SPACE}")  # 11:00-12:00
    assert str(open_space.label).endswith(" 16 percent elapsed.")
    # Up next has not started: no bar.
    up_next = shown.node("now.session.27")
    assert not [c for c in _walk(up_next) if isinstance(c, ft.ProgressBar)]
    assert "elapsed" not in str(up_next.label)


async def test_between_two_slots_it_says_nothing_is_on(
    render: Callable[..., Any],
) -> None:
    """Between two slots, Happening now says "Nothing in session right now"."""
    shown = await render(may(15, 7, 45))  # registration opened at 7:30 (a notice)
    assert shown.headings() == [
        "Your next session",
        "Happening now",
        "Up next · 8:00 AM",
    ]
    assert "Nothing in session right now" in shown.texts()


async def test_before_a_day_starts_it_shows_what_is_first_up(
    render: Callable[..., Any],
) -> None:
    """Before a day starts, the header says when it does, and Up next lists it."""
    shown = await render(may(15, 6))
    assert "First up today at 7:30 AM" in header(shown)
    assert shown.headings() == ["Your next session", "Up next · 7:30 AM"]


async def test_after_a_day_it_wraps_up_and_points_at_tomorrow(
    render: Callable[..., Any],
) -> None:
    """After a day ends, Now says it is a wrap, and Up next names tomorrow."""
    shown = await render(may(15, 21))
    assert "That's a wrap for today" in header(shown)
    assert shown.headings() == ["Your next session", "Up next · tomorrow at 7:00 AM"]
    # The Schedule opens on today: the link does not promise tomorrow.
    assert "Open the schedule" in shown.texts()
    assert "See the rest of today in Schedule" not in shown.texts()


async def test_in_the_evening_saved_sessions_are_for_a_later_day(
    render: Callable[..., Any],
) -> None:
    """At 9 PM "nothing in the next 3 hours" is true but odd: the day is over."""
    shown = await render(may(15, 21), saved=(TALK,))  # tomorrow morning
    tile = shown.node("now.next_session")
    assert _texts(tile)[:2] == [
        "Nothing more saved for today",
        "See your saved sessions in My schedule",
    ]


async def test_after_the_last_session_the_sprints_are_next(
    render: Callable[..., Any],
) -> None:
    """After the last session and on sprint days, Now shows the sprints' tile alone."""
    for now in (may(17, 21), may(18, 10)):
        shown = await render(now)
        assert shown.headings() == []
        assert shown.listed() == []
        sprints = shown.node("now.sprints")
        assert _texts(sprints) == ["Sprints", "Join a project · May 18–19"]
        (subtitle,) = [c for c in _walk(sprints) if isinstance(c, ft.Text)]
        assert subtitle.semantics_label == "Join a project, May 18 to 19"


async def test_in_the_last_slot_of_the_conference_the_schedule_is_still_linked(
    render: Callable[..., Any], data: ConferenceData
) -> None:
    """In the conference's last slot, the card's tile and the Schedule link stay.

    Without Sunday's 8 PM notice, the 5:05 PM Closing is the last slot: there is no Up
    next, but the day still runs.
    """
    sunday = data.days[-1]
    trimmed = replace(
        data, days=(*data.days[:-1], replace(sunday, groups=sunday.groups[:-1]))
    )
    now = may(17, 17, 10)
    assert now_next(trimmed, now).phase is Phase.DAY
    assert now_next(trimmed, now).up_next is None
    conference = Conference(data=trimmed, source="bundled", version=1, fetched_at=now)
    shown = await render(now, conference=conference)
    assert shown.headings() == ["Your next session", "Happening now"]
    assert _texts(shown.node("now.next_session"))[0] == "Nothing saved yet"
    assert "See the rest of today in Schedule" in shown.texts()


async def test_after_the_sprints_it_says_see_you_next_year(
    render: Callable[..., Any],
) -> None:
    """After the sprints, Now says see you next year and links back to the schedule."""
    shown = await render(may(25, 10))
    assert header(shown).startswith("PyCon US 2026. See you next year.")
    assert not shown.has("now.sprints")
    assert _texts(shown.node("now.schedule")) == ["Look back at the schedule"]
