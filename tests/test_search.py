"""Tests for global search: the index, matching and results (D-46, D-180; NEW-02).

The fold itself is tested in ``test_queries.py``. Here: AND matching of folded words,
markup that never matches, grouping and ordering, scopes, empty queries, both feeds, and
the cut to each type's first rows (D-218).
"""

import dataclasses
import logging
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from pycon_us.config import load_year
from pycon_us.core.feed import process
from pycon_us.core.models import ConferenceData, Room, Session, Speaker
from pycon_us.core.queries import fold, speaker_order
from pycon_us.core.search import SearchResults, first_results, search, search_index
from pycon_us.core.slugs import room_sort_key, slugify_room
from pycon_us.core.timeline import DaySessions, timeline, track_sessions
from pycon_us.year_map import Pin
from tests.feeds import YEARS, changed, processed, settings

pytestmark = pytest.mark.usefixtures("machine_tz")


ZONE = ZoneInfo("America/Los_Angeles")


def at(day: int, hour: int, minute: int = 0) -> datetime:
    """That time on that day of May 2026, in Pacific Time."""
    return datetime(2026, 5, day, hour, minute, tzinfo=ZONE)


def talk(
    id: str,
    name: str,
    start: datetime,
    *,
    location: str = "Room 1",
    text: str = "",
    speakers: tuple[str, ...] = (),
    in_timeline: bool = True,
) -> Session:
    """A session as feed processing leaves it, its search text folded (D-140)."""
    return Session(
        id=id,
        name=name,
        kind="talk",
        track="Talk",
        location=location,
        display_location=location,
        rooms=(location,),
        description="",
        start=start,
        display_start=start,
        end=start + timedelta(minutes=30),
        day=start.date(),
        speaker_ids=(),
        speaker_names=speakers,
        pre_registered=False,
        spanish=False,
        url="",
        image_url="",
        in_timeline=in_timeline,
        search_text=fold(" ".join([name, text, *speakers])),
    )


def model(
    sessions: Sequence[Session],
    speakers: Sequence[str] = (),
    rooms: Sequence[str] = (),
) -> ConferenceData:
    """A processed feed holding just these sessions, speakers and rooms, in order."""
    return ConferenceData(
        sessions={s.id: s for s in sessions},
        speakers={
            str(n): Speaker(str(n), name, "", "") for n, name in enumerate(speakers)
        },
        days=(),
        rooms={
            slugify_room(name): Room(slugify_room(name), name, ()) for name in rooms
        },
        posters=(),
        sprints=(),
        job_listings=(),
        dropped={},
        skipped=(),
        content={},
    )


def _schedule_order(session: Session) -> tuple[object, ...]:
    """D-31 written out on its own, so the index's order is checked, not restated."""
    place = room_sort_key(session.display_location)
    return session.day, session.display_start, place, session.name, session.id


def spot(key: str, label: str, sublabel: str = "") -> Pin:
    """A venue spot's pin on the concourse plan (``MapData.venue_spots()``)."""
    return Pin(
        key=key, label=label, plan="concourse", x=50.0, y=50.0, sublabel=sublabel
    )


def ids(results: SearchResults) -> list[str]:
    """The ids of the sessions found, in the order shown."""
    return [session.id for day in results.sessions for session in day.sessions]


TYPING = model(
    [
        talk("1", "Typing in Python", at(14, 10)),
        talk("2", "Python packaging", at(14, 11), text="Wheels and typing-free builds"),
        talk("3", "Typing for Rust", at(15, 9)),
    ],
    speakers=["Cristián Maureira-Fredes", "Łukasz Langa", "Ana Typing"],
    rooms=["Room 103ABC", "Hall A"],
)


def test_every_word_of_the_query_must_match() -> None:
    """D-46: all words, in any order and anywhere in the text (AND, not Ionic's OR)."""
    index = search_index(TYPING)
    assert ids(search(index, "python typing")) == ["1", "2"]
    assert ids(search(index, "TYPING   python")) == ["1", "2"]
    assert ids(search(index, "typing rust")) == ["3"]
    assert ids(search(index, "typing rust python")) == []


def test_a_word_matches_inside_a_longer_word() -> None:
    """Results narrow as the user types: each word is a substring, not a whole word."""
    index = search_index(TYPING)
    assert ids(search(index, "pyth")) == ["1", "2"]
    assert ids(search(index, "ackag")) == ["2"]


