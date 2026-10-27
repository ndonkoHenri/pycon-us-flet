"""Tests for the high-contrast colour schemes, their tokens and how the app picks them.

D-23, D-151, D-265, D-285; THEME-04..06, THEME-08; ux.md §3.2..§3.4;
testing-and-quality.md §7.1. The line above the bottom bar is tested with the bar, in
``test_navigation_views.py``.
"""

import dataclasses
import re
from typing import cast

import flet as ft
import pytest

from pycon_us import theme
from pycon_us.app import apply_theme
from pycon_us.prefs import Prefs
from pycon_us.theme_badges import HC_BADGE_BORDER, BadgeColors
from pycon_us.theme_hc import HC_DARK, HC_LIGHT
from pycon_us.ui.badges import TrackBadge
from tests.fakes import FakePage
from tests.test_theme import (
    FLET_THEME_DART,
    NEUTRAL_RAMP,
    TEXT_TOKENS,
    badges,
    contrast_ratio,
    hex_role,
)

AAA_TEXT = 7.0
"""High contrast's text minimum (D-23, D-33)."""

NON_TEXT = 3.0
"""WCAG 1.4.11's minimum for a boundary, such as an outline."""

ROLES = [field.name for field in dataclasses.fields(ft.ColorScheme)]
"""Every role of a Flet colour scheme."""

SURFACES = [
    role for role in ROLES if role.startswith("surface") and role != "surface_tint"
]
"""Every role something sits on: ``surface``, its bright and dim, the five containers."""

# Background roles and the text drawn on them: each "on" partner, the inverse roles a
# SnackBar draws (its action in inverse_primary), and each fixed role under both of its
# text roles.
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
    ("inverse_surface", "inverse_primary"),
    *(
        (f"{brand}_fixed{dim}", f"on_{brand}_fixed{variant}")
        for brand in ("primary", "secondary", "tertiary")
        for dim in ("", "_dim")
        for variant in ("", "_variant")
    ),
]

TEXT_ON_SURFACES = [
    "on_surface",
    "on_surface_variant",
    "primary",
    "secondary",
    "tertiary",
    "error",
]
"""Roles drawn as text straight on a surface: body text, links, text buttons, errors."""


SCHEME_FIELDS = {
    "color_scheme": None,
    "system_overlay_style": None,
    "scaffold_bgcolor": None,
    "canvas_color": None,
    "card_bgcolor": None,
    "divider_color": None,
    "card_theme": None,
    "chip_theme": None,
    "navigation_bar_theme": None,
    "navigation_rail_theme": None,
}
"""The theme fields that come from the scheme; the rest is the same in every scheme.

HC's component themes are among them: its cards are flat and bordered (THEME-06), its
chips outlined and its selected pill ringed (D-306, ``test_hc_boundaries.py``).
"""


def hc_scheme(dark: bool) -> ft.ColorScheme:
    """Return the colour scheme of the high-contrast light or dark theme."""
    color_scheme = theme.build_theme(dark=dark, high_contrast=True).color_scheme
    assert color_scheme is not None
    return color_scheme


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_every_role_is_set_by_hand(dark: bool) -> None:
    """No role of a high-contrast scheme is left to the seed: each is a #RRGGBB colour.

    A role Flet adds to ``ColorScheme`` fails here until it is given a value.
    """
    color_scheme = hc_scheme(dark)
    unset = [role for role in ROLES if getattr(color_scheme, role) is None]
    assert unset == []
    for role in ROLES:
        hex_role(color_scheme, role)


