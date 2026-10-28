"""The one sync loop of the staff outbox: it sends queued rows to the mock (D-56).

``SyncWorker`` sends the signed-in account's due rows in order (``OutboxDb.due_rows()``),
each with its own sponsor snapshot (STORE-11), and stores each outcome through
``core/outbox.py``'s transitions: a ``NetworkError`` ends the pass and is never counted,
and flags the row when the request may have reached the server (D-410); an ``ApiError``
is counted and the tenth makes the row ``failed``. A refused key (401) is the account's
fault, not the row's: the row waits uncounted and the account's flags are asked again,
which makes it ``expired`` (D-57, D-403). ``run()`` passes at once, then on every
``kick()`` and every 60 s, only while the app is in the foreground.

``supervise()``, which ``use_sync_worker()`` runs from an ``App`` effect, keeps exactly
one worker per session (LEAD-12; Ionic started a loop per page visit): one while a
client exists (a mock API URL, D-51) and the account is signed in and not expired, none
otherwise, and none once the session closes (D-147). It trusts transport errors, not
``ft.Connectivity``, which only kicks it when a connection comes back (D-407).

Outbox times are real epoch seconds (``time.time()``), as the client's signatures are:
the Developer fake clock moves the schedule, not the queue (D-407).
"""

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, cast

import flet as ft

from pycon_us.core import outbox
from pycon_us.core.outbox import NETWORK_BACKOFF, Kind, Row
from pycon_us.services.api import ApiClient, ApiError, NetworkError
from pycon_us.services.endpoints import (
    LEAD_CAPTURE,
    LEAD_NOTE,
    REDEEM,
    lead_capture_query,
)
from pycon_us.services.errors import report_errors
from pycon_us.services.outbox_db import OutboxDb

if TYPE_CHECKING:  # the stores import the services, not the other way round
    from pycon_us.account import Account
    from pycon_us.prefs import Prefs
    from pycon_us.services import Services
    from pycon_us.staff import Staff

logger = logging.getLogger(__name__)

REFUSED_KEY = 401
"""The status of a key the server no longer knows (the mock's ``revoked``)."""

type Ended = tuple[str | None, bool, bool]
"""How a pass ended: the last failure's message (None without one), whether the server
answered every row tried, and whether it stopped on a ``NetworkError`` (offline)."""


async def send(api: ApiClient, row: Row) -> object:
    """Send one outbox row with its own owner's key and its own sponsor snapshot.

    The payloads are what the enqueue stored: a lead's ``{"badge_validator"}``, a
    note's ``{"accessCode", "note"}`` and a door check-in's ``redeem`` body as it goes.
    The sponsor is the row's snapshot, never the one picked now (STORE-11; Ionic sent
    the current one); a sponsor's own account has none, and sends none.

    Args:
        api: The client, signing with the signed-in account's key.
        row: A due row.

    Returns:
        The server's answer: a lead's ``{first_name}``, a check-in's redeem reply.

    Raises:
        NetworkError: No answer arrived.
        ApiError: The server refused the row, or its reply could not be read.
    """
    match row.kind:
        case Kind.LEAD:
            validator = str(row.payload["badge_validator"])
            query = lead_capture_query(row.key, validator, row.sponsor_id)
            return await api.request(LEAD_CAPTURE, query=query)
        case Kind.NOTE:
            sponsor = {} if row.sponsor_id is None else {"sponsor_id": row.sponsor_id}
            payload = {**row.payload, **sponsor}
            return await api.request(LEAD_NOTE, row.key, payload=payload)
        case Kind.DOOR:
            return await api.request(REDEEM, payload=dict(row.payload))


