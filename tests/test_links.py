"""Tests for the link rule (INFO-14, ux.md §4.7): ``ui.links``.

What a target is and how it opens, Copy for phone numbers and addresses, and how a
failure is said and logged. The helpers run with a fake page bound as Flet binds a
session's page and the in-memory launcher and clipboard (``tests/fakes.py``); the rows
that use them are tested in ``test_rows.py``.
"""

import logging
from collections.abc import Awaitable, Callable, Iterator
from pathlib import Path
from typing import cast

import flet as ft
import pytest

from pycon_us.config import load_year
from pycon_us.services import Services
from pycon_us.services.storage import Storage
from pycon_us.state import ViewMemory
from pycon_us.theme import MARKDOWN_STYLE
from pycon_us.ui import links
from pycon_us.ui.links import (
    COULD_NOT_OPEN,
    LinkKind,
    contact_of,
    copy_contact,
    feed_link,
    feed_markdown,
    link_kind,
    open_feed_link,
    open_link,
)
from tests.fakes import (
    FakePage,
    MemoryClipboard,
    MemoryHaptics,
    MemoryLauncher,
    MemoryPrefs,
    MemorySemantics,
    android_device,
    bound,
)

WEB = "https://us.pycon.org/2026/"
PROFILE = "https://fosstodon.org/@pycon"
HOTLINE = "tel:+1-562-662-4082"
EMAIL = "mailto:pycon-coc@python.org?subject=Report"
ADDRESS = "pycon-coc@python.org"


@pytest.fixture
def svc(tmp_path: Path) -> Services:
    """The session's services, with an in-memory launcher and clipboard."""
    return Services(
        year=load_year(2026),
        storage=Storage(prefs=MemoryPrefs(), directory=tmp_path, year=2026),
        memory=ViewMemory(),
        semantics=MemorySemantics(),
        haptics=MemoryHaptics(),
        launcher=MemoryLauncher(),
        clipboard=MemoryClipboard(),
    )


@pytest.fixture
def page(svc: Services) -> Iterator[FakePage]:
    # After the services: a Flet service built while a page is bound registers with it.
    fake = FakePage()
    with bound(fake):
        yield fake


def launcher(svc: Services) -> MemoryLauncher:
    return cast(MemoryLauncher, svc.launcher)


def clipboard(svc: Services) -> MemoryClipboard:
    return cast(MemoryClipboard, svc.clipboard)


def said(page: FakePage) -> list[str]:
    """The SnackBars' texts, in order."""
    result = []
    for dialog in page.dialogs:
        assert isinstance(dialog, ft.SnackBar)
        assert isinstance(dialog.content, ft.Text)
        result.append(str(dialog.content.value))
    return result


# ------------------------------------------------------------------ the rule


@pytest.mark.parametrize(
    ("target", "app", "kind"),
    [
        ("/more/speakers", False, LinkKind.PAGE),
        ("/schedule/session/42", False, LinkKind.PAGE),
        (WEB, False, LinkKind.WEB),
        ("http://example.org/page", False, LinkKind.WEB),
        ("HTTPS://Example.org/", False, LinkKind.WEB),  # schemes ignore case
        (PROFILE, True, LinkKind.APP),
        ("https://maps.apple.com/?q=Long+Beach+Convention+Center", True, LinkKind.APP),
        ("geo:33.7637,-118.1888", False, LinkKind.APP),  # a map always opens its app
        ("geo:33.7637,-118.1888", True, LinkKind.APP),
        (HOTLINE, False, LinkKind.PHONE),
        (EMAIL, False, LinkKind.EMAIL),
        ("MAILTO:a@b.org", False, LinkKind.EMAIL),
    ],
)
def test_the_link_rule_tells_pages_web_pages_apps_and_contacts_apart(
    target: str, app: bool, kind: LinkKind
) -> None:
    assert link_kind(target, app=app) is kind


@pytest.mark.parametrize(
    ("kind", "mode"),
    [
        # the attendee stays in context
        (LinkKind.WEB, ft.LaunchMode.IN_APP_BROWSER_VIEW),
        (LinkKind.APP, ft.LaunchMode.EXTERNAL_APPLICATION),
        (LinkKind.PHONE, ft.LaunchMode.EXTERNAL_APPLICATION),
        (LinkKind.EMAIL, ft.LaunchMode.EXTERNAL_APPLICATION),
    ],
)
def test_each_external_kind_opens_in_its_launch_mode(
    kind: LinkKind, mode: ft.LaunchMode
) -> None:
    assert links.LAUNCH_MODES[kind] is mode


def test_a_page_has_no_launch_mode_since_it_is_pushed() -> None:
    assert LinkKind.PAGE not in links.LAUNCH_MODES


@pytest.mark.parametrize(
    "target",
    [
        "javascript:alert(1)",
        "file:///etc/hosts",
        "more/speakers",
        "",
        "sms:+15555550100",
    ],
)
def test_a_target_the_app_does_not_open_is_refused(target: str) -> None:
    with pytest.raises(ValueError, match="not a link the app opens"):
        link_kind(target)


@pytest.mark.parametrize("target", ["/more/speakers", HOTLINE, EMAIL])
def test_only_a_web_address_can_be_marked_as_another_app_s(target: str) -> None:
    # The flag never does nothing silently: a page, a phone or an email has one way.
    with pytest.raises(ValueError, match="only a web address opens in another app"):
        link_kind(target, app=True)


@pytest.mark.parametrize(
    ("target", "copied"),
    [
        (HOTLINE, "+1-562-662-4082"),
        ("tel:+1%20562%20662%204082", "+1 562 662 4082"),
        (EMAIL, ADDRESS),  # without the query
    ],
)
def test_copy_takes_the_number_or_the_address_alone(target: str, copied: str) -> None:
    assert contact_of(target) == copied


