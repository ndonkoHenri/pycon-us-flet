"""Tests for the My schedule tab's states and its notice of dropped sessions (D-329).

The screen runs in ``tests/my_schedule_view.py``'s harness.
"""

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any, cast

import flet as ft
import pytest

from pycon_us.core.change_batches import Batch
from pycon_us.core.diff import Change, ChangeKind, Listing
from pycon_us.screens import my_schedule_extras as extras
from pycon_us.ui.favorite import REMOVED, UNDO
from tests import my_schedule_view
from tests.my_schedule_view import FAVORITES, SAVED, THURSDAY, ZONE, Setup, Shown, _walk

setup, shown, before = (
    my_schedule_view.setup,
    my_schedule_view.shown,
    my_schedule_view.before,
)


# ------------------------------------------------------------------ states


@pytest.fixture
def nothing_saved(setup: Setup) -> None:
    """Save no session."""
    setup.saved = ()


@pytest.mark.usefixtures("nothing_saved")
async def test_nothing_saved_says_how_and_opens_the_schedule(shown: Shown) -> None:
    """ux.md §4.6, SCHED-08."""
    shown.node("my_schedule.empty")
    assert "Nothing saved yet" in shown.texts()
    (button,) = [c for c in shown.controls if isinstance(c, ft.FilledTonalButton)]
    assert button.content == "Browse the schedule"
    await shown.session.dispatch_event(button._i, "click", None)
    await shown.settle()
    assert shown.went == ["/schedule"]


@pytest.fixture
def dropped(setup: Setup) -> None:
    """Save only an id the feed does not list."""
    setup.saved = ("no-such-session",)


@pytest.mark.usefixtures("dropped")
async def test_saved_sessions_the_feed_dropped_are_not_nothing_saved(
    shown: Shown,
) -> None:
    """Saved ids the feed dropped get their own state, not "Nothing saved yet".

    D-172 keeps ids the feed no longer lists: saying "Nothing saved yet" would be
    untrue.
    """
    shown.node("my_schedule.dropped")
    assert not shown.nodes("my_schedule.dropped_notice")  # the state says it all
    assert "None of your saved sessions is in the schedule" in shown.texts()
    assert "Nothing saved yet" not in shown.texts()
    (button,) = [c for c in shown.controls if isinstance(c, ft.FilledTonalButton)]
    assert button.content == "Browse the schedule"


@pytest.fixture
def unread(setup: Setup) -> None:
    """Give the screen favorites that were never read."""
    setup.loaded = False


@pytest.mark.usefixtures("unread")
async def test_a_failed_read_is_not_an_empty_list(shown: Shown) -> None:
    """D-172: after the gate, ``loaded`` False means the saved list could not be read."""
    shown.node("my_schedule.unavailable")
    assert "Couldn't open My schedule" in shown.texts()
    assert "Nothing saved yet" not in shown.texts()
    assert not any(isinstance(c, ft.FilledTonalButton) for c in shown.controls)


@pytest.fixture
def no_data(setup: Setup) -> None:
    """Start without conference data or a fetch problem."""
    setup.data = False


@pytest.mark.usefixtures("no_data")
async def test_without_data_the_skeleton_shows_until_the_first_fetch_fails(
    shown: Shown,
) -> None:
    """Without data, before a fetch has failed, the screen shows the skeleton."""
    assert "skeleton" in shown.texts()


@pytest.fixture
def failed_fetch(setup: Setup) -> None:
    """Start without conference data, after a fetch failed offline."""
    setup.data, setup.problem = False, "offline"


@pytest.mark.usefixtures("failed_fetch")
async def test_without_data_a_failed_fetch_offers_try_again(shown: Shown) -> None:
    """Without data, a failed fetch shows the "Can't load the schedule" state."""
    shown.node("my_schedule.no_data")
    assert "Can't load the schedule" in shown.texts()


# ------------------------------------------------------------------ some dropped (D-329)

GONE, LOST = "gone-session", "lost-session"
"""Saved ids the 2026 feed does not list."""


