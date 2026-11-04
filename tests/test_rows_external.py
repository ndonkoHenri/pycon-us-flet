"""Tests for the external rows: `LinkTile` with a URL (#83; ux.md §3.9; D-182).

A web row opens the in-app browser, a profile its app, a phone number or an email its
app with Copy beside it. The services, the bound page and the lookups are
`tests/row_tiles.py`'s; the in-app rows are `test_rows.py`'s and the link rule
`test_links.py`'s. What the in-app browser looks like is checked on devices (the PR).
"""

from typing import cast

import flet as ft
import pytest

from pycon_us.services import Services
from pycon_us.ui.link_tile import LinkTile
from tests import row_tiles
from tests.fake_page import FakePage
from tests.row_tiles import (
    EMAIL,
    HOTLINE,
    PROFILE,
    WEB,
    clipboard,
    copy_button_of,
    launcher,
    node_of,
    said,
    tap_async,
    tile_of,
)

svc, page = row_tiles.svc, row_tiles.page  # the fixtures, under this module's names


@pytest.mark.parametrize(
    ("target", "app", "heard"),
    [(WEB, False, "Opens in browser"), (PROFILE, True, "Opens in another app")],
)
def test_an_external_row_is_a_link_whose_icon_says_where_it_opens(
    page: FakePage, target: str, app: bool, heard: str
) -> None:
    """An external row is a link whose open-in-new icon says where it opens."""
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
    """A web row opens its URL in the in-app browser, without a navigation."""
    await tap_async(tile_of(LinkTile("PyCon US website", WEB)))
    assert launcher(svc).launched == [(WEB, ft.LaunchMode.IN_APP_BROWSER_VIEW)]
    assert page.navigated == []


async def test_a_profile_row_opens_in_its_app(page: FakePage, svc: Services) -> None:
    """A profile row with `app=True` opens its URL in the external app."""
    await tap_async(tile_of(LinkTile("PyCon on Mastodon", PROFILE, app=True)))
    assert launcher(svc).launched == [(PROFILE, ft.LaunchMode.EXTERNAL_APPLICATION)]


async def test_a_row_the_platform_cannot_open_says_so(
    page: FakePage, svc: Services
) -> None:
    """A row whose launch fails says it couldn't open the link."""
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
    """A phone or email row's Copy copies the number or address and says so."""
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
    """A phone row opens its `tel:` URL in the external app."""
    await tap_async(tile_of(LinkTile("Call the hotline", HOTLINE)))
    assert launcher(svc).launched == [(HOTLINE, ft.LaunchMode.EXTERNAL_APPLICATION)]


def test_the_copy_button_is_a_stop_of_its_own_with_an_identifier(
    page: FakePage,
) -> None:
    """Copy is outside the link's merge, a merged node of its own with an identifier."""
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


def test_a_screen_can_name_the_copy_button_otherwise(page: FakePage) -> None:
    """`copy_identifier` names Copy where the screen's scheme differs (D-281)."""
    row = LinkTile(
        "Call the hotline",
        HOTLINE,
        identifier="help.report.tel",
        copy_identifier="help.copy.tel",
    )
    holder = cast(ft.Row, row).controls[1]
    assert isinstance(holder, ft.Container)
    assert isinstance(holder.content, ft.MergeSemantics)
    node = holder.content.content
    assert isinstance(node, ft.Semantics) and node.identifier == "help.copy.tel"
    link = node_of(row)
    assert link is not None and link.identifier == "help.report.tel"


async def test_a_copy_that_fails_says_so(page: FakePage, svc: Services) -> None:
    """A copy that fails says it couldn't copy the phone number."""
    clipboard(svc).error = TimeoutError()
    await tap_async(copy_button_of(LinkTile("Call the hotline", HOTLINE)))
    assert said(page) == ["Couldn't copy the phone number"]