# ------------------------------------------------------------------ opening


async def test_open_link_pushes_a_page_as_a_markdown_link_would(
    page: FakePage, svc: Services
) -> None:
    await open_link(svc, "/more/sprints")
    assert page.navigated == ["/more/sprints"]
    assert launcher(svc).launched == []


async def test_open_link_launches_a_web_page_in_the_in_app_browser(
    page: FakePage, svc: Services
) -> None:
    await open_link(svc, WEB)
    assert launcher(svc).launched == [(WEB, ft.LaunchMode.IN_APP_BROWSER_VIEW)]


async def test_a_link_the_platform_cannot_open_says_so_and_logs_no_address(
    page: FakePage, svc: Services, caplog: pytest.LogCaptureFixture
) -> None:
    # What Android's url_launcher reports, through Flet, when no app takes the intent.
    launcher(svc).error = RuntimeError(
        f"PlatformException(ACTIVITY_NOT_FOUND, No Activity found to handle intent "
        f"{{ {EMAIL} }}, null, null)"
    )
    with caplog.at_level(logging.WARNING):
        await open_link(svc, EMAIL)
    assert said(page) == ["Couldn't open the link"]
    assert [r.getMessage() for r in caplog.records] == [
        "Could not open the email link: RuntimeError"
    ]
    assert ADDRESS not in caplog.text  # nor in a traceback (D-72)


# ------------------------------------------------------------------ feed texts (D-197)

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
    assert feed_link(href, SITE) is None


def test_the_scheme_less_open_space_link_is_not_joined_to_the_site() -> None:
    """D-140's slip: joined, it would be a page of the site that does not exist."""
    assert feed_link("pytest.org", SITE) != f"{SITE}pytest.org"


async def test_a_feed_link_opens_in_the_in_app_browser(
    page: FakePage, svc: Services
) -> None:
    await open_feed_link(svc, "pytest.org")
    assert launcher(svc).launched == [
        ("https://pytest.org", ft.LaunchMode.IN_APP_BROWSER_VIEW)
    ]
    assert page.navigated == []  # a site path is a web page, never an app page


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
    await open_feed_link(svc, f"mailto:{ADDRESS}")
    assert launcher(svc).launched == [
        (f"mailto:{ADDRESS}", ft.LaunchMode.EXTERNAL_APPLICATION)
    ]


async def test_a_feed_link_that_opens_nothing_says_so_and_logs_no_link(
    page: FakePage, svc: Services, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        await open_feed_link(svc, "javascript:steal('secret')")
    assert launcher(svc).launched == []
    assert said(page) == [COULD_NOT_OPEN]
    assert "secret" not in caplog.text  # the link is never logged (D-72)
    assert caplog.records  # but the tap is


def test_a_feed_text_is_selectable_github_markdown_with_the_app_s_sheet(
    page: FakePage, svc: Services
) -> None:
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


# ------------------------------------------------------------------ copying


@pytest.mark.parametrize(
    ("target", "copied", "message"),
    [
        (HOTLINE, "+1-562-662-4082", "Phone number copied"),
        (EMAIL, ADDRESS, "Email address copied"),
    ],
)
async def test_a_copy_puts_the_contact_on_the_clipboard_and_says_so(
    page: FakePage, svc: Services, target: str, copied: str, message: str
) -> None:
    await copy_contact(svc, target)
    assert clipboard(svc).value == copied
    assert said(page) == [message]


@pytest.mark.parametrize(
    ("sdk", "messages"), [(32, ["Email address copied"]), (33, []), (36, [])]
)
async def test_android_13_and_later_confirm_a_copy_themselves(
    page: FakePage, svc: Services, sdk: int, messages: list[str]
) -> None:
    page.platform = ft.PagePlatform.ANDROID
    page.device = android_device(sdk)
    await copy_contact(svc, EMAIL)
    assert clipboard(svc).value == ADDRESS
    assert said(page) == messages  # no SnackBar over the system's own overlay


async def test_a_copy_is_confirmed_when_the_android_version_cannot_be_read(
    page: FakePage, svc: Services
) -> None:
    page.platform = ft.PagePlatform.ANDROID
    page.device_error = TimeoutError()
    await copy_contact(svc, EMAIL)
    assert said(page) == ["Email address copied"]


@pytest.mark.parametrize(
    ("target", "message"),
    [
        (HOTLINE, "Couldn't copy the phone number"),
        (EMAIL, "Couldn't copy the email address"),
    ],
)
async def test_a_copy_that_fails_says_what_was_not_copied_and_logs_no_address(
    page: FakePage,
    svc: Services,
    caplog: pytest.LogCaptureFixture,
    target: str,
    message: str,
) -> None:
    page.platform = ft.PagePlatform.ANDROID  # a failure is said on every platform
    page.device = android_device(34)
    # What Flet raises when the Flutter side does not answer: the call's arguments.
    clipboard(svc).error = TimeoutError(
        f"Timeout waiting for invokeMethod set({{'data': '{contact_of(target)}'}}) call"
    )
    with caplog.at_level(logging.WARNING):
        await copy_contact(svc, target)
    assert said(page) == [message]
    assert contact_of(target) not in caplog.text
    assert [r.getMessage() for r in caplog.records] == [
        f"Could not copy the {link_kind(target).value} link: TimeoutError"
    ]


async def test_only_phone_and_email_links_copy(page: FakePage, svc: Services) -> None:
    with pytest.raises(ValueError, match="only phone and email"):
        await copy_contact(svc, WEB)
