"""Tests for Now & Next and My schedule: Now, your next session and My schedule.

#93: SCHED-25, NEW-01; D-14, D-43, D-153, D-179.
"""

from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime, timedelta, timezone, tzinfo

import pytest

from pycon_us.config import load_year
from pycon_us.core.agenda import (
    Agenda,
    AgendaDay,
    NowNext,
    Phase,
    elapsed_percent,
    fold_ended,
    my_schedule,
    next_for_me,
    now_next,
)
from pycon_us.core.models import ConferenceData, Session
from pycon_us.core.timeline import timeline
from tests.feeds import processed

pytestmark = pytest.mark.usefixtures("machine_tz")


POSTERS_ROW = "poster-Expo Hall AB-2026-05-17T09:30:00-07:00"


def may(year: int, day: int, hour: int, minute: int = 0) -> datetime:
    """An instant in May of ``year``, in that year's conference zone."""
    zone = load_year(year).conference.zone
    return datetime(year, 5, day, hour, minute, tzinfo=zone)


# The answers hold the model's sessions (D-185); these read them by id, so the expected
# values stay as the feed names them.


def ids(sessions: Iterable[Session]) -> tuple[str, ...]:
    """Return the ids of ``sessions``, in their order."""
    return tuple(session.id for session in sessions)


def happening(result: NowNext) -> tuple[str, ...]:
    """Return the ids of the sessions Now says are happening."""
    return ids(result.happening)


def next_start(result: NowNext) -> datetime | None:
    """Return the start of Now's next slot, or None when nothing is next."""
    return None if result.up_next is None else result.up_next.start


def up_next(result: NowNext) -> tuple[str, ...]:
    """Return the ids of the sessions in Now's next slot; empty when none is next."""
    return () if result.up_next is None else ids(result.up_next.sessions)


def shown(
    result: NowNext,
) -> tuple[Phase, tuple[str, ...], datetime | None, tuple[str, ...]]:
    """What Now shows: the phase, what is on, and the next slot's start and rows."""
    return result.phase, happening(result), next_start(result), up_next(result)


def next_id(data: ConferenceData, saved: frozenset[str], now: datetime) -> str | None:
    """Return the id of the next saved session at ``now``, or None."""
    session = next_for_me(data, saved, now)
    return None if session is None else session.id


def agenda_ids(
    agenda: Agenda,
) -> list[tuple[date, list[tuple[datetime, tuple[str, ...]]]]]:
    """My schedule's days, each with its slots' starts and session ids."""
    return [
        (day.day, [(slot.start, ids(slot.sessions)) for slot in day.slots])
        for day in agenda.days
    ]


def overlap_ids(agenda: Agenda) -> dict[str, tuple[str, ...]]:
    """Return My schedule's overlaps by id: each session's clashing session ids."""
    return {session.id: ids(others) for session, others in agenda.overlaps.items()}


def test_before_the_conference_the_first_slot_is_up_next() -> None:
    """A minute before the first slot, Now is before, with the 7:30 AM notice next."""
    assert shown(now_next(processed(2026), may(2026, 13, 7, 29))) == (
        Phase.BEFORE,
        (),
        may(2026, 13, 7, 30),
        ("196",),
    )


def test_months_before_the_conference_it_is_still_before() -> None:
    """On New Year's Day, Now is still before, with the first 7:30 AM slot next."""
    result = now_next(processed(2026), datetime(2026, 1, 1, tzinfo=UTC))
    assert (result.phase, next_start(result)) == (Phase.BEFORE, may(2026, 13, 7, 30))


def test_the_day_starts_with_its_first_slot_and_a_notice_is_never_happening() -> None:
    """At 7:30 AM the day starts, its notice is not on, and the 9:00 slot is next."""
    result = now_next(processed(2026), may(2026, 13, 7, 30))
    assert result.phase is Phase.DAY
    assert happening(result) == ()  # "Registration Desk Opens" lasts no time
    assert next_start(result) == may(2026, 13, 9)


