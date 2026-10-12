"""Invariants of the processed feed, and the reviewed snapshot of it (D-77; DATA-17, SCHED-19).

Each invariant runs on every recorded feed (2025 and 2026) under both machine zones. The
snapshot is a readable outline of *our* processed model, one line per session, compared
with ``tests/fixtures/snapshots/outline-<year>.json``. After a deliberate change, run
``uv run pytest tests/test_feed_invariants.py --snapshot-update`` and explain the diff in
the PR. Ionic's own processing output is a separate, one-off reference (#66).
"""

import re
from collections import Counter
from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from pycon_us.config import load_year
from pycon_us.core.models import ConferenceData, Session
from pycon_us.core.names import plain_text
from pycon_us.core.rules import COLLAPSED_KINDS
from pycon_us.core.slugs import room_sort_key, slugify_room
from pycon_us.core.timefmt import local_date
from tests.feeds import YEARS, document, processed

pytestmark = [
    pytest.mark.usefixtures("machine_tz"),
    pytest.mark.parametrize("year", YEARS),
]

ID_FORMS = re.compile(
    r"\d+"  # a slot's conf_key, or an open space's conf_key + 9000
    r"|poster-detail-\d+"
    r"|(break|poster)-.*-\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d"  # a collapsed row
)
DROP_RULES = {
    "available-open-space",
    "open-space-duplicate",
    "placeholder",
    "posters-plenary",
    "blank",
    "collapsed",
    "unscheduled-open-space",
}


def collapsed_rows(data: ConferenceData) -> list[Session]:
    return [
        s for s in data.sessions.values() if s.kind in COLLAPSED_KINDS and s.in_timeline
    ]


def test_no_session_is_lost(year: int) -> None:
    """Every slot is its own session or dropped by one named rule; nothing else vanishes."""
    doc = document(year)
    data = processed(year)
    zone = load_year(year).conference.zone
    assert set(data.dropped) <= DROP_RULES and data.skipped == ()
    dropped = [i for ids in data.dropped.values() for i in ids]
    assert len(dropped) == len(set(dropped)), "a record dropped by two rules"
    slots = [str(slot["conf_key"]) for slot in doc["schedule"]]
    own = [
        s.id
        for s in data.sessions.values()
        if s.id in set(slots) and s.kind != "open-space"
    ]
    assert sorted(own + [i for i in dropped if i in set(slots)]) == sorted(slots)
    # A collapsed slot lies within a row of its kind on its day.
    rows = collapsed_rows(data)
    for slot in doc["schedule"]:
        if str(slot["conf_key"]) in data.dropped.get("collapsed", ()):
            start = datetime.fromisoformat(slot["start"])
            end = datetime.fromisoformat(slot["end"])
            assert any(
                row.kind == slot["kind"]
                and row.day == local_date(start, zone)
                and row.start <= start
                and end <= row.end
                for row in rows
            ), slot["conf_key"]
    # An open space is a session or unscheduled; a poster has its detail session.
    for space in doc.get("open-spaces", []):
        space_id = str(space["conf_key"] + 9000)
        assert (space_id in data.sessions) != (
            space_id in data.dropped.get("unscheduled-open-space", ())
        )
    for poster in data.posters:
        assert f"poster-detail-{poster.id}" in data.sessions


def test_ids_are_unique_stable_strings_in_ionics_forms(year: int) -> None:
    """D-42, DATA-26: the same bytes give the same ids, in Ionic's four forms."""
    data = processed(year)
    for session_id, session in data.sessions.items():
        assert type(session.id) is str and session_id == session.id
        assert ID_FORMS.fullmatch(session.id), session.id
    assert outline(processed(year), year) == outline(data, year)


def test_every_session_is_on_one_conference_day(year: int) -> None:
    """DATA-12, DATA-13: in the timeline once, under its conference-local date."""
    conference = load_year(year).conference
    data = processed(year)
    grouped = Counter(
        (day.date, i)
        for day in data.days
        for group in day.groups
        for i in group.session_ids
    )
    timeline = [s for s in data.sessions.values() if s.in_timeline]
    assert sorted(grouped) == sorted((s.day, s.id) for s in timeline)
    assert set(grouped.values()) == {1}
    for session in data.sessions.values():
        assert session.day == local_date(session.start, conference.zone)
        assert conference.first_day <= session.day <= conference.last_day
    dates = [day.date for day in data.days]
    assert dates == sorted(set(dates))


def test_times_are_aware_in_the_years_zone_and_ordered(year: int) -> None:
    """D-43: every time in the conference zone; nothing ends before it starts."""
    zone = load_year(year).conference.zone
    for session in processed(year).sessions.values():
        for moment in (session.start, session.display_start, session.end):
            assert moment.tzinfo == zone, session.id
        assert session.start <= session.end, session.id


def test_every_group_has_a_start_and_ordered_rows(year: int) -> None:
    """DATA-13, D-31: groups sorted by their start; rows by location, then name."""
    data = processed(year)
    for day in data.days:
        starts = [group.start for group in day.groups]
        assert starts == sorted(set(starts)), day.date
        for group in day.groups:
            rows = [data.sessions[i] for i in group.session_ids]
            assert all(row.start == group.start for row in rows)
            keys = [(row.location, row.name) for row in rows]
            assert keys == sorted(keys)


