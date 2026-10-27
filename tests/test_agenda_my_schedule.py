"""Tests for My schedule's agenda and its overlaps, and the refusal of a naive now.

#93: NEW-01; D-43, D-153.
"""

from collections.abc import Callable
from datetime import date, datetime

import pytest

from pycon_us.core.agenda import (
    Agenda,
    elapsed_percent,
    my_schedule,
    next_for_me,
    now_next,
)
from pycon_us.core.models import ConferenceData
from pycon_us.core.timeline import timeline
from tests.agenda_answers import POSTERS_ROW, agenda_ids, may, next_id, overlap_ids
from tests.feeds import processed

pytestmark = pytest.mark.usefixtures("machine_tz")


def test_my_schedule_lists_saved_sessions_by_day_and_slot_in_timeline_order() -> None:
    """My schedule groups saved sessions by day and slot in timeline order.

    An id not in the feed is dropped, and an open space is listed: My schedule has no
    filters.
    """
    saved = frozenset({"188", "19", "2", "153", "9106", "no-such-id"})
    assert agenda_ids(my_schedule(processed(2026), saved)) == [
        (
            date(2026, 5, 13),
            [
                (may(2026, 13, 9), ("2", "19")),  # Room 101A, then 101B
                (may(2026, 13, 13, 30), ("188",)),
            ],
        ),
        (
            date(2026, 5, 15),
            [
                (may(2026, 15, 9, 45), ("153",)),
                (may(2026, 15, 10), ("9106",)),  # an open space: no filters
            ],
        ),
    ]


def test_my_schedule_and_the_next_session_follow_the_schedule_s_room_order() -> None:
    """Natural room order, ignoring case (D-178): "garden outside 315" before "Lounge".

    Two open spaces from 2:00 PM on May 18, 2025; the raw location string put the
    lounge first.
    """
    data, saved = processed(2025), frozenset({"9199", "9164"})
    slot = (may(2025, 18, 14), ("9164", "9199"))
    assert agenda_ids(my_schedule(data, saved)) == [(date(2025, 5, 18), [slot])]
    assert next_id(data, saved, may(2025, 18, 13)) == "9164"


def test_my_schedule_lists_a_saved_poster_on_its_day() -> None:
    """My schedule lists a saved poster in its 9:30 AM slot on May 17."""
    agenda = my_schedule(processed(2026), frozenset({"poster-detail-60"}))
    slot = (may(2026, 17, 9, 30), ("poster-detail-60",))
    assert agenda_ids(agenda) == [(date(2026, 5, 17), [slot])]


def test_my_schedule_holds_the_schedule_s_slots_and_the_model_s_sessions() -> None:
    """My schedule's slots carry the Schedule's keys and hold the model's own sessions.

    One ``Slot`` (D-185): a saved slot has the key of the Schedule's slot at its start
    (D-155's ``slot-<iso>``); its rows and the overlaps are the sessions.
    """
    data = processed(2026)
    agenda = my_schedule(data, frozenset({"2", "19", "153"}))
    slots = [slot for day in agenda.days for slot in day.slots]
    schedule = {
        slot.start: slot.key
        for day in (date(2026, 5, 13), date(2026, 5, 15))
        for slot in timeline(data, day, ())
    }
    assert [slot.key for slot in slots] == [schedule[slot.start] for slot in slots]
    listed = [s for slot in slots for s in slot.sessions]
    assert all(session is data.sessions[session.id] for session in listed)
    assert set(agenda.overlaps) == {data.sessions["2"], data.sessions["19"]}


def test_nothing_saved_is_an_empty_agenda() -> None:
    """With nothing saved, My schedule has no days and no overlaps: ``Agenda((), {})``."""
    assert my_schedule(processed(2026), frozenset()) == Agenda((), {})


def test_an_agenda_s_sessions_are_its_rows_in_agenda_order() -> None:
    """``Agenda.sessions`` lists every saved session in the feed, day by day and slot by slot.

    It is what My schedule's export holds (#426): the model's own sessions, an id the
    feed dropped left out, and nothing at all with nothing saved.
    """
    data = processed(2026)
    saved = frozenset({"188", "19", "2", "153", "9106", "no-such-id"})
    sessions = my_schedule(data, saved).sessions
    assert [s.id for s in sessions] == ["2", "19", "188", "153", "9106"]
    assert all(session is data.sessions[session.id] for session in sessions)
    assert my_schedule(data, frozenset()).sessions == ()


def test_two_saved_sessions_at_the_same_time_overlap_each_other() -> None:
    """Two saved tutorials at one time overlap each other; a later one neither."""
    agenda = my_schedule(processed(2026), frozenset({"2", "19", "188"}))
    assert overlap_ids(agenda) == {"2": ("19",), "19": ("2",)}


