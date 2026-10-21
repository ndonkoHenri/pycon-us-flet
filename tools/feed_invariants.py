"""The invariants of a processed feed, shared by the tests and the live-feed check (D-77).

Each invariant takes a ``ProcessedFeed`` and returns its problems, one line each; an empty
list means it holds. ``tests/test_feed_invariants.py`` asserts that every list is empty for
the recorded feeds, and ``tools/check_feed.py`` prints them for the live feed, so both run
the same code (testing-and-quality.md §3.3). They return problems instead of asserting so
the weekly check can report every broken invariant, not only the first.

The stable-ids invariant compares two outlines of the model: ``tools/feed_outline.py``'s
``outline()``, the reviewed snapshot's view of it. The sponsor and job-listing invariants
live in ``tools/sponsor_invariants.py``; ``INVARIANTS`` lists them with the others.
"""

import json
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from pycon_us.config import YearData
from pycon_us.core.feed import process
from pycon_us.core.models import ConferenceData, Session
from pycon_us.core.names import plain_text
from pycon_us.core.rules import COLLAPSED_KINDS
from pycon_us.core.slugs import room_sort_key, slugify_room
from pycon_us.core.timefmt import instant, local_date
from tools.feed_outline import clock, outline
from tools.sponsor_invariants import (
    job_listings_name_a_sponsor,
    sponsor_levels_are_sorted_and_not_empty,
    sponsor_slugs_are_unique,
)

ID_FORMS = re.compile(
    r"\d+"  # a slot's conf_key, or an open space's conf_key + 9000
    r"|poster-detail-\d+"
    r"|(break|poster)-.*-\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d"  # a collapsed row
)
"""Ionic's four id forms (D-42, DATA-26)."""

DROP_RULES = frozenset(
    {
        "available-open-space",
        "open-space-duplicate",
        "placeholder",
        "posters-plenary",
        "blank",
        "collapsed",
        "unscheduled-open-space",
    }
)
"""The named rules that may drop a record (D-123)."""


@dataclass(frozen=True, eq=False)
class ProcessedFeed:
    """A feed's bytes, their JSON and their model, with the year they belong to.

    Attributes:
        raw: The feed's bytes.
        document: The same bytes as JSON, to compare the model with.
        data: The model ``feed.process`` built from them.
        year: The year's data: its zone, dates and display-time overrides.
    """

    raw: bytes
    document: dict[str, Any]
    data: ConferenceData
    year: YearData

    @property
    def zone(self) -> ZoneInfo:
        """The conference's time zone."""
        return self.year.conference.zone


def processed_feed(raw: bytes, year: YearData) -> ProcessedFeed:
    """Process ``raw`` with the year's settings.

    Raises:
        FeedError: The feed does not parse.
    """
    data = process(raw, year.feed_settings)
    return ProcessedFeed(raw, json.loads(raw), data, year)