def test_a_session_ending_exactly_at_now_is_no_longer_happening() -> None:
    """At 12:30 the tutorials ending then are gone: only lunch is on, 1:30 PM is next.

    P1 exit criterion 2: Now respects end times (Ionic kept the slot until midnight).
    """
    result = now_next(processed(2026), may(2026, 13, 12, 30))
    # The morning tutorials end at 12:30, as the lunch break starts.
    assert happening(result) == ("break--2026-05-13T12:30:00-07:00",)
    assert (next_start(result), up_next(result)) == (
        may(2026, 13, 13, 30),
        ("188", "16", "57", "56", "83"),
    )


def test_a_session_is_happening_until_the_minute_it_ends() -> None:
    """The 9:45-10:30 keynote is happening from 9:45 to 10:29, not at 9:44 or 10:30."""
    data = processed(2026)  # the Friday keynote runs from 9:45 to 10:30 AM
    assert "153" not in happening(now_next(data, may(2026, 15, 9, 44)))
    assert "153" in happening(now_next(data, may(2026, 15, 9, 45)))
    assert "153" in happening(now_next(data, may(2026, 15, 10, 29)))
    assert "153" not in happening(now_next(data, may(2026, 15, 10, 30)))


def test_between_slots_nothing_is_happening_and_the_day_goes_on() -> None:
    """At 5:30 PM nothing is on, the day goes on, and the 6:00 PM notice is next.

    After the afternoon tutorials, the day's last item is that notice.
    """
    assert shown(now_next(processed(2026), may(2026, 13, 17, 30))) == (
        Phase.DAY,
        (),
        may(2026, 13, 18),
        ("197",),
    )


def test_happening_now_lists_sessions_by_start() -> None:
    """At 10:00 on May 14, Now lists the 9:00 tutorials before the 9:30 workshops."""
    result = now_next(processed(2026), may(2026, 14, 10))
    tutorials = ["106", "107", "112"]  # from 9:00
    workshops = ["111", "803", "200"]  # from 9:30
    positions = [happening(result).index(i) for i in tutorials + workshops]
    assert max(positions[:3]) < min(positions[3:])


def test_the_last_slot_of_a_day_runs_to_its_end_and_tomorrow_is_up_next() -> None:
    """At 9 PM Saturday the auction is still on, and Sunday's 8:00 AM slot is next.

    The PyLadies Auction (6:45 to 10:30 PM) ends the Saturday.
    """
    late = now_next(processed(2026), may(2026, 16, 21))
    assert (late.phase, happening(late)) == (Phase.DAY, ("223",))
    assert next_start(late) == may(2026, 17, 8)
    assert up_next(late) == (
        "226",
        "225",
        "break-Expo Hall AB-2026-05-17T08:00:00-07:00",
        "175",
    )


@pytest.mark.parametrize(
    ("day", "hour", "minute", "phase"),
    [
        (16, 22, 30, Phase.AFTER_DAY),  # the moment the day's last session ends
        (16, 23, 59, Phase.AFTER_DAY),  # still "That's a wrap for today"
        (17, 0, 0, Phase.BEFORE_DAY),  # midnight: the next slot is today
        (17, 3, 0, Phase.BEFORE_DAY),  # the night
        (17, 7, 59, Phase.BEFORE_DAY),  # the morning, before the day's first slot
    ],
)
def test_between_days_nothing_is_happening_and_the_next_day_is_up_next(
    day: int, hour: int, minute: int, phase: Phase
) -> None:
    """Between days nothing is on, and May 17's 8:00 AM slot is next.

    The phase is AFTER_DAY until midnight, then BEFORE_DAY (ux.md §5.1: "That's a wrap
    for today" until midnight, then "First up today").
    """
    result = now_next(processed(2026), may(2026, day, hour, minute))
    assert (result.phase, happening(result)) == (phase, ())
    assert next_start(result) == may(2026, 17, 8)


@pytest.mark.parametrize(
    ("local", "zone", "phase"),
    [
        # 5:30 AM on May 17 in UTC, but still the evening of May 16 at the venue.
        ((16, 22, 30), UTC, Phase.AFTER_DAY),
        # 9:30 PM on May 16 in Honolulu, but already the night of May 17 at the venue.
        ((17, 0, 30), timezone(timedelta(hours=-10)), Phase.BEFORE_DAY),
    ],
)
def test_between_days_the_date_is_the_conference_s_whatever_the_zone_of_now(
    local: tuple[int, int, int], zone: tzinfo, phase: Phase
) -> None:
    """Between days, the phase follows the venue's date, whatever the zone of now."""
    now = may(2026, *local).astimezone(zone)
    assert now_next(processed(2026), now).phase is phase


