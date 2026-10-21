"""Tests for sponsor detail (``screens/sponsor.py``; SPON-03, SPON-05, #396).

The screen runs in a real Flet session (``tests/sessions.py``'s ``showing()``) on the
recorded 2026 feed. The roles come from ``core/jobs.py``, tested in
``tests/test_jobs.py``; these tests read what the page makes of them. How it looks,
wraps at 200 % and reads to TalkBack and VoiceOver is checked on devices (the PR).
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from dataclasses import replace
from pathlib import Path
from typing import cast

import flet as ft
import pytest

from pycon_us.config import load_year
from pycon_us.core.jobs import listings_of
from pycon_us.core.models import Sponsor
from pycon_us.core.sponsors import sponsor_by_slug
from pycon_us.screens import sponsor as screen
from pycon_us.state import Conference
from pycon_us.ui.buttons import ICON_PADDING
from tests.feeds import processed
from tests.sessions import Shown, showing, text_of

YEAR = load_year(2026)
DATA = processed(2026)

VIEW_PATH = "/more/sponsors/sponsor/bloomberg"
"""The sponsor's View, pushed from the Sponsors list."""

ROLE = "sponsor.role."
"""The prefix of a role row's semantics identifier."""

type Show = Callable[..., Awaitable[Shown]]


def sponsor(slug: str) -> Sponsor:
    """Return the 2026 sponsor whose slug is ``slug``."""
    found = sponsor_by_slug(DATA, slug)
    assert found is not None
    return found


@pytest.fixture
async def show(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Show]:
    """Return a function that shows a sponsor's page, given its slug.

    It takes an optional ``Conference`` too; the default holds the recorded 2026 feed.
    """
    async with AsyncExitStack() as stack:

        async def render(slug: str, conference: Conference | None = None) -> Shown:
            return await stack.enter_async_context(
                showing(
                    lambda: screen.SponsorDetail(slug),
                    screen,
                    year=YEAR,
                    conference=conference
                    or Conference(data=DATA, source="bundled", version=1),
                    tmp_path=tmp_path,
                    monkeypatch=monkeypatch,
                    view_path=VIEW_PATH,
                )
            )

        yield render


def headings(shown: Shown) -> list[tuple[str, int | None]]:
    """The page's headings as their text and level, in no set order."""
    return [(text_of(n), n.heading_level) for n in shown.find(ft.Semantics) if n.header]


def role_ids(shown: Shown) -> list[str]:
    """The role rows' identifiers, in the rows' order."""
    ids = [str(n.identifier) for n in shown.nodes(ROLE)]
    return sorted(ids, key=lambda i: int(i.removeprefix(ROLE)))


# ------------------------------------------------------------------ the rules


def test_the_facts_say_the_booth_and_the_table_or_either_alone() -> None:
    """The booth and the table, either alone, or None when the sponsor has neither."""
    assert screen.facts_line(sponsor("bloomberg")) == "Booth 613 · Job fair table T2"
    assert screen.facts_line(sponsor("hudson-river-trading")) == "Booth 127"
    bare = replace(sponsor("nvidia"), booth=None, job_fair_table="T9")
    assert screen.facts_line(bare) == "Job fair table T9"
    assert screen.facts_line(sponsor("nvidia")) is None


# ------------------------------------------------------------------ the intro


async def test_the_name_is_the_page_s_heading_over_the_logo_plate(show: Show) -> None:
    """D-186: the heading in the body, the bar's title empty; a 240 × 96 white plate."""
    shown = await show("bloomberg")
    title = shown.node("sponsor.title")
    assert title.header and title.heading_level == 1
    assert cast(ft.Text, title.content).value == "Bloomberg"
    assert shown.titles[-1] == ""
    (plate,) = [c for c in shown.find(ft.Container) if c.bgcolor == ft.Colors.WHITE]
    assert (plate.width, plate.height) == (screen.PLATE_WIDTH, screen.PLATE_HEIGHT)
    image = plate.content
    assert isinstance(image, ft.Image) and image.exclude_from_semantics


async def test_at_large_text_the_name_steps_down_still_centred(show: Show) -> None:
    """D-328: where a slot's time leaves the gutter, the name takes a row title's type."""
    shown = await show("bloomberg")
    shown.prefs.time_above = True  # what GutterProbe measures at that size
    await shown.settle()
    name = cast(ft.Text, shown.node("sponsor.title").content)
    assert (name.theme_style, name.text_align, name.selectable) == (
        ft.TextThemeStyle.TITLE_MEDIUM,
        ft.TextAlign.CENTER,
        True,
    )


async def test_the_level_is_a_line_not_a_control_and_the_facts_read_as_words(
    show: Show,
) -> None:
    """No Chip that does nothing; the middle dot is said as a comma."""
    shown = await show("bloomberg")
    assert "Visionary sponsor" in shown.texts()
    assert shown.find(ft.Chip) == []
    (facts,) = [
        t for t in shown.find(ft.Text) if t.value == "Booth 613 · Job fair table T2"
    ]
    assert facts.semantics_label == "Booth 613, Job fair table T2"


