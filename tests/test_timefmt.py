"""Tests for conference-local days and time labels (D-35, D-43; DATA-12, SCHED-18).

Every test runs under two machine time zones (``machine_tz``); the results must not change.
"""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from pycon_us.core import timefmt

pytestmark = pytest.mark.usefixtures("machine_tz")

PACIFIC = ZoneInfo("America/Los_Angeles")
KIRITIMATI = ZoneInfo("Pacific/Kiritimati")


def pacific(day: int, hour: int, minute: int) -> datetime:
    """An instant on a day of May 2026, in conference time."""
    return datetime(2026, 5, day, hour, minute, tzinfo=PACIFIC)


def test_day_bucket_changes_at_conference_midnight() -> None:
    last_second = datetime(2026, 5, 16, 6, 59, 59, tzinfo=UTC)  # 23:59:59 PDT
    assert timefmt.local_date(last_second, PACIFIC) == date(2026, 5, 15)
    assert timefmt.local_date(last_second + timedelta(seconds=1), PACIFIC) == date(
        2026, 5, 16
    )


def test_today_is_the_conference_date_not_the_device_date() -> None:
    now = datetime(2026, 5, 15, 10, 0, tzinfo=UTC)  # 3:00 AM Friday in Long Beach
    assert now.astimezone(KIRITIMATI).date() == date(2026, 5, 16)
    assert timefmt.today(now, PACIFIC) == date(2026, 5, 15)


@pytest.mark.parametrize(
    ("hour", "minute", "twelve", "twenty_four"),
    [
        (0, 5, "12:05 AM", "00:05"),
        (9, 25, "9:25 AM", "09:25"),
        (11, 59, "11:59 AM", "11:59"),
        (12, 0, "12:00 PM", "12:00"),
        (13, 45, "1:45 PM", "13:45"),
        (23, 59, "11:59 PM", "23:59"),
    ],
)
def test_time_label_in_12_and_24_hour_form(
    hour: int, minute: int, twelve: str, twenty_four: str
) -> None:
    moment = pacific(15, hour, minute)
    assert timefmt.time_label(moment, PACIFIC, use_24h=False) == twelve
    assert timefmt.time_label(moment, PACIFIC, use_24h=True) == twenty_four


def test_time_label_converts_any_aware_instant_to_conference_time() -> None:
    moment = datetime(2026, 5, 15, 16, 25, tzinfo=UTC)
    assert timefmt.time_label(moment, PACIFIC, use_24h=False) == "9:25 AM"
    assert (
        timefmt.time_label(moment.astimezone(KIRITIMATI), PACIFIC, use_24h=False)
        == "9:25 AM"
    )


def test_spring_forward_skips_the_missing_hour() -> None:
    before = datetime(2026, 3, 8, 9, 59, tzinfo=UTC)  # 1:59 AM PST
    after = before + timedelta(minutes=1)  # 3:00 AM PDT
    assert timefmt.time_label(before, PACIFIC, use_24h=False) == "1:59 AM"
    assert timefmt.time_label(after, PACIFIC, use_24h=False) == "3:00 AM"
    assert timefmt.local_date(before, PACIFIC) == timefmt.local_date(after, PACIFIC)


def test_fall_back_shows_the_repeated_hour_twice() -> None:
    first = datetime(2026, 11, 1, 8, 30, tzinfo=UTC)  # 1:30 AM PDT
    second = first + timedelta(hours=1)  # 1:30 AM PST
    assert timefmt.time_label(first, PACIFIC, use_24h=True) == "01:30"
    assert timefmt.time_label(second, PACIFIC, use_24h=True) == "01:30"
    assert timefmt.local_date(second, PACIFIC) == date(2026, 11, 1)


@pytest.mark.parametrize(
    ("start", "end", "twelve", "twenty_four"),
    [
        ((9, 25), (10, 10), "9:25–10:10 AM", "09:25–10:10"),
        ((11, 30), (12, 15), "11:30 AM–12:15 PM", "11:30–12:15"),
        ((13, 30), (17, 0), "1:30–5:00 PM", "13:30–17:00"),
        ((7, 30), (7, 30), "7:30 AM", "07:30"),
    ],
)
def test_time_range_label(
    start: tuple[int, int], end: tuple[int, int], twelve: str, twenty_four: str
) -> None:
    first, last = pacific(15, *start), pacific(15, *end)
    assert timefmt.time_range_label(first, last, PACIFIC, use_24h=False) == twelve
    assert timefmt.time_range_label(first, last, PACIFIC, use_24h=True) == twenty_four


