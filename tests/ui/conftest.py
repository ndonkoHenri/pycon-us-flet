"""Fixtures for the UI flows, which ``flet test`` runs on an emulator or a simulator.

Flet's pytest plugin gives each flow ``flet_app``: a fresh launch of the test build,
driven through ``flet_app.tester`` (D-78; testing-and-quality.md §5). Plain
``uv run pytest`` never collects this directory (``addopts``), since that fixture
provisions a Flutter test host.
"""

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

    The URL is the one the app can reach: the Android emulator sees this machine at
    ``10.0.2.2``, the iOS simulator shares its network. Flows set it in the Developer
    screen (P1-28); a closed port stands for "offline", since airplane mode would also
    cut the tester's own socket (testing-and-quality.md §5.2).
    """
    handler = partial(SimpleHTTPRequestHandler, directory=str(FEEDS))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    Thread(target=server.serve_forever, daemon=True).start()
    host = "10.0.2.2" if PLATFORM == "android" else "127.0.0.1"
    try:
        yield f"http://{host}:{server.server_address[1]}/conference-{YEAR}.json"
    finally:
        server.shutdown()
        server.server_close()
