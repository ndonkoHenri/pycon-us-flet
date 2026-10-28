"""Local reminders: the pure plan of what to schedule (D-59, D-221, D-222; NOTIF-05, NEW-05).

``plan()`` turns the feed, My schedule, the reminder settings and the conference
moments into the reminders to schedule, soonest first and at most ``MAX_PENDING``. It is
pure. ``Scheduler.apply()`` schedules it with E3, cancelling only what is pending, at
every start and resume and whenever its inputs change (D-222, D-389); ``start()`` builds
the session's ``Scheduler`` when the build has E3, and only this module imports the
extension (D-63). Without it, as in the companion app, there is no ``Scheduler`` and the
interim applies (D-60).

A reminder's route is its payload, and a tap opens it (D-21, D-396): the ``Scheduler``
holds a tap that comes before the app routes, the one that launched the app included,
for ``routes.Start``, and navigates to a later one at once. It also knows whether the OS
shows the app's notifications, which the in-app Banner's rule reads
(``ui.reminder_banner``).
"""

import asyncio
import logging
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, tzinfo
from typing import TYPE_CHECKING
from zlib import crc32

import flet as ft

from pycon_us import capabilities
from pycon_us.core.models import ConferenceData, Session
from pycon_us.core.timefmt import instant, time_label
from pycon_us.locations import drill_href
from pycon_us.reminder_settings import ReminderSettings
from pycon_us.year_moments import EventReminder

if TYPE_CHECKING:  # imported only when the build has them (D-63)
    from flet_notifications import NotificationEvent, Notifications
    from flet_permission_handler import PermissionHandler

logger = logging.getLogger(__name__)

MAX_PENDING = 60
"""The most reminders a plan holds: iOS keeps 64 pending and drops the soonest beyond
that, so the app never hands it more (D-222)."""

SYNTHETIC_BASE = 1_000_000
"""Where the ids of sessions without a numeric id start: 1,000,000 + crc32 % 1,000,000,
clear of the conference keys, the open spaces (9000 + key) and the moments (D-59)."""

SESSION_VIEW = "/my-schedule"
"""The View a session reminder opens its session on: it is there because it is saved."""

LAUNCH_WAIT = 3.0
"""Seconds the start waits at most for E3 to answer (``Scheduler.read_enabled()``),
which it does only once it has handed over the tap that launched the app (F246)."""


@dataclass(frozen=True)
class Reminder:
    """One local notification to schedule.

    Attributes:
        id: Its notification id, the same at every plan (D-59): ``reminder_id()`` for a
            saved session, the moment's for a conference moment.
        at: When it fires; aware.
        title: The notification's title.
        body: The notification's text.
        route: What a tap opens, e.g. ``/my-schedule/session/142``.
    """

    id: int
    at: datetime
    title: str
    body: str
    route: str


def reminder_id(session_id: str) -> int:
    """Return the notification id of a saved session's reminder (D-59).

    Args:
        session_id: The session's id (D-42).

    Returns:
        The id itself when it is a number, as a slot's conference key and an open
        space's are; else ``SYNTHETIC_BASE`` plus its CRC-32 modulo 1,000,000, for a
        poster detail or a collapsed row. The same session always gets the same id, so
        a moved session keeps its reminder's.
    """
    if session_id.isascii() and session_id.isdigit():
        return int(session_id)
    return SYNTHETIC_BASE + crc32(session_id.encode()) % SYNTHETIC_BASE


