"""Tests for the start sequence and the boot gate (DATA-35, SHELL-01; D-69, D-147).

``bootstrap()`` runs against fakes: the in-memory SharedPreferences and
SemanticsService of ``tests/fakes.py``, a fake page, and ``api.fetch_feed`` replaced so
nothing reaches the network. The components themselves are checked on devices (the PR).
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterator
from pathlib import Path
from typing import cast

import flet as ft
import pytest

from pycon_us.app import (
    NO_THEME_ANIMATION,
    apply_theme,
    bootstrap,
    read_accessibility,
)
from pycon_us.config import YearData, load_year
from pycon_us.prefs import Prefs
from pycon_us.services import Services, api
from pycon_us.services.storage import Storage
from pycon_us.state import Conference, ViewMemory
from tests.fakes import FakePage, MemoryPrefs, MemorySemantics
from tests.feeds import recorded

type Fetch = Callable[..., Awaitable[bytes]]


@pytest.fixture(scope="module")
def year() -> YearData:
    return load_year(2026)


@pytest.fixture
def shared() -> MemoryPrefs:
    return MemoryPrefs()


@pytest.fixture
def semantics() -> MemorySemantics:
    return MemorySemantics()


@pytest.fixture
def svc(
    year: YearData, shared: MemoryPrefs, semantics: MemorySemantics, tmp_path: Path
) -> Services:
    storage = Storage(prefs=shared, directory=tmp_path, year=2026)
    return Services(
        year=year, storage=storage, memory=ViewMemory(), semantics=semantics
    )


@pytest.fixture
def fake_page() -> FakePage:
    return FakePage()


class Network:
    """Stands in for ``api.fetch_feed``: held until released, then answers or fails."""

    def __init__(self) -> None:
        self.answer: bytes | Exception = recorded(2026)
        self.released = asyncio.Event()

    async def fetch_feed(self, url: str, **_: object) -> bytes:
        await self.released.wait()
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


@pytest.fixture
def network(monkeypatch: pytest.MonkeyPatch) -> Iterator[Network]:
    network = Network()
    monkeypatch.setattr(api, "fetch_feed", network.fetch_feed)
    yield network
    network.released.set()  # let a held refresh end with the test


async def started(fake_page: FakePage, svc: Services) -> tuple[Conference, Prefs]:
    conference, prefs = Conference(), Prefs()
    await bootstrap(cast(ft.Page, fake_page), svc, conference, prefs)
    return conference, prefs


async def finish_refresh(conference: Conference, network: Network) -> None:
    network.released.set()
    assert conference._task is not None
    await conference._task


# ------------------------------------------------------------------ the gate


async def test_the_gate_opens_on_the_bundled_feed_without_waiting_for_the_network(
    fake_page: FakePage, svc: Services, network: Network
) -> None:
    conference, prefs = await started(fake_page, svc)
    # The network has not answered, yet the first screen has data (D-38).
    assert prefs.loaded
    assert conference.source == "bundled"
    assert conference.data is not None
    await asyncio.sleep(0)  # the refresh task's first step
    assert conference.refreshing  # in the background, not awaited


async def test_the_stored_theme_is_on_the_page_before_the_gate_opens(
    fake_page: FakePage, svc: Services, shared: MemoryPrefs, network: Network
) -> None:
    shared.values["pycon.theme"] = "dark"
    conference, prefs = Conference(), Prefs()
    seen_at_open: list[object] = []

    def listener(_sender: object, name: str | None) -> None:
        if name == "theme":
            seen_at_open.append(fake_page.theme_animation_style)
        if name == "loaded":
            seen_at_open.append(fake_page.theme_mode)
            seen_at_open.append(conference.source)

    assert isinstance(prefs, ft.Observable)
    prefs.subscribe(listener)
    await bootstrap(cast(ft.Page, fake_page), svc, conference, prefs)
    # No theme flash and no empty first screen (SHELL-01): the stored theme is set with
    # no crossfade, before the gate opens, and later changes crossfade again.
    assert seen_at_open == [NO_THEME_ANIMATION, ft.ThemeMode.DARK, "bundled"]
    assert fake_page.theme_animation_style is None
    assert fake_page.theme is not None and fake_page.dark_theme is not None


async def test_the_os_brightness_and_accessibility_flags_are_read_at_start(
    svc: Services, semantics: MemorySemantics, network: Network
) -> None:
    semantics.features.update(high_contrast=True, disable_animations=True)
    _, prefs = await started(FakePage(ft.Brightness.DARK), svc)
    assert (prefs.os_dark, prefs.os_high_contrast, prefs.reduce_motion) == (
        True,
        True,
        True,
    )
    assert prefs.dark  # Appearance System follows the OS


async def test_the_cache_is_shown_before_the_snapshot(
    fake_page: FakePage, svc: Services, network: Network
) -> None:
    await svc.storage.write_feed(recorded(2026))
    conference, _ = await started(fake_page, svc)
    assert conference.source == "cache"


async def test_an_offline_start_keeps_the_snapshot_and_says_offline(
    fake_page: FakePage, svc: Services, network: Network
) -> None:
    network.answer = api.NetworkError("no route to host")
    conference, _ = await started(fake_page, svc)
    await finish_refresh(conference, network)
    assert conference.source == "bundled"
    assert conference.problem == "offline"


async def test_an_online_start_replaces_the_snapshot_with_the_network_feed(
    fake_page: FakePage, svc: Services, network: Network
) -> None:
    conference, _ = await started(fake_page, svc)
    await finish_refresh(conference, network)
    assert conference.source == "network"
    assert conference.version == 2
    assert svc.storage.feed_path.exists()


async def test_an_unexpected_start_error_is_logged_and_the_gate_still_opens(
    fake_page: FakePage,
    svc: Services,
    network: Network,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def broken(*_: object) -> None:
        raise RuntimeError("a bug")

    monkeypatch.setattr(Conference, "load_local", broken)
    with caplog.at_level(logging.ERROR):
        conference, prefs = await started(fake_page, svc)
    assert prefs.loaded  # never stuck on the boot view
    assert conference.data is None
    assert "Start failed" in caplog.text
    assert "RuntimeError: a bug" in caplog.text


async def test_unreadable_accessibility_flags_keep_their_defaults(
    fake_page: FakePage,
    svc: Services,
    semantics: MemorySemantics,
    network: Network,
    caplog: pytest.LogCaptureFixture,
) -> None:
    semantics.error = TimeoutError()
    with caplog.at_level(logging.WARNING):
        _, prefs = await started(fake_page, svc)
    assert prefs.loaded
    assert (prefs.os_high_contrast, prefs.reduce_motion) == (False, False)
    assert "accessibility features" in caplog.text


# ------------------------------------------------------------------ page handlers


async def test_a_brightness_change_writes_the_store(
    fake_page: FakePage, svc: Services, network: Network
) -> None:
    _, prefs = await started(fake_page, svc)
    page = cast(ft.Page, fake_page)
    fake_page.platform_brightness = ft.Brightness.DARK
    # What the pinned Flet delivers: a plain event whose data is the name (iOS sim).
    fake_page.on_platform_brightness_change(
        ft.ControlEvent(name="platform_brightness_change", control=page, data="dark")
    )
    assert prefs.os_dark


async def test_a_resume_reads_the_accessibility_flags_again(
    fake_page: FakePage, svc: Services, semantics: MemorySemantics, network: Network
) -> None:
    _, prefs = await started(fake_page, svc)
    page = cast(ft.Page, fake_page)

    def event(state: ft.AppLifecycleState) -> ft.AppLifecycleStateChangeEvent:
        return ft.AppLifecycleStateChangeEvent(
            name="app_lifecycle_state_change", control=page, state=state
        )

    semantics.features["high_contrast"] = True
    await fake_page.on_app_lifecycle_state_change(event(ft.AppLifecycleState.HIDE))
    assert semantics.reads == 1 and not prefs.os_high_contrast
    await fake_page.on_app_lifecycle_state_change(event(ft.AppLifecycleState.RESUME))
    assert semantics.reads == 2 and prefs.os_high_contrast  # a snapshot (F13)


async def test_closing_the_page_stops_the_session_s_refresh(
    fake_page: FakePage, svc: Services, network: Network
) -> None:
    conference, _ = await started(fake_page, svc)
    assert fake_page.on_close == svc.close
    fake_page.on_close()  # a new session replaced this one (D-147)
    assert svc.closed.is_set()
    await finish_refresh(conference, network)
    assert conference.source == "bundled"  # nothing written to a closed session (F30)


# ------------------------------------------------------------------ theme and services


@pytest.mark.parametrize(
    ("theme", "mode"),
    [
        ("system", ft.ThemeMode.SYSTEM),
        ("light", ft.ThemeMode.LIGHT),
        ("dark", ft.ThemeMode.DARK),
    ],
)
def test_the_theme_mode_follows_the_appearance_setting(
    theme: str, mode: ft.ThemeMode, fake_page: FakePage
) -> None:
    apply_theme(cast(ft.Page, fake_page), Prefs(theme=theme))  # type: ignore[arg-type]
    assert fake_page.theme_mode == mode
    assert fake_page.theme is not None and fake_page.dark_theme is not None
    assert fake_page.theme.color_scheme != fake_page.dark_theme.color_scheme


async def test_read_accessibility_counts_either_motion_flag(
    semantics: MemorySemantics,
) -> None:
    prefs = Prefs()
    semantics.features["reduce_motion"] = True  # iOS reports this one (F13)
    await read_accessibility(semantics, prefs)
    assert prefs.reduce_motion


def test_services_are_built_for_the_active_year_in_the_data_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path))
    memory = ViewMemory()
    svc = Services.create(memory)
    assert svc.storage.directory == tmp_path.absolute()
    assert svc.storage.year == svc.year.conference.year
    assert svc.memory is memory
    assert not svc.closed.is_set()
    svc.close()
    assert svc.closed.is_set()