def no_session_is_lost(feed: ProcessedFeed) -> list[str]:
    """Every slot is its own session or dropped by one named rule; nothing else vanishes.

    A collapsed slot lies within a row of its kind on its day; an open space is a session
    when its raw times and room are set, and dropped otherwise; every raw poster, top-level
    or nested in a slot (D-121), has its detail session.
    """
    doc, data = feed.document, feed.data
    problems = [f"skipped {reason}" for reason in data.skipped]
    if unknown := sorted(set(data.dropped) - DROP_RULES):
        problems.append(f"unknown drop rules: {', '.join(unknown)}")
    dropped = [i for ids in data.dropped.values() for i in ids]
    if twice := sorted(i for i, count in Counter(dropped).items() if count > 1):
        problems.append(f"dropped by two rules: {', '.join(twice)}")
    slots = Counter(str(slot["conf_key"]) for slot in doc["schedule"])
    accounted = Counter(
        s.id for s in data.sessions.values() if s.id in slots and s.kind != "open-space"
    )
    accounted.update(i for i in dropped if i in slots)
    if lost := sorted((slots - accounted).elements()):
        problems.append(f"slots neither a session nor dropped: {', '.join(lost)}")
    if extra := sorted((accounted - slots).elements()):
        problems.append(f"slots counted twice: {', '.join(extra)}")

    rows = collapsed_rows(data)
    for slot in doc["schedule"]:
        if str(slot["conf_key"]) in data.dropped.get("collapsed", ()):
            start = datetime.fromisoformat(slot["start"])
            end = datetime.fromisoformat(slot["end"])
            if not any(
                row.kind == slot["kind"]
                and row.day == local_date(start, feed.zone)
                and row.start <= start
                and end <= row.end
                for row in rows
            ):
                problems.append(f"collapsed slot {slot['conf_key']} is in no row")

    unscheduled = data.dropped.get("unscheduled-open-space", ())
    for space in doc.get("open-spaces", []):
        space_id = str(space["conf_key"] + 9000)
        room = (space.get("room_display") or "").strip() or (space.get("room") or "")
        if space.get("start") and space.get("end") and room.strip():
            if space_id not in data.sessions or space_id in unscheduled:
                problems.append(f"scheduled open space {space_id} is not a session")
        elif space_id not in unscheduled or space_id in data.sessions:
            problems.append(f"unscheduled open space {space_id} is not dropped")

    raw_posters = [str(p["conf_key"]) for p in doc.get("posters", [])]
    raw_posters += [
        str(p["conf_key"]) for s in doc["schedule"] for p in s.get("sessions") or []
    ]
    if [poster.id for poster in data.posters] != raw_posters:
        problems.append("the posters differ from the feed's, or are in another order")
    for poster_id in raw_posters:
        detail = data.sessions.get(f"poster-detail-{poster_id}")
        if detail is None or detail.in_timeline:
            problems.append(
                f"poster {poster_id} has no detail session off the timeline"
            )
    return problems


def ids_are_unique_stable_strings_in_ionics_forms(feed: ProcessedFeed) -> list[str]:
    """D-42, DATA-26: the same bytes give the same ids, in Ionic's four forms."""
    problems = []
    for session_id, session in feed.data.sessions.items():
        if type(session.id) is not str or session_id != session.id:
            problems.append(f"session {session_id!r} has the id {session.id!r}")
        elif not ID_FORMS.fullmatch(session.id):
            problems.append(f"id {session.id!r} is in none of Ionic's forms")
    again = process(feed.raw, feed.year.feed_settings)
    if outline(again, feed.zone) != outline(feed.data, feed.zone):
        problems.append("processing the same bytes again gives another outline")
    return problems


def every_session_is_on_one_conference_day(feed: ProcessedFeed) -> list[str]:
    """DATA-12, DATA-13: in the timeline once, under its conference-local date."""
    conference, data = feed.year.conference, feed.data
    problems = []
    grouped = Counter(
        (day.date, i)
        for day in data.days
        for group in day.groups
        for i in group.session_ids
    )
    timeline = Counter((s.day, s.id) for s in data.sessions.values() if s.in_timeline)
    if not timeline:
        problems.append("no session is in the timeline")
    if missing := sorted(timeline - grouped):
        problems.append(f"in no time group: {', '.join(i for _, i in missing)}")
    if extra := sorted(grouped - timeline):
        problems.append(f"grouped twice or wrongly: {', '.join(i for _, i in extra)}")
    for session in data.sessions.values():
        if session.day != local_date(session.start, conference.zone):
            problems.append(f"{session.id} is listed on a day it does not start on")
        if not conference.first_day <= session.day <= conference.last_day:
            problems.append(f"{session.id} is on {session.day}, outside the conference")
    dates = [day.date for day in data.days]
    if dates != sorted(set(dates)):
        problems.append("the days are not sorted, or repeat a date")
    return problems


def times_are_aware_in_the_years_zone_and_ordered(feed: ProcessedFeed) -> list[str]:
    """D-43: every time in the conference zone; nothing ends before it starts."""
    problems = []
    for session in feed.data.sessions.values():
        moments = (session.start, session.display_start, session.end)
        if any(moment.tzinfo != feed.zone for moment in moments):
            problems.append(f"{session.id} has a time outside the conference zone")
        if session.end.astimezone(UTC) < session.start.astimezone(UTC):  # #513
            problems.append(f"{session.id} ends before it starts")
    return problems


