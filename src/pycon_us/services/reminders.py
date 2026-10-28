"""Local reminders: E3's scheduling of the plan (D-59, D-221, D-222; NOTIF-05, NEW-05).

``services/reminder_plan.py``'s ``plan()`` says what to schedule. ``Scheduler.apply()``
schedules it with E3, cancelling only what is pending, at every start and resume and
whenever its inputs change (D-222, D-389); ``start()`` builds the session's
``Scheduler`` when the build has E3, and only this module imports the extension (D-63).
Without it, as in the companion app, there is no ``Scheduler`` and the interim applies
(D-60).

A reminder's route is its payload, and a tap opens it (D-21, D-396): the ``Scheduler``
holds a tap that comes before the app routes, the one that launched the app included,
for ``routes.Start``, and navigates to a later one at once. It also knows whether the OS
shows the app's notifications, which the in-app Banner's rule reads
(``ui.reminder_banner``).

``Scheduler.access()`` and ``Scheduler.request_permission()`` are the notification
permission's status and request, which the primer uses (``ui/reminder_primer.py``;
D-61, D-395). ``Scheduler.schedule_test()`` schedules Developer's test reminder
(``screens/developer_reminders.py``; DEV-06, D-402).
"""

import asyncio
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

import flet as ft

from pycon_us import capabilities
from pycon_us.services.reminder_plan import Reminder

if TYPE_CHECKING:  # imported only when the build has them (D-63)
    from flet_notifications import NotificationEvent, Notifications
    from flet_permission_handler import PermissionHandler

logger = logging.getLogger(__name__)

type Access = Literal["allowed", "askable", "blocked", "unknown"]
"""Whether the OS shows the app's notifications (ux.md §4.8, D-395): it does; it may
still ask; it won't ask again (only the system settings can change that); unknown."""

_ACCESS: dict[str, Access] = {
    "granted": "allowed",
    "limited": "allowed",
    "provisional": "allowed",
    "denied": "askable",  # never asked, or the OS may ask again
    "permanentlyDenied": "blocked",
    "restricted": "blocked",
}
"""``flet-permission-handler``'s ``PermissionStatus`` values, mapped (ux.md §4.8)."""

TEST_ID = 8999
"""The Developer test reminder's notification id, outside the plan's ranges (D-59)."""

type TestResult = Literal["exact", "inexact", "failed"]
"""How ``Scheduler.schedule_test()`` scheduled the test reminder."""

