"""Tests for the ``ChangeLog`` store: what a refresh that publishes records (D-47, D-255).

Each case runs a real ``Conference`` refresh over an ``httpx.MockTransport`` that serves a
copy of the recorded 2026 feed, or of the bundled snapshot, with named edits
(``tests/feeds.py``); the log and the cache live in a temporary directory, and
SharedPreferences is the in-memory fake.
"""

import asyncio
import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import flet as ft
import httpx
import pytest

from pycon_us import clock
from pycon_us.change_log import RECENT_FOR, ChangeLog
from pycon_us.config import YearData, load_year
from pycon_us.core.change_batches import Batch
from pycon_us.core.diff import Change, ChangeKind, Listing
from pycon_us.favorites import Favorites
from pycon_us.services import changes_file
from pycon_us.services.storage import Pref, Storage, fetched
from pycon_us.state import Conference
from tests.fakes import MemoryPrefs
from tests.feeds import Edit, add, changed, move, recorded, remove, rename, slot

NOW = datetime(2026, 10, 12, 9, 30, tzinfo=UTC)
TALK = 142  # a 2026 talk, in the recorded feed and in the snapshot
OTHER = 51  # another talk, never saved here
TEST_URL = "https://example.test/conference.json"


@pytest.fixture(autouse=True)
def frozen_clock() -> Iterator[None]:
    """Freeze ``clock.now()`` at ``NOW`` for the test, then return to real time."""
    clock.set_test_now(NOW)
    yield
    clock.set_test_now(None)


@pytest.fixture(scope="module")
def year() -> YearData:
    """The 2026 year data, loaded once for the module."""
    return load_year(2026)


@pytest.fixture
def storage(tmp_path: Path) -> Storage:
    """A 2026 ``Storage`` in ``tmp_path``, over in-memory SharedPreferences."""
    return Storage(prefs=MemoryPrefs(), directory=tmp_path, year=2026)


def serving(body: bytes) -> httpx.MockTransport:
    """A transport that answers any feed URL with ``body``."""
    return httpx.MockTransport(lambda request: httpx.Response(200, content=body))


def snapshot_with(year: YearData, *edits: Edit) -> bytes:
    """The bundled 2026 snapshot with ``edits`` applied to a fresh copy of its JSON."""
    doc = json.loads(year.read_snapshot().raw)
    for edit in edits:
        edit(doc)
    return json.dumps(doc).encode()


async def started(
    storage: Storage, year: YearData, saved: frozenset[str] = frozenset()
) -> tuple[Conference, ChangeLog]:
    """Return the stores after a start, as ``bootstrap()`` loads them, with ``saved``."""
    favorites = Favorites(ids=saved)
    log = ChangeLog(_favorites=favorites)
    await log.load(storage, year.conference.zone)
    conference = Conference(_change_log=log)
    await conference.load_local(storage, year)
    return conference, log


def log_file(storage: Storage) -> Path:
    """The year's change log file."""
    return changes_file.changes_path(storage)


async def marker(storage: Storage) -> bool:
    """Return the stored ``pycon.2026.fetched``."""
    return await storage.get(fetched(2026))


# ------------------------------------------------------------------ over the cache


async def test_a_new_feed_over_the_cache_records_one_batch_and_writes_it(
    storage: Storage, year: YearData
) -> None:
    """A move over the cache is one batch, newest first, in memory and on file."""
    await storage.write_feed(recorded(2026))
    conference, log = await started(storage, year)

    await conference.refresh(
        storage, year, transport=serving(changed(2026, move(TALK, "Room 101B")))
    )

    [batch] = log.batches
    assert batch.detected_at == NOW
    assert [(c.id, c.kind) for c in batch.changes] == [(str(TALK), ChangeKind.ROOM)]
    assert log_file(storage).exists()
    assert await marker(storage) is True


