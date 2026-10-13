"""The one source of "now" (D-43, DATA-12).

``now()`` answers, in order: a test override, then the Developer screen's fake clock, then
real time. Only screens and stores call it; ``core`` functions take ``now`` as an argument,
so they stay pure and testable with fixed instants. The fake clock's text form, as the
Developer screen writes and reads it, is here too (D-187).
"""

from datetime import UTC, datetime, timedelta, tzinfo

FAKE_CLOCK_FORMAT = "%Y-%m-%d %H:%M"
"""How the Developer screen writes the fake clock's start: ISO 8601 with a space, in
conference time."""

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


def fake_clock_text(moment: datetime | None, zone: tzinfo) -> str:
    """Return the Developer field's text for the fake clock's start; "" for real time.

    Args:
        moment: The start (aware), or None.
        zone: The conference's zone, which the field writes in.
    """
    return "" if moment is None else moment.astimezone(zone).strftime(FAKE_CLOCK_FORMAT)


def parse_fake_clock(text: str, zone: tzinfo) -> datetime | None:
    """Return the instant the Developer field names, or None when it is empty.

    Args:
        text: ISO 8601, e.g. ``2026-05-15 09:00`` or ``2026-05-15T09:00:00-07:00``;
            without an offset it is conference time.
        zone: The conference's zone.

    Raises:
        ValueError: The text is not a date and time; its message is the field's error.
    """
    text = text.strip()
    if not text:
        return None
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        raise ValueError("Write it as YYYY-MM-DD HH:MM") from None
    return moment.replace(tzinfo=zone) if moment.utcoffset() is None else moment


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
