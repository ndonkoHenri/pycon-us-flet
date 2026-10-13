"""Read-only questions screens ask of the processed feed (architecture §7.5).

Queries never change the model (SCHED-17): they return new values computed from it.
"""

import unicodedata
from collections.abc import Callable, Collection, Mapping
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import StrEnum
from itertools import groupby
from operator import attrgetter
from typing import cast
from weakref import WeakKeyDictionary

from pycon_us.core.models import ConferenceData, Day, Session
from pycon_us.core.slugs import room_sort_key


def days(data: ConferenceData, first_day: date, last_day: date) -> tuple[date, ...]:
    """Return the Schedule's days: every date of the conference, in order (DATA-17).

    The range runs from the conference's first day to its last (the sprints, which the
    feed has no sessions for), and widens to any schedule day outside it, so no session
    is ever without its day. A day's index is its position here, and it never moves while
    the feed and the year stay the same. Filters play no part (Ionic ignored them too).

    Args:
        data: The processed feed.
        first_day: The conference's first day, from ``conference.toml``.
        last_day: The conference's last day, from ``conference.toml``.

    Returns:
        The dates, one per day, oldest first.
    """
    dates = [day.date for day in data.days]
    start, end = min([first_day, *dates]), max([last_day, *dates])
    return tuple(start + timedelta(days=n) for n in range((end - start).days + 1))


