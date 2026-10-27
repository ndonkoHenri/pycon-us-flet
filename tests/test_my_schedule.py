"""Tests for My schedule's agenda and overlaps (#94; NEW-01, SCHED-07; ux.md §5.6).

The screen runs in ``tests/my_schedule_view.py``'s harness. What has ended, removal and
Undo are ``test_my_schedule_ended.py``'s, the states and the dropped sessions' notice
``test_my_schedule_states.py``'s. The fold itself is a pure function, tested in
``test_agenda_fold.py``.
"""

from typing import cast

import flet as ft
import pytest

from pycon_us.core.row_views import spoken_phrase
from pycon_us.ui import session_rows as rows
from tests import my_schedule_view
from tests.feeds import processed
from tests.my_schedule_view import (
    CHEESE_SHOP,
    DECORATORS,
    INFERENCE,
    KEYNOTE,
    MCP,
    NBSP,
    NOTEBOOKS,
    OPEN_SPACE,
    RAG,
    TALK,
    WELCOME,
    ZONE,
    Shown,
    _walk,
    name,
)

setup, shown, before = (
    my_schedule_view.setup,
    my_schedule_view.shown,
    my_schedule_view.before,
)


# ------------------------------------------------------------------ the agenda


@pytest.mark.usefixtures("before")
async def test_saved_sessions_show_by_day_and_slot_in_schedule_order(
    shown: Shown,
) -> None:
    """Every saved session shows under its day header, in the Schedule's order."""
    assert shown.headers() == [
        "Wednesday, May 13",
        "Thursday, May 14",
        "Friday, May 15",
        "Saturday, May 16",
        "Sunday, May 17",
    ]
    assert shown.shown() == [
        MCP,  # 9:00, Room 101A
        DECORATORS,  # 9:00, Room 101B
        RAG,
        NOTEBOOKS,  # 9:00
        CHEESE_SHOP,  # 9:30
        INFERENCE,  # 11:30
        WELCOME,
        KEYNOTE,
        TALK,
        OPEN_SPACE,  # hidden on the Schedule by default, shown here (D-20)
    ]


@pytest.mark.usefixtures("before")
async def test_each_start_is_one_slot_with_its_gutter(shown: Shown) -> None:
    """Saved sessions with one start share one slot and its time gutter."""
    gutters = [
        str(c.label)
        for c in _walk(shown.root())
        if isinstance(c, ft.Semantics) and c.header and c.label
    ]
    # Wednesday's two 9:00 tutorials share one gutter.
    assert gutters[:3] == ["9:00 AM", "1:30 PM", "9:00 AM"]


@pytest.mark.usefixtures("before")
async def test_every_saved_row_has_a_filled_star(shown: Shown) -> None:
    """A saved row's star is toggled on."""
    star = shown.node(f"my_schedule.favorite.{TALK}")
    assert star.toggled is True


async def test_the_strip_shows_the_data_s_state_but_never_refreshes_by_itself(
    shown: Shown,
) -> None:
    """D-40: only Now and Schedule refresh every 15 min while they show."""
    assert shown.strips and all(kwargs == {} for kwargs in shown.strips)
    assert shown.root().controls[0] == ft.Text("strip")


# ------------------------------------------------------------------ overlaps


@pytest.mark.usefixtures("before")
async def test_both_rows_of_a_clash_say_so_in_words_and_with_an_icon(
    shown: Shown,
) -> None:
    """P1 exit criterion 1; D-33: an icon and text, never colour alone."""
    assert shown.phrase(MCP).endswith(f"Overlaps with “{name(DECORATORS)}”.")
    assert shown.phrase(DECORATORS).endswith(f"Overlaps with “{name(MCP)}”.")
    line = f"Overlaps with “{name(DECORATORS)}”"
    (text,) = [c for c in shown.controls if isinstance(c, ft.Text) and c.value == line]
    row = cast(ft.Control, text.parent).parent
    assert isinstance(row, ft.Row)
    icon = cast(ft.Container, row.controls[0]).content
    assert isinstance(icon, ft.Icon) and icon.icon == ft.Icons.WARNING_AMBER


@pytest.mark.usefixtures("before")
async def test_a_session_inside_a_long_one_names_its_clash(shown: Shown) -> None:
    """A tutorial names both workshops inside it, and a workshop the tutorial."""
    assert shown.phrase(NOTEBOOKS).endswith(
        f"Overlaps with “{name(CHEESE_SHOP)}” and “{name(INFERENCE)}”."
    )
    assert shown.phrase(CHEESE_SHOP).endswith(f"Overlaps with “{name(NOTEBOOKS)}”.")


@pytest.mark.usefixtures("before")
async def test_a_row_without_a_clash_says_nothing_of_one(shown: Shown) -> None:
    """Rows without a clash say nothing of one: only five rows have the line."""
    for session_id in (RAG, WELCOME, KEYNOTE, TALK):
        assert "Overlaps" not in shown.phrase(session_id)
    lines = [text for text in shown.texts() if text.startswith("Overlaps")]
    assert len(lines) == 5  # Wednesday's pair and Thursday's three, nothing more


@pytest.mark.usefixtures("before")
async def test_more_clashes_are_counted_on_a_line_the_cut_never_hides(
    shown: Shown,
) -> None:
    """D-188's "Now:" line: the name may be cut at three lines, the count never is."""
    line = f"Overlaps with “{name(CHEESE_SHOP)}”"
    (text,) = [c for c in shown.controls if isinstance(c, ft.Text) and c.value == line]
    assert text.max_lines == 3
    lines = cast(ft.Column, text.parent).controls
    assert [cast(ft.Text, c).value for c in lines] == [line, f"and 1{NBSP}more"]
    assert cast(ft.Text, lines[1]).max_lines is None
    # The phrase names every clash in full.
    assert shown.phrase(NOTEBOOKS).endswith(
        f"Overlaps with “{name(CHEESE_SHOP)}” and “{name(INFERENCE)}”."
    )


def test_the_phrase_names_three_clashes_in_a_list() -> None:
    """The spoken phrase lists three clashes as “A”, “B” and “C”."""
    view = rows.session_views(processed(2026), (TALK,), ZONE, use_24h=False)[0]
    assert spoken_phrase([], view, overlaps=("A", "B", "C")).endswith(
        "Overlaps with “A”, “B” and “C”."
    )


async def test_a_clash_that_has_ended_is_not_shown(shown: Shown) -> None:
    """An ended clash is not named, and folded rows carry no clash line.

    Thursday 10:45: the 9:30 workshop is over, so the tutorial names only 11:30's.
    Neither an ended clash nor a folded row can change a plan any more.
    """
    assert shown.phrase(NOTEBOOKS).endswith(f"Overlaps with “{name(INFERENCE)}”.")
    assert f"and 1{NBSP}more" not in shown.texts()
    for folded in (MCP, DECORATORS, CHEESE_SHOP):
        assert "Overlaps" not in shown.phrase(folded)
