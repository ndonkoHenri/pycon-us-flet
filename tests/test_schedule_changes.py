"""Tests for Schedule changes (``screens/schedule_changes.py``; NEW-04, D-255, #435).

The screen runs in a real Flet session (``tests/sessions.py``) under a ``ChangeLog``
seeded with batches built by hand, so each line and sentence is pinned exactly; the
words themselves are ``tests/test_change_views.py``'s. The clock is held at 10:42 AM
on Saturday, May 16 in Long Beach. The seen marks' 2 s wait is held until the test
releases it (``tests/timers.py``), and the list can be left in the same session.
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path
from typing import cast

import flet as ft
import pytest

from pycon_us.change_log import ChangeLog
from pycon_us.config import load_year
from pycon_us.core.change_batches import Batch
from pycon_us.core.change_views import (
    AFFECTS_MY_SCHEDULE,
    ALL_CHANGES,
    REMOVED_NOTE,
    ChangeView,
    change_view,
)
from pycon_us.core.diff import Change, ChangeKind, Listing
from pycon_us.locations import parent_of
from pycon_us.prefs import Prefs
from pycon_us.screens import schedule_changes as screen
from pycon_us.screens import schedule_changes_seen as seen
from pycon_us.services.changes_file import read_batches
from pycon_us.state import Conference
from tests.feeds import processed
from tests.sessions import Shown, showing
from tests.timers import HeldSleeps

YEAR = load_year(2026)
DATA = processed(2026)
LA = YEAR.conference.zone

NOW = datetime(2026, 5, 16, 17, 42, tzinfo=UTC)
"""10:42 AM on Saturday, May 16 in Long Beach."""

VIEW = "/now/changes/2026"
"""The list pushed on Now, as Now's card pushes it."""

SAVED = "142"
"""A saved session, moved in the newest batch and retimed in the older one."""


def listing(
    title: str = "Python for Humans", hour: int = 10, location: str = "Room 104A"
) -> Listing:
    """A session's listing on Saturday, May 16, from ``hour``:30 for 30 minutes."""
    start = datetime(2026, 5, 16, hour, 30, tzinfo=LA)
    return Listing(title, start, start + timedelta(minutes=30), location)


NEWEST = Batch(
    NOW - timedelta(minutes=30),
    (
        Change(SAVED, ChangeKind.ROOM, listing(), listing(location="Room 103ABC")),
        Change("7", ChangeKind.TITLE, listing("Old name"), listing("Building Y")),
        Change("8", ChangeKind.REMOVED, listing("Gone talk"), None),
    ),
)
"""Today, 10:12 AM: a saved session moved, a rename and a removal."""

OLDER = Batch(
    NOW - timedelta(days=1, hours=2),
    (
        Change(SAVED, ChangeKind.TIME, listing(), listing(hour=11)),
        Change("9", ChangeKind.ADDED, None, listing("New talk", location="Hall B")),
    ),
    seen=True,
)
"""Yesterday, 8:42 AM, seen: the saved session retimed and an addition."""


@dataclass
class Changes(Shown):
    """The harness's ``Shown`` on Schedule changes, with its held wait and a way out."""

    sleeps: HeldSleeps = field(default_factory=HeldSleeps)
    """The seen marks' sleeps: the 2 s wait ends when the test releases it."""
    toggles: list[Callable[[bool], None]] = field(default_factory=list)
    """The setter that shows the list or leaves it, once its first render has run."""

    async def leave(self) -> None:
        """Leave the list (Back) in the same Flet session; let the cleanups run."""
        self.toggles[0](False)
        await self.settle()

    def unseen(self) -> list[bool]:
        """Each batch's seen mark in the log, ``True`` for unseen, in the log's order."""
        return [not batch.seen for batch in self.change_log.batches]

    def dots(self) -> dict[str, float]:
        """Each item's dot opacity, by the item's identifier."""
        return {
            str(node.identifier): _dot(node).opacity or 0.0
            for node in self.nodes("changes.change.")
        }


def _dot(node: ft.Semantics) -> ft.Container:
    """The unseen dot of an item's node: the second child of its leading ``Stack``."""
    tile = cast(ft.ListTile, node.content)
    stack = cast(ft.Stack, tile.leading)
    return cast(ft.Container, stack.controls[1])


type Show = Callable[..., Awaitable[Changes]]


