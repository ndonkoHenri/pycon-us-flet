"""Named tests for Ionic's rules on a session's details: name, place, flags, people, rooms.

D-41; DATA-07..11, DATA-15, DATA-16, SCHED-19. Each test asserts a concrete case of the
recorded 2025 or 2026 feed, or of a copy of it with one record changed, under two machine
time zones (``machine_tz``). Which slots become sessions, and how they fold, is
``test_rules.py``'s, as are the helpers shared here.
"""

import re
from typing import Any

import pytest

from pycon_us.core.feed import process
from pycon_us.core.slugs import slugify_room
from tests.feeds import changed, document, processed, settings
from tests.test_rules import KEPT_TALK, TALK_ID, pacific

pytestmark = pytest.mark.usefixtures("machine_tz")


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
