"""Tests for the high-contrast colour schemes and how the app picks them.

D-23, D-151, D-265; THEME-04, THEME-05; ux.md §3.2; testing-and-quality.md §7.1.
"""

import dataclasses
import re
from typing import cast

import flet as ft
import pytest

from pycon_us import theme
from pycon_us.app import apply_theme
from pycon_us.prefs import Prefs
from pycon_us.theme_hc import HC_DARK, HC_LIGHT
from tests.fakes import FakePage
from tests.test_theme import FLET_THEME_DART, contrast_ratio, hex_role

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
    """Font, seed, transitions, tiles and bar icons are the standard theme's (D-151)."""
    standard = theme.build_theme(dark=dark, high_contrast=False)
    high = theme.build_theme(dark=dark, high_contrast=True)
    assert standard.system_overlay_style is not None
    assert high.system_overlay_style is not None
    assert dataclasses.replace(
        high.system_overlay_style, system_navigation_bar_color=None
    ) == dataclasses.replace(
        standard.system_overlay_style, system_navigation_bar_color=None
    )
    assert dataclasses.replace(
        high, color_scheme=None, system_overlay_style=None
    ) == dataclasses.replace(standard, color_scheme=None, system_overlay_style=None)


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


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_tokens_stay_the_standard_ones_until_p2_60(dark: bool) -> None:
    """High contrast keeps the standard tokens; P2-60 (#420) gives it its own."""
    assert theme.build_tokens(dark=dark, high_contrast=True) == theme.build_tokens(
        dark=dark, high_contrast=False
    )


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
