"""The Conference store's feeds, transports and fixtures, for its four test modules (#312).

``test_state.py`` (the cache-first load and the refresh), ``test_state_refresh_ends.py``
(the same feed again, a closed session, an unexpected error), ``test_state_status.py``
(the status, the data's age and the automatic refreshes) and ``test_state_feed_url.py``
(the Developer feed URL and the reset) serve the feed with an ``httpx.MockTransport``,
never the network. The feed cache lives in a temporary directory, with SharedPreferences
replaced by the in-memory fake from ``tests/fakes.py``; time comes from
``clock.set_test_now()``. A module takes the fixtures by assigning them to its own names,
as ``docs/testing-and-quality.md`` §3.1 says.
"""

import asyncio
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from pycon_us import clock
from pycon_us.config import YearData, load_year
from pycon_us.core.models import ConferenceData
from pycon_us.feed_refresh import Status
from pycon_us.services.storage import Storage
from pycon_us.state import Conference
from tests.fakes import MemoryPrefs
from tests.feeds import changed
from tests.small_stack import TOO_DEEP_TO_PARSE, nested_lists

NOW = datetime(2026, 10, 12, 9, 30, tzinfo=UTC)
TALK = "142"  # a 2026 talk; the variants below rename it


def renamed(name: str) -> bytes:
    """The recorded 2026 feed with talk 142 renamed, so its source shows."""

    def rename(document: dict[str, Any]) -> None:
        slot = next(s for s in document["schedule"] if s.get("conf_key") == int(TALK))
        slot["name"] = name

    return changed(2026, rename)


NETWORK_FEED = renamed("Renamed on the server")
CACHED_FEED = renamed("Renamed in the cache")


@pytest.fixture(autouse=True)
def frozen_clock() -> Iterator[None]:
    """Freeze ``clock.now()`` at ``NOW`` for the test, then return to real time."""
    clock.set_test_now(NOW)
    yield
    clock.set_test_now(None)


@pytest.fixture(scope="module")
def year() -> YearData:
    """The 2026 year data, loaded once for the module."""
    return load_year(2026)


@pytest.fixture
def storage(tmp_path: Path) -> Storage:
    """A 2026 ``Storage`` in ``tmp_path``, over in-memory SharedPreferences."""
    return Storage(prefs=MemoryPrefs(), directory=tmp_path, year=2026)


def serving(body: bytes, status: int = 200) -> httpx.MockTransport:
    """A transport that answers the 2026 feed URL with ``body``."""

    def handle(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://us.pycon.org/2026/schedule/conference.json"
        return httpx.Response(status, content=body)

    return httpx.MockTransport(handle)


def failing(error: Exception) -> httpx.MockTransport:
    """A transport whose every request raises ``error``."""

    def handle(request: httpx.Request) -> httpx.Response:
        raise error

    return httpx.MockTransport(handle)


class HeldFeed:
    """A transport that serves ``NETWORK_FEED`` once ``release()`` is called, counting requests.

    Given an ``error``, it raises that instead once released: a refresh that fails late.
    """

    def __init__(self, error: Exception | None = None) -> None:
        """Hold every request until ``release()``; raise ``error`` then, if given."""
        self.error = error
        self.requests = 0
        self.arrived = asyncio.Event()
        self._released = asyncio.Event()
        self.transport = httpx.MockTransport(self._handle)

    def release(self) -> None:
        """Let the held requests, and any later one, answer."""
        self._released.set()

    async def _handle(self, request: httpx.Request) -> httpx.Response:
        """Count the request, wait for the release, then answer or raise."""
        self.requests += 1
        self.arrived.set()
        await self._released.wait()
        if self.error is not None:
            raise self.error
        return httpx.Response(200, content=NETWORK_FEED)


def title(data: ConferenceData | None) -> str:
    """Return talk 142's name in ``data``, which must be loaded."""
    assert data is not None
    return data.sessions[TALK].name


async def loaded(storage: Storage, year: YearData) -> Conference:
    """Return a new ``Conference`` after its ``load_local()``."""
    conference = Conference()
    await conference.load_local(storage, year)
    return conference


FAILURES: list[tuple[str, Callable[[], httpx.MockTransport], Status]] = [
    ("no connection", lambda: failing(httpx.ConnectError("offline")), "offline"),
    ("timeout", lambda: failing(httpx.ReadTimeout("timed out")), "offline"),
    ("HTTP 500", lambda: serving(b"<h1>Server error</h1>", status=500), "problem"),
    ("HTTP 404", lambda: serving(b"", status=404), "problem"),
    ("an HTML page", lambda: serving(b"<html>Wi-Fi sign-in</html>"), "problem"),
    ("a truncated feed", lambda: serving(NETWORK_FEED[:1000]), "problem"),
    ("nested too deep", lambda: serving(nested_lists(TOO_DEEP_TO_PARSE)), "problem"),
    ("no schedule", lambda: serving(b'{"posters": []}'), "problem"),
]
