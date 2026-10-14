"""Tests for the Open spaces page (``screens/open_spaces.py``; #105, EVT-01, EVT-02).

The page runs in a real Flet session over the recorded feeds (``tests/sessions.py``).
How it looks, wraps at 200 % and reads to screen readers is checked on devices (the
PR).
"""

from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import AsyncExitStack
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from typing import Any, cast

import flet as ft
import pytest

from pycon_us import clock
from pycon_us.config import load_year
from pycon_us.core.row_views import SessionView
from pycon_us.core.timefmt import day_heading
from pycon_us.core.timeline import track_sessions
from pycon_us.screens import open_spaces as screen
from pycon_us.state import Conference
from pycon_us.ui.semantics import semantics_key
from tests.feeds import processed
from tests.sessions import Shown, showing, text_of

YEAR = load_year(2026)
DATA = processed(2026)
PACIFIC = YEAR.conference.zone
VIEW = "/more/open-spaces"
SATURDAY = datetime(2026, 5, 16, 10, 0, tzinfo=PACIFIC)
OCTOBER = datetime(2026, 10, 13, 12, 0, tzinfo=PACIFIC)

type Show = Callable[..., Awaitable[Shown]]


@pytest.fixture
async def show(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Show]:
    """Return show(...): the Open spaces page over a feed, at a time."""
    async with AsyncExitStack() as stack:

        async def render(
            *,
            year: int = 2026,
            conference: Conference | None = None,
            now: datetime = OCTOBER,
        ) -> Shown:
            clock.set_test_now(now)
            if conference is None:
                conference = Conference(
                    data=processed(year), source="bundled", version=1
                )
            return await stack.enter_async_context(
                showing(
                    screen.OpenSpaces,
                    screen,
                    year=load_year(year),
                    conference=conference,
                    tmp_path=tmp_path,
                    monkeypatch=monkeypatch,
                    view_path=VIEW,
                )
            )

        try:
            yield render
        finally:
            clock.set_test_now(None)


def tabs(page: Shown) -> ft.Tabs:
    (found,) = page.find(ft.Tabs)
    return found


def tab_labels(page: Shown) -> list[tuple[str, str]]:
    """Each day tab's text and what it says to screen readers, in tab order."""
    labels: list[tuple[str, str]] = []
    for node in sorted(
        page.nodes("open_spaces.day_tab."),
        key=lambda n: int(str(n.identifier).rsplit(".", 1)[1]),
    ):
        label = node.content
        if isinstance(label, ft.Row):  # today's: the text beside its dot
            label = label.controls[0]
        text = cast(ft.Text, label)
        labels.append((str(text.value), str(text.semantics_label)))
    return labels


def open_spaces(year: int = 2026) -> list[str]:
    return [
        s.id for d in track_sessions(processed(year), "Open Space") for s in d.sessions
    ]


@pytest.mark.parametrize(
    ("year", "labels"),
    [
        (2026, ["Fri 15", "Sat 16", "Sun 17"]),
        (2025, ["Fri 16", "Sat 17", "Sun 18"]),
    ],
)
async def test_day_tabs_come_from_the_data(
    show: Show, year: int, labels: list[str]
) -> None:
    """EVT-01: a tab per day with open spaces, named by its date. Ionic called every
    day after Saturday "Sunday"."""
    page = await show(year=year)
    days = [d.day for d in track_sessions(processed(year), "Open Space")]
    assert tab_labels(page) == [
        (label, day_heading(day)) for label, day in zip(labels, days, strict=True)
    ]
    assert tabs(page).length == len(days)


async def test_it_opens_on_today_marked_as_today(show: Show) -> None:
    page = await show(now=SATURDAY)
    assert tabs(page).selected_index == 1
    assert tab_labels(page)[1] == ("Sat 16", "Saturday, May 16, today")


async def test_outside_the_conference_it_opens_on_the_first_day(show: Show) -> None:
    page = await show(now=OCTOBER)
    assert tabs(page).selected_index == 0


async def test_a_picked_day_stays_picked_across_a_render(show: Show) -> None:
    page = await show(now=SATURDAY)
    page.session.apply_patch(tabs(page)._i, {"selected_index": 2})  # as Flutter does
    await page.event(tabs(page), "change", 2)
    first = page.nodes("open_spaces.favorite.")[0]
    await page.click(cast(ft.Control, first.content))  # a render of the page
    assert tabs(page).selected_index == 2


async def test_every_open_space_is_a_row_with_its_star(show: Show) -> None:
    """D-20: the Schedule's default filter hides them; their own page never does."""
    page = await show()
    ids = open_spaces()
    assert len(ids) == 123
    rows = [str(n.identifier) for n in page.nodes("open_spaces.session.")]
    assert sorted(rows) == sorted(
        f"open_spaces.session.{semantics_key(i)}" for i in ids
    )
    assert len(page.nodes("open_spaces.favorite.")) == len(ids)


async def test_rows_sit_in_time_slots_with_the_gutter(show: Show) -> None:
    """D-31: one gutter per slot, its time a heading screen readers move by."""
    page = await show()
    starts = {
        (s.day, s.start) for d in track_sessions(DATA, "Open Space") for s in d.sessions
    }
    gutters = [n for n in page.find(ft.Semantics) if n.header and n.label]
    assert len(gutters) == len(starts)


async def test_rows_leave_out_the_open_space_badge(show: Show) -> None:
    """D-199: the page is all open spaces, so no row repeats it."""
    page = await show()
    assert "Open space" not in page.texts()
    for row in page.nodes("open_spaces.session."):
        assert not str(row.label).startswith("Open space"), row.label


