"""Tests for `tools/run_flows.py`: a lane's order, each flow's setup and the command line."""

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tools import run_flows

JOURNEYS = sorted(path.stem for path in Path("maestro/journeys").glob("*.yaml"))


def test_a_lane_runs_every_journey_once() -> None:
    """Nothing in `maestro/journeys/` is left out of a lane or run twice."""
    assert sorted(run_flows.lane_order(JOURNEYS)) == JOURNEYS


def test_large_text_follows_the_flow_it_starts_from() -> None:
    """`sponsors_large_text` has no fresh start, so it comes right after `sponsors_back`."""
    order = run_flows.lane_order(JOURNEYS)
    assert order.index("sponsors_large_text") == order.index("sponsors_back") + 1


def test_the_landscape_flow_comes_last() -> None:
    """Nothing follows `rail_tabs`, so nothing inherits its turn or its reboot."""
    assert run_flows.lane_order(JOURNEYS)[-2:] == ["offline_scans", "rail_tabs"]


def test_the_regression_flow_is_outside_the_lanes() -> None:
    """The timing-sensitive flow lives in `maestro/regression/`, which a lane doesn't read."""
    assert run_flows.REGRESSION not in JOURNEYS
    assert Path(f"maestro/regression/{run_flows.REGRESSION}.yaml").exists()


def test_each_special_flow_exists() -> None:
    """A renamed journey can't silently lose its setup here."""
    named = {
        *run_flows.MOCK_FLOWS,
        *run_flows.FEED_PAIR_MOVES,
        *run_flows.LAST_IN_THE_LANE,
    }
    assert named <= set(JOURNEYS)


def test_staff_flows_reach_their_lanes_mock() -> None:
    """Each platform has its own mock, at the address its device sees the Mac by."""
    assert run_flows.flow_env("door_check", "android") == [
        ("MOCK_URL", "http://10.0.2.2:8601")
    ]
    assert run_flows.flow_env("door_check", "ios") == [
        ("MOCK_URL", "http://localhost:8602")
    ]


def test_swag_pickup_requires_the_hand_out() -> None:
    """The lane's mock hasn't seen the flow, so the hand-out sheet is mandatory."""
    assert ("HAND_OUT", "required") in run_flows.flow_env("swag_pickup", "ios")


def test_feed_pair_flows_get_the_server_and_its_control() -> None:
    """The device reads the feed by its own address; the flow's scripts swap on the Mac's."""
    assert run_flows.flow_env("change_log", "android") == [
        ("FEED_URL", "http://10.0.2.2:8611/conference-2026.json"),
        ("CONTROL_URL", "http://127.0.0.1:8611"),
    ]


def test_maestro_command_keeps_output_by_flow() -> None:
    """Every flow's output goes under its own folder, and `-e` pairs precede the flow."""
    command = run_flows.maestro_command(
        "emulator-5594", Path("out/r1/android/x"), [("A", "b")], "x.yaml"
    )
    assert command[:3] == ["maestro", "--device", "emulator-5594"]
    assert command[command.index("--debug-output") + 1] == "out/r1/android/x/debug"
    assert command[-3:] == ["-e", "A=b", "x.yaml"]


def test_no_logo_feed_moves_each_logo() -> None:
    """Every logo points at the closed port."""
    feed = run_flows.no_logo_feed(
        '{"logo_url":"https://pycon-archive.python.org/a.png"}'
    )
    assert feed == '{"logo_url":"http://127.0.0.1:9/a.png"}'


def test_no_logo_feed_refuses_a_moved_host() -> None:
    """A feed whose logos live elsewhere would load real logos, so it stops instead."""
    with pytest.raises(SystemExit):
        run_flows.no_logo_feed('{"logo_url":"https://elsewhere.example/a.png"}')


def test_a_run_needs_a_device() -> None:
    """With no device, it says so rather than running nothing."""
    with pytest.raises(SystemExit, match="name a device"):
        run_flows.main(["--out", "unused"])


def test_a_run_refuses_the_owners_device() -> None:
    """The flows replace the app's data, so the owner's emulator is refused."""
    with pytest.raises(SystemExit, match="owner"):
        run_flows.main(["--out", "unused", "--android", "emulator-5554"])


def _run_at(tmp_path: Path) -> run_flows.FlowRun:
    """Return a run with its folder in `tmp_path`, starting no device."""
    return run_flows.FlowRun(tmp_path, None, set())


