"""The account's leads read from the outbox, for the leads list and its count (#743).

LEAD-08. ``leads()`` returns the signed-in account's ``lead`` rows, newest first, each
with whether a note row exists for its code: pending, failed and synced alike, as
synced rows are kept (D-56), and only that account's (D-414; other accounts' rows stay
in Developer). ``lead_count()`` is the "Leads (42)" button's number. Both return None
when the outbox can't be read (logged by ``OutboxDb``), never an empty list, so the
page says so instead of "No leads yet" (D-120).
"""

from pycon_us.core.outbox import Kind, Row, Status
from pycon_us.services.outbox_db import OutboxDb


def leads(db: OutboxDb | None, owner: str) -> list[tuple[Row, bool]] | None:
    """Return the owner's lead rows newest first, each with whether it has a note.

    Args:
        db: The outbox (``Services.outbox``).
        owner: The signed-in account's lower-cased email.

    Returns:
        ``(row, has_note)`` pairs by ``created_at`` then id, newest first; None when
        there is no outbox or its read failed.
    """
    rows = None if db is None else db.rows(owner, tuple(Status))  # oldest first
    if rows is None:
        return None
    noted = {row.key for row in rows if row.kind is Kind.NOTE}
    return [(row, row.key in noted) for row in reversed(rows) if row.kind is Kind.LEAD]


def lead_count(db: OutboxDb | None, owner: str) -> int | None:
    """Return how many leads the owner has, or None when the outbox can't be read.

    Args:
        db: The outbox (``Services.outbox``).
        owner: The signed-in account's lower-cased email.
    """
    found = leads(db, owner)
    return None if found is None else len(found)
