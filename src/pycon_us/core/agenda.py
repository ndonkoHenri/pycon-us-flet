"""Now & Next and My schedule (#93; SCHED-25, NEW-01; D-14, D-179).

Now and My schedule ask these. Each takes ``now`` and the saved ids as arguments, so they
stay pure (D-43), and none takes the Schedule's filters (D-20). Their results are frozen
values that compare by value, so a screen that recomputes them every 60 s re-renders only
what changed (D-153). They name sessions by id, as ``TimeGroup`` does, and list a slot's
sessions in schedule order, as the Schedule does (D-178).
"""

from collections.abc import Mapping
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import StrEnum
from itertools import groupby
from operator import attrgetter

from pycon_us.core.models import ConferenceData, Day, Session
from pycon_us.core.timeline import day_slots, schedule_order

NEXT_SESSION_WINDOW = timedelta(hours=3)
"""How soon a saved session must start to be "Your next session" on Now (SCHED-25)."""


class Phase(StrEnum):
    """Where an instant falls in the conference's timeline (D-14's seasons).

    A day runs from its first start to its last end, over every session listed under it.
    Between two days, the conference-local date tells the evening from the morning, as
    ux.md §5.1 words them: "That's a wrap for today", then "First up today at 9:00 AM".

    Attributes:
        BEFORE: Before the conference's first start.
        BEFORE_DAY: Between days, on the conference-local date of the next day's first
            start: from midnight to that start.
        DAY: Within a day, between slots included.
        AFTER_DAY: Between days, on an earlier conference-local date than the next day's
            first start: from a day's last end to midnight.
        AFTER: From the conference's last end on.
    """

    BEFORE = "before"
    BEFORE_DAY = "before_day"
    DAY = "day"
    AFTER_DAY = "after_day"
    AFTER = "after"


@dataclass(frozen=True)
class NowNext:
    """What Now shows at one instant, whatever is saved.

    Attributes:
        phase: Where the instant falls in the conference.
        happening: The sessions with ``start <= now < end``, by time slot, then in
            schedule order (``schedule_order``); a notice (no duration) is never
            happening.
        next_start: The start of the first time slot after ``now``, on any day; None
            after the last one.
        up_next: That slot's sessions, in schedule order; empty when ``next_start`` is
            None.
    """

    phase: Phase
    happening: tuple[str, ...]
    next_start: datetime | None
    up_next: tuple[str, ...]


@dataclass(frozen=True)
class AgendaSlot:
    """The saved sessions of one day that start at the same instant.

    Attributes:
        start: Their shared start, as in the day's ``TimeGroup``.
        session_ids: The sessions in schedule order (``schedule_order``), as the
            Schedule lists the slot.
    """

    start: datetime
    session_ids: tuple[str, ...]


@dataclass(frozen=True)
class AgendaDay:
    """One day of My schedule.

    Attributes:
        date: The day the sessions are listed under (``Session.day``).
        slots: Its slots, by start.
    """

    date: date
    slots: tuple[AgendaSlot, ...]


@dataclass(frozen=True)
class Agenda:
    """My schedule: the saved sessions by day and time slot, and where they overlap.

    Attributes:
        days: The days with a saved session, oldest first.
        overlaps: For each saved session that overlaps another, the saved sessions it
            overlaps, in agenda order. Sessions overlap when each starts before the other
            ends, so back-to-back sessions do not, and sessions in the same place at the
            same time (the posters of one poster session) are one visit, not a clash.
    """

    days: tuple[AgendaDay, ...]
    # A dict is not hashable; leaving it out of the hash keeps ``Agenda`` hashable.
    overlaps: Mapping[str, tuple[str, ...]] = field(hash=False)


def now_next(data: ConferenceData, now: datetime) -> NowNext:
    """Return the conference's phase, what is on and what is next at ``now`` (SCHED-25).

    Only the timeline counts, in the Schedule's slots and order (unfiltered): poster
    details share the Posters row's time and would crowd it out. A slot is never
    happening once it has ended, which Ionic got wrong (it kept the last slot that had
    started until midnight).

    Args:
        data: The processed feed.
        now: An aware instant, in any zone.

    Returns:
        The phase, the sessions happening now and the next time slot.

    Raises:
        ValueError: ``now`` is naive.
    """
    _require_aware(now)
    slots = [slot for day in data.days for slot in day_slots(data, day.date)]
    happening = tuple(
        session.id
        for slot in slots
        if slot.start <= now
        for session in slot.sessions
        if now < session.end
    )
    upcoming = next((slot for slot in slots if slot.start > now), None)
    if upcoming is None:
        return NowNext(_phase(data, now), happening, None, ())
    up_next = tuple(session.id for session in upcoming.sessions)
    return NowNext(_phase(data, now), happening, upcoming.start, up_next)


