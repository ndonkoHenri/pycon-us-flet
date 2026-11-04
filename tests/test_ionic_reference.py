"""Our processed feeds against Ionic's own processing of them, captured once (D-77; SCHED-19).

Ionic is a reference, not an oracle. Where we chose to differ, `INTENDED_DIFFERENCES`
names the decision or feature id, the normaliser in `tests/ionic.py` turns Ionic's facts
into what we intend, and a named test below shows the difference on the captured output.
Everything else must match exactly, on both recorded feeds and under both machine zones.
"""

import re

import pytest

from pycon_us.config import load_year
from pycon_us.core.rules import COLLAPSED_KINDS
from pycon_us.core.slugs import room_sort_key
from tests.feeds import YEARS, processed, settings
from tests.ionic import (
    HOSTED_BY,
    IONIC_HALL_PREFIX,
    IONIC_LIGHTNING_TALKS_LOCATION,
    Facts,
    captured,
    clock_label,
    comparable_ours,
    hall_names,
    intended,
    ionic_facts,
    lightning_talks_in_their_place,
    mismatches,
    nested_posters,
    our_facts,
    with_our_hall_names,
)

pytestmark = pytest.mark.usefixtures("machine_tz")

INTENDED_DIFFERENCES = {
    "D-121": "2025's nested posters are posters: each has a poster detail, and its authors "
    "join the directory first, as every poster author does (Ionic never read them)",
    "D-122": "the 'Expo ' before a 'Hall …' room is year data; 2025's feed has no such prefix",
    "D-124": "the lightning talks' place is year data; 2025's show the room they list",
    "D-125": "'Hosted by …' is text, not a speaker; a room lists its sessions by start, then "
    "name (Ionic: by start, then in whatever order its arrays had)",
    "D-31": "a slot's rows are ordered by room, then name, not in the order Ionic met them",
    "DATA-13": "every time group has a start (Ionic's first group of a new day had none)",
    "MAP-08": "sprint-only rooms come from map.toml in P2 (Ionic seeded its 2026 venue's "
    "into every year, empty)",
}


# The comparisons.


@pytest.mark.parametrize("year", YEARS)
def test_session_ids_match_ionic(year: int) -> None:
    """DATA-26: the same ids, Ionic's synthetic ones included."""
    assert set(comparable_ours(year).sessions) == set(intended(year).sessions)


@pytest.mark.parametrize("year", YEARS)
def test_session_facts_match_ionic(year: int) -> None:
    """Names, tracks, places, times, the Job Fair's label, speakers and flags (DATA-08..16)."""
    assert mismatches(comparable_ours(year).sessions, intended(year).sessions) == {}


@pytest.mark.parametrize("year", YEARS)
def test_timeline_matches_ionic(year: int) -> None:
    """DATA-12, DATA-13: the same days and groups, in the same order, with the same rows."""
    ours, theirs = our_facts(year).timeline, intended(year).timeline
    assert {day: list(groups) for day, groups in ours.items()} == {
        day: list(groups) for day, groups in theirs.items()
    }
    assert ours == theirs


@pytest.mark.parametrize("year", YEARS)
def test_collapsed_rows_match_ionic(year: int) -> None:
    """DATA-06: the same Coffee, Break, Lunch and Posters rows, with the same spans."""
    hall = hall_names(year)
    rows = {
        hall(row["id"]): (row["name"], hall(row["location"]), row["start"], row["end"])
        for row in captured(year, "collapsed")
    }
    ours = {
        s.id: (s.name, s.location, s.start.isoformat(), s.end.isoformat())
        for s in processed(year).sessions.values()
        if s.kind in COLLAPSED_KINDS and s.in_timeline
    }
    assert ours == rows


@pytest.mark.parametrize("year", YEARS)
def test_rooms_match_ionic(year: int) -> None:
    """DATA-16: the same rooms, each with the same sessions (in D-125's order)."""
    assert mismatches(comparable_ours(year).rooms, intended(year).rooms) == {}


@pytest.mark.parametrize("year", YEARS)
def test_rooms_sort_as_ionic_sorted_them(year: int) -> None:
    """D-125: `room_sort_key` gives localeCompare's numeric, accent-blind order."""
    names = [room["name"] for room in captured(year, "rooms")]
    assert sorted(names, key=room_sort_key) == names


@pytest.mark.parametrize("year", YEARS)
def test_speakers_match_ionic(year: int) -> None:
    """DATA-15: the same directory, in the same order, each speaker on the same sessions."""
    ours, theirs = comparable_ours(year).speakers, intended(year).speakers
    assert mismatches(ours, theirs) == {}
    authors = nested_posters(year)[1]  # D-121: registered first, as poster authors
    assert [i for i in ours if i not in authors] == [
        i for i in theirs if i not in authors
    ]


def test_capture_agrees_with_the_earlier_simulation() -> None:
    """docs/research/ionic/data-layer.md §3.7 simulated Ionic in Python; Node agrees."""
    summary = captured(2026, "summary")
    assert (summary["sessions"], summary["speakers"], summary["rooms"]) == (
        345,
        170,
        38,
    )
    days = [(day["groups"], day["sessions"]) for day in summary["days"]]
    assert days == [(5, 13), (11, 31), (26, 111), (28, 107), (18, 58)]
    assert len(captured(2026, "collapsed")) == 14


# One test per intended difference, showing it on the captured output.


