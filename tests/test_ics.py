"""Tests for the calendar files of a session or a whole agenda (``core/ics.py``; D-62, D-268).

Every test runs under both machine zones (D-43): the file's times are UTC whatever the
device's zone.
"""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import icalendar
import pytest
from ical.calendar_stream import IcsCalendarStream

from pycon_us import APP_NAME
from pycon_us.core.feed import process
from pycon_us.core.ics import (
    ALARM,
    FILE_SLUG_CHARS,
    LINE_OCTETS,
    calendar_file,
    file_slug,
)
from pycon_us.core.models import ConferenceData, Session
from pycon_us.core.timeline import schedule_order
from tests.feeds import YEARS, processed, recorded, settings

pytestmark = pytest.mark.usefixtures("machine_tz")

NOW = datetime(2026, 5, 1, 5, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
"""When the files are made: 12:00 UTC, given in another zone on purpose."""

COLLAPSED = (
    "break-Room 103ABC, Room 104AB, Room 104C, Grand Ballroom A, Grand Ballroom B"
    "-2026-05-16T10:05:00-07:00"
)
"""A collapsed break's synthetic id in the 2026 feed: spaces, commas and colons."""

ODD_NAME = "Foo; Bar, 2027"
"""An app name that a TEXT value must escape: a semicolon and a comma."""


def lines(data: bytes) -> list[str]:
    """Return a file's physical lines, decoded, without the empty one after the last CRLF."""
    assert data.endswith(b"\r\n")
    return [line.decode() for line in data.split(b"\r\n")[:-1]]


def unfolded(data: bytes) -> list[str]:
    """Return a file's content lines, each continuation joined back (RFC 5545 §3.1)."""
    return data.decode().replace("\r\n ", "").split("\r\n")[:-1]


def values(data: bytes, name: str) -> list[str]:
    """Return the value of every unfolded ``name:`` line, in the file's order."""
    prefix = f"{name}:"
    return [
        line.removeprefix(prefix) for line in unfolded(data) if line.startswith(prefix)
    ]


def one(data: ConferenceData, session_id: str, alarm: timedelta = ALARM) -> bytes:
    """Return the 2026 calendar file of one session of ``data``, made at ``NOW``."""
    return calendar_file([data.sessions[session_id]], year=2026, now=NOW, alarm=alarm)


def test_one_sessions_file_is_pinned_byte_for_byte() -> None:
    """A talk's file is exactly this: CRLF, escaped commas, folded lines and an alarm."""
    expected = (
        b"BEGIN:VCALENDAR\r\n"
        b"VERSION:2.0\r\n"
        b"PRODID:-//Conf Companion//EN\r\n"
        b"BEGIN:VEVENT\r\n"
        b"UID:2026-101@confcompanion.ndonkohenri.github.io\r\n"
        b"DTSTAMP:20260501T120000Z\r\n"
        b"DTSTART:20260516T001500Z\r\n"
        b"DTEND:20260516T004500Z\r\n"
        b"SUMMARY:How to Build Your First Real-Time Voice Agent in Python (Without Lo\r\n"
        b" sing Your Mind)\r\n"
        b"LOCATION:Grand Ballroom A\r\n"
        b"DESCRIPTION:Camila Hinojosa A\xc3\xb1ez\\, Elizabeth Fuentes\\nhttps://us.pycon.org\r\n"
        b" /2026/schedule/presentation/101/\r\n"
        b"URL:https://us.pycon.org/2026/schedule/presentation/101/\r\n"
        b"BEGIN:VALARM\r\n"
        b"ACTION:DISPLAY\r\n"
        b"DESCRIPTION:How to Build Your First Real-Time Voice Agent in Python (Withou\r\n"
        b" t Losing Your Mind)\r\n"
        b"TRIGGER:-PT10M\r\n"
        b"END:VALARM\r\n"
        b"END:VEVENT\r\n"
        b"END:VCALENDAR\r\n"
    )
    assert one(processed(2026), "101") == expected


def test_prodid_names_the_app_and_no_psf_mark() -> None:
    """``PRODID`` comes from the app's display name, never from the conference's."""
    data = one(processed(2026), "142")
    assert values(data, "PRODID") == [f"-//{APP_NAME}//EN"]
    assert "PyCon" not in values(data, "PRODID")[0]


def test_prodid_escapes_the_app_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """``PRODID`` is TEXT: a semicolon or comma in the app's name is escaped."""
    monkeypatch.setattr("pycon_us.core.ics.APP_NAME", ODD_NAME)
    assert lines(one(processed(2026), "142"))[2] == "PRODID:-//Foo\\; Bar\\, 2027//EN"


@pytest.mark.parametrize("year", YEARS)
def test_no_line_of_a_whole_feed_passes_75_octets_or_splits_a_character(
    year: int,
) -> None:
    """Every physical line of a whole feed's file fits 75 octets and is valid UTF-8."""
    data = calendar_file(processed(year).sessions.values(), year=year, now=NOW)
    for raw in data.split(b"\r\n"):
        assert len(raw) <= LINE_OCTETS
        raw.decode()  # a fold inside a character raises UnicodeDecodeError here


@pytest.mark.parametrize("char", ["é", "€", "💗"])
def test_folding_falls_between_multibyte_characters(char: str) -> None:
    """A name of two-, three- or four-octet characters folds between them and unfolds back."""
    data = processed(2026)
    session = replace(data.sessions["142"], name=char * 90)
    file = calendar_file([session], year=2026, now=NOW)
    summary = [line for line in lines(file) if line.startswith(("SUMMARY:", " "))]
    assert len(summary) > 2
    assert all(len(line.encode()) <= LINE_OCTETS for line in summary)
    assert values(file, "SUMMARY") == [char * 90]


def test_a_line_of_exactly_75_octets_is_not_folded() -> None:
    """A line that fits 75 octets exactly stays one line; one more octet folds it."""
    data = processed(2026)
    fits = "x" * (LINE_OCTETS - len("SUMMARY:"))
    file = calendar_file([replace(data.sessions["142"], name=fits)], year=2026, now=NOW)
    assert f"SUMMARY:{fits}" in lines(file)
    longer = calendar_file(
        [replace(data.sessions["142"], name=fits + "y")], year=2026, now=NOW
    )
    assert f"SUMMARY:{fits}" in lines(longer)
    assert " y" in lines(longer)


def test_times_are_utc_from_the_start_the_app_shows() -> None:
    """A 10:30 PDT talk starts at 17:30 UTC; the Job Fair at its shown 9:30 (DATA-11)."""
    data = processed(2026)
    talk = one(data, "142")
    assert values(talk, "DTSTART") == ["20260516T173000Z"]
    assert values(talk, "DTEND") == ["20260516T180000Z"]
    assert values(talk, "DTSTAMP") == ["20260501T120000Z"]
    job_fair = data.sessions["178"]
    assert job_fair.display_start < job_fair.start
    assert values(one(data, "178"), "DTSTART") == ["20260517T163000Z"]


def test_a_notice_has_no_end() -> None:
    """A notice, which ends when it starts, gets no ``DTEND`` (RFC 5545 wants it later)."""
    data = processed(2026)
    notice = data.sessions["196"]
    assert notice.end == notice.start
    file = one(data, "196")
    assert values(file, "DTSTART") == ["20260513T143000Z"]
    assert values(file, "DTEND") == []


@pytest.mark.parametrize("year", YEARS)
def test_uids_are_the_same_across_two_loads_and_unique(year: int) -> None:
    """Two loads of the same feed give the same ``UID``s, one per session."""
    sessions = processed(year).sessions
    first = calendar_file(sessions.values(), year=year, now=NOW)
    later = NOW + timedelta(days=3)
    reloaded = process(recorded(year), settings(year))
    second = calendar_file(reloaded.sessions.values(), year=year, now=later)
    uids = values(first, "UID")
    assert uids == values(second, "UID")
    assert len(set(uids)) == len(sessions)


def test_a_uid_names_the_year_and_keeps_out_spaces_and_commas() -> None:
    """A ``UID`` is ``<year>-<id>@<domain>``, a synthetic id percent-encoded."""
    data = processed(2026)
    assert values(one(data, "142"), "UID") == [
        "2026-142@confcompanion.ndonkohenri.github.io"
    ]
    (uid,) = values(one(data, COLLAPSED), "UID")
    assert uid.startswith("2026-break-Room%20103ABC%2C%20Room%20104AB%2C")
    assert uid.endswith("-07%3A00@confcompanion.ndonkohenri.github.io")
    file = calendar_file([data.sessions["142"]], year=2027, now=NOW)
    assert values(file, "UID") == ["2027-142@confcompanion.ndonkohenri.github.io"]


@pytest.mark.parametrize("session_id", [COLLAPSED, "poster-detail-60"])
def test_synthetic_ids_get_no_url(session_id: str) -> None:
    """A collapsed break and a poster detail have no page: no ``URL``, none in the text."""
    file = one(processed(2026), session_id)
    assert values(file, "URL") == []
    assert "https://" not in file.decode()


def test_a_poster_lists_its_authors_without_a_page() -> None:
    """A poster detail's description is its authors alone (D-206)."""
    file = one(processed(2026), "poster-detail-52")
    assert values(file, "DESCRIPTION")[0] == r"Wenxin Jiang\, Jian Yin"


def test_a_generic_break_has_no_location_and_no_description() -> None:
    """A break that is everywhere has no ``LOCATION``, and nothing to describe."""
    file = one(processed(2026), COLLAPSED)
    assert values(file, "LOCATION") == []
    assert values(file, "DESCRIPTION") == ["Break"]  # the alarm's, alone


def test_lightning_talks_are_at_the_place_their_row_shows() -> None:
    """The lightning talks' place is the year's hall, as the row shows (D-124)."""
    file = one(processed(2026), "175")
    assert values(file, "LOCATION") == ["Pacific Ballroom - Arena"]


def test_text_is_escaped_and_control_characters_dropped() -> None:
    """Backslashes, semicolons, commas and newlines are escaped; other controls go."""
    data = processed(2026)
    session = replace(data.sessions["142"], name="a,b;c\\d\r\ne\tf\x07g")
    file = calendar_file([session], year=2026, now=NOW)
    assert values(file, "SUMMARY") == ["a\\,b\\;c\\\\d\\ne\tfg"]


@pytest.mark.parametrize("year", YEARS)
def test_a_whole_agenda_is_one_calendar_in_start_order(year: int) -> None:
    """Every session, given backwards, is one ``VCALENDAR`` of events by start."""
    data = processed(year)
    file = calendar_file(reversed(list(data.sessions.values())), year=year, now=NOW)
    content = unfolded(file)
    assert content.count("BEGIN:VCALENDAR") == 1
    assert content[0] == "BEGIN:VCALENDAR"
    assert content[-1] == "END:VCALENDAR"
    assert content.count("BEGIN:VEVENT") == len(data.sessions)
    assert content.count("BEGIN:VALARM") == len(data.sessions)
    starts = values(file, "DTSTART")
    assert starts == sorted(starts)


def test_the_agenda_order_is_the_schedules() -> None:
    """Sessions at the same start come in the Schedule's order: by place, then name."""
    data = processed(2026)
    ids = ["218", "51", "142", "196"]  # 196 is days earlier; the rest share 10:30
    file = calendar_file([data.sessions[i] for i in ids], year=2026, now=NOW)
    assert values(file, "UID") == [
        "2026-196@confcompanion.ndonkohenri.github.io",
        "2026-142@confcompanion.ndonkohenri.github.io",  # Grand Ballroom A
        "2026-51@confcompanion.ndonkohenri.github.io",  # Grand Ballroom B
        "2026-218@confcompanion.ndonkohenri.github.io",  # Room 201A
    ]


@pytest.mark.parametrize(
    ("alarm", "trigger"),
    [
        (timedelta(minutes=5), "-PT5M"),
        (timedelta(minutes=15), "-PT15M"),
        (timedelta(minutes=90), "-PT1H30M"),
        (timedelta(seconds=30), "-PT30S"),
        (timedelta(0), "PT0S"),
    ],
)
def test_the_alarm_lead_is_a_parameter(alarm: timedelta, trigger: str) -> None:
    """The alarm goes off the given lead before the start; zero is at the start."""
    file = one(processed(2026), "142", alarm=alarm)
    assert values(file, "TRIGGER") == [trigger]
    assert values(file, "ACTION") == ["DISPLAY"]


def test_bad_arguments_are_refused() -> None:
    """No session, a naive ``now`` or a negative lead raises ``ValueError``."""
    session = processed(2026).sessions["142"]
    with pytest.raises(ValueError, match="at least one session"):
        calendar_file([], year=2026, now=NOW)
    with pytest.raises(ValueError, match="aware"):
        calendar_file([session], year=2026, now=datetime(2026, 5, 1))  # noqa: DTZ001
    with pytest.raises(ValueError, match="negative"):
        calendar_file(
            [session], year=2026, now=NOW.astimezone(UTC), alarm=timedelta(minutes=-1)
        )


def shown(session: Session) -> tuple[object, ...]:
    """Return what a calendar should read back for ``session``.

    Its name, place, description, start and end, each ``None`` when the file leaves the
    property out: no place for a generic break, no end for a notice.
    """
    details = "\n".join(d for d in (", ".join(session.speaker_names), session.url) if d)
    return (
        session.name,
        session.display_location or None,
        details or None,
        session.display_start,
        session.end if session.end > session.display_start else None,
    )


def agenda(year: int, monkeypatch: pytest.MonkeyPatch) -> tuple[bytes, list[tuple]]:
    """Return a year's whole-agenda file under ``ODD_NAME`` and what each event holds."""
    monkeypatch.setattr("pycon_us.core.ics.APP_NAME", ODD_NAME)
    sessions = sorted(processed(year).sessions.values(), key=schedule_order)
    return calendar_file(sessions, year=year, now=NOW), [shown(s) for s in sessions]


# The two parser tests below are D-268's independent check: readers we didn't write, so
# a misreading of RFC 5545 that core/ics.py shares with the tests above can't hide.


@pytest.mark.parametrize("year", YEARS)
def test_icalendar_reads_every_session_back(
    year: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``icalendar`` parses a whole agenda: each event and alarm reads back unchanged."""
    file, expected = agenda(year, monkeypatch)
    calendar = icalendar.Calendar.from_ical(file)
    events = calendar.walk("VEVENT")
    assert str(calendar["PRODID"]) == f"-//{ODD_NAME}//EN"
    assert [e.errors for e in events if e.errors] == []

    def text(event, name: str) -> str | None:
        """Return the event's ``name`` property as a string, ``None`` when absent."""
        return str(event[name]) if name in event else None

    read = [
        (
            text(e, "SUMMARY"),
            text(e, "LOCATION"),
            text(e, "DESCRIPTION"),
            e.decoded("DTSTART"),
            e.decoded("DTEND") if "DTEND" in e else None,
        )
        for e in events
    ]
    assert read == expected
    assert [len(e.walk("VALARM")) for e in events] == [1] * len(expected)


@pytest.mark.parametrize("year", YEARS)
def test_ical_reads_every_session_back(
    year: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stricter ``ical`` parses a whole agenda: each event reads back unchanged."""
    file, expected = agenda(year, monkeypatch)
    calendar = IcsCalendarStream.calendar_from_ics(file.decode())
    assert calendar.prodid == f"-//{ODD_NAME}//EN"
    read = [
        (e.summary, e.location, e.description, e.dtstart, e.dtend)
        for e in calendar.events
    ]
    assert read == expected
    assert [len(e.alarm) for e in calendar.events] == [1] * len(expected)


# ------------------------------------------------------------------ the file's name


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        ("Lightning Talks", "lightning-talks"),
        ("Café & Croissants: a 101", "cafe-croissants-a-101"),
        (
            "Python for Humans - Designing Python Code Like a User Interface",
            "python-for-humans-designing-python-code",
        ),
        ("日本語のトーク", "session"),
        ("", "session"),
    ],
)
def test_a_file_s_name_is_its_title_s_first_words(name: str, slug: str) -> None:
    """Lower-case ASCII words joined by ``-``, cut after a word; none gives ``session``."""
    assert file_slug(name) == slug


def test_a_file_s_name_is_never_longer_than_its_limit() -> None:
    """A title of one long word is cut inside it; a cut never leaves a trailing ``-``."""
    assert file_slug("a" * 50) == "a" * FILE_SLUG_CHARS
    long_title = "talk " * 20
    assert len(file_slug(long_title)) <= FILE_SLUG_CHARS
    assert not file_slug(long_title).endswith("-")
