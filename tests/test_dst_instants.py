"""Session times compare as instants across the end of summer time (D-43, #535).

On 2026-11-01 Pacific time falls back from 2:00 PDT to 1:00 PST, so 1:00 to 2:00 comes
twice. Two datetimes that share the conference ``ZoneInfo`` compare by wall clock and
ignore ``fold``, so 1:10 PST would read as before 1:40 PDT. Every case here has a wall
clock that disagrees with the instants; each passes only when the code compares in UTC.
Only a shifted feed (#383) can put a session on that night.
"""

from dataclasses import replace
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from pycon_us.config import load_year
from pycon_us.core.agenda import (
    Agenda,
    AgendaDay,
    Phase,
    fold_ended,
    my_schedule,
    next_for_me,
    now_next,
)
from pycon_us.core.diff import ChangeKind, diff
from pycon_us.core.feed import process
from pycon_us.core.ics import calendar_file
from pycon_us.core.models import ConferenceData, Session
from pycon_us.core.rooms import room_now
from pycon_us.core.row_views import by_slot, session_view
from pycon_us.core.timefmt import ENDED, HAPPENING_NOW, instant, time_status
from pycon_us.core.timeline import Slot, now_place, schedule_order, timeline
from pycon_us.reminder_settings import ReminderSettings
from pycon_us.services.reminder_plan import plan
from pycon_us.ui.reminder_banner import due_session
from pycon_us.year_moments import keynote_moments
from tests.feeds import changed, processed, settings

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


def night_feed(
    first: tuple[datetime, ...], second: tuple[datetime, ...]
) -> ConferenceData:
    """Return 2026's feed processed with talks 142 and 153 moved to ``first`` and ``second``.

    The feed's own times are rewritten, so the Schedule's days and time groups are built
    from them as from any feed.
    """
    return feed_moved({142: first, 153: second})


def feed_moved(spans: dict[int, tuple[datetime, ...]]) -> ConferenceData:
    """Return 2026's feed processed with each slot (by ``conf_key``) moved to its span.

    The feed's own times are rewritten, so everything processing derives from them (days,
    time groups, rooms, collapsed rows, displayed starts) is built as from any feed.
    """

    def move(doc: dict[str, Any]) -> None:
        """Rewrite the slots' start and end in the feed's JSON."""
        for item in doc["schedule"]:
            if (span := spans.get(item.get("conf_key"))) is not None:
                item["start"], item["end"] = (moment.isoformat() for moment in span)

    return process(changed(2026, move), settings(2026))


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


def test_the_schedule_shows_the_same_wall_time_twice_as_two_slots() -> None:
    """The Schedule's night has a 1:30 PDT slot, then a 1:30 PST slot, not one merged slot."""
    data = night_feed((at(8, 30), at(8, 45)), (at(9, 30), at(9, 45)))
    slots = timeline(data, NIGHT, ())
    assert [[s.id for s in slot.sessions] for slot in slots] == [["142"], ["153"]]
    assert [slot.start for slot in slots] == [at(8, 30), at(9, 30)]
    assert slots[0].key != slots[1].key  # each slot keeps its own offset


def test_the_schedule_lists_the_repeated_hour_after_the_first() -> None:
    """On the Schedule, 1:40 PDT comes before 1:05 PST, though its wall clock is later."""
    data = night_feed(ACROSS, AFTER_THE_CHANGE)
    slots = timeline(data, NIGHT, ())
    assert [[s.id for s in slot.sessions] for slot in slots] == [["142"], ["153"]]


def test_schedule_order_puts_sessions_in_the_order_they_happen(
    data: ConferenceData,
) -> None:
    """``schedule_order`` sorts a 1:40 PDT talk before a 1:05 PST one."""
    first = retimed(data, "153", ACROSS)
    second = retimed(data, "142", AFTER_THE_CHANGE)
    assert sorted([second, first], key=schedule_order) == [first, second]