@pytest.fixture
async def show(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Show]:
    """Return a function that shows Schedule changes over the recorded 2026 feed.

    It takes the log's ``batches``, the ``saved`` session ids, the drill id and the
    ``Prefs`` (a screen reader, reduced motion). The seen marks' wait is held.
    """
    monkeypatch.setattr(screen, "now", lambda: NOW)
    sleeps = HeldSleeps()
    monkeypatch.setattr(seen, "asyncio", sleeps)  # the seen module's name only
    async with AsyncExitStack() as stack:

        async def render(
            batches: tuple[Batch, ...] = (NEWEST, OLDER),
            *,
            saved: tuple[str, ...] = (SAVED,),
            year: str = "2026",
            prefs: Prefs | None = None,
        ) -> Changes:
            toggles: list[Callable[[bool], None]] = []

            @ft.component
            def Opened() -> ft.Control:
                shown, set_shown = ft.use_state(True)
                toggles[:] = [set_shown]
                if not shown:
                    return ft.Text("Back on Now")
                return screen.ScheduleChanges(year)

            return await stack.enter_async_context(
                showing(
                    Opened,
                    screen,
                    year=YEAR,
                    conference=Conference(data=DATA, source="bundled", version=1),
                    tmp_path=tmp_path,
                    monkeypatch=monkeypatch,
                    view_path=VIEW,
                    prefs=prefs,
                    saved=saved,
                    change_log=ChangeLog(batches=batches),
                    kind=partial(Changes, sleeps=sleeps, toggles=toggles),
                )
            )

        yield render


def outline(page: Shown) -> list[str]:
    """The list's headings and item sentences, in reading order (the stars left out)."""
    (view,) = page.find(ft.ListView)
    said: list[str] = []

    def walk(control: object) -> None:
        if isinstance(control, ft.Semantics) and control.header:
            said.append(f"h{control.heading_level} {_text(control)}")
            return
        if isinstance(control, ft.Semantics) and str(control.identifier).startswith(
            "changes.change."
        ):
            said.append(str(control.label))
            return
        for name in ("content", "_b"):  # `_b`: a component's rendered body
            child = getattr(control, name, None)
            if isinstance(child, ft.BaseControl | ft.Component):
                walk(child)
        for child in getattr(control, "controls", None) or ():
            walk(child)

    for item in view.controls:
        walk(item)
    return said


def _text(control: object) -> str:
    """The first ``Text`` value under ``control``."""
    while control is not None and not isinstance(control, ft.Text):
        control = getattr(control, "content", None)
    return str(control.value) if control is not None else ""


async def test_saved_sessions_come_first_and_groups_go_newest_first(
    show: Show,
) -> None:
    """Affects My schedule, then All changes; in each, batches newest first (ux.md §6.4)."""
    page = await show()
    assert page.titles[-1] == "Schedule changes"
    assert outline(page) == [
        f"h2 {AFFECTS_MY_SCHEDULE}",
        "h3 Today, 10:12 AM",
        (
            "New: Python for Humans: room changed from Room 104A to Room 103ABC."
            " In My schedule."
        ),
        "h3 Yesterday, 8:42 AM",
        (
            "Python for Humans: time changed. Was 10:30 to 11:00 AM,"
            " now 11:30 AM to 12:00 PM. In My schedule."
        ),
        f"h2 {ALL_CHANGES}",
        "h3 Today, 10:12 AM",
        "New: Building Y: renamed from “Old name”.",
        (
            "New: Gone talk: removed from the latest schedule."
            " Was Saturday, May 16, 10:30 to 11:00 AM, Room 104A."
        ),
        "h3 Yesterday, 8:42 AM",
        "New talk: added, Saturday, May 16, 10:30 to 11:00 AM, Hall B.",
    ]


async def test_without_saved_sessions_every_change_is_under_all_changes(
    show: Show,
) -> None:
    """With nothing saved, "Affects My schedule" is left out."""
    page = await show(saved=())
    headings = [line for line in outline(page) if line.startswith("h2")]
    assert headings == [f"h2 {ALL_CHANGES}"]


async def test_an_item_shows_old_struck_through_then_new_in_bold(show: Show) -> None:
    """The old value is struck through, the new one W_600; the sentence says both."""
    page = await show()
    line = screen.change_line(_view(NEWEST.changes[0]))
    old, arrow, new = line.spans or []
    assert (old.text, arrow.text, new.text) == ("Room 104A", " → ", "Room 103ABC")
    assert old.style and old.style.decoration == ft.TextDecoration.LINE_THROUGH
    assert new.style and new.style.weight == ft.FontWeight.W_600
    node = page.node("changes.change.142.room")
    assert node.button and node.exclude_semantics


