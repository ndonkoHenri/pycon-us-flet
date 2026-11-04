"""The `Favorites` store: the sessions saved to My schedule (STORE-02, SCHED-12; D-48).

Favourites are local-first: they need no account and are saved per conference year under
`pycon.<year>.favorites`, because ids are unique only within one year's feed, so a 2026
favourite never marks a 2027 session (D-48). Signed in, `services/favorites_sync.py`
syncs them with the mock account (D-55, D-406); the store itself makes no request.

**How a list uses it without re-rendering every row** (D-153, D-172): only the component
that owns a list calls `use_favorites()`, since a subscription re-renders its component
on every change (F3). It hands each memoised day list or slot `favorites.ids & their_ids`,
each memoised row `session_id in favorites.ids`, and one `on_toggle(session_id)` made
with `ft.use_callback(..., [])`: the store and `Storage` are the same objects for the
whole session, so a callback that closes over them never goes stale. A row that called
`use_favorites()` itself would re-render on every star tap, wherever it was.
"""

import logging
from collections.abc import Iterable
from dataclasses import dataclass

import flet as ft

from pycon_us.services.pref_keys import favorites
from pycon_us.services.storage import SERVICE_ERRORS, Storage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Change:
    """What one edit of the favourites did: what Undo reverses and what the UI says.

    Attributes:
        added: The ids the edit saved. Ids that were saved already are not in it, so
            Undo never removes a session the user had saved before.
        removed: The ids the edit removed. Ids that were not saved are not in it.
        saved: Whether the new favourites were written. On False the session keeps
            them, and the caller says "Couldn't save your change" (D-120).
    """

    added: frozenset[str] = frozenset()
    removed: frozenset[str] = frozenset()
    saved: bool = True


