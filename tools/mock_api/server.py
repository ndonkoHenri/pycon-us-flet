"""The mock API on the LAN: a stdlib HTTP server over `handle` (D-50, NEW-08).

`python -m tools.mock_api.server` serves the same pure `handle` the tests drive
through `transport.py` to the companion client, emulators, simulators and phones. Its
state is in memory, so a restart is a clean slate. It answers only from `handle`: it
never points at, proxies or copies a PSF host (D-51). `--fault` and `--skew` replay
conference Wi-Fi on a device (D-57). Options and base URLs are in `README.md`
("Running it") and `docs/development.md` §6.
"""

import argparse
import contextlib
import re
import socket
import threading
from collections.abc import Sequence
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import cast

from pycon_us.config import YEAR
from tools.mock_api.faults import FAULTS, Fault
from tools.mock_api.state import CAPTURES, MockState
from tools.mock_api.transport import handle_with_faults

MAX_BODY = 1_000_000
"""The largest request body read, in bytes; no request the app sends comes near it."""

HOLD = 60.0
"""Seconds the `timeout` fault keeps a request unanswered at most, if the client
doesn't hang up first; every Ionic timeout is shorter (20 s at most)."""

DROPPED: dict[Fault, str] = {
    "connect": "connect fault, dropped",
    "timeout": "timeout fault, held unanswered",
    "lost_response": "lost_response fault, reply dropped",
}
"""What the log says after the status for a request a fault took."""

EMULATOR_HOST = "10.0.2.2"
"""The Android emulator's alias for the host machine's loopback."""

ACCESS_CODE_IN_PATH = re.compile(r"(/lead_retrieval/)[^/]+(/note/)")
"""The one path that carries an attendee's access code as a segment."""


def loggable(path: str) -> str:
    """Return `path` as the log may show it: no query, and no access code.

    Args:
        path: The request target as received.

    Returns:
        The path without its query, with the code in `lead_retrieval/<code>/note/`
        replaced by `<code>`.
    """
    return ACCESS_CODE_IN_PATH.sub(r"\1<code>\2", path.partition("?")[0])


class MockServer(ThreadingHTTPServer):
    """A threaded HTTP server that answers every request with `handle`.

    One lock serialises the calls to `handle`, since `MockState` is not thread-safe
    and a request may both read and write it.

    Attributes:
        state: The mock's state, shared by every request.
        lock: Held while `handle` runs.
    """

    daemon_threads = True  # a hung client never keeps Ctrl-C from stopping the server

    def __init__(self, address: tuple[str, int], state: MockState) -> None:
        """Bind the server.

        Args:
            address: The host and port to listen on; port 0 picks a free one.
            state: The mock's state.
        """
        super().__init__(address, MockRequestHandler)
        self.state = state
        self.lock = threading.Lock()


class MockRequestHandler(BaseHTTPRequestHandler):
    """Hands one HTTP request to `handle` and writes its reply back unchanged.

    Every response, `handle`'s or an error the server sends itself, logs exactly one
    line through `log_request`; the inherited request-line and error logging, which
    would show the query, is replaced.
    """

    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        """Log one line: the method, the path without query or access code, the status.

        Args:
            code: The response status.
            size: Unused; the inherited signature's response size.
        """
        method = getattr(self, "command", None) or "-"
        path = loggable(getattr(self, "path", "") or "-")
        self.log_message("%s %s %s", method, path, code)

    def log_error(self, format: str, *args: object) -> None:
        """Log nothing: the error's response logs its own line (`log_request`).

        Args:
            format: Unused; the inherited message format.
            *args: Unused; its arguments.
        """

    def answer(self) -> None:
        """Answer the request with `handle`'s reply, and log one line about it.

        The request target and the body reach `handle` exactly as received, so the
        signature is checked over the bytes the client signed. The reply's headers are
        `handle`'s alone: its `Date` comes from the mock's clock, which the client
        learns clock skew from (D-53), so the server adds no `Date` of its own.

        A transport fault (D-57) sends no reply and closes the connection: `connect`
        at once, without running `handle`; `timeout` once the client hangs up (or
        after `HOLD`), without running it; `lost_response` after `handle` has
        run, so its writes stay.
        """
        server = cast(MockServer, self.server)
        length = self.headers.get("Content-Length", "0")
        if not (length.isascii() and length.isdigit()):
            self.send_error(400, "Malformed Content-Length")
            return
        if int(length) > MAX_BODY:
            self.send_error(413)
            return
        body = self.rfile.read(int(length))
        with server.lock:
            fault, answered = handle_with_faults(
                server.state, self.command, self.path, dict(self.headers.items()), body
            )
        if fault is not None:
            self.drop(fault, answered[0] if answered else "-")
            return
        assert answered is not None  # no fault took it, so handle ran
        status, headers, reply = answered
        # Logged before the reply is sent, so the line is there by the time the client
        # has its answer; send_response_only logs nothing itself.
        self.log_request(status)
        self.send_response_only(status)
        for name, value in headers.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(reply)))
        self.end_headers()
        self.wfile.write(reply)

    do_GET = do_POST = do_PATCH = do_PUT = do_DELETE = answer

    def drop(self, fault: Fault, status: int | str) -> None:
        """Log a request a fault took, then close its connection without a reply.

        Args:
            fault: The fault taken.
            status: `handle`'s status when it ran (`lost_response`), else `-`.
        """
        self.log_request(f"{status} ({DROPPED[fault]})")
        self.close_connection = True
        if fault == "timeout":
            # Wait for the client to give up: its read returns b"" once it hangs up.
            self.connection.settimeout(HOLD)
            with contextlib.suppress(OSError):  # HOLD passed first
                self.rfile.read(1)


