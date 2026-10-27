"""Tests for the start sequence and the boot gate (DATA-35, SHELL-01; D-69, D-147).

``bootstrap()`` runs against fakes: the in-memory SharedPreferences and
SemanticsService of ``tests/fakes.py``, a fake page, and ``api.fetch_feed`` replaced so
nothing reaches the network. The components themselves are checked on devices (the PR).
"""

import asyncio
import inspect
import json
import logging
from collections.abc import Awaitable, Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import flet as ft
import pytest
from flet.components.component import Renderer

from pycon_us import app, clock
from pycon_us.app import (
    NO_THEME_ANIMATION,
    apply_theme,
    bootstrap,
    on_resume,
)
from pycon_us.change_log import ChangeLog
from pycon_us.config import YearData, load_year
from pycon_us.core.change_batches import Batch
from pycon_us.favorites import Favorites
from pycon_us.layout import Layout
from pycon_us.memory import ViewMemory
from pycon_us.prefs import Prefs, read_accessibility
from pycon_us.services import Services, api, changes_file, errors
from pycon_us.services.storage import Storage
from pycon_us.state import Conference
from pycon_us.theme_hc import HC_DARK
from pycon_us.ui.time_gutter import GutterProbe
from tests.fakes import (
    FakePage,
    MemoryClipboard,
    MemoryHaptics,
    MemoryLauncher,
    MemoryPrefs,
    MemorySemantics,
    bound,
)
from tests.feeds import changed, recorded

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
        cast(ft.Page, fake_page), svc, conference, prefs, Favorites(), ChangeLog()
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
        cast(ft.Page, fake_page), svc, Conference(), prefs, favorites, ChangeLog()
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
        cast(ft.Page, fake_page), svc, Conference(), Prefs(), Favorites(), change_log
    )
    assert change_log.batches == (batch,)


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
    """A stored fake time, error details and feed URL apply before the gate opens."""
    monkeypatch.setattr(errors, "_details", False)
    shared.values["pycon.dev"] = json.dumps(
        {
            "unlocked": True,
            "fake_now": "2026-05-15T09:00:00-07:00",
            "feed_url": "http://127.0.0.1:8000/conference-2026.json",
        }
    )
    await started(fake_page, svc)
    # Each start runs the fake clock from its stored start again (D-187).
    start = datetime(2026, 5, 15, 16, 0, tzinfo=UTC)
    assert timedelta(0) <= clock.now() - start < timedelta(seconds=5)
    assert errors._details is True  # error details, as the unlock shows them
    await asyncio.sleep(0)  # the refresh's first step
    assert network.urls == ["http://127.0.0.1:8000/conference-2026.json"]


async def test_without_developer_options_the_app_runs_on_real_time_and_its_feed(
    fake_page: FakePage, svc: Services, network: Network, real_time: None
) -> None:
    """With no developer options, the clock is real and the year's feed is fetched."""
    clock.start_fake_clock(datetime(2030, 1, 1, tzinfo=UTC))  # left by a session before
    await started(fake_page, svc)
    assert abs(clock.now() - datetime.now(UTC)) < timedelta(seconds=5)
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
        cast(ft.Page, fake_page), svc, Conference(), prefs, favorites, ChangeLog()
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


# ------------------------------------------------------------------ page handlers


async def test_a_brightness_change_writes_the_store(
    fake_page: FakePage, svc: Services, network: Network
) -> None:
    """A platform brightness change event sets ``Prefs.os_dark`` from the page."""
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
    """A resume, not a hide, reads the accessibility flags again."""
    _, prefs = await started(fake_page, svc)
    page = cast(ft.Page, fake_page)

    def event(state: ft.AppLifecycleState) -> ft.AppLifecycleStateChangeEvent:
        return ft.AppLifecycleStateChangeEvent(
            name="app_lifecycle_state_change", control=page, state=state
        )

    # Changed in the OS settings while the app was in the background.
    semantics.features.update(high_contrast=True, reduce_motion=True)
    await fake_page.on_app_lifecycle_state_change(event(ft.AppLifecycleState.HIDE))
    assert semantics.reads == 1 and not prefs.os_high_contrast
    await fake_page.on_app_lifecycle_state_change(event(ft.AppLifecycleState.RESUME))
    assert semantics.reads == 2  # a snapshot (F13)
    assert prefs.os_high_contrast and prefs.reduce_motion


