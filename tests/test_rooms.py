"""Tests for the rooms queries: the Map's list and one room's "now" (ROOM-01, ROOM-02).

On the recorded 2026 feed, at fixed instants in conference time: the rooms' order, the
other locations, and what is on in a room before, during, between and after sessions
(#100, D-188), which room detail's "Now in this room" asks of one room (#101, D-194).
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from pycon_us.config import load_year
from pycon_us.core.models import ConferenceData, Room
from pycon_us.core.rooms import (
    SPRINTS_LINE,
    RoomEntry,
    RoomList,
    count_line,
    room_list,
    room_now,
    seed_sprint_rooms,
    session_count,
)
from pycon_us.core.slugs import room_sort_key
from tests.feeds import processed

PACIFIC = ZoneInfo("America/Los_Angeles")
OTHERS = load_year(2026).content.other_locations
FLOORS = load_year(2026).map.floors()


pytestmark = pytest.mark.usefixtures("machine_tz")  # D-43: two machine zones


@pytest.fixture
def data() -> ConferenceData:
    """The recorded 2026 feed, processed again in each machine zone."""
    return processed(2026)


def at(month: int, day: int, hour: int, minute: int = 0) -> datetime:
    """That time in 2026, in Pacific Time."""
    return datetime(2026, month, day, hour, minute, tzinfo=PACIFIC)


def rooms_of(listing: RoomList) -> list[RoomEntry]:
    """Every room of the list, floor after floor, the other locations left out."""
    return [e for floor in listing.floors for e in floor.rooms]


def entry(listing: RoomList, slug: str) -> RoomEntry:
    """The one entry, room or other location, with that slug."""
    (found,) = [
        e for e in (*rooms_of(listing), *listing.other_locations) if e.room.slug == slug
    ]
    return found


def on_now(listing: RoomList, slug: str) -> list[str]:
    """The names of the sessions on now in the place with that slug."""
    return [session.name for session in entry(listing, slug).on_now]


def test_rooms_are_in_natural_order_and_every_room_is_listed_once(
    data: ConferenceData,
) -> None:
    """Rooms are in natural order, numbers by value, and each place is listed once."""
    listing = room_list(data, at(5, 15, 11, 10), OTHERS)
    names = [e.room.name for e in rooms_of(listing)]
    assert [floor.title for floor in listing.floors] == ["Rooms"]  # no plans given
    assert names == sorted(names, key=room_sort_key)
    # Numbers by value: Room 101A before Room 102A before Room 201A.
    assert (
        names.index("Room 101A") < names.index("Room 102A") < names.index("Room 201A")
    )
    listed = [e.room.slug for e in (*rooms_of(listing), *listing.other_locations)]
    assert sorted(listed) == sorted(data.rooms)


def test_the_places_that_are_not_rooms_are_other_locations(
    data: ConferenceData,
) -> None:
    """The year's other locations are listed apart from the rooms, by name."""
    listing = room_list(data, at(5, 15, 11, 10), OTHERS)
    assert [e.room.name for e in listing.other_locations] == [
        "Elsewhere",
        "Lobby",
        "Out Front of Hyatt Regency",
    ]
    assert not {"elsewhere", "lobby"} & {e.room.slug for e in rooms_of(listing)}


def test_other_locations_match_by_slug_and_ignore_names_no_room_has(
    data: ConferenceData,
) -> None:
    """Other locations match places by slug, and a name no place has is left out."""
    listing = room_list(
        data, at(5, 15, 11), ["LOBBY", "out front of hyatt-regency", "Moon"]
    )
    assert [e.room.slug for e in listing.other_locations] == [
        "lobby",
        "out-front-of-hyatt-regency",
    ]


def test_without_other_locations_every_place_is_a_room(data: ConferenceData) -> None:
    """Without other locations, every place in the feed is listed as a room."""
    listing = room_list(data, at(5, 15, 11), ())
    assert listing.other_locations == ()
    assert len(rooms_of(listing)) == len(data.rooms)


def test_every_listed_other_location_is_a_place_in_the_recorded_feed(
    data: ConferenceData,
) -> None:
    """Every other location in the 2026 year data is a place in the recorded feed."""
    listing = room_list(data, at(5, 15, 11), OTHERS)
    assert len(listing.other_locations) == len(OTHERS)


@pytest.mark.parametrize(
    "now",
    [
        at(5, 12, 12),  # the day before the tutorials
        at(5, 18, 12),  # the sprints: the feed has no sessions
        at(6, 1, 9),  # weeks after
    ],
)
def test_outside_the_conference_s_sessions_nothing_is_on(
    data: ConferenceData, now: datetime
) -> None:
    """Before the tutorials, on sprint days and weeks after, nothing is on anywhere."""
    listing = room_list(data, now, OTHERS)
    assert all(not e.on_now for e in (*rooms_of(listing), *listing.other_locations))


