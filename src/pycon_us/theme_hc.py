"""The high-contrast light and dark colour schemes (D-23; THEME-04, THEME-05).

Hand-authored from ``docs/ux.md`` §3.2: every ``ft.ColorScheme`` role is set here, so
none falls back to the seed that ``theme.build_theme()`` still passes (F9), and every
text colour reads at 7:1 or better on what it sits on (tests/test_high_contrast.py).
Light is dark purple and ink on cream; dark is yellow and paper white on near-black.

The rules the values follow, beyond §3.2's table:

- One surface: ``surface_bright``, ``surface_dim`` and the five ``surface_container*``
  roles equal ``surface``, so a card or a bar is told apart by its outline, not by a
  tint of grey (THEME-06 adds those outlines, P2-60). ``surface_tint`` is ``surface``
  too, so elevation tints nothing.
- Strong roles are their own containers: ``primary_container`` and
  ``error_container`` equal their role. ``secondary_container`` is a quiet fill under
  ink, and ``tertiary_container`` repeats it (§3.2).
- Lines are ink: ``outline`` and ``outline_variant`` are the text colour, 7:1 or more
  on every surface where WCAG asks only 3:1 of a boundary.
- The inverse roles (SnackBars) swap the schemes: ``inverse_surface`` is the text
  colour, ``on_inverse_surface`` the surface, and ``inverse_primary`` the other
  scheme's ``primary``.
- The fixed roles, which Material keeps the same in light and dark, are one neutral
  pair under ink in both schemes; no screen uses them.

With one surface, high contrast draws structure with lines (THEME-06, D-285): the token
colours below (``theme.py`` builds HC's ``Tokens`` from them and outlines every badge)
and ``hc_card_theme()``, which trades the cards' shadows and fills
for a border.

Module of its own because ``theme.py`` is near D-66's 400 lines (decisions §M).
"""

import flet as ft

_HC_INK = "#1A1D24"
"""HC light's text, outlines and inverse surface."""

_HC_CREAM = "#FBFAF6"
"""HC light's one surface."""

_HC_PURPLE = "#4A0072"
"""HC light's primary, secondary and tertiary: 13.1:1 on the cream."""

_HC_NIGHT = "#0B0F17"
"""HC dark's one surface, and the text on its yellow."""

_HC_PAPER = "#F5F5F0"
"""HC dark's text, outlines and inverse surface."""

_HC_YELLOW = "#FFD60A"
"""HC dark's primary and tertiary: 13.6:1 on the night."""

_FIXED = "#E9E7E1"
"""Every ``*_fixed`` role in both schemes (13.6:1 under ink)."""

_FIXED_DIM = "#D6D3CB"
"""Every ``*_fixed_dim`` role in both schemes (11.3:1 under ink)."""

HC_LIGHT_LIVE = "#0F5A26"
"""HC light's ``live`` and ``success`` token: 8.0:1 on the cream (ux.md §3.3)."""

HC_LIGHT_WARNING = "#7A4A00"
"""HC light's ``warning`` token: 7.2:1 on the cream."""

HC_DARK_LIVE = "#30D158"
"""HC dark's ``live`` and ``success`` token: 9.5:1 on the night."""

HC_DARK_WARNING = _HC_YELLOW
"""HC dark's ``warning`` token, its primary yellow: 13.6:1 on the night."""