def test_the_query_is_folded_like_the_index() -> None:
    """Acceptance: "cristian" finds "Cristián"; and the other way round."""
    index = search_index(TYPING)
    assert [s.name for s in search(index, "cristian").speakers] == [
        "Cristián Maureira-Fredes"
    ]
    assert [s.name for s in search(index, "CRISTIÁN").speakers] == [
        "Cristián Maureira-Fredes"
    ]
    assert [s.name for s in search(index, "lukasz").speakers] == ["Łukasz Langa"]
    assert [r.name for r in search(index, "103abc").rooms] == ["Room 103ABC"]


def test_curly_quotes_and_dashes_in_a_query_match_straight_ones() -> None:
    """Curly and straight quotes and dashes match each other, in the query or the text.

    iOS's smart punctuation turns ' into ’ and -- into —; the feeds mix both.
    """
    index = search_index(
        model(
            [
                talk("1", "Don't panic", at(14, 10)),
                talk("2", "Type‐safe – and fast", at(14, 11)),
            ]
        )
    )
    assert ids(search(index, "don’t")) == ["1"]
    assert ids(search(index, "dont")) == ["1"]  # the apostrophe left out on a phone
    assert ids(search(index, "type-safe")) == ["2"]
    assert ids(search(index, "safe —")) == ["2"]


@pytest.mark.parametrize("query", ["", " ", "\t\n", "\u00a0", "\u00ad", "\u200b"])
def test_an_empty_or_blank_query_finds_nothing(query: str) -> None:
    """A query that is empty, or only blank or invisible characters, finds nothing."""
    assert search(search_index(TYPING), query) == SearchResults()


def test_sessions_are_grouped_by_day_then_ordered_as_the_schedule() -> None:
    """Days oldest first; in a day by shown start, then place in natural order (D-31)."""
    job_fair = dataclasses.replace(
        talk("fair", "Python job fair", at(14, 11)), display_start=at(14, 9, 30)
    )
    index = search_index(
        model(
            [
                talk("late", "Python late", at(15, 16)),
                talk("b10", "Python b", at(14, 10), location="Room 10"),
                talk("b2", "Python b", at(14, 10), location="Room 2"),
                talk("break", "Python break", at(14, 10), location=""),
                talk("poster", "Python poster", at(14, 9), in_timeline=False),
                talk("a2", "Python z", at(14, 10), location="Room 1"),
                talk("a1", "Python a", at(14, 10), location="Room 1"),
                job_fair,
                talk("first", "Python first", at(13, 9)),
            ]
        )
    )
    results = search(index, "python")
    assert [day.day for day in results.sessions] == [
        date(2026, 5, 13),
        date(2026, 5, 14),
        date(2026, 5, 15),
    ]
    assert ids(results) == [
        "first",
        "poster",
        "fair",  # by the start it shows, 9:30, not its slot's
        "break",  # a row without a place comes first in its slot
        "a1",
        "a2",
        "b2",  # Room 2 before Room 10, as the printed grid reads
        "b10",
        "late",
    ]
    assert results.session_count == 9


def test_speakers_sort_by_folded_name_and_rooms_keep_their_order() -> None:
    """D-46: case and accents do not move a speaker; rooms stay in natural order."""
    data = model(
        [],
        speakers=["carla", "Álvaro", "Bea", "álex"],
        rooms=["Room 2", "Room 10", "Room 1"],
    )
    results = search(search_index(data), "a")
    assert [s.name for s in results.speakers] == ["álex", "Álvaro", "Bea", "carla"]
    assert [r.name for r in search(search_index(data), "room").rooms] == [
        "Room 2",
        "Room 10",
        "Room 1",
    ]


def test_results_are_grouped_by_type() -> None:
    """A word can find a session, a speaker and a room at once; each has its group."""
    results = search(search_index(TYPING), "typing")
    assert ids(results) == ["1", "2", "3"]
    assert [s.name for s in results.speakers] == ["Ana Typing"]
    assert results.rooms == ()


@pytest.mark.parametrize(
    ("scope", "sessions", "speakers", "places"),
    [
        ("all", 1, 1, 2),
        ("sessions", 1, 0, 0),
        ("speakers", 0, 1, 0),
        ("places", 0, 0, 2),
    ],
)
def test_the_scope_limits_the_types(
    scope: str, sessions: int, speakers: int, places: int
) -> None:
    """A scope limits the results to its type; "all" finds every type (D-351)."""
    data = model(
        [talk("1", "Hall talk", at(14, 10))], speakers=["Ann Hall"], rooms=["Hall A"]
    )
    results = search(
        search_index(data, [spot("hall-desk", "Hall desk")]), "hall", scope
    )
    counts = (results.session_count, len(results.speakers), results.place_count)
    assert counts == (sessions, speakers, places)


