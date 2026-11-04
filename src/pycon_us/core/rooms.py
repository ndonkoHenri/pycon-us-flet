"""The rooms list the Map tab shows, and what is on in one room (ROOM-01, ROOM-02).

`room_list()` answers "where is it, and what is on there now?": every room of the feed
floor by floor, in natural order on each, with the sessions on in it at an instant, and
apart from them the places the feed lists that are not rooms (year data,
`Content.other_locations`). `room_now()` is one room's part of it, for room detail's
"Now in this room". What is on comes from Now & Next's own rule (`agenda.now_next`,
D-179), so the Map, room detail and Now never disagree.

`seed_sprint_rooms()` is the last step of feed processing (MAP-08): the rooms only the
sprints use, which no session names, join the rooms index empty, so the Map lists them.
"""

from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from pycon_us.core.agenda import now_next
from pycon_us.core.models import ConferenceData, Room, Session
from pycon_us.core.slugs import normalize_room_key, room_sort_key, slugify_room
from pycon_us.core.timefmt import instant

SPRINTS_LINE = "Sprints"
"""What a sprint-only room's row says in place of its session count (MAP-08)."""


@dataclass(frozen=True)
class RoomEntry:
    """One row of the rooms list.

    Attributes:
        room: The room, as the model holds it.
        on_now: The sessions on in it, the one that started last first; ties keep the
            Schedule's order. Empty when nothing is on.
    """

    room: Room
    on_now: tuple[Session, ...]


@dataclass(frozen=True)
class Floor:
    """The rooms of one floor plan, a group of the rooms list (ROOM-01).

    Attributes:
        title: Its heading: the plan's title ("Concourse level"), or "Rooms" ("Other
            rooms" after the floors) for the rooms on no plan.
        rooms: Its rooms, in natural order (`slugs.room_sort_key`).
    """

    title: str
    rooms: tuple[RoomEntry, ...]


@dataclass(frozen=True)
class RoomList:
    """The Map's rooms by floor, then the other locations, each group in natural order.

    Attributes:
        floors: The floors with rooms, in the Map's order of the plans; the rooms on
            no plan come last, and are the one group of a year without plans.
        other_locations: The places that are not rooms ("Elsewhere", "Lobby"), which the
            list shows last, under "Other locations".
    """

    floors: tuple[Floor, ...]
    other_locations: tuple[RoomEntry, ...]


def session_count(count: int) -> str:
    """Return a room's count line: "26 sessions", "1 session".

    The Map's rooms list and search's room results both show it (D-188, D-193).

    Args:
        count: The sessions listed under the room, poster details included (ROOM-02).
    """
    return f"{count} session" if count == 1 else f"{count} sessions"


def count_line(room: Room) -> str:
    """Return the line under a room's name: its session count, or "Sprints".

    A room without sessions is a sprint-only room (`seed_sprint_rooms()`, MAP-08),
    which says what it is for rather than "0 sessions".

    Args:
        room: The room, as the model holds it.
    """
    return session_count(len(room.session_ids)) if room.session_ids else SPRINTS_LINE


def seed_sprint_rooms(
    rooms: Mapping[str, Room], names: Iterable[str]
) -> dict[str, Room]:
    """Return the rooms index with the sprint-only rooms added, empty (MAP-08).

    Ionic seeded them from its room registry, so the Seaside rooms the sprints use show
    in the Rooms list though no session names them. A name is keyed by `slugify_room`,
    as the feed's rooms are, so a room the feed already has (S-1, which open spaces use)
    keeps its sessions and is never listed twice; a name given twice is seeded once.

    Args:
        rooms: The feed's rooms index (`rules.rooms`), in natural order.
        names: The sprint rooms' names (`FeedSettings.sprint_rooms`: the `map.toml`
            pins marked `sprint`).

    Returns:
        The rooms by slug, the seeded ones among them, in natural order of name.
    """
    seeded = dict(rooms)
    for name in names:
        slug = slugify_room(name)
        seeded.setdefault(slug, Room(slug=slug, name=name, session_ids=()))
    return {
        slug: seeded[slug]
        for slug in sorted(seeded, key=lambda slug: room_sort_key(seeded[slug].name))
    }


