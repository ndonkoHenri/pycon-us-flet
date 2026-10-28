"""The plan of local reminders: what to schedule, pure (D-59, D-222; NOTIF-05, NEW-05).

``plan()`` turns the feed, My schedule, the reminder settings and the conference
moments into the reminders to schedule, soonest first and at most ``MAX_PENDING``.
``services/reminders.py``'s ``Scheduler`` hands them to E3; this module imports no
extension (D-63), so the companion app and the tests use it as is.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo
from zlib import crc32

from pycon_us.core.models import ConferenceData, Session
from pycon_us.core.timefmt import instant, time_label
from pycon_us.locations import drill_href
from pycon_us.reminder_settings import ReminderSettings
from pycon_us.year_moments import EventReminder

MAX_PENDING = 60
"""The most reminders a plan holds: iOS keeps 64 pending and drops the soonest beyond
that, so the app never hands it more (D-222)."""

SYNTHETIC_BASE = 1_000_000
"""Where the ids of sessions without a numeric id start: 1,000,000 + crc32 % 1,000,000,
clear of the conference keys, the open spaces (9000 + key) and the moments (D-59)."""

SESSION_VIEW = "/my-schedule"
"""The View a session reminder opens its session on: it is there because it is saved."""


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