def test_a_venue_spot_is_found_by_its_label_or_what_happens_there() -> None:
    """Places finds a spot by any words of its label and sublabel, after the rooms."""
    desk = spot("info-desk", "Information desk", "Promenade Lobby (Main Entrance)")
    data = model([], rooms=["Lobby", "Room 104C"])
    index = search_index(data, [desk, spot("quiet-room", "Quiet room", "VIP Room A")])
    assert search(index, "info desk", "places").spots == (desk,)
    assert search(index, "promenade", "places").spots == (desk,)
    found = search(index, "lobby", "places")
    assert ([r.name for r in found.rooms], found.spots) == (["Lobby"], (desk,))
    assert found.place_count == 2
    assert search(index, "room 104c", "places").spots == ()
    assert not search(index, "desk", "sessions").spots


def test_an_unknown_scope_is_an_error() -> None:
    """An unknown scope raises ``ValueError`` naming it."""
    with pytest.raises(ValueError, match="booths"):
        search(search_index(TYPING), "python", "booths")


def test_results_are_frozen_values_equal_for_the_same_matches() -> None:
    """Equal results let a memoised result list skip a keystroke (D-153)."""
    index = search_index(TYPING)
    first, again = search(index, "python"), search(index, "PYTHON ")
    assert first == again and hash(first) == hash(again)
    assert first != search(index, "python packaging")
    with pytest.raises(dataclasses.FrozenInstanceError):
        first.speakers = ()  # type: ignore[misc]
    assert isinstance(first.sessions[0], DaySessions)


def test_building_the_index_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    """Building the index logs its time and its session, speaker and room counts."""
    with caplog.at_level(logging.INFO, logger="pycon_us.core.search"):
        search_index(TYPING)
    [record] = caplog.records
    assert record.getMessage().startswith("Search index built in ")
    assert record.getMessage().endswith(
        " ms: 3 sessions, 3 speakers, 2 rooms, 0 spots, 0 sponsors"
    )


# Search over the recorded feeds


def test_markup_never_matches() -> None:
    """Acceptance: tags, attributes, link targets and scripts are not searched (D-46)."""

    def marked_up(doc: dict[str, Any]) -> None:
        slot = next(s for s in doc["schedule"] if s["kind"] == "talk")
        slot["description"] = (
            '<p>Read <a href="https://example.com/zebra">the guide</a> and <strong>'
            "bold</strong> <em>ideas</em>.</p><script>quokka()</script>"
        )

    data = process(changed(2026, marked_up), settings(2026))
    index = search_index(data)
    [session_id] = ids(search(index, "read the guide and bold ideas"))
    assert "zebra" in data.sessions[session_id].description
    for query in ("zebra", "example.com", "href", "strong", "<em>", "quokka", "script"):
        assert session_id not in ids(search(index, query)), query


@pytest.mark.parametrize("year", YEARS)
@pytest.mark.parametrize("query", ["href", "<p>", "</a>", "**", "](", "&amp;", "&#36;"])
def test_no_markup_matches_in_either_feed(year: int, query: str) -> None:
    """Neither the HTML nor its Markdown, escapes or open-space syntax is searched."""
    assert search(search_index(processed(year)), query) == SearchResults()


def test_an_open_space_link_destination_does_not_match() -> None:
    """2026's pytest open space links ``[pytest](pytest.org)`` (D-140)."""
    data = processed(2026)
    assert "(pytest.org)" in data.sessions["9086"].description
    index = search_index(data)
    assert ids(search(index, "pytest.org")) == []
    assert "9086" in ids(search(index, "pytest is great"))


@pytest.mark.parametrize("year", YEARS)
def test_everything_is_found_by_its_own_name(year: int) -> None:
    """Every session, speaker and room of both feeds is found by its displayed name."""
    data = processed(year)
    index = search_index(data)
    for session in data.sessions.values():
        assert session.id in ids(search(index, session.name, "sessions")), session.name
    for speaker in data.speakers.values():
        assert speaker in search(index, speaker.name, "speakers").speakers
    for room in data.rooms.values():
        assert room in search(index, room.name, "places").rooms


@pytest.mark.parametrize(
    ("query", "found"),
    [
        ("info desk", "Information desk"),
        ("104c", "Room 104C"),
        ("room 104c", "Room 104C"),
        ("s-3a", "S-3A"),  # a sprint-only room, seeded from map.toml (MAP-08)
    ],
)
def test_places_find_2026_s_rooms_and_venue_spots(query: str, found: str) -> None:
    """#393's acceptance: Places finds a feed room, a sprint room or a venue spot."""
    year = load_year(2026)
    index = search_index(processed(2026), year.map.venue_spots())
    results = search(index, query, "places")
    names = [r.name for r in results.rooms] + [pin.label for pin in results.spots]
    assert names[0] == found


