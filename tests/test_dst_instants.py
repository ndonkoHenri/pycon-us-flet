"""Session times compare as instants across the end of summer time (D-43, #535).

On 2026-11-01 Pacific time falls back from 2:00 PDT to 1:00 PST, so 1:00 to 2:00 comes
twice. Two datetimes that share the conference ``ZoneInfo`` compare by wall clock and
ignore ``fold``, so 1:10 PST would read as before 1:40 PDT. Every case here has a wall
clock that disagrees with the instants; each passes only when the code compares in UTC.
Only a shifted feed (#383) can put a session on that night.
"""

from dataclasses import replace
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from pycon_us.config import load_year
from pycon_us.core.agenda import Agenda, AgendaDay, fold_ended, my_schedule, next_for_me
from pycon_us.core.ics import calendar_file
from pycon_us.core.models import ConferenceData, Session
from pycon_us.core.timefmt import instant
from pycon_us.core.timeline import Slot, now_place
from pycon_us.reminder_settings import ReminderSettings
from pycon_us.services.reminders import due_session, plan
from pycon_us.year_moments import keynote_moments
from tests.feeds import processed

ZONE = ZoneInfo("America/Los_Angeles")
"""2026's conference zone."""

NIGHT = date(2026, 11, 1)
"""The night summer time ends in the conference zone."""


def at(hour: int, minute: int) -> datetime:
    """Return ``hour:minute`` UTC on the night of the change, read in the conference zone."""
    return datetime(2026, 11, 1, hour, minute, tzinfo=UTC).astimezone(ZONE)


ACROSS = (at(8, 40), at(9, 10))
"""1:40 PDT to 1:10 PST: half an hour across the change, its wall clocks backwards."""

LATE = (at(8, 50), at(9, 30))
"""1:50 PDT to 1:30 PST: starts while ``ACROSS`` is on, though its wall clock is later."""

AFTER_THE_CHANGE = (at(9, 5), at(9, 35))
"""1:05 PST to 1:35 PST: a talk that starts in the repeated hour."""


@pytest.fixture(scope="module")
def data() -> ConferenceData:
    """2026's recorded feed, processed: its sessions are retimed onto the night."""
    return processed(2026)


def retimed(
    data: ConferenceData, session_id: str, span: tuple[datetime, ...]
) -> Session:
    """Return a 2026 session moved to ``span`` (start, end) on the night of the change."""
    start, end = span
    return replace(
        data.sessions[session_id], start=start, display_start=start, end=end, day=NIGHT
    )


def with_sessions(data: ConferenceData, *sessions: Session) -> ConferenceData:
    """Return ``data`` holding only ``sessions``, by id."""
    return replace(data, sessions={s.id: s for s in sessions})


def test_instant_is_utc_and_orders_the_repeated_hour() -> None:
    """``instant`` puts 1:10 PST after 1:40 PDT, which their wall clocks reverse."""
    start, end = ACROSS
    assert end < start  # the wall-clock comparison this module guards against
    assert instant(end) > instant(start)
    assert instant(end).tzinfo is UTC
    assert instant(end) == datetime(2026, 11, 1, 9, 10, tzinfo=UTC)


def test_a_calendar_event_across_the_change_keeps_its_end(data: ConferenceData) -> None:
    """The exported event has a ``DTEND`` half an hour after its ``DTSTART``."""
    talk = retimed(data, "142", ACROSS)
    text = calendar_file([talk], year=2026, now=at(7, 0)).decode()
    assert "DTSTART:20261101T084000Z" in text
    assert "DTEND:20261101T091000Z" in text


def test_a_session_across_the_change_has_not_ended_in_the_first_hour(
    data: ConferenceData,
) -> None:
    """At 1:50 PDT the 1:40 PDT-1:10 PST talk is still to come in My schedule."""
    talk = retimed(data, "142", ACROSS)
    agenda = Agenda((AgendaDay(NIGHT, (Slot(talk.start, (talk,)),)),), {})
    folded = fold_ended(agenda, at(8, 50), ZONE)
    assert folded.earlier_today is None
    assert [s for d in folded.ahead for slot in d.slots for s in slot.sessions] == [
        talk
    ]
    later = fold_ended(agenda, at(9, 10), ZONE)  # 1:10 PST: it has ended
    assert later.earlier_today is not None
    assert not later.ahead


