"""The ``ChangeLog`` store, with its context and hook: what refreshes changed (D-47, D-255).

NEW-04. A refresh that publishes a new feed hands the feed it replaces and the new one to
``ChangeLog.record()`` (``Conference._refresh``), which diffs them under D-255's rules and
records what changed as one batch (``core/change_batches.py``), kept in
``changes-<year>.json`` (``services/changes_file.py``). A store of its own, not a field of
``Conference``, so ``state.py`` stays the feed's (D-160, D-231). Screens read ``batches``,
``recent()`` and the batch to announce; the reminders' re-plan (#27) subscribes too.
Schedule changes marks batches seen (``mark_seen()``, ux.md §6.4), which Now's card and
Settings › Data count (``unseen_saved()``).
"""

import asyncio
import logging
import time
from collections.abc import Callable, Collection
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, tzinfo

import flet as ft

from pycon_us import clock
from pycon_us.core.change_batches import Batch, trim
from pycon_us.core.change_views import unseen_saved
from pycon_us.core.diff import Change, ChangeKind, diff
from pycon_us.core.models import ConferenceData
from pycon_us.favorites import Favorites
from pycon_us.feed_refresh import Source
from pycon_us.services import changes_file
from pycon_us.services.pref_keys import fetched
from pycon_us.services.storage import Storage

logger = logging.getLogger(__name__)

RECENT_FOR = timedelta(hours=24)
"""How long a time, room or title change marks its session's rows: the Changed badge."""

BADGED = frozenset((ChangeKind.TIME, ChangeKind.ROOM, ChangeKind.TITLE))
"""The kinds the Changed badge marks: none for an addition or a removal (D-255)."""


@dataclass(frozen=True)
class Published:
    """A feed as ``Conference`` published it, one side of the hand-off.

    Attributes:
        data: The processed feed; None before the first publish.
        source: Where it came from.
        url: The feed URL it counts as: the one fetched or cached from, and the year's
            for the bundled snapshot (D-255).
    """

    data: ConferenceData | None
    source: Source
    url: str