@pytest.mark.skipif(
    not FLET_THEME_DART.exists(), reason="needs the pinned Flet checkout (.flet-src)"
)
def test_flet_applies_every_role_it_declares() -> None:
    """Flet's Dart side reads every ``ColorScheme`` role, so none set here is lost (F9).

    ``parseColorScheme`` in ``utils/theme.dart`` at the ``.flet-ref`` pin.
    """
    source = FLET_THEME_DART.read_text()
    body = source[source.index("ColorScheme? parseColorScheme(") :]
    body = body[: body.index("\n}\n")]
    parsed = set(re.findall(r'value\["(\w+)"\]', body))
    assert parsed == set(ROLES)


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_every_text_pair_reads_at_7_to_1(dark: bool) -> None:
    """Each text role reads at 7:1 or more on the background it is made for."""
    color_scheme = hc_scheme(dark)
    for background, text in PAIRS:
        ratio = contrast_ratio(
            hex_role(color_scheme, text), hex_role(color_scheme, background)
        )
        assert ratio >= AAA_TEXT, (background, text, round(ratio, 2))


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_text_on_the_surfaces_reads_at_7_to_1_on_every_one(dark: bool) -> None:
    """Body text, links, text buttons and errors read at 7:1 on every surface role."""
    color_scheme = hc_scheme(dark)
    for surface in SURFACES:
        for text in TEXT_ON_SURFACES:
            ratio = contrast_ratio(
                hex_role(color_scheme, text), hex_role(color_scheme, surface)
            )
            assert ratio >= AAA_TEXT, (surface, text, round(ratio, 2))


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
@pytest.mark.parametrize("outline", ["outline", "outline_variant"])
def test_outlines_read_at_3_to_1_on_every_surface(dark: bool, outline: str) -> None:
    """Both outline roles separate a boundary from every surface at 3:1 or more."""
    color_scheme = hc_scheme(dark)
    for surface in SURFACES:
        ratio = contrast_ratio(
            hex_role(color_scheme, outline), hex_role(color_scheme, surface)
        )
        assert ratio >= NON_TEXT, (surface, outline, round(ratio, 2))


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_there_is_one_surface(dark: bool) -> None:
    """Every surface role and the elevation tint equal ``surface``: no grey tiers."""
    color_scheme = hc_scheme(dark)
    for role in [*SURFACES, "surface_tint"]:
        assert getattr(color_scheme, role) == color_scheme.surface, role


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_strong_roles_are_their_own_containers(dark: bool) -> None:
    """Primary and error fill their containers; tertiary's repeats secondary's."""
    s = hc_scheme(dark)
    assert (s.primary_container, s.on_primary_container) == (s.primary, s.on_primary)
    assert (s.error_container, s.on_error_container) == (s.error, s.on_error)
    assert (s.tertiary_container, s.on_tertiary_container) == (
        s.secondary_container,
        s.on_secondary_container,
    )


@pytest.mark.parametrize(
    ("dark", "values"),
    [
        (
            False,
            {
                "primary": "#4A0072",
                "on_primary": "#FFFFFF",
                "secondary": "#4A0072",
                "secondary_container": "#E9E7E1",
                "on_secondary_container": "#1A1D24",
                "tertiary": "#4A0072",
                "surface": "#FBFAF6",
                "on_surface": "#1A1D24",
                "on_surface_variant": "#1A1D24",
                "outline": "#1A1D24",
                "error": "#8C0009",
            },
        ),
        (
            True,
            {
                "primary": "#FFD60A",
                "on_primary": "#0B0F17",
                "secondary": "#F5F5F0",
                "secondary_container": "#21252F",
                "on_secondary_container": "#F5F5F0",
                "tertiary": "#FFD60A",
                "surface": "#0B0F17",
                "on_surface": "#F5F5F0",
                "on_surface_variant": "#F5F5F0",
                "outline": "#F5F5F0",
                "error": "#FFB4AB",
            },
        ),
    ],
    ids=["light", "dark"],
)
def test_the_schemes_follow_the_ux_table(dark: bool, values: dict[str, str]) -> None:
    """The roles ux.md §3.2 names have its values."""
    color_scheme = hc_scheme(dark)
    assert {role: getattr(color_scheme, role) for role in values} == values


