"""Tests for the reminder plan (``services/reminders.py``; #427, D-59, D-222, NEW-05).

Every case runs at a fixed ``now`` over a recorded feed: the plan is pure, so what it
returns is all there is to check until E3's ``apply()`` schedules it.
"""

from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from pycon_us.config import load_year
from pycon_us.core.feed import process
from pycon_us.core.models import ConferenceData
from pycon_us.reminder_settings import ReminderSettings, SessionLead
from pycon_us.services.reminders import (
    BANNER_LEAD,
    MAX_PENDING,
    SYNTHETIC_BASE,
    DueSession,
    Reminder,
    due_session,
    plan,
    reminder_id,
)
from pycon_us.year_moments import EventReminder, keynote_moments
from tests.feeds import YEARS, changed, processed, remove, retime, settings

ZONE = ZoneInfo("America/Los_Angeles")
"""2026's conference zone."""

BEFORE = datetime(2026, 5, 1, 9, 0, tzinfo=ZONE)
"""A fixed now before PyCon US 2026 starts: every session is in the future."""

TALK = "142"
"""A 2026 talk: Saturday 16 May at 10:30 AM in Grand Ballroom A."""

KEYNOTE = "153"
"""2026's first keynote: Friday 15 May at 9:45 AM, whose moment is 8050."""

ALL_OFF = ReminderSettings(lightning=False, open_space=False, keynote=False)
"""No conference moment; session reminders as each test sets them."""


@pytest.fixture(scope="module")
def data() -> ConferenceData:
    """2026's recorded feed, processed."""
    return processed(2026)


def moments(year: int, data: ConferenceData) -> tuple[EventReminder, ...]:
    """Every conference moment of ``year``: the hand-written sign-ups and the keynotes."""
    year_data = load_year(year)
    derived = keynote_moments(
        data, year_data.content.keynotes, year_data.conference.zone, use_24h=False
    )
    return year_data.content.event_reminders + derived


def planned(
    data: ConferenceData,
    favorites: list[str],
    reminder_settings: ReminderSettings,
    now: datetime = BEFORE,
    *,
    use_24h: bool = False,
) -> list[Reminder]:
    """The 2026 plan for ``favorites`` with every 2026 moment offered."""
    return plan(
        data,
        favorites,
        reminder_settings,
        moments(2026, data),
        now,
        zone=ZONE,
        use_24h=use_24h,
    )


# ------------------------------------------------------------------ session reminders


@pytest.mark.parametrize("lead", [5, 10, 15])
def test_a_saved_session_is_reminded_its_lead_before_it_starts(
    data: ConferenceData, lead: SessionLead
) -> None:
    """One reminder per saved session, ``lead`` minutes before, opening it in My schedule."""
    reminders = planned(data, [TALK], replace(ALL_OFF, session_lead=lead))
    start = data.sessions[TALK].display_start
    assert reminders == [
        Reminder(
            id=142,
            at=start - timedelta(minutes=lead),
            title=data.sessions[TALK].name,
            body="Starts at 10:30 AM · Grand Ballroom A",
            route="/my-schedule/session/142",
        )
    ]


def test_a_reminder_says_the_start_in_the_users_clock_format(
    data: ConferenceData,
) -> None:
    """The text gives the conference-local start in 24-hour form when the phone uses it."""
    [reminder] = planned(data, [TALK], replace(ALL_OFF, session_lead=10), use_24h=True)
    assert reminder.body == "Starts at 10:30 · Grand Ballroom A"


def test_session_reminders_off_gives_none(data: ConferenceData) -> None:
    """A lead of 0 is off: saved sessions get no reminder."""
    assert planned(data, [TALK, "51"], ALL_OFF) == []


def test_a_reminder_already_due_is_skipped(data: ConferenceData) -> None:
    """A reminder whose time is now or past is not planned; a later one still is."""
    start = data.sessions[TALK].display_start
    lead = replace(ALL_OFF, session_lead=10)
    assert planned(data, [TALK], lead, now=start - timedelta(minutes=10)) == []
    assert planned(data, [TALK], lead, now=start - timedelta(minutes=11))


def test_a_saved_id_not_in_the_feed_is_ignored(data: ConferenceData) -> None:
    """A favourite the feed does not have (removed, or from another year) gets nothing."""
    assert planned(data, ["no-such-session"], replace(ALL_OFF, session_lead=5)) == []


