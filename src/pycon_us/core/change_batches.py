"""The change log's batches and their JSON form, ``changes-<year>.json`` (D-47, D-255; NEW-04).

A refresh whose diff finds changes records them as one ``Batch``: when they were detected,
the changes, and whether the user has seen them. The log keeps the batches of the last 14
days (``trim()``). Encoding and decoding are pure; ``services/changes_file.py`` reads and
writes the file.

The file is a JSON list of batches, each one an object::

    {"detected_at": "2026-05-16T17:42:00+00:00", "seen": false,
     "changes": [{"id": "142", "kind": "room",
                  "old": {"title": "...", "start": "2026-05-16T10:30:00-07:00",
                          "end": "2026-05-16T11:00:00-07:00", "location": "Room 101A"},
                  "new": {...}}]}

Times are ISO 8601 with their offset; ``old`` is null for an addition and ``new`` for a
removal, as in ``Change``.
"""

import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo
from typing import Any

from pycon_us.core.diff import Change, ChangeKind, Listing

logger = logging.getLogger(__name__)

KEPT_FOR = timedelta(days=14)
"""How long the log keeps a batch after its detection (architecture §7.9)."""


@dataclass(frozen=True)
class Batch:
    """The changes one refresh brought, as the log keeps them.

    Attributes:
        detected_at: When the refresh that found them published (aware).
        changes: What changed, in ``diff()``'s order.
        seen: Whether the user has seen them on Schedule changes (ux.md §6.4).
    """

    detected_at: datetime
    changes: tuple[Change, ...]
    seen: bool = False


def trim(batches: Iterable[Batch], now: datetime) -> list[Batch]:
    """Return the batches detected in the 14 days up to ``now``, in their order.

    A batch detected exactly 14 days before ``now`` is kept; one a moment older goes. A
    batch detected after ``now`` (the Developer fake clock set back) is kept.

    Args:
        batches: The log's batches.
        now: The current instant (aware), ``clock.now()``.
    """
    return [batch for batch in batches if now - batch.detected_at <= KEPT_FOR]


def encode_batches(batches: Iterable[Batch]) -> bytes:
    """Return the batches as the log file's bytes, UTF-8 JSON, in their order.

    Args:
        batches: The batches to keep; their times must be aware.
    """
    return json.dumps(
        [_encoded_batch(batch) for batch in batches], ensure_ascii=False
    ).encode()


def decode_batches(raw: bytes, zone: tzinfo) -> list[Batch]:
    """Return the batches that the log file's bytes hold, in their order.

    What can be read is read: a batch that is not as ``encode_batches()`` writes it (a
    field missing or of the wrong type, an unknown kind, a time without an offset) is
    skipped and logged, and the others are kept. Bytes that are not a JSON list give no
    batches (logged). Nothing raises: the log is a convenience, never a reason to stop.

    Args:
        raw: The file's bytes.
        zone: The conference's time zone; every time is read back in it, so a row shows
            it as it showed before (D-43).
    """
    try:
        items = json.loads(raw)
    except ValueError as error:  # JSONDecodeError and UnicodeDecodeError are both
        logger.warning("The change log is not JSON; nothing read: %s", error)
        return []
    if not isinstance(items, list):
        logger.warning("The change log is not a list; nothing read")
        return []
    batches: list[Batch] = []
    for index, item in enumerate(items):
        try:
            batches.append(_batch(item, zone))
        except (KeyError, TypeError, ValueError) as error:
            logger.warning(
                "Skipped change batch %d of the log: %s: %s",
                index,
                type(error).__name__,
                error,
            )
    return batches


# ------------------------------------------------------------------ encoding


def _encoded_batch(batch: Batch) -> dict[str, Any]:
    return {
        "detected_at": batch.detected_at.isoformat(),
        "seen": batch.seen,
        "changes": [_encoded_change(change) for change in batch.changes],
    }


def _encoded_change(change: Change) -> dict[str, Any]:
    return {
        "id": change.id,
        "kind": change.kind.value,
        "old": _encoded_listing(change.old),
        "new": _encoded_listing(change.new),
    }


def _encoded_listing(listing: Listing | None) -> dict[str, str] | None:
    if listing is None:
        return None
    return {
        "title": listing.title,
        "start": listing.start.isoformat(),
        "end": listing.end.isoformat(),
        "location": listing.location,
    }


# ------------------------------------------------------------------ decoding


def _batch(item: Any, zone: tzinfo) -> Batch:
    """Return the batch ``item`` holds; raise KeyError, TypeError or ValueError if none."""
    if not isinstance(item, dict):
        raise TypeError("a batch is not an object")
    changes, seen = item["changes"], item["seen"]
    if not isinstance(changes, list) or not isinstance(seen, bool):
        raise TypeError("its changes are not a list or its seen mark not a bool")
    return Batch(
        detected_at=_time(item["detected_at"], zone),
        changes=tuple(_change(change, zone) for change in changes),
        seen=seen,
    )


def _change(item: Any, zone: tzinfo) -> Change:
    """Return the change ``item`` holds, whose sides must match its kind."""
    if not isinstance(item, dict):
        raise TypeError("a change is not an object")
    key = _text(item["id"])
    kind = ChangeKind(item["kind"])
    old, new = _listing(item["old"], zone), _listing(item["new"], zone)
    # An addition has no old side and a removal no new one; every other kind has both.
    sides = (kind is not ChangeKind.ADDED, kind is not ChangeKind.REMOVED)
    if (old is not None, new is not None) != sides:
        raise ValueError(f"a {kind.value} change with the wrong sides")
    return Change(key, kind, old, new)


def _listing(item: Any, zone: tzinfo) -> Listing | None:
    """Return the listing ``item`` holds, or None for a JSON null."""
    if item is None:
        return None
    if not isinstance(item, dict):
        raise TypeError("a listing is not an object")
    return Listing(
        title=_text(item["title"]),
        start=_time(item["start"], zone),
        end=_time(item["end"], zone),
        location=_text(item["location"]),
    )


def _text(value: Any) -> str:
    """Return ``value``, which must be a string."""
    if not isinstance(value, str):
        raise TypeError("a text field is not a string")
    return value


def _time(value: Any, zone: tzinfo) -> datetime:
    """Return the ISO 8601 time ``value`` in ``zone``; a time without an offset fails."""
    moment = datetime.fromisoformat(_text(value))
    if moment.tzinfo is None:
        raise ValueError("a time without an offset")
    return moment.astimezone(zone)
