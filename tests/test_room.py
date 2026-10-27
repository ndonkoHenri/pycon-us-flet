"""Tests for room detail's highlight (#101; ROOM-02, ROOM-03; ux.md §5.9).

How the page looks, at 200 % text and in dark mode, is checked on devices (the PR);
here, what it shows, says and does: the highlight's parsing, its one scroll and its
fade. The day lists and "Now in this room" are ``test_room_days.py``'s, an unknown room
and the location card ``test_room_location.py``'s; the harness is
``tests/room_view.py``'s.
"""

from datetime import date, datetime
from typing import cast
from urllib.parse import quote

import flet as ft
import pytest

from pycon_us.locations import query_of
from pycon_us.screens import room as screen
from pycon_us.screens import room_days
from pycon_us.theme import DARK_SCHEME, LIGHT_SCHEME
from pycon_us.ui import scrolling
from tests import room_view
from tests.feeds import processed
from tests.room_view import (
    HUMANS,
    PACIFIC,
    ROOM,
    SHARED_SLOT,
    SUNDAY_TALK,
    TACHYON,
    VIEW,
    Render,
    Scroll,
    highlighted,
)
from tests.test_theme import contrast_ratio
from tests.trees import descendants

render = room_view.render


# ------------------------------------------------------------------ the highlight


def test_the_highlight_names_one_of_the_room_s_sessions() -> None:
    """The highlight is the query's id only when it names one of the room's sessions."""
    data = processed(2026)
    room = data.rooms[ROOM]
    assert screen.highlight_of({"highlight": TACHYON}, room) == TACHYON
    assert screen.highlight_of({}, room) is None
    assert screen.highlight_of({"highlight": ""}, room) is None
    # A session of another room: a stale or hand-made link highlights nothing.
    assert screen.highlight_of({"highlight": "191"}, room) is None
    assert screen.highlight_of({"highlight": TACHYON}, None) is None


def test_the_highlight_compares_ids_as_strings() -> None:
    """The highlight matches the session's id as a string: "31" does, "031" does not.

    Ionic compared a number with a string, so its highlight never showed (ROOM-03).
    """
    room = processed(2026).rooms[ROOM]
    query = query_of(highlighted(TACHYON))
    assert query == {"highlight": "31"}
    assert screen.highlight_of(query, room) == "31"
    assert screen.highlight_of({"highlight": "031"}, room) is None


def test_a_quoted_synthetic_id_reaches_the_room_whole() -> None:
    """A break's quoted id, spaces and colons included, highlights that break.

    A break's id holds spaces and colons (D-42); the tile quotes it, the query unquotes.
    """
    data = processed(2026)
    coffee = "break-Expo Hall AB-2026-05-15T08:00:00-07:00"
    query = query_of(f"/map/room/expo-hall-ab?highlight={quote(coffee, safe='')}")
    assert screen.highlight_of(query, data.rooms["expo-hall-ab"]) == coffee


@pytest.mark.parametrize(
    ("highlighted_day", "current", "expected"),
    [
        (date(2026, 5, 17), date(2026, 5, 16), date(2026, 5, 17)),  # the row's day
        (None, date(2026, 5, 16), date(2026, 5, 16)),  # today
        (None, date(2026, 10, 13), date(2026, 5, 15)),  # off season: the first day
        (date(2026, 5, 13), date(2026, 5, 13), date(2026, 5, 15)),  # neither listed
    ],
)
def test_the_room_opens_on_the_row_s_day_else_today_else_its_first_day(
    highlighted_day: date | None, current: date, expected: date
) -> None:
    """The room opens on the highlighted row's day, else today, else its first day."""
    days = [date(2026, 5, 15), date(2026, 5, 16), date(2026, 5, 17)]
    assert screen.opening_day(days, highlighted_day, current) == expected


