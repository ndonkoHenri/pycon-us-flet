"""Tests for global search: the index, matching and results (D-46, D-180; NEW-02).

The fold itself is tested in ``test_queries.py``. Here: AND matching of folded words,
markup that never matches, grouping and ordering, scopes, empty queries, and both feeds.
"""

import dataclasses
import logging
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from pycon_us.core.feed import process
from pycon_us.core.models import ConferenceData, Room, Session, Speaker
from pycon_us.core.queries import fold, speaker_order
from pycon_us.core.search import SearchResults, search, search_index
from pycon_us.core.slugs import room_sort_key, slugify_room
from pycon_us.core.timeline import DaySessions, timeline, track_sessions
from tests.feeds import YEARS, changed, processed, settings

pytestmark = pytest.mark.usefixtures("machine_tz")


ZONE = ZoneInfo("America/Los_Angeles")


def at(day: int, hour: int, minute: int = 0) -> datetime:
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


def ids(results: SearchResults) -> list[str]:
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
    """iOS's smart punctuation turns ' into ’ and -- into —; the feeds mix both."""
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
    ("scope", "sessions", "speakers", "rooms"),
    [
        ("all", 1, 1, 1),
        ("sessions", 1, 0, 0),
        ("speakers", 0, 1, 0),
        ("rooms", 0, 0, 1),
    ],
)
def test_the_scope_limits_the_types(
    scope: str, sessions: int, speakers: int, rooms: int
) -> None:
    data = model(
        [talk("1", "Hall talk", at(14, 10))], speakers=["Ann Hall"], rooms=["Hall A"]
    )
    results = search(search_index(data), "hall", scope)
    counts = (results.session_count, len(results.speakers), len(results.rooms))
    assert counts == (sessions, speakers, rooms)


def test_an_unknown_scope_is_an_error() -> None:
    with pytest.raises(ValueError, match="sponsors"):
        search(search_index(TYPING), "python", "sponsors")


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
    with caplog.at_level(logging.INFO, logger="pycon_us.core.search"):
        search_index(TYPING)
    [record] = caplog.records
    assert record.getMessage().startswith("Search index built in ")
    assert record.getMessage().endswith(" ms: 3 sessions, 3 speakers, 2 rooms")


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
        assert room in search(index, room.name, "rooms").rooms


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
    """One session order (D-178): a day's matches come as its track pages list them,
    and each slot's as the Schedule lists the slot."""
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
