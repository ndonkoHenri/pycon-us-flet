"""The ``Conference`` store, its context and hook, and ``ViewMemory`` (D-69; architecture §6).

Each store is an ``@ft.observable`` dataclass with its own context (D-70 rule 5): a
component that reads a store through its hook re-renders when one of the store's public
fields is assigned (F3, F5). Fields starting with ``_`` never notify. The other stores
have modules of their own (D-160): ``prefs.py`` and ``favorites.py`` (P1).

``ViewMemory`` is plain, not a store: it lives for the whole process (D-143).
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Literal, cast

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

REFRESH_EVERY = timedelta(minutes=15)
"""How long after a refresh began the next automatic one is due: on resume, and on Now
and Schedule while they show (D-40)."""


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

    A refresh is automatic (``start_refresh``, ``start_refresh_if_due``) or asked for by
    the user (``refresh``). An automatic one is quiet: ``status()`` keeps saying what it
    said before, and only ``refreshing`` shows that one runs (D-181).

    Attributes:
        data: The processed feed; None until ``load_local`` publishes.
        source: Where ``data`` came from.
        fetched_at: When ``data`` was fetched (aware): the cache file's modification
            time, the snapshot's capture time, or ``clock.now()`` after a refresh.
        refreshing: Whether a refresh is running, automatic or asked for: the status
            strip's progress bar (D-181).
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
    _started_at: datetime | None = field(default=None, repr=False)
    # Whether the user asked for the running refresh (D-181): only then does status()
    # say "refreshing". Private, so setting it notifies nobody unless refresh() asks.
    _asked: bool = field(default=False, repr=False)
    _feed_url: str | None = field(default=None, repr=False)

    def set_feed_url(self, url: str | None) -> None:
        """Refresh from ``url`` from the next refresh on; None returns to the year's feed.

        The Developer screen's feed URL (D-73, D-187): ``bootstrap()`` sets the stored
        one, and Apply a new one, with no restart. A refresh already running keeps the
        URL it started with.

        Args:
            url: An ``http://`` or ``https://`` feed URL, or None.
        """
        if url != self._feed_url:
            logger.info(
                "Feed refreshes use %s", "a Developer feed URL" if url else "the year's"
            )
        self._feed_url = url

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
        closed: asyncio.Event | None = None,
    ) -> asyncio.Task[None]:
        """Start a background refresh, unless one is running already (single flight).

        The refresh it starts is automatic, so quiet: it leaves ``status()`` as it was
        (D-181). Call it from the event loop's thread (D-70 rule 7). Expected failures
        never raise, they set ``problem``. An unexpected error is logged as soon as the
        refresh ends, whether or not anyone awaits the task (D-71); ``refresh()``
        callers also get it raised.

        Args:
            storage: Where the feed cache lives.
            year: The year's data: the feed URL (unless ``set_feed_url()`` gave one)
                and feed settings.
            transport: The HTTP transport; tests pass an ``httpx.MockTransport``.
            closed: Set when the store's session has been replaced (``Services.closed``,
                D-147). A refresh that ends after it is set writes nothing: neither the
                cache nor the store, whose subscribers belong to a destroyed session
                (F30).

        Returns:
            The running refresh: the new one, or the one already in flight.
        """
        if self._task is None or self._task.done():
            self._started_at = clock.now()
            url = self._feed_url or year.conference.feed_url
            self._task = asyncio.create_task(
                self._refresh(url, storage, year, transport, closed)
            )
            self._task.add_done_callback(_log_unexpected)
        return self._task

    def refresh_due(self) -> bool:
        """Return whether an automatic refresh is due (D-40).

        It is due when no refresh has started in this session, or when the last one
        started ``REFRESH_EVERY`` or more ago by ``clock.now()``, whatever its outcome:
        the interval counts from the last attempt, not from the data's age, so a phone
        without a network retries every 15 min rather than on every check. A clock set
        back before the last start (the Developer fake clock) makes it due as well.
        Never while one is running: that one is the attempt.
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
            closed: Set when the store's session has been replaced; see
                ``start_refresh``.

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
            closed: Set when the store's session has been replaced; see
                ``start_refresh``.
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
        """Fetch, parse, cache and publish; on any expected failure keep what is published."""

        def session_closed() -> bool:
            if closed is None or not closed.is_set():
                return False
            logger.info("Feed refresh ended after its session closed; nothing written")
            return True

        self.refreshing = True
        try:
            result = await _fetch(url, year, transport)
            if session_closed():
                return
            if isinstance(result, str):
                self.problem = result
                return
            raw, data = result
            # Only a feed that parsed is cached (D-39). A failed write is logged and the
            # parsed data is still published (D-120).
            await storage.write_feed(raw)
            if not session_closed():
                self._publish(data, "network", clock.now())
        finally:
            self._asked = False  # private: the next refresh starts quiet (D-181)
            # A closed session's store must not be written at all (F30).
            if closed is None or not closed.is_set():
                self.refreshing = False

    def _publish(
        self, data: ConferenceData, source: Source, fetched_at: datetime
    ) -> None:
        self.data = data  # a new frozen eq=False object: always notifies (F5)
        self.source = source
        self.fetched_at = fetched_at
        self.problem = None
        self.version += 1


