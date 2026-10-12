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
from datetime import datetime, timedelta
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
    # A scheduled open space (its raw times and room) is a session; another is dropped.
    unscheduled = data.dropped.get("unscheduled-open-space", ())
    for space in doc.get("open-spaces", []):
        space_id = str(space["conf_key"] + 9000)
        room = (space.get("room_display") or "").strip() or (space.get("room") or "")
        if space.get("start") and space.get("end") and room.strip():
            assert space_id in data.sessions and space_id not in unscheduled
        else:
            assert space_id in unscheduled and space_id not in data.sessions
    # Every raw poster, top-level or nested in a slot (D-121), has its detail session.
    raw_posters = [str(p["conf_key"]) for p in doc.get("posters", [])]
    raw_posters += [
        str(p["conf_key"]) for s in doc["schedule"] for p in s.get("sessions") or []
    ]
    assert [poster.id for poster in data.posters] == raw_posters
    for poster_id in raw_posters:
        assert not data.sessions[f"poster-detail-{poster_id}"].in_timeline


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
    """DATA-04, DATA-06: no free or duplicate open space, placeholder, Posters plenary or
    blank is a session; posters and breaks remain, as one Posters row a poster day and
    break rows."""
    doc = document(year)
    data = processed(year)
    zone = load_year(year).conference.zone
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
        ):
            assert str(slot["conf_key"]) not in data.sessions, slot["conf_key"]
    poster_days = {
        local_date(datetime.fromisoformat(slot["start"]), zone)
        for slot in doc["schedule"]
        if slot["kind"] == "poster"
    }
    rows = collapsed_rows(data)
    posters_rows = Counter(row.day for row in rows if row.name == "Posters")
    assert set(posters_rows) == poster_days and set(posters_rows.values()) == {1}
    assert any(row.kind == "break" for row in rows)


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
        shift = 0
        if session.kind not in ("open-space", "break", "poster"):  # slots' titles only
            matched = [o for o in overrides if o.pattern.fullmatch(session.name)]
            shift = matched[0].minutes if matched else 0
        assert session.display_start == session.start + timedelta(minutes=shift)


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
        order = [
            (data.sessions[i].start, data.sessions[i].name) for i in room.session_ids
        ]
        assert order == sorted(order), slug  # by start, then name (D-125)
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
    ``speakers <ids>`` and ``text <names not in the directory>``. ``markdown`` shows
    the converted fields (D-130): see ``markdown_samples``.
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
        "markdown": markdown_samples(data),
    }


def markdown_samples(data: ConferenceData) -> dict[str, list[str]]:
    """Every content block's Markdown, and one of each other converted field, by line.

    The other fields show their first value that conversion changed: enough to review a
    change of conversion without copying every description into the snapshot. Open
    spaces pass through unchanged (DATA-25), so none is shown.
    """
    samples = {
        f"content {key}": value.splitlines() for key, value in data.content_md.items()
    }
    fields = {
        "session": [
            (s.id, s.description, s.description_md) for s in data.sessions.values()
        ],
        "speaker": [(s.id, s.bio, s.bio_md) for s in data.speakers.values()],
        "poster": [(p.id, p.description, p.description_md) for p in data.posters],
        "sprint": [(s.id, s.description, s.description_md) for s in data.sprints],
        "job listing": [
            (j.id, j.description, j.description_md) for j in data.job_listings
        ],
    }
    for field, values in fields.items():
        if sample := next((v for v in values if v[1] != v[2]), None):
            samples[f"{field} {sample[0]}"] = sample[2].splitlines()
    return samples


def clock(moment: datetime, zone: ZoneInfo) -> str:
    return moment.astimezone(zone).strftime("%H:%M")
