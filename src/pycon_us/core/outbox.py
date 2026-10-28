"""The staff outbox's rules: what a scan enqueues, how a send moves a row, what is due.

The outbox keeps every lead scan, lead note and door check-in until the server has it
(D-56): "never lose or misattribute a scan". The rules that keep that promise are pure
and live here, so a hypothesis state machine proves them (D-77) before any sqlite
(``services/outbox_db.py``) or sending (``services/sync.py``) code exists. Every function
takes rows and returns new ones; the caller stores them. ``due()`` is the Python twin of
the due-rows query in docs/architecture.md §12.1, and §12.2 is the transition table.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any

RETRY_CAP = 10
"""Counted failures (``ApiError``s) after which a row is ``failed`` (D-56)."""

NETWORK_BACKOFF = 60.0
"""Seconds a row waits after a failed send: the ``SyncWorker``'s tick (LEAD-12)."""


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
        payload: The request (``payload_json`` in sqlite); once synced it also holds the
            server's answer under ``"result"``.
        owner: The lower-cased account email at enqueue; never changes.
        sponsor_id: The sponsor snapshot at enqueue (STORE-11); never changes.
        sponsor_name: The sponsor's name, snapshot with its id.
        status: Pending, synced or failed.
        tries: Counted failures since the row was last made pending by hand.
        next_at: When the row is next due (epoch seconds).
        created_at: When it was scanned (epoch seconds); the due order's second key.
        last_error: The last counted failure's message, for the queue sheet.
        idem_key: A door row's idempotency key, ``code|sorted product ids|session``.
        id: The sqlite row id; None until the row is first stored.
        revision: How many times an enqueue changed the stored row. A send's outcome
            is saved only over the revision it was read at, so a note edited while
            its old text was in flight keeps the new text (D-56).
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


class Outcome(StrEnum):
    """What an enqueue decided, so the caller knows whether to store and what to say."""

    QUEUED = "queued"
    """A new row: insert it and kick the worker."""
    UPDATED = "updated"
    """An existing row changed: save it and kick the worker."""
    ALREADY = "already"
    """Nothing to store: the lead is already in your leads, or the check-in is queued."""
    IGNORED = "ignored"
    """Nothing to store: an empty note."""


@dataclass(frozen=True)
class Enqueued:
    """An enqueue's decision.

    Attributes:
        outcome: What happened.
        row: The row to insert (``QUEUED``) or save (``UPDATED``), or the existing row
            that made the scan a no-op (``ALREADY``); None for an ignored note.
    """

    outcome: Outcome
    row: Row | None = None


def _find(rows: Iterable[Row], owner: str, kind: Kind, key: str) -> Row | None:
    """Return the owner's row of a kind for an access code, if there is one."""
    return next(
        (r for r in rows if r.owner == owner and r.kind == kind and r.key == key), None
    )


def _requeue(row: Row, now: float) -> Row:
    """Return a row pending again from scratch: no counted failures, due now."""
    return replace(row, status=Status.PENDING, tries=0, next_at=now, last_error=None)


def scan_lead(
    rows: Iterable[Row],
    *,
    owner: str,
    code: str,
    payload: Mapping[str, Any],
    sponsor_id: str | None,
    sponsor_name: str | None,
    now: float,
) -> Enqueued:
    """Decide what a lead scan does: one lead row per (owner, code).

    A synced row means the lead is already in your leads; a pending row is made due
    now; a failed one is pending again, as "Retry failed" would make it. Either keeps
    its first payload and sponsor snapshot. Otherwise a new row snapshots the sponsor.

    Args:
        rows: The outbox rows (any owner's; only ``owner``'s count).
        owner: The signed-in account's lower-cased email.
        code: The attendee's access code.
        payload: The capture request.
        sponsor_id: The sponsor the scan is for now.
        sponsor_name: That sponsor's name.
        now: The current time (epoch seconds).

    Returns:
        ``ALREADY`` with the synced row, ``UPDATED`` with the existing row requeued, or
        ``QUEUED`` with a new row.
    """
    existing = _find(rows, owner, Kind.LEAD, code)
    if existing is None:
        row = Row(
            Kind.LEAD, code, dict(payload), owner, sponsor_id, sponsor_name, now, now
        )
        return Enqueued(Outcome.QUEUED, row)
    if existing.status is Status.SYNCED:
        return Enqueued(Outcome.ALREADY, existing)
    if existing.status is Status.FAILED:
        return Enqueued(Outcome.UPDATED, _requeue(existing, now))
    return Enqueued(Outcome.UPDATED, replace(existing, next_at=now))


def save_note(
    rows: Iterable[Row],
    *,
    owner: str,
    code: str,
    note: str,
    sponsor_id: str | None,
    sponsor_name: str | None,
    now: float,
) -> Enqueued:
    """Decide what saving a lead note does: one note row per (owner, code).

    An empty or blank note is ignored. An existing note row takes the new text and is
    pending from scratch, whatever its status: a synced note was edited, so it is sent
    again. A new row takes its lead's sponsor snapshot when the lead row exists, so a
    sponsor switch between the scan and the note cannot send the note elsewhere;
    otherwise the current sponsor's.

    Args:
        rows: The outbox rows (any owner's; only ``owner``'s count).
        owner: The signed-in account's lower-cased email.
        code: The lead's access code.
        note: The note's text.
        sponsor_id: The sponsor the app scans for now.
        sponsor_name: That sponsor's name.
        now: The current time (epoch seconds).

    Returns:
        ``IGNORED``, ``UPDATED`` with the existing row, or ``QUEUED`` with a new row.
    """
    if not note.strip():
        return Enqueued(Outcome.IGNORED)
    rows = tuple(rows)  # Searched twice: a one-pass iterator would miss the lead.
    payload = {"accessCode": code, "note": note}
    existing = _find(rows, owner, Kind.NOTE, code)
    if existing is not None:
        return Enqueued(
            Outcome.UPDATED, _requeue(replace(existing, payload=payload), now)
        )
    lead = _find(rows, owner, Kind.LEAD, code)
    if lead is not None:
        sponsor_id, sponsor_name = lead.sponsor_id, lead.sponsor_name
    row = Row(Kind.NOTE, code, payload, owner, sponsor_id, sponsor_name, now, now)
    return Enqueued(Outcome.QUEUED, row)


