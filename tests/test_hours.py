"""Tests for the venue hours' open-now rule (`core/hours.py`; MAP-09, D-282).

They run on 2026's year data and on small made-up services, under two machine time
zones (`machine_tz`): the answers must not change with the device's zone (D-43).
"""

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from pycon_us.config import load_year
from pycon_us.core.hours import (
    CLOSED_TODAY,
    HoursStatus,
    Opening,
    ServiceHours,
    days,
    hours_status,
)

pytestmark = pytest.mark.usefixtures("machine_tz")

PACIFIC = ZoneInfo("America/Los_Angeles")
KIRITIMATI = ZoneInfo("Pacific/Kiritimati")
HOURS = load_year(2026).content.venue_hours


def pacific(day: int, hour: int, minute: int = 0, second: int = 0) -> datetime:
    """An instant on a day of May 2026, in conference time."""
    return datetime(2026, 5, day, hour, minute, second, tzinfo=PACIFIC)


def status(
    service: str, now: datetime, hours: tuple[ServiceHours, ...] = HOURS
) -> HoursStatus | None:
    """The status `service` has at `now` in 12-hour form; None off-season."""
    statuses = hours_status(hours, now, PACIFIC, use_24h=False)
    return None if statuses is None else statuses[service]


def label(service: str, now: datetime) -> str:
    """The label 2026's `service` shows at `now`; the season must be on."""
    found = status(service, now)
    assert found is not None
    return found.label


def test_the_opening_minute_is_open() -> None:
    """Registration is open from 7:30:00 on Wednesday, and says until when: 6 PM."""
    assert status("Registration", pacific(13, 7, 30)) == HoursStatus(
        "open", "Open now · until 6:00 PM", "Open now, until 6:00 PM"
    )


def test_the_closing_minute_is_closed() -> None:
    """At 6:00 PM registration has closed; a second before it is still open."""
    assert label("Registration", pacific(13, 17, 59, 59)) == "Open now · until 6:00 PM"
    assert status("Registration", pacific(13, 18)) == HoursStatus(
        "another_day", "Opens tomorrow at 7:30 AM", "Opens tomorrow at 7:30 AM"
    )


def test_before_opening_it_says_when_it_opens_today() -> None:
    """Before 7:30 on Wednesday, registration says "Opens 7:30 AM", to the second."""
    assert status("Registration", pacific(13, 7)) == HoursStatus(
        "later_today", "Opens 7:30 AM", "Opens 7:30 AM"
    )
    assert label("Registration", pacific(13, 7, 29, 59)) == "Opens 7:30 AM"
    assert label("Registration", pacific(13, 0, 0)) == "Opens 7:30 AM"


def test_after_closing_it_names_the_next_opening() -> None:
    """After Thursday's close, registration names Friday's 7:30 AM opening."""
    assert label("Registration", pacific(14, 21)) == "Opens tomorrow at 7:30 AM"
    assert label("Information desk", pacific(15, 16)) == "Opens tomorrow at 8:00 AM"


def test_a_later_day_is_named_and_spoken_in_full() -> None:
    """Swag pickup, first open on Friday, names that day on Wednesday: short and spoken."""
    assert status("Swag pickup", pacific(13, 10)) == HoursStatus(
        "another_day",
        "Opens Fri, May 15 at 9:00 AM",
        "Opens Friday, May 15 at 9:00 AM",
    )
    assert label("Quiet room", pacific(13, 10)) == "Opens tomorrow at 9:00 AM"


def test_with_no_opening_left_it_is_closed_today() -> None:
    """On Sunday afternoon registration is done for the year while the quiet room is open."""
    now = pacific(17, 14)
    assert status("Registration", now) == CLOSED_TODAY
    assert label("Swag pickup", now) == "Closed today"
    assert label("Quiet room", now) == "Open now · until 5:00 PM"


