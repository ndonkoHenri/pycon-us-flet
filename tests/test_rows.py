"""Tests for the shared rows: ``LinkTile`` and the link rule (#77, #83; ux.md §3.9, §4.7).

The builders run outside a renderer, with a fake page bound as Flet binds a session's
page; the external form's component body runs unwrapped, with the session's services
given by the test. How tall a row is on screen, what TalkBack and VoiceOver read, and
what the in-app browser looks like are checked on devices (the PR).
"""

import inspect
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
from pycon_us.ui import rows
from pycon_us.ui.rows import (
    LinkKind,
    LinkTile,
    contact_of,
    copy_contact,
    link_kind,
    open_link,
)
from tests.fakes import (
    FakePage,
    MemoryClipboard,
    MemoryLauncher,
    MemoryPrefs,
    MemorySemantics,
    bound,
)

WEB = "https://us.pycon.org/2026/"
PROFILE = "https://fosstodon.org/@pycon"
HOTLINE = "tel:+1-562-662-4082"
EMAIL = "mailto:pycon-coc@python.org?subject=Report"


@pytest.fixture
def svc(tmp_path: Path) -> Services:
    """The session's services, built before a page is bound, as ``App`` builds them."""
    return Services(
        year=load_year(2026),
        storage=Storage(prefs=MemoryPrefs(), directory=tmp_path, year=2026),
        memory=ViewMemory(),
        semantics=MemorySemantics(),
        launcher=MemoryLauncher(),
        clipboard=MemoryClipboard(),
    )


@pytest.fixture
def page(svc: Services, monkeypatch: pytest.MonkeyPatch) -> Iterator[FakePage]:
    # The external row's component body runs inline: there is no renderer here.
    monkeypatch.setattr(
        rows, "_ExternalLinkTile", inspect.unwrap(rows._ExternalLinkTile)
    )
    monkeypatch.setattr(rows, "use_services", lambda: svc)
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


def tile_of(row: ft.Control) -> ft.ListTile:
    """The ``ListTile`` inside a row's semantics wrappers."""
    if isinstance(row, ft.Row):  # a phone or email row: the link, then Copy
        holder = row.controls[0]
        assert isinstance(holder, ft.Container) and holder.content is not None
        row = holder.content
    assert isinstance(row, ft.MergeSemantics)  # one node for screen readers
    inner = row.content
    if isinstance(inner, ft.Semantics):
        inner = inner.content
    assert isinstance(inner, ft.ListTile)
    return inner


def node_of(row: ft.Control) -> ft.Semantics | None:
    """The ``Semantics`` that annotates a row's merged node, if any."""
    tile = tile_of(row)
    merged = row if isinstance(row, ft.MergeSemantics) else None
    if isinstance(row, ft.Row):
        holder = row.controls[0]
        assert isinstance(holder, ft.Container)
        merged = holder.content
    assert isinstance(merged, ft.MergeSemantics)
    node = merged.content
    if isinstance(node, ft.Semantics):
        assert node.content is tile
        return node
    return None


def copy_button_of(row: ft.Control) -> ft.IconButton:
    assert isinstance(row, ft.Row)
    holder = row.controls[1]
    assert isinstance(holder, ft.Container)
    button = holder.content
    if isinstance(button, ft.Semantics):
        button = button.content
    assert isinstance(button, ft.IconButton)
    return button


def tap(tile: ft.ListTile) -> None:
    assert tile.on_click is not None
    cast(Callable[[], None], tile.on_click)()


async def tap_async(control: ft.ListTile | ft.IconButton) -> None:
    assert control.on_click is not None
    await cast(Callable[[], Awaitable[None]], control.on_click)()


# ------------------------------------------------------------------ the link rule


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
        (
            LinkKind.WEB,
            ft.LaunchMode.IN_APP_BROWSER_VIEW,
        ),  # the attendee stays in context
        (LinkKind.APP, ft.LaunchMode.EXTERNAL_APPLICATION),
        (LinkKind.PHONE, ft.LaunchMode.EXTERNAL_APPLICATION),
        (LinkKind.EMAIL, ft.LaunchMode.EXTERNAL_APPLICATION),
    ],
)
def test_each_external_kind_opens_in_its_launch_mode(
    kind: LinkKind, mode: ft.LaunchMode
) -> None:
    assert rows.LAUNCH_MODES[kind] is mode


