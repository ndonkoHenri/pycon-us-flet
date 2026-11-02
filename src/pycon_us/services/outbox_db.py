"""The staff outbox's sqlite database, ``outbox-<year>.db`` in the data directory (D-49, D-56).

``core/outbox_enqueue.py`` and ``core/outbox.py`` decide what a scan, a send or a
sign-out does to the rows; this module only stores them. One connection, opened on
first use and used only from the asyncio loop thread: statements take milliseconds,
so nothing goes to ``to_thread``, and sqlite's ``check_same_thread`` refuses any other
thread (D-49). The file is in WAL mode and migrated by ``PRAGMA user_version``. S1 ran
``sqlite3`` in the packaged runtime on both platforms, and the file survived update
installs (D-108).

A database that cannot be opened, read or written is an expected failure: it is logged
and returned, never raised (D-120), so the caller can say "Couldn't save the scan".
"""

import contextlib
import logging
import sqlite3
from collections.abc import Callable, Collection, Iterator
from dataclasses import dataclass, replace
from pathlib import Path

from pycon_us.core.outbox import Row, Status
from pycon_us.core.outbox_enqueue import Enqueued, Outcome
from pycon_us.services.outbox_schema import (
    COLUMNS,
    DELETE_SYNCED_SQL,
    DUE_SQL,
    VALUES,
    file_name,
    is_edit,
    migrate,
    to_params,
    to_row,
    update,
)

logger = logging.getLogger(__name__)


class DbClosed(Exception):
    """The session closed the database; a late write is refused, not raised (D-120)."""


@dataclass(frozen=True)
class Counts:
    """An owner's rows by status, for the sync chip and sign-out's question.

    Attributes:
        pending: Rows waiting to be sent.
        failed: Rows given up on until "Retry failed".
        synced: Rows the server has.
    """

    pending: int = 0
    failed: int = 0
    synced: int = 0


