"""Tests for the session rows: ``SessionRow`` and ``NoticeRow`` (D-184).

Rows run in a real Flet session (``Rendered``, from ``tests/row_sessions.py``): a list
owner like the screens' renders memoised rows under the store providers, a star tap is
a dispatched click, and Flet's own scheduler re-renders what changed, so a test sees
what a device would get. How tall a row is, how it wraps at 200 % and what TalkBack
reads are checked on devices (#81's PR); here, the semantics a screen reader is given.
What a row and a notice are made of is tested in ``test_session_rows_layout.py``.

The session is ``tests/harness.py``'s ``showing()``, which reaches into Flet internals
as Flet's own component tests do (SnackBars from ``page._dialogs``, clicks through
``Session.dispatch_event(control._i, ...)``). A Flet pin bump (D-81) that renames one
of them breaks that module, not the rows: look there first.
"""

import asyncio
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import flet as ft
import pytest

from pycon_us import clock
from pycon_us.change_log import RECENT_FOR
from pycon_us.core.change_batches import Batch
from pycon_us.core.diff import Change, ChangeKind
from pycon_us.theme import LIGHT_TOKENS
from pycon_us.ui import session_rows as rows
from pycon_us.ui.badges import CHANGED
from pycon_us.ui.favorite import (
    ADD_LABEL,
    FAVORITE_LABEL,
    NOT_SAVED,
    REMOVE_LABEL,
    REMOVED,
    UNDO,
)
from tests import row_sessions
from tests.row_sessions import (
    CHARLA,
    LIST,
    NOTICE,
    OWNER_RENDERS,
    TALK,
    TUTORIAL,
    Rendered,
    rendering,
)

# The harness's fixture, under this module's name, where pytest looks it up.
rendered = row_sessions.rendered


# ------------------------------------------------------------------ the memoised path


async def test_each_row_renders_once_when_the_list_first_shows(
    rendered: Rendered,
) -> None:
    """The list's first show renders each of its rows exactly once."""
    assert sorted(rendered.renders) == sorted(LIST)


async def test_a_star_tap_re_renders_exactly_one_row(rendered: Rendered) -> None:
    """D-153: the owner re-renders, but every other row skips its body (F34)."""
    rendered.renders.clear()
    await rendered.tap_star(CHARLA)
    assert rendered.favorites.ids == {CHARLA}
    assert rendered.renders == [CHARLA]
    assert rendered.filled(CHARLA)
    assert not rendered.filled(TALK)

    rendered.renders.clear()
    await rendered.tap_star(CHARLA)  # and back
    assert rendered.renders == [CHARLA]
    assert rendered.favorites.ids == frozenset()


async def test_the_handler_is_the_same_object_on_every_render(
    rendered: Rendered,
) -> None:
    """Every row gets the same star handler object across renders and taps.

    With ``use_callback(..., [])`` the handler never changes, so memoised rows stay
    skipped.
    """
    handlers: set[int] = set()
    original = rows._SessionRow

    def spy(*args: Any, **kwargs: Any) -> ft.Control:
        handlers.add(id(args[2]))
        return original(*args, **kwargs)

    rows._SessionRow = spy  # pyright: ignore[reportAttributeAccessIssue]
    try:
        await rendered.tap_star(TALK)
        await rendered.tap_star(TUTORIAL)
    finally:
        rows._SessionRow = original  # pyright: ignore[reportAttributeAccessIssue]
    assert len(handlers) == 1  # use_callback(..., []): memoised rows stay skipped


# ------------------------------------------------------------------ Changed (D-315)

DETECTED = datetime(2026, 5, 15, 17, 0, tzinfo=UTC)
"""When the tests' batch was recorded."""


@pytest.fixture
def frozen_clock() -> Iterator[None]:
    """Freeze ``clock.now()`` an hour after ``DETECTED``; real time again after."""
    clock.set_test_now(DETECTED + timedelta(hours=1))
    yield
    clock.set_test_now(None)


def badge_labels(rendered: Rendered, session_id: str) -> list[str]:
    """The labels of the badges a session row shows, in order."""
    column = rendered.node(f"test.session.{session_id}").content
    badges = cast(ft.Column, column).controls[0]
    assert isinstance(badges, ft.Row)
    return [
        cast(ft.Text, cast(ft.Container, b).content).value or ""
        for b in badges.controls
    ]


async def record(rendered: Rendered, *changes: tuple[str, ChangeKind]) -> None:
    """Record one batch of ``(session id, kind)`` changes, as a refresh would."""
    batch = Batch(
        DETECTED, tuple(Change(key, kind, None, None) for key, kind in changes)
    )
    rendered.change_log.batches = (batch,)  # the store notifies its subscribers
    await rendered.settle()


