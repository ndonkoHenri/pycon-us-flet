"""What an install that ran 2026 finds when an update makes 2027 the year (D-48, D-466).

Rehearsed for #842: a 2026 install's preferences, files and staff data, then a real
`bootstrap()` as 2027 over them. The 2027 is 2026's data a year on, with the same
session ids, so a mix-up would show: a 2026 id names a real 2027 session.
"""

import json
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import cast

import flet as ft
import pytest

from pycon_us import clock
from pycon_us.account import Account
from pycon_us.app import bootstrap
from pycon_us.change_log import ChangeLog
from pycon_us.config import YearData, load_year
from pycon_us.core import outbox, outbox_enqueue
from pycon_us.core.change_batches import Batch
from pycon_us.core.door_sessions import DoorChoice
from pycon_us.core.lead_sponsors import LeadSponsor
from pycon_us.core.outbox import Status
from pycon_us.door_choice import read_door_session, save_door_session
from pycon_us.favorites import Favorites
from pycon_us.memory import ViewMemory
from pycon_us.prefs import Prefs
from pycon_us.services import Services, changes_file
from pycon_us.services.outbox_db import OutboxDb
from pycon_us.services.pref_keys import (
    EXCLUDED_TRACKS,
    STAFF_PREFIX,
    THEME,
    favorites,
    fetched,
    staff_swag_categories,
)
from pycon_us.services.storage import Storage
from pycon_us.staff_sponsor import read_sponsor, save_sponsor
from pycon_us.state import Conference
from tests import app_start
from tests.app_start import Network, finish_refresh
from tests.fake_page import FakePage
from tests.fakes import (
    MemoryClipboard,
    MemoryHaptics,
    MemoryLauncher,
    MemoryPrefs,
    MemorySemantics,
)
from tests.feeds import recorded
from tests.next_year import copy_forward

fake_page, network = app_start.fake_page, app_start.network

SAVED = "142"
"""A session saved in 2026, whose id is also a session of this 2027."""

HIDDEN = ["Open Space", "Sponsor Presentation"]
"""The 2026 install's schedule filter, not the default one."""

OWNER = "staff@example.com"
"""The staff account the scans belong to."""


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """Year folders with 2026 and its 2027, apart from the app's data directory."""
    folder = tmp_path / "data"
    folder.mkdir()
    return copy_forward(folder)


@pytest.fixture
def year_2027(data_dir: Path) -> YearData:
    """The new year's data."""
    return load_year(2027, data_dir)


@pytest.fixture
def shared() -> MemoryPrefs:
    """The install's SharedPreferences, which survive the update."""
    return MemoryPrefs()


@pytest.fixture
def directory(tmp_path: Path) -> Path:
    """The install's durable data directory, which survives the update."""
    folder = tmp_path / "app"
    folder.mkdir()
    return folder


@pytest.fixture
def last_year(shared: MemoryPrefs, directory: Path) -> Storage:
    """The 2026 build's storage, over what the install keeps."""
    return Storage(prefs=shared, directory=directory, year=2026)


@pytest.fixture
def this_year(shared: MemoryPrefs, directory: Path) -> Storage:
    """The 2027 build's storage, over the same preferences and files."""
    return Storage(prefs=shared, directory=directory, year=2027)


@dataclass
class Session:
    """The stores of a 2027 session, empty until `bootstrap()` loads them."""

    conference: Conference = field(default_factory=Conference)
    prefs: Prefs = field(default_factory=Prefs)
    favorites: Favorites = field(default_factory=Favorites)
    change_log: ChangeLog = field(default_factory=ChangeLog)


@pytest.fixture
async def started(
    last_year: Storage,
    this_year: Storage,
    year_2027: YearData,
    fake_page: FakePage,
    network: Network,
) -> Session:
    """Use the install in 2026, then start it as 2027, its first refresh held."""
    assert await last_year.set(THEME, "dark")
    assert await last_year.set(EXCLUDED_TRACKS, HIDDEN)
    assert await last_year.set(favorites(2026), [SAVED])
    assert await last_year.set(fetched(2026), True)
    assert await last_year.write_feed(recorded(2026))
    assert await changes_file.write_batches(last_year, [Batch(clock.now(), ())])

    # A feed that isn't the bundled bytes, so the refresh publishes (D-224).
    document = json.loads(year_2027.read_snapshot().raw)
    document["schedule"][0]["name"] = "Renamed since the snapshot"
    network.answer = json.dumps(document).encode()
    session = Session()
    services = Services(
        year=year_2027,
        storage=this_year,
        memory=ViewMemory(),
        semantics=MemorySemantics(),
        haptics=MemoryHaptics(),
        launcher=MemoryLauncher(),
        clipboard=MemoryClipboard(),
    )
    await bootstrap(
        cast(ft.Page, fake_page),
        services,
        session.conference,
        session.prefs,
        session.favorites,
        session.change_log,
        Account(),
    )
    return session


