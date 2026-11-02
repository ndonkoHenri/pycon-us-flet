"""The app's Material 3 themes and colour tokens (D-22..D-28).

One theme per colour scheme, identical on Android and iOS (D-10): seeded from the PyCon
indigo with neutral surfaces, the brand overrides of ``docs/ux.md`` §3.2, the bundled Roboto
(D-105), left-aligned app-bar titles, per-platform page transitions (D-11) and the system
bar style of D-113. ``Tokens`` holds the colours Material 3 has no role for (D-24), the
track badges among them (D-25, from ``theme_badges.py``). ``MARKDOWN_STYLE``, the one
style sheet every feed text uses (D-116), is ``theme_markdown.py``'s.

The high-contrast schemes, their token colours and their card theme live in
``theme_hc.py`` (THEME-04..06); the ``high_contrast`` flag selects them, and HC's tokens
outline every badge and carry the flag to the components (D-285).
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

import flet as ft

from pycon_us.theme_badges import (
    HC_BADGE_BORDER,
    NEUTRAL,
    SPANISH,
    TRACK_PAIRS,
    BadgeColors,
    tonal,
)
from pycon_us.theme_hc import (
    HC_DARK,
    HC_DARK_LIVE,
    HC_DARK_WARNING,
    HC_LIGHT,
    HC_LIGHT_LIVE,
    HC_LIGHT_WARNING,
    with_hc_components,
)

SEED = "#3B3EA9"
"""PyCon indigo: the seed of every scheme and the light ``primary`` (ux.md §3.1)."""

BOOTH_AMBER = "#F2C14E"
"""A selected expo booth's fill in every scheme, as the plan is the same (ux.md §6.2).

