"""Tests for the ``ChangeLog`` store over the bundled snapshot, and ``recent()`` (D-47).

Before the first fetch, only saved sessions are diffed against the snapshot, without
additions (D-255); then what ``recent()`` and ``recent_of()`` say for the last 24 hours.
Each case runs a real ``Conference`` refresh with the fixtures and helpers of
``tests/change_log_feeds.py``; what a refresh over the cache records, and feed URLs, are
in ``test_change_log.py``.
"""

import json
from datetime import UTC, datetime, timedelta

import pytest

from pycon_us import clock
from pycon_us.change_log import RECENT_FOR, ChangeLog
from pycon_us.config import YearData
from pycon_us.core.change_batches import Batch
from pycon_us.core.diff import Change, ChangeKind, Listing
from pycon_us.favorites import Favorites
from pycon_us.services import changes_file
from pycon_us.services.storage import Storage
from pycon_us.state import Conference
from tests import change_log_feeds
from tests.change_log_feeds import (
    NOW,
    OTHER,
    TALK,
    TEST_URL,
    log_file,
    marker,
    serving,
    snapshot_with,
    started,
)
from tests.feeds import add, changed, move, recorded, remove, rename, slot

# The harness's fixtures, under this module's names, where pytest looks them up.
frozen_clock, year, storage = (
    change_log_feeds.frozen_clock,
    change_log_feeds.year,
    change_log_feeds.storage,
)


# ------------------------------------------------------------------ over the snapshot


async def test_over_the_snapshot_nothing_saved_means_no_diff(
    storage: Storage, year: YearData
) -> None:
    """A first install with nothing saved records nothing, and saves the marker."""
    conference, log = await started(storage, year)

    feed = snapshot_with(year, move(TALK, "Room 101B"))
    await conference.refresh(storage, year, transport=serving(feed))

    assert conference.source == "network"
    assert log.batches == ()
    assert await marker(storage) is True


async def test_over_the_snapshot_only_saved_sessions_are_diffed_without_additions(
    storage: Storage, year: YearData
) -> None:
    """Before the marker, the batch holds the saved sessions' changes, no addition."""
    conference, log = await started(storage, year, saved=frozenset({str(TALK)}))

    feed = snapshot_with(
        year,
        move(TALK, "Room 101B"),
        move(OTHER, "Room 101B"),
        add(5000, like=TALK, name="A late addition"),
    )
    await conference.refresh(storage, year, transport=serving(feed))

    [batch] = log.batches
    assert [(c.id, c.kind) for c in batch.changes] == [(str(TALK), ChangeKind.ROOM)]


async def test_over_the_snapshot_a_saved_removal_is_recorded(
    storage: Storage, year: YearData
) -> None:
    """A saved session the feed dropped is listed with its last values (D-255)."""
    conference, log = await started(storage, year, saved=frozenset({str(TALK)}))

    await conference.refresh(
        storage, year, transport=serving(snapshot_with(year, remove(TALK)))
    )

    [batch] = log.batches
    [change] = batch.changes
    assert change.kind is ChangeKind.REMOVED
    assert change.old is not None


@pytest.mark.parametrize("why", ["clear cached feed", "corrupt cache", "url change"])
async def test_over_the_snapshot_once_fetched_nothing_is_diffed(
    storage: Storage, year: YearData, why: str
) -> None:
    """A start back on the snapshot after a network feed records nothing (D-255)."""
    await storage.write_feed(recorded(2026))
    conference, _ = await started(storage, year, saved=frozenset({str(TALK)}))
    await conference.refresh(storage, year, transport=serving(recorded(2026) + b" "))
    assert await marker(storage) is True
    if why == "clear cached feed":
        await storage.delete_feed("Clear cached feed (Developer)")
    elif why == "corrupt cache":
        storage.feed_path.write_bytes(b"{not json")
    else:
        await conference.set_feed_url(TEST_URL, storage)
        await conference.set_feed_url(None, storage)

    relaunched, log = await started(storage, year, saved=frozenset({str(TALK)}))
    assert relaunched.source == "bundled"
    feed = snapshot_with(year, move(TALK, "Room 101B"))
    await relaunched.refresh(storage, year, transport=serving(feed))

    assert relaunched.source == "network"
    assert log.batches == ()
    assert not log_file(storage).exists()


async def test_over_the_snapshot_a_developer_feed_url_is_not_diffed(
    storage: Storage, year: YearData
) -> None:
    """The snapshot counts as the year's feed URL's, so a test URL's feed is not diffed."""
    log = ChangeLog(_favorites=Favorites(ids=frozenset({str(TALK)})))
    await log.load(storage, year.conference.zone)
    conference = Conference(_change_log=log)
    await conference.set_feed_url(TEST_URL, storage)  # restored before the load
    await conference.load_local(storage, year)

    feed = snapshot_with(year, move(TALK, "Room 101B"))
    await conference.refresh(storage, year, transport=serving(feed))

    assert log.batches == ()