@pytest.mark.parametrize(
    ("query", "found"),
    [
        ("bloomberg", ["Bloomberg"]),
        ("anthropic pbc", ["Anthropic, PBC"]),  # the comma folds away (D-180)
        ("ANTHROPIC", ["Anthropic, PBC"]),
    ],
)
def test_sponsors_are_found_by_their_name(query: str, found: list[str]) -> None:
    """#397's acceptance: a sponsor is found by any words of its folded name."""
    results = search(search_index(processed(2026)), query, "sponsors")
    assert [s.name for s in results.sponsors] == found


def test_a_level_finds_its_sponsors_in_the_sponsors_page_order() -> None:
    """A level finds its sponsors: "visionary" finds the 7, in feed order."""
    data = processed(2026)
    results = search(search_index(data), "visionary", "sponsors")
    assert results.sponsors == data.sponsor_levels[0].sponsors
    assert len(results.sponsors) == 7


def test_a_sponsor_is_never_found_by_its_booth_or_description() -> None:
    """Booth numbers are Places' (D-351), and a description's mentions would bury it."""
    data = processed(2026)
    index = search_index(data)
    bloomberg = next(s for _, s in index.sponsors if s.name == "Bloomberg")
    assert bloomberg.booth == "613"
    assert search(index, "613", "sponsors").empty
    assert "techatbloomberg" in fold(bloomberg.description)
    assert search(index, "techatbloomberg", "sponsors").empty


@pytest.mark.parametrize(
    ("scope", "found"), [("all", 1), ("sponsors", 1), ("places", 0)]
)
def test_the_sponsors_scope_finds_sponsors_only(scope: str, found: int) -> None:
    """All and Sponsors find sponsors; every other scope leaves them out."""
    results = search(search_index(processed(2026)), "bloomberg", scope)
    assert len(results.sponsors) == found
    assert results.session_count == 0 or scope == "all"


def test_every_sponsor_is_in_the_index_in_level_order() -> None:
    """The index holds each sponsor once, by level, then feed order (DATA-22)."""
    data = processed(2026)
    expected = [s for level in data.sponsor_levels for s in level.sponsors]
    assert [s for _, s in search_index(data).sponsors] == expected


def test_sponsors_are_cut_on_their_own_limit() -> None:
    """``first_results()`` cuts sponsors to their limit; None leaves them whole."""
    broad = search(search_index(processed(2026)), "a")
    assert len(broad.sponsors) > 5
    cut = first_results(broad, sessions=None, speakers=None, sponsors=5)
    assert cut.sponsors == broad.sponsors[:5]
    assert cut.sessions is broad.sessions and cut.speakers is broad.speakers
    whole = first_results(broad, sessions=None, speakers=None, sponsors=None)
    assert whole is broad
    with pytest.raises(ValueError, match="at least 1"):
        first_results(broad, sessions=None, speakers=None, sponsors=0)


def test_a_cut_keeps_every_venue_spot() -> None:
    """``first_results()`` cuts sessions and speakers, never the venue spots."""
    index = search_index(processed(2026), load_year(2026).map.venue_spots())
    found = search(index, "a")
    assert found.spots and found.session_count > 1
    assert first_results(found, sessions=1, speakers=1).spots is found.spots


@pytest.mark.parametrize("year", YEARS)
def test_the_index_holds_everything_in_the_schedules_order(year: int) -> None:
    """Poster details included; filters play no part (D-20, DATA-07)."""
    data = processed(year)
    index = search_index(data)
    assert {s.id for _, s in index.sessions} == set(data.sessions)
    sessions = [s for _, s in index.sessions]
    for day in data.days:
        listed = {i for group in day.groups for i in group.session_ids}
        assert {s.id for s in sessions if s.in_timeline and s.day == day.date} == listed
    assert sessions == sorted(sessions, key=_schedule_order)
    assert [s for _, s in index.speakers] == sorted(
        data.speakers.values(), key=speaker_order
    )
    assert [r for _, r in index.rooms] == list(data.rooms.values())


def in_common_order[T](
    first: Sequence[T], second: Sequence[T]
) -> tuple[list[T], list[T]]:
    """The items the two sequences share, in the order of each."""
    return [x for x in first if x in second], [x for x in second if x in first]


