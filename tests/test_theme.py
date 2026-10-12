"""Tests for the themes, tokens and Markdown style sheet (D-22..D-26, D-33, D-113, D-116)."""

import ast
import dataclasses
import re
from pathlib import Path

import flet as ft
import pytest

from pycon_us import theme

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

# Flet's neutral ramp (neutralizeSurfaces in packages/flet/lib/src/utils/theme.dart at
# the .flet-ref pin): every surface, including surface_bright, surface_dim and the five
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
FLET_THEME_DART = (
    Path(__file__).resolve().parents[1]
    / ".flet-src/packages/flet/lib/src/utils/theme.dart"
)

AA_TEXT = 4.5

SRC = Path(__file__).resolve().parents[1] / "src"


def luminance(hex_color: str) -> float:
    """Relative luminance of #RRGGBB, as WCAG 2.x defines it."""
    channels = [int(hex_color.lstrip("#")[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    r, g, b = (
        c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels
    )
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: str, b: str) -> float:
    lighter, darker = sorted((luminance(a), luminance(b)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def scheme(dark: bool) -> ft.ColorScheme:
    color_scheme = theme.build_theme(dark=dark, high_contrast=False).color_scheme
    assert color_scheme is not None
    return color_scheme


def hex_role(color_scheme: ft.ColorScheme, role: str) -> str:
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
    assert contrast_ratio(background, foreground) == pytest.approx(ratio, abs=0.01)


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_every_declared_text_pair_reads_at_aa(dark: bool) -> None:
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
    color_scheme = scheme(dark)
    for background, foreground in PAIRS[:6] + PAIRS[8:10]:
        assert getattr(color_scheme, background) is not None, background
        assert getattr(color_scheme, foreground) is not None, foreground


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_surface_roles_match_flets_neutral_ramp(dark: bool) -> None:
    # The scheme repeats the ramp's text roles so the pairs above check what Flutter shows.
    color_scheme, ramp = scheme(dark), NEUTRAL_RAMP[dark]
    assert hex_role(color_scheme, "surface") == ramp["surface"]
    assert hex_role(color_scheme, "on_surface") == ramp["onSurface"]
    assert hex_role(color_scheme, "on_surface_variant") == ramp["onSurfaceVariant"]


@pytest.mark.skipif(
    not FLET_THEME_DART.exists(), reason="CI checks out only .flet-src/sdk/python"
)
def test_neutral_ramp_mirrors_the_pinned_flet_source() -> None:
    # Runs wherever the full pin is checked out, so a Flet bump that changes the ramp
    # fails here instead of leaving the contrast tests green on stale colours.
    source = FLET_THEME_DART.read_text(encoding="utf-8")
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
    color_scheme = scheme(dark)
    tokens = theme.build_tokens(dark=dark, high_contrast=False)
    texts = {
        "on_surface": hex_role(color_scheme, "on_surface"),
        "on_surface_variant": hex_role(color_scheme, "on_surface_variant"),
        "primary (links)": hex_role(color_scheme, "primary"),
        **{
            f"tokens.{name}": value
            for name, value in dataclasses.asdict(tokens).items()
        },
    }
    for name, text in texts.items():
        for surface in NEUTRAL_SURFACES[dark]:
            ratio = contrast_ratio(surface, text)
            assert ratio >= AA_TEXT, (name, surface, round(ratio, 2))


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_brand_overrides_follow_the_palette(dark: bool) -> None:
    # D-22: indigo, purple and the 7:1 magenta in light; tuned light tones in dark.
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
    built = theme.build_theme(dark=dark, high_contrast=False)
    assert built.color_scheme_seed == "#3B3EA9"
    assert built.surfaces == ft.ThemeSurfaces.NEUTRAL
    assert built.font_family == "packages/roboto_fonts/Roboto"  # D-105, not "Roboto"


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_ios_defaults_are_pinned_to_material(dark: bool) -> None:
    built = theme.build_theme(dark=dark, high_contrast=False)
    assert built.appbar_theme is not None
    assert built.appbar_theme.center_title is False  # D-10
    assert built.page_transitions is not None
    assert built.page_transitions.android == ft.PageTransitionTheme.PREDICTIVE  # D-11
    assert built.page_transitions.ios == ft.PageTransitionTheme.CUPERTINO


def test_light_overlay_style_has_dark_icons() -> None:
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
def test_high_contrast_uses_the_standard_scheme_until_p2(dark: bool) -> None:
    assert theme.build_theme(dark=dark, high_contrast=True) == theme.build_theme(
        dark=dark, high_contrast=False
    )
    assert theme.build_tokens(dark=dark, high_contrast=True) == theme.build_tokens(
        dark=dark, high_contrast=False
    )


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_favorite_token_is_the_tertiary_role(dark: bool) -> None:
    tokens = theme.build_tokens(dark=dark, high_contrast=False)
    assert tokens.favorite == scheme(dark).tertiary  # ux.md §3.3
    assert tokens.success == tokens.live


def test_tokens_are_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        theme.LIGHT_TOKENS.live = "#000000"  # type: ignore[misc]


def test_tokens_context_defaults_to_the_light_tokens() -> None:
    assert theme.TokensCtx.default_value is theme.LIGHT_TOKENS


def test_every_markdown_text_style_names_a_checked_colour() -> None:
    # F28: a style given in the sheet replaces the theme's, so one without a colour is
    # black on the dark surface. The colours are roles whose contrast is tested above.
    styles = {
        field.name: getattr(theme.MARKDOWN_STYLE, field.name)
        for field in dataclasses.fields(ft.MarkdownStyleSheet)
        if field.name.endswith("_text_style")
    }
    given = {name: style for name, style in styles.items() if style is not None}
    assert given.keys() >= {
        "a_text_style",
        "p_text_style",
        "h1_text_style",
        "code_text_style",
    }
    for name, style in given.items():
        expected = ft.Colors.PRIMARY if name == "a_text_style" else ft.Colors.ON_SURFACE
        assert style.color == expected, name


def test_every_markdown_text_style_names_its_font_and_decoration_colour() -> None:
    # D-152: Markdown text does not inherit the theme's font (iOS showed SF Pro), and an
    # unnamed decoration colour drew near-black lines on the dark surface.
    sheet = theme.MARKDOWN_STYLE
    for field in dataclasses.fields(ft.MarkdownStyleSheet):
        style = getattr(sheet, field.name)
        if not field.name.endswith("_text_style") or style is None:
            continue
        if field.name == "code_text_style":
            assert style.font_family == "monospace", field.name
            assert style.font_family_fallback == ["Menlo"], field.name
        else:
            assert style.font_family == "packages/roboto_fonts/Roboto", field.name
        if style.decoration is not None:
            assert style.decoration_color == style.color, field.name


def test_markdown_links_are_underlined_and_headings_stay_below_the_title() -> None:
    sheet = theme.MARKDOWN_STYLE
    assert sheet.a_text_style is not None
    assert (
        sheet.a_text_style.decoration == ft.TextDecoration.UNDERLINE
    )  # not colour alone (D-33)
    headings = [
        sheet.h1_text_style,
        sheet.h2_text_style,
        sheet.h3_text_style,
        sheet.h4_text_style,
    ]
    assert [style.size for style in headings if style] == [
        22,
        18,
        16,
        16,
    ]  # TITLE_LARGE is 22


def adaptive_true_calls(source: str) -> list[int]:
    """Return the lines of calls in ``source`` that pass ``adaptive=True``."""
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
    # D-10: Material only, identical on both platforms.
    offenders = {
        str(path.relative_to(SRC)): lines
        for path in sorted(SRC.rglob("*.py"))
        if (lines := adaptive_true_calls(path.read_text(encoding="utf-8")))
    }
    assert offenders == {}


def test_adaptive_scan_finds_the_keyword() -> None:
    assert adaptive_true_calls(
        "ft.Switch(adaptive=True)\nft.Switch(adaptive=False)\n"
    ) == [1]