async def test_a_relaunch_reads_the_batches_back(
    storage: Storage, year: YearData
) -> None:
    """The next start's log holds the batches the last session recorded."""
    await storage.write_feed(recorded(2026))
    conference, log = await started(storage, year)
    await conference.refresh(
        storage, year, transport=serving(changed(2026, rename(TALK, "Renamed")))
    )

    _, relaunched = await started(storage, year)

    assert relaunched.batches == log.batches
    assert len(relaunched.batches) == 1


async def test_batches_are_kept_newest_first(storage: Storage, year: YearData) -> None:
    """A second batch goes before the first."""
    await storage.write_feed(recorded(2026))
    conference, log = await started(storage, year)
    first = changed(2026, move(TALK, "Room 101B"))
    await conference.refresh(storage, year, transport=serving(first))
    clock.set_test_now(NOW + timedelta(hours=1))
    second = changed(2026, rename(TALK, "Renamed"))
    await conference.refresh(storage, year, transport=serving(second))

    assert [b.detected_at for b in log.batches] == [NOW + timedelta(hours=1), NOW]


async def test_the_store_notifies_once_per_batch(
    storage: Storage, year: YearData
) -> None:
    """A recorded batch is one notification, with the batch to announce already set."""
    await storage.write_feed(recorded(2026))
    conference, log = await started(storage, year)
    seen: list[object] = []

    def keep(_sender: object, _field: str | None) -> None:
        """Take the batch to announce, as the SnackBar will on the notification."""
        seen.append(log.take_announcement())

    assert isinstance(log, ft.Observable)
    log.subscribe(keep)

    await conference.refresh(
        storage, year, transport=serving(changed(2026, move(TALK, "Room 101B")))
    )

    assert seen == [log.batches[0]]
    assert log.take_announcement() is None  # taken once


async def test_a_batch_of_additions_only_is_recorded_but_not_announced(
    storage: Storage, year: YearData
) -> None:
    """Additions are listed in a batch, but alone they announce nothing (D-255)."""
    await storage.write_feed(recorded(2026))
    conference, log = await started(storage, year)

    edit = add(5000, like=TALK, name="A late addition")
    await conference.refresh(storage, year, transport=serving(changed(2026, edit)))

    [batch] = log.batches
    assert [c.kind for c in batch.changes] == [ChangeKind.ADDED]
    assert log.take_announcement() is None


async def test_the_same_bytes_record_nothing(storage: Storage, year: YearData) -> None:
    """A refresh that brings the published feed again publishes and records nothing."""
    await storage.write_feed(recorded(2026))
    conference, log = await started(storage, year)

    await conference.refresh(storage, year, transport=serving(recorded(2026)))

    assert log.batches == ()
    assert not log_file(storage).exists()


async def test_a_failed_refresh_records_nothing(
    storage: Storage, year: YearData
) -> None:
    """A refresh whose answer is unusable records nothing."""
    await storage.write_feed(recorded(2026))
    conference, log = await started(storage, year)

    broken = httpx.MockTransport(lambda request: httpx.Response(500))
    await conference.refresh(storage, year, transport=broken)

    assert conference.problem == "server"
    assert log.batches == ()
    assert not log_file(storage).exists()


async def test_a_refresh_of_a_closed_session_records_nothing(
    storage: Storage, year: YearData
) -> None:
    """A refresh that ends after its session closed writes nothing, the log included."""
    await storage.write_feed(recorded(2026))
    conference, log = await started(storage, year)
    closed = asyncio.Event()
    closed.set()

    feed = changed(2026, move(TALK, "Room 101B"))
    await conference.refresh(storage, year, transport=serving(feed), closed=closed)

    assert log.batches == ()
    assert not log_file(storage).exists()


async def test_the_diff_time_and_count_are_logged(
    storage: Storage, year: YearData, caplog: pytest.LogCaptureFixture
) -> None:
    """The diff logs how long it took and how many changes it found."""
    await storage.write_feed(recorded(2026))
    conference, _ = await started(storage, year)

    with caplog.at_level(logging.INFO, logger="pycon_us.change_log"):
        await conference.refresh(
            storage, year, transport=serving(changed(2026, move(TALK, "Room 101B")))
        )

    assert any(
        m.startswith("Feeds diffed in ") and m.endswith(" ms: 1 changes")
        for m in caplog.messages
    )


