"""Tests for the start sequence and the boot gate (DATA-35, SHELL-01; D-69, D-147).

``bootstrap()`` runs against ``tests/app_start.py``'s fakes. The page's handlers are
``test_app_handlers.py``'s, the theme and services ``test_app_theme.py``'s. The
components themselves are checked on devices (the PR).
"""

import asyncio
import json
import logging
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import cast

import flet as ft
import pytest
from flet_notifications import Notifications

from pycon_us import app, clock
from pycon_us.account import Account
from pycon_us.app import NO_THEME_ANIMATION, bootstrap
from pycon_us.change_log import ChangeLog
from pycon_us.core.change_batches import Batch
from pycon_us.favorites import Favorites
from pycon_us.prefs import Prefs
from pycon_us.services import Services, api, changes_file, errors
from pycon_us.services.reminders import Scheduler
from pycon_us.state import Conference
from pycon_us.theme_hc import HC_DARK
from tests import app_start
from tests.app_start import Network, finish_refresh, started
from tests.fake_page import FakePage
from tests.fakes import MemoryNotifications, MemoryPrefs, MemorySemantics
from tests.feeds import changed, recorded

year, shared, semantics, svc, fake_page, network = (
    app_start.year,
    app_start.shared,
    app_start.semantics,
    app_start.svc,
    app_start.fake_page,
    app_start.network,
)


# ------------------------------------------------------------------ the gate


async def test_the_gate_opens_on_the_bundled_feed_without_waiting_for_the_network(
    fake_page: FakePage, svc: Services, network: Network
) -> None:
    """The gate opens on the bundled feed while a quiet refresh runs behind it."""
    conference, prefs = await started(fake_page, svc)
    # The network has not answered, yet the first screen has data (D-38).
    assert prefs.loaded
    assert conference.source == "bundled"
    assert conference.data is not None
    await asyncio.sleep(0)  # the refresh task's first step
    assert conference.refreshing  # in the background, not awaited
    # Automatic, so quiet: the strip keeps what it says about the bundled data (D-181).
    assert conference.status(svc.year.conference) != "refreshing"


async def test_the_stored_theme_is_on_the_page_before_the_gate_opens(
    fake_page: FakePage, svc: Services, shared: MemoryPrefs, network: Network
) -> None:
    """The stored theme is set, with no crossfade, before the gate opens on data."""
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
    await bootstrap(
        cast(ft.Page, fake_page),
        svc,
        conference,
        prefs,
        Favorites(),
        ChangeLog(),
        Account(),
    )
    # No theme flash and no empty first screen (SHELL-01): the stored theme is set before
    # the gate opens, still with no crossfade, and later changes crossfade again.
    assert seen_at_open == [NO_THEME_ANIMATION, ft.ThemeMode.DARK, "bundled"]
    assert fake_page.theme_animation_style is None
    assert fake_page.theme is not None and fake_page.dark_theme is not None


async def test_the_os_brightness_and_accessibility_flags_are_read_at_start(
    svc: Services, semantics: MemorySemantics, network: Network
) -> None:
    """The start reads the OS's dark mode, high contrast and reduced motion.

    The high-contrast schemes are on the page before the gate opens (D-161, D-23).
    """
    semantics.features.update(high_contrast=True, disable_animations=True)
    fake_page = FakePage(ft.Brightness.DARK)
    _, prefs = await started(fake_page, svc)
    assert (prefs.os_dark, prefs.os_high_contrast, prefs.reduce_motion) == (
        True,
        True,
        True,
    )
    assert prefs.dark  # Appearance System follows the OS
    assert fake_page.dark_theme is not None
    assert fake_page.dark_theme.color_scheme == HC_DARK


async def test_the_year_s_favourites_are_loaded_before_the_gate_opens(
    fake_page: FakePage, svc: Services, shared: MemoryPrefs, network: Network
) -> None:
    """The year's stored favourites are in the store when the gate opens (D-48)."""
    shared.values["pycon.2026.favorites"] = ["42", "poster-detail-7"]
    favorites, prefs = Favorites(), Prefs()
    ids_at_open: list[frozenset[str]] = []

    def listener(_sender: object, name: str | None) -> None:
        if name == "loaded":
            ids_at_open.append(favorites.ids)

    assert isinstance(prefs, ft.Observable)
    prefs.subscribe(listener)
    await bootstrap(
        cast(ft.Page, fake_page),
        svc,
        Conference(),
        prefs,
        favorites,
        ChangeLog(),
        Account(),
    )
    # No star fills in after the first screen (D-48).
    assert ids_at_open == [frozenset({"42", "poster-detail-7"})]


async def test_the_year_s_change_log_is_loaded_at_start(
    fake_page: FakePage, svc: Services, network: Network
) -> None:
    """The start reads the batches the last session recorded, before any refresh."""
    batch = Batch(clock.now(), ())
    await changes_file.write_batches(svc.storage, [batch])
    change_log = ChangeLog()
    await bootstrap(
        cast(ft.Page, fake_page),
        svc,
        Conference(),
        Prefs(),
        Favorites(),
        change_log,
        Account(),
    )
    assert change_log.batches == (batch,)