def test_a_moved_session_keeps_its_id_with_the_new_time() -> None:
    """A session the feed moves keeps its reminder id; the time is the new one."""
    edit = retime(142, "2026-05-17T13:00:00-07:00", "2026-05-17T13:30:00-07:00")
    moved = process(changed(2026, edit), settings(2026))
    [reminder] = planned(moved, [TALK], replace(ALL_OFF, session_lead=10))
    assert reminder.id == 142
    assert reminder.at == datetime(2026, 5, 17, 12, 50, tzinfo=ZONE)
    assert reminder.body.startswith("Starts at 1:00 PM")


def test_a_removed_session_drops_out() -> None:
    """A saved session the feed no longer has has no reminder."""
    gone = process(changed(2026, remove(142)), settings(2026))
    assert planned(gone, [TALK], replace(ALL_OFF, session_lead=10)) == []


# ----------------------------------------------------------------- conference moments


@pytest.mark.parametrize("category", ["lightning", "open_space", "keynote"])
def test_each_category_of_moment_turns_on_and_off(
    data: ConferenceData, category: str
) -> None:
    """A category's moments are planned when it is on, and none of them when it is off."""
    ids = {m.id for m in moments(2026, data) if m.category == category}
    assert ids
    on = {r.id for r in planned(data, [], replace(ALL_OFF, **{category: True}))}
    assert on == ids
    off = replace(ReminderSettings(), **{category: False})
    assert not ids & {r.id for r in planned(data, [], off)}


def test_a_moment_keeps_its_own_copy_and_page(data: ConferenceData) -> None:
    """A moment becomes a reminder with its id, time, text and route unchanged."""
    moment = moments(2026, data)[0]
    on = replace(ALL_OFF, **{moment.category: True})
    reminder = next(r for r in planned(data, [], on) if r.id == moment.id)
    assert reminder == Reminder(
        moment.id, moment.at, moment.title, moment.body, moment.route
    )


def test_past_moments_are_skipped(data: ConferenceData) -> None:
    """After the conference, no moment is planned."""
    after = datetime(2026, 6, 1, tzinfo=ZONE)
    assert planned(data, [], ReminderSettings(), now=after) == []


@pytest.mark.parametrize("lead", [5, 10, 15])
def test_a_saved_keynote_gets_one_reminder_the_earlier(
    data: ConferenceData, lead: SessionLead
) -> None:
    """A saved keynote with its moment on is reminded once: by its moment, 15 min before."""
    on = ReminderSettings(lightning=False, open_space=False, session_lead=lead)
    keynotes = {m.id for m in moments(2026, data) if m.category == "keynote"}
    assert 8050 in keynotes
    assert {r.id for r in planned(data, [KEYNOTE], on)} == keynotes


def test_a_saved_keynote_is_reminded_by_itself_with_keynote_moments_off(
    data: ConferenceData,
) -> None:
    """With keynote moments off, a saved keynote gets its session reminder."""
    reminders = planned(data, [KEYNOTE], replace(ALL_OFF, session_lead=5))
    assert [r.id for r in reminders] == [153]


def test_a_saved_keynote_whose_moment_passed_keeps_its_session_reminder(
    data: ConferenceData,
) -> None:
    """Between its moment and its own reminder, a saved keynote still gets the latter."""
    start = data.sessions[KEYNOTE].start
    on = ReminderSettings(lightning=False, open_space=False, session_lead=5)
    reminders = planned(data, [KEYNOTE], on, now=start - timedelta(minutes=10))
    assert reminders[0].id == 153


# --------------------------------------------------------------------- the cap and ids


def test_seventy_candidates_give_the_soonest_sixty(data: ConferenceData) -> None:
    """The plan keeps the 60 soonest reminders, sorted, and drops the rest (D-222)."""
    saved = [s.id for s in data.sessions.values() if s.in_timeline][:70]
    assert len(saved) == 70
    lead = replace(ALL_OFF, session_lead=10)
    reminders = planned(data, saved, lead)
    every = sorted(
        (data.sessions[t].display_start - timedelta(minutes=10), reminder_id(t))
        for t in saved
    )
    assert len(reminders) == MAX_PENDING
    assert [(r.at, r.id) for r in reminders] == every[:MAX_PENDING]


def test_the_plan_is_the_same_whatever_the_favourites_order(
    data: ConferenceData,
) -> None:
    """Same inputs, same plan: favourites come from a set, whose order varies."""
    saved = [TALK, "51", KEYNOTE]
    on = replace(ReminderSettings(), session_lead=15)
    assert planned(data, saved, on) == planned(data, saved[::-1], on)