def test_the_closing_day_runs_to_its_last_notice() -> None:
    """The closing day stays on until its 8:00 PM notice, which is next until then."""
    data = processed(2026)
    closing = now_next(data, may(2026, 17, 17, 10))
    assert happening(closing) == ("9056", "185")  # the 5:00 PM open space, then Closing
    assert (next_start(closing), up_next(closing)) == (may(2026, 17, 20), ("234",))
    assert shown(now_next(data, may(2026, 17, 19, 59))) == (
        Phase.DAY,
        (),
        may(2026, 17, 20),
        ("234",),
    )


@pytest.mark.parametrize(
    "instant", [(2026, 5, 17, 20), (2026, 5, 18, 10), (2027, 1, 1, 0)]
)
def test_after_the_conference_nothing_is_on_or_next(
    instant: tuple[int, int, int, int],
) -> None:
    """From the last end, through the sprints and into 2027, nothing is on or next.

    The sprint days have no sessions in the feed, so they come after it.
    """
    year, month, day, hour = instant
    now = datetime(year, month, day, hour, tzinfo=load_year(2026).conference.zone)
    assert shown(now_next(processed(2026), now)) == (Phase.AFTER, (), None, ())


@pytest.mark.parametrize(
    ("year", "first", "last_end"),
    [(2025, (14, 7, 0), (18, 20, 0)), (2026, (13, 7, 30), (17, 20, 0))],
)
def test_the_phase_turns_at_the_first_start_and_the_last_end(
    year: int, first: tuple[int, int, int], last_end: tuple[int, int, int]
) -> None:
    """In 2025 and 2026, the phase is DAY from the first start to the last end."""
    data, minute = processed(year), timedelta(minutes=1)
    assert now_next(data, may(year, *first) - minute).phase is Phase.BEFORE
    assert now_next(data, may(year, *first)).phase is Phase.DAY
    assert now_next(data, may(year, *last_end) - minute).phase is Phase.DAY
    assert now_next(data, may(year, *last_end)).phase is Phase.AFTER


def test_now_lists_a_slot_as_the_schedule_does() -> None:
    """Now's next slot is one of the Schedule's, led at 10:00 by the 9:30 Job Fair.

    One order and one slot in the app (D-178, D-185).
    """
    data = processed(2026)
    result = now_next(data, may(2026, 17, 9, 59))
    schedule = timeline(data, date(2026, 5, 17), ())
    assert up_next(result)[:3] == ("178", "break--2026-05-17T10:00:00-07:00", "228")
    assert any(slot is result.up_next for slot in schedule)


def test_the_zone_of_now_does_not_matter() -> None:
    """One instant gives the same answer in UTC as in the conference's zone."""
    data, local = processed(2026), may(2026, 15, 10, 15)
    assert now_next(data, local.astimezone(UTC)) == now_next(data, local)


def test_now_ignores_filters_and_leaves_poster_details_to_the_posters_row() -> None:
    """Now lists open spaces, and the Posters row without its posters' details.

    Open spaces are hidden on the Schedule by default (D-20); Now has no filters.
    """
    data = processed(2026)
    assert {"9106", "9042"} <= set(happening(now_next(data, may(2026, 15, 10, 15))))
    posters = happening(now_next(data, may(2026, 17, 10)))
    assert "poster-Expo Hall AB-2026-05-17T09:30:00-07:00" in posters
    assert not [i for i in posters if i.startswith("poster-detail-")]


def test_the_same_answer_at_two_instants_compares_equal() -> None:
    """Now's answers at 10:16 and at 10:20 compare equal, and they hash.

    Now recomputes every 60 s and memoises on the value (D-153).
    """
    data = processed(2026)
    assert now_next(data, may(2026, 15, 10, 16)) == now_next(
        data, may(2026, 15, 10, 20)
    )
    assert hash(now_next(data, may(2026, 15, 10, 16)))


