"""Tests for the Keynotes page and its cards (``screens/keynotes.py``, ``keynote_card.py``).

SPKR-04, #104, D-217. The page runs in a real Flet session over the recorded feeds
(``tests/sessions.py``). How it looks, wraps at 200 % and reads to screen readers is
checked on devices (the PR).
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import flet as ft
import pytest

from pycon_us.config import YearData, load_year
from pycon_us.core.models import Session
from pycon_us.core.timeline import keynote_sessions
from pycon_us.screens import keynote_card
from pycon_us.screens import keynotes as screen
from pycon_us.screens.keynote_card import (
    CLAMP_LINES,
    TALK_TITLE,
    card_text,
    clamps,
)
from pycon_us.screens.tracks import track_count
from pycon_us.state import Conference
from pycon_us.year_keynotes import keynote_of
from tests.feeds import processed
from tests.sessions import Shown, showing, text_of
from tests.trees import descendants, texts

YEAR = load_year(2026)
KEYNOTES = YEAR.content.keynotes
DATA = processed(2026)
VIEW = "/more/keynotes"
IDS = [k.session_id for k in KEYNOTES]

type Show = Callable[..., Awaitable[Shown]]


@pytest.fixture
async def show(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Show]:
    """Return show(...): the Keynotes page over a feed."""
    async with AsyncExitStack() as stack:

        async def render(
            *,
            year: int = 2026,
            year_data: YearData | None = None,
            conference: Conference | None = None,
            view_path: str = VIEW,
        ) -> Shown:
            if conference is None:
                conference = Conference(
                    data=processed(year), source="bundled", version=1
                )
            return await stack.enter_async_context(
                showing(
                    screen.Keynotes,
                    screen,
                    year=year_data or load_year(year),
                    conference=conference,
                    tmp_path=tmp_path,
                    monkeypatch=monkeypatch,
                    view_path=view_path,
                )
            )

        yield render


def card_ids(page: Shown) -> list[str]:
    """The sessions of the cards, in order: their tiles' identifiers."""
    return [
        str(n.identifier).removeprefix("keynotes.session.")
        for n in page.nodes("keynotes.session.")
    ]


# ------------------------------------------------------------------ the list


def test_the_page_lists_the_keynotes_and_the_panels_in_time_order() -> None:
    """SPKR-04: the feed's keynotes, and the panels the year data names (plenaries)."""
    sessions = keynote_sessions(DATA, "Keynote", IDS)
    assert [s.id for s in sessions] == ["153", "164", "165", "176", "182", "183"]
    assert {s.track for s in sessions} == {"Keynote", "Plenary"}


def test_a_keynote_without_year_data_is_listed_too() -> None:
    """A keynote announced after the build still gets a card, with its name."""
    assert [s.id for s in keynote_sessions(DATA, "Keynote", [])] == [
        "153",
        "165",
        "176",
        "182",
    ]


def test_the_hubs_keynotes_row_counts_what_the_page_lists() -> None:
    """D-199's rule: a hub row's count is its page's; the panels are on it (D-217)."""
    assert track_count(DATA, "Keynote", IDS) == 6
    assert track_count(DATA, "Keynote") == 4
    assert track_count(DATA, "Talk", IDS) == track_count(DATA, "Talk")


async def test_one_card_per_session_with_its_people(show: Show) -> None:
    page = await show()
    assert card_ids(page) == ["153", "164", "165", "176", "182", "183"]
    assert page.titles[-1] == "Keynotes"
    headings = [
        (text_of(n), n.heading_level)
        for n in page.find(ft.Semantics)
        if n.header and n.heading_level
    ]
    # A keynote's people are its headings; a panel's own title is its heading.
    assert headings == [
        ("Lin Qiao", 2),
        ("Python is for Everyone: Growing the Community Without Limits", 2),
        ("Pablo Galindo Salgado", 2),
        ("amanda casari", 2),
        ("Rachell Calhoun", 2),
        ("Tim Schilling", 2),
        ("Python Steering Council", 2),
    ]
    shown = page.texts()
    assert "CEO and co-founder, Fireworks AI" in shown  # the role
    assert "Djangonaut Space" in shown  # the talk's own title
    assert "Diversity & Inclusion Panel" in shown  # the feed's name, over the title


