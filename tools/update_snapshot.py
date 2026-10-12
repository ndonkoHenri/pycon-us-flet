"""Refresh the bundled feed snapshot from the public feed (D-38, NEW-03).

Run it before a build for testers (``docs/development.md`` §8.3)::

    uv run python tools/update_snapshot.py

It fetches the public feed of ``config.YEAR`` from the year's ``feed_url`` and checks it with
``feed.process``, the app's own parser. A feed that does not parse, or that has a record the
parser skips, is refused and nothing changes. Otherwise it writes the bytes unchanged to
``data/<year>/conference.json``, records the time in ``conference.toml``'s
``snapshot_captured_at``, and prints how the counts changed. Both files are replaced
atomically.
"""

import re
import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path

import httpx

from pycon_us.config import (
    DATA_DIR,
    SNAPSHOT_FILE,
    YEAR,
    Snapshot,
    YearData,
    YearDataError,
    load_year,
)
from pycon_us.core.feed import FeedError, process
from pycon_us.core.models import ConferenceData
from pycon_us.services.storage import write_atomic

TIMEOUT = 30.0
"""Seconds to wait for the feed; the 2026 feed is about 800 KB."""

_CAPTURED_LINE = re.compile(r"^snapshot_captured_at\s*=.*$", re.MULTILINE)
_FEED_URL_LINE = re.compile(r"^feed_url\s*=.*$", re.MULTILINE)


class SnapshotError(Exception):
    """The new feed was refused; the snapshot and ``conference.toml`` are unchanged."""


def update_snapshot(
    year: int = YEAR,
    data_dir: Path = DATA_DIR,
    *,
    transport: httpx.BaseTransport | None = None,
    now: datetime | None = None,
) -> str:
    """Replace a year's bundled snapshot with its current public feed.

    Args:
        year: The conference year; its feed URL comes from its ``conference.toml``.
        data_dir: The folder that holds the year folders.
        transport: The HTTP transport; tests pass an ``httpx.MockTransport``.
        now: The capture time to record (aware); defaults to the current time.

    Returns:
        A report for the terminal: the source, the bytes and the count changes.

    Raises:
        SnapshotError: The feed could not be fetched, does not parse, or has records the
            parser skips; nothing was written.
        YearDataError: The year's data files are invalid.
        OSError: Writing a file failed; that file is unchanged (``write_atomic``).
    """
    year_data = load_year(year, data_dir)
    conference = year_data.conference
    raw = _fetch(conference.feed_url, transport)
    try:
        new = process(raw, year_data.feed_settings)
    except FeedError as error:
        raise SnapshotError(f"the feed does not parse: {error}") from None
    if new.skipped:
        lines = "\n".join(f"  {reason}" for reason in new.skipped)
        raise SnapshotError(
            f"the parser skips {len(new.skipped)} feed record(s):\n{lines}"
        )

    previous = _previous(year_data)
    captured_at = (now or datetime.now(UTC)).astimezone(conference.zone)
    captured_at = captured_at.replace(microsecond=0)
    toml_path = year_data.folder / "conference.toml"
    toml_text = _with_captured_at(toml_path.read_text(encoding="utf-8"), captured_at)

    write_atomic(year_data.folder / SNAPSHOT_FILE, raw)
    write_atomic(toml_path, toml_text.encode())
    return _report(year_data, captured_at, raw, new, previous)


def main() -> int:
    """Update the active year's snapshot and print the report.

    Returns:
        The exit status: 0 when the snapshot was updated, 1 when the feed was refused.
    """
    try:
        print(update_snapshot())
    except SnapshotError as error:
        print(f"Refused, nothing changed: {error}", file=sys.stderr)
        return 1
    return 0


def _fetch(url: str, transport: httpx.BaseTransport | None) -> bytes:
    try:
        with httpx.Client(
            transport=transport, timeout=TIMEOUT, follow_redirects=True
        ) as client:
            response = client.get(url)
            response.raise_for_status()
    except httpx.HTTPError as error:
        raise SnapshotError(f"could not fetch {url}: {error}") from None
    return response.content


def _previous(year_data: YearData) -> Snapshot | None:
    """Return the snapshot being replaced, or None in a new year folder."""
    try:
        return year_data.read_snapshot()
    except YearDataError:
        return None


def _with_captured_at(text: str, captured_at: datetime) -> str:
    """Return ``conference.toml``'s text with ``snapshot_captured_at`` set.

    Only that line changes, so the hand-written comments stay. A year folder without the
    line (a new year) gets it right after ``feed_url``.
    """
    line = f"snapshot_captured_at = {captured_at.isoformat()}"
    if _CAPTURED_LINE.search(text):
        updated = _CAPTURED_LINE.sub(lambda _: line, text, count=1)
    elif match := _FEED_URL_LINE.search(text):
        updated = f"{text[: match.end()]}\n{line}{text[match.end() :]}"
    else:
        raise SnapshotError(
            "conference.toml has no feed_url line to add the time after"
        )
    if tomllib.loads(updated).get("snapshot_captured_at") != captured_at:
        raise SnapshotError("could not set snapshot_captured_at in conference.toml")
    return updated


def _counts(data: ConferenceData) -> dict[str, int]:
    return {
        "sessions": len(data.sessions),
        "speakers": len(data.speakers),
        "days": len(data.days),
        "posters": len(data.posters),
        "sprints": len(data.sprints),
        "job listings": len(data.job_listings),
    }


def _report(
    year_data: YearData,
    captured_at: datetime,
    raw: bytes,
    new: ConferenceData,
    previous: Snapshot | None,
) -> str:
    """Describe the update: where from, the bytes, and each count before and after."""
    old: dict[str, int] = {}
    if previous is None:
        size = f"{len(raw):,} bytes, the first snapshot"
    else:
        size = f"{len(raw):,} bytes" + (
            ", unchanged" if previous.raw == raw else f" (was {len(previous.raw):,})"
        )
        try:
            old = _counts(process(previous.raw, year_data.feed_settings))
        except FeedError:  # the parser changed since; there is nothing to compare
            size += "; the previous snapshot no longer parses"
    conference = year_data.conference
    lines = [
        f"Updated {conference.year}/{SNAPSHOT_FILE} from {conference.feed_url}",
        f"captured at {captured_at.isoformat()}; {size}",
    ]
    for name, after in _counts(new).items():
        before = old.get(name)
        change = "" if before in (None, after) else f"  {after - before:+d}"
        was = "-" if before is None else str(before)
        lines.append(f"  {name:<13}{was:>6} -> {after:<6}{change}".rstrip())
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
