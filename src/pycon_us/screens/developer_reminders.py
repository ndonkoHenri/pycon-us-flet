"""The Developer screen's Reminders section: a test reminder in 5 s per category (DEV-06).

``TestReminders`` is one row per kind of reminder the app sends, saved sessions and the
three kinds of conference moment, in D-198's shape, with one outcome line under them
that says why a test reminder will or won't show: scheduled (exact, or inexact and maybe
late), muted (that kind is off in the reminder settings), denied (the OS doesn't show the
app's notifications) or not scheduled (the OS refused it). Without E3, as in the
companion app, the rows are disabled and say "Not available in this build" (D-63).

The reminder is ``services.reminders.TEST_ID`` (D-59), due 5 s after the real time,
never the fake clock's: the OS fires it by its own clock. Its payload is the kind's
route, so a tap opens what that kind's reminders are about (D-402).
"""

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Any

import flet as ft

from pycon_us.prefs import use_prefs
from pycon_us.reminder_settings import ReminderSettings
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.services.reminder_plan import Reminder
from pycon_us.services.reminders import TEST_ID, Access, TestResult
from pycon_us.theme import use_tokens
from pycon_us.ui.actions import NO_OUTCOME, Outcome, action_row, outcome_line

LEAD = timedelta(seconds=5)
"""How long after the tap the test reminder is due."""

UNAVAILABLE = "Not available in this build"
"""A row's second line without E3: the companion app, or a build without it."""


@dataclass(frozen=True)
class Kind:
    """A kind of reminder the app sends, as its test row shows it.

    Attributes:
        key: ``"session"``, or one of ``year_moments.CATEGORIES``.
        name: Its name in the outcome's words, e.g. "Lightning talk reminders".
        title: The row's title, a verb first.
        icon: The row's icon: the page the kind opens, as More draws it.
        place: What a tap on the reminder opens, in words.
        route: What a tap on the reminder opens: the notification's payload.
    """

    key: str
    name: str
    title: str
    icon: ft.IconData
    place: str
    route: str


KINDS = (
    Kind(
        "session",
        "Session reminders",
        "Test a session reminder",
        ft.Icons.STAR_BORDER,
        "My schedule",
        "/my-schedule",
    ),
    Kind(
        "lightning",
        "Lightning talk reminders",
        "Test a lightning talk reminder",
        ft.Icons.BOLT_OUTLINED,
        "Lightning talks",
        "/more/lightning-talks",
    ),
    Kind(
        "open_space",
        "Open space reminders",
        "Test an open space reminder",
        ft.Icons.FORUM_OUTLINED,
        "Open spaces",
        "/more/open-spaces",
    ),
    Kind(
        "keynote",
        "Keynote reminders",
        "Test a keynote reminder",
        ft.Icons.CO_PRESENT_OUTLINED,
        "Keynotes",
        "/more/keynotes",
    ),
)
"""Every kind of reminder, in Settings' order: saved sessions, then the moments."""


def muted(settings: ReminderSettings, key: str) -> bool:
    """Return whether the user turned this kind of reminder off.

    Args:
        settings: The reminder settings (``Prefs.reminders``).
        key: A ``Kind.key``.
    """
    if key == "session":
        return settings.session_lead == 0
    return not settings.wants(key)


def reminder_for(kind: Kind, now: datetime) -> Reminder:
    """Return the test reminder of ``kind``, due ``LEAD`` after ``now``.

    Args:
        kind: The kind tested.
        now: The real time, aware (never the fake clock's).
    """
    return Reminder(
        id=TEST_ID,
        at=now + LEAD,
        title=f"Test: {kind.name.lower()}",
        body=f"From Developer options. Tap to open {kind.place}.",
        route=kind.route,
    )


DENIED: dict[Access, str] = {
    "askable": "Not scheduled: this app's notifications aren't allowed yet.",
    "refused": "Not scheduled: Android refused this app's notifications.",
    "blocked": "Not scheduled: this app's notifications are off in system settings.",
    "unknown": "Not scheduled: couldn't read whether notifications are allowed.",
}
"""Why nothing was scheduled, by what the OS says of the app's notifications."""


def denied(access: Access) -> Outcome:
    """Return the outcome when the OS doesn't show the app's notifications."""
    return DENIED[access], False


def muted_outcome(kind: Kind) -> Outcome:
    """Return the outcome when the user turned ``kind`` off: nothing is scheduled."""
    return f"Not scheduled: {kind.name.lower()} are off in Settings.", False


def scheduled(kind: Kind, result: TestResult) -> Outcome:
    """Return the outcome of a test reminder handed to the OS, or refused by it.

    Args:
        kind: The kind tested.
        result: ``Scheduler.schedule_test()``'s answer.
    """
    opens = f"Tapping it opens {kind.place}."
    if result == "exact":
        return f"Scheduled: it shows in about 5 s. {opens}", True
    if result == "inexact":
        late = "Scheduled, but Alarms & reminders isn't allowed, so it may come late."
        return f"{late} {opens}", False
    return "Couldn't schedule it: the system refused. The log says why.", False


@ft.component
def TestReminders() -> ft.Control:
    """The Reminders section: a test row per kind of reminder and their outcome line."""
    svc = use_services()
    prefs = use_prefs()
    tokens = use_tokens()
    outcome, set_outcome = ft.use_state(NO_OUTCOME)
    scheduler = svc.reminders

    @report_errors
    async def test(kind: Kind) -> None:
        assert scheduler is not None  # the rows are disabled without it
        set_outcome(NO_OUTCOME)
        access = await scheduler.access()
        if access != "allowed":
            set_outcome(denied(access))
        elif muted(prefs.reminders, kind.key):
            set_outcome(muted_outcome(kind))
        else:
            result = await scheduler.schedule_test(
                lambda: reminder_for(kind, datetime.now(UTC))
            )
            set_outcome(scheduled(kind, result))

    return ft.Column(
        [
            # A partial: a coroutine function of no arguments, which Flet awaits.
            *(kind_row(kind, partial(test, kind), scheduler is None) for kind in KINDS),
            ft.Semantics(
                identifier="developer.reminder_outcome",
                live_region=True,
                visible=bool(outcome[0]),
                content=outcome_line(*outcome, tokens=tokens),
            ),
        ],
        spacing=0,
    )


def kind_row(
    kind: Kind, on_click: Callable[[], Coroutine[Any, Any, None]], unavailable: bool
) -> ft.Control:
    """Return the row that tests ``kind``: what a tap on its reminder opens, or why not.

    Args:
        kind: The kind tested.
        on_click: Schedules its test reminder.
        unavailable: The build has no E3: the row is disabled and says so.
    """
    return action_row(
        f"developer.test_reminder.{kind.key}",
        kind.icon,
        kind.title,
        UNAVAILABLE if unavailable else f"Shows in 5 s; tapping it opens {kind.place}",
        on_click,
        disabled=unavailable,
    )
