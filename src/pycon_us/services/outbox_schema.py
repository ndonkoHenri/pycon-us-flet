"""The staff outbox's schema and its row mapping, for ``services/outbox_db.py`` (D-49, D-56).

The tables (architecture §12.1), their migrations by ``PRAGMA user_version``, the two
queries with a Python twin in ``core/outbox.py``, the conversion between a stored
record and ``core.outbox.Row``, and the write of a changed row that only lands while the
record is at the row's revision (D-56). ``OutboxDb`` is their one user; split from it at
D-66's ~400 lines (#732, #755).
"""

import json
import sqlite3
from dataclasses import replace

from pycon_us.core.outbox import Kind, Row, Status


def file_name(year: int) -> str:
    """Return a year's database file in the data directory (D-108, D-466).

    One file per conference year, as the feed cache and the change log are (D-48):
    every query and send then stays within the year, since a row's sponsor, products
    and access code mean nothing in another year's data (D-56).

    Args:
        year: The conference year.

    Returns:
        ``outbox-<year>.db``.
    """
    return f"outbox-{year}.db"


OUTBOX_V1 = """
CREATE TABLE IF NOT EXISTS outbox (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    kind         TEXT NOT NULL CHECK (kind IN ('lead', 'note', 'door')),
    key          TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    owner        TEXT NOT NULL,
    sponsor_id   TEXT,
    sponsor_name TEXT,
    status       TEXT NOT NULL DEFAULT 'pending'
                 CHECK (status IN ('pending', 'synced', 'failed')),
    tries        INTEGER NOT NULL DEFAULT 0,
    next_at      REAL NOT NULL,
    created_at   REAL NOT NULL,
    last_error   TEXT,
    idem_key     TEXT,
    revision     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS outbox_due ON outbox (owner, status, next_at);
CREATE INDEX IF NOT EXISTS outbox_key ON outbox (owner, kind, key);
CREATE UNIQUE INDEX IF NOT EXISTS outbox_idem ON outbox (idem_key)
    WHERE idem_key IS NOT NULL;
"""
"""The first schema (architecture §12.1): the table and its three indexes."""

OUTBOX_V2 = """
ALTER TABLE outbox ADD COLUMN maybe_sent INTEGER NOT NULL DEFAULT 0;
"""
"""``Row.maybe_sent``: a send got no answer after the server may have had it (D-410)."""

MIGRATIONS = (OUTBOX_V1, OUTBOX_V2)
"""Each schema change, in order: a file at ``user_version`` n runs the ones after n."""

DUE_SQL = """
SELECT o.* FROM outbox o
WHERE o.owner = :owner AND o.status = 'pending' AND o.next_at <= :now
  AND (o.kind <> 'note' OR EXISTS (SELECT 1 FROM outbox l WHERE l.owner = o.owner
       AND l.kind = 'lead' AND l.key = o.key AND l.status = 'synced'))
ORDER BY CASE o.kind WHEN 'lead' THEN 0 WHEN 'door' THEN 1 ELSE 2 END, o.created_at, o.id
"""
"""The due rows in send order (§12.1); ``core.outbox.due()`` is its Python twin."""

DELETE_SYNCED_SQL = """
DELETE FROM outbox WHERE owner = :owner AND status = 'synced'
  AND NOT (kind = 'lead' AND EXISTS (SELECT 1 FROM outbox n WHERE n.owner = :owner
           AND n.kind = 'note' AND n.key = outbox.key AND n.status <> 'synced'))
"""
"""``core.outbox.forget_synced()`` in SQL: a synced lead stays while its note waits."""


COLUMNS = (
    "kind, key, payload_json, owner, sponsor_id, sponsor_name, status, tries, "
    "next_at, created_at, last_error, idem_key, maybe_sent"
)
"""The columns an insert or a save writes; ``revision`` counts edits on its own."""
VALUES = ":kind, :key, :payload_json, :owner, :sponsor_id, :sponsor_name, :status, "
VALUES += ":tries, :next_at, :created_at, :last_error, :idem_key, :maybe_sent"


def to_params(row: Row) -> dict[str, object]:
    """Return a row's columns as named parameters, its payload as JSON."""
    return {
        "kind": row.kind.value,
        "key": row.key,
        "payload_json": json.dumps(dict(row.payload)),
        "owner": row.owner,
        "sponsor_id": row.sponsor_id,
        "sponsor_name": row.sponsor_name,
        "status": row.status.value,
        "tries": row.tries,
        "next_at": row.next_at,
        "created_at": row.created_at,
        "last_error": row.last_error,
        "idem_key": row.idem_key,
        "maybe_sent": int(row.maybe_sent),
        "id": row.id,
        "revision": row.revision,
    }


def to_row(record: sqlite3.Row) -> Row:
    """Return a stored record as the ``Row`` that ``core.outbox`` works with."""
    return Row(
        kind=Kind(record["kind"]),
        key=record["key"],
        payload=json.loads(record["payload_json"]),
        owner=record["owner"],
        sponsor_id=record["sponsor_id"],
        sponsor_name=record["sponsor_name"],
        next_at=record["next_at"],
        created_at=record["created_at"],
        status=Status(record["status"]),
        tries=record["tries"],
        last_error=record["last_error"],
        idem_key=record["idem_key"],
        id=record["id"],
        revision=record["revision"],
        maybe_sent=bool(record["maybe_sent"]),
    )


def migrate(connection: sqlite3.Connection) -> None:
    """Run the migrations the file hasn't had, each with its ``user_version``, atomically."""
    (version,) = connection.execute("PRAGMA user_version").fetchone()
    for number, script in enumerate(MIGRATIONS[version:], start=version + 1):
        # executescript() runs in autocommit mode, so the script brings its own BEGIN:
        # the schema and its version land together or not at all.
        connection.executescript(
            f"BEGIN IMMEDIATE;{script}PRAGMA user_version = {number}; COMMIT;"
        )


def update(connection: sqlite3.Connection, row: Row, *, edit: bool = True) -> bool:
    """Write a row's columns over its record, if the record is still at its revision.

    Args:
        connection: The connection, in a write transaction.
        row: A stored row, changed from the record at ``row.revision``.
        edit: Whether this is an enqueue's edit, which counts a new revision; a
            send's outcome or "Retry failed" leaves the revision as it is.

    Returns:
        Whether the record was written: False when an edit changed it since.

    Raises:
        ValueError: The row was never stored (no id): a bug.
    """
    if row.id is None:
        raise ValueError("an outbox row is saved only once it is stored")
    sets = ", ".join(f"{name} = :{name}" for name in COLUMNS.split(", "))
    # A flag set by id since the row was read stays: nothing clears it (D-410).
    sets = sets.replace("maybe_sent = :", "maybe_sent = maybe_sent OR :")
    bump = ", revision = revision + 1" if edit else ""
    cursor = connection.execute(
        f"UPDATE outbox SET {sets}{bump} WHERE id = :id AND revision = :revision",
        to_params(row),
    )
    return cursor.rowcount == 1


def is_edit(rows: list[Row], row: Row) -> bool:
    """Whether an enqueue changed more of a stored row than when it is due (D-57).

    A rescan of a pending lead only makes it due now: a send already under way still
    sends what the row holds, so its outcome must save. Counting a revision would drop
    a success and resend it, a second record that no lost answer explains.

    Args:
        rows: The code's rows, read in the enqueue's transaction.
        row: The row the decision changed, with its stored id.
    """
    stored = next(r for r in rows if r.id == row.id)
    return replace(row, next_at=stored.next_at) != stored
