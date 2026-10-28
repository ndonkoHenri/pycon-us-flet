"""Where the app keeps things between launches (STORE-01; D-39, D-49, D-108).

Two places, one job each:

* **SharedPreferences** for small values. Every key is a ``Pref`` in the table below,
  prefixed ``pycon.``, with its type and default. SharedPreferences takes only ``str``,
  ``int``, ``float``, ``bool`` and ``list[str]`` (F12), so dict values are JSON strings.
* **Files in the durable data directory** (``FLET_APP_STORAGE_DATA``) for the raw feed
  cache, ``feed-<year>.json``, and the change log, ``changes-<year>.json``
  (``changes_file.py``), replaced atomically: readers see the old file or the new.

Storage failures are expected (D-71): logged and returned, never raised, because the
data in memory stays correct for the session and the next write tries again (D-120).
The one exception is a data directory that cannot be created: a broken install.
"""

import asyncio
import contextlib
import copy
import json
import logging
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import flet as ft

logger = logging.getLogger(__name__)

DATA_DIR_VARIABLE = "FLET_APP_STORAGE_DATA"
"""Set by packaged builds and by ``flet run`` to the durable, app-private directory (F14)."""

FALLBACK_DATA_DIR = Path(".flet", "storage", "data")
"""Used under the working directory when the variable is unset, as ``flet run`` would set it."""

SERVICE_ERRORS = (TimeoutError, RuntimeError)
"""What any call to the Flutter side raises (``session.invoke_method``: SharedPreferences,
SemanticsService, UrlLauncher, Clipboard, ``page.get_device_info``) when it times out
(``TimeoutError``) or reports an error (``RuntimeError``); the app's one name for it.
Both messages can repeat the call's arguments: where those hold personal data (an email
address), a log names the class only (D-72)."""

_write_lock = threading.Lock()
"""Gives writes and deletions turns, a cancelled one's too (D-120), not order (D-244)."""


@dataclass(frozen=True)
class Pref[T]:
    """One SharedPreferences key, with the type and default of its value.

    The default's type is the value's type. A dict default means the value is
    stored as a JSON object string, since SharedPreferences cannot hold dicts.

    Attributes:
        key: The SharedPreferences key, prefixed ``pycon.``.
        default: The value used when the key is absent or unreadable.
    """

    key: str
    default: T


# ------------------------------------------------------------------ the key table (decisions §M)

PREFIX = "pycon."
"""Starts every key the app keeps in SharedPreferences, app-wide and per year."""

# P3 adds `pycon.staff_sponsor` and `pycon.start_screen` here, with the features that
# use them.

THEME: Pref[str] = Pref("pycon.theme", "system")
"""``system``, ``light`` or ``dark`` (THEME-01)."""

HIGH_CONTRAST: Pref[str] = Pref("pycon.high_contrast", "system")
"""``system``, ``on`` or ``off`` (THEME-01)."""

ONBOARDED: Pref[bool] = Pref("pycon.onboarded", False)
"""Whether the Welcome screen was seen (STORE-07)."""

EXCLUDED_TRACKS: Pref[list[str]] = Pref("pycon.excluded_tracks", ["Open Space"])
"""Track keys hidden from the schedule; a stored ``[]`` hides nothing (STORE-09)."""

REMINDERS: Pref[dict[str, Any]] = Pref("pycon.reminders", {})
"""Reminder settings, merged over the store's defaults (P2)."""

DEV: Pref[dict[str, Any]] = Pref("pycon.dev", {})
"""Developer options, merged over the store's defaults (D-73)."""

ACCOUNT: Pref[dict[str, Any]] = Pref("pycon.account", {})
"""The signed-in mock account: ``email``, ``nickname`` and ``features`` (P3, D-49).
Its key and secret are ``services/credentials.py``'s, never here."""