def test_sessions_across_the_change_overlap(data: ConferenceData) -> None:
    """A talk starting at 1:50 PDT overlaps one that runs until 1:10 PST."""
    first = retimed(data, "142", ACROSS)
    second = retimed(data, "153", LATE)
    agenda = my_schedule(with_sessions(data, first, second), {first.id, second.id})
    assert agenda.overlaps == {first: (second,), second: (first,)}


def test_the_agenda_lists_the_repeated_hour_after_the_first(
    data: ConferenceData,
) -> None:
    """1:05 PST comes after 1:40 PDT in My schedule, though its wall clock is earlier."""
    first = retimed(data, "142", ACROSS)
    second = retimed(data, "153", AFTER_THE_CHANGE)
    agenda = my_schedule(with_sessions(data, first, second), {first.id, second.id})
    assert [slot.sessions for slot in agenda.days[0].slots] == [(first,), (second,)]


def test_your_next_session_is_the_one_on_across_the_change(
    data: ConferenceData,
) -> None:
    """At 1:50 PDT the talk running until 1:10 PST is the saved session that is on."""
    talk = retimed(data, "142", ACROSS)
    assert next_for_me(with_sessions(data, talk), {talk.id}, at(8, 50)) is talk


def test_the_now_line_marks_a_slot_on_across_the_change(data: ConferenceData) -> None:
    """At 1:50 PDT the slot of the 1:40 PDT-1:10 PST talk is the one that is on."""
    talk = retimed(data, "142", ACROSS)
    slot = Slot(talk.start, (talk,))
    assert now_place([slot], at(8, 50)).on == slot.key
    assert now_place([slot], at(9, 10)).on is None  # 1:10 PST: over


def test_a_reminder_in_the_repeated_hour_is_due_its_lead_before(
    data: ConferenceData,
) -> None:
    """A talk at 1:05 PST is reminded at 1:55 PDT, ten minutes before, not 70."""
    talk = retimed(data, "142", AFTER_THE_CHANGE)
    settings = ReminderSettings(
        lightning=False, open_space=False, keynote=False, session_lead=10
    )
    [reminder] = plan(
        with_sessions(data, talk),
        [talk.id],
        settings,
        [],
        at(7, 0),
        zone=ZONE,
        use_24h=False,
    )
    assert instant(reminder.at) == datetime(2026, 11, 1, 8, 55, tzinfo=UTC)


def test_the_banner_counts_minutes_to_a_start_in_the_repeated_hour(
    data: ConferenceData,
) -> None:
    """At 1:57 PDT a talk at 1:05 PST is 8 minutes away, inside the Banner's lead."""
    talk = retimed(data, "142", AFTER_THE_CHANGE)
    due = due_session(with_sessions(data, talk), [talk.id], at(8, 57))
    assert due is not None
    assert due.minutes == 8


def test_a_keynote_in_the_repeated_hour_is_due_its_lead_before(
    data: ConferenceData,
) -> None:
    """A keynote at 1:05 PST gets its moment 15 minutes before, at 1:50 PDT, not 75."""
    keynote = retimed(data, "153", AFTER_THE_CHANGE)
    keynotes = load_year(2026).content.keynotes
    moments = keynote_moments(
        with_sessions(data, keynote), keynotes, ZONE, use_24h=False
    )
    [moment] = [m for m in moments if m.session_id == keynote.id]
    assert instant(moment.at) == datetime(2026, 11, 1, 8, 50, tzinfo=UTC)


def test_the_same_wall_time_twice_is_two_slots(data: ConferenceData) -> None:
    """1:30 PDT and 1:30 PST are an hour apart: My schedule lists two slots, not one."""
    first = retimed(data, "142", (at(8, 30), at(8, 45)))  # 1:30-1:45 PDT
    second = retimed(data, "153", (at(9, 30), at(9, 45)))  # 1:30-1:45 PST
    agenda = my_schedule(with_sessions(data, first, second), {first.id, second.id})
    assert [slot.sessions for slot in agenda.days[0].slots] == [(first,), (second,)]
