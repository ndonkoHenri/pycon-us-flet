"""Tests for ``tools/shifted_feed.py``, the feed shifted to now for real-time checks (P2-23).

Every test shifts the bundled 2026 snapshot, the feed the tool reads, at a fixed
``now``, and checks the result with the app's own parser and the invariants of
``tools/feed_invariants.py``, under two machine zones (D-43).
"""

import argparse
import json
import shlex
from datetime import UTC, datetime, timedelta
from functools import cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from pycon_us.config import YearData, load_year
from pycon_us.core.feed import process
from tools import shifted_feed
from tools.feed_invariants import INVARIANTS, processed_feed
from tools.shifted_feed import (
    MOVED_FILE,
    SHIFTED_FILE,
    ShiftError,
    duration,
    main,
    shift_feed,
    shifted_year,
)

pytestmark = pytest.mark.usefixtures("machine_tz")

ZONE = ZoneInfo("America/Los_Angeles")
NOW = datetime(2026, 10, 20, 14, 2, 41, 123456, tzinfo=ZONE)
"""A Tuesday afternoon in October, between seconds, months after the 2026 conference."""

TALK = "142"
"""A talk on 2026-05-16 at 10:30."""

FIVE = timedelta(minutes=5)


@cache
def year() -> YearData:
    """The 2026 year data, whose snapshot the tool shifts."""
    return load_year(2026)


@cache
def snapshot() -> bytes:
    """The bundled 2026 snapshot's bytes."""
    return year().read_snapshot().raw


def times(raw: bytes) -> list[str]:
    """Every slot's and open space's ``start`` and ``end`` in ``raw``, in feed order."""
    document = json.loads(raw)
    return [
        record[key]
        for section in ("schedule", "open-spaces")
        for record in document[section]
        for key in ("start", "end")
        if record.get(key)
    ]


def problems(raw: bytes, shifted: YearData) -> dict[str, list[str]]:
    """The broken invariants of ``raw`` against ``shifted``, by name; empty when all hold."""
    feed = processed_feed(raw, shifted)
    return {i.__name__: found for i in INVARIANTS if (found := i(feed))}


def command(printed: str, program: str) -> list[str]:
    """The arguments of the printed command line that runs ``program``, as a shell splits them."""
    line = next(
        line for line in printed.splitlines() if line.strip().startswith(program + " ")
    )
    return shlex.split(line)


def utc(moment: datetime) -> datetime:
    """``moment`` in UTC, so instants compare as instants even in a repeated hour."""
    return moment.astimezone(UTC)


def without_times(document: dict[str, Any], conf_key: int) -> dict[str, Any]:
    """``document`` with slot ``conf_key``'s ``start`` and ``end`` removed, in place."""
    slot = next(s for s in document["schedule"] if s["conf_key"] == conf_key)
    del slot["start"], slot["end"]
    return document


def test_the_session_starts_at_the_asked_minute_and_every_invariant_holds() -> None:
    """The session starts 5 min after the current minute, and every invariant holds."""
    feed = shift_feed(snapshot(), year(), TALK, now=NOW, lead=FIVE)

    assert problems(feed.shifted, shifted_year(year(), feed.delta)) == {}
    session = process(feed.shifted, year().feed_settings).sessions[TALK]
    assert session.start == datetime(2026, 10, 20, 14, 7, tzinfo=ZONE)
    assert feed.start == session.start
    assert feed.moved is None and feed.moved_start is None


def test_every_time_moves_by_one_wall_clock_delta_and_ids_stay() -> None:
    """Each time moves by the same wall-clock delta in the zone; the session ids stay."""
    feed = shift_feed(snapshot(), year(), TALK, now=NOW, lead=FIVE)

    for old, new in zip(times(snapshot()), times(feed.shifted), strict=True):
        before, after = datetime.fromisoformat(old), datetime.fromisoformat(new)
        assert after.replace(tzinfo=None) - before.replace(tzinfo=None) == feed.delta
        assert after.utcoffset() == after.replace(tzinfo=ZONE).utcoffset()
    original = process(snapshot(), year().feed_settings).sessions
    shifted = process(feed.shifted, year().feed_settings).sessions
    assert {i for i in original if i.isdigit()} == {i for i in shifted if i.isdigit()}


