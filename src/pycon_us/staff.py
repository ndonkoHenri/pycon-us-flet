"""The ``Staff`` store: the staff outbox as the screens see it (P3, D-56).

The rows live in ``outbox.db`` (``services/outbox_db.py``); this store holds what the
sync chip, the queue sheet and sign-out's question show about them: how many of the
signed-in account's rows are pending, failed and synced, whether a sync pass is under
way and how the last one ended. ``services/sync.py``'s ``SyncWorker`` writes it after
each pass, and whatever else changes the rows (an enqueue, ``retry_failed()``) calls
``update_counts()`` after its write. ``revision`` counts those calls, so a list of rows
re-reads the database when it changes (D-69). The sponsor picked to scan for, the door
inventory and the Code of Conduct directory join it with #39, #40 and #42.
"""

from dataclasses import dataclass

import flet as ft

from pycon_us.core import outbox
from pycon_us.core.outbox import Status
from pycon_us.services.outbox_db import Counts, OutboxDb


# eq=False: a store is one object, compared by identity (F5), as Account.
@ft.observable
@dataclass(eq=False)
class Staff:
    """The signed-in account's outbox at a glance (architecture §6.1).

    Attributes:
        pending: The account's rows waiting to be sent.
        failed: The account's rows given up on until "Retry failed".
        synced: The account's rows the server has.
        syncing: Whether a sync pass is under way; also what keeps a second pass from
            starting while one runs (one drain at a time).
        last_sync_at: When the last pass that reached the server for every row it
            tried ended (epoch seconds), or None before the first.
        last_error: Why the last pass stopped or a row was refused, or None when the
            last pass went through.
        offline: Whether the last pass ended without an answer (a ``NetworkError``):
            the sync chip then says "Offline · 3 queued" (#694).
        revision: Bumped each time the rows change, so a list of them re-reads.
    """

    pending: int = 0
    failed: int = 0
    synced: int = 0
    syncing: bool = False
    last_sync_at: float | None = None
    last_error: str | None = None
    offline: bool = False
    revision: int = 0

    def update_counts(self, counts: Counts | None) -> None:
        """Take the account's counts in after its rows changed, and bump ``revision``.

        Args:
            counts: ``OutboxDb.counts()`` for the signed-in account, or None when the
                database failed (logged): the counts shown stay as they were, and only
                ``revision`` moves.
        """
        if counts is not None:
            self.pending = counts.pending
            self.failed = counts.failed
            self.synced = counts.synced
        self.revision += 1

    def clear(self) -> None:
        """Forget the outbox's state, as signed out: no counts and no last pass."""
        self.pending = self.failed = self.synced = 0
        self.syncing = False
        self.last_sync_at = None
        self.last_error = None
        self.offline = False
        self.revision += 1

    def retry_failed(self, db: OutboxDb, owner: str, now: float) -> int:
        """Make the owner's failed rows pending again ("Retry failed"), then recount.

        Each row is saved as ``outbox.retry_failed()`` makes it: no counted failures,
        due now, its "may be recorded twice" flag kept (D-410). The caller then kicks
        the worker (``Services.kick_sync()``).

        Args:
            db: The outbox.
            owner: The signed-in account's lower-cased email.
            now: The current time (epoch seconds).

        Returns:
            How many rows are pending again; 0 when the database failed (logged).
        """
        rows = db.rows(owner, (Status.FAILED,)) or []
        retried = sum(db.save(outbox.retry_failed(row, now)) for row in rows)
        self.update_counts(db.counts(owner))
        return retried


StaffCtx: ft.ContextProvider[Staff | None] = ft.create_context(None)
"""Provides the session's ``Staff``; ``App`` writes the provider out (D-69)."""


def use_staff() -> Staff:
    """Return the ``Staff`` store and re-render the caller when it changes (F3).

    Raises:
        RuntimeError: No ``StaffCtx`` provider is above the calling component.
    """
    store = ft.use_context(StaffCtx)
    if store is None:
        raise RuntimeError("use_staff() needs a StaffCtx provider above it")
    return store
