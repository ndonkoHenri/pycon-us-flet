"""Tests for the themes and their text colours, and the helpers other tests share.

D-22..D-26, D-33, D-113, D-116. The tokens' badges have tests/test_theme_badges.py, the
Markdown style sheet tests/test_theme_markdown.py, and the high-contrast schemes
tests/test_high_contrast.py.
"""

import ast
import dataclasses
import math
import re
from pathlib import Path

import flet as ft
import pytest

from pycon_us import theme
from pycon_us.theme_badges import BadgeColors
from tests.flet_dart import flet_dart_file

# Background roles and their text partners. A role the theme leaves to the seed is None in
# both columns; Flutter computes it on the Dart side, so it is checked on screen instead
# (testing-and-quality.md §7.1).
PAIRS = [
    ("primary", "on_primary"),
    ("primary_container", "on_primary_container"),
    ("secondary", "on_secondary"),
    ("secondary_container", "on_secondary_container"),
    ("tertiary", "on_tertiary"),
    ("tertiary_container", "on_tertiary_container"),
    ("error", "on_error"),
    ("error_container", "on_error_container"),
    ("surface", "on_surface"),
    ("surface", "on_surface_variant"),
    ("inverse_surface", "on_inverse_surface"),
]

# Flet's neutral ramp (neutralizeSurfaces in packages/flet/lib/src/utils/theme.dart in
# our Flet): every surface, including surface_bright, surface_dim and the five
# surface_container* roles that cards, sheets, bars and Markdown code spans sit on, and
# the text roles the ramp sets. A test checks this mirror against the Dart source.
NEUTRAL_RAMP = {
    False: {
        "surface": "#FFFFFF",
        "surfaceBright": "#FFFFFF",
        "surfaceDim": "#DDDDDD",
        "surfaceContainerLowest": "#FFFFFF",
        "surfaceContainerLow": "#F7F7F7",
        "surfaceContainer": "#F2F2F2",
        "surfaceContainerHigh": "#EDEDED",
        "surfaceContainerHighest": "#E7E7E7",
        "onSurface": "#1B1B1B",
        "onSurfaceVariant": "#5E5E5E",
    },
    True: {
        "surface": "#121212",
        "surfaceBright": "#3B3B3B",
        "surfaceDim": "#121212",
        "surfaceContainerLowest": "#0D0D0D",
        "surfaceContainerLow": "#1B1B1B",
        "surfaceContainer": "#202020",
        "surfaceContainerHigh": "#292929",
        "surfaceContainerHighest": "#313131",
        "onSurface": "#E7E7E7",
        "onSurfaceVariant": "#ABABAB",
    },
}
NEUTRAL_SURFACES = {
    dark: [value for role, value in ramp.items() if role.startswith("surface")]
    for dark, ramp in NEUTRAL_RAMP.items()
}
FLET_THEME_DART = "lib/src/utils/theme.dart"

AA_TEXT = 4.5

TEXT_TOKENS = ("live", "warning", "success", "favorite")
"""The tokens that are a text colour on the surfaces; the others are badges."""

SRC = Path(__file__).resolve().parents[1] / "src"