def every_group_has_a_start_and_ordered_rows(feed: ProcessedFeed) -> list[str]:
    """DATA-13, D-31: groups sorted by their start; rows by location, then name.

    Starts compare as instants: one zone's starts compare by wall clock, which would
    read 1:30 PDT and 1:30 PST as one start on the night summer time ends (#535).
    """
    data = feed.data
    problems = []
    for day in data.days:
        starts = [instant(group.start) for group in day.groups]
        if starts != sorted(set(starts)):
            problems.append(f"{day.date}: the groups are not sorted, or repeat a start")
        for group in day.groups:
            rows = [data.sessions[i] for i in group.session_ids]
            where = f"{day.date} {clock(group.start, feed.zone)}"
            if any(instant(row.start) != instant(group.start) for row in rows):
                problems.append(f"{where}: a row starts at another time")
            keys = [(row.location, row.name) for row in rows]
            if keys != sorted(keys):
                problems.append(f"{where}: rows not ordered by location, then name")
    return problems


def no_dropped_category_survives(feed: ProcessedFeed) -> list[str]:
    """DATA-04, DATA-06: no record of a dropped category is a session of its own.

    No free or duplicate open space, placeholder, Posters plenary or blank is a session;
    posters and breaks remain, as one Posters row a poster day and break rows.
    """
    doc, data = feed.document, feed.data
    problems = []
    for slot in doc["schedule"]:
        kind, name = slot["kind"], slot["name"]
        placeholder = (
            kind not in COLLAPSED_KINDS
            and name.strip().lower() == kind.lower()
            and not (slot.get("description") or "").strip()
            and not slot.get("contact")
            and not slot.get("authors")
        )
        posters_plenary = kind == "plenary" and re.fullmatch(
            r"posters?(\s*\([^)]*\))?", plain_text(name), re.IGNORECASE
        )
        if (
            kind.startswith("available-open-space")
            or kind in ("open-space", "blank", *COLLAPSED_KINDS)
            or name == "Slot"
            or placeholder
            or posters_plenary
        ) and str(slot["conf_key"]) in data.sessions:
            problems.append(f"slot {slot['conf_key']} ({kind}) is a session")
    rows = collapsed_rows(data)
    problems += _one_row_a_day(
        feed, rows, "Posters", lambda slot: slot["kind"] == "poster"
    )
    has_breaks = any(slot["kind"] == "break" for slot in doc["schedule"])
    if has_breaks and not any(row.kind == "break" for row in rows):
        problems.append("the feed has breaks, but no break row")
    return problems


def one_lunch_row_per_day_with_lunch(feed: ProcessedFeed) -> list[str]:
    """DATA-06, SCHED-19: staggered lunch slots fold into one row a day."""
    return _one_row_a_day(
        feed,
        collapsed_rows(feed.data),
        "Lunch",
        lambda slot: (
            slot["kind"] == "break"
            and plain_text(slot["name"]).lower().startswith("lunch")
        ),
    )


def only_overridden_sessions_show_another_start(feed: ProcessedFeed) -> list[str]:
    """DATA-11: the Job Fair is shown at its display time and grouped at its start."""
    overrides = feed.year.content.display_time_overrides
    problems = []
    for session in feed.data.sessions.values():
        shift = 0
        if session.kind not in ("open-space", "break", "poster"):  # slots' titles only
            matched = [o for o in overrides if o.pattern.fullmatch(session.name)]
            shift = matched[0].minutes if matched else 0
        if session.display_start != session.start + timedelta(minutes=shift):
            problems.append(f"{session.id} is shown at another time than expected")
    return problems


