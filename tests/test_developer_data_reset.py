"""Tests for the Developer screen's Data section: share the log, welcome, reset (#107).

The fixtures and lookups are ``tests/data_section.py``'s. The share sheet and a reset on
a device are checked on devices (the PR).
"""

import asyncio
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import flet as ft
import pytest

from pycon_us import clock
from pycon_us.account import Account
from pycon_us.core.change_batches import Batch
from pycon_us.favorites import Favorites
from pycon_us.memory import ViewMemory
from pycon_us.prefs import Prefs
from pycon_us.reminder_settings import ReminderSettings
from pycon_us.screens.developer_data import (
    RESET_INCOMPLETE,
    WELCOME_NOT_SAVED,
    reset_app,
)
from pycon_us.screens.developer_ui import (
    reset_losses,
)
from pycon_us.services import Services, api, changes_file, errors
from pycon_us.services.storage import ACCOUNT
from pycon_us.staff import Staff
from pycon_us.state import Conference
from pycon_us.ui.share import DIAGNOSTICS_SHARED, LOG_SHARED, WITH_LOG, WITHOUT_LOG
from tests import data_section
from tests.data_section import (
    DEV_FEED,
    Rendered,
    outcome,
    press,
    row,
    said,
    subtitle,
    tap,
)
from tests.fake_page import FakePage
from tests.fakes import MemoryPaths, MemoryPrefs, MemoryShare
from tests.feeds import recorded

(
    real_time,
    offline,
    page,
    svc,
    stored,
    prefs,
    conference,
    favorites,
    account,
    staff,
    packaged,
    rendered,
    minutes,
    render,
) = (
    data_section.real_time,
    data_section.offline,
    data_section.page,
    data_section.svc,
    data_section.stored,
    data_section.prefs,
    data_section.conference,
    data_section.favorites,
    data_section.account,
    data_section.staff,
    data_section.packaged,
    data_section.rendered,
    data_section.minutes,
    data_section.render,
)


# ------------------------------------------------------------------ Share log
# What the share sends and says in every case is test_share_report.py's.


async def test_share_log_shares_the_console_log_with_the_diagnostics(
    render: Callable[[], ft.Column], svc: Services, tmp_path: Path
) -> None:
    """In a packaged build, Share log says so and shares console.log with the diagnostics.

    The diagnostics are the file's text, and the row says beforehand what a tap sends.
    """
    log = tmp_path / "console.log"
    log.write_text("12:00:00.000 INFO pycon_us.app: started\n")
    cast(MemoryPaths, svc.paths).console_log = str(log)
    assert subtitle(render(), "developer.share_log") == WITH_LOG
    await tap(render, "developer.share_log")
    share = cast(MemoryShare, svc.share)
    [files] = share.shared
    assert [file.path for file in files] == [str(log)]
    assert share.file_options[0]["text"].startswith("App: ")
    assert outcome(render()) == LOG_SHARED[0]
    assert row(render(), "developer.share_log").disabled is False  # usable again


async def test_outside_a_packaged_build_share_log_sends_the_diagnostics_alone(
    render: Callable[[], ft.Column],
    svc: Services,
    packaged: Callable[[bool], None],
) -> None:
    """Outside a packaged build, Share log stays on and shares the diagnostics alone.

    Its second line says beforehand why no log goes; the diagnostics go as a text.
    """
    packaged(False)
    assert row(render(), "developer.share_log").disabled is False
    assert subtitle(render(), "developer.share_log") == WITHOUT_LOG
    await tap(render, "developer.share_log")
    share = cast(MemoryShare, svc.share)
    assert share.shared == []
    [(text, _)] = share.texts
    assert text.startswith("App: ")
    assert outcome(render()) == DIAGNOSTICS_SHARED[0]


# ------------------------------------------------------------ Show welcome again


async def test_show_welcome_again_clears_onboarded_and_opens_welcome(
    render: Callable[[], ft.Column],
    stored: dict[str, Any],
    prefs: Prefs,
    favorites: Favorites,
    page: FakePage,
) -> None:
    """Show welcome again stores onboarded as false and opens Welcome, keeping the rest.

    The settings and saved sessions stay (SHELL-02); Welcome's Get started saves
    onboarded again, so a relaunch after it opens Now (D-287).
    """
    stored["pycon.onboarded"] = True
    prefs.onboarded = True
    prefs.theme = "dark"
    await tap(render, "developer.show_welcome")
    assert stored["pycon.onboarded"] is False
    assert prefs.onboarded is False
    assert page.navigated == ["/welcome"]
    assert (prefs.theme, favorites.ids) == ("dark", frozenset({"1", "2", "3"}))
    assert outcome(render()) is None
    assert said(page) == []