def luminance(hex_color: str) -> float:
    """Relative luminance of #RRGGBB, as WCAG 2.x defines it."""
    channels = [int(hex_color.lstrip("#")[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    r, g, b = (
        c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels
    )
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: str, b: str) -> float:
    """Return the WCAG 2.x contrast ratio of two #RRGGBB colours."""
    lighter, darker = sorted((luminance(a), luminance(b)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def cielab(hex_color: str) -> tuple[float, float, float]:
    """CIELAB (D65) of #RRGGBB, from linear sRGB through XYZ."""
    channels = [int(hex_color.lstrip("#")[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    r, g, b = (
        c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels
    )
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
    fx, fy, fz = (
        t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116
        for t in (x, y, z)
    )
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def color_distance(a: str, b: str) -> float:
    """CIE76 colour difference: about 2.3 is just noticeable, 10 clearly different."""
    return math.dist(cielab(a), cielab(b))


def scheme(dark: bool) -> ft.ColorScheme:
    """Return the light or dark theme's colour scheme, without high contrast."""
    color_scheme = theme.build_theme(dark=dark, high_contrast=False).color_scheme
    assert color_scheme is not None
    return color_scheme


def hex_role(color_scheme: ft.ColorScheme, role: str) -> str:
    """Return a scheme role's colour, checked to be a #RRGGBB string."""
    value = getattr(color_scheme, role)
    assert isinstance(value, str) and value.startswith("#") and len(value) == 7, (
        role,
        value,
    )
    return value


@pytest.mark.parametrize(
    ("background", "foreground", "ratio"),
    [
        ("#FFFFFF", "#000000", 21.0),
        ("#FFFFFF", "#FFFFFF", 1.0),
        ("#FFFFFF", "#767676", 4.54),  # the classic lightest AA grey on white
        ("#FFFFFF", "#DD04D2", 4.18),  # Ionic's magenta (D-25)
    ],
)
def test_contrast_ratio_matches_known_values(
    background: str, foreground: str, ratio: float
) -> None:
    """The contrast helper gives the known WCAG ratios, to 0.01."""
    assert contrast_ratio(background, foreground) == pytest.approx(ratio, abs=0.01)


@pytest.mark.parametrize(
    ("a", "b", "distance"),
    [
        ("#FFFFFF", "#000000", 100.0),
        ("#FFFFFF", "#FFFFFF", 0.0),
        ("#808080", "#FF0000", 104.6),  # red is L 53.24, a 80.09, b 67.20
        ("#FFDAD6", "#FFD7F3", 16.4),  # error_container against the En Español pink
    ],
)
def test_color_distance_matches_known_values(a: str, b: str, distance: float) -> None:
    """The CIE76 helper gives known distances, to 0.1."""
    assert color_distance(a, b) == pytest.approx(distance, abs=0.1)


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_every_declared_text_pair_reads_at_aa(dark: bool) -> None:
    """Each declared background role has its text partner, and the two read at AA."""
    color_scheme = scheme(dark)
    for background, foreground in PAIRS:
        bg, fg = getattr(color_scheme, background), getattr(color_scheme, foreground)
        assert (bg is None) == (fg is None), (
            f"{background} overridden without {foreground}"
        )
        if bg is not None:
            ratio = contrast_ratio(
                hex_role(color_scheme, background), hex_role(color_scheme, foreground)
            )
            assert ratio >= AA_TEXT, (background, foreground, round(ratio, 2))


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_brand_roles_are_all_declared(dark: bool) -> None:
    """The six brand roles, the surface and their text partners are all declared."""
    color_scheme = scheme(dark)
    for background, foreground in PAIRS[:6] + PAIRS[8:10]:
        assert getattr(color_scheme, background) is not None, background
        assert getattr(color_scheme, foreground) is not None, foreground


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_surface_roles_match_flets_neutral_ramp(dark: bool) -> None:
    """The scheme's surface and its text roles are Flet's neutral ramp.

    The scheme repeats the ramp's text roles so the pairs above check what Flutter
    shows.
    """
    color_scheme, ramp = scheme(dark), NEUTRAL_RAMP[dark]
    assert hex_role(color_scheme, "surface") == ramp["surface"]
    assert hex_role(color_scheme, "on_surface") == ramp["onSurface"]
    assert hex_role(color_scheme, "on_surface_variant") == ramp["onSurfaceVariant"]


def test_neutral_ramp_mirrors_the_flet_source() -> None:
    """The mirrored neutral ramp is the one in our Flet's Dart source.

    Runs wherever a build has fetched that source, so a Flet bump that changes the ramp
    fails here instead of leaving the contrast tests green on stale colours.
    """
    source = flet_dart_file(FLET_THEME_DART).read_text(encoding="utf-8")
    body = source[source.index("ColorScheme neutralizeSurfaces(") :]
    dark_branch, light_branch = body.split("return scheme.copyWith(")[1:3]
    pattern = r"(\w+): const Color\(0xFF([0-9A-F]{6})\)"
    for dark, branch in ((True, dark_branch), (False, light_branch)):
        found = {role: f"#{value}" for role, value in re.findall(pattern, branch)}
        assert {role: found.get(role) for role in NEUTRAL_RAMP[dark]} == NEUTRAL_RAMP[
            dark
        ]


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_text_colours_read_at_aa_on_every_neutral_surface(dark: bool) -> None:
    """Body text, links and the text tokens read at AA on every neutral surface."""
    color_scheme = scheme(dark)
    tokens = theme.build_tokens(dark=dark, high_contrast=False)
    texts = {
        "on_surface": hex_role(color_scheme, "on_surface"),
        "on_surface_variant": hex_role(color_scheme, "on_surface_variant"),
        "primary (links)": hex_role(color_scheme, "primary"),
        **{f"tokens.{name}": getattr(tokens, name) for name in TEXT_TOKENS},
    }
    for name, text in texts.items():
        for surface in NEUTRAL_SURFACES[dark]:
            ratio = contrast_ratio(surface, text)
            assert ratio >= AA_TEXT, (name, surface, round(ratio, 2))


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_brand_overrides_follow_the_palette(dark: bool) -> None:
    """Primary, secondary and tertiary are the palette's indigo, purple and magenta.

    D-22: indigo, purple and the 7:1 magenta in light; tuned light tones in dark.
    """
    expected = (
        ("#BFC1FF", "#F4AEFF", "#FFACEB") if dark else ("#3B3EA9", "#680579", "#A1009A")
    )
    color_scheme = scheme(dark)
    assert (
        color_scheme.primary,
        color_scheme.secondary,
        color_scheme.tertiary,
    ) == expected


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_theme_is_seeded_with_neutral_surfaces_and_bundled_roboto(dark: bool) -> None:
    """The theme is seeded with the indigo, on neutral surfaces, in bundled Roboto."""
    built = theme.build_theme(dark=dark, high_contrast=False)
    assert built.color_scheme_seed == "#3B3EA9"
    assert built.surfaces == ft.ThemeSurfaces.NEUTRAL
    assert built.font_family == "packages/roboto_fonts/Roboto"  # D-105, not "Roboto"


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_ios_defaults_are_pinned_to_material(dark: bool) -> None:
    """The app bar's title starts left; Android uses predictive back, iOS Cupertino."""
    built = theme.build_theme(dark=dark, high_contrast=False)
    assert built.appbar_theme is not None
    assert built.appbar_theme.center_title is False  # D-10
    assert built.page_transitions is not None
    assert built.page_transitions.android == ft.PageTransitionTheme.PREDICTIVE  # D-11
    assert built.page_transitions.ios == ft.PageTransitionTheme.CUPERTINO


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_a_tall_tiles_icons_sit_by_its_titles_first_line(dark: bool) -> None:
    """The theme's list tiles align their icons with their title's first line.

    D-188, D-205: also a fold's header, which has no alignment of its own, so a wrapped
    "Think you can't do one?" lines its icons up with the link row under it.
    """
    built = theme.build_theme(dark=dark, high_contrast=False)
    assert built.list_tile_theme is not None
    assert built.list_tile_theme.title_alignment == (
        ft.ListTileTitleAlignment.TITLE_HEIGHT
    )


def test_light_overlay_style_has_dark_icons() -> None:
    """The light theme's system bars have dark icons over a transparent status bar."""
    style = theme.build_theme(dark=False, high_contrast=False).system_overlay_style
    assert style == ft.SystemOverlayStyle(
        status_bar_color=ft.Colors.TRANSPARENT,
        system_navigation_bar_color=ft.Colors.SURFACE_CONTAINER,  # D-151
        status_bar_icon_brightness=ft.Brightness.DARK,
        system_navigation_bar_icon_brightness=ft.Brightness.DARK,
        status_bar_brightness=ft.Brightness.LIGHT,
        enforce_system_navigation_bar_contrast=False,
    )


def test_dark_overlay_style_has_light_icons() -> None:
    """The dark theme's system bars have light icons over a transparent status bar."""
    style = theme.build_theme(dark=True, high_contrast=False).system_overlay_style
    assert style == ft.SystemOverlayStyle(
        status_bar_color=ft.Colors.TRANSPARENT,
        system_navigation_bar_color=ft.Colors.SURFACE_CONTAINER,  # D-151
        status_bar_icon_brightness=ft.Brightness.LIGHT,
        system_navigation_bar_icon_brightness=ft.Brightness.LIGHT,
        status_bar_brightness=ft.Brightness.DARK,
        enforce_system_navigation_bar_contrast=False,
    )


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_favorite_token_is_the_tertiary_role(dark: bool) -> None:
    """The favourite token is the tertiary role, and success is the live colour."""
    tokens = theme.build_tokens(dark=dark, high_contrast=False)
    assert tokens.favorite == scheme(dark).tertiary  # ux.md §3.3
    assert tokens.success == tokens.live


def badges(tokens: theme.Tokens) -> dict[str, BadgeColors]:
    """Every badge the tokens hold, by a name for the failure message."""
    return {
        **{f"track {key!r}": colors for key, colors in tokens.tracks.items()},
        "unknown track": tokens.unknown_track,
        "En Español": tokens.spanish,
        "Registration required": tokens.registration,
        "New track": tokens.new_track,
        "Changed": tokens.changed,
    }


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_error_roles_are_the_seeds_own(dark: bool) -> None:
    """The error roles are declared as the colours Flutter's seeded scheme draws.

    Declared so the contrast test sees what Flutter's fromSeed draws (Material's error
    palette, hue 25); the rendered colour was checked on screen (#80).
    """
    expected = ("#FFB4AB", "#690005") if dark else ("#BA1A1A", "#FFFFFF")
    color_scheme = scheme(dark)
    assert (color_scheme.error, color_scheme.on_error) == expected


def adaptive_true_calls(source: str) -> list[int]:
    """Return the lines of calls in `source` that pass `adaptive=True`."""
    return [
        node.lineno
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        for keyword in node.keywords
        if keyword.arg == "adaptive"
        and isinstance(keyword.value, ast.Constant)
        and keyword.value.value is True
    ]


def test_nothing_sets_adaptive() -> None:
    """No call in `src` passes `adaptive=True`.

    D-10: Material only, identical on both platforms.
    """
    offenders = {
        str(path.relative_to(SRC)): lines
        for path in sorted(SRC.rglob("*.py"))
        if (lines := adaptive_true_calls(path.read_text(encoding="utf-8")))
    }
    assert offenders == {}


def test_adaptive_scan_finds_the_keyword() -> None:
    """The scan finds a call passing `adaptive=True`, not one passing False."""
    assert adaptive_true_calls(
        "ft.Switch(adaptive=True)\nft.Switch(adaptive=False)\n"
    ) == [1]


def resolved(role: object, dark: bool) -> str:
    """The #RRGGBB a scheme role (`ft.Colors.ON_SURFACE`, "onsurface") takes."""
    name = str(getattr(role, "value", role))
    color_scheme = scheme(dark)
    by_name = {
        field.name.replace("_", ""): getattr(color_scheme, field.name)
        for field in dataclasses.fields(ft.ColorScheme)
    }
    value = by_name.get(name)
    if value is None:  # a role the theme leaves to Flet's neutral ramp
        value = {key.lower(): v for key, v in NEUTRAL_RAMP[dark].items()}[name]
    assert isinstance(value, str) and value.startswith("#"), (name, value)
    return value
