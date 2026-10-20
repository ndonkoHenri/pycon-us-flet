"""Tests for the badges (THEME-08, SCHED-20; D-25): the pill, and which a session shows.

The colours' contrast is in ``tests/test_theme.py``; here, that a badge draws them and
always carries a name from ``track_name()`` (DATA-28). How badges look is checked on
devices (the PR). The sessions are the recorded 2026 feed's. The star's tests are in
``tests/test_favorite.py`` (D-267).
"""

from dataclasses import replace

import flet as ft
import pytest

from pycon_us import theme
from pycon_us.config import ConferenceInfo, load_year
from pycon_us.core.models import ConferenceData, Session
from pycon_us.ui.badges import (
    REGISTRATION,
    SPANISH,
    TrackBadge,
    badge_row,
    session_badges,
)
from tests.feeds import processed

TALK = "142"
AI = "105"
CHARLA = "76"
SPANISH_KEYNOTE = "165"
TUTORIAL = "19"
EDUCATION_SUMMIT = "199"
TYPING_SUMMIT = "201"  # the one summit open to all (DATA-09)
NOTICE = "196"
OPEN_SPACE = "9119"
SPONSOR_PRESENTATION = "111"


@pytest.fixture(scope="module")
def data() -> ConferenceData:
    """The recorded 2026 feed, processed once for the module."""
    return processed(2026)


@pytest.fixture(scope="module")
def info() -> ConferenceInfo:
    """The 2026 conference's year data."""
    return load_year(2026).conference


def label(badge: ft.Control) -> str:
    """The text a badge shows, checking it is a container around a Text."""
    assert isinstance(badge, ft.Container) and isinstance(badge.content, ft.Text)
    return str(badge.content.value)


def labels(session: Session, info: ConferenceInfo, dark: bool = False) -> list[str]:
    """The labels of the badges a session shows, in the light or dark scheme."""
    tokens = theme.build_tokens(dark=dark, high_contrast=False)
    return [label(badge) for badge in session_badges(session, info, tokens)]


def test_a_tonal_badge_is_its_label_on_its_fill() -> None:
    """A tonal badge is its label in its text colour on its fill, with a fill border."""
    colors = theme.BadgeColors(text="#014271", fill="#C7DBFE")
    badge = TrackBadge("Talk", colors)
    assert isinstance(badge, ft.Container) and isinstance(badge.content, ft.Text)
    assert badge.content.value == "Talk"
    assert badge.content.color == "#014271"
    assert badge.bgcolor == "#C7DBFE"
    # A border in the fill's colour: invisible, and as large as an outlined badge's.
    assert badge.border == ft.Border.all(1, "#C7DBFE")


def test_an_outlined_badge_has_no_fill_and_a_border_in_its_text_colour() -> None:
    """An outlined badge has no fill; its border and its label take its text colour."""
    badge = TrackBadge(REGISTRATION, theme.BadgeColors(text="#BA1A1A"))
    assert isinstance(badge, ft.Container) and isinstance(badge.content, ft.Text)
    assert badge.bgcolor is None
    assert badge.border == ft.Border.all(1, "#BA1A1A")
    assert badge.content.color == "#BA1A1A"


def test_a_badge_is_a_material_label_in_an_8_dp_pill() -> None:
    """A badge is a LABEL_SMALL label in an 8 dp pill that grows and wraps with it.

    ux.md §3.6 and §3.9: 8 dp corners, 8 dp beside and 2 dp above the label.
    """
    badge = TrackBadge("Talk", theme.LIGHT_TOKENS.track_badge("Talk"))
    assert isinstance(badge, ft.Container) and isinstance(badge.content, ft.Text)
    assert badge.content.theme_style == ft.TextThemeStyle.LABEL_SMALL
    assert badge.border_radius == 8
    assert badge.padding == ft.Padding.symmetric(horizontal=8, vertical=2)
    assert badge.height is None and badge.width is None  # grows with the text (D-26)
    assert badge.content.max_lines is None  # wraps at 200 %, never clipped


