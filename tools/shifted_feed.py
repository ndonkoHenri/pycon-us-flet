"""Write the bundled feed shifted in time, so reminders can be checked in real time (P2-23).

The Developer fake clock moves what the app shows, but the OS fires reminders at real
instants, so a May session cannot be checked in October. This tool writes a copy of the
bundled snapshot (``data/<year>/conference.json``) in which a chosen session starts a
few minutes from now, to serve to an emulator or a simulator through Developer › Feed
URL (testing-and-quality.md §9.1)::

    uv run python -m tools.shifted_feed 142 --in 5m               # session 142 in 5 minutes
    uv run python -m tools.shifted_feed 142 --in 5m --move 15m    # and a copy with it moved

Every slot's and open space's ``start`` and ``end`` move by one delta of wall-clock time
in the conference zone, so 9:00 stays on the hour and each offset is the one of its new
date (D-43); ids are unchanged, so saved sessions stay saved. The chosen session starts
at the current minute plus ``--in``, as an instant: on the night summer time ends, it is
the right one of the repeated hour's two. A time that the delta moves into the hour
skipped when summer time starts does not exist, so the tool refuses that ``--in``. With
``--move``, a second file is the shifted feed with only that session's times moved by
that much more: served under the same URL, it is a schedule change the app diffs (D-255).

Before writing, it runs every invariant of ``tools/feed_invariants.py`` on each file,
against the year's dates shifted by the same delta, and refuses a feed that breaks one.
The files go to ``--out`` (``build/shifted-feed``, which git ignores) and are never
committed. It prints the feed URL for the Android emulator and the iOS simulator and the
command that serves them.
"""

import argparse
import copy
import json
import re
import shlex
import sys
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from pycon_us.config import YEAR, YearData, load_year
from pycon_us.core.feed import process
from tools.feed_invariants import INVARIANTS, processed_feed

SHIFTED_FILE = "conference-shifted.json"
"""The shifted feed's name in the output folder: the one the app's feed URL names."""

MOVED_FILE = "conference-moved.json"
"""The shifted feed with the chosen session moved (``--move``)."""

DEFAULT_OUT = Path("build") / "shifted-feed"
"""Where the files go by default: under ``build/``, which git ignores."""

DEFAULT_PORT = 8765
"""The port the printed ``http.server`` command serves the files on."""

EMULATOR_HOST = "10.0.2.2"
"""The laptop's loopback as the Android emulator reaches it."""

SIMULATOR_HOST = "127.0.0.1"
"""The laptop's loopback as the iOS simulator reaches it (it shares the Mac's network)."""

OPEN_SPACE_OFFSET = 9000
"""An open space's session id is its ``conf_key`` plus this (D-42, DATA-26)."""

_DURATION = re.compile(r"([+-]?\d+)([mh]?)")


class ShiftError(Exception):
    """The feed cannot be shifted as asked; nothing was written."""


@dataclass(frozen=True)
class ShiftedFeed:
    """The shifted feed, and what the report says about it.

    Attributes:
        shifted: The shifted feed's bytes.
        moved: The shifted feed with the session moved; None without ``--move``.
        delta: How far every wall-clock time moved, in the conference zone.
        name: The session's title, as the app shows it.
        start: When the session starts in the shifted feed; aware, in the conference zone.
        moved_start: When it starts in the moved feed; None without ``--move``.
    """

    shifted: bytes
    moved: bytes | None
    delta: timedelta
    name: str
    start: datetime
    moved_start: datetime | None


def duration(text: str) -> timedelta:
    """Read a command-line duration: ``5m``, ``2h``, ``-30m``; a bare number is minutes.

    Raises:
        argparse.ArgumentTypeError: ``text`` is none of those.
    """
    match = _DURATION.fullmatch(text.strip())
    if match is None:
        raise argparse.ArgumentTypeError(f"{text!r} is not a duration such as 5m or 2h")
    amount, unit = int(match[1]), match[2]
    return timedelta(hours=amount) if unit == "h" else timedelta(minutes=amount)


