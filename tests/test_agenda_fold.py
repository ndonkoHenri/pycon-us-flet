"""Tests for folding what has ended in My schedule, and Now's elapsed share (#95)."""

from collections.abc import Iterable
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from pycon_us.config import load_year
from pycon_us.core.agenda import AgendaDay, elapsed_percent, fold_ended, my_schedule
from tests.agenda_answers import ids, may
from tests.feeds import processed

pytestmark = pytest.mark.usefixtures("machine_tz")


# ------------------------------------------------------------------ folding what has ended


FOLDED = frozenset({"2", "19", "188", "106", "111", "22", "153"})
"""May 13: two tutorials 9:00-12:30 and one 1:30-5:00 PM. May 14: a tutorial 9:00-12:30,
workshops 9:30-10:30 and 11:30-12:30. May 15: the keynote, 9:45-10:30."""


def day_ids(days: Iterable[AgendaDay]) -> list[tuple[date, list[tuple[str, ...]]]]:
    """Return each day with its slots' session ids."""
    return [(day.day, [ids(slot.sessions) for slot in day.slots]) for day in days]


def folded_at(now: datetime) -> tuple[list[date], list[tuple[str, ...]], list[date]]:
    """The earlier days, today's ended slots and the days ahead at `now`."""
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
    """Folding at a naive instant raises `ValueError`."""
    agenda = my_schedule(processed(2026), FOLDED)
    naive = datetime(2026, 5, 14, 10)  # noqa: DTZ001
    with pytest.raises(ValueError, match="aware"):
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


def test_the_elapsed_share_counts_instants_across_the_end_of_summer_time() -> None:
    """A session from 1:40 PDT to 1:10 PST is 30 minutes long, not minus 30 (#513).

    The start, the end and `now` share the conference zone, where wall clocks would
    read the end as before the start.
    """
    zone = load_year(2026).conference.zone
    start = datetime(2026, 11, 1, 8, 40, tzinfo=UTC).astimezone(zone)  # 1:40 PDT
    end = datetime(2026, 11, 1, 9, 10, tzinfo=UTC).astimezone(zone)  # 1:10 PST
    talk = replace(
        processed(2026).sessions["142"], start=start, display_start=start, end=end
    )

    def at(hour: int, minute: int) -> int:
        """Return the talk's share at `hour:minute` UTC, read in the conference zone."""
        return elapsed_percent(
            talk, datetime(2026, 11, 1, hour, minute, tzinfo=UTC).astimezone(zone)
        )

    assert at(8, 30) == 0
    assert at(8, 49) == 30  # 1:49 PDT: 9 of 30 minutes
    assert (
        at(9, 1) == 70
    )  # 1:01 PST: 21 of 30 minutes, wall-clock earlier than the start
    assert at(9, 10) == 100
