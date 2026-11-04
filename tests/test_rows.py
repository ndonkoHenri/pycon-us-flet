"""Tests for the shared rows: in-app `LinkTile` and `SpeakerTile` (#77; ux.md §3.9).

The link rule itself is tested in `test_links.py`, the external rows in
`test_rows_external.py` (#83, #623).

The builders run outside a renderer, with `tests/row_tiles.py`'s fake page bound as
Flet binds a session's page. How tall a row is on screen and what TalkBack and
VoiceOver read are checked on devices (the PR).
"""

import flet as ft
import pytest

from pycon_us.core.models import Speaker
from pycon_us.ui.brands import brand_icon
from pycon_us.ui.rows import LinkTile, SpeakerTile, speaker_avatar
from tests import row_tiles
from tests.fake_page import FakePage
from tests.row_tiles import HOTLINE, PROFILE, node_of, tap, tile_of

svc, page = row_tiles.svc, row_tiles.page  # the fixtures, under this module's names


# ------------------------------------------------------------------ in-app rows


def test_a_link_tile_is_one_merged_list_tile_with_a_trailing_chevron(
    page: FakePage,
) -> None:
    """A link tile is a merged `ListTile` with its title, its icon and a chevron."""
    tile = tile_of(LinkTile("Speakers", "/more/speakers", icon=ft.Icons.PEOPLE_OUTLINE))
    assert tile.title == "Speakers"
    assert isinstance(tile.trailing, ft.Icon)
    assert tile.trailing.icon == ft.Icons.CHEVRON_RIGHT  # an in-app page (§3.7)
    assert isinstance(tile.leading, ft.Icon)
    assert tile.leading.icon == ft.Icons.PEOPLE_OUTLINE


def test_a_link_tile_takes_a_control_as_its_leading_mark(page: FakePage) -> None:
    """A control given as the icon (a brand's mark, D-264) leads the row as it is."""
    mark = ft.Image(src=b"<svg/>", width=24, height=24)
    tile = tile_of(LinkTile("Mastodon", PROFILE, icon=mark, app=True))
    assert tile.leading is mark


def test_a_link_tile_without_an_icon_or_subtitle_has_neither(page: FakePage) -> None:
    """A link tile given no icon or subtitle has no leading icon and no subtitle."""
    tile = tile_of(LinkTile("Ana Lima", "/more/speakers/speaker/17"))
    assert tile.leading is None
    assert tile.subtitle is None


@pytest.mark.parametrize("target", ["/more/speakers", PROFILE])
def test_a_control_given_as_the_icon_leads_the_row_as_it_is(
    page: FakePage, target: str
) -> None:
    """A brand's mark, given as a control, is the row's leading, unwrapped (D-264)."""
    mark = brand_icon("mastodon")
    tile = tile_of(LinkTile("Mastodon", target, icon=mark, app=target == PROFILE))
    assert tile.leading is mark


def test_a_link_tile_shows_its_subtitle(page: FakePage) -> None:
    """A link tile shows the subtitle it is given."""
    tile = tile_of(LinkTile("Ana Lima", "/x", subtitle="Typing deep dive"))
    assert tile.subtitle == "Typing deep dive"


def test_a_row_without_a_subtitle_centres_its_icons_by_the_title_height(
    page: FakePage,
) -> None:
    """A row with no subtitle aligns its icons by the title's height, in M3's 56 dp."""
    tile = tile_of(LinkTile("Keynotes", "/more/keynotes", icon=ft.Icons.MIC))
    assert tile.title_alignment == ft.ListTileTitleAlignment.TITLE_HEIGHT
    assert tile.min_vertical_padding is None  # M3's 56 dp row


@pytest.mark.parametrize("subtitle", ["26 sessions", ft.Column([ft.Text("a")])])
def test_a_row_with_a_subtitle_tops_its_icons_level_with_the_title(
    page: FakePage, subtitle: str | ft.Control
) -> None:
    """Icons and the title line share a centre at every height, so none moves (D-188).

    `TOP` puts the icons `min_vertical_padding` down, and so is the title: 14 dp is
    more than Flutter's own two-line title offset, so the tile lays out from it.
    """
    tile = tile_of(LinkTile("Room 103ABC", "/map/room/x", subtitle=subtitle))
    assert tile.title_alignment == ft.ListTileTitleAlignment.TOP
    assert tile.min_vertical_padding == 14  # 14 + 24 + 20 + 14: still a 72 dp row


