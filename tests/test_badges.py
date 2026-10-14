"""Tests for the badges (THEME-08, SCHED-20; D-25): the pill, and which a session shows.

Also the selection click the star and search's chips share (ux.md §4.5, D-193), and
the star's last SnackBar, which an edit that says nothing closes (D-251, #334): those
tests star rows in a real Flet session (``tests/row_sessions.py``).

The colours' contrast is in ``tests/test_theme.py``; here, that a badge draws them and
always carries a name from ``track_name()`` (DATA-28). How badges look is checked on
devices (the PR). The sessions are the recorded 2026 feed's.
"""

import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import flet as ft
import pytest

from pycon_us import theme
from pycon_us.config import ConferenceInfo, load_year
from pycon_us.core.models import ConferenceData, Session
from pycon_us.ui.badges import (
    REGISTRATION,
    REMOVED,
    SPANISH,
    TrackBadge,
    badge_row,
    selection_click,
    session_badges,
)
from tests import row_sessions
from tests.fakes import MemoryHaptics
from tests.feeds import processed
from tests.row_sessions import Rendered, rendering
from tests.sessions import text_of

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
    return processed(2026)


@pytest.fixture(scope="module")
def info() -> ConferenceInfo:
    return load_year(2026).conference


def label(badge: ft.Control) -> str:
    assert isinstance(badge, ft.Container) and isinstance(badge.content, ft.Text)
    return str(badge.content.value)


def labels(session: Session, info: ConferenceInfo, dark: bool = False) -> list[str]:
    tokens = theme.build_tokens(dark=dark, high_contrast=False)
    return [label(badge) for badge in session_badges(session, info, tokens)]


def test_a_tonal_badge_is_its_label_on_its_fill() -> None:
    colors = theme.BadgeColors(text="#014271", fill="#C7DBFE")
    badge = TrackBadge("Talk", colors)
    assert isinstance(badge, ft.Container) and isinstance(badge.content, ft.Text)
    assert badge.content.value == "Talk"
    assert badge.content.color == "#014271"
    assert badge.bgcolor == "#C7DBFE"
    # A border in the fill's colour: invisible, and as large as an outlined badge's.
    assert badge.border == ft.Border.all(1, "#C7DBFE")


def test_an_outlined_badge_has_no_fill_and_a_border_in_its_text_colour() -> None:
    badge = TrackBadge(REGISTRATION, theme.BadgeColors(text="#BA1A1A"))
    assert isinstance(badge, ft.Container) and isinstance(badge.content, ft.Text)
    assert badge.bgcolor is None
    assert badge.border == ft.Border.all(1, "#BA1A1A")
    assert badge.content.color == "#BA1A1A"


def test_a_badge_is_a_material_label_in_an_8_dp_pill() -> None:
    # ux.md §3.6 and §3.9: LABEL_SMALL, 8 dp corners, 8 dp beside and 2 dp above the label.
    badge = TrackBadge("Talk", theme.LIGHT_TOKENS.track_badge("Talk"))
    assert isinstance(badge, ft.Container) and isinstance(badge.content, ft.Text)
    assert badge.content.theme_style == ft.TextThemeStyle.LABEL_SMALL
    assert badge.border_radius == 8
    assert badge.padding == ft.Padding.symmetric(horizontal=8, vertical=2)
    assert badge.height is None and badge.width is None  # grows with the text (D-26)
    assert badge.content.max_lines is None  # wraps at 200 %, never clipped


def test_badges_wrap_onto_more_lines_with_gaps_on_the_grid() -> None:
    row = badge_row([TrackBadge("Talk", theme.LIGHT_TOKENS.track_badge("Talk"))])
    assert row.wrap is True
    # ux.md §3.6: 8 dp within a group; 4 dp between wrapped lines.
    assert (row.spacing, row.run_spacing) == (8, 4)


def test_a_talk_shows_its_track(data: ConferenceData, info: ConferenceInfo) -> None:
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
    session = data.sessions[session_id]
    assert labels(session, info)[0] == expected == info.track_name(session.track)


@pytest.mark.parametrize("session_id", [CHARLA, SPANISH_KEYNOTE])
def test_a_session_in_spanish_adds_en_espanol(
    data: ConferenceData, info: ConferenceInfo, session_id: str
) -> None:
    session = data.sessions[session_id]
    assert labels(session, info) == [info.track_name(session.track), SPANISH]


@pytest.mark.parametrize("session_id", [TUTORIAL, EDUCATION_SUMMIT])
def test_a_session_needing_registration_adds_registration_required(
    data: ConferenceData, info: ConferenceInfo, session_id: str
) -> None:
    session = data.sessions[session_id]
    assert labels(session, info) == [info.track_name(session.track), REGISTRATION]


def test_the_typing_summit_needs_no_registration(
    data: ConferenceData, info: ConferenceInfo
) -> None:
    assert labels(data.sessions[TYPING_SUMMIT], info) == ["Summit"]


def test_badges_take_the_scheme_they_are_given(
    data: ConferenceData, info: ConferenceInfo
) -> None:
    session = data.sessions[CHARLA]
    for tokens in (theme.LIGHT_TOKENS, theme.DARK_TOKENS):
        track, spanish = session_badges(session, info, tokens)
        assert isinstance(track, ft.Container) and isinstance(spanish, ft.Container)
        assert track.bgcolor == tokens.track_badge("Charla").fill
        assert spanish.bgcolor == tokens.spanish.fill