def test_a_rooms_day_shows_the_same_wall_time_twice_as_two_slots(
    data: ConferenceData,
) -> None:
    """``by_slot`` keeps 1:30 PDT and 1:30 PST apart, in the order they happen."""
    first = retimed(data, "142", (at(8, 30), at(8, 45)))
    second = retimed(data, "153", (at(9, 30), at(9, 45)))
    views = [session_view(s, ZONE, use_24h=False) for s in (second, first)]
    slots = by_slot(views)
    assert [(start, [v.session for v in group]) for start, group in slots] == [
        (at(8, 30), [first]),
        (at(9, 30), [second]),
    ]


def test_a_move_by_the_repeated_hour_is_a_time_change(data: ConferenceData) -> None:
    """A talk moved from 1:30 PDT to 1:30 PST shows in the change log as a new time."""
    before = retimed(data, "142", (at(8, 30), at(8, 45)))
    after = retimed(data, "142", (at(9, 30), at(9, 45)))
    changes = diff(with_sessions(data, before), with_sessions(data, after))
    assert [change.kind for change in changes] == [ChangeKind.TIME]


def test_reminders_come_in_the_order_they_fire(data: ConferenceData) -> None:
    """A reminder at 1:30 PDT is planned before one at 1:10 PST, which reads earlier."""
    first = retimed(data, "142", (at(8, 40), at(9, 0)))  # 1:40 PDT, reminded 1:30 PDT
    second = retimed(data, "153", (at(9, 20), at(9, 40)))  # 1:20 PST, reminded 1:10 PST
    settings_ = ReminderSettings(
        lightning=False, open_space=False, keynote=False, session_lead=10
    )
    reminders = plan(
        with_sessions(data, first, second),
        [second.id, first.id],
        settings_,
        [],
        at(7, 0),
        zone=ZONE,
        use_24h=False,
    )
    assert [instant(r.at) for r in reminders] == [
        datetime(2026, 11, 1, 8, 30, tzinfo=UTC),
        datetime(2026, 11, 1, 9, 10, tzinfo=UTC),
    ]


@pytest.mark.parametrize("zone", [UTC, ZONE], ids=["utc", "conference"])
def test_a_session_across_the_change_is_happening_in_the_first_hour(zone: Any) -> None:
    """At 1:50 PDT the 1:40 PDT-1:10 PST talk is on, then ended at 1:10 PST, in any zone."""
    start, end = ACROSS
    assert time_status(start, end, at(8, 50).astimezone(zone), ZONE) == HAPPENING_NOW
    assert time_status(start, end, at(9, 10).astimezone(zone), ZONE) == ENDED


@pytest.mark.parametrize("zone", [UTC, ZONE], ids=["utc", "conference"])
def test_the_countdown_to_a_start_in_the_repeated_hour_counts_elapsed_time(
    zone: Any,
) -> None:
    """At 1:30 PDT a talk at 1:40 PST starts in 1 h 10 min, not 10 min, in any zone."""
    status = time_status(at(9, 40), at(10, 0), at(8, 30).astimezone(zone), ZONE)
    assert status is not None
    assert status.label == "Starts in 1 h 10 min"


def test_one_room_at_the_same_wall_times_twice_still_overlaps(
    data: ConferenceData,
) -> None:
    """In one room, 1:30 PDT-1:45 PST and 1:30-1:45 PST overlap: they are not one visit."""
    first = retimed(data, "142", (at(8, 30), at(9, 45)))  # 1:30 PDT-1:45 PST
    second = retimed(data, "10", (at(9, 30), at(9, 45)))  # 1:30-1:45 PST
    assert first.location == second.location  # what makes them look like one visit
    agenda = my_schedule(with_sessions(data, first, second), {first.id, second.id})
    assert agenda.overlaps == {first: (second,), second: (first,)}


