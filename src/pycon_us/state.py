"""The app's observable stores, their contexts and ``use_*`` hooks (D-69; architecture §6).

Each store is an ``@ft.observable`` dataclass with its own context (D-70 rule 5): a
component that reads a store through its hook re-renders when one of the store's public
fields is assigned (F3, F5). Fields starting with ``_`` never notify.

P0 has ``Conference``; ``Prefs`` joins with the boot gate (P0-20) and ``Favorites`` in P1.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal

import flet as ft
import httpx

from pycon_us import clock
from pycon_us.config import ConferenceInfo, YearData
from pycon_us.core import feed
from pycon_us.core.models import ConferenceData
from pycon_us.core.timefmt import today
from pycon_us.services import api
from pycon_us.services.storage import Storage

logger = logging.getLogger(__name__)

type Source = Literal["none", "bundled", "cache", "network"]
"""Where the published data came from; ``none`` until ``load_local`` publishes."""

type Problem = Literal["offline", "server"]
"""Why the last refresh failed: no answer, or an answer that could not be used."""

type Status = Literal["fresh", "stale", "refreshing", "offline", "problem"]
"""What the status strip says about the data (D-32, D-146)."""

STALE_ON_CONFERENCE_DAYS = timedelta(hours=6)
"""Data older than this is stale from the first to the last conference day (D-32)."""

STALE_OTHERWISE = timedelta(hours=24)
"""Data older than this is stale on any other day (D-32)."""


# eq=False: a store is one object, compared by identity. A generated __eq__ would compare
# every field, the whole processed feed included, whenever Flet compares it (F5).
@ft.observable
@dataclass(eq=False)
class Conference:
    """This year's processed feed, where it came from and how fresh it is (D-38, D-39).

    ``load_local`` publishes the best local copy before the first frame; ``start_refresh``
    or ``refresh`` then replaces it from the network. A published ``ConferenceData`` is
    frozen and never mutated: a refresh publishes a new one, so screens memoise on
    ``version``.

    Attributes:
        data: The processed feed; None until ``load_local`` publishes.
        source: Where ``data`` came from.
        fetched_at: When ``data`` was fetched (aware): the cache file's modification
            time, the snapshot's capture time, or ``clock.now()`` after a refresh.
        refreshing: Whether a refresh is running.
        problem: Why the last refresh failed, or None after a good one. The data stays
            whatever was published last.
        version: Incremented on every publish; the memo key of every view model.
    """

    data: ConferenceData | None = None
    source: Source = "none"
    fetched_at: datetime | None = None
    refreshing: bool = False
    problem: Problem | None = None
    version: int = 0
    _task: asyncio.Task[None] | None = field(default=None, repr=False)

    async def load_local(self, storage: Storage, year: YearData) -> None:
        """Publish the feed cache, or the bundled snapshot when there is no usable cache.

        A cache that no longer parses is deleted, and the snapshot is used (D-39). Call it
        once at start, before the first refresh.

        Args:
            storage: Where the feed cache lives.
            year: The year's data: feed settings and the bundled snapshot.

        Raises:
            YearDataError: The year bundles no snapshot (a broken build; D-135).
            FeedError: The bundled snapshot does not parse (a broken build; a test
                processes the committed one).
        """
        cached = await storage.read_feed()
        if cached is not None:
            try:
                data = feed.process(cached.raw, year.feed_settings)
            except feed.FeedError as error:
                await storage.delete_feed(f"it does not parse: {error}")
            else:
                saved_at = datetime.fromtimestamp(cached.saved_at, UTC)
                self._publish(data, "cache", saved_at)
                return
        snapshot = year.read_snapshot()
        data = feed.process(snapshot.raw, year.feed_settings)
        self._publish(data, "bundled", snapshot.captured_at)

    def start_refresh(
        self,
        storage: Storage,
        year: YearData,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> asyncio.Task[None]:
        """Start a background refresh, unless one is running already (single flight).

        Call it from the event loop's thread (D-70 rule 7). Without awaiting the task, an
        unexpected error reaches only asyncio's exception handler (F4); expected
        failures never raise, they set ``problem``.

        Args:
            storage: Where the feed cache lives.
            year: The year's data: the feed URL and feed settings.
            transport: The HTTP transport; tests pass an ``httpx.MockTransport``.

        Returns:
            The running refresh: the new one, or the one already in flight.
        """
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._refresh(storage, year, transport))
        return self._task

    async def refresh(
        self,
        storage: Storage,
        year: YearData,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Refresh from the network and wait for it; concurrent calls share one request.

        Cancelling one caller does not cancel the shared refresh, which others may be
        waiting for.

        Args:
            storage: Where the feed cache lives.
            year: The year's data: the feed URL and feed settings.
            transport: The HTTP transport; tests pass an ``httpx.MockTransport``.
        """
        await asyncio.shield(self.start_refresh(storage, year, transport=transport))

    def age(self) -> timedelta | None:
        """Return how old the data is by ``clock.now()``, never negative; None without data."""
        if self.fetched_at is None:
            return None
        return max(clock.now() - self.fetched_at, timedelta(0))

    def status(self, info: ConferenceInfo) -> Status:
        """Return what the status strip says about the data (D-32, D-146).

        In order: ``refreshing`` while a refresh runs; ``offline`` or ``problem`` when the
        last refresh failed with no answer or a bad one; ``stale`` when the data is older
        than 6 h on a conference day (``first_day`` to ``last_day`` in conference time) or
        24 h on another day, or when there is no data yet; otherwise ``fresh``.

        Args:
            info: The year's facts: its dates and time zone.
        """
        if self.refreshing:
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
        storage: Storage,
        year: YearData,
        transport: httpx.AsyncBaseTransport | None,
    ) -> None:
        """Fetch, parse, cache and publish; on any expected failure keep what is published."""
        self.refreshing = True
        try:
            raw = await api.fetch_feed(year.conference.feed_url, transport=transport)
            data = feed.process(raw, year.feed_settings)  # on the loop (D-109)
        except api.NetworkError as error:
            logger.info("Feed refresh: no answer (%s); keeping the current data", error)
            self.problem = "offline"
        except (api.ApiError, feed.FeedError) as error:
            logger.warning("Feed refresh failed (%s); keeping the current data", error)
            self.problem = "server"
        else:
            # Only a feed that parsed is cached (D-39). A failed write is logged and the
            # parsed data is still published (D-120).
            await storage.write_feed(raw)
            self._publish(data, "network", clock.now())
        finally:
            self.refreshing = False

    def _publish(
        self, data: ConferenceData, source: Source, fetched_at: datetime
    ) -> None:
        self.data = data  # a new frozen eq=False object: always notifies (F5)
        self.source = source
        self.fetched_at = fetched_at
        self.problem = None
        self.version += 1


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
