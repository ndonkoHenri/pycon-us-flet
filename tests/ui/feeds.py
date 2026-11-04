"""The feeds a UI flow's app reads from this machine: one that never answers, and a pair.

``laptop_url()`` is the URL the app reaches this machine at. ``SilentFeed`` is a feed
server that takes each request and hangs up with no answer, for F1 (D-223): the app
reads that as no answer from the feed (httpx's ``RemoteProtocolError``, a
``TransportError``, so ``api.NetworkError``), "offline" without airplane mode, which
would also cut the tester's own socket (testing-and-quality.md §5.2). ``PairFeed``
serves a change-log pair at one URL, the old feed and then, once swapped, the new one,
for the change log's device check (#460, D-255); ``tools/feed_pair.py`` runs it.
"""

import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from pycon_us.config import YEAR
from tests.ui.helpers import PLATFORM

HOLD_LIMIT = 30.0
"""Seconds a held request waits for ``hang_up()`` at most, so a failed flow's teardown
never waits on it. The app gives up first: its feed timeout is 10 s (``api.FEED_TIMEOUT``),
which the app also reads as no answer."""


def laptop_url(port: int) -> str:
    """Return the URL of the active year's feed on this machine's ``port``, as the app reaches it.

    The Android emulator sees this machine at ``10.0.2.2``; the iOS simulator shares its
    network.
    """
    host = "10.0.2.2" if PLATFORM == "android" else "127.0.0.1"
    return f"http://{host}:{port}/conference-{YEAR}.json"


class SilentFeed:
    """A feed server on this machine that takes each request and hangs up, unanswered.

    It counts the requests it has taken, so a flow knows the app asked; ``hold()`` keeps
    the next ones open until ``hang_up()``, so a flow sees a refresh it asked for run
    ("Updating the schedule…") and then end. A refused connection, on a closed port,
    can start and end between two polls, and then a flow cannot tell a refresh that
    ran from a tap that was lost.

    Attributes:
        url: The feed URL the app can reach (``laptop_url()``).
    """

    def __init__(self) -> None:
        """Create the server on a free port of ``127.0.0.1``; ``serve()`` starts it."""
        self._lock = threading.Lock()
        self._requests = 0
        self._answer_now = threading.Event()  # set: hang up at once; clear: hold
        self._answer_now.set()
        feed = self

        class HangUp(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                feed._took()
                feed._answer_now.wait(HOLD_LIMIT)
                # Returning without a response closes the connection: no answer.

            def log_message(self, format: str, *args: object) -> None:
                pass  # each refresh would print a line in the flow's output

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), HangUp)
        self.url = laptop_url(self._server.server_address[1])

    @property
    def requests(self) -> int:
        """How many requests the server has taken so far."""
        with self._lock:
            return self._requests

    def hold(self) -> None:
        """Keep the next requests open, unanswered, until ``hang_up()``."""
        self._answer_now.clear()

    def hang_up(self) -> None:
        """Close the held requests, and the next ones at once, with no answer."""
        self._answer_now.set()

    def serve(self) -> None:
        """Start serving on a daemon thread."""
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def close(self) -> None:
        """Hang up on any held request, then stop the server and free its port."""
        self.hang_up()
        self._server.shutdown()
        self._server.server_close()

    def _took(self) -> None:
        """Count one request the feed took, under the lock."""
        with self._lock:
            self._requests += 1


class PairFeed:
    """A feed server on this machine that serves a pair's old feed, then its new one.

    The active year's feed path (``laptop_url()``'s) answers with ``old`` until
    ``swap()``, then with ``new``: one feed URL whose feed changes, which is what the
    app diffs (D-255; a feed URL change would delete the cache and the change log). A
    flow on the laptop calls ``swap()``; Maestro, whose scripts run on the laptop too,
    posts to ``control_url``: ``POST /swap`` serves the new feed, ``POST /reset`` the
    old one again, so a flow can start from the old feed on a server left running.
    ``POST /hold`` keeps the next feed requests open until ``POST /release``, so a flow
    sees a refresh run for as long as it needs, up to the app's own feed timeout (D-449);
    a reset releases them too. Any other path is a 404.

    Attributes:
        port: The port it listens on, on ``127.0.0.1``.
        url: The feed URL the app can reach (``laptop_url()``).
        feed_path: The path the feed is served at, ``/conference-<year>.json``.
        control_url: Where the laptop reaches the control paths: ``http://127.0.0.1:<port>``.
    """

    def __init__(self, old: bytes, new: bytes, port: int = 0) -> None:
        """Create the server; ``serve()`` starts it.

        Args:
            old: The feed served first.
            new: The feed served once swapped.
            port: The port to listen on; 0 picks a free one.
        """
        self._lock = threading.Lock()
        self._sides = (old, new)
        self._swapped = False
        self._requests = 0
        self._answer_now = threading.Event()  # set: answer at once; clear: hold
        self._answer_now.set()
        feed = self

        class Pair(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if self.path.partition("?")[0] != feed.feed_path:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                feed._answer_now.wait(HOLD_LIMIT)
                body = feed._took()
                try:
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except OSError:
                    pass  # the app gave up on a held request: its own timeout

            def do_POST(self) -> None:
                controls = {
                    "/swap": feed.swap,
                    "/reset": feed.reset,
                    "/hold": feed.hold,
                    "/release": feed.release,
                }
                control = controls.get(self.path)
                if control is None:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                control()
                side = b"new" if feed.swapped else b"old"
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(side)))
                self.end_headers()
                self.wfile.write(side)

            def log_message(self, format: str, *args: object) -> None:
                pass  # the CLI says what it serves; a line per request is noise

        self._server = ThreadingHTTPServer(("127.0.0.1", port), Pair)
        self.port: int = self._server.server_address[1]
        self.url = laptop_url(self.port)
        self.feed_path = urlsplit(self.url).path
        self.control_url = f"http://127.0.0.1:{self.port}"

    @property
    def requests(self) -> int:
        """How many feed requests the server has answered so far."""
        with self._lock:
            return self._requests

    @property
    def swapped(self) -> bool:
        """Whether the server serves the new feed."""
        with self._lock:
            return self._swapped

    def swap(self) -> None:
        """Serve the new feed from the next request on."""
        with self._lock:
            self._swapped = True

    def reset(self) -> None:
        """Serve the old feed again from the next request on, with nothing held."""
        with self._lock:
            self._swapped = False
        self.release()

    def hold(self) -> None:
        """Keep the next feed requests open until ``release()``."""
        self._answer_now.clear()

    def release(self) -> None:
        """Answer the held feed requests, and the next ones at once."""
        self._answer_now.set()

    def serve(self) -> None:
        """Start serving on a daemon thread."""
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def close(self) -> None:
        """Release any held request, then stop the server and free its port."""
        self.release()
        self._server.shutdown()
        self._server.server_close()

    def _took(self) -> bytes:
        """Count one feed request and return the side to answer it with, under the lock."""
        with self._lock:
            self._requests += 1
            return self._sides[self._swapped]
