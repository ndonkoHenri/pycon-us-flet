"""Tests for global search: the index, matching and results (D-46, D-180; NEW-02).

The fold itself is tested in `test_queries.py`. Here, over small built feeds: AND
matching of folded words, grouping and ordering, scopes and empty queries. Search over
both recorded feeds and the cut to each type's first rows (D-218) are in
`test_search_feeds.py`.
"""

import dataclasses
import logging
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from pycon_us.core.models import ConferenceData, Room, Session, Speaker
from pycon_us.core.queries import fold
from pycon_us.core.search import SearchResults, search, search_index
from pycon_us.core.slugs import slugify_room
from pycon_us.core.timeline import DaySessions
from pycon_us.year_map import Pin

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


def spot(key: str, label: str, sublabel: str = "") -> Pin:
    """A venue spot's pin on the concourse plan (`MapData.venue_spots()`)."""
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
    """An unknown scope raises `ValueError` naming it."""
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
        " ms: 3 sessions, 3 speakers, 2 rooms, 0 spots, 0 booths, 0 sponsors"
    )
