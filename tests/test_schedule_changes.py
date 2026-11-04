"""Tests for the Schedule changes list (`screens/schedule_changes.py`; NEW-04, D-255, #435).

The screen runs in `tests/changes_view.py`'s harness, a real Flet session under a
`ChangeLog` seeded with batches built by hand, so each line and sentence is pinned
exactly; the words themselves are `tests/test_change_views.py`'s. The seen marks are
`tests/test_schedule_changes_seen.py`'s.
"""

from typing import cast

import flet as ft
import pytest

from pycon_us.core.change_views import (
    AFFECTS_MY_SCHEDULE,
    ALL_CHANGES,
    REMOVED_NOTE,
    ChangeView,
    change_view,
)
from pycon_us.core.diff import Change
from pycon_us.locations import parent_of
from pycon_us.screens import schedule_changes as screen
from tests import changes_view
from tests.changes_view import (
    LA,
    NEWEST,
    OLDER,
    SAVED,
    VIEW,
    Show,
    outline,
)

show = changes_view.show  # the fixture, under this module's name


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
    """The view of `change` in Long Beach's zone, 12-hour clock."""
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
    """A tap pushes `…/changes/2026/session/<id>`; Back pops that one level.

    The tap sits on a Container outside the excluded subtree, under the
    MergeSemantics, so the item's one node keeps the action a screen reader activates
    (a handler inside `exclude_semantics` is dropped from the tree).
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


async def test_a_star_tap_re_renders_only_the_items_of_that_session(
    show: Show, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A star tap re-renders the session's two items and skips the others (D-153).

    The test fails with `ft.memo` taken off `ChangeItem`.
    """
    rendered: list[str] = []
    line = screen.change_line

    def counted(view: ChangeView) -> ft.Text:
        rendered.append(view.change.id)  # each item's body builds its line once
        return line(view)

    monkeypatch.setattr(screen, "change_line", counted)
    page = await show()
    rendered.clear()
    star = page.node("changes.favorite.142.room")
    await page.click(cast(ft.IconButton, star.content))
    assert rendered == [SAVED, SAVED]


async def test_an_empty_log_says_no_changes_yet_with_a_way_out(show: Show) -> None:
    """No batch: `HISTORY`, "No changes yet", and "Open schedule" (ux.md §4.6)."""
    page = await show(batches=())
    assert page.node("changes.empty")
    assert screen.EMPTY in page.texts()
    (button,) = page.find(ft.FilledTonalButton)
    await page.click(button)
    assert page.went == ["/schedule"]


async def test_an_id_that_is_not_the_year_shows_the_not_found_state(
    show: Show,
) -> None:
    """`changes/2025` shows the not-found state on its own level (D-186, D-255)."""
    page = await show(year="2025")
    assert page.node("changes.not_found")
    assert screen.NOT_FOUND in page.texts()
    assert not page.nodes("changes.change.")
