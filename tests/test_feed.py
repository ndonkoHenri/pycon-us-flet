"""Tests for decoding the feed into the model (D-41, D-42; DATA-01, DATA-13, DATA-24, DATA-26).

They run on the recorded 2025 and 2026 feeds, under two machine time zones (``machine_tz``).
Edge cases are deep copies of the recorded feeds with one record changed. Ionic's rules
have their own tests in ``test_rules.py``, and the invariants and snapshot of the
processed model are in ``test_feed_invariants.py``.
"""

import logging
from collections.abc import Callable
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from pycon_us.core.feed import FeedError, process
from tests.feeds import YEARS, changed, document, processed, settings

pytestmark = pytest.mark.usefixtures("machine_tz")

KEPT = 5  # the index of a 2026 slot that becomes a session ("Registration Desk Opens")


@pytest.mark.parametrize("year", YEARS)
def test_recorded_feeds_have_no_unreadable_record(year: int) -> None:
    assert processed(year).skipped == ()


def test_the_bundled_snapshot_processes_cleanly() -> None:
    """NEW-03: the snapshot the app opens with offline reads without a skipped record.

    ``tools/update_snapshot.py`` refuses a feed that fails this, so it holds for every
    snapshot the tool writes. The P0-13 invariants should take the snapshot as an input
    too when they land.
    """
    year_data = load_year()
    data = process(year_data.read_snapshot().raw, year_data.feed_settings)
    assert data.skipped == ()
    assert data.sessions and data.days
    conference = year_data.conference
    days = [day.date for day in data.days]
    assert conference.first_day <= days[0] and days[-1] <= conference.last_day


def test_2026_has_five_schedule_days() -> None:
    assert [day.date for day in processed(2026).days] == [
        date(2026, 5, d) for d in range(13, 18)
    ]


def test_2025_times_stay_in_eastern_time() -> None:
    # "Registration / Information Desks Open"
    session = processed(2025).sessions["1745"]
    eastern = ZoneInfo("America/New_York")
    assert session.start == datetime(2025, 5, 14, 7, 0, tzinfo=eastern)
    assert session.start.tzinfo == eastern
    assert session.day == date(2025, 5, 14)


def test_a_late_evening_session_stays_on_its_local_day() -> None:
    # 23:30 Pacific on Friday is already Saturday in UTC and in Kiritimati.
    def late(doc: dict[str, Any]) -> None:
        doc["schedule"][KEPT].update(
            start="2026-05-15T23:30:00-07:00", end="2026-05-15T23:45:00-07:00"
        )

    data = process(changed(2026, late), settings(2026))
    session_id = str(document(2026)["schedule"][KEPT]["conf_key"])
    assert data.sessions[session_id].day == date(2026, 5, 15)
    (friday,) = [day for day in data.days if day.date == date(2026, 5, 15)]
    assert session_id in friday.groups[-1].session_ids


def test_slot_fields_are_decoded() -> None:
    slot = next(s for s in document(2026)["schedule"] if s["kind"] == "talk")
    session = processed(2026).sessions[str(slot["conf_key"])]
    assert (session.name, session.kind, session.track, session.location) == (
        slot["name"],
        slot["kind"],
        "Talk",
        slot["room"],
    )
    assert session.description == slot["description"]
    assert session.url == slot.get("conf_url", "")


@pytest.mark.parametrize("year", YEARS)
def test_speakers_are_registered_once_by_id_from_sessions_and_posters(
    year: int,
) -> None:
    # No dropped slot carries speakers, so every speaker record of the feed is registered,
    # but for the pseudo-speaker "Hosted by …" (DATA-15).
    doc = document(year)
    slots = doc["schedule"]
    records = [s for slot in slots for s in slot.get("speakers") or []]
    records += [s for poster in doc.get("posters", []) for s in poster["speakers"]]
    nested = [p for slot in slots for p in slot.get("sessions") or []]  # 2025 (D-121)
    records += [s for poster in nested for s in poster["speakers"]]
    data = processed(year)
    people = [r for r in records if not r["name"].startswith("Hosted by ")]
    assert set(data.speakers) == {str(record["id"]) for record in people}
    for session in data.sessions.values():
        assert set(session.speaker_ids) <= set(data.speakers)
    for poster in data.posters:
        assert poster.speaker_ids and set(poster.speaker_ids) <= set(data.speakers)


