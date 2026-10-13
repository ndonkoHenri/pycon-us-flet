"""The schedule queries: a day's slots, the track pages and schedule order (D-178).

#85; DATA-18, DATA-20, DATA-30, SCHED-17; D-20, D-31. Queries never change the model
(SCHED-17). Memoised per feed: the same feed, day and filter return the same objects,
which is what lets the Schedule's memoised day lists, slots and rows skip work (D-153,
F34).
"""

from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from itertools import groupby
from typing import cast
from weakref import WeakKeyDictionary

from pycon_us.core.models import ConferenceData, Session
from pycon_us.core.slugs import room_sort_key


@dataclass(frozen=True)
class Slot:
    """Sessions that start at the same instant: one list item with a time gutter (D-31).

    The Schedule's slots (``timeline``), Now's next slot and My schedule's slots
    (``agenda``) are all ``Slot``s. A value: two slots with the same start and the same
    session objects are equal. Its sessions are the model's own, which compare by
    identity, so comparing two slots never compares a session's fields.

    Attributes:
        start: The slot's start (``TimeGroup.start``): aware, in the conference zone.
        sessions: Its rows in schedule order (``schedule_order``); never empty.
    """

    start: datetime
    sessions: tuple[Session, ...]

    @property
    def key(self) -> str:
        """``slot-<start in ISO 8601>``: the item's ``ScrollKey`` and list key (D-155).

        Derived from the start, so the Schedule's slot and My schedule's slot at one
        start share it, and Jump to now finds either by it.
        """
        return f"slot-{self.start.isoformat()}"


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
    sessions at all (ux.md §4.6). "Jump to now" picks its target from the filtered
    slots, because a slot the filter leaves out has no item to scroll to (D-155).

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
        data, ("timeline", day, hidden), lambda: _without(day_slots(data, day), hidden)
    )


NOW_KEY = "now"
"""The now line's ``ScrollKey`` in today's Schedule list (D-202); no slot key clashes
with it, since every slot key starts with ``slot-``."""


@dataclass(frozen=True)
class NowPlace:
    """Where now falls among a day's slots: the now line and Jump to now (D-202).

    A value: two places compare equal when the line and the slot that is on are the
    same, so the Schedule can tell when its last jump still shows where now is.

    Attributes:
        line: How many slots have started: the now line sits just before
            ``slots[line]``, so 0 puts it above the first slot and ``len(slots)``
            after the last.
        on: The key of the slot that is on, else None: the last slot that has
            started, while one of its sessions has not ended (``start <= now < end``,
            Now's half-open rule, D-179). A notice has no duration, so a slot of
            notices alone is over as soon as it starts.
    """

    line: int
    on: str | None

    @property
    def target(self) -> str:
        """Where Jump to now lands: the slot that is on, else the now line.

        Between two slots, before the day's first and after its last, nothing is
        on, and the line sits just above what comes next (or ends the day), so
        landing on it shows the line and the next slot together.
        """
        return self.on or NOW_KEY


def now_place(slots: Sequence[Slot], now: datetime) -> NowPlace:
    """Return where now falls among the slots a list shows (SCHED-16, D-202).

    Only the last slot that has started can be on: a long session in an earlier
    slot (a tutorial, an open space) does not hold the jump back, since the attendee
    wants what is starting next.

    Args:
        slots: The slots the list shows (``timeline(data, day, excluded)``), so the
            target always has an item to scroll to (D-178); may be empty.
        now: The current instant (``clock.now()``), aware.

    Returns:
        The now line's index and the slot that is on.
    """
    line = sum(1 for slot in slots if slot.start <= now)  # slots come by start
    if line and any(s.end > now for s in slots[line - 1].sessions):
        return NowPlace(line, slots[line - 1].key)
    return NowPlace(line, None)


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


def day_slots(data: ConferenceData, day: date) -> tuple[Slot, ...]:
    """Return every slot of ``day``, unfiltered: what Now reads (D-179).

    The Schedule asks ``timeline`` instead, the one query that takes its filter (D-20).
    Memoised per feed and day; ``timeline`` filters these same objects.

    Args:
        data: The processed feed.
        day: A conference-local date.

    Returns:
        The day's slots by start, each with its rows in ``schedule_order``; ``()`` for
        a day without sessions.
    """

    def build() -> tuple[Slot, ...]:
        for schedule_day in data.days:
            if schedule_day.date == day:
                return tuple(
                    Slot(
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
            kept.append(Slot(slot.start, sessions))
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