async def test_opened_from_a_session_the_room_shows_its_day_and_scrolls_to_it_once(
    render: Render,
) -> None:
    """Opened with a highlight, the room shows the row's day and scrolls to it once.

    The scroll takes 400 ms, and the view memory records the highlight for the View.
    """
    room = await render(highlighted(TACHYON))
    assert room.tabs.selected_index == 1  # Friday, Saturday, Sunday
    assert room.scrolls == [Scroll("session-31", 400)]
    assert room.memory.room_highlights == {VIEW: TACHYON}


async def test_only_the_scrolled_day_s_list_builds_every_row(render: Render) -> None:
    """Only the highlighted day's list is built in full and listens to its scroll.

    ``scroll_to`` reaches only a built item (F32): that list is built in full (D-154).
    """
    room = await render(highlighted(TACHYON))
    lists = room.day_lists()
    assert [lst.cache_extent for lst in lists] == [
        None,
        scrolling.FULL_LIST_EXTENT,
        None,
    ]
    assert [lst.on_scroll is not None for lst in lists] == [False, True, False]


async def test_the_row_is_lit_then_the_highlight_fades(render: Render) -> None:
    """The row is lit at once, stays lit while its wait runs, then fades.

    The box animates over 250 ms, and the wait, ``HIGHLIGHT_S``, is asked for once.
    """
    room = await render(highlighted(TACHYON))
    box = room.lit_box()
    anchor = room.anchor()
    # D-242: the key marks the row's top; the row is not under it, so it keeps its
    # nodes, and the screen reader's focus comes back to it after Back (F62).
    assert anchor.key == ft.ScrollKey("session-31")
    assert anchor.content is None and anchor.height == 0
    assert not _inside(room.node(f"room.session.{TACHYON}"), anchor)
    assert box.bgcolor == room_days.HIGHLIGHT
    assert isinstance(box.animate, ft.Animation) and box.animate.duration == 250
    await room.until(lambda: room.sleeps.held == 1)
    assert room.sleeps.asked == [screen.HIGHLIGHT_S]  # all of it, once in place
    assert room.lit_box().bgcolor == room_days.HIGHLIGHT  # lit while it waits
    await room.fade()


async def test_a_row_alone_in_its_slot_is_lit_with_its_time(render: Render) -> None:
    """The tint spans the slot, the gutter's time too, as a selected item (D-194).

    The slot's divider stays above the box, as the Schedule's (ux.md §5.2): the jump
    puts the time under the tab bar's line, not a second line. 3:15 PM is not the
    day's first slot, so it has one.
    """
    room = await render(highlighted(TACHYON))
    box = room.lit_box()
    assert _inside(room.node(f"room.session.{TACHYON}"), box)
    assert any(
        isinstance(c, ft.Semantics) and c.header and c.label == "3:15 PM"
        for c in descendants(box)
    )
    assert not any(isinstance(c, ft.Divider) for c in descendants(box))
    slot = cast(ft.Column, box.parent)
    assert isinstance(slot.controls[0], ft.Divider) and slot.controls[1] is box


def _inside(node: ft.Control, ancestor: ft.Control) -> bool:
    """Whether ``node`` renders under ``ancestor``, through components too."""
    parent = node.parent
    while parent is not None:
        if parent is ancestor:
            return True
        parent = parent.parent
    return False


async def test_a_row_that_shares_its_slot_is_lit_alone(render: Render) -> None:
    """Of two rows in one slot, only the highlighted one is inside the lit box."""
    first, other = SHARED_SLOT
    room = await render(
        highlighted(first),  # the fixture's View path; the slug is what counts
        slug="room-102c",
        now=datetime(2026, 5, 16, 14, 10, tzinfo=PACIFIC),
    )
    box = room.lit_box()
    _, row = cast(ft.Column, box.content).controls  # the anchor, then the row
    assert getattr(row, "key", None) == first  # the row, keyed by its id
    assert not _inside(room.node(f"room.session.{other}"), box)


async def test_under_reduced_motion_the_scroll_jumps_and_the_highlight_just_goes(
    render: Render,
) -> None:
    """Under reduced motion the scroll jumps (0 ms), and the lit box is not animated."""
    room = await render(highlighted(TACHYON), reduce_motion=True)
    assert room.scrolls == [Scroll("session-31", 0)]
    assert room.lit_box().bgcolor == room_days.HIGHLIGHT
    assert room.lit_box().animate is None
    await room.until(lambda: room.sleeps.held == 1)
    assert room.sleeps.asked == [screen.HIGHLIGHT_S]
    await room.fade()


