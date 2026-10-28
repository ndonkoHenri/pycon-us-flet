"""Tests for the favourites' reconcile, pure (API-04; D-55, D-406).

``core.favorites_sync.reconcile()`` decides what a pull keeps and whether it pushes;
``server_ids()`` reads a ``mobile_state`` reply. The sync that calls them is
``test_favorites_sync.py``'s.
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pycon_us.core.favorites_sync import (
    Reconciled,
    SyncState,
    reconcile,
    server_ids,
)

IDS = st.frozensets(st.sampled_from(["1", "2", "3", "4", "poster-7"]))
"""Small sets of ids, so the local and server lists often overlap."""


@pytest.mark.parametrize(
    ("local", "server", "state", "expected"),
    [
        # The first sync after sign-in: the union, sent unless the server has it.
        ({"1", "2"}, {"2", "3"}, SyncState.MERGE, ({"1", "2", "3"}, True)),
        ({"1"}, {"1", "2"}, SyncState.MERGE, ({"1", "2"}, False)),
        ({"1"}, set(), SyncState.MERGE, ({"1"}, True)),
        (set(), set(), SyncState.MERGE, (set(), False)),
        # An unsent edit: the local list is kept and sent.
        ({"1"}, {"1", "2"}, SyncState.DIRTY, ({"1"}, True)),
        (set(), {"2"}, SyncState.DIRTY, (set(), True)),
        ({"1"}, {"1"}, SyncState.DIRTY, ({"1"}, False)),
        # Up to date: the server's list is adopted, [] included (a removal elsewhere).
        ({"1", "2"}, {"2", "3"}, SyncState.CLEAN, ({"2", "3"}, False)),
        ({"1"}, set(), SyncState.CLEAN, (set(), False)),
    ],
)
def test_reconcile_table(
    local: set[str],
    server: set[str],
    state: SyncState,
    expected: tuple[set[str], bool],
) -> None:
    """Each state keeps what D-55 and D-406 say, and pushes only a difference."""
    keep, push = expected
    assert reconcile(local, server, state) == Reconciled(frozenset(keep), push)


@given(local=IDS, server=IDS)
def test_the_first_sync_never_loses_a_local_id(
    local: frozenset[str], server: frozenset[str]
) -> None:
    """At the first sync every local and every server id is kept (Ionic lost local ones)."""
    result = reconcile(local, server, SyncState.MERGE)
    assert local <= result.keep and server <= result.keep


@given(local=IDS, server=IDS)
def test_a_dirty_edit_is_never_overwritten(
    local: frozenset[str], server: frozenset[str]
) -> None:
    """A dirty list is kept as it is, and sent whenever the server's differs."""
    result = reconcile(local, server, SyncState.DIRTY)
    assert result.keep == local
    assert result.push == (local != server)


@given(local=IDS, server=IDS, state=st.sampled_from(SyncState))
def test_after_a_pull_the_server_gets_what_the_device_keeps(
    local: frozenset[str], server: frozenset[str], state: SyncState
) -> None:
    """When nothing is pushed the device keeps exactly the server's list."""
    result = reconcile(local, server, state)
    assert result.push or result.keep == server


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ({"favorites": ["1", "poster-7"]}, {"1", "poster-7"}),
        ({"favorites": [1, "2"]}, {"1", "2"}),  # ints become strings
        ({"favorites": []}, set()),
    ],
)
def test_server_ids_reads_a_reply(reply: object, expected: set[str]) -> None:
    """A ``mobile_state`` reply gives its ids as strings."""
    assert server_ids(reply) == expected


@pytest.mark.parametrize(
    "reply",
    [
        None,
        [],
        {},
        {"favorites": None},
        {"favorites": "1"},
        {"favorites": [1.0]},
        {"favorites": [True]},
        {"favorites": [None]},
    ],
)
def test_server_ids_refuses_another_body(reply: object) -> None:
    """Any other body is not a list of ids: None, so nothing is adopted."""
    assert server_ids(reply) is None
