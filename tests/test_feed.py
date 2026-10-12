"""Tests for decoding the feed into the model (D-41, D-42; DATA-01, DATA-13, DATA-24, DATA-26).

They run on the recorded 2025 and 2026 feeds, under two machine time zones (``machine_tz``).
Edge cases are deep copies of the recorded feeds with one record changed.
"""

import json
import logging
from collections.abc import Callable
from datetime import date, datetime
from functools import cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from pycon_us.config import load_year
from pycon_us.core.feed import FeedError, FeedSettings, process
from pycon_us.core.models import ConferenceData

pytestmark = pytest.mark.usefixtures("machine_tz")

FEEDS = Path(__file__).parent / "fixtures" / "feeds"
YEARS = [2025, 2026]


@cache
def recorded(year: int) -> bytes:
    return (FEEDS / f"conference-{year}.json").read_bytes()


def settings(year: int) -> FeedSettings:
    return load_year(year).feed_settings


def decoded(year: int) -> ConferenceData:
    return process(recorded(year), settings(year))


def changed(year: int, change: Callable[[dict[str, Any]], object]) -> bytes:
    """The recorded feed with ``change`` applied to a fresh copy of its JSON."""
    document = json.loads(recorded(year))
    change(document)
    return json.dumps(document).encode()


@pytest.mark.parametrize("year", YEARS)
def test_recorded_feed_decodes_every_slot(year: int) -> None:
    slots = json.loads(recorded(year))["schedule"]
    data = decoded(year)
    assert data.skipped == ()
    assert len(data.sessions) == len(slots)


@pytest.mark.parametrize("year", YEARS)
def test_session_ids_are_the_slots_conf_keys_as_strings(year: int) -> None:
    slots = json.loads(recorded(year))["schedule"]
    data = decoded(year)
    assert list(data.sessions) == [str(slot["conf_key"]) for slot in slots]
    assert all(type(session.id) is str for session in data.sessions.values())
    assert all(
        session_id == session.id for session_id, session in data.sessions.items()
    )


@pytest.mark.parametrize("year", YEARS)
def test_every_time_group_has_an_aware_start_in_the_conference_zone(year: int) -> None:
    zone = load_year(year).conference.zone
    data = decoded(year)
    for day in data.days:
        starts = [group.start for group in day.groups]
        assert starts == sorted(set(starts)), day.date
        for group in day.groups:
            assert group.start.tzinfo == zone
            assert group.start.astimezone(zone).date() == day.date
            for session_id in group.session_ids:
                assert data.sessions[session_id].start == group.start


@pytest.mark.parametrize("year", YEARS)
def test_every_session_is_in_exactly_one_group(year: int) -> None:
    data = decoded(year)
    grouped = [
        i for day in data.days for group in day.groups for i in group.session_ids
    ]
    assert sorted(grouped) == sorted(data.sessions)


@pytest.mark.parametrize("year", YEARS)
def test_days_are_conference_dates_in_order(year: int) -> None:
    conference = load_year(year).conference
    days = [day.date for day in decoded(year).days]
    assert days == sorted(days)
    assert conference.first_day <= days[0] and days[-1] <= conference.last_day


def test_2026_has_five_schedule_days() -> None:
    assert [day.date for day in decoded(2026).days] == [
        date(2026, 5, d) for d in range(13, 18)
    ]


def test_2025_times_stay_in_eastern_time() -> None:
    session = decoded(2025).sessions["1745"]  # "Registration / Information Desks Open"
    eastern = ZoneInfo("America/New_York")
    assert session.start == datetime(2025, 5, 14, 7, 0, tzinfo=eastern)
    assert session.start.tzinfo == eastern
    assert session.day == date(2025, 5, 14)


def test_a_late_evening_session_stays_on_its_local_day() -> None:
    # 23:30 Pacific on Friday is already Saturday in UTC and in Kiritimati.
    def late(doc: dict[str, Any]) -> None:
        doc["schedule"][0].update(
            start="2026-05-15T23:30:00-07:00", end="2026-05-15T23:45:00-07:00"
        )

    data = process(changed(2026, late), settings(2026))
    session_id = str(json.loads(recorded(2026))["schedule"][0]["conf_key"])
    assert data.sessions[session_id].day == date(2026, 5, 15)
    (friday,) = [day for day in data.days if day.date == date(2026, 5, 15)]
    assert session_id in friday.groups[-1].session_ids


