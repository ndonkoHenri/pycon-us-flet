"""Tests for Now & Next: what is on, what is next and your next session.

#93: SCHED-25; D-14, D-43, D-153, D-179. My schedule is
``test_agenda_my_schedule.py``'s, the fold and the elapsed share
``test_agenda_fold.py``'s.
"""

from datetime import UTC, date, datetime, timedelta, timezone, tzinfo

import pytest

from pycon_us.config import load_year
from pycon_us.core.agenda import Phase, my_schedule, next_for_me, now_next
from pycon_us.core.timeline import timeline
from tests.agenda_answers import happening, may, next_id, next_start, shown, up_next
from tests.feeds import processed

pytestmark = pytest.mark.usefixtures("machine_tz")


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