A selected job fair table's too, on the print's purple at well over 3:1 (#402)."""

BOOT_COLOR = "#680579"
"""The splash's purple (``[tool.flet.splash]``, ux.md §2.6): the boot view and the start
route show it in every scheme, so the launch never flashes."""

FONT_FAMILY = "packages/roboto_fonts/Roboto"
"""Roboto 400/500/700 from the local Flutter package (D-26, D-105).

``flet run`` has no such package and falls back to the system font (accepted, D-26).
"""

# Flet builds ColorScheme.fromSeed, neutralises the surfaces, then applies these overrides
# (F9). Every overridden role comes with its "on" partner, so the contrast test can check
# the pair (testing-and-quality.md §7.1). The surface roles repeat Flet's neutral ramp
# (packages/flet/lib/src/utils/theme.dart, neutralizeSurfaces), and the error roles the
# seed's own (Material's error palette: tones 40 and 100 in light, 80 and 20 in dark), so
# the test sees them too: the "Registration required" badge is drawn in error.
_ERROR_LIGHT = "#BA1A1A"
_ERROR_DARK = "#FFB4AB"

LIGHT_SCHEME = ft.ColorScheme(
    primary=SEED,
    on_primary="#FFFFFF",
    primary_container="#E1E0FF",
    on_primary_container="#13126B",
    secondary="#680579",
    on_secondary="#FFFFFF",
    secondary_container="#FCD6FF",
    on_secondary_container="#36003F",
    tertiary="#A1009A",  # Ionic's magenta #DD04D2 darkened to 7:1 on white (D-22)
    on_tertiary="#FFFFFF",
    tertiary_container="#FFD7F3",
    on_tertiary_container="#3B0037",
    error=_ERROR_LIGHT,
    on_error="#FFFFFF",
    surface="#FFFFFF",
    on_surface="#1B1B1B",
    on_surface_variant="#5E5E5E",
)
"""The light scheme's overrides (ux.md §3.2)."""

DARK_SCHEME = ft.ColorScheme(
    primary="#BFC1FF",
    on_primary="#1F2189",
    primary_container=SEED,
    on_primary_container="#E1E0FF",
    secondary="#F4AEFF",
    on_secondary="#52005E",
    secondary_container="#680579",
    on_secondary_container="#FCD6FF",
    tertiary="#FFACEB",
    on_tertiary="#5E0058",
    tertiary_container="#85007F",
    on_tertiary_container="#FFD7F3",
    error=_ERROR_DARK,
    on_error="#690005",
    surface="#121212",
    on_surface="#E7E7E7",
    on_surface_variant="#ABABAB",
)
"""The dark scheme's overrides: tuned light tones of the same brand (ux.md §3.2)."""


THEME_MODES = {
    "system": ft.ThemeMode.SYSTEM,
    "light": ft.ThemeMode.LIGHT,
    "dark": ft.ThemeMode.DARK,
}
"""``page.theme_mode`` for each Appearance setting (``Prefs.theme``, THEME-01).

Under ``system`` Flutter itself switches between ``page.theme`` and ``page.dark_theme``
when the OS changes mode.
"""


def build_theme(*, dark: bool, high_contrast: bool) -> ft.Theme:
    """Build the theme for one colour scheme (architecture §15).

    ``page.theme`` gets the light result and ``page.dark_theme`` the dark one.

    Args:
        dark: Build the dark scheme instead of the light one.
        high_contrast: Build the high-contrast variant (THEME-04, THEME-05), which sets
            every role by hand (``theme_hc.py``) and draws lines where fills drew
            edges: cards, chips and the selected pill (THEME-06, D-306); the rest of
            the theme is the same.

    Returns:
        A Material 3 theme; nothing in it depends on the platform except the page
        transitions (D-11).
    """
    if high_contrast:
        scheme = HC_DARK if dark else HC_LIGHT
    else:
        scheme = DARK_SCHEME if dark else LIGHT_SCHEME
    built = ft.Theme(
        color_scheme_seed=SEED,
        surfaces=ft.ThemeSurfaces.NEUTRAL,
        color_scheme=scheme,
        # Flet builds ThemeData, which derives these, from the seeded scheme, before the
        # overrides apply: unnamed, HC's page stayed white under cream bars (U64, #483).
        scaffold_bgcolor=scheme.surface,
        canvas_color=scheme.surface,
        card_bgcolor=scheme.surface,
        divider_color=scheme.outline,
        font_family=FONT_FAMILY,
        appbar_theme=ft.AppBarTheme(center_title=False),  # iOS would centre it (D-10)
        page_transitions=ft.PageTransitionsTheme(
            android=ft.PageTransitionTheme.PREDICTIVE,  # Android 14+ predictive Back
            ios=ft.PageTransitionTheme.CUPERTINO,  # keeps the iOS edge swipe (D-11)
        ),
        system_overlay_style=overlay_style(dark=dark, high_contrast=high_contrast),
        # A tall tile's icons beside its title's first line, not the middle of the
        # block (D-188), fold headers (FoldTile's ListTile, D-354) included.
        list_tile_theme=ft.ListTileTheme(
            title_alignment=ft.ListTileTitleAlignment.TITLE_HEIGHT
        ),
    )
    return with_hc_components(built, dark=dark) if high_contrast else built


def overlay_style(*, dark: bool, high_contrast: bool) -> ft.SystemOverlayStyle:
    """Return the status- and navigation-bar style for a light or dark scheme (D-113).

    The icons contrast with the scheme. Navigation-bar contrast is not enforced: the
    Android scrim put grey 3-button icons on dark grey (2.3:1, #311). The status bar is
    transparent, since the app draws under it. Below Android 15 the app does not draw
    under the navigation bar, so that bar gets the ``NavigationBar``'s colour; a
    transparent one would show the window background, which a live dark-mode switch
    leaves in the old mode (D-151). Android 15 and later ignore that colour.

    Flet resolves a role in this style against the seeded, neutralised scheme, before
    the overrides apply (``parseTheme`` in Flet's ``utils/theme.dart``). The standard
    schemes keep that ramp's ``surface_container``, so the role is the bar's colour;
    the high-contrast ones replace it, so they name their own (D-265).

    Args:
        dark: The scheme is dark.
        high_contrast: The scheme is a high-contrast one.

    Returns:
        The style for ``Theme.system_overlay_style``.
    """
    icons = ft.Brightness.LIGHT if dark else ft.Brightness.DARK
    if high_contrast:
        navigation_bar = (HC_DARK if dark else HC_LIGHT).surface_container
    else:  # the NavigationBar's default fill
        navigation_bar = ft.Colors.SURFACE_CONTAINER
    return ft.SystemOverlayStyle(
        status_bar_color=ft.Colors.TRANSPARENT,
        system_navigation_bar_color=navigation_bar,
        status_bar_icon_brightness=icons,  # Android
        system_navigation_bar_icon_brightness=icons,  # Android
        status_bar_brightness=(  # iOS: the bar's background, so the opposite of icons
            ft.Brightness.DARK if dark else ft.Brightness.LIGHT
        ),
        enforce_system_navigation_bar_contrast=False,
    )


@dataclass(frozen=True)
class Tokens:
    """Colours Material 3 has no role for (D-24), as ``#RRGGBB`` for one scheme.

    Each text colour reads at 4.5:1 or better on every surface of its scheme, and each
    badge's label on its fill (tests/test_theme.py, tests/test_theme_badges.py); 7:1
    in high contrast (tests/test_high_contrast.py). Compared and hashed by value, so
    they can be a dictionary key. Screens get the current scheme's tokens from
    ``use_tokens()``.

    Attributes:
        live: Happening now, open now.
        warning: Stale data, overlaps, pending scans.
        success: Scan accepted.
        favorite: The filled star.
        tracks: Each track's badge, by track key (D-25); read it through
            ``track_badge()``, which knows the fallback.
        unknown_track: The badge of a track the palette lacks: the neutral grey.
        spanish: The "En Español" badge (D-25).
        registration: The "Registration required" badge, outlined in ``error``.
        new_track: The "New track" badge, outlined in ``primary``: a mark of status,
            not another category among the tonal track fills (D-199).
        changed: The "Changed" badge of a session whose time, room or title changed in
            the last 24 h, outlined in ``warning``: a mark of status, like New track,
            and never En Español's fill (D-315).
        booth_outline: A selected expo booth's outline, 3:1 or better on white (the
            booths), on ``surface`` and on ``booth_fill`` (EXPO-01).
        booth_fill: A selected booth's fill (ux.md §6.2), drawn see-through over the
            plan, and every booth's faint outline.
        high_contrast: The tokens are a high-contrast scheme's, whose structure
            differs too: a component that draws a line there instead of a fill or a
            shadow reads it here, never from ``Prefs`` (D-285).
    """

    live: str
    warning: str
    success: str
    favorite: str
    # A read-only mapping is unhashable, so it stays out of the generated __hash__; equal
    # tokens have equal other fields, so the hash still agrees with ==.
    tracks: Mapping[str, BadgeColors] = field(hash=False)
    unknown_track: BadgeColors
    spanish: BadgeColors
    registration: BadgeColors
    new_track: BadgeColors
    changed: BadgeColors
    booth_outline: str
    booth_fill: str = BOOTH_AMBER
    high_contrast: bool = False

    def track_badge(self, key: str) -> BadgeColors:
        """Return the badge colours of track ``key``; the neutral grey if it has none."""
        return self.tracks.get(key, self.unknown_track)


def _tokens(
    *,
    dark: bool,
    live: str,
    warning: str,
    favorite: str,
    primary: str,
    booth_outline: str,
) -> Tokens:
    """Build one scheme's tokens: the given colours and that scheme's badges."""
    return Tokens(
        live=live,
        warning=warning,
        success=live,  # ux.md §3.3: success is live
        favorite=favorite,
        # Read-only, as the tokens are frozen; a test checks every pair.
        tracks=MappingProxyType(
            {key: tonal(pair, dark=dark) for key, pair in TRACK_PAIRS.items()}
        ),
        unknown_track=tonal(NEUTRAL, dark=dark),
        spanish=tonal(SPANISH, dark=dark),
        registration=BadgeColors(text=_ERROR_DARK if dark else _ERROR_LIGHT),
        new_track=BadgeColors(text=primary),
        changed=BadgeColors(text=warning),
        booth_outline=booth_outline,
    )


LIGHT_TOKENS = _tokens(
    dark=False,
    live="#1B6E35",
    warning="#7A5900",
    favorite="#A1009A",  # the light tertiary (tested)
    primary=SEED,  # the light primary (tested)
    booth_outline="#5C4300",
)
"""Tokens for the light scheme (ux.md §3.3, §3.4)."""

DARK_TOKENS = _tokens(
    dark=True,
    live="#8BD89A",
    warning="#F2C14E",
    favorite="#FFACEB",  # the dark tertiary (tested)
    primary="#BFC1FF",  # the dark primary (tested)
    booth_outline="#8A6500",  # 3:1 on white, on surface and on the amber alike
)
"""Tokens for the dark scheme (ux.md §3.3, §3.4)."""


def _hc_tokens(
    scheme: ft.ColorScheme, *, live: str, warning: str, booth_outline: str
) -> Tokens:
    """Build a high-contrast scheme's tokens: every badge outlined (ux.md §3.4).

    Tracks, En Español and Changed are outlined in ``on_surface``, which the star takes
    too; Registration required keeps ``error`` and New track ``primary`` (D-315).
    """
    ink, error, primary = str(scheme.on_surface), str(scheme.error), str(scheme.primary)
    outlined = BadgeColors(text=ink, border_width=HC_BADGE_BORDER)
    return Tokens(
        live=live,
        warning=warning,
        success=live,
        favorite=ink,
        tracks=MappingProxyType(dict.fromkeys(TRACK_PAIRS, outlined)),
        unknown_track=outlined,
        spanish=outlined,
        registration=BadgeColors(text=error, border_width=HC_BADGE_BORDER),
        new_track=BadgeColors(text=primary, border_width=HC_BADGE_BORDER),
        changed=outlined,
        booth_outline=booth_outline,
        high_contrast=True,
    )


HC_LIGHT_TOKENS = _hc_tokens(
    HC_LIGHT,
    live=HC_LIGHT_LIVE,
    warning=HC_LIGHT_WARNING,
    booth_outline=str(HC_LIGHT.on_surface),
)
"""Tokens for the high-contrast light scheme (ux.md §3.3, §3.4)."""

HC_DARK_TOKENS = _hc_tokens(
    HC_DARK, live=HC_DARK_LIVE, warning=HC_DARK_WARNING, booth_outline="#7F5D00"
)
"""Tokens for the high-contrast dark scheme (ux.md §3.3, §3.4)."""


def build_tokens(*, dark: bool, high_contrast: bool) -> Tokens:
    """Return the tokens that go with ``build_theme(dark=..., high_contrast=...)``.

    Args:
        dark: The dark scheme.
        high_contrast: The high-contrast variant (D-285).

    Returns:
        The scheme's tokens.
    """
    if high_contrast:
        return HC_DARK_TOKENS if dark else HC_LIGHT_TOKENS
    return DARK_TOKENS if dark else LIGHT_TOKENS


TokensCtx = ft.create_context(LIGHT_TOKENS)
"""Carries the current scheme's ``Tokens`` (D-150).

``App`` provides ``build_tokens()`` for the scheme it shows. The value is plain, not an
observable, so reading it subscribes to nothing: ``App`` re-renders when the scheme
changes, and its subtree with it. Without a provider, the light tokens apply.
"""


def use_tokens() -> Tokens:
    """Return the tokens of the colour scheme on screen (D-24, D-150).

    A hook: call it unconditionally, at the top of a component (D-70).
    """
    return ft.use_context(TokensCtx)
