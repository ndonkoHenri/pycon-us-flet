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
    """An instant's day changes at midnight in conference time, not in UTC."""
    last_second = datetime(2026, 5, 16, 6, 59, 59, tzinfo=UTC)  # 23:59:59 PDT
    assert timefmt.local_date(last_second, PACIFIC) == date(2026, 5, 15)
    assert timefmt.local_date(last_second + timedelta(seconds=1), PACIFIC) == date(
        2026, 5, 16
    )


def test_today_is_the_conference_date_not_the_device_date() -> None:
    """``today()`` is the date in Long Beach while Kiritimati is already a day ahead."""
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
    """A time reads "9:25 AM" in 12-hour form and "09:25" in 24-hour form."""
    moment = pacific(15, hour, minute)
    assert timefmt.time_label(moment, PACIFIC, use_24h=False) == twelve
    assert timefmt.time_label(moment, PACIFIC, use_24h=True) == twenty_four


def test_time_label_converts_any_aware_instant_to_conference_time() -> None:
    """An instant reads in conference time, whichever zone it carries."""
    moment = datetime(2026, 5, 15, 16, 25, tzinfo=UTC)
    assert timefmt.time_label(moment, PACIFIC, use_24h=False) == "9:25 AM"
    assert (
        timefmt.time_label(moment.astimezone(KIRITIMATI), PACIFIC, use_24h=False)
        == "9:25 AM"
    )


def test_spring_forward_skips_the_missing_hour() -> None:
    """A minute after 1:59 AM on spring-forward night is 3:00 AM, on the same day."""
    before = datetime(2026, 3, 8, 9, 59, tzinfo=UTC)  # 1:59 AM PST
    after = before + timedelta(minutes=1)  # 3:00 AM PDT
    assert timefmt.time_label(before, PACIFIC, use_24h=False) == "1:59 AM"
    assert timefmt.time_label(after, PACIFIC, use_24h=False) == "3:00 AM"
    assert timefmt.local_date(before, PACIFIC) == timefmt.local_date(after, PACIFIC)


def test_fall_back_shows_the_repeated_hour_twice() -> None:
    """Both 1:30 AMs of fall-back night read "01:30", the second still on Nov 1."""
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
    """A range says AM or PM once when both ends share it; equal ends are one time."""
    first, last = pacific(15, *start), pacific(15, *end)
    assert timefmt.time_range_label(first, last, PACIFIC, use_24h=False) == twelve
    assert timefmt.time_range_label(first, last, PACIFIC, use_24h=True) == twenty_four


@pytest.mark.parametrize(
    ("label", "shown"),
    [
        ("9:45–10:30 AM", "9:45–10:30\N{NO-BREAK SPACE}AM"),
        ("11:30 AM–12:15 PM", "11:30\N{NO-BREAK SPACE}AM–12:15\N{NO-BREAK SPACE}PM"),
        ("09:25–10:10", "09:25–10:10"),
        ("7:30 AM", "7:30\N{NO-BREAK SPACE}AM"),
    ],
)
def test_a_time_on_screen_can_break_only_after_its_dash(label: str, shown: str) -> None:
    """On screen, a time's spaces are no-break spaces and its en dash is left alone.

    D-229: Unicode lets a line break after an en dash and at a space, nowhere else in
    a time. No-break spaces keep "AM" with its digits; nothing joins the dash, as a
    range wider than its line would then break inside a time ("9:00 AM–12" / ":30 PM",
    D-186) rather than after it.
    """
    assert timefmt.on_screen(label) == shown
    assert "\N{WORD JOINER}" not in timefmt.on_screen(
        label
    )  # no word joiner at the dash


def test_time_range_across_midnight_names_both_meridiems() -> None:
    """A range from 10 PM to 1 AM the next day names both: "10:00 PM–1:00 AM"."""
    first, last = pacific(15, 22, 0), pacific(16, 1, 0)
    assert (
        timefmt.time_range_label(first, last, PACIFIC, use_24h=False)
        == "10:00 PM–1:00 AM"
    )


def test_day_labels_use_fixed_english_names() -> None:
    """A day's label is "Fri, May 15" and its heading "Friday, May 15", in English."""
    assert timefmt.day_label(date(2026, 5, 15)) == "Fri, May 15"
    assert timefmt.day_heading(date(2026, 5, 15)) == "Friday, May 15"
    assert timefmt.day_heading(date(2026, 9, 1)) == "Tuesday, September 1"


def test_a_day_tab_is_one_short_line_and_its_weekday_is_spelt_out() -> None:
    """SCHED-01: one line, so the tab keeps its text at 200 % (S2)."""
    assert timefmt.day_tab_label(date(2026, 5, 15)) == "Fri 15"
    assert timefmt.day_tab_label(date(2026, 5, 9)) == "Sat 9"


def test_a_weekday_is_named_in_full() -> None:
    """``weekday_name()`` spells the weekday out: "Friday", "Monday"."""
    assert timefmt.weekday_name(date(2026, 5, 15)) == "Friday"
    assert timefmt.weekday_name(date(2026, 5, 18)) == "Monday"


def test_a_span_of_days_names_its_month_once_when_it_can() -> None:
    """Days read "May 13–19" in a month, "May 30–June 2" across two, "May 13" alone."""
    assert timefmt.date_range_label(date(2026, 5, 13), date(2026, 5, 19)) == "May 13–19"
    assert (
        timefmt.date_range_label(date(2027, 5, 30), date(2027, 6, 2)) == "May 30–June 2"
    )
    assert timefmt.date_range_label(date(2026, 5, 13), date(2026, 5, 13)) == "May 13"


