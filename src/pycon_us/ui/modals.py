"""A route change first closes the open dialogs and sheets (D-291).

A warm deep link is a route change like any other (architecture §5.6), and at the pin
the dialogs, sheets and menus open over the old screen stay open over the new one
(F109): the filter sheet open on the Schedule stayed over Now after
`confcompanion://app/now`. Closing them after the new Views are in does not work either:
Flet draws each one in the top View and keeps the route it opened in that widget's
state, so a new top View draws it again without the route, and its close then closes
nothing (F109). So the route change waits: `use_modals_close_on_route_change()` puts
`close_then()` in front of the Router's own route-change handler, which closes every
open dialog and sheet, waits for Flutter to say each one has gone (or `CLOSE_WAIT`),
and only then hands the change on.

SnackBars and Banners stay (`KEPT`): they are messages, not routes (Flutter's
`ScaffoldMessenger` shows them over every page). The one exception is a SnackBar kept
for a screen reader, which goes as the route changes, without waiting, since TalkBack
would speak it again on every later screen (`close_kept_snack_bars()`, D-496). What
Python cannot close stays as Flutter leaves it, until U89: a popup menu, which Flet gives Python no handle on, and a date or time picker
(`UNCLOSABLE`), which Flet only opens; Back closes either (D-208), and a picker goes
with its View.

The rule holds for every route change, not only for links: the Router replaces
`page.on_route_change` without chaining it (`router.py:660-667`), and Flet does
not say where a route change came from. In-app navigations come from taps, which a
modal's barrier keeps off the screen below, so they meet an open modal only when a
modal navigates itself, and then it is already closing.
"""

import asyncio
import logging
from collections.abc import Callable
from typing import Any

import flet as ft

from pycon_us.services.errors import report_errors
from pycon_us.ui.snack_bars import close_kept_snack_bars

logger = logging.getLogger(__name__)

KEPT = (ft.SnackBar, ft.Banner)
"""What a route change leaves open: messages shown over every page, not routes."""

UNCLOSABLE = (ft.DatePicker, ft.TimePicker, ft.DateRangePicker)
"""What a route change cannot close: at the pin Flet's pickers open on `open = True`
and have no branch for `False` (`date_picker.dart`, `time_picker.dart`,
`date_range_picker.dart`), so waiting for one would only delay the link (F109, U89)."""

CLOSE_WAIT = 1.0
"""Seconds a route change waits for the modals it closed. A Material dialog or sheet
leaves in about 200 ms; a dismissal that never comes delays the new location by this
much, never longer."""

POLL = 0.05
"""Seconds between two looks at whether the closed modals have gone."""


def open_modals(page: ft.Page) -> list[ft.DialogControl]:
    """Return what a route change closes: the open dialogs and sheets, oldest first.

    Neither `KEPT` nor `UNCLOSABLE`. Flet keeps a page's dialogs in
    `page._dialogs` (`base_page.py`), which `show_dialog()` and
    `ft.use_dialog` both fill; there is no public list (U89).

    Args:
        page: The session's page.
    """
    dialogs = page._dialogs.controls
    return [d for d in dialogs if d.open and not isinstance(d, KEPT + UNCLOSABLE)]


async def close_modals(page: ft.Page) -> None:
    """Close the open dialogs and sheets, and wait until Flutter took them away.

    Each is closed as `page.pop_dialog()` closes the top one (`open = False`),
    but never a SnackBar, a Banner or a picker (`open_modals()`). Flet removes a
    dialog from the page's list when Flutter reports it dismissed, after its exit
    animation (`base_page.py`), which is what this waits for, at most
    `CLOSE_WAIT`.

    Args:
        page: The session's page.
    """
    closing = open_modals(page)
    if not closing:
        return
    for dialog in closing:
        dialog.open = False
        dialog.update()
    loop = asyncio.get_running_loop()
    deadline = loop.time() + CLOSE_WAIT
    dialogs = page._dialogs.controls
    while any(d is c for d in closing for c in dialogs):
        if loop.time() >= deadline:
            logger.warning("A route change went on with a modal still closing")
            return
        await asyncio.sleep(POLL)


def close_then(page: ft.Page, handler: Callable[..., Any]) -> Callable[..., Any]:
    """Return a route-change handler that closes the open modals, then calls `handler`.

    With nothing open and nothing waiting, it calls `handler` at once, as the Router
    alone would. Otherwise the change waits its turn behind a lock: while one change
    waits for its modals to go, a second one (two quick links) must not show first and
    then be covered by the first.

    Args:
        page: The session's page.
        handler: The Router's own handler, which shows the new location.
    """
    turn = asyncio.Lock()
    waiting: set[asyncio.Task[None]] = set()  # held, so no task is collected mid-wait

    @report_errors
    async def in_turn(e: ft.RouteChangeEvent) -> None:
        async with turn:
            await close_modals(page)
            handler(e)

    @report_errors
    def on_route_change(e: ft.RouteChangeEvent) -> None:
        close_kept_snack_bars(page)
        if not turn.locked() and not open_modals(page):
            handler(e)
            return
        # Its own task, which copies the context and so keeps the session's page.
        task = asyncio.get_running_loop().create_task(in_turn(e))
        waiting.add(task)
        task.add_done_callback(waiting.discard)

    on_route_change.closes_modals = True  # pyright: ignore[reportFunctionMemberAccess]
    return on_route_change


def use_modals_close_on_route_change() -> None:
    """Put `close_then()` in front of the Router's route-change handler, once.

    A hook for the screens under the Router (`AppScaffold` calls it): Flet runs a
    parent's mount effects before its children's, so the Router has set its handler
    when a screen's effect runs. Every screen asks, and only the first wraps.
    """
    page = ft.context.page

    @report_errors
    def wrap() -> None:
        handler = page.on_route_change
        if handler is None or getattr(handler, "closes_modals", False):
            return
        page.on_route_change = close_then(page, handler)

    ft.use_effect(wrap, [])