async def test_a_re_render_does_not_scroll_again(render: Render) -> None:
    """A re-render after a star tap scrolls no more: the room scrolled once.

    A star tap, a refresh, Back from a detail: the effect ran once (D-18).
    """
    room = await render(highlighted(TACHYON))
    await room.favorites.toggle(room.storage, HUMANS)
    await room.wait(0.1)
    assert len(room.scrolls) == 1


async def test_a_view_rebuilt_in_a_new_session_does_not_scroll_or_light_up(
    render: Render,
) -> None:
    """A View rebuilt in a new session opens on the row's day, without scroll or light.

    D-143: a replaced session's View never unmounts (F30); its successor finds it. It
    still opens on the session's day, Sunday, where the user came for it.
    """
    first = await render(highlighted(SUNDAY_TALK))
    again = await render(highlighted(SUNDAY_TALK), memory=first.memory)
    assert again.scrolls == []
    assert again.tabs.selected_index == 2
    assert not any(
        isinstance(c, ft.Container) and isinstance(c.key, ft.ScrollKey)
        for c in again.session.index.values()
    )


async def test_after_leaving_the_room_the_next_room_tile_highlights_again(
    render: Render,
) -> None:
    """Back forgets the highlight, so the room opened again scrolls to the row again."""
    room = await render(highlighted(TACHYON))
    await room.fade()
    await room.show(False)  # Back pops the room: it forgets its highlight
    assert room.memory.room_highlights == {}
    await room.show(True)  # the session's room tile, tapped again
    await room.until(lambda: len(room.scrolls) == 2)
    assert [scroll.key for scroll in room.scrolls] == ["session-31", "session-31"]


async def test_without_a_highlight_nothing_scrolls_and_today_shows(
    render: Render,
) -> None:
    """Without a highlight, today shows; nothing scrolls, lights or is built in full."""
    room = await render(VIEW)
    assert room.scrolls == []
    assert room.tabs.selected_index == 1  # the clock says Saturday
    assert room.memory.room_highlights == {}
    assert not any(
        isinstance(c, ft.Container) and isinstance(c.key, ft.ScrollKey)
        for c in room.session.index.values()
    )
    # A room opened from the Map builds no list in full.
    assert {lst.cache_extent for lst in room.day_lists()} == {None}


async def test_a_highlight_of_another_room_s_session_is_ignored(
    render: Render,
) -> None:
    """A highlight of another room's session neither scrolls nor is remembered."""
    room = await render(highlighted("191"))  # a tutorial in Room 102C
    assert room.scrolls == []
    assert room.memory.room_highlights == {}


@pytest.mark.parametrize("dark", [False, True])
def test_the_lit_row_s_text_keeps_its_contrast(dark: bool) -> None:
    """On the lit fill both text colours keep 4.5:1, and the fill shows on the surface.

    In light and in dark: dark ``primary_container`` put the supporting text at 3.7:1
    (D-194).
    """
    scheme = DARK_SCHEME if dark else LIGHT_SCHEME
    fill = _blend(str(scheme.primary), str(scheme.surface), room_days.HIGHLIGHT_OPACITY)
    for text in (scheme.on_surface, scheme.on_surface_variant):
        assert contrast_ratio(fill, str(text)) >= 4.5
    assert contrast_ratio(fill, str(scheme.surface)) >= 1.25  # it shows


def _blend(color: str, under: str, opacity: float) -> str:
    """Return ``color`` at ``opacity`` over ``under``, as ``#RRGGBB``."""
    channels = [
        round(
            opacity * int(color[i : i + 2], 16)
            + (1 - opacity) * int(under[i : i + 2], 16)
        )
        for i in (1, 3, 5)
    ]
    return "#" + "".join(f"{c:02X}" for c in channels)