@pytest.mark.parametrize(
    "now",
    [
        pacific(12, 12),  # the day before the first opening
        pacific(12, 23, 59, 59),
        pacific(18, 0, 0),  # the sprints: every service is done
        pacific(19, 10),
        datetime(2026, 10, 20, 9, 0, tzinfo=PACIFIC),
        datetime(2027, 5, 13, 9, 0, tzinfo=PACIFIC),  # a year on, the same date
    ],
)
def test_off_season_there_is_no_status(now: datetime) -> None:
    """Outside the days a service opens on, `hours_status()` is None: no labels."""
    assert hours_status(HOURS, now, PACIFIC, use_24h=False) is None


def test_the_season_starts_and_ends_at_conference_midnight() -> None:
    """The season's first and last days are conference-local, whatever the instant's zone."""
    assert hours_status(HOURS, pacific(13, 0), PACIFIC, use_24h=False) is not None
    sunday_night = pacific(17, 23, 59, 59).astimezone(UTC)  # Monday in UTC
    assert hours_status(HOURS, sunday_night, PACIFIC, use_24h=False) is not None


def test_a_service_without_hours_has_no_status() -> None:
    """Lost & found and the luggage check have no hours of their own, so no label."""
    statuses = hours_status(HOURS, pacific(15, 10), PACIFIC, use_24h=False)
    assert statuses is not None
    assert list(statuses) == [
        "Registration",
        "Information desk",
        "Swag pickup",
        "Quiet room",
    ]


def test_the_answer_does_not_depend_on_the_instant_s_zone() -> None:
    """The same instant in UTC or in Kiritimati (a day ahead) gets the same statuses."""
    now = pacific(15, 7, 45)
    expected = hours_status(HOURS, now, PACIFIC, use_24h=False)
    for zone in (UTC, KIRITIMATI):
        assert hours_status(HOURS, now.astimezone(zone), PACIFIC, use_24h=False) == (
            expected
        )
    assert expected is not None
    assert expected["Quiet room"].label == "Open now · until 5:00 PM"
    assert expected["Swag pickup"].label == "Opens 9:00 AM"


def test_24_hour_times_follow_the_device_setting() -> None:
    """With the device's 24-hour setting the labels read "18:00" and "07:30"."""
    statuses = hours_status(HOURS, pacific(13, 9), PACIFIC, use_24h=True)
    assert statuses is not None
    assert statuses["Registration"].label == "Open now · until 18:00"
    assert statuses["Quiet room"].label == "Opens tomorrow at 09:00"
    later = hours_status(HOURS, pacific(13, 7), PACIFIC, use_24h=True)
    assert later is not None
    assert later["Registration"].label == "Opens 07:30"


def test_a_break_in_the_day_says_when_it_opens_again() -> None:
    """A service closed for lunch says it reopens at 1 PM, and one may close as the next opens."""
    desk = ServiceHours(
        "Desk",
        open=(
            Opening(date(2026, 5, 15), time(13), time(17)),  # out of order on purpose
            Opening(date(2026, 5, 15), time(9), time(12)),
            Opening(date(2026, 5, 16), time(9), time(12)),
            Opening(date(2026, 5, 16), time(12), time(15)),
        ),
    )
    hours = (desk,)
    assert status("Desk", pacific(15, 12), hours) == HoursStatus(
        "later_today", "Opens 1:00 PM", "Opens 1:00 PM"
    )
    assert status("Desk", pacific(15, 11), hours) == HoursStatus(
        "open", "Open now · until 12:00 PM", "Open now, until 12:00 PM"
    )
    assert status("Desk", pacific(16, 12), hours) == HoursStatus(
        "open", "Open now · until 3:00 PM", "Open now, until 3:00 PM"
    )


def test_days_are_the_dates_any_service_opens_on() -> None:
    """2026's season runs from Wednesday to Sunday; a year without hours has none."""
    assert days(HOURS) == tuple(date(2026, 5, day) for day in range(13, 18))
    assert days(()) == ()
    assert hours_status((), pacific(15, 10), PACIFIC, use_24h=False) is None


def test_a_naive_instant_is_refused() -> None:
    """A `now` without a zone has no instant, so the rule refuses it (D-43)."""
    with pytest.raises(ValueError, match="aware"):
        hours_status(HOURS, datetime(2026, 5, 15, 10), PACIFIC, use_24h=False)  # noqa: DTZ001 (naive on purpose: the call must refuse it)
