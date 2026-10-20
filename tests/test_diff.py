"""The change log's diff over feed pairs (D-47, D-255; NEW-04).

Each pair is the recorded feed and a copy with named edits (``tests/feeds.py``), both
processed by the current code, as the app diffs a refresh. The recorded side of a pair is
processed once per year; only the edited side is processed per test.
"""

from dataclasses import replace
from datetime import datetime, timedelta
from functools import cache
from zoneinfo import ZoneInfo

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pycon_us.core.diff import Change, ChangeKind, Listing, diff
from pycon_us.core.feed import process
from pycon_us.core.models import ConferenceData, Session
from tests.feeds import (
    YEARS,
    Edit,
    add,
    move,
    pair,
    processed,
    recorded,
    remove,
    rename,
    retime,
    settings,
)

PACIFIC = ZoneInfo("America/Los_Angeles")
EASTERN = ZoneInfo("America/New_York")
TALK = 142
"""2026's "Python for Humans …", in Grand Ballroom A, Saturday 10:30 to 11:00 AM."""
TITLE = "Python for Humans - Designing Python Code Like a User Interface"


@cache
def recorded_model(year: int) -> ConferenceData:
    """The recorded feed of ``year``, processed once for the whole module."""
    return processed(year)


def changes(year: int, *edits: Edit) -> list[Change]:
    """The diff from the recorded feed of ``year`` to a copy with ``edits`` applied."""
    _, new = pair(year, *edits)
    return diff(recorded_model(year), process(new, settings(year)))


def pacific(day: int, hour: int, minute: int = 0) -> datetime:
    """May ``day``, 2026, at ``hour``:``minute``, Pacific time."""
    return datetime(2026, 5, day, hour, minute, tzinfo=PACIFIC)


RECORDED = Listing(
    title=TITLE,
    start=pacific(16, 10, 30),
    end=pacific(16, 11),
    location="Grand Ballroom A",
)
"""The talk's listing in the recorded feed."""


def talk(**values: object) -> Listing:
    """The talk's recorded listing with ``values`` (its fields' new values) changed."""
    return replace(RECORDED, **values)


def test_a_room_move_is_one_room_change_with_both_rooms() -> None:
    """A talk moved to another room gives one room change, from its room to the new one."""
    assert changes(2026, move(TALK, "Room 101B")) == [
        Change("142", ChangeKind.ROOM, talk(), talk(location="Room 101B"))
    ]


def test_a_later_start_is_a_time_change() -> None:
    """A talk that starts 15 minutes later, ending as before, gives one time change."""
    edit = retime(TALK, "2026-05-16T10:45:00-07:00", "2026-05-16T11:00:00-07:00")
    assert changes(2026, edit) == [
        Change("142", ChangeKind.TIME, talk(), talk(start=pacific(16, 10, 45)))
    ]


def test_a_later_end_alone_is_a_time_change() -> None:
    """A talk that ends 15 minutes later, starting as before, gives one time change."""
    edit = retime(TALK, "2026-05-16T10:30:00-07:00", "2026-05-16T11:15:00-07:00")
    assert changes(2026, edit) == [
        Change("142", ChangeKind.TIME, talk(), talk(end=pacific(16, 11, 15)))
    ]


@pytest.mark.usefixtures("machine_tz")
def test_a_move_to_another_day_is_a_time_change_on_the_new_day() -> None:
    """A talk moved from Saturday to Sunday afternoon is one time change, in any zone."""
    edit = retime(TALK, "2026-05-17T14:00:00-07:00", "2026-05-17T14:30:00-07:00")
    assert changes(2026, edit) == [
        Change(
            "142",
            ChangeKind.TIME,
            talk(),
            talk(start=pacific(17, 14), end=pacific(17, 14, 30)),
        )
    ]


def test_a_rename_is_a_title_change_listed_under_the_new_title() -> None:
    """A renamed talk gives one title change, whose title is the new name."""
    [change] = changes(2026, rename(TALK, "Python for People"))
    assert change == Change(
        "142", ChangeKind.TITLE, talk(), talk(title="Python for People")
    )
    assert change.title == "Python for People"


def test_a_name_that_cleans_to_the_same_title_is_no_change() -> None:
    """Markup the parser strips from a name changes nothing: the cleaned names compare."""
    assert changes(2026, rename(TALK, f"<em>{TITLE}</em>")) == []


def test_an_added_session_has_only_a_new_listing() -> None:
    """A new slot gives one addition, with no old listing and the new one's values."""
    [change] = changes(2026, add(5000, like=TALK, name="A late addition"))
    assert change == Change(
        "5000", ChangeKind.ADDED, None, talk(title="A late addition")
    )
    assert change.title == "A late addition"


