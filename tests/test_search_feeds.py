"""Tests for global search over the recorded feeds, and the cut to the first rows.

Markup that never matches, every name found, places and sponsors, the schedule's order
(D-46, D-178, D-180) and `first_results()`'s cut to each type's first rows (D-218).
The index, matching and results over small built feeds are in `test_search.py`.
"""

from collections.abc import Sequence
from typing import Any

import pytest

from pycon_us.config import load_year
from pycon_us.core.feed import process
from pycon_us.core.models import Session
from pycon_us.core.queries import fold, speaker_order
from pycon_us.core.search import SearchResults, first_results, search, search_index
from pycon_us.core.slugs import room_sort_key
from pycon_us.core.timeline import timeline, track_sessions
from tests.feeds import YEARS, changed, processed, settings
from tests.test_search import ids

pytestmark = pytest.mark.usefixtures("machine_tz")


def _schedule_order(session: Session) -> tuple[object, ...]:
    """D-31 written out on its own, so the index's order is checked, not restated."""
    place = room_sort_key(session.display_location)
    return session.day, session.display_start, place, session.name, session.id


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
    """2026's pytest open space links `[pytest](pytest.org)` (D-140)."""
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
    """`first_results()` cuts sponsors to their limit; None leaves them whole."""
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
    """`first_results()` cuts sessions and speakers, never the venue spots."""
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
    """The ids of the sessions in `results`, in the order shown."""
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