async def test_the_saved_account_is_restored_before_the_gate_opens(
    fake_page: FakePage, svc: Services, shared: MemoryPrefs, network: Network
) -> None:
    """The start signs the saved account in again from local reads, with no mock URL.

    STORE-03, SHELL-15; kept with no URL set, which only hides it (D-398).
    """
    shared.values["pycon.account"] = json.dumps(
        {"email": "all@example.com", "nickname": "Robin", "features": {}}
    )
    await svc.credentials.write("mock-key-all", "mock-secret-all")
    account, prefs = Account(), Prefs()
    restored_at_open: list[bool] = []

    def listener(_sender: object, name: str | None) -> None:
        if name == "loaded":
            restored_at_open.append(account.signed_in)

    assert isinstance(prefs, ft.Observable)
    prefs.subscribe(listener)
    await bootstrap(
        cast(ft.Page, fake_page),
        svc,
        Conference(),
        prefs,
        Favorites(),
        ChangeLog(),
        account,
    )
    assert restored_at_open == [True]
    assert svc.api is None and account.credentials() == (
        "mock-key-all",
        "mock-secret-all",
    )


@pytest.fixture
def real_time() -> Iterator[None]:
    """Return the process to real time after a test that starts the fake clock."""
    yield
    clock.start_fake_clock(None)


