"""Tests for the links in feed texts (D-197): ``feed_link`` and ``feed_markdown``.

``core.links.feed_link`` reads the address a feed link names, and a feed text is shown
in Markdown whose every tap goes through the link rule.

The rule itself is tested in ``test_links.py``; both take the services and the page
from ``tests/link_rule.py``.
"""

import logging
from collections.abc import Awaitable, Callable, Iterator
from typing import cast

import flet as ft
import pytest

from pycon_us.core.links import feed_link
from pycon_us.services import Services
from pycon_us.theme_markdown import MARKDOWN_STYLE
from pycon_us.ui.links import COULD_NOT_OPEN, feed_markdown, open_feed_link
from tests import link_rule
from tests.fake_page import FakePage
from tests.link_rule import ADDRESS, launcher, said

svc, page = link_rule.svc, link_rule.page

SITE = "https://us.pycon.org/2026/"


@pytest.mark.parametrize(
    ("href", "opens"),
    [
        # As written: the converter made the HTML descriptions' links absolute.
        (f"{SITE}schedule/presentation/142/", f"{SITE}schedule/presentation/142/"),
        ("http://example.org/", "http://example.org/"),
        ("HTTPS://Example.org/", "HTTPS://Example.org/"),
        ("mailto:a@b.org", "mailto:a@b.org"),
        ("  https://pytest.org  ", "https://pytest.org"),  # edge spaces dropped
        # Site-relative: the one relative form the year's site URL resolves right.
        ("/2026/sponsors/", "https://us.pycon.org/2026/sponsors/"),
        ("/about/", "https://us.pycon.org/about/"),
        ("//docs.python.org/3/", "https://docs.python.org/3/"),
        # A web address without its scheme: 2026's open space 9086 writes pytest.org.
        ("pytest.org", "https://pytest.org"),
        ("docs.pytest.org/en/stable/", "https://docs.pytest.org/en/stable/"),
        ("www.python.org/psf?x=1#top", "https://www.python.org/psf?x=1#top"),
    ],
)
def test_a_feed_link_opens_the_address_its_author_meant(href: str, opens: str) -> None:
    """A feed link opens the web or mail address its author meant.

    An absolute link opens as written, without its edge spaces; a site-relative one is
    joined to the year's site, and a web address without its scheme gets https.
    """
    assert feed_link(href, SITE) == opens


@pytest.mark.parametrize(
    "href",
    [
        None,  # a link without a destination
        "",
        "   ",
        "#schedule",  # relative to a page the app does not know
        "../slides.pdf",
        "notes",
        "localhost",
        "javascript:alert(1)",  # only http, https and mailto open
        "file:///etc/hosts",
        "tel:+1-555-0100",
        "ftp://example.org/",
        "http://[",  # urlsplit cannot read it
        "//[",  # nor its host when the site URL is joined
    ],
)
def test_a_feed_link_that_names_no_web_address_opens_nothing(href: str | None) -> None:
    """A feed link that names no web or mail address opens nothing.

    That is a missing or blank destination, one relative to a page, a bare word,
    another scheme, or an address urlsplit cannot read.
    """
    assert feed_link(href, SITE) is None


def test_the_scheme_less_open_space_link_is_not_joined_to_the_site() -> None:
    """D-140's slip: joined, it would be a page of the site that does not exist."""
    assert feed_link("pytest.org", SITE) != f"{SITE}pytest.org"


async def test_a_feed_link_opens_in_the_in_app_browser(
    page: FakePage, svc: Services
) -> None:
    """A scheme-less feed link launches as https in the in-app browser, never pushed."""
    await open_feed_link(svc, "pytest.org")
    assert launcher(svc).launched == [
        ("https://pytest.org", ft.LaunchMode.IN_APP_BROWSER_VIEW)
    ]
    assert page.navigated == []  # a web address is launched, never pushed


async def test_a_site_relative_feed_link_is_a_web_page_not_an_app_page(
    page: FakePage, svc: Services
) -> None:
    """``link_kind`` would push "/2026/…" as a page of the app."""
    await open_feed_link(svc, "/2026/sponsors/")
    assert page.navigated == []
    assert launcher(svc).launched == [
        ("https://us.pycon.org/2026/sponsors/", ft.LaunchMode.IN_APP_BROWSER_VIEW)
    ]


async def test_a_mailto_in_a_feed_text_hands_off_to_the_mail_app(
    page: FakePage, svc: Services
) -> None:
    """A mailto feed link launches in the external mail app."""
    await open_feed_link(svc, f"mailto:{ADDRESS}")
    assert launcher(svc).launched == [
        (f"mailto:{ADDRESS}", ft.LaunchMode.EXTERNAL_APPLICATION)
    ]


async def test_a_feed_link_that_opens_nothing_says_so_and_logs_no_link(
    page: FakePage, svc: Services, caplog: pytest.LogCaptureFixture
) -> None:
    """A feed link that opens nothing says so and logs the tap, never the link."""
    with caplog.at_level(logging.WARNING):
        await open_feed_link(svc, "javascript:steal('secret')")
    assert launcher(svc).launched == []
    assert said(page) == [COULD_NOT_OPEN]
    assert "secret" not in caplog.text  # the link is never logged (D-72)
    assert caplog.records  # but the tap is


def test_a_feed_text_is_selectable_github_markdown_with_the_app_s_sheet(
    page: FakePage, svc: Services
) -> None:
    """A feed text is selectable GitHub Markdown with the app's style sheet.

    It sits under its identifier and never follows a link itself: every tap goes through
    the link rule.
    """
    node = feed_markdown("See [pytest](pytest.org).", svc, identifier="x.description")
    assert isinstance(node, ft.Semantics) and node.identifier == "x.description"
    text = next(c for c in _below(node) if isinstance(c, ft.Markdown))
    assert text.value == "See [pytest](pytest.org)."
    assert text.selectable  # D-26; on_tap_link still fires with it (D-116)
    assert text.extension_set is ft.MarkdownExtensionSet.GITHUB_WEB
    assert text.md_style_sheet is MARKDOWN_STYLE  # every style names its colour (F28)
    assert text.auto_follow_links is False  # every tap goes through the link rule


async def test_a_tap_on_a_link_in_a_feed_text_opens_it(
    page: FakePage, svc: Services
) -> None:
    """A tapped link in a feed text opens by the link rule, in the in-app browser."""
    node = feed_markdown("See [pytest](pytest.org).", svc)
    text = next(c for c in _below(node) if isinstance(c, ft.Markdown))
    handler = text.on_tap_link
    assert handler is not None
    event = ft.Event(name="tap_link", control=text, data="pytest.org")
    await cast(Callable[[ft.Event[ft.Markdown]], Awaitable[None]], handler)(event)
    assert launcher(svc).launched == [
        ("https://pytest.org", ft.LaunchMode.IN_APP_BROWSER_VIEW)
    ]


def _below(control: ft.Control) -> Iterator[ft.Control]:
    """``control`` and every control in its ``content`` chain."""
    node: object = control
    while isinstance(node, ft.Control):
        yield node
        node = getattr(node, "content", None)
