"""Global search over the processed feed: the index and the matching (D-46, D-180).

``search_index()`` is built once per feed version over what ``queries.fold`` has folded:
each session's ``search_text`` (its title, its description's text from ``html_md`` and its
speakers' names, never markup; D-140), the speaker directory's names, and the places: the
rooms' names, the venue spots' labels with what happens there (``map.toml``, D-351)
and the expo's booths by number and exhibitor (#406), and the sponsors' names and
levels (#397).
``search()`` folds a query the same way and keeps the entries that hold every one of its
words, grouped by type and day. Screens never fold or match on their own (NEW-02, #97).
``first_results()`` cuts results to each type's first rows, which is what the result
list renders until the user asks for the rest (D-218).
"""

import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import groupby
from typing import TYPE_CHECKING

from pycon_us.core.expo import BoothEntry, booth_entries, expo_booths
from pycon_us.core.models import ConferenceData, Room, Session, Speaker, Sponsor
from pycon_us.core.queries import fold, speaker_order
from pycon_us.core.timeline import DaySessions, schedule_order

if TYPE_CHECKING:  # the year data's type only: core never imports the loader (D-67)
    from pycon_us.year_map import Booth, Pin

logger = logging.getLogger(__name__)

SCOPES = ("all", "sessions", "speakers", "places", "sponsors")
"""Search's scopes, in the order of its chips (D-19, D-351)."""


@dataclass(frozen=True, eq=False)
class SearchIndex:
    """What search scans, built once per feed version (D-180).

    Each entry pairs a folded text with what it finds, already in the order results show.

    Attributes:
        sessions: Every session with its ``search_text``, by day, then in schedule
            order (``timeline.schedule_order``, D-178).
        speakers: The speaker directory with each folded name, as the Speakers list
            orders it (``queries.speaker_order``).
        rooms: The rooms with each folded name, in natural order (D-125), the
            sprint-only rooms among them (MAP-08).
        spots: The venue spots (``MapData.venue_spots()``) with each folded label and
            sublabel, in ``map.toml``'s order.
        booths: Each exhibitor at its booth, and each booth without one
            (``expo.booth_entries()``), with "booth", the number and the name folded,
            by booth number in natural order.
        sponsors: The sponsors with each folded name and level, in the Sponsors page's
            order: by level, then feed order. Never the booth, which Places finds, nor
            the description, whose mentions would bury the sponsor named (D-351).
    """

    sessions: tuple[tuple[str, Session], ...]
    speakers: tuple[tuple[str, Speaker], ...]
    rooms: tuple[tuple[str, Room], ...]
    spots: tuple[tuple[str, Pin], ...] = ()
    booths: tuple[tuple[str, BoothEntry], ...] = ()
    sponsors: tuple[tuple[str, Sponsor], ...] = ()


@dataclass(frozen=True)
class SearchResults:
    """What a search found, grouped by type, in the order the screen shows it (D-180).

    Equal results hold the same model objects, which compare by identity, so a memoised
    result list (D-153) can skip a keystroke that changes nothing.

    Attributes:
        sessions: The matching sessions by day (``timeline.DaySessions``, as the track
            pages give them), oldest day first, each day in schedule order.
        speakers: The matching speakers, by folded name, then id.
        rooms: The matching rooms, in natural order.
        spots: The matching venue spots, in ``map.toml``'s order.
        booths: The matching booths, an entry per exhibitor, by number; with the
            rooms and the spots, the places.
        sponsors: The matching sponsors, by level, then feed order.
    """

    sessions: tuple[DaySessions, ...] = ()
    speakers: tuple[Speaker, ...] = ()
    rooms: tuple[Room, ...] = ()
    spots: tuple[Pin, ...] = ()
    booths: tuple[BoothEntry, ...] = ()
    sponsors: tuple[Sponsor, ...] = ()

    @property
    def session_count(self) -> int:
        """How many sessions matched, over all days."""
        return sum(len(day.sessions) for day in self.sessions)

    @property
    def place_count(self) -> int:
        """How many places matched: rooms, venue spots and booths."""
        return len(self.rooms) + len(self.spots) + len(self.booths)

    @property
    def empty(self) -> bool:
        """Whether nothing matched, of any type."""
        return not (
            self.sessions
            or self.speakers
            or self.rooms
            or self.spots
            or self.booths
            or self.sponsors
        )


