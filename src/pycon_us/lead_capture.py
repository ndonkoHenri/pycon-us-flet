"""A lead scan through the outbox, with its result at once (#741; LEAD-07, LEAD-09).

``capture()`` is the Lead scanner's ``on_badge``. It enqueues the scan as a ``lead``
row (``core/outbox.py``'s ``scan_lead``, one row per owner, code and sponsor, D-459), so
it survives airplane mode and a kill (D-56); the row keeps the sponsor it was scanned
for (STORE-11), and a staff account's result says which sponsor that is, and any other
it has the attendee in its leads for. It then kicks the ``SyncWorker``, which stays the
only sender (D-407), waits up to ``WAIT_SECONDS`` for the worker's pass to take the row, and reads the row
back by id: its state is the result (D-426). A ``Staff`` change marks each step of a
pass, so the wait is driven by the worker's reports, never by polling (LEAD-09).
"""

import asyncio
import time
from collections.abc import Callable
from dataclasses import replace
from functools import partial
from typing import cast

import flet as ft

from pycon_us.core.badges import Badge, ScanOutcome, ScanResult
from pycon_us.core.lead_sponsors import LeadSponsor, snapshot
from pycon_us.core.lead_views import first_name, for_line
from pycon_us.core.outbox import Outcome, Row, Status, scan_lead
from pycon_us.services.outbox_db import OutboxDb
from pycon_us.staff import Staff

WAIT_SECONDS = 3.0
"""How long a scan waits for the worker: the capture's 2 s timeout, plus margin."""

CAPTURED = "Lead captured"
ALREADY = "Already in your leads"
SAVED = "Saved. Will sync."
NOT_CAPTURED = "Not captured"
NOT_CONFIRMED = "Not confirmed"
"""Each outcome's word (ux.md §7.3)."""

WILL_RETRY = "It will retry. See the sync queue."
RETRY_FROM_QUEUE = "Retry it from the sync queue."
NOT_SAVED = "Couldn't save this scan on this device."
MAY_BE_TWICE = "May be recorded twice"
"""Detail lines: a refusal's next step, a failed save (D-120), a lost answer (D-410)."""

ALSO_FOR = "Also in your leads for"
"""A detail line's start, before the other sponsors a staff lead is for (D-459)."""


async def capture(
    db: OutboxDb | None,
    staff: Staff,
    kick: Callable[[], object],
    badge: Badge,
    *,
    owner: str,
    sponsor: LeadSponsor | None,
    clock: Callable[[], float] = time.time,
) -> ScanResult:
    """Queue a lead scan, let the worker send it, and say how it went.

    Args:
        db: The outbox (``Services.outbox``); None says the scan couldn't be saved.
        staff: The ``Staff`` store: its counts are updated, and its changes end
            the wait.
        kick: Asks the worker for a pass (``Services.kick_sync``).
        badge: The badge scanned; the lead's validator is its last segment. Last of
            the positional arguments, so the screen passes a ``functools.partial``
            of the others as its ``on_badge``.
        owner: The signed-in account's lower-cased email.
        sponsor: The sponsor a staff account scans for; None for a sponsor's own.
        clock: The time of the scan, epoch seconds as the worker's (D-407).

    Returns:
        The result panel's answer, from the row as the wait left it.
    """
    decide = partial(
        scan_lead,
        owner=owner,
        code=badge.code,
        payload={"badge_validator": badge.lead_validator},
        sponsor_id=None if sponsor is None else sponsor.id,
        sponsor_name=None if sponsor is None else sponsor.name,
        now=clock(),
    )
    enqueued = None if db is None else db.enqueue(badge.code, decide)
    if db is None or enqueued is None or enqueued.row is None:  # logged (D-120)
        return ScanResult(
            ScanOutcome.DENIED, NOT_CAPTURED, badge.code, (NOT_SAVED,), badge.code
        )
    row = enqueued.row
    if enqueued.outcome is Outcome.ALREADY:
        result = named(ScanOutcome.DUPLICATE, ALREADY, row)
    else:
        staff.update_counts(db.counts(owner))
        result = result_of(row, await sent(db, staff, kick, row))
    return attributed(result, row, enqueued.others)


