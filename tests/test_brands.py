"""Tests for the brand marks: the bundled SVGs, their tints and ``brand_icon()``.

D-27, D-264, THEME-12.
"""

import itertools
import re
from pathlib import Path

import flet as ft
import pytest

from pycon_us.ui import brands
from tests.test_theme import contrast_ratio, resolved

NON_TEXT = 3.0
"""WCAG 1.4.11's ratio for a graphic against what it sits on."""

ROOT = Path(__file__).resolve().parents[1]

FLET_SVG_TAG = b' xmlns="http://www.w3.org/2000/svg"'
"""What Flet looks for to draw bytes as an SVG (``svgTag``, ``utils/images.dart``)."""


def tint_hex(tint: str, dark: bool) -> str:
    """Return a tint as ``#RRGGBB`` in the light or dark scheme, a role resolved."""
    return tint if tint.startswith("#") else resolved(tint, dark)


def test_every_brand_has_its_svg_and_every_svg_a_brand() -> None:
    """The bundled folder holds exactly one ``<key>.svg`` per key of ``BRANDS``."""
    files = {path.stem for path in brands.ICONS_DIR.glob("*")}
    assert files == set(brands.BRANDS)
    assert {path.suffix for path in brands.ICONS_DIR.glob("*")} == {".svg"}


def test_the_marks_are_the_eight_the_info_pages_name() -> None:
    """THEME-12's brands: Python, PyPI, Mastodon, Bluesky, X, LinkedIn, YouTube, Discord."""
    assert set(brands.BRANDS) == {
        "python",
        "pypi",
        "mastodon",
        "bluesky",
        "x",
        "linkedin",
        "youtube",
        "discord",
    }


def test_the_marks_live_where_decisions_m_puts_icons() -> None:
    """The SVGs are in ``src/assets/icons/brands/``, which ``flet build`` bundles."""
    assert brands.ICONS_DIR == ROOT / "src/assets/icons/brands"


@pytest.mark.parametrize("key", sorted(brands.BRANDS))
def test_every_svg_is_a_simple_icons_one_colour_square_mark(key: str) -> None:
    """Each file is one 24 × 24 SVG with no colour of its own, so the tint draws it all.

    It also carries the namespace attribute Flet detects SVG bytes by, so the bytes
    ``brand_icon()`` sends are drawn as a picture.
    """
    svg = (brands.ICONS_DIR / f"{key}.svg").read_bytes()
    assert svg.startswith(b"<svg ") and svg.rstrip().endswith(b"</svg>")
    assert b'viewBox="0 0 24 24"' in svg
    assert FLET_SVG_TAG in svg
    assert re.search(rb"fill=|stroke=|style=|<style|<script|<image|href=", svg) is None


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_every_tint_reads_at_three_to_one_on_every_surface_a_mark_sits_on(
    dark: bool,
) -> None:
    """Each mark's tint reads at 3:1 or better on each of ``BRAND_SURFACES`` (1.4.11)."""
    for (key, tint), surface in itertools.product(
        brands.BRANDS.items(), brands.BRAND_SURFACES
    ):
        ratio = contrast_ratio(tint_hex(tint, dark), resolved(surface, dark))
        assert ratio >= NON_TEXT, (key, surface, round(ratio, 2))


def test_the_marks_sit_on_the_page_surface() -> None:
    """Marks are drawn beside link rows on the page, so the test checks ``surface``."""
    assert ft.Colors.SURFACE in brands.BRAND_SURFACES


def test_x_follows_the_text_colour_so_it_never_vanishes_in_dark() -> None:
    """X's mark is drawn in ``on_surface``: its brand black would vanish on the dark surface.

    The general contrast test checks the ``on_surface`` tint in both schemes.
    """
    assert brands.BRANDS["x"] == ft.Colors.ON_SURFACE
    assert contrast_ratio("#000000", resolved(ft.Colors.SURFACE, True)) < NON_TEXT


@pytest.mark.parametrize(
    ("key", "tint"),
    [
        ("python", "#3776AB"),
        ("pypi", "#3775A9"),
        ("mastodon", "#6364FF"),
        ("bluesky", "#0285FF"),
        ("linkedin", "#0A66C2"),
        ("youtube", "#FF0000"),
        ("discord", "#5865F2"),
    ],
)
def test_the_other_marks_keep_their_brands_own_colour(key: str, tint: str) -> None:
    """Every mark but X keeps Simple Icons' hex for its brand, in both schemes."""
    assert brands.BRANDS[key] == tint


@pytest.mark.parametrize("key", sorted(brands.BRANDS))
def test_brand_icon_is_a_decorative_tinted_24_dp_picture_of_the_bundled_svg(
    key: str,
) -> None:
    """The mark is the file's bytes, 24 dp square, tinted, and out of the semantics.

    Bytes, not the asset path: Flet drops ``exclude_from_semantics`` for an SVG file
    (F83, U63).
    """
    image = brands.brand_icon(key)
    assert isinstance(image, ft.Image)
    assert image.src == (brands.ICONS_DIR / f"{key}.svg").read_bytes()
    assert (image.width, image.height) == (24, 24)
    assert image.color == brands.BRANDS[key]
    assert image.exclude_from_semantics is True
    assert image.semantics_label is None


def test_brand_icon_takes_another_size() -> None:
    """``size`` sets the mark's width and height together."""
    image = brands.brand_icon("python", size=40)
    assert (image.width, image.height) == (40, 40)


def test_brand_icon_refuses_an_unknown_brand() -> None:
    """A key that is not a brand raises ``KeyError`` rather than drawing nothing."""
    with pytest.raises(KeyError):
        brands.brand_icon("myspace")


def test_notice_credits_simple_icons_at_the_pinned_version() -> None:
    """``NOTICE`` names the source, the version the files come from and the licence."""
    notice = (ROOT / "NOTICE").read_text()
    assert "Simple Icons" in notice
    assert f"version {brands.SIMPLE_ICONS_VERSION}" in notice
    assert "CC0" in notice
