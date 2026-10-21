"""Tests for Now's Schedule changes card (#438; NEW-04, D-255, ux.md §5.1 item 6).

What the card counts is ``core.change_views.now_card_text()``'s (``test_change_views.py``);
here, on the screen at a fixed time of the 2026 feed: the card shows under Your next
session while an unseen change of the last 24 hours touches a saved session, never for
an unsaved one, goes once its batch is seen or 24 hours have passed, and pushes the
list on Now. The screen runs in a real Flet session through ``test_now.py``'s harness.
How the card looks and reads is checked on devices (the PR).
"""

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import flet as ft
import pytest

from pycon_us.change_log import ChangeLog
from pycon_us.core.change_batches import Batch
from pycon_us.core.diff import Change, ChangeKind, Listing
from pycon_us.screens.now_changes import IDENTIFIER
from tests.test_now import TALK, may, render  # noqa: F401  (fixture)

AT = may(16, 9)
"""9:00 AM on Saturday, May 16: TALK, saved, is next at 10:30 AM."""

OTHER = "7"
"""A 2026 session nobody saved in these tests."""


@pytest.fixture
def show(render: Callable[..., Any]) -> Callable[..., Any]:  # noqa: F811
    """``test_now.py``'s ``render``: Now at a time, in a real Flet session."""
    return render


def moved(session: str, at: datetime, *, seen: bool = False) -> Batch:
    """A batch detected ``at`` that moved ``session`` from Room 104A to Room 103ABC."""
    start = may(16, 10, 30)
    end = start + timedelta(minutes=30)
    old = Listing("Python for Humans", start, end, "Room 104A")
    new = Listing("Python for Humans", start, end, "Room 103ABC")
    return Batch(at, (Change(session, ChangeKind.ROOM, old, new),), seen=seen)


def card_tile(shown: Any) -> ft.ListTile:
    """The card's tile, under its one node."""
    tile = shown.node(IDENTIFIER).content
    assert isinstance(tile, ft.ListTile)
    return tile


def has_card(shown: Any) -> bool:
    """Whether the card is on screen."""
    return any(
        isinstance(c, ft.Semantics) and c.identifier == IDENTIFIER for c in shown.all()
    )


async def test_an_unseen_change_to_a_saved_session_shows_the_card_under_your_next(
    show: Callable[..., Any],
) -> None:
    """The card says how many saved sessions changed, after Your next session's card."""
    log = ChangeLog(batches=(moved(TALK, AT - timedelta(hours=1)),))
    shown = await show(AT, saved=(TALK,), change_log=log)
    tile = card_tile(shown)
    assert tile.title == "1 saved session changed"
    assert tile.subtitle == "Review"
    controls = shown.all()
    (next_card,) = [
        c
        for c in controls
        if isinstance(c, ft.Card) and c.variant == ft.CardVariant.FILLED
    ]
    assert controls.index(next_card) < controls.index(shown.node(IDENTIFIER))


async def test_the_card_pushes_schedule_changes_on_now(
    show: Callable[..., Any],
) -> None:
    """A tap pushes ``/now/changes/2026``, so Back returns to Now (D-255)."""
    log = ChangeLog(batches=(moved(TALK, AT - timedelta(hours=1)),))
    shown = await show(AT, saved=(TALK,), change_log=log)
    await shown.click(card_tile(shown))
    assert shown.went == ["/now/changes/2026"]


async def test_changes_to_unsaved_sessions_show_no_card(
    show: Callable[..., Any],
) -> None:
    """Changes to sessions nobody saved never show on Now (D-255)."""
    log = ChangeLog(batches=(moved(OTHER, AT - timedelta(hours=1)),))
    shown = await show(AT, saved=(TALK,), change_log=log)
    assert not has_card(shown)


async def test_the_card_goes_once_its_batch_is_seen(
    show: Callable[..., Any],
) -> None:
    """Marking the batch seen (the list's 2 s, Mark all as seen) removes the card."""
    log = ChangeLog(batches=(moved(TALK, AT - timedelta(hours=1)),))
    shown = await show(AT, saved=(TALK,), change_log=log)
    assert has_card(shown)
    log.batches = (moved(TALK, AT - timedelta(hours=1), seen=True),)
    await shown.settle()
    assert not has_card(shown)


async def test_the_card_goes_24_hours_after_the_change(
    show: Callable[..., Any],
) -> None:
    """Unseen but older than 24 hours, the change no longer shows: a minute tick."""
    log = ChangeLog(batches=(moved(TALK, AT - timedelta(hours=23, minutes=59)),))
    shown = await show(AT, saved=(TALK,), change_log=log)
    assert has_card(shown)
    await shown.at(AT + timedelta(minutes=2))
    assert not has_card(shown)
