"""Keep a mock on this checkout's own port, past the command that starts it.

Usage, from the checkout's root::

    uv run python -m tools.mock_api.own start [server options, e.g. --fault lost_response]
    uv run python -m tools.mock_api.own url android|ios
    uv run python -m tools.mock_api.own stop

The default port 8000 is everyone's, so a parallel agent's flows would land on someone
else's mock. Here the port comes from the checkout's path, and stays until the checkout
goes. A second ``start`` keeps the running mock and its state; ``stop`` then ``start`` is
a clean slate (``docs/development.md`` §6).
"""

import argparse
import hashlib
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from tools.mock_api.server import EMULATOR_HOST

ROOT = Path(__file__).resolve().parents[2]
FIRST_PORT = 8100
PORTS = 800
"""The range the ports come from, clear of the mock's 8000 and hot reload's 8550 by chance
only: a port something else holds moves the mock to the next free one."""

START_SECONDS = 30.0
"""How long the server may take to answer: it imports the app's core, on a busy host."""


def preferred_port(root: Path) -> int:
    """Return the port this checkout tries first, the same on every run."""
    digest = hashlib.sha256(str(root).encode()).digest()
    return FIRST_PORT + int.from_bytes(digest[:4], "big") % PORTS


def _answers(port: int) -> bool:
    """Return whether something accepts connections on this port of this machine."""
    with socket.socket() as probe:
        probe.settimeout(0.5)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def free_port(root: Path) -> int:
    """Return this checkout's port, or the next one nothing holds."""
    first = preferred_port(root)
    for step in range(PORTS):
        port = FIRST_PORT + (first - FIRST_PORT + step) % PORTS
        if not _answers(port):
            return port
    sys.exit("own.py: every port in the range is taken")


def url(port: int, platform: str) -> str:
    """Return ``MOCK_URL`` for a device on this machine: an emulator reaches it differently."""
    return f"http://{EMULATOR_HOST if platform == 'android' else 'localhost'}:{port}"


def running(state: Path) -> tuple[int, int] | None:
    """Return the (pid, port) of this checkout's mock, or None if it has gone."""
    try:
        pid, port = (int(part) for part in (state / "pid").read_text().split())
        os.kill(pid, 0)
    except OSError, ValueError:
        return None
    return pid, port


def start(state: Path, options: list[str]) -> int:
    """Start the mock unless it is running, and return its port.

    Args:
        state: The folder for its pid and log.
        options: Passed to ``tools.mock_api.server`` when it starts here; a running mock
            keeps the options it has, and this says so.
    """
    alive = running(state)
    if alive:
        if options:
            print(
                f"own.py: already running; ignoring {options}: stop it first",
                file=sys.stderr,
            )
        return alive[1]
    state.mkdir(parents=True, exist_ok=True)
    port = free_port(ROOT)
    with (state / "log").open("w") as log:
        # Its own session, so it outlives this command.
        process = subprocess.Popen(
            [
                sys.executable,
                "-u",
                "-m",
                "tools.mock_api.server",
                "--port",
                str(port),
                *options,
            ],
            cwd=ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    deadline = time.monotonic() + START_SECONDS
    while not _answers(port):
        if process.poll() is not None or time.monotonic() > deadline:
            process.terminate()
            sys.exit(f"own.py: the mock didn't start; see {state / 'log'}")
        time.sleep(0.2)
    (state / "pid").write_text(f"{process.pid} {port}\n")
    return port


def stop(state: Path) -> bool:
    """Stop this checkout's mock and return whether one was running."""
    alive = running(state)
    (state / "pid").unlink(missing_ok=True)
    if alive is None:
        return False
    os.kill(alive[0], signal.SIGTERM)
    return True


def main(argv: list[str] | None = None, state: Path = ROOT / "build" / "mock") -> None:
    """Run the command line."""
    parser = argparse.ArgumentParser(prog="tools.mock_api.own", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "start", help="start it unless it runs; the rest goes to the server"
    )
    which = commands.add_parser("url", help="print MOCK_URL for a platform")
    which.add_argument("platform", choices=("android", "ios"))
    commands.add_parser("stop", help="stop it; its state goes with it")
    args, options = parser.parse_known_args(argv)
    if args.command == "start":
        port = start(state, options)
        print(f"Android emulator: -e MOCK_URL={url(port, 'android')}")
        print(f"iOS simulator:    -e MOCK_URL={url(port, 'ios')}")
        print(f"Log: {state / 'log'}")
    elif options:
        parser.error(f"unrecognised arguments: {' '.join(options)}")
    elif args.command == "url":
        alive = running(state)
        if alive is None:
            sys.exit("own.py: not running: start it first")
        print(url(alive[1], args.platform))
    elif not stop(state):
        print("own.py: wasn't running", file=sys.stderr)


if __name__ == "__main__":
    main()
