"""The ``Conference`` store with its context and hook (D-69, D-160; architecture §6.2).

Assigning a public field re-renders the store's readers (F3, F5); ``_`` fields never
notify. A refresh's words, timings and network step are ``feed_refresh.py``'s (D-231).
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import cast

import flet as ft
import httpx

from pycon_us import clock
from pycon_us.config import ConferenceInfo, YearData
from pycon_us.core import feed
from pycon_us.core.models import ConferenceData
from pycon_us.core.timefmt import today
from pycon_us.feed_refresh import (
    REFRESH_EVERY,
    STALE_ON_CONFERENCE_DAYS,
    STALE_OTHERWISE,
    Problem,
    Source,
    Status,
    feed_digest,
    fetch,
    log_unexpected,
)
from pycon_us.services import changes_file
from pycon_us.services.storage import Storage

logger = logging.getLogger(__name__)


# eq=False: a store is one object, compared by identity. A generated __eq__ would compare
# every field, the whole processed feed included, whenever Flet compares it (F5).
@ft.observable
@dataclass(eq=False)
class Conference:
    """This year's processed feed, where it came from and how fresh it is (D-38, D-39).

    ``load_local`` publishes the best local copy before the first frame; ``start_refresh``
    or ``refresh`` then replaces it from the network. A published ``ConferenceData`` is
    frozen and never mutated: a refresh publishes a new one, so screens memoise on
    ``version``. A refresh that brings the very bytes already published publishes
    nothing: only its freshness changes (D-224).

    A refresh is automatic (``start_refresh``, ``start_refresh_if_due``) or asked for by
    the user (``refresh``). An automatic one is quiet: ``status()`` keeps saying what it
    said before, and only ``refreshing`` shows that one runs (D-181).

    Attributes:
        data: The processed feed; None until ``load_local`` publishes.
        source: Where ``data`` came from.
        fetched_at: When ``data`` was fetched (aware): the cache file's modification
            time, the snapshot's capture time, or ``clock.now()`` after a refresh,
            one that found the same feed included (D-224).
        refreshing: Whether a refresh is running, automatic or asked for: the status
            strip's progress bar (D-181).
        problem: Why the last refresh failed, or None after a good one. The data stays
            whatever was published last.
        version: Incremented on every publish, so on every new feed but not on a
            refresh that brings the same one (D-224); the memo key of every view model.
    """

    data: ConferenceData | None = None
    source: Source = "none"
    fetched_at: datetime | None = None
    refreshing: bool = False
    problem: Problem | None = None
    version: int = 0
    _task: asyncio.Task[None] | None = field(default=None, repr=False)
    _started_at: datetime | None = field(default=None, repr=False)
    # Whether the user asked for the running refresh (D-181): only then does status()
    # say "refreshing". Private, so setting it notifies nobody unless refresh() asks.
    _asked: bool = field(default=False, repr=False)
    _feed_url: str | None = field(default=None, repr=False)
    # The SHA-256 of the raw feed `data` was processed from: a refresh whose bytes have
    # it brings nothing new to publish (D-224).
    _digest: bytes | None = field(default=None, repr=False)

    async def set_feed_url(self, url: str | None, storage: Storage) -> None:
        """Refresh from ``url`` from the next refresh on; None returns to the year's feed.

        The Developer feed URL (D-73, D-187), with no restart. Once the feed has loaded
        (not at the start), a change deletes the cache and the change log, the old URL's,
        which would mix two feeds (D-255). A refresh from a URL left writes nothing.

        Args:
            url: An ``http://`` or ``https://`` feed URL, or None.
            storage: Where the feed cache and the change log live.
        """
        if url == self._feed_url:
            return
        # Changed before the deletion, so a refresh from the URL left sees it (D-244).
        self._feed_url = url
        logger.info(
            "Feed refreshes use %s", "a Developer feed URL" if url else "the year's"
        )
        if self.data is not None:
            await storage.delete_feed("the feed URL changed")
            await changes_file.delete_batches(storage, "the feed URL changed")

    async def load_local(self, storage: Storage, year: YearData) -> None:
        """Publish the feed cache, or the bundled snapshot when there is no usable cache.

        A cache that no longer parses is deleted, and the snapshot is used (D-39). Call it
        once at start, before the first refresh.

        Args:
            storage: Where the feed cache lives.
            year: The year's data: feed settings and the bundled snapshot.

        Raises:
            YearDataError: The year bundles no snapshot (a broken build; D-135).
            FeedError: The bundled snapshot does not parse (a broken build; tested).
        """
        cached = await storage.read_feed()
        if cached is not None:
            try:
                data = feed.process(cached.raw, year.feed_settings)
            except feed.FeedError as error:
                await storage.delete_feed(f"it does not parse: {error}")
            else:
                saved_at = datetime.fromtimestamp(cached.saved_at, UTC)
                self._publish(data, feed_digest(cached.raw), "cache", saved_at)
                return
        self._publish_snapshot(year)

    async def reset(self, storage: Storage, year: YearData) -> bool:
        """Return to what a fresh install shows: the bundled snapshot, from the year's feed.

        Reset app (DEV-05, D-198). A running refresh is cancelled, and waited for, so it
        cannot cache or publish after the reset; the feed URL returns to the year's; the
        cache is deleted; the snapshot is published, so every screen shows it at once.
        The caller starts the next refresh, as ``bootstrap()`` does. A caller awaiting
        ``refresh()`` ends with ``CancelledError`` too (the shield passes the inner
        cancel on), so a Refresh tapped before the reset says nothing about a refresh
        that never ended.

        Args:
            storage: Where the feed cache lives.
            year: The year's data: the bundled snapshot and the feed settings.

        Returns:
            Whether the cache is gone; when it is not (logged), the snapshot is still
            shown, and the next start publishes the cache again.
        """
        task = self._task
        if task is not None and not task.done():
            task.cancel()
            await asyncio.wait({task})  # its `finally` runs now, not over the next one
        self._task = None
        self._started_at = None
        self._asked = False
        self.refreshing = False
        await self.set_feed_url(None, storage)
        deleted = await storage.delete_feed("Reset app")
        self._publish_snapshot(year)
        return deleted

    def start_refresh(
        self,
        storage: Storage,
        year: YearData,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        closed: asyncio.Event | None = None,
    ) -> asyncio.Task[None]:
        """Start a background refresh, unless one is running already (single flight).

        The refresh it starts is automatic, so quiet: it leaves ``status()`` as it was
        (D-181). Call it from the event loop's thread (D-70 rule 7). Expected failures
        set ``problem``; an unexpected error is logged when the refresh ends, awaited or
        not (D-71), and raised to ``refresh()`` callers.

        Args:
            storage: Where the feed cache lives.
            year: The year's data: the feed URL (unless ``set_feed_url()`` gave one)
                and feed settings.
            transport: The HTTP transport; tests pass an ``httpx.MockTransport``.
            closed: Set when the store's session is replaced (``Services.closed``,
                D-147). A refresh that ends after it writes nothing: neither the cache
                nor the store, whose subscribers belong to a destroyed session (F30).

        Returns:
            The running refresh: the new one, or the one already in flight.
        """
        if self._task is None or self._task.done():
            self._started_at = clock.now()
            self._task = asyncio.create_task(
                self._refresh(self._url(year), storage, year, transport, closed)
            )
            self._task.add_done_callback(log_unexpected)
        return self._task

    def refresh_due(self) -> bool:
        """Return whether an automatic refresh is due (D-40).

        Due when no refresh has started in this session, or the last one started
        ``REFRESH_EVERY`` or more ago by ``clock.now()``, whatever its outcome: counted
        from the last attempt, not the data's age, so a phone offline retries every
        15 min, not on every check. A clock set back before the last start (the fake
        clock) makes it due too. Never while one runs: that one is the attempt.
        """
        if self._task is not None and not self._task.done():
            return False
        if self._started_at is None:
            return True
        since = clock.now() - self._started_at
        return not timedelta(0) <= since < REFRESH_EVERY

    def start_refresh_if_due(
        self,
        storage: Storage,
        year: YearData,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        closed: asyncio.Event | None = None,
    ) -> asyncio.Task[None] | None:
        """Start a background refresh when ``refresh_due()``; the automatic triggers' call.

        The app calls it on resume, and the status strip of Now and Schedule every
        minute while it shows (D-40). Like ``start_refresh``, it never raises for an
        expected failure and never clears what is published.

        Args:
            storage: Where the feed cache lives.
            year: The year's data: the feed URL and feed settings.
            transport: The HTTP transport; tests pass an ``httpx.MockTransport``.
            closed: Set when the store's session is replaced; see ``start_refresh``.

        Returns:
            The refresh it started, or None when none was due.
        """
        if not self.refresh_due():
            return None
        logger.info("An automatic feed refresh is due; starting it")
        return self.start_refresh(storage, year, transport=transport, closed=closed)

    async def refresh(
        self,
        storage: Storage,
        year: YearData,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        closed: asyncio.Event | None = None,
    ) -> None:
        """Refresh from the network because the user asked, and wait for it.

        Concurrent calls share one request. The user's refresh is not quiet:
        ``status()`` says ``refreshing`` until it ends, and joining an automatic refresh
        that is running makes that one the user's at once (D-181). Cancelling one caller
        does not cancel the shared refresh, which others may be waiting for.

        Args:
            storage: Where the feed cache lives.
            year: The year's data: the feed URL and feed settings.
            transport: The HTTP transport; tests pass an ``httpx.MockTransport``.
            closed: Set when the store's session is replaced; see ``start_refresh``.
        """
        task = self.start_refresh(storage, year, transport=transport, closed=closed)
        if not self._asked:
            self._asked = True
            # A new refresh notifies when it sets `refreshing`; a quiet one that is
            # running already has, so the strip learns of the tap from this. The cast:
            # @ft.observable mixes `notify` in, which pyright cannot see.
            if self.refreshing:
                cast(ft.Observable, self).notify()
        await asyncio.shield(task)

    def age(self) -> timedelta | None:
        """Return how old the data is by ``clock.now()``, never negative; None without data."""
        if self.fetched_at is None:
            return None
        return max(clock.now() - self.fetched_at, timedelta(0))

    @property
    def digest(self) -> bytes | None:
        """The SHA-256 of the published feed's bytes, which names it (D-224, D-271)."""
        return self._digest

    def status(self, info: ConferenceInfo) -> Status:
        """Return what the status strip says about the data (D-32, D-146).

        In order: ``refreshing`` while a refresh the user asked for runs (``refresh()``);
        ``offline`` or ``problem`` when the last refresh failed with no answer or a bad
        one; ``stale`` when the data is older than 6 h on a conference day (``first_day``
        to ``last_day`` in conference time) or 24 h on another day, or when there is no
        data yet; otherwise ``fresh``. An automatic refresh changes none of it until it
        ends, so the strip's live region changes only with an outcome (D-181).

        Args:
            info: The year's facts: its dates and time zone.
        """
        if self.refreshing and self._asked:
            return "refreshing"
        if self.problem == "offline":
            return "offline"
        if self.problem == "server":
            return "problem"
        age = self.age()
        if age is None:
            return "stale"
        day = today(clock.now(), info.zone)
        conference_day = info.first_day <= day <= info.last_day
        limit = STALE_ON_CONFERENCE_DAYS if conference_day else STALE_OTHERWISE
        return "stale" if age > limit else "fresh"

    async def _refresh(
        self,
        url: str,
        storage: Storage,
        year: YearData,
        transport: httpx.AsyncBaseTransport | None,
        closed: asyncio.Event | None,
    ) -> None:
        """Fetch, parse, cache and publish; on any expected failure keep what is published.

        Bytes equal to the published feed's (by digest) are cached, which creates or
        dates the cache, but neither parsed nor published: a new version would re-render
        every list and bring the Schedule's "Now" button back for nothing (#290);
        ``_confirm()`` updates the freshness (D-224). A refresh whose session closed, or
        whose ``url`` is no longer the one in effect, writes nothing (F30, D-244).
        """

        def discarded() -> bool:
            if closed is not None and closed.is_set():
                why = "its session closed"
            elif url != self._url(year):
                why = "its feed URL was left"
            else:
                return False
            logger.info("Feed refresh ended after %s; nothing written", why)
            return True

        self.refreshing = True
        try:
            result = await fetch(url, year, transport, self._digest)
            if discarded():
                return
            if isinstance(result, str):
                self.problem = result
                return
            raw, digest, data = result
            # Only a feed that parsed is cached (D-39). A failed write is logged and the
            # parsed data is still published (D-120).
            await storage.write_feed(raw)
            # Left during the write: set_feed_url's deletion waited for it (D-244).
            if discarded():
                return
            if data is None:
                self._confirm()
            else:
                self._publish(data, digest, "network", clock.now())
        finally:
            self._asked = False  # private: the next refresh starts quiet (D-181)
            # A closed session's store must not be written at all (F30).
            if closed is None or not closed.is_set():
                self.refreshing = False

    def _url(self, year: YearData) -> str:
        """Return the feed URL in effect: the Developer one, else the year's (D-187)."""
        return self._feed_url or year.conference.feed_url

    def _publish_snapshot(self, year: YearData) -> None:
        snapshot = year.read_snapshot()
        data = feed.process(snapshot.raw, year.feed_settings)
        self._publish(data, feed_digest(snapshot.raw), "bundled", snapshot.captured_at)

    def _publish(
        self, data: ConferenceData, digest: bytes, source: Source, fetched_at: datetime
    ) -> None:
        self.data = data  # a new frozen eq=False object: always notifies (F5)
        self._digest = digest
        self.source = source
        self.fetched_at = fetched_at
        self.problem = None
        self.version += 1

    def _confirm(self) -> None:
        """Record a good refresh that brought the published feed again (D-224).

        ``data`` and ``version`` stay, so no memo keyed on the version re-renders
        (D-153). Only the freshness that the strip and the Developer screen read
        changes: the age, the source (the network, even for the snapshot's bytes) and
        the last problem.
        """
        logger.info("Feed refresh: the same feed as shown; nothing new to publish")
        self.source = "network"
        self.fetched_at = clock.now()
        self.problem = None


ConferenceCtx: ft.ContextProvider[Conference | None] = ft.create_context(None)
"""Provides the session's ``Conference``; ``App`` writes the provider out (D-69)."""


def use_conference() -> Conference:
    """Return the ``Conference`` store and re-render the caller when it changes (F3).

    Raises:
        RuntimeError: No ``ConferenceCtx`` provider is above the calling component.
    """
    conference = ft.use_context(ConferenceCtx)
    if conference is None:
        raise RuntimeError("use_conference() needs a ConferenceCtx provider above it")
    return conference