def door_key(code: str, product_ids: Iterable[int | str], session: str) -> str:
    """Return a check-in's idempotency key: ``code|sorted product ids|scan session``.

    Args:
        code: The attendee's access code.
        product_ids: The products admitted.
        session: The scan session (the door screen's visit) the check-in belongs to.

    Returns:
        The key; the same check-in always gives the same one.
    """
    ids = ",".join(sorted(str(product_id) for product_id in product_ids))
    return f"{code}|{ids}|{session}"


def admit(
    rows: Iterable[Row],
    *,
    owner: str,
    code: str,
    product_ids: Iterable[int | str],
    session: str,
    payload: Mapping[str, Any],
    sponsor_id: str | None,
    sponsor_name: str | None,
    now: float,
) -> Enqueued:
    """Decide what a door admission does: one row per check-in.

    A check-in is its idempotency key (``door_key()``), unique across the outbox: the
    same attendee, products and scan session admitted again is the row already queued.
    Any other check-in, for another session say, gets a row of its own (STORE-12).

    Args:
        rows: The outbox rows (every owner's: the key is unique across them).
        owner: The signed-in account's lower-cased email.
        code: The attendee's access code.
        product_ids: The products admitted.
        session: The scan session.
        payload: The redeem request.
        sponsor_id: The sponsor snapshot (None for the door, usually).
        sponsor_name: That sponsor's name.
        now: The current time (epoch seconds).

    Returns:
        ``ALREADY`` with the existing row, or ``QUEUED`` with a new row.
    """
    idem_key = door_key(code, product_ids, session)
    existing = next((r for r in rows if r.idem_key == idem_key), None)
    if existing is not None:
        return Enqueued(Outcome.ALREADY, existing)
    row = Row(
        Kind.DOOR,
        code,
        dict(payload),
        owner,
        sponsor_id,
        sponsor_name,
        now,
        now,
        idem_key=idem_key,
    )
    return Enqueued(Outcome.QUEUED, row)


def _pending(row: Row) -> None:
    """Refuse to send a row that isn't pending: only ``due()`` rows are sent."""
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


def after_network_error(row: Row, now: float) -> Row:
    """Return a row whose send got no answer: still pending, its tries unchanged.

    A ``NetworkError`` is the connection's fault, not the row's, so it is never counted;
    the row waits a tick and the worker ends its pass.

    Args:
        row: The pending row that was sent.
        now: The current time (epoch seconds).

    Returns:
        The row, due again in ``NETWORK_BACKOFF`` seconds.
    """
    _pending(row)
    return replace(row, next_at=now + NETWORK_BACKOFF)


def after_error(row: Row, message: str, now: float) -> Row:
    """Return a row the server refused: one more counted failure.

    The row waits a tick like after a network error; the ``RETRY_CAP``-th counted
    failure makes it ``failed``, until "Retry failed".

    Args:
        row: The pending row that was sent.
        message: The ``ApiError``'s message.
        now: The current time (epoch seconds).

    Returns:
        The row, pending and due in ``NETWORK_BACKOFF`` seconds, or failed.
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
    )


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
    return _requeue(row, now)


def due(rows: Iterable[Row], owner: str, now: float) -> list[Row]:
    """Return the owner's rows to send now, in the order to send them.

    Pending rows whose ``next_at`` has come: leads, then door check-ins, then notes,
    each by ``created_at`` (then id). A note waits until its lead is synced.

    Args:
        rows: The outbox rows (any owner's).
        owner: The signed-in account's lower-cased email.
        now: The current time (epoch seconds).

    Returns:
        The due rows, in send order.
    """
    mine = [r for r in rows if r.owner == owner]
    synced_leads = {
        r.key for r in mine if r.kind is Kind.LEAD and r.status is Status.SYNCED
    }
    ready = [
        r
        for r in mine
        if r.status is Status.PENDING
        and r.next_at <= now
        and (r.kind is not Kind.NOTE or r.key in synced_leads)
    ]
    return sorted(ready, key=lambda r: (SEND_ORDER[r.kind], r.created_at, r.id or 0))


def forget_synced(rows: Iterable[Row], owner: str) -> list[Row]:
    """Return the rows kept when ``owner`` signs out for another account.

    Their synced rows go (the next account must not see "Already in your leads" for
    someone else's leads), except a synced lead whose note hasn't synced: the note
    waits for it, and would wait forever. Their pending and failed rows stay until
    synced or cleared with confirmation, as does every other owner's row.

    Args:
        rows: The outbox rows.
        owner: The previous account's lower-cased email.

    Returns:
        The rows to keep, in their order.
    """
    rows = list(rows)
    waiting = {
        r.key
        for r in rows
        if r.owner == owner and r.kind is Kind.NOTE and r.status is not Status.SYNCED
    }
    return [
        r
        for r in rows
        if r.owner != owner
        or r.status is not Status.SYNCED
        or (r.kind is Kind.LEAD and r.key in waiting)
    ]