# eq=False: a store is one object, compared by identity (F5), as Conference and Prefs.
@ft.observable
@dataclass(eq=False)
class Favorites:
    """The session ids saved to My schedule for the active conference year (D-30, D-48).

    `ids` is a frozenset: a lookup is O(1), and the part of it under a memoised list
    (`ids & day_ids`) compares equal while nothing under that list changed (D-153,
    F34). Every edit assigns `ids` once, so it notifies once, and an edit that changes
    nothing neither notifies nor writes. It is saved sorted, as `list[str]` (F12).

    Each edit returns a `Change` for its Undo; `undo()` takes it back. An edit shows
    first and is saved after (D-172): the star changes without waiting for
    SharedPreferences, and a second tap during the write starts from the first's result.

    Attributes:
        ids: The saved session ids. Change it only through the methods, which persist;
            ids that are no longer in the feed stay, since a later feed may bring
            their session back.
        loaded: Whether the year's favourites were read. Until a read succeeds the
            store is read-only on the device: edits show but are not saved, so an
            empty set never replaces a list nobody read (D-172). After the boot gate
            False means the read failed, or the start broke before it, and My schedule
            says it can't open rather than "Nothing saved yet" (ux.md §4.6).
    """

    ids: frozenset[str] = frozenset()
    loaded: bool = False

    async def load(self, storage: Storage) -> None:
        """Read the year's favourites.

        An absent or unreadable value reads as none (logged, D-120). Until a read
        succeeds, edits show but are not saved (`saved=False`, `loaded` stays
        False): a read that fails leaves the store empty, and an empty set is never
        written over favourites that could not be read (D-172).

        Args:
            storage: Where they are kept; its `year` picks the key (D-48).
        """
        key = favorites(storage.year)
        try:
            stored = await storage.read(key)
        except SERVICE_ERRORS:
            logger.warning(
                "Could not read %s; changes are not saved this session",
                key.key,
                exc_info=True,
            )
            return
        self.ids = frozenset(stored)
        self.loaded = True

    def reset(self) -> None:
        """Forget every saved session, as after a fresh install, without writing.

        Reset app (DEV-05, D-198) calls it once `Storage.clear_prefs()` has removed
        the stored list, so there is nothing to write; `loaded` stays as it is, and
        the next edit saves as usual.
        """
        self.ids = frozenset()

    async def toggle(self, storage: Storage, session_id: str) -> Change:
        """Save a session, or remove it when it is saved already (D-30).

        Args:
            storage: Where the favourites are kept.
            session_id: The session's id.

        Returns:
            The change: `added` or `removed` holds the id. A removal is what shows
            "Removed from My schedule · Undo" (ux.md §4.4).
        """
        if session_id in self.ids:
            return await self._edit(storage, remove=frozenset((session_id,)))
        return await self._edit(storage, add=frozenset((session_id,)))

    async def add_many(self, storage: Storage, session_ids: Iterable[str]) -> Change:
        """Save several sessions at once, e.g. a whole track (SCHED-24).

        Args:
            storage: Where the favourites are kept.
            session_ids: The sessions' ids; those saved already are left as they are.

        Returns:
            The change; `added` holds only the newly saved ids, so "Added 16 sessions"
            counts them and Undo removes only them.

        Raises:
            TypeError: `session_ids` is one string, not a collection of ids.
        """
        return await self._edit(storage, add=_id_set(session_ids) - self.ids)

    async def remove_many(self, storage: Storage, session_ids: Iterable[str]) -> Change:
        """Remove several sessions at once.

        Args:
            storage: Where the favourites are kept.
            session_ids: The sessions' ids; those not saved are ignored.

        Returns:
            The change; `removed` holds only the ids that were saved.

        Raises:
            TypeError: `session_ids` is one string, not a collection of ids.
        """
        return await self._edit(storage, remove=_id_set(session_ids) & self.ids)

    async def replace(self, storage: Storage, session_ids: Iterable[str]) -> bool:
        """Take the account's list in, after a pull (D-55); there is no Undo for it.

        Shown first and saved after, as every edit (D-172).

        Args:
            storage: Where the favourites are kept.
            session_ids: The ids to keep, `core.favorites_sync.reconcile()`'s.

        Returns:
            Whether they were written, or nothing needed writing; False also while no
            read has succeeded, when nothing is written (`loaded`).

        Raises:
            TypeError: `session_ids` is one string, not a collection of ids.
        """
        ids = _id_set(session_ids)
        change = await self._edit(storage, add=ids - self.ids, remove=self.ids - ids)
        return change.saved

    async def undo(self, storage: Storage, change: Change) -> Change:
        """Take back an edit: remove what it added and save again what it removed.

        Args:
            storage: Where the favourites are kept.
            change: What `toggle`, `add_many`, `remove_many` or `undo` returned.

        Returns:
            The change the undo made, itself undoable.
        """
        return await self._edit(
            storage, add=change.removed - self.ids, remove=change.added & self.ids
        )

    async def _edit(
        self,
        storage: Storage,
        *,
        add: frozenset[str] = frozenset(),
        remove: frozenset[str] = frozenset(),
    ) -> Change:
        """Show the edit at once, then save the whole set (D-172); nothing to do, no-op."""
        if not add and not remove:
            return Change()
        self.ids = (self.ids - remove) | add  # one assignment, one notification
        if not self.loaded:  # never write over favourites that no read has seen
            return Change(added=add, removed=remove, saved=False)
        # The set is read here, before the first await, and Flet sends a service call
        # before it awaits the answer (Session.invoke_method), so the writes reach
        # SharedPreferences in the order of the edits and the last one holds them all.
        saved = await storage.set(favorites(storage.year), sorted(self.ids))
        return Change(added=add, removed=remove, saved=saved)


def _id_set(session_ids: Iterable[str]) -> frozenset[str]:
    """Return the ids as a set, refusing one string, which would iterate as characters."""
    if isinstance(session_ids, str):
        raise TypeError("pass a collection of session ids, not one id")
    return frozenset(session_ids)


FavoritesCtx: ft.ContextProvider[Favorites | None] = ft.create_context(None)
"""Provides the session's `Favorites`; `App` writes the provider out (D-69)."""


def use_favorites() -> Favorites:
    """Return the `Favorites` store and re-render the caller when it changes (F3).

    Call it in the component that owns a list, never in its rows (module docstring,
    D-153): each caller re-renders on every star tap.

    Raises:
        RuntimeError: No `FavoritesCtx` provider is above the calling component.
    """
    store = ft.use_context(FavoritesCtx)
    if store is None:
        raise RuntimeError("use_favorites() needs a FavoritesCtx provider above it")
    return store