def plan(
    data: ConferenceData,
    favorites: Iterable[str],
    settings: ReminderSettings,
    moments: Iterable[EventReminder],
    now: datetime,
    *,
    zone: tzinfo,
    use_24h: bool,
) -> list[Reminder]:
    """Return every future reminder the user asked for, soonest first, at most 60.

    A saved session still in the feed gets one ``settings.session_lead`` minutes before
    the start the app shows; a moment of a category that is on gets its own. Only what
    fires after ``now`` is kept. A saved keynote would get both its own reminder and its
    keynote moment: it gets the earlier of the two only (the moment on a tie). The
    plan is cut to the ``MAX_PENDING`` soonest (D-222); equal times go by id, so the
    same inputs always give the same plan.

    Args:
        data: The processed feed: a session no longer in it has no reminder, a moved
            one has its new time.
        favorites: The saved session ids (My schedule).
        settings: The reminder settings: the lead (0 for none) and the categories.
        moments: The conference moments: ``Content.event_reminders`` and
            ``year_moments.keynote_moments()`` of the same feed.
        now: The current time (``clock.now()``); aware.
        zone: The conference's time zone: a session reminder says its start in
            conference time, as the schedule does.
        use_24h: Whether that time is in 24-hour form.

    Returns:
        The reminders, sorted by time and then id.
    """
    wanted = [
        m
        for m in moments
        if settings.wants(m.category) and instant(m.at) > instant(now)
    ]
    saved = _session_reminders(data, favorites, settings, now, zone, use_24h=use_24h)
    # Compared and sorted as instants: reminder times are in the conference zone, where
    # they compare by wall clock and put the repeated hour first (#535).
    moment_at = {m.session_id: instant(m.at) for m in wanted if m.session_id}
    saved_at = {session_id: instant(r.at) for session_id, r in saved.items()}
    reminders = [
        r
        for session_id, r in saved.items()
        if session_id not in moment_at or instant(r.at) < moment_at[session_id]
    ]
    reminders += [
        Reminder(m.id, m.at, m.title, m.body, m.route)
        for m in wanted
        if m.session_id not in saved_at or instant(m.at) <= saved_at[m.session_id]
    ]
    return sorted(reminders, key=lambda r: (instant(r.at), r.id))[:MAX_PENDING]


def _session_reminders(
    data: ConferenceData,
    favorites: Iterable[str],
    settings: ReminderSettings,
    now: datetime,
    zone: tzinfo,
    *,
    use_24h: bool,
) -> dict[str, Reminder]:
    """Return the future reminders of the saved sessions still in the feed, by session id."""
    if not settings.session_lead:
        return {}
    lead = timedelta(minutes=settings.session_lead)
    reminders = {}
    for session_id in favorites:
        session = data.sessions.get(session_id)
        # The shown start, which the Job Fair's is earlier than its slot's (DATA-11):
        # "10 min before" is before the time the user saw.
        if session is None or instant(session.display_start) - lead <= instant(now):
            continue
        reminders[session_id] = Reminder(
            id=reminder_id(session_id),
            # In UTC, then back in the conference's zone: a wall-clock subtraction
            # is an hour off across a change (#535).
            at=(instant(session.display_start) - lead).astimezone(zone),
            title=session.name,
            body=_starts(session, zone, use_24h=use_24h),
            route=drill_href(SESSION_VIEW, "session", session_id),
        )
    return reminders


def _starts(session: Session, zone: tzinfo, *, use_24h: bool) -> str:
    """Return a session reminder's text: "Starts at 10:30 AM · Room 103ABC"."""
    text = f"Starts at {time_label(session.display_start, zone, use_24h=use_24h)}"
    if session.display_location:
        text += f" · {session.display_location}"
    return text