def removal(session_id: str) -> Batch:
    """A batch, an hour before Thursday's clock, that removed ``session_id``."""
    start = datetime(2026, 5, 15, 11, 0, tzinfo=ZONE)
    last = Listing("A dropped talk", start, start + timedelta(minutes=30), "Room 104A")
    change = Change(session_id, ChangeKind.REMOVED, last, None)
    return Batch(THURSDAY - timedelta(hours=1), (change,))


@pytest.fixture
def one_dropped(setup: Setup) -> None:
    """Save every default session and one id the feed no longer lists."""
    setup.saved = (*SAVED, GONE)


@pytest.mark.usefixtures("one_dropped", "before")
async def test_a_notice_says_a_saved_session_is_no_longer_in_the_schedule(
    shown: Shown,
) -> None:
    """D-329: one live node says how many are gone; the rest of the list stays."""
    node = shown.node("my_schedule.dropped_notice")
    assert node.live_region
    texts = shown.texts()
    assert "1 saved session is no longer in the schedule" in texts
    assert "If the schedule lists it again, it comes back here." in texts
    assert shown.shown() == list(SAVED)
    # Under the status strip, before the first day's header.
    under_strip = list(_walk(shown.root().controls[1]))
    assert node in under_strip
    assert not shown.nodes("my_schedule.see_changes")  # the log has no removal
    shown.node("my_schedule.forget")


@pytest.mark.usefixtures("one_dropped", "before")
async def test_forget_unsaves_only_the_dropped_ids_with_undo(shown: Shown) -> None:
    """D-329: "Forget it" removes the dropped id, says so with Undo, and Undo restores."""
    forget = cast(ft.TextButton, shown.node("my_schedule.forget").content)
    assert forget.content == "Forget it"
    await shown.click(forget)
    assert shown.favorites.ids == frozenset(SAVED)
    assert shown.prefs_service.values[FAVORITES] == sorted(SAVED)
    assert not _words(shown.node("my_schedule.dropped_notice"))  # quiet again
    assert not shown.nodes("my_schedule.forget")
    (snack,) = shown.snack_bars
    assert cast(ft.Text, snack.content).value == REMOVED
    action = cast(ft.SnackBarAction, snack.action)
    assert action.label == UNDO

    await cast(Callable[[], Any], action.on_click)()
    await shown.settle()
    assert GONE in shown.favorites.ids
    assert _words(shown.node("my_schedule.dropped_notice"))


def _words(node: ft.Control) -> list[str]:
    """Return the texts under ``node`` (the live region or its merge), in order."""
    return [str(c.value) for c in _walk(node) if isinstance(c, ft.Text)]


@pytest.mark.usefixtures("one_dropped", "before")
async def test_the_notice_says_its_title_then_its_body_as_one_heading(
    shown: Shown,
) -> None:
    """D-329: one node whose label is the title, then the body, as the screen shows.

    A merge of the texts read the body first on Android: Flet's ``Semantics``
    always states ``enabled``, so a heading ``Semantics`` inside the live region
    conflicted with it and became a child node, whose label a merge puts after the
    live region's own. So the label is explicit and the texts are excluded.
    """
    node = cast(ft.Semantics, shown.node("my_schedule.dropped_notice"))
    title = "1 saved session is no longer in the schedule"
    body = "If the schedule lists it again, it comes back here."
    assert node.label == f"{title}\n{body}"
    assert _words(node) == [title, body]  # the screen's order too
    assert node.exclude_semantics
    assert node.container and node.live_region
    assert node.header and node.heading_level == 2
    inner = [c for c in _walk(node) if c is not node]
    assert not any(isinstance(c, ft.Semantics | ft.MergeSemantics) for c in inner)
    assert not any(isinstance(c, ft.TextButton) for c in inner)


@pytest.mark.usefixtures("two_dropped_one_logged")
async def test_the_notice_label_follows_the_count(shown: Shown) -> None:
    """D-329: with two dropped, the label is the plural title, then the plural body."""
    node = cast(ft.Semantics, shown.node("my_schedule.dropped_notice"))
    assert node.label == (
        "2 saved sessions are no longer in the schedule\n"
        "If the schedule lists them again, they come back here."
    )