# ------------------------------------------------------------------ feed URLs


async def test_a_feed_from_another_feed_url_is_not_diffed(
    storage: Storage, year: YearData
) -> None:
    """After a feed URL change, the next refresh publishes without a diff (D-255)."""
    await storage.write_feed(recorded(2026))
    conference, log = await started(storage, year)
    await conference.set_feed_url(TEST_URL, storage)

    feed = changed(2026, move(TALK, "Room 101B"))
    await conference.refresh(storage, year, transport=serving(feed))

    assert conference.source == "network"
    assert log.batches == ()
    # ...and the next one, from the same URL, is diffed again.
    again = changed(2026, move(TALK, "Room 101C"))
    await conference.refresh(storage, year, transport=serving(again))
    assert len(log.batches) == 1


async def test_a_new_feed_urls_same_bytes_count_as_its_feed_for_the_next_diff(
    storage: Storage, year: YearData
) -> None:
    """A new feed URL's first refresh that brings the feed shown makes it that URL's.

    It publishes nothing (D-224), but the next feed from that URL is diffed against
    it, as after a first refresh that publishes (D-255): a feed pair whose old side is
    the feed already shown keeps its change (#460).
    """
    await storage.write_feed(recorded(2026))
    conference, log = await started(storage, year)
    await conference.set_feed_url(TEST_URL, storage)

    await conference.refresh(storage, year, transport=serving(recorded(2026)))
    assert log.batches == ()
    feed = changed(2026, move(TALK, "Room 101B"))
    await conference.refresh(storage, year, transport=serving(feed))

    assert [change.kind for change in log.batches[0].changes] == [ChangeKind.ROOM]


async def test_a_feed_url_change_forgets_the_batches_in_memory(
    storage: Storage, year: YearData
) -> None:
    """The log deleted with the old URL's cache is gone from memory too (D-255)."""
    await storage.write_feed(recorded(2026))
    conference, log = await started(storage, year)
    feed = changed(2026, move(TALK, "Room 101B"))
    await conference.refresh(storage, year, transport=serving(feed))

    await conference.set_feed_url(TEST_URL, storage)

    assert log.batches == ()
    assert not log_file(storage).exists()


async def test_a_url_left_between_the_publish_and_the_log_write_records_nothing(
    storage: Storage, year: YearData, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A URL left during the hand-off's last await records nothing, though it published."""
    await storage.write_feed(recorded(2026))
    conference, log = await started(storage, year)
    save = Storage.set

    async def leave_then_save(self: Storage, pref: Pref[bool], value: bool) -> bool:
        """Leave the feed URL, then save: the marker's save, the hand-off's last await."""
        await conference.set_feed_url(TEST_URL, storage)
        return await save(self, pref, value)

    monkeypatch.setattr(Storage, "set", leave_then_save)
    feed = changed(2026, move(TALK, "Room 101B"))
    await conference.refresh(storage, year, transport=serving(feed))

    assert conference.source == "network"
    assert log.batches == ()
    assert not log_file(storage).exists()


async def test_a_session_closed_between_the_publish_and_the_log_write_records_nothing(
    storage: Storage, year: YearData, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A session closed during the hand-off's last await records nothing (F30)."""
    await storage.write_feed(recorded(2026))
    conference, log = await started(storage, year)
    closed = asyncio.Event()
    save = Storage.set

    async def close_then_save(self: Storage, pref: Pref[bool], value: bool) -> bool:
        """Close the session, then save: the marker's save, the hand-off's last await."""
        closed.set()
        return await save(self, pref, value)

    monkeypatch.setattr(Storage, "set", close_then_save)
    feed = changed(2026, move(TALK, "Room 101B"))
    await conference.refresh(storage, year, transport=serving(feed), closed=closed)

    assert log.batches == ()
    assert not log_file(storage).exists()


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
