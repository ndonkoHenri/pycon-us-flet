"""A lead note through the outbox: the note saved for a lead, and saving one (#742).

LEAD-10, LEAD-11. The note sheet (``ui/lead_note_sheet.py``) prefills from
``saved_note()``: the account's note row for the lead, pending, failed or synced, its
text parsed (``core/lead_notes.parse``). Its Save calls ``store()``, which enqueues the
composed text as the lead's one ``note`` row (``core/outbox.save_note``: a blank note
is ignored, an edit is sent again, the row keeps its lead's sponsor), then
``confirm()``, which kicks the worker and says how it went: "Note saved" once the note
has synced, "Note saved. Will sync." while it is queued. A note waits for its lead
(D-56), so a note on a lead still queued is said at once, without a wait; otherwise
the wait is the capture's (``lead_capture.sent()``, at most ``WAIT_SECONDS``), driven
by the worker's reports. The ``SyncWorker`` stays the only sender (D-407).
"""

import time
from collections.abc import Callable
from functools import partial

from pycon_us.core.lead_notes import LeadNote, compose, parse
from pycon_us.core.lead_sponsors import LeadSponsor
from pycon_us.core.outbox import Enqueued, Kind, Row, Status, save_note
from pycon_us.lead_capture import sent
from pycon_us.services.outbox_db import OutboxDb
from pycon_us.staff import Staff

NOTE_SAVED = "Note saved"
WILL_SYNC = "Note saved. Will sync."
NOTHING_TO_SAVE = "Nothing to save"
"""The SnackBar after Save: synced, still queued, or an empty note (ignored)."""

NOT_SAVED = "Couldn't save this note on this device."
"""The sheet's line when the outbox can't store the note (D-120); the sheet stays."""


def lead_rows(db: OutboxDb | None, owner: str, code: str) -> list[Row]:
    """Return the account's rows for one lead (its lead and note rows), oldest first.

    Args:
        db: The outbox; None, or a failed read (logged), gives no rows.
        owner: The signed-in account's lower-cased email.
        code: The lead's access code.
    """
    rows = None if db is None else db.rows(owner, tuple(Status))
    return [row for row in rows or () if row.key == code]


def find(rows: list[Row], kind: Kind) -> Row | None:
    """Return the row of a kind among one lead's rows, if there is one."""
    return next((row for row in rows if row.kind is kind), None)


def saved_note(db: OutboxDb | None, owner: str, code: str) -> LeadNote:
    """Return the note saved for a lead, parsed; an empty one when there is none.

    Args:
        db: The outbox.
        owner: The signed-in account's lower-cased email.
        code: The lead's access code.
    """
    row = find(lead_rows(db, owner, code), Kind.NOTE)
    text = None if row is None else row.payload.get("note")
    return parse(text) if isinstance(text, str) else LeadNote()


def store(
    db: OutboxDb | None,
    code: str,
    note: LeadNote,
    *,
    owner: str,
    sponsor: LeadSponsor | None,
    clock: Callable[[], float] = time.time,
) -> Enqueued | None:
    """Enqueue a lead's note as its composed text (``save_note``).

    Args:
        db: The outbox (``Services.outbox``).
        code: The lead's access code.
        note: The note as the sheet left it.
        owner: The signed-in account's lower-cased email.
        sponsor: The sponsor a staff account scans for now; the row takes its lead's
            snapshot instead whenever the lead row exists. None for a sponsor's own.
        clock: The time of the save, epoch seconds as the worker's (D-407).

    Returns:
        The decision: ``IGNORED`` for an empty note, else the stored row. None when
        the outbox could not store it (logged, D-120).
    """
    if db is None:
        return None
    decide = partial(
        save_note,
        owner=owner,
        code=code,
        note=compose(note),
        sponsor_id=None if sponsor is None else sponsor.id,
        sponsor_name=None if sponsor is None else sponsor.name,
        now=clock(),
    )
    return db.enqueue(code, decide)


async def confirm(
    db: OutboxDb, staff: Staff, kick: Callable[[], object], row: Row
) -> str:
    """Update the counts, let the worker send the note, and say how it went.

    Args:
        db: The outbox.
        staff: The ``Staff`` store: its counts, and its changes end the wait.
        kick: Asks the worker for a pass (``Services.kick_sync``).
        row: The note row ``store()`` stored.

    Returns:
        ``NOTE_SAVED`` once synced, else ``WILL_SYNC``: the lead is still queued,
        offline, or the wait ran out.
    """
    staff.update_counts(db.counts(row.owner))
    lead = find(lead_rows(db, row.owner, row.key), Kind.LEAD)
    if lead is None or lead.status is not Status.SYNCED:
        kick()  # the lead's own send may be due; the note follows it (D-56)
        return WILL_SYNC
    after = await sent(db, staff, kick, row)
    synced = after is not None and after.status is Status.SYNCED
    return NOTE_SAVED if synced else WILL_SYNC