def test_a_removed_session_keeps_its_last_title_time_and_room() -> None:
    """A dropped slot gives one removal, whose old listing is all the item shows (D-255)."""
    [change] = changes(2026, remove(TALK))
    assert change == Change("142", ChangeKind.REMOVED, talk(), None)
    assert change.title == TITLE


def test_a_moved_break_is_not_reported() -> None:
    """A coffee break that starts later gets a new collapsed id, and the diff skips both."""
    edit = retime(150, "2026-05-15T08:30:00-07:00", "2026-05-15T09:00:00-07:00")
    _, new = pair(2026, edit)
    ids = set(process(new, settings(2026)).sessions)
    assert "break-Expo Hall AB-2026-05-15T08:00:00-07:00" not in ids
    assert "break-Expo Hall AB-2026-05-15T08:30:00-07:00" in ids
    assert changes(2026, edit) == []


def test_a_poster_moved_within_the_posters_row_is_not_reported() -> None:
    """A poster slot moved inside the Posters row's span changes no session at all."""
    edit = retime(11, "2026-05-17T09:50:00-07:00", "2026-05-17T09:55:00-07:00")
    assert changes(2026, edit) == []


def test_an_earlier_posters_row_and_its_posters_are_not_reported() -> None:
    """A Posters row moved earlier gives no change: its id is new, its posters are skipped."""
    edit = retime(62, "2026-05-17T09:00:00-07:00", "2026-05-17T09:05:00-07:00")
    _, new = pair(2026, edit)
    posters = [
        s for s in process(new, settings(2026)).sessions.values() if s.kind == "poster"
    ]
    assert {s.start for s in posters if not s.in_timeline} == {pacific(17, 9)}
    assert changes(2026, edit) == []


def test_the_job_fair_keeps_its_shown_start_on_both_sides() -> None:
    """The Job Fair's listings start 30 minutes before its slot, as its row does (DATA-11)."""
    edit = retime(178, "2026-05-17T10:30:00-07:00", "2026-05-17T13:00:00-07:00")
    [change] = changes(2026, edit)
    assert change.kind == ChangeKind.TIME
    assert change.old is not None and change.new is not None
    assert (change.old.start, change.new.start) == (pacific(17, 9, 30), pacific(17, 10))


def test_several_changes_to_one_session_come_as_time_room_title() -> None:
    """A talk retimed, moved and renamed gives three changes, one per kind, in order."""
    found = changes(
        2026,
        rename(TALK, "Python for People"),
        move(TALK, "Room 101B"),
        retime(TALK, "2026-05-16T11:30:00-07:00", "2026-05-16T12:00:00-07:00"),
    )
    new = talk(
        title="Python for People",
        start=pacific(16, 11, 30),
        end=pacific(16, 12),
        location="Room 101B",
    )
    assert found == [
        Change("142", kind, talk(), new)
        for kind in (ChangeKind.TIME, ChangeKind.ROOM, ChangeKind.TITLE)
    ]


def test_changes_come_by_new_start_or_a_removals_old_start() -> None:
    """Additions, moves and removals interleave by start (a removal's is its old one)."""
    found = changes(
        2026,
        remove(TALK),
        move(51, "Room 101B"),
        add(5000, like=19, name="Early bird"),
        retime(90, "2026-05-13T09:00:00-07:00", "2026-05-13T09:30:00-07:00"),
    )
    assert [(c.id, c.kind) for c in found] == [
        ("5000", ChangeKind.ADDED),
        ("90", ChangeKind.TIME),
        ("142", ChangeKind.REMOVED),
        ("51", ChangeKind.ROOM),
    ]


def test_same_start_same_kind_changes_go_by_id_as_text() -> None:
    """Two room moves at one start come by id as text, "1142" before "90", not feed order."""
    found = changes(2026, move(90, "Room 101B"), move(1142, "Room 101C"))
    assert [c.id for c in found] == ["1142", "90"]


def test_at_one_start_id_comes_before_kind() -> None:
    """At one start, 142's room change comes before 51's removal: id, then kind."""
    found = changes(2026, remove(51), move(TALK, "Room 101B"))
    assert [(c.id, c.kind) for c in found] == [
        ("142", ChangeKind.ROOM),
        ("51", ChangeKind.REMOVED),
    ]


