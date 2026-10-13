"""Tests for the themes, tokens, badges and Markdown style sheet (D-22..D-26, D-33, D-113,
D-116)."""

import ast
import dataclasses
import itertools
import math
import re
from pathlib import Path
from types import MappingProxyType

import flet as ft
import pytest

from pycon_us import config, theme

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
    assert color_distance(a, b) == pytest.approx(distance, abs=0.1)


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
        **{f"tokens.{name}": getattr(tokens, name) for name in TEXT_TOKENS},
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


BADGE_TOKENS = ("tracks", "unknown_track", "spanish", "registration")

YEARS = sorted(
    int(path.name) for path in config.DATA_DIR.iterdir() if path.name.isdigit()
)


def badges(tokens: theme.Tokens) -> dict[str, theme.BadgeColors]:
    """Every badge the tokens hold, by a name for the failure message."""
    return {
        **{f"track {key!r}": colors for key, colors in tokens.tracks.items()},
        "unknown track": tokens.unknown_track,
        "En Español": tokens.spanish,
        "Registration required": tokens.registration,
    }


def test_every_token_is_a_checked_text_colour_or_badge() -> None:
    # A new token must join one of the contrast tests, not slip past both.
    names = {field.name for field in dataclasses.fields(theme.Tokens)}
    assert names == {*TEXT_TOKENS, *BADGE_TOKENS}


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_every_badge_reads_at_aa(dark: bool) -> None:
    # D-25: a tonal badge's label on its fill; an outlined badge's label sits on the
    # surface itself, so on every surface of the neutral ramp. WCAG 2.x formula.
    tokens = theme.build_tokens(dark=dark, high_contrast=False)
    for name, colors in badges(tokens).items():
        backgrounds = [colors.fill] if colors.fill else NEUTRAL_SURFACES[dark]
        for background in backgrounds:
            ratio = contrast_ratio(background, colors.text)
            assert ratio >= AA_TEXT, (name, background, colors.text, round(ratio, 2))


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_every_badge_fill_differs_from_every_other(dark: bool) -> None:
    # The label carries the meaning (D-33), but two tracks of near-equal colour would
    # look like one, and En Español beside a track like part of it (#181's review). So
    # any two fills, the grey of breaks included, differ by a CIE76 distance of 10.
    tokens = theme.build_tokens(dark=dark, high_contrast=False)
    fills = {
        colors.fill: name for name, colors in badges(tokens).items() if colors.fill
    }
    for a, b in itertools.combinations(fills, 2):
        distance = color_distance(a, b)
        assert distance >= 10, (fills[a], fills[b], round(distance, 1))


@pytest.mark.parametrize("year", YEARS)
@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_every_track_of_every_year_has_its_own_badge(dark: bool, year: int) -> None:
    # Palette keys must equal the registry's keys exactly, spaces and capitals included
    # (THEME-08), or a track would fall back to the grey.
    tokens = theme.build_tokens(dark=dark, high_contrast=False)
    keys = {track.key for track in config.load_year(year).conference.tracks}
    assert keys - tokens.tracks.keys() == set()


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_notices_summits_events_and_breaks_get_colours(dark: bool) -> None:
    # Ionic left them grey with no entry (SCHED-20); breaks and notices share the grey.
    tokens = theme.build_tokens(dark=dark, high_contrast=False)
    grey = tokens.unknown_track
    assert tokens.track_badge("Informational") == tokens.track_badge("Break") == grey
    assert tokens.track_badge("Summit") != grey
    assert tokens.track_badge("Event") != grey
    assert tokens.track_badge("Summit") != tokens.track_badge("Event")


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_an_unknown_track_gets_the_neutral_badge(dark: bool) -> None:
    tokens = theme.build_tokens(dark=dark, high_contrast=False)
    assert tokens.track_badge("Workshop") == tokens.unknown_track
    assert tokens.unknown_track.fill is not None


def test_en_espanol_is_the_tonal_pair_inverted_in_dark() -> None:
    # D-25: #FFD7F3 / #5E0058 (10.1:1), instead of Ionic's #DD04D2 (4.18:1).
    light, dark = theme.LIGHT_TOKENS.spanish, theme.DARK_TOKENS.spanish
    assert light == theme.BadgeColors(text="#5E0058", fill="#FFD7F3")
    assert dark == theme.BadgeColors(text="#FFD7F3", fill="#5E0058")
    ratio = contrast_ratio(light.text, light.fill or "")
    assert ratio == pytest.approx(10.06, abs=0.01)


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_registration_badge_is_outlined_in_the_error_role(dark: bool) -> None:
    registration = theme.build_tokens(dark=dark, high_contrast=False).registration
    assert registration == theme.BadgeColors(text=hex_role(scheme(dark), "error"))
    assert registration.fill is None  # outlined


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_error_roles_are_the_seeds_own(dark: bool) -> None:
    # Declared so the contrast test sees what Flutter's fromSeed draws (Material's error
    # palette, hue 25); the rendered colour was checked on screen (#80).
    expected = ("#FFB4AB", "#690005") if dark else ("#BA1A1A", "#FFFFFF")
    color_scheme = scheme(dark)
    assert (color_scheme.error, color_scheme.on_error) == expected


def test_tokens_are_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        theme.LIGHT_TOKENS.live = "#000000"  # type: ignore[misc]
    with pytest.raises(TypeError):  # the palette too
        theme.LIGHT_TOKENS.tracks["Talk"] = theme.BadgeColors("#000000")  # type: ignore[index]
    # Hashable by value although the palette is a mapping: tokens can be a dict key.
    palette = MappingProxyType(dict(theme.LIGHT_TOKENS.tracks))
    rebuilt = dataclasses.replace(theme.LIGHT_TOKENS, tracks=palette)
    assert rebuilt == theme.LIGHT_TOKENS
    assert hash(rebuilt) == hash(theme.LIGHT_TOKENS)


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


def resolved(role: object, dark: bool) -> str:
    """The #RRGGBB a scheme role (``ft.Colors.ON_SURFACE``, "onsurface") takes."""
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


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_markdown_text_reads_at_aa_on_every_background_the_sheet_draws(
    dark: bool,
) -> None:
    """SESS-06: a description's text, links and code on the page, on a code span and
    in a block quote, in both schemes."""
    sheet = theme.MARKDOWN_STYLE
    assert sheet.code_text_style is not None and sheet.blockquote_decoration is not None
    texts = {
        field.name: resolved(style.color, dark)
        for field in dataclasses.fields(ft.MarkdownStyleSheet)
        if field.name.endswith("_text_style")
        and (style := getattr(sheet, field.name)) is not None
    }
    backgrounds = {
        "surface": resolved(ft.Colors.SURFACE, dark),
        "code": resolved(sheet.code_text_style.bgcolor, dark),
        "blockquote": resolved(sheet.blockquote_decoration.bgcolor, dark),
    }
    for (text, color), (where, background) in itertools.product(
        texts.items(), backgrounds.items()
    ):
        ratio = contrast_ratio(background, color)
        assert ratio >= AA_TEXT, (text, where, round(ratio, 2))