# eq=False: a store is one object, compared by identity (F5), as Conference.
@ft.observable
@dataclass(eq=False)
class ChangeLog:
    """The change batches of the active year, newest first, and the one to announce.

    Only ``batches`` is public, so a recorded batch notifies once: the batch to announce
    is set before it. Built by ``App`` with the session's ``Favorites``, which the diff
    over the bundled snapshot keeps to (D-255).

    Attributes:
        batches: The batches of the last 14 days, newest first (``trim()``).
    """

    batches: tuple[Batch, ...] = ()
    _favorites: Favorites | None = field(default=None, repr=False)
    # Whether `pycon.<year>.fetched` is set: a network feed was published (D-255).
    _fetched: bool = field(default=False, repr=False)
    _announce: Batch | None = field(default=None, repr=False)
    # The log's file writes, kept until they land: nobody awaits a cleanup's mark.
    _saves: set[asyncio.Task[bool]] = field(default_factory=set, repr=False)
    # One write at a time, each saving the log as it is once the one before landed:
    # the storage's thread lock gives turns, not order (D-244).
    _writing: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    # Counts the deletions and resets: a write asked for before the latest one is
    # dropped when its turn comes, whatever the order of the turns (``_write()``).
    _generation: int = field(default=0, repr=False)

    async def load(self, storage: Storage, zone: tzinfo) -> None:
        """Read the year's log and its marker; call it once at start, before a refresh.

        Args:
            storage: Where the log and the marker are kept.
            zone: The conference's time zone, which the log's times are read in.
        """
        batches = await changes_file.read_batches(storage, zone)
        self._fetched = await storage.get(fetched(storage.year))
        self.batches = tuple(trim(batches, clock.now()))

    async def delete(self, storage: Storage, reason: str) -> bool:
        """Delete the log, after a file write under way lands (D-244, D-255).

        A write asked for before the deletion and not yet started is dropped, whenever
        its turn comes: the log it would save was the old feed URL's, and landing after
        the deletion would bring the file back. Writes asked for after it land.

        A feed URL change after the load: the log was the old URL's.

        Args:
            storage: Where the log is kept.
            reason: Why, for the log, e.g. "the feed URL changed".

        Returns:
            Whether the file is gone; the batches in memory go either way.
        """
        self._forget()
        async with self._writing:
            return await changes_file.delete_batches(storage, reason)

    def reset(self) -> None:
        """Return to a fresh install's log, without writing: Reset app (D-198, D-255).

        Reset app deletes the file and clears the marker with every ``pycon.`` key; a
        write asked for before the reset and not yet started is dropped, as for
        ``delete()``.
        """
        self._fetched = False
        self._forget()

    def recent(self, now: datetime) -> dict[str, frozenset[ChangeKind]]:
        """Return the sessions to badge as Changed: id → what changed in the last 24 h.

        A change counts for 24 h after its batch's detection (``RECENT_FOR``), seen or
        not; additions and removals never count (D-255). A session changed by two
        batches of the last 24 h has the kinds of both: "Time and room changed".

        Args:
            now: The current instant (aware), ``clock.now()``.
        """
        badged: dict[str, set[ChangeKind]] = {}
        for batch in self.batches:
            if now - batch.detected_at < RECENT_FOR:
                for change in batch.changes:
                    if change.kind in BADGED:
                        badged.setdefault(change.id, set()).add(change.kind)
        return {key: frozenset(kinds) for key, kinds in badged.items()}

    def recent_of(self, session_id: str, now: datetime) -> tuple[Change, ...]:
        """Return a session's badged changes of the last 24 h, one per kind (ux.md §5.5).

        Session detail's badges say the old value ("Moved from Room 102A"), so each kind
        spans every batch of the last 24 h: its old side is the oldest change's, the
        value before the first of them, and its new side the newest change's. A kind
        whose value came back to where it was (a move, then a move back) is left out.

        Args:
            session_id: The session's id (D-42).
            now: The current instant (aware), ``clock.now()``.

        Returns:
            The merged changes in ``ChangeKind``'s order; empty for an unchanged session.
        """
        spans: dict[ChangeKind, Change] = {}
        oldest_first = sorted(self.batches, key=lambda batch: batch.detected_at)
        for batch in oldest_first:
            if now - batch.detected_at >= RECENT_FOR:
                continue
            for change in batch.changes:
                if change.id != session_id or change.kind not in BADGED:
                    continue
                first = spans.get(change.kind)
                old = first.old if first is not None else change.old
                spans[change.kind] = Change(session_id, change.kind, old, change.new)
        return tuple(
            spans[kind]
            for kind in ChangeKind
            if kind in spans and not _came_back(spans[kind])
        )

    @property
    def has_unseen(self) -> bool:
        """Whether a batch is still unseen: Mark all as seen has something to do."""
        return any(not batch.seen for batch in self.batches)

    def unseen_saved(self, saved: Collection[str], now: datetime) -> int:
        """Return how many saved sessions the unseen batches of the last 24 h changed.

        Each session once, additions left out: the count Now's card and Settings ›
        Data show (``core.change_views.unseen_saved()``, ux.md §5.1).

        Args:
            saved: The ids of the saved sessions.
            now: The current instant (aware), ``clock.now()``.
        """
        return unseen_saved(self.batches, saved, now)

    def mark_seen(
        self, storage: Storage, batches: Collection[Batch] | None = None
    ) -> asyncio.Task[bool] | None:
        """Mark ``batches`` seen, or every batch when None, and save the log (ux.md §6.4).

        Synchronous, so a screen's sync cleanup can call it (D-70): the marks apply at
        once and notify, and the file write is a task the store keeps until it lands.
        The write saves the batches as they are when its turn comes (``_save()``), so a
        batch recorded meanwhile is kept.

        Args:
            storage: Where the log is kept.
            batches: The batches to mark, as the caller read them from ``batches``;
                one already marked, or no longer in the log, is skipped.

        Returns:
            The write's task (its result says whether the file was replaced), or None
            when nothing was unseen.
        """
        picked = None if batches is None else {id(batch) for batch in batches}
        marked = tuple(
            replace(batch, seen=True)
            if not batch.seen and (picked is None or id(batch) in picked)
            else batch
            for batch in self.batches
        )
        if all(new is old for new, old in zip(marked, self.batches, strict=True)):
            return None
        self.batches = marked
        return self._save(storage)

    def _save(self, storage: Storage) -> asyncio.Task[bool]:
        """Start writing the log, after the writes before it; return the kept task.

        Every write of the log goes through here, one at a time: each saves the
        batches as they are once the one before it landed, so a seen mark's write can
        never land over a newer batch's. The task is kept until it lands, so a
        cancelled caller (a refresh, a cleanup) leaves it to finish. A deletion or a
        reset before its turn drops it (``delete()``); its result is then False.
        """
        save = asyncio.create_task(self._write(storage, self._generation))
        self._saves.add(save)
        save.add_done_callback(self._saves.discard)
        return save

    async def _write(self, storage: Storage, generation: int) -> bool:
        """Write the log as it is when its turn comes; a failure is logged (D-120).

        Args:
            storage: Where the log is kept.
            generation: ``_generation`` when the write was asked for: once a deletion
                or a reset has changed it, the write is dropped and returns False.
        """
        async with self._writing:
            if generation != self._generation:
                logger.info("Change log write dropped: the log was deleted since")
                return False
            return await changes_file.write_batches(storage, list(self.batches))

    def take_announcement(self) -> Batch | None:
        """Return the batch to announce, once: the next call returns None.

        A batch is announced when it holds a change other than an addition: a batch of
        additions only is recorded silently (D-255).
        """
        batch, self._announce = self._announce, None
        return batch

    async def record(
        self,
        storage: Storage,
        before: Published,
        after: Published,
        current: Callable[[], bool],
    ) -> Batch | None:
        """Record what changed from ``before`` to ``after``, a network feed just published.

        The first network publish of the year saves ``pycon.<year>.fetched``. The diff
        runs under D-255's rules: only against a feed of the same feed URL; over the
        bundled snapshot only before the marker was set and only when sessions are
        saved, keeping their changes and no addition. No change records nothing. Just
        before it writes, ``current()`` says whether the refresh still counts (its URL
        in effect, its session open); when not, nothing is recorded.

        Args:
            storage: Where the log and the marker are kept.
            before: The feed that was shown.
            after: The feed just published, from the network.
            current: ``Conference._refresh``'s check, True while the refresh may write.

        Returns:
            The batch recorded, or None.
        """
        was_fetched = self._fetched
        if not was_fetched:
            self._fetched = True
            await storage.set(fetched(storage.year), True)
        changes = self._changes(before, after, was_fetched)
        if not changes:
            return None
        if not current():  # the last await is behind: nothing can change it now
            logger.info("Change batch of %d changes not recorded", len(changes))
            return None
        batch = Batch(clock.now(), tuple(changes))
        if any(change.kind is not ChangeKind.ADDED for change in changes):
            self._announce = batch  # before `batches`, whose assignment notifies
        self.batches = (batch, *trim(self.batches, batch.detected_at))
        await asyncio.shield(self._save(storage))
        return batch

    def _forget(self) -> None:
        """Clear the batches and the announcement, and drop the writes not yet started."""
        self._generation += 1
        self._announce = None
        self.batches = ()

    def _changes(
        self, before: Published, after: Published, was_fetched: bool
    ) -> list[Change]:
        """Return the changes D-255 records from ``before`` to ``after``; logs why none."""
        if before.data is None or after.data is None:
            return []
        if before.url != after.url:
            logger.info("Not diffed: the feed shown came from another feed URL")
            return []
        saved = self._favorites.ids if self._favorites is not None else frozenset()
        if before.source == "bundled" and (was_fetched or not saved):
            logger.info(
                "Not diffed over the bundled snapshot: %s",
                "a network feed was shown before" if was_fetched else "nothing saved",
            )
            return []
        started = time.perf_counter()
        changes = diff(before.data, after.data)
        if before.source == "bundled":
            changes = [
                change
                for change in changes
                if change.id in saved and change.kind is not ChangeKind.ADDED
            ]
        elapsed = (time.perf_counter() - started) * 1000
        logger.info("Feeds diffed in %.1f ms: %d changes", elapsed, len(changes))
        return changes


def _came_back(change: Change) -> bool:
    """Return whether a merged change ends where it started: nothing to say."""
    old, new = change.old, change.new
    if old is None or new is None:
        return False
    if change.kind is ChangeKind.TIME:
        return (old.start, old.end) == (new.start, new.end)
    if change.kind is ChangeKind.ROOM:
        return old.location == new.location
    return old.title == new.title


ChangeLogCtx: ft.ContextProvider[ChangeLog | None] = ft.create_context(None)
"""Provides the session's ``ChangeLog``; ``App`` writes the provider out (D-69)."""


def use_change_log() -> ChangeLog:
    """Return the ``ChangeLog`` store and re-render the caller when it records a batch (F3).

    Raises:
        RuntimeError: No ``ChangeLogCtx`` provider is above the calling component.
    """
    store = ft.use_context(ChangeLogCtx)
    if store is None:
        raise RuntimeError("use_change_log() needs a ChangeLogCtx provider above it")
    return store
