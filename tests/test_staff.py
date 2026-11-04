"""The `Staff` store: the outbox's counts, the pass under way and its context (#692)."""

import flet as ft
import pytest

from pycon_us import staff as staff_module
from pycon_us.services.outbox_db import Counts
from pycon_us.staff import Staff, use_staff
from tests.accounts import Changes


def test_update_counts_takes_the_counts_in_and_bumps_the_revision() -> None:
    """Each call is a change of the rows: the counts follow, and lists re-read."""
    store = Staff()
    store.update_counts(Counts(pending=2, failed=1, synced=5))
    assert (store.pending, store.failed, store.synced) == (2, 1, 5)
    assert store.revision == 1


def test_a_failed_count_keeps_the_counts_shown_but_still_bumps() -> None:
    """A database that failed (None) never zeroes the counts sign-out reads (D-120)."""
    store = Staff(pending=3)
    store.update_counts(None)
    assert store.pending == 3
    assert store.revision == 1


def test_clear_forgets_counts_and_the_last_pass_and_notifies() -> None:
    """Signed out, nothing of the last account's outbox shows."""
    store = Staff(
        pending=1,
        failed=2,
        synced=3,
        syncing=True,
        last_sync_at=9.0,
        last_error="x",
        offline=True,
    )
    listener = Changes()
    assert isinstance(store, ft.Observable)
    store.subscribe(listener)
    store.clear()
    assert (
        store.pending,
        store.failed,
        store.synced,
        store.syncing,
        store.last_sync_at,
        store.last_error,
        store.offline,
    ) == (0, 0, 0, False, None, None, False)
    assert "revision" in listener.fields


def test_use_staff_needs_a_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without `StaffCtx` above it, the hook says so rather than returning None."""
    monkeypatch.setattr(staff_module.ft, "use_context", lambda _ctx: None)
    with pytest.raises(RuntimeError, match="StaffCtx"):
        use_staff()