async def test_a_talks_title_is_in_one_type_on_every_card(show: Show) -> None:
    """#281: a panel's title in TITLE_LARGE broke inside "Community" at iOS's largest
    text; a talk's title, a keynote's or a panel's, is TALK_TITLE, and only people's
    names, whose words are short, are TITLE_LARGE."""
    page = await show()
    titles = {str(k.title) for k in KEYNOTES if k.title}  # the year data's own
    styles = {
        str(t.value): t.theme_style for t in page.find(ft.Text) if t.value in titles
    }
    assert set(styles) == titles
    assert set(styles.values()) == {TALK_TITLE} == {ft.TextThemeStyle.TITLE_MEDIUM}
    # The other headings are keynote speakers' names.
    names = [
        cast(ft.Text, n.content).theme_style
        for n in page.nodes("keynotes.name.")
        if text_of(n) not in titles
    ]
    assert names and set(names) == {ft.TextThemeStyle.TITLE_LARGE}


async def test_the_photos_are_decorative_with_the_initials_under_them(
    show: Show,
) -> None:
    """The name beside the photo says who; the initials show until it loads."""
    page = await show()
    avatars = page.find(ft.CircleAvatar)
    lin = next(a for a in avatars if "lin_qiao" in str(a.foreground_image_src))
    assert lin.radius == 48  # the 96 dp photo of ux.md §5.11
    assert text_of(lin) == "LQ"
    assert isinstance(lin.parent, ft.Semantics) and lin.parent.exclude_semantics


async def test_a_panel_shows_its_people_as_a_row_of_photos(show: Show) -> None:
    page = await show()
    council = keynote_of(KEYNOTES, "183")
    assert council is not None

    def names(row: ft.Row) -> list[str]:
        return [
            str(t.value)
            for t in descendants(row)
            if isinstance(t, ft.Text)
            and t.theme_style == ft.TextThemeStyle.BODY_SMALL
            # Its own width, so the largest text never breaks a surname in two.
            and t.width is None
        ]

    rows = [r for r in page.find(ft.Row) if r.wrap and names(r)]
    assert [names(r) for r in rows] == [
        [p.name for p in keynote.speakers]
        for keynote in KEYNOTES
        if keynote.kind == "panel"
    ]
    panel = rows[-1]
    radii = [a.radius for a in descendants(panel) if isinstance(a, ft.CircleAvatar)]
    assert radii == [32] * 5  # 64 dp photos
    # Each person is one stop, read as the name.
    assert all(isinstance(c, ft.MergeSemantics) for c in panel.controls)


# ------------------------------------------------------------------ the clamp


def test_a_keynotes_card_cuts_its_bios_and_a_panels_its_abstract() -> None:
    lin = keynote_of(KEYNOTES, "153")
    together = keynote_of(KEYNOTES, "182")
    panel = keynote_of(KEYNOTES, "164")
    assert lin is not None and together is not None and panel is not None
    assert card_text(lin) == lin.speakers[0].bio
    assert card_text(together) == "\n\n".join(p.bio for p in together.speakers)
    assert card_text(panel) == panel.abstract
    assert all(clamps(card_text(k)) for k in KEYNOTES)
    # Short enough to show whole even at 200 % text: no "Read more" to tap.
    assert not clamps("Python Steering Council member.")
    assert clamps("one\ntwo")


def bio(page: Shown, session_id: str) -> ft.Text:
    """The cut text of one card: the Text above its "Read more"."""
    keynote = keynote_of(KEYNOTES, session_id)
    assert keynote is not None
    (found,) = [t for t in page.find(ft.Text) if t.value == card_text(keynote)]
    return found


