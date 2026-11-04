"""Tests for what has ended on the My schedule tab, and removal and Undo (SCHED-08).

The screen runs in `tests/my_schedule_view.py`'s harness, with the minute tick moved
by hand.
"""

from collections.abc import Callable
from datetime import datetime
from typing import Any, cast

import flet as ft
import pytest

from pycon_us import clock
from pycon_us.screens import my_schedule_extras as extras
from pycon_us.ui import fold, states
from pycon_us.ui.buttons import LABEL_PADDING
from pycon_us.ui.favorite import REMOVED, UNDO
from tests import my_schedule_view
from tests.my_schedule_view import (
    AFTER,
    CHEESE_SHOP,
    DECORATORS,
    FAVORITES,
    INFERENCE,
    KEYNOTE,
    LAST_EVENING,
    MCP,
    NBSP,
    NOTEBOOKS,
    OPEN_SPACE,
    RAG,
    SAVED,
    TALK,
    WELCOME,
    ZONE,
    Setup,
    Shown,
    _walk,
)

setup, shown, before = (
    my_schedule_view.setup,
    my_schedule_view.shown,
    my_schedule_view.before,
)


# ------------------------------------------------------------------ what has ended


async def test_earlier_days_and_today_s_ended_sessions_fold_away(
    shown: Shown,
) -> None:
    """Thursday 10:45: Wednesday is over, and so is Thursday's 9:30 workshop."""
    earlier_days = shown.fold("earlier_days")
    title = cast(ft.Text, earlier_days.title)
    assert title.value == f"Earlier days (3{NBSP}sessions)"
    assert earlier_days.expanded is False  # folded until tapped
    assert earlier_days.said == "Collapsed"
    assert earlier_days.animation.duration == fold.EXPAND_MS
    assert shown.folded("earlier_days") == [MCP, DECORATORS, RAG]
    assert f"Earlier today (1{NBSP}session)" in shown.texts()
    assert shown.folded("earlier_today") == [CHEESE_SHOP]
    # Today's header comes first, then what is still on or to come.
    assert shown.headers()[:2] == ["Thursday, May 14", "Friday, May 15"]
    assert shown.shown() == [NOTEBOOKS, INFERENCE, WELCOME, KEYNOTE, TALK, OPEN_SPACE]


@pytest.fixture
def reduced(setup: Setup) -> None:
    """Turn reduced motion on before the screen renders."""
    setup.reduce_motion = True


@pytest.mark.usefixtures("reduced")
async def test_the_folds_open_without_animation_under_reduced_motion(
    shown: Shown,
) -> None:
    """D-173: the tiles' animation is `prefs.motion_ms()` long, 0 here."""
    for identifier in ("earlier_days", "earlier_today"):
        assert shown.fold(identifier).animation.duration == 0


async def test_a_fold_stays_open_across_renders(shown: Shown) -> None:
    """Controlled: the next render passes the state back instead of the default."""
    await shown.toggle_fold("earlier_days", True)
    assert shown.fold("earlier_days").expanded is True
    shown.tick()  # a minute later: a re-render
    await shown.settle()
    assert shown.fold("earlier_days").expanded is True
    assert shown.fold("earlier_today").expanded is False
    await shown.toggle_fold("earlier_days", False)
    assert shown.fold("earlier_days").expanded is False


async def test_the_next_day_s_earlier_today_starts_collapsed(shown: Shown) -> None:
    """The open state belongs to the day: Friday's tile is not Thursday's."""
    await shown.toggle_fold("earlier_today", True)
    assert shown.fold("earlier_today").expanded is True
    clock.set_test_now(datetime(2026, 5, 15, 10, 0, tzinfo=ZONE))  # the welcome is over
    shown.tick()
    await shown.settle()
    assert shown.folded("earlier_today") == [WELCOME]
    assert shown.fold("earlier_today").expanded is False


async def test_the_minute_tick_folds_a_session_once_it_has_ended(
    shown: Shown,
) -> None:
    """The tick at 12:30 folds the sessions that end then into Earlier today."""
    clock.set_test_now(datetime(2026, 5, 14, 12, 30, tzinfo=ZONE))  # both end now
    shown.tick()
    await shown.settle()
    assert shown.folded("earlier_today") == [NOTEBOOKS, CHEESE_SHOP, INFERENCE]
    assert f"Earlier today (3{NBSP}sessions)" in shown.texts()
    assert shown.shown() == [WELCOME, KEYNOTE, TALK, OPEN_SPACE]


@pytest.fixture
def last_evening(setup: Setup) -> None:
    """Set the time to Sunday evening, when every saved session has ended."""
    setup.now = LAST_EVENING


