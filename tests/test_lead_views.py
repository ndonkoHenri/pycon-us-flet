"""Tests for the leads list's data: ``lead_list.py``'s reads, ``core/lead_views.py``.

LEAD-06, LEAD-08 (#743). The reads run against a real ``outbox.db`` in a temp dir;
``lead_view()``, ``phrase()`` and ``filter_leads()`` are pure.
"""

from dataclasses import replace

import pytest

from pycon_us.core.lead_views import LeadView, filter_leads, lead_view, phrase
from pycon_us.core.outbox import Kind, Status
from pycon_us.lead_list import lead_count, leads
from pycon_us.services.outbox_db import OutboxDb
from tests.lead_rows import OWNER, add, note
from tests.sync_rig import outbox_db

db = outbox_db

NOW = 10_000.0


def test_leads_are_newest_first_with_their_note_flag(db: OutboxDb) -> None:
    """Every lead row of the account, newest first; a note row flags its lead only."""
    add(db, "OLD", 100.0, status=Status.SYNCED, name="Ada")
    add(db, "MID", 200.0, status=Status.FAILED)
    add(db, "NEW", 300.0)
    note(db, "OLD", "Interest: warm")
    found = leads(db, OWNER)
    assert found is not None
    assert [(row.key, has_note) for row, has_note in found] == [
        ("NEW", False),
        ("MID", False),
        ("OLD", True),
    ]
    assert all(row.kind is Kind.LEAD for row, _ in found)
    assert lead_count(db, OWNER) == 3


def test_another_account_s_rows_never_show(db: OutboxDb) -> None:
    """A lead and a note of another owner are not this account's (D-414)."""
    add(db, "MINE", 100.0)
    add(db, "THEIRS", 200.0, owner="b@example.com")
    note(db, "MINE", "Notes: theirs", owner="b@example.com")
    found = leads(db, OWNER)
    assert [(row.key, has_note) for row, has_note in found or []] == [("MINE", False)]
    assert lead_count(db, "c@example.com") == 0


def test_a_failed_read_is_none_never_an_empty_list(db: OutboxDb) -> None:
    """No outbox, or a closed one, reads None: the page says so (D-120)."""
    assert leads(None, OWNER) is None
    assert lead_count(None, OWNER) is None
    db.close()
    assert leads(db, OWNER) is None


def test_each_status_has_its_words_and_a_pending_lead_only_its_code(
    db: OutboxDb,
) -> None:
    """Queued, Failed, Confirmed with the first name, and the flag's words."""
    queued = add(db, "Q1", NOW - 30)
    failed = add(db, "F1", NOW - 120, status=Status.FAILED)
    confirmed = add(db, "C1", NOW - 300, status=Status.SYNCED, name="Ada")
    flagged = add(db, "T1", NOW - 7200, status=Status.SYNCED, name="Bo", flagged=True)
    views = [lead_view(row, False, NOW) for row in (queued, failed, confirmed, flagged)]
    assert [(v.title, v.words, v.ago, v.flagged) for v in views] == [
        ("Q1", "Queued", "just now", False),
        ("F1", "Failed", "2 minutes ago", False),
        ("Ada", "Confirmed", "5 minutes ago", False),
        ("Bo", "Confirmed · may be recorded twice", "2 hours ago", True),
    ]
    assert views[0].name is None  # PII-light: a pending lead has only its code


def test_a_row_reads_as_one_phrase(db: OutboxDb) -> None:
    """Name, status, time, sponsor and note, the flag in words too (ux.md §9)."""
    row = add(db, "C1", NOW - 300, status=Status.SYNCED, name="Ada")
    assert phrase(lead_view(row, True, NOW)) == (
        "Ada, Confirmed, 5 minutes ago, has a note"
    )
    staff_row = replace(
        row, sponsor_id="1", sponsor_name="Example Corp", maybe_sent=True
    )
    assert phrase(lead_view(staff_row, False, NOW)) == (
        "Ada, Confirmed, may be recorded twice, 5 minutes ago, Example Corp"
    )


def view(code: str, name: str | None = None, sponsor: str | None = None) -> LeadView:
    """A confirmed lead's view, for the filter's tests."""
    return LeadView(
        code=code,
        name=name,
        status=Status.SYNCED,
        words="Confirmed",
        flagged=False,
        ago="just now",
        sponsor_id=sponsor,
        sponsor_name=None,
        has_note=False,
    )


@pytest.mark.parametrize(
    ("query", "found"),
    [
        ("", ["MOCK0001", "MOCK0002", "MOCK0003"]),
        ("ada", ["MOCK0001"]),
        ("  GRÂCE ", ["MOCK0002"]),  # folded as search folds (D-46)
        ("mock0003", ["MOCK0003"]),
        ("0001 ada", ["MOCK0001"]),  # every word, in the name or the code
        ("zzz", []),
    ],
)
def test_search_matches_the_name_or_the_code(query: str, found: list[str]) -> None:
    """Each word anywhere in the name or the code; the order is kept."""
    views = [view("MOCK0001", "Ada"), view("MOCK0002", "Grace"), view("MOCK0003")]
    assert [v.code for v in filter_leads(views, query, None)] == found


def test_the_sponsor_filter_compares_ids_not_names() -> None:
    """Two sponsors whose names differ only by quotes stay apart (LEAD-06)."""
    views = [
        replace(view("A1", sponsor="1"), sponsor_name="Example Corp"),
        replace(view("B1", sponsor="2"), sponsor_name='"Example Corp"'),
        view("C1"),
    ]
    assert [v.code for v in filter_leads(views, "", "1")] == ["A1"]
    assert [v.code for v in filter_leads(views, "", "2")] == ["B1"]
    assert [v.code for v in filter_leads(views, "", None)] == ["A1", "B1", "C1"]