async def test_a_changed_row_shows_the_badge_and_says_what_changed(
    rendered: Rendered, frozen_clock: None
) -> None:
    """A moved and retimed talk shows Changed and says "Time and room changed"."""
    rendered.renders.clear()
    await record(rendered, (TALK, ChangeKind.ROOM), (TALK, ChangeKind.TIME))
    assert badge_labels(rendered, TALK) == ["Talk", CHANGED]
    phrase = rendered.node(f"test.session.{TALK}").label or ""
    assert phrase.startswith("Talk, Time and room changed. Python for Humans")
    assert rendered.renders == [TALK]  # the other rows skip their bodies (D-153)


async def test_additions_and_removals_badge_no_row(
    rendered: Rendered, frozen_clock: None
) -> None:
    """D-255: only a time, room or title change is badged."""
    await record(rendered, (TALK, ChangeKind.ADDED), (CHARLA, ChangeKind.REMOVED))
    assert badge_labels(rendered, TALK) == ["Talk"]
    assert badge_labels(rendered, CHARLA) == ["Charla", "En Español"]


async def test_the_badge_goes_a_minute_past_its_24_hours(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, frozen_clock: None
) -> None:
    """The tick removes the badge once its batch is 24 h old, re-rendering one row.

    The tick is the strip's 60 s loop, made 10 ms here before the list mounts.
    """
    monkeypatch.setattr(rows, "TICK_SECONDS", 0.01)
    async with rendering(tmp_path, monkeypatch) as rendered:
        await record(rendered, (TALK, ChangeKind.TITLE))
        assert CHANGED in badge_labels(rendered, TALK)
        clock.set_test_now(DETECTED + RECENT_FOR - timedelta(seconds=1))
        await asyncio.sleep(0.05)  # ticks a second before the end: still shown
        assert CHANGED in badge_labels(rendered, TALK)
        rendered.renders.clear()

        clock.set_test_now(DETECTED + RECENT_FOR + timedelta(minutes=1))
        for _ in range(300):
            await asyncio.sleep(0.01)
            if CHANGED not in badge_labels(rendered, TALK):
                break
        assert badge_labels(rendered, TALK) == ["Talk"]
        assert rendered.renders == [TALK]


async def test_a_tick_after_a_batch_that_ends_no_mark_renders_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, frozen_clock: None
) -> None:
    """D-315: a tick compares with the marks the batch's render showed, not older ones.

    So after a recorded batch, ticks whose time ends no mark leave the owner alone
    (D-194's leaf rule).
    """
    monkeypatch.setattr(rows, "TICK_SECONDS", 0.01)
    async with rendering(tmp_path, monkeypatch) as rendered:
        await record(rendered, (TALK, ChangeKind.ROOM))
        OWNER_RENDERS.clear()
        await asyncio.sleep(0.1)  # about ten ticks, the clock frozen
        assert OWNER_RENDERS == []


def notice_badges(rendered: Rendered, session_id: str) -> list[str]:
    """The labels of the badges a notice row shows over its title, in order."""
    row = cast(ft.Row, rendered.notice(session_id).content)
    column = cast(ft.Column, row.controls[1])
    first = column.controls[0]
    if not isinstance(first, ft.Row):
        return []
    return [
        cast(ft.Text, cast(ft.Container, b).content).value or "" for b in first.controls
    ]


async def test_a_changed_notice_shows_the_badge_until_its_24_hours_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, frozen_clock: None
) -> None:
    """A moved informational session is badged and says "Room changed", then not.

    Registration Desk Opens is diffed like any session (D-255): its notice row shows
    Changed a second before the 24 h end, and neither badge nor words a minute after.
    """
    monkeypatch.setattr(rows, "TICK_SECONDS", 0.01)
    async with rendering(tmp_path, monkeypatch) as rendered:
        rendered.renders.clear()
        await record(rendered, (NOTICE, ChangeKind.ROOM))
        assert rendered.renders == [NOTICE]
        assert notice_badges(rendered, NOTICE) == [CHANGED]
        phrase = rendered.notice(NOTICE).label or ""
        assert phrase.startswith("Notice, Room changed. Registration Desk Opens")

        clock.set_test_now(DETECTED + RECENT_FOR - timedelta(seconds=1))
        await asyncio.sleep(0.05)
        assert notice_badges(rendered, NOTICE) == [CHANGED]

        clock.set_test_now(DETECTED + RECENT_FOR + timedelta(minutes=1))
        for _ in range(300):
            await asyncio.sleep(0.01)
            if not notice_badges(rendered, NOTICE):
                break
        assert notice_badges(rendered, NOTICE) == []
        phrase = rendered.notice(NOTICE).label or ""
        assert phrase.startswith("Notice. Registration Desk Opens")


# ------------------------------------------------------------------ the star (D-30)


async def test_adding_fills_the_star_with_a_click_and_no_snack_bar(
    rendered: Rendered,
) -> None:
    """Adding a session saves it, gives a selection click and shows no SnackBar."""
    await rendered.tap_star(TALK)
    assert rendered.prefs_service.values["pycon.2026.favorites"] == [TALK]
    assert rendered.haptics.effects == ["selection_click"]
    assert rendered.snack_bars == []


