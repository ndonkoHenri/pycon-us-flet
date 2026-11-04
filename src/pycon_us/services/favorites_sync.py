"""Favourites follow the mock account while signed in (API-04, AUTH-12; D-55, D-406).

`FavoritesSync` is `Services.favorites_sync`, and `App` runs it once the start has
loaded the stores (`use_favorites_sync()`). It pulls `mobile_state` at the start,
on resume (`app.on_resume()`'s `request()`) and at each sign-in, and decides what
to keep with `core.favorites_sync.reconcile()`. Each local edit marks the list
dirty and schedules one full-list PATCH a second later (`DEBOUNCE`); a quick run of
stars sends one. One request at a time, in one loop: a pull asked for during a PATCH
runs after it, so it never reads a list older than the one just sent.

What the server has is saved per year as a `SyncState` (`pref_keys.favorites_sync`)
as soon as it changes, even while a request is out, and before any request, so a kill
never forgets an unsent edit or a first sync that has not happened. A failure keeps it for the next start or resume.
Nothing is sent while signed out, expired, with no mock URL (D-51) or with favourites that could not be read
(D-172). The Account page's Sign out first tries once to send what waits (`flush()`,
D-411); a sign-out stops the sync and forgets the state, and the local list stays
(D-48). `Favorites` itself makes no request: it only notifies its edits.
"""

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING, cast

import flet as ft

from pycon_us.core.favorites_sync import SyncState, reconcile, server_ids
from pycon_us.services.api import ApiClient, ApiError, NetworkError
from pycon_us.services.endpoints import READ_MOBILE_STATE, WRITE_MOBILE_STATE
from pycon_us.services.errors import report_errors
from pycon_us.services.pref_keys import favorites_sync
from pycon_us.services.private_api import PrivateApi
from pycon_us.services.storage import Storage

if TYPE_CHECKING:  # the stores import the services package: names for types only
    from pycon_us.account import Account
    from pycon_us.favorites import Favorites
    from pycon_us.prefs import Prefs
    from pycon_us.services import Services

logger = logging.getLogger(__name__)

DEBOUNCE = 1.0
"""Seconds from a local edit to its PATCH; each edit meanwhile starts them again."""


