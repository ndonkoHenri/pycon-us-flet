"""Read-only questions screens ask of the processed feed (architecture §7.5).

Queries never change the model (SCHED-17): they return new values computed from it.
"""

import unicodedata
from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from itertools import groupby
from typing import cast
from weakref import WeakKeyDictionary

from pycon_us.core.models import ConferenceData, Session
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
    every track both give ``()``. Memoised on the feed, the day and the set of excluded
    keys (D-178): the same arguments return the same tuple, a slot the filter does not
    touch is the same object as in the unfiltered day, and a filter that hides nothing
    that day returns the unfiltered tuple itself.

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
    that stands for them on the Schedule. Memoised on the feed and the track (D-178).

    Args:
        data: The processed feed.
        track: A track key (``Session.track``), e.g. ``Talk`` or ``Open Space``.

    Returns:
        The days that have sessions of the track, oldest first; ``()`` for a track
        without sessions.
    """

    def build() -> tuple[DaySessions, ...]:
        sessions = [s for s in data.sessions.values() if s.track == track]
        if any(not s.in_timeline for s in sessions):  # poster details (DATA-07)
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
