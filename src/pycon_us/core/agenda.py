"""Now & Next and My schedule (#93; SCHED-25, NEW-01; D-14, D-179).

Now and My schedule ask these. Each takes ``now`` and the saved ids as arguments, so they
stay pure (D-43), and none takes the Schedule's filters (D-20). Their results are frozen
values that compare by value, so a screen that recomputes them every 60 s re-renders only
what changed (D-153). Like the schedule queries, they hold the model's own sessions, in
the Schedule's ``Slot``s and its order (D-178, D-185): the sessions compare by identity,
so comparing two results never compares a session's fields, and a screen needs no lookup
by id.
"""

from collections.abc import Callable, Mapping
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta, tzinfo
from enum import StrEnum
from itertools import groupby
from operator import attrgetter

from pycon_us.core.models import ConferenceData, Day, Session
from pycon_us.core.timefmt import today
from pycon_us.core.timeline import Slot, day_slots, schedule_order

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
        up_next: The first time slot after ``now``, on any day: the Schedule's own
            ``Slot`` (unfiltered), whose ``start`` Now names; None after the last one.
            Its ``key`` has an item in the Schedule only when the filter keeps the
            slot on the shown day (D-155, D-185); otherwise scroll to
            ``now_place()``'s target over that day's filtered slots (D-204).
    """

    phase: Phase
    happening: tuple[Session, ...]
    up_next: Slot | None


@dataclass(frozen=True)
class AgendaDay:
    """One day of My schedule: a day of slots, where ``DaySessions`` is a flat day.

    Attributes:
        day: The day the sessions are listed under (``Session.day``).
        slots: Its slots, by start, each holding only saved sessions, in schedule order;
            a slot's ``key`` is the Schedule's slot's at that start.
    """

    day: date
    slots: tuple[Slot, ...]


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
    overlaps: Mapping[Session, tuple[Session, ...]] = field(hash=False)

    @property
    def sessions(self) -> tuple[Session, ...]:
        """Every saved session the agenda holds, in agenda order: what an export takes."""
        return tuple(
            session
            for day in self.days
            for slot in day.slots
            for session in slot.sessions
        )


@dataclass(frozen=True)
class FoldedAgenda:
    """My schedule at one instant: what has ended, folded away, and what is to come.

    Attributes:
        earlier_days: The days before today, whole: they fold into one tile at the top.
        earlier_today: Today's sessions that have ended, by slot, folded under today's
            header; None when none has.
        ahead: Today's other sessions, then the later days.
        overlaps: The clashes that can still change a plan: for each session ahead,
            the saved sessions it overlaps that have not ended, in agenda order. A
            folded row has none, and a session ahead with only ended clashes is left
            out.
    """

    earlier_days: tuple[AgendaDay, ...]
    earlier_today: AgendaDay | None
    ahead: tuple[AgendaDay, ...]
    # As Agenda's: a dict is not hashable.
    overlaps: Mapping[Session, tuple[Session, ...]] = field(hash=False)


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
        session
        for slot in slots
        if slot.start <= now
        for session in slot.sessions
        if now < session.end
    )
    up_next = next((slot for slot in slots if slot.start > now), None)
    return NowNext(_phase(data, now), happening, up_next)


def next_for_me(
    data: ConferenceData, favorites: AbstractSet[str], now: datetime
) -> Session | None:
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
        The session, or None when no saved session is on or due within the window.

    Raises:
        ValueError: ``now`` is naive.
    """
    _require_aware(now)
    saved = sorted(_saved(data, favorites), key=_agenda_order)
    upcoming = [s for s in saved if now < s.start <= now + NEXT_SESSION_WINDOW]
    if upcoming:
        return upcoming[0]
    ongoing = [s for s in saved if s.start <= now < s.end]
    # ``max`` keeps the first of equal starts, so a tie goes to the agenda's order.
    return max(ongoing, key=attrgetter("start")) if ongoing else None


