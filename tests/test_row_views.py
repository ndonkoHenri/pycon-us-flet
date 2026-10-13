"""Tests for the row views lists hand their rows (``core/row_views.py``; SCHED-03, D-184)."""

from dataclasses import replace
from datetime import date

import pytest

from pycon_us.config import load_year
from pycon_us.core.models import Room
from pycon_us.core.row_views import by_day, places, session_view, session_views
from tests.feeds import processed

pytestmark = pytest.mark.usefixtures("machine_tz")

ZONE_2026 = load_year(2026).conference.zone


def test_a_row_view_has_the_range_place_and_speakers_a_row_shows() -> None:
    view = session_view(processed(2026).sessions["142"], ZONE_2026, use_24h=False)
    assert view.when == "10:30–11:00 AM"
    assert view.place == "Grand Ballroom A"
    assert view.speakers == "Justin Lee"


def test_a_screen_reader_hears_to_in_place_of_the_range_s_dash() -> None:
    view = session_view(processed(2026).sessions["142"], ZONE_2026, use_24h=False)
    assert view.spoken_when == "10:30 to 11:00 AM"


def test_a_row_view_follows_the_device_s_24_hour_clock() -> None:
    view = session_view(processed(2026).sessions["142"], ZONE_2026, use_24h=True)
    assert (view.when, view.spoken_when) == ("10:30–11:00", "10:30 to 11:00")


def test_a_notice_shows_one_time_and_a_generic_break_no_place() -> None:
    sessions = processed(2026).sessions
    notice = session_view(sessions["196"], ZONE_2026, use_24h=False)
    assert notice.when == "7:30 AM"  # Registration Desk Opens: start equals end
    generic = session_view(
        sessions["break--2026-05-17T10:00:00-07:00"], ZONE_2026, use_24h=False
    )
    assert (generic.when, generic.place) == ("10:00 AM–12:00 PM", "")


def test_the_job_fair_row_shows_its_displayed_start() -> None:
    """DATA-11: grouped at 10:00, it opens at 9:30."""
    view = session_view(processed(2026).sessions["178"], ZONE_2026, use_24h=False)
    assert view.when == "9:30 AM–1:00 PM"


def test_pseudo_speakers_show_on_the_speakers_line() -> None:
    """DATA-15: the lightning talks' hosts are text, not directory speakers."""
    view = session_view(processed(2026).sessions["175"], ZONE_2026, use_24h=False)
    assert view.speakers == "Hosted by Abigail, Chris, Cristián, and Lorena"


def test_on_a_room_s_page_a_row_leaves_out_the_room_s_own_name() -> None:
    """The page's title names the room (#101): no place, shown or said."""
    talk = processed(2026).sessions["142"]  # in Grand Ballroom A
    view = session_view(talk, ZONE_2026, use_24h=False, in_room="grand-ballroom-a")
    assert (view.when, view.place) == ("10:30–11:00 AM", "")


def test_on_a_room_s_page_another_place_stays() -> None:
    """The lightning talks are given in the Arena and streamed to Grand Ballroom A."""
    talks = processed(2026).sessions["175"]
    view = session_view(talks, ZONE_2026, use_24h=False, in_room="grand-ballroom-a")
    assert view.place == "Pacific Ballroom - Arena"


def test_the_room_s_name_is_matched_by_slug() -> None:
    """``Session.display_location`` and ``Room.slug`` meet through ``slugify_room``."""
    talk = replace(processed(2026).sessions["142"], display_location="grand ballroom A")
    view = session_view(talk, ZONE_2026, use_24h=False, in_room="grand-ballroom-a")
    assert view.place == ""


def test_every_other_list_keeps_the_place() -> None:
    talk = processed(2026).sessions["142"]
    assert session_view(talk, ZONE_2026, use_24h=False).place == "Grand Ballroom A"
    elsewhere = session_view(talk, ZONE_2026, use_24h=False, in_room="room-103abc")
    assert elsewhere.place == "Grand Ballroom A"


