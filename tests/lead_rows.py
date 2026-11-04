"""Lead rows put straight into a real outbox, in any state, for the leads list's tests.

Shared by `tests/test_lead_views.py` and `tests/test_staff_leads.py`: `add()`
enqueues a lead as a scan does (`scan_lead`), then saves the state a send would
have left it in, and `note()` enqueues its note (`save_note`).
"""

from dataclasses import replace
from functools import partial

from pycon_us.core import outbox, outbox_enqueue
from pycon_us.core.outbox import Row, Status
from pycon_us.services.outbox_db import OutboxDb

OWNER = "a@example.com"


def add(
    db: OutboxDb,
    code: str,
    at: float,
    *,
    owner: str = OWNER,
    status: Status = Status.PENDING,
    name: str | None = None,
    flagged: bool = False,
    sponsor: tuple[str, str] | None = None,
) -> Row:
    """Store a lead for `code` scanned at `at`, left in `status`; return it.

    Args:
        db: The outbox.
        code: The access code.
        at: When it was scanned (epoch seconds).
        owner: The account that scanned it.
        status: Pending, synced (with `name` as the answer's first name) or failed.
        name: The first name a synced lead's answer holds.
        flagged: Its send may have been recorded twice (D-410).
        sponsor: The `(id, name)` a staff account scanned it for.
    """
    decide = partial(
        outbox_enqueue.scan_lead,
        owner=owner,
        code=code,
        payload={"badge_validator": "v"},
        sponsor_id=None if sponsor is None else sponsor[0],
        sponsor_name=None if sponsor is None else sponsor[1],
        now=at,
    )
    enqueued = db.enqueue(code, decide)
    assert enqueued is not None and enqueued.row is not None
    row = enqueued.row
    if status is Status.SYNCED:
        row = outbox.after_success(row, {"first_name": name} if name else {})
    elif status is Status.FAILED:
        row = replace(row, status=Status.FAILED, tries=10, last_error="Not found")
    if row is not enqueued.row:
        assert db.save(row)
    if flagged:
        assert row.id is not None and db.flag_maybe_sent(row.id)
        row = replace(row, maybe_sent=True)
    return row


def note(
    db: OutboxDb,
    code: str,
    text: str,
    *,
    owner: str = OWNER,
    sponsor: tuple[str, str] | None = None,
) -> None:
    """Store `text` as the account's note on the lead `code` for `sponsor`."""
    decide = partial(
        outbox_enqueue.save_note,
        owner=owner,
        code=code,
        note=text,
        sponsor_id=None if sponsor is None else sponsor[0],
        sponsor_name=None if sponsor is None else sponsor[1],
        now=0.0,
    )
    assert db.enqueue(code, decide) is not None