def fold(text: str) -> str:
    """Return text as search compares it: accents stripped and case folded (D-46).

    So ``Cristián`` and ``CRISTIAN`` both fold to ``cristian``. Feed processing folds
    ``Session.search_text`` once; a query is folded the same way.

    Args:
        text: Any text.

    Returns:
        The NFKD decomposition without its combining marks, case folded.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


# --------------------------------------------------------------------------------------
# Schedule queries (#85; DATA-18, DATA-20, DATA-30, SCHED-17; D-20, D-31, D-178)
#
# Memoised per feed: the same feed, day and filter return the same objects, which is
# what lets the Schedule's memoised day lists, slots and rows skip work (D-153, F34).
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Slot:
    """One time slot of a day, as the Schedule lists it: one list item (D-31).

    A value: two slots with the same key and the same session objects are equal. Its
    sessions are the model's own, which compare by identity, so comparing two slots
    never compares a session's fields.

    Attributes:
        key: ``slot-<start in ISO 8601>``: the slot item's ``ScrollKey``, which Jump to
            now targets (D-155), and its key in the list.
        start: The slot's start (``TimeGroup.start``): aware, in the conference zone.
        sessions: Its rows in schedule order (``schedule_order``); never empty.
    """

    key: str
    start: datetime
    sessions: tuple[Session, ...]


@dataclass(frozen=True)
class DaySessions:
    """The sessions of one conference-local day, for a list with day headers.

    Attributes:
        day: The date.
        sessions: The day's sessions in schedule order (``schedule_order``); never empty.
    """

    day: date
    sessions: tuple[Session, ...]


def schedule_order(session: Session) -> tuple[object, ...]:
    """Return the key that orders sessions as the Schedule shows them (DATA-30, D-31).

    By the start a row shows, then by the place it shows, in natural order
    (``slugs.room_sort_key``: ``Room 102A`` before ``Room 1000``, as the printed grid
    reads), then by name and id, so ties always come out the same. A row without a place
    (a notice, a generic break) comes first in its slot.

    Args:
        session: A session of the model.

    Returns:
        A key for ``sorted``.
    """
    return (
        session.display_start,
        room_sort_key(session.display_location),
        session.name,
        session.id,
    )


def timeline(
    data: ConferenceData, day: date, excluded: Collection[str]
) -> tuple[Slot, ...]:
    """Return a day's slots for the Schedule, without the excluded tracks (DATA-18, D-20).

    The Schedule's filter applies here and nowhere else: this is the only query that
    takes ``excluded``, and only the Schedule calls it. My schedule, Now and Search never
    filter (SCHED-07, D-20).

    A session passes unless its track key is excluded (SCHED-10); a slot the filter
    empties is left out. A day without sessions (the sprint days) and a filter that hides
    every track both give ``()``; a screen tells the two empty states apart by asking for
    the unfiltered day: ``timeline(data, day, ())`` is ``()`` only when the day has no
    sessions at all (ux.md §4.6). "Jump to now" picks its key from the filtered slots,
    because a slot the filter leaves out has no item to scroll to (D-155).

    Memoised on the feed, the day and the set of excluded keys (D-178): the same
    arguments return the same tuple, a slot the filter does not touch is the same object
    as in the unfiltered day, and a filter that hides nothing that day returns the
    unfiltered tuple itself.

    Args:
        data: The processed feed.
        day: A conference-local date, e.g. one of ``days()``.
        excluded: The track keys to hide (``Prefs.excluded_tracks``); order and
            repeats do not matter.

    Returns:
        The day's slots by start, each with its rows in ``schedule_order``.

    Raises:
        TypeError: ``excluded`` is one string, not a collection of track keys.
    """
    if isinstance(excluded, str):
        raise TypeError("excluded must be a collection of track keys, not one string")
    hidden = frozenset(excluded)
    return _memoised(
        data, ("timeline", day, hidden), lambda: _without(_day_slots(data, day), hidden)
    )


def track_sessions(data: ConferenceData, track: str) -> tuple[DaySessions, ...]:
    """Return a track page's sessions, by day (DATA-20, SCHED-22).

    Every session whose track key is ``track``, in ``schedule_order`` within each day,
    whatever the Schedule's filter (a track page shows its own track, open spaces
    included). The Posters track lists its posters (DATA-07) instead of the Posters row
    that stands for them on the Schedule; until the feed publishes posters, the row
    itself is listed, so the page is never empty while the Schedule shows one. Memoised
    on the feed and the track (D-178).

    Args:
        data: The processed feed.
        track: A track key (``Session.track``), e.g. ``Talk`` or ``Open Space``.

    Returns:
        The days that have sessions of the track, oldest first; ``()`` for a track
        without sessions.
    """

    def build() -> tuple[DaySessions, ...]:
        sessions = [s for s in data.sessions.values() if s.track == track]
        details = [s for s in sessions if not s.in_timeline]  # posters (DATA-07)
        if details:
            sessions = [s for s in sessions if not _is_posters_row(s)]
        ordered = sorted(sessions, key=lambda s: (s.day, schedule_order(s)))
        return tuple(
            DaySessions(day, tuple(group))
            for day, group in groupby(ordered, key=lambda s: s.day)
        )

    return _memoised(data, ("track", track), build)


def _is_posters_row(session: Session) -> bool:
    """Whether ``session`` is the Posters row, which the poster slots collapse into."""
    return session.kind == "poster" and session.in_timeline


def _day_slots(data: ConferenceData, day: date) -> tuple[Slot, ...]:
    """Return every slot of ``day``, unfiltered, memoised per feed and day."""

    def build() -> tuple[Slot, ...]:
        for schedule_day in data.days:
            if schedule_day.date == day:
                return tuple(
                    Slot(
                        key=f"slot-{group.start.isoformat()}",
                        start=group.start,
                        sessions=tuple(
                            sorted(
                                (data.sessions[sid] for sid in group.session_ids),
                                key=schedule_order,
                            )
                        ),
                    )
                    for group in schedule_day.groups
                )
        return ()

    return _memoised(data, ("slots", day), build)


def _without(slots: tuple[Slot, ...], hidden: frozenset[str]) -> tuple[Slot, ...]:
    """Return ``slots`` without the sessions of the ``hidden`` tracks.

    Slots that lose nothing are kept as they are, so a memoised slot item sees the same
    object and skips its body; when no slot loses anything, ``slots`` itself is returned.
    """
    kept: list[Slot] = []
    changed = False
    for slot in slots:
        sessions = tuple(s for s in slot.sessions if s.track not in hidden)
        if len(sessions) == len(slot.sessions):
            kept.append(slot)
            continue
        changed = True
        if sessions:
            kept.append(Slot(slot.key, slot.start, sessions))
    return tuple(kept) if changed else slots


_MEMO: WeakKeyDictionary[ConferenceData, dict[tuple[object, ...], object]] = (
    WeakKeyDictionary()
)
"""The schedule queries' results, per feed. A processed feed is one object per feed
version (``Conference.version`` counts them), so it is the version in the key; weak, so a
replaced feed's results go with it. Only the event loop's thread calls the queries."""


def _memoised[T](
    data: ConferenceData, key: tuple[object, ...], build: Callable[[], T]
) -> T:
    """Return the value stored for ``data`` and ``key``, building and storing it once."""
    results = _MEMO.setdefault(data, {})
    if key not in results:
        results[key] = build()
    return cast(T, results[key])


# --------------------------------------------------------------------------------------
# Agenda and Now & Next (#93; SCHED-25, NEW-01; D-14, D-179)
#
# Now and My schedule ask these. Each takes ``now`` and the saved ids as arguments, so
# they stay pure (D-43), and none takes the Schedule's filters (D-20). Their results are
# frozen values that compare by value, so a screen that recomputes them every 60 s
# re-renders only what changed (D-153). They name sessions by id, as ``TimeGroup`` does,
# and list a slot's sessions in schedule order, as the Schedule does (D-178).
# --------------------------------------------------------------------------------------

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
    slots = [slot for day in data.days for slot in _day_slots(data, day.date)]
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