class OutboxDb:
    """A year's outbox rows: every outbox read and write goes through here.

    Built by ``Services.create()`` and closed by ``Services.close()``. The connection
    opens on first use, from the loop thread that then owns it, so an install whose
    staff tools never run (they are hidden without a mock API URL, D-51) never creates
    the file. Every method is synchronous and runs on that thread (D-49).

    Attributes:
        path: The database file, ``outbox-<year>.db`` in the data directory.
    """

    def __init__(self, directory: Path, year: int) -> None:
        """Point at ``year``'s file in ``directory``; nothing is opened yet.

        Args:
            directory: The durable data directory, from ``data_dir()`` (D-108).
            year: The conference year whose rows it holds (D-466).
        """
        self.path = directory / file_name(year)
        self._connection: sqlite3.Connection | None = None
        self._closed = False

    def _connect(self) -> sqlite3.Connection:
        """Return the connection, opening and migrating the file on first use."""
        if self._closed:
            raise DbClosed
        if self._connection is None:
            # isolation_level=None: autocommit, so each transaction is an explicit BEGIN.
            connection = sqlite3.connect(self.path, isolation_level=None)
            try:
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA journal_mode=WAL")
                migrate(connection)
            except sqlite3.Error:
                connection.close()
                raise
            self._connection = connection
        return self._connection

    @contextlib.contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        """Run the block in one write transaction, rolled back when it fails."""
        connection = self._connect()
        connection.execute("BEGIN IMMEDIATE")
        try:
            yield connection
            connection.execute("COMMIT")
        except BaseException:
            if connection.in_transaction:
                with contextlib.suppress(sqlite3.Error):  # keep the original error
                    connection.rollback()
            raise

    def _attempt[T](self, what: str, action: Callable[[], T]) -> T | None:
        """Return ``action()``, or None when the database fails, logged (D-120).

        A use from another thread (``sqlite3.ProgrammingError``) is a bug, not a storage
        failure, so it is raised.
        """
        try:
            return action()
        except DbClosed:
            logger.warning("Outbox closed; refused to %s", what)
        except sqlite3.ProgrammingError:
            raise
        except sqlite3.Error, OSError:
            logger.warning("Could not %s in the outbox", what, exc_info=True)
        return None

    def _select(self, sql: str, params: dict[str, object] | tuple = ()) -> list[Row]:
        """Return the rows a query selects."""
        return [to_row(r) for r in self._connect().execute(sql, params).fetchall()]

    def enqueue(
        self, code: str, decide: Callable[[list[Row]], Enqueued]
    ) -> Enqueued | None:
        """Apply a ``core.outbox_enqueue`` decision and store its row, atomically.

        ``decide`` is ``scan_lead``, ``save_note`` or ``admit`` with every argument but
        the rows (a ``functools.partial``). It is given every row of the access code,
        every owner's: all three decide from those alone, since a door row's
        ``idem_key`` starts with its code.

        Args:
            code: The attendee's access code.
            decide: The decision, given the code's rows.

        Returns:
            The decision, with the stored row and its id for ``QUEUED``; None when the
            database failed (logged) and nothing was stored.
        """

        def run() -> Enqueued:
            with self._transaction() as connection:
                rows = self._select("SELECT * FROM outbox WHERE key = ?", (code,))
                enqueued = decide(rows)
                if enqueued.row is None:
                    return enqueued
                if enqueued.row.key != code:  # it was decided over the wrong rows
                    raise ValueError(
                        f"enqueued a row for {enqueued.row.key!r}, not {code!r}"
                    )
                if enqueued.outcome is Outcome.QUEUED:
                    values = to_params(enqueued.row)
                    cursor = connection.execute(
                        f"INSERT INTO outbox ({COLUMNS}) VALUES ({VALUES})", values
                    )
                    return replace(
                        enqueued, row=replace(enqueued.row, id=cursor.lastrowid)
                    )
                if enqueued.outcome is Outcome.UPDATED:
                    # Read in this transaction, so its revision is the stored one.
                    edit = is_edit(rows, enqueued.row)
                    update(connection, enqueued.row, edit=edit)
                    edited = replace(
                        enqueued.row, revision=enqueued.row.revision + edit
                    )
                    return replace(enqueued, row=edited)
                return enqueued

        return self._attempt("enqueue", run)

    def save(self, row: Row) -> bool:
        """Store a changed row over its record: a send's outcome or "Retry failed".

        The record is written only while it is at the revision the row was read at: a
        note edited while its old text was being sent keeps the new text, pending, and
        the old send's outcome is dropped (D-56). The next pass sends the edit.

        Args:
            row: A stored row (with its id), as ``core.outbox`` changed it.

        Returns:
            Whether it was saved: False when the database failed (logged, D-120) or an
            enqueue edited the record since it was read (logged; the edit stays).

        Raises:
            ValueError: The row was never stored (no id): a bug.
        """
        if row.id is None:
            raise ValueError("an outbox row is saved only once it is stored")

        def run() -> bool:
            with self._transaction() as connection:
                saved = update(connection, row, edit=False)
            if not saved:
                logger.info("Kept outbox row %s: it was edited while sent", row.id)
            return saved

        return self._attempt("save a row", run) or False

    def flag_maybe_sent(self, row_id: int) -> bool:
        """Flag a row "may be recorded twice" whatever its revision (D-410).

        A send that may have reached the server is a fact about the row, not about the
        revision that was sent: an edit while it was in flight drops the send's
        outcome (``save()``), never this flag.

        Args:
            row_id: The stored row's id.

        Returns:
            Whether the flag landed; a failure is logged (D-120).
        """
        sql = "UPDATE outbox SET maybe_sent = 1 WHERE id = :id"
        return self._execute("flag a row", sql, {"id": row_id})

    def due_now(self, owner: str, now: float) -> bool:
        """Make the owner's pending rows due now: "Sync now" skips their backoff (D-414).

        A row that waits out a 60 s backoff after a failed send would otherwise miss
        the pass the tap asks for. Neither the tries nor the revision change, so a
        pass under way saves its outcome as usual.

        Args:
            owner: The signed-in account's lower-cased email.
            now: The current time (epoch seconds).

        Returns:
            Whether the rows were updated; a failure is logged (D-120).
        """
        sql = (
            "UPDATE outbox SET next_at = :now WHERE owner = :owner "
            "AND status = 'pending' AND next_at > :now"
        )
        return self._execute("make rows due", sql, {"owner": owner, "now": now})

    def due_rows(self, owner: str, now: float) -> list[Row]:
        """Return the owner's rows to send now, in send order (§12.1's query).

        Args:
            owner: The signed-in account's lower-cased email.
            now: The current time (epoch seconds).

        Returns:
            The rows, as ``core.outbox.due()`` orders them; none when the database
            fails (logged): nothing is sent, and the next pass tries again.
        """
        params = {"owner": owner, "now": now}
        return (
            self._attempt("read due rows", lambda: self._select(DUE_SQL, params)) or []
        )

    def counts(self, owner: str | None) -> Counts | None:
        """Return how many of the owner's rows are pending, failed and synced.

        Args:
            owner: The account's lower-cased email; None for every account's rows
                (Clear staff data and Reset app, D-414).

        Returns:
            The counts, or None when the database fails (logged): never zeros that
            would let a sign-out drop unsynced rows without asking.
        """

        def run() -> Counts:
            where, params = (
                ("WHERE owner = ?", (owner,)) if owner is not None else ("", ())
            )
            sql = f"SELECT status, count(*) FROM outbox {where} GROUP BY status"
            found = dict(self._connect().execute(sql, params).fetchall())
            return Counts(
                **{status.value: found.get(status.value, 0) for status in Status}
            )

        return self._attempt("count rows", run)

    def rows(self, owner: str, statuses: Collection[Status]) -> list[Row] | None:
        """Return the owner's rows in some statuses, oldest first: the queue sheet's.

        Args:
            owner: The account's lower-cased email.
            statuses: The statuses to list.

        Returns:
            The rows by ``created_at`` then id, or None when the database fails (logged).
        """
        marks = ", ".join("?" * len(statuses))
        sql = f"SELECT * FROM outbox WHERE owner = ? AND status IN ({marks})"
        params = (owner, *(Status(status).value for status in statuses))
        return self._attempt(
            "list rows", lambda: self._select(f"{sql} ORDER BY created_at, id", params)
        )

    def door_rows(self, owner: str, code: str) -> list[Row] | None:
        """Return the owner's door rows for an access code, every status (STORE-12).

        Door check's "Already checked in" reads them (``core.admission.decide()``).

        Returns:
            The rows, or None when the database fails (logged).
        """
        sql = "SELECT * FROM outbox WHERE owner = ? AND kind = 'door' AND key = ?"
        return self._attempt("read check-ins", lambda: self._select(sql, (owner, code)))

    def row(self, row_id: int) -> Row | None:
        """Return one row by id: how a lead scan's send ended (D-426).

        Returns:
            The row, or None when it is gone or the database fails (logged).
        """
        sql = "SELECT * FROM outbox WHERE id = ?"
        found = self._attempt("read a row", lambda: self._select(sql, (row_id,)))
        return found[0] if found else None

    def owners_with_unsynced(self) -> list[str] | None:
        """Return every owner with a pending or failed row, sorted.

        Returns:
            The owners, or None when the database fails (logged).
        """
        return self._owners("WHERE status <> 'synced'", ())

    def _owners(self, where: str, params: tuple[str, ...]) -> list[str] | None:
        """Return the owners of the rows ``where`` selects, sorted."""
        sql = f"SELECT DISTINCT owner FROM outbox {where} ORDER BY owner"
        return self._attempt(
            "list owners",
            lambda: [o for (o,) in self._connect().execute(sql, params).fetchall()],
        )

    def delete_synced(self, owner: str) -> bool:
        """Delete the owner's synced rows on an account switch (``forget_synced()``).

        A synced lead whose note hasn't synced stays, as the note waits for it; pending
        and failed rows stay, as does every other owner's row.

        Returns:
            Whether the rows are gone; a failure is logged (D-120).
        """
        return self._execute("delete synced rows", DELETE_SYNCED_SQL, {"owner": owner})

    def forget_other_accounts(self, owner: str) -> bool:
        """Delete every other owner's synced rows, as an account switch does (D-414).

        Each other owner's rows go as ``delete_synced()`` deletes them: a synced lead
        whose note hasn't synced stays, as do the pending and failed rows. The worker
        runs it at each start of a signed-in account's sync (``services.sync``): an
        earlier account's synced rows are then ones the new account must not see, and
        the next start finds none left.

        Args:
            owner: The signed-in account's lower-cased email, whose rows stay.

        Returns:
            Whether every deletion landed; a failure is logged (D-120), and the next
            start tries again.
        """
        owners = self._owners("WHERE owner <> ?", (owner,))
        if owners is None:
            return False
        deleted = [self.delete_synced(other) for other in owners]  # each one tried
        return all(deleted)

    def clear(self, owner: str | None = None) -> bool:
        """Delete every row of ``owner``, or every row ("Clear staff data", confirmed).

        Returns:
            Whether the rows are gone; a failure is logged (D-120).
        """
        if owner is None:
            return self._execute("clear the outbox", "DELETE FROM outbox", {})
        sql = "DELETE FROM outbox WHERE owner = :owner"
        return self._execute("clear an owner's rows", sql, {"owner": owner})

    def _execute(self, what: str, sql: str, params: dict[str, object]) -> bool:
        """Run one write statement in its own transaction; whether it landed."""

        def run() -> bool:
            with self._transaction() as connection:
                connection.execute(sql, params)
            return True

        return self._attempt(what, run) or False

    def close(self) -> None:
        """Close the connection for good: later calls are refused and logged, not raised."""
        self._closed = True
        if self._connection is not None:
            self._connection.close()
            self._connection = None
