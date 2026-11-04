"""Tests for how long Now's Happening now and Up next are at peak times (#222; D-327).

The cut is pure (`now_fold.ordered()` and `cut()`); on the screen, at fixed times of
the 2026 feed: the fold after your saved sessions and three others, the count in the
button's words and its spoken label, the button's target (the rest in place, then
"Show fewer sessions"), and a fold that holds through a minute and closes on a new
slot. The screen runs in a real Flet session through `tests/now_view.py`'s harness.
How far down Up next sits on a phone is checked on devices (the PR).
"""

from collections.abc import Callable
from datetime import datetime
from typing import Any

import flet as ft
import pytest

from pycon_us.core.models import ConferenceData, Session
from pycon_us.screens.now_fold import SHOWN, cut, ordered
from tests.feeds import processed
from tests.now_view import AT_11, FIRST_AT_11, may, render  # noqa: F401  (fixture)

OPEN_SPACES_AT_11 = ("9113", "9040", "9072", "9059", "9086")
"""The open spaces of AT_11, in the slot's order."""


@pytest.fixture
def show(render: Callable[..., Any]) -> Callable[..., Any]:  # noqa: F811
    """`tests/now_view.py`'s `render`: Now at a time, in a real Flet session."""
    return render


@pytest.fixture(scope="module")
def at_11() -> tuple[Session, ...]:
    """AT_11's sessions from the 2026 feed, in the slot's order."""
    data: ConferenceData = processed(2026)
    return tuple(data.sessions[i] for i in AT_11)


def ids(sessions: list[Session]) -> list[str]:
    """The ids of `sessions`, in order."""
    return [session.id for session in sessions]


def test_saved_sessions_lead_and_open_spaces_follow_the_rest(
    at_11: tuple[Session, ...],
) -> None:
    """Saved first; in each group talks before open spaces, then the slot's order."""
    saved = frozenset({"9072", "102"})
    assert ids(ordered(at_11, saved)) == [
        "102",
        "9072",
        "105",
        "4",
        "15",
        "41",
        "9113",
        "9040",
        "9059",
        "9086",
    ]


def test_a_section_keeps_its_saved_sessions_and_three_others(
    at_11: tuple[Session, ...],
) -> None:
    """Folded, a section shows every saved session and the first three others."""
    saved = frozenset(OPEN_SPACES_AT_11[:4])
    rows, foldable = cut(at_11, saved, expanded=False)
    assert foldable
    assert ids(rows) == [*OPEN_SPACES_AT_11[:4], *FIRST_AT_11]
    rows, foldable = cut(at_11, saved, expanded=True)
    assert foldable and len(rows) == len(AT_11)


def test_a_section_never_folds_away_a_single_row(
    at_11: tuple[Session, ...],
) -> None:
    """A button in place of one row saves nothing: four others show whole."""
    rows, foldable = cut(at_11[: SHOWN + 1], frozenset(), expanded=False)
    assert not foldable and len(rows) == SHOWN + 1
    rows, foldable = cut(at_11[: SHOWN + 2], frozenset(), expanded=False)
    assert foldable and len(rows) == SHOWN


async def test_show_all_lists_the_rest_in_place_and_folds_back(
    show: Callable[..., Any],
) -> None:
    """The button counts the section, says which, shows the rest, then folds it."""
    shown = await show(may(15, 11, 10))
    button = shown.fold_button("happening")
    words = button.content
    assert isinstance(words, ft.Text)
    assert words.value == "Show all 10 sessions"
    assert words.semantics_label == "Show all 10 sessions happening now"
    expanded = shown.node("now.show_all.happening").content
    assert isinstance(expanded, ft.Semantics) and expanded.expanded is False
    assert shown.listed()[:3] == list(FIRST_AT_11)

    await shown.show_all()
    assert len(shown.listed()) == len(AT_11) + 1  # and Up next's one talk
    assert set(AT_11) <= set(shown.listed())
    assert shown.went == []  # in place: not the Schedule, whose filters hide some
    words = shown.fold_button("happening").content
    assert isinstance(words, ft.Text)
    assert words.value == "Show fewer sessions"
    assert words.semantics_label == "Show fewer sessions happening now"
    expanded = shown.node("now.show_all.happening").content
    assert isinstance(expanded, ft.Semantics) and expanded.expanded is True

    await shown.show_all()
    assert shown.listed() == [*FIRST_AT_11, "27"]


async def test_saved_sessions_on_are_never_folded_away(
    show: Callable[..., Any],
) -> None:
    """With four open spaces saved, the card has one and Happening now the rest."""
    saved = OPEN_SPACES_AT_11[:4]
    shown = await show(may(15, 11, 10), saved=saved)
    (mine,) = shown.listed("now.next.session.")
    listed = shown.listed()
    assert set(saved) - {mine} <= set(listed[:3])
    assert listed[3:6] == list(FIRST_AT_11)
    assert OPEN_SPACES_AT_11[-1] not in listed  # the unsaved open space is folded


async def test_up_next_folds_a_slot_of_open_spaces(
    show: Callable[..., Any],
) -> None:
    """At 1:50 PM on Friday, Up next's slot is folded with a button of its own."""
    shown = await show(may(15, 13, 50))
    words = shown.fold_button("up_next").content
    assert isinstance(words, ft.Text)
    assert str(words.value).startswith("Show all ")
    assert str(words.semantics_label).endswith(" sessions up next")
    before = len(shown.listed())
    await shown.show_all("up_next")
    assert len(shown.listed()) > before
    assert shown.went == []


async def test_a_minute_keeps_a_section_open_and_a_new_slot_folds_it(
    show: Callable[..., Any],
) -> None:
    """An opened section stays open as the minute ticks, and folds when it changes."""
    shown = await show(may(15, 11, 10))
    await shown.show_all()
    await shown.at(may(15, 11, 11))
    assert len(shown.listed()) == len(AT_11) + 1
    await shown.at(may(15, 14))  # another slot: 17 sessions on
    words = shown.fold_button("happening").content
    assert isinstance(words, ft.Text)
    assert str(words.value).startswith("Show all ")
    assert len(shown.listed()) < len(AT_11)


@pytest.mark.parametrize(
    ("now", "section", "star"),
    [(may(15, 11, 10), "happening", "105"), (may(15, 10, 50), "up_next", "4")],
)
async def test_a_star_that_changes_the_card_keeps_a_section_open(
    show: Callable[..., Any], now: datetime, section: str, star: str
) -> None:
    """Starring a row moves it into the card and unstarring it back: still open."""
    shown = await show(now)
    await shown.show_all(section)
    words = shown.fold_button(section).content
    assert isinstance(words, ft.Text) and words.value == "Show fewer sessions"

    await shown.favorites.toggle(shown.storage, star)
    await shown.settle()
    assert shown.listed("now.next.session.") == [star]
    words = shown.fold_button(section).content
    assert isinstance(words, ft.Text) and words.value == "Show fewer sessions"

    await shown.favorites.toggle(shown.storage, star)
    await shown.settle()
    assert shown.listed("now.next.session.") == []
    words = shown.fold_button(section).content
    assert isinstance(words, ft.Text) and words.value == "Show fewer sessions"


def test_the_test_s_open_spaces_are_open_spaces() -> None:
    """OPEN_SPACES_AT_11 names the feed's open spaces of AT_11, in its order."""
    data = processed(2026)
    kinds = {i: data.sessions[i].kind for i in AT_11}
    assert tuple(i for i in AT_11 if kinds[i] == "open-space") == OPEN_SPACES_AT_11
