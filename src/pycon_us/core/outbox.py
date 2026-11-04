"""The staff outbox's rows and their send rules: how a send moves a row, what is due.

The outbox keeps every lead scan, lead note and door check-in until the server has it
(D-56): "never lose or misattribute a scan". The rules that keep that promise are pure
and live here and in `core/outbox_enqueue.py` (what a scan, a note or an admission
enqueues), so a hypothesis state machine proves them (D-77) before any sqlite
(`services/outbox_db.py`) or sending (`services/sync.py`) code exists. Every function
takes rows and returns new ones; the caller stores them. `due()` is the Python twin of
the due-rows query in docs/architecture.md §12.1, and §12.2 is the transition table.
`status_text()` says a row's status, flagged "may be recorded twice" after a send
whose answer was lost or could not be read (D-57, D-410).
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any

RETRY_CAP = 10
"""Counted failures (`ApiError`s) after which a row is `failed` (D-56)."""

NETWORK_BACKOFF = 60.0
"""Seconds a row waits after a failed send: the `SyncWorker`'s tick (LEAD-12)."""


class Kind(StrEnum):
    """What a row records, and so which endpoint sends it."""

    LEAD = "lead"
    NOTE = "note"
    DOOR = "door"


class Status(StrEnum):
    """Where a row is: waiting to be sent, on the server, or given up on until retried."""

    PENDING = "pending"
    SYNCED = "synced"
    FAILED = "failed"


SEND_ORDER = {Kind.LEAD: 0, Kind.DOOR: 1, Kind.NOTE: 2}
"""The due order's first key: leads, then door check-ins, then notes (§12.1)."""


@dataclass(frozen=True)
class Row:
    """One outbox row, column for column as §12.1 stores it.

    Attributes:
        kind: What the row records.
        key: The attendee's access code.
        payload: The request (`payload_json` in sqlite); once synced it also holds the
            server's answer under `"result"`.
        owner: The lower-cased account email at enqueue; never changes.
        sponsor_id: The sponsor snapshot at enqueue (STORE-11); never changes.
        sponsor_name: The sponsor's name, snapshot with its id.
        status: Pending, synced or failed.
        tries: Counted failures since the row was last made pending by hand.
        next_at: When the row is next due (epoch seconds).
        created_at: When it was scanned (epoch seconds); the due order's second key.
        last_error: The last counted failure's message, for the queue sheet.
        idem_key: A door row's idempotency key, `code|sorted product ids|session`.
        id: The sqlite row id; None until the row is first stored.
        revision: How many times an enqueue changed the stored row. A send's outcome
            is saved only over the revision it was read at, so a note edited while
            its old text was in flight keeps the new text (D-56).
        maybe_sent: Whether a send got no answer, or none we could read, after the
            server may have had the request (`NetworkError.maybe_sent`,
            `ApiError.unreadable`), so a resend may record it twice (D-57, D-410).
            Once set, never cleared: a later success keeps it.
    """

    kind: Kind
    key: str
    payload: Mapping[str, Any] = field(hash=False)
    owner: str
    sponsor_id: str | None
    sponsor_name: str | None
    next_at: float
    created_at: float
    status: Status = Status.PENDING
    tries: int = 0
    last_error: str | None = None
    idem_key: str | None = None
    id: int | None = None
    revision: int = 0
    maybe_sent: bool = False


STATUS_WORDS = {
    Status.PENDING: "Queued",
    Status.SYNCED: "Confirmed",
    Status.FAILED: "Failed",
}
"""Each status as the queue sheet and the tools' lists say it (ux.md §7.2)."""

MAYBE_TWICE = "may be recorded twice"
"""What a flagged row adds to its status (`Row.maybe_sent`, D-410): only "may", since
an idempotent server records it once and the app cannot tell which it talks to."""


def status_text(row: Row) -> str:
    """Return a row's status in words: "Confirmed · may be recorded twice" when flagged.

    The one place the words are kept, for the queue sheet and the tools' lists (#694,
    #39, #40), which show a flagged row with an icon beside them.
    """
    words = STATUS_WORDS[row.status]
    return f"{words} · {MAYBE_TWICE}" if row.maybe_sent else words


def _pending(row: Row) -> None:
    """Refuse to send a row that isn't pending: only `due()` rows are sent."""
    if row.status is not Status.PENDING:
        raise ValueError(f"outbox row {row.id} is {row.status}, not pending")


def after_success(row: Row, result: object) -> Row:
    """Return a sent row: synced, with the server's answer merged into its payload.

    Args:
        row: The pending row that was sent.
        result: The server's answer.

    Returns:
        The synced row, kept for lead dedupe and "Already checked in".
    """
    _pending(row)
    payload = {**row.payload, "result": result}
    return replace(row, status=Status.SYNCED, payload=payload, last_error=None)