def room_list(
    data: ConferenceData,
    now: datetime,
    other_locations: Collection[str],
    floors: Sequence[tuple[str, Collection[str]]] = (),
) -> RoomList:
    """Return the Map's rooms list at `now`, floor by floor (ROOM-01).

    A session is on in a room while `start <= now < end`, over the timeline only, as
    "Happening now" counts it (`now_next`): a poster detail stays inside its Posters
    row, a notice (no duration) is never on, and outside the conference's sessions
    nothing is. A session listed in several rooms (a plenary, the lightning talks'
    streams) is on in each. When several are on in one room, the one that started
    last comes first: it is the newest thing to walk into, while a long summit or the
    Job Fair has been there for hours.

    Args:
        data: The processed feed.
        now: An aware instant, in any zone (`clock.now()`).
        other_locations: The names of the places that are not rooms, from the year's
            `content.toml`; compared by room slug, so case and punctuation do not
            matter, and a name no room has is ignored.
        floors: Each floor plan's title and the pin keys on it, in the Map's order
            (`MapData.floors()`); a room is on the floor of its pin, found by
            `normalize_room_key()`. A floor without rooms is left out.

    Returns:
        The rooms by floor and the other locations, each group in natural order.

    Raises:
        ValueError: `now` is naive.
    """
    on = _on_by_room(data, now)
    others = {slugify_room(name) for name in other_locations}
    by_floor: list[list[RoomEntry]] = [[] for _ in floors]
    unplaced: list[RoomEntry] = []
    elsewhere: list[RoomEntry] = []
    for room in data.rooms.values():  # in natural order of name (D-125)
        entry = RoomEntry(room, _latest_first(on.get(room.slug, ())))
        key = normalize_room_key(room.name)
        floor = next((i for i, (_, keys) in enumerate(floors) if key in keys), None)
        if room.slug in others:
            elsewhere.append(entry)
        elif floor is None:
            unplaced.append(entry)
        else:
            by_floor[floor].append(entry)
    groups = [
        Floor(title, tuple(entries))
        for (title, _), entries in zip(floors, by_floor, strict=True)
        if entries
    ]
    if unplaced:
        groups.append(Floor("Other rooms" if groups else "Rooms", tuple(unplaced)))
    return RoomList(tuple(groups), tuple(elsewhere))


def room_now(data: ConferenceData, slug: str, now: datetime) -> tuple[Session, ...]:
    """Return the sessions on in one room at `now`: "Now in this room" (ROOM-02).

    The same sessions in the same order as that room's `RoomEntry.on_now` in
    `room_list()`: the timeline only, `start <= now < end`, the one that started
    last first.

    Args:
        data: The processed feed.
        slug: The room's slug (`Room.slug`); a slug no room has gives `()`.
        now: An aware instant, in any zone (`clock.now()`).

    Raises:
        ValueError: `now` is naive.
    """
    return _latest_first(_on_by_room(data, now).get(slug, ()))


def _on_by_room(data: ConferenceData, now: datetime) -> dict[str, list[Session]]:
    """Return the sessions on at `now` by room slug, each in the Schedule's order."""
    on: dict[str, list[Session]] = {}
    for session in now_next(data, now).happening:
        for name in session.rooms:
            on.setdefault(slugify_room(name), []).append(session)
    return on


def _latest_first(sessions: Iterable[Session]) -> tuple[Session, ...]:
    """Return sessions by start, the latest first; a stable sort keeps ties in order.

    By instant, so a start in the repeated hour of the night summer time ends counts as
    later than one in the first (#535).
    """
    return tuple(sorted(sessions, key=lambda s: instant(s.start), reverse=True))