def elapsed_percent(session: Session, now: datetime) -> int:
    """Return how much of a session has passed at ``now``, in whole percent (SCHED-25).

    Counted over the time its row shows, from ``display_start`` to ``end``: the Job
    Fair's row says 9:30, though it is happening only from its 10:00 slot (DATA-11), so
    at 10:00 its bar already stands at a seventh. Rounded down, so a session that is on
    reads 0 to 99 and never "100 percent" before its end: 0 before it starts, 100 from
    its end on; a session without a duration (a notice) is 0 before it, 100 after.

    Args:
        session: A session of the model.
        now: An aware instant, in any zone.

    Returns:
        The share of the session that has passed, from 0 to 100.

    Raises:
        ValueError: ``now`` is naive.
    """
    _require_aware(now)
    # In UTC: datetimes sharing a ZoneInfo compare and subtract by wall clock, ignoring
    # ``fold``, which is wrong for a session across the end of summer time (#513).
    now, start, end = (
        moment.astimezone(UTC) for moment in (now, session.display_start, session.end)
    )
    if now >= end:
        return 100
    if now <= start:
        return 0
    # Whole timedeltas floor-divided: a float share would make 29 percent 28.999….
    return (now - start) * 100 // (end - start)


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
                Slot(start, tuple(slot))
                for start, slot in groupby(on_day, key=attrgetter("start"))
            ),
        )
        # Sorted by start, sessions are sorted by day too: a day is the local date of
        # its sessions' start.
        for day, on_day in groupby(saved, key=attrgetter("day"))
    )
    return Agenda(days, _overlaps(saved))


def fold_ended(agenda: Agenda, now: datetime, zone: tzinfo) -> FoldedAgenda:
    """Split My schedule at ``now`` into what has ended and what is to come (ux.md §5.6).

    A day before today has ended whole. Today, a session has ended when ``end <= now``,
    the half-open rule of ``now_next``: a talk that ends at 10:30 is over at 10:30. A
    slot whose sessions end at different times splits, so a three-hour tutorial stays
    while the talk saved beside it folds. A clash is kept only between a session ahead
    and one that has not ended: a warning about the past asks for nothing. The result
    compares by value, so a screen that folds every minute gets an equal answer until a
    session ends.

    Args:
        agenda: ``my_schedule()``'s answer.
        now: An aware instant, in any zone.
        zone: The conference's zone, whose date is "today" (D-43).

    Returns:
        The folded agenda; before the conference nothing has ended, and after it
        everything has.

    Raises:
        ValueError: ``now`` is naive.
    """
    _require_aware(now)
    day = today(now, zone)
    earlier_today: AgendaDay | None = None
    ahead: list[AgendaDay] = []
    for agenda_day in agenda.days:
        if agenda_day.day > day:
            ahead.append(agenda_day)
        elif agenda_day.day == day:
            ended = _slots_where(agenda_day, lambda session: session.end <= now)
            to_come = _slots_where(agenda_day, lambda session: now < session.end)
            earlier_today = AgendaDay(day, ended) if ended else None
            if to_come:
                ahead.append(AgendaDay(day, to_come))
    earlier_days = tuple(d for d in agenda.days if d.day < day)
    on_or_next = {s for d in ahead for slot in d.slots for s in slot.sessions}
    overlaps = {
        session: live
        for session, others in agenda.overlaps.items()
        if session in on_or_next and (live := tuple(o for o in others if now < o.end))
    }
    return FoldedAgenda(earlier_days, earlier_today, tuple(ahead), overlaps)


def _slots_where(day: AgendaDay, keep: Callable[[Session], bool]) -> tuple[Slot, ...]:
    """Return a day's slots with only the sessions ``keep`` accepts; empty slots go."""
    slots = (
        Slot(slot.start, tuple(s for s in slot.sessions if keep(s)))
        for slot in day.slots
    )
    return tuple(slot for slot in slots if slot.sessions)


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


def _overlaps(saved: list[Session]) -> dict[Session, tuple[Session, ...]]:
    """Pair the sessions that overlap, in one sweep over ``saved``, sorted by start."""
    found: dict[Session, list[Session]] = {}
    # The sessions that started before the current one and have not ended at its start.
    running: list[Session] = []
    for session in saved:
        if session.end == session.start:
            continue  # an instant overlaps nothing
        running = [other for other in running if other.end > session.start]
        for other in running:
            if _same_visit(session, other):
                continue
            found.setdefault(other, []).append(session)
            found.setdefault(session, []).append(other)
        running.append(session)
    # Each list is in agenda order: the earlier sessions were added together when the
    # session itself came, then the later ones one by one as they came.
    return {session: tuple(others) for session, others in found.items()}


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