async def test_show_welcome_again_says_in_place_when_it_cannot_save(
    render: Callable[[], ft.Column], svc: Services, page: FakePage
) -> None:
    """A failed save stays on Developer and says so under the rows (D-120, D-210)."""
    cast(MemoryPrefs, svc.storage.prefs).fail_writes = True
    await tap(render, "developer.show_welcome")
    assert page.navigated == []
    assert outcome(render()) == WELCOME_NOT_SAVED[0]


# ------------------------------------------------------------------ Reset app


def test_reset_lists_exactly_what_is_lost() -> None:
    """Reset lists the settings, saved sessions, cache, change log and Developer options.

    With nothing saved it says none, and outside a packaged build Developer does not
    lock again (D-73).
    """
    assert reset_losses(3, packaged=True) == (
        "Your settings: Appearance and the schedule's filters",
        "Your saved sessions in My schedule: 3",
        "The cached schedule: the app shows the bundled one until it refreshes",
        "Schedule changes: what recent refreshes changed",
        (
            "Developer options: the fake clock, the feed URL and the mock API URL, "
            "and Developer locks again"
        ),
    )
    losses = reset_losses(0, packaged=False)  # Developer is always there (D-73)
    assert losses[1] == "Your saved sessions in My schedule: none"
    assert losses[4] == (
        "Developer options: the fake clock, the feed URL and the mock API URL"
    )


async def test_reset_app_asks_first_and_its_dialog_lists_the_losses(
    render: Callable[[], ft.Column],
    rendered: Rendered,
    stored: dict[str, Any],
) -> None:
    """Reset app first asks in a dialog listing the losses; Cancel deletes nothing."""
    stored["pycon.theme"] = "dark"
    await tap(render, "developer.reset_app")
    render()
    dialog = rendered.dialog
    assert dialog is not None and dialog.modal is True and dialog.scrollable is True
    assert dialog.title == ft.Text("Reset the app?")
    # Its icon in error, as the row that opened it: one destructive accent.
    assert dialog.icon == ft.Icon(ft.Icons.RESTART_ALT, color=ft.Colors.ERROR)
    lines = [
        str(cast(ft.Text, cast(ft.Row, line).controls[1]).value)
        for line in cast(ft.Column, dialog.content).controls[1:]
    ]
    assert lines == list(reset_losses(3, packaged=True))
    await press(dialog, "developer.reset_app.cancel")
    render()
    assert rendered.dialog is None
    assert stored["pycon.theme"] == "dark"  # nothing deleted


async def test_reset_app_clears_storage_and_every_store_as_after_a_fresh_install(
    render: Callable[[], ft.Column],
    rendered: Rendered,
    svc: Services,
    stored: dict[str, Any],
    prefs: Prefs,
    conference: Conference,
    favorites: Favorites,
    account: Account,
    page: FakePage,
    offline: list[str],
) -> None:
    """Confirming the reset leaves storage and every store as after a fresh install.

    The session has been used: settings (reminders too), favourites of two years, the
    Developer options, a cache, a change log, a fake clock, a feed URL, remembered
    places and a signed-in mock account, whose key and secret go too (#684). Only another app's key is left; the device facts stay and Developer locks
    again. Then, as at a start, a quiet refresh of the year's feed runs, the app goes to
    Welcome, as a first start does (D-287), and says "App reset".
    """
    stored.update(
        {
            "pycon.theme": "dark",
            "pycon.onboarded": True,
            "pycon.excluded_tracks": [],
            "pycon.2026.favorites": ["1", "2", "3"],
            "pycon.2025.favorites": ["9"],
            "pycon.dev": '{"unlocked": true}',
            "flutter.not_ours": "kept",
        }
    )
    await prefs.save(
        svc.storage,
        theme="dark",
        onboarded=True,
        excluded_tracks=(),
        reminders=ReminderSettings(session_lead=10, keynote=False, primer="accepted"),
    )
    prefs.os_dark = True
    clock.start_fake_clock(datetime(2026, 5, 15, 16, tzinfo=UTC))
    errors.show_details(True)
    await conference.set_feed_url(DEV_FEED, svc.storage)
    # After the URL change, which deletes both files once the feed has loaded (D-255).
    await svc.storage.write_feed(recorded(2026))
    await changes_file.write_batches(svc.storage, [Batch(clock.now(), ())])
    svc.memory.last_location = "/more/developer"
    svc.memory.schedule_offsets[date(2026, 5, 15)] = 1200.0
    svc.memory.jumped_on = date(2026, 5, 15)
    await svc.credentials.write("mock-key-all", "mock-secret-all")
    profile = {"email": "all@example.com", "nickname": "Robin", "features": {}}
    await svc.storage.set(ACCOUNT, profile)
    await account.restore(svc.storage, svc.credentials)
    assert account.signed_in

    await tap(render, "developer.reset_app")
    render()
    await press(rendered.dialog, "developer.reset_app.confirm")

    # On the device: nothing of the app's is left.
    assert stored == {"flutter.not_ours": "kept"}
    assert not svc.storage.feed_path.exists()
    assert not changes_file.changes_path(svc.storage).exists()
    # In memory, without a restart.
    assert abs(clock.now() - datetime.now(UTC)) < timedelta(seconds=5)
    assert errors._details is False
    assert (prefs.theme, prefs.onboarded, prefs.excluded_tracks, prefs.dev) == (
        "system",
        False,
        ("Open Space",),
        {},
    )
    assert prefs.reminders == ReminderSettings()  # off, the primer unasked (D-275)
    assert prefs.developer is False  # a packaged build: locked again
    assert prefs.os_dark is True and prefs.loaded is True  # device facts stay
    assert favorites.ids == frozenset()
    assert not account.signed_in and account.credentials() == (None, None)
    assert await svc.credentials.read() == (None, None)
    assert svc.memory == ViewMemory()
    assert conference.source == "bundled"
    assert conference._feed_url is None
    # Then, as at a start: a quiet refresh of the year's feed, and the index route.
    await asyncio.sleep(0)
    assert offline == [svc.year.conference.feed_url]
    assert page.navigated == ["/welcome"]
    assert said(page) == ["App reset"]


