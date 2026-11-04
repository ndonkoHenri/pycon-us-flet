r"""Calendar files: one session, or a whole agenda, as iCalendar bytes (D-62, D-268; SESS-05).

`calendar_file()` builds the file: session detail's Add to calendar passes one session,
My schedule's export every saved one (P2-65, P2-66), and either hands the bytes to the
calendar (`services.calendar`, D-272) under a name from `file_slug()`. RFC 5545 asks
for CRLF line ends, text escaped (`\`, `;`, `,` and newlines), and lines folded at
75 octets; a fold here never splits a UTF-8 character. Times are UTC, so a calendar
anywhere shows the right instant, and each event carries an alarm, which the original
app's file had none of.

Like the rest of `core`, it is pure: the time the file is made (`now`, D-43) is an
argument, and nothing here imports Flet (D-68).
"""

import re
import unicodedata
from collections.abc import Iterable
from datetime import datetime, timedelta
from urllib.parse import quote

from pycon_us import APP_NAME, CALENDAR_DOMAIN
from pycon_us.core.models import Session
from pycon_us.core.timefmt import instant
from pycon_us.core.timeline import schedule_order

ALARM = timedelta(minutes=10)
"""How long before a session its alarm goes off, by default (ux.md §5.5)."""

LINE_OCTETS = 75
"""The longest a line may be, in octets, without its CRLF (RFC 5545 §3.1)."""

FILE_SLUG_CHARS = 40
"""The longest a calendar file's name may be without `.ics`: a SnackBar says it."""

_NOT_SLUG = re.compile(r"[^a-z0-9]+")
_NEWLINE = re.compile(r"\r\n|\r|\n")
_CONTROL = re.compile(r"[\x00-\x08\x0a-\x1f\x7f]")
"""The control characters a TEXT value may not hold (RFC 5545 §3.3.11); a tab may stay."""


def calendar_file(
    sessions: Iterable[Session],
    *,
    year: int,
    now: datetime,
    alarm: timedelta = ALARM,
) -> bytes:
    """Return an iCalendar file with one event per session, in the Schedule's order.

    One `VCALENDAR`, its events in `timeline.schedule_order` (by the start a row
    shows), so a whole agenda reads in time order. Each event (D-268):

    * `UID`: `<year>-<session id>@<CALENDAR_DOMAIN>`, the id percent-encoded, so
      a collapsed row's spaces and commas stay out. The same session gives the same
      `UID` after every refresh, so a calendar can tell it is one event.
    * `DTSTART` and `DTEND` in UTC, from the start the app shows (the Job Fair's
      9:30, DATA-11) to the end. A notice has no `DTEND`: it ends when it starts, and
      RFC 5545 wants an end after the start.
    * `SUMMARY` its name; `LOCATION` the place its row shows (none for a generic
      break, which is everywhere); `DESCRIPTION` its speakers as the row lists them,
      then its public page; `URL` that page, when the feed gives one: synthetic ids
      and sessions the site has no page for have none (D-206).
    * A `VALARM` that shows its name `alarm` before it starts.

    Args:
        sessions: The sessions, in any order; at least one.
        year: The conference year, so that next year's session with the same id is
            another event.
        now: When the file is made, aware (`DTSTAMP`).
        alarm: How long before each session its alarm goes off; zero for at its start.

    Returns:
        The file's bytes, UTF-8 with CRLF line ends.

    Raises:
        ValueError: When there is no session (a calendar holds at least one event), or
            `now` is naive, or `alarm` is negative.
    """
    events = sorted(sessions, key=schedule_order)
    if not events:
        raise ValueError("a calendar file needs at least one session")
    if now.tzinfo is None:
        raise ValueError("now must be aware")
    if alarm < timedelta(0):
        raise ValueError("alarm must not be negative")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:-//{_text(APP_NAME)}//EN",  # a TEXT value, escaped like the rest
    ]
    for session in events:
        lines += _event(session, year=year, now=now, alarm=alarm)
    lines.append("END:VCALENDAR")
    return "".join(_fold(line) + "\r\n" for line in lines).encode()


def file_slug(name: str) -> str:
    """Return a calendar file's name without `.ics`, from what it holds: its title.

    Lower-case ASCII words joined by `-`, accents dropped (`Café` is `cafe`), cut
    after a whole word at `FILE_SLUG_CHARS`, so the Files app and Android's
    SnackBar show a name a person recognises:
    `python-for-humans-designing-python-code`
    (D-272). A name with no such word (all in another script) gives `session`.

    Args:
        name: The session's name.
    """
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = _NOT_SLUG.sub("-", folded.lower()).strip("-")
    if len(slug) > FILE_SLUG_CHARS:
        cut = slug[: FILE_SLUG_CHARS + 1]
        slug = cut.rsplit("-", 1)[0] if "-" in cut else slug[:FILE_SLUG_CHARS]
    return slug or "session"


def _event(
    session: Session, *, year: int, now: datetime, alarm: timedelta
) -> list[str]:
    """Return the unfolded lines of one session's `VEVENT`, its `VALARM` inside."""
    lines = [
        "BEGIN:VEVENT",
        f"UID:{year}-{quote(session.id, safe='')}@{CALENDAR_DOMAIN}",
        f"DTSTAMP:{_utc(now)}",
        f"DTSTART:{_utc(session.display_start)}",
    ]
    if instant(session.end) > instant(session.display_start):
        lines.append(f"DTEND:{_utc(session.end)}")
    lines.append(f"SUMMARY:{_text(session.name)}")
    if session.display_location:
        lines.append(f"LOCATION:{_text(session.display_location)}")
    details = "\n".join(d for d in (", ".join(session.speaker_names), session.url) if d)
    if details:
        lines.append(f"DESCRIPTION:{_text(details)}")
    if session.url:
        lines.append(f"URL:{session.url}")
    lines += [
        "BEGIN:VALARM",
        "ACTION:DISPLAY",
        f"DESCRIPTION:{_text(session.name)}",
        f"TRIGGER:{_before(alarm)}",
        "END:VALARM",
        "END:VEVENT",
    ]
    return lines


def _utc(moment: datetime) -> str:
    """Return an aware instant as a UTC DATE-TIME: `20260516T173000Z`."""
    return instant(moment).strftime("%Y%m%dT%H%M%SZ")


def _text(value: str) -> str:
    r"""Return `value` as a TEXT value: escaped, each newline a `\n` (RFC 5545 §3.3.11)."""
    value = value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
    return _CONTROL.sub("", _NEWLINE.sub("\\\\n", value))


def _before(lead: timedelta) -> str:
    """Return a trigger `lead` before the start: `-PT10M`, `-PT1H30M`, `PT0S`."""
    seconds = int(lead.total_seconds())
    if not seconds:
        return "PT0S"
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    parts = ((hours, "H"), (minutes, "M"), (seconds, "S"))
    return "-PT" + "".join(f"{n}{unit}" for n, unit in parts if n)


def _fold(line: str) -> str:
    """Return `line` folded so no line passes `LINE_OCTETS` octets of UTF-8.

    Each continuation starts with a space, which counts toward its octets. A fold
    falls between characters, never inside one's bytes, so every line stays valid
    UTF-8 for a reader that decodes before it unfolds.
    """
    parts: list[str] = []
    current = ""
    size = 0
    room = LINE_OCTETS
    for char in line:
        width = len(char.encode())
        if size + width > room:
            parts.append(current)
            current, size, room = "", 0, LINE_OCTETS - 1
        current += char
        size += width
    parts.append(current)
    return "\r\n ".join(parts)