def test_a_page_has_no_launch_mode_since_it_is_pushed() -> None:
    assert LinkKind.PAGE not in rows.LAUNCH_MODES


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


def test_a_page_cannot_be_marked_as_another_app_s() -> None:
    with pytest.raises(ValueError, match="opens no other app"):
        link_kind("/more/speakers", app=True)


@pytest.mark.parametrize(
    ("target", "copied"),
    [
        (HOTLINE, "+1-562-662-4082"),
        ("tel:+1%20562%20662%204082", "+1 562 662 4082"),
        (EMAIL, "pycon-coc@python.org"),  # without the query
    ],
)
def test_copy_takes_the_number_or_the_address_alone(target: str, copied: str) -> None:
    assert contact_of(target) == copied


# ------------------------------------------------------------------ in-app rows


def test_a_link_tile_is_one_merged_list_tile_with_a_trailing_chevron(
    page: FakePage,
) -> None:
    tile = tile_of(LinkTile("Speakers", "/more/speakers", icon=ft.Icons.PEOPLE_OUTLINE))
    assert tile.title == "Speakers"
    assert isinstance(tile.trailing, ft.Icon)
    assert tile.trailing.icon == ft.Icons.CHEVRON_RIGHT  # an in-app page (§3.7)
    assert isinstance(tile.leading, ft.Icon)
    assert tile.leading.icon == ft.Icons.PEOPLE_OUTLINE


def test_a_link_tile_without_an_icon_or_subtitle_has_neither(page: FakePage) -> None:
    tile = tile_of(LinkTile("Ana Lima", "/more/speakers/speaker/17"))
    assert tile.leading is None
    assert tile.subtitle is None


def test_a_link_tile_shows_its_subtitle(page: FakePage) -> None:
    tile = tile_of(LinkTile("Ana Lima", "/x", subtitle="Typing deep dive"))
    assert tile.subtitle == "Typing deep dive"


def test_a_tap_on_a_link_tile_pushes_its_location(page: FakePage) -> None:
    tap(tile_of(LinkTile("Keynotes", "/more/keynotes")))
    assert page.navigated == ["/more/keynotes"]


def test_a_link_tile_s_identifier_tags_the_merged_node(page: FakePage) -> None:
    row = LinkTile("Sprints", "/more/sprints", identifier="more.sprints")
    node = node_of(row)
    assert node is not None
    assert node.identifier == "more.sprints"
    assert node.label is None  # the row is read as its title (D-166's merge)
    assert not node.link  # a page is a button, not a link


def test_a_link_tile_without_an_identifier_adds_no_semantics_node(
    page: FakePage,
) -> None:
    assert node_of(LinkTile("Sprints", "/more/sprints")) is None


def test_a_tap_that_fails_is_reported_not_raised(page: FakePage) -> None:
    def broken(location: str) -> None:
        raise RuntimeError("no route")

    tile = tile_of(LinkTile("Keynotes", "/more/keynotes"))
    page.navigate = broken  # type: ignore[method-assign]
    tap(tile)
    assert len(page.dialogs) == 1  # "Something went wrong" (D-163), not a crash


# ------------------------------------------------------------------ external rows


@pytest.mark.parametrize(
    ("target", "app", "heard"),
    [(WEB, False, "Opens in browser"), (PROFILE, True, "Opens in another app")],
)
def test_an_external_row_is_a_link_whose_icon_says_where_it_opens(
    page: FakePage, target: str, app: bool, heard: str
) -> None:
    row = LinkTile("PyCon US website", target, app=app, identifier="about.website")
    node = node_of(row)
    assert node is not None
    assert node.link  # screen readers say "link" (INFO-14)
    assert node.identifier == "about.website"
    trailing = tile_of(row).trailing
    assert isinstance(trailing, ft.Icon)
    assert trailing.icon == ft.Icons.OPEN_IN_NEW  # external (§3.7)
    # Read after the title in the one merged node: "PyCon US website, Opens in browser"
    assert trailing.semantics_label == heard


