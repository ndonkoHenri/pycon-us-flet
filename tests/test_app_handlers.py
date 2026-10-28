"""Tests for the page's handlers: brightness, resume and pause, failures and close.

``bootstrap()`` runs against ``tests/app_start.py``'s fakes (D-69).
"""

import asyncio
import json
import logging
import time
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import cast

import flet as ft
import httpx
import pytest

from pycon_us import app, clock
from pycon_us.accessibility import read_accessibility
from pycon_us.account import Account
from pycon_us.app import bootstrap, on_resume
from pycon_us.change_log import ChangeLog
from pycon_us.favorites import Favorites
from pycon_us.prefs import Prefs
from pycon_us.services import Services, api
from pycon_us.services.favorites_sync import FavoritesSync
from pycon_us.services.private_api import PrivateApi
from pycon_us.state import Conference
from tests import app_start
from tests.api_clients import BASE_URL, Recorder
from tests.app_start import Network, finish_refresh, started
from tests.fake_page import FakePage, bound
from tests.fakes import MemoryPrefs, MemorySemantics
from tests.mock_calls import Clock, state_at
from tools.mock_api.transport import mock_transport

year, shared, semantics, svc, fake_page, network = (
    app_start.year,
    app_start.shared,
    app_start.semantics,
    app_start.svc,
    app_start.fake_page,
    app_start.network,
)


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
    await on_resume(svc, conference, prefs, Account())
    assert prefs.screen_reader and prefs.announcements


class AskedSync(FavoritesSync):
    """A favourites sync that counts the pulls asked of it."""

    def __init__(self) -> None:
        """Start with no pull asked."""
        super().__init__()
        self.asked = 0

    def request(self) -> None:
        """Count the ask, then ask as the real sync does."""
        self.asked += 1
        super().request()


async def test_a_resume_asks_the_favourites_sync_for_a_pull(
    fake_page: FakePage, svc: Services, network: Network
) -> None:
    """A resume asks for one favourites pull, which also sends a failed edit (D-406)."""
    conference, prefs = await started(fake_page, svc)
    sync = AskedSync()
    await on_resume(replace(svc, favorites_sync=sync), conference, prefs, Account())
    assert sync.asked == 1


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
    with caplog.at_level(logging.WARNING, logger="pycon_us.accessibility"):
        await on_resume(svc, conference, prefs, Account())
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
    with caplog.at_level(logging.INFO, logger="pycon_us.accessibility"):
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
            cast(ft.Page, fake_page),
            svc,
            conference,
            prefs,
            Favorites(),
            ChangeLog(),
            Account(),
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


# ------------------------------------------------------------------ role flags


class Silent(Recorder):
    """A mock server that never answers: each request is kept and waits for ever."""

    def __init__(self) -> None:
        """Answer nothing, with nothing sent yet."""
        super().__init__(httpx.MockTransport(lambda _: httpx.Response(500)))

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Record the request, then wait until the test cancels it."""
        self.sent.append(request)
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


async def signed_in_start(
    fake_page: FakePage,
    svc: Services,
    shared: MemoryPrefs,
    transport: httpx.AsyncBaseTransport,
) -> tuple[Account, Services]:
    """Start with the seeded ``all`` account saved and a mock URL on ``transport``."""
    shared.values["pycon.account"] = json.dumps(
        {"email": "all@example.com", "nickname": "Robin", "features": {}}
    )
    shared.values["pycon.dev"] = json.dumps({"mock_api_url": BASE_URL})
    await svc.credentials.write("mock-key-all", "mock-secret-all")
    account = Account()
    svc = replace(svc, private_api=PrivateApi(transport, account.credentials))
    await bootstrap(
        cast(ft.Page, fake_page),
        svc,
        Conference(),
        Prefs(),
        Favorites(),
        ChangeLog(),
        account,
    )
    return account, svc


async def test_the_start_refreshes_the_flags_without_waiting_for_them(
    fake_page: FakePage, svc: Services, shared: MemoryPrefs, network: Network
) -> None:
    """A server that never answers still lets the gate open (DATA-35, D-54)."""
    silent = Silent()
    account, _ = await signed_in_start(fake_page, svc, shared, silent)
    assert fake_page.on_app_lifecycle_state_change is not None  # the start ended
    await asyncio.sleep(0.01)
    assert [r.url.path for r in silent.sent] == ["/2026/api/v1/user/check_features/"]
    assert account._refresh is not None and not account._refresh.done()
    account._refresh.cancel()


async def test_a_resume_refreshes_the_flags_and_a_revoked_key_asks_for_a_sign_in(
    fake_page: FakePage, svc: Services, shared: MemoryPrefs, network: Network
) -> None:
    """Each resume asks ``check_features``; a refused key expires the account (D-57)."""
    state = state_at(clock=Clock(time.time()))
    recorder = Recorder(mock_transport(state))
    account, svc = await signed_in_start(fake_page, svc, shared, recorder)
    assert account._refresh is not None
    await account._refresh
    assert account.door_check and not account.expired  # the server's flags
    state.faults.inject("revoked", until_cleared=True)
    resume = lifecycle(fake_page, ft.AppLifecycleState.RESUME)
    await fake_page.on_app_lifecycle_state_change(resume)
    await account._refresh
    assert account.expired and account.signed_in
    assert len(recorder.sent) == 2
