"""Room detail's day lists and the lit row (ROOM-02, ROOM-03; ux.md §5.9).

``screens/room.py`` owns the screen: the stores, the day tabs (the Schedule's
``day_tab()``), the highlight's effect and "Now in this room". Here is what it places in
each ``TabBarView`` page: ``day_list()``, a day's time slots (D-31, ``TimeSlot``: a
``TimeGutter`` beside the slot's ``SessionRow``s and ``NoticeRow``s), with the row the
room was opened from keyed for the jump (``ui.scrolling.jump_to_key()``) and lit: its
whole slot when it has the slot to itself.
"""

from collections.abc import Callable

import flet as ft

from pycon_us.config import ConferenceInfo
from pycon_us.core.row_views import SessionView, by_slot
from pycon_us.core.timefmt import time_label
from pycon_us.theme import Tokens
from pycon_us.ui.badges import ToggleFavorite
from pycon_us.ui.scrolling import FULL_LIST_EXTENT, SCROLL_EVENT_MS, anchored
from pycon_us.ui.session_rows import NoticeRow, SessionRow, is_notice
from pycon_us.ui.time_gutter import TimeSlot

SCREEN = "room"
"""The screen's name in its semantics identifiers (decisions §M)."""

HIGHLIGHT_OPACITY = 0.16
"""The share of ``primary`` in the lit row's fill, which the contrast test blends."""

HIGHLIGHT = ft.Colors.with_opacity(HIGHLIGHT_OPACITY, ft.Colors.PRIMARY)
"""The lit row's fill: a ``primary`` tint over the surface, close to ``primary_container``
in light. Dark ``primary_container`` would put the rows' supporting text at 3.7:1; on
the tint it reads 5.0:1 in light and 5.9:1 in dark (D-194)."""

UNLIT = ft.Colors.with_opacity(0, ft.Colors.PRIMARY)
"""The same fill, clear: the fade runs from one to the other."""


def row_key(session_id: str) -> str:
    """Return the ``ScrollKey`` value of a session's row on a room's page (ux.md §5.9)."""
    return f"session-{session_id}"


def day_list(
    views: list[SessionView],
    info: ConferenceInfo,
    *,
    favorites: frozenset[str],
    on_toggle: ToggleFavorite,
    tokens: Tokens,
    use_24h: bool,
    time_above: bool,
    reveal: str | None,
    lit: bool,
    fade_ms: int,
    list_ref: ft.Ref[ft.ListView] | None = None,
    on_scroll: Callable[[ft.OnScrollEvent], None] | None = None,
    head: ft.Control | None = None,
) -> ft.ListView:
    """Return one day's list: its time slots, a divider between them (D-31).

    A plain builder: the rows are memoised components (D-153, D-184), and a room's day
    holds a few dozen at most.

    Args:
        views: The day's row views, in the room's order (by start, then name).
        info: The year's facts: the zone and the track registry.
        favorites: The saved ids (``Favorites.ids``).
        on_toggle: The screen's one star handler (``use_favorite_toggle()``).
        tokens: The scheme's tokens (D-150).
        use_24h: Whether the device uses the 24-hour clock.
        time_above: Put each slot's time above its rows (``Prefs.time_above``,
            D-216).
        reveal: The session whose row the room was opened from, if this View shows it:
            that row gets its ``ScrollKey`` and the highlight.
        lit: Whether the highlight is on.
        fade_ms: How long it fades out, through ``prefs.motion_ms()``.
        list_ref: The list's ref, for the list that scrolls to the row.
        on_scroll: Its scroll handler, which reads each scroll's end.
        head: What comes before the slots: today's "Now in this room".
    """
    items: list[ft.Control] = []
    for start, slot in by_slot(views):
        # The row alone is lit when it shares its slot; else the whole slot, its time
        # too, edge to edge as a selected list item is (D-194).
        alone = [view.session.id for view in slot] == [reveal]
        rows: list[ft.Control] = []
        for view in slot:
            session = view.session
            row = (
                NoticeRow(view, screen=SCREEN)
                if is_notice(session, info)
                else SessionRow(
                    view, session.id in favorites, on_toggle, tokens, screen=SCREEN
                )
            )
            if session.id == reveal and not alone:
                row = _lit(row, row_key(session.id), on=lit, ms=fade_ms)
            rows.append(row)
        label = time_label(start, info.zone, use_24h=use_24h)
        item = TimeSlot(label, rows, divider=False, above=time_above)
        if alone:
            item = _lit(item, row_key(slot[0].session.id), on=lit, ms=fade_ms)
        if items:
            # The divider stays outside the lit box, as the Schedule's slots keep it
            # outside theirs: the jump puts the time, not a line, under the tab bar's.
            item = ft.Column([ft.Divider(height=1), item], spacing=0)
        items.append(item)
    return ft.ListView(
        [head, *items] if head is not None else items,
        ref=list_ref,
        expand=True,
        padding=ft.Padding.only(bottom=8),
        # Only the list that scrolls needs every row built (D-154).
        cache_extent=FULL_LIST_EXTENT if list_ref is not None else None,
        scroll_interval=SCROLL_EVENT_MS,
        on_scroll=on_scroll,
    )


def _lit(row: ft.Control, key: str, *, on: bool, ms: int) -> ft.Control:
    """Wrap the row the room was opened from, or its slot: the scroll target, lit.

    An anchor at the top of the box carries the ``ScrollKey`` (a plain key is never
    registered for ``scroll_to``), so the row keeps its nodes (D-242); the box carries
    the tint, which fades out in ``ms``; at 0, under reduced motion (D-173), the
    highlight simply goes.
    """
    return ft.Container(
        anchored(key, row),
        bgcolor=HIGHLIGHT if on else UNLIT,
        animate=ft.Animation(ms, ft.AnimationCurve.EASE_OUT) if ms else None,
    )