def after_network_error(row: Row, now: float, *, maybe_sent: bool = False) -> Row:
    """Return a row whose send got no answer: still pending, its tries unchanged.

    A `NetworkError` is the connection's fault, not the row's, so it is never counted;
    the row waits a tick and the worker ends its pass. One that may have reached the
    server flags the row for good: the resend may be a second record (D-410).

    Args:
        row: The pending row that was sent.
        now: The current time (epoch seconds).
        maybe_sent: Whether the request may have reached the server
            (`NetworkError.maybe_sent`); False for a refused key, which answered.

    Returns:
        The row, due again in `NETWORK_BACKOFF` seconds.
    """
    _pending(row)
    flagged = row.maybe_sent or maybe_sent
    return replace(row, next_at=now + NETWORK_BACKOFF, maybe_sent=flagged)


def after_error(row: Row, message: str, now: float, *, maybe_sent: bool = False) -> Row:
    """Return a row the server answered unusably: one more counted failure.

    The row waits a tick like after a network error; the `RETRY_CAP`-th counted
    failure makes it `failed`, until "Retry failed". An answer that could not be read
    flags the row for good, as a lost one does, and still counts: resending it for ever
    to a server that always answers so could record it without end (D-410).

    Args:
        row: The pending row that was sent.
        message: The `ApiError`'s message.
        now: The current time (epoch seconds).
        maybe_sent: Whether the server may have applied it though it answered
            (`ApiError.unreadable`); False for a refusal.

    Returns:
        The row, pending and due in `NETWORK_BACKOFF` seconds, or failed.
    """
    _pending(row)
    tries = row.tries + 1
    status = Status.FAILED if tries >= RETRY_CAP else Status.PENDING
    return replace(
        row,
        status=status,
        tries=tries,
        last_error=message,
        next_at=now + NETWORK_BACKOFF,
        maybe_sent=row.maybe_sent or maybe_sent,
    )


def requeue(row: Row, now: float) -> Row:
    """Return a row pending again from scratch: no counted failures, due now.

    Behind "Retry failed" and an enqueue that brings a row back
    (`core/outbox_enqueue.py`). Unlike `retry_failed()`, it takes any status.

    Args:
        row: The row.
        now: The current time (epoch seconds).

    Returns:
        The row, pending.
    """
    return replace(row, status=Status.PENDING, tries=0, next_at=now, last_error=None)


def retry_failed(row: Row, now: float) -> Row:
    """Return a failed row pending again ("Retry failed"): no counted failures, due now.

    Args:
        row: A failed row.
        now: The current time (epoch seconds).

    Returns:
        The row, pending.

    Raises:
        ValueError: When the row isn't failed.
    """
    if row.status is not Status.FAILED:
        raise ValueError(f"outbox row {row.id} is {row.status}, not failed")
    return requeue(row, now)


def due(rows: Iterable[Row], owner: str, now: float) -> list[Row]:
    """Return the owner's rows to send now, in the order to send them.

    Pending rows whose `next_at` has come: leads, then door check-ins, then notes,
    each by `created_at` (then id). A note waits until its lead, the same sponsor's,
    is synced (D-459).

    Args:
        rows: The outbox rows (any owner's).
        owner: The signed-in account's lower-cased email.
        now: The current time (epoch seconds).

    Returns:
        The due rows, in send order.
    """
    mine = [r for r in rows if r.owner == owner]
    synced_leads = {
        (r.key, r.sponsor_id)
        for r in mine
        if r.kind is Kind.LEAD and r.status is Status.SYNCED
    }
    ready = [
        r
        for r in mine
        if r.status is Status.PENDING
        and r.next_at <= now
        and (r.kind is not Kind.NOTE or (r.key, r.sponsor_id) in synced_leads)
    ]
    return sorted(ready, key=lambda r: (SEND_ORDER[r.kind], r.created_at, r.id or 0))


def forget_synced(rows: Iterable[Row], owner: str) -> list[Row]:
    """Return the rows kept when `owner` signs out for another account.

    Their synced rows go (the next account must not see "Already in your leads" for
    someone else's leads), except a synced lead whose note, the same sponsor's, hasn't
    synced: the note waits for it, and would wait forever. Their pending and failed
    rows stay until synced or cleared with confirmation, as does every other owner's
    row.

    Args:
        rows: The outbox rows.
        owner: The previous account's lower-cased email.

    Returns:
        The rows to keep, in their order.
    """
    rows = list(rows)
    waiting = {
        (r.key, r.sponsor_id)
        for r in rows
        if r.owner == owner and r.kind is Kind.NOTE and r.status is not Status.SYNCED
    }
    return [
        r
        for r in rows
        if r.owner != owner
        or r.status is not Status.SYNCED
        or (r.kind is Kind.LEAD and (r.key, r.sponsor_id) in waiting)
    ]
