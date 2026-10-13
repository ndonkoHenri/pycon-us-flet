"""Tests for the queries over the processed feed (architecture §7.5).

DATA-17's days, D-46's fold, the schedule queries of #85 (DATA-18, DATA-20, DATA-30,
SCHED-17), and the agenda and Now & Next queries of #93 (SCHED-25, NEW-01).
"""

import ast
import gc
import inspect
import weakref
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from pycon_us.config import load_year
from pycon_us.core import queries
from pycon_us.core.feed import process
from pycon_us.core.models import ConferenceData, Session
from pycon_us.core.queries import (
    Agenda,
    AgendaDay,
    AgendaSlot,
    NowNext,
    Phase,
    Slot,
    days,
    fold,
    my_schedule,
    next_for_me,
    now_next,
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


# --- Agenda and Now & Next (D-14, D-179; SCHED-25, NEW-01) ----------------------------


def may(year: int, day: int, hour: int, minute: int = 0) -> datetime:
    """An instant in May of ``year``, in that year's conference zone."""
    zone = load_year(year).conference.zone
    return datetime(year, 5, day, hour, minute, tzinfo=zone)


def test_before_the_conference_the_first_slot_is_up_next() -> None:
    assert now_next(processed(2026), may(2026, 13, 7, 29)) == NowNext(
        Phase.BEFORE, (), may(2026, 13, 7, 30), ("196",)
    )


def test_months_before_the_conference_it_is_still_before() -> None:
    result = now_next(processed(2026), datetime(2026, 1, 1, tzinfo=UTC))
    assert (result.phase, result.next_start) == (Phase.BEFORE, may(2026, 13, 7, 30))


def test_the_day_starts_with_its_first_slot_and_a_notice_is_never_happening() -> None:
    result = now_next(processed(2026), may(2026, 13, 7, 30))
    assert result.phase is Phase.DAY
    assert result.happening == ()  # "Registration Desk Opens" lasts no time
    assert result.next_start == may(2026, 13, 9)


def test_a_session_ending_exactly_at_now_is_no_longer_happening() -> None:
    """P1 exit criterion 2: Now respects end times (Ionic kept the slot until midnight)."""
    result = now_next(processed(2026), may(2026, 13, 12, 30))
    # The morning tutorials end at 12:30, as the lunch break starts.
    assert result.happening == ("break--2026-05-13T12:30:00-07:00",)
    assert (result.next_start, result.up_next) == (
        may(2026, 13, 13, 30),
        ("188", "16", "57", "56", "83"),
    )


def test_a_session_is_happening_until_the_minute_it_ends() -> None:
    data = processed(2026)  # the Friday keynote runs from 9:45 to 10:30 AM
    assert "153" not in now_next(data, may(2026, 15, 9, 44)).happening
    assert "153" in now_next(data, may(2026, 15, 9, 45)).happening
    assert "153" in now_next(data, may(2026, 15, 10, 29)).happening
    assert "153" not in now_next(data, may(2026, 15, 10, 30)).happening


def test_between_slots_nothing_is_happening_and_the_day_goes_on() -> None:
    """After the afternoon tutorials, the day's last item is a notice at 6:00 PM."""
    assert now_next(processed(2026), may(2026, 13, 17, 30)) == NowNext(
        Phase.DAY, (), may(2026, 13, 18), ("197",)
    )


def test_happening_now_lists_sessions_by_start() -> None:
    result = now_next(processed(2026), may(2026, 14, 10))
    tutorials = ["106", "107", "112"]  # from 9:00
    workshops = ["111", "803", "200"]  # from 9:30
    positions = [result.happening.index(i) for i in tutorials + workshops]
    assert max(positions[:3]) < min(positions[3:])


def test_the_last_slot_of_a_day_runs_to_its_end_and_tomorrow_is_up_next() -> None:
    """The PyLadies Auction (6:45 to 10:30 PM) ends the Saturday."""
    late = now_next(processed(2026), may(2026, 16, 21))
    assert (late.phase, late.happening) == (Phase.DAY, ("223",))
    assert late.next_start == may(2026, 17, 8)
    assert late.up_next == (
        "226",
        "225",
        "break-Expo Hall AB-2026-05-17T08:00:00-07:00",
        "175",
    )


@pytest.mark.parametrize(
    ("day", "hour", "minute"),
    [
        (16, 22, 30),  # the moment the day's last session ends
        (17, 3, 0),  # the night
        (17, 7, 59),  # the morning, before the day's first slot
    ],
)
def test_between_days_nothing_is_happening_and_the_next_day_is_up_next(
    day: int, hour: int, minute: int
) -> None:
    result = now_next(processed(2026), may(2026, day, hour, minute))
    assert (result.phase, result.happening) == (Phase.BETWEEN_DAYS, ())
    assert result.next_start == may(2026, 17, 8)


def test_the_closing_day_runs_to_its_last_notice() -> None:
    data = processed(2026)
    closing = now_next(data, may(2026, 17, 17, 10))
    assert closing.happening == ("9056", "185")  # the 5:00 PM open space, then Closing
    assert (closing.next_start, closing.up_next) == (may(2026, 17, 20), ("234",))
    assert now_next(data, may(2026, 17, 19, 59)) == NowNext(
        Phase.DAY, (), may(2026, 17, 20), ("234",)
    )


@pytest.mark.parametrize(
    "instant", [(2026, 5, 17, 20), (2026, 5, 18, 10), (2027, 1, 1, 0)]
)
def test_after_the_conference_nothing_is_on_or_next(
    instant: tuple[int, int, int, int],
) -> None:
    """The sprint days have no sessions in the feed, so they come after it."""
    year, month, day, hour = instant
    now = datetime(year, month, day, hour, tzinfo=load_year(2026).conference.zone)
    assert now_next(processed(2026), now) == NowNext(Phase.AFTER, (), None, ())


@pytest.mark.parametrize(
    ("year", "first", "last_end"),
    [(2025, (14, 7, 0), (18, 20, 0)), (2026, (13, 7, 30), (17, 20, 0))],
)
def test_the_phase_turns_at_the_first_start_and_the_last_end(
    year: int, first: tuple[int, int, int], last_end: tuple[int, int, int]
) -> None:
    data, minute = processed(year), timedelta(minutes=1)
    assert now_next(data, may(year, *first) - minute).phase is Phase.BEFORE
    assert now_next(data, may(year, *first)).phase is Phase.DAY
    assert now_next(data, may(year, *last_end) - minute).phase is Phase.DAY
    assert now_next(data, may(year, *last_end)).phase is Phase.AFTER


def test_the_zone_of_now_does_not_matter() -> None:
    data, local = processed(2026), may(2026, 15, 10, 15)
    assert now_next(data, local.astimezone(UTC)) == now_next(data, local)


def test_now_ignores_filters_and_leaves_poster_details_to_the_posters_row() -> None:
    """Open spaces, hidden on the Schedule by default (D-20), are on Now."""
    data = processed(2026)
    assert {"9106", "9042"} <= set(now_next(data, may(2026, 15, 10, 15)).happening)
    posters = now_next(data, may(2026, 17, 10)).happening
    assert "poster-Expo Hall AB-2026-05-17T09:30:00-07:00" in posters
    assert not [i for i in posters if i.startswith("poster-detail-")]


def test_the_same_answer_at_two_instants_compares_equal() -> None:
    """Now recomputes every 60 s and memoises on the value (D-153)."""
    data = processed(2026)
    assert now_next(data, may(2026, 15, 10, 16)) == now_next(
        data, may(2026, 15, 10, 20)
    )
    assert hash(now_next(data, may(2026, 15, 10, 16)))


def test_the_next_session_is_a_saved_one_starting_within_three_hours() -> None:
    data, saved = processed(2026), frozenset({"153"})  # 9:45 to 10:30 AM
    assert next_for_me(data, saved, may(2026, 15, 6, 44)) is None
    assert next_for_me(data, saved, may(2026, 15, 6, 45)) == "153"  # exactly 3 h ahead


def test_the_next_session_stays_while_it_is_on_and_goes_when_it_ends() -> None:
    data, saved = processed(2026), frozenset({"153"})
    assert next_for_me(data, saved, may(2026, 15, 10, 29)) == "153"
    assert next_for_me(data, saved, may(2026, 15, 10, 30)) is None


def test_a_saved_session_that_is_on_comes_before_one_starting_soon() -> None:
    data = processed(2026)
    saved = frozenset({"2", "188"})  # tutorials 9:00 to 12:30 and 1:30 to 5:00 PM
    assert next_for_me(data, saved, may(2026, 13, 12)) == "2"
    assert next_for_me(data, saved, may(2026, 13, 12, 30)) == "188"


def test_the_next_session_ignores_unsaved_and_unknown_ids() -> None:
    data = processed(2026)
    assert next_for_me(data, frozenset(), may(2026, 15, 9)) is None
    assert next_for_me(data, frozenset({"no-such-id"}), may(2026, 15, 9)) is None


def test_a_saved_poster_can_be_the_next_session() -> None:
    saved = frozenset({"poster-detail-60"})
    assert next_for_me(processed(2026), saved, may(2026, 17, 9)) == "poster-detail-60"


def test_my_schedule_lists_saved_sessions_by_day_and_slot_in_timeline_order() -> None:
    saved = frozenset({"188", "19", "2", "153", "9106", "no-such-id"})
    assert my_schedule(processed(2026), saved).days == (
        AgendaDay(
            date(2026, 5, 13),
            (
                AgendaSlot(may(2026, 13, 9), ("2", "19")),  # Room 101A, then 101B
                AgendaSlot(may(2026, 13, 13, 30), ("188",)),
            ),
        ),
        AgendaDay(
            date(2026, 5, 15),
            (
                AgendaSlot(may(2026, 15, 9, 45), ("153",)),
                AgendaSlot(may(2026, 15, 10), ("9106",)),  # an open space: no filters
            ),
        ),
    )


def test_my_schedule_lists_a_saved_poster_on_its_day() -> None:
    agenda = my_schedule(processed(2026), frozenset({"poster-detail-60"}))
    slot = AgendaSlot(may(2026, 17, 9, 30), ("poster-detail-60",))
    assert agenda.days == (AgendaDay(date(2026, 5, 17), (slot,)),)


def test_nothing_saved_is_an_empty_agenda() -> None:
    assert my_schedule(processed(2026), frozenset()) == Agenda((), {})


def test_two_saved_sessions_at_the_same_time_overlap_each_other() -> None:
    agenda = my_schedule(processed(2026), frozenset({"2", "19", "188"}))
    assert agenda.overlaps == {"2": ("19",), "19": ("2",)}


def test_overlaps_follow_a_chain_without_joining_its_ends() -> None:
    """Education Summit 9:00-4:30, Typing Summit 1:00-5:00, Newcomer Orientation 4:30-5:00.

    The first and the last only touch, so they do not overlap.
    """
    agenda = my_schedule(processed(2026), frozenset({"199", "201", "146"}))
    assert agenda.overlaps == {"199": ("201",), "201": ("199", "146"), "146": ("201",)}


def test_one_long_session_overlaps_each_session_inside_it_in_agenda_order() -> None:
    """A tutorial 9:00-12:30 and two sponsor workshops, 9:30-10:30 and 11:30-12:30."""
    agenda = my_schedule(processed(2026), frozenset({"22", "111", "106"}))
    assert agenda.overlaps == {"106": ("111", "22"), "111": ("106",), "22": ("106",)}


def test_back_to_back_sessions_do_not_overlap() -> None:
    """The Friday welcome, PSF welcome and keynote: 9:00-9:25, 9:25-9:45, 9:45-10:30."""
    assert my_schedule(processed(2026), frozenset({"151", "152", "153"})).overlaps == {}


def test_a_notice_overlaps_nothing() -> None:
    """A notice has no star, but a synced list could hold one: it lasts no time."""
    saved = frozenset(
        {"219", "220"}
    )  # "Swag Pickup Closes" at 1:30, in a 12:30-2:00 lunch
    assert my_schedule(processed(2026), saved).overlaps == {}


def test_the_same_saved_sessions_give_an_equal_agenda() -> None:
    """My schedule memoises on the value (D-153)."""
    data, saved = processed(2026), frozenset({"2", "19", "153"})
    assert my_schedule(data, saved) == my_schedule(data, set(saved))
    assert hash(my_schedule(data, saved))


@pytest.mark.parametrize(
    "ask",
    [
        lambda data, naive: now_next(data, naive),
        lambda data, naive: next_for_me(data, frozenset({"153"}), naive),
    ],
)
def test_a_naive_now_is_refused(
    ask: Callable[[ConferenceData, datetime], object],
) -> None:
    with pytest.raises(ValueError, match="aware"):
        ask(processed(2026), datetime(2026, 5, 15, 10))  # noqa: DTZ001
