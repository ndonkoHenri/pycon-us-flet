"""Tests for About the PSF (``screens/psf.py``; #415, INFO-06, D-283).

The page runs in a real Flet session (``tests/sessions.py``) over the bundled year data,
with and without a feed. How it looks, wraps at 200 % and reads to screen readers is
checked on devices (the PR).
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from pathlib import Path
from typing import cast

import flet as ft
import pytest

from pycon_us.config import load_year
from pycon_us.screens import psf as screen
from pycon_us.state import Conference
from pycon_us.ui.semantics import semantics_key
from pycon_us.year_info import PsfInfo, PsfLink
from tests.feeds import processed
from tests.sessions import Shown, showing

_PSF = load_year(2026).content.psf
assert _PSF is not None
PSF: PsfInfo = _PSF
VIEW = "/more/psf"

type Show = Callable[..., Awaitable[Shown]]


@pytest.fixture
async def show(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Show]:
    """Return a function that renders About the PSF for a year, over a feed or none."""
    async with AsyncExitStack() as stack:

        async def render(*, year: int = 2026, feed: int | None = None) -> Shown:
            """Render the page with ``year``'s data and ``feed``'s feed (None: none yet)."""
            conference = (
                Conference()
                if feed is None
                else Conference(data=processed(feed), source="bundled", version=1)
            )
            return await stack.enter_async_context(
                showing(
                    screen.AboutPsf,
                    screen,
                    year=load_year(year),
                    conference=conference,
                    tmp_path=tmp_path,
                    monkeypatch=monkeypatch,
                    view_path=VIEW,
                )
            )

        yield render


def identifier(link: PsfLink) -> str:
    """A link's row identifier: ``psf.link.<its label as a key>``."""
    return f"psf.link.{semantics_key(link.label)}"


def tile_of(node: ft.Semantics) -> ft.ListTile:
    """The ``ListTile`` an external row's link node holds."""
    assert isinstance(node.content, ft.ListTile)
    return node.content


async def test_offline_the_page_shows_the_mission_once_from_the_year_data(
    show: Show,
) -> None:
    """With no feed yet, the bundled mission shows at once, once, with no feed block."""
    page = await show()
    assert page.titles == [screen.TITLE]
    assert sum(PSF.mission in text for text in page.texts()) == 1
    assert page.nodes("psf.mission")
    assert not page.nodes("psf.feed") and not page.nodes("psf.empty")


async def test_over_a_feed_the_mission_still_shows_once(show: Show) -> None:
    """The feed's block, which repeats the mission, stays out when the year has data."""
    page = await show(feed=2026)
    assert sum("promote, protect, and advance" in t for t in page.texts()) == 1
    assert not page.find(ft.Markdown)


async def test_the_sections_are_level_2_headings_in_the_page_s_order(
    show: Show,
) -> None:
    """Mission, Get involved, Python resources, Follow the PSF: level 2, in this order."""
    (body,) = (await show()).find(ft.ListView)
    headings = [c for c in body.controls if isinstance(c, ft.Semantics) and c.header]
    assert {heading.heading_level for heading in headings} == {2}  # D-211
    texts = [cast(ft.Container, h.content).content for h in headings]
    assert [cast(ft.Text, text).value for text in texts] == [
        "Mission",
        "Get involved",
        "Python resources",
        "Follow the PSF",
    ]


@pytest.mark.parametrize("link", PSF.links, ids=lambda link: link.label)
async def test_every_link_is_an_external_row_that_opens_by_the_link_rule(
    show: Show, link: PsfLink
) -> None:
    """Each row is a link that says where it opens, and opens there: a profile its app."""
    page = await show()
    node = page.node(identifier(link))
    assert node.link  # "link" for screen readers (INFO-14)
    tile = tile_of(node)
    assert tile.title == link.label
    trailing = cast(ft.Icon, tile.trailing)
    assert trailing.icon == ft.Icons.OPEN_IN_NEW
    heard = "Opens in another app" if link.app else "Opens in browser"
    assert trailing.semantics_label == heard
    await page.click(tile)
    mode = (
        ft.LaunchMode.EXTERNAL_APPLICATION
        if link.app
        else ft.LaunchMode.IN_APP_BROWSER_VIEW
    )
    assert page.launcher.launched == [(link.url, mode)]
    assert page.went == []  # it leaves the app; nothing is pushed


@pytest.mark.parametrize("link", PSF.links, ids=lambda link: link.label)
async def test_each_row_leads_with_its_brand_mark_or_its_icon(
    show: Show, link: PsfLink
) -> None:
    """A brand's link shows its decorative mark; any other its outlined icon (D-264)."""
    leading = tile_of((await show()).node(identifier(link))).leading
    if link.brand is not None:
        assert isinstance(leading, ft.Image)
        assert leading.exclude_from_semantics  # the title names the brand
        assert (leading.width, leading.height) == (24, 24)
    else:
        assert isinstance(leading, ft.Icon)
        assert leading.icon == getattr(ft.Icons, cast(str, link.icon))


async def test_donate_is_a_filled_button_link_to_the_donation_page(show: Show) -> None:
    """Donate leaves the app: a link whose name ends "Opens in browser", in-app browser."""
    page = await show()
    node = page.node("psf.donate")
    assert node.link
    button = node.content
    assert isinstance(button, ft.FilledButton)
    label = cast(ft.Text, button.content)
    assert label.value == "Donate to the PSF"
    assert label.semantics_label == "Donate to the PSF\nOpens in browser"
    assert button.icon == ft.Icons.OPEN_IN_NEW
    await page.click(button)
    assert page.launcher.launched == [
        (PSF.donate_url, ft.LaunchMode.IN_APP_BROWSER_VIEW)
    ]


async def test_donate_is_the_page_s_only_way_to_the_donation_page(show: Show) -> None:
    """One Donate: no row repeats the button's link (Ionic had it twice)."""
    page = await show()
    assert len(page.find(ft.FilledButton)) == 1
    assert PSF.donate_url not in {link.url for link in PSF.links}


async def test_a_link_that_cannot_open_says_so(show: Show) -> None:
    """A launch that fails says "Couldn't open the link" (ux.md §4.7)."""
    page = await show()
    page.launcher.error = TimeoutError("no browser")
    await page.click(tile_of(page.node(identifier(PSF.links[0]))))
    assert [cast(ft.Text, bar.content).value for bar in page.snack_bars] == [
        "Couldn't open the link"
    ]


async def test_a_year_without_psf_data_shows_the_feed_s_block(show: Show) -> None:
    """2025 has no ``[psf]``: the page shows the feed's ``about-psf`` block instead."""
    page = await show(year=2025, feed=2025)
    (text,) = page.find(ft.Markdown)
    assert "Python Software Foundation" in text.value
    assert page.nodes("psf.feed")
    assert not page.nodes("psf.mission") and not page.nodes("psf.donate")
    assert not page.nodes("psf.empty")


async def test_without_psf_data_or_a_feed_the_page_says_it_will_come(
    show: Show,
) -> None:
    """No ``[psf]`` and no feed yet: the empty state says the page fills in later."""
    page = await show(year=2025)
    texts = page.texts()
    assert screen.NO_PSF in texts and screen.NO_PSF_BODY in texts
    assert page.nodes("psf.empty")
    assert not page.find(ft.Markdown)