def test_a_shift_across_the_end_of_summer_time_keeps_the_wall_clock_times() -> None:
    """Shifted to the night PDT ends, later times keep their wall clock under -08:00."""
    now = datetime(2026, 10, 31, 23, 50, tzinfo=ZONE)
    feed = shift_feed(snapshot(), year(), TALK, now=now, lead=FIVE)

    offsets = {datetime.fromisoformat(t).utcoffset() for t in times(feed.shifted)}
    assert offsets == {timedelta(hours=-7), timedelta(hours=-8)}
    assert feed.start == datetime(2026, 10, 31, 23, 55, tzinfo=ZONE)
    assert problems(feed.shifted, shifted_year(year(), feed.delta)) == {}


@pytest.mark.parametrize(
    ("now", "offset"),
    [
        (datetime(2026, 11, 1, 8, 20, tzinfo=UTC), timedelta(hours=-7)),
        (datetime(2026, 11, 1, 9, 20, tzinfo=UTC), timedelta(hours=-8)),
    ],
    ids=["first 1:25, PDT", "second 1:25, PST"],
)
@pytest.mark.parametrize(
    "move",
    [None, timedelta(minutes=-15), timedelta(minutes=15)],
    # From the first 1:25, +15m moves the talk to 1:40 PDT-1:10 PST, across the change (#513).
    ids=["not moved", "moved -15m", "moved +15m"],
)
def test_a_session_in_the_repeated_hour_starts_at_the_asked_instant(
    now: datetime, offset: timedelta, move: timedelta | None
) -> None:
    """Either 1:25 of the night PDT ends is the asked instant, moved or not, for 30 min.

    Instants are compared in UTC: Python never finds a time in a repeated hour equal to
    one in another zone (PEP 495), and subtracts two in one zone by their wall clocks.
    """
    feed = shift_feed(snapshot(), year(), TALK, now=now, lead=FIVE, move=move)

    session = process(feed.shifted, year().feed_settings).sessions[TALK]
    assert utc(session.start) == utc(feed.start) == now + FIVE
    assert feed.start.utcoffset() == offset
    assert utc(session.end) - utc(session.start) == timedelta(minutes=30)
    if move is not None:
        assert feed.moved is not None and feed.moved_start is not None
        moved = process(feed.moved, year().feed_settings).sessions[TALK]
        assert utc(moved.start) == utc(feed.moved_start) == now + FIVE + move
        assert utc(moved.end) - utc(moved.start) == timedelta(minutes=30)


def test_a_time_moved_into_the_skipped_hour_is_refused() -> None:
    """A 10:00 talk the delta moves to 02:30 on the night PDT starts does not exist: refused."""
    now = datetime(2027, 3, 14, 9, 55, tzinfo=UTC)  # 142 at 03:00 PDT, 10:00 at 02:30

    with pytest.raises(ShiftError, match="does not exist in America/Los_Angeles"):
        shift_feed(snapshot(), year(), TALK, now=now, lead=FIVE)


def test_a_negative_lead_puts_the_session_on_now() -> None:
    """With ``--in -10m`` the session started 10 min before the current minute."""
    feed = shift_feed(snapshot(), year(), TALK, now=NOW, lead=-2 * FIVE)

    assert feed.start == datetime(2026, 10, 20, 13, 52, tzinfo=ZONE)
    assert problems(feed.shifted, shifted_year(year(), feed.delta)) == {}


def test_the_moved_feed_differs_only_in_the_sessions_times() -> None:
    """With ``--move 15m`` the second feed moves that slot's start and end, and nothing else."""
    feed = shift_feed(
        snapshot(), year(), TALK, now=NOW, lead=FIVE, move=timedelta(minutes=15)
    )
    assert feed.moved is not None
    shifted, moved = json.loads(feed.shifted), json.loads(feed.moved)

    assert without_times(shifted, 142) == without_times(moved, 142)
    session = process(feed.moved, year().feed_settings).sessions[TALK]
    assert session.start == datetime(2026, 10, 20, 14, 22, tzinfo=ZONE)
    assert session.end - session.start == timedelta(minutes=30)
    assert feed.moved_start == session.start
    moved_year = shifted_year(year(), feed.delta, feed.delta + timedelta(minutes=15))
    assert problems(feed.moved, moved_year) == {}


def test_an_open_space_is_named_by_its_session_id() -> None:
    """An open space's id is its conf_key plus 9000, and it starts at the asked minute."""
    feed = shift_feed(snapshot(), year(), "9119", now=NOW, lead=FIVE)

    assert feed.name == "5K Fun Run"
    assert feed.start == datetime(2026, 10, 20, 14, 7, tzinfo=ZONE)
    assert problems(feed.shifted, shifted_year(year(), feed.delta)) == {}