async def test_a_row_pushes_its_session(show: Show) -> None:
    page = await show()
    first = open_spaces()[0]
    node = page.node(f"open_spaces.session.{semantics_key(first)}")
    await page.click(cast(ft.Control, node.parent))
    assert page.went == [f"{VIEW}/session/{first}"]


async def test_a_star_tap_re_renders_one_day_and_one_row(
    show: Show, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-153: each day is memoised and given only its own saved ids; it fails with
    ``ft.memo`` taken off ``_DayList`` or ``SessionRow``."""
    days: list[date] = []
    slots = screen.by_slot

    def counted(views: Sequence[SessionView]) -> list[Any]:
        days.append(views[0].session.day)  # each day body groups its slots once
        return slots(views)

    monkeypatch.setattr(screen, "by_slot", counted)
    page = await show()
    first = open_spaces()[0]
    star = page.node(f"open_spaces.favorite.{semantics_key(first)}")
    days.clear()
    page.rows.clear()
    await page.click(cast(ft.Control, star.content))
    assert first in page.favorites.ids
    assert days == [DATA.sessions[first].day]
    assert page.rows == [first]


async def test_each_day_starts_with_the_years_intro(show: Show) -> None:
    page = await show()
    intro = YEAR.content.open_spaces
    assert intro is not None
    lists = [v for v in page.find(ft.ListView) if str(v.key).startswith("day-")]
    assert len(lists) == 3
    for day_list in lists:
        assert text_of(day_list.controls[0]) == intro.intro


async def test_propose_opens_the_years_sign_up_in_the_in_app_browser(
    show: Show,
) -> None:
    """EVT-02, INFO-14: a link, said to leave the app."""
    page = await show()
    node = page.node("open_spaces.propose")
    assert node.link
    labelled = cast(ft.Semantics, node.content)
    assert labelled.label == "Propose an open space\nOpens in browser"
    await page.click(cast(ft.Control, labelled.content))
    copy = YEAR.content.open_spaces
    assert copy is not None
    assert page.launcher.launched == [
        (copy.propose_url, ft.LaunchMode.IN_APP_BROWSER_VIEW)
    ]
    assert page.titles[-1] == "Open spaces"


async def test_a_year_without_the_page_s_data_has_no_propose_and_no_intro(
    show: Show,
) -> None:
    """2025's year data has no ``[open_spaces]``: its sessions show alone."""
    page = await show(year=2025)
    assert page.nodes("open_spaces.propose") == []
    assert len(page.nodes("open_spaces.session.")) == len(open_spaces(2025))
    lists = [v for v in page.find(ft.ListView) if str(v.key).startswith("day-")]
    assert lists
    for day_list in lists:  # each starts with its first slot (a Row), not the intro
        assert isinstance(day_list.controls[0], ft.Row)


async def test_a_feed_without_open_spaces_offers_to_propose_one(show: Show) -> None:
    """ux.md §4.6: before the conference the feed has none."""
    sessions = {k: s for k, s in DATA.sessions.items() if s.track != "Open Space"}
    data = replace(DATA, sessions=sessions)
    page = await show(conference=Conference(data=data, version=1))
    assert page.node("open_spaces.none").live_region
    assert page.find(ft.Tabs) == []
    (button,) = page.find(ft.FilledTonalButton)
    assert text_of(button) == "Propose one"
    await page.click(button)
    assert (
        page.launcher.launched[0][0] == "https://us.pycon.org/2026/signup/open-space/"
    )


async def test_propose_one_is_a_link_said_to_leave_the_app(show: Show) -> None:
    """ux.md §4.7: the same sign-up as "+", so the same icon, words and link flag."""
    sessions = {k: s for k, s in DATA.sessions.items() if s.track != "Open Space"}
    page = await show(conference=Conference(data=replace(DATA, sessions=sessions)))
    node = page.node("open_spaces.propose_one")
    assert node.link
    (button,) = page.find(ft.FilledTonalButton)
    assert button.icon == ft.Icons.OPEN_IN_NEW
    assert isinstance(button.content, ft.Text)
    assert button.content.semantics_label == "Propose one\nOpens in browser"


async def test_a_year_without_a_sign_up_offers_no_button(show: Show) -> None:
    """D-175: with nowhere to propose, the sentence alone; the app refreshes itself."""
    data = processed(2025)
    sessions = {k: s for k, s in data.sessions.items() if s.track != "Open Space"}
    conference = Conference(data=replace(data, sessions=sessions))
    page = await show(year=2025, conference=conference)
    assert page.node("open_spaces.none").live_region
    assert page.find(ft.FilledTonalButton) == []


async def test_without_data_it_loads_then_offers_to_try_again(show: Show) -> None:
    """ux.md §4.1: the skeleton until the first fetch has failed, then the way out."""
    loading = await show(conference=Conference())
    assert "Loading schedule" in [n.label for n in loading.find(ft.Semantics)]
    failed = await show(conference=Conference(problem="offline"))
    assert failed.node("open_spaces.no_data").live_region
    assert failed.nodes("open_spaces.propose")  # the year still says where


def test_the_opening_day_is_today_with_open_spaces_else_the_first() -> None:
    days = [date(2026, 5, 15), date(2026, 5, 16), date(2026, 5, 17)]
    assert screen.opening_day(days, date(2026, 5, 16)) == date(2026, 5, 16)
    assert screen.opening_day(days, date(2026, 5, 14)) == date(2026, 5, 15)
    assert screen.opening_day(days, date(2026, 10, 13)) == date(2026, 5, 15)