def test_now_and_the_next_session_hold_the_model_s_own_sessions() -> None:
    """Now and the next session hold the model's own ``Session`` objects.

    D-185: a row gets its session itself, with no lookup by id.
    """
    data = processed(2026)
    result = now_next(data, may(2026, 15, 10, 15))
    assert result.happening
    assert all(session is data.sessions[session.id] for session in result.happening)
    assert (
        next_for_me(data, frozenset({"153"}), may(2026, 15, 9)) is data.sessions["153"]
    )


def test_a_new_feed_version_gives_answers_of_its_own() -> None:
    """Now and My schedule over two loads of one feed never compare equal.

    Sessions compare by identity, so the answer over a refreshed feed, where a session
    may have moved, never equals the old feed's (D-153, D-185).
    """
    now, saved = may(2026, 15, 10, 15), frozenset({"2", "19", "153"})
    assert now_next(processed(2026), now) != now_next(processed(2026), now)
    assert my_schedule(processed(2026), saved) != my_schedule(processed(2026), saved)


def test_the_next_session_is_a_saved_one_starting_within_three_hours() -> None:
    """A saved session becomes the next one exactly three hours before it starts."""
    data, saved = processed(2026), frozenset({"153"})  # 9:45 to 10:30 AM
    assert next_id(data, saved, may(2026, 15, 6, 44)) is None
    assert next_id(data, saved, may(2026, 15, 6, 45)) == "153"  # exactly 3 h ahead


def test_the_next_session_stays_while_it_is_on_and_goes_when_it_ends() -> None:
    """The next session stays while it is on, at 10:29, and is gone at its 10:30 end."""
    data, saved = processed(2026), frozenset({"153"})
    assert next_id(data, saved, may(2026, 15, 10, 29)) == "153"
    assert next_id(data, saved, may(2026, 15, 10, 30)) is None


def test_a_saved_session_starting_soon_comes_before_a_long_one_that_is_on() -> None:
    """A saved talk due within three hours comes before a long saved one that is on.

    The Maintainers Summit (10:30 AM to 5:30 PM) and a 2:30 PM talk, both saved: the
    talk is next from 11:30 until it ends, then the summit again.
    """
    data, saved = processed(2026), frozenset({"218", "61"})
    assert next_id(data, saved, may(2026, 16, 11, 29)) == "218"  # talk not yet due
    assert next_id(data, saved, may(2026, 16, 11, 30)) == "61"  # 3 h ahead: due
    assert next_id(data, saved, may(2026, 16, 14, 20)) == "61"
    assert next_id(data, saved, may(2026, 16, 14, 40)) == "61"  # on, started last
    assert next_id(data, saved, may(2026, 16, 15)) == "218"  # only the summit is on


def test_a_saved_session_that_is_on_shows_when_nothing_is_due() -> None:
    """A saved session that is on is next until another is due within three hours."""
    data = processed(2026)
    saved = frozenset({"2", "188"})  # tutorials 9:00 to 12:30 and 1:30 to 5:00 PM
    # At 10:29, 188 is 3 h 1 min away.
    assert next_id(data, saved, may(2026, 13, 10, 29)) == "2"
    assert next_id(data, saved, may(2026, 13, 10, 30)) == "188"


def test_saved_sessions_with_one_start_are_taken_in_agenda_order() -> None:
    """Of two saved sessions with one start, the first in agenda order is next.

    Tutorials in Room 101A and Room 101B, both 9:00 to 12:30 on May 13: Room 101A's is
    next while both are due and while both are on.
    """
    data, saved = processed(2026), frozenset({"2", "19"})
    assert next_id(data, saved, may(2026, 13, 8)) == "2"  # both due
    assert next_id(data, saved, may(2026, 13, 10)) == "2"  # both on


def test_the_next_session_ignores_unsaved_and_unknown_ids() -> None:
    """With nothing saved, or only an id not in the feed, there is no next session."""
    data = processed(2026)
    assert next_id(data, frozenset(), may(2026, 15, 9)) is None
    assert next_id(data, frozenset({"no-such-id"}), may(2026, 15, 9)) is None


def test_a_saved_poster_can_be_the_next_session() -> None:
    """A saved poster is the next session at 9:00 AM on May 17, before its 9:30 start."""
    saved = frozenset({"poster-detail-60"})
    assert next_id(processed(2026), saved, may(2026, 17, 9)) == "poster-detail-60"


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


