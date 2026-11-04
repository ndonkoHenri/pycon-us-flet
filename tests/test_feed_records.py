"""Tests for decoding feed records: text repair and records that are skipped (D-41, D-42).

Lone surrogates and CESU-8 emoji in text, bad slots and records in every section, and
feeds that cannot be used at all, as deep copies of the recorded feeds with one record
changed, under two machine time zones (`machine_tz`). Whole feeds are `test_feed.py`'s.
"""

import logging
from collections.abc import Callable
from typing import Any

import pytest

from pycon_us.core.feed import FeedError, process
from pycon_us.core.models import ConferenceData
from tests.feeds import changed, document, processed, settings
from tests.test_feed import KEPT

pytestmark = pytest.mark.usefixtures("machine_tz")


def first_talk(doc: dict[str, Any]) -> dict[str, Any]:
    """Return the first talk slot of a feed document."""
    return next(slot for slot in doc["schedule"] if slot["kind"] == "talk")


TALK_ID = str(first_talk(document(2026))["conf_key"])


@pytest.mark.parametrize(
    ("field", "read"),
    [
        ("description", lambda data: data.sessions[TALK_ID].description),
        ("name", lambda data: data.sessions[TALK_ID].name),
        ("authors", lambda data: data.sessions[TALK_ID].speaker_names[0]),
        ("id", lambda data: data.sprints[0].id),
    ],
)
def test_a_lone_surrogate_becomes_a_replacement_character(
    field: str, read: Callable[[ConferenceData], str]
) -> None:
    """#150: JSON can escape a lone surrogate, which Flet's strict UTF-8 cannot send."""

    def add_surrogate(doc: dict[str, Any]) -> None:
        value = "Lone \ud800 here"
        if field == "authors":
            first_talk(doc)["authors"][0] = value
        elif field == "id":
            doc["sprints"][0]["id"] = value
        else:
            first_talk(doc)[field] = value

    raw = changed(2026, add_surrogate)
    assert b'"Lone \\ud800 here"' in raw  # the escape json.loads keeps as a code point
    data = process(raw, settings(2026))
    assert data.skipped == ()
    assert read(data) == "Lone \ufffd here"


def test_emoji_and_other_non_ascii_text_are_unchanged() -> None:
    """#150: an emoji is a pair of surrogate escapes in JSON, decoded as one character."""
    name = "Snakes \U0001f40d, caf\u00e9 and \U00020000"

    def rename(doc: dict[str, Any]) -> None:
        first_talk(doc)["name"] = name

    raw = changed(2026, rename)
    assert b"\\ud83d\\udc0d" in raw
    assert process(raw, settings(2026)).sessions[TALK_ID].name == name


def test_an_emoji_sent_as_cesu_8_bytes_is_kept() -> None:
    """json.loads decodes bytes with surrogatepass, so a CESU-8 pair is two code points."""

    def rename(doc: dict[str, Any]) -> None:
        first_talk(doc)["name"] = "Snakes CESU"

    raw = changed(2026, rename).replace(b"CESU", b"\xed\xa0\xbd\xed\xb0\x8d")
    assert process(raw, settings(2026)).sessions[TALK_ID].name == "Snakes \U0001f40d"


def test_a_lone_surrogate_in_a_content_block_becomes_a_replacement_character() -> None:
    """#152: the `conference.content` blocks bypass the record decoders."""

    def add_surrogates(doc: dict[str, Any]) -> None:
        content = doc["conference"]["content"]
        content["venues-hours"] = "Lone \ud800 here"
        content["lone-\ud800"] = "Snakes \U0001f40d"

    raw = changed(2026, add_surrogates)
    assert b'"Lone \\ud800 here"' in raw
    data = process(raw, settings(2026))
    assert data.skipped == ()
    assert data.content["venues-hours"] == "Lone \ufffd here"
    assert "Lone \ufffd here" in data.content_md["venues-hours"]
    assert data.content["lone-\ufffd"] == "Snakes \U0001f40d"
    assert "Snakes \U0001f40d" in data.content_md["lone-\ufffd"]


def break_start(doc: dict[str, Any]) -> None:
    """Delete the kept slot's start in a feed document."""
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
    """A malformed slot alone is skipped, its index and problem logged as a warning."""
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
    """A record that repeats an id is skipped, in any section; the first is kept."""

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
    """A start in year 1, which has no Pacific time, skips its slot as out of range."""
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
    """Bad posters, open spaces, sprints and job listings are skipped one by one.

    A start of 0 or an end of False is bad too, not "not scheduled"; the reasons come in
    section order and the other records are kept.
    """

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
    """A body that is no JSON object with a readable slot raises `FeedError`."""
    with pytest.raises(FeedError, match=problem):
        process(raw, settings(2026))


def test_optional_section_of_the_wrong_type_raises_feed_error() -> None:
    """A `sprints` section that is not a list raises `FeedError`."""
    raw = changed(2026, lambda doc: doc.update(sprints={"oops": 1}))
    with pytest.raises(FeedError, match="'sprints' is not a list"):
        process(raw, settings(2026))