class SyncWorker:
    """Sends the signed-in account's due rows: the only sender of the outbox (§12.3).

    Built by ``supervise()`` for one client and one owner; a new client, a sign-out,
    another account or ``expired`` ends it and, when one is due, starts another.
    """

    def __init__(
        self,
        db: OutboxDb,
        api: ApiClient,
        account: Account,
        staff: Staff,
        *,
        wake: asyncio.Event | None = None,
        foreground: asyncio.Event | None = None,
        closed: asyncio.Event | None = None,
        on_refused: Callable[[], object] = lambda: None,
        now: Callable[[], float] = time.time,
    ) -> None:
        """Create the worker; nothing runs until ``run()`` or ``drain()``.

        Args:
            db: The outbox.
            api: The client to send with (``Services.api``).
            account: The ``Account`` store: the owner, and whether it may still send.
            staff: The ``Staff`` store it reports to.
            wake: What ``kick()`` sets: ``Services.sync_wake``, which the connectivity
                handler and ``on_resume()`` set too. A new event by default.
            foreground: ``Services.foreground``: the loop waits while it is clear.
            closed: ``Services.closed``: a replaced session sends and writes nothing.
            on_refused: Called when the server refuses the key: asks the account's
                flags again (``Account.refresh_flags``), which sets ``expired``.
            now: The clock, epoch seconds; tests move it by hand.
        """
        self._db, self._api, self._account, self._staff = db, api, account, staff
        self._wake = wake or asyncio.Event()
        self._foreground = foreground
        self._closed = closed
        self._on_refused = on_refused
        self._now = now

    def kick(self) -> None:
        """Ask for a pass now: an enqueue, "Sync now", a resume or a reconnection."""
        self._wake.set()

    def _may_send(self, owner: str) -> bool:
        """Whether rows of ``owner`` may still be sent with this worker's client.

        Checked before each row: in the background (``foreground`` clear) a pass stops
        and its rows stay due for the resume's kick (D-407).
        """
        account = self._account
        return (
            not (self._closed is not None and self._closed.is_set())
            and (self._foreground is None or self._foreground.is_set())
            and account.signed_in
            and not account.expired
            and account.owner == owner
        )

    async def drain(self) -> None:
        """Send the due rows in order and store each outcome; one pass at a time.

        A pass already under way (``Staff.syncing``) makes this one return at once:
        that one is the pass. A cancelled pass stores no outcome for the row in flight,
        which stays due, its tries unchanged: each outcome is one transaction
        (``OutboxDb.save``). The server may have had that send, so the row is flagged
        "may be recorded twice" (D-410).
        """
        staff = self._staff
        owner = self._account.owner
        if staff.syncing or not self._may_send(owner):
            return
        staff.syncing = True
        outcome: Ended = (None, False, False)
        try:
            outcome = await self._send_due(owner)
        finally:
            if not (self._closed is not None and self._closed.is_set()):
                self._report(owner, *outcome)

    async def _send_due(self, owner: str) -> Ended:
        """Send ``owner``'s due rows until none is left or the pass has to stop.

        The due rows are read again once sent, so a note whose lead synced in this
        pass goes in it too, and so does a row edited while it was sent; a row is
        never sent twice at the same revision in one pass, so a save that failed
        cannot loop. Before each row the account is checked again: a sign-out,
        another account, ``expired`` or a pause stops the pass, so no row is ever
        sent with another owner's key, nor in the background.

        Returns:
            How the pass ended (``Ended``).
        """
        error: str | None = None
        tried: set[tuple[int | None, int]] = set()
        while rows := [
            row
            for row in self._db.due_rows(owner, self._now())
            if (row.id, row.revision) not in tried
        ]:
            for row in rows:
                if not self._may_send(owner):
                    return error, False, False
                tried.add((row.id, row.revision))
                assert row.id is not None  # a due row is a stored one
                try:
                    result = await send(self._api, row)
                except asyncio.CancelledError:
                    # The server may have it already: flag it, leave it pending.
                    self._db.flag_maybe_sent(row.id)
                    raise
                except NetworkError as failure:
                    if failure.maybe_sent:  # by id, so an edit since keeps it
                        self._db.flag_maybe_sent(row.id)
                    waiting = outbox.after_network_error(
                        row, self._now(), maybe_sent=failure.maybe_sent
                    )
                    self._db.save(waiting)
                    return str(failure), False, True
                except ApiError as failure:
                    if failure.status == REFUSED_KEY:  # the key's fault: not counted
                        self._db.save(outbox.after_network_error(row, self._now()))
                        self._on_refused()
                        return str(failure), False, False
                    error = str(failure)
                    self._db.save(outbox.after_error(row, failure.message, self._now()))
                else:
                    self._db.save(outbox.after_success(row, result))
        return error, True, False

    def _report(
        self, owner: str, error: str | None, reached: bool, offline: bool
    ) -> None:
        """Write the pass's outcome to ``Staff``: counts, error, time, not syncing."""
        staff = self._staff
        staff.update_counts(self._db.counts(owner))
        staff.last_error = error
        staff.offline = offline
        if reached:
            staff.last_sync_at = self._now()
        staff.syncing = False

    async def run(self, tick: float = NETWORK_BACKOFF) -> None:
        """Pass now, then after each ``kick()`` or ``tick`` seconds, until cancelled.

        In the background it waits for the resume (``foreground``), and it returns
        when the session closes (D-147). A kick during a pass makes another one right
        after it.

        Args:
            tick: Seconds between two passes without a kick: the backoff's 60 s.
        """
        while True:
            if self._foreground is not None:
                await self._foreground.wait()
            if self._closed is not None and self._closed.is_set():
                return
            self._wake.clear()
            await report_errors(self.drain)()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), tick)