def test_a_room_s_row_views_all_leave_out_the_room() -> None:
    data = processed(2026)
    room = data.rooms["expo-hall-ab"]
    views = session_views(
        data, room.session_ids, ZONE_2026, use_24h=False, in_room=room.slug
    )
    assert len(views) == len(room.session_ids)
    assert {view.place for view in views} == {""}


def test_row_views_keep_the_list_s_order_and_skip_unknown_ids() -> None:
    views = session_views(
        processed(2026), ["74", "gone", "142"], ZONE_2026, use_24h=False
    )
    assert [view.session.id for view in views] == ["74", "142"]


def test_views_group_by_their_conference_local_day_in_order() -> None:
    """A speaker's rows go under a heading per day: a row says only its time."""
    sessions = processed(2026).sessions
    views = [
        session_view(sessions[i], ZONE_2026, use_24h=False) for i in ("19", "142", "76")
    ]
    grouped = [
        (day, [v.session.id for v in group]) for day, group in by_day(views, ZONE_2026)
    ]
    assert grouped == [
        (date(2026, 5, 13), ["19"]),
        (date(2026, 5, 16), ["142", "76"]),
    ]


# ------------------------------------------------------------------ places (SESS-02)


def room_names(rooms: tuple[Room, ...]) -> list[str]:
    return [room.name for room in rooms]


def test_a_talk_has_one_room_and_nothing_to_fold() -> None:
    data = processed(2026)
    where = places(data.sessions["142"], data.rooms)
    assert where.label == "Grand Ballroom A"
    assert where.room is data.rooms["grand-ballroom-a"]
    assert where.others == ()


def test_a_streamed_session_shows_its_place_and_folds_the_rooms_it_lists() -> None:
    """Lightning talks are shown in the Arena and streamed to four rooms (D-124)."""
    data = processed(2026)
    where = places(data.sessions["175"], data.rooms)
    assert where.label == "Pacific Ballroom - Arena"
    assert where.room is data.rooms["pacific-ballroom-arena"]
    assert room_names(where.others) == [
        "Room 103ABC",
        "Room 104AB",
        "Grand Ballroom A",
        "Grand Ballroom B",
    ]
    assert where.others_label == "+4 more rooms"


def test_the_place_shown_is_not_folded_again() -> None:
    """A multi-room event shows its first room; the fold holds the others only."""
    data = processed(2026)
    where = places(data.sessions["219"], data.rooms)  # PSF Members Lunch
    assert where.label == "Room 101A"
    assert room_names(where.others) == ["Room 101B"]
    assert where.others_label == "+1 more room"


def test_a_break_in_many_rooms_has_no_one_place() -> None:
    data = processed(2026)
    break_id = (
        "break-Room 103ABC, Room 104AB, Room 104C, Grand Ballroom A, "
        "Grand Ballroom B-2026-05-16T10:05:00-07:00"
    )
    where = places(data.sessions[break_id], data.rooms)
    assert (where.label, where.room) == ("", None)
    assert where.others_label == "In 5 rooms"


def test_a_notice_has_no_place() -> None:
    data = processed(2026)
    where = places(data.sessions["196"], data.rooms)  # Registration Desk Opens
    assert (where.label, where.room, where.others) == ("", None, ())


def test_a_place_the_feed_has_no_room_for_is_shown_but_opens_nothing() -> None:
    data = processed(2026)
    moved = replace(data.sessions["142"], display_location="Hallway track")
    where = places(moved, data.rooms)
    assert (where.label, where.room) == ("Hallway track", None)
    assert room_names(where.others) == ["Grand Ballroom A"]  # its listed room stays


def test_a_room_listed_twice_is_folded_once() -> None:
    data = processed(2026)
    twice = replace(data.sessions["219"], rooms=("Room 101A", "Room 101B", "Room 101B"))
    assert room_names(places(twice, data.rooms).others) == ["Room 101B"]