def test_overlaps_follow_a_chain_without_joining_its_ends() -> None:
    """Each session overlaps the ones it clashes with, not its clashes' clashes.

    Education Summit 9:00-4:30, Typing Summit 1:00-5:00, Newcomer Orientation 4:30-5:00.
    The first and the last only touch, so they do not overlap.
    """
    agenda = my_schedule(processed(2026), frozenset({"199", "201", "146"}))
    assert overlap_ids(agenda) == {
        "199": ("201",),
        "201": ("199", "146"),
        "146": ("201",),
    }


def test_one_long_session_overlaps_each_session_inside_it_in_agenda_order() -> None:
    """A long tutorial overlaps both workshops inside it, listed in agenda order.

    A tutorial 9:00-12:30 and two sponsor workshops, 9:30-10:30 and 11:30-12:30.
    """
    agenda = my_schedule(processed(2026), frozenset({"22", "111", "106"}))
    assert overlap_ids(agenda) == {
        "106": ("111", "22"),
        "111": ("106",),
        "22": ("106",),
    }


def test_a_session_inside_two_earlier_ones_lists_them_in_agenda_order() -> None:
    """A workshop inside two tutorials overlaps both, listed in agenda order.

    May 14: tutorials 9:00-12:30 in Room 101A and 101B, a workshop 9:30-10:30.
    """
    agenda = my_schedule(processed(2026), frozenset({"106", "107", "111"}))
    assert overlap_ids(agenda) == {
        "106": ("107", "111"),
        "107": ("106", "111"),
        "111": ("106", "107"),
    }


def test_the_posters_of_one_poster_session_are_one_visit() -> None:
    """Posters, the Posters row and the Job Fair never overlap each other.

    They share Expo Hall AB, 9:30 AM-1:00 PM: one visit. An open space in Room 102C from
    10:00 to 11:00 still overlaps each of them.
    """
    posters = {"poster-detail-60", "poster-detail-52", POSTERS_ROW, "227"}
    data = processed(2026)
    assert overlap_ids(my_schedule(data, frozenset(posters))) == {}
    overlaps = dict(overlap_ids(my_schedule(data, frozenset(posters | {"9028"}))))
    assert overlaps.pop("9028") == (
        "poster-detail-60",
        "poster-detail-52",
        "227",
        POSTERS_ROW,
    )
    assert overlaps == dict.fromkeys(posters, ("9028",))


def test_sessions_in_one_room_that_end_apart_still_overlap() -> None:
    """Two sessions in one room that start together overlap, though they end apart.

    Two open spaces in Room 102C from 2:00 PM, one to 5:00 PM, one to 3:00 PM.
    """
    agenda = my_schedule(processed(2026), frozenset({"9163", "9126"}))
    assert overlap_ids(agenda) == {"9126": ("9163",), "9163": ("9126",)}


def test_back_to_back_sessions_do_not_overlap() -> None:
    """Sessions that end as the next one starts do not overlap.

    The Friday welcome, PSF welcome and keynote: 9:00-9:25, 9:25-9:45, 9:45-10:30.
    """
    assert (
        overlap_ids(my_schedule(processed(2026), frozenset({"151", "152", "153"})))
        == {}
    )


def test_a_notice_overlaps_nothing() -> None:
    """A saved notice overlaps nothing, not even the saved lunch around it.

    A notice has no star, but a synced list could hold one: it lasts no time.
    """
    saved = frozenset(
        {"219", "220"}
    )  # "Swag Pickup Closes" at 1:30, in a 12:30-2:00 lunch
    assert overlap_ids(my_schedule(processed(2026), saved)) == {}


def test_the_same_saved_sessions_give_an_equal_agenda() -> None:
    """My schedule over equal saved sets compares equal, and it hashes.

    My schedule memoises on the value (D-153).
    """
    data, saved = processed(2026), frozenset({"2", "19", "153"})
    assert my_schedule(data, saved) == my_schedule(data, set(saved))
    assert hash(my_schedule(data, saved))


@pytest.mark.parametrize(
    "ask",
    [
        lambda data, naive: now_next(data, naive),
        lambda data, naive: next_for_me(data, frozenset({"153"}), naive),
        lambda data, naive: elapsed_percent(data.sessions["142"], naive),
    ],
)
def test_a_naive_now_is_refused(
    ask: Callable[[ConferenceData, datetime], object],
) -> None:
    """Now, the next session and the elapsed share refuse a naive now."""
    with pytest.raises(ValueError, match="aware"):
        ask(processed(2026), datetime(2026, 5, 15, 10))  # noqa: DTZ001
