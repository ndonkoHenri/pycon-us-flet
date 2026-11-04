"""Tests for Schedule changes' seen marks (`screens/schedule_changes_seen.py`; #436).

The screen runs in `tests/changes_view.py`'s harness, with the clock held at 10:42 AM
on Saturday, May 16 in Long Beach. The seen marks' 2 s wait is held until the test
releases it (`tests/timers.py`), and the list can be left in the same session; under
the Router, the list is left for a session pushed on it.
"""

from collections.abc import Awaitable, Callable
from typing import cast

import flet as ft
import pytest

from pycon_us.change_log import ChangeLog
from pycon_us.core.change_batches import Batch
from pycon_us.prefs import Prefs
from pycon_us.screens import schedule_changes as screen
from pycon_us.screens import schedule_changes_seen as seen
from pycon_us.services.changes_file import changes_path
from tests import changes_view, links
from tests.changes_view import (
    NEWEST,
    NOW,
    OLDER,
    SAVED,
    VIEW,
    Changes,
    Show,
    _dot,
    outline,
)
from tests.links import Open
from tests.timers import HeldSleeps

show = changes_view.show  # the fixture, under this module's name
open_at = links.open_at  # the fixture, under this module's name (tests/chrome.py)


# ------------------------------------------------------------------ seen marks (#436)


async def test_unseen_items_have_a_dot_and_seen_ones_none(show: Show) -> None:
    """The newest batch's items show the 6 dp dot; the seen batch's have it at 0."""
    page = await show()
    dots = page.dots()
    assert dots["changes.change.142.room"] == 1.0
    assert dots["changes.change.8.removed"] == 1.0
    assert dots["changes.change.142.time"] == 0.0
    dot = _dot(page.node("changes.change.142.room"))
    assert (dot.width, dot.height, dot.bgcolor) == (6, 6, ft.Colors.PRIMARY)


async def test_the_list_marks_what_it_shows_seen_after_two_seconds(
    show: Show,
) -> None:
    """After the 2 s wait the batch is seen, "New:" goes, the dot fades, and it is saved."""
    page = await show()
    assert page.sleeps.asked == [seen.SEEN_AFTER_S]
    await page.sleeps.release()
    await page.settle()
    assert page.unseen() == [False, False]
    assert not any(line.startswith("New: ") for line in outline(page))
    assert set(page.dots().values()) == {0.0}
    assert _dot(page.node("changes.change.142.room")).animate_opacity == seen.FADE_MS
    assert await page.saved() == [True, True]


async def test_leaving_before_two_seconds_keeps_the_batch_unseen(show: Show) -> None:
    """Left at 1 s, the wait is cancelled: the batch stays unseen, Now's card stays."""
    page = await show()
    assert page.sleeps.held == 1
    await page.leave()
    assert page.sleeps.held == 0
    assert page.unseen() == [True, False]
    assert page.change_log.unseen_saved({SAVED}, NOW) == 1


async def test_with_a_screen_reader_the_list_marks_on_leaving(show: Show) -> None:
    """No timer drops "New:" mid-reading: the batches are marked when the list is left."""
    page = await show(prefs=Prefs(loaded=True, screen_reader=True))
    await page.settle()
    assert page.sleeps.asked == []
    assert page.unseen() == [True, False]
    await page.leave()
    assert page.unseen() == [False, False]
    assert await page.saved() == [True, True]


async def test_mark_all_as_seen_marks_every_batch_then_disables(show: Show) -> None:
    """The overflow's Mark all as seen marks the log seen and is then disabled."""
    unseen_older = Batch(OLDER.detected_at, OLDER.changes)
    page = await show((NEWEST, unseen_older))
    item = _mark_all(page)
    assert not item.disabled
    await page.click(item)
    assert page.unseen() == [False, False]
    assert _mark_all(page).disabled
    assert await page.saved() == [True, True]


def _mark_all(page: Changes) -> ft.PopupMenuItem:
    """The overflow's Mark all as seen item."""
    (menu,) = page.find(ft.PopupMenuButton)
    (item,) = menu.items or []
    assert cast(ft.Semantics, item.content).identifier == "changes.mark_all"
    return item


async def test_mark_all_is_disabled_with_nothing_unseen(show: Show) -> None:
    """A log whose batches are all seen shows Mark all as seen disabled, and no wait."""
    page = await show((OLDER,))
    assert _mark_all(page).disabled
    assert page.sleeps.asked == []


