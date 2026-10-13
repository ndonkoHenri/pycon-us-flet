"""The rooms list the Map tab shows (ROOM-01; D-13, D-188).

``room_list()`` answers "where is it, and what is on there now?": every room of the feed
in natural order, each with the sessions on in it at an instant, and apart from them the
places the feed lists that are not rooms (year data, ``Content.other_locations``). What
is on comes from Now & Next's own rule (``agenda.now_next``, D-179), so the Map and Now
never disagree.
"""

from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from operator import attrgetter

from pycon_us.core.agenda import now_next
from pycon_us.core.models import ConferenceData, Room, Session
from pycon_us.core.slugs import slugify_room


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
class RoomList:
    """The Map's rooms, in two groups, each in natural order (``slugs.room_sort_key``).

    Attributes:
        rooms: The rooms.
        other_locations: The places that are not rooms ("Elsewhere", "Lobby"), which the
            list shows last, under "Other locations".
    """

    rooms: tuple[RoomEntry, ...]
    other_locations: tuple[RoomEntry, ...]


def session_count(count: int) -> str:
    """Return a room's count line: "26 sessions", "1 session".

    The Map's rooms list and search's room results both show it (D-188, D-193).

    Args:
        count: The sessions listed under the room, poster details included (ROOM-02).
    """
    return f"{count} session" if count == 1 else f"{count} sessions"


def room_list(
    data: ConferenceData, now: datetime, other_locations: Collection[str]
) -> RoomList:
    """Return the Map's rooms list at ``now`` (ROOM-01).

    A session is on in a room while ``start <= now < end``, over the timeline only, as
    "Happening now" counts it (``now_next``): a poster detail stays inside its Posters
    row, a notice (no duration) is never on, and outside the conference's sessions
    nothing is. A session listed in several rooms (a plenary, the lightning talks'
    streams) is on in each. When several are on in one room, the one that started
    last comes first: it is the newest thing to walk into, while a long summit or the
    Job Fair has been there for hours.

    Args:
        data: The processed feed.
        now: An aware instant, in any zone (``clock.now()``).
        other_locations: The names of the places that are not rooms, from the year's
            ``content.toml``; compared by room slug, so case and punctuation do not
            matter, and a name no room has is ignored.

    Returns:
        The rooms and the other locations, each in the model's natural order.

    Raises:
        ValueError: ``now`` is naive.
    """
    on: dict[str, list[Session]] = {}
    for session in now_next(data, now).happening:
        for name in session.rooms:
            on.setdefault(slugify_room(name), []).append(session)
    others = {slugify_room(name) for name in other_locations}
    rooms: list[RoomEntry] = []
    elsewhere: list[RoomEntry] = []
    for room in data.rooms.values():  # in natural order of name (D-125)
        # A stable sort keeps the Schedule's order among equal starts.
        sessions = sorted(on.get(room.slug, ()), key=attrgetter("start"), reverse=True)
        entry = RoomEntry(room, tuple(sessions))
        (elsewhere if room.slug in others else rooms).append(entry)
    return RoomList(tuple(rooms), tuple(elsewhere))