async def _fetch(
    url: str, year: YearData, transport: httpx.AsyncBaseTransport | None
) -> tuple[bytes, ConferenceData] | Problem:
    """Fetch and process the feed; return its bytes and data, or why that failed (D-146)."""
    try:
        raw = await api.fetch_feed(url, transport=transport)
        return raw, feed.process(raw, year.feed_settings)  # on the loop (D-109)
    except api.NetworkError as error:
        logger.info("Feed refresh: no answer (%s); keeping the current data", error)
        return "offline"
    except (api.ApiError, feed.FeedError) as error:
        logger.warning("Feed refresh failed (%s); keeping the current data", error)
        return "server"


def _log_unexpected(task: asyncio.Task[None]) -> None:
    """Log a refresh that failed with an unexpected error, as soon as it ends (D-71).

    Without it, the error of a refresh nobody awaits would surface only when the finished
    task is garbage collected, which ``Conference._task`` delays until the next refresh.
    """
    if not task.cancelled() and (error := task.exception()) is not None:
        logger.error("Feed refresh failed unexpectedly", exc_info=error)


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


@dataclass
class ViewMemory:
    """Where the user left the app, kept for the whole Python process (D-18, D-143).

    Plain, not observable: writing it re-renders nothing. ``main.py`` creates one at
    import and every session's ``App`` gets that one, so a new session in the same
    process (an Android activity recreation, F26, or a relaunch after Back on Now, F29)
    finds it as the user left it. Fields join with the screens that remember something
    (the Schedule's day and offsets; the search query and scope from P1).

    Attributes:
        last_location: The top View's route, where the start route returns a new
            session (D-143, #74); empty until a screen records it.
        search_base: The location, query included, that opened ``/search``; Back from
            search returns there (D-19). The opener records it.
        schedule_day: The day the Schedule shows; None until the user picks one, so
            the Schedule opens on today during the conference (SCHED-01).
        schedule_offsets: Each day list's scroll offset when its last scroll ended,
            in logical pixels: the Schedule puts it back when the list shows again.
        jumped_to_now: Whether the Schedule has jumped to the current slot in this
            process: it does so once, on the first display of today (D-18, D-155).
        search_query: What is typed in the search field; an opener clears it, so
            each search starts empty (D-193).
        search_scope: The search's scope, one of ``core.search.SCOPES``, for a Search
            View that mounts without its ``?scope=`` (a deep entry below a result).
        room_highlights: The session each mounted room View has highlighted, by its
            View path (ROOM-03): a View rebuilt in a new session from the same
            location (D-143) finds its own and neither scrolls nor lights up again
            (D-18). The View removes its entry when it leaves, so the next room tile
            highlights again.
    """

    last_location: str = ""
    search_base: str = "/now"
    schedule_day: date | None = None
    schedule_offsets: dict[date, float] = field(default_factory=dict)
    jumped_to_now: bool = False
    search_query: str = ""
    search_scope: str = "all"
    room_highlights: dict[str, str] = field(default_factory=dict)