def test_the_inverse_roles_swap_the_schemes() -> None:
    """A SnackBar in one scheme is the other's surface, ink and primary."""
    for scheme, other in ((HC_LIGHT, HC_DARK), (HC_DARK, HC_LIGHT)):
        assert scheme.inverse_surface == scheme.on_surface
        assert scheme.on_inverse_surface == scheme.surface
        assert scheme.inverse_primary == other.primary


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_only_the_scheme_and_the_navigation_bar_change(dark: bool) -> None:
    """Font, seed, transitions, tiles and bar icons are the standard theme's (D-151).

    Only the scheme, the colours named from it and the navigation bar's colour differ.
    """
    standard = theme.build_theme(dark=dark, high_contrast=False)
    high = theme.build_theme(dark=dark, high_contrast=True)
    assert standard.system_overlay_style is not None
    assert high.system_overlay_style is not None
    assert dataclasses.replace(
        high.system_overlay_style, system_navigation_bar_color=None
    ) == dataclasses.replace(
        standard.system_overlay_style, system_navigation_bar_color=None
    )
    assert dataclasses.replace(high, **SCHEME_FIELDS) == dataclasses.replace(
        standard, **SCHEME_FIELDS
    )


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
@pytest.mark.parametrize("high_contrast", [False, True], ids=["standard", "hc"])
def test_the_page_canvas_card_and_divider_follow_the_scheme(
    dark: bool, high_contrast: bool
) -> None:
    """The colours ThemeData derives from the scheme are named from the one shown.

    Flet derives them from the seeded scheme, before the overrides apply (U64): in HC
    the page stayed white under cream bars on the Android emulator. HC names its
    divider from ``outline``; the standard schemes set no ``outline``, so their
    divider stays Flet's derived one, and naming one there would fail here.
    """
    built = theme.build_theme(dark=dark, high_contrast=high_contrast)
    assert built.color_scheme is not None
    surface = built.color_scheme.surface
    assert (built.scaffold_bgcolor, built.canvas_color, built.card_bgcolor) == (
        surface,
        surface,
        surface,
    )
    if high_contrast:
        assert built.color_scheme.outline is not None
        assert built.divider_color == built.color_scheme.outline
    else:
        assert built.divider_color is None


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_the_seeded_text_colour_still_reads_at_7_to_1(dark: bool) -> None:
    """The text theme's colour, which Flet takes from the seeded scheme, reads at 7:1.

    Flutter's ``Typography.material2021`` colours the text theme with the seeded,
    neutralised ``onSurface`` (U64), not HC's; it must still read on HC's surface.
    """
    seeded_text = NEUTRAL_RAMP[dark]["onSurface"]
    ratio = contrast_ratio(seeded_text, hex_role(hc_scheme(dark), "surface"))
    assert ratio >= AAA_TEXT, round(ratio, 2)


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_the_navigation_bar_takes_the_hc_navigation_bar_fill(dark: bool) -> None:
    """Android's navigation bar gets the scheme's own ``surface_container`` (D-151).

    The ``NavigationBar`` fills with that role. In the style a role would resolve
    against the seeded scheme's grey ramp, not these overrides, so the colour is named.
    """
    built = theme.build_theme(dark=dark, high_contrast=True)
    assert built.system_overlay_style is not None
    assert built.color_scheme is not None
    color = built.system_overlay_style.system_navigation_bar_color
    assert color == built.color_scheme.surface_container
    assert re.fullmatch(r"#[0-9A-F]{6}", str(color))


