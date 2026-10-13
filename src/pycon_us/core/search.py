"""Global search over the processed feed: the index and the matching (D-46, D-180).

``search_index()`` is built once per feed version over what ``queries.fold`` has folded:
each session's ``search_text`` (its title, its description's text from ``html_md`` and its
speakers' names, never markup; D-140), the speaker directory's names and the rooms' names.
``search()`` folds a query the same way and keeps the entries that hold every one of its
words, grouped by type and day. Screens never fold or match on their own (NEW-02, #97).
"""

import logging
import time
from dataclasses import dataclass
from datetime import date, datetime
from itertools import groupby

from pycon_us.core.models import ConferenceData, Room, Session, Speaker
from pycon_us.core.queries import fold

logger = logging.getLogger(__name__)

SCOPES = ("all", "sessions", "speakers", "rooms")
"""Search's scopes in P1, in the order of its chips (D-19); P2 adds sponsors and places."""


@dataclass(frozen=True, eq=False)
class SearchIndex:
    """What search scans, built once per feed version (D-180).

    Each entry pairs a folded text with what it finds, already in the order results show.

    Attributes:
        sessions: Every session with its ``search_text``, by day, then as the timeline
            orders a day.
        speakers: The speaker directory with each folded name, by folded name.
        rooms: The rooms with each folded name, in natural order (D-125).
    """

    sessions: tuple[tuple[str, Session], ...]
    speakers: tuple[tuple[str, Speaker], ...]
    rooms: tuple[tuple[str, Room], ...]


@dataclass(frozen=True)
class DaySessions:
    """The sessions of one day that match a search.

    Attributes:
        day: The conference-local date the sessions are listed under.
        sessions: The matches, in timeline order; never empty.
    """

    day: date
    sessions: tuple[Session, ...]


@dataclass(frozen=True)
class SearchResults:
    """What a search found, grouped by type, in the order the screen shows it (D-180).

    Equal results hold the same model objects, which compare by identity, so a memoised
    result list (D-153) can skip a keystroke that changes nothing.

    Attributes:
        sessions: The matching sessions by day, oldest day first.
        speakers: The matching speakers, by folded name.
        rooms: The matching rooms, in natural order.
    """

    sessions: tuple[DaySessions, ...] = ()
    speakers: tuple[Speaker, ...] = ()
    rooms: tuple[Room, ...] = ()

    @property
    def session_count(self) -> int:
        """How many sessions matched, over all days."""
        return sum(len(day.sessions) for day in self.sessions)


def search_index(data: ConferenceData) -> SearchIndex:
    """Return the index that ``search()`` scans, and log how long building it took.

    Build it once per feed version, never per keystroke. Every session is in it, poster
    details and collapsed rows included, and the Schedule's filters play no part (D-20).

    Args:
        data: The processed feed.

    Returns:
        The index, its entries in result order.
    """
    started = time.perf_counter()
    sessions = sorted(data.sessions.values(), key=_timeline_order)
    speakers = sorted(((fold(s.name), s) for s in data.speakers.values()), key=_by_name)
    index = SearchIndex(
        sessions=tuple((s.search_text, s) for s in sessions),
        speakers=tuple(speakers),
        rooms=tuple((fold(room.name), room) for room in data.rooms.values()),
    )
    logger.info(
        "Search index built in %.1f ms: %d sessions, %d speakers, %d rooms",
        (time.perf_counter() - started) * 1000,
        len(index.sessions),
        len(index.speakers),
        len(index.rooms),
    )
    return index


def search(index: SearchIndex, query: str, scope: str = "all") -> SearchResults:
    """Return what every word of ``query`` finds, over all days (D-46, NEW-02).

    The query is folded like the index and split on whitespace; an entry matches when
    each word occurs anywhere in its text (AND), so the results narrow as the user types,
    and ``async`` finds ``asyncio``. An empty or blank query finds nothing.

    Args:
        index: The index of the shown feed version.
        query: What the user typed.
        scope: One of ``SCOPES``; ``all`` searches every type.

    Returns:
        Sessions by day, then speakers, then rooms; types outside the scope are empty.

    Raises:
        ValueError: ``scope`` is not one of ``SCOPES``.
    """
    if scope not in SCOPES:
        raise ValueError(f"Unknown search scope {scope!r}; expected one of {SCOPES}")
    words = fold(query).split()
    if not words:
        return SearchResults()

    def found[T](entries: tuple[tuple[str, T], ...], kind: str) -> list[T]:
        if scope not in ("all", kind):
            return []
        return [item for text, item in entries if all(w in text for w in words)]

    by_day = groupby(found(index.sessions, "sessions"), key=lambda s: s.day)
    return SearchResults(
        sessions=tuple(DaySessions(day, tuple(group)) for day, group in by_day),
        speakers=tuple(found(index.speakers, "speakers")),
        rooms=tuple(found(index.rooms, "rooms")),
    )


def _timeline_order(session: Session) -> tuple[date, datetime, str, str, str]:
    """The Schedule's order: by day and start, then location and name (D-31, DATA-13).

    Poster details, which no time group lists, take their place by the Posters row's
    start; the id breaks the remaining ties, so the order never depends on the feed's.
    """
    return (session.day, session.start, session.location, session.name, session.id)


def _by_name(entry: tuple[str, Speaker]) -> tuple[str, str]:
    folded, speaker = entry
    return folded, speaker.id