# ------------------------------------------------------------------ folding what has ended


FOLDED = frozenset({"2", "19", "188", "106", "111", "22", "153"})
"""May 13: two tutorials 9:00-12:30 and one 1:30-5:00 PM. May 14: a tutorial 9:00-12:30,
workshops 9:30-10:30 and 11:30-12:30. May 15: the keynote, 9:45-10:30."""


def day_ids(days: Iterable[AgendaDay]) -> list[tuple[date, list[tuple[str, ...]]]]:
    """Return each day with its slots' session ids."""
    return [(day.day, [ids(slot.sessions) for slot in day.slots]) for day in days]


def folded_at(now: datetime) -> tuple[list[date], list[tuple[str, ...]], list[date]]:
    """The earlier days, today's ended slots and the days ahead at ``now``."""
    zone = load_year(2026).conference.zone
    result = fold_ended(my_schedule(processed(2026), FOLDED), now, zone)
    today = day_ids([result.earlier_today]) if result.earlier_today else []
    return (
        [day.day for day in result.earlier_days],
        [slot for _, slots in today for slot in slots],
        [day.day for day in result.ahead],
    )


def test_before_the_conference_nothing_has_ended() -> None:
    """Before the conference, nothing is folded and all three days are ahead."""
    assert folded_at(may(2026, 1, 12)) == (
        [],
        [],
        [date(2026, 5, 13), date(2026, 5, 14), date(2026, 5, 15)],
    )


def test_days_before_today_fold_whole_and_today_folds_what_has_ended() -> None:
    """Earlier days fold whole, and today folds only its sessions that have ended.

    May 14, 10:45: the 9:30 workshop has ended; the 9:00 tutorial has not.
    """
    zone = load_year(2026).conference.zone
    result = fold_ended(
        my_schedule(processed(2026), FOLDED), may(2026, 14, 10, 45), zone
    )
    assert [day.day for day in result.earlier_days] == [date(2026, 5, 13)]
    assert result.earlier_today is not None
    assert day_ids([result.earlier_today]) == [(date(2026, 5, 14), [("111",)])]
    assert day_ids(result.ahead) == [
        (date(2026, 5, 14), [("106",), ("22",)]),
        (date(2026, 5, 15), [("153",)]),
    ]


def test_a_session_has_ended_at_its_end() -> None:
    """The half-open rule of Now (D-179): over at 10:30, on at 10:29."""
    assert folded_at(may(2026, 14, 10, 29))[1] == []
    assert folded_at(may(2026, 14, 10, 30))[1] == [("111",)]


def test_a_slot_splits_when_its_sessions_end_apart() -> None:
    """Today's ended sessions fold while its later ones keep the day ahead.

    May 13, 12:30: the two 9:00 tutorials have ended together; at 3 PM the third is
    still on, and Wednesday is not over.
    """
    assert folded_at(may(2026, 13, 12, 30))[1] == [("2", "19")]
    earlier, ended, ahead = folded_at(may(2026, 13, 15))
    assert (earlier, ended) == ([], [("2", "19")])
    assert ahead[0] == date(2026, 5, 13)


def test_when_today_s_sessions_have_all_ended_today_is_not_ahead() -> None:
    """Once today's saved sessions have all ended, they fold and today is not ahead."""
    earlier, ended, ahead = folded_at(may(2026, 14, 13))
    assert (earlier, ended) == ([date(2026, 5, 13)], [("106",), ("111",), ("22",)])
    assert ahead == [date(2026, 5, 15)]


def test_after_the_conference_every_day_is_earlier() -> None:
    """After the conference, every day folds as an earlier day and none is ahead."""
    assert folded_at(datetime(2026, 6, 1, tzinfo=UTC)) == (
        [date(2026, 5, 13), date(2026, 5, 14), date(2026, 5, 15)],
        [],
        [],
    )