def test_a_session_is_on_in_its_room_from_its_start_until_its_end(
    data: ConferenceData,
) -> None:
    """A session is on in its room from its start up to, not including, its end."""
    assert on_now(room_list(data, at(5, 15, 10, 59), OTHERS), "room-103abc") == [
        "Break"
    ]
    for minute in (0, 10, 29):  # "Mind the gap! …", 11:00 to 11:30 AM
        listing = room_list(data, at(5, 15, 11, minute), OTHERS)
        assert [s.id for s in entry(listing, "room-103abc").on_now] == ["15"]
    # At its end it is over, and the next talk has not started (11:45).
    assert on_now(room_list(data, at(5, 15, 11, 30), OTHERS), "room-103abc") == []
    assert on_now(room_list(data, at(5, 15, 11, 40), OTHERS), "room-103abc") == []


def test_a_session_in_several_rooms_is_on_in_each(data: ConferenceData) -> None:
    """A session in several rooms, like the Lightning Talks, is on in each of them."""
    listing = room_list(data, at(5, 16, 8, 30), OTHERS)
    for slug in ("room-103abc", "room-104ab", "room-104c", "grand-ballroom-a"):
        assert on_now(listing, slug) == ["Lightning Talks"]


def test_the_session_that_started_last_comes_first(data: ConferenceData) -> None:
    """Of a room's sessions on, the one that started last comes first."""
    listing = room_list(data, at(5, 16, 16, 30), OTHERS)
    assert on_now(listing, "room-102c") == [
        "Organizing IRL meetups",  # 4:00 PM
        "Board Games Prt. 2",  # 2:00 PM to 5:00 PM
    ]


def test_poster_details_stay_inside_their_posters_row(data: ConferenceData) -> None:
    """Poster details are not listed apart from their Posters row in the hall."""
    listing = room_list(data, at(5, 17, 10, 30), OTHERS)
    hall = entry(listing, "expo-hall-ab").on_now
    assert "Posters" in [session.name for session in hall]
    assert not [s for s in hall if s.id.startswith("poster-detail-")]
    # The Job Fair row starts at 10:00 (shown at 9:30): it started last.
    assert hall[0].start == at(5, 17, 10)


def test_now_may_be_in_any_zone(data: ConferenceData) -> None:
    """The same instant in Pacific Time or UTC finds the same sessions on."""
    pacific = room_list(data, at(5, 15, 11, 10), OTHERS)
    utc = room_list(data, at(5, 15, 11, 10).astimezone(ZoneInfo("UTC")), OTHERS)
    assert on_now(pacific, "room-103abc") == on_now(utc, "room-103abc")


def test_a_naive_now_is_refused(data: ConferenceData) -> None:
    """A naive `now` is refused with `ValueError`."""
    with pytest.raises(ValueError, match="aware"):
        room_list(data, datetime(2026, 5, 15, 11), OTHERS)  # noqa: DTZ001


@pytest.mark.parametrize(
    ("count", "line"), [(0, "0 sessions"), (1, "1 session"), (26, "26 sessions")]
)
def test_the_count_line_agrees_with_its_number(count: int, line: str) -> None:
    """The count line says "session" for one and "sessions" otherwise, 0 included."""
    assert session_count(count) == line


# ------------------------------------------------------------------ one room (#101)


@pytest.mark.parametrize(
    "now",
    [
        at(5, 15, 10, 59),  # a break in the room
        at(5, 15, 11, 10),  # a talk
        at(5, 15, 11, 30),  # the talk's end: nothing
        at(5, 16, 8, 30),  # the lightning talks, streamed here
        at(5, 12, 12),  # before the conference
        at(5, 18, 12),  # a sprint day
    ],
)
def test_one_room_s_now_is_its_entry_in_the_rooms_list(
    data: ConferenceData, now: datetime
) -> None:
    """Room detail and the Map say the same: one query, one rule (D-179)."""
    listing = room_list(data, now, OTHERS)
    assert room_now(data, "room-103abc", now) == entry(listing, "room-103abc").on_now


def test_one_room_s_now_follows_the_session_s_start_and_end(
    data: ConferenceData,
) -> None:
    """From the start up to, not including, the end ("Mind the gap! …", 11:00-11:30)."""
    assert room_now(data, "room-103abc", at(5, 15, 10, 59))[0].name == "Break"
    for minute in (0, 29):
        on = room_now(data, "room-103abc", at(5, 15, 11, minute))
        assert [s.id for s in on] == ["15"]
    assert room_now(data, "room-103abc", at(5, 15, 11, 30)) == ()


def test_in_one_room_the_session_that_started_last_comes_first(
    data: ConferenceData,
) -> None:
    """In one room's now, the session that started last comes first."""
    on = room_now(data, "room-102c", at(5, 16, 16, 30))
    assert [s.name for s in on] == ["Organizing IRL meetups", "Board Games Prt. 2"]


def test_a_room_the_feed_lacks_has_nothing_on(data: ConferenceData) -> None:
    """A room slug the feed lacks has nothing on."""
    assert room_now(data, "no-such-room", at(5, 15, 11, 10)) == ()


