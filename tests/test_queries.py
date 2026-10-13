"""Tests for the queries over the processed feed (architecture §7.5).

DATA-17's days, D-46's fold, and the schedule queries of #85 (DATA-18, DATA-20, DATA-30,
SCHED-17).
"""

import ast
import gc
import inspect
import weakref
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from pycon_us.config import load_year
from pycon_us.core import queries
from pycon_us.core.feed import process
from pycon_us.core.models import ConferenceData, Session
from pycon_us.core.queries import (
    Slot,
    days,
    fold,
    schedule_order,
    timeline,
    track_sessions,
)
from pycon_us.prefs import Prefs
from tests.feeds import YEARS, changed, processed, settings

pytestmark = pytest.mark.usefixtures("machine_tz")


def test_2026_days_run_from_tutorials_to_the_last_sprint_day() -> None:
    """DATA-17: the two sprint days have no sessions in the feed but get a day."""
    conference = load_year(2026).conference
    assert days(processed(2026), conference.first_day, conference.last_day) == tuple(
        date(2026, 5, d) for d in range(13, 20)
    )


@pytest.mark.parametrize("year", YEARS)
def test_every_schedule_day_is_one_of_the_days(year: int) -> None:
    conference = load_year(year).conference
    result = days(processed(year), conference.first_day, conference.last_day)
    assert {day.date for day in processed(year).days} <= set(result)
    assert list(result) == sorted(set(result))
    assert (result[0], result[-1]) == (conference.first_day, conference.last_day)


def test_a_session_outside_the_conference_dates_widens_the_days() -> None:
    def early(doc: dict[str, Any]) -> None:
        doc["schedule"][5].update(
            start="2026-05-11T09:00:00-07:00", end="2026-05-11T10:00:00-07:00"
        )

    data = process(changed(2026, early), settings(2026))
    conference = load_year(2026).conference
    result = days(data, conference.first_day, conference.last_day)
    assert result[:3] == (date(2026, 5, 11), date(2026, 5, 12), date(2026, 5, 13))


@pytest.mark.parametrize(
    ("text", "folded"),
    [
        ("Cristián", "cristian"),
        ("ÜBER Python", "uber python"),
        ("Straße", "strasse"),  # case folding, not just lower-casing
        ("ﬁle", "file"),  # NFKD splits the ligature
    ],
)
def test_fold_ignores_case_and_accents(text: str, folded: str) -> None:
    """D-46: search and the Speakers sort compare folded text."""
    assert fold(text) == folded


# --------------------------------------------------------------------------------------
# Schedule queries (#85): the timeline, the track filter and track pages
# --------------------------------------------------------------------------------------


def schedule_days(year: int) -> tuple[date, ...]:
    conference = load_year(year).conference
    return days(processed(year), conference.first_day, conference.last_day)


def slot_at(data: ConferenceData, start: str) -> Slot:
    """The unfiltered slot of ``data`` that starts at ``start`` (ISO 8601)."""
    day = date.fromisoformat(start[:10])
    return next(slot for slot in timeline(data, day, ()) if slot.key == f"slot-{start}")


def sessions_like(*changes: dict[str, Any]) -> list[Session]:
    """Copies of one 2026 session, one per dict of changes, for cases the feeds lack."""
    base = next(iter(processed(2026).sessions.values()))
    return [replace(base, **change) for change in changes]


@pytest.mark.parametrize("year", YEARS)
def test_timeline_lists_every_timeline_session_once_in_its_days_slots(
    year: int,
) -> None:
    """DATA-18, D-31: one slot per time group, every row of the day in exactly one."""
    data = processed(year)
    listed = [
        (day, slot, session)
        for day in schedule_days(year)
        for slot in timeline(data, day, ())
        for session in slot.sessions
    ]
    ids = [session.id for _, _, session in listed]
    assert len(ids) == len(set(ids))
    assert set(ids) == {s.id for s in data.sessions.values() if s.in_timeline}
    for day, slot, session in listed:
        assert (session.day, session.start) == (day, slot.start)
        assert slot.key == f"slot-{slot.start.isoformat()}"


@pytest.mark.parametrize("year", YEARS)
def test_slots_run_by_start_and_rows_by_shown_start_then_room(year: int) -> None:
    """DATA-30: the order is computed in the query, never by sorting shared lists."""
    data = processed(year)
    for day in schedule_days(year):
        slots = timeline(data, day, ())
        assert [slot.start for slot in slots] == sorted(slot.start for slot in slots)
        for slot in slots:
            assert list(slot.sessions) == sorted(slot.sessions, key=schedule_order)


def test_a_row_shown_earlier_leads_its_slot_and_rows_without_a_place_follow() -> None:
    """2026's Job Fair, shown at 9:30 in the 10:00 slot (DATA-11), comes first; then the
    break and the notice, which have no place; then the rooms."""
    slot = slot_at(processed(2026), "2026-05-17T10:00:00-07:00")
    assert slot.sessions[0].name.startswith("Job Fair")
    assert [s.display_location for s in slot.sessions][:5] == [
        "Expo Hall AB",
        "",
        "",
        "Room 102A",
        "Room 102B",
    ]


