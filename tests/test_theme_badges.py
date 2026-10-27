"""Tests for the tokens and the badge colours: contrast, distinctness and roles.

D-22..D-26, D-33, D-255, D-315. The contrast helpers and ``badges()`` are
``tests/test_theme.py``'s; the high-contrast badges have tests/test_high_contrast.py.
"""

import dataclasses
import itertools
from types import MappingProxyType

import pytest

from pycon_us import config, theme
from pycon_us.theme_badges import BadgeColors
from tests.test_theme import (
    AA_TEXT,
    NEUTRAL_SURFACES,
    TEXT_TOKENS,
    badges,
    color_distance,
    contrast_ratio,
    hex_role,
    scheme,
)

BADGE_TOKENS = (
    "tracks",
    "unknown_track",
    "spanish",
    "registration",
    "new_track",
    "changed",
)


YEARS = sorted(
    int(path.name) for path in config.DATA_DIR.iterdir() if path.name.isdigit()
)


def test_every_token_is_a_checked_text_colour_or_badge() -> None:
    """Every token is a text colour or a badge, so a contrast test checks it.

    A new token must join one of the contrast tests, not slip past both; the one
    field that is no colour is the high-contrast flag (D-285).
    """
    names = {field.name for field in dataclasses.fields(theme.Tokens)}
    assert names == {*TEXT_TOKENS, *BADGE_TOKENS, *BOOTH_TOKENS, "high_contrast"}


BOOTH_TOKENS = ("booth_outline", "booth_fill")
"""The tokens a selected expo booth is drawn with (EXPO-01)."""


BOOTH_SCHEMES = {
    "light": (theme.LIGHT_TOKENS, "#FFFFFF"),
    "dark": (theme.DARK_TOKENS, "#121212"),
    "hc light": (theme.HC_LIGHT_TOKENS, str(theme.HC_LIGHT.surface)),
    "hc dark": (theme.HC_DARK_TOKENS, str(theme.HC_DARK.surface)),
}
"""Each scheme's tokens and its ``surface``, which the expo plan sits on."""


@pytest.mark.parametrize("name", BOOTH_SCHEMES)
def test_a_selected_booths_outline_passes_3_to_1(name: str) -> None:
    """The outline reads at 3:1 on white, on ``surface`` and on the amber fill.

    The booths are white tiles on the plan, the plan sits on ``surface``, and the
    fill is inside the outline: WCAG 1.4.11's 3:1 for a component's boundary, in
    every scheme (ux.md §6.2; Ionic's selection was 1.7:1).
    """
    tokens, surface = BOOTH_SCHEMES[name]
    outline = tokens.booth_outline
    for against in ("#FFFFFF", surface, tokens.booth_fill):
        assert contrast_ratio(outline, against) >= 3, (name, outline, against)


def test_high_contrast_changes_the_booth_outline() -> None:
    """High contrast has outlines of its own: ink on its light scheme (D-285)."""
    assert theme.HC_LIGHT_TOKENS.booth_outline == str(theme.HC_LIGHT.on_surface)
    assert theme.HC_DARK_TOKENS.booth_outline != theme.DARK_TOKENS.booth_outline


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_every_badge_reads_at_aa(dark: bool) -> None:
    """Every badge's label reads at AA on its fill, or on every surface if outlined.

    D-25: a tonal badge's label on its fill; an outlined badge's label sits on the
    surface itself, so on every surface of the neutral ramp. WCAG 2.x formula.
    """
    tokens = theme.build_tokens(dark=dark, high_contrast=False)
    for name, colors in badges(tokens).items():
        backgrounds = [colors.fill] if colors.fill else NEUTRAL_SURFACES[dark]
        for background in backgrounds:
            ratio = contrast_ratio(background, colors.text)
            assert ratio >= AA_TEXT, (name, background, colors.text, round(ratio, 2))


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_every_badge_fill_differs_from_every_other(dark: bool) -> None:
    """Any two badge fills differ by a CIE76 distance of at least 10.

    The label carries the meaning (D-33), but two tracks of near-equal colour would look
    like one, and En Español beside a track like part of it (#181's review). So any two
    fills, the grey of breaks included, differ by 10.
    """
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
    """Every track key in every year's registry has a badge of its own.

    Palette keys must equal the registry's keys exactly, spaces and capitals included
    (THEME-08), or a track would fall back to the grey.
    """
    tokens = theme.build_tokens(dark=dark, high_contrast=False)
    keys = {track.key for track in config.load_year(year).conference.tracks}
    assert keys - tokens.tracks.keys() == set()


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_notices_summits_events_and_breaks_get_colours(dark: bool) -> None:
    """Notices and breaks share the grey; summits and events get two other colours.

    Ionic left them all grey, with no entry (SCHED-20).
    """
    tokens = theme.build_tokens(dark=dark, high_contrast=False)
    grey = tokens.unknown_track
    assert tokens.track_badge("Informational") == tokens.track_badge("Break") == grey
    assert tokens.track_badge("Summit") != grey
    assert tokens.track_badge("Event") != grey
    assert tokens.track_badge("Summit") != tokens.track_badge("Event")


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_an_unknown_track_gets_the_neutral_badge(dark: bool) -> None:
    """An unknown track gets the neutral badge, which has a fill."""
    tokens = theme.build_tokens(dark=dark, high_contrast=False)
    assert tokens.track_badge("Workshop") == tokens.unknown_track
    assert tokens.unknown_track.fill is not None