async def test_reset_app_deletes_the_change_log_when_no_feed_url_was_set(
    svc: Services,
    prefs: Prefs,
    conference: Conference,
    favorites: Favorites,
) -> None:
    """Reset app deletes the change log when no feed URL was set (D-255).

    ``Conference.reset()`` deletes the log only through a feed URL change, so here only
    ``reset_app()``'s own deletion can remove it.
    """
    await changes_file.write_batches(svc.storage, [Batch(clock.now(), ())])
    assert (
        await reset_app(svc, conference, prefs, favorites, Account(), Staff()) is True
    )
    assert not changes_file.changes_path(svc.storage).exists()


async def test_a_reset_that_cannot_delete_everything_says_so(
    render: Callable[[], ft.Column],
    rendered: Rendered,
    svc: Services,
    stored: dict[str, Any],
    favorites: Favorites,
    page: FakePage,
) -> None:
    """A reset that cannot delete everything still resets the session and says so.

    It goes to Welcome, as a full reset does (D-120, D-287).
    """
    stored["pycon.2026.favorites"] = ["1"]
    cast(MemoryPrefs, svc.storage.prefs).fail_removes = True
    await tap(render, "developer.reset_app")
    render()
    await press(rendered.dialog, "developer.reset_app.confirm")
    assert favorites.ids == frozenset()  # the session is reset all the same (D-120)
    assert page.navigated == ["/welcome"]
    assert said(page) == [RESET_INCOMPLETE]


async def test_reset_cancels_a_refresh_from_a_developer_feed_before_it_caches_it(
    svc: Services,
    prefs: Prefs,
    conference: Conference,
    favorites: Favorites,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reset cancels a refresh from a Developer feed before that feed is cached.

    The new refresh then asks for the year's feed, and its own outcome stands.
    """
    release = asyncio.Event()
    asked: list[str] = []

    async def hold(url: str, **_: Any) -> bytes:
        asked.append(url)
        if url != DEV_FEED:
            raise api.NetworkError("ConnectError: offline")
        await release.wait()
        return recorded(2026)

    monkeypatch.setattr(api, "fetch_feed", hold)
    await conference.set_feed_url(DEV_FEED, svc.storage)
    running = conference.start_refresh(svc.storage, svc.year)
    await asyncio.sleep(0)
    async with asyncio.timeout(5):  # without the cancel it waits for the feed forever
        assert (
            await reset_app(svc, conference, prefs, favorites, Account(), Staff())
            is True
        )
    assert running.cancelled()
    release.set()
    await asyncio.sleep(0.05)
    assert not svc.storage.feed_path.exists()  # the test feed was never cached
    assert conference.source == "bundled"
    assert asked == [DEV_FEED, svc.year.conference.feed_url]  # then the year's feed
    assert conference.problem == "offline"  # the new refresh's own outcome