def test_rooms_sort_naturally_and_ignore_case() -> None:
    """D-31: room order matches the printed grid, not ASCII order."""
    rooms = ["Room 1000", "room 102B", "Room 102A", "S-3", "Grand Ballroom A", "Room 2"]
    sessions = sessions_like(
        *({"id": str(n), "display_location": room} for n, room in enumerate(rooms))
    )
    assert [s.display_location for s in sorted(sessions, key=schedule_order)] == [
        "Grand Ballroom A",
        "Room 2",
        "Room 102A",
        "room 102B",
        "Room 1000",
        "S-3",
    ]


def test_ties_on_start_and_room_break_by_name_then_id() -> None:
    sessions = sessions_like(
        {"id": "b", "name": "Same"},
        {"id": "z", "name": "Another"},
        {"id": "a", "name": "Same"},
    )
    for given in (sessions, sessions[::-1]):
        assert [s.id for s in sorted(given, key=schedule_order)] == ["z", "a", "b"]


@pytest.mark.parametrize("year", YEARS)
def test_a_day_without_sessions_has_no_slots(year: int) -> None:
    """The sprint days, and any date outside the feed, are empty, filtered or not."""
    data = processed(year)
    scheduled = {day.date for day in data.days}
    empty = [day for day in schedule_days(year) if day not in scheduled]
    assert empty  # both years have sprint days without sessions
    for day in [*empty, date(1999, 1, 1)]:
        assert timeline(data, day, ()) == ()
        assert timeline(data, day, ["Talk"]) == ()


@pytest.mark.parametrize("year", YEARS)
def test_excluding_every_track_leaves_every_day_empty(year: int) -> None:
    data = processed(year)
    every_track = {s.track for s in data.sessions.values()}
    for day in schedule_days(year):
        assert timeline(data, day, every_track) == ()


@pytest.mark.parametrize("year", YEARS)
def test_an_excluded_track_hides_its_rows_and_the_slots_it_empties(year: int) -> None:
    """SCHED-10: a session passes unless its track key is excluded."""
    data = processed(year)
    for day in schedule_days(year):
        expected = [
            (slot.key, [s.id for s in slot.sessions if s.track != "Open Space"])
            for slot in timeline(data, day, ())
        ]
        filtered = timeline(data, day, ["Open Space"])
        assert [(slot.key, [s.id for s in slot.sessions]) for slot in filtered] == [
            (key, ids) for key, ids in expected if ids
        ]


def test_the_default_filter_hides_open_spaces_and_nothing_else() -> None:
    """D-20: open spaces are hidden by default; every other track shows."""
    data, friday = processed(2026), date(2026, 5, 15)
    default = Prefs().excluded_tracks
    shown = {s.track for slot in timeline(data, friday, default) for s in slot.sessions}
    every = {s.track for slot in timeline(data, friday, ()) for s in slot.sessions}
    assert default == ("Open Space",)
    assert shown == every - {"Open Space"}


def test_one_string_is_not_a_filter() -> None:
    with pytest.raises(TypeError):
        timeline(processed(2026), date(2026, 5, 15), "Open Space")


@pytest.mark.parametrize("year", YEARS)
def test_the_same_feed_day_and_filter_give_the_same_objects(year: int) -> None:
    """D-153, D-178: identity is what lets memoised day lists, slots and rows skip work.

    The filter is a set: its order, repeats and type do not matter.
    """
    data = processed(year)
    for day in schedule_days(year):
        assert timeline(data, day, ()) is timeline(data, day, [])
        filtered = timeline(data, day, ("Open Space", "Talk"))
        assert timeline(data, day, ["Talk", "Open Space", "Talk"]) is filtered
        assert timeline(data, day, frozenset({"Open Space", "Talk"})) is filtered


@pytest.mark.parametrize("year", YEARS)
def test_a_filter_keeps_the_slots_it_does_not_touch(year: int) -> None:
    """A filter change re-renders only the slots whose rows changed (D-153)."""
    data = processed(year)
    for day in schedule_days(year):
        full = {slot.key: slot for slot in timeline(data, day, ())}
        for slot in timeline(data, day, ["Open Space"]):
            untouched = all(s.track != "Open Space" for s in full[slot.key].sessions)
            assert (slot is full[slot.key]) == untouched
            for session in slot.sessions:  # rows are the model's own sessions
                assert session is data.sessions[session.id]


def test_a_filter_that_hides_nothing_that_day_returns_the_whole_day() -> None:
    data, tutorials_day = processed(2026), date(2026, 5, 13)
    assert timeline(data, tutorials_day, ["Open Space"]) is timeline(
        data, tutorials_day, ()
    )


def test_a_new_feed_version_gets_its_own_results() -> None:
    """The memo is per feed: a refreshed model never shows the old model's rows."""
    old, new, friday = processed(2026), processed(2026), date(2026, 5, 15)
    before, after = timeline(old, friday, ()), timeline(new, friday, ())
    assert before is not after
    assert [[s.id for s in slot.sessions] for slot in before] == [
        [s.id for s in slot.sessions] for slot in after
    ]
    assert all(s is new.sessions[s.id] for slot in after for s in slot.sessions)


