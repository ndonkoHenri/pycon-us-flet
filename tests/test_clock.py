"""Tests for the one source of "now" (D-43)."""

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from pycon_us import clock


@pytest.fixture(autouse=True)
def real_time() -> Iterator[None]:
    """Leave the clock on real time after each test."""
    yield
    clock.set_test_now(None)
    clock.start_fake_clock(None)


def test_real_time_is_aware_utc() -> None:
    """Without a fake clock or an override, `now()` is real time, aware, in UTC."""
    before = datetime.now(UTC)
    now = clock.now()
    assert now.tzinfo is UTC
    assert before <= now <= datetime.now(UTC)


class SteppedTime(datetime):
    """Stands in for real time in `clock`: it only moves when a test steps it."""

    current = datetime(2026, 10, 12, 8, 0, tzinfo=UTC)

    @classmethod
    def now(cls, tz=None) -> datetime:  # same signature as datetime.now
        """The stepped time, in UTC, whatever zone is asked for."""
        return cls.current


def test_fake_clock_runs_forward_with_real_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fake clock starts at its moment, in UTC, and moves on as real time does."""
    monkeypatch.setattr(clock, "datetime", SteppedTime)
    monkeypatch.setattr(SteppedTime, "current", SteppedTime.current)
    start = datetime(2026, 5, 15, 9, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    clock.start_fake_clock(start)
    assert clock.now() == start
    assert clock.now().tzinfo is UTC
    SteppedTime.current += timedelta(minutes=90)
    assert clock.now() == start + timedelta(minutes=90)


def test_test_override_wins_over_the_fake_clock() -> None:
    """A test's frozen `now` wins over the fake clock, set or not, until cleared."""
    clock.start_fake_clock(datetime(2026, 5, 15, 16, 0, tzinfo=UTC))
    frozen = datetime(2026, 5, 16, 9, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    clock.set_test_now(frozen)
    assert clock.now() == frozen
    assert clock.now().tzinfo is UTC
    clock.start_fake_clock(None)
    assert clock.now() == frozen  # still frozen while the override is set
    clock.start_fake_clock(datetime(2026, 5, 15, 16, 0, tzinfo=UTC))
    clock.set_test_now(None)
    assert clock.now().date() == date(2026, 5, 15)  # the fake clock again


def test_real_now_skips_the_fake_clock_but_not_a_test_override() -> None:
    """`real_now()`, the reminders' time, stays real under the fake clock (D-389)."""
    clock.start_fake_clock(datetime(2026, 5, 15, 16, 0, tzinfo=UTC))
    assert abs(clock.real_now() - datetime.now(UTC)) < timedelta(seconds=5)
    frozen = datetime(2026, 5, 16, 9, 0, tzinfo=UTC)
    clock.set_test_now(frozen)
    assert clock.real_now() == frozen


def test_clearing_the_fake_clock_returns_to_real_time() -> None:
    """Clearing the fake clock brings `now()` back to within seconds of real time."""
    clock.start_fake_clock(datetime(2030, 1, 1, tzinfo=UTC))
    clock.start_fake_clock(None)
    assert abs(clock.now() - datetime.now(UTC)) < timedelta(seconds=5)


@pytest.mark.parametrize("setter", [clock.set_test_now, clock.start_fake_clock])
def test_naive_datetimes_are_refused(setter) -> None:
    """Both the test override and the fake clock refuse a naive datetime."""
    with pytest.raises(ValueError, match="aware"):
        setter(datetime(2026, 5, 15, 9, 0))  # noqa: DTZ001


# ------------------------------------------------------------------ the Developer field (D-187)


def test_a_clock_without_an_offset_is_conference_time() -> None:
    """A clock typed without an offset, with a space or a `T`, is conference time."""
    assert clock.parse_fake_clock(
        " 2026-05-15 09:00 ", ZoneInfo("America/Los_Angeles")
    ) == datetime(2026, 5, 15, 9, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    assert clock.parse_fake_clock(
        "2026-05-15T09:00", ZoneInfo("America/Los_Angeles")
    ) == datetime(2026, 5, 15, 9, 0, tzinfo=ZoneInfo("America/Los_Angeles"))


def test_a_clock_with_an_offset_keeps_it() -> None:
    """A clock typed with an offset is that instant, whatever the conference's zone."""
    moment = clock.parse_fake_clock(
        "2026-05-15T18:00:00+02:00", ZoneInfo("America/Los_Angeles")
    )
    assert moment == datetime(2026, 5, 15, 16, 0, tzinfo=UTC)


def test_an_empty_clock_is_real_time_and_garbage_is_refused() -> None:
    """A blank clock is real time; another format is refused with the expected one."""
    assert clock.parse_fake_clock("  ", ZoneInfo("America/Los_Angeles")) is None
    with pytest.raises(ValueError, match="YYYY-MM-DD HH:MM"):
        clock.parse_fake_clock("15/05/2026 9am", ZoneInfo("America/Los_Angeles"))


def test_the_field_writes_the_start_in_conference_time() -> None:
    """The field writes a start in conference time, which parses back to it.

    No start writes an empty field.
    """
    start = datetime(2026, 5, 15, 16, 0, tzinfo=UTC)
    zone = ZoneInfo("America/Los_Angeles")
    assert clock.fake_clock_text(start, zone) == "2026-05-15 09:00"
    assert clock.parse_fake_clock(clock.fake_clock_text(start, zone), zone) == start
    assert clock.fake_clock_text(None, zone) == ""
