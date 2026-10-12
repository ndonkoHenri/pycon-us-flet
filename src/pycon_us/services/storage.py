"""Where the app keeps things between launches (STORE-01; D-39, D-49, D-108).

Two places, one job each:

* **SharedPreferences** for small values. Every key is a ``Pref`` in the table
  below, prefixed ``pycon.``, with its type and default. SharedPreferences
  takes only ``str``, ``int``, ``float``, ``bool`` and ``list[str]`` (F12), so
  dict values are stored as JSON strings.
* **Files in the durable data directory** (``FLET_APP_STORAGE_DATA``) for the
  raw feed cache, ``feed-<year>.json``. Files are replaced atomically, so a
  reader sees the old file or the new one, never half of one.

Storage failures are expected failures (D-71): they are logged and returned,
never raised, because the data in memory stays correct for the session and the
next write tries again (D-120). The one exception is a data directory that
cannot be created, which means a broken install.
"""

import asyncio
import contextlib
import copy
import json
import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import flet as ft

logger = logging.getLogger(__name__)

DATA_DIR_VARIABLE = "FLET_APP_STORAGE_DATA"
"""Set by packaged builds and by ``flet run`` to the durable, app-private directory (F14)."""

FALLBACK_DATA_DIR = Path(".flet", "storage", "data")
"""Used under the working directory when the variable is unset, as ``flet run`` would set it."""

PREFS_ERRORS = (TimeoutError, RuntimeError)
"""What a SharedPreferences call raises when the Flutter side times out or fails."""

_write_lock = threading.Lock()
"""Serialises ``write_atomic``: a cancelled ``to_thread`` write keeps running (D-120)."""


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
# P3 adds `pycon.account`, `pycon.staff_sponsor`, `pycon.start_screen` and
# `pycon.<year>.favorites_dirty` here, with the features that use them.

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

APP_PREFS: tuple[Pref[Any], ...] = (
    THEME,
    HIGH_CONTRAST,
    ONBOARDED,
    EXCLUDED_TRACKS,
    REMINDERS,
    DEV,
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
        year: The conference year whose feed is cached.
    """

    prefs: ft.SharedPreferences
    directory: Path
    year: int

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
            stored = await self.prefs.get(pref.key)
        except PREFS_ERRORS:
            logger.warning("Could not read preference %s", pref.key, exc_info=True)
            return copy.deepcopy(pref.default)
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
        except PREFS_ERRORS:
            logger.warning("Could not save preference %s", pref.key, exc_info=True)
            return False
        if not saved:
            logger.warning("Could not save preference %s", pref.key)
        return saved

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
        """Replace the feed cache atomically (D-39).

        Call it only after ``raw`` parsed successfully, so the cache always holds
        the last good feed. Nothing deletes the cache first, so a failed refresh
        keeps it.

        Args:
            raw: The feed bytes exactly as downloaded.

        Returns:
            Whether the cache was replaced; a failure is logged and the previous
            cache stays.
        """
        try:
            await asyncio.to_thread(write_atomic, self.feed_path, raw)
        except OSError:
            logger.warning(
                "Could not save the feed cache %s", self.feed_path.name, exc_info=True
            )
            return False
        return True

    async def delete_feed(self, reason: str) -> None:
        """Delete the feed cache and log why, e.g. because it no longer parses.

        The app then continues from the bundled snapshot (D-39).

        Args:
            reason: Why, for the log, e.g. "it does not parse: <error>".
        """
        logger.warning("Deleting the cached feed %s: %s", self.feed_path.name, reason)
        try:
            self.feed_path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Could not delete %s", self.feed_path.name, exc_info=True)


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