def test_the_rehearsal_s_2027_is_another_year(year_2027: YearData) -> None:
    """Its feed URL and all its slots are 2027's, or these tests would prove nothing."""
    assert "/2027/" in year_2027.conference.feed_url
    slots = json.loads(year_2027.read_snapshot().raw)["schedule"]
    assert {slot["start"][:4] for slot in slots} == {"2027"}


async def test_the_new_year_opens_on_its_own_snapshot_not_last_year_s_cache(
    started: Session, year_2027: YearData, network: Network
) -> None:
    """The first start shows the bundled 2027 feed: `feed-2026.json` isn't read."""
    data = started.conference.data
    assert started.conference.source == "bundled"
    assert data is not None and data.days[0].date.year == 2027
    assert network.urls == [year_2027.conference.feed_url]


async def test_a_saved_session_of_2026_marks_no_session_of_2027(
    started: Session, last_year: Storage
) -> None:
    """My schedule starts empty though the id exists in 2027, and 2026's list stays."""
    data = started.conference.data
    assert data is not None and SAVED in data.sessions
    assert not started.favorites.ids
    assert await last_year.get(favorites(2026)) == [SAVED]


async def test_the_change_log_and_its_marker_start_again(
    started: Session, this_year: Storage, last_year: Storage
) -> None:
    """2027's log is empty and unmarked; 2026's file and marker aren't touched."""
    assert started.change_log.batches == ()
    assert await this_year.get(fetched(2027)) is False
    assert await last_year.get(fetched(2026)) is True
    assert changes_file.changes_path(last_year).exists()


async def test_the_settings_carry_over(started: Session) -> None:
    """The app-wide settings are the person's, not the year's (decisions §M)."""
    assert started.prefs.theme == "dark"
    assert started.prefs.excluded_tracks == tuple(HIDDEN)


async def test_the_first_refresh_caches_2027_beside_2026_and_logs_no_change(
    started: Session, network: Network, this_year: Storage, last_year: Storage
) -> None:
    """The first feed caches on its own, with no change logged across the years."""
    old_cache = last_year.feed_path.read_bytes()
    await finish_refresh(started.conference, network)
    assert started.conference.source == "network"
    assert this_year.feed_path.read_bytes() == network.answer
    assert await this_year.get(fetched(2027)) is True
    assert started.change_log.batches == ()
    assert last_year.feed_path.read_bytes() == old_cache


async def test_a_staff_choice_of_2026_is_not_2027_s(
    last_year: Storage, this_year: Storage
) -> None:
    """A sponsor's, a session's or a category's id means nothing in the next year."""
    await save_sponsor(last_year, LeadSponsor("7", "Old Sponsor", None, None))
    await save_door_session(last_year, DoorChoice(1, (10,), "Old session", False))
    assert await last_year.set(staff_swag_categories(2026), ["3"])

    assert await read_sponsor(this_year) is None
    assert await read_door_session(this_year) is None
    assert await this_year.get(staff_swag_categories(2027)) == []
    assert await read_sponsor(last_year) is not None


async def test_a_sign_out_removes_every_year_s_staff_choices(
    last_year: Storage, this_year: Storage, shared: MemoryPrefs
) -> None:
    """`STAFF_PREFIX` still covers them, so no old sponsor outlives a sign-out (D-414)."""
    await save_sponsor(last_year, LeadSponsor("7", "Old Sponsor", None, None))
    await save_sponsor(this_year, LeadSponsor("8", "New Sponsor", None, None))
    assert await this_year.clear_prefs(STAFF_PREFIX)
    assert not [key for key in shared.values if key.startswith(STAFF_PREFIX)]


@pytest.fixture
def outboxes(directory: Path) -> Iterator[tuple[OutboxDb, OutboxDb]]:
    """The 2026 build's outbox and the 2027 build's, in one data directory."""
    old, new = OutboxDb(directory, 2026), OutboxDb(directory, 2027)
    yield old, new
    old.close()
    new.close()


def scan(
    db: OutboxDb, code: str, sponsor: tuple[str, str] = ("7", "Old Sponsor")
) -> outbox_enqueue.Enqueued:
    """Enqueue a lead scan of `code` for `OWNER` and `sponsor`, not sent yet."""
    enqueued = db.enqueue(
        code,
        lambda rows: outbox_enqueue.scan_lead(
            rows,
            owner=OWNER,
            code=code,
            payload={"badge_validator": "v"},
            sponsor_id=sponsor[0],
            sponsor_name=sponsor[1],
            now=1.0,
        ),
    )
    assert enqueued is not None and enqueued.row is not None
    return enqueued


