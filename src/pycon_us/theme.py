"""The app's Material 3 themes, colour tokens and Markdown style sheet (D-22..D-28).

One theme per colour scheme, identical on Android and iOS (D-10): seeded from the PyCon
indigo with neutral surfaces, the brand overrides of ``docs/ux.md`` §3.2, the bundled Roboto
(D-105), left-aligned app-bar titles, per-platform page transitions (D-11) and the system
bar style of D-113. ``Tokens`` holds the colours Material 3 has no role for (D-24), and
``MARKDOWN_STYLE`` is the one style sheet every feed text uses (D-116).

The high-contrast schemes arrive in P2 (THEME-04, THEME-05); until then the
``high_contrast`` flag selects the standard ones.
"""

from dataclasses import dataclass

import flet as ft

SEED = "#3B3EA9"
"""PyCon indigo: the seed of every scheme and the light ``primary`` (ux.md §3.1)."""

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
# (packages/flet/lib/src/utils/theme.dart, neutralizeSurfaces) so the test sees them too.
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
        high_contrast: Build the high-contrast variant. Ignored until P2 (THEME-04,
            THEME-05): the standard scheme is returned.

    Returns:
        A Material 3 theme; nothing in it depends on the platform except the page
        transitions (D-11).
    """
    return ft.Theme(
        color_scheme_seed=SEED,
        surfaces=ft.ThemeSurfaces.NEUTRAL,
        color_scheme=DARK_SCHEME if dark else LIGHT_SCHEME,
        font_family=FONT_FAMILY,
        appbar_theme=ft.AppBarTheme(center_title=False),  # iOS would centre it (D-10)
        page_transitions=ft.PageTransitionsTheme(
            android=ft.PageTransitionTheme.PREDICTIVE,  # Android 14+ predictive Back
            ios=ft.PageTransitionTheme.CUPERTINO,  # keeps the iOS edge swipe (D-11)
        ),
        system_overlay_style=overlay_style(dark=dark),
    )


def overlay_style(*, dark: bool) -> ft.SystemOverlayStyle:
    """Return the status- and navigation-bar style for a light or dark scheme (D-113).

    The icons contrast with the scheme. Navigation-bar contrast is not enforced: the
    Android scrim put grey 3-button icons on dark grey (2.3:1, #311). The status bar is
    transparent, since the app draws under it. Below Android 15 the app does not draw
    under the navigation bar, so that bar gets the ``NavigationBar``'s colour; a
    transparent one would show the window background, which a live dark-mode switch
    leaves in the old mode (D-151). Android 15 and later ignore that colour.

    Args:
        dark: The scheme is dark.

    Returns:
        The style for ``Theme.system_overlay_style``.
    """
    icons = ft.Brightness.LIGHT if dark else ft.Brightness.DARK
    return ft.SystemOverlayStyle(
        status_bar_color=ft.Colors.TRANSPARENT,
        # A role resolves against the seeded scheme: the NavigationBar's default fill.
        system_navigation_bar_color=ft.Colors.SURFACE_CONTAINER,
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

    Each reads at 4.5:1 or better on every surface of its scheme (tests/test_theme.py).
    Screens get the current scheme's tokens from ``use_tokens()``.

    Attributes:
        live: Happening now, open now.
        warning: Stale data, overlaps, pending scans.
        success: Scan accepted.
        favorite: The filled star.
    """

    live: str
    warning: str
    success: str
    favorite: str


LIGHT_TOKENS = Tokens(
    live="#1B6E35",
    warning="#7A5900",
    success="#1B6E35",
    favorite="#A1009A",  # the light tertiary (tested)
)
"""Tokens for the light scheme (ux.md §3.3)."""

DARK_TOKENS = Tokens(
    live="#8BD89A",
    warning="#F2C14E",
    success="#8BD89A",
    favorite="#FFACEB",  # the dark tertiary (tested)
)
"""Tokens for the dark scheme (ux.md §3.3)."""


def build_tokens(*, dark: bool, high_contrast: bool) -> Tokens:
    """Return the tokens that go with ``build_theme(dark=..., high_contrast=...)``.

    Args:
        dark: The dark scheme.
        high_contrast: The high-contrast variant; ignored until P2, like in
            ``build_theme``.

    Returns:
        The scheme's tokens.
    """
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


_TEXT = ft.Colors.ON_SURFACE
_HEADING = ft.FontWeight.W_500
_BODY = ft.TextStyle(size=16, height=1.5, color=_TEXT, font_family=FONT_FAMILY)


def _heading(size: int) -> ft.TextStyle:
    return ft.TextStyle(
        size=size, weight=_HEADING, color=_TEXT, font_family=FONT_FAMILY
    )


MARKDOWN_STYLE = ft.MarkdownStyleSheet(
    a_text_style=ft.TextStyle(
        color=ft.Colors.PRIMARY,
        decoration=ft.TextDecoration.UNDERLINE,
        decoration_color=ft.Colors.PRIMARY,  # unnamed, it was near-black in dark
        font_family=FONT_FAMILY,
    ),
    del_text_style=ft.TextStyle(
        color=_TEXT,
        decoration=ft.TextDecoration.LINE_THROUGH,
        decoration_color=_TEXT,
        font_family=FONT_FAMILY,
    ),
    p_text_style=_BODY,
    list_bullet_text_style=_BODY,
    blockquote_text_style=_BODY,
    h1_text_style=_heading(22),
    h2_text_style=_heading(18),
    h3_text_style=_heading(16),
    h4_text_style=_heading(16),
    code_text_style=ft.TextStyle(
        size=14,
        color=_TEXT,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        font_family="monospace",  # Android's alias; iOS has no such family
        font_family_fallback=["Menlo"],  # so iOS takes its system monospace font
    ),
    blockquote_decoration=ft.BoxDecoration(
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        border=ft.Border(left=ft.BorderSide(4, ft.Colors.OUTLINE)),
    ),
    block_spacing=12,
)
"""The style sheet of every feed text (D-116): pass it as ``ft.Markdown(md_style_sheet=...)``.

A style given here replaces the theme's instead of merging with it (F28), so every text
style names its colour and font family, and every decoration its colour (D-152):
Markdown text does not inherit the theme's font (on iOS it rendered in SF Pro), and an
unnamed decoration colour drew near-black lines on the dark surface. The colours are
scheme roles, resolved against the theme on screen, so this one sheet serves every
scheme. h5 and h6 keep Flet's defaults, which come from the theme's text styles and so
carry its colour and font.
"""