APP_PREFS: tuple[Pref[Any], ...] = (
    THEME,
    HIGH_CONTRAST,
    ONBOARDED,
    EXCLUDED_TRACKS,
    REMINDERS,
    DEV,
    ACCOUNT,
)
"""Every app-wide key; per-year keys are built by the functions below."""


def favorites(year: int) -> Pref[list[str]]:
    """Return the key of a conference year's favourite session ids (D-48).

    Args:
        year: The conference year; ids are unique only within one year's feed.

    Returns:
        The ``pycon.<year>.favorites`` key, a ``list[str]`` that defaults to empty.
    """
    return Pref(f"pycon.{year}.favorites", [])


def favorites_sync(year: int) -> Pref[str]:
    """Return the key of what the account has of a year's favourites (D-55, D-406).

    Args:
        year: The conference year, as ``favorites(year)``'s.

    Returns:
        The ``pycon.<year>.favorites_sync`` key, a ``core.favorites_sync.SyncState``
        value; absent, ``merge``: the next pull takes the union. A sign-in and a
        sign-out remove it.
    """
    return Pref(f"pycon.{year}.favorites_sync", "merge")


def fetched(year: int) -> Pref[bool]:
    """Return the key that says a network feed of ``year`` was published (D-255).

    Saved by the install's first network publish for the year: from then on a refresh
    over the bundled snapshot is not diffed (``ChangeLog``). Reset app clears it.
    """
    return Pref(f"pycon.{year}.fetched", False)


# ------------------------------------------------------------------ files


def data_dir() -> Path:
    """Return the durable data directory, creating it when needed.

    Call it on every start and never store the result: iOS moves the app's data
    container on an update (D-108). Outside ``flet run`` and packaged builds,
    for example under pytest, the directory is ``.flet/storage/data`` under the
    working directory.

    Returns:
        An absolute path to an existing directory.

    Raises:
        OSError: The directory cannot be created, which means a broken install,
            not an expected failure (D-120).
    """
    configured = os.environ.get(DATA_DIR_VARIABLE)
    path = Path(configured) if configured else Path.cwd() / FALLBACK_DATA_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path.absolute()


def write_atomic(path: Path, data: bytes) -> None:
    """Write ``data`` to ``path`` so that readers see the old file or the new one.

    The bytes go to ``<name>.tmp`` next to ``path``, are flushed to disk, and
    the temp file then replaces ``path`` in one ``os.replace``. A force-stop
    during the write leaves the previous file intact (S1). Writers take turns
    (a lock), because they share the temp file: a refresh whose task was
    cancelled can still be writing in its thread when the next one starts.

    Args:
        path: The file to replace.
        data: Its new content.

    Raises:
        OSError: The write failed; ``path`` is unchanged, and the temp file is
            removed when the file system allows it.
    """
    tmp = path.with_name(path.name + ".tmp")
    with _write_lock:
        try:
            with open(tmp, "wb") as file:
                file.write(data)
                file.flush()
                os.fsync(file.fileno())
            os.replace(tmp, path)
        except OSError:
            with contextlib.suppress(OSError):  # keep the original error
                tmp.unlink(missing_ok=True)
            raise


@dataclass(frozen=True, eq=False)
class CachedFeed:
    """The raw feed bytes last saved after a good parse.

    Attributes:
        raw: The feed exactly as downloaded, so the current parser reads it (D-47).
        saved_at: When it was saved, in seconds since the epoch (the file's mtime).
    """

    raw: bytes
    saved_at: float


def _unlink(path: Path) -> None:
    """Delete ``path`` if it exists, never in the middle of a ``write_atomic`` (the lock)."""
    with _write_lock:
        path.unlink(missing_ok=True)


def _read_feed_file(path: Path) -> CachedFeed | None:
    try:
        with open(path, "rb") as file:
            return CachedFeed(
                raw=file.read(), saved_at=os.fstat(file.fileno()).st_mtime
            )
    except FileNotFoundError:
        return None
    except OSError:
        logger.warning("Could not read the cached feed %s", path.name, exc_info=True)
        return None