LAUNCH_WAIT = 3.0
"""Seconds the start waits at most for E3 to answer (``Scheduler.read_enabled()``),
which it does only once it has handed over the tap that launched the app (F246)."""


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
            listeners of ``watch()``.
        exact: Whether exact alarms are allowed, as last read (``exact_allowed()``):
            before each apply and after ``request_exact()``. None until read, or
            when the read fails. A read that changes it calls the listeners of
            ``watch()``: Settings' Alarms & reminders card follows it (D-401).
    """

    notifications: Notifications
    permissions: PermissionHandler | None = None
    android: bool = False
    tapped: str = ""
    navigate: Callable[[str], object] | None = None
    enabled: bool = False
    exact: bool | None = None
    _wanted: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    _listeners: list[Callable[[], object]] = field(default_factory=list, repr=False)

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
            self._changed()
        return self.enabled

    def watch(self, listener: Callable[[], object]) -> Callable[[], None]:
        """Call ``listener`` whenever a read changes ``enabled`` or ``exact``.

        A change in system settings is seen at the next read, on resume or before an
        apply, and no store changes with it: the Banner (D-396) and Settings'
        Reminders section (D-401) listen.

        Args:
            listener: Called with no arguments after ``enabled`` changes.

        Returns:
            A function that stops the calls.
        """
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def _changed(self) -> None:
        """Call every listener of ``watch()``."""
        for listener in list(self._listeners):
            listener()

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
        a warning says so (D-220). A failed check is logged and reads as False. The
        answer is kept in ``exact`` (None when the check failed).
        """
        from flet_notifications import NotificationException

        try:
            allowed = bool(await self.notifications.can_schedule_exact_alarms())
        except (NotificationException, TimeoutError) as e:
            logger.warning("Reminders: exact alarms unknown, scheduling inexact: %s", e)
            self._set_exact(None)
            return False
        self._set_exact(allowed)
        if self.android and self.permissions is not None:
            await self._check_agreement(allowed)
        return allowed

    def _set_exact(self, exact: bool | None) -> None:
        """Keep the exact-alarm answer, telling the listeners when it changed."""
        if exact != self.exact:
            self.exact = exact
            self._changed()

    async def request_exact(self) -> None:
        """Open Android's Alarms & reminders page for the app, then read its answer.

        Settings' card calls it (D-221, D-401). E3's call returns once the user leaves
        that page; the new answer is read into ``exact`` and the plan applied again,
        exact when allowed. A failure is logged, never raised (D-120).
        """
        from flet_notifications import NotificationException

        try:
            await self.notifications.request_exact_alarm_permission()
        except (NotificationException, TimeoutError) as e:
            logger.warning("Reminders: the Alarms & reminders page failed: %s", e)
        await self.exact_allowed()
        self.request()

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
        from flet_notifications import NotificationException

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
                exact = await self._schedule_best(reminder, exact=exact)
            except (NotificationException, TimeoutError) as e:
                logger.warning("Reminders: %s not scheduled: %s", reminder.id, e)
                complete = False
        logger.info(
            "Reminders: a plan of %d applied, %s",
            len(plan),
            "exact" if exact else "inexact",
        )
        return complete

    async def schedule_test(self, build: Callable[[], Reminder]) -> TestResult:
        """Schedule Developer's test reminder now, exact when allowed (DEV-06, D-402).

        Outside the apply loop: the next apply's cancel removes it if it is still
        pending, which a developer tool can live with. Whether the OS shows the app's
        notifications is the caller's check (``access()``).

        Args:
            build: Returns the test reminder, ``TEST_ID``. It is called after the
                exact-alarm check, so a slow check can't leave its time in the past,
                which E3 refuses.

        Returns:
            How it was scheduled: ``"exact"``, ``"inexact"`` (Android refuses exact
            alarms, so it may come late) or ``"failed"`` (logged).
        """
        from flet_notifications import NotificationException

        try:
            exact = await self.exact_allowed()
            reminder = build()  # due from now, not from before the check
            exact = await self._schedule_best(reminder, exact=exact)
        except (NotificationException, TimeoutError) as e:
            logger.warning("Reminders: the test reminder not scheduled: %s", e)
            return "failed"
        logger.info("Reminders: a test reminder to %s scheduled", reminder.route)
        return "exact" if exact else "inexact"

    async def _schedule_best(self, reminder: Reminder, *, exact: bool) -> bool:
        """Schedule one reminder, inexact when Android refuses exact; return if exact."""
        from flet_notifications import NotificationPermissionException

        try:
            await self._schedule(reminder, exact=exact)
        except NotificationPermissionException as e:
            if not exact:
                raise
            logger.warning("Reminders: exact refused, scheduling inexact: %s", e)
            await self._schedule(reminder, exact=False)
            return False
        return exact

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

    async def access(self) -> Access:
        """Return whether the OS shows the app's notifications (ux.md §4.8, D-395).

        On Android, ``flet-permission-handler``'s ``NOTIFICATION`` status, mapped by
        ``_ACCESS``. On iOS that status always reads "denied": Flet's build template
        turns on no permission_handler macro for notifications (F17, F245). So E3's
        ``are_notifications_enabled()`` answers there, "allowed" or else "askable":
        iOS does not tell "not asked yet" from "refused", and a request after a
        refusal shows nothing and returns False. A failed read is logged and reads as
        "unknown".
        """
        from flet_notifications import NotificationException
        from flet_permission_handler import Permission

        try:
            if self.android and self.permissions is not None:
                status = await self.permissions.get_status(Permission.NOTIFICATION)
                return _ACCESS.get(status.value, "unknown") if status else "unknown"
            enabled = await self.notifications.are_notifications_enabled()
        except (NotificationException, RuntimeError, TimeoutError) as e:
            logger.warning("Reminders: notification permission unread: %s", e)
            return "unknown"
        return "allowed" if enabled else "askable"

    async def request_permission(self) -> bool:
        """Ask the OS to show the app's notifications; return whether it allows them.

        E3's request on both platforms (D-61, F17): Android 13+'s prompt, iOS's alerts
        and sounds (the app sets no badge). A failure is logged and reads as False.
        """
        from flet_notifications import NotificationException

        try:
            return bool(await self.notifications.request_permissions(badge=False))
        except (NotificationException, TimeoutError) as e:
            logger.warning("Reminders: notification permission request failed: %s", e)
            return False

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
