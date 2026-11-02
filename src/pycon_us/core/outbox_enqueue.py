"""The staff outbox's enqueue decisions: what a lead scan, a note or an admission does.

The pure half of the outbox's rules that a capture runs (``core/outbox.py`` has the rows
and what a send does to them; D-56, D-77). Each function takes rows and returns an
``Enqueued``; ``services/outbox_db.py`` stores what it decides. A lead belongs to a
sponsor, so an account keeps one lead row and one note row per (owner, code, sponsor
id); a sponsor's own account has one sponsor id, None (D-459).
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any

from pycon_us.core.outbox import Kind, Row, Status, requeue


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
        others: A lead scan's: the names of the other sponsors this account has the
            attendee in its leads for, so the result can say so (D-459).
    """

    outcome: Outcome
    row: Row | None = None
    others: tuple[str, ...] = ()


def _find(
    rows: Iterable[Row], owner: str, kind: Kind, key: str, sponsor_id: str | None
) -> Row | None:
    """Return the owner's row of a kind for an access code and a sponsor, if any."""
    wanted = (owner, kind, key, sponsor_id)
    return next(
        (r for r in rows if (r.owner, r.kind, r.key, r.sponsor_id) == wanted), None
    )


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
    """Decide what a lead scan does: one lead row per (owner, code, sponsor) (D-459).

    A lead belongs to its sponsor, so only this sponsor's row counts. A synced row
    means the lead is already in your leads; a pending row is made due now; a failed
    one is pending again, as "Retry failed" would make it. Either keeps its first
    payload. Otherwise a new row snapshots the sponsor, even if the attendee is a lead
    for another sponsor: that lead's row stays as it is, and ``others`` names it.

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
        ``QUEUED`` with a new row; each with ``others``.
    """
    rows = tuple(rows)  # Searched twice: a one-pass iterator would miss the row.
    others = tuple(
        r.sponsor_name
        for r in rows
        if r.owner == owner
        and r.kind is Kind.LEAD
        and r.key == code
        and r.sponsor_id != sponsor_id
        and r.sponsor_name
    )
    existing = _find(rows, owner, Kind.LEAD, code, sponsor_id)
    if existing is None:
        row = Row(
            Kind.LEAD, code, dict(payload), owner, sponsor_id, sponsor_name, now, now
        )
        return Enqueued(Outcome.QUEUED, row, others)
    if existing.status is Status.SYNCED:
        return Enqueued(Outcome.ALREADY, existing, others)
    if existing.status is Status.FAILED:
        return Enqueued(Outcome.UPDATED, requeue(existing, now), others)
    return Enqueued(Outcome.UPDATED, replace(existing, next_at=now), others)


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
    """Decide what saving a lead note does: one note row per (owner, code, sponsor).

    An empty or blank note is ignored. An existing note row takes the new text and is
    pending from scratch, whatever its status: a synced note was edited, so it is sent
    again. A new row snapshots the sponsor of the lead it is for, which the caller
    takes from that lead's row or result, never from the sponsor chosen now, so a
    switch between the scan and the note cannot send the note elsewhere (D-459).

    Args:
        rows: The outbox rows (any owner's; only ``owner``'s count).
        owner: The signed-in account's lower-cased email.
        code: The lead's access code.
        note: The note's text.
        sponsor_id: The sponsor of the lead the note is for.
        sponsor_name: That sponsor's name.
        now: The current time (epoch seconds).

    Returns:
        ``IGNORED``, ``UPDATED`` with the existing row, or ``QUEUED`` with a new row.
    """
    if not note.strip():
        return Enqueued(Outcome.IGNORED)
    payload = {"accessCode": code, "note": note}
    existing = _find(rows, owner, Kind.NOTE, code, sponsor_id)
    if existing is not None:
        return Enqueued(
            Outcome.UPDATED, requeue(replace(existing, payload=payload), now)
        )
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