@pytest.mark.parametrize(("subtitle", "top"), [(None, 4), ("+1-562-662-4082", 2)])
def test_the_copy_button_sits_level_with_the_leading_icon(
    page: FakePage, subtitle: str | None, top: int
) -> None:
    """Copy is padded 4 dp down, or 2 dp with a subtitle, level with the icon."""
    row = LinkTile("Call the hotline", HOTLINE, subtitle=subtitle)
    assert isinstance(row, ft.Row)
    holder = row.controls[1]
    assert isinstance(holder, ft.Container)
    # The 48 dp button's 24 dp icon is 12 dp inside it: 16 dp, or 14 with a subtitle.
    assert holder.padding == ft.Padding.only(top=top, right=12)


def test_a_tap_on_a_link_tile_pushes_its_location(page: FakePage) -> None:
    """A tap on a link tile navigates to its location."""
    tap(tile_of(LinkTile("Keynotes", "/more/keynotes")))
    assert page.navigated == ["/more/keynotes"]


def test_a_link_tile_s_identifier_tags_the_merged_node(page: FakePage) -> None:
    """A link tile's identifier tags its merged node, which adds no label or link."""
    row = LinkTile("Sprints", "/more/sprints", identifier="more.sprints")
    node = node_of(row)
    assert node is not None
    assert node.identifier == "more.sprints"
    assert node.label is None  # the row is read as its title (D-166's merge)
    assert not node.link  # a page is a button, not a link


def test_a_link_tile_without_an_identifier_adds_no_semantics_node(
    page: FakePage,
) -> None:
    """A link tile with no identifier has no `Semantics` inside its merge."""
    assert node_of(LinkTile("Sprints", "/more/sprints")) is None


def test_a_tap_that_fails_is_reported_not_raised(page: FakePage) -> None:
    """A tap whose navigation raises shows one message instead of raising."""

    def broken(location: str) -> None:
        raise RuntimeError("no route")

    tile = tile_of(LinkTile("Keynotes", "/more/keynotes"))
    page.navigate = broken  # type: ignore[method-assign]
    tap(tile)
    assert len(page.dialogs) == 1  # "Something went wrong" (D-163), not a crash


# ------------------------------------------------------------------ external rows


# ------------------------------------------------------------------ speaker tiles

ANA = Speaker(id="17", name="Ana Lima", photo_url="https://example.org/ana.jpg", bio="")
NO_PHOTO = Speaker(id="18", name="Bo Chen", photo_url="", bio="")


def test_a_speaker_avatar_shows_the_photo_over_the_initials() -> None:
    """A speaker's avatar is a 48 dp circle with the photo over the initials."""
    avatar = speaker_avatar(ANA)
    assert avatar.foreground_image_src == ANA.photo_url
    assert isinstance(avatar.content, ft.Text) and avatar.content.value == "AL"
    assert (avatar.bgcolor, avatar.color, avatar.radius) == (
        ft.Colors.PRIMARY_CONTAINER,  # with its on_ pair: a tested contrast
        ft.Colors.ON_PRIMARY_CONTAINER,
        24,  # a 48 dp circle
    )


def test_a_speaker_without_a_photo_shows_the_initials_alone() -> None:
    """A speaker without a photo gets the initials alone and no image request."""
    avatar = speaker_avatar(NO_PHOTO)
    assert avatar.foreground_image_src is None  # no request for an empty URL
    assert isinstance(avatar.content, ft.Text) and avatar.content.value == "BC"


def test_a_speaker_tile_is_one_button_named_by_the_speaker(page: FakePage) -> None:
    """A speaker tile is one merged button read as the name, its avatar left out."""
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
    """A tap on a speaker tile navigates to the speaker's location."""
    tap(tile_of(SpeakerTile(ANA, "/x/speaker/17", identifier="session.speaker.17")))
    assert page.navigated == ["/x/speaker/17"]