@pytest.mark.usefixtures("last_evening")
async def test_when_everything_has_ended_it_says_so_and_offers_today(
    shown: Shown,
) -> None:
    """With every session ended, a heading says so and a button opens Now."""
    shown.node("my_schedule.all_over")
    assert "All your saved sessions are over" in shown.texts()
    # A level, or it is no heading for TalkBack or VoiceOver (F40); the heading
    # first, as on screen (#592).
    node = cast(ft.Semantics, shown.node("my_schedule.all_over"))
    assert (node.header, node.heading_level) == (True, 2)
    assert node.label == extras.ALL_OVER
    assert node.exclude_semantics
    assert shown.shown() == []
    (button,) = [c for c in shown.controls if isinstance(c, ft.FilledTonalButton)]
    assert button.content == "See what's on today"
    assert button.style is not None  # its sides stay 24 dp at large text (D-344)
    assert button.style.padding == LABEL_PADDING
    assert button.elevation == 0  # flat, as M3's tonal button
    await shown.session.dispatch_event(button._i, "click", None)
    await shown.settle()
    assert shown.went == ["/now"]


@pytest.fixture
def after(setup: Setup) -> None:
    """Set the time after the conference."""
    setup.now = AFTER


@pytest.mark.usefixtures("after")
async def test_after_the_conference_it_offers_no_today(shown: Shown) -> None:
    """Nothing is on today any more, so no button promises it."""
    shown.node("my_schedule.all_over")
    assert "PyCon US 2026 is over. Your saved sessions stay here." in shown.texts()
    node = cast(ft.Semantics, shown.node("my_schedule.all_over"))
    assert node.label == (  # the heading, then the body (#592)
        f"{extras.ALL_OVER}\nPyCon US 2026 is over. Your saved sessions stay here."
    )
    assert shown.folded("earlier_days") == list(SAVED)
    assert shown.shown() == []
    assert not any(isinstance(c, ft.FilledTonalButton) for c in shown.controls)


@pytest.mark.usefixtures("after")
async def test_the_all_over_notice_sits_above_the_earlier_days_tile(
    shown: Shown,
) -> None:
    """Compact, not the full-screen empty state: the tile is still content."""
    root = shown.root().controls  # the strip, the quiet dropped notice (D-329), ...
    notice, tile = root[2], root[3]
    assert tile is shown.fold("earlier_days").root
    assert not any(
        isinstance(c, ft.Icon) and c.size == states.ICON_SIZE for c in _walk(notice)
    )


# ------------------------------------------------------------------ removal and Undo


@pytest.mark.usefixtures("before")
async def test_unstarring_removes_the_row_at_once_and_undo_brings_it_back(
    shown: Shown,
) -> None:
    """ux.md §4.4, §5.6: the row goes with the tap; Undo restores it."""
    await shown.tap_star(TALK)
    assert TALK not in shown.shown()
    assert TALK not in shown.favorites.ids
    assert shown.prefs_service.values[FAVORITES] == sorted(set(SAVED) - {TALK})
    (snack,) = shown.snack_bars
    assert cast(ft.Text, snack.content).value == REMOVED
    action = cast(ft.SnackBarAction, snack.action)
    assert action.label == UNDO

    await cast(Callable[[], Any], action.on_click)()
    await shown.settle()
    assert shown.shown()[-2:] == [TALK, OPEN_SPACE]
    assert shown.prefs_service.values[FAVORITES] == sorted(SAVED)


@pytest.mark.usefixtures("before")
async def test_removing_one_side_of_a_clash_clears_the_other_s_line(
    shown: Shown,
) -> None:
    """Unstarring one side of a clash drops the overlap from the other's phrase."""
    await shown.tap_star(DECORATORS)
    assert "Overlaps" not in shown.phrase(MCP)


@pytest.mark.usefixtures("before")
async def test_a_removal_re_renders_no_other_row(shown: Shown) -> None:
    """D-153: the views stay the same objects, so every other row skips its body."""
    shown.rows.clear()
    await shown.tap_star(TALK)
    assert shown.rows == []
    (snack,) = shown.snack_bars
    await cast(Callable[[], Any], cast(ft.SnackBarAction, snack.action).on_click)()
    await shown.settle()
    assert shown.rows == [TALK]  # only the row that came back


@pytest.mark.usefixtures("before")
async def test_a_removal_re_renders_only_its_own_day(shown: Shown) -> None:
    """D-153: the other days' sections get equal props and skip their bodies."""
    shown.slots.clear()
    await shown.tap_star(DECORATORS)
    assert shown.slots == ["9:00 AM", "1:30 PM"]  # Wednesday's two slots


@pytest.mark.usefixtures("before")
async def test_a_clash_removed_re_renders_only_the_row_whose_line_changed(
    shown: Shown,
) -> None:
    """Unstarring one side of a clash re-renders only the other side's row."""
    shown.rows.clear()
    await shown.tap_star(DECORATORS)
    assert shown.rows == [MCP]
