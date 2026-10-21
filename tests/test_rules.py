"""Named tests for Ionic's processing rules (D-41; DATA-04..16, DATA-27, SCHED-19).

Each test asserts a concrete case of the recorded 2025 or 2026 feed, or of a copy of it with
one record changed, under two machine time zones (``machine_tz``).
"""

import logging
import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from pycon_us.core.feed import process
from pycon_us.core.rules import track
from pycon_us.core.slugs import slugify_room
from tests.feeds import changed, document, processed, settings

pytestmark = pytest.mark.usefixtures("machine_tz")

PACIFIC = ZoneInfo("America/Los_Angeles")
KEPT_TALK = next(
    i for i, s in enumerate(document(2026)["schedule"]) if s["kind"] == "talk"
)
TALK_ID = str(document(2026)["schedule"][KEPT_TALK]["conf_key"])
EASTERN = ZoneInfo("America/New_York")


def pacific(day: int, hour: int, minute: int = 0) -> datetime:
    """May ``day``, 2026, at ``hour``:``minute``, Pacific time."""
    return datetime(2026, 5, day, hour, minute, tzinfo=PACIFIC)


def test_track_is_the_kind_capitalised_except_sponsor_workshops() -> None:
    """DATA-14: track keys as config's track registry names them."""
    assert [
        track(k) for k in ("talk", "ai", "lightning-talks", "sponsor-workshop")
    ] == [
        "Talk",
        "Ai",
        "Lightning-talks",
        "Sponsor Presentation",
    ]


def test_placeholder_slots_dropped_but_posters_and_breaks_kept() -> None:
    """DATA-04: cancelled stubs go; poster and break slots of the same shape collapse."""
    dropped = processed(2026).dropped
    assert dropped["placeholder"] == ("130", "34", "1136", "32")
    assert processed(2025).dropped["placeholder"] == ("34",)
    poster_slots = [s for s in document(2026)["schedule"] if s["kind"] == "poster"]
    assert poster_slots[0]["name"] == "poster" and not poster_slots[0]["description"]
    assert {str(s["conf_key"]) for s in poster_slots} <= set(dropped["collapsed"])


def test_open_space_slots_are_dropped_from_the_schedule() -> None:
    """DATA-04: free rooms, and the booked ones the open-spaces list also has."""
    dropped = processed(2026).dropped
    assert (
        len(dropped["available-open-space"]),
        len(dropped["open-space-duplicate"]),
    ) == (
        484,
        7,
    )
    assert (
        "1140" in dropped["open-space-duplicate"]
    )  # "5K Fun Run", also open space 119


def test_posters_plenary_is_dropped_as_a_copy_of_the_posters_row() -> None:
    """DATA-04: "[Posters (Hall AB)](...)" is a plenary copy of the collapsed row."""
    assert processed(2026).dropped["posters-plenary"] == ("179",)


def test_blank_slots_are_dropped() -> None:
    """A slot of kind ``blank``, or named ``Slot``, is dropped as blank."""

    def blank(doc: dict[str, Any]) -> None:
        doc["schedule"][4]["kind"] = "blank"  # 196, "Registration Desk Opens"
        doc["schedule"][5]["name"] = "Slot"  # 198

    data = process(changed(2026, blank), settings(2026))
    assert data.dropped["blank"] == ("196", "198")


def test_open_spaces_become_sessions_with_offset_ids() -> None:
    """DATA-05: id conf_key + 9000, track Open Space, the room_display as location."""
    data = processed(2026)
    run = data.sessions["9119"]  # open space 119, "5K Fun Run", room "Elsewhere"
    assert (run.name, run.kind, run.track, run.location) == (
        "5K Fun Run",
        "open-space",
        "Open Space",
        "Out Front of Hyatt Regency",
    )
    assert (run.start, run.end, run.day) == (
        pacific(16, 7),
        pacific(16, 8),
        pacific(16, 7).date(),
    )
    assert run.description.startswith("Meet out front of Hyatt Regency 7AM")
    assert run.url == "https://us.pycon.org/2026/schedule/open-spaces/#OpenSpace-119"
    assert run.image_url.endswith("/2026/media/open_spaces_images/running-sand.png")
    assert run.speaker_ids == () and run.in_timeline
    assert sum(s.kind == "open-space" for s in data.sessions.values()) == 123
    assert sum(s.kind == "open-space" for s in processed(2025).sessions.values()) == 146


