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
    before = datetime.now(UTC)
    now = clock.now()
    assert now.tzinfo is UTC
    assert before <= now <= datetime.now(UTC)


class SteppedTime(datetime):
    """Stands in for real time in ``clock``: it only moves when a test steps it."""

    current = datetime(2026, 10, 12, 8, 0, tzinfo=UTC)

    @classmethod
    def now(cls, tz=None) -> datetime:  # same signature as datetime.now
        return cls.current


def test_fake_clock_runs_forward_with_real_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(clock, "datetime", SteppedTime)
    monkeypatch.setattr(SteppedTime, "current", SteppedTime.current)
    start = datetime(2026, 5, 15, 9, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    clock.start_fake_clock(start)
    assert clock.now() == start
    assert clock.now().tzinfo is UTC
    SteppedTime.current += timedelta(minutes=90)
    assert clock.now() == start + timedelta(minutes=90)


def test_test_override_wins_over_the_fake_clock() -> None:
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


def test_clearing_the_fake_clock_returns_to_real_time() -> None:
    clock.start_fake_clock(datetime(2030, 1, 1, tzinfo=UTC))
    clock.start_fake_clock(None)
    assert abs(clock.now() - datetime.now(UTC)) < timedelta(seconds=5)


@pytest.mark.parametrize("setter", [clock.set_test_now, clock.start_fake_clock])
def test_naive_datetimes_are_refused(setter) -> None:
    with pytest.raises(ValueError, match="aware"):
        setter(datetime(2026, 5, 15, 9, 0))  # noqa: DTZ001
