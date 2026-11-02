"""Two ways to Schedule changes: the Review SnackBar and the Schedule's overflow.

NEW-04, D-255, D-335. A refresh that records a batch with something other than
additions gets one floating SnackBar, "2 saved sessions changed" or "Schedule updated ·
3 changes" (``core/change_views.snackbar_text()``), whose **Review** pushes the list on
the View on top (``changes/<year>``, a drill level), so Back returns there. It keeps
the Undo SnackBar's timing: 4 s, kept for a screen reader until used or replaced
(D-184). Showing the list closes it, by any route, and so does Mark all as seen
(``close_review()``), as D-251 closes the favourites SnackBar: the page's last Review
SnackBar is held weakly, and closing it is ``open = False`` and ``update()``, never
``page.pop_dialog()``. Review on a View that already is the list only closes it.

The Schedule's overflow ("More options") holds "Schedule changes" (ux.md §5.2 item 1),
pushing ``/schedule/changes/<year>``.
"""

from collections.abc import Callable
from typing import cast
from urllib.parse import urlparse
from weakref import WeakKeyDictionary, ref

import flet as ft

from pycon_us.change_log import ChangeLog
from pycon_us.core.change_views import snackbar_text
from pycon_us.favorites import Favorites
from pycon_us.locations import drill_href
from pycon_us.prefs import Prefs
from pycon_us.services import Services, use_services
from pycon_us.services.errors import report_errors
from pycon_us.ui.menus import menu_item, overflow_menu, view_source_items
from pycon_us.ui.snack_bars import SNACK_BAR_MS, keep_while_screen_reader

REVIEW = "Review"
"""The SnackBar's one action, which pushes Schedule changes (D-255)."""

MENU_LABEL = "Schedule changes"
"""The Schedule's overflow item, the list's own title."""

_SHOWN: WeakKeyDictionary[ft.Page, ref[ft.SnackBar]] = WeakKeyDictionary()
"""The last Review SnackBar each page showed, which the list and Mark all as seen close.

Weak both ways, as the favourites one (D-251): the SnackBar holds its page (its
Review's closure, Flet's dismiss handler), and the page's dialogs own it while it shows."""


def use_review_snack_bar(
    svc: Services, change_log: ChangeLog, favorites: Favorites, prefs: Prefs
) -> None:
    """Show the Review SnackBar for each batch the change log announces (a hook, D-70).

    ``App`` calls it on every render, before the boot gate's early return. It
    subscribes to the store rather than reading it in a render, so ``App`` never
    re-renders for a batch: the listener takes the batch to announce, once
    (``ChangeLog.take_announcement()``), and shows its SnackBar; a recorded batch of
    additions only, a load and a deletion have none to take.

    Args:
        svc: The session's services: the active year, whose log the store keeps, and
            the ``SemanticsService`` that says when no screen reader is on.
        change_log: The session's ``ChangeLog`` store.
        favorites: The session's ``Favorites`` store: the saved sessions counted first.
        prefs: The session's ``Prefs`` store: a screen reader keeps the SnackBar,
            until none is on (D-356).
    """
    page = ft.context.page
    # The store keeps its listeners weakly: the listener and its disposer live here.
    held = ft.use_memo(list[object], [])

    @report_errors
    def on_change(_sender: object, field: str | None) -> None:
        if field not in ("batches", None):
            return
        batch = change_log.take_announcement()
        if batch is None:
            return
        text = snackbar_text(batch.changes, favorites.ids)
        if text is not None:
            keep = prefs.screen_reader
            bar = show_review(page, text, str(svc.storage.year), keep=keep)
            if keep:  # until no screen reader is on (D-356)
                keep_while_screen_reader(bar, svc, prefs)

    @report_errors
    async def listen() -> None:
        held[:] = [on_change, cast(ft.Observable, change_log).subscribe(on_change)]

    @report_errors
    def stop() -> None:
        if held:
            cast(Callable[[], None], held[1])()
        held.clear()

    ft.use_effect(listen, [], cleanup=stop)


def show_review(page: ft.Page, text: str, year: str, *, keep: bool) -> ft.SnackBar:
    """Show a batch's floating SnackBar, its one action Review; it replaces the last one.

    Flet's ``SnackBarControl`` removes the SnackBar showing before it shows one
    (D-251), so the next batch's, or any other, replaces it.

    Args:
        page: The session's page.
        text: What it says, ``snackbar_text()``'s words.
        year: The conference year, the list's drill id.
        keep: A screen reader is on: the SnackBar stays until it is used, replaced or
            closed (D-184).

    Returns:
        The SnackBar, showing.
    """

    @report_errors
    def review() -> None:
        location = urlparse(page.route).path.rstrip("/") or "/"
        if location.split("/")[-2:] == ["changes", year]:
            close_review(page)  # already on the list: nothing to push (D-255)
            return
        page.navigate(drill_href(location, "changes", year))

    bar = ft.SnackBar(
        content=ft.Text(text),
        action=ft.SnackBarAction(REVIEW, on_click=review),
        behavior=ft.SnackBarBehavior.FLOATING,
        duration=SNACK_BAR_MS,
        # Flutter keeps a SnackBar with an action until it is used; only a
        # screen-reader user needs that time to reach Review (D-184).
        persist=keep,
    )
    page.show_dialog(bar)
    _SHOWN[page] = ref(bar)
    return bar


def close_review(page: ft.Page) -> None:
    """Close the page's last Review SnackBar while Flet still reports it showing (D-251).

    For the list when it shows and for Mark all as seen (D-255): with a screen reader
    on, D-184 would otherwise keep "Schedule updated · Review" over the list it points
    to. Only that SnackBar, never ``page.pop_dialog()``'s top dialog; one already gone
    (Flet sets ``open`` False once it has) is not sent again.

    Args:
        page: The session's page.
    """
    shown = _SHOWN.pop(page, None)
    last = shown() if shown is not None else None
    if last is not None and last.open:
        last.open = False
        last.update()


def use_close_review() -> None:
    """Close the page's Review SnackBar once, when the calling list mounts (a hook).

    Only at the mount: a SnackBar a newer batch shows while the list is open stays
    until it is used or replaced, or Mark all as seen (D-255).
    """
    page = ft.context.page

    @report_errors
    async def close() -> None:
        close_review(page)

    ft.use_effect(close, [])


@ft.component
def ScheduleOverflow(*, source: str) -> ft.Control:
    """The Schedule's overflow ("More options"): "Schedule changes" (ux.md §5.2 item 1).

    The item pushes the list on the Schedule, ``/schedule/changes/<year>``, so Back
    returns to the Schedule (D-255).

    Args:
        source: The Schedule's ``__name__``, for View source (D-461).
    """
    page = ft.context.page
    svc = use_services()
    view_path = ft.use_view_path()

    @report_errors
    def open_changes() -> None:
        page.navigate(drill_href(view_path, "changes", str(svc.storage.year)))

    item = menu_item(
        ft.Icons.HISTORY,  # the list's empty state's icon
        MENU_LABEL,
        open_changes,
        identifier="schedule.changes",
    )
    return overflow_menu("schedule.overflow", [item, *view_source_items(svc, source)])