def test_open_space_image_is_made_absolute() -> None:
    """A relative open-space image URL is made absolute on us.pycon.org."""

    def relative(doc: dict[str, Any]) -> None:
        doc["open-spaces"][0]["image_url"] = "/2026/media/open_spaces_images/x.png"

    data = process(changed(2026, relative), settings(2026))
    space = document(2026)["open-spaces"][0]
    session = data.sessions[str(space["conf_key"] + 9000)]
    assert (
        session.image_url == "https://us.pycon.org/2026/media/open_spaces_images/x.png"
    )


def test_unscheduled_open_space_is_dropped() -> None:
    """DATA-05: without a start, an end or a room it is a proposal, not a session."""

    def unschedule(doc: dict[str, Any]) -> None:
        doc["open-spaces"][0]["start"] = None
        del doc["open-spaces"][1]["end"]
        doc["open-spaces"][2].update(room_display=" ", room="")

    data = process(changed(2026, unschedule), settings(2026))
    ids = tuple(str(s["conf_key"] + 9000) for s in document(2026)["open-spaces"][:3])
    assert data.dropped["unscheduled-open-space"] == ids
    assert not set(ids) & set(data.sessions)
    assert data.skipped == ()


def test_open_space_without_room_display_uses_its_room() -> None:
    """DATA-05: Ionic checked room_display or room but showed only room_display."""

    def no_display(doc: dict[str, Any]) -> None:
        doc["open-spaces"][0]["room_display"] = ""

    data = process(changed(2026, no_display), settings(2026))
    assert data.sessions["9119"].location == "Elsewhere"


def test_lunch_row_spans_earliest_start_to_latest_end() -> None:
    """DATA-06, SCHED-19: Friday's staggered "Lunch (Hall AB)" slots make one row."""
    lunch = processed(2026).sessions["break-Expo Hall AB-2026-05-15T12:30:00-07:00"]
    assert (lunch.name, lunch.track, lunch.location) == (
        "Lunch",
        "Break",
        "Expo Hall AB",
    )
    assert (lunch.start, lunch.end) == (pacific(15, 12, 30), pacific(15, 14))


def test_a_rows_span_and_id_come_from_its_earliest_slot_wherever_it_is() -> None:
    """DATA-06: an earlier slot found later still moves the row's start and id."""

    def earliest_last(doc: dict[str, Any]) -> None:
        lunches = [s for s in doc["schedule"] if s["conf_key"] in (149, 155, 156)]
        for lunch in lunches:
            doc["schedule"].remove(lunch)
        doc["schedule"] += sorted(lunches, key=lambda s: s["start"], reverse=True)

    data = process(changed(2026, earliest_last), settings(2026))
    lunch = data.sessions["break-Expo Hall AB-2026-05-15T12:30:00-07:00"]
    assert (lunch.start, lunch.end) == (pacific(15, 12, 30), pacific(15, 14))


def test_collapsed_ids_do_not_depend_on_the_feeds_offset() -> None:
    """D-123: the same instants written in UTC give the same ids."""

    def in_utc(doc: dict[str, Any]) -> None:
        for slot in doc["schedule"]:
            for key in ("start", "end"):
                moment = datetime.fromisoformat(slot[key]).astimezone(ZoneInfo("UTC"))
                slot[key] = moment.isoformat()

    utc = process(changed(2026, in_utc), settings(2026))
    assert list(utc.sessions) == list(processed(2026).sessions)


def test_one_lunch_row_per_day_that_has_lunch() -> None:
    """DATA-06: Thursday to Sunday in 2026; every day in 2025."""
    for year, expected in ((2026, 4), (2025, 5)):
        lunches = [
            s.day for s in processed(year).sessions.values() if s.name == "Lunch"
        ]
        assert len(lunches) == len(set(lunches)) == expected


def test_all_posters_of_a_day_fold_into_one_row() -> None:
    """DATA-06: 26 five-minute poster slots become one Posters row."""
    data = processed(2026)
    (row,) = [s for s in data.sessions.values() if s.kind == "poster" and s.in_timeline]
    assert row.id == "poster-Expo Hall AB-2026-05-17T09:30:00-07:00"
    assert (row.name, row.track, row.location) == ("Posters", "Poster", "Expo Hall AB")
    assert (row.start, row.end) == (pacific(17, 9, 30), pacific(17, 13))
    assert (row.description, row.speaker_ids) == ("", ())


