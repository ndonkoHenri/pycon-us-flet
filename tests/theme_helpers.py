"""Colour helpers the theme tests share: WCAG contrast, CIELAB distance, scheme lookups.

The assertions stay in the test modules (`tests/test_theme*.py`, `tests/test_high_contrast*.py`
and the screens' own contrast tests); this module holds what they compute with and the
constants they check against, so nothing is imported from a collected test module.
"""

import dataclasses
import math

import flet as ft

from pycon_us import theme
from pycon_us.theme_badges import BadgeColors

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

AAA_TEXT = 7.0
"""High contrast's text minimum (D-23, D-33)."""

TEXT_TOKENS = ("live", "warning", "success", "favorite")
"""The tokens that are a text colour on the surfaces; the others are badges."""


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
