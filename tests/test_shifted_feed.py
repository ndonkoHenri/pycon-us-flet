"""Tests for ``tools/shifted_feed.py``, the feed shifted to now for real-time checks (P2-23).

Every test shifts the bundled 2026 snapshot, the feed the tool reads, at a fixed
``now``, and checks the result with the app's own parser and the invariants of
``tools/feed_invariants.py``, under two machine zones (D-43).
"""

import argparse
import json
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
    assert f"http.server 8765 --bind 127.0.0.1 --directory {out}" in printed
    assert f"cp {out / MOVED_FILE} {out / SHIFTED_FILE}" in printed
    assert "2026-10-20 14:07-07:00" in printed


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
