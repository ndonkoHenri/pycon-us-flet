"""Tests for About PyCon US (`screens/about.py`; #414, INFO-02, INFO-05, D-28).

The page runs in a real Flet session (`tests/sessions.py`) over the bundled year data,
with and without a feed; the band's colours are checked against every scheme. How it
looks, wraps at 200 % and reads to screen readers is checked on devices (the PR).
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from pathlib import Path
from typing import cast

import flet as ft
import pytest

from pycon_us.config import load_year
from pycon_us.locations import parent_of
from pycon_us.prefs import Appearance, Prefs
from pycon_us.screens import about as screen
from pycon_us.state import Conference
from pycon_us.theme import DARK_SCHEME, LIGHT_SCHEME
from pycon_us.theme_hc import HC_DARK, HC_LIGHT
from tests.feeds import processed
from tests.harness import Shown, showing
from tests.test_theme import contrast_ratio

type Show = Callable[..., Awaitable[Shown]]


@pytest.fixture
async def show(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Show]:
    """Return a function that renders About PyCon US for a year, over a feed or none."""
    async with AsyncExitStack() as stack:

        async def render(
            *, year: int = 2026, feed: int | None = 2026, theme: Appearance = "light"
        ) -> Shown:
            """Render the page with `year`'s data, `feed`'s feed and a theme."""
            conference = (
                Conference()
                if feed is None
                else Conference(data=processed(feed), source="bundled", version=1)
            )
            return await stack.enter_async_context(
                showing(
                    screen.AboutPycon,
                    screen,
                    year=load_year(year),
                    conference=conference,
                    tmp_path=tmp_path,
                    monkeypatch=monkeypatch,
                    view_path=screen.LOCATION,
                    prefs=Prefs(loaded=True, theme=theme),
                )
            )

        yield render


def card_of(page: Shown) -> ft.Container:
    """The band's card, under its heading node."""
    return cast(ft.Container, page.node("about.band").content)


async def test_the_band_names_the_year_its_dates_and_its_city_from_data(
    show: Show,
) -> None:
    """2026's band says its name, May 13–19 and Long Beach, read as one heading."""
    page = await show()
    assert page.titles == [screen.TITLE]
    assert {"PyCon US 2026", "May 13–19 · Long Beach, CA"} <= set(page.texts())
    band = page.node("about.band")
    assert band.header and band.heading_level == 2  # under the bar's title (D-211)
    assert band.label == "PyCon US 2026. May 13 to 19, Long Beach, CA."


async def test_a_2025_year_shows_2025_s_dates_and_city(show: Show) -> None:
    """Nothing is hard-coded: 2025's data gives Pittsburgh and May 14–22 (D-35)."""
    page = await show(year=2025, feed=None)
    assert {"PyCon US 2025", "May 14–22 · Pittsburgh, PA"} <= set(page.texts())
    assert not any("2026" in text for text in page.texts())


async def test_the_feed_s_about_text_shows_as_markdown(show: Show) -> None:
    """The feed's `about` block is the page's text, as selectable Markdown."""
    page = await show()
    (text,) = page.find(ft.Markdown)
    assert "largest annual gathering" in str(text.value)
    assert text.selectable
    assert page.nodes("about.feed")


async def test_offline_with_no_feed_the_page_still_shows_without_a_loader(
    show: Show,
) -> None:
    """With no feed on the device: the band, a line for the text and the links."""
    page = await show(feed=None)
    assert screen.NO_ABOUT in page.texts()
    assert not page.find(ft.Markdown)
    assert not page.find(ft.ProgressRing) and not page.find(ft.ProgressBar)
    for key in ("about.band", "about.help", "about.venue", "about.website"):
        assert page.nodes(key), key


@pytest.mark.parametrize(
    ("identifier", "target"),
    [("about.help", "/more/about/help"), ("about.venue", "/more/about/venue")],
)
async def test_in_app_links_push_under_the_page_so_back_returns_to_it(
    show: Show, identifier: str, target: str
) -> None:
    """Help & safety and Venue & hours open under About, so Back comes back here."""
    page = await show()
    await page.click(cast(ft.Control, page.node(identifier).content))
    assert page.went == [target]
    assert parent_of(target) == screen.LOCATION


async def test_the_website_row_says_it_opens_in_the_browser_and_does(
    show: Show,
) -> None:
    """The website row is a link read "Opens in browser" that opens the site there."""
    page = await show()
    node = page.node("about.website")
    assert node.link
    tile = cast(ft.ListTile, node.content)
    trailing = cast(ft.Icon, tile.trailing)
    assert trailing.icon == ft.Icons.OPEN_IN_NEW
    assert trailing.semantics_label == "Opens in browser"
    await page.click(tile)
    assert page.launcher.launched == [
        ("https://us.pycon.org/2026/", ft.LaunchMode.IN_APP_BROWSER_VIEW)
    ]
    assert page.went == []


@pytest.mark.parametrize(
    ("theme", "fill", "ink"),
    [
        ("light", ft.Colors.PRIMARY, ft.Colors.ON_PRIMARY),
        ("dark", ft.Colors.PRIMARY_CONTAINER, ft.Colors.ON_PRIMARY_CONTAINER),
    ],
)
async def test_the_band_is_the_brand_indigo_with_its_ink_in_each_scheme(
    show: Show, theme: Appearance, fill: ft.Colors, ink: ft.Colors
) -> None:
    """The band takes the indigo's roles: `primary` in light, its container in dark."""
    card = card_of(await show(theme=theme))
    assert card.bgcolor == fill
    column = cast(ft.Column, card.content)
    assert all(cast(ft.Text, line).color == ink for line in column.controls)


def role(scheme: ft.ColorScheme, name: ft.Colors) -> str:
    """The hex a scheme gives a colour role, e.g. `primary_container`."""
    return cast(str, getattr(scheme, name.name.lower()))


@pytest.mark.parametrize(
    ("scheme", "dark", "minimum"),
    [
        (LIGHT_SCHEME, False, 4.5),
        (DARK_SCHEME, True, 4.5),
        # High contrast asks AAA for text (D-33); its roles are HC's (D-306).
        (HC_LIGHT, False, 7.0),
        (HC_DARK, True, 7.0),
    ],
    ids=["light", "dark", "hc-light", "hc-dark"],
)
def test_the_band_s_text_passes_aa_on_its_fill_in_every_scheme(
    scheme: ft.ColorScheme, dark: bool, minimum: float
) -> None:
    """The band's ink on its fill reads at 4.5:1, and at 7:1 in high contrast."""
    fill, ink = screen.band_colors(dark=dark)
    assert contrast_ratio(role(scheme, ink), role(scheme, fill)) >= minimum