def test_the_registration_badge_is_outlined(
    data: ConferenceData, info: ConferenceInfo
) -> None:
    *_, registration = session_badges(data.sessions[TUTORIAL], info, theme.DARK_TOKENS)
    assert isinstance(registration, ft.Container)
    assert registration.bgcolor is None
    assert registration.border == ft.Border.all(1, theme.DARK_TOKENS.registration.text)


def test_a_session_without_a_track_shows_no_empty_pill(
    data: ConferenceData, info: ConferenceInfo
) -> None:
    assert labels(replace(data.sessions[TALK], track=""), info) == []
    assert labels(replace(data.sessions[TUTORIAL], track=""), info) == [REGISTRATION]


async def test_selection_click_gives_the_click() -> None:
    haptics = MemoryHaptics()
    await selection_click(haptics)
    assert haptics.effects == ["selection_click"]


@pytest.mark.parametrize("error", [TimeoutError(), RuntimeError("no engine")])
async def test_a_failed_click_is_logged_not_raised(
    error: Exception, caplog: pytest.LogCaptureFixture
) -> None:
    haptics = MemoryHaptics()
    haptics.error = error
    with caplog.at_level(logging.WARNING, logger="pycon_us.ui.badges"):
        await selection_click(haptics)  # a missed click is no error message
    assert "Haptic feedback failed" in caplog.text


# ------------------------------------------------------------------ the last SnackBar


@pytest.fixture
async def rendered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Rendered]:
    """A list of starred rows in a real Flet session, a screen reader on (D-184)."""
    async with rendering(tmp_path, monkeypatch) as shown:
        shown.prefs.screen_reader = True  # the Undo SnackBar stays until used
        yield shown


def updates(monkeypatch: pytest.MonkeyPatch) -> list[ft.SnackBar]:
    """Record each SnackBar sent to the client again: a closed one must be sent."""
    sent: list[ft.SnackBar] = []

    def update(snack: ft.SnackBar) -> None:
        sent.append(snack)

    monkeypatch.setattr(ft.SnackBar, "update", update)
    return sent


async def removed(rendered: Rendered, session_id: str) -> ft.SnackBar:
    """Save the session, then remove it: return the "Removed" SnackBar, showing."""
    await rendered.tap_star(session_id)
    await rendered.tap_star(session_id)
    snack = rendered.snack_bars[-1]
    assert text_of(snack.content) == REMOVED
    assert snack.open and snack.persist
    return snack


async def test_saving_a_session_again_closes_its_removed_snack_bar(
    rendered: Rendered, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#334: a screen reader must not go on saying "Removed" about a saved session."""
    snack = await removed(rendered, row_sessions.TALK)
    sent = updates(monkeypatch)
    await rendered.tap_star(row_sessions.TALK)
    assert rendered.favorites.ids == {row_sessions.TALK}
    # Flet removes the SnackBar whose open goes false (snack_bar.dart).
    assert not snack.open and sent == [snack]
    assert rendered.snack_bars == [snack]  # and the add shows none of its own


async def test_undo_closes_the_removed_snack_bar(rendered: Rendered) -> None:
    snack = await removed(rendered, row_sessions.TALK)
    await cast(Callable[[], Any], cast(ft.SnackBarAction, snack.action).on_click)()
    await rendered.settle()
    assert rendered.favorites.ids == {row_sessions.TALK}
    assert not snack.open
    assert rendered.snack_bars == [snack]


async def test_saving_another_session_closes_it_too(rendered: Rendered) -> None:
    """Any edit that says nothing: the bar would not say which session it removed."""
    snack = await removed(rendered, row_sessions.TALK)
    await rendered.tap_star(row_sessions.TUTORIAL)
    assert not snack.open


async def test_a_removal_snack_bar_stays_until_the_next_edit(
    rendered: Rendered,
) -> None:
    """D-184 is unchanged: nothing closes it but an edit, Undo or Flet itself."""
    snack = await removed(rendered, row_sessions.TALK)
    await rendered.settle()
    assert snack.open
    # A second removal shows its own; Flet's show replaces the first on the device.
    second = await removed(rendered, row_sessions.TUTORIAL)
    assert second is not snack and second.open


async def test_an_edit_leaves_a_snack_bar_that_is_not_the_stars_alone(
    rendered: Rendered,
) -> None:
    """Never the top dialog (ux.md §4.5): only the star's own SnackBar closes."""
    snack = await removed(rendered, row_sessions.TALK)
    other = ft.SnackBar(ft.Text("Something went wrong"))
    rendered.session.page.show_dialog(other)
    await rendered.tap_star(row_sessions.TALK)
    assert not snack.open and other.open
    await rendered.tap_star(row_sessions.TUTORIAL)  # with no star SnackBar left
    assert other.open


async def test_a_snack_bar_that_has_gone_is_not_closed_again(
    rendered: Rendered, monkeypatch: pytest.MonkeyPatch
) -> None:
    snack = await removed(rendered, row_sessions.TALK)
    snack.open = False  # as Flet reports a SnackBar that timed out or was swiped
    sent = updates(monkeypatch)
    await rendered.tap_star(row_sessions.TALK)
    assert rendered.favorites.ids == {row_sessions.TALK}
    assert sent == []
