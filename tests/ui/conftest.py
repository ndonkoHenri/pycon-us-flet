"""Fixtures for the UI flows, which `flet test` runs on an emulator or a simulator.

Flet's pytest plugin gives each flow `flet_app`: a fresh launch of the test build,
driven through `flet_app.tester` (D-78; testing-and-quality.md §5). Plain
`uv run pytest` never collects this directory (`addopts`), since that fixture
provisions a Flutter test host.
"""

import os
import shutil
from collections.abc import Iterator
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

from tests.ui.feeds import SilentFeed, laptop_url

FEEDS = Path(__file__).parents[1] / "fixtures" / "feeds"


@pytest.fixture(autouse=True)
def fresh_linux_install() -> None:
    """Forget the app's data before a flow on Linux, as an install does on a phone (S9 only)."""
    if os.environ.get("FLET_TEST_PLATFORM") != "linux":
        return
    home = Path.home() / ".local" / "share"
    print("S9: app data before this flow:", sorted(p.name for p in home.glob("*")))
    for folder in [*home.glob("*confcompanion*"), *home.glob("*pycon*")]:
        shutil.rmtree(folder, ignore_errors=True)


@pytest.fixture
def feed_url() -> Iterator[str]:
    """Serve the recorded feeds from this machine; return the active year's feed URL.

    The URL is the one the app can reach (`laptop_url()`). Flows set it in the
    Developer screen with `fresh_start()` (`tests/ui/developer.py`).
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
def silent_feed() -> Iterator[SilentFeed]:
    """Serve a feed that never answers from this machine (`SilentFeed`).

    Flows set its `url` in the Developer screen, as a person would; `hold()` and
    `hang_up()` let a flow see a refresh run and end (F1).
    """
    feed = SilentFeed()
    feed.serve()
    try:
        yield feed
    finally:
        feed.close()
