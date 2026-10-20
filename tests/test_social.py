"""Tests for the Social media page (``screens/social.py``; #416, INFO-10, D-284).

The page runs in a real Flet session (``tests/sessions.py``) over the bundled year data,
with and without a feed. How it looks, wraps at 200 % and reads to screen readers is
checked on devices (the PR).
"""

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from pathlib import Path
from typing import cast

import flet as ft
import pytest

from pycon_us.config import load_year
from pycon_us.screens import social as screen
from pycon_us.state import Conference
from pycon_us.ui.links import OPENS_IN, LinkKind
from tests.fakes import MemoryClipboard
from tests.feeds import processed
from tests.sessions import Shown, showing, text_of

SOCIAL = load_year(2026).content.social
VIEW = "/more/social"

type Show = Callable[..., Awaitable[Shown]]


@pytest.fixture
async def show(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Show]:
    """Return a function that renders the Social page for a year, over a feed or none."""
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
                    screen.Social,
                    screen,
                    year=load_year(year),
                    conference=conference,
                    tmp_path=tmp_path,
                    monkeypatch=monkeypatch,
                    view_path=VIEW,
                )
            )

        yield render


def clipboard(page: Shown) -> MemoryClipboard:
    """The in-memory clipboard the page copies to."""
    return cast(MemoryClipboard, page.services.clipboard)


def snack_texts(page: Shown) -> list[str]:
    """What the page's SnackBars said, in order."""
    return [text_of(bar.content) for bar in page.snack_bars]


def chip(page: Shown, index: int) -> ft.Chip:
    """The hashtag chip ``social.hashtag.<index>`` names, under its ``named()`` node."""
    content = page.node(f"social.hashtag.{index}").content
    assert isinstance(content, ft.Chip)
    return content


def tile(page: Shown, key: str) -> ft.ListTile:
    """The ``ListTile`` of the link row ``social.link.<key>``."""
    content = page.node(f"social.link.{key}").content
    assert isinstance(content, ft.ListTile)
    return content


def headings(page: Shown) -> list[str]:
    """The page's section headings, in order on the page."""
    body = page.find(ft.ListView)
    assert len(body) == 1
    found = []
    for block in body[0].controls:
        if isinstance(block, ft.Semantics) and block.header:
            assert block.heading_level == 2  # sections under the page's title (D-211)
            found.append(text_of(block))
    return found


async def test_with_no_feed_the_page_shows_the_year_s_hashtags_and_links(
    show: Show,
) -> None:
    """Offline on a fresh install, before any feed: the bundled table shows at once."""
    assert SOCIAL is not None
    page = await show()
    assert page.titles == [screen.TITLE]
    texts = page.texts()
    for hashtag in SOCIAL.hashtags:
        assert hashtag in texts
    for link in SOCIAL.links:
        assert page.node(f"social.link.{link.key}")
    assert not page.nodes("social.feed") and not page.nodes("social.empty")


async def test_the_sections_follow_the_hashtags_in_the_page_s_order(
    show: Show,
) -> None:
    """Hashtags, then PyCon US, the PSF and the blogs, each a level-2 heading (D-211)."""
    page = await show()
    assert headings(page) == [
        "Hashtags",
        "PyCon US",
        "Python Software Foundation",
        "Blogs",
    ]


async def test_each_hashtag_is_a_chip_named_for_what_a_tap_does(show: Show) -> None:
    """A chip shows the hashtag and reads "Copy hashtag #PyConUS" (ux.md §9)."""
    assert SOCIAL is not None
    page = await show()
    for index, hashtag in enumerate(SOCIAL.hashtags):
        label = chip(page, index).label
        assert isinstance(label, ft.Text)
        assert label.value == hashtag
        assert label.semantics_label == f"Copy hashtag {hashtag}"
    assert not page.nodes(f"social.hashtag.{len(SOCIAL.hashtags)}")


async def test_a_hashtag_tap_copies_it_and_says_so_once(show: Show) -> None:
    """A tap puts the hashtag, with its ``#``, on the clipboard: one SnackBar."""
    assert SOCIAL is not None
    page = await show()
    await page.click(chip(page, 1))
    assert clipboard(page).value == SOCIAL.hashtags[1] == "#PyConUS2026"
    assert snack_texts(page) == ["Hashtag copied"]


async def test_a_failed_hashtag_copy_says_so_and_logs_no_value(
    show: Show, caplog: pytest.LogCaptureFixture
) -> None:
    """A clipboard that fails says the hashtag was not copied; the log holds no value."""
    page = await show()
    clipboard(page).error = TimeoutError("timed out setting #PyConUS")
    with caplog.at_level(logging.WARNING):
        await page.click(chip(page, 0))
    assert snack_texts(page) == ["Couldn't copy the hashtag"]
    assert [r.getMessage() for r in caplog.records] == [
        "Couldn't copy the hashtag: TimeoutError"
    ]
    assert "#PyConUS" not in caplog.text


async def test_each_link_is_a_row_with_its_mark_and_its_handle(show: Show) -> None:
    """A row: the brand's mark (a feed icon without one), its name, its handle."""
    assert SOCIAL is not None
    page = await show()
    for link in SOCIAL.links:
        row = tile(page, link.key)
        assert row.title == link.label
        assert row.subtitle == link.handle
        if link.brand:
            assert isinstance(row.leading, ft.Image)
            assert row.leading.exclude_from_semantics  # the row names the brand
        else:
            assert isinstance(row.leading, ft.Icon)
            assert row.leading.icon == screen.NO_BRAND_ICON


async def test_a_profile_opens_in_its_app_and_a_blog_in_the_browser(
    show: Show,
) -> None:
    """Profiles open with ``EXTERNAL_APPLICATION``, blogs in the in-app browser."""
    assert SOCIAL is not None
    page = await show()
    for link in SOCIAL.links:
        await page.click(tile(page, link.key))
    assert page.launcher.launched == [
        (
            link.url,
            ft.LaunchMode.IN_APP_BROWSER_VIEW
            if link.section == "blogs"
            else ft.LaunchMode.EXTERNAL_APPLICATION,
        )
        for link in SOCIAL.links
    ]
    assert page.went == []  # nothing in the app is pushed


async def test_each_row_is_a_link_that_says_where_it_opens(show: Show) -> None:
    """Each row's node is a link; its icon says "Opens in another app" or browser."""
    page = await show()
    profile, blog = tile(page, "pycon_mastodon"), tile(page, "blogs_pypi_blog")
    assert page.node("social.link.pycon_mastodon").link
    for row, kind in ((profile, LinkKind.APP), (blog, LinkKind.WEB)):
        assert isinstance(row.trailing, ft.Icon)
        assert row.trailing.semantics_label == OPENS_IN[kind]


async def test_a_year_without_social_data_shows_the_feed_s_block(show: Show) -> None:
    """2025 has no ``[social]``: over its feed, the page shows the feed's own block."""
    page = await show(year=2025, feed=2025)
    assert page.nodes("social.feed")
    (text,) = page.find(ft.Markdown)
    assert "Mastodon" in text.value
    assert not page.nodes("social.hashtag.0") and not page.nodes("social.empty")


async def test_without_social_data_or_a_feed_the_page_points_to_the_website(
    show: Show,
) -> None:
    """2025 with no feed yet: the empty state names the website as the way out."""
    page = await show(year=2025)
    texts = page.texts()
    assert screen.NO_SOCIAL in texts
    assert "The website, us.pycon.org, links to PyCon US's profiles." in texts
    assert page.nodes("social.empty")
    assert not page.nodes("social.feed")
