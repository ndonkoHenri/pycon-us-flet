"""Tests for the white logo tile (`ui/logos.py`; EVT-05, SPON-01; D-202, D-262).

The tile is built without a renderer: these tests read the control tree it returns.
How it looks is checked on devices (the PR), and the Sprints cards that use it in
`tests/test_sprints.py`.
"""

import flet as ft

from pycon_us.ui.logos import CORNER, EDGE, INK, INSET, logo_tile
from tests.test_theme import contrast_ratio
from tests.trees import descendants, only

LOGO = "https://example.com/arcade.png"
"""A logo URL; nothing loads it here."""


def plate(tile: ft.Control) -> ft.Container:
    """Return the tile as the white container it is, with nothing around it."""
    assert isinstance(tile, ft.Container)
    return tile


def test_without_a_url_the_tile_shows_the_initials_and_no_image() -> None:
    """A project or sponsor with no logo in the feed shows its initials in the ink."""
    tile = logo_tile("CUDA Python", None, size=56)
    assert [node for node in descendants(tile) if isinstance(node, ft.Image)] == []
    avatar = only(tile, ft.CircleAvatar)
    assert only(avatar, ft.Text).value == "CP"
    assert avatar.color == INK
    assert avatar.bgcolor == ft.Colors.TRANSPARENT


def test_an_empty_url_counts_as_none() -> None:
    """An empty logo URL draws the initials rather than an image that cannot load."""
    tile = logo_tile("Arcade", "", size=56)
    assert [node for node in descendants(tile) if isinstance(node, ft.Image)] == []
    assert only(only(tile, ft.CircleAvatar), ft.Text).value == "A"


def test_a_logo_fits_the_tile_with_the_initials_for_when_it_cannot_load() -> None:
    """The logo is contained; a failing URL (offline, broken) shows the initials."""
    image = only(logo_tile("Arcade", LOGO, size=56), ft.Image)
    assert image.src == LOGO
    assert image.fit == ft.BoxFit.CONTAIN
    fallback = image.error_content
    assert isinstance(fallback, ft.CircleAvatar)
    assert only(fallback, ft.Text).value == "A"
    assert fallback.color == INK


def test_the_logo_and_the_initials_are_left_out_of_semantics() -> None:
    """Decorative: the name beside the tile is said, so neither the logo nor initials are.

    Each part leaves itself out, and no `Semantics` wraps the tile: one with
    `exclude_semantics` was still an empty, focusable node on Android (F81).
    """
    image = only(logo_tile("Arcade", LOGO, size=56), ft.Image)
    assert image.exclude_from_semantics is True
    assert isinstance(image.error_content, ft.CircleAvatar)
    assert only(image.error_content, ft.Text).semantics_label == ""
    for url in (None, LOGO):
        tile = logo_tile("Arcade", url, size=56)
        assert [n for n in descendants(tile) if isinstance(n, ft.Semantics)] == []
    assert only(logo_tile("Arcade", None, size=56), ft.Text).semantics_label == ""


def test_the_tile_is_white_with_a_hairline_edge_in_both_schemes() -> None:
    """Logos are drawn for white: the tile names white and a role edge, no scheme."""
    container = plate(logo_tile("Arcade", LOGO, size=56))
    assert container.bgcolor == ft.Colors.WHITE
    assert container.border == ft.Border.all(EDGE, ft.Colors.OUTLINE_VARIANT)
    assert container.border_radius == CORNER
    assert container.padding == INSET
    assert container.alignment == ft.Alignment.CENTER


def test_a_square_tile_takes_its_size_and_the_initials_fill_its_inset() -> None:
    """At 56 dp, the Sprints card's tile, the initials' circle is 42 dp across.

    That is the content box inside the 6 dp inset and the 1 dp edge, which Flutter's
    `Container` adds to its padding.
    """
    tile = logo_tile("Arcade", None, size=56)
    container = plate(tile)
    assert (container.width, container.height) == (56, 56)
    assert only(tile, ft.CircleAvatar).radius == 56 / 2 - INSET - EDGE == 21


def test_a_wide_plate_keeps_the_initials_to_its_height() -> None:
    """Sponsor detail's 240 × 96 plate (ux.md §6.5): the circle, 82 dp, fits the height."""
    tile = logo_tile("Bloomberg", None, size=96, width=240)
    container = plate(tile)
    assert (container.width, container.height) == (240, 96)
    assert only(tile, ft.CircleAvatar).radius == 96 / 2 - INSET - EDGE == 41


def test_a_filling_plate_takes_its_parents_width_and_keeps_its_height() -> None:
    """The Sponsors cards' plates (D-279): no width, centred, so as wide as the card.

    Its height stays fixed, so a logo that loads or fails moves nothing.
    """
    tile = logo_tile("Bloomberg", None, size=72, fill=True)
    container = plate(tile)
    assert (container.width, container.height) == (None, 72)
    assert container.alignment == ft.Alignment.CENTER
    assert only(tile, ft.CircleAvatar).radius == 72 / 2 - INSET - EDGE


def test_the_initials_ink_reads_on_white_at_aaa() -> None:
    """The brand indigo on the white tile: 8.6:1, over AAA's 7:1 in every scheme."""
    assert contrast_ratio(str(INK), "#FFFFFF") >= 8.5