def test_a_server_that_stops_at_its_start_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A server that dies at once stops the lane, quoting its log, kept in the round's folder."""
    monkeypatch.setattr(run_flows, "SERVER_START_SECONDS", 0.5)
    log = tmp_path / "r1" / "ios" / "mock.log"
    script = "import sys; print('booting'); sys.exit('boom')"
    with (
        pytest.raises(RuntimeError, match=r"(?s)stopped at its start \(see its log.*boom"),
        _run_at(tmp_path).server(log, _free_port(), sys.executable, "-c", script),
    ):
        pass
    assert log.read_text(encoding="utf-8").splitlines() == ["booting", "boom"]


def test_a_server_that_finds_its_port_taken_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bind error in the log is named as a taken port, not a bare stop (#1137)."""
    monkeypatch.setattr(run_flows, "SERVER_START_SECONDS", 0.5)
    script = "import sys; sys.exit('OSError: [Errno 48] Address already in use')"
    with (
        pytest.raises(RuntimeError, match="its port is taken"),
        _run_at(tmp_path).server(
            tmp_path / "mock.log", _free_port(), sys.executable, "-c", script
        ),
    ):
        pass


def test_a_port_another_process_holds_stops_the_server_before_it_starts(
    tmp_path: Path,
) -> None:
    """A listener already on the port would answer the flows: the run names the port."""
    with socket.socket() as holder:
        holder.bind(("127.0.0.1", 0))
        holder.listen()
        port = holder.getsockname()[1]
        with (
            pytest.raises(RuntimeError, match=f"port {port} is taken"),
            _run_at(tmp_path).server(tmp_path / "x.log", port, "true"),
        ):
            pass
    assert not (tmp_path / "x.log").exists()  # nothing was started


def test_a_server_s_output_stays_in_its_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What a running server prints is kept for after the run, not dropped."""
    monkeypatch.setattr(run_flows, "SERVER_START_SECONDS", 0.5)
    log = tmp_path / "feed_pair.log"
    script = "import sys, time; print('serving', flush=True); time.sleep(30)"
    with _run_at(tmp_path).server(log, _free_port(), sys.executable, "-c", script):
        pass
    assert log.read_text(encoding="utf-8") == "serving\n"


def _free_port() -> int:
    """Return a port nothing listens on now."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def test_a_stopped_lane_is_recorded_and_fails_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A lane's exception would die with its thread, so it gets a line and fails the run."""
    run = _run_at(tmp_path)

    def stop(*_: object) -> None:
        """Stand in for a lane whose setup fails."""
        raise RuntimeError("no mock")

    monkeypatch.setattr(run, "lane", stop)
    run.guarded_lane("ios", "udid", "r1", [])
    line = json.loads((tmp_path / "results.jsonl").read_text(encoding="utf-8"))
    assert (line["flow"], line["rc"], line["error"]) == ("LANE STOPPED", 1, "no mock")
    assert run.failed


def test_large_text_is_reset_when_its_flow_cannot_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failure while at the largest text doesn't leave later flows at that size."""
    run = _run_at(tmp_path)
    calls: list[tuple[str, ...]] = []

    def prefs(_: str, *options: str) -> None:
        """Note what was asked of the device."""
        calls.append(options)

    def fail(*_: object) -> None:
        """Stand in for a flow that can't start."""
        raise OSError("no maestro")

    monkeypatch.setattr(run, "prefs", prefs)
    monkeypatch.setattr(run, "run", fail)
    with pytest.raises(OSError, match="no maestro"):
        run.journey("udid", "ios", "r1", "sponsors_large_text")
    assert calls == [("--text", "max", "--bold"), ("--reset",)]


def test_a_failed_setup_tool_raises(tmp_path: Path) -> None:
    """A text size that wasn't set stops the lane instead of passing at the default size."""
    with pytest.raises(subprocess.CalledProcessError):
        _run_at(tmp_path).tool("tools.no_such_tool")


def test_a_timeout_ends_the_whole_group(tmp_path: Path) -> None:
    """A flow's child process doesn't outlive it to drive the device under the next flow."""
    pid_file = tmp_path / "pid"
    child = "import time; time.sleep(60)"
    script = (
        "import pathlib, subprocess, sys, time\n"
        f"p = subprocess.Popen([sys.executable, '-c', {child!r}])\n"
        f"pathlib.Path({str(pid_file)!r}).write_text(str(p.pid))\n"
        "time.sleep(60)\n"
    )
    with (tmp_path / "log").open("w", encoding="utf-8") as log:
        rc = run_flows.run_in_group(
            [sys.executable, "-c", script], dict(os.environ), log, 2
        )
    assert rc == -1
    pid = int(pid_file.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and _alive(pid):
        time.sleep(0.1)
    assert not _alive(pid)


def _alive(pid: int) -> bool:
    """Say whether a process is still there."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True