@pytest.mark.usefixtures("machine_tz")
def test_a_retime_on_the_eastern_2025_feed_is_in_eastern_time() -> None:
    """2025's talk 104 moved half an hour later reads 11:00 AM Eastern, in any zone."""
    edit = retime(104, "2025-05-17T11:00:00-04:00", "2025-05-17T11:30:00-04:00")
    [change] = changes(2025, edit)
    assert change.kind == ChangeKind.TIME
    assert change.old == Listing(
        title="Finding 2.0",
        start=datetime(2025, 5, 17, 10, 30, tzinfo=EASTERN),
        end=datetime(2025, 5, 17, 11, tzinfo=EASTERN),
        location="Ballroom A",
    )
    assert change.new is not None
    assert change.new.start == datetime(2025, 5, 17, 11, tzinfo=EASTERN)
    assert change.new.start.utcoffset() == timedelta(hours=-4)


@pytest.mark.parametrize("year", YEARS)
def test_a_feed_against_itself_has_no_change(year: int) -> None:
    """One processed feed on both sides gives an empty diff."""
    data = recorded_model(year)
    assert diff(data, data) == []


@pytest.mark.parametrize("year", YEARS)
def test_the_same_bytes_parsed_twice_have_no_change(year: int) -> None:
    """Two models parsed from one feed's bytes share no object and give an empty diff."""
    first, second = (process(recorded(year), settings(year)) for _ in range(2))
    key = next(iter(first.sessions))
    assert first.sessions[key] is not second.sessions[key]
    assert diff(first, second) == []


type Step = tuple[str, str, str | int]
"""One edit of a model: a session id, what is done to it and the drawn value."""

STEPS: dict[str, st.SearchStrategy[str | int]] = {
    "remove": st.just(0),
    "retime": st.integers(-600, 600).filter(bool),
    "stretch": st.integers(1, 600),
    "move": st.text(max_size=12),
    "rename": st.text(max_size=12),
}
"""Each edit of an existing session, with its value: minutes, or a room or title."""


@st.composite
def plans(draw: st.DrawFn) -> tuple[Step, ...]:
    """A few edits of 2026's recorded sessions, and a few additions.

    Any session may be drawn, collapsed rows included. An addition is a copy of a drawn
    session under a new id (``added-<n>``). Plans are drawn, not models,
    so a failing example prints a few steps rather than a whole feed.
    """
    ids = sorted(recorded_model(2026).sessions)
    steps: list[Step] = []
    for key in draw(st.lists(st.sampled_from(ids), unique=True, max_size=6)):
        edit = draw(st.sampled_from(sorted(STEPS)))
        steps.append((key, edit, draw(STEPS[edit])))
    for n in range(draw(st.integers(0, 3))):
        steps.append((f"added-{n}", "add", draw(st.sampled_from(ids))))
    return tuple(steps)


def applied(plan: tuple[Step, ...]) -> ConferenceData:
    """2026's recorded model with ``plan``'s steps applied to a copy of its sessions."""
    data = recorded_model(2026)
    sessions = dict(data.sessions)
    for key, edit, value in plan:
        if edit == "add":
            sessions[key] = replace(data.sessions[str(value)], id=key)
        elif edit == "remove":
            del sessions[key]
        else:
            sessions[key] = _edited(sessions[key], edit, value)
    return replace(data, sessions=sessions)


def _edited(session: Session, edit: str, value: str | int) -> Session:
    """``session`` retimed or stretched by ``value`` minutes, or moved or renamed."""
    if edit == "move":
        return replace(session, location=str(value))
    if edit == "rename":
        return replace(session, name=str(value))
    shift = timedelta(minutes=int(value))
    if edit == "stretch":
        return replace(session, end=session.end + shift)
    return replace(
        session,
        start=session.start + shift,
        display_start=session.display_start + shift,
        end=session.end + shift,
    )


def swapped(change: Change) -> Change:
    """``change`` as the diff in the other direction states it."""
    kind = {ChangeKind.ADDED: ChangeKind.REMOVED, ChangeKind.REMOVED: ChangeKind.ADDED}
    return Change(change.id, kind.get(change.kind, change.kind), change.new, change.old)


@given(plans(), plans())
def test_swapping_sides_swaps_additions_removals_and_values(
    first: tuple[Step, ...], second: tuple[Step, ...]
) -> None:
    """``diff(b, a)`` holds exactly ``diff(a, b)``'s changes with the sides swapped."""
    old, new = applied(first), applied(second)
    forward, backward = diff(old, new), diff(new, old)
    assert len(set(forward)) == len(forward)
    assert {swapped(c) for c in forward} == set(backward)
    assert len(backward) == len(forward)