async def test_a_web_row_opens_in_the_in_app_browser(
    page: FakePage, svc: Services
) -> None:
    await tap_async(tile_of(LinkTile("PyCon US website", WEB)))
    assert launcher(svc).launched == [(WEB, ft.LaunchMode.IN_APP_BROWSER_VIEW)]
    assert page.navigated == []


async def test_a_profile_row_opens_in_its_app(page: FakePage, svc: Services) -> None:
    await tap_async(tile_of(LinkTile("PyCon on Mastodon", PROFILE, app=True)))
    assert launcher(svc).launched == [(PROFILE, ft.LaunchMode.EXTERNAL_APPLICATION)]


async def test_a_link_the_platform_cannot_open_says_so_and_logs_no_address(
    page: FakePage, svc: Services, caplog: pytest.LogCaptureFixture
) -> None:
    launcher(svc).error = RuntimeError(f"No app for {EMAIL}")
    with caplog.at_level(logging.WARNING):
        await tap_async(tile_of(LinkTile("Email the CoC team", EMAIL)))
    assert said(page) == ["Couldn't open the link"]
    assert [r.getMessage() for r in caplog.records] == ["Could not open the email link"]


@pytest.mark.parametrize(
    ("target", "tooltip", "copied", "message"),
    [
        (HOTLINE, "Copy phone number", "+1-562-662-4082", "Phone number copied"),
        (EMAIL, "Copy email address", "pycon-coc@python.org", "Email address copied"),
    ],
)
async def test_a_phone_or_email_row_offers_copy_beside_it(
    page: FakePage,
    svc: Services,
    target: str,
    tooltip: str,
    copied: str,
    message: str,
) -> None:
    row = LinkTile("Call the hotline", target, identifier="help.coc")
    button = copy_button_of(row)
    assert button.tooltip == tooltip  # its accessible name (D-27)
    assert tile_of(row).trailing is None  # the title says where a tap goes
    await tap_async(button)
    assert clipboard(svc).value == copied
    assert said(page) == [message]


async def test_a_phone_row_hands_the_number_to_the_phone_app(
    page: FakePage, svc: Services
) -> None:
    await tap_async(tile_of(LinkTile("Call the hotline", HOTLINE)))
    assert launcher(svc).launched == [(HOTLINE, ft.LaunchMode.EXTERNAL_APPLICATION)]


def test_the_copy_button_is_a_stop_of_its_own_with_an_identifier(
    page: FakePage,
) -> None:
    row = LinkTile("Call the hotline", HOTLINE, identifier="help.coc")
    assert isinstance(row, ft.Row)
    merged = row.controls[0]
    assert isinstance(merged, ft.Container)
    assert isinstance(merged.content, ft.MergeSemantics)  # Copy is outside the merge
    holder = row.controls[1]
    assert isinstance(holder, ft.Container)
    assert isinstance(holder.content, ft.Semantics)
    assert holder.content.identifier == "help.coc.copy"


async def test_a_copy_that_fails_says_so(page: FakePage, svc: Services) -> None:
    clipboard(svc).error = TimeoutError()
    await tap_async(copy_button_of(LinkTile("Call the hotline", HOTLINE)))
    assert said(page) == ["Couldn't copy"]


# ------------------------------------------------------------------ the helpers


async def test_open_link_pushes_a_page_as_a_markdown_link_would(
    page: FakePage, svc: Services
) -> None:
    await open_link(svc, "/more/sprints")
    assert page.navigated == ["/more/sprints"]
    assert launcher(svc).launched == []


async def test_only_phone_and_email_links_copy(page: FakePage, svc: Services) -> None:
    with pytest.raises(ValueError, match="only phone and email"):
        await copy_contact(svc, WEB)
