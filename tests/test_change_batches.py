"""The change log's batches and their JSON form (D-47, D-255; NEW-04).

Batches hold real changes: the diff of a recorded feed and a copy with named edits
(``tests/feeds.py``), so every kind, both sides and both years' zones go through the file
format the app writes.
"""

import json
import logging
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from functools import cache
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pycon_us.core.change_batches import (
    KEPT_FOR,
    Batch,
    decode_batches,
    encode_batches,
    trim,
)
from pycon_us.core.diff import Change, ChangeKind, diff
from pycon_us.core.feed import process
from tests.feeds import YEARS, add, move, pair, processed, remove, rename, settings

ZONES = {2025: ZoneInfo("America/New_York"), 2026: ZoneInfo("America/Los_Angeles")}
"""Each year's conference zone: 2025 in Pittsburgh, 2026 in Long Beach."""

TALKS = {2025: (104, 103), 2026: (142, 51)}
"""Per year, a talk that is moved and renamed, and one that is removed."""

NOW = datetime(2026, 5, 16, 17, 42, tzinfo=UTC)


@cache
def year_changes(year: int) -> tuple[Change, ...]:
    """Changes of four kinds on ``year``'s recorded feed: added, removed, room and title.

    One talk is moved and renamed, so it has two changes; the addition copies it under
    a new id; another talk is removed.
    """
    edited, dropped = TALKS[year]
    _, new = pair(
        year,
        move(edited, "Room 999"),
        rename(edited, "A renamed talk, café ☕"),
        add(990001, like=edited, name="An added talk"),
        remove(dropped),
    )
    return tuple(diff(processed(year), process(new, settings(year))))


def batch(year: int, *, seen: bool = False, at: datetime = NOW) -> Batch:
    """A batch of ``year_changes(year)`` detected at ``at``."""
    return Batch(detected_at=at, changes=year_changes(year), seen=seen)


def stored(raw: bytes) -> list[dict[str, Any]]:
    """The JSON list the log file's bytes hold."""
    return json.loads(raw)


# ------------------------------------------------------------------ round trips


@pytest.mark.parametrize("year", YEARS)
def test_a_round_trip_keeps_every_change_in_the_year_s_zone(year: int) -> None:
    """Batches read back equal, every listing time in the conference zone (D-43)."""
    batches = [batch(year), batch(year, seen=True, at=NOW - timedelta(days=3))]
    assert {change.kind for change in year_changes(year)} == {
        ChangeKind.ADDED,
        ChangeKind.REMOVED,
        ChangeKind.ROOM,
        ChangeKind.TITLE,
    }
    decoded = decode_batches(encode_batches(batches), ZONES[year])
    assert decoded == batches
    for change in decoded[0].changes:
        for listing in (change.old, change.new):
            if listing is not None:
                assert listing.start.tzinfo is ZONES[year]
                assert listing.end.tzinfo is ZONES[year]
    original = [c.latest.start for c in batches[0].changes]
    assert [c.latest.start.hour for c in decoded[0].changes] == [
        start.hour for start in original
    ]  # the same wall-clock times as the feed's


def test_the_file_is_the_documented_json() -> None:
    """The file is a list of batches with ISO 8601 times and null for a missing side."""
    [entry] = stored(encode_batches([batch(2026)]))
    assert entry["detected_at"] == "2026-05-16T17:42:00+00:00"
    assert entry["seen"] is False
    by_kind = {change["kind"]: change for change in entry["changes"]}
    assert by_kind["added"]["old"] is None and by_kind["removed"]["new"] is None
    room = by_kind["room"]
    assert room["id"] == "142"
    assert room["old"] == {
        "title": "Python for Humans - Designing Python Code Like a User Interface",
        "start": "2026-05-16T10:30:00-07:00",
        "end": "2026-05-16T11:00:00-07:00",
        "location": "Grand Ballroom A",
    }
    assert room["new"]["location"] == "Room 999"


def test_text_beyond_ascii_is_kept_as_utf_8() -> None:
    """A title with accents and emoji is written as UTF-8 and read back the same."""
    raw = encode_batches([batch(2026)])
    assert "café ☕".encode() in raw
    titles = {c.title for c in decode_batches(raw, ZONES[2026])[0].changes}
    assert "A renamed talk, café ☕" in titles


def test_no_batches_is_an_empty_list() -> None:
    """An empty log is written as ``[]`` and read back as no batches."""
    assert encode_batches([]) == b"[]"
    assert decode_batches(b"[]", UTC) == []


@given(seen=st.booleans(), hours=st.integers(min_value=-1000, max_value=1000))
def test_any_detection_time_and_seen_mark_round_trip(seen: bool, hours: int) -> None:
    """Any detection time and seen mark read back as the same instant and mark."""
    detected = NOW + timedelta(hours=hours, microseconds=hours % 7)
    [decoded] = decode_batches(
        encode_batches([batch(2026, seen=seen, at=detected)]), ZONES[2026]
    )
    assert (decoded.detected_at, decoded.seen) == (detected, seen)


