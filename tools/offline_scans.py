"""Run F8 Maestro with a mock whose listener can stop without losing its captures.

Usage: uv run python -m tools.offline_scans --device <id> --platform android|ios
The control listener binds only to the laptop's loopback. It is test tooling, never
an endpoint in the app or the public mock contract. Non-idempotent mode exposes
accidental duplicate sends that an idempotent mock would hide.
"""

import argparse
import subprocess
import threading
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from tools.mock_api.server import MockServer
from tools.mock_api.state import MockState


class Listener:
    """Own a replaceable mock listener and the state that survives its replacement."""

    def __init__(self, port: int) -> None:
        """Create the seed state, then open the mock's port."""
        self.port = port
        self.state = MockState.from_seed(capture="non_idempotent")
        self.server: MockServer | None = None
        self.online()

    def online(self) -> None:
        """Resume the mock, preserving the same seed and captures."""
        if self.server is None:
            self.server = MockServer(("127.0.0.1", self.port), self.state)
            self.port = self.server.server_port
            threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def offline(self) -> None:
        """Close the mock's listening socket before the flow enters its codes."""
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.server = None


def main() -> None:
    """Run one device's journey, verify exact captures, and close both listeners."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", required=True)
    parser.add_argument("--platform", choices=("android", "ios"), required=True)
    parser.add_argument("--port", type=int, default=8470)
    parser.add_argument("--control-port", type=int, default=8471)
    args = parser.parse_args()
    listener = Listener(args.port)

    class Control(BaseHTTPRequestHandler):
        """Accept only the two listener actions from the laptop's Maestro process."""

        def do_POST(self) -> None:
            """Finish changing the listener before acknowledging the action."""
            if self.path == "/offline":
                listener.offline()
            elif self.path == "/online":
                listener.online()
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")

    try:
        with ThreadingHTTPServer(("127.0.0.1", args.control_port), Control) as control:
            threading.Thread(target=control.serve_forever, daemon=True).start()
            host = "10.0.2.2" if args.platform == "android" else "127.0.0.1"
            try:
                subprocess.run(
                    [
                        "maestro",
                        "--device",
                        args.device,
                        "test",
                        "-e",
                        f"MOCK_URL=http://{host}:{listener.port}",
                        "-e",
                        f"CONTROL_URL=http://127.0.0.1:{args.control_port}",
                        "maestro/journeys/offline_scans.yaml",
                    ],
                    check=True,
                    timeout=900,
                )
                listener.offline()
                counts = Counter(
                    (lead.sponsor_id, lead.access_code) for lead in listener.state.leads
                )
                expected = Counter({(1, "MOCK0001"): 1, (1, "MOCK0002"): 1})
                if counts != expected:
                    raise RuntimeError(
                        f"F8 captures differ: {counts!r}, expected {expected!r}"
                    )
                print("F8: exactly one capture per code for scan-time sponsor 1")
            finally:
                control.shutdown()
    finally:
        listener.offline()


if __name__ == "__main__":
    main()