def test_time_range_across_midnight_names_both_meridiems() -> None:
    first, last = pacific(15, 22, 0), pacific(16, 1, 0)
    assert (
        timefmt.time_range_label(first, last, PACIFIC, use_24h=False)
        == "10:00 PM–1:00 AM"
    )


def test_day_labels_use_fixed_english_names() -> None:
    assert timefmt.day_label(date(2026, 5, 15)) == "Fri, May 15"
    assert timefmt.day_heading(date(2026, 5, 15)) == "Friday, May 15"
    assert timefmt.day_heading(date(2026, 9, 1)) == "Tuesday, September 1"


def test_zone_note_only_when_the_device_offset_differs() -> None:
    now = datetime(2026, 5, 15, 17, 0, tzinfo=UTC)
    in_long_beach = now.astimezone(PACIFIC).utcoffset()
    in_kiritimati = now.astimezone(KIRITIMATI).utcoffset()
    assert timefmt.zone_note(now, PACIFIC, "Pacific Time", in_long_beach) is None
    assert (
        timefmt.zone_note(now, PACIFIC, "Pacific Time", in_kiritimati)
        == "Times are Pacific Time (PDT)"
    )


def test_zone_note_names_standard_time_in_winter() -> None:
    now = datetime(2026, 12, 1, 17, 0, tzinfo=UTC)
    note = timefmt.zone_note(now, PACIFIC, "Pacific Time", timedelta(hours=-7))
    assert note == "Times are Pacific Time (PST)"


def test_zone_note_follows_the_machine_zone(machine_tz: str) -> None:
    now = datetime(2026, 5, 15, 17, 0, tzinfo=UTC)
    note = timefmt.zone_note(now, PACIFIC, "Pacific Time", now.astimezone().utcoffset())
    assert (note is None) == (machine_tz == "America/Los_Angeles")


def test_an_hour_apart_in_the_fall_back_fold_is_a_range() -> None:
    first = datetime(2026, 11, 1, 1, 30, tzinfo=PACIFIC)  # 1:30 AM PDT
    second = first.replace(fold=1)  # 1:30 AM PST, an hour later
    assert first == second  # same tzinfo: Python compares wall times
    assert timefmt.time_range_label(first, second, PACIFIC, use_24h=False) == (
        "1:30–1:30 AM"
    )


def test_the_same_instant_in_two_zones_is_one_time() -> None:
    folded = datetime(2026, 11, 1, 1, 30, fold=1, tzinfo=PACIFIC)  # 1:30 AM PST
    label = timefmt.time_range_label(
        folded, folded.astimezone(UTC), PACIFIC, use_24h=False
    )
    assert label == "1:30 AM"


NAIVE = datetime(2026, 5, 15, 9, 0)  # noqa: DTZ001
AWARE = datetime(2026, 5, 15, 16, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "call",
    [
        lambda: timefmt.local_date(NAIVE, PACIFIC),
        lambda: timefmt.today(NAIVE, PACIFIC),
        lambda: timefmt.time_label(NAIVE, PACIFIC, use_24h=False),
        lambda: timefmt.time_range_label(NAIVE, AWARE, PACIFIC, use_24h=False),
        lambda: timefmt.time_range_label(AWARE, NAIVE, PACIFIC, use_24h=True),
        lambda: timefmt.time_range_label(NAIVE, NAIVE, PACIFIC, use_24h=False),
        lambda: timefmt.zone_note(NAIVE, PACIFIC, "Pacific Time", timedelta(0)),
        lambda: timefmt.time_status(AWARE, AWARE, NAIVE, PACIFIC),
    ],
)
def test_naive_datetimes_are_refused(call: Callable[[], object]) -> None:
    with pytest.raises(ValueError, match="aware"):
        call()


@pytest.mark.parametrize(
    ("elapsed", "label"),
    [
        (timedelta(seconds=59), "just now"),
        (timedelta(minutes=1), "1 minute ago"),
        (timedelta(minutes=59, seconds=59), "59 minutes ago"),
        (timedelta(hours=1), "1 hour ago"),
        (timedelta(hours=9, minutes=59), "9 hours ago"),
        (timedelta(hours=23, minutes=59), "23 hours ago"),
        (timedelta(days=1), "1 day ago"),
        (timedelta(days=3, hours=23), "3 days ago"),
    ],
)
def test_ago_label_says_whole_units_rounded_down_in_words(
    elapsed: timedelta, label: str
) -> None:
    now = pacific(15, 10, 0)
    assert timefmt.ago_label(now - elapsed, now) == label


def test_ago_label_compares_instants_not_wall_times() -> None:
    now = pacific(15, 10, 0)
    then = (now - timedelta(hours=2)).astimezone(KIRITIMATI)  # a day ahead on the wall
    assert timefmt.ago_label(then, now) == "2 hours ago"


