"""Tests for the schedule queries: the timeline, the track filter and track pages.

#85: DATA-18, DATA-20, DATA-30, SCHED-17; D-20, D-31, D-153, D-178.
"""

import ast
import gc
import inspect
import weakref
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest

import pycon_us.core.timeline as timeline_module
from pycon_us.config import load_year
from pycon_us.core import agenda, queries, search
from pycon_us.core.feed import process
from pycon_us.core.models import ConferenceData, Session
from pycon_us.core.queries import days
from pycon_us.core.timeline import (
    Slot,
    current_slot_key,
    schedule_order,
    timeline,
    track_sessions,
)
from pycon_us.prefs import Prefs
from tests.feeds import YEARS, changed, processed, settings

pytestmark = pytest.mark.usefixtures("machine_tz")


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
    for order in (sessions, sessions[::-1]):
        assert [s.id for s in sorted(order, key=schedule_order)] == ["z", "a", "b"]


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

    Every public query of the query modules is checked, those added later included.
    """
    takers = {
        name
        for module in (queries, timeline_module, agenda, search)
        for name, function in inspect.getmembers(module, inspect.isfunction)
        if function.__module__ == module.__name__
        and not name.startswith("_")
        and "excluded" in inspect.signature(function).parameters
    }
    assert takers == {"timeline"}


FILTER_USERS = {
    "timeline": {"core/timeline.py", "screens/schedule.py"},
    "excluded_tracks": {
        "prefs.py",
        "screens/schedule.py",
        "screens/schedule_filter.py",
    },
}
"""The modules that may name the Schedule's filter: its query, its preference, the
Schedule and its filter (#87, which edits the preference; its sheet module is given the
hidden keys and names neither). The module ``core/timeline.py`` shares the function's name, so outside the Schedule import
its names directly (``from pycon_us.core.timeline import DaySessions``);
``from pycon_us.core import timeline`` trips this scan (D-185)."""


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
    assert "core/timeline.py" in found["timeline"]
    assert "prefs.py" in found["excluded_tracks"]


# ------------------------------------------------------------------ Jump to now (SCHED-16)

PACIFIC = load_year(2026).conference.zone
FRIDAY = date(2026, 5, 15)


def friday_at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 5, 15, hour, minute, tzinfo=PACIFIC)


def friday_slots() -> tuple[Slot, ...]:
    return timeline(processed(2026), FRIDAY, Prefs().excluded_tracks)


def test_the_jump_lands_on_the_slot_that_is_on() -> None:
    """2:00 PM's talks run to 2:30 PM: at 2:10 that slot is the current one."""
    assert current_slot_key(friday_slots(), friday_at(14, 10)) == (
        "slot-2026-05-15T14:00:00-07:00"
    )


def test_a_slot_counts_from_its_first_minute() -> None:
    assert current_slot_key(friday_slots(), friday_at(14)) == (
        "slot-2026-05-15T14:00:00-07:00"
    )


def test_once_a_slot_is_over_the_jump_lands_on_the_next_one() -> None:
    """At 2:35 the 2:00 PM slot is over; the next one starts at 2:45 PM."""
    assert current_slot_key(friday_slots(), friday_at(14, 35)) == (
        "slot-2026-05-15T14:45:00-07:00"
    )


def test_a_long_session_earlier_does_not_hold_the_jump_back() -> None:
    """The 1:45 PM slot holds a summit until 5:45 PM; at 2:35 the jump goes on."""
    slots = friday_slots()
    earlier = next(s for s in slots if s.key == "slot-2026-05-15T13:45:00-07:00")
    assert any(s.end > friday_at(14, 35) for s in earlier.sessions)
    assert current_slot_key(slots, friday_at(14, 35)) != earlier.key


def test_before_the_day_the_jump_lands_on_its_first_slot() -> None:
    slots = friday_slots()
    assert current_slot_key(slots, friday_at(6)) == slots[0].key


def test_after_the_day_the_jump_lands_on_its_last_slot() -> None:
    slots = friday_slots()
    assert current_slot_key(slots, friday_at(23, 30)) == slots[-1].key


def test_a_slot_of_notices_alone_is_over_once_it_starts() -> None:
    """7:30 AM holds only "Registration Desk Opens", which has no duration."""
    slots = friday_slots()
    assert {s.track for s in slots[0].sessions} == {"Informational"}
    assert current_slot_key(slots, friday_at(7, 31)) == slots[1].key


def test_without_slots_there_is_nowhere_to_jump() -> None:
    assert current_slot_key((), friday_at(10)) is None


def test_the_key_is_always_one_the_filtered_day_shows() -> None:
    """D-178: a slot the filter leaves out has no item to scroll to."""
    slots = friday_slots()
    keys = {s.key for s in slots}
    assert all(current_slot_key(slots, friday_at(h)) in keys for h in range(6, 24))
