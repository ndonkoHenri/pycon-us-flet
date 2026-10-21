"""The in-app reminder Banner: a saved session starts soon (D-60's interim, NEW-05).

Until E3 schedules notifications, the app says it itself while it is open: from
``BANNER_LEAD`` before a saved session's shown start, a top ``Banner`` "Typing deep dive
starts in 9 min · Room 103ABC" with Dismiss and Open (ux.md §6.9, architecture §14.2).
``App`` holds its one ``ft.use_dialog`` slot through ``use_reminder_banner()``.

What it shows is ``services.reminders.due_session()``'s answer, asked again every
``TICK_SECONDS`` while the app is in the foreground (``Services.run_every``, D-175), so
the minutes count down; and at once when the favourites or the feed change in the
foreground, so a session unsaved or removed goes without waiting for the tick. Dismiss and Open remember
the session until the app restarts; the Banner then closes by re-render, never by
``page.pop_dialog()``, which could close a newer dialog. It is the app's, not a View's:
navigating keeps it (Flutter's ``ScaffoldMessenger`` sits above the Views).
"""

from collections.abc import Callable
from typing import cast

import flet as ft

from pycon_us import clock
from pycon_us.favorites import Favorites
from pycon_us.services import Services
from pycon_us.services.errors import report_errors
from pycon_us.services.reminders import DueSession, due_session
from pycon_us.state import Conference
from pycon_us.ui.semantics import named
from pycon_us.ui.status_strip import TICK_SECONDS, stop_ticks

SCREEN = "reminder"
"""The Banner's name in the identifiers (decisions §M)."""


def use_reminder_banner(
    svc: Services, conference: Conference, favorites: Favorites, *, ready: bool
) -> None:
    """Show the reminder Banner while a saved session is about to start (a hook, D-70).

    Call it on every render, before any early return. It subscribes to nothing that
    re-renders its component: the stores' changes and the minute tick each ask
    ``due_session()`` again, and only a different answer sets the state.

    Args:
        svc: The session's services: the foreground ticks.
        conference: The session's ``Conference`` store: the feed.
        favorites: The session's ``Favorites`` store: My schedule.
        ready: Whether the boot gate is open; nothing shows over the boot view.
    """
    page = ft.context.page
    due, set_due = ft.use_state(cast(DueSession | None, None))
    # The sessions dismissed or opened from the Banner, until the app restarts.
    dismissed = ft.use_memo(set, [])

    @report_errors
    def check() -> None:
        if not svc.foreground.is_set():  # a store change in the background (D-40)
            return
        data = conference.data
        found = (
            None
            if data is None
            else due_session(data, favorites.ids, clock.now(), dismissed)
        )
        set_due(found)  # the same session at the same minute renders nothing

    @report_errors
    def on_change(_sender: object, _field: str | None) -> None:
        check()

    @report_errors
    async def keep_up() -> None:
        # Held here while the loop runs: the stores keep their listeners weakly.
        stops = [
            cast(ft.Observable, store).subscribe(on_change)
            for store in (conference, favorites)
        ]
        try:
            await svc.run_every(TICK_SECONDS, check)
        finally:
            for stop in stops:
                stop()

    ft.use_effect(keep_up, [], cleanup=stop_ticks)

    @report_errors
    def dismiss() -> None:
        if due is not None:
            dismissed.add(due.id)
            check()

    @report_errors
    def open_session() -> None:
        if due is not None:
            dismiss()  # first: the Banner goes as the session opens
            page.navigate(due.route)

    ft.use_dialog(
        reminder_banner(due, open_session, dismiss) if ready and due else None
    )


def reminder_banner(
    due: DueSession,
    on_open: Callable[[], object],
    on_dismiss: Callable[[], object],
) -> ft.Banner:
    """Return the Banner for a session about to start (ux.md §4.5, §6.9).

    Flutter's ``MaterialBanner`` is a live region of its own, so a screen reader says
    it when it appears and as its minutes change (F118). A swipe or a screen reader's
    dismiss action counts as Dismiss.

    Args:
        due: The session, from ``due_session()``.
        on_open: Open: the session over My schedule, and the Banner goes.
        on_dismiss: Dismiss: the Banner goes until the app restarts.
    """
    return ft.Banner(
        leading=ft.Icon(ft.Icons.NOTIFICATIONS_ACTIVE_OUTLINED),
        content=ft.Semantics(identifier=f"{SCREEN}.banner", content=ft.Text(due.text)),
        actions=[
            named(f"{SCREEN}.dismiss", ft.TextButton("Dismiss", on_click=on_dismiss)),
            named(f"{SCREEN}.open", ft.TextButton("Open", on_click=on_open)),
        ],
        on_dismiss=on_dismiss,
    )
