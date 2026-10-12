"""Ionic's captured output and the normaliser that compares it with ours (D-77; #66).

``tools/capture_ionic_reference/`` ran Ionic's ``processData`` under Node on the recorded
feeds and wrote what it made of them to ``tests/fixtures/ionic/<year>/``. This module only
reads those files, so neither CI nor contributors need Node.

The normaliser:

1. Both sides become the same ``Facts``: each session's name, track, location, shown
   location, start, end, shown start (as Ionic's ``h:mm am`` label), linked speakers,
   author names, flags, and whether the timeline lists it; the timeline (day → time label
   → session ids); the rooms (slug → name and session ids); the speakers (id → name and
   session ids).
2. A slot's rows (D-31) and a speaker's sessions are sets: they are sorted on both sides.
   The days, their groups, a room's sessions and the speaker directory keep their order.
3. ``intended()`` adjusts Ionic's facts for each intended difference that applies to the
   year (D-122, D-124, D-125, MAP-08); ``comparable_ours()`` leaves out 2025's nested
   posters, which Ionic never read (D-121).
"""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from functools import cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from pycon_us.config import load_year
from pycon_us.core.models import ConferenceData, Session
from pycon_us.core.slugs import slugify_room
from tests.feeds import document, processed, settings

IONIC = Path(__file__).parent / "fixtures" / "ionic"

IONIC_HALL_PREFIX = "Expo "  # conference-data.ts: room = `Expo ${room}`
IONIC_LIGHTNING_TALKS_LOCATION = "Pacific Ballroom - Arena"  # displayLocationOverride
# A room Ionic prefixed; "Expo Hall Opens" is a name, not a room.
EXPO_HALL = re.compile(r"\bExpo (Hall [A-Z]+)\b")
HOSTED_BY = "Hosted by"

type Table = dict[str, dict[str, Any]]


@dataclass(frozen=True)
class Facts:
    """What one side made of a feed, in Ionic's shape.

    Attributes:
        sessions: Each session's facts, by id.
        timeline: Day → time label → session ids, sorted (D-31).
        rooms: Slug → ``{"name", "sessions"}``, the sessions in the side's own order.
        speakers: Id → ``{"name", "sessions"}``, the session ids sorted; in directory order.
    """

    sessions: Table
    timeline: dict[str, dict[str, list[str]]]
    rooms: Table
    speakers: Table


@cache
def captured(year: int, name: str) -> Any:
    """One of Ionic's fixture files for ``year``, as JSON (do not mutate it)."""
    return json.loads((IONIC / str(year) / f"{name}.json").read_text(encoding="utf-8"))


def clock_label(moment: datetime, zone: ZoneInfo) -> str:
    """Ionic's time label: ``9:00 am``, ``12:30 pm``."""
    local = moment.astimezone(zone)
    return f"{local.hour % 12 or 12}:{local.minute:02d} {'am' if local.hour < 12 else 'pm'}"


def ionic_facts(year: int) -> Facts:
    """Ionic's output for ``year``, as captured."""
    return Facts(
        sessions={
            s["id"]: {key: value for key, value in s.items() if key != "id"}
            for s in captured(year, "sessions")
        },
        timeline={
            date: {time: sorted(ids) for time, ids in groups.items()}
            for date, groups in captured(year, "timeline").items()
        },
        rooms={
            room["slug"]: {"name": room["name"], "sessions": room["sessions"]}
            for room in captured(year, "rooms")
        },
        speakers={
            sp["id"]: {"name": sp["name"], "sessions": sorted(sp["sessions"])}
            for sp in captured(year, "speakers")
        },
    )


def our_facts(year: int) -> Facts:
    """Our processed model for ``year``, in Ionic's shape."""
    data = processed(year)
    zone = load_year(year).conference.zone

    def facts(session: Session) -> dict[str, Any]:
        return {
            "name": session.name,
            "track": session.track,
            "location": session.location,
            "displayLocation": session.display_location,
            "start": session.start.isoformat(),
            "end": session.end.isoformat(),
            "timeStart": clock_label(session.display_start, zone),
            "speakers": list(session.speaker_ids),
            "speakerNames": list(session.speaker_names),
            "preRegistered": session.pre_registered,
            "spanish": session.spanish,
            "inTimeline": session.in_timeline,
        }

    return Facts(
        sessions={s.id: facts(s) for s in data.sessions.values()},
        timeline={
            day.date.isoformat(): {
                clock_label(group.start, zone): sorted(group.session_ids)
                for group in day.groups
            }
            for day in data.days
        },
        rooms={
            slug: {"name": room.name, "sessions": list(room.session_ids)}
            for slug, room in data.rooms.items()
        },
        speakers={
            i: {"name": sp.name, "sessions": sorted(linked(data, i))}
            for i, sp in data.speakers.items()
        },
    )


def linked(data: ConferenceData, speaker_id: str) -> list[str]:
    """The ids of the sessions that link ``speaker_id`` (DATA-15)."""
    return [s.id for s in data.sessions.values() if speaker_id in s.speaker_ids]


def nested_posters(year: int) -> tuple[set[str], set[str]]:
    """D-121: the poster details of posters nested in a poster slot, and their authors."""
    nested = [
        poster
        for slot in document(year)["schedule"]
        if slot["kind"] == "poster"
        for poster in slot.get("sessions") or []
    ]
    details = {f"poster-detail-{poster['conf_key']}" for poster in nested}
    authors = {str(sp["id"]) for poster in nested for sp in poster["speakers"]}
    return details, authors