def test_ionic_never_read_2025s_nested_posters() -> None:
    """D-121."""
    details, authors = nested_posters(2025)
    assert len(details) == 19
    assert not details & set(ionic_facts(2025).sessions)
    assert details <= set(our_facts(2025).sessions)
    assert authors - set(ionic_facts(2025).speakers)
    assert authors <= set(our_facts(2025).speakers)


def test_ionic_put_expo_before_2025s_halls() -> None:
    """D-122: 2026's prefix is Ionic's; 2025's halls keep the feed's names."""
    assert settings(2026).hall_prefix == IONIC_HALL_PREFIX
    assert settings(2025).hall_prefix == ""
    ionic_rooms = {room["name"] for room in ionic_facts(2025).rooms.values()}
    our_rooms = {room["name"] for room in our_facts(2025).rooms.values()}
    assert {"Expo Hall A", "Expo Hall B", "Expo Hall C"} <= ionic_rooms
    assert {"Hall A", "Hall B", "Hall C"} <= our_rooms
    assert not any(name.startswith(IONIC_HALL_PREFIX) for name in our_rooms)


@pytest.mark.parametrize(
    ("year", "place"), [(2025, "Hall B"), (2026, IONIC_LIGHTNING_TALKS_LOCATION)]
)
def test_ionic_showed_every_years_lightning_talks_in_2026s_arena(
    year: int, place: str
) -> None:
    """D-124: 2025's lightning talks list one room, Hall B, and show it."""
    ionic = ionic_facts(year).sessions
    talks = [i for i, s in ionic.items() if s["track"] == "Lightning-talks"]
    assert len(talks) == 4
    assert {ionic[i]["displayLocation"] for i in talks} == {
        IONIC_LIGHTNING_TALKS_LOCATION
    }
    ours = our_facts(year).sessions
    assert {ours[i]["displayLocation"] for i in talks} == {place}


@pytest.mark.parametrize("year", YEARS)
def test_ionic_listed_hosted_by_as_a_speaker(year: int) -> None:
    """D-125: the lightning talks' hosts are text, not a directory entry."""
    ionic = ionic_facts(year).speakers
    (host,) = [i for i, sp in ionic.items() if sp["name"].startswith(HOSTED_BY)]
    ours = our_facts(year)
    assert host not in ours.speakers
    for session_id in ionic[host]["sessions"]:
        assert host not in ours.sessions[session_id]["speakers"]
        assert ionic[host]["name"] in ours.sessions[session_id]["speakerNames"]


@pytest.mark.parametrize("year", YEARS)
def test_ionic_listed_a_rooms_sessions_by_start_only(year: int) -> None:
    """D-125: where sessions start together, we order them by name; Ionic kept array order."""
    ours = comparable_ours(year).rooms
    ionic = with_our_hall_names(ionic_facts(year), hall_names(year)).rooms
    reordered = [
        slug
        for slug, room in ours.items()
        if room["sessions"] != ionic[slug]["sessions"]
        and sorted(room["sessions"]) == sorted(ionic[slug]["sessions"])
    ]
    assert reordered  # 2025: Room 318; 2026: Expo Hall AB and Room 202A


@pytest.mark.parametrize("year", YEARS)
def test_ionic_ordered_a_slots_rows_as_it_met_them(year: int) -> None:
    """D-31: our rows are ordered by room, then name."""
    hall = hall_names(year)
    zone = load_year(year).conference.zone
    timeline = captured(year, "timeline")
    reordered = [
        (day.date, group.start)
        for day in processed(year).days
        for group in day.groups
        if list(group.session_ids)
        != [
            hall(i)
            for i in timeline[day.date.isoformat()][clock_label(group.start, zone)]
        ]
    ]
    assert reordered


@pytest.mark.parametrize("year", YEARS)
def test_ionic_left_a_new_days_first_group_without_start(year: int) -> None:
    """DATA-13: Ionic's "Registration Desk Opens" groups had no start; ours always do."""
    missing = captured(year, "summary")["groupsWithoutStart"]
    assert len(missing) == 2
    zone = load_year(year).conference.zone
    starts = {
        f"{day.date.isoformat()} {clock_label(group.start, zone)}"
        for day in processed(year).days
        for group in day.groups
    }
    assert set(missing) <= starts


@pytest.mark.parametrize("year", YEARS)
def test_ionic_seeded_2026s_sprint_rooms_into_every_year(year: int) -> None:
    """MAP-08: Ionic's empty rooms are its 2026 venue's sprint rooms, and so are ours.

    Ours come from the year's `map.toml`, so 2026 seeds exactly Ionic's rooms and
    2025, which has no plans, seeds none, where Ionic seeded 2026's venue into it.
    """
    empty = {room["name"] for room in captured(year, "rooms") if not room["sessions"]}
    assert empty
    assert all(re.fullmatch(r"S-\d[AB]?|Seaside .+", name) for name in empty)
    ours = {
        room.name for room in processed(year).rooms.values() if not room.session_ids
    }
    assert ours == (empty if year == 2026 else set())


def test_a_null_ionic_location_shows_as_a_mismatch_not_a_crash() -> None:
    """driver.ts writes a missing location as null; the normaliser passes it through."""
    row = {
        "track": "Lightning-talks",
        "location": None,
        "displayLocation": IONIC_LIGHTNING_TALKS_LOCATION,
    }
    facts = Facts(sessions={"1": row}, timeline={}, rooms={}, speakers={})
    halls = with_our_hall_names(facts, hall_names(2025))
    adjusted = lightning_talks_in_their_place(halls, "")
    assert adjusted.sessions["1"] == row | {"displayLocation": ""}
