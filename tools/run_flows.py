"""Run every Maestro journey with its setup, one lane per platform, for one or more rounds.

Usage, from the repo's root, with the build under test installed on your own devices:
    uv run python -m tools.run_flows --out build/flows --rounds r1,r2 \
        --android emulator-5594 --ios <udid>
    uv run python -m tools.run_flows --out build/flows --rounds r2 --ios <udid> \
        --flows wifi_copy,find_room
    uv run python -m tools.run_flows --out build/flows --rounds r1 --android emulator-5594 \
        --skip about_app,calendar_export

One platform's lane runs next to the other's, so they share the host: read a failure with
the `load` beside it. `<out>/results.jsonl` gets one line per flow (`round`, `platform`,
`flow`, `rc`, `seconds`, `load`, `at`), and `<out>/<round>/<platform>/<flow>/` keeps its
log, debug output and screenshots. It reports; it never reruns: a rerun's pass isn't a
first-run pass. Each flow's setup is the one `maestro/README.md` gives it, and
`docs/testing-and-quality.md` §5.5 says when a full run is due.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import NamedTuple

from tools.device import refuse_owners

FLOW_SECONDS = 1800
"""How long one flow may take. Under load `now_next` has taken over 700 s."""

SIMULATOR_SETTLE_SECONDS = 45
"""How long a rebooted simulator rests before `rail_tabs`, which needs a fresh one (#1011)."""

SERVER_START_SECONDS = 4
"""How long a server just started gets to open its port; `feed_pair` first runs the parser."""

NO_LOGO_PORT = 8766
"""`sponsors_offline_logos.yaml`'s default port for its feed on iOS."""

NO_LOGO_YEAR = 2026
"""The snapshot that flow's default URL names, and the year the feed-pair flows are told."""

LOGO_HOST = "https://pycon-archive.python.org/"
"""Where the snapshot's logos live; the no-logo feed points them at a closed port."""

LAST_IN_THE_LANE = ("offline_scans", "rail_tabs")
"""Last, so nothing inherits `rail_tabs`' landscape or its reboot of the simulator."""

REGRESSION = "fling_after_sheet"
"""Timing-sensitive, so it runs after the lanes, one platform at a time."""

MOCK_FLOWS = ("coc_capture", "lead_capture", "door_check", "swag_pickup")
"""The `staff` flows: each signs in to a local mock."""

FEED_PAIR_MOVES = {
    "change_log": ("--move", "123", "Room 103ABC", "--move", "142", "Room 101B"),
    "pull_to_refresh": ("--move", "2", "Room 103ABC"),
}
"""The flows on a served feed pair, and the edits each expects (`feed_pair.py`)."""

PORTRAIT_FLOW = """appId: io.github.ndonkohenri.confcompanion
---
- setOrientation: PORTRAIT
"""
"""Turns the device back after `rail_tabs`."""


class Lane(NamedTuple):
    """One platform's ports, kept apart so two lanes can run side by side."""

    mock: int
    feed: int
    offline: int
    control: int
    mock_host: str
    feed_host: str


LANES = {
    "android": Lane(8601, 8611, 8621, 8622, "10.0.2.2", "10.0.2.2"),
    "ios": Lane(8602, 8612, 8631, 8632, "localhost", "127.0.0.1"),
}


def lane_order(journeys: Sequence[str]) -> list[str]:
    """Return `journeys` in a lane's order.

    `sponsors_large_text` starts from the data the last flow left, so it follows
    `sponsors_back` (`maestro/README.md`, "Large text").
    """
    order = [
        j
        for j in sorted(journeys)
        if j != "sponsors_large_text" and j not in LAST_IN_THE_LANE
    ]
    if "sponsors_large_text" in journeys:
        order.insert(order.index("sponsors_back") + 1, "sponsors_large_text")
    return [*order, *(j for j in LAST_IN_THE_LANE if j in journeys)]


def flow_env(flow: str, platform: str) -> list[tuple[str, str]]:
    """Return the `-e` pairs `flow` needs on `platform`'s lane."""
    lane = LANES[platform]
    if flow in MOCK_FLOWS:
        mock = [("MOCK_URL", f"http://{lane.mock_host}:{lane.mock}")]
        return [*mock, ("HAND_OUT", "required")] if flow == "swag_pickup" else mock
    if flow in FEED_PAIR_MOVES:
        return [
            (
                "FEED_URL",
                f"http://{lane.feed_host}:{lane.feed}/conference-{NO_LOGO_YEAR}.json",
            ),
            ("CONTROL_URL", f"http://127.0.0.1:{lane.feed}"),
        ]
    if flow == "rail_tabs":
        return [("ORIENTATION", "LANDSCAPE")]
    return []


def maestro_command(
    device: str, directory: Path, env: Sequence[tuple[str, str]], flow_file: Path | str
) -> list[str]:
    """Return the line that runs `flow_file`, its output under `directory`."""
    command = ["maestro", "--device", device, "test"]
    command += ["--test-output-dir", str(directory / "out")]
    command += ["--debug-output", str(directory / "debug"), "--flatten-debug-output"]
    for name, value in env:
        command += ["-e", f"{name}={value}"]
    return [*command, str(flow_file)]


def no_logo_feed(snapshot: str) -> str:
    """Return `snapshot` with every logo at a closed port, or exit if none moved."""
    moved = snapshot.replace(LOGO_HOST, "http://127.0.0.1:9/")
    if '"logo_url":"http://127.0.0.1:9/' not in moved:
        sys.exit(f"run_flows: no logo at {LOGO_HOST}: real logos would load")
    return moved


class FlowRun:
    """One run's output folder, its environment and the results it records."""

    def __init__(self, out: Path, flows: set[str] | None, skip: set[str]) -> None:
        """Prepare `out`, with what the flows on iOS and `rail_tabs` read from it."""
        self.out = out
        self.flows = flows
        self.skip = skip
        self.lock = threading.Lock()
        self.env = {
            **os.environ,
            "MAESTRO_CLI_NO_ANALYTICS": "1",
            "MAESTRO_DRIVER_STARTUP_TIMEOUT": "240000",  # a busy host starts the driver late
            "LANG": "en_US.UTF-8",
        }
        out.mkdir(parents=True, exist_ok=True)
        (out / "portrait.yaml").write_text(PORTRAIT_FLOW, encoding="utf-8")
        snapshot = Path(f"src/pycon_us/data/{NO_LOGO_YEAR}/conference.json")
        feed = out / "no-logo-feed" / f"conference-{NO_LOGO_YEAR}.json"
        feed.parent.mkdir(exist_ok=True)
        feed.write_text(
            no_logo_feed(snapshot.read_text(encoding="utf-8")), encoding="utf-8"
        )

    def wanted(self, flow: str) -> bool:
        """Say whether this run includes `flow`."""
        return flow not in self.skip and (self.flows is None or flow in self.flows)

    def record(self, **result: object) -> None:
        """Add a line to `results.jsonl`, and print it to follow the run."""
        line = json.dumps(
            {**result, "load": os.getloadavg()[0], "at": time.strftime("%H:%M:%S")}
        )
        with (
            self.lock,
            (self.out / "results.jsonl").open("a", encoding="utf-8") as results,
        ):
            results.write(line + "\n")
        print(line, flush=True)

    def run(
        self, command: list[str], directory: Path, name: tuple[str, str, str]
    ) -> None:
        """Run `command`, its output in `directory`, and record how it ended."""
        rnd, platform, flow = name
        directory.mkdir(parents=True, exist_ok=True)
        start = time.monotonic()
        with (directory / "stdout.log").open("w", encoding="utf-8") as log:
            try:
                rc = subprocess.run(
                    command,
                    check=False,
                    env=self.env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=FLOW_SECONDS,
                ).returncode
            except subprocess.TimeoutExpired:
                rc = -1
        seconds = round(time.monotonic() - start)
        self.record(round=rnd, platform=platform, flow=flow, rc=rc, seconds=seconds)

    @contextmanager
    def server(self, *command: str) -> Iterator[None]:
        """Keep a server running for a `with` block."""
        process = subprocess.Popen(
            command, env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        time.sleep(SERVER_START_SECONDS)
        try:
            yield
        finally:
            process.terminate()
            process.wait()

    def prefs(self, device: str, *options: str) -> None:
        """Set `device`'s text size through `tools.device`."""
        self.tool("tools.device", "prefs", device, *options)

    def tool(self, *module_and_args: str) -> None:
        """Run one of these tools and wait for it, its output dropped."""
        subprocess.run(
            [sys.executable, "-m", *module_and_args],
            check=False,
            env=self.env,
            capture_output=True,
        )

    def journey(self, device: str, platform: str, rnd: str, flow: str) -> None:
        """Run one journey with the setup `maestro/README.md` gives it."""
        directory = self.out / rnd / platform / flow
        name = (rnd, platform, flow)
        lane = LANES[platform]
        path = Path("maestro/journeys") / f"{flow}.yaml"
        command = maestro_command(device, directory, flow_env(flow, platform), path)
        if flow == "offline_scans":
            scans = [sys.executable, "-m", "tools.offline_scans", "--device", device]
            scans += ["--platform", platform, "--port", str(lane.offline)]
            scans += ["--control-port", str(lane.control)]
            self.run(scans, directory, name)
        elif flow in FEED_PAIR_MOVES:
            moves = FEED_PAIR_MOVES[flow]
            pair = [
                sys.executable,
                "-m",
                "tools.feed_pair",
                "--port",
                str(lane.feed),
                *moves,
            ]
            with self.server(*pair):
                self.run(command, directory, name)
        elif flow == "sponsors_large_text":
            self.prefs(device, "--text", "max", "--bold")
            self.run(command, directory, name)
            self.prefs(device, "--reset")
        elif flow == "rail_tabs":
            if platform == "ios":
                reboot_simulator(device)
            self.run(command, directory, name)
            portrait = [
                "maestro",
                "--device",
                device,
                "test",
                str(self.out / "portrait.yaml"),
            ]
            subprocess.run(portrait, check=False, env=self.env, capture_output=True)
        else:
            self.run(command, directory, name)

    def lane(
        self, platform: str, device: str, rnd: str, journeys: Sequence[str]
    ) -> None:
        """Run `journeys` on one platform in a lane's order, beside its servers."""
        mock = [
            sys.executable,
            "-m",
            "tools.mock_api.server",
            "--port",
            str(LANES[platform].mock),
        ]
        with self.server(*mock):
            feed = [
                sys.executable,
                *["-m", "http.server", str(NO_LOGO_PORT), "--bind", "127.0.0.1"],
                *["--directory", str(self.out / "no-logo-feed")],
            ]
            # Android cuts its network, so only iOS's flow reads this feed (`maestro/README.md`).
            with self.server(*feed) if platform == "ios" else no_server():
                for flow in lane_order(journeys):
                    if self.wanted(flow):
                        self.journey(device, platform, rnd, flow)

    def round(self, rnd: str, devices: dict[str, str], journeys: Sequence[str]) -> None:
        """Run the lanes side by side, then the regression flow on each in turn."""
        lanes = [
            threading.Thread(target=self.lane, args=(platform, device, rnd, journeys))
            for platform, device in devices.items()
        ]
        for lane in lanes:
            lane.start()
        for lane in lanes:
            lane.join()
        if self.wanted(REGRESSION):
            path = Path("maestro/regression") / f"{REGRESSION}.yaml"
            for platform, device in devices.items():
                directory = self.out / rnd / platform / REGRESSION
                command = maestro_command(device, directory, [], path)
                self.run(command, directory, (rnd, platform, REGRESSION))
        self.record(round=rnd, platform="-", flow="ROUND DONE", rc=0, seconds=0)


@contextmanager
def no_server() -> Iterator[None]:
    """Stand in for `FlowRun.server` on a lane that needs none."""
    yield


def reboot_simulator(udid: str) -> None:
    """Reboot a simulator: `rail_tabs` fails on one that ran the lane (#1011)."""
    subprocess.run(
        ["xcrun", "simctl", "shutdown", udid], check=False, capture_output=True
    )
    time.sleep(5)
    subprocess.run(["xcrun", "simctl", "boot", udid], check=False, capture_output=True)
    subprocess.run(
        ["xcrun", "simctl", "bootstatus", udid], check=False, capture_output=True
    )
    time.sleep(SIMULATOR_SETTLE_SECONDS)


def _names(text: str) -> set[str]:
    """Return a comma-separated argument's names."""
    return {name for name in text.split(",") if name}


def parser() -> argparse.ArgumentParser:
    """Build the command line."""
    arguments = argparse.ArgumentParser(
        description="Run the Maestro journeys, one lane each."
    )
    arguments.add_argument(
        "--out", type=Path, required=True, help="the folder for the results"
    )
    arguments.add_argument(
        "--rounds",
        default="r1",
        help="round names, comma-separated, each its own folder",
    )
    arguments.add_argument("--android", help="your emulator's serial")
    arguments.add_argument("--ios", help="your simulator's udid")
    arguments.add_argument("--flows", type=_names, help="only these, comma-separated")
    arguments.add_argument(
        "--skip", type=_names, default=set(), help="not these, comma-separated"
    )
    return arguments


def main(argv: Sequence[str] | None = None) -> None:
    """Run the rounds asked for."""
    options = parser().parse_args(argv)
    devices = {
        platform: device
        for platform, device in (("android", options.android), ("ios", options.ios))
        if device
    }
    if not devices:
        sys.exit("run_flows: name a device with --android or --ios")
    for device in devices.values():
        refuse_owners(device)
    if shutil.which("maestro") is None:
        sys.exit("run_flows: no maestro on PATH (maestro/README.md)")
    journeys = [path.stem for path in Path("maestro/journeys").glob("*.yaml")]
    run = FlowRun(options.out, options.flows, options.skip)
    for rnd in options.rounds.split(","):
        run.round(rnd, devices, journeys)


if __name__ == "__main__":
    main()