def speakers_and_sessions_link_both_ways(feed: ProcessedFeed) -> list[str]:
    """DATA-15: every linked speaker exists and has a session, and is named in it."""
    data = feed.data
    problems = []
    linked = {i for s in data.sessions.values() for i in s.speaker_ids}
    if missing := sorted(linked - set(data.speakers)):
        problems.append(f"linked, not in the directory: {', '.join(missing)}")
    if idle := sorted(set(data.speakers) - linked):
        problems.append(f"in the directory without a session: {', '.join(idle)}")
    for session in data.sessions.values():
        for speaker_id in session.speaker_ids:
            speaker = data.speakers.get(speaker_id)
            if speaker and speaker.name not in session.speaker_names:
                problems.append(f"{session.id} does not name speaker {speaker_id}")
    for speaker in data.speakers.values():
        if speaker.name.startswith("Hosted by"):
            problems.append(f"pseudo-speaker {speaker.id} is in the directory")
    return problems


def rooms_and_sessions_agree(feed: ProcessedFeed) -> list[str]:
    """DATA-16, ROOM-06: one room per slug, naturally sorted, listing who names it."""
    data = feed.data
    problems = []
    names = [room.name for room in data.rooms.values()]
    if names != sorted(names, key=room_sort_key):
        problems.append("the rooms are not in natural order")
    for slug, room in data.rooms.items():
        if slug != slugify_room(room.name):
            problems.append(f"room {room.name!r} is filed under {slug!r}")
        if not room.session_ids:
            problems.append(f"room {slug} has no session")
        if len(room.session_ids) != len(set(room.session_ids)):
            problems.append(f"room {slug} lists a session twice")
        order = [
            (instant(data.sessions[i].start), data.sessions[i].name)
            for i in room.session_ids
        ]
        if order != sorted(order):  # by start, then name (D-125)
            problems.append(f"room {slug}'s sessions are not by start, then name")
        for session_id in room.session_ids:
            rooms = data.sessions[session_id].rooms
            if slug not in {slugify_room(r) for r in rooms}:
                problems.append(f"room {slug} lists {session_id}, which is elsewhere")
    for session in data.sessions.values():
        for name in session.rooms:
            room = data.rooms.get(slugify_room(name))
            if room is None or session.id not in room.session_ids:
                problems.append(f"{session.id}'s room {name!r} does not list it")
    return problems


INVARIANTS: tuple[Callable[[ProcessedFeed], list[str]], ...] = (
    no_session_is_lost,
    ids_are_unique_stable_strings_in_ionics_forms,
    every_session_is_on_one_conference_day,
    times_are_aware_in_the_years_zone_and_ordered,
    every_group_has_a_start_and_ordered_rows,
    no_dropped_category_survives,
    one_lunch_row_per_day_with_lunch,
    only_overridden_sessions_show_another_start,
    speakers_and_sessions_link_both_ways,
    rooms_and_sessions_agree,
    sponsor_slugs_are_unique,
    sponsor_levels_are_sorted_and_not_empty,
    job_listings_name_a_sponsor,
)
"""Every invariant, in the order of testing-and-quality.md §3.3."""


def collapsed_rows(data: ConferenceData) -> list[Session]:
    """The collapsed Break, Lunch and Posters rows of the timeline."""
    return [
        s for s in data.sessions.values() if s.kind in COLLAPSED_KINDS and s.in_timeline
    ]


def _one_row_a_day(
    feed: ProcessedFeed,
    rows: list[Session],
    name: str,
    is_slot: Callable[[dict[str, Any]], bool],
) -> list[str]:
    """Check that each day with a matching slot has exactly one row called ``name``."""
    slot_days = {
        local_date(datetime.fromisoformat(slot["start"]), feed.zone)
        for slot in feed.document["schedule"]
        if is_slot(slot)
    }
    row_days = Counter(row.day for row in rows if row.name == name)
    problems = [
        f"{day} has {count} {name} rows" for day, count in row_days.items() if count > 1
    ]
    if missing := sorted(slot_days - set(row_days)):
        problems.append(f"{name} rows missing on {_dates(missing)}")
    if extra := sorted(set(row_days) - slot_days):
        problems.append(f"{name} rows without a {name} slot on {_dates(extra)}")
    return problems


def _dates(days: list[date]) -> str:
    return ", ".join(day.isoformat() for day in days)
