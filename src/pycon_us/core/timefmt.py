"""Conference-local days and time labels (D-35, D-43; DATA-12, SCHED-18).

Times are always shown in the conference's zone, whatever the device's zone. Every function
here is pure: the instant (``now`` included) and the zone are arguments, and the 12/24-hour
choice is passed in by the UI (from ``page.media.always_use_24_hour_format``). Day and month
names come from fixed English tuples and labels are built by hand, so nothing depends on the
device locale or on ``strftime`` flags. Naive datetimes are refused: they have no instant.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, tzinfo

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
    first, last = _local(start, zone), _local(end, zone)
    # Compare in UTC: datetimes sharing a tzinfo compare wall times and ignore DST folds.
    if first.astimezone(UTC) == last.astimezone(UTC):
        return time_label(first, zone, use_24h=use_24h)
    if use_24h:
        return f"{time_label(first, zone, use_24h=True)}–{time_label(last, zone, use_24h=True)}"
    if first.date() == last.date() and _meridiem(first) == _meridiem(last):
        return f"{_clock12(first)}–{_clock12(last)} {_meridiem(last)}"
    return f"{_clock12(first)} {_meridiem(first)}–{_clock12(last)} {_meridiem(last)}"


def on_screen(label: str) -> str:
    """Return a time or a range as a line shows it: it can break only after its dash.

    Its spaces become no-break spaces, so "AM" keeps to its digits, and a time never
    breaks: "9:45–10:30 AM" stays on one line whenever it fits, and a range wider
    than its line breaks after its en dash, "9:45–" / "10:30 AM", the one break
    Unicode allows in it (D-229). No word joiner at the dash: with no break left,
    Flutter breaks a run wider than its line inside a time ("9:00 AM–12" / ":30 PM",
    D-186), and a range always starts its own line, so a joiner never keeps one whole.
    Shared text (``row_views.share_text()``) and spoken labels keep plain spaces.

    Args:
        label: A ``time_label()`` or ``time_range_label()``.
    """
    return label.replace(" ", "\N{NO-BREAK SPACE}")


def day_label(day: date) -> str:
    """Return a short date label, e.g. "Fri, May 15"."""
    return f"{_WEEKDAYS[day.weekday()][:3]}, {_MONTHS[day.month - 1][:3]} {day.day}"


def day_heading(day: date) -> str:
    """Return a day heading, e.g. "Friday, May 15"."""
    return f"{_WEEKDAYS[day.weekday()]}, {_MONTHS[day.month - 1]} {day.day}"


def day_tab_label(day: date) -> str:
    """Return a day tab's one-line label, e.g. "Fri 15" (SCHED-01).

    One line, so the tab keeps its text at 200 %, where a second line is clipped by
    the tab bar's fixed height (S2); the month is in the spoken label
    (``day_heading()``).
    """
    return f"{_WEEKDAYS[day.weekday()][:3]} {day.day}"


def weekday_name(day: date) -> str:
    """Return the day's name, e.g. "Friday"."""
    return _WEEKDAYS[day.weekday()]


def date_range_label(first: date, last: date) -> str:
    """Return a span of days as people write it: "May 13–19", "May 30–June 2".

    One date when both ends are the same day ("May 13"); the year is left out, as the
    screens name the conference beside it.
    """
    start = f"{_MONTHS[first.month - 1]} {first.day}"
    if first == last:
        return start
    if (first.year, first.month) == (last.year, last.month):
        return f"{start}–{last.day}"
    return f"{start}–{_MONTHS[last.month - 1]} {last.day}"


def day_range_label(first: date, last: date) -> str:
    """Return a span of days with their weekdays: "Mon, May 18 – Tue, May 19".

    One day when both ends are the same ("Mon, May 18"). For a span whose weekdays
    matter, as the key dates and the sprints are; ``date_range_label()`` is the short
    form.
    """
    if first == last:
        return day_label(first)
    return f"{day_label(first)} – {day_label(last)}"


