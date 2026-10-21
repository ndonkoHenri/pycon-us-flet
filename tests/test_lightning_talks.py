"""Tests for the Lightning talks page (``screens/lightning_talks.py``; #105, EVT-03).

The page runs in a real Flet session over the recorded feeds (``tests/sessions.py``).
How it looks, wraps at 200 % and reads to screen readers is checked on devices (the
PR).
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from dataclasses import replace
from pathlib import Path
from typing import cast

import flet as ft
import pytest

from pycon_us.config import load_year
from pycon_us.core.timefmt import day_heading
from pycon_us.core.timeline import track_sessions
from pycon_us.screens import lightning_talks as screen
from pycon_us.state import Conference
from pycon_us.ui.semantics import semantics_key
from tests.feeds import processed
from tests.folds import folds
from tests.sessions import Shown, showing, text_of

YEAR = load_year(2026)
COPY = YEAR.content.lightning_talks
DATA = processed(2026)
VIEW = "/more/lightning-talks"

type Show = Callable[..., Awaitable[Shown]]


@pytest.fixture
async def show(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Show]:
    """Return a function that renders the Lightning talks page over a year's feed."""
    async with AsyncExitStack() as stack:

        async def render(
            *, year: int = 2026, conference: Conference | None = None
        ) -> Shown:
            if conference is None:
                conference = Conference(
                    data=processed(year), source="bundled", version=1
                )
            return await stack.enter_async_context(
                showing(
                    screen.LightningTalks,
                    screen,
                    year=load_year(year),
                    conference=conference,
                    tmp_path=tmp_path,
                    monkeypatch=monkeypatch,
                    view_path=VIEW,
                )
            )

        yield render


def talks(year: int = 2026) -> list[str]:
    """The ids of the year's lightning talks, in the track page's order."""
    data = processed(year)
    return [s.id for d in track_sessions(data, "Lightning-talks") for s in d.sessions]


async def test_the_card_holds_the_years_copy_and_the_sign_up(show: Show) -> None:
    """EVT-03: the copy is year data (D-45), never code."""
    assert COPY is not None
    page = await show()
    texts = page.texts()
    assert COPY.heading in texts
    assert all(paragraph in texts for paragraph in COPY.intro)
    headings = [
        text_of(n) for n in page.find(ft.Semantics) if n.header and n.heading_level
    ]
    assert headings[0] == COPY.heading
    assert page.titles[-1] == "Lightning talks"


async def test_the_card_s_heading_is_read_alone_before_its_paragraphs(
    show: Show,
) -> None:
    """D-211: a Card merges what it holds into one node, a heading over the whole card.

    So the card is no node of its own, and the heading and the paragraphs are each a
    container, the heading first.
    """
    assert COPY is not None
    page = await show()
    (card,) = page.find(ft.Card)
    assert card.semantic_container is False
    column = cast(ft.Column, cast(ft.Container, card.content).content)
    heading, paragraphs = column.controls[:2]
    assert isinstance(heading, ft.Semantics) and heading.header and heading.container
    assert text_of(heading) == COPY.heading
    assert isinstance(paragraphs, ft.Semantics) and paragraphs.container
    assert not paragraphs.header
    lines = cast(ft.Column, paragraphs.content).controls
    assert [cast(ft.Text, line).value for line in lines] == list(COPY.intro)


async def test_sign_up_opens_the_years_sign_up_in_the_in_app_browser(
    show: Show,
) -> None:
    """INFO-14: a link, said to leave the app."""
    assert COPY is not None
    page = await show()
    node = page.node("lightning_talks.sign_up")
    assert node.link
    button = cast(ft.FilledButton, node.content)
    assert cast(ft.Text, button.content).semantics_label == (
        "Sign up for a lightning talk\nOpens in browser"
    )
    # Room above and below a label that wraps at 200 %; still 40 dp on one line.
    assert button.style is not None
    padding = cast(ft.Padding, button.style.padding)
    assert padding.top == padding.bottom == 10
    await page.click(button)
    assert page.launcher.launched == [
        (COPY.signup_url, ft.LaunchMode.IN_APP_BROWSER_VIEW)
    ]


def doubt_texts(control: ft.Control) -> list[str]:
    """A doubt's node: its texts, the doubt then the answer."""
    column = cast(
        ft.Column, cast(ft.Container, cast(ft.Semantics, control).content).content
    )
    return [str(cast(ft.Text, text).value) for text in column.controls]