def next_for_me(
    data: ConferenceData, favorites: AbstractSet[str], now: datetime
) -> str | None:
    """Return "Your next session": the saved session to go to next, else the one that is on.

    That is the first saved session that starts after ``now`` and within
    ``NEXT_SESSION_WINDOW``; when none does, the saved session that is on and started
    last. A session that is on never hides the next one: a saved summit or tutorial runs
    for hours, and the talk after it is what the attendee has to walk to. Poster details
    count, since they can be saved. Saved ids that are not in the feed are ignored.

    Args:
        data: The processed feed.
        favorites: The saved session ids (``Favorites.ids``, D-172).
        now: An aware instant, in any zone.

    Returns:
        The session's id, or None when no saved session is on or due within the window.

    Raises:
        ValueError: ``now`` is naive.
    """
    _require_aware(now)
    saved = sorted(_saved(data, favorites), key=_agenda_order)
    upcoming = [s for s in saved if now < s.start <= now + NEXT_SESSION_WINDOW]
    if upcoming:
        return upcoming[0].id
    ongoing = [s for s in saved if s.start <= now < s.end]
    # ``max`` keeps the first of equal starts, so a tie goes to the agenda's order.
    return max(ongoing, key=attrgetter("start")).id if ongoing else None


def my_schedule(data: ConferenceData, favorites: AbstractSet[str]) -> Agenda:
    """Return My schedule: the saved sessions by day and slot, and their overlaps (NEW-01).

    Every saved session in the feed is listed, wherever it is (a poster detail too) and
    whatever the Schedule's filters hide (a saved open space stays). Saved ids that are
    not in the feed are left out. What has ended is the screen's to fold away, since it
    depends on ``now``.

    Args:
        data: The processed feed.
        favorites: The saved session ids (``Favorites.ids``, D-172).

    Returns:
        The agenda.
    """
    saved = sorted(_saved(data, favorites), key=_agenda_order)
    days = tuple(
        AgendaDay(
            day,
            tuple(
                AgendaSlot(start, tuple(session.id for session in slot))
                for start, slot in groupby(on_day, key=attrgetter("start"))
            ),
        )
        # Sorted by start, sessions are sorted by day too: a day is the local date of
        # its sessions' start.
        for day, on_day in groupby(saved, key=attrgetter("day"))
    )
    return Agenda(days, _overlaps(saved))


def _phase(data: ConferenceData, now: datetime) -> Phase:
    """Place ``now`` against each day's span, from its first start to its last end."""
    spans = [(day.groups[0].start, _day_end(data, day)) for day in data.days]
    if not spans or now < spans[0][0]:
        return Phase.BEFORE
    if now >= max(end for _, end in spans):
        return Phase.AFTER
    if any(start <= now < end for start, end in spans):
        return Phase.DAY
    next_start = min(start for start, _ in spans if start > now)
    # Compare dates in the conference's zone (the feed's), not in the zone of ``now``.
    if now.astimezone(next_start.tzinfo).date() == next_start.date():
        return Phase.BEFORE_DAY
    return Phase.AFTER_DAY


def _day_end(data: ConferenceData, day: Day) -> datetime:
    return max(data.sessions[i].end for group in day.groups for i in group.session_ids)


def _overlaps(saved: list[Session]) -> dict[str, tuple[str, ...]]:
    """Pair the sessions that overlap, in one sweep over ``saved``, sorted by start."""
    found: dict[str, list[str]] = {}
    # The sessions that started before the current one and have not ended at its start.
    running: list[Session] = []
    for session in saved:
        if session.end == session.start:
            continue  # an instant overlaps nothing
        running = [other for other in running if other.end > session.start]
        for other in running:
            if _same_visit(session, other):
                continue
            found.setdefault(other.id, []).append(session.id)
            found.setdefault(session.id, []).append(other.id)
        running.append(session)
    # Each list is in agenda order: the earlier sessions were added together when the
    # session itself came, then the later ones one by one as they came.
    return {session_id: tuple(ids) for session_id, ids in found.items()}


def _same_visit(a: Session, b: Session) -> bool:
    # The posters of one poster session, its Posters row and the Job Fair listed with it
    # share one hall and one time: the attendee can see them all, so they do not clash.
    return (a.location, a.start, a.end) == (b.location, b.start, b.end)


def _saved(data: ConferenceData, favorites: AbstractSet[str]) -> list[Session]:
    return [data.sessions[i] for i in favorites if i in data.sessions]


def _agenda_order(session: Session) -> tuple[datetime, tuple[object, ...]]:
    # The Schedule's order: by slot (``start``), then as the slot lists its rows. The
    # slot comes first because the Job Fair shows 9:30 but sits in the 10:00 slot.
    return session.start, schedule_order(session)


def _require_aware(now: datetime) -> None:
    if now.utcoffset() is None:
        raise ValueError(f"expected an aware datetime, got {now!r}")