@pytest.mark.parametrize("year", YEARS)
@pytest.mark.parametrize("query", ["e", "python"])
def test_search_lists_a_day_as_the_schedule_queries_do(year: int, query: str) -> None:
    """Search orders a day's matches as the track pages and the Schedule do (D-178).

    One session order: a day's matches come as its track pages list them, and each
    slot's as the Schedule lists the slot.
    """
    data = processed(year)
    results = search(search_index(data), query)
    found = {group.day: group.sessions for group in results.sessions}
    assert results.session_count > 50
    for track in {s.track for s in data.sessions.values()}:
        for group in track_sessions(data, track):
            matches, listed = in_common_order(found.get(group.day, ()), group.sessions)
            assert matches == listed, (track, group.day)
    for day in data.days:
        for slot in timeline(data, day.date, ()):
            matches, listed = in_common_order(found.get(day.date, ()), slot.sessions)
            assert matches == listed, slot.key


@pytest.mark.parametrize(
    ("year", "query", "speaker"),
    [(2026, "cristian", "Cristián Maureira-Fredes"), (2025, "lukasz", "Łukasz Langa")],
)
def test_an_unaccented_query_finds_a_real_speaker_and_their_sessions(
    year: int, query: str, speaker: str
) -> None:
    """An unaccented name finds its speaker in a real feed, and all their sessions."""
    data = processed(year)
    results = search(search_index(data), query)
    [found] = results.speakers
    assert found.name == speaker
    sessions = {s.id for day in results.sessions for s in day.sessions}
    assert {
        s.id for s in data.sessions.values() if found.id in s.speaker_ids
    } <= sessions


def test_a_pseudo_speaker_is_found_through_its_sessions_only() -> None:
    """D-125: "Hosted by …" is text on the lightning talks, not a directory entry."""
    results = search(search_index(processed(2026)), "hosted by")
    assert results.session_count > 0
    assert results.speakers == ()


# ------------------------------------------------------------------ first rows (D-218)


def _ids(results: SearchResults) -> list[str]:
    """The ids of the sessions in ``results``, in the order shown."""
    return [s.id for day in results.sessions for s in day.sessions]


def test_the_first_rows_keep_the_order_and_cut_the_last_day_shown() -> None:
    """The first rows keep the order, cut only the last day shown, and keep rooms."""
    found = search(search_index(processed(2026)), "p")
    assert found.session_count > 60 and len(found.speakers) > 20  # a broad query
    first = first_results(found, sessions=60, speakers=20)
    assert _ids(first) == _ids(found)[:60]
    assert first.speakers == found.speakers[:20]
    assert first.rooms is found.rooms  # places are never cut
    # The days before the cut are the very same objects, so their memoised groups
    # skip a render (D-153); only the last one shown is a new, shorter day.
    *whole, last = first.sessions
    assert all(a is b for a, b in zip(whole, found.sessions, strict=False))
    assert last.day == found.sessions[len(whole)].day
    assert 0 < len(last.sessions) <= len(found.sessions[len(whole)].sessions)


def test_a_cut_on_a_day_boundary_leaves_no_empty_day() -> None:
    """A cut at the end of a day leaves no empty day after it and reuses that day."""
    found = search(search_index(processed(2026)), "p")
    first_day = len(found.sessions[0].sessions)
    first = first_results(found, sessions=first_day, speakers=None)
    assert first.sessions == found.sessions[:1]
    assert first.sessions[0] is found.sessions[0]
    assert first.speakers is found.speakers  # None keeps them all


def test_results_within_the_limits_are_the_same_object() -> None:
    """Nothing to cut, nothing new: a memoised list sees the same results (D-153)."""
    found = search(search_index(processed(2026)), "typing")
    assert first_results(found, sessions=50, speakers=20) is found
    assert first_results(found, sessions=None, speakers=None) is found
    broad = search(search_index(processed(2026)), "a")
    assert first_results(broad, sessions=None, speakers=None) is broad


def test_each_type_is_cut_on_its_own() -> None:
    """Sessions and speakers are cut on their own limits; None leaves a type whole."""
    broad = search(search_index(processed(2026)), "a")
    sessions_only = first_results(broad, sessions=5, speakers=None)
    assert _ids(sessions_only) == _ids(broad)[:5]
    assert sessions_only.speakers is broad.speakers
    speakers_only = first_results(broad, sessions=None, speakers=5)
    assert speakers_only.sessions is broad.sessions
    assert speakers_only.speakers == broad.speakers[:5]


@pytest.mark.parametrize(("sessions", "speakers"), [(0, 20), (50, 0), (-1, None)])
def test_a_limit_below_one_is_an_error(
    sessions: int | None, speakers: int | None
) -> None:
    """A type that matched always shows a row: its "Show all" row needs one above it."""
    with pytest.raises(ValueError, match="at least 1"):
        first_results(SearchResults(), sessions=sessions, speakers=speakers)
