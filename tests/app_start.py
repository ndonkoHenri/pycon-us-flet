"""The start sequence's fakes and fixtures, for its three test modules (#312).

``test_app.py`` (the boot gate), ``test_app_handlers.py`` (the page's handlers) and
``test_app_theme.py`` (the theme, the services and the slots layout) run ``bootstrap()``
against fakes: the in-memory SharedPreferences and SemanticsService of
``tests/fakes.py``, a fake page, and ``api.fetch_feed`` replaced by a held ``Network``,
so nothing reaches the network. A module takes the fixtures by assigning them to its own
names, as ``docs/testing-and-quality.md`` §3.1 says.
"""

import asyncio
from collections.abc import Awaitable, Callable, Iterator
from pathlib import Path
from typing import cast

import flet as ft
import pytest

from pycon_us.app import NO_THEME_ANIMATION, bootstrap
from pycon_us.change_log import ChangeLog
from pycon_us.config import YearData, load_year
from pycon_us.favorites import Favorites
from pycon_us.memory import ViewMemory
from pycon_us.prefs import Prefs
from pycon_us.services import Services, api
from pycon_us.services.storage import Storage
from pycon_us.state import Conference
from tests.fakes import (
    FakePage,
    MemoryClipboard,
    MemoryHaptics,
    MemoryLauncher,
    MemoryPrefs,
    MemorySemantics,
)
from tests.feeds import recorded

type Fetch = Callable[..., Awaitable[bytes]]


@pytest.fixture(scope="module")
def year() -> YearData:
    """The 2026 year data, loaded once for the module."""
    return load_year(2026)


@pytest.fixture
def shared() -> MemoryPrefs:
    """An empty in-memory SharedPreferences under the storage service."""
    return MemoryPrefs()


@pytest.fixture
def semantics() -> MemorySemantics:
    """An in-memory SemanticsService whose accessibility flags a test sets."""
    return MemorySemantics()


@pytest.fixture
def svc(
    year: YearData, shared: MemoryPrefs, semantics: MemorySemantics, tmp_path: Path
) -> Services:
    """Services for 2026 over the in-memory fakes, with files in ``tmp_path``."""
    storage = Storage(prefs=shared, directory=tmp_path, year=2026)
    return Services(
        year=year,
        storage=storage,
        memory=ViewMemory(),
        semantics=semantics,
        haptics=MemoryHaptics(),
        launcher=MemoryLauncher(),
        clipboard=MemoryClipboard(),
    )


@pytest.fixture
def fake_page() -> FakePage:
    """A fake page as ``main.prepare_first_page`` leaves it: theme crossfade off."""
    page = FakePage()
    page.theme_animation_style = NO_THEME_ANIMATION
    return page


class Network:
    """Stands in for ``api.fetch_feed``: held until released, then answers or fails."""

    def __init__(self) -> None:
        """Hold every fetch, with the recorded 2026 feed as the answer."""
        self.answer: bytes | Exception = recorded(2026)
        self.released = asyncio.Event()
        self.urls: list[str] = []

    async def fetch_feed(self, url: str, **_: object) -> bytes:
        """Record ``url``, wait for the release, then answer or raise."""
        self.urls.append(url)
        await self.released.wait()
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


@pytest.fixture
def network(monkeypatch: pytest.MonkeyPatch) -> Iterator[Network]:
    """Put a held ``Network`` in place of ``api.fetch_feed``; release it after."""
    network = Network()
    monkeypatch.setattr(api, "fetch_feed", network.fetch_feed)
    yield network
    network.released.set()  # let a held refresh end with the test


async def started(fake_page: FakePage, svc: Services) -> tuple[Conference, Prefs]:
    """Run ``bootstrap()`` on new stores and return its Conference and Prefs."""
    conference, prefs = Conference(), Prefs()
    await bootstrap(
        cast(ft.Page, fake_page), svc, conference, prefs, Favorites(), ChangeLog()
    )
    return conference, prefs


async def finish_refresh(conference: Conference, network: Network) -> None:
    """Release the network and wait for the Conference's refresh to end."""
    network.released.set()
    assert conference._task is not None
    await conference._task