async def test_website_shows_only_when_the_feed_gives_one(show: Show) -> None:
    """2026 has none; one in the feed is an outlined link to the in-app browser."""
    shown = await show("bloomberg")
    assert shown.nodes("sponsor.website") == []
    site = replace(sponsor("bloomberg"), external_url="https://www.bloomberg.com/")
    levels = tuple(
        replace(
            level,
            sponsors=tuple(site if s.slug == site.slug else s for s in level.sponsors),
        )
        for level in DATA.sponsor_levels
    )
    data = replace(DATA, sponsor_levels=levels)
    shown = await show("bloomberg", Conference(data=data, source="bundled", version=1))
    node = shown.node("sponsor.website")
    assert node.link
    (button,) = shown.find(ft.OutlinedButton)
    assert button.style is not None  # its sides stay put at large text (D-344)
    assert button.style.padding == ICON_PADDING
    await shown.click(button)
    assert shown.launcher.launched == [
        ("https://www.bloomberg.com/", ft.LaunchMode.IN_APP_BROWSER_VIEW)
    ]


# ------------------------------------------------------------------ About


async def test_about_keeps_the_description_s_line_breaks(show: Show) -> None:
    """SPON-03: plain, selectable text, its paragraphs apart, as Ionic's HTML was not."""
    hrt = sponsor("hudson-river-trading")
    assert "\n" in hrt.description
    shown = await show(hrt.slug)
    (text,) = [t for t in shown.find(ft.Text) if t.value == hrt.description.strip()]
    assert text.selectable
    assert shown.node("sponsor.about").container
    assert ("About", 2) in headings(shown)


async def test_a_sponsor_without_a_description_has_no_about(show: Show) -> None:
    """Netflix's feed text is empty: no heading over nothing."""
    assert not sponsor("netflix").description.strip()
    shown = await show("netflix")
    assert ("About", 2) not in headings(shown)
    assert shown.nodes("sponsor.about") == []


# ------------------------------------------------------------------ Open roles


@pytest.mark.parametrize(
    ("slug", "count"), [("bloomberg", 15), ("hudson-river-trading", 5)]
)
async def test_each_role_is_a_link_to_the_in_app_browser(
    show: Show, slug: str, count: int
) -> None:
    """SPON-05: Bloomberg's 15 roles and HRT's 5, each a linked row, in order."""
    shown = await show(slug)
    (listing,) = listings_of(DATA, sponsor(slug))
    assert role_ids(shown) == [f"{ROLE}{i}" for i in range(count)]
    assert ("Open roles", 2) in headings(shown)
    titles = [str(tile.title) for tile in shown.find(ft.ListTile)]
    for index, role in enumerate(listing.roles):
        assert shown.node(f"{ROLE}{index}").link
        assert role.title in titles
    first = shown.node(f"{ROLE}0")
    (tile,) = [t for t in shown.find(ft.ListTile) if first in _ancestors(t)]
    assert cast(ft.Icon, tile.leading).icon == ft.Icons.WORK_OUTLINE
    await shown.click(tile)
    assert shown.launcher.launched == [
        (listing.roles[0].url, ft.LaunchMode.IN_APP_BROWSER_VIEW)
    ]


async def test_a_long_form_listing_shows_its_markdown(show: Show) -> None:
    """SerpApi's listing is a job description (D-278): its Markdown, no role rows."""
    serpapi = sponsor("serpapi")
    (listing,) = listings_of(DATA, serpapi)
    shown = await show(serpapi.slug)
    assert shown.nodes(ROLE) == []
    assert shown.nodes(f"sponsor.listing.{listing.id}")
    (markdown,) = shown.find(ft.Markdown)
    assert markdown.value == listing.description_md
    assert ("Open roles", 2) in headings(shown)


@pytest.mark.parametrize("slug", ["openedg-python-institute", "microsoft"])
async def test_no_listing_or_a_placeholder_has_no_open_roles(
    show: Show, slug: str
) -> None:
    """OpenEDG's "N/A" and a sponsor without a listing: no heading over nothing."""
    shown = await show(slug)
    assert ("Open roles", 2) not in headings(shown)
    assert shown.nodes(ROLE) == []
    assert shown.find(ft.Markdown) == []


# ------------------------------------------------------------------ the states


@pytest.mark.parametrize("slug", ["nobody", "", "Bloomberg"])
async def test_an_unknown_slug_shows_not_found_with_the_way_to_all_sponsors(
    show: Show, slug: str
) -> None:
    """D-186: on its own level under the back arrow, never a redirect nor a blank card."""
    shown = await show(slug)
    assert shown.node("sponsor.not_found").live_region
    assert screen.NOT_FOUND in shown.texts()
    assert shown.titles[-1] == "Not found"
    (button,) = shown.find(ft.FilledTonalButton)
    await shown.click(button)
    assert shown.went == ["/more/sponsors"]


async def test_without_data_the_page_loads_then_offers_to_try_again(
    show: Show,
) -> None:
    """ux.md §4.1: the skeleton until the first fetch has failed, then the way out."""
    loading = await show("bloomberg", Conference())
    assert "Loading schedule" in [n.label for n in loading.find(ft.Semantics)]
    failed = await show("bloomberg", Conference(problem="offline"))
    assert failed.node("sponsor.no_data").live_region
    assert loading.titles[-1] == failed.titles[-1] == "Sponsor"
    assert failed.nodes("sponsor.not_found") == []


def _ancestors(control: ft.BaseControl) -> list[ft.BaseControl]:
    """Return the controls ``control`` is mounted under, nearest first."""
    found: list[ft.BaseControl] = []
    node = control.parent
    while node is not None:
        found.append(node)
        node = node.parent
    return found
