"""Room detail's day tabs and day lists, the lit row and the scroll to it (ROOM-02, -03).

``screens/room.py`` owns the screen: the stores, the highlight's effect and "Now in this
room". Here is what it places under the tab bar (ux.md §5.9):

- ``day_tab()``, one tab per day the room has sessions, today marked by a dot;
- ``day_list()``, one per day: its time slots (D-31), a ``TimeGutter`` beside the slot's
  ``SessionRow``s and ``NoticeRow``s, the row the room was opened from lit and keyed;
- ``scroll_to_row()``, the one scroll to that row (D-155).

The day tab and the scroll are local versions of the Schedule's (#220), to be shared
once both are on ``main`` (#228).
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import date, datetime

import flet as ft

from pycon_us.config import ConferenceInfo
from pycon_us.core.row_views import SessionView
from pycon_us.core.timefmt import day_heading, day_label, time_label
from pycon_us.theme import Tokens
from pycon_us.ui.badges import ToggleFavorite
from pycon_us.ui.session_rows import NoticeRow, SessionRow, TimeGutter, is_notice

logger = logging.getLogger(__name__)

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

TAB_HEIGHT = 56
"""A day tab's height in dp: the tab bar cannot grow with the text and Flet cannot read
the text scale (U16), so it is sized for the largest iOS size, as the Schedule's."""

TODAY_DOT = 6
"""The diameter of the dot that marks today's tab, in dp, as on the Schedule."""

LIST_EXTENT = 100_000
"""The highlighted day's ``cache_extent``: it builds every row, so the row's
``ScrollKey`` is registered wherever it is (D-154, F32)."""

SCROLL_EVENT_MS = 250
"""How often the highlighted day's list may report a scroll; only its end is read."""

JUMP_TRIES = 3
"""How many times the scroll to the row is asked for before it gives up."""

LANDING_S = 0.5
"""How long after its duration a scroll may take to report its end, in seconds."""


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
        reveal: The session whose row the room was opened from, if this View shows it:
            that row gets its ``ScrollKey`` and the highlight.
        lit: Whether the highlight is on.
        fade_ms: How long it fades out, through ``prefs.motion_ms()``.
        list_ref: The list's ref, for the list that scrolls to the row.
        on_scroll: Its scroll handler, which reads each scroll's end.
        head: What comes before the slots: today's "Now in this room".
    """
    items: list[ft.Control] = []
    for start, slot in _slots(views):
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
            if session.id == reveal:
                row = _lit(row, row_key(session.id), on=lit, ms=fade_ms)
            rows.append(row)
        label = time_label(start, info.zone, use_24h=use_24h)
        items.append(_slot(label, rows, divider=bool(items)))
    return ft.ListView(
        [head, *items] if head is not None else items,
        ref=list_ref,
        expand=True,
        padding=ft.Padding.only(bottom=8),
        # Only the list that scrolls needs every row built (D-154).
        cache_extent=LIST_EXTENT if list_ref is not None else None,
        scroll_interval=SCROLL_EVENT_MS,
        on_scroll=on_scroll,
    )


def _slots(views: list[SessionView]) -> list[tuple[datetime, list[SessionView]]]:
    """Group a day's views by their time group's start, as the Schedule's slots are.

    The Job Fair sits in the 10:00 slot and its row says 9:30 (DATA-11, D-41).
    """
    slots: dict[datetime, list[SessionView]] = {}
    for view in views:
        slots.setdefault(view.session.start, []).append(view)
    return list(slots.items())


def _slot(label: str, rows: list[ft.Control], *, divider: bool) -> ft.Control:
    """One time slot (D-31): the gutter beside its rows, under a divider after the first."""
    slot = ft.Row(
        [TimeGutter(label), ft.Column(rows, spacing=0, expand=True)],
        spacing=0,
        vertical_alignment=ft.CrossAxisAlignment.START,
    )
    return ft.Column([ft.Divider(height=1), slot], spacing=0) if divider else slot


def _lit(row: ft.Control, key: str, *, on: bool, ms: int) -> ft.Control:
    """Wrap the row the room was opened from: its scroll target, and its highlight.

    The box carries the ``ScrollKey`` (a plain key is never registered for
    ``scroll_to``) and the tint, which fades out in ``ms``; at 0, under reduced motion
    (D-173), the highlight simply goes.
    """
    return ft.Container(
        row,
        key=ft.ScrollKey(key),
        bgcolor=HIGHLIGHT if on else UNLIT,
        animate=ft.Animation(ms, ft.AnimationCurve.EASE_OUT) if ms else None,
    )


def day_tab(index: int, day: date, *, is_today: bool) -> ft.Tab:
    """Return a day's tab: "Fri, May 15", today with a dot, read "Friday, May 15, today".

    Flutter's tab bar adds the tab's position and its selection to what it reads.

    Args:
        index: The tab's position, in its semantics identifier ``room.day_tab.<n>``.
        day: The conference-local date.
        is_today: Mark it as today (``clock.now()`` in conference time).
    """
    spoken = f"{day_heading(day)}, today" if is_today else day_heading(day)
    label: ft.Control = ft.Text(day_label(day), semantics_label=spoken)
    if is_today:
        # Beside the text, centred on it, so it stays by the digits at every size.
        dot = ft.Container(
            width=TODAY_DOT,
            height=TODAY_DOT,
            border_radius=TODAY_DOT / 2,
            bgcolor=ft.Colors.PRIMARY,
        )
        label = ft.Row(
            [label, dot],
            spacing=4,
            tight=True,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
    return ft.Tab(
        height=TAB_HEIGHT,
        # Unlabelled: Flutter merges the identifier into the tab's node (D-166).
        label=ft.Semantics(identifier=f"{SCREEN}.day_tab.{index}", content=label),
    )


async def scroll_to_row(
    list_ref: ft.Ref[ft.ListView],
    key: str,
    *,
    duration: int,
    ended: asyncio.Event,
) -> bool:
    """Scroll the list so the row with this ``ScrollKey`` is at its top (D-155).

    Flutter answers ``scroll_to`` before the scroll runs, and does nothing for a row it
    has not built yet (F7), so the call alone proves nothing: the list's ``on_scroll``
    sets ``ended`` when a scroll ends, and without an end in time the scroll is asked
    for again, up to ``JUMP_TRIES`` times. A row already in place never scrolls, so it
    ends the same way. A list that has left the page (the user swiped to another day)
    makes Flutter time out, which Flet raises as a ``RuntimeError``: logged, and the
    row stays where it is.

    Args:
        list_ref: The day list's ref; nothing happens while it is unset.
        key: The row's ``ScrollKey`` value (``row_key()``).
        duration: The scroll's length in milliseconds, through ``prefs.motion_ms()``.
        ended: Set by the list's ``on_scroll`` when a scroll ends.

    Returns:
        Whether the list reported a scroll that ended.
    """
    for _ in range(JUMP_TRIES):
        list_view = list_ref.current
        if list_view is None:
            return False
        ended.clear()
        try:
            await list_view.scroll_to(scroll_key=ft.ScrollKey(key), duration=duration)
        except RuntimeError as error:
            if "TimeoutException" not in str(error):
                raise
            logger.warning("Room highlight: the list was not shown in time")
            return False
        try:
            await asyncio.wait_for(ended.wait(), duration / 1000 + LANDING_S)
        except TimeoutError:
            continue  # not built yet, or already in place
        return True
    return False