@pytest.mark.parametrize(
    ("dark", "live", "warning"),
    [(False, "#0F5A26", "#7A4A00"), (True, "#30D158", "#FFD60A")],
    ids=["light", "dark"],
)
def test_the_hc_tokens_follow_the_ux_table(dark: bool, live: str, warning: str) -> None:
    """HC's text tokens are ux.md §3.3's: success is live, the star is the ink."""
    tokens = theme.build_tokens(dark=dark, high_contrast=True)
    assert (tokens.live, tokens.warning, tokens.success) == (live, warning, live)
    assert tokens.favorite == hc_scheme(dark).on_surface


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_only_the_hc_tokens_carry_the_high_contrast_flag(dark: bool) -> None:
    """The flag is on in HC's tokens and off in the standard ones (D-285)."""
    assert theme.build_tokens(dark=dark, high_contrast=True).high_contrast is True
    assert theme.build_tokens(dark=dark, high_contrast=False).high_contrast is False


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_the_hc_text_tokens_read_at_7_to_1_on_every_surface(dark: bool) -> None:
    """Live, warning, success and the star read at 7:1 on every HC surface."""
    tokens = theme.build_tokens(dark=dark, high_contrast=True)
    color_scheme = hc_scheme(dark)
    for surface in SURFACES:
        background = hex_role(color_scheme, surface)
        for name in TEXT_TOKENS:
            ratio = contrast_ratio(getattr(tokens, name), background)
            assert ratio >= AAA_TEXT, (surface, name, round(ratio, 2))


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_every_hc_badge_is_outlined_1_5_dp(dark: bool) -> None:
    """Every HC badge has no fill and a 1.5 dp outline (ux.md §3.4, THEME-06).

    Tracks, the unknown track's grey, En Español and Changed in ``on_surface``;
    Registration required keeps ``error`` and New track ``primary`` (D-315).
    """
    tokens = theme.build_tokens(dark=dark, high_contrast=True)
    s = hc_scheme(dark)
    for name, colors in badges(tokens).items():
        assert (colors.fill, colors.border_width) == (None, HC_BADGE_BORDER), name
    ink = BadgeColors(text=str(s.on_surface), border_width=HC_BADGE_BORDER)
    assert set(tokens.tracks.values()) == {ink}
    assert (tokens.unknown_track, tokens.spanish, tokens.changed) == (ink, ink, ink)
    assert tokens.registration.text == s.error
    assert tokens.new_track.text == s.primary


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_every_hc_badge_label_reads_at_7_to_1_on_every_surface(dark: bool) -> None:
    """An outlined label sits on the surface itself: 7:1 on every HC surface role."""
    tokens = theme.build_tokens(dark=dark, high_contrast=True)
    color_scheme = hc_scheme(dark)
    for surface in SURFACES:
        background = hex_role(color_scheme, surface)
        for name, colors in badges(tokens).items():
            ratio = contrast_ratio(colors.text, background)
            assert ratio >= AAA_TEXT, (surface, name, round(ratio, 2))


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_hc_has_a_badge_for_every_track_the_palette_knows(dark: bool) -> None:
    """HC outlines the same track keys the tonal palette colours, no more, no fewer."""
    hc = theme.build_tokens(dark=dark, high_contrast=True)
    standard = theme.build_tokens(dark=dark, high_contrast=False)
    assert hc.tracks.keys() == standard.tracks.keys()


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_outside_hc_every_badge_keeps_its_1_dp_border(dark: bool) -> None:
    """The standard schemes' badges are unchanged: a 1 dp border on every one."""
    tokens = theme.build_tokens(dark=dark, high_contrast=False)
    for name, colors in badges(tokens).items():
        assert colors.border_width == 1, name


def test_an_hc_badge_is_drawn_with_a_1_5_dp_border_and_no_fill() -> None:
    """``TrackBadge`` draws an HC badge as its label in a 1.5 dp outline, unfilled."""
    colors = theme.HC_LIGHT_TOKENS.track_badge("Talk")
    badge = TrackBadge("Talk", colors)
    assert isinstance(badge, ft.Container) and isinstance(badge.content, ft.Text)
    assert badge.bgcolor is None
    assert badge.border == ft.Border.all(1.5, "#1A1D24")
    assert badge.content.color == "#1A1D24"


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_hc_cards_are_flat_with_a_1_dp_outline(dark: bool) -> None:
    """HC cards have no shadow and a 1 dp border in ``outline``, named as a hex.

    In a component theme a role resolves against the seeded scheme (U64), where
    ``outline`` is a mid grey, so the colour is the HC scheme's own value.
    """
    cards = theme.build_theme(dark=dark, high_contrast=True).card_theme
    assert cards is not None and cards.elevation == 0
    shape = cards.shape
    assert isinstance(shape, ft.RoundedRectangleBorder) and shape.radius == 12
    assert shape.side is not None
    assert (shape.side.width, shape.side.color) == (1, hc_scheme(dark).outline)
    assert re.fullmatch(r"#[0-9A-F]{6}", str(shape.side.color))


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_standard_cards_keep_material_s_defaults(dark: bool) -> None:
    """Outside HC the theme sets no card theme: cards keep their fills and shadows."""
    assert theme.build_theme(dark=dark, high_contrast=False).card_theme is None


@pytest.mark.parametrize(
    ("setting", "os_flag", "shown"),
    [
        ("system", True, True),
        ("system", False, False),
        ("on", False, True),
        ("off", True, False),
    ],
)
def test_the_page_shows_high_contrast_in_both_slots_when_asked(
    setting: str, os_flag: bool, shown: bool
) -> None:
    """The OS flag, or the setting, puts the HC schemes in the light and dark slots."""
    page = FakePage()
    prefs = Prefs(high_contrast=setting, os_high_contrast=os_flag)  # type: ignore[arg-type]
    apply_theme(cast(ft.Page, page), prefs)
    assert page.theme is not None and page.dark_theme is not None
    expected = (HC_LIGHT, HC_DARK) if shown else (theme.LIGHT_SCHEME, theme.DARK_SCHEME)
    assert (page.theme.color_scheme, page.dark_theme.color_scheme) == expected
