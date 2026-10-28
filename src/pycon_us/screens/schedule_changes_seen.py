"""Schedule changes' seen marks: the unseen dot, the timer and Mark all as seen (ux.md §6.4).

NEW-04. An item of an unseen batch has a 6 dp ``primary`` dot beside its icon and its
sentence starts with "New: " (``item_phrase()``). The list marks the batches it shows
seen once it has shown them 2 s as the top View (``use_seen_marks()``), which also
clears Now's card; left sooner, or a session pushed on it, they stay unseen. With a
screen reader on, a 2 s timer would drop "New:" while the list is still being read, so
the batches are marked when the list is left instead. The app bar's overflow has Mark all as seen, disabled with nothing unseen. The marks are
saved in the log's file (``ChangeLog.mark_seen()``), so they survive a relaunch.
"""

import asyncio

import flet as ft

from pycon_us.change_log import ChangeLog
from pycon_us.core.change_batches import Batch
from pycon_us.prefs import Prefs
from pycon_us.services.errors import report_errors
from pycon_us.services.storage import Storage
from pycon_us.ui.menus import menu_item, overflow_menu

SEEN_AFTER_S = 2.0
"""How long the list shows unseen batches before they are marked seen (ux.md §6.4)."""

MARK_ALL = "Mark all as seen"
"""The overflow item's label."""

DOT = 6
"""The unseen dot's diameter, in dp."""

FADE_MS = 200
"""The dot's fade once its batch is seen; none under reduced motion (D-173)."""


def use_seen_marks(
    change_log: ChangeLog,
    storage: Storage,
    prefs: Prefs,
    closed: asyncio.Event,
    shown: tuple[Batch, ...],
) -> None:
    """Mark the unseen batches the list shows seen: after 2 s, or on leaving.

    A plain function that calls hooks, so the screen calls it once per render, before
    any early return (D-70). The list shows batches only while it is the top View: a
    session pushed on it, or a deep link to one beneath it, keeps it mounted unseen
    (``is_top_view()``), so the screen passes none then. The wait restarts when the
    batches shown change (a refresh records one, a View is pushed or popped) or the
    screen reader is turned on or off, and stops when the list is left: Flet cancels
    the effect's task first. With a screen reader on there is no wait: the batches the
    list showed are marked when it is left, by a push or an unmount. Nothing is marked
    once the session has closed (D-147): its log is stale.

    Args:
        change_log: The session's ``ChangeLog``.
        storage: Where the log is kept.
        prefs: The ``Prefs`` store, read for ``screen_reader``.
        closed: ``Services.closed``, set when a new session replaced this one.
        shown: The unseen batches the list shows; none while it is not the top View,
            or shows no log (the not-found state).
    """
    showing = ft.use_ref(shown)  # what the list showed last, for a reader's marks
    reader = prefs.screen_reader

    @report_errors
    async def after_a_while() -> None:
        left, showing.current = showing.current, shown
        if reader:
            if not shown:  # pushed under a session: the reader left the list
                _mark(change_log, storage, closed, left)
            return
        if not shown:
            return
        await asyncio.sleep(SEEN_AFTER_S)
        if not prefs.screen_reader:  # turned on meanwhile: the list is still read
            _mark(change_log, storage, closed, shown)

    @report_errors
    def on_leaving() -> None:
        if prefs.screen_reader:
            _mark(change_log, storage, closed, showing.current)

    ft.use_effect(after_a_while, [shown, reader])
    ft.on_unmounted(on_leaving)


def _mark(
    change_log: ChangeLog,
    storage: Storage,
    closed: asyncio.Event,
    batches: tuple[Batch, ...] | None,
) -> None:
    """Mark ``batches`` seen, unless none or the session has closed (D-147)."""
    if batches and not closed.is_set():
        change_log.mark_seen(storage, batches)


def mark_all_menu(
    change_log: ChangeLog, storage: Storage, *, screen: str
) -> ft.Control:
    """Return the app bar's overflow with Mark all as seen, disabled with nothing unseen.

    Disabled in place rather than left out, so the button keeps its node (D-225).

    Args:
        change_log: The session's ``ChangeLog``.
        storage: Where the log is kept.
        screen: The screen's name in identifiers: the menu is ``<screen>.overflow``
            and the item ``<screen>.mark_all``.
    """

    @report_errors
    def mark_all() -> None:
        change_log.mark_seen(storage)

    item = menu_item(
        ft.Icons.DONE_ALL,
        MARK_ALL,
        mark_all,
        identifier=f"{screen}.mark_all",
        disabled=not change_log.has_unseen,
    )
    return overflow_menu(f"{screen}.overflow", [item])


def with_dot(icon: ft.Control, *, unseen: bool, fade_ms: int) -> ft.Control:
    """Return an item's leading icon with the unseen dot at its top end.

    Decorative: the sentence says "New: " instead. The dot stays in the tree and fades
    out once its batch is seen, so the row never moves.

    Args:
        icon: The item's kind icon.
        unseen: Whether the item's batch is unseen.
        fade_ms: The fade's length, ``prefs.motion_ms(FADE_MS)``.
    """
    dot = ft.Container(
        width=DOT,
        height=DOT,
        border_radius=DOT / 2,
        bgcolor=ft.Colors.PRIMARY,
        opacity=1.0 if unseen else 0.0,
        animate_opacity=fade_ms or None,
        top=0,
        right=0,
    )
    return ft.Stack([icon, dot], width=24, height=24)