def test_slot_fields_are_decoded() -> None:
    session = decoded(2026).sessions["1136"]
    slot = next(
        s for s in json.loads(recorded(2026))["schedule"] if s["conf_key"] == 1136
    )
    assert (session.name, session.kind, session.location) == (
        slot["name"],
        slot["kind"],
        slot["room"],
    )
    assert session.description == slot["description"]
    assert session.url == slot.get("conf_url", "")


def test_speakers_are_registered_once_by_id_from_slots_and_posters() -> None:
    document = json.loads(recorded(2026))
    records = [s for slot in document["schedule"] for s in slot.get("speakers") or []]
    records += [s for poster in document["posters"] for s in poster["speakers"]]
    data = decoded(2026)
    assert set(data.speakers) == {str(record["id"]) for record in records}
    for session in data.sessions.values():
        assert set(session.speaker_ids) <= set(data.speakers)
    for poster in data.posters:
        assert poster.speaker_ids and set(poster.speaker_ids) <= set(data.speakers)


def test_first_record_of_a_speaker_wins() -> None:
    document = json.loads(recorded(2026))
    first = next(slot for slot in document["schedule"] if slot.get("speakers"))
    speaker = first["speakers"][0]

    def rename_later_copy(doc: dict[str, Any]) -> None:
        doc["posters"][0]["speakers"].append(dict(speaker, name="Someone Else", bio=""))

    data = process(changed(2026, rename_later_copy), settings(2026))
    registered = data.speakers[str(speaker["id"])]
    assert (registered.name, registered.bio) == (speaker["name"], speaker["bio"])


def test_posters_sprints_and_job_listings_pass_through() -> None:
    document = json.loads(recorded(2026))
    data = decoded(2026)
    assert (len(data.posters), len(data.sprints), len(data.job_listings)) == (
        25,
        24,
        13,
    )

    poster, record = data.posters[0], document["posters"][0]
    assert (poster.id, poster.title, poster.description) == (
        str(record["conf_key"]),
        record["title"],
        record["description_html"],
    )
    assert poster.speaker_ids == tuple(str(s["id"]) for s in record["speakers"])

    for sprint, record in zip(data.sprints, document["sprints"], strict=True):
        assert (sprint.id, sprint.name, sprint.url, sprint.submitter) == (
            str(record["id"]),
            record["name"],
            record["url"],
            record["submitter"],
        )
        assert sprint.logo_url == record["logo_url"]  # None for two projects
    assert sum(sprint.logo_url is None for sprint in data.sprints) == 2

    listing, record = data.job_listings[0], document["job-listings"][0]
    assert (listing.id, listing.sponsor_name, listing.sponsor_level) == (
        str(record["id"]),
        record["sponsor_name"],
        record["sponsor_level"],
    )
    assert listing.description == record["description_html"]


def test_feed_without_optional_sections_decodes_them_empty() -> None:
    data = decoded(2025)
    assert (data.posters, data.sprints, data.job_listings) == ((), (), ())


def test_unknown_fields_are_ignored() -> None:
    def add_fields(doc: dict[str, Any]) -> None:
        doc["something-new"] = {"a": 1}
        doc["schedule"][0]["subtitle"] = "new in 2027"
        doc["posters"][0]["video_url"] = "https://example.org/v"

    data = process(changed(2026, add_fields), settings(2026))
    assert data.skipped == ()
    assert len(data.sessions) == len(decoded(2026).sessions)


def test_processing_the_same_bytes_twice_gives_the_same_model() -> None:
    first, second = decoded(2026), decoded(2026)
    assert list(first.sessions) == list(second.sessions)
    assert [
        (d.date, [(g.start, g.session_ids) for g in d.groups]) for d in first.days
    ] == [(d.date, [(g.start, g.session_ids) for g in d.groups]) for d in second.days]


