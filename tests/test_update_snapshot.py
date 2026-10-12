"""Tests for ``tools/update_snapshot.py``, the bundled-snapshot refresher (D-38, NEW-03).

The feed comes from an ``httpx.MockTransport`` serving the recorded 2026 feed or a broken
copy of it, never the network; the year data is a writable copy of the bundled folders.
"""

import json
import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from pycon_us import config
from pycon_us.config import load_year
from tools.update_snapshot import SnapshotError, update_snapshot

RECORDED = (
    Path(__file__).parent / "fixtures" / "feeds" / "conference-2026.json"
).read_bytes()
FEED_URL = "https://us.pycon.org/2026/schedule/conference.json"
NOW = datetime(2026, 10, 12, 17, 4, 31, 999, tzinfo=UTC)


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """A writable copy of the bundled year data."""
    shutil.copytree(config.DATA_DIR, tmp_path, dirs_exist_ok=True)
    return tmp_path


def serving(body: bytes, status: int = 200) -> httpx.MockTransport:
    """A transport that answers the 2026 feed URL with ``body``, and fails anything else."""

    def handle(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == FEED_URL
        return httpx.Response(status, content=body)

    return httpx.MockTransport(handle)


def changed(change: Callable[[dict[str, Any]], object]) -> bytes:
    """The recorded feed with ``change`` applied to a fresh copy of its JSON."""
    document = json.loads(RECORDED)
    change(document)
    return json.dumps(document).encode()


def files(data_dir: Path) -> tuple[bytes, bytes]:
    folder = data_dir / "2026"
    return (
        (folder / "conference.json").read_bytes(),
        (folder / "conference.toml").read_bytes(),
    )


def test_update_bundles_the_feed_bytes_unchanged_with_the_capture_time(
    data_dir: Path,
) -> None:
    feed = changed(lambda doc: doc["schedule"].pop())
    update_snapshot(2026, data_dir, transport=serving(feed), now=NOW)

    snapshot = load_year(2026, data_dir).read_snapshot()
    assert snapshot.raw == feed
    # Seconds, in conference time: what a reader of conference.toml expects.
    assert snapshot.captured_at.isoformat() == "2026-10-12T10:04:31-07:00"
    assert not list((data_dir / "2026").glob("*.tmp"))


def test_update_changes_only_the_capture_line_of_conference_toml(
    data_dir: Path,
) -> None:
    toml = data_dir / "2026" / "conference.toml"
    before = toml.read_text(encoding="utf-8").splitlines()
    update_snapshot(2026, data_dir, transport=serving(RECORDED), now=NOW)
    after = toml.read_text(encoding="utf-8").splitlines()

    assert len(after) == len(before)
    differences = [(a, b) for a, b in zip(before, after, strict=True) if a != b]
    assert differences == [
        (
            next(line for line in before if line.startswith("snapshot_captured_at")),
            "snapshot_captured_at = 2026-10-12T10:04:31-07:00",
        )
    ]


def test_a_new_year_folder_gets_its_first_snapshot(data_dir: Path) -> None:
    folder = data_dir / "2026"
    (folder / "conference.json").unlink()
    toml = folder / "conference.toml"
    lines = toml.read_text(encoding="utf-8").splitlines(keepends=True)
    toml.write_text(
        "".join(line for line in lines if "snapshot_captured_at" not in line),
        encoding="utf-8",
    )
    with pytest.raises(config.YearDataError):
        load_year(2026, data_dir).read_snapshot()

    report = update_snapshot(2026, data_dir, transport=serving(RECORDED), now=NOW)

    assert "the first snapshot" in report
    assert load_year(2026, data_dir).read_snapshot().raw == RECORDED


def test_report_shows_each_count_before_and_after(data_dir: Path) -> None:
    def drop_a_slot_and_a_sprint(doc: dict[str, Any]) -> None:
        doc["schedule"].pop()
        doc["sprints"].pop()

    report = update_snapshot(
        2026, data_dir, transport=serving(changed(drop_a_slot_and_a_sprint)), now=NOW
    )

    lines = report.splitlines()
    assert lines[0] == f"Updated 2026/conference.json from {FEED_URL}"
    assert lines[1].startswith("captured at 2026-10-12T10:04:31-07:00; ")
    assert lines[2:] == [
        "  sessions        728 -> 727     -1",
        "  speakers        170 -> 170",
        "  days              5 -> 5",
        "  posters          25 -> 25",
        "  sprints          24 -> 23      -1",
        "  job listings     13 -> 13",
    ]


def test_report_says_when_the_previous_snapshot_no_longer_parses(
    data_dir: Path,
) -> None:
    (data_dir / "2026" / "conference.json").write_bytes(b"[]")
    report = update_snapshot(2026, data_dir, transport=serving(RECORDED), now=NOW)
    assert "; the previous snapshot no longer parses" in report.splitlines()[1]
    assert "  sessions          - -> 728" in report.splitlines()


def test_report_says_when_the_feed_is_unchanged(data_dir: Path) -> None:
    report = update_snapshot(2026, data_dir, transport=serving(RECORDED), now=NOW)
    assert f"{len(RECORDED):,} bytes, unchanged" in report


@pytest.mark.parametrize(
    ("body", "status", "problem"),
    [
        (
            b"<html>Down for maintenance</html>",
            200,
            "the feed does not parse: not JSON",
        ),
        (b'{"schedule": {}}', 200, "the feed does not parse: no 'schedule' list"),
        (b"", 503, "could not fetch"),
        (
            changed(lambda doc: doc["schedule"][0].pop("start")),
            200,
            "the parser skips 1 feed record(s):\n  schedule[0]: ",
        ),
        (
            changed(
                lambda doc: [
                    slot.update(
                        start=slot["start"].replace("2026-", "2027-"),
                        end=slot["end"].replace("2026-", "2027-"),
                    )
                    for slot in doc["schedule"]
                ]
            ),
            200,
            "the feed's days, 2027-05-13 to 2027-05-17, fall outside the conference's, 2026-05-13 to 2026-05-19",
        ),
    ],
    ids=["html", "wrong-structure", "server-error", "skipped-record", "wrong-year"],
)
def test_a_feed_that_does_not_parse_cleanly_is_refused_and_nothing_changes(
    data_dir: Path, body: bytes, status: int, problem: str
) -> None:
    before = files(data_dir)
    with pytest.raises(SnapshotError) as error:
        update_snapshot(2026, data_dir, transport=serving(body, status), now=NOW)
    assert str(error.value).startswith(problem)
    assert files(data_dir) == before


def test_an_unexpected_conference_toml_layout_is_refused_and_nothing_changes(
    data_dir: Path,
) -> None:
    # Valid TOML, but not the bare key the tool rewrites: it must not write a duplicate.
    toml = data_dir / "2026" / "conference.toml"
    text = toml.read_text(encoding="utf-8")
    toml.write_text(
        text.replace("\nsnapshot_captured_at =", '\n"snapshot_captured_at" ='),
        encoding="utf-8",
    )
    before = files(data_dir)
    with pytest.raises(SnapshotError, match="^could not set snapshot_captured_at"):
        update_snapshot(2026, data_dir, transport=serving(RECORDED), now=NOW)
    assert files(data_dir) == before


def test_a_network_failure_is_refused_and_nothing_changes(data_dir: Path) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    before = files(data_dir)
    with pytest.raises(SnapshotError, match="^could not fetch "):
        update_snapshot(2026, data_dir, transport=httpx.MockTransport(fail), now=NOW)
    assert files(data_dir) == before