async def test_a_screen_reader_turned_on_away_from_the_app_is_seen_on_resume(
    fake_page: FakePage,
    svc: Services,
    semantics: MemorySemantics,
    network: Network,
) -> None:
    """A resume sees a screen reader and announcements turned on in the background.

    D-184: an Undo SnackBar then stays until it is used.
    """
    conference, prefs = await started(fake_page, svc)
    assert not prefs.screen_reader and not prefs.announcements
    semantics.features["accessible_navigation"] = True  # TalkBack or VoiceOver
    semantics.features["supports_announcements"] = True  # iOS (F13)
    await on_resume(svc, conference, prefs)
    assert prefs.screen_reader and prefs.announcements


async def test_a_failed_read_on_resume_keeps_the_flags_and_the_crossfade(
    fake_page: FakePage,
    svc: Services,
    semantics: MemorySemantics,
    network: Network,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failed read on resume keeps the last flags and the theme crossfade."""
    semantics.features.update(high_contrast=True, reduce_motion=True)
    conference, prefs = await started(fake_page, svc)
    semantics.error = TimeoutError()  # the Flutter side does not answer
    with caplog.at_level(logging.WARNING, logger="pycon_us.prefs"):
        await on_resume(svc, conference, prefs)
    assert semantics.reads == 2
    # The last good snapshot stands; nothing falls back to the defaults (F13).
    assert prefs.os_high_contrast and prefs.reduce_motion
    assert fake_page.theme_animation_style is None
    assert "Could not read the accessibility features" in caplog.text


async def test_a_change_of_reduced_motion_is_logged_once(
    semantics: MemorySemantics, caplog: pytest.LogCaptureFixture
) -> None:
    """Reduced motion turning on is logged once, not again on an unchanged read."""
    prefs = Prefs()
    semantics.features["disable_animations"] = True
    with caplog.at_level(logging.INFO, logger="pycon_us.prefs"):
        await read_accessibility(semantics, prefs)
        await read_accessibility(semantics, prefs)  # unchanged: resumes are many
    assert [r.getMessage() for r in caplog.records] == ["Reduced motion is on"]


def lifecycle(
    fake_page: FakePage, state: ft.AppLifecycleState
) -> ft.AppLifecycleStateChangeEvent:
    """Build the lifecycle event Flet sends ``fake_page`` for ``state``."""
    return ft.AppLifecycleStateChangeEvent(
        name="app_lifecycle_state_change", control=cast(ft.Page, fake_page), state=state
    )


@pytest.fixture
def frozen_clock() -> Iterator[datetime]:
    """Freeze the app's clock at ``STARTED_AT``, and unfreeze it after."""
    clock.set_test_now(STARTED_AT)
    yield STARTED_AT
    clock.set_test_now(None)


STARTED_AT = datetime(2026, 10, 12, 9, 30, tzinfo=UTC)


async def test_a_pause_stops_the_ticks_and_a_resume_starts_them_again(
    fake_page: FakePage, svc: Services, network: Network
) -> None:
    """Going to the background clears ``svc.foreground``; only a resume sets it."""
    await started(fake_page, svc)
    handler = fake_page.on_app_lifecycle_state_change
    for state in ("inactive", "hide", "pause"):  # going to the background (D-147)
        await handler(lifecycle(fake_page, ft.AppLifecycleState(state)))
    assert not svc.foreground.is_set()  # Services.run_every waits (D-40)
    for state in ("restart", "show"):
        await handler(lifecycle(fake_page, ft.AppLifecycleState(state)))
    assert not svc.foreground.is_set()
    await handler(lifecycle(fake_page, ft.AppLifecycleState.RESUME))
    assert svc.foreground.is_set()


async def test_inactive_and_resume_mark_a_trip_away_from_the_app(
    fake_page: FakePage, svc: Services, network: Network
) -> None:
    """``inactive`` alone (the share sheet's) leaves, and ``resume`` comes back (D-372)."""
    await started(fake_page, svc)
    handler = fake_page.on_app_lifecycle_state_change
    returns = svc.presence.returns
    back = asyncio.create_task(svc.presence.back_since(returns, leave_within=1))
    await handler(lifecycle(fake_page, ft.AppLifecycleState.INACTIVE))
    assert svc.foreground.is_set()  # the ticks go on: the app is still on screen
    await asyncio.sleep(0)
    assert not back.done()
    await handler(lifecycle(fake_page, ft.AppLifecycleState.RESUME))
    assert await back and svc.presence.returns == returns + 1


async def test_a_resume_refreshes_once_the_last_refresh_began_15_minutes_ago(
    fake_page: FakePage, svc: Services, network: Network, frozen_clock: datetime
) -> None:
    """A resume refreshes only once 15 minutes have passed since the last refresh."""
    conference, _ = await started(fake_page, svc)
    at_start = conference._task
    await finish_refresh(conference, network)
    resume = lifecycle(fake_page, ft.AppLifecycleState.RESUME)

    clock.set_test_now(frozen_clock + timedelta(minutes=14))
    await fake_page.on_app_lifecycle_state_change(resume)
    assert conference._task is at_start  # not due yet: no request

    clock.set_test_now(frozen_clock + timedelta(minutes=15))
    await fake_page.on_app_lifecycle_state_change(resume)
    assert conference._task is not at_start  # a new request
    await finish_refresh(conference, network)
    assert conference.source == "network"


async def test_an_offline_resume_keeps_the_data_and_says_offline(
    fake_page: FakePage, svc: Services, network: Network, frozen_clock: datetime
) -> None:
    """A resume whose refresh finds no network keeps the data and says offline."""
    conference, _ = await started(fake_page, svc)
    await finish_refresh(conference, network)
    shown = conference.data
    network.answer = api.NetworkError("airplane mode")

    clock.set_test_now(frozen_clock + timedelta(hours=2))
    await fake_page.on_app_lifecycle_state_change(
        lifecycle(fake_page, ft.AppLifecycleState.RESUME)
    )
    await finish_refresh(conference, network)

    assert conference.data is shown and conference.source == "network"
    assert conference.problem == "offline"
    assert conference.status(svc.year.conference) == "offline"


async def test_a_page_handler_that_fails_unexpectedly_reports_instead_of_raising(
    fake_page: FakePage,
    svc: Services,
    semantics: MemorySemantics,
    network: Network,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A bug in the lifecycle handler is logged and shown in a SnackBar, not raised."""
    await started(fake_page, svc)
    page = cast(ft.Page, fake_page)
    semantics.error = ValueError("not a service error")  # a bug, not SERVICE_ERRORS
    with bound(fake_page):  # Flet binds the page while a handler runs
        await fake_page.on_app_lifecycle_state_change(
            ft.AppLifecycleStateChangeEvent(
                name="app_lifecycle_state_change",
                control=page,
                state=ft.AppLifecycleState.RESUME,
            )
        )
    # report_errors (D-71): a raise here would end the session (F4).
    assert "Unexpected error in pycon_us.app.bootstrap.<locals>.on_lifecycle" in (
        caplog.text
    )
    assert [type(dialog) for dialog in fake_page.dialogs] == [ft.SnackBar]


async def test_closing_the_page_stops_the_session_s_refresh(
    fake_page: FakePage, svc: Services, network: Network
) -> None:
    """Closing the page sets ``svc.closed``, so its refresh writes nothing (F30)."""
    conference, _ = await started(fake_page, svc)
    assert fake_page.on_close == svc.close
    fake_page.on_close()  # a new session replaced this one (D-147)
    assert svc.closed.is_set()
    await finish_refresh(conference, network)
    assert conference.source == "bundled"  # nothing written to a closed session (F30)


async def test_a_session_closed_during_the_start_stops_there_without_an_error(
    fake_page: FakePage,
    svc: Services,
    network: Network,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A session closed mid-start stops quietly: no gate, refresh or error log."""
    reading, release = asyncio.Event(), asyncio.Event()

    async def held_read(*_: object) -> None:
        reading.set()
        await release.wait()
        # What a store write from a replaced session raises (F30).
        raise RuntimeError("An attempt to fetch destroyed session.")

    monkeypatch.setattr(app, "read_accessibility", held_read)
    conference, prefs = Conference(), Prefs()
    start = asyncio.create_task(
        bootstrap(
            cast(ft.Page, fake_page), svc, conference, prefs, Favorites(), ChangeLog()
        )
    )
    await reading.wait()
    fake_page.on_close()  # replaced while the start awaits (F26, F29; D-147)
    release.set()
    with caplog.at_level(logging.INFO):
        await start
    assert not prefs.loaded
    assert conference._task is None  # no refresh into a destroyed session
    assert fake_page.on_app_lifecycle_state_change is None
    assert "Start failed" not in caplog.text
    assert "closed during the start" in caplog.text


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
    """Each Appearance setting gives its theme mode, over two distinct schemes."""
    apply_theme(cast(ft.Page, fake_page), Prefs(theme=theme))  # type: ignore[arg-type]
    assert fake_page.theme_mode == mode
    assert fake_page.theme is not None and fake_page.dark_theme is not None
    assert fake_page.theme.color_scheme != fake_page.dark_theme.color_scheme


async def test_read_accessibility_counts_either_motion_flag(
    semantics: MemorySemantics,
) -> None:
    """The ``reduce_motion`` flag alone, which iOS reports, turns reduced motion on."""
    prefs = Prefs()
    semantics.features["reduce_motion"] = True  # iOS reports this one (F13)
    await read_accessibility(semantics, prefs)
    assert prefs.reduce_motion


def test_services_are_built_for_the_active_year_in_the_data_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``Services.create`` uses the active year, the data directory and the memory.

    The new services start open, and ``close()`` closes them.
    """
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path))
    memory = ViewMemory()
    svc = Services.create(memory)
    assert svc.storage.directory == tmp_path.absolute()
    assert svc.storage.year == svc.year.conference.year
    assert svc.memory is memory
    assert not svc.closed.is_set()
    svc.close()
    assert svc.closed.is_set()


@pytest.mark.parametrize(
    ("loaded", "measured", "open_"),
    [
        (False, False, False),
        (True, False, False),
        (False, True, False),
        (True, True, True),
    ],
)
def test_the_boot_gate_waits_for_the_settings_and_the_slots_layout(
    loaded: bool,
    measured: bool,
    open_: bool,
    fake_page: FakePage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The boot view stays until the settings load and the slots' layout is measured.

    D-216: the first screen comes only once the slots' layout is known.
    """
    prefs = Prefs(loaded=loaded, time_measured=measured)
    monkeypatch.setattr(ft, "use_memo", lambda *_, **__: object())
    monkeypatch.setattr(ft, "use_state", lambda initial: (prefs, lambda _: None))
    monkeypatch.setattr(ft, "use_effect", lambda *_, **__: None)
    banners: list[bool] = []
    monkeypatch.setattr(
        app, "use_reminder_banner", lambda *_, ready: banners.append(ready)
    )
    # The Review SnackBar has its own tests (tests/test_changes_review.py).
    monkeypatch.setattr(app, "use_review_snack_bar", lambda *_: None)
    with Renderer().with_context(), bound(fake_page):
        shown = inspect.unwrap(app.App)(ViewMemory())
    assert banners == [open_]  # the slot is there before the gate, shown after it
    booting = (
        isinstance(shown, list)
        and len(shown) == 1
        and isinstance(shown[0], ft.Component)
        and shown[0].fn is inspect.unwrap(app.BootView)
    )
    assert booting is not open_
    if open_:  # the providers end in the Router
        assert isinstance(shown, ft.Component)
        assert shown.fn.__name__ == "Router"


def test_app_seeds_the_layout_from_the_page_width_and_follows_its_resizes(
    fake_page: FakePage, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``App`` gives the Router a ``Layout`` seeded from ``page.width`` that follows resizes.

    D-277: a first screen opened in landscape shows the rail, and a rotation flips it.
    """
    fake_page.width = 900.0
    prefs = Prefs(loaded=True, time_measured=True)
    setups: list[Callable[[], object]] = []
    provided: list[Layout] = []

    def layout_ctx(value: Layout, body: Callable[[], object]) -> object:
        """Record the ``Layout`` handed to the provider, then render its body."""
        provided.append(value)
        return body()

    monkeypatch.setattr(ft, "use_memo", lambda fn, *_, **__: fn())
    monkeypatch.setattr(ft, "use_state", lambda initial: (prefs, lambda _: None))
    monkeypatch.setattr(ft, "use_effect", lambda setup, *_, **__: setups.append(setup))
    monkeypatch.setattr(app, "LayoutCtx", layout_ctx)
    monkeypatch.setattr(app, "apply_theme", lambda *_: None)
    # The reminder Banner has its own tests; here it would read stand-in stores.
    monkeypatch.setattr(app, "use_reminder_banner", lambda *_, **__: None)
    monkeypatch.setattr(app, "use_review_snack_bar", lambda *_: None)
    monkeypatch.setattr(app, "Services", SimpleNamespace(create=lambda _: object()))
    with Renderer().with_context(), bound(fake_page):
        shown = inspect.unwrap(app.App)(ViewMemory())
        assert isinstance(shown, ft.Component) and shown.fn.__name__ == "Router"
        (layout,) = provided  # LayoutCtx is in the chain to the Router
        assert layout.wide is True  # seeded before any effect runs
        for setup in setups:
            if not inspect.iscoroutinefunction(setup):
                setup()
        assert fake_page.on_resize is not None
        fake_page.on_resize(SimpleNamespace(width=375.0))
        assert layout.wide is False


async def test_the_boot_view_measures_the_slots_layout_before_the_first_screen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The boot view holds the layout probe and stops waiting for it after a delay.

    D-216: a Schedule opened with the gutter and switched later lost its jump.
    """
    prefs, setups = Prefs(), []
    monkeypatch.setattr(app, "use_prefs", lambda: prefs)
    monkeypatch.setattr(ft, "use_state", lambda initial: (initial, lambda _: None))
    monkeypatch.setattr(ft, "use_effect", lambda setup, *_, **__: setups.append(setup))
    monkeypatch.setattr(app, "RING_DELAY", 0.01)
    with Renderer().with_context():  # what calling a component needs, as in a render
        view = inspect.unwrap(app.BootView)()
    assert isinstance(view, ft.View)
    ring, probe = view.controls
    assert isinstance(ring, ft.ProgressRing)
    assert isinstance(probe, ft.Component)
    assert probe.fn is inspect.unwrap(GutterProbe)
    assert view.spacing == 0  # the 0 dp probe leaves the ring centred
    # Should the probe never answer, the gate stops waiting with the ring.
    (setup,) = setups
    setup()
    assert prefs.time_measured is False
    await asyncio.sleep(0.05)
    assert prefs.time_measured is True
    assert prefs.time_above is False  # the gutter, until a screen's probe answers