@pytest.mark.usefixtures("before")
async def test_the_live_region_is_there_before_a_session_is_dropped(
    shown: Shown,
) -> None:
    """D-329, F61: the quiet node is mounted and keeps its id when a drop appears.

    Android's engine sends a live region's change only for a node it had in its
    previous update, so the notice must not mount with its words.
    """
    quiet = shown.node("my_schedule.dropped_notice")
    assert quiet.live_region
    assert not _words(quiet)
    assert not shown.nodes("my_schedule.forget")
    assert "EVENT_BUSY_OUTLINED" not in [
        str(c.icon) for c in shown.find(ft.Icon) if c.visible
    ]

    await shown.favorites.add_many(shown.storage, [GONE])  # as a refresh would
    await shown.settle()
    spoken = shown.node("my_schedule.dropped_notice")
    assert spoken._i == quiet._i  # the same node, its label changed
    assert _words(spoken)[0] == "1 saved session is no longer in the schedule"
    shown.node("my_schedule.forget")


@pytest.mark.usefixtures("before")
async def test_the_quiet_node_is_hidden_and_shows_with_its_words(
    shown: Shown,
) -> None:
    """D-329, F95: hidden with no dropped session, shown with one, hidden after Forget.

    Empty is not quiet on Android: Flet's ``Semantics`` always states ``enabled``,
    a focusable flag, so only ``hidden`` keeps TalkBack from stopping on the blank
    node. The node keeps its id throughout, so its reveal is a label change (F61).
    """
    quiet = cast(ft.Semantics, shown.node("my_schedule.dropped_notice"))
    assert quiet.hidden is True
    assert not _words(quiet)
    assert not quiet.label

    await shown.favorites.add_many(shown.storage, [GONE])  # 0 -> 1, as a refresh
    await shown.settle()
    spoken = shown.node("my_schedule.dropped_notice")
    assert spoken._i == quiet._i
    assert spoken.hidden is False
    assert _words(spoken)[0] == "1 saved session is no longer in the schedule"
    assert cast(ft.Semantics, spoken).label  # the reveal changes the label (F61)

    await shown.click(cast(ft.TextButton, shown.node("my_schedule.forget").content))
    again = shown.node("my_schedule.dropped_notice")  # 1 -> 0
    assert again._i == quiet._i
    assert again.hidden is True
    assert not _words(again)
    assert not cast(ft.Semantics, again).label


@pytest.fixture
def two_dropped_one_logged(setup: Setup) -> None:
    """Save two ids the feed no longer lists, one of them removed in the change log."""
    setup.saved = (*SAVED, GONE, LOST)
    setup.batches = (removal(LOST),)


@pytest.mark.usefixtures("two_dropped_one_logged")
async def test_a_logged_removal_links_to_schedule_changes(shown: Shown) -> None:
    """D-329: with a removal in the log, "See what changed" pushes Schedule changes."""
    texts = shown.texts()
    assert "2 saved sessions are no longer in the schedule" in texts
    assert "If the schedule lists them again, they come back here." in texts
    forget = cast(ft.TextButton, shown.node("my_schedule.forget").content)
    assert forget.content == "Forget them"
    see = cast(ft.TextButton, shown.node("my_schedule.see_changes").content)
    assert see.content == "See what changed"
    await shown.click(see)
    assert shown.went == ["/changes/2026"]  # on top of the View (no Router here)


def test_only_a_removal_of_a_dropped_id_counts_as_logged() -> None:
    """D-329: another session's removal, or a dropped id's retiming, links nowhere."""
    assert extras.logged({GONE}, [removal(GONE)])
    assert not extras.logged({GONE}, [removal(LOST)])
    moved = removal(GONE).changes[0]
    retimed = Change(GONE, ChangeKind.TIME, moved.old, moved.old)
    assert not extras.logged({GONE}, [Batch(THURSDAY, (retimed,))])
    assert not extras.logged({GONE}, [])