def synced(db: OutboxDb, enqueued: outbox_enqueue.Enqueued) -> None:
    """Store a scan's row as sent, as a pass of the worker would."""
    assert enqueued.row is not None
    assert db.save(outbox.after_success(stored(db, enqueued.row.key), {"ok": True}))


def stored(db: OutboxDb, code: str) -> outbox.Row:
    """Return `code`'s only row in `db`, with its id."""
    rows = [row for row in db.rows(OWNER, tuple(Status)) or [] if row.key == code]
    assert len(rows) == 1
    return rows[0]


def test_a_scan_of_2026_is_neither_sent_nor_listed_in_2027(
    outboxes: tuple[OutboxDb, OutboxDb],
) -> None:
    """2026's sponsor would be credited at `/2027/` (D-56): the row stays in its file."""
    old, new = outboxes
    scan(old, "MOCK0001")

    assert new.due_rows(OWNER, 2.0) == []
    assert new.rows(OWNER, tuple(Status)) == []
    counts = new.counts(None)
    assert counts is not None and counts.pending == 0
    assert [row.key for row in old.rows(OWNER, (Status.PENDING,)) or []] == ["MOCK0001"]


def test_the_same_badge_scanned_in_each_year_is_two_rows(
    outboxes: tuple[OutboxDb, OutboxDb],
) -> None:
    """A code seen last year is no duplicate this year: lead dedupe stays in the year."""
    old, new = outboxes
    scan(old, "MOCK0001")
    scan(new, "MOCK0001")
    assert len(old.rows(OWNER, tuple(Status)) or []) == 1
    assert len(new.rows(OWNER, tuple(Status)) or []) == 1


@pytest.mark.parametrize(
    "sponsor", [("7", "Old Sponsor"), ("8", "New Sponsor")], ids=["same", "another"]
)
def test_a_lead_synced_in_2026_is_no_repeat_and_no_other_sponsor_in_2027(
    outboxes: tuple[OutboxDb, OutboxDb], sponsor: tuple[str, str]
) -> None:
    """D-459's key stays in the year: not `ALREADY`, and no "Also in your leads for"."""
    old, new = outboxes
    synced(old, scan(old, "MOCK0001"))
    enqueued = scan(new, "MOCK0001", sponsor)
    assert enqueued.outcome is outbox_enqueue.Outcome.QUEUED
    assert enqueued.others == ()


def test_a_note_in_2027_does_not_follow_a_lead_synced_in_2026(
    outboxes: tuple[OutboxDb, OutboxDb],
) -> None:
    """D-459's note waits for its sponsor's lead, and last year's file doesn't hold it."""
    old, new = outboxes
    synced(old, scan(old, "MOCK0001"))
    noted = new.enqueue(
        "MOCK0001",
        lambda rows: outbox_enqueue.save_note(
            rows,
            owner=OWNER,
            code="MOCK0001",
            note="Hot",
            sponsor_id="7",
            sponsor_name="Old Sponsor",
            now=1.0,
        ),
    )
    assert noted is not None and noted.outcome is outbox_enqueue.Outcome.QUEUED
    assert new.due_rows(OWNER, 2.0) == []


def test_a_lost_answer_in_2026_says_nothing_of_the_same_lead_in_2027(
    outboxes: tuple[OutboxDb, OutboxDb],
) -> None:
    """D-410's flag, which #885 sets on an unreadable 200 too, stays on 2026's row."""
    old, new = outboxes
    scan(old, "MOCK0001")
    row_id = stored(old, "MOCK0001").id
    assert row_id is not None and old.flag_maybe_sent(row_id)
    scan(new, "MOCK0001")
    assert stored(old, "MOCK0001").maybe_sent
    assert not stored(new, "MOCK0001").maybe_sent


async def test_only_other_years_files_go_at_a_reset(
    last_year: Storage, this_year: Storage, directory: Path
) -> None:
    """`delete_other_years()` leaves this year's cache and log, and any other file."""
    await last_year.write_feed(b"{}")
    await changes_file.write_batches(last_year, [Batch(clock.now(), ())])
    await this_year.write_feed(b"{}")
    await changes_file.write_batches(this_year, [Batch(clock.now(), ())])
    (directory / "outbox-2026.db").touch()

    assert await this_year.delete_other_years() is True

    assert sorted(path.name for path in directory.iterdir()) == [
        "changes-2027.json",
        "feed-2027.json",
        "outbox-2026.db",
    ]


async def test_a_reset_that_cannot_list_the_files_does_not_call_them_gone(
    last_year: Storage,
    this_year: Storage,
    directory: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failed listing is a failed deletion, logged: Reset app must not report success."""
    await last_year.write_feed(b"{}")
    feed = directory / "feed-2026.json"
    # A file for a directory: a real failure for any listing, where a mode-000 folder
    # refuses everyone but root.
    assert await replace(this_year, directory=feed).delete_other_years() is False
    assert "Could not list the data directory" in caplog.text
    assert feed.exists()
