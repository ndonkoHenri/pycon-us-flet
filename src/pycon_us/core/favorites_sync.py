"""How the favourites and the account's `mobile_state` agree after a pull (D-55, D-406).

Pure: `services/favorites_sync.py` reads the server's list, asks `reconcile()` what
to keep and whether to push, then does it. Three states say what the device knows
(`SyncState`); the state is saved per year, so a kill never forgets an unsent edit
or a first sync that has not happened yet.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum


class SyncState(StrEnum):
    """What the server has of this device's favourites, as saved in `favorites_sync`."""

    MERGE = "merge"
    """The first sync after a sign-in has not happened: the next pull takes the union,
    so no local id is lost (Ionic replaced the local list, `[]` included)."""
    DIRTY = "dirty"
    """A local edit has not reached the server: the next pull keeps the local list and
    pushes it, so an unsent edit is never overwritten."""
    CLEAN = "clean"
    """The server had this device's last list: the next pull adopts the server's, `[]`
    included, since a difference is then an edit made elsewhere."""


@dataclass(frozen=True)
class Reconciled:
    """What a pull ends with.

    Attributes:
        keep: The ids the device keeps.
        push: Whether `keep` is sent to the server (a full-list PATCH).
    """

    keep: frozenset[str]
    push: bool


def server_ids(reply: object) -> frozenset[str] | None:
    """Return the ids of a `mobile_state` reply, integers as their decimal strings.

    Args:
        reply: The decoded reply, `{"favorites": [...]}` (`tools/mock_api`).

    Returns:
        The ids, or None when the reply is not that shape: a list of strings and
        integers. A bool is refused, though Python counts it an int, and so is a
        float, whose text depends on who printed it (D-42).
    """
    if not isinstance(reply, dict):
        return None
    ids = reply.get("favorites")
    if not isinstance(ids, list) or not all(type(item) in (str, int) for item in ids):
        return None
    return frozenset(str(item) for item in ids)


def reconcile(
    local: Iterable[str], server: Iterable[str], state: SyncState
) -> Reconciled:
    """Decide what the device keeps after a pull, and whether it pushes (D-55, D-406).

    Args:
        local: The device's ids now, edits made during the pull included.
        server: The ids the server sent (`server_ids()`).
        state: The saved `SyncState`, read after the pull's reply.

    Returns:
        `MERGE`: the union. `DIRTY`: the local list. `CLEAN`: the server's
        list. Pushed whenever it differs from the server's.
    """
    local, server = frozenset(local), frozenset(server)
    if state is SyncState.MERGE:
        keep = local | server
    elif state is SyncState.DIRTY:
        keep = local
    else:
        keep = server
    return Reconciled(keep, push=keep != server)