def test_breaks_other_than_lunch_fold_per_start() -> None:
    """DATA-06: Friday's 10:30 and 16:00 breaks stay two rows."""
    friday = [
        (s.start, s.end)
        for s in processed(2026).sessions.values()
        if s.name == "Break" and s.day == pacific(15, 0).date()
    ]
    assert friday == [
        (pacific(15, 10, 30), pacific(15, 11)),
        (pacific(15, 16), pacific(15, 16, 30)),
    ]


def test_collapsed_ids_keep_ionics_form_with_the_room() -> None:
    """DATA-06, D-42: "<kind>-<room>-<start>", with an empty room for Wednesday's break."""
    data = processed(2026)
    wednesday = data.sessions["break--2026-05-13T12:30:00-07:00"]
    assert (wednesday.name, wednesday.location) == ("Break", "")
    coffee = data.sessions["break-Expo Hall AB-2026-05-15T08:00:00-07:00"]
    assert coffee.name == "Coffee"  # "(Hall AB)" moved to the room


def test_hall_rooms_get_the_years_prefix() -> None:
    """D-122: "Lunch (Hall C)" is in Expo Hall C in 2026; 2025's halls keep their names."""
    thursday = processed(2026).sessions["break-Expo Hall C-2026-05-14T12:30:00-07:00"]
    assert thursday.name == "Lunch"
    posters = processed(2025).sessions["poster-Hall A-2025-05-18T10:00:00-04:00"]
    assert posters.start == datetime(2025, 5, 18, 10, tzinfo=EASTERN)


def test_friday_to_sunday_break_at_lunchtime_is_renamed_lunch() -> None:
    """DATA-06: a "Break" from 12:00 to 13:59 on a main conference day is Lunch."""

    def noon(doc: dict[str, Any]) -> None:
        for slot in doc["schedule"]:
            if slot["conf_key"] == 154:  # Friday's 10:30 break
                slot.update(
                    start="2026-05-15T12:15:00-07:00", end="2026-05-15T12:45:00-07:00"
                )
            if slot["conf_key"] == 144:  # Wednesday's 12:30 break stays a Break
                slot["start"] = "2026-05-13T12:15:00-07:00"

    sessions = process(changed(2026, noon), settings(2026)).sessions.values()
    renamed = [s for s in sessions if s.start == pacific(15, 12, 15)]
    assert [s.name for s in renamed] == ["Lunch"]
    assert [s.name for s in sessions if s.start == pacific(13, 12, 15)] == ["Break"]


def test_empty_room_takes_a_later_slots_room() -> None:
    """DATA-06: as in Ionic, a row without a room adopts a later slot's "(Room)".

    Only a poster row can have one: its name becomes "Posters" before the room is read.
    """

    def roomless(doc: dict[str, Any]) -> None:
        for slot in doc["schedule"]:
            if slot["kind"] == "poster":
                slot.update(name="poster (Hall AB)", room="")

    data = process(changed(2026, roomless), settings(2026))
    row = data.sessions["poster-Expo Hall AB-2026-05-17T09:30:00-07:00"]
    assert (row.name, row.location) == ("Posters", "Expo Hall AB")


def test_poster_details_inherit_the_posters_row() -> None:
    """DATA-07: poster-detail-<conf_key>, at the Posters row's time and place."""
    data = processed(2026)
    row = data.sessions["poster-Expo Hall AB-2026-05-17T09:30:00-07:00"]
    details = [s for s in data.sessions.values() if s.id.startswith("poster-detail-")]
    assert [s.id for s in details] == [f"poster-detail-{p.id}" for p in data.posters]
    for detail, poster in zip(details, data.posters, strict=True):
        assert (detail.name, detail.description) == (poster.title, poster.description)
        assert (detail.kind, detail.track, detail.location) == (
            "poster",
            "Poster",
            row.location,
        )
        assert (detail.start, detail.end, detail.day) == (row.start, row.end, row.day)
        assert detail.speaker_ids == poster.speaker_ids
        assert not detail.in_timeline


def test_2025_nested_posters_become_posters_and_poster_details() -> None:
    """D-121, DATA-27: the 19 sessions of 2025's "Posters Session" slot are posters."""
    data = processed(2025)
    assert len(data.posters) == 19
    first = data.posters[0]
    assert first.id == "1544"
    assert first.title.startswith("Putting a Face to the Pattern")
    assert first.description.startswith("<p>In recent times")
    detail = data.sessions["poster-detail-1544"]
    assert (detail.location, detail.start) == (
        "Hall A",
        datetime(2025, 5, 18, 10, tzinfo=EASTERN),
    )
    assert set(first.speaker_ids) <= set(data.speakers)


