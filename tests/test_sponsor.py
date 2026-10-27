"""Tests for sponsor detail (``screens/sponsor.py``; SPON-03, SPON-05, #396).

The screen runs in a real Flet session (``tests/harness.py``'s ``showing()``) on the
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
from tests.harness import Shown, showing
from tests.sessions import text_of

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


def test_the_facts_say_the_booth_only_in_a_year_without_a_hall() -> None:
    """The booth is a plain line without a hall, a button with one; the table, a button."""
    assert screen.facts_line(sponsor("bloomberg"), hall=False) == "Booth 613"
    assert screen.facts_line(sponsor("hudson-river-trading"), hall=False) == (
        "Booth 127"
    )
    assert screen.facts_line(sponsor("bloomberg"), hall=True) is None
    bare = replace(sponsor("nvidia"), booth=None, job_fair_table="T9")
    assert screen.facts_line(bare, hall=False) is None
    assert screen.facts_line(sponsor("nvidia"), hall=False) is None


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


async def test_the_level_is_a_line_not_a_control(show: Show) -> None:
    """No Chip that does nothing; the level is a plain line, the booth a button."""
    shown = await show("bloomberg")
    assert "Visionary sponsor" in shown.texts()
    assert "Booth 613" not in shown.texts()  # Find booth 613 says it
    assert shown.find(ft.Chip) == []


async def test_find_booth_shows_the_booth_in_the_expo_hall(show: Show) -> None:
    """The tonal "Find booth 613" pushes the hall at booth 613 on the sponsor."""
    shown = await show("bloomberg")
    button = cast(ft.FilledTonalButton, shown.node("sponsor.find_booth").content)
    assert button.style is not None
    assert (button.content, button.icon, button.style.padding) == (
        "Find booth 613",
        ft.Icons.STOREFRONT_OUTLINED,
        ICON_PADDING,
    )
    await shown.click(button)
    assert shown.went == [f"{VIEW_PATH}/plan/expo?booth=613"]


async def test_bloomberg_has_both_place_buttons_in_one_wrapping_row(
    show: Show,
) -> None:
    """Find booth, then Job fair table, side by side, stacking at large text."""
    shown = await show("bloomberg")
    booth = shown.node("sponsor.find_booth")
    table = shown.node("sponsor.job_fair_table")
    (row,) = [r for r in shown.find(ft.Row) if booth.parent in r.controls]
    assert row.controls == [booth.parent, table.parent]  # each in its merge (D-214)
    assert (row.wrap, row.alignment) == (True, ft.MainAxisAlignment.CENTER)


async def test_nvidia_has_neither_place_button(show: Show) -> None:
    """No booth and no table: no Find booth, no Job fair table, no facts line."""
    shown = await show("nvidia")
    assert shown.nodes("sponsor.find_booth") == []
    assert shown.nodes("sponsor.job_fair_table") == []
    assert not any(text.startswith("Booth ") for text in shown.texts())


async def test_a_year_without_a_hall_says_the_booth_as_a_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No expo hall to open: "Booth 613" stays a plain line, and no Find booth."""
    year = replace(YEAR, map=replace(YEAR.map, booths=()))
    async with showing(
        lambda: screen.SponsorDetail("bloomberg"),
        screen,
        year=year,
        conference=Conference(data=DATA, source="bundled", version=1),
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        view_path=VIEW_PATH,
    ) as shown:
        assert "Booth 613" in shown.texts()
        assert shown.nodes("sponsor.find_booth") == []
        assert shown.nodes("sponsor.job_fair_table")


async def test_the_job_fair_table_button_shows_the_table_on_the_plan(
    show: Show,
) -> None:
    """The "Job fair table T2" button pushes the job fair plan with T2 selected."""
    shown = await show("bloomberg")
    button = cast(ft.OutlinedButton, shown.node("sponsor.job_fair_table").content)
    assert (button.content, button.icon) == (
        "Job fair table T2",
        ft.Icons.GROUPS_OUTLINED,
    )
    await shown.click(button)
    assert shown.went == [f"{VIEW_PATH}/plan/job-fair?table=T2"]


async def test_a_sponsor_without_a_table_has_no_job_fair_button(show: Show) -> None:
    """NVIDIA has no job fair table, so no button."""
    shown = await show("nvidia")
    assert shown.nodes("sponsor.job_fair_table") == []


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
    (button,) = [
        b for b in shown.find(ft.OutlinedButton) if b.icon == ft.Icons.OPEN_IN_NEW
    ]
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