async def test_read_more_shows_the_whole_bio_and_show_less_cuts_it_again(
    show: Show,
) -> None:
    """ux.md §5.11: a 4-line bio with "Read more"."""
    page = await show()
    text = bio(page, "153")
    assert (text.max_lines, text.overflow) == (CLAMP_LINES, ft.TextOverflow.ELLIPSIS)
    more = cast(ft.Semantics, page.node("keynotes.more.153").content)
    assert more.expanded is False  # said "collapsed"
    button = cast(ft.TextButton, more.content)
    label = cast(ft.Text, button.content)
    # The bios it opens are about the person, whom the feed names the keynote by.
    assert (label.value, label.semantics_label) == (
        "Read more",
        "Read more about Lin Qiao",
    )
    # Pinned, as Material shrinks it at large text: the label stays on the text's edge.
    assert button.style is not None
    assert button.style.padding == ft.Padding.symmetric(horizontal=12, vertical=8)
    await page.click(button)
    assert bio(page, "153").max_lines is None
    more = cast(ft.Semantics, page.node("keynotes.more.153").content)
    assert more.expanded is True
    button = cast(ft.TextButton, more.content)
    assert text_of(button) == "Show less"
    # A panel's opens its abstract: about the panel, by its own title.
    council = keynote_of(KEYNOTES, "183")
    assert council is not None
    council_more = cast(ft.Semantics, page.node("keynotes.more.183").content)
    council_label = cast(ft.Text, cast(ft.TextButton, council_more.content).content)
    assert council_label.semantics_label == f"Read more about {council.title}"
    # The other cards stay cut.
    assert bio(page, "165").max_lines == CLAMP_LINES
    await page.click(button)
    assert bio(page, "153").max_lines == CLAMP_LINES


# ------------------------------------------------------------------ time, room, star


async def test_the_tile_says_when_and_where_and_opens_the_session(show: Show) -> None:
    page = await show()
    tile = page.node("keynotes.session.153")
    # The range keeps its period with a no-break space, so it never breaks in two.
    assert texts(tile) == [
        "Friday, May 15",
        "9:45–10:30\u00a0AM",
        "Pacific Ballroom - Arena",
    ]
    spoken = [t.semantics_label for t in descendants(tile) if isinstance(t, ft.Text)]
    assert "9:45 to 10:30 AM" in spoken
    await page.click(cast(ft.Control, tile.content))
    assert page.went == ["/more/keynotes/session/153"]


async def test_under_the_hub_the_tile_opens_the_session_there(show: Show) -> None:
    """D-207: Back from the session returns to the page under the hub."""
    page = await show(view_path="/more/tracks/keynotes")
    await page.click(cast(ft.Control, page.node("keynotes.session.183").content))
    assert page.went == ["/more/tracks/keynotes/session/183"]


async def test_the_star_saves_the_session_and_rerenders_one_card(
    show: Show, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-153: the page re-renders, but every other card skips its body."""
    ran: list[str] = []
    head = keynote_card._head

    def counted_head(session: Session, *args: Any) -> list[ft.Control]:
        ran.append(session.id)
        return head(session, *args)

    monkeypatch.setattr(keynote_card, "_head", counted_head)
    page = await show()
    assert sorted(ran) == sorted(card_ids(page))  # the counter sees every card
    ran.clear()
    star = page.node("keynotes.favorite.176")
    await page.click(cast(ft.Control, star.content))
    assert "176" in page.favorites.ids
    assert page.node("keynotes.favorite.176").toggled is True
    assert ran == ["176"]


# ------------------------------------------------------------------ states


async def test_a_keynote_without_year_data_shows_its_name_and_tile(show: Show) -> None:
    """A keynote announced after the build: its name as its heading, nothing cut."""
    year = load_year(2026)
    without = replace(year, content=replace(year.content, keynotes=()))
    page = await show(year_data=without)
    assert card_ids(page) == ["153", "165", "176", "182"]  # no panels: no data
    assert [text_of(n) for n in page.nodes("keynotes.name.")] == [
        "Lin Qiao",
        "Pablo Galindo Salgado",
        "amanda casari",
        "Rachell Calhoun & Tim Schilling",
    ]
    assert page.nodes("keynotes.more.") == []
    assert page.find(ft.CircleAvatar) == []


async def test_a_year_without_keynotes_says_none_are_announced(show: Show) -> None:
    """2025's feed has no keynote track and its year data no keynotes."""
    page = await show(year=2025)
    assert page.nodes("keynotes.session.") == []
    assert "No keynotes announced yet" in texts(page.node("keynotes.empty"))


async def test_without_data_the_page_loads_then_offers_try_again(show: Show) -> None:
    """ux.md §4.1: the sessions load and fail as the Schedule's."""
    loading = await show(conference=Conference())
    assert "Loading schedule" in [n.label for n in loading.find(ft.Semantics)]
    failed = await show(conference=Conference(problem="offline"))
    assert failed.node("keynotes.no_data").live_region
