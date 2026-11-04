"""What happens to staff data on an account switch and on Clear staff data (D-56, D-414).

Never drop an unsynced row without asking (P3 exit criterion 2), never show or send one
account's rows as another's, and leave nothing of a previous account's staff choices
behind. Ionic kept scan queues and the staff sponsor across a sign-out and shared them
with the next person, and its "Clear scan data" missed the door-check keys.

- **An account switch:** when a signed-in account's sync starts, every other account's
  synced rows are deleted (`OutboxDb.forget_other_accounts()`, architecture §12.1);
  their pending and failed rows stay, under their owner, until that owner signs in
  again or Clear staff data deletes them. `Account` removes the staff keys
  (`STAFF_PREFIX`) at a sign-out and at a sign-in as someone else.
- **Clear staff data** (Developer › Data, DEV-03) and **Reset app** delete every row of
  every account and the staff keys, after a confirmation that names how many rows have
  not synced (`clear_staff_data()`).

`outbox-<year>.db` is opened only where staff tools run (D-51): `staff_counts()`
answers zeros without opening a file that was never created. Another year's file is left
alone, unsynced rows and all: this year's server would misattribute them, and no
confirmation names them (D-466).
"""

import logging

from pycon_us.services.outbox_db import Counts, OutboxDb
from pycon_us.services.pref_keys import STAFF_PREFIX
from pycon_us.services.storage import Storage
from pycon_us.staff import Staff

logger = logging.getLogger(__name__)


def unsynced(counts: Counts | Staff) -> int:
    """Return how many rows have not reached the server: pending and failed ones."""
    return counts.pending + counts.failed


def staff_counts(db: OutboxDb | None) -> Counts | None:
    """Return every account's rows by status, for Clear staff data and Reset app.

    Args:
        db: The outbox, or None where the session has none.

    Returns:
        The counts; zeros without opening the file when it was never created
        (D-51); None when it can't be read (logged, D-120).
    """
    if db is None or not db.path.exists():
        return Counts()
    return db.counts(None)


async def clear_staff_data(
    db: OutboxDb | None, storage: Storage, staff: Staff, *, named: bool = True
) -> bool:
    """Delete every account's rows and every staff key, then zero `Staff`'s counts.

    The caller has confirmed it, naming how many rows have not synced (DEV-03); rows
    that can't be counted now, or that the confirmation couldn't count (`named`),
    are not deleted, as no confirmation named them. The sync's own state (a pass
    under way, the last error) stays: a pass under way finds its rows gone, so it
    sends none of them and saves nothing.

    Args:
        db: The outbox, or None where the session has none.
        storage: Where the staff keys are.
        staff: The `Staff` store, whose counts drop to zero.
        named: Whether the confirmation named the rows; False when it said it
            couldn't read them, so they stay (Reset app's, D-414).

    Returns:
        Whether everything was deleted; a failure is logged (D-120).
    """
    # Unreadable rows stay: their confirmation could not say how many (D-414).
    counted = named and staff_counts(db) is not None
    rows = counted and (db is None or not db.path.exists() or db.clear())
    keys = await storage.clear_prefs(STAFF_PREFIX)
    staff.update_counts(Counts() if rows else None)
    logger.info("Staff data cleared: %s", "done" if rows and keys else "partly")
    return rows and keys