def test_first_record_of_a_speaker_wins_poster_authors_first() -> None:
    """As in Ionic, poster authors are registered before the schedule's speakers."""
    first = next(slot for slot in document(2026)["schedule"] if slot["kind"] == "talk")
    speaker = first["speakers"][0]
    poster_copy = dict(speaker, bio="<p>From the poster.</p>")

    def add_poster_copy(doc: dict[str, Any]) -> None:
        doc["posters"][0]["speakers"].append(poster_copy)
        doc["posters"][1]["speakers"].append(dict(speaker, bio="<p>Later.</p>"))

    data = process(changed(2026, add_poster_copy), settings(2026))
    registered = data.speakers[str(speaker["id"])]
    assert (registered.name, registered.bio) == (speaker["name"], poster_copy["bio"])


def test_a_nested_poster_with_a_posters_id_is_skipped() -> None:
    """D-121: top-level and nested posters share one id space."""

    def nest_a_copy(doc: dict[str, Any]) -> None:
        poster = doc["posters"][0]
        doc["schedule"].append(
            {
                **doc["schedule"][KEPT],
                "conf_key": 99999,
                "kind": "poster",
                "sessions": [{"conf_key": poster["conf_key"], "name": "Copy"}],
            }
        )

    data = process(changed(2026, nest_a_copy), settings(2026))
    poster_id = str(document(2026)["posters"][0]["conf_key"])
    assert data.skipped == (f"schedule posters[0]: duplicate id '{poster_id}'",)
    assert [p.title for p in data.posters if p.id == poster_id] == [
        document(2026)["posters"][0]["title"]
    ]


def test_posters_sprints_and_job_listings_pass_through() -> None:
    doc = document(2026)
    data = processed(2026)
    assert (len(data.posters), len(data.sprints), len(data.job_listings)) == (
        25,
        24,
        13,
    )

    poster, record = data.posters[0], doc["posters"][0]
    assert (poster.id, poster.title, poster.description) == (
        str(record["conf_key"]),
        record["title"],
        record["description_html"],
    )
    assert poster.speaker_ids == tuple(str(s["id"]) for s in record["speakers"])

    for sprint, record in zip(data.sprints, doc["sprints"], strict=True):
        assert (sprint.id, sprint.name, sprint.url, sprint.submitter) == (
            str(record["id"]),
            record["name"],
            record["url"],
            record["submitter"],
        )
        assert sprint.logo_url == record["logo_url"]  # None for two projects
        assert sprint.description == record["description_html"]
    assert sum(sprint.logo_url is None for sprint in data.sprints) == 2

    listing, record = data.job_listings[0], doc["job-listings"][0]
    assert (listing.id, listing.sponsor_name, listing.sponsor_level) == (
        str(record["id"]),
        record["sponsor_name"],
        record["sponsor_level"],
    )
    assert listing.description == record["description_html"]
    assert listing.sponsor_logo_url == record["sponsor_logo_url"]


def test_feed_without_optional_sections_decodes_them_empty() -> None:
    data = processed(2025)  # its posters are nested in a slot instead (test_rules.py)
    assert (data.sprints, data.job_listings) == ((), ())


def test_unknown_fields_are_ignored() -> None:
    def add_fields(doc: dict[str, Any]) -> None:
        doc["something-new"] = {"a": 1}
        doc["schedule"][0]["subtitle"] = "new in 2027"
        doc["posters"][0]["video_url"] = "https://example.org/v"

    data = process(changed(2026, add_fields), settings(2026))
    assert data.skipped == ()
    assert len(data.sessions) == len(processed(2026).sessions)


