"""Tests for high contrast's tokens, badges and cards, and how the page asks for it.

D-23, D-174, D-285; THEME-04..06; ux.md §3.2..§3.4. The schemes themselves, and the
helpers both modules use, are `tests/test_high_contrast.py`'s (#623).
"""

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
from tests.fake_page import FakePage
from tests.test_high_contrast import AAA_TEXT, SURFACES, hc_scheme
from tests.theme_helpers import (
    TEXT_TOKENS,
    badges,
    contrast_ratio,
    hex_role,
)


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

    Tracks, the unknown track's grey, En Español and Changed in `on_surface`;
    Registration required keeps `error` and New track `primary` (D-315).
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
    """`TrackBadge` draws an HC badge as its label in a 1.5 dp outline, unfilled."""
    colors = theme.HC_LIGHT_TOKENS.track_badge("Talk")
    badge = TrackBadge("Talk", colors)
    assert isinstance(badge, ft.Container) and isinstance(badge.content, ft.Text)
    assert badge.bgcolor is None
    assert badge.border == ft.Border.all(1.5, "#1A1D24")
    assert badge.content.color == "#1A1D24"


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_hc_cards_are_flat_with_a_1_dp_outline(dark: bool) -> None:
    """HC cards have no shadow and a 1 dp border in `outline`, named as a hex.

    In a component theme a role resolves against the seeded scheme (U64), where
    `outline` is a mid grey, so the colour is the HC scheme's own value.
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
