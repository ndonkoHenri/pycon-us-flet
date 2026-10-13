"""Tests for the Map's rooms list query (#100; ROOM-01, D-188).

On the recorded 2026 feed, at fixed instants in conference time: the rooms' order, the
other locations, and what is on in a room before, during, between and after sessions.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from pycon_us.config import load_year
from pycon_us.core.models import ConferenceData
from pycon_us.core.rooms import RoomEntry, RoomList, room_list, session_count
from pycon_us.core.slugs import room_sort_key
from tests.feeds import processed

PACIFIC = ZoneInfo("America/Los_Angeles")
OTHERS = load_year(2026).content.other_locations


pytestmark = pytest.mark.usefixtures("machine_tz")  # D-43: two machine zones


@pytest.fixture
def data() -> ConferenceData:
    return processed(2026)  # again in each machine zone


def at(month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=PACIFIC)


def entry(listing: RoomList, slug: str) -> RoomEntry:
    (found,) = [
        e for e in (*listing.rooms, *listing.other_locations) if e.room.slug == slug
    ]
    return found


def on_now(listing: RoomList, slug: str) -> list[str]:
    return [session.name for session in entry(listing, slug).on_now]


def test_rooms_are_in_natural_order_and_every_room_is_listed_once(
    data: ConferenceData,
) -> None:
    listing = room_list(data, at(5, 15, 11, 10), OTHERS)
    names = [e.room.name for e in listing.rooms]
    assert names == sorted(names, key=room_sort_key)
    # Numbers by value: Room 101A before Room 102A before Room 201A.
    assert (
        names.index("Room 101A") < names.index("Room 102A") < names.index("Room 201A")
    )
    listed = [e.room.slug for e in (*listing.rooms, *listing.other_locations)]
    assert sorted(listed) == sorted(data.rooms)


def test_the_places_that_are_not_rooms_are_other_locations(
    data: ConferenceData,
) -> None:
    listing = room_list(data, at(5, 15, 11, 10), OTHERS)
    assert [e.room.name for e in listing.other_locations] == [
        "Elsewhere",
        "Lobby",
        "Out Front of Hyatt Regency",
    ]
    assert not {"elsewhere", "lobby"} & {e.room.slug for e in listing.rooms}


def test_other_locations_match_by_slug_and_ignore_names_no_room_has(
    data: ConferenceData,
) -> None:
    listing = room_list(
        data, at(5, 15, 11), ["LOBBY", "out front of hyatt-regency", "Moon"]
    )
    assert [e.room.slug for e in listing.other_locations] == [
        "lobby",
        "out-front-of-hyatt-regency",
    ]


def test_without_other_locations_every_place_is_a_room(data: ConferenceData) -> None:
    listing = room_list(data, at(5, 15, 11), ())
    assert listing.other_locations == ()
    assert len(listing.rooms) == len(data.rooms)


def test_every_listed_other_location_is_a_place_in_the_recorded_feed(
    data: ConferenceData,
) -> None:
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
    listing = room_list(data, now, OTHERS)
    assert all(not e.on_now for e in (*listing.rooms, *listing.other_locations))


def test_a_session_is_on_in_its_room_from_its_start_until_its_end(
    data: ConferenceData,
) -> None:
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
    listing = room_list(data, at(5, 16, 8, 30), OTHERS)
    for slug in ("room-103abc", "room-104ab", "room-104c", "grand-ballroom-a"):
        assert on_now(listing, slug) == ["Lightning Talks"]


def test_the_session_that_started_last_comes_first(data: ConferenceData) -> None:
    listing = room_list(data, at(5, 16, 16, 30), OTHERS)
    assert on_now(listing, "room-102c") == [
        "Organizing IRL meetups",  # 4:00 PM
        "Board Games Prt. 2",  # 2:00 PM to 5:00 PM
    ]


def test_poster_details_stay_inside_their_posters_row(data: ConferenceData) -> None:
    listing = room_list(data, at(5, 17, 10, 30), OTHERS)
    hall = entry(listing, "expo-hall-ab").on_now
    assert "Posters" in [session.name for session in hall]
    assert not [s for s in hall if s.id.startswith("poster-detail-")]
    # The Job Fair row starts at 10:00 (shown at 9:30): it started last.
    assert hall[0].start == at(5, 17, 10)


def test_now_may_be_in_any_zone(data: ConferenceData) -> None:
    pacific = room_list(data, at(5, 15, 11, 10), OTHERS)
    utc = room_list(data, at(5, 15, 11, 10).astimezone(ZoneInfo("UTC")), OTHERS)
    assert on_now(pacific, "room-103abc") == on_now(utc, "room-103abc")


def test_a_naive_now_is_refused(data: ConferenceData) -> None:
    with pytest.raises(ValueError, match="aware"):
        room_list(data, datetime(2026, 5, 15, 11), OTHERS)  # noqa: DTZ001


@pytest.mark.parametrize(
    ("count", "line"), [(0, "0 sessions"), (1, "1 session"), (26, "26 sessions")]
)
def test_the_count_line_agrees_with_its_number(count: int, line: str) -> None:
    assert session_count(count) == line