def test_a_feed_that_breaks_an_invariant_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Checked against the bundled May dates, the October feed breaks one and is refused."""
    monkeypatch.setattr(shifted_feed, "shifted_year", lambda year, *deltas: year)

    with pytest.raises(ShiftError, match="every_session_is_on_one_conference_day"):
        shift_feed(snapshot(), year(), TALK, now=NOW, lead=FIVE)


@pytest.mark.parametrize(
    "session_id",
    ["150", "130", "999999", "poster-detail-1"],
    ids=["a collapsed break", "a placeholder", "unknown", "not a slot"],
)
def test_an_id_that_names_no_session_with_times_is_refused(session_id: str) -> None:
    """A break folded into its row, a dropped placeholder or an unknown id is refused."""
    with pytest.raises(ShiftError, match="is not a session"):
        shift_feed(snapshot(), year(), session_id, now=NOW, lead=FIVE)


def test_the_shifted_years_dates_hold_every_moment_of_the_conference() -> None:
    """The first day takes midnight under the smallest delta, the rest the day's end."""
    late = timedelta(days=156, hours=18)
    shifted = shifted_year(year(), late, late - timedelta(hours=19)).conference

    assert shifted.first_day.isoformat() == "2026-10-15"  # 05-13 00:00 + 155 d 23 h
    assert shifted.last_talk_day.isoformat() == "2026-10-21"  # 05-17 23:59 + 156 d 18 h
    assert shifted.last_day.isoformat() == "2026-10-23"


@pytest.mark.parametrize(
    ("text", "minutes"),
    [("5m", 5), ("2h", 120), ("-30m", -30), ("+15m", 15), ("7", 7)],
)
def test_a_duration_is_minutes_or_hours(text: str, minutes: int) -> None:
    """``5m``, ``2h``, a sign and a bare number of minutes are read as durations."""
    assert duration(text) == timedelta(minutes=minutes)


def test_a_duration_in_another_unit_is_refused() -> None:
    """``30s`` is an argparse error, so the command line says what it expects."""
    with pytest.raises(argparse.ArgumentTypeError, match="5m or 2h"):
        duration("30s")


def test_main_writes_both_files_and_prints_the_urls_and_the_server(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The run writes the two feeds and prints both devices' URLs and the server line."""
    out = tmp_path / "out"
    now = NOW.astimezone(UTC)

    status = main([TALK, "--in", "5m", "--move", "15m", "--out", str(out)], now=now)

    assert status == 0
    assert sorted(p.name for p in out.iterdir()) == [MOVED_FILE, SHIFTED_FILE]
    printed = capsys.readouterr().out
    assert f"http://10.0.2.2:8765/{SHIFTED_FILE}" in printed
    assert f"http://127.0.0.1:8765/{SHIFTED_FILE}" in printed
    assert command(printed, "uv")[-2:] == ["--directory", str(out)]
    assert command(printed, "cp") == [
        "cp",
        str(out / MOVED_FILE),
        str(out / SHIFTED_FILE),
    ]
    assert "2026-10-20 14:07-07:00" in printed


def test_the_printed_commands_quote_a_folder_with_spaces(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """With an ``--out`` that has spaces, the server and copy commands still parse right."""
    out = tmp_path / "path with spaces"

    assert main([TALK, "--in", "5m", "--move", "15m", "--out", str(out)], now=NOW) == 0
    printed = capsys.readouterr().out
    assert command(printed, "uv")[-2:] == ["--directory", str(out)]
    assert command(printed, "cp") == [
        "cp",
        str(out / MOVED_FILE),
        str(out / SHIFTED_FILE),
    ]


def test_main_writes_nothing_for_an_unknown_session(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An id that names no session exits with 1, says why and leaves no folder."""
    out = tmp_path / "out"

    assert main(["999999", "--in", "5m", "--out", str(out)], now=NOW) == 1
    assert "Nothing written" in capsys.readouterr().err
    assert not out.exists()


def test_main_takes_a_negative_duration_as_a_value(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--in -10m --move -5m`` are read as values, not options: 13:52, moved to 13:47."""
    args = [TALK, "--in", "-10m", "--move", "-5m", "--out", str(tmp_path)]

    assert main(args, now=NOW) == 0
    printed = capsys.readouterr().out
    assert "starts at 2026-10-20 13:52-07:00" in printed
    assert "with it at 2026-10-20 13:47-07:00" in printed
