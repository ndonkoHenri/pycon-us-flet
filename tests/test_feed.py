"""Tests for decoding the feed into the model (D-41, D-42; DATA-01, DATA-13, DATA-24, DATA-26).

They run on the recorded 2025 and 2026 feeds, under two machine time zones (`machine_tz`).
Edge cases are deep copies of the recorded feeds with one record changed. Ionic's rules
have their own tests in `test_rules.py` and `test_rules_details.py`, and the
invariants and snapshot of the processed model are in `test_feed_invariants.py`. Text
repair and the records that are skipped are `test_feed_records.py`'s.
"""

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from pycon_us.config import load_year
from pycon_us.core.feed import process
from tests.feeds import YEARS, changed, document, processed, settings

pytestmark = pytest.mark.usefixtures("machine_tz")

KEPT = 5  # the index of a 2026 slot that becomes a session ("Registration Desk Opens")


@pytest.mark.parametrize("year", YEARS)
def test_recorded_feeds_have_no_unreadable_record(year: int) -> None:
    """Each recorded feed processes without a skipped record."""
    assert processed(year).skipped == ()


def test_the_bundled_snapshot_processes_cleanly() -> None:
    """NEW-03: the snapshot the app opens with offline reads without a skipped record.

    `tools/update_snapshot.py` refuses a feed that fails this, so it holds for every
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
    """The 2026 feed's schedule days are the five days from May 13 to 17."""
    assert [day.date for day in processed(2026).days] == [
        date(2026, 5, d) for d in range(13, 18)
    ]


def test_2025_times_stay_in_eastern_time() -> None:
    """A 2025 session starts at 7:00 AM in the New York zone itself, on May 14.

    The session is "Registration / Information Desks Open".
    """
    session = processed(2025).sessions["1745"]
    eastern = ZoneInfo("America/New_York")
    assert session.start == datetime(2025, 5, 14, 7, 0, tzinfo=eastern)
    assert session.start.tzinfo == eastern
    assert session.day == date(2025, 5, 14)


def test_a_late_evening_session_stays_on_its_local_day() -> None:
    """A session at 11:30 PM on Friday stays on Friday, in the day's last group.

    23:30 Pacific on Friday is already Saturday in UTC and in Kiritimati.
    """

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
    """A talk slot's name, kind, track, room, description and URL reach its session."""
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
    """The feed's speakers are registered by id; sessions and posters name only them.

    No dropped slot carries speakers, so every speaker record of the feed is registered,
    but for the pseudo-speaker "Hosted by …" (DATA-15).
    """
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
    """2026's 25 posters, 24 sprints and 13 job listings keep the feed's fields.

    Two sprint projects have no logo, kept as None.
    """
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
    """2025's feed, without sprints or job listings, decodes both as empty."""
    data = processed(2025)  # its posters are nested in a slot instead (test_rules.py)
    assert (data.sprints, data.job_listings) == ((), ())


def test_unknown_fields_are_ignored() -> None:
    """Unknown fields at the top and in records skip nothing and drop no session."""

    def add_fields(doc: dict[str, Any]) -> None:
        doc["something-new"] = {"a": 1}
        doc["schedule"][0]["subtitle"] = "new in 2027"
        doc["posters"][0]["video_url"] = "https://example.org/v"

    data = process(changed(2026, add_fields), settings(2026))
    assert data.skipped == ()
    assert len(data.sessions) == len(processed(2026).sessions)