def _view(change: Change) -> ChangeView:
    """The view of ``change`` in Long Beach's zone, 12-hour clock."""
    return change_view(change, LA, use_24h=False)


def test_a_removal_says_removed_inline_and_an_addition_shows_its_new_value() -> None:
    """A removal's line is its last listing struck, then the note; never strike alone."""
    removed = screen.change_line(_view(NEWEST.changes[2]))
    texts = [span.text for span in removed.spans or []]
    assert texts == ["Sat, May 16, 10:30–11:00 AM · Room 104A", f" · {REMOVED_NOTE}"]
    added = screen.change_line(_view(OLDER.changes[1]))
    assert [span.text for span in added.spans or []] == [
        "Sat, May 16, 10:30–11:00 AM · Hall B"
    ]


async def test_a_tap_pushes_the_session_on_the_list_and_back_returns_to_it(
    show: Show,
) -> None:
    """A tap pushes ``…/changes/2026/session/<id>``; Back pops that one level.

    The tap sits on a Container outside the excluded subtree, under the
    MergeSemantics, so the item's one node keeps the action a screen reader activates
    (a handler inside ``exclude_semantics`` is dropped from the tree).
    """
    page = await show()
    tappable = page.node("changes.change.7.title").parent
    assert isinstance(tappable, ft.Container) and tappable.on_click is not None
    assert isinstance(tappable.parent, ft.MergeSemantics)
    await page.click(tappable)
    assert page.went == [f"{VIEW}/session/7"]
    assert parent_of(page.went[0]) == VIEW


async def test_a_removed_item_is_no_link_but_keeps_its_star(show: Show) -> None:
    """A removed session opens nothing (D-186) and its star still saves it (D-255)."""
    page = await show()
    node = page.node("changes.change.8.removed")
    assert not node.button
    tappable = node.parent
    assert isinstance(tappable, ft.Container) and tappable.on_click is None
    star = page.node("changes.favorite.8.removed")
    assert star.toggled is False
    await page.click(cast(ft.IconButton, star.content))
    assert "8" in page.favorites.ids
    assert page.node("changes.favorite.8.removed").toggled is True


async def test_a_star_tap_keeps_the_item_in_its_section(show: Show) -> None:
    """Removing a saved session changes its star and sentence, not its place."""
    page = await show()
    star = page.node("changes.favorite.142.room")
    await page.click(cast(ft.IconButton, star.content))
    assert SAVED not in page.favorites.ids
    lines = outline(page)
    assert lines[:3] == [
        f"h2 {AFFECTS_MY_SCHEDULE}",
        "h3 Today, 10:12 AM",
        "New: Python for Humans: room changed from Room 104A to Room 103ABC.",
    ]


async def test_an_empty_log_says_no_changes_yet_with_a_way_out(show: Show) -> None:
    """No batch: ``HISTORY``, "No changes yet", and "Open schedule" (ux.md §4.6)."""
    page = await show(batches=())
    assert page.node("changes.empty")
    assert screen.EMPTY in page.texts()
    (button,) = page.find(ft.FilledTonalButton)
    await page.click(button)
    assert page.went == ["/schedule"]


async def test_an_id_that_is_not_the_year_shows_the_not_found_state(
    show: Show,
) -> None:
    """``changes/2025`` shows the not-found state on its own level (D-186, D-255)."""
    page = await show(year="2025")
    assert page.node("changes.not_found")
    assert screen.NOT_FOUND in page.texts()
    assert not page.nodes("changes.change.")


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
    saved = await read_batches(page.storage, LA)
    assert [batch.seen for batch in saved] == [True, True]


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
    saved = await read_batches(page.storage, LA)
    assert [batch.seen for batch in saved] == [True, True]


async def test_mark_all_as_seen_marks_every_batch_then_disables(show: Show) -> None:
    """The overflow's Mark all as seen marks the log seen and is then disabled."""
    unseen_older = Batch(OLDER.detected_at, OLDER.changes)
    page = await show((NEWEST, unseen_older))
    item = _mark_all(page)
    assert not item.disabled
    await page.click(item)
    assert page.unseen() == [False, False]
    assert _mark_all(page).disabled
    saved = await read_batches(page.storage, LA)
    assert [batch.seen for batch in saved] == [True, True]


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