@dataclass(eq=False)
class Scheduler:
    """E3's scheduling for one session: one apply at a time, the newest wins (D-389).

    ``request()`` asks for the plan to be applied again; ``keep_applied()``, the loop
    of ``reminder_schedule.use_reminder_schedule()``'s effect, then reads whether exact
    alarms are allowed and applies a fresh plan. A request made while an apply runs
    stops that apply before its next call, and the loop applies the newer plan.

    It also takes the taps on the reminders (``on_tap``, D-396): one that comes before
    the app routes is held in ``tapped`` for ``routes.Start``; once ``navigate`` is
    set, a tap opens its route at once, over whatever is open (D-291).

    Attributes:
        notifications: The session's ``flet_notifications.Notifications``.
        permissions: ``flet-permission-handler``'s service, for D-220's check that its
            exact-alarm status agrees with the plugin's; None without it.
        android: Whether the app runs on Android, the one platform that restricts
            exact alarms.
        tapped: The route of a reminder tapped before the app routed, the one that
            launched it included; empty once ``take_tap()`` has taken it.
        navigate: ``page.navigate`` once the boot gate is open and the Router
            routes; None before, while taps are held.
        enabled: Whether the OS shows the app's notifications, as last read
            (``read_enabled()``): at the start and before each apply. False until
            read, or when the read fails. A read that changes it calls the
            listeners of ``watch_enabled()``.
    """

    notifications: Notifications
    permissions: PermissionHandler | None = None
    android: bool = False
    tapped: str = ""
    navigate: Callable[[str], object] | None = None
    enabled: bool = False
    _wanted: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    _on_enabled: list[Callable[[], object]] = field(default_factory=list, repr=False)

    def on_tap(self, e: NotificationEvent) -> None:
        """E3's ``on_tap``: open the tapped reminder's route, its payload (D-21)."""
        self.open_tapped(e.payload)

    def open_tapped(self, route: str | None) -> None:
        """Open a tapped reminder's route now, or hold it until the app routes.

        Args:
            route: The notification's payload: a route from ``plan()``. A payload
                that is no route (empty, or not from ``/``) opens nothing.
        """
        if not route or not route.startswith("/"):
            logger.warning("Reminders: a tap without a route: %r", route)
            return
        if self.navigate is None:
            logger.info("Reminders: a tap on %s, held for the start", route)
            self.tapped = route  # routes.Start opens it (locations.launch_target)
        else:
            logger.info("Reminders: a tap on %s, opened", route)
            self.navigate(route)

    def take_tap(self) -> str:
        """Return the held tap's route, or empty, and hold it no longer."""
        route, self.tapped = self.tapped, ""
        return route

    async def read_enabled(self, timeout: float | None = None) -> bool:
        """Read whether the OS shows the app's notifications into ``enabled``.

        E3 answers a call only once it has initialized, which hands over the tap that
        launched the app first (F246), so the start awaits this before it opens the
        boot gate: a launch tap is then held for ``routes.Start``. A failed read, or
        one slower than ``timeout``, is logged and reads as False.

        Args:
            timeout: Seconds to wait at most; None waits as long as E3 takes.

        Returns:
            The new ``enabled``.
        """
        from flet_notifications import NotificationException

        try:
            enabled = await asyncio.wait_for(
                self.notifications.are_notifications_enabled(), timeout
            )
        except (NotificationException, TimeoutError) as e:
            logger.warning("Reminders: whether notifications show is unknown: %s", e)
            enabled = False
        if bool(enabled) != self.enabled:
            self.enabled = bool(enabled)
            for listener in list(self._on_enabled):
                listener()
        return self.enabled

    def watch_enabled(self, listener: Callable[[], object]) -> Callable[[], None]:
        """Call ``listener`` whenever a read changes ``enabled``, as the Banner needs.

        A change in system settings is seen at the next read, on resume or before an
        apply, and no store changes with it (D-396).

        Args:
            listener: Called with no arguments after ``enabled`` changes.

        Returns:
            A function that stops the calls.
        """
        self._on_enabled.append(listener)
        return lambda: self._on_enabled.remove(listener)

    def request(self) -> None:
        """Ask for the plan to be applied again; a newer request supersedes one in flight."""
        self._wanted.set()

    async def keep_applied(
        self, planner: Callable[[], Sequence[Reminder] | None], closed: asyncio.Event
    ) -> None:
        """Apply ``planner()``'s plan at each request, until the session closes.

        ``Services.close()`` makes a request, so a replaced session's loop wakes and
        returns (D-147).

        Args:
            planner: Returns the plan for this moment, called after each request; or
                None when it could not plan (an error it reported), and then nothing
                is cancelled.
            closed: The session's ``Services.closed``.
        """
        while True:
            await self._wanted.wait()
            if closed.is_set():
                return
            self._wanted.clear()
            await self.read_enabled()  # for the Banner's rule (D-396)
            exact = await self.exact_allowed()  # re-read before each apply (D-221)
            reminders = planner()
            if reminders is not None:
                await self.apply(reminders, exact=exact)

    async def exact_allowed(self) -> bool:
        """Return whether Android allows exact alarms now; True elsewhere (D-221).

        The plugin's answer counts, since it is the one that schedules. When
        ``flet-permission-handler``'s ``SCHEDULE_EXACT_ALARM`` status disagrees with it,
        a warning says so (D-220). A failed check is logged and reads as False.
        """
        from flet_notifications import NotificationException

        try:
            allowed = bool(await self.notifications.can_schedule_exact_alarms())
        except (NotificationException, TimeoutError) as e:
            logger.warning("Reminders: exact alarms unknown, scheduling inexact: %s", e)
            return False
        if self.android and self.permissions is not None:
            await self._check_agreement(allowed)
        return allowed

    async def apply(self, plan: Sequence[Reminder], *, exact: bool) -> bool:
        """Cancel every pending reminder, then schedule ``plan`` (D-59, D-222).

        ``cancel_all_pending()`` leaves the reminders already shown, which
        ``cancel_all()`` would clear. Each reminder keeps its id, so a moved session's
        reminder moves. A failure is logged, never raised (D-120): a failed cancel
        still schedules, a failed reminder still schedules the rest, and an exact
        alarm Android refuses is scheduled inexact, as is the rest of the plan.

        Args:
            plan: The reminders, from ``plan()``: at most ``MAX_PENDING``.
            exact: Whether Android allows exact alarms (``exact_allowed()``).

        Returns:
            Whether the whole plan was handed to the OS: False when a newer request
            superseded it or a call failed.
        """
        from flet_notifications import (
            NotificationException,
            NotificationPermissionException,
        )

        if self._wanted.is_set():  # superseded before it began
            return False
        complete = True
        try:
            await self.notifications.cancel_all_pending()
        except (NotificationException, TimeoutError) as e:
            logger.warning("Reminders: cancelling the pending ones failed: %s", e)
            complete = False
        for reminder in plan:
            if self._wanted.is_set():  # a newer request: the loop applies its plan
                logger.info("Reminders: apply superseded by a newer one")
                return False
            try:
                try:
                    await self._schedule(reminder, exact=exact)
                except NotificationPermissionException as e:
                    if not exact:
                        raise
                    logger.warning(
                        "Reminders: exact refused, scheduling inexact: %s", e
                    )
                    exact = False
                    await self._schedule(reminder, exact=False)
            except (NotificationException, TimeoutError) as e:
                logger.warning("Reminders: %s not scheduled: %s", reminder.id, e)
                complete = False
        logger.info(
            "Reminders: a plan of %d applied, %s",
            len(plan),
            "exact" if exact else "inexact",
        )
        return complete

    async def _schedule(self, reminder: Reminder, *, exact: bool) -> None:
        """Hand one reminder to the OS; its route is the payload a tap opens (D-21)."""
        from flet_notifications import AndroidScheduleMode

        await self.notifications.schedule(
            reminder.id,
            when=reminder.at,  # aware: the instant is kept (D-43)
            title=reminder.title,
            body=reminder.body,
            payload=reminder.route,
            schedule_mode=AndroidScheduleMode.EXACT_ALLOW_WHILE_IDLE
            if exact
            else AndroidScheduleMode.INEXACT_ALLOW_WHILE_IDLE,
        )

    async def _check_agreement(self, allowed: bool) -> None:
        """Warn when the permission handler's exact-alarm status disagrees (D-220)."""
        from flet_permission_handler import Permission, PermissionStatus

        assert self.permissions is not None
        try:
            status = await self.permissions.get_status(Permission.SCHEDULE_EXACT_ALARM)
        except (RuntimeError, TimeoutError) as e:
            logger.warning("Reminders: exact-alarm status unread: %s", e)
            return
        if (status == PermissionStatus.GRANTED) != allowed:
            logger.warning(
                "Reminders: exact alarms %s by the plugin, %s by the permission handler",
                "allowed" if allowed else "refused",
                status.value if status is not None else "unknown",
            )


def start(permissions: PermissionHandler | None) -> Scheduler | None:
    """Return the session's ``Scheduler`` when the build has E3, else None (D-63).

    Call it while rendering, in the page's context: the ``Notifications`` service
    registers with the page that is current when it is built. The extension is
    imported only here, so the companion app is never sent a control its client may
    lack, and keeps the interim (D-60, F14).

    Args:
        permissions: The session's ``flet-permission-handler`` service, or None.
    """
    if not capabilities.REMINDERS:
        return None
    from flet_notifications import Notifications

    # The handler goes in with the construction: a service registers with the page as
    # it is built, and one set afterwards misses the tap that launched the app (F246).
    notifications = Notifications(on_tap=lambda e: scheduler.on_tap(e))
    scheduler = Scheduler(
        notifications,
        permissions,
        android=ft.context.page.platform == ft.PagePlatform.ANDROID,
    )
    return scheduler