HC_LIGHT = ft.ColorScheme(
    primary=_HC_PURPLE,
    on_primary="#FFFFFF",
    primary_container=_HC_PURPLE,
    on_primary_container="#FFFFFF",
    secondary=_HC_PURPLE,
    on_secondary="#FFFFFF",
    secondary_container="#E9E7E1",
    on_secondary_container=_HC_INK,
    tertiary=_HC_PURPLE,
    on_tertiary="#FFFFFF",
    tertiary_container="#E9E7E1",
    on_tertiary_container=_HC_INK,
    error="#8C0009",
    on_error="#FFFFFF",
    error_container="#8C0009",
    on_error_container="#FFFFFF",
    surface=_HC_CREAM,
    on_surface=_HC_INK,
    on_surface_variant=_HC_INK,
    outline=_HC_INK,
    outline_variant=_HC_INK,
    shadow="#000000",
    scrim="#000000",
    inverse_surface=_HC_INK,
    on_inverse_surface=_HC_CREAM,
    inverse_primary=_HC_YELLOW,
    surface_tint=_HC_CREAM,
    primary_fixed=_FIXED,
    primary_fixed_dim=_FIXED_DIM,
    on_primary_fixed=_HC_INK,
    on_primary_fixed_variant=_HC_INK,
    secondary_fixed=_FIXED,
    secondary_fixed_dim=_FIXED_DIM,
    on_secondary_fixed=_HC_INK,
    on_secondary_fixed_variant=_HC_INK,
    tertiary_fixed=_FIXED,
    tertiary_fixed_dim=_FIXED_DIM,
    on_tertiary_fixed=_HC_INK,
    on_tertiary_fixed_variant=_HC_INK,
    surface_bright=_HC_CREAM,
    surface_dim=_HC_CREAM,
    surface_container_lowest=_HC_CREAM,
    surface_container_low=_HC_CREAM,
    surface_container=_HC_CREAM,
    surface_container_high=_HC_CREAM,
    surface_container_highest=_HC_CREAM,
)
"""The high-contrast light scheme: every role (THEME-04, ux.md §3.2)."""

HC_DARK = ft.ColorScheme(
    primary=_HC_YELLOW,
    on_primary=_HC_NIGHT,
    primary_container=_HC_YELLOW,
    on_primary_container=_HC_NIGHT,
    secondary=_HC_PAPER,
    on_secondary=_HC_NIGHT,
    secondary_container="#21252F",
    on_secondary_container=_HC_PAPER,
    tertiary=_HC_YELLOW,
    on_tertiary=_HC_NIGHT,
    tertiary_container="#21252F",
    on_tertiary_container=_HC_PAPER,
    error="#FFB4AB",
    on_error=_HC_NIGHT,
    error_container="#FFB4AB",
    on_error_container=_HC_NIGHT,
    surface=_HC_NIGHT,
    on_surface=_HC_PAPER,
    on_surface_variant=_HC_PAPER,
    outline=_HC_PAPER,
    outline_variant=_HC_PAPER,
    shadow="#000000",
    scrim="#000000",
    inverse_surface=_HC_PAPER,
    on_inverse_surface=_HC_NIGHT,
    inverse_primary=_HC_PURPLE,
    surface_tint=_HC_NIGHT,
    primary_fixed=_FIXED,
    primary_fixed_dim=_FIXED_DIM,
    on_primary_fixed=_HC_INK,
    on_primary_fixed_variant=_HC_INK,
    secondary_fixed=_FIXED,
    secondary_fixed_dim=_FIXED_DIM,
    on_secondary_fixed=_HC_INK,
    on_secondary_fixed_variant=_HC_INK,
    tertiary_fixed=_FIXED,
    tertiary_fixed_dim=_FIXED_DIM,
    on_tertiary_fixed=_HC_INK,
    on_tertiary_fixed_variant=_HC_INK,
    surface_bright=_HC_NIGHT,
    surface_dim=_HC_NIGHT,
    surface_container_lowest=_HC_NIGHT,
    surface_container_low=_HC_NIGHT,
    surface_container=_HC_NIGHT,
    surface_container_high=_HC_NIGHT,
    surface_container_highest=_HC_NIGHT,
)
"""The high-contrast dark scheme: every role (THEME-05, ux.md §3.2)."""


def hc_card_theme(*, dark: bool) -> ft.CardTheme:
    """Return a high-contrast scheme's card theme: no shadow, a 1 dp border (THEME-06).

    Every card variant lies flat on the one surface and is told apart by its outline;
    the 12 dp corners are Material 3's for every variant. The border names the scheme's
    ``outline`` as a hex: Flet resolves a role in a component theme against the seeded
    scheme, before the overrides apply, where it is a mid grey (U64, #483).

    Args:
        dark: The high-contrast dark scheme's cards instead of the light one's.
    """
    outline = _HC_PAPER if dark else _HC_INK  # each scheme's outline
    return ft.CardTheme(
        elevation=0,
        shape=ft.RoundedRectangleBorder(
            radius=12, side=ft.BorderSide(width=1, color=outline)
        ),
    )
