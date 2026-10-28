"""The in-app reminder Banner: a saved session starts soon (D-60's interim, NEW-05).

Where the OS does not remind, the app says it itself while it is open: from
``BANNER_LEAD`` before a saved session's shown start, a top ``Banner`` "Typing deep dive
starts in 9 min · Room 103ABC" with Dismiss and Open (ux.md §6.9, architecture §14.2).
``App`` holds its one ``ft.use_dialog`` slot through ``use_reminder_banner()``.

What it shows is ``due_session()``'s answer, which is pure, asked again every
``TICK_SECONDS`` while the app is in the foreground (``Services.run_every``, D-175), so
the minutes count down; and at once when the favourites, the feed or the settings
change in the foreground, so a session unsaved or removed goes without waiting for the
tick. ``os_reminds()`` hides it while the OS shows the saved sessions' reminders
itself: E3 schedules them, the OS shows the app's notifications and session reminders
are on (D-396). Dismiss and Open remember the session until the app restarts; the
Banner then closes by re-render, never by ``page.pop_dialog()``, which could close a
newer dialog. It is the app's, not a View's: navigating keeps it (Flutter's
``ScaffoldMessenger`` sits above the Views).
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import ceil
from typing import cast

import flet as ft

from pycon_us import clock
from pycon_us.core.models import ConferenceData
from pycon_us.core.timefmt import instant
from pycon_us.favorites import Favorites
from pycon_us.locations import drill_href
from pycon_us.prefs import Prefs
from pycon_us.reminder_settings import ReminderSettings
from pycon_us.services import Services
from pycon_us.services.errors import report_errors
from pycon_us.services.reminders import SESSION_VIEW, Scheduler
from pycon_us.state import Conference
from pycon_us.ui.semantics import named
from pycon_us.ui.status_strip import TICK_SECONDS

BANNER_LEAD = timedelta(minutes=10)
"""How long before a saved session's shown start the in-app Banner appears (D-60)."""

SCREEN = "reminder"
"""The Banner's name in the identifiers (decisions §M)."""


@dataclass(frozen=True)
class DueSession:
    """A saved session the in-app Banner announces (``due_session()``).

    Compared by value, so a tick that finds the same session at the same minute
    changes no state and renders nothing.

    Attributes:
        id: The session's id (D-42).
        name: The session's name.
        minutes: Whole minutes until its shown start, rounded up: 1 to 10.
        location: Where it is (``display_location``); empty when the feed says nowhere.
        route: What Open lands on: the session over My schedule.
    """

    id: str
    name: str
    minutes: int
    location: str
    route: str

    @property
    def text(self) -> str:
        """The Banner's words: "Typing deep dive starts in 9 min · Room 103ABC"."""
        text = f"{self.name} starts in {self.minutes} min"
        return f"{text} · {self.location}" if self.location else text


def due_session(
    data: ConferenceData,
    favorites: Iterable[str],
    now: datetime,
    dismissed: Iterable[str] = (),
) -> DueSession | None:
    """Return the saved session starting within ``BANNER_LEAD``, if any (D-60).

    A session counts from ``BANNER_LEAD`` before the start the app shows until that
    start: an unsaved session, one no longer in the feed, one that has started and one
    the user dismissed or opened from the Banner never do. Of several, the soonest
    wins, then the lowest id, so the same inputs always give the same answer.

    Args:
        data: The processed feed.
        favorites: The saved session ids (My schedule).
        now: The current time (``clock.now()``); aware.
        dismissed: The ids the Banner was dismissed or opened for, this app session.

    Returns:
        The session to announce, with its minutes to go, or None.
    """
    skipped = set(dismissed)
    due = [
        session
        for session_id in favorites
        if session_id not in skipped
        and (session := data.sessions.get(session_id)) is not None
        and instant(session.display_start) - BANNER_LEAD
        <= instant(now)
        < instant(session.display_start)
    ]
    if not due:
        return None
    session = min(due, key=lambda s: (instant(s.display_start), s.id))
    return DueSession(
        id=session.id,
        name=session.name,
        minutes=ceil(
            (instant(session.display_start) - instant(now)) / timedelta(minutes=1)
        ),
        location=session.display_location,
        route=drill_href(SESSION_VIEW, "session", session.id),
    )


def os_reminds(scheduler: Scheduler | None, settings: ReminderSettings) -> bool:
    """Return whether the OS reminds of the saved sessions, so the Banner need not (D-396).

    It does when E3 schedules the reminders (a ``Scheduler``), the OS shows the app's
    notifications (``Scheduler.enabled``) and session reminders are on. Otherwise,
    in the companion app, with notifications denied or session reminders off, the
    Banner keeps D-60's interim while the app is open.

    Args:
        scheduler: The session's ``Scheduler``, None without E3.
        settings: The reminder settings (``Prefs.reminders``).
    """
    return scheduler is not None and scheduler.enabled and settings.session_lead > 0


def use_reminder_banner(
    svc: Services,
    conference: Conference,
    favorites: Favorites,
    prefs: Prefs,
    *,
    ready: bool,
) -> None:
    """Show the reminder Banner while a saved session is about to start (a hook, D-70).

    Call it on every render, before any early return. It subscribes to nothing that
    re-renders its component: the stores' changes and the minute tick each ask
    ``due_session()`` again, unless ``os_reminds()``, and only a different answer
    sets the state.

    Args:
        svc: The session's services: the foreground ticks and the ``Scheduler``.
        conference: The session's ``Conference`` store: the feed.
        favorites: The session's ``Favorites`` store: My schedule.
        prefs: The session's ``Prefs`` store: the reminder settings.
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
            if data is None or os_reminds(svc.reminders, prefs.reminders)
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
            for store in (conference, favorites, prefs)
        ]
        try:
            await svc.run_every(TICK_SECONDS, check)
        finally:
            for stop in stops:
                stop()

    ft.use_effect(keep_up, [])

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