async def test_removing_says_so_and_undo_saves_the_session_again(
    rendered: Rendered,
) -> None:
    """Removing shows a floating SnackBar whose Undo saves the session again.

    Without a screen reader it goes after 4 s, and Undo shows no SnackBar of its own.
    """
    await rendered.tap_star(TALK)
    await rendered.tap_star(TALK)
    (snack,) = rendered.snack_bars
    assert cast(ft.Text, snack.content).value == REMOVED
    assert snack.behavior == ft.SnackBarBehavior.FLOATING
    assert snack.persist is False  # no screen reader: it goes after 4 s
    action = cast(ft.SnackBarAction, snack.action)
    assert action.label == UNDO

    await cast(Callable[[], Any], action.on_click)()
    await rendered.settle()
    assert rendered.favorites.ids == {TALK}
    assert rendered.prefs_service.values["pycon.2026.favorites"] == [TALK]
    assert rendered.filled(TALK)
    assert len(rendered.snack_bars) == 1  # Undo itself says nothing more


async def test_with_a_screen_reader_the_undo_snack_bar_waits_to_be_used(
    rendered: Rendered,
) -> None:
    """D-184: a screen-reader user cannot reach Undo within 4 s."""
    rendered.prefs.screen_reader = True
    await rendered.tap_star(TALK)
    await rendered.tap_star(TALK)
    added, snack = rendered.snack_bars  # the add says "Added" to it first (D-355)
    assert snack.persist is True and not added.persist


async def test_an_add_that_was_not_saved_says_so_without_undo(
    rendered: Rendered,
) -> None:
    """An add that fails to save fills the star, then says so without an Undo."""
    rendered.prefs_service.fail_writes = True
    await rendered.tap_star(TALK)
    assert rendered.filled(TALK)  # shown first, as the store does (D-172)
    (snack,) = rendered.snack_bars
    assert cast(ft.Text, snack.content).value == NOT_SAVED
    assert snack.action is None


async def test_a_removal_that_was_not_saved_says_so_once_and_keeps_undo(
    rendered: Rendered,
) -> None:
    """A removal that fails to save shows one SnackBar saying so, with Undo."""
    await rendered.tap_star(TALK)
    rendered.prefs_service.fail_writes = True
    await rendered.tap_star(TALK)
    (snack,) = rendered.snack_bars  # one SnackBar for one tap (ux.md §4.4)
    assert cast(ft.Text, snack.content).value == NOT_SAVED
    assert cast(ft.SnackBarAction, snack.action).label == UNDO


async def test_a_failed_click_does_not_stop_the_star(rendered: Rendered) -> None:
    """A haptic click that fails still saves the session and shows no SnackBar."""
    rendered.haptics.error = TimeoutError()
    await rendered.tap_star(TALK)
    assert rendered.favorites.ids == {TALK}
    assert rendered.snack_bars == []  # neither the click nor "Something went wrong"


async def test_the_star_is_one_named_toggle_for_screen_readers(
    rendered: Rendered,
) -> None:
    """S2: the IconButton alone was a nameless Button without a state in TalkBack."""
    node = rendered.node(f"test.favorite.{TALK}")
    assert (node.label, node.button, node.toggled) == (FAVORITE_LABEL, True, False)
    assert isinstance(node.parent, ft.MergeSemantics)
    button = rendered.star(TALK)
    assert (button.icon, button.icon_color) == (ft.Icons.STAR_BORDER, None)

    await rendered.tap_star(TALK)
    node = rendered.node(f"test.favorite.{TALK}")
    # The same name; only the state changes: "Save to My schedule, switch, on".
    assert (node.label, node.toggled) == (FAVORITE_LABEL, True)
    button = rendered.star(TALK)
    assert (button.icon, button.icon_color) == (ft.Icons.STAR, LIGHT_TOKENS.favorite)


async def test_the_star_s_state_is_said_once(rendered: Rendered) -> None:
    """VoiceOver read the tooltip after the label, and a "selected" after the "on"."""
    await rendered.tap_star(TALK)
    button = rendered.star(TALK)
    assert button.selected is None  # IconButton.selected adds Semantics(selected:)
    tooltip = button.tooltip
    assert isinstance(tooltip, ft.Tooltip) and tooltip.exclude_from_semantics


async def test_the_star_s_tooltip_says_what_a_tap_does(rendered: Rendered) -> None:
    """D-27, D-30: "Add to My schedule", then "Remove from My schedule"."""
    assert cast(ft.Tooltip, rendered.star(TALK).tooltip).message == ADD_LABEL
    await rendered.tap_star(TALK)
    assert cast(ft.Tooltip, rendered.star(TALK).tooltip).message == REMOVE_LABEL
