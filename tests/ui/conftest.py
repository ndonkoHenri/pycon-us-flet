"""Fixtures for the UI flows, which ``flet test`` runs on an emulator or a simulator.

Flet's pytest plugin gives each flow ``flet_app``: a fresh launch of the test build,
driven through ``flet_app.tester`` (D-78; testing-and-quality.md §5). Plain
``uv run pytest`` never collects this directory (``addopts``), since that fixture
provisions a Flutter test host.
"""

import socket
from collections.abc import Iterator
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

from pycon_us.config import YEAR
from tests.ui.helpers import PLATFORM

FEEDS = Path(__file__).parents[1] / "fixtures" / "feeds"


@pytest.fixture
def feed_url() -> Iterator[str]:
    """Serve the recorded feeds from this machine; return the active year's feed URL.

    The URL is the one the app can reach (``laptop_url()``). Flows set it in the
    Developer screen with ``fresh_start()`` (``tests/ui/developer.py``).
    """
    handler = partial(SimpleHTTPRequestHandler, directory=str(FEEDS))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield laptop_url(server.server_address[1])
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def offline_url() -> str:
    """Return a feed URL on a closed port of this machine: a feed that never answers.

    The port is one the system just handed out and took back, so nothing listens there
    and the app's request is refused at once: "offline" without airplane mode, which
    would also cut the tester's own socket (testing-and-quality.md §5.2).
    """
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    return laptop_url(port)


def laptop_url(port: int) -> str:
    """Return the URL of the active year's feed on this machine's ``port``, as the app reaches it.

    The Android emulator sees this machine at ``10.0.2.2``; the iOS simulator shares its
    network.
    """
    host = "10.0.2.2" if PLATFORM == "android" else "127.0.0.1"
    return f"http://{host}:{port}/conference-{YEAR}.json"
