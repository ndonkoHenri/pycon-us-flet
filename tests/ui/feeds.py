"""The feeds a UI flow's app reads from this machine, and the one that never answers.

``laptop_url()`` is the URL the app reaches this machine at. ``SilentFeed`` is a feed
server that takes each request and hangs up with no answer, for F1 (D-223): the app
reads that as no answer from the feed (httpx's ``RemoteProtocolError``, a
``TransportError``, so ``api.NetworkError``), "offline" without airplane mode, which
would also cut the tester's own socket (testing-and-quality.md §5.2).
"""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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
        with self._lock:
            self._requests += 1