def sync_target(svc: Services, account: Account) -> tuple[ApiClient, str] | None:
    """Return the client and the owner a worker sends for now, or None for no worker.

    A worker runs while a mock API URL is set (``Services.api``, D-51), the outbox
    exists, and the account is signed in and not ``expired`` (D-403).
    """
    api = svc.api
    if api is None or svc.outbox is None or not account.signed_in or account.expired:
        return None
    return api, account.owner


async def _first_set(*events: asyncio.Event) -> None:
    """Wait until any of the events is set."""
    waits = [asyncio.ensure_future(event.wait()) for event in events]
    try:
        await asyncio.wait(waits, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for wait in waits:
            wait.cancel()


async def _stop(task: asyncio.Task[None] | None) -> None:
    """Cancel a worker's task and wait until it has stopped."""
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


async def supervise(
    svc: Services, account: Account, staff: Staff, prefs: Prefs | None = None
) -> None:
    """Keep one ``SyncWorker`` running while ``sync_target()`` names one, until closed.

    Every change of the account or the settings (where the mock URL is kept) checks
    the target again; a new target stops the old worker before the next starts, so
    two never send at once. Signed out, ``Staff`` is cleared, whatever the target was
    (an expired account or no client has none either); signed in, it takes the
    owner's counts at once. Returns when the session closes; cancelling it (the
    effect's unmount) stops the worker too.

    Args:
        svc: The session's services: the client, the outbox and the events.
        account: The ``Account`` store.
        staff: The ``Staff`` store.
        prefs: The ``Prefs`` store, whose mock URL change rebuilds the client.
    """
    changed = asyncio.Event()

    def on_change(_sender: object, _name: str | None) -> None:
        changed.set()

    # Held here while the loop runs: the stores keep their listeners weakly.
    watched = [account] if prefs is None else [account, prefs]
    stops = [cast(ft.Observable, store).subscribe(on_change) for store in watched]
    target: tuple[ApiClient, str] | None = None
    task: asyncio.Task[None] | None = None
    try:
        while not svc.closed.is_set():
            changed.clear()
            now = sync_target(svc, account)
            if now != target:
                await _stop(task)
                target, task = now, _start(svc, account, staff, now)
            if not account.signed_in:  # after the stop: a cancelled pass reports
                staff.clear()
            await _first_set(changed, svc.closed)
    finally:
        await _stop(task)
        for stop in stops:
            stop()


def _start(
    svc: Services,
    account: Account,
    staff: Staff,
    target: tuple[ApiClient, str] | None,
) -> asyncio.Task[None] | None:
    """Start a worker's loop for ``target``, or none without one.

    An expired account keeps its counts: its rows wait for the next sign-in. Every
    other account's synced rows are deleted first, as an account switch does (D-414).
    """
    if target is None or svc.outbox is None:
        return None
    api, owner = target
    # An account switch; a failure is logged, and the next start tries again.
    svc.outbox.forget_other_accounts(owner)
    logger.info("Staff sync started")
    worker = SyncWorker(
        svc.outbox,
        api,
        account,
        staff,
        wake=svc.sync_wake,
        foreground=svc.foreground,
        closed=svc.closed,
        on_refused=lambda: account.refresh_flags(api, svc.storage, closed=svc.closed),
    )
    staff.update_counts(svc.outbox.counts(owner))
    return asyncio.create_task(worker.run())


def use_sync_worker(
    svc: Services, account: Account, staff: Staff, prefs: Prefs
) -> None:
    """Run ``supervise()`` once the start has restored the account (a hook, D-70).

    Call it from ``App`` on every render, before any early return: ``App`` never
    unmounts, so whatever the navigation there is one loop per session (LEAD-12).

    Args:
        svc: The session's services.
        account: The session's ``Account`` store.
        staff: The session's ``Staff`` store.
        prefs: The session's ``Prefs`` store; the loop starts once it is loaded.
    """

    @report_errors
    async def keep_syncing() -> None:
        if prefs.loaded:
            await supervise(svc, account, staff, prefs)

    ft.use_effect(keep_syncing, [prefs.loaded])
