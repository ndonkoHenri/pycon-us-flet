"""The outbox's sqlite database (architecture §12.1; D-49, D-56, D-120).

Every test runs over a temporary data directory. The SQL is checked against its Python
twins in ``core/outbox.py`` on random row sets (hypothesis): the due order against
``due()``, the account switch's deletion against ``forget_synced()``.
"""

import contextlib
import logging
import sqlite3
import tempfile
import threading
from collections.abc import Callable, Iterator
from dataclasses import replace
from functools import partial
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pycon_us.config import YEAR
from pycon_us.core import outbox, outbox_enqueue
from pycon_us.core.outbox import Kind, Row, Status
from pycon_us.core.outbox_enqueue import Outcome
from pycon_us.memory import ViewMemory
from pycon_us.services import Services
from pycon_us.services.outbox_db import Counts, OutboxDb
from pycon_us.services.outbox_schema import MIGRATIONS

OWNER = "staff@example.com"
OTHER = "other@example.com"
NOW = 1_000_000.0


@pytest.fixture
def db(tmp_path: Path) -> Iterator[OutboxDb]:
    """Yield an outbox database in an empty data directory, closed afterwards."""
    database = OutboxDb(tmp_path, 2026)
    yield database
    database.close()


def scan(
    db: OutboxDb, code: str = "A1", now: float = NOW
) -> outbox_enqueue.Enqueued | None:
    """Enqueue ``OWNER``'s lead scan of ``code`` for sponsor 7."""
    decide = partial(
        outbox_enqueue.scan_lead,
        owner=OWNER,
        code=code,
        payload={"code": code},
        sponsor_id="7",
        sponsor_name="Acme",
        now=now,
    )
    return db.enqueue(code, decide)


def note(db: OutboxDb, code: str = "A1", text: str = "Met at the booth"):
    """Enqueue ``OWNER``'s note on ``code``'s lead for sponsor 7."""
    decide = partial(
        outbox_enqueue.save_note,
        owner=OWNER,
        code=code,
        note=text,
        sponsor_id="7",
        sponsor_name="Acme",
        now=NOW,
    )
    return db.enqueue(code, decide)


def admit(db: OutboxDb, code: str = "A1", owner: str = OWNER):
    """Enqueue ``owner``'s door check-in of ``code`` for product 3 in session ``s1``."""
    decide = partial(
        outbox_enqueue.admit,
        owner=owner,
        code=code,
        product_ids=[3],
        session="s1",
        payload={"code": code},
        sponsor_id=None,
        sponsor_name=None,
        now=NOW,
    )
    return db.enqueue(code, decide)


@contextlib.contextmanager
def raw(path: Path) -> Iterator[sqlite3.Connection]:
    """Yield a second connection to the file, as another reader would; commit and close."""
    with contextlib.closing(sqlite3.connect(path)) as connection, connection:
        yield connection


def queued(enqueued: outbox_enqueue.Enqueued | None) -> Row:
    """Return the stored row of an enqueue that queued one."""
    assert enqueued is not None and enqueued.outcome is Outcome.QUEUED
    assert enqueued.row is not None and enqueued.row.id is not None
    return enqueued.row


def everything(db: OutboxDb) -> list[Row]:
    """Return every owner's rows of every status, by created_at then id."""
    owners = {OWNER, OTHER, *ROW_OWNERS}
    found = [db.rows(owner, list(Status)) for owner in sorted(owners)]
    return sorted((r for rows in found for r in rows or []), key=lambda r: r.id or 0)


# ------------------------------------------------------------------ opening and migrating


def test_first_use_creates_the_file_in_wal_mode_at_the_latest_version(
    db: OutboxDb,
) -> None:
    """The file appears on first use only, in WAL mode, migrated to every version."""
    assert not db.path.exists()  # built, not opened (D-51: unused without a mock)
    assert db.counts(OWNER) == Counts()
    with raw(db.path) as other:
        assert other.execute("PRAGMA journal_mode").fetchone() == ("wal",)
        assert other.execute("PRAGMA user_version").fetchone() == (len(MIGRATIONS),)
        indexes = {name for (name,) in other.execute("SELECT name FROM sqlite_master")}
    assert {"outbox", "outbox_due", "outbox_key", "outbox_idem"} <= indexes


def test_an_empty_file_is_migrated(tmp_path: Path) -> None:
    """A zero-byte outbox file (an interrupted first open) is migrated, not refused."""
    (tmp_path / "outbox-2026.db").touch()
    database = OutboxDb(tmp_path, 2026)
    assert queued(scan(database)).key == "A1"
    database.close()