def ago_label(then: datetime, now: datetime) -> str:
    """Return how long before ``now`` ``then`` was, in words (DATA-31).

    "just now" under a minute (and for a ``then`` after ``now``, as a fake clock can
    make it), then whole minutes, hours or days, rounded down: "1 minute ago",
    "9 hours ago", "3 days ago". Words, not "9 h", so screen readers say them.
    """
    seconds = (_local(now, UTC) - _local(then, UTC)).total_seconds()
    minutes = int(max(seconds, 0) // 60)
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return _ago(minutes, "minute")
    if minutes < 24 * 60:
        return _ago(minutes // 60, "hour")
    return _ago(minutes // (24 * 60), "day")


@dataclass(frozen=True)
class TimeStatus:
    """Where a session stands at an instant, as session detail says it (SESS-01).

    Attributes:
        label: What the screen shows: "Starts in 25 min", "Happening now", "Ended".
        spoken: The same in words for screen readers: "Starts in 25 minutes"
            (D-165's rule for "h"); equal to ``label`` when it has no unit.
        happening: Whether the session is on, which the screen draws in ``live``.
    """

    label: str
    spoken: str
    happening: bool = False


HAPPENING_NOW = TimeStatus("Happening now", "Happening now", happening=True)
"""A session that has started and not ended."""

ENDED = TimeStatus("Ended", "Ended")
"""A session whose end has come."""


def time_status(
    start: datetime, end: datetime, now: datetime, zone: tzinfo
) -> TimeStatus | None:
    """Return where a session stands at ``now``, or None when there is nothing to say.

    A session is on from its start up to, not including, its end (D-179's half-open
    interval), so at 10:30 a talk that ends then has ended. Before it starts, the
    countdown shows only on its own conference-local day, in whole minutes rounded up
    (so it never says "in 0 min"), with hours from 60 minutes: "Starts in 1 h 5 min".
    A notice has no duration: it is never on, and it never says "Ended" (the
    registration desk that opened at 7:30 is still open).

    Args:
        start: When the session starts, aware.
        end: When it ends, aware; equal to ``start`` for a notice.
        now: ``clock.now()``.
        zone: The conference's zone, for "its own day" (D-43).
    """
    on_its_day = local_date(now, zone) == local_date(start, zone)  # refuses naive
    if now < start:
        if not on_its_day:
            return None  # the date beside it says when
        minutes = -(-int((start - now).total_seconds()) // 60)  # rounded up
        hours, rest = divmod(max(minutes, 1), 60)
        short = [f"{hours} h"] if hours else []
        words = [_count(hours, "hour")] if hours else []
        if rest:
            short.append(f"{rest} min")
            words.append(_count(rest, "minute"))
        return TimeStatus(
            f"Starts in {' '.join(short)}", f"Starts in {' '.join(words)}"
        )
    if start == end:
        return None
    return HAPPENING_NOW if now < end else ENDED


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


def utc_offset_label(offset: timedelta) -> str:
    """Return a UTC offset as people write it: "UTC−07:00", "UTC+05:30" or "UTC".

    Args:
        offset: The offset from UTC, e.g. ``now.astimezone().utcoffset()``.
    """
    if not offset:
        return "UTC"
    sign = "+" if offset > timedelta(0) else "−"  # a minus sign, not a hyphen
    minutes = abs(int(offset.total_seconds())) // 60
    return f"UTC{sign}{minutes // 60:02d}:{minutes % 60:02d}"


def _local(moment: datetime, zone: tzinfo) -> datetime:
    if moment.utcoffset() is None:
        raise ValueError(f"expected an aware datetime, got {moment!r}")
    return moment.astimezone(zone)


def _clock12(local: datetime) -> str:
    return f"{local.hour % 12 or 12}:{local.minute:02d}"


def _meridiem(local: datetime) -> str:
    return "AM" if local.hour < 12 else "PM"


def _ago(amount: int, unit: str) -> str:
    return f"{_count(amount, unit)} ago"


def _count(amount: int, unit: str) -> str:
    return f"{amount} {unit}" if amount == 1 else f"{amount} {unit}s"
