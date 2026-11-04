"""The change log's file, `changes-<year>.json` in the data directory (D-47, D-255; NEW-04).

The batches a year's refreshes recorded, kept for 14 days (`core/change_batches.py` has
the batches, their JSON form and the trim). Writes and deletions go through `Storage`,
so they keep the feed cache's order: every write, of either file, is a task kept in
`Storage._writes`, and a deletion waits for all of them, so a log write asked for
before a feed URL change cannot land after its deletion and mix two feeds (D-244, D-255).
Failures are logged and returned, never raised (D-120): the batches in memory stay right
for the session.
"""

import asyncio
import logging
from datetime import tzinfo
from pathlib import Path

from pycon_us.core.change_batches import Batch, decode_batches, encode_batches
from pycon_us.services.storage import Storage

logger = logging.getLogger(__name__)


def changes_path(storage: Storage) -> Path:
    """Return the change log of `storage`'s year, `changes-<year>.json`.

    Args:
        storage: The session's storage: its data directory and year.
    """
    return storage.directory / f"changes-{storage.year}.json"


async def read_batches(storage: Storage, zone: tzinfo) -> list[Batch]:
    """Read the year's change log.

    Args:
        storage: The session's storage.
        zone: The conference's time zone, which every time is read back in.

    Returns:
        The batches in the file's order; none when there is no file, or it cannot be
        read (logged). A file that is partly corrupt gives the batches that can be read
        (`decode_batches()`, logged).
    """
    raw = await asyncio.to_thread(_read, changes_path(storage))
    return [] if raw is None else decode_batches(raw, zone)


async def write_batches(storage: Storage, batches: list[Batch]) -> bool:
    """Replace the year's change log with `batches`, atomically.

    The caller trims them first (`trim()`) and gives them in the order to keep.

    Args:
        storage: The session's storage.
        batches: Every batch to keep.

    Returns:
        Whether the file was replaced; on a failure (logged) the previous file stays.
    """
    return await storage.write_file(changes_path(storage), encode_batches(batches))


async def delete_batches(storage: Storage, reason: str) -> bool:
    """Delete the year's change log, once every file write asked for before it lands.

    A feed URL change after the load and Reset app delete it (D-255, D-198).

    Args:
        storage: The session's storage.
        reason: Why, for the log, e.g. "Reset app".

    Returns:
        Whether the file is gone (or there was none); a failure is logged.
    """
    return await storage.delete_file(changes_path(storage), reason)


def _read(path: Path) -> bytes | None:
    """Return the bytes of `path`, or None when it is missing or unreadable (logged)."""
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError:
        logger.warning("Could not read the change log %s", path.name, exc_info=True)
        return None