# ------------------------------------------------------------------ what can be read


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"[{",
        b"\xff\xfe",
        b'{"detected_at": "x"}',
        b"null",
        b"[" * 100_000 + b"]" * 100_000,
    ],
    ids=["empty", "truncated", "not UTF-8", "an object", "null", "nested too deep"],
)
def test_a_file_that_is_not_a_json_list_gives_nothing_and_a_log(
    raw: bytes, caplog: pytest.LogCaptureFixture
) -> None:
    """Bytes that are not a JSON list read as no batches, with a warning."""
    with caplog.at_level(logging.WARNING):
        assert decode_batches(raw, UTC) == []
    assert "The change log is not" in caplog.text


def broken(edit: Any) -> list[dict[str, Any]]:
    """Three good 2026 batches with ``edit`` applied to the second's JSON."""
    entries = stored(
        encode_batches([batch(2026, at=NOW - timedelta(hours=n)) for n in range(3)])
    )
    edit(entries[1])
    return entries


def change_of(entry: dict[str, Any], kind: str) -> dict[str, Any]:
    """The change of ``kind`` in a batch's JSON."""
    return next(change for change in entry["changes"] if change["kind"] == kind)


def removal(entry: dict[str, Any]) -> dict[str, Any]:
    """The removal in a batch's JSON: 2026's talk 51."""
    return change_of(entry, "removed")


BREAKS = {
    "an empty object": lambda e: e.clear(),
    "no detection time": lambda e: e.pop("detected_at"),
    "a time without an offset": lambda e: e.update(detected_at="2026-05-16T10:00:00"),
    "a time that is no time": lambda e: e.update(detected_at="Saturday"),
    # Too far out to be put in the conference's zone: OverflowError, back and forward.
    "an out-of-range time": lambda e: e.update(detected_at="0001-01-01T00:00:00+05:00"),
    "an out-of-range start": lambda e: removal(e)["old"].update(
        start="9999-12-31T23:00:00-05:00"
    ),
    "seen not a bool": lambda e: e.update(seen="no"),
    "changes not a list": lambda e: e.update(changes={}),
    "an unknown kind": lambda e: removal(e).update(kind="cancelled"),
    "an id not a string": lambda e: removal(e).update(id=51),
    "a removal with a new side": lambda e: removal(e).update(new=removal(e)["old"]),
    "an addition with an old side": lambda e: change_of(e, "added").update(
        old=removal(e)["old"]
    ),
    "a room change without a side": lambda e: change_of(e, "room").update(new=None),
    "a listing with no title": lambda e: removal(e)["old"].pop("title"),
    "a listing not an object": lambda e: removal(e).update(old=[1]),
}
"""Ways a batch's JSON can be wrong, each applied to one batch of three."""


@pytest.mark.parametrize("edit", BREAKS.values(), ids=BREAKS.keys())
def test_a_malformed_batch_is_skipped_with_a_log_and_the_others_kept(
    edit: Any, caplog: pytest.LogCaptureFixture
) -> None:
    """A batch not as the app writes it is skipped and logged; the others are read."""
    entries = broken(edit)
    with caplog.at_level(logging.WARNING):
        decoded = decode_batches(json.dumps(entries).encode(), ZONES[2026])
    assert [b.detected_at for b in decoded] == [NOW, NOW - timedelta(hours=2)]
    assert "Skipped change batch 1 of the log" in caplog.text


def test_an_entry_that_is_not_an_object_is_skipped() -> None:
    """A list item that is not an object (a string, a number) is skipped alone."""
    entries: list[Any] = [*stored(encode_batches([batch(2026)])), "x", 3]
    assert len(decode_batches(json.dumps(entries).encode(), UTC)) == 1


def test_a_decoded_removal_still_has_its_last_listing() -> None:
    """A removed session read back keeps its last title, time and room (D-255)."""
    [decoded] = decode_batches(encode_batches([batch(2026)]), ZONES[2026])
    [removal] = [c for c in decoded.changes if c.kind is ChangeKind.REMOVED]
    assert removal.id == "51" and removal.new is None
    assert removal.latest == removal.old


# ------------------------------------------------------------------ trim


def test_trim_keeps_exactly_fourteen_days() -> None:
    """A batch detected exactly 14 days ago is kept; a microsecond older goes."""
    kept = batch(2026, at=NOW - timedelta(days=14))
    gone = batch(2026, at=NOW - timedelta(days=14, microseconds=1))
    recent = batch(2026, at=NOW - timedelta(minutes=5))
    assert trim([recent, kept, gone], NOW) == [recent, kept]


def test_trim_keeps_the_order_and_a_batch_from_the_future() -> None:
    """Trimming keeps the given order, and a batch after ``now`` (a clock set back)."""
    later = batch(2026, at=NOW + timedelta(days=2))
    older = batch(2026, at=NOW - timedelta(days=13))
    assert trim([older, later], NOW) == [older, later]
    assert trim([], NOW) == []


def test_trim_compares_instants_across_zones() -> None:
    """A batch's age is its instant's: a detection time in another zone counts the same."""
    pacific = (NOW - KEPT_FOR).astimezone(ZONES[2026])
    assert trim([batch(2026, at=pacific)], NOW) == [batch(2026, at=pacific)]


def test_a_batch_is_unseen_unless_marked() -> None:
    """A new batch is unseen; marking it seen is a new frozen batch."""
    fresh = Batch(detected_at=NOW, changes=())
    assert fresh.seen is False
    assert replace(fresh, seen=True).seen is True
