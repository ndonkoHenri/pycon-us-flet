"""Tests for the row views lists hand their rows (``core/row_views.py``; SCHED-03, D-184)."""

from dataclasses import replace
from datetime import date

import pytest

from pycon_us.config import load_year
from pycon_us.core.models import Room, Speaker
from pycon_us.core.row_views import (
    by_day,
    people,
    places,
    session_view,
    session_views,
)
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


# ------------------------------------------------------------------ people (SESS-07)


def names(found: tuple[Speaker | str, ...]) -> list[str]:
    """Each entry's name, a pseudo-speaker's text marked with ``text:``."""
    return [f"text:{e}" if isinstance(e, str) else e.name for e in found]


def test_a_panel_lists_its_speakers_in_the_feed_s_order() -> None:
    data = processed(2026)
    session = data.sessions["110"]  # Beyond the Hype: six speakers
    found = people(session, data.speakers)
    assert all(isinstance(entry, Speaker) for entry in found)
    assert names(found) == list(session.speaker_names)
    assert [s.id for s in found if isinstance(s, Speaker)] == list(session.speaker_ids)


@pytest.mark.parametrize("year", [2025, 2026])
def test_a_pseudo_speaker_is_text_not_a_speaker(year: int) -> None:
    """D-125: the lightning talks' hosts are not a person with a page."""
    data = processed(year)
    lightning = next(s for s in data.sessions.values() if s.kind == "lightning-talks")
    found = people(lightning, data.speakers)
    assert names(found) == ["text:Hosted by Abigail, Chris, Cristián, and Lorena"]


def test_speakers_and_names_keep_the_authors_order_each_once() -> None:
    data = processed(2026)
    ana, bo = data.speakers["183"], data.speakers["184"]
    session = replace(
        data.sessions["110"],
        speaker_ids=(ana.id, bo.id),
        speaker_names=(ana.name, "Hosted by the PSF", bo.name, ana.name),
    )
    assert people(session, data.speakers) == (ana, "Hosted by the PSF", bo)


def test_a_speaker_linked_by_id_under_another_name_still_gets_a_row() -> None:
    """Poster authors link by id (D-125); the row must not depend on the spelling."""
    data = processed(2026)
    ana = data.speakers["183"]
    session = replace(
        data.sessions["110"], speaker_ids=(ana.id,), speaker_names=("C. Willing",)
    )
    assert people(session, data.speakers) == ("C. Willing", ana)


def test_a_session_without_authors_has_no_one() -> None:
    data = processed(2026)
    assert people(data.sessions["176"], data.speakers) == ()  # a keynote