def test_the_memo_does_not_keep_a_replaced_feed_alive() -> None:
    data = processed(2026)
    timeline(data, date(2026, 5, 15), ["Open Space"])
    track_sessions(data, "Talk")
    gone = weakref.ref(data)
    del data
    gc.collect()
    assert gone() is None


@pytest.mark.parametrize("year", YEARS)
def test_a_track_page_lists_its_sessions_by_day_in_schedule_order(year: int) -> None:
    """DATA-20, SCHED-22: every session of the track once, under its own day."""
    data = processed(year)
    for track in {s.track for s in data.sessions.values()} - {"Poster"}:
        result = track_sessions(data, track)
        assert [group.day for group in result] == sorted({g.day for g in result})
        listed = [s for group in result for s in group.sessions]
        assert len(listed) == len({s.id for s in listed})
        assert {s.id for s in listed} == {
            s.id for s in data.sessions.values() if s.track == track
        }
        for group in result:
            assert group.sessions
            assert all(s.day == group.day for s in group.sessions)
            assert list(group.sessions) == sorted(group.sessions, key=schedule_order)


@pytest.mark.parametrize("year", YEARS)
def test_the_posters_track_lists_the_posters_not_the_posters_row(year: int) -> None:
    """SCHED-22: Ionic listed both the posters and the row they collapse into."""
    data = processed(year)
    listed = [s for group in track_sessions(data, "Poster") for s in group.sessions]
    assert len(listed) == len(data.posters) > 0
    assert all(s.id.startswith("poster-detail-") for s in listed)


def _without_posters(doc: dict[str, Any]) -> None:
    """Drop the posters from a feed: 2026's ``posters`` list, 2025's poster slot."""
    doc["posters"] = []
    for slot in doc["schedule"]:
        if slot.get("kind") == "poster":
            slot.pop("sessions", None)


@pytest.mark.parametrize("year", YEARS)
def test_before_posters_are_published_the_posters_track_lists_the_posters_row(
    year: int,
) -> None:
    """The page is never empty while the Schedule shows a Posters row."""
    data = process(changed(year, _without_posters), settings(year))
    assert data.posters == ()
    listed = [s for group in track_sessions(data, "Poster") for s in group.sessions]
    assert len(listed) == 1
    assert listed[0].kind == "poster" and listed[0].in_timeline


def test_a_track_page_ignores_the_schedule_filter() -> None:
    """Open spaces are hidden on the Schedule by default, yet all listed on their page."""
    data = processed(2026)
    assert "Open Space" in Prefs().excluded_tracks
    expected = {s.id for s in data.sessions.values() if s.track == "Open Space"}
    assert expected
    listed = [s for group in track_sessions(data, "Open Space") for s in group.sessions]
    assert {s.id for s in listed} == expected


def test_a_track_without_sessions_has_an_empty_page() -> None:
    assert track_sessions(processed(2026), "Sprint") == ()


def test_a_track_page_is_memoised_per_feed() -> None:
    data = processed(2026)
    assert track_sessions(data, "Talk") is track_sessions(data, "Talk")
    assert track_sessions(data, "Talk") is not track_sessions(processed(2026), "Talk")


def test_only_the_timeline_takes_the_schedule_filter() -> None:
    """D-20, SCHED-17: My schedule, Now and Search get queries that cannot filter.

    Every public query is checked, those added later included.
    """
    takers = {
        name
        for name, function in inspect.getmembers(queries, inspect.isfunction)
        if function.__module__ == queries.__name__
        and not name.startswith("_")
        and "excluded" in inspect.signature(function).parameters
    }
    assert takers == {"timeline"}


FILTER_USERS = {
    "timeline": {"core/queries.py", "screens/schedule.py"},
    "excluded_tracks": {"prefs.py", "screens/schedule.py"},
}
"""The modules that may name the Schedule's filter: its query, its preference and the
Schedule. The filter sheet (#87) adds its module here if it gets one of its own."""


def test_only_the_schedule_reads_the_filter_or_calls_the_timeline() -> None:
    """D-20: My schedule, Now, Search and the track pages never see the filter."""
    package = Path(queries.__file__).resolve().parents[1]
    found: dict[str, set[str]] = {name: set() for name in FILTER_USERS}
    for path in package.rglob("*.py"):
        module = path.relative_to(package).as_posix()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Name):
                names = {node.id}
            elif isinstance(node, ast.Attribute):
                names = {node.attr}
            elif isinstance(node, ast.ImportFrom):
                names = {alias.name for alias in node.names}
            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                names = {node.name}
            elif isinstance(node, ast.keyword | ast.arg) and node.arg:
                names = {node.arg}  # excluded_tracks=..., or a parameter of that name
            else:
                continue
            for name in names & found.keys():
                found[name].add(module)
    for name, modules in found.items():
        assert modules <= FILTER_USERS[name], name
    # The scan sees where they are defined, so it would see a use anywhere else.
    assert "core/queries.py" in found["timeline"]
    assert "prefs.py" in found["excluded_tracks"]