def search_index(
    data: ConferenceData, spots: Sequence[Pin] = (), booths: Sequence[Booth] = ()
) -> SearchIndex:
    """Return the index that ``search()`` scans, and log how long building it took.

    Build it once per feed version, never per keystroke. Every session is in it, poster
    details and collapsed rows included, and the Schedule's filters play no part (D-20).

    Args:
        data: The processed feed.
        spots: The year's venue spots (``MapData.venue_spots()``): a spot is found by
            its label or by what happens there ("info desk", "Promenade Lobby").
        booths: The year's booths (``MapData.booths``): an exhibitor is found at its
            booth by the number ("613", "booth 613") or its name ("socal python"),
            and so is a sponsor's booth the plan does not draw.

    Returns:
        The index, its entries in result order.
    """
    started = time.perf_counter()
    # By day, then in schedule order (D-178), as the track pages list a day: each slot's
    # sessions as the Schedule lists the slot, poster details at the Posters row's start.
    sessions = sorted(data.sessions.values(), key=lambda s: (s.day, schedule_order(s)))
    speakers = sorted(data.speakers.values(), key=speaker_order)
    index = SearchIndex(
        sessions=tuple((s.search_text, s) for s in sessions),
        speakers=tuple((fold(s.name), s) for s in speakers),
        rooms=tuple((fold(room.name), room) for room in data.rooms.values()),
        spots=tuple((fold(f"{pin.label} {pin.sublabel}"), pin) for pin in spots),
        booths=tuple(
            (fold(f"booth {entry.number} {entry.name}"), entry)
            for entry in booth_entries(expo_booths(data, booths))
        ),
        sponsors=tuple(
            (fold(f"{sponsor.name} {sponsor.level}"), sponsor)
            for level in data.sponsor_levels
            for sponsor in level.sponsors
        ),
    )
    logger.info(
        "Search index built in %.1f ms: %d sessions, %d speakers, %d rooms, %d spots, "
        "%d booths, %d sponsors",
        (time.perf_counter() - started) * 1000,
        len(index.sessions),
        len(index.speakers),
        len(index.rooms),
        len(index.spots),
        len(index.booths),
        len(index.sponsors),
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
        Sessions by day, then speakers, then places (rooms, venue spots, then
        booths), then sponsors; types outside the scope are empty.

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
        rooms=tuple(found(index.rooms, "places")),
        spots=tuple(found(index.spots, "places")),
        booths=tuple(found(index.booths, "places")),
        sponsors=tuple(found(index.sponsors, "sponsors")),
    )


def first_results(
    results: SearchResults,
    *,
    sessions: int | None,
    speakers: int | None,
    sponsors: int | None = None,
) -> SearchResults:
    """Return the first rows of each type of ``results``, every place (D-218).

    A broad query finds most of the feed ("p": 319 sessions), and rendering every row
    of it is what made its first render slow (#216), so the list shows each type's
    first rows and says how to see the rest. The cut keeps ``search()``'s order: the
    sessions are the first ``sessions`` by day, the last day shown cut short. Days the
    cut leaves whole are the same objects, and so is ``results`` when nothing is cut,
    so a memoised list (D-153) skips what did not change.

    Args:
        results: A search's results.
        sessions: How many sessions to keep, or None for all of them.
        speakers: How many speakers to keep, or None for all of them.
        sponsors: How many sponsors to keep, or None for all of them.

    Returns:
        The results' first rows, in the same order; places are never cut.

    Raises:
        ValueError: A limit is below 1: a type that matched never shows no row.
    """
    limits = (sessions, speakers, sponsors)
    if any(limit is not None and limit < 1 for limit in limits):
        raise ValueError(
            f"Limits must be at least 1: {sessions=}, {speakers=}, {sponsors=}"
        )
    days = results.sessions
    if sessions is not None and results.session_count > sessions:
        days = _first_sessions(days, sessions)
    found = _first(results.speakers, speakers)
    backers = _first(results.sponsors, sponsors)
    if (
        days is results.sessions
        and found is results.speakers
        and backers is results.sponsors
    ):
        return results
    return SearchResults(
        sessions=days,
        speakers=found,
        rooms=results.rooms,
        spots=results.spots,
        booths=results.booths,
        sponsors=backers,
    )


def _first[T](items: tuple[T, ...], count: int | None) -> tuple[T, ...]:
    """Return the first ``count`` of ``items``: ``items`` itself when none is cut."""
    return items if count is None or len(items) <= count else items[:count]


def _first_sessions(
    days: tuple[DaySessions, ...], count: int
) -> tuple[DaySessions, ...]:
    """Return the first ``count`` sessions of ``days``, the last day shown cut short."""
    kept: list[DaySessions] = []
    for day in days:
        if count <= 0:
            break
        kept.append(
            day
            if len(day.sessions) <= count
            else DaySessions(day.day, day.sessions[:count])
        )
        count -= len(day.sessions)
    return tuple(kept)