def test_today_is_the_conference_s_date_whatever_the_zone_of_now() -> None:
    """Today is the venue's date: at 1:00 AM UTC on May 15, May 14 is today.

    May 15, 1:00 AM UTC is still May 14 in Long Beach, 6 PM: Thursday is over.
    """
    earlier, ended, ahead = folded_at(datetime(2026, 5, 15, 1, tzinfo=UTC))
    assert earlier == [date(2026, 5, 13)]
    assert ended == [("106",), ("111",), ("22",)]
    assert ahead == [date(2026, 5, 15)]


def test_the_fold_is_equal_from_minute_to_minute_until_a_session_ends() -> None:
    """The fold at 10:31 equals the one at 10:32, and differs once a session ends.

    A screen that folds every minute re-renders only when the answer changes.
    """
    zone = load_year(2026).conference.zone
    agenda = my_schedule(processed(2026), FOLDED)
    first = fold_ended(agenda, may(2026, 14, 10, 31), zone)
    assert fold_ended(agenda, may(2026, 14, 10, 32), zone) == first
    assert fold_ended(agenda, may(2026, 14, 12, 30), zone) != first


def test_folding_needs_an_aware_instant() -> None:
    """Folding at a naive instant raises ``ValueError``."""
    agenda = my_schedule(processed(2026), FOLDED)
    with pytest.raises(ValueError, match="aware"):
        naive = datetime(2026, 5, 14, 10)  # noqa: DTZ001
        fold_ended(agenda, naive, load_year(2026).conference.zone)


def test_only_clashes_that_can_still_change_a_plan_are_kept() -> None:
    """The fold keeps only the overlaps between sessions that have not ended.

    May 14, 10:45: the tutorial still clashes with the 11:30 workshop, not with the 9:30
    one, which has ended; Wednesday's two tutorials, folded, clash no more.
    """
    zone = load_year(2026).conference.zone
    agenda = my_schedule(processed(2026), FOLDED)
    result = fold_ended(agenda, may(2026, 14, 10, 45), zone)
    assert {s.id: ids(others) for s, others in result.overlaps.items()} == {
        "106": ("22",),
        "22": ("106",),
    }


def test_before_the_conference_every_clash_is_kept() -> None:
    """Before the conference, the fold keeps every overlap of My schedule."""
    zone = load_year(2026).conference.zone
    agenda = my_schedule(processed(2026), FOLDED)
    assert fold_ended(agenda, may(2026, 1, 12), zone).overlaps == agenda.overlaps


# ------------------------------------------------------------------ elapsed (#95)


def test_the_elapsed_share_counts_whole_percents_rounded_down() -> None:
    """The elapsed share is whole percents rounded down: 0 before, 100 after."""
    talk = processed(2026).sessions["142"]  # 10:30-11:00 AM on Saturday, May 16
    assert elapsed_percent(talk, may(2026, 16, 10, 30)) == 0
    assert elapsed_percent(talk, may(2026, 16, 10, 39)) == 30  # 9 of 30 minutes
    assert elapsed_percent(talk, may(2026, 16, 10, 48)) == 60
    # 29 minutes is 96.67 %: rounded down, so a session that is on never says 100.
    assert elapsed_percent(talk, may(2026, 16, 10, 59)) == 96
    assert elapsed_percent(talk, may(2026, 16, 11, 0)) == 100
    assert elapsed_percent(talk, may(2026, 16, 9, 0)) == 0
    assert elapsed_percent(talk, may(2026, 16, 12, 0)) == 100


def test_a_share_that_floats_would_round_badly_counts_exactly() -> None:
    """8 min 42 s of a 30-minute talk is exactly 29 %; floats would round it down to 28."""
    talk = processed(2026).sessions["142"]
    # 8.7 of 30 minutes is exactly 29 %; 0.29 * 100 in floats is 28.999….
    at = may(2026, 16, 10, 38) + timedelta(seconds=42)
    assert elapsed_percent(talk, at) == 29


def test_the_elapsed_share_follows_the_start_a_row_shows() -> None:
    """The elapsed share counts from the 9:30 start the row shows, not the 10:00 slot.

    The Job Fair's row says 9:30, though its slot is 10:00 (DATA-11).
    """
    fair = processed(2026).sessions["178"]  # 9:30 AM-1:00 PM, in the 10:00 slot
    assert fair.display_start < fair.start
    assert elapsed_percent(fair, may(2026, 17, 10, 0)) == 14  # 30 of 210 minutes
