"""The outbox's rules (architecture §12.2): one test per table row, then the due order.

The hypothesis state machine that checks the invariants over any sequence of these
is ``tests/test_outbox_machine.py`` (D-77).
"""

from dataclasses import replace

import pytest

from pycon_us.core import outbox
from pycon_us.core.outbox import Kind, Outcome, Row, Status

OWNER = "staff@example.com"
NOW = 1_000_000.0


def stored(row: Row | None, row_id: int) -> Row:
    """Return a decision's row as the db would store it, with its id."""
    assert row is not None
    return replace(row, id=row_id)


def lead(
    code: str = "A1", *, status: Status = Status.PENDING, **changes: object
) -> Row:
    """Return a stored lead row for ``code``, scanned at ``NOW`` for sponsor 7."""
    row = Row(Kind.LEAD, code, {"code": code}, OWNER, "7", "Acme", NOW, NOW, status)
    return replace(row, **{"id": 1, **changes})


def scan(rows: list[Row], code: str = "A1", sponsor: str = "7", now: float = NOW):
    """Scan ``code`` for ``sponsor`` as ``OWNER``."""
    return outbox.scan_lead(
        rows,
        owner=OWNER,
        code=code,
        payload={"code": code},
        sponsor_id=sponsor,
        sponsor_name=f"Sponsor {sponsor}",
        now=now,
    )


def note(rows: list[Row], text: str, code: str = "A1", now: float = NOW):
    """Save ``text`` as the note on ``code``, as ``OWNER`` scanning for sponsor 9."""
    return outbox.save_note(
        rows,
        owner=OWNER,
        code=code,
        note=text,
        sponsor_id="9",
        sponsor_name="Other",
        now=now,
    )


def admit(rows: list[Row], products: list[int], session: str = "s1"):
    """Admit attendee ``A1`` to ``products`` in ``session`` as ``OWNER``."""
    return outbox.admit(
        rows,
        owner=OWNER,
        code="A1",
        product_ids=products,
        session=session,
        payload={"products": products},
        sponsor_id=None,
        sponsor_name=None,
        now=NOW,
    )


def test_lead_already_synced_adds_nothing() -> None:
    """A scan of a lead already synced says "already in your leads" and stores nothing."""
    synced = lead(status=Status.SYNCED)
    assert scan([synced]) == outbox.Enqueued(Outcome.ALREADY, synced)


def test_lead_pending_is_due_now_and_keeps_its_snapshot() -> None:
    """A scan of a pending lead makes it due now; payload and sponsor stay as queued."""
    waiting = lead(next_at=NOW + 60)
    decision = scan([waiting], sponsor="8", now=NOW + 5)
    assert decision == outbox.Enqueued(
        Outcome.UPDATED, replace(waiting, next_at=NOW + 5)
    )


def test_lead_failed_is_pending_again() -> None:
    """A scan of a failed lead requeues it as "Retry failed" would, keeping its sponsor."""
    failed = lead(status=Status.FAILED, tries=10, last_error="500 down", next_at=NOW)
    decision = scan([failed], sponsor="8", now=NOW + 5)
    assert decision.outcome is Outcome.UPDATED
    assert decision.row == replace(
        failed, status=Status.PENDING, tries=0, last_error=None, next_at=NOW + 5
    )


def test_new_lead_snapshots_the_sponsor() -> None:
    """A first scan queues a pending row due now, with the owner and current sponsor."""
    other_owner = replace(lead(), owner="else@example.com")
    decision = scan([other_owner], code="A1", sponsor="8")
    assert decision == outbox.Enqueued(
        Outcome.QUEUED,
        Row(Kind.LEAD, "A1", {"code": "A1"}, OWNER, "8", "Sponsor 8", NOW, NOW),
    )


def test_empty_note_is_ignored() -> None:
    """An empty or blank note stores nothing."""
    assert note([lead()], "") == outbox.Enqueued(Outcome.IGNORED)
    assert note([lead()], " \n ") == outbox.Enqueued(Outcome.IGNORED)


def test_new_note_takes_its_leads_sponsor() -> None:
    """A first note queues one row with Ionic's body and its lead's sponsor snapshot."""
    decision = note([lead()], "Hot")
    assert decision == outbox.Enqueued(
        Outcome.QUEUED,
        Row(
            Kind.NOTE,
            "A1",
            {"accessCode": "A1", "note": "Hot"},
            OWNER,
            "7",
            "Acme",
            NOW,
            NOW,
        ),
    )


def test_note_without_a_lead_row_takes_the_current_sponsor() -> None:
    """A note on a code with no local lead row snapshots the sponsor scanned for now."""
    decision = note([], "Hot")
    assert decision.row is not None
    assert (decision.row.sponsor_id, decision.row.sponsor_name) == ("9", "Other")


@pytest.mark.parametrize("status", list(Status))
def test_note_upserts_one_row_per_lead(status: Status) -> None:
    """Saving again rewrites the one note row, pending from scratch, whatever its status."""
    first = stored(note([lead()], "Warm").row, 2)
    earlier = replace(first, status=status, tries=3, last_error="x", next_at=NOW + 60)
    decision = note([lead(), earlier], "Hot", now=NOW + 9)
    assert decision == outbox.Enqueued(
        Outcome.UPDATED,
        replace(
            first,
            payload={"accessCode": "A1", "note": "Hot"},
            next_at=NOW + 9,
        ),
    )