def test_the_job_fairs_earlier_display_is_half_an_hour_across_the_change() -> None:
    """Processing the Job Fair at 1:10 PST shows it from 1:40 PDT, 30 minutes earlier."""
    data = feed_moved({178: (at(9, 10), at(10, 0))})  # 1:10-2:00 PST
    job_fair = data.sessions["178"]
    assert instant(job_fair.display_start) == datetime(2026, 11, 1, 8, 40, tzinfo=UTC)
    assert job_fair.display_start.tzinfo is ZONE  # shown in the conference's zone
    assert job_fair.display_start.utcoffset() == at(8, 40).utcoffset()  # PDT


def test_now_shows_a_session_across_the_change_as_happening() -> None:
    """At 1:50 PDT the 1:40 PDT-1:10 PST talk is on, and 1:05 PST's slot is next."""
    data = night_feed(ACROSS, AFTER_THE_CHANGE)
    now = now_next(data, at(8, 50))  # in the conference zone, where wall clocks mislead
    assert [s.id for s in now.happening] == ["142"]
    assert now.up_next is not None
    assert [s.id for s in now.up_next.sessions] == ["153"]


def test_a_day_ends_with_its_latest_end_in_the_repeated_hour() -> None:
    """A night ending at 1:35 PST, after a 1:55 PDT end, is still on at 1:20 PST."""
    data = night_feed((at(8, 40), at(8, 55)), AFTER_THE_CHANGE)  # 1:55 PDT, 1:35 PST
    assert now_next(data, at(9, 20)).phase is Phase.DAY
    assert now_next(data, at(9, 35)).phase is Phase.AFTER


def test_a_rooms_sessions_come_in_the_order_they_happen() -> None:
    """In one room, a 1:40 PDT talk is listed before a 1:05 PST one, and on now after it.

    The room's list runs by start; "Now in this room" puts the latest start first.
    """
    data = feed_moved({142: (at(8, 40), at(9, 30)), 10: AFTER_THE_CHANGE})
    [room] = [r for r in data.rooms.values() if r.name == "Grand Ballroom A"]
    assert [i for i in room.session_ids if i in {"142", "10"}] == ["142", "10"]
    assert [s.id for s in room_now(data, room.slug, at(9, 10))] == ["10", "142"]


def test_breaks_at_the_same_wall_time_twice_are_two_rows() -> None:
    """Breaks at 1:30 PDT and 1:30 PST, both "Break", collapse into two rows, not one."""
    data = feed_moved({154: (at(8, 30), at(8, 45)), 166: (at(9, 30), at(9, 45))})
    breaks = sorted(
        (s for s in data.sessions.values() if s.kind == "break" and s.day == NIGHT),
        key=lambda s: instant(s.start),
    )
    assert [(instant(s.start), instant(s.end)) for s in breaks] == [
        (instant(at(8, 30)), instant(at(8, 45))),
        (instant(at(9, 30)), instant(at(9, 45))),
    ]


def test_a_posters_row_spans_its_slots_in_the_order_they_happen() -> None:
    """Posters at 1:40-1:55 PDT and 1:05-1:35 PST make one row from 1:40 PDT to 1:35 PST."""
    data = feed_moved({62: (at(8, 40), at(8, 55)), 11: AFTER_THE_CHANGE})
    [row] = [
        s
        for s in data.sessions.values()
        if s.kind == "poster" and s.in_timeline and s.day == NIGHT
    ]
    assert (instant(row.start), instant(row.end)) == (
        instant(at(8, 40)),
        instant(at(9, 35)),
    )


def test_the_change_log_lists_changes_in_the_order_they_happen(
    data: ConferenceData,
) -> None:
    """A talk moved to 1:40 PDT is listed before one moved to 1:05 PST."""
    first = retimed(data, "142", ACROSS)
    second = retimed(data, "153", AFTER_THE_CHANGE)
    old = with_sessions(data, data.sessions["142"], data.sessions["153"])
    changes = diff(old, with_sessions(data, first, second))
    assert [(c.id, c.kind) for c in changes] == [
        ("142", ChangeKind.TIME),
        ("153", ChangeKind.TIME),
    ]