def test_nested_sessions_of_another_kind_are_ignored_and_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """DATA-27: Ionic's shared-session branch is not ported."""

    def nest(doc: dict[str, Any]) -> None:
        doc["schedule"][4]["sessions"] = [{"conf_key": 1, "name": "Inner"}]

    with caplog.at_level(logging.WARNING, logger="pycon_us.core.feed"):
        data = process(changed(2026, nest), settings(2026))
    assert caplog.messages == ["Ignored the nested sessions of slot 196 (DATA-27)"]
    assert len(data.posters) == 25 and data.skipped == ()


def test_posters_without_a_posters_row_get_no_session(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """D-123: no Posters row, no time to give the poster details."""

    def no_poster_slots(doc: dict[str, Any]) -> None:
        doc["schedule"] = [s for s in doc["schedule"] if s["kind"] != "poster"]

    with caplog.at_level(logging.WARNING, logger="pycon_us.core.feed"):
        data = process(changed(2026, no_poster_slots), settings(2026))
    assert not any(s.kind == "poster" for s in data.sessions.values())
    assert len(data.posters) == 25
    assert caplog.messages == ["No Posters row: the 25 posters get no session"]


def test_a_session_id_already_taken_is_skipped() -> None:
    """D-42: ids stay unique; the later session is skipped and recorded."""

    def collide(doc: dict[str, Any]) -> None:
        doc["schedule"][5]["conf_key"] = 9119  # open space 119's session id

    data = process(changed(2026, collide), settings(2026))
    assert data.skipped == ("session '5K Fun Run': duplicate id '9119'",)
    assert data.sessions["9119"].kind == "informational"


def test_dropped_slots_are_counted_in_the_log(caplog: pytest.LogCaptureFixture) -> None:
    """Processing logs how many slots it dropped, counted by reason."""
    with caplog.at_level(logging.INFO, logger="pycon_us.core.feed"):
        processed(2026)
    message, _ = caplog.messages  # then "Feed processed in N ms: ..."
    assert message == (
        "Dropped 484 available-open-space, 7 open-space-duplicate, 49 collapsed,"
        " 4 placeholder, 1 posters-plenary"
    )


def test_keynote_room_moves_from_title_to_location() -> None:
    """DATA-08: "[Keynote — Lin Qiao (Pacific Ballroom - Arena)](...)"."""
    keynote = processed(2026).sessions["153"]
    assert (keynote.name, keynote.location, keynote.display_location) == (
        "Lin Qiao",
        "Pacific Ballroom - Arena",
        "Pacific Ballroom - Arena",
    )
    assert keynote.rooms == ("Pacific Ballroom - Arena",)


def test_names_lose_their_markup() -> None:
    """DATA-08, D-114: Markdown links and tags become text, in both years."""
    assert processed(2026).sessions["223"].name == "PyLadies Auction"
    assert processed(2025).sessions["153"].name == "Job Fair and Community Showcase"
    cancelled = processed(2025).sessions["1791"]
    assert cancelled.name == "CANCELLED: Introduction to Sprints Workshop"
    for year in (2025, 2026):
        for session in processed(year).sessions.values():
            assert not re.search(r"\]\(|</?[a-z]+>", session.name), session.name


def test_hall_rooms_in_plenary_names_get_the_prefix() -> None:
    """D-122: "Opening Reception (Hall AB)" is in Expo Hall AB; 2025's Hall A stays."""
    assert processed(2026).sessions["147"].location == "Expo Hall AB"
    assert processed(2025).sessions["27"].location == "Hall A"


def test_pre_registration_is_flagged_and_cut_from_the_name() -> None:
    """DATA-09: the phrase, every tutorial, and every summit but Typing."""
    sessions = processed(2026).sessions
    lunch = sessions["219"]
    assert (lunch.name, lunch.pre_registered) == ("PSF Members Lunch", True)
    assert sessions["218"].pre_registered  # "Maintainers Summit", no phrase
    assert not sessions["201"].pre_registered  # "Typing Summit"
    tutorials = [s for s in sessions.values() if s.kind == "tutorial"]
    assert len(tutorials) == 20 and all(s.pre_registered for s in tutorials)
    language = processed(2025).sessions["1746"]
    assert (language.name, language.pre_registered) == ("Python Language Summit", True)
    others = [
        s for s in sessions.values() if s.kind in ("open-space", "break", "poster")
    ]
    assert not any(s.pre_registered for s in others)


def test_spanish_flag_matches_espanol_with_and_without_tilde() -> None:
    """DATA-10: charlas, and "En Español" in a name, which is cut."""
    sessions = processed(2026).sessions
    keynote = sessions["165"]
    assert (keynote.name, keynote.spanish) == ("Pablo Galindo Salgado", True)
    charlas = [s for s in sessions.values() if s.kind == "charla"]
    assert len(charlas) == 16 and all(s.spanish for s in charlas)
    assert sum(s.spanish for s in sessions.values()) == 17

    def without_tilde(doc: dict[str, Any]) -> None:
        doc["schedule"][KEPT_TALK]["name"] = "Datos abiertos, en espanol"

    talk = process(changed(2026, without_tilde), settings(2026)).sessions[TALK_ID]
    assert (talk.name, talk.spanish) == ("Datos abiertos", True)


def test_job_fair_grouped_at_ten_labelled_nine_thirty() -> None:
    """DATA-11: the override in content.toml moves the label, not the time group."""
    data = processed(2026)
    job_fair = data.sessions["178"]
    assert job_fair.name == "Job Fair & Community Showcase"
    assert (job_fair.start, job_fair.display_start) == (
        pacific(17, 10),
        pacific(17, 9, 30),
    )
    (sunday,) = [day for day in data.days if day.date == pacific(17, 0).date()]
    (ten,) = [group for group in sunday.groups if group.start == pacific(17, 10)]
    assert "178" in ten.session_ids
    longer = data.sessions["227"]  # "Job Fair & Community Showcase & Poster Sessions"
    assert longer.display_start == longer.start == pacific(17, 9, 30)
    shifted = [s.id for s in data.sessions.values() if s.display_start != s.start]
    assert shifted == ["178"]
    assert all(s.display_start == s.start for s in processed(2025).sessions.values())


def test_lightning_talks_show_the_years_location() -> None:
    """D-124: 2026's are streamed to five rooms and shown in the Arena."""
    talks = processed(2026).sessions["163"]
    assert talks.display_location == "Pacific Ballroom - Arena"
    assert talks.rooms == (
        "Room 103ABC",
        "Room 104AB",
        "Room 104C",
        "Grand Ballroom A",
        "Grand Ballroom B",
    )
    assert processed(2025).sessions["99"].display_location == "Hall B"


def test_speakers_link_by_name() -> None:
    """DATA-15: an author is linked when a speaker record carries the same name."""
    sessions = processed(2026).sessions
    talk = sessions[TALK_ID]
    record = document(2026)["schedule"][KEPT_TALK]
    assert talk.speaker_names == tuple(record["authors"])
    assert talk.speaker_ids == tuple(str(s["id"]) for s in record["speakers"])

    def misspell(doc: dict[str, Any]) -> None:
        doc["schedule"][KEPT_TALK]["authors"] = ["Someone Else"]

    unlinked = process(changed(2026, misspell), settings(2026)).sessions[TALK_ID]
    assert (unlinked.speaker_names, unlinked.speaker_ids) == (("Someone Else",), ())


def test_hosted_by_is_not_a_speaker() -> None:
    """DATA-15: the lightning talks' "Hosted by …" stays text, out of the directory."""
    for year, talk_id in ((2026, "163"), (2025, "99")):
        data = processed(year)
        talks = data.sessions[talk_id]
        assert talks.speaker_names == (
            "Hosted by Abigail, Chris, Cristián, and Lorena",
        )
        assert talks.speaker_ids == ()
        assert not any(s.name.startswith("Hosted by") for s in data.speakers.values())
    assert len(processed(2026).speakers) == 169  # Ionic's 170 less the pseudo-speaker


def test_poster_details_link_their_authors() -> None:
    """DATA-07, DATA-15: by id, as Ionic did for posters."""
    data = processed(2026)
    for poster in data.posters:
        detail = data.sessions[f"poster-detail-{poster.id}"]
        assert detail.speaker_ids == poster.speaker_ids
        assert detail.speaker_names == tuple(
            data.speakers[i].name for i in poster.speaker_ids
        )


def test_multi_room_session_appears_in_each_room() -> None:
    """DATA-16: a session is listed under every room of its location."""
    data = processed(2026)
    lunch = data.sessions["219"]  # PSF Members Lunch
    assert lunch.rooms == ("Room 101A", "Room 101B")
    assert lunch.display_location == "Room 101A"
    for slug in ("room-101a", "room-101b"):
        assert "219" in data.rooms[slug].session_ids
    generic = data.sessions[
        "break-Room 103ABC, Room 201B, Room 202A, Room 104AB, Room 104C,"
        " Grand Ballroom A, Grand Ballroom B-2026-05-15T10:30:00-07:00"
    ]
    assert len(generic.rooms) == 7 and generic.display_location == ""
    assert all(
        generic.id in data.rooms[slugify_room(r)].session_ids for r in generic.rooms
    )


def test_rooms_are_indexed_by_slug_in_natural_order() -> None:
    """DATA-16, ROOM-06: Ionic's 28 rooms with sessions in 2026, and their counts.

    The 10 sprint-only rooms seeded from ``map.toml`` join them, empty (MAP-08).
    """
    rooms = processed(2026).rooms
    assert [(r.name, len(r.session_ids)) for r in rooms.values()][:4] == [
        ("Elsewhere", 8),
        ("Expo Hall AB", 35),
        ("Expo Hall C", 1),
        ("Grand Ballroom A", 26),
    ]
    assert len([room for room in rooms.values() if room.session_ids]) == 28
    assert len(rooms) == 38
    assert all(slug == slugify_room(room.name) for slug, room in rooms.items())
    names = [room.name for room in rooms.values()]
    assert names.index("Room 101AB") < names.index("Room 102A") < names.index("S-1")
    arena = rooms["pacific-ballroom-arena"]
    starts = [processed(2026).sessions[i].start for i in arena.session_ids]
    assert starts == sorted(starts)


def test_a_session_without_a_room_is_in_no_room() -> None:
    """DATA-16: 2026's notices have an empty room."""
    data = processed(2026)
    notice = data.sessions["196"]  # "Registration Desk Opens"
    assert (notice.location, notice.rooms, notice.display_location) == ("", (), "")


def test_poster_details_keep_every_authors_name() -> None:
    """D-125: an author left out of the directory still shows as text."""

    def pseudo_author(doc: dict[str, Any]) -> None:
        doc["posters"][0]["speakers"][0]["name"] = "Hosted by Example"

    data = process(changed(2026, pseudo_author), settings(2026))
    poster = document(2026)["posters"][0]
    detail = data.sessions[f"poster-detail-{poster['conf_key']}"]
    assert detail.speaker_names[0] == "Hosted by Example"
    assert str(poster["speakers"][0]["id"]) not in detail.speaker_ids


def test_a_name_links_the_first_speaker_of_that_name_once() -> None:
    """D-125: two records with one name link the first; a repeated author links once."""
    talks = [s for s in document(2026)["schedule"] if s["kind"] == "talk"]
    first, other = talks[0], talks[1]
    name = first["authors"][0]

    def same_name(doc: dict[str, Any]) -> None:
        for record in doc["schedule"]:
            if record["conf_key"] == other["conf_key"]:
                record["speakers"][0]["name"] = name
                record["authors"] = [name, name]

    data = process(changed(2026, same_name), settings(2026))
    linked = data.sessions[str(other["conf_key"])]
    assert linked.speaker_ids == (str(first["speakers"][0]["id"]),)
    assert linked.speaker_names == (name, name)


def test_a_rooms_sessions_with_one_start_are_in_name_order() -> None:
    """D-125: the Posters row, the Job Fair and 25 poster details all start at 9:30."""
    data = processed(2026)
    sessions = [data.sessions[i] for i in data.rooms["expo-hall-ab"].session_ids]
    at_nine_thirty = [s.name for s in sessions if s.start == pacific(17, 9, 30)]
    assert len(at_nine_thirty) == 27
    assert at_nine_thirty == sorted(at_nine_thirty)


def test_room_spellings_sharing_a_slug_list_a_session_once() -> None:
    """DATA-16: "Room 101A" and "room 101a" are one room, named as first written."""

    def respell(doc: dict[str, Any]) -> None:
        doc["schedule"][KEPT_TALK]["room"] = "Room 101A, room 101a"

    data = process(changed(2026, respell), settings(2026))
    assert data.sessions[TALK_ID].rooms == ("Room 101A",)
    assert data.rooms["room-101a"].session_ids.count(TALK_ID) == 1