def break_start(doc: dict[str, Any]) -> None:
    del doc["schedule"][KEPT]["start"]


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        (break_start, "'start' should be a string, got None"),
        (
            lambda doc: doc["schedule"][KEPT].update(start="2026-05-15T09:00:00"),
            "'start' has no UTC offset",
        ),
        (
            lambda doc: doc["schedule"][KEPT].update(start="tomorrow"),
            "'start' is not an ISO 8601 time: 'tomorrow'",
        ),
        (
            lambda doc: doc["schedule"][KEPT].update(end="2026-05-01T09:00:00-07:00"),
            "before it starts",
        ),
        (
            lambda doc: doc["schedule"][KEPT].update(conf_key=True),
            "'conf_key' should be an id, got True",
        ),
        (
            lambda doc: doc["schedule"][KEPT].update(name=None),
            "'name' should be a string, got None",
        ),
        (
            lambda doc: doc["schedule"][KEPT].update(speakers={}),
            "'speakers' should be a list",
        ),
        (
            lambda doc: doc["schedule"][KEPT].update(speakers=[{"name": "Ana"}]),
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
    bad = str(document(2026)["schedule"][KEPT]["conf_key"])
    with caplog.at_level(logging.WARNING, logger="pycon_us.core.feed"):
        data = process(changed(2026, change), settings(2026))
    assert set(processed(2026).sessions) - set(data.sessions) == {bad}
    assert len(data.sessions) == len(processed(2026).sessions) - 1
    (reason,) = data.skipped
    assert reason.startswith(f"schedule[{KEPT}]: ") and problem in reason
    assert [r.getMessage() for r in caplog.records] == [
        f"Skipped a feed record: {reason}"
    ]


@pytest.mark.parametrize(
    ("section", "index", "key", "field", "count"),
    [
        ("schedule", KEPT, "conf_key", "name", 345),
        ("posters", 0, "conf_key", "title", 25),
        ("sprints", 0, "id", "name", 24),
        ("job-listings", 0, "id", "sponsor_name", 13),
    ],
)
def test_duplicate_id_keeps_the_first(
    section: str, index: int, key: str, field: str, count: int
) -> None:
    def duplicate(doc: dict[str, Any]) -> None:
        first = doc[section][index]
        doc[section].append(dict(first, **{key: str(first[key]), field: "Impostor"}))

    data = process(changed(2026, duplicate), settings(2026))
    first = document(2026)[section][index]
    position = len(document(2026)[section])
    assert data.skipped == (f"{section}[{position}]: duplicate id '{first[key]}'",)
    records = {
        "schedule": list(data.sessions.values()),
        "posters": data.posters,
        "sprints": data.sprints,
        "job-listings": data.job_listings,
    }[section]
    kept = [record for record in records if record.id == str(first[key])]
    assert len(records) == count
    assert [getattr(record, field) for record in kept] == [first[field]]


def test_time_out_of_range_is_skipped() -> None:
    raw = changed(
        2026,
        lambda doc: doc["schedule"][KEPT].update(start="0001-01-01T00:00:00+00:00"),
    )
    data = process(raw, settings(2026))
    assert data.skipped == (
        f"schedule[{KEPT}]: 'start' is out of range: '0001-01-01T00:00:00+00:00'",
    )
    assert len(data.sessions) == len(processed(2026).sessions) - 1


def test_bad_records_in_other_sections_are_skipped() -> None:
    def spoil(doc: dict[str, Any]) -> None:
        doc["posters"][0]["title"] = 7
        doc["sprints"][1] = None
        del doc["job-listings"][2]["sponsor_name"]
        doc["open-spaces"][3]["conf_key"] = "3"
        doc["open-spaces"][4]["start"] = "soon"
        doc["open-spaces"][5]["start"] = 0  # falsy, but not "not scheduled"
        doc["open-spaces"][6]["end"] = False

    data = process(changed(2026, spoil), settings(2026))
    assert (len(data.posters), len(data.sprints), len(data.job_listings)) == (
        24,
        23,
        12,
    )
    open_spaces = [s for s in data.sessions.values() if s.kind == "open-space"]
    assert len(open_spaces) == 119
    assert [reason.split(":")[0] for reason in data.skipped] == [
        "posters[0]",
        "open-spaces[3]",
        "open-spaces[4]",
        "open-spaces[5]",
        "open-spaces[6]",
        "sprints[1]",
        "job-listings[2]",
    ]
    assert "'conf_key' should be an integer, got '3'" in data.skipped[1]


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