def shift_feed(
    raw: bytes,
    year: YearData,
    session_id: str,
    *,
    now: datetime,
    lead: timedelta,
    move: timedelta | None = None,
) -> ShiftedFeed:
    """Shift ``raw`` so that ``session_id`` starts ``lead`` after the minute of ``now``.

    Args:
        raw: The feed's bytes, the bundled snapshot's.
        year: The year's data: its zone, feed settings and dates.
        session_id: The session's id in the app: a slot's ``conf_key``, or an open
            space's plus 9000.
        now: The current instant; aware.
        lead: How long after the current minute the session starts.
        move: How much later the session starts in the moved feed (earlier when
            negative); None writes no moved feed.

    Returns:
        The shifted feed, and the moved one when asked.

    Raises:
        ShiftError: The id names no session that has times, a time lands in the hour
            skipped when summer time starts, or a written feed breaks an invariant.
    """
    zone = year.conference.zone
    session = process(raw, year.feed_settings).sessions.get(session_id)
    document = json.loads(raw)
    record = _record(document, session_id)
    if session is None or record is None:
        raise ShiftError(
            f"{session_id!r} is not a session of the feed with its own times: "
            "use a slot's id or an open space's (its conf_key plus 9000)"
        )
    target = now.replace(second=0, microsecond=0).astimezone(UTC) + lead
    original = dict(record)  # its times before the shift: _pin keeps its length
    delta = _wall(target, zone) - _wall(datetime.fromisoformat(record["start"]), zone)
    shift_times(document, delta, zone)
    _pin(record, original, target, zone)
    shifted = _checked(document, shifted_year(year, delta), SHIFTED_FILE)
    moved = moved_start = None
    if move is not None:
        moved_document = copy.deepcopy(document)
        moved_record = _record(moved_document, session_id)
        assert moved_record is not None  # the same feed, shifted
        _pin(moved_record, original, target + move, zone)
        moved_year = shifted_year(year, delta, delta + move)
        moved = _checked(moved_document, moved_year, MOVED_FILE)
        moved_start = datetime.fromisoformat(moved_record["start"])
    return ShiftedFeed(
        shifted,
        moved,
        delta,
        session.name,
        datetime.fromisoformat(record["start"]).astimezone(zone),
        moved_start.astimezone(zone) if moved_start else None,
    )


def shift_times(document: dict[str, Any], delta: timedelta, zone: ZoneInfo) -> None:
    """Move every slot's and open space's ``start`` and ``end`` by ``delta``, in place.

    The delta is wall-clock time in ``zone``: a 9:00 start stays on the hour across a
    daylight-saving change, and its offset becomes the one of its new date. A time that
    is missing or empty (an open space not scheduled yet) stays so.

    Raises:
        ShiftError: A time lands in the hour skipped when summer time starts.
    """
    for section in ("schedule", "open-spaces"):
        for record in document.get(section) or []:
            for key in ("start", "end"):
                if record.get(key):
                    record[key] = _shifted(record[key], delta, zone)


def shifted_year(year: YearData, *deltas: timedelta) -> YearData:
    """Return ``year`` with its conference dates moved as ``shift_times`` moves the feed.

    The first day becomes the date that its midnight lands on under the smallest delta,
    and the other dates the ones that their last moment lands on under the largest, so
    every session the deltas move falls within the shifted conference, as the
    invariants check. The app keeps the bundled dates; only the invariants use these.

    Args:
        year: The year's data.
        *deltas: The wall-clock deltas the feed's times moved by: one, or two when one
            session moved further (``--move``).
    """
    info, earliest, latest = year.conference, min(deltas), max(deltas)
    return replace(
        year,
        conference=replace(
            info,
            first_day=_moved(info.first_day, time.min, earliest),
            last_talk_day=_moved(info.last_talk_day, time.max, latest),
            last_day=_moved(info.last_day, time.max, latest),
        ),
    )


def main(argv: Sequence[str] | None = None, *, now: datetime | None = None) -> int:
    """Write the shifted feed, and the moved one with ``--move``, then say how to serve them.

    Args:
        argv: The command-line arguments; ``sys.argv[1:]`` when None.
        now: The current instant; the real time when None (tests pass one).

    Returns:
        The exit status: 0 when the files were written, 1 when the feed was refused.
    """
    parser = argparse.ArgumentParser(
        description="Write the bundled feed shifted so a session starts soon."
    )
    parser.add_argument("session_id", help="the session's id, as in its route")
    parser.add_argument(
        "--in",
        dest="lead",
        type=duration,
        required=True,
        help="how soon the session starts, after the current minute: 5m, 2h",
    )
    parser.add_argument(
        "--move",
        type=duration,
        help="also write a copy with the session moved this much later: 15m, -10m",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"the folder to write the files to (default: {DEFAULT_OUT})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"the port in the printed URLs and command (default: {DEFAULT_PORT})",
    )
    args = parser.parse_args(argv)
    year = load_year(YEAR)
    try:
        feed = shift_feed(
            year.read_snapshot().raw,
            year,
            args.session_id,
            now=now or datetime.now(UTC),
            lead=args.lead,
            move=args.move,
        )
    except ShiftError as error:
        print(f"Nothing written: {error}", file=sys.stderr)
        return 1
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    (out / SHIFTED_FILE).write_bytes(feed.shifted)
    if feed.moved is not None:
        (out / MOVED_FILE).write_bytes(feed.moved)
    print("\n".join(report(feed, args.session_id, out, args.port)))
    return 0