async def test_under_reduced_motion_the_dot_does_not_fade(show: Show) -> None:
    """With reduced motion the dot goes at once (D-173)."""
    page = await show(prefs=Prefs(loaded=True, reduce_motion=True))
    assert _dot(page.node("changes.change.142.room")).animate_opacity is None


async def test_a_screen_reader_turned_on_during_the_wait_stops_it(show: Show) -> None:
    """Turned on mid-wait, the timer stops: "New:" stays until the list is left."""
    page = await show()
    assert page.sleeps.held == 1
    page.prefs.screen_reader = True
    await page.settle()
    assert page.sleeps.held == 0
    assert page.unseen() == [True, False]
    await page.leave()
    assert page.unseen() == [False, False]


async def test_a_screen_reader_turned_off_starts_the_wait(show: Show) -> None:
    """Turned off on the list, the 2 s wait starts and then marks what it shows."""
    page = await show(prefs=Prefs(loaded=True, screen_reader=True))
    assert page.sleeps.asked == []
    page.prefs.screen_reader = False
    await page.settle()
    assert page.sleeps.asked == [seen.SEEN_AFTER_S]
    await page.sleeps.release()
    await page.settle()
    assert page.unseen() == [False, False]


async def test_a_closed_session_marks_nothing_and_writes_nothing(show: Show) -> None:
    """The wait that ends after its session closed leaves the log and its file (D-147)."""
    page = await show()
    page.services.closed.set()  # a new session replaced this one, still mounted (F30)
    await page.sleeps.release()
    await page.settle()
    assert page.unseen() == [True, False]
    assert not changes_path(page.storage).exists()


# ------------------------------------------------------------------ under the Router


@pytest.fixture
def routed(
    open_at: Open, monkeypatch: pytest.MonkeyPatch
) -> Callable[..., Awaitable[links.Shown]]:
    """Return `open(location, prefs=...)`: the app's Views at a location (D-141).

    The log holds `NEWEST` (unseen) and `OLDER`; the seen marks' wait is held, its
    `HeldSleeps` in the result's `sleeps`.
    """
    monkeypatch.setattr(screen, "now", lambda: NOW)
    sleeps = HeldSleeps()
    monkeypatch.setattr(seen, "asyncio", sleeps)

    async def open_(location: str, prefs: Prefs | None = None) -> links.Shown:
        shown = await open_at(
            location, change_log=ChangeLog(batches=(NEWEST, OLDER)), prefs=prefs
        )
        shown.sleeps = sleeps  # pyright: ignore[reportAttributeAccessIssue]
        return shown

    return open_


async def test_a_session_pushed_on_the_list_stops_the_wait(
    routed: Callable[..., Awaitable[links.Shown]],
) -> None:
    """The list stays mounted under a session, unseen: the wait restarts on Back."""
    page = await routed(VIEW)
    sleeps: HeldSleeps = page.sleeps  # pyright: ignore[reportAttributeAccessIssue]
    assert sleeps.held == 1
    await page.go(f"{VIEW}/session/7")
    assert page.routes()[-2:] == [VIEW, f"{VIEW}/session/7"]
    assert sleeps.held == 0
    assert [b.seen for b in page.change_log.batches] == [False, True]
    await page.go(VIEW)  # Back
    await sleeps.release()
    await page.settle()
    assert [b.seen for b in page.change_log.batches] == [True, True]


async def test_a_deep_link_to_a_session_beneath_the_list_starts_no_wait(
    routed: Callable[..., Awaitable[links.Shown]],
) -> None:
    """A cold link to `…/changes/2026/session/7` builds the list unseen: no wait."""
    page = await routed(f"{VIEW}/session/7")
    sleeps: HeldSleeps = page.sleeps  # pyright: ignore[reportAttributeAccessIssue]
    assert VIEW in page.routes()
    assert sleeps.asked == []
    assert [b.seen for b in page.change_log.batches] == [False, True]


async def test_with_a_screen_reader_a_pushed_session_marks_the_list(
    routed: Callable[..., Awaitable[links.Shown]],
) -> None:
    """With a screen reader, leaving the list for a session marks what it showed."""
    page = await routed(VIEW, prefs=Prefs(loaded=True, screen_reader=True))
    assert [b.seen for b in page.change_log.batches] == [False, True]
    await page.go(f"{VIEW}/session/7")
    assert [b.seen for b in page.change_log.batches] == [True, True]