def test_no_dropped_category_survives(year: int) -> None:
    """DATA-04, DATA-06: no free or duplicate open space, placeholder or blank; posters
    and breaks remain, as collapsed rows and poster details only."""
    data = processed(year)
    for session in data.sessions.values():
        assert not session.kind.startswith("available-open-space")
        assert session.kind != "blank" and session.name != "Slot"
        if session.kind not in COLLAPSED_KINDS:  # a placeholder's shape (DATA-04)
            name = session.name.strip().lower()
            assert name != session.kind.lower() or session.description, session.id
        if session.kind in COLLAPSED_KINDS:
            assert session.id.startswith((f"{session.kind}-", "poster-detail-"))
        if session.kind == "plenary":
            assert plain_text(session.name).lower() not in ("poster", "posters")
    kinds = {row.kind for row in collapsed_rows(data)}
    assert kinds == {"poster", "break"}


def test_one_lunch_row_per_day_with_lunch(year: int) -> None:
    """DATA-06, SCHED-19: staggered lunch slots fold into one row a day."""
    data = processed(year)
    lunches = Counter(s.day for s in collapsed_rows(data) if s.name == "Lunch")
    assert set(lunches.values()) == {1}
    zone = load_year(year).conference.zone
    lunch_days = {
        local_date(datetime.fromisoformat(slot["start"]), zone)
        for slot in document(year)["schedule"]
        if slot["kind"] == "break"
        and plain_text(slot["name"]).lower().startswith("lunch")
    }
    assert set(lunches) == lunch_days


def test_only_overridden_sessions_show_another_start(year: int) -> None:
    """DATA-11: the Job Fair is shown at its display time and grouped at its start."""
    overrides = load_year(year).content.display_time_overrides
    for session in processed(year).sessions.values():
        matched = [o for o in overrides if o.pattern.fullmatch(session.name)]
        if session.display_start != session.start:
            assert matched and session.kind not in ("open-space", "break", "poster")
            minutes = (session.display_start - session.start).total_seconds() / 60
            assert minutes == matched[0].minutes


def test_speakers_and_sessions_link_both_ways(year: int) -> None:
    """DATA-15: every linked speaker exists and has a session, and is named in it."""
    data = processed(year)
    linked = {i for s in data.sessions.values() for i in s.speaker_ids}
    assert linked == set(data.speakers)
    for session in data.sessions.values():
        for speaker_id in session.speaker_ids:
            assert data.speakers[speaker_id].name in session.speaker_names
    assert not any(s.name.startswith("Hosted by") for s in data.speakers.values())


def test_rooms_and_sessions_agree(year: int) -> None:
    """DATA-16, ROOM-06: one room per slug, naturally sorted, listing who names it."""
    data = processed(year)
    names = [room.name for room in data.rooms.values()]
    assert names == sorted(names, key=room_sort_key)
    for slug, room in data.rooms.items():
        assert slug == slugify_room(room.name) and room.session_ids
        assert len(room.session_ids) == len(set(room.session_ids))
        for session_id in room.session_ids:
            rooms = data.sessions[session_id].rooms
            assert slug in {slugify_room(r) for r in rooms}
    for session in data.sessions.values():
        for name in session.rooms:
            assert session.id in data.rooms[slugify_room(name)].session_ids


def test_processed_model_matches_the_reviewed_snapshot(
    year: int, snapshot: Callable[[str, object], None]
) -> None:
    """D-77: a deliberate change updates the snapshot and explains its diff."""
    snapshot(f"outline-{year}", outline(processed(year), year))


def outline(data: ConferenceData, year: int) -> dict[str, object]:
    """A compact, reviewable view of the model: one line per session.

    A line reads ``id | name | track | shown location | start-end`` in conference time,
    then, when they apply: ``shown HH:MM``, ``pre-registration``, ``español``,
    ``speakers <ids>`` and ``text <names not in the directory>``.
    """
    zone = load_year(year).conference.zone

    def line(session: Session) -> str:
        parts = [
            session.id,
            session.name,
            session.track,
            session.display_location or "-",
            f"{clock(session.start, zone)}-{clock(session.end, zone)}",
        ]
        if session.display_start != session.start:
            parts.append(f"shown {clock(session.display_start, zone)}")
        if session.pre_registered:
            parts.append("pre-registration")
        if session.spanish:
            parts.append("español")
        if session.speaker_ids:
            parts.append("speakers " + " ".join(session.speaker_ids))
        linked = {data.speakers[i].name for i in session.speaker_ids}
        if text := [name for name in session.speaker_names if name not in linked]:
            parts.append("text " + "; ".join(text))
        return " | ".join(parts)

    return {
        "days": {
            day.date.isoformat(): {
                clock(group.start, zone): [
                    line(data.sessions[i]) for i in group.session_ids
                ]
                for group in day.groups
            }
            for day in data.days
        },
        "outside the timeline": [
            line(s) for s in data.sessions.values() if not s.in_timeline
        ],
        "rooms": [
            f"{room.slug}: {room.name} ({len(room.session_ids)})"
            for room in data.rooms.values()
        ],
        "speakers": [f"{s.id}: {s.name}" for s in data.speakers.values()],
        "dropped": {rule: len(ids) for rule, ids in data.dropped.items()},
        "skipped": list(data.skipped),
    }


def clock(moment: datetime, zone: ZoneInfo) -> str:
    return moment.astimezone(zone).strftime("%H:%M")