def report(feed: ShiftedFeed, session_id: str, out: Path, port: int) -> list[str]:
    """Say what was written, how to serve it and the feed URL on each device.

    Returns:
        The report's lines.
    """
    lines = [
        f"Wrote {out / SHIFTED_FILE}: every time moved by {feed.delta}.",
        f"  Session {session_id}, {feed.name!r}, starts at {_moment(feed.start)}.",
    ]
    if feed.moved_start is not None:
        moved_at = _moment(feed.moved_start)
        lines.append(f"Wrote {out / MOVED_FILE}: the same, with it at {moved_at}.")
    lines += [
        "Serve the folder, and keep it running:",
        f"  uv run python -m http.server {port} --bind 127.0.0.1 --directory {_quoted(out)}",
        "In Developer options, clear the fake clock, set the feed URL, Apply, Refresh now:",
        f"  Android emulator: http://{EMULATOR_HOST}:{port}/{SHIFTED_FILE}",
        f"  iOS simulator:    http://{SIMULATOR_HOST}:{port}/{SHIFTED_FILE}",
    ]
    if feed.moved is not None:
        lines += [
            "To move the session, serve the moved feed at the same URL (D-255), then",
            "Refresh now:",
            f"  cp {_quoted(out / MOVED_FILE)} {_quoted(out / SHIFTED_FILE)}",
        ]
    return lines


def _record(document: dict[str, Any], session_id: str) -> dict[str, Any] | None:
    """Return the slot or open space whose session id is ``session_id``, with times."""
    for slot in document.get("schedule") or []:
        if str(slot.get("conf_key")) == session_id:
            return slot if slot.get("start") else None
    for space in document.get("open-spaces") or []:
        key = space.get("conf_key")
        if isinstance(key, int) and str(key + OPEN_SPACE_OFFSET) == session_id:
            return space if space.get("start") and space.get("end") else None
    return None


def _checked(document: dict[str, Any], year: YearData, name: str) -> bytes:
    """Serialise ``document`` once every invariant holds for it, against ``year``.

    Raises:
        ShiftError: An invariant is broken; the error lists each one with its problems.
    """
    raw = json.dumps(document).encode()
    feed = processed_feed(raw, year)
    broken = [
        f"{invariant.__name__}: {'; '.join(problems)}"
        for invariant in INVARIANTS
        if (problems := invariant(feed))
    ]
    if broken:
        raise ShiftError(f"{name} breaks invariants: " + " | ".join(broken))
    return raw


def _pin(
    record: dict[str, Any], original: dict[str, Any], start: datetime, zone: ZoneInfo
) -> None:
    """Make ``record`` start at the instant ``start`` and last as long as ``original``.

    Wall-clock arithmetic cannot tell the two 1:25s of the night summer time ends apart,
    so the chosen session's times are set from instants instead, written in ``zone``.

    Raises:
        ShiftError: The written start is not ``start`` (a guard: it never should be).
    """
    begin = datetime.fromisoformat(original["start"])
    record["start"] = start.astimezone(zone).isoformat()
    if original.get("end"):
        length = datetime.fromisoformat(original["end"]) - begin
        record["end"] = (start + length).astimezone(zone).isoformat()
    if datetime.fromisoformat(record["start"]) != start:
        raise ShiftError(f"the session would start at {record['start']}, not {start}")


def _shifted(text: str, delta: timedelta, zone: ZoneInfo) -> str:
    """Return an ISO 8601 time moved by ``delta`` of wall-clock time in ``zone``.

    A time in the repeated hour of the night summer time ends is its first occurrence.

    Raises:
        ShiftError: The moved wall-clock time does not exist in ``zone``: it is in the
            hour skipped when summer time starts.
    """
    wall = _wall(datetime.fromisoformat(text), zone) + delta
    if _wall(wall.replace(tzinfo=zone).astimezone(UTC), zone) != wall:
        raise ShiftError(
            f"{text} would move to {wall:%Y-%m-%d %H:%M}, which does not exist in "
            f"{zone.key} (summer time starts): choose another --in"
        )
    return wall.replace(tzinfo=zone).isoformat()


def _wall(moment: datetime, zone: ZoneInfo) -> datetime:
    """Return ``moment``'s naive wall-clock time in ``zone``."""
    return moment.astimezone(zone).replace(tzinfo=None)


def _quoted(path: Path) -> str:
    """Return ``path`` quoted for a POSIX shell, so a printed command can be pasted."""
    return shlex.quote(str(path))


def _moved(day: date, at: time, delta: timedelta) -> date:
    """Return the date that ``at`` on ``day``, moved by ``delta``, falls on."""
    return (datetime.combine(day, at) + delta).date()


def _moment(moment: datetime) -> str:
    """Write an aware time for the report: ``2026-10-20 15:05-07:00``."""
    return moment.isoformat(sep=" ", timespec="minutes")


if __name__ == "__main__":
    sys.exit(main())
