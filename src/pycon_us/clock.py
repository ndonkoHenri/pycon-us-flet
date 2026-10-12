"""The one source of "now" (D-43, DATA-12).

``now()`` answers, in order: a test override, then the Developer screen's fake clock, then
real time. Only screens and stores call it; ``core`` functions take ``now`` as an argument,
so they stay pure and testable with fixed instants.
"""

from datetime import UTC, datetime, timedelta

_test_now: datetime | None = None
_fake_offset: timedelta | None = None


def now() -> datetime:
    """Return the current instant as an aware UTC datetime."""
    if _test_now is not None:
        return _test_now
    real = datetime.now(UTC)
    return real if _fake_offset is None else real + _fake_offset


def start_fake_clock(at: datetime | None) -> None:
    """Make ``now()`` run forward from ``at`` (the Developer fake clock, D-73).

    Args:
        at: An aware instant to start from, or None to return to real time.

    Raises:
        ValueError: ``at`` is naive.
    """
    global _fake_offset
    _fake_offset = None if at is None else _aware(at) - datetime.now(UTC)


def set_test_now(at: datetime | None) -> None:
    """Freeze ``now()`` at ``at`` for a test; None lifts the override.

    Args:
        at: An aware instant, or None.

    Raises:
        ValueError: ``at`` is naive.
    """
    global _test_now
    _test_now = None if at is None else _aware(at).astimezone(UTC)


def _aware(at: datetime) -> datetime:
    if at.utcoffset() is None:
        raise ValueError(f"expected an aware datetime, got {at!r}")
    return at