def attributed(result: ScanResult, row: Row, others: tuple[str, ...]) -> ScanResult:
    """Return a result that says who its lead is for, and who else has it (D-459).

    A staff account's result gets "For Example Corp" first, then "Also in your leads
    for Sample Systems" when the attendee is a lead for another sponsor too, so a
    scan for the wrong sponsor shows at once. A sponsor's own lead has neither.

    Args:
        result: The scan's result.
        row: The lead row it is about.
        others: The other sponsors' names (``Enqueued.others``).
    """
    lines = (for_line(row.sponsor_name),) if row.sponsor_name else ()
    also = (f"{ALSO_FOR} {', '.join(others)}",) if others else ()
    return replace(
        result,
        details=(*lines, *also, *result.details),
        sponsor=snapshot(row.sponsor_id, row.sponsor_name),
    )


async def sent(
    db: OutboxDb, staff: Staff, kick: Callable[[], object], row: Row
) -> Row | None:
    """Kick the worker and return the row once a send has moved it, or at the limit.

    Each ``Staff`` change (a pass starting, its report) reads the row again; it stops
    as soon as the row is synced, failed, counted a refusal or put off after a
    network error, or after ``WAIT_SECONDS`` (a backlog, no worker): the row as it is.

    Args:
        db: The outbox.
        staff: The ``Staff`` store the worker reports to.
        kick: Asks the worker for a pass.
        row: The row just enqueued, stored (with its id).

    Returns:
        The row read back, or None when it is gone or can't be read (logged).
    """
    assert row.id is not None  # an enqueued row is a stored one
    changed = asyncio.Event()

    def on_change(_sender: object, _name: str | None) -> None:
        changed.set()

    # Held in this frame while it waits: the store keeps its listeners weakly.
    stop = cast(ft.Observable, staff).subscribe(on_change)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + WAIT_SECONDS
    try:
        kick()
        while True:
            changed.clear()  # before the read: a change after it wakes the wait
            after = db.row(row.id)
            if after is None or moved(row, after):
                return after
            try:
                await asyncio.wait_for(changed.wait(), deadline - loop.time())
            except TimeoutError:
                return db.row(row.id)
    finally:
        stop()


def moved(before: Row, after: Row) -> bool:
    """Whether a send has changed the row since its enqueue: its outcome is known.

    A success syncs it; a refusal counts a try (the tenth fails it); a network
    error, or a refused key, puts it off a tick (``next_at``).
    """
    return (
        after.status is not Status.PENDING
        or after.tries != before.tries
        or after.next_at > before.next_at
    )


def result_of(before: Row, after: Row | None) -> ScanResult:
    """Return what a scan shows, from its row before and after the wait (D-426).

    Synced: "Lead captured" with the name. Refused in this pass: "Not captured", the
    server's message and "It will retry"; failed: "Retry it from the sync queue".
    Still waiting (offline, a backlog, the wait ran out, the row unreadable):
    "Saved. Will sync.". A row whose answer was lost or could not be read adds "May be
    recorded twice", and "Not confirmed" replaces "Not captured": it may be on record.

    Args:
        before: The row as enqueued.
        after: The row read back, or None.
    """
    if after is None or (
        after.status is Status.PENDING and after.tries == before.tries
    ):
        flags = () if after is None else flag(after)
        return ScanResult(ScanOutcome.QUEUED, SAVED, before.key, flags, before.key)
    if after.status is Status.SYNCED:
        return named(ScanOutcome.ACCEPTED, CAPTURED, after)
    message = (after.last_error,) if after.last_error else ()
    then = RETRY_FROM_QUEUE if after.status is Status.FAILED else WILL_RETRY
    details = (*message, then, *flag(after))
    word = NOT_CONFIRMED if after.maybe_sent else NOT_CAPTURED  # it may be on record
    return ScanResult(ScanOutcome.DENIED, word, after.key, details, after.key)


def named(outcome: ScanOutcome, word: str, row: Row) -> ScanResult:
    """Return a synced lead's result: the attendee's first name, then the code.

    Without a name in the server's answer, the code is the title.
    """
    name = first_name(row)
    if name is None:
        return ScanResult(outcome, word, row.key, flag(row), row.key)
    return ScanResult(outcome, word, name, (row.key, *flag(row)), row.key)


def flag(row: Row) -> tuple[str, ...]:
    """Return "May be recorded twice" for a row resent after a lost answer (D-410)."""
    return (MAY_BE_TWICE,) if row.maybe_sent else ()