def test_en_espanol_is_the_tonal_pair_inverted_in_dark() -> None:
    """En Español is #5E0058 on #FFD7F3 (10.06:1) in light, the pair inverted in dark.

    D-25: instead of Ionic's #DD04D2 (4.18:1).
    """
    light, dark = theme.LIGHT_TOKENS.spanish, theme.DARK_TOKENS.spanish
    assert light == BadgeColors(text="#5E0058", fill="#FFD7F3")
    assert dark == BadgeColors(text="#FFD7F3", fill="#5E0058")
    ratio = contrast_ratio(light.text, light.fill or "")
    assert ratio == pytest.approx(10.06, abs=0.01)


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_registration_badge_is_outlined_in_the_error_role(dark: bool) -> None:
    """The registration badge is outlined, its text in the error role."""
    registration = theme.build_tokens(dark=dark, high_contrast=False).registration
    assert registration == BadgeColors(text=hex_role(scheme(dark), "error"))
    assert registration.fill is None  # outlined


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_new_track_badge_is_outlined_in_the_primary_role(dark: bool) -> None:
    """The new-track badge is outlined, its text in the primary role.

    D-199: a status mark beside a track's badge, not one more tonal fill, which in light
    sat 6.8 from the En Español pink and in dark outshone every track.
    """
    new_track = theme.build_tokens(dark=dark, high_contrast=False).new_track
    assert new_track == BadgeColors(text=hex_role(scheme(dark), "primary"))
    assert new_track.fill is None  # outlined


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_changed_badge_is_outlined_in_the_warning_token(dark: bool) -> None:
    """The Changed badge is outlined in ``warning``, never En Español's tonal fill.

    D-315: ``tertiary_container``, ux.md §3.4's first choice, is the pink of En Español;
    an outline in ``warning`` reads as a status mark, as Registration required does.
    ``test_every_badge_reads_at_aa`` checks its label on every surface.
    """
    tokens = theme.build_tokens(dark=dark, high_contrast=False)
    assert tokens.changed == BadgeColors(text=tokens.warning)
    assert tokens.changed.fill is None  # outlined
    assert tokens.spanish.fill is not None  # tonal: the two never look alike
    assert color_distance(tokens.changed.text, tokens.spanish.text) >= 10


def test_tokens_are_frozen() -> None:
    """Tokens and their palette are read-only, and tokens hash and compare by value."""
    with pytest.raises(dataclasses.FrozenInstanceError):
        theme.LIGHT_TOKENS.live = "#000000"  # type: ignore[misc]
    with pytest.raises(TypeError):  # the palette too
        theme.LIGHT_TOKENS.tracks["Talk"] = BadgeColors("#000000")  # type: ignore[index]
    # Hashable by value although the palette is a mapping: tokens can be a dict key.
    palette = MappingProxyType(dict(theme.LIGHT_TOKENS.tracks))
    rebuilt = dataclasses.replace(theme.LIGHT_TOKENS, tracks=palette)
    assert rebuilt == theme.LIGHT_TOKENS
    assert hash(rebuilt) == hash(theme.LIGHT_TOKENS)


def test_tokens_context_defaults_to_the_light_tokens() -> None:
    """The tokens context defaults to the light tokens."""
    assert theme.TokensCtx.default_value is theme.LIGHT_TOKENS
