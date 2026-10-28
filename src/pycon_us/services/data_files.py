"""The durable data directory and its files, written atomically (STORE-01; D-39, D-108).

``data_dir()`` is where the files go; ``write_atomic()`` replaces one so that readers
see the old file or the new, and ``unlink()`` deletes one, never in the middle of a
write. ``services/storage.py``'s ``Storage`` writes the feed cache and the change log
through them, off the event loop, and logs their failures (D-120).
"""

import contextlib
import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR_VARIABLE = "FLET_APP_STORAGE_DATA"
"""Set by packaged builds and by ``flet run`` to the durable, app-private directory (F14)."""

FALLBACK_DATA_DIR = Path(".flet", "storage", "data")
"""Used under the working directory when the variable is unset, as ``flet run`` would set it."""

write_lock = threading.Lock()
"""Gives writes and deletions turns, a cancelled one's too (D-120), not order (D-244)."""


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
    with write_lock:
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


def unlink(path: Path) -> None:
    """Delete ``path`` if it exists, never in the middle of a ``write_atomic`` (the lock)."""
    with write_lock:
        path.unlink(missing_ok=True)


def read_feed_file(path: Path) -> CachedFeed | None:
    """Return the feed cache at ``path``, or None when it is missing or unreadable."""
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