def test_one_room_s_now_refuses_a_naive_now(data: ConferenceData) -> None:
    """One room's now refuses a naive `now` with `ValueError`."""
    with pytest.raises(ValueError, match="aware"):
        room_now(data, "room-103abc", datetime(2026, 5, 15, 11))  # noqa: DTZ001


# ------------------------------------------------------------------ floors (ROOM-01)


def test_rooms_are_grouped_by_floor_in_the_map_s_order(data: ConferenceData) -> None:
    """Each room is under its pin's plan, the plans in map.toml's order (ROOM-01).

    The campus plan has no room, so it is no group; the other locations keep their
    own group, and no room is left without a floor in 2026.
    """
    listing = room_list(data, at(5, 15, 11, 10), OTHERS, FLOORS)
    assert [floor.title for floor in listing.floors] == [
        "Concourse level",
        "Upper level",
        "Arena & exhibit halls",
        "Seaside meeting rooms",
    ]
    concourse, upper, arena, seaside = (
        [e.room.name for e in floor.rooms] for floor in listing.floors
    )
    assert concourse[:3] == ["Room 101A", "Room 101AB", "Room 101B"]
    assert upper == [
        "Grand Ballroom A",
        "Grand Ballroom B",
        "Room 201A",
        "Room 201B",
        "Room 202A",
        "Room 202B",
        "Room 202C",
    ]
    assert arena == ["Expo Hall AB", "Expo Hall C", "Pacific Ballroom - Arena"]
    assert seaside[:4] == ["S-1", "S-2", "S-3", "S-3A"]
    for floor in listing.floors:
        names = [e.room.name for e in floor.rooms]
        assert names == sorted(names, key=room_sort_key)
    assert len(rooms_of(listing)) + len(listing.other_locations) == len(data.rooms)


def test_a_room_on_no_floor_comes_after_the_floors(data: ConferenceData) -> None:
    """A room without a pin is listed last among the rooms, under "Other rooms"."""
    floors = [(title, keys - {"104c"}) for title, keys in FLOORS]
    listing = room_list(data, at(5, 15, 11, 10), OTHERS, floors)
    last = listing.floors[-1]
    assert (last.title, [e.room.name for e in last.rooms]) == (
        "Other rooms",
        ["Room 104C"],
    )


def test_rooms_keep_their_now_lines_under_their_floor(data: ConferenceData) -> None:
    """Grouping changes no room's entry: the same sessions are on (D-188)."""
    now = at(5, 15, 11, 10)
    flat = room_list(data, now, OTHERS)
    grouped = room_list(data, now, OTHERS, FLOORS)
    for slug in data.rooms:
        assert entry(grouped, slug).on_now == entry(flat, slug).on_now


# ------------------------------------------------------------------ sprint rooms (MAP-08)


def room(name: str, *ids: str) -> Room:
    """A room of that name, under its slug, listing `ids`."""
    return Room(slug=name.lower().replace(" ", "-"), name=name, session_ids=ids)


def test_sprint_rooms_are_seeded_once_in_natural_order() -> None:
    """A sprint room joins empty, once, among the feed's rooms in natural order."""
    feed = {r.slug: r for r in (room("S-1", "7"), room("S-10", "8"))}
    rooms = seed_sprint_rooms(feed, ["S-2", "S-2", "Seaside Lobby"])
    assert [(r.name, r.session_ids) for r in rooms.values()] == [
        ("S-1", ("7",)),
        ("S-2", ()),
        ("S-10", ("8",)),
        ("Seaside Lobby", ()),
    ]
    assert list(rooms) == ["s-1", "s-2", "s-10", "seaside-lobby"]


def test_a_sprint_room_the_feed_has_keeps_its_sessions() -> None:
    """A sprint room the feed names is never listed twice: its sessions stay."""
    feed = {"s-1": room("S-1", "7")}
    assert seed_sprint_rooms(feed, ["s 1", "S-1"]) == feed


def test_the_2026_sprint_rooms_leave_out_the_staff_office(data: ConferenceData) -> None:
    """2026 seeds the ten Seaside sprint rooms no session names, and not S-7 (MAP-08)."""
    empty = [r.name for r in data.rooms.values() if not r.session_ids]
    assert empty == [
        "S-2",
        "S-3A",
        "S-3B",
        "S-4A",
        "S-4B",
        "S-5A",
        "S-5B",
        "S-6",
        "Seaside Ballroom",
        "Seaside Lobby",
    ]
    assert "s-7" not in data.rooms
    assert "S-7" not in load_year(2026).feed_settings.sprint_rooms


def test_a_sprint_only_room_says_sprints_where_a_room_counts_sessions(
    data: ConferenceData,
) -> None:
    """A sprint-only room's line says "Sprints"; a room with sessions counts them."""
    assert count_line(data.rooms["s-2"]) == SPRINTS_LINE == "Sprints"
    assert count_line(data.rooms["s-1"]) == session_count(
        len(data.rooms["s-1"].session_ids)
    )