def test_rows_survive_close_and_reopen_without_migrating_again(tmp_path: Path) -> None:
    """A re-open keeps the rows and the version: the migration is idempotent."""
    first = OutboxDb(tmp_path, 2026)
    row = queued(scan(first))
    first.close()
    second = OutboxDb(tmp_path, 2026)
    assert second.rows(OWNER, [Status.PENDING]) == [row]
    with raw(second.path) as other:
        assert other.execute("PRAGMA user_version").fetchone() == (len(MIGRATIONS),)
    second.close()


def test_a_version_1_file_gains_the_flag_with_its_rows_unflagged(
    tmp_path: Path,
) -> None:
    """``OUTBOX_V2`` adds ``maybe_sent`` to a v1 file, its rows unflagged (D-410)."""
    with raw(tmp_path / "outbox-2026.db") as v1:
        v1.executescript(f"{MIGRATIONS[0]}PRAGMA user_version = 1;")
        v1.execute(
            "INSERT INTO outbox (kind, key, payload_json, owner, next_at, created_at)"
            " VALUES ('lead', 'A1', '{}', ?, ?, ?)",
            (OWNER, NOW, NOW),
        )
    database = OutboxDb(tmp_path, 2026)
    (row,) = database.rows(OWNER, [Status.PENDING]) or []
    assert (row.key, row.maybe_sent) == ("A1", False)
    flagged = outbox.after_network_error(row, NOW, maybe_sent=True)
    assert database.save(flagged)
    assert database.rows(OWNER, [Status.PENDING]) == [flagged]
    database.close()


def test_the_connection_refuses_any_thread_but_the_one_that_opened_it(
    db: OutboxDb,
) -> None:
    """Every use is on the loop thread: sqlite's ``check_same_thread`` raises otherwise."""
    db.counts(OWNER)  # opened here, on the test's (the loop's) thread
    errors: list[BaseException] = []

    def elsewhere() -> None:
        """Count from another thread, as ``to_thread`` would, and keep the error."""
        try:
            db.counts(OWNER)
        except sqlite3.ProgrammingError as error:
            errors.append(error)

    thread = threading.Thread(target=elsewhere)
    thread.start()
    thread.join()
    assert len(errors) == 1


