"""Keep E3's reminders in step with the app: at start, on resume and on every change.

``App`` calls ``use_reminder_schedule()`` once. Its one effect, once the start has read
the settings, the favourites and the feed, asks the session's ``Scheduler`` for an
apply and runs its loop; each change of the favourites, the reminder settings, the
feed or the change log asks again, and so does ``app.on_resume()``, which brings back
what the OS dropped (D-222, D-389). A newer ask supersedes an apply in flight
(``services.reminders.Scheduler``). Without E3 (the companion app) it does nothing and
the interim applies (D-60).

``current_plan()`` is the plan at a given moment: ``services.reminders.plan()`` over the
stores, with the year's sign-up moments and the keynotes' moments of the current feed.

``use_reminder_taps()`` lets a tap on a reminder navigate once the boot gate is open;
before, the ``Scheduler`` holds it for ``routes.Start`` (D-396).
"""

from datetime import datetime
from typing import cast

import flet as ft

from pycon_us import clock
from pycon_us.change_log import ChangeLog
from pycon_us.config import YearData
from pycon_us.favorites import Favorites
from pycon_us.prefs import Prefs
from pycon_us.services import Services
from pycon_us.services.errors import report_errors
from pycon_us.services.reminders import Reminder, plan
from pycon_us.state import Conference
from pycon_us.year_moments import keynote_moments

WATCHED = frozenset({"version", "ids", "reminders", "batches"})
"""The store fields whose change asks for an apply: the feed's ``version``, the
favourites' ``ids``, the reminder settings and the change log's ``batches``. Other
changes, such as a refresh starting or the theme, leave the plan as it is."""


def current_plan(
    year: YearData,
    conference: Conference,
    favorites: Favorites,
    prefs: Prefs,
    now: datetime,
    *,
    use_24h: bool,
) -> list[Reminder]:
    """Return the reminders to schedule at ``now``: none until a feed is published.

    Args:
        year: The year's data: its zone, sign-up moments and keynote entries.
        conference: The ``Conference`` store: the feed.
        favorites: The ``Favorites`` store: My schedule.
        prefs: The ``Prefs`` store: the reminder settings.
        now: The current instant, ``clock.real_now()``: the OS fires at real
            instants, so the Developer fake clock does not apply here (D-389).
        use_24h: Whether times in the text are in 24-hour form, as the device's are.
    """
    data = conference.data
    if data is None:
        return []
    zone = year.conference.zone
    moments = (
        *year.content.event_reminders,
        *keynote_moments(data, year.content.keynotes, zone, use_24h=use_24h),
    )
    return plan(
        data,
        favorites.ids,
        prefs.reminders,
        moments,
        now,
        zone=zone,
        use_24h=use_24h,
    )


def use_reminder_schedule(
    svc: Services,
    conference: Conference,
    favorites: Favorites,
    change_log: ChangeLog,
    prefs: Prefs,
) -> None:
    """Keep the scheduled reminders those of ``current_plan()`` (a hook, D-70).

    Call it on every render, before any early return. Its effect waits for
    ``prefs.loaded``, which the start sets once the favourites and the feed are in,
    then applies at once and at each change of a ``WATCHED`` field, until the
    session closes (D-147).

    Args:
        svc: The session's services: the ``Scheduler``, None without E3.
        conference: The session's ``Conference`` store.
        favorites: The session's ``Favorites`` store.
        change_log: The session's ``ChangeLog`` store.
        prefs: The session's ``Prefs`` store.
    """
    page = ft.context.page
    scheduler = svc.reminders

    @report_errors
    def planned() -> list[Reminder]:
        # A planning error is reported and returns None: nothing is cancelled then.
        use_24h = bool(page.media and page.media.always_use_24_hour_format)
        return current_plan(
            svc.year, conference, favorites, prefs, clock.real_now(), use_24h=use_24h
        )

    @report_errors
    def on_change(_sender: object, name: str | None) -> None:
        if scheduler is not None and (name is None or name in WATCHED):
            scheduler.request()

    @report_errors
    async def keep_applied() -> None:
        if scheduler is None or not prefs.loaded:
            return
        # Held here while the loop runs: the stores keep their listeners weakly.
        stops = [
            cast(ft.Observable, store).subscribe(on_change)
            for store in (conference, favorites, change_log, prefs)
        ]
        try:
            scheduler.request()  # the start's apply
            await scheduler.keep_applied(planned, svc.closed)
        finally:
            for stop in stops:
                stop()

    ft.use_effect(keep_applied, [prefs.loaded])


def use_reminder_taps(svc: Services, *, ready: bool) -> None:
    """Let reminder taps navigate while the boot gate is open (a hook, D-70, D-396).

    Call it on every render, before any early return. Until the gate opens there is
    no Router to navigate, so the ``Scheduler`` holds a tap, the one that launched the
    app included, and ``routes.Start`` opens it in place of its own target
    (``locations.launch_target()``); from then on a tap navigates at once. Without E3
    it does nothing.

    Args:
        svc: The session's services: the ``Scheduler``, None without E3.
        ready: Whether the boot gate is open.
    """
    page = ft.context.page

    @report_errors
    def follow_gate() -> None:
        if svc.reminders is not None:
            svc.reminders.navigate = page.navigate if ready else None

    ft.use_effect(follow_gate, [ready])