class FavoritesSync:
    """The session's favourites sync: one loop, one request at a time (D-406)."""

    def __init__(self, delay: float = DEBOUNCE) -> None:
        """Start idle; `run()` reads the saved state.

        Args:
            delay: The debounce, `DEBOUNCE`; tests shorten it.
        """
        self._delay = delay
        self._wake = asyncio.Event()
        self._pull = False
        self._due: float | None = None  # loop time of the debounced PATCH
        self._state = SyncState.MERGE
        self._saved: SyncState | None = None  # what storage holds, when known
        self._edits = 0  # local edits so far: a reply older than one settles nothing
        self._generation = 0  # sign-ins and sign-outs: an older reply is dropped
        self._signed_in = False
        self._adopting = False  # the next `ids` change is the sync's own
        self._saving = asyncio.Lock()  # one state write at a time, in order
        self._sending = asyncio.Lock()  # one request at a time: the loop's or flush()'s
        # Held: the event loop keeps its tasks weakly.
        self._saves: set[asyncio.Task[None]] = set()

    def request(self) -> None:
        """Ask for a pull: at the start, on resume, at a sign-in, and to wake `run`."""
        self._pull = True
        self._wake.set()

    async def run(
        self,
        private_api: PrivateApi,
        storage: Storage,
        favorites: Favorites,
        account: Account,
        closed: asyncio.Event,
    ) -> None:
        """Keep the favourites and the account in step until the session closes.

        Starts with a pull. `Services.close()` wakes it, so it returns (D-147).

        Args:
            private_api: `Services.private_api`; its client is read per request.
            storage: Where the favourites and the sync state are kept.
            favorites: The session's `Favorites`, loaded.
            account: The session's `Account`, restored.
            closed: `Services.closed`.
        """
        key = favorites_sync(storage.year)
        stored = await storage.get(key)
        self._saved = SyncState(stored) if stored in SyncState else None
        self._signed_in = account.signed_in
        # Signed out, a state left by a removal that failed means nothing (MERGE).
        if self._signed_in and self._saved is not None:
            self._state = self._saved
        self._publish(account)

        def on_favorites(_sender: object, name: str | None) -> None:
            if name == "ids":
                self._on_edit(account)
                self._save_soon(storage, closed)

        def on_account(_sender: object, name: str | None) -> None:
            if name == "signed_in" and account.signed_in != self._signed_in:
                self._on_account(account)
                self._save_soon(storage, closed)

        # Held here while the loop runs: the stores keep their listeners weakly.
        stops = (
            cast(ft.Observable, favorites).subscribe(on_favorites),
            cast(ft.Observable, account).subscribe(on_account),
        )
        try:
            self.request()  # the start's pull
            while not closed.is_set():
                await self._next()
                if closed.is_set():
                    return
                await self._save(storage)
                if closed.is_set():
                    return
                work = self._take_work()
                if work is None:
                    continue
                async with self._sending:  # a sign-out's flush() waits, or goes first
                    # Read only now: while flush() held the lock the session may have
                    # closed, or Developer replaced the client and closed this one.
                    if closed.is_set():
                        return
                    client = private_api.client
                    if client is None or not favorites.loaded:
                        continue
                    if not account.signed_in or account.expired:
                        continue
                    if not work and self._state is not SyncState.DIRTY:
                        continue  # flush() sent it meanwhile
                    await self._attempt(
                        client, storage, favorites, account, closed, pull=work
                    )
        finally:
            for stop in stops:
                stop()

    async def flush(
        self,
        private_api: PrivateApi,
        storage: Storage,
        favorites: Favorites,
        account: Account,
        closed: asyncio.Event,
    ) -> bool:
        """Try once, now, to give the account this device's list, before a sign-out.

        The Account page's Sign out calls it before its dialog, which says so when it
        failed (D-411). It waits for a request the loop has out, then sends what is
        still waiting: the PATCH, or a first sync's pull and PATCH, on the endpoints'
        own timeouts. Nothing is sent when nothing waits or nothing may be sent.

        Args:
            private_api: `Services.private_api`.
            storage: Where the favourites and the sync state are kept.
            favorites: The session's `Favorites`.
            account: The session's `Account`.
            closed: `Services.closed`.

        Returns:
            Whether the account has this device's list: True when nothing waits.
        """
        async with self._sending:
            if not account.favorites_dirty:
                return True
            client = private_api.client
            if client is None or not favorites.loaded or account.expired:
                return False
            pull = self._state is SyncState.MERGE  # a first sync reads before it sends
            await self._attempt(client, storage, favorites, account, closed, pull=pull)
            return not account.favorites_dirty

    async def _attempt(
        self,
        api: ApiClient,
        storage: Storage,
        favorites: Favorites,
        account: Account,
        closed: asyncio.Event,
        *,
        pull: bool,
    ) -> None:
        """Sync once, keeping a failure for later, then publish and save the state."""
        try:
            await self._sync(api, storage, favorites, account, closed, pull=pull)
        except NetworkError:
            logger.info("Favourites not synced: no answer; kept for later")
        except ApiError as error:
            logger.warning("Favourites not synced: %s", error.status)
        if not closed.is_set():
            self._publish(account)
            await self._save(storage)

    async def _next(self) -> None:
        """Wait for a request, a change or the debounced PATCH's time, whichever is first."""
        loop = asyncio.get_running_loop()
        timeout = None if self._due is None else max(0.0, self._due - loop.time())
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._wake.wait(), timeout)
        self._wake.clear()

    def _take_work(self) -> bool | None:
        """Return True for a pull, False for a PATCH, None for nothing to send now."""
        loop = asyncio.get_running_loop()
        push = self._due is not None and loop.time() >= self._due
        if push:
            self._due = None
        pull, self._pull = self._pull, False
        if pull or (push and self._state is SyncState.MERGE):
            return True  # a first sync is a union: it reads before it sends
        return False if push and self._state is SyncState.DIRTY else None

    async def _sync(
        self,
        api: ApiClient,
        storage: Storage,
        favorites: Favorites,
        account: Account,
        closed: asyncio.Event,
        *,
        pull: bool,
    ) -> None:
        """Pull and reconcile, or PATCH the local list; settle the state when it held.

        After each await it goes on only while the same account is signed in, usable,
        and the session open (`_current()`): a late reply adopts and sends nothing.
        """
        generation = self._generation
        if not pull:
            edits = self._edits
            await self._push(api, favorites.ids)
            self._settle(generation, edits)
            return
        ids = server_ids(await api.request(READ_MOBILE_STATE))
        if ids is None:
            logger.warning("Favourites not synced: not a mobile_state reply")
            return
        if not self._current(generation, account, closed):
            return  # signed out, in again or closed while the pull was out
        edits = self._edits
        result = reconcile(favorites.ids, ids, self._state)
        # The reconciled list is now the device's to send: an edit from here on is
        # pushed as it is, never merged again with a list it removed something from.
        self._state = SyncState.DIRTY
        self._save_soon(storage, closed)
        if result.keep != favorites.ids:
            self._adopting = True  # `replace` assigns before its first await
            try:
                await favorites.replace(storage, result.keep)
            finally:
                self._adopting = False
            logger.info("Favourites: took the account's list in")
            if not self._current(generation, account, closed):
                return  # the next account's sign-in pull does its own union
        if result.push:
            await self._push(api, result.keep)
        self._settle(generation, edits)

    def _current(
        self, generation: int, account: Account, closed: asyncio.Event
    ) -> bool:
        """Whether a sync started in `generation` may still change or send anything."""
        return (
            generation == self._generation
            and account.signed_in
            and not account.expired
            and not closed.is_set()
        )

    async def _push(self, api: ApiClient, ids: frozenset[str]) -> None:
        """Send the whole list, sorted: a PATCH replaces the server's (idempotent)."""
        await api.request(WRITE_MOBILE_STATE, payload={"favorites": sorted(ids)})
        logger.info("Favourites: sent %d ids", len(ids))

    def _settle(self, generation: int, edits: int) -> None:
        """Mark the server up to date, unless the account or the list changed meanwhile."""
        if generation == self._generation and edits == self._edits:
            self._state = SyncState.CLEAN

    def _on_edit(self, account: Account) -> None:
        """A local edit: mark the list dirty and schedule its PATCH (debounced)."""
        if self._adopting:
            self._adopting = False
            return
        if not self._signed_in:
            return  # signed out, favourites are only local (D-48)
        self._edits += 1
        if self._state is SyncState.CLEAN:
            self._state = SyncState.DIRTY  # a first sync pending stays a union
        self._due = asyncio.get_running_loop().time() + self._delay
        self._publish(account)
        self._wake.set()  # saves the state now, then waits for the PATCH's time

    def _on_account(self, account: Account) -> None:
        """A sign-in or a sign-out: the next sync is a first sync again, a union."""
        self._signed_in = account.signed_in
        self._generation += 1
        self._state = SyncState.MERGE
        self._due = None
        self._publish(account)
        if self._signed_in:
            self.request()
        else:
            self._wake.set()  # removes the saved state

    def _publish(self, account: Account) -> None:
        """Say on the account whether the server lacks this device's list (#688)."""
        account.favorites_dirty = self._signed_in and self._state is not SyncState.CLEAN

    def _save_soon(self, storage: Storage, closed: asyncio.Event) -> None:
        """Save a changed state now, without waiting for a request that is out.

        An edit made while the loop awaits the network is then dirty on disk too,
        so a kill before the reply never adopts the server's list over it.
        """
        if self._state is self._saved or closed.is_set():
            return
        task = asyncio.create_task(self._save(storage))
        self._saves.add(task)
        task.add_done_callback(self._saves.discard)

    async def _save(self, storage: Storage) -> None:
        """Save the state when it changed; `MERGE` is the key's absence.

        Writes take turns (`_saving`), so the loop's save before a request waits
        for any that `_save_soon()` started, and the last state is what stays.
        """
        async with self._saving:
            state = self._state
            if state is self._saved:
                return
            key = favorites_sync(storage.year)
            if state is SyncState.MERGE:
                saved = await storage.remove(key)
            else:
                saved = await storage.set(key, state.value)
            if saved:  # a failure is logged by the storage, and tried again next time
                self._saved = state


def use_favorites_sync(
    svc: Services, favorites: Favorites, account: Account, prefs: Prefs
) -> None:
    """Run `Services.favorites_sync` once the start has loaded (a hook, D-70).

    Call it on every render, before any early return. `prefs.loaded` comes after the
    favourites' load and the account's restore, so the sync starts from both.

    Args:
        svc: The session's services.
        favorites: The session's `Favorites` store.
        account: The session's `Account` store.
        prefs: The session's `Prefs` store.
    """

    @report_errors
    async def keep_synced() -> None:
        if not prefs.loaded:
            return
        await svc.favorites_sync.run(
            svc.private_api, svc.storage, favorites, account, svc.closed
        )

    ft.use_effect(keep_synced, [prefs.loaded])
