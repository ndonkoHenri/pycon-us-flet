"""Rows written under one lead per (owner, code), in a version 2 file (D-459, #829).

Keying leads and notes by sponsor as well changes no column, so the file isn't migrated:
every row written before it is already a valid row of the new key, since a note always
took its lead's sponsor. These tests write a year's file (D-466) by hand, with the
migrations as they were, and use it through ``OutboxDb`` and the rules as the app does.
A device's ``outbox.db`` from those builds is left unread (D-466), and the last test
pins that.
"""

import contextlib
import json
import sqlite3
from collections.abc import Iterator
from functools import partial
from pathlib import Path

import pytest

from pycon_us.core import outbox_enqueue
from pycon_us.core.outbox import Kind, Status
from pycon_us.core.outbox_enqueue import Outcome
from pycon_us.services.outbox_db import OutboxDb
from pycon_us.services.outbox_schema import OUTBOX_V1, OUTBOX_V2, file_name

YEAR = 2026
OWNER = "staff@example.com"
NOW = 1_000_000.0
ANSWERED = json.dumps({"badge_validator": "v", "result": {"first_name": "Ada"}})
NOTED = json.dumps({"accessCode": "A1", "note": "Hot"})


def write_old_rows(path: Path) -> None:
    """Write a version 2 file at ``path`` holding what an earlier build left.

    A1: a synced lead for Acme with a note waiting. B2: a pending lead for Acme.
    C3: a failed lead for Acme. D4: a sponsor's own synced lead (no sponsor).
    """
    with contextlib.closing(sqlite3.connect(path)) as old, old:
        old.executescript(f"{OUTBOX_V1}{OUTBOX_V2}PRAGMA user_version = 2;")
        old.executemany(
            "INSERT INTO outbox (kind, key, payload_json, owner, sponsor_id,"
            " sponsor_name, status, tries, next_at, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("lead", "A1", ANSWERED, OWNER, "7", "Acme", "synced", 0, NOW, NOW),
                ("note", "A1", NOTED, OWNER, "7", "Acme", "pending", 0, NOW, NOW + 1),
                ("lead", "B2", "{}", OWNER, "7", "Acme", "pending", 0, NOW + 60, NOW),
                ("lead", "C3", "{}", OWNER, "7", "Acme", "failed", 10, NOW, NOW),
                ("lead", "D4", ANSWERED, OWNER, None, None, "synced", 0, NOW, NOW),
            ],
        )


@pytest.fixture
def device(tmp_path: Path) -> Iterator[OutboxDb]:
    """Yield an outbox over a version 2 file of its year, with the old rows in it."""
    write_old_rows(tmp_path / file_name(YEAR))
    database = OutboxDb(tmp_path, YEAR)
    yield database
    database.close()


def scan(
    db: OutboxDb, code: str, sponsor: tuple[str | None, str | None] = ("7", "Acme")
) -> outbox_enqueue.Enqueued:
    """Scan ``code`` for ``sponsor`` as the upgraded app does."""
    decide = partial(
        outbox_enqueue.scan_lead,
        owner=OWNER,
        code=code,
        payload={"badge_validator": "v"},
        sponsor_id=sponsor[0],
        sponsor_name=sponsor[1],
        now=NOW + 5,
    )
    enqueued = db.enqueue(code, decide)
    assert enqueued is not None
    return enqueued


def test_the_file_opens_as_it_was_and_its_waiting_note_is_still_due(
    device: OutboxDb,
) -> None:
    """Five rows read back unchanged, and the note follows its synced lead."""
    rows = device.rows(OWNER, list(Status)) or []
    assert [(r.kind, r.key, r.sponsor_id, r.status) for r in rows] == [
        (Kind.LEAD, "A1", "7", Status.SYNCED),
        (Kind.LEAD, "B2", "7", Status.PENDING),
        (Kind.LEAD, "C3", "7", Status.FAILED),
        (Kind.LEAD, "D4", None, Status.SYNCED),
        (Kind.NOTE, "A1", "7", Status.PENDING),
    ]
    assert [r.kind for r in device.due_rows(OWNER, NOW)] == [Kind.NOTE]


@pytest.mark.parametrize(
    ("code", "sponsor", "outcome"),
    [
        ("A1", ("7", "Acme"), Outcome.ALREADY),
        ("B2", ("7", "Acme"), Outcome.UPDATED),
        ("C3", ("7", "Acme"), Outcome.UPDATED),
        ("D4", (None, None), Outcome.ALREADY),
    ],
)
def test_a_rescan_for_the_same_sponsor_is_still_a_repeat_of_the_old_row(
    device: OutboxDb,
    code: str,
    sponsor: tuple[str | None, str | None],
    outcome: Outcome,
) -> None:
    """An old row is found by its snapshot: no second row, and nothing else moves."""
    before = len(device.rows(OWNER, list(Status)) or [])
    enqueued = scan(device, code, sponsor)
    assert enqueued.outcome is outcome
    assert enqueued.others == ()
    assert len(device.rows(OWNER, list(Status)) or []) == before


def test_a_scan_for_another_sponsor_adds_a_lead_beside_the_old_row(
    device: OutboxDb,
) -> None:
    """The old row stays as it was; the new one is its own, and names the old sponsor."""
    enqueued = scan(device, "A1", ("8", "Beta"))
    assert enqueued.outcome is Outcome.QUEUED
    assert enqueued.others == ("Acme",)
    leads = [
        r
        for r in device.rows(OWNER, list(Status)) or []
        if r.kind is Kind.LEAD and r.key == "A1"
    ]
    assert [(r.sponsor_id, r.status) for r in leads] == [
        ("7", Status.SYNCED),
        ("8", Status.PENDING),
    ]


def test_an_edit_of_the_old_note_stays_on_its_row(device: OutboxDb) -> None:
    """Saved again for its lead's sponsor, the old note is rewritten, not doubled."""
    decide = partial(
        outbox_enqueue.save_note,
        owner=OWNER,
        code="A1",
        note="Cold",
        sponsor_id="7",
        sponsor_name="Acme",
        now=NOW + 5,
    )
    enqueued = device.enqueue("A1", decide)
    assert enqueued is not None and enqueued.outcome is Outcome.UPDATED
    notes = [r for r in device.rows(OWNER, list(Status)) or [] if r.kind is Kind.NOTE]
    assert [r.payload["note"] for r in notes] == ["Cold"]


def test_a_switch_of_account_keeps_the_old_lead_its_note_waits_for(
    device: OutboxDb,
) -> None:
    """The purge goes by key and sponsor: A1's lead stays, D4's goes."""
    assert device.delete_synced(OWNER)
    kept = device.rows(OWNER, list(Status)) or []
    assert sorted({r.key for r in kept}) == ["A1", "B2", "C3"]


def test_a_device_s_outbox_db_from_before_the_years_is_left_unread(
    tmp_path: Path,
) -> None:
    """Its rows are the mock's (D-466): the year's outbox starts empty, the file as it was."""
    old_file = tmp_path / "outbox.db"
    write_old_rows(old_file)
    before = old_file.read_bytes()
    database = OutboxDb(tmp_path, YEAR)
    assert database.rows(OWNER, list(Status)) == []
    assert database.due_rows(OWNER, NOW) == []
    database.close()
    assert old_file.read_bytes() == before