def lan_addresses() -> list[str]:
    """Return the IPv4 address other devices on this machine's network reach it at.

    Connecting a UDP socket sends nothing: it only asks the OS which interface would
    carry traffic to that address. 192.0.2.1 is TEST-NET-1 (RFC 5737), reserved for
    documentation, so no real host is involved.

    Returns:
        The address in a list, or an empty list when the machine has no network.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("192.0.2.1", 9))
            address = probe.getsockname()[0]
    except OSError:
        return []
    return [] if address.startswith(("127.", "0.")) else [address]


def banner(host: str, port: int, state: MockState, lan: Sequence[str]) -> str:
    """Say where the server listens, which base URL each device uses, and how to sign in.

    Args:
        host: The address the server is bound to.
        port: The port it listens on.
        state: The mock's state, for its year, capture semantics and accounts.
        lan: This machine's LAN addresses (`lan_addresses()`).

    Returns:
        The text printed on start. It names each account's email and password, all
        fake, and never a key or a secret.
    """
    lines = [
        f"Mock PyCon API {state.year} on {host}:{port}, {state.capture} capture.",
        "Base URLs for Developer › Mock API base URL:",
    ]
    if host in ("0.0.0.0", "127.0.0.1", "localhost"):
        lines += [
            f"  this machine, iOS simulator  http://localhost:{port}",
            f"  Android emulator             http://{EMULATOR_HOST}:{port}",
        ]
        if host != "0.0.0.0":
            lines.append(
                "  phones on the Wi-Fi          not reachable: use --host 0.0.0.0"
            )
        for address in lan if host == "0.0.0.0" else ():
            lines.append(f"  phones on the Wi-Fi          http://{address}:{port}")
    else:
        lines.append(f"  devices that reach {host}  http://{host}:{port}")
    lines.extend(fault_lines(state))
    lines.append("Seeded accounts (fake; they work only against this mock):")
    email = max(len(account.email) for account in state.accounts)
    password = max(len(account.password) for account in state.accounts)
    for account in state.accounts:
        lines.append(
            f"  {account.email:<{email}}  {account.password:<{password}}  {account.role}"
        )
    return "\n".join(lines)


def fault_lines(state: MockState) -> list[str]:
    """Say which faults are on and how far the clock is skewed, for the banner.

    Args:
        state: The mock's state.

    Returns:
        One line for the faults and one for the skew, each only when there is one.
    """
    lines = []
    if state.faults.on:
        faults = ", ".join(
            f"{fault} ({'every request' if every else 'next request'})"
            for fault, every in state.faults.on.items()
        )
        lines.append(f"Faults on (D-57): {faults}.")
    if state.skew:
        lines.append(f"Clock skewed {state.skew:+g} s from this machine's.")
    return lines


def parser() -> argparse.ArgumentParser:
    """The command line's parser: where to listen, the semantics and the faults."""
    parser = argparse.ArgumentParser(
        prog="python -m tools.mock_api.server",
        description="Serve the mock PyCon API (fake data only) over HTTP.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="IPv4 address to listen on (default 127.0.0.1: this machine, its "
        "simulators and emulators; 0.0.0.0 also serves phones on the LAN)",
    )
    parser.add_argument("--port", type=int, default=8000, help="default 8000")
    parser.add_argument(
        "--capture",
        choices=CAPTURES,
        default="idempotent",
        help="how a repeated capture or redeem is applied (D-57; default idempotent)",
    )
    parser.add_argument(
        "--fault",
        action="append",
        choices=FAULTS,
        default=[],
        help="a fault for the next request (repeat for several; D-57)",
    )
    parser.add_argument(
        "--every-request",
        action="store_true",
        help="keep each --fault on for every request until the server stops",
    )
    parser.add_argument(
        "--skew",
        type=float,
        default=0.0,
        metavar="SECONDS",
        help="run the mock's clock this far ahead (behind when negative; default 0)",
    )
    parser.add_argument(
        "--attendees",
        type=attendee_count,
        default=0,
        metavar="N",
        help="add N made-up attendees after the seeded four, MOCK0005 onwards "
        "(a large CoC directory; default 0)",
    )
    return parser


def attendee_count(value: str) -> int:
    """Read `--attendees`: a whole number, 0 or more.

    Raises:
        argparse.ArgumentTypeError: For anything else, which argparse reports.
    """
    try:
        count = int(value)
    except ValueError:
        count = -1
    if count < 0:
        raise argparse.ArgumentTypeError(f"not a count of attendees: {value!r}")
    return count


def state_for(args: argparse.Namespace) -> MockState:
    """A fresh seeded state with the command line's semantics, attendees, faults and skew."""
    state = MockState.from_seed(capture=args.capture, attendees=args.attendees)
    state.year = YEAR  # the app's: the seed stays on the year the tests pin
    for fault in args.fault:
        state.faults.inject(fault, until_cleared=args.every_request)
    state.skew = args.skew
    return state


def main(argv: Sequence[str] | None = None) -> None:
    """Run the server until Ctrl-C.

    Args:
        argv: The command-line arguments; None reads `sys.argv`.
    """
    args = parser().parse_args(argv)
    state = state_for(args)
    with MockServer((args.host, args.port), state) as server:
        port = server.server_port
        print(banner(args.host, port, state, lan_addresses()), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped; the state is gone.")


if __name__ == "__main__":
    main()