async def test_think_you_cant_do_one_starts_folded_and_opens(show: Show) -> None:
    """EVT-03: a collapsed ``FoldTile``, controlled so a render keeps it open."""
    page = await show()
    (fold,) = folds(page.find(ft.Container))
    assert text_of(fold.title) == "Think you can't do one?"
    assert fold.identifier == "lightning_talks.doubts"  # on its header (D-354)
    # A row's title, as the link row under it, not a heading's size (ux.md §5.11).
    title = cast(ft.Text, fold.title)
    assert title.theme_style is None
    assert fold.expanded is False
    await page.click(fold.header)
    (fold,) = folds(page.find(ft.Container))
    assert fold.expanded is True
    star = page.nodes("lightning_talks.favorite.")[0]
    await page.click(cast(ft.Control, star.content))  # a render of the page
    (fold,) = folds(page.find(ft.Container))
    assert fold.expanded is True


async def test_each_doubt_reads_as_one_node_with_its_answer(show: Show) -> None:
    """Each doubt under the fold is one node: the doubt, then its answer."""
    assert COPY is not None
    page = await show()
    (fold,) = folds(page.find(ft.Container))
    controls = fold.controls
    assert all(cast(ft.Semantics, c).container for c in controls)
    assert [doubt_texts(c) for c in controls] == [
        [d.doubt, d.answer] for d in COPY.doubts
    ]


async def test_more_about_lightning_talks_opens_the_sites_page(show: Show) -> None:
    """The us.pycon.org row is a link opening the site's page in the in-app browser."""
    assert COPY is not None
    page = await show()
    assert page.node("lightning_talks.more_info").link
    (tile,) = [t for t in page.find(ft.ListTile) if t.subtitle == "us.pycon.org"]
    await page.click(tile)
    assert page.launcher.launched == [
        (COPY.info_url, ft.LaunchMode.IN_APP_BROWSER_VIEW)
    ]


async def test_the_talks_are_listed_by_day_each_with_its_star(show: Show) -> None:
    """EVT-03: the sessions on the same page, under a level-2 heading per day."""
    page = await show()
    ids = talks()
    assert len(ids) == 4
    rows = [str(n.identifier) for n in page.nodes("lightning_talks.session.")]
    assert rows == [f"lightning_talks.session.{semantics_key(i)}" for i in ids]
    assert len(page.nodes("lightning_talks.favorite.")) == 4
    days = [
        text_of(n) for n in page.find(ft.Semantics) if n.header and n.heading_level == 2
    ]
    assert COPY is not None
    assert days == [
        COPY.heading,
        *(day_heading(d.day) for d in track_sessions(DATA, "Lightning-talks")),
    ]


async def test_rows_leave_out_the_lightning_talks_badge(show: Show) -> None:
    """D-199: the page is all lightning talks, so no row repeats it.

    The badge's text and its place at the head of the phrase are checked, not the
    session's name, which differs from the badge's only by a letter's case.
    """
    page = await show()
    badge = YEAR.conference.track_name("Lightning-talks")
    assert badge not in page.texts()
    rows = page.nodes("lightning_talks.session.")
    assert rows
    for row in rows:
        assert f"{badge}." not in str(row.label), row.label


async def test_a_row_pushes_its_session_and_a_star_saves_it(show: Show) -> None:
    """A row pushes its session; its star saves it, re-rendering that row alone."""
    page = await show()
    first = talks()[0]
    node = page.node(f"lightning_talks.session.{semantics_key(first)}")
    await page.click(cast(ft.Control, node.parent))
    assert page.went == [f"{VIEW}/session/{first}"]
    star = page.node(f"lightning_talks.favorite.{semantics_key(first)}")
    page.rows.clear()
    await page.click(cast(ft.Control, star.content))
    assert first in page.favorites.ids
    assert page.rows == [first]  # one row of one memoised day (D-153)


async def test_a_year_without_the_copy_shows_its_talks_alone(show: Show) -> None:
    """2025's year data has no ``[lightning_talks]``."""
    page = await show(year=2025)
    assert page.find(ft.Card) == []
    assert folds(page.find(ft.Container)) == []
    assert len(page.nodes("lightning_talks.session.")) == len(talks(2025)) == 4


async def test_without_data_the_copy_stays_and_the_talks_load(show: Show) -> None:
    """ux.md §4.1: the copy is bundled; the sessions load and fail as the Schedule's."""
    loading = await show(conference=Conference())
    assert loading.nodes("lightning_talks.sign_up")
    assert "Loading schedule" in [n.label for n in loading.find(ft.Semantics)]
    failed = await show(conference=Conference(problem="offline"))
    assert failed.node("lightning_talks.no_data").live_region


async def test_a_feed_without_lightning_talks_says_so(show: Show) -> None:
    """A feed with no lightning talks shows the empty state's live region, no rows."""
    sessions = {k: s for k, s in DATA.sessions.items() if s.track != "Lightning-talks"}
    data = replace(DATA, sessions=sessions)
    page = await show(conference=Conference(data=data, version=1))
    assert page.node("lightning_talks.empty").live_region
    assert page.nodes("lightning_talks.session.") == []