def test_ago_label_says_just_now_for_a_time_after_now() -> None:
    # A Developer fake clock set before the data's fetch time (D-145: age never < 0).
    now = pacific(15, 10, 0)
    assert timefmt.ago_label(now + timedelta(hours=3), now) == "just now"


def test_ago_label_refuses_naive_datetimes() -> None:
    with pytest.raises(ValueError, match="aware"):
        timefmt.ago_label(NAIVE, pacific(15, 10, 0))


@pytest.mark.parametrize(
    ("hours", "minutes", "text"),
    [(-7, 0, "UTC−07:00"), (5, 30, "UTC+05:30"), (0, 0, "UTC"), (14, 0, "UTC+14:00")],
)
def test_utc_offsets_read_as_people_write_them(
    hours: int, minutes: int, text: str
) -> None:
    sign = -1 if hours < 0 else 1
    offset = timedelta(hours=hours) + sign * timedelta(minutes=minutes)
    assert timefmt.utc_offset_label(offset) == text


# A talk on Saturday, May 16, 10:30-11:00 AM in Long Beach.
TALK_START, TALK_END = pacific(16, 10, 30), pacific(16, 11, 0)


@pytest.mark.parametrize(
    ("now", "label", "spoken"),
    [
        (pacific(16, 10, 5), "Starts in 25 min", "Starts in 25 minutes"),
        (pacific(16, 9, 30), "Starts in 1 h", "Starts in 1 hour"),
        (pacific(16, 8, 25), "Starts in 2 h 5 min", "Starts in 2 hours 5 minutes"),
        # Rounded up: 30 s before the start is "in 1 min", never "in 0 min".
        (
            pacific(16, 10, 29) + timedelta(seconds=30),
            "Starts in 1 min",
            "Starts in 1 minute",
        ),
        (  # 24 min 30 s before: only rounding up says 25
            pacific(16, 10, 5) + timedelta(seconds=30),
            "Starts in 25 min",
            "Starts in 25 minutes",
        ),
        (  # 1 h 0 min 59 s before: rounded up across the hour
            pacific(16, 9, 29) + timedelta(seconds=1),
            "Starts in 1 h 1 min",
            "Starts in 1 hour 1 minute",
        ),
        (  # from midnight on
            pacific(16, 0, 0),
            "Starts in 10 h 30 min",
            "Starts in 10 hours 30 minutes",
        ),
    ],
)
def test_on_its_day_a_session_counts_down_to_its_start(
    now: datetime, label: str, spoken: str
) -> None:
    status = timefmt.time_status(TALK_START, TALK_END, now, PACIFIC)
    assert status is not None and not status.happening
    assert (status.label, status.spoken) == (label, spoken)


def test_the_day_before_there_is_no_countdown() -> None:
    eve = pacific(15, 23, 59)
    assert timefmt.time_status(TALK_START, TALK_END, eve, PACIFIC) is None


def test_the_countdown_s_day_is_the_conference_s_not_the_device_s() -> None:
    # 2 PM in Kiritimati is 4 PM the day before in Long Beach: no countdown yet.
    now = datetime(2026, 5, 16, 14, 0, tzinfo=KIRITIMATI)
    assert timefmt.local_date(now, PACIFIC) == date(2026, 5, 15)
    assert timefmt.time_status(TALK_START, TALK_END, now, PACIFIC) is None


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (TALK_START, timefmt.HAPPENING_NOW),  # from its start
        (pacific(16, 10, 59), timefmt.HAPPENING_NOW),
        (TALK_END, timefmt.ENDED),  # at its end it is over (D-179's half-open span)
        (pacific(18, 9, 0), timefmt.ENDED),  # and stays over, days later
    ],
)
def test_a_session_is_on_from_its_start_until_its_end(
    now: datetime, expected: timefmt.TimeStatus
) -> None:
    status = timefmt.time_status(TALK_START, TALK_END, now, PACIFIC)
    assert status == expected
    assert status is not None and status.happening is (
        expected is timefmt.HAPPENING_NOW
    )


def test_a_notice_counts_down_but_never_ends() -> None:
    """Registration Desk Opens at 7:30: at 8:00 the desk is open, not "Ended"."""
    opens = pacific(13, 7, 30)
    before = timefmt.time_status(opens, opens, pacific(13, 7, 0), PACIFIC)
    assert before is not None and before.label == "Starts in 30 min"
    assert timefmt.time_status(opens, opens, opens, PACIFIC) is None
    assert timefmt.time_status(opens, opens, pacific(13, 8, 0), PACIFIC) is None
