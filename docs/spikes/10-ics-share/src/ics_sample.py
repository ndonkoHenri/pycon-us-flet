"""The hand-written calendar file the #364 spike shares.

Two events on 2026-10-22, in UTC as D-62 prescribes: a talk with a ``VALARM``
ten minutes before, and a break without one. The text exercises what
``core/ics.py`` will produce: CRLF line ends, escaped commas, semicolons and
newlines, a line folded at 75 octets, a stable ``UID`` and a ``DTSTAMP``.
"""

LINES = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//pycon-us-flet//ics spike 364//EN",
    "CALSCALE:GREGORIAN",
    "METHOD:PUBLISH",
    "BEGIN:VEVENT",
    "UID:spike-364-talk@pycon-us-flet.invalid",
    "DTSTAMP:20261020T090000Z",
    "DTSTART:20261022T173000Z",
    "DTEND:20261022T180000Z",
    "SUMMARY:Spike talk: typing\\, async and you",
    "LOCATION:Grand Ballroom A\\; Long Beach Convention Center",
    "DESCRIPTION:First line of the description.\\nSecond line\\, with a comma. A l",
    " ong line folded at 75 octets.",
    "URL:https://us.pycon.org/2026/schedule/presentation/42/",
    "BEGIN:VALARM",
    "ACTION:DISPLAY",
    "DESCRIPTION:Spike talk starts in 10 minutes",
    "TRIGGER:-PT10M",
    "END:VALARM",
    "END:VEVENT",
    "BEGIN:VEVENT",
    "UID:spike-364-break@pycon-us-flet.invalid",
    "DTSTAMP:20261020T090000Z",
    "DTSTART:20261022T190000Z",
    "DTEND:20261022T194500Z",
    "SUMMARY:Spike break (no alarm)",
    "LOCATION:Hall A",
    "END:VEVENT",
    "END:VCALENDAR",
]

ICS_BYTES = ("\r\n".join(LINES) + "\r\n").encode()
FILE_NAME = "spike-364.ics"
MIME_TYPE = "text/calendar"