# ------------------------------------------------------------------ the service


@dataclass(frozen=True, eq=False)
class Storage:
    """SharedPreferences and the data directory, for one conference year.

    Built once per session in ``Services.create()``; screens reach it through
    ``use_services()``.

    Attributes:
        prefs: The page's SharedPreferences service.
        directory: The durable data directory, from ``data_dir()``.
        year: The conference year whose feed and favourites are kept.
    """

    prefs: ft.SharedPreferences
    directory: Path
    year: int
    # The file writes not landed yet, even those whose caller was cancelled (D-244).
    _writes: set[asyncio.Task[bool]] = field(default_factory=set, init=False)

    async def get[T](self, pref: Pref[T]) -> T:
        """Read a preference.

        Args:
            pref: A key from the table.

        Returns:
            The stored value, or a copy of the default when the key is absent,
            its value is not of the pref's type, or SharedPreferences fails (the
            last two are logged).
        """
        try:
            return await self.read(pref)
        except SERVICE_ERRORS:
            logger.warning("Could not read preference %s", pref.key, exc_info=True)
            return copy.deepcopy(pref.default)

    async def read[T](self, pref: Pref[T]) -> T:
        """Read a preference, raising when SharedPreferences fails.

        For a store that must not mistake a failed read for an empty value: the
        favourites, which would otherwise write that empty value over the saved one
        (D-172). Everything else uses ``get``.

        Args:
            pref: A key from the table.

        Returns:
            The stored value, or a copy of the default when the key is absent or its
            value is not of the pref's type (logged).

        Raises:
            TimeoutError: SharedPreferences did not answer (``SERVICE_ERRORS``).
            RuntimeError: SharedPreferences reported an error (``SERVICE_ERRORS``).
        """
        stored = await self.prefs.get(pref.key)
        if stored is None:
            return copy.deepcopy(pref.default)
        value = _decode(pref, stored)
        if value is None:
            logger.warning("Preference %s is unreadable; using its default", pref.key)
            return copy.deepcopy(pref.default)
        return value

    async def set[T](self, pref: Pref[T], value: T) -> bool:
        """Save a preference, JSON-encoding dict values.

        Args:
            pref: A key from the table.
            value: The new value, of the pref's type.

        Returns:
            Whether SharedPreferences saved it; a failure is logged. A store that
            saves what the user chose shows the failure too (D-120).
        """
        # A T that is not a dict is one of the SharedPreferences types (F12).
        stored: Any = json.dumps(value) if isinstance(pref.default, dict) else value
        try:
            saved = await self.prefs.set(pref.key, stored)
        except SERVICE_ERRORS as error:
            # The class only: Flet's error repeats the call's arguments, the value
            # among them, e.g. the account's email (D-72).
            logger.warning(
                "Could not save preference %s: %s", pref.key, type(error).__name__
            )
            return False
        if not saved:
            logger.warning("Could not save preference %s", pref.key)
        return saved

    async def remove(self, pref: Pref[Any]) -> bool:
        """Remove a preference, so it reads as its default again.

        Args:
            pref: A key from the table.

        Returns:
            Whether the key is gone (or was never there); a failure is logged with
            the key, never the value (D-120).
        """
        try:
            # SharedPreferences answers False for an absent key too: ask first.
            present = await self.prefs.contains_key(pref.key)
            if present and not await self.prefs.remove(pref.key):
                logger.warning("Could not remove preference %s", pref.key)
                return False
        except SERVICE_ERRORS:
            logger.warning("Could not remove preference %s", pref.key, exc_info=True)
            return False
        return True

    @property
    def feed_path(self) -> Path:
        """The feed cache, ``feed-<year>.json`` in the data directory."""
        return self.directory / f"feed-{self.year}.json"

    async def read_feed(self) -> CachedFeed | None:
        """Read the feed cache.

        Returns:
            The cached bytes and when they were saved, or None when there is no
            cache or it cannot be read (logged). The bytes are not checked: the
            caller parses them and calls ``delete_feed`` when that fails.
        """
        return await asyncio.to_thread(_read_feed_file, self.feed_path)

    async def write_feed(self, raw: bytes) -> bool:
        """``write_file`` the feed cache (D-39), only with bytes that parsed.

        So the cache always holds the last good feed; nothing deletes it first, so a
        failed refresh keeps it.
        """
        return await self.write_file(self.feed_path, raw)

    async def write_file(self, path: Path, data: bytes) -> bool:
        """Replace a data directory file atomically: the feed cache or the change log.

        The write is a task of its own, kept in ``_writes`` until it lands: a cancelled
        caller leaves it to land, as its thread does, and ``delete_file`` waits for it.

        Args:
            path: The file, in ``directory``.
            data: Its new content.

        Returns:
            Whether the file was replaced; a failure is logged and the previous file
            stays (D-120).
        """
        write = asyncio.create_task(self._write(path, data))
        self._writes.add(write)
        write.add_done_callback(self._writes.discard)
        return await asyncio.shield(write)

    async def _write(self, path: Path, data: bytes) -> bool:
        try:
            await asyncio.to_thread(write_atomic, path, data)
        except OSError:
            logger.warning("Could not save %s", path.name, exc_info=True)
            return False
        return True

    async def delete_feed(self, reason: str) -> bool:
        """``delete_file`` the feed cache; the next start then uses the snapshot (D-39).

        The one way the cache goes: a cache that no longer parses, a feed URL change
        after the load (D-255), and Clear cached feed and Reset app (D-198).
        """
        return await self.delete_file(self.feed_path, reason)

    async def delete_file(self, path: Path, reason: str) -> bool:
        """Delete a data directory file, and log why, after every write asked before it.

        Every ``write_file`` asked for before it lands first, of either file and a
        cancelled caller's too: the threads' lock gives turns, not order, so a write
        could bring the file back (D-244), or a log write mix two feeds (D-255).

        Args:
            path: The file, in ``directory``.
            reason: Why, for the log, e.g. "Reset app".

        Returns:
            Whether the file is gone (or there was none); a failure is logged.
        """
        logger.warning("Deleting %s: %s", path.name, reason)
        if self._writes:
            await asyncio.wait(set(self._writes))
        try:
            await asyncio.to_thread(_unlink, path)
        except OSError:
            logger.warning("Could not delete %s", path.name, exc_info=True)
            return False
        return True

    async def clear_prefs(self) -> bool:
        """Remove every key the app keeps in SharedPreferences: all of ``PREFIX``.

        Reset app (DEV-05, D-198): the settings, every year's favourites and the
        Developer options. Keys outside ``PREFIX`` are not the app's and stay.

        Returns:
            Whether every key is gone; a failure is logged with the key, never the
            value (D-120).
        """
        try:
            keys = await self.prefs.get_keys(PREFIX)
        except SERVICE_ERRORS:
            logger.warning("Could not list the preferences", exc_info=True)
            return False
        cleared = True
        for key in keys:
            try:
                removed = await self.prefs.remove(key)
            except SERVICE_ERRORS:
                logger.warning("Could not remove preference %s", key, exc_info=True)
                removed = False
            else:
                if not removed:
                    logger.warning("Could not remove preference %s", key)
            cleared = cleared and removed
        return cleared


def _decode[T](pref: Pref[T], stored: object) -> T | None:
    """Return ``stored`` as the pref's type, or None when it is not one."""
    value = stored
    if isinstance(pref.default, dict):
        if not isinstance(stored, str):
            return None
        try:
            value = json.loads(stored)
        except json.JSONDecodeError:
            return None
    if isinstance(pref.default, list):
        valid = isinstance(value, list) and all(isinstance(item, str) for item in value)
    else:
        valid = type(value) is type(pref.default)  # `is`: a bool is not an int here
    return cast(T, value) if valid else None