async def test_the_stored_developer_options_take_effect_before_the_gate_opens(
    fake_page: FakePage,
    svc: Services,
    shared: MemoryPrefs,
    network: Network,
    real_time: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stored fake time, error details, feed URL and mock API URL apply before the gate.

    The mock API URL builds the private-API client on it (D-51).
    """
    monkeypatch.setattr(errors, "_details", False)
    shared.values["pycon.dev"] = json.dumps(
        {
            "unlocked": True,
            "fake_now": "2026-05-15T09:00:00-07:00",
            "feed_url": "http://127.0.0.1:8000/conference-2026.json",
            "mock_api_url": "http://10.0.2.2:8000",
        }
    )
    await started(fake_page, svc)
    assert svc.private_api.base_url == "http://10.0.2.2:8000"
    assert svc.api is not None
    # Each start runs the fake clock from its stored start again (D-187).
    start = datetime(2026, 5, 15, 16, 0, tzinfo=UTC)
    assert timedelta(0) <= clock.now() - start < timedelta(seconds=5)
    assert errors._details is True  # error details, as the unlock shows them
    await asyncio.sleep(0)  # the refresh's first step
    assert network.urls == ["http://127.0.0.1:8000/conference-2026.json"]


async def test_without_developer_options_the_app_runs_on_real_time_and_its_feed(
    fake_page: FakePage, svc: Services, network: Network, real_time: None
) -> None:
    """With no developer options: real time, the year's feed and no private-API client."""
    clock.start_fake_clock(datetime(2030, 1, 1, tzinfo=UTC))  # left by a session before
    await started(fake_page, svc)
    assert abs(clock.now() - datetime.now(UTC)) < timedelta(seconds=5)
    assert svc.api is None  # no code path can reach the private API (D-51)
    await asyncio.sleep(0)
    assert network.urls == ["https://us.pycon.org/2026/schedule/conference.json"]


@pytest.mark.parametrize("flag", ["reduce_motion", "disable_animations"])
async def test_under_reduced_motion_theme_changes_still_crossfade(
    fake_page: FakePage,
    svc: Services,
    semantics: MemorySemantics,
    network: Network,
    flag: str,
) -> None:
    """Under either reduced-motion flag, theme changes still crossfade (D-173)."""
    semantics.features[flag] = True  # iOS Reduce Motion, Android's Remove animations
    _, prefs = await started(fake_page, svc)
    assert prefs.reduce_motion
    # A crossfade changes colour, not position; a hard swap left Material's text tween
    # dark on dark for a few frames on iOS (D-173).
    assert fake_page.theme_animation_style is None


async def test_the_cache_is_shown_before_the_snapshot(
    fake_page: FakePage, svc: Services, network: Network
) -> None:
    """A cached feed is what the start shows, ahead of the bundled snapshot."""
    await svc.storage.write_feed(recorded(2026))
    conference, _ = await started(fake_page, svc)
    assert conference.source == "cache"


async def test_an_offline_start_keeps_the_snapshot_and_says_offline(
    fake_page: FakePage, svc: Services, network: Network
) -> None:
    """A start whose refresh finds no network keeps the snapshot and says offline."""
    network.answer = api.NetworkError("no route to host")
    conference, _ = await started(fake_page, svc)
    await finish_refresh(conference, network)
    assert conference.source == "bundled"
    assert conference.problem == "offline"


async def test_an_online_start_replaces_the_snapshot_with_the_network_feed(
    fake_page: FakePage, svc: Services, network: Network
) -> None:
    """A changed network feed replaces the snapshot as version 2 and is cached."""
    network.answer = changed(2026, lambda feed: feed["schedule"].pop())
    conference, _ = await started(fake_page, svc)
    await finish_refresh(conference, network)
    assert conference.source == "network"
    assert conference.version == 2
    assert svc.storage.feed_path.exists()


async def test_an_online_start_that_finds_the_snapshot_s_feed_keeps_its_version(
    fake_page: FakePage, svc: Services, network: Network
) -> None:
    """A network feed equal to the snapshot is cached but keeps version 1.

    D-224: the same bytes publish nothing, so no screen re-renders its lists.
    """
    network.answer = svc.year.read_snapshot().raw
    conference, _ = await started(fake_page, svc)
    await finish_refresh(conference, network)
    assert conference.source == "network"
    assert conference.version == 1
    assert svc.storage.feed_path.read_bytes() == network.answer  # the next start's


async def test_an_unexpected_start_error_is_logged_and_the_gate_still_opens(
    fake_page: FakePage,
    svc: Services,
    network: Network,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A bug while the start loads is logged, and the gate opens with no data."""

    async def broken(*_: object) -> None:
        raise RuntimeError("a bug")

    monkeypatch.setattr(Conference, "load_local", broken)
    with caplog.at_level(logging.ERROR):
        conference, prefs = await started(fake_page, svc)
    assert prefs.loaded  # never stuck on the boot view
    assert conference.data is None
    assert "Start failed" in caplog.text
    assert "RuntimeError: a bug" in caplog.text


class LaunchedByTap(MemoryNotifications):
    """E3 started by a tap on a reminder: it hands the tap over, then answers (F246)."""

    def __init__(self, route: str) -> None:
        """Hand over ``route``'s tap before the first answer, to ``scheduler``."""
        super().__init__()
        self.route = route
        self.scheduler: Scheduler | None = None

    async def are_notifications_enabled(self) -> bool:
        """Deliver the launch tap first, as E3's start does, then answer."""
        assert self.scheduler is not None
        self.scheduler.open_tapped(self.route)
        return await super().are_notifications_enabled()


async def test_the_gate_waits_for_e3_so_a_launch_tap_is_held_for_start(
    fake_page: FakePage, svc: Services, network: Network
) -> None:
    """The start awaits E3's first answer, by which the launch tap is in (D-396).

    So ``Start`` finds it when the gate opens, and the first screen is the session.
    """
    os = LaunchedByTap("/my-schedule/session/142")
    scheduler = Scheduler(cast(Notifications, os))
    os.scheduler = scheduler
    _, prefs = await started(fake_page, replace(svc, reminders=scheduler))
    assert prefs.loaded
    assert scheduler.tapped == "/my-schedule/session/142"
    assert scheduler.enabled


async def test_an_e3_that_never_answers_delays_the_gate_by_launch_wait_at_most(
    fake_page: FakePage,
    svc: Services,
    network: Network,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """E3 stuck in its start holds the gate ``LAUNCH_WAIT`` at most, then reads off."""
    os = MemoryNotifications()
    os.initialized = asyncio.Event()  # never set
    monkeypatch.setattr(app, "LAUNCH_WAIT", 0.01)
    scheduler = Scheduler(cast(Notifications, os))
    _, prefs = await started(fake_page, replace(svc, reminders=scheduler))
    assert prefs.loaded
    assert not scheduler.enabled


async def test_a_start_that_breaks_before_the_favourites_never_writes_over_them(
    fake_page: FakePage,
    svc: Services,
    shared: MemoryPrefs,
    network: Network,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A start that fails before the favourites load leaves the stored ones as they are.

    The gate opens, but the favourites stay unloaded, so a star tap reports that it
    could not save and the stored list is unchanged.
    """

    async def broken(*_: object) -> None:
        raise RuntimeError("a bug")

    shared.values["pycon.2026.favorites"] = ["17", "42"]
    monkeypatch.setattr(Prefs, "load", broken)
    favorites, prefs = Favorites(), Prefs()
    await bootstrap(
        cast(ft.Page, fake_page),
        svc,
        Conference(),
        prefs,
        favorites,
        ChangeLog(),
        Account(),
    )
    assert prefs.loaded  # the gate opens (D-161)
    assert not favorites.loaded  # so My schedule says it can't open
    change = await favorites.toggle(svc.storage, "99")
    assert not change.saved  # "Couldn't save your change"
    assert shared.values["pycon.2026.favorites"] == ["17", "42"]


async def test_unreadable_accessibility_flags_keep_their_defaults(
    fake_page: FakePage,
    svc: Services,
    semantics: MemorySemantics,
    network: Network,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unreadable accessibility flags are logged and stay off."""
    semantics.error = TimeoutError()
    with caplog.at_level(logging.WARNING):
        _, prefs = await started(fake_page, svc)
    assert prefs.loaded
    assert (prefs.os_high_contrast, prefs.reduce_motion) == (False, False)
    assert "accessibility features" in caplog.text