def hall_names(year: int) -> Callable[[str], str]:
    """D-122: how a room name, location or id Ionic wrote reads in our model of ``year``.

    Ionic wrote ``Expo `` before every ``Hall …`` room it moved into a location. 2026's
    ``hall_prefix`` is the same; 2025's feed has none, so ours keeps ``Hall A``.
    """
    prefix = settings(year).hall_prefix
    if prefix == IONIC_HALL_PREFIX:
        return lambda text: text
    assert prefix == ""  # the one other case D-122 knows
    return lambda text: EXPO_HALL.sub(r"\1", text)


def with_our_hall_names(facts: Facts, hall: Callable[[str], str]) -> Facts:
    """D-122: Ionic's facts with ``hall`` applied to every room name, location and id."""
    rooms: Table = {}
    for room in facts.rooms.values():
        name = hall(room["name"])  # 2025: "Expo Hall A" joins "Hall A"
        entry = rooms.setdefault(slugify_room(name), {"name": name, "sessions": []})
        entry["sessions"] = entry["sessions"] + [hall(i) for i in room["sessions"]]
    places = ("location", "displayLocation")
    return Facts(
        sessions={
            # A null place (driver.ts writes `?? null`) stays null, to show as a mismatch.
            hall(i): s | {key: hall(s[key]) for key in places if s[key] is not None}
            for i, s in facts.sessions.items()
        },
        timeline={
            date: {time: sorted(map(hall, ids)) for time, ids in groups.items()}
            for date, groups in facts.timeline.items()
        },
        rooms=rooms,
        speakers={
            i: sp | {"sessions": sorted(map(hall, sp["sessions"]))}
            for i, sp in facts.speakers.items()
        },
    )


def lightning_talks_in_their_place(facts: Facts, place: str) -> Facts:
    """D-124: Ionic showed every lightning-talks row at 2026's Arena; ours, the year's place.

    Without one, a row shows its first room, as any other row does.
    """

    def moved(s: dict[str, Any]) -> bool:
        arena = s["displayLocation"] == IONIC_LIGHTNING_TALKS_LOCATION
        return arena and s["track"] == "Lightning-talks"

    def first_room(s: dict[str, Any]) -> str:
        return (s["location"] or "").split(",")[0].strip()

    return replace(
        facts,
        sessions={
            i: s | {"displayLocation": place or first_room(s)} if moved(s) else s
            for i, s in facts.sessions.items()
        },
    )


def without_pseudo_speakers(facts: Facts) -> Facts:
    """D-125: Ionic listed "Hosted by …" as a speaker; it stays text in ``speakerNames``."""
    pseudo = {i for i, sp in facts.speakers.items() if sp["name"].startswith(HOSTED_BY)}
    return replace(
        facts,
        sessions={
            i: s | {"speakers": [x for x in s["speakers"] if x not in pseudo]}
            for i, s in facts.sessions.items()
        },
        speakers={i: sp for i, sp in facts.speakers.items() if i not in pseudo},
    )


def rooms_by_start_then_name(facts: Facts) -> Facts:
    """D-125: a room's sessions by start, then name; MAP-08: no empty sprint rooms yet."""

    def key(session_id: str) -> tuple[datetime, str]:
        session = facts.sessions[session_id]
        return datetime.fromisoformat(session["start"]), session["name"]

    return replace(
        facts,
        rooms={
            slug: room | {"sessions": sorted(room["sessions"], key=key)}
            for slug, room in facts.rooms.items()
            if room["sessions"]
        },
    )


@cache
def intended(year: int) -> Facts:
    """Ionic's facts, adjusted for every intended difference that applies to ``year``."""
    facts = with_our_hall_names(ionic_facts(year), hall_names(year))
    place = settings(year).lightning_talks_location
    if place != IONIC_LIGHTNING_TALKS_LOCATION:
        facts = lightning_talks_in_their_place(facts, place)
    return rooms_by_start_then_name(without_pseudo_speakers(facts))


def comparable_ours(year: int) -> Facts:
    """Our facts without what Ionic never made: 2025's nested posters (D-121).

    Their details leave the sessions, rooms and speakers, and so do the authors who have
    no other session and the rooms that held only those details.
    """
    facts, details = our_facts(year), nested_posters(year)[0]

    def kept(ids: list[str]) -> list[str]:
        return [i for i in ids if i not in details]

    rooms = {
        slug: room | {"sessions": kept(room["sessions"])}
        for slug, room in facts.rooms.items()
    }
    speakers = {
        i: sp | {"sessions": kept(sp["sessions"])} for i, sp in facts.speakers.items()
    }
    return Facts(
        sessions={i: s for i, s in facts.sessions.items() if i not in details},
        timeline=facts.timeline,
        rooms={slug: room for slug, room in rooms.items() if room["sessions"]},
        speakers={i: sp for i, sp in speakers.items() if sp["sessions"]},
    )


def mismatches(ours: Table, theirs: Table) -> dict[str, tuple[Any, Any]]:
    """The keys whose values differ, as ``(ours, Ionic's)``; a missing value is None."""
    return {
        key: (ours.get(key), theirs.get(key))
        for key in ours.keys() | theirs.keys()
        if ours.get(key) != theirs.get(key)
    }