def test_badges_wrap_onto_more_lines_with_gaps_on_the_grid() -> None:
    """A badge row wraps, 8 dp apart within a line and 4 dp between lines."""
    row = badge_row([TrackBadge("Talk", theme.LIGHT_TOKENS.track_badge("Talk"))])
    assert row.wrap is True
    # ux.md §3.6: 8 dp within a group; 4 dp between wrapped lines.
    assert (row.spacing, row.run_spacing) == (8, 4)


def test_a_talk_shows_its_track(data: ConferenceData, info: ConferenceInfo) -> None:
    """A talk shows one badge: its track's name, Talk."""
    assert labels(data.sessions[TALK], info) == ["Talk"]


@pytest.mark.parametrize(
    ("session_id", "expected"),
    [
        (AI, "AI"),  # Ionic's room detail showed the key, "Ai" (SCHED-20)
        (OPEN_SPACE, "Open space"),
        (SPONSOR_PRESENTATION, "Sponsor presentation"),
        (NOTICE, "Notice"),
    ],
)
def test_track_names_come_from_track_name(
    data: ConferenceData, info: ConferenceInfo, session_id: str, expected: str
) -> None:
    """A track badge says the name ``track_name()`` gives, such as AI, not the key."""
    session = data.sessions[session_id]
    assert labels(session, info)[0] == expected == info.track_name(session.track)


@pytest.mark.parametrize("session_id", [CHARLA, SPANISH_KEYNOTE])
def test_a_session_in_spanish_adds_en_espanol(
    data: ConferenceData, info: ConferenceInfo, session_id: str
) -> None:
    """A session in Spanish shows its track's badge, then En Español."""
    session = data.sessions[session_id]
    assert labels(session, info) == [info.track_name(session.track), SPANISH]


@pytest.mark.parametrize("session_id", [TUTORIAL, EDUCATION_SUMMIT])
def test_a_session_needing_registration_adds_registration_required(
    data: ConferenceData, info: ConferenceInfo, session_id: str
) -> None:
    """A tutorial or a closed summit shows its track, then Registration required."""
    session = data.sessions[session_id]
    assert labels(session, info) == [info.track_name(session.track), REGISTRATION]


def test_the_typing_summit_needs_no_registration(
    data: ConferenceData, info: ConferenceInfo
) -> None:
    """The Typing summit, open to all, shows its track's badge alone (DATA-09)."""
    assert labels(data.sessions[TYPING_SUMMIT], info) == ["Summit"]


def test_badges_take_the_scheme_they_are_given(
    data: ConferenceData, info: ConferenceInfo
) -> None:
    """The track and Spanish badges take their fills from the tokens they are given."""
    session = data.sessions[CHARLA]
    for tokens in (theme.LIGHT_TOKENS, theme.DARK_TOKENS):
        track, spanish = session_badges(session, info, tokens)
        assert isinstance(track, ft.Container) and isinstance(spanish, ft.Container)
        assert track.bgcolor == tokens.track_badge("Charla").fill
        assert spanish.bgcolor == tokens.spanish.fill


def test_the_registration_badge_is_outlined(
    data: ConferenceData, info: ConferenceInfo
) -> None:
    """The registration badge has no fill and a border in its text colour."""
    *_, registration = session_badges(data.sessions[TUTORIAL], info, theme.DARK_TOKENS)
    assert isinstance(registration, ft.Container)
    assert registration.bgcolor is None
    assert registration.border == ft.Border.all(1, theme.DARK_TOKENS.registration.text)


def test_a_session_without_a_track_shows_no_empty_pill(
    data: ConferenceData, info: ConferenceInfo
) -> None:
    """A session without a track shows no track badge, not even an empty pill.

    A tutorial without one still shows Registration required.
    """
    assert labels(replace(data.sessions[TALK], track=""), info) == []
    assert labels(replace(data.sessions[TUTORIAL], track=""), info) == [REGISTRATION]