def test_ids_are_deterministic() -> None:
    """A numeric id is itself; any other is 1,000,000 + crc32 % 1,000,000, every time."""
    assert reminder_id("142") == 142
    assert reminder_id("9177") == 9177
    synthetic = reminder_id("poster-detail-12")
    assert synthetic == reminder_id("poster-detail-12")
    assert SYNTHETIC_BASE <= synthetic < 2 * SYNTHETIC_BASE


@pytest.mark.parametrize("year", YEARS)
def test_no_session_id_collides_with_a_moment_or_the_test_reminder(year: int) -> None:
    """Every session of a year has its own id, outside 8000-8099 and 8999 (D-59)."""
    ids = [reminder_id(session_id) for session_id in processed(year).sessions]
    assert len(set(ids)) == len(ids)
    assert not [i for i in ids if 8000 <= i <= 8099 or i == 8999]


# ------------------------------------------------------------------ the in-app Banner

TALK_START = datetime(2026, 5, 16, 10, 30, tzinfo=ZONE)
"""When ``TALK`` starts, as the app shows it."""

SAME_TIME = "51"
"""Another 2026 talk at ``TALK``'s time, in Grand Ballroom B."""


def test_a_saved_session_is_due_from_ten_minutes_before_its_start(
    data: ConferenceData,
) -> None:
    """At the lead, the Banner names the session, its minutes, room and route."""
    due = due_session(data, [TALK], TALK_START - BANNER_LEAD)
    assert due == DueSession(
        id=TALK,
        name=data.sessions[TALK].name,
        minutes=10,
        location="Grand Ballroom A",
        route=f"/my-schedule/session/{TALK}",
    )
    assert due is not None
    assert due.text == (
        f"{data.sessions[TALK].name} starts in 10 min · Grand Ballroom A"
    )


@pytest.mark.parametrize(
    ("before", "minutes"),
    [
        (timedelta(minutes=9), 9),
        (timedelta(minutes=8, seconds=59), 9),
        (timedelta(minutes=1), 1),
        (timedelta(seconds=1), 1),
    ],
)
def test_the_minutes_count_down_rounded_up(
    data: ConferenceData, before: timedelta, minutes: int
) -> None:
    """The minutes are whole, rounded up, so the Banner never says 0 min."""
    due = due_session(data, [TALK], TALK_START - before)
    assert due is not None
    assert due.minutes == minutes


@pytest.mark.parametrize(
    "before",
    [BANNER_LEAD + timedelta(seconds=1), timedelta(0), -timedelta(minutes=5)],
)
def test_nothing_is_due_before_the_lead_nor_once_the_session_started(
    data: ConferenceData, before: timedelta
) -> None:
    """Earlier than the lead, at the start and after it, there is no Banner."""
    assert due_session(data, [TALK], TALK_START - before) is None


def test_an_unsaved_session_is_never_due(data: ConferenceData) -> None:
    """A session that is not in My schedule gets no Banner, whatever the time."""
    assert due_session(data, [], TALK_START - timedelta(minutes=5)) is None


def test_a_session_no_longer_in_the_feed_is_never_due() -> None:
    """A saved session the feed removed gets no Banner."""
    gone = process(changed(2026, remove(142)), settings(2026))
    assert due_session(gone, [TALK], TALK_START - timedelta(minutes=5)) is None


def test_a_dismissed_session_is_not_due_and_the_next_one_shows(
    data: ConferenceData,
) -> None:
    """A dismissed session stays away, and another saved one at that time shows."""
    now = TALK_START - timedelta(minutes=5)
    saved = [TALK, SAME_TIME]
    first = due_session(data, saved, now)
    assert first is not None
    assert first.id == TALK  # equal starts: the lower id, "142" < "51" as text
    second = due_session(data, saved, now, dismissed={TALK})
    assert second is not None
    assert second.id == SAME_TIME
    assert due_session(data, saved, now, dismissed={TALK, SAME_TIME}) is None


def test_the_soonest_saved_session_wins(data: ConferenceData) -> None:
    """Of two due sessions, the one that starts first is announced."""
    edit = retime(142, "2026-05-16T10:25:00-07:00", "2026-05-16T11:00:00-07:00")
    earlier = process(changed(2026, edit), settings(2026))
    due = due_session(earlier, [SAME_TIME, TALK], TALK_START - timedelta(minutes=8))
    assert due is not None
    assert (due.id, due.minutes) == (TALK, 3)


def test_a_session_with_no_place_says_only_its_start(data: ConferenceData) -> None:
    """Without a shown location the words end at the minutes."""
    due = DueSession(id="1", name="Lunch", minutes=4, location="", route="/x")
    assert due.text == "Lunch starts in 4 min"