def test_a_day_range_names_its_weekdays() -> None:
    """The key dates and the sprints: "Mon, May 18 – Tue, May 19", or one day."""
    assert (
        timefmt.day_range_label(date(2026, 5, 18), date(2026, 5, 19))
        == "Mon, May 18 – Tue, May 19"
    )
    assert (
        timefmt.day_range_label(date(2026, 5, 18), date(2026, 5, 18)) == "Mon, May 18"
    )


def test_zone_note_only_when_the_device_offset_differs() -> None:
    """The zone note shows only when the device's offset is not the conference's."""
    now = datetime(2026, 5, 15, 17, 0, tzinfo=UTC)
    in_long_beach = now.astimezone(PACIFIC).utcoffset()
    in_kiritimati = now.astimezone(KIRITIMATI).utcoffset()
    assert timefmt.zone_note(now, PACIFIC, "Pacific Time", in_long_beach) is None
    assert (
        timefmt.zone_note(now, PACIFIC, "Pacific Time", in_kiritimati)
        == "Times are Pacific Time (PDT)"
    )


def test_zone_note_names_standard_time_in_winter() -> None:
    """In December the zone note names standard time: "Times are Pacific Time (PST)"."""
    now = datetime(2026, 12, 1, 17, 0, tzinfo=UTC)
    note = timefmt.zone_note(now, PACIFIC, "Pacific Time", timedelta(hours=-7))
    assert note == "Times are Pacific Time (PST)"


def test_zone_note_follows_the_machine_zone(machine_tz: str) -> None:
    """With the machine's own offset, the note shows unless it is on Pacific Time."""
    now = datetime(2026, 5, 15, 17, 0, tzinfo=UTC)
    note = timefmt.zone_note(now, PACIFIC, "Pacific Time", now.astimezone().utcoffset())
    assert (note is None) == (machine_tz == "America/Los_Angeles")


def test_an_hour_apart_in_the_fall_back_fold_is_a_range() -> None:
    """The two 1:30 AMs of fall-back night, equal as wall times, make a range."""
    first = datetime(2026, 11, 1, 1, 30, tzinfo=PACIFIC)  # 1:30 AM PDT
    second = first.replace(fold=1)  # 1:30 AM PST, an hour later
    assert first == second  # same tzinfo: Python compares wall times
    assert timefmt.time_range_label(first, second, PACIFIC, use_24h=False) == (
        "1:30–1:30 AM"
    )


def test_the_same_instant_in_two_zones_is_one_time() -> None:
    """A range whose ends are one instant in two zones reads as one time."""
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
    """The functions that take a zone raise ``ValueError`` for a naive datetime."""
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
    """An age is "just now" under a minute, then whole units rounded down, in words."""
    now = pacific(15, 10, 0)
    assert timefmt.ago_label(now - elapsed, now) == label


def test_ago_label_compares_instants_not_wall_times() -> None:
    """Two hours ago is "2 hours ago" though its zone's wall clock is a day ahead."""
    now = pacific(15, 10, 0)
    then = (now - timedelta(hours=2)).astimezone(KIRITIMATI)  # a day ahead on the wall
    assert timefmt.ago_label(then, now) == "2 hours ago"


def test_ago_label_says_just_now_for_a_time_after_now() -> None:
    """A time after now is "just now": an age is never below zero (D-145).

    A Developer fake clock set before the data's fetch time does this.
    """
    now = pacific(15, 10, 0)
    assert timefmt.ago_label(now + timedelta(hours=3), now) == "just now"


@pytest.mark.parametrize(
    ("seconds", "label"),
    [
        (-2, "just now"),
        (0.9, "just now"),
        (1, "1 second ago"),
        (12.7, "12 seconds ago"),
        (59.9, "59 seconds ago"),
        (60, "1 minute ago"),
        (3599, "59 minutes ago"),
        (7200, "2 hours ago"),
        (2 * 86400, "2 days ago"),
    ],
)
def test_seconds_ago_counts_seconds_under_a_minute(seconds: float, label: str) -> None:
    """The scan screen's age: whole seconds under a minute, then ``ago_label``'s units."""
    assert timefmt.seconds_ago(seconds) == label


def test_ago_label_refuses_naive_datetimes() -> None:
    """``ago_label()`` raises ``ValueError`` for a naive datetime."""
    with pytest.raises(ValueError, match="aware"):
        timefmt.ago_label(NAIVE, pacific(15, 10, 0))


@pytest.mark.parametrize(
    ("hours", "minutes", "text"),
    [(-7, 0, "UTC−07:00"), (5, 30, "UTC+05:30"), (0, 0, "UTC"), (14, 0, "UTC+14:00")],
)
def test_utc_offsets_read_as_people_write_them(
    hours: int, minutes: int, text: str
) -> None:
    """An offset reads "UTC−07:00" or "UTC+05:30", with a real minus, and "UTC" at 0."""
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
    """On its day, a session counts down to its start in minutes rounded up.

    The label abbreviates ("Starts in 2 h 5 min"); the spoken form says the words.
    """
    status = timefmt.time_status(TALK_START, TALK_END, now, PACIFIC)
    assert status is not None and not status.happening
    assert (status.label, status.spoken) == (label, spoken)


def test_the_day_before_there_is_no_countdown() -> None:
    """A minute before midnight on the eve of a session's day, there is no countdown."""
    eve = pacific(15, 23, 59)
    assert timefmt.time_status(TALK_START, TALK_END, eve, PACIFIC) is None


def test_the_countdown_s_day_is_the_conference_s_not_the_device_s() -> None:
    """The countdown waits for the session's day in conference time.

    2 PM in Kiritimati is 4 PM the day before in Long Beach: no countdown yet.
    """
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
    """A session is "Happening now" from its start, and "Ended" from its end on."""
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
