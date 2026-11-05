"""Tests for `tools/run_flows.py`: a lane's order, each flow's setup and the command line."""

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
