"""Brand marks: the logos beside a link to Python, PyPI and the social networks.

Material Icons have no brand logos, so the eight marks the info pages need are bundled
SVGs (D-27, THEME-12, D-264): Simple Icons' one-colour 24 × 24 marks at a pinned
version, CC0, credited in ``NOTICE``. Each is shown only as a marker beside a link to
that brand, never as the app's own branding (D-36).
"""

import functools
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

import flet as ft

SIMPLE_ICONS_VERSION = "13.21.0"
"""The Simple Icons release the SVGs come from, as ``NOTICE`` names it (a test).

The last release with all eight marks: LinkedIn left the set in 14.0.0.
"""

ICONS_DIR = Path(__file__).resolve().parents[2] / "assets" / "icons" / "brands"
"""``src/assets/icons/brands/``: one ``<key>.svg`` per brand, as Simple Icons ships it.

``flet build`` bundles ``src/`` whole, this folder included, so the app reads the files
where they are (decisions §M's ``src/assets/icons/``).
"""

BRAND_SURFACES: tuple[str, ...] = (ft.Colors.SURFACE,)
"""The surfaces a mark is drawn on: the page, beside a link row.

Each tint is checked at 3:1 on these, in light and dark (``tests/test_brands.py``); a
mark placed on another surface (a card's container, say) adds it here first, and the
test then tells whether its tint still holds there.
"""

BRANDS: Mapping[str, str] = MappingProxyType(
    {
        # The brand's own colour (Simple Icons' hex) wherever it reads at 3:1 on the
        # surfaces above in both schemes (WCAG 1.4.11; tested).
        "python": "#3776AB",
        "pypi": "#3775A9",
        "mastodon": "#6364FF",
        "bluesky": "#0285FF",
        "linkedin": "#0A66C2",
        "youtube": "#FF0000",
        "discord": "#5865F2",
        # X's mark is black, which vanishes on the dark surface: it follows the text
        # colour in every scheme instead.
        "x": ft.Colors.ON_SURFACE,
    }
)
"""Each brand's tint, by key (the SVG file's name): ``#RRGGBB`` or a scheme role.

A role resolves against the theme on screen, so one builder serves every scheme.
"""


@functools.cache
def _svg(key: str) -> bytes:
    """Return the bundled SVG of brand ``key``, read once per process."""
    return (ICONS_DIR / f"{key}.svg").read_bytes()


def brand_icon(key: str, size: int = 24) -> ft.Image:
    """Return brand ``key``'s mark, tinted, ``size`` dp square, for beside a link.

    The mark is decorative: the link beside it names the brand, so a screen reader
    skips the picture. It goes to Flutter as the SVG's bytes rather than its asset
    path: at the pin, Flet draws an SVG file without passing on
    ``exclude_from_semantics``, so the picture would add an image to the link's node
    (F83, U63). Its tint is drawn over the whole mark (``BlendMode.SRC_IN``, Flet's
    default for an SVG), as every mark is one colour.

    Args:
        key: A key of ``BRANDS``, e.g. ``"mastodon"``.
        size: The mark's width and height in dp; 24, an icon's size, by default.

    Returns:
        The mark as an ``Image``.

    Raises:
        KeyError: ``key`` is not a brand of ``BRANDS``.
    """
    tint = BRANDS[key]  # first, so an unknown key reads no file
    return ft.Image(
        src=_svg(key),
        width=size,
        height=size,
        color=tint,
        exclude_from_semantics=True,
    )