def test_door_admit_has_a_unique_idempotency_key() -> None:
    """A check-in queues a row keyed by code, sorted product ids and scan session."""
    decision = admit([], [12, 3])
    assert decision.outcome is Outcome.QUEUED
    assert decision.row is not None
    assert decision.row.idem_key == "A1|12,3|s1"
    assert decision.row.kind is Kind.DOOR
    assert decision.row.status is Status.PENDING


def test_door_one_row_per_check_in() -> None:
    """The same check-in again is the queued row; another session gets its own row."""
    first = stored(admit([], [3, 12]).row, 1)
    assert admit([first], [12, 3]) == outbox.Enqueued(Outcome.ALREADY, first)
    assert admit([first], [3, 12], session="s2").outcome is Outcome.QUEUED


def test_sent_row_is_synced_with_the_result_merged() -> None:
    """A successful send marks the row synced and keeps the answer in its payload."""
    sent = outbox.after_success(lead(last_error="earlier"), {"first_name": "Ada"})
    assert sent == replace(
        lead(),
        status=Status.SYNCED,
        payload={"code": "A1", "result": {"first_name": "Ada"}},
    )


def test_network_error_waits_without_counting() -> None:
    """A ``NetworkError`` leaves tries alone and makes the row due a minute later."""
    assert outbox.after_network_error(lead(tries=4), NOW) == lead(
        tries=4, next_at=NOW + outbox.NETWORK_BACKOFF
    )


def test_api_error_counts_and_fails_at_the_cap() -> None:
    """Each ``ApiError`` counts; the tenth makes the row failed, not before."""
    row = lead()
    for tries in range(1, outbox.RETRY_CAP + 1):
        row = outbox.after_error(row, f"500 #{tries}", NOW)
        assert (row.tries, row.last_error) == (tries, f"500 #{tries}")
        assert row.next_at == NOW + outbox.NETWORK_BACKOFF
        assert row.status is (Status.FAILED if tries == 10 else Status.PENDING)


def test_retry_failed_is_pending_from_scratch() -> None:
    """Retrying a failed row makes it pending, uncounted and due now."""
    failed = lead(status=Status.FAILED, tries=10, last_error="500", next_at=NOW)
    assert outbox.retry_failed(failed, NOW + 1) == lead(next_at=NOW + 1)


@pytest.mark.parametrize("status", [Status.SYNCED, Status.FAILED])
def test_only_pending_rows_are_sent(status: Status) -> None:
    """Every send transition refuses a row that isn't pending."""
    row = lead(status=status)
    for transition in (
        lambda: outbox.after_success(row, {}),
        lambda: outbox.after_network_error(row, NOW),
        lambda: outbox.after_error(row, "x", NOW),
    ):
        with pytest.raises(ValueError, match="not pending"):
            transition()


@pytest.mark.parametrize("status", [Status.PENDING, Status.SYNCED])
def test_retry_failed_refuses_other_rows(status: Status) -> None:
    """Only a failed row can be retried."""
    with pytest.raises(ValueError, match="not failed"):
        outbox.retry_failed(lead(status=status), NOW)


def test_due_order_leads_then_door_then_notes() -> None:
    """Due rows come leads first, then door, then notes, each oldest first, then by id."""
    rows = [
        lead("B", status=Status.SYNCED, id=1),
        replace(lead("B"), kind=Kind.NOTE, created_at=NOW - 9, id=2),
        replace(lead("C"), kind=Kind.DOOR, idem_key="C||s", created_at=NOW - 8, id=3),
        lead("D", created_at=NOW - 1, id=5),
        lead("E", created_at=NOW - 1, id=4),
        lead("F", created_at=NOW, id=6),
    ]
    assert [r.id for r in outbox.due(rows, OWNER, NOW)] == [4, 5, 6, 3, 2]


def test_due_skips_what_isnt_ready() -> None:
    """Not due: later rows, synced or failed rows, other owners' and unsynced leads' notes."""
    rows = [
        lead("A", next_at=NOW + 1, id=1),
        lead("B", status=Status.SYNCED, id=2),
        lead("C", status=Status.FAILED, id=3),
        replace(lead("D"), owner="else@example.com", id=4),
        lead("E", id=5),
        replace(lead("E"), kind=Kind.NOTE, id=6),
        replace(lead("B"), kind=Kind.NOTE, owner="else@example.com", id=7),
    ]
    assert [r.id for r in outbox.due(rows, OWNER, NOW)] == [5]


def test_forget_synced_keeps_what_isnt_on_the_server() -> None:
    """An account switch drops the old owner's synced rows, but not a waiting note's lead."""
    rows = [
        lead("A", status=Status.SYNCED, id=1),
        lead("B", status=Status.SYNCED, id=2),
        replace(lead("B"), kind=Kind.NOTE, id=3),
        lead("C", status=Status.FAILED, id=4),
        lead("D", id=5),
        replace(lead("E", status=Status.SYNCED), owner="else@example.com", id=6),
    ]
    assert [r.id for r in outbox.forget_synced(rows, OWNER)] == [2, 3, 4, 5, 6]
