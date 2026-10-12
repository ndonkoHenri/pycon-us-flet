"""Conference-local days and time labels (D-35, D-43; DATA-12, SCHED-18).

Times are always shown in the conference's zone, whatever the device's zone. Every function
here is pure: the instant (``now`` included) and the zone are arguments, and the 12/24-hour
choice is passed in by the UI (from ``page.media.always_use_24_hour_format``). Day and month
names come from fixed English tuples and labels are built by hand, so nothing depends on the
device locale or on ``strftime`` flags. Naive datetimes are refused: they have no instant.
"""

from datetime import date, datetime, timedelta, tzinfo

_WEEKDAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)
_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def local_date(moment: datetime, zone: tzinfo) -> date:
    """Return the conference-local date of ``moment``: the day it belongs to (its day bucket)."""
    return _local(moment, zone).date()


def today(now: datetime, zone: tzinfo) -> date:
    """Return the conference-local date at ``now``: the app's one definition of "today"."""
    return local_date(now, zone)


def time_label(moment: datetime, zone: tzinfo, *, use_24h: bool) -> str:
    """Return the conference-local time of ``moment``: "9:25 AM", or "09:25" in 24-hour form."""
    local = _local(moment, zone)
    if use_24h:
        return f"{local.hour:02d}:{local.minute:02d}"
    return f"{_clock12(local)} {_meridiem(local)}"


def time_range_label(
    start: datetime, end: datetime, zone: tzinfo, *, use_24h: bool
) -> str:
    """Return a conference-local range as ux.md writes it.

    "9:25–10:10 AM" when both ends share AM or PM, "11:30 AM–12:15 PM" when they don't, and
    a single time when the range is empty (a notice such as "Registration opens").
    In 24-hour form: "09:25–10:10".
    """
    if start == end:
        return time_label(start, zone, use_24h=use_24h)
    first, last = _local(start, zone), _local(end, zone)
    if use_24h:
        return f"{time_label(first, zone, use_24h=True)}–{time_label(last, zone, use_24h=True)}"
    if first.date() == last.date() and _meridiem(first) == _meridiem(last):
        return f"{_clock12(first)}–{_clock12(last)} {_meridiem(last)}"
    return f"{_clock12(first)} {_meridiem(first)}–{_clock12(last)} {_meridiem(last)}"


def day_label(day: date) -> str:
    """Return a short date label, e.g. "Fri, May 15"."""
    return f"{_WEEKDAYS[day.weekday()][:3]}, {_MONTHS[day.month - 1][:3]} {day.day}"


def day_heading(day: date) -> str:
    """Return a day heading, e.g. "Friday, May 15"."""
    return f"{_WEEKDAYS[day.weekday()]}, {_MONTHS[day.month - 1]} {day.day}"


def zone_note(
    now: datetime, zone: tzinfo, zone_name: str, device_offset: timedelta | None
) -> str | None:
    """Return a note such as "Times are Pacific Time (PDT)" when the device's clock differs.

    Args:
        now: The current instant.
        zone: The conference zone.
        zone_name: Its display name from the year data, e.g. "Pacific Time".
        device_offset: The device's UTC offset at ``now``; the UI passes
            ``now.astimezone().utcoffset()``.

    Returns:
        The note, or None when the device shows the same wall-clock time as the conference.
    """
    local = _local(now, zone)
    if local.utcoffset() == device_offset:
        return None
    return f"Times are {zone_name} ({local.tzname()})"


def _local(moment: datetime, zone: tzinfo) -> datetime:
    if moment.utcoffset() is None:
        raise ValueError(f"expected an aware datetime, got {moment!r}")
    return moment.astimezone(zone)


def _clock12(local: datetime) -> str:
    return f"{local.hour % 12 or 12}:{local.minute:02d}"


def _meridiem(local: datetime) -> str:
    return "AM" if local.hour < 12 else "PM"