def test_a_file_that_cannot_be_opened_is_logged_and_returned(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """An open failure returns "nothing stored" for the caller to say, not an error."""
    database = OutboxDb(tmp_path / "missing", 2026)
    with caplog.at_level(logging.WARNING):
        assert scan(database) is None
        assert database.counts(OWNER) is None
        assert database.due_rows(OWNER, NOW) == []
    assert "Could not enqueue in the outbox" in caplog.text


def test_a_write_after_close_is_refused_not_raised(
    db: OutboxDb, caplog: pytest.LogCaptureFixture
) -> None:
    """A replaced session's late write is logged and returned (D-120)."""
    row = queued(scan(db))
    db.close()
    with caplog.at_level(logging.WARNING):
        assert scan(db) is None
        assert not db.save(replace(row, tries=1))
        assert not db.clear()
        assert db.rows(OWNER, [Status.PENDING]) is None
    assert "Outbox closed; refused to enqueue" in caplog.text


# ------------------------------------------------------------------ enqueue and save


def test_enqueue_stores_what_the_rules_decide(db: OutboxDb) -> None:
    """A new scan is inserted; a repeat is saved over it; a synced lead is already in."""
    first = queued(scan(db, now=NOW))
    again = scan(db, now=NOW + 5)
    assert again is not None and again.outcome is Outcome.UPDATED
    stored = replace(first, next_at=NOW + 5)  # due now: no new revision (D-57)
    assert again.row == stored
    assert db.rows(OWNER, [Status.PENDING]) == [stored]
    assert db.save(outbox.after_success(stored, {"ok": 1}))
    already = scan(db)
    assert already is not None and already.outcome is Outcome.ALREADY
    assert db.counts(OWNER) == Counts(synced=1)


def test_a_door_check_in_is_stored_once_per_idempotency_key(db: OutboxDb) -> None:
    """The same check-in, from any owner, is the queued row; the index forbids a copy."""
    row = queued(admit(db))
    again = admit(db, owner=OTHER)
    assert again == outbox_enqueue.Enqueued(Outcome.ALREADY, row)
    with raw(db.path) as other, pytest.raises(sqlite3.IntegrityError):
        other.execute(
            "INSERT INTO outbox (kind, key, payload_json, owner, next_at, created_at,"
            " idem_key) VALUES ('door', 'A1', '{}', ?, 0, 0, ?)",
            (OTHER, row.idem_key),
        )


def test_a_note_is_never_due_before_its_lead_is_synced(db: OutboxDb) -> None:
    """The lead goes first; its note waits until the lead is synced."""
    lead = queued(scan(db))
    text = queued(note(db))
    assert db.due_rows(OWNER, NOW) == [lead]
    refused = outbox.after_error(lead, "Bad badge", NOW)
    assert db.save(refused)
    assert db.due_rows(OWNER, NOW + outbox.NETWORK_BACKOFF) == [refused]
    synced = outbox.after_success(refused, {"id": 1})
    assert db.save(synced)
    assert db.due_rows(OWNER, NOW) == [text]


@pytest.mark.parametrize(
    "outcome",
    [
        lambda row: outbox.after_success(row, {"id": 1}),
        lambda row: outbox.after_network_error(row, NOW),
        lambda row: outbox.after_error(row, "Bad note", NOW),
    ],
    ids=["success", "network error", "api error"],
)
def test_a_note_edited_while_sent_keeps_the_edit(
    db: OutboxDb, outcome: Callable[[Row], Row]
) -> None:
    """A send's outcome never overwrites a note edited after it was read (D-56)."""
    lead = queued(scan(db))
    assert db.save(outbox.after_success(lead, {"id": 1}))
    queued(note(db, text="First"))
    (sent,) = db.due_rows(OWNER, NOW)  # the worker reads the note and sends it ...
    edited = note(db, text="Second")  # ... while the user saves a new text
    assert edited is not None and edited.row is not None
    assert edited.outcome is Outcome.UPDATED
    assert not db.save(outcome(sent))  # the old send's outcome is dropped
    assert db.due_rows(OWNER, NOW) == [edited.row]  # the edit is sent next
    assert edited.row.payload["note"] == "Second"


def test_the_flag_outlives_an_edit_while_sent_and_a_later_save(db: OutboxDb) -> None:
    """``flag_maybe_sent`` ignores the revision, and no later save clears it (D-410)."""
    lead = queued(scan(db))
    assert db.save(outbox.after_success(lead, {"id": 1}))
    queued(note(db, text="First"))
    (sent,) = db.due_rows(OWNER, NOW)  # the worker reads the note and sends it ...
    edit = note(db, text="Second")  # ... while it is edited: a new revision
    assert edit is not None and edit.row is not None
    edited = edit.row
    assert not db.save(outbox.after_network_error(sent, NOW, maybe_sent=True))
    assert sent.id is not None and db.flag_maybe_sent(sent.id)
    (stored,) = db.due_rows(OWNER, NOW)
    assert (stored.revision, stored.maybe_sent) == (edited.revision, True)
    assert db.save(outbox.after_success(edited, {"id": 1}))  # read unflagged
    assert [row.maybe_sent for row in everything(db)] == [False, True]


def test_a_decision_for_another_code_is_a_bug_and_stores_nothing(db: OutboxDb) -> None:
    """``enqueue`` refuses a row whose code isn't the one its rows were read for."""
    decide = partial(
        outbox_enqueue.scan_lead,
        owner=OWNER,
        code="B2",
        payload={},
        sponsor_id=None,
        sponsor_name=None,
        now=NOW,
    )
    with pytest.raises(ValueError, match="not 'A1'"):
        db.enqueue("A1", decide)
    assert db.counts(OWNER) == Counts()


def test_saving_a_row_never_stored_is_a_bug(db: OutboxDb) -> None:
    """Only stored rows are saved: a row without an id raises."""
    row = Row(Kind.LEAD, "A1", {}, OWNER, None, None, NOW, NOW)
    with pytest.raises(ValueError, match="only once it is stored"):
        db.save(row)


# ------------------------------------------------------------------ counts, lists, clearing


def test_counts_lists_and_owners_cover_each_status(db: OutboxDb) -> None:
    """Counts, the queue sheet's lists and the owners with unsynced rows agree."""
    lead = queued(scan(db, "A1"))
    other = queued(scan(db, "B2", now=NOW + 1))
    failed = lead
    for _ in range(outbox.RETRY_CAP):
        failed = outbox.after_error(failed, "No", NOW)
    assert db.save(failed)
    queued(admit(db, "C3", owner=OTHER))
    assert db.counts(OWNER) == Counts(pending=1, failed=1)
    assert db.rows(OWNER, [Status.FAILED]) == [failed]
    assert db.rows(OWNER, [Status.PENDING, Status.FAILED]) == [failed, other]
    assert db.owners_with_unsynced() == [OTHER, OWNER]
    assert db.clear(OWNER)
    assert db.owners_with_unsynced() == [OTHER]
    assert db.clear()
    assert db.owners_with_unsynced() == []


def test_delete_synced_keeps_pending_and_failed_rows(db: OutboxDb) -> None:
    """An account switch drops the synced rows only, and no other owner's."""
    synced = queued(scan(db, "A1"))
    assert db.save(outbox.after_success(synced, {}))
    pending = queued(scan(db, "B2"))
    theirs = queued(admit(db, "C3", owner=OTHER))
    assert db.save(outbox.after_success(theirs, {}))
    assert db.delete_synced(OWNER)
    assert db.rows(OWNER, list(Status)) == [pending]
    assert db.counts(OTHER) == Counts(synced=1)


# ------------------------------------------------------------------ the SQL against its twins

ROW_OWNERS = ("a@example.com", "b@example.com")
TIMES = st.integers(0, 4).map(float)  # few values, so ties and "due now" happen often

ROWS = st.lists(
    st.builds(
        Row,
        kind=st.sampled_from(Kind),
        key=st.sampled_from(("A1", "B2", "C3")),
        payload=st.just({}),
        owner=st.sampled_from(ROW_OWNERS),
        sponsor_id=st.sampled_from((None, "1", "2")),
        sponsor_name=st.none(),
        next_at=TIMES,
        created_at=TIMES,
        status=st.sampled_from(Status),
        tries=st.integers(0, outbox.RETRY_CAP),
    ),
    max_size=12,
)


@contextlib.contextmanager
def stored_rows(rows: list[Row]) -> Iterator[OutboxDb]:
    """Yield a fresh database holding ``rows``, door rows with unique idempotency keys."""
    insert = (
        "INSERT INTO outbox (kind, key, payload_json, owner, sponsor_id, status,"
        " tries, next_at, created_at, idem_key)"
        " VALUES (?, ?, '{}', ?, ?, ?, ?, ?, ?, ?)"
    )
    with tempfile.TemporaryDirectory() as directory:
        database = OutboxDb(Path(directory), 2026)
        assert database.clear()  # opens and migrates
        with raw(database.path) as other:
            for index, r in enumerate(rows):
                idem_key = f"{r.key}|{index}|s" if r.kind is Kind.DOOR else None
                values = (
                    r.kind.value,
                    r.key,
                    r.owner,
                    r.sponsor_id,
                    r.status.value,
                    r.tries,
                )
                other.execute(insert, (*values, r.next_at, r.created_at, idem_key))
        yield database
        database.close()


@given(rows=ROWS, owner=st.sampled_from(ROW_OWNERS), now=TIMES)
def test_the_due_sql_matches_the_pure_due_order(
    rows: list[Row], owner: str, now: float
) -> None:
    """For any row set, ``due_rows()`` is ``core.outbox.due()``, row for row, in order."""
    with stored_rows(rows) as database:
        expected = outbox.due(everything(database), owner, now)
        assert database.due_rows(owner, now) == expected


@given(rows=ROWS, owner=st.sampled_from(ROW_OWNERS))
def test_delete_synced_keeps_what_forget_synced_keeps(
    rows: list[Row], owner: str
) -> None:
    """For any row set, ``delete_synced()`` leaves exactly ``forget_synced()``'s rows."""
    with stored_rows(rows) as database:
        expected = outbox.forget_synced(everything(database), owner)
        assert database.delete_synced(owner)
        assert everything(database) == expected


# ------------------------------------------------------------------ the session's database


def test_services_build_the_outbox_in_the_data_directory_and_close_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``Services.create`` points the outbox at the data directory; ``close()`` closes it."""
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path))
    svc = Services.create(ViewMemory())
    assert svc.outbox is not None
    assert svc.outbox.path == tmp_path.absolute() / f"outbox-{YEAR}.db"
    assert not svc.outbox.path.exists()  # nothing opened until the staff tools run
    queued(scan(svc.outbox))
    svc.close()
    assert scan(svc.outbox) is None