async def test_reset_app_clears_the_marker_and_the_log(
    storage: Storage, year: YearData
) -> None:
    """After Reset app the snapshot is diffed again for saved sessions (D-198, D-255)."""
    await storage.write_feed(recorded(2026))
    conference, log = await started(storage, year, saved=frozenset({str(TALK)}))
    feed = changed(2026, move(TALK, "Room 101B"))
    await conference.refresh(storage, year, transport=serving(feed))
    assert log.batches

    await storage.clear_prefs()
    await conference.reset(storage, year)
    await changes_file.delete_batches(storage, "Reset app")

    assert log.batches == ()
    assert await marker(storage) is False
    feed = snapshot_with(year, move(TALK, "Room 101C"))
    await conference.refresh(storage, year, transport=serving(feed))
    assert len(log.batches) == 1


# ------------------------------------------------------------------ recent


async def test_recent_badges_a_change_for_24_hours_after_its_detection(
    storage: Storage, year: YearData
) -> None:
    """A room change badges its session until 24 h after detection, then not."""
    await storage.write_feed(recorded(2026))
    conference, log = await started(storage, year)
    feed = changed(2026, move(TALK, "Room 101B"))
    await conference.refresh(storage, year, transport=serving(feed))

    assert str(TALK) in log.recent(NOW + RECENT_FOR - timedelta(seconds=1))
    assert log.recent(NOW + RECENT_FOR) == {}


async def test_recent_badges_neither_additions_nor_removals(
    storage: Storage, year: YearData
) -> None:
    """Only time, room and title changes badge a row (D-255)."""
    await storage.write_feed(recorded(2026))
    conference, log = await started(storage, year)
    edits = (add(5000, like=TALK, name="A late addition"), remove(OTHER))
    doc = json.loads(recorded(2026))
    for edit in edits:
        edit(doc)
    await conference.refresh(storage, year, transport=serving(json.dumps(doc).encode()))

    assert {c.kind for c in log.batches[0].changes} == {
        ChangeKind.ADDED,
        ChangeKind.REMOVED,
    }
    assert log.recent(NOW) == {}


async def test_recent_joins_the_kinds_of_every_batch_of_the_last_24_hours(
    storage: Storage, year: YearData
) -> None:
    """A session moved, then renamed an hour later, is badged with both kinds."""
    await storage.write_feed(recorded(2026))
    conference, log = await started(storage, year)
    await conference.refresh(
        storage, year, transport=serving(changed(2026, move(TALK, "Room 101B")))
    )
    clock.set_test_now(NOW + timedelta(hours=1))
    doc = json.loads(changed(2026, move(TALK, "Room 101B")))
    rename(TALK, "Python for Humans, again")(doc)
    await conference.refresh(storage, year, transport=serving(json.dumps(doc).encode()))

    assert log.recent(NOW + timedelta(hours=1)) == {
        str(TALK): {ChangeKind.ROOM, ChangeKind.TITLE}
    }
    # A minute past the first batch's 24 h, only the rename is left.
    later = NOW + RECENT_FOR + timedelta(minutes=1)
    assert log.recent(later) == {str(TALK): {ChangeKind.TITLE}}


def room_batch(detected: datetime, old: str, new: str, key: str = "142") -> Batch:
    """A batch moving session ``key`` from room ``old`` to room ``new``."""
    start = datetime(2026, 5, 16, 17, 30, tzinfo=UTC)
    end = start + timedelta(minutes=30)
    before, after = (Listing("Talk", start, end, room) for room in (old, new))
    return Batch(detected, (Change(key, ChangeKind.ROOM, before, after),))


def test_recent_of_spans_the_last_24_hours_from_the_oldest_old_value() -> None:
    """Moved twice in 24 h, a session says the room before the first move (ux.md §5.5)."""
    log = ChangeLog(
        batches=(
            room_batch(NOW, "Room 102B", "Room 103C"),
            room_batch(NOW - timedelta(hours=2), "Room 102A", "Room 102B"),
            room_batch(NOW - RECENT_FOR, "Room 101", "Room 102A"),  # too old
        )
    )
    (moved,) = log.recent_of("142", NOW)
    assert moved.old is not None and moved.new is not None
    assert (moved.old.location, moved.new.location) == ("Room 102A", "Room 103C")
    assert log.recent_of("51", NOW) == ()  # another session: nothing


def test_recent_of_leaves_out_a_value_that_came_back() -> None:
    """Moved, then moved back within 24 h: "Moved from" its own room would mislead."""
    log = ChangeLog(
        batches=(
            room_batch(NOW, "Room 102B", "Room 102A"),
            room_batch(NOW - timedelta(hours=1), "Room 102A", "Room 102B"),
        )
    )
    assert log.recent_of("142", NOW) == ()


def test_the_fixture_talks_exist_in_the_snapshot(year: YearData) -> None:
    """The talks these cases edit are in the bundled snapshot, so the edits apply."""
    doc = json.loads(year.read_snapshot().raw)
    assert slot(doc, TALK) and slot(doc, OTHER)
