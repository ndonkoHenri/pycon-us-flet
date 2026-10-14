"""Tests for the shared rows: ``LinkTile``, in-app and external (#77, #83; ux.md §3.9).

The link rule itself is tested in ``test_links.py``.

The builders run outside a renderer, with a fake page bound as Flet binds a session's
page; the external form's component body runs unwrapped, with the session's services
given by the test. How tall a row is on screen, what TalkBack and VoiceOver read, and
what the in-app browser looks like are checked on devices (the PR).
"""

import inspect
from collections.abc import Awaitable, Callable, Iterator
from pathlib import Path
from typing import cast

import flet as ft
import pytest

from pycon_us.config import load_year
from pycon_us.core.models import Speaker
from pycon_us.memory import ViewMemory
from pycon_us.services import Services
from pycon_us.services.storage import Storage
from pycon_us.ui import rows
from pycon_us.ui.rows import LinkTile, SpeakerTile, speaker_avatar
from tests.fakes import (
    FakePage,
    MemoryClipboard,
    MemoryHaptics,
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
        haptics=MemoryHaptics(),
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
    assert isinstance(button, ft.MergeSemantics)  # one node with its tooltip (D-234)
    button = button.content
    if isinstance(button, ft.Semantics):  # with an identifier (D-214)
        button = button.content
    assert isinstance(button, ft.IconButton)
    return button


def tap(tile: ft.ListTile) -> None:
    assert tile.on_click is not None
    cast(Callable[[], None], tile.on_click)()


async def tap_async(control: ft.ListTile | ft.IconButton) -> None:
    assert control.on_click is not None
    await cast(Callable[[], Awaitable[None]], control.on_click)()


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


def test_a_row_without_a_subtitle_centres_its_icons_by_the_title_height(
    page: FakePage,
) -> None:
    tile = tile_of(LinkTile("Keynotes", "/more/keynotes", icon=ft.Icons.MIC))
    assert tile.title_alignment == ft.ListTileTitleAlignment.TITLE_HEIGHT
    assert tile.min_vertical_padding is None  # M3's 56 dp row


@pytest.mark.parametrize("subtitle", ["26 sessions", ft.Column([ft.Text("a")])])
def test_a_row_with_a_subtitle_tops_its_icons_level_with_the_title(
    page: FakePage, subtitle: str | ft.Control
) -> None:
    """Icons and the title line share a centre at every height, so none moves (D-188).

    ``TOP`` puts the icons ``min_vertical_padding`` down, and so is the title: 14 dp is
    more than Flutter's own two-line title offset, so the tile lays out from it.
    """
    tile = tile_of(LinkTile("Room 103ABC", "/map/room/x", subtitle=subtitle))
    assert tile.title_alignment == ft.ListTileTitleAlignment.TOP
    assert tile.min_vertical_padding == 14  # 14 + 24 + 20 + 14: still a 72 dp row


@pytest.mark.parametrize(("subtitle", "top"), [(None, 4), ("+1-562-662-4082", 2)])
def test_the_copy_button_sits_level_with_the_leading_icon(
    page: FakePage, subtitle: str | None, top: int
) -> None:
    row = LinkTile("Call the hotline", HOTLINE, subtitle=subtitle)
    assert isinstance(row, ft.Row)
    holder = row.controls[1]
    assert isinstance(holder, ft.Container)
    # The 48 dp button's 24 dp icon is 12 dp inside it: 16 dp, or 14 with a subtitle.
    assert holder.padding == ft.Padding.only(top=top, right=12)


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


async def test_a_row_the_platform_cannot_open_says_so(
    page: FakePage, svc: Services
) -> None:
    launcher(svc).error = RuntimeError("no app")
    await tap_async(tile_of(LinkTile("Email the CoC team", EMAIL)))
    assert said(page) == ["Couldn't open the link"]


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
    # Merged: bare, an identifier is a node of its own around the button (D-190).
    assert isinstance(holder.content, ft.MergeSemantics)
    node = holder.content.content
    assert isinstance(node, ft.Semantics) and node.identifier == "help.coc.copy"
    assert isinstance(node.content, ft.IconButton)


async def test_a_copy_that_fails_says_so(page: FakePage, svc: Services) -> None:
    clipboard(svc).error = TimeoutError()
    await tap_async(copy_button_of(LinkTile("Call the hotline", HOTLINE)))
    assert said(page) == ["Couldn't copy the phone number"]


# ------------------------------------------------------------------ speaker tiles

ANA = Speaker(id="17", name="Ana Lima", photo_url="https://example.org/ana.jpg", bio="")
NO_PHOTO = Speaker(id="18", name="Bo Chen", photo_url="", bio="")


def test_a_speaker_avatar_shows_the_photo_over_the_initials() -> None:
    avatar = speaker_avatar(ANA)
    assert avatar.foreground_image_src == ANA.photo_url
    assert isinstance(avatar.content, ft.Text) and avatar.content.value == "AL"
    assert (avatar.bgcolor, avatar.color, avatar.radius) == (
        ft.Colors.PRIMARY_CONTAINER,  # with its on_ pair: a tested contrast
        ft.Colors.ON_PRIMARY_CONTAINER,
        24,  # a 48 dp circle
    )


def test_a_speaker_without_a_photo_shows_the_initials_alone() -> None:
    avatar = speaker_avatar(NO_PHOTO)
    assert avatar.foreground_image_src is None  # no request for an empty URL
    assert isinstance(avatar.content, ft.Text) and avatar.content.value == "BC"


def test_a_speaker_tile_is_one_button_named_by_the_speaker(page: FakePage) -> None:
    row = SpeakerTile(ANA, "/x/speaker/17", identifier="session.speaker.17")
    tile = tile_of(row)
    assert tile.title == "Ana Lima"
    assert isinstance(tile.trailing, ft.Icon)
    assert tile.trailing.icon == ft.Icons.CHEVRON_RIGHT  # it pushes a page (§3.7)
    node = node_of(row)
    assert node is not None and node.identifier == "session.speaker.17"
    assert node.label is None and not node.link  # read as its title, a button
    # The initials are left out of the merged node, which says the name once.
    assert isinstance(tile.leading, ft.Semantics) and tile.leading.exclude_semantics
    assert isinstance(tile.leading.content, ft.CircleAvatar)


def test_stacked_speaker_tiles_keep_material_s_space_around_the_avatar(
    page: FakePage,
) -> None:
    """At the default 56 dp, six avatars 8 dp apart read as one column (D-197)."""
    tile = tile_of(SpeakerTile(ANA, "/x/speaker/17", identifier="session.speaker.17"))
    assert tile.min_height == 64  # 8 dp, the 48 dp avatar, 8 dp


def test_a_tap_on_a_speaker_tile_pushes_the_speaker(page: FakePage) -> None:
    tap(tile_of(SpeakerTile(ANA, "/x/speaker/17", identifier="session.speaker.17")))
    assert page.navigated == ["/x/speaker/17"]