def break_start(doc: dict[str, Any]) -> None:
    del doc["schedule"][5]["start"]


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        (break_start, "'start' should be a string, got None"),
        (
            lambda doc: doc["schedule"][5].update(start="2026-05-15T09:00:00"),
            "'start' has no UTC offset",
        ),
        (
            lambda doc: doc["schedule"][5].update(start="tomorrow"),
            "'start' is not an ISO 8601 time: 'tomorrow'",
        ),
        (
            lambda doc: doc["schedule"][5].update(end="2026-05-01T09:00:00-07:00"),
            "before it starts",
        ),
        (
            lambda doc: doc["schedule"][5].update(conf_key=True),
            "'conf_key' should be an id, got True",
        ),
        (
            lambda doc: doc["schedule"][5].update(name=None),
            "'name' should be a string, got None",
        ),
        (
            lambda doc: doc["schedule"][5].update(speakers={}),
            "'speakers' should be a list",
        ),
        (
            lambda doc: doc["schedule"][5].update(speakers=[{"name": "Ana"}]),
            "'id' should be an id, got None",
        ),
        (
            lambda doc: doc["schedule"].__setitem__(5, "slot"),
            "expected an object, got 'slot'",
        ),
    ],
)
def test_bad_slot_is_skipped_and_logged(
    change: Callable[[dict[str, Any]], object],
    problem: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    slots = json.loads(recorded(2026))["schedule"]
    with caplog.at_level(logging.WARNING, logger="pycon_us.core.feed"):
        data = process(changed(2026, change), settings(2026))
    assert str(slots[5]["conf_key"]) not in data.sessions
    assert len(data.sessions) == len(slots) - 1
    (reason,) = data.skipped
    assert reason.startswith("schedule[5]: ") and problem in reason
    assert [r.getMessage() for r in caplog.records] == [
        f"Skipped a feed record: {reason}"
    ]


@pytest.mark.parametrize(
    ("section", "key", "count"),
    [
        ("schedule", "conf_key", 728),
        ("posters", "conf_key", 25),
        ("sprints", "id", 24),
        ("job-listings", "id", 13),
    ],
)
def test_duplicate_id_keeps_the_first(section: str, key: str, count: int) -> None:
    def duplicate(doc: dict[str, Any]) -> None:
        first = doc[section][0]
        doc[section].append(dict(first, **{key: str(first[key])}))  # "6" repeats 6

    data = process(changed(2026, duplicate), settings(2026))
    first = json.loads(recorded(2026))[section][0]
    assert data.skipped == (f"{section}[{count}]: duplicate id '{first[key]}'",)


def test_time_out_of_range_is_skipped() -> None:
    raw = changed(
        2026, lambda doc: doc["schedule"][5].update(start="0001-01-01T00:00:00+00:00")
    )
    data = process(raw, settings(2026))
    assert data.skipped == (
        "schedule[5]: 'start' is out of range: '0001-01-01T00:00:00+00:00'",
    )
    assert len(data.sessions) == 727


def test_bad_records_in_other_sections_are_skipped() -> None:
    def spoil(doc: dict[str, Any]) -> None:
        doc["posters"][0]["title"] = 7
        doc["sprints"][1] = None
        del doc["job-listings"][2]["sponsor_name"]

    data = process(changed(2026, spoil), settings(2026))
    assert (len(data.posters), len(data.sprints), len(data.job_listings)) == (
        24,
        23,
        12,
    )
    assert [reason.split(":")[0] for reason in data.skipped] == [
        "posters[0]",
        "sprints[1]",
        "job-listings[2]",
    ]


@pytest.mark.parametrize(
    ("raw", "problem"),
    [
        (b"<html>Maintenance</html>", "not JSON"),
        (b"\xff\xfe\x00", "not JSON"),
        (b"[]", "not a JSON object"),
        (b'{"conference": {}}', "no 'schedule' list"),
        (b'{"schedule": {}}', "no 'schedule' list"),
        (b'{"schedule": []}', "no readable schedule slot"),
        (b'{"schedule": [42, "slot"]}', "no readable schedule slot"),
    ],
)
def test_unusable_feed_raises_feed_error(raw: bytes, problem: str) -> None:
    with pytest.raises(FeedError, match=problem):
        process(raw, settings(2026))


def test_optional_section_of_the_wrong_type_raises_feed_error() -> None:
    raw = changed(2026, lambda doc: doc.update(sprints={"oops": 1}))
    with pytest.raises(FeedError, match="'sprints' is not a list"):
        process(raw, settings(2026))
