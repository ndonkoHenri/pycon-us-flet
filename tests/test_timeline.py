"""Tests for the schedule queries: the timeline, the track filter and Jump to now.

#85: DATA-18, DATA-30, SCHED-16, SCHED-17; D-20, D-31, D-153, D-178. The track pages
and a Posters row's posters are tested in ``test_timeline_tracks.py``.
"""

import ast
import gc
import inspect
import weakref
from annotationlib import Format
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest

import pycon_us.core.timeline as timeline_module
from pycon_us.config import load_year
from pycon_us.core import agenda, queries, search
from pycon_us.core.models import ConferenceData, Session
from pycon_us.core.queries import days
from pycon_us.core.timeline import (
    NOW_KEY,
    NowPlace,
    Slot,
    now_place,
    schedule_order,
    timeline,
    track_sessions,
)
from pycon_us.prefs import Prefs
from tests.feeds import YEARS, processed

pytestmark = pytest.mark.usefixtures("machine_tz")


def schedule_days(year: int) -> tuple[date, ...]:
    """The Schedule's days of ``year``: every conference date, in order."""
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
    """A slot lists the row shown earliest first, then the rows without a place.

    2026's Job Fair, shown at 9:30 in the 10:00 slot (DATA-11), comes first; then the
    break and the notice, which have no place; then the rooms.
    """
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
    """Rows with the same start and room sort by name, then id, in any input order."""
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
    """Excluding every track of the feed leaves every day without slots."""
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
    """``timeline`` raises ``TypeError`` for a bare string as the filter."""
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
    """A filter that hides nothing on a day gives that day's unfiltered slots."""
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
    """The timeline and track memos let a dropped feed be garbage-collected."""
    data = processed(2026)
    timeline(data, date(2026, 5, 15), ["Open Space"])
    track_sessions(data, "Talk")
    gone = weakref.ref(data)
    del data
    gc.collect()
    assert gone() is None


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
        # Names only: a type core takes from the year data exists only for the type
        # checker (D-67), so its annotation stays a forward reference.
        and "excluded"
        in inspect.signature(function, annotation_format=Format.FORWARDREF).parameters
    }
    assert takers == {"timeline"}


FILTER_USERS = {
    "timeline": {
        "core/timeline.py",
        "screens/schedule.py",
        "screens/schedule_slots.py",  # the Schedule's day lists (#708)
    },
    "excluded_tracks": {
        "prefs.py",
        "screens/schedule.py",
        "screens/schedule_filter.py",
    },
}
"""The modules that may name the Schedule's filter: its query, its preference, the
Schedule (with its day lists' data) and its filter (#87, which edits the preference; its sheet module is given the
hidden keys and names neither). The module ``core/timeline.py`` shares the function's
name, so outside the Schedule import its names directly
(``from pycon_us.core.timeline import DaySessions``); ``from pycon_us.core import
timeline`` trips this scan (D-185)."""


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
    """Friday, May 15, 2026 at ``hour``:``minute``, conference time."""
    return datetime(2026, 5, 15, hour, minute, tzinfo=PACIFIC)


def friday_slots() -> tuple[Slot, ...]:
    """Friday's 2026 slots under the default filter."""
    return timeline(processed(2026), FRIDAY, Prefs().excluded_tracks)


def test_the_jump_lands_on_the_slot_that_is_on() -> None:
    """2:00 PM's talks run to 2:30 PM: at 2:10 that slot is on, the line under it."""
    slots = friday_slots()
    place = now_place(slots, friday_at(14, 10))
    assert place.on == place.target == "slot-2026-05-15T14:00:00-07:00"
    assert slots[place.line - 1].key == place.on  # the line follows the slot that is on


def test_a_slot_counts_from_its_first_minute() -> None:
    """A slot is on from the minute it starts."""
    place = now_place(friday_slots(), friday_at(14))
    assert place.on == "slot-2026-05-15T14:00:00-07:00"


def test_once_a_slot_is_over_the_jump_lands_on_the_line_above_the_next() -> None:
    """Once a slot is over, nothing is on and the jump targets the line (D-204).

    At 2:35 the 2:00 PM slot is over; the line sits above 2:45 PM, and so the jump
    shows the line and the slot that comes next together.
    """
    slots = friday_slots()
    place = now_place(slots, friday_at(14, 35))
    assert place.on is None and place.target == NOW_KEY
    assert slots[place.line].key == "slot-2026-05-15T14:45:00-07:00"


def test_a_long_session_earlier_does_not_hold_the_jump_back() -> None:
    """The 1:45 PM slot holds a summit until 5:45 PM; at 2:35 the jump goes on."""
    slots = friday_slots()
    earlier = next(s for s in slots if s.key == "slot-2026-05-15T13:45:00-07:00")
    assert any(s.end > friday_at(14, 35) for s in earlier.sessions)
    assert now_place(slots, friday_at(14, 35)).target != earlier.key


def test_before_the_day_the_line_tops_the_list() -> None:
    """Before the day's first slot the line is at the top and no slot is on."""
    assert now_place(friday_slots(), friday_at(6)) == NowPlace(0, None)


def test_after_the_day_the_line_ends_the_list() -> None:
    """After the day's last slot the line is at the end and no slot is on."""
    slots = friday_slots()
    assert now_place(slots, friday_at(23, 30)) == NowPlace(len(slots), None)


def test_a_slot_of_notices_alone_is_over_once_it_starts() -> None:
    """7:30 AM holds only "Registration Desk Opens", which has no duration."""
    slots = friday_slots()
    assert {s.track for s in slots[0].sessions} == {"Informational"}
    assert now_place(slots, friday_at(7, 31)) == NowPlace(1, None)


def test_without_slots_the_line_is_all_there_is() -> None:
    """With no slots, the line is the list's only item and nothing is on."""
    assert now_place((), friday_at(10)) == NowPlace(0, None)


def test_the_target_is_always_an_item_the_filtered_day_shows() -> None:
    """D-178: a slot the filter leaves out has no item to scroll to; the line has one."""
    slots = friday_slots()
    keys = {s.key for s in slots} | {NOW_KEY}
    instants = [friday_at(h, m) for h in range(6, 24) for m in (0, 20, 40)]
    assert all(now_place(slots, at).target in keys for at in instants)
    assert all(0 <= now_place(slots, at).line <= len(slots) for at in instants)
