"""Tests for ``services/calendar.py``: Add to calendar's two routes (D-272, SESS-04).

iOS's runs the real loopback server against a launcher that fetches the URL as
SFSafariViewController does and then raises as url_launcher_ios does (F91); Android's
records the save dialog's file (``MemoryFilePicker``). Whether a calendar then adds the
event is checked on devices (the PR, #121).
"""

import asyncio
import logging
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import flet as ft
import pytest

from pycon_us.config import load_year
from pycon_us.services import Services, calendar
from pycon_us.services.calendar import (
    CONTENT_TYPE,
    NOT_OPENED,
    LoopbackFile,
    add_to_calendar,
    saved_text,
)
from tests.fake_page import FakePage, bound
from tests.fakes import MemoryFilePicker, MemoryLauncher
from tests.sessions import memory_services

DATA = b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n"
"""A calendar file's bytes: what is served or saved, never parsed here."""

SLUG = "python-for-humans"
"""The file's name without ``.ics``."""

LAUNCH_ERROR = "PlatformException(Error, Error while launching http://127.0.0.1)"
"""What url_launcher_ios raises after the sheet showed (F91)."""


class Fetch:
    """What one GET of the served URL answered: status, type and body."""

    def __init__(self, status: int, content_type: str | None, body: bytes) -> None:
        """Keep the answer's status, ``Content-Type`` and body."""
        self.status = status
        self.content_type = content_type
        self.body = body


def get(url: str) -> Fetch:
    """GET ``url`` as a browser would; a 404 is an answer too, not an error."""
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return Fetch(
                response.status, response.headers["Content-Type"], response.read()
            )
    except urllib.error.HTTPError as error:
        return Fetch(error.code, error.headers["Content-Type"], error.read())


def is_down(url: str) -> bool:
    """Whether nothing answers at ``url`` any more."""
    try:
        urllib.request.urlopen(url, timeout=2).close()
    except urllib.error.HTTPError:
        return False  # something answered, if only with an error
    except OSError:
        return True
    return False


class SafariLauncher(MemoryLauncher):
    """A launcher that loads the URL as the in-app browser does, then raises (F91)."""

    def init(self) -> None:
        """Start with nothing launched or fetched; first fetch nothing else."""
        super().init()
        self.fetches: list[Fetch] = []
        self.also: list[str] = []  # paths fetched before the file, e.g. an icon
        self.fetch_file = True
        self.hold = False  # never report, as a browser view that never loads

    async def launch_url(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, url: str, *, mode: ft.LaunchMode = ft.LaunchMode.PLATFORM_DEFAULT
    ) -> None:
        """Record the URL, GET the other paths and then the file, and raise.

        With ``hold``, wait for ever (until cancelled) instead.
        """
        self.launched.append((url, mode))
        if self.hold:
            await asyncio.Event().wait()
        origin = url.rsplit("/", 1)[0]
        for path in self.also:
            self.fetches.append(await asyncio.to_thread(get, origin + path))
        if self.fetch_file:
            self.fetches.append(await asyncio.to_thread(get, url))
        raise RuntimeError(LAUNCH_ERROR)


@pytest.fixture
def page(svc: Services) -> Iterator[FakePage]:
    """Return a fake iPhone page, bound as Flet binds it while a handler runs.

    Bound after ``svc`` is built: a Flet service registers with a bound page.
    """
    fake = FakePage()
    with bound(fake):
        yield fake


@pytest.fixture
def svc(tmp_path: Path) -> Services:
    """Return services with the memory fakes and a launcher that loads the URL."""
    services = memory_services(load_year(2026), tmp_path)
    object.__setattr__(services, "launcher", SafariLauncher())
    return services


def said(page: FakePage) -> list[str]:
    """The texts of the SnackBars the page was asked to show, in order."""
    return [
        str(cast(ft.Text, d.content).value)
        for d in page.dialogs
        if isinstance(d, ft.SnackBar)
    ]


def launcher(svc: Services) -> SafariLauncher:
    """The services' launcher, which loads what it is given."""
    return cast(SafariLauncher, svc.launcher)


def picker(svc: Services) -> MemoryFilePicker:
    """The services' file picker, which records each save."""
    return cast(MemoryFilePicker, svc.file_picker)


# ------------------------------------------------------------------ iOS: the loopback


async def test_ios_serves_the_file_on_the_loopback_in_the_in_app_browser(
    page: FakePage, svc: Services
) -> None:
    """The file is served as ``text/calendar`` and opened in the in-app browser.

    Never ``EXTERNAL_APPLICATION``, which opens a calendar subscription (D-272).
    """
    await add_to_calendar(svc, SLUG, DATA)
    ((url, mode),) = launcher(svc).launched
    assert url.startswith("http://127.0.0.1:")
    assert url.endswith(f"/{SLUG}.ics")
    assert mode == ft.LaunchMode.IN_APP_BROWSER_VIEW
    (fetch,) = launcher(svc).fetches
    assert (fetch.status, fetch.content_type, fetch.body) == (200, CONTENT_TYPE, DATA)
    assert picker(svc).saved == []  # no save dialog on iOS


async def test_ios_takes_the_served_file_as_success_though_the_launch_raises(
    page: FakePage, svc: Services
) -> None:
    """F91: the launch raises although the sheet showed; the GET says it did."""
    await add_to_calendar(svc, SLUG, DATA)
    assert said(page) == []


async def test_ios_says_so_when_the_browser_never_fetched_the_file(
    page: FakePage, svc: Services
) -> None:
    """A launch that fails before any GET of the file says it couldn't open it."""
    launcher(svc).fetch_file = False
    launcher(svc).also = ["/favicon.ico"]  # another path does not count
    await add_to_calendar(svc, SLUG, DATA)
    assert [f.status for f in launcher(svc).fetches] == [404]
    assert said(page) == [NOT_OPENED]


async def test_ios_stops_the_server_once_the_launch_is_over(
    page: FakePage, svc: Services
) -> None:
    """The server is per tap: once the launch returns or raises, nothing answers."""
    await add_to_calendar(svc, SLUG, DATA)
    ((url, _),) = launcher(svc).launched
    assert await asyncio.to_thread(is_down, url)


async def test_ios_stops_serving_after_serve_seconds_at_most(
    page: FakePage, svc: Services, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A launch that never reports is given up on, the server stopped (D-272)."""
    monkeypatch.setattr(calendar, "SERVE_SECONDS", 0.05)
    launcher(svc).hold = True
    await asyncio.wait_for(add_to_calendar(svc, SLUG, DATA), 5)
    ((url, _),) = launcher(svc).launched
    assert await asyncio.to_thread(is_down, url)
    assert said(page) == [NOT_OPENED]  # nothing fetched it


async def test_ios_says_so_when_no_port_can_be_bound(
    page: FakePage, svc: Services, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A loopback server that cannot start launches nothing and says so."""

    def no_port(*_: object) -> None:
        raise OSError("no port")

    monkeypatch.setattr(LoopbackFile, "__init__", no_port)
    await add_to_calendar(svc, SLUG, DATA)
    assert launcher(svc).launched == []
    assert said(page) == [NOT_OPENED]


# ------------------------------------------------------------------ the server itself


async def test_the_server_logs_each_request_s_method_path_and_status(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """D-272's check: a device's log shows every request the browser and sheet sent."""
    caplog.set_level(logging.INFO, logger=calendar.__name__)
    served = LoopbackFile(f"{SLUG}.ics", DATA)
    try:
        origin = served.url.rsplit("/", 1)[0]
        await asyncio.to_thread(get, origin + "/favicon.ico")
        await asyncio.to_thread(get, served.url)
    finally:
        await asyncio.to_thread(served.close)
    lines = [
        r.getMessage() for r in caplog.records if "Calendar file server" in r.message
    ]
    assert any("GET /favicon.ico" in line and "404" in line for line in lines)
    assert any(f"GET /{SLUG}.ics" in line and "200" in line for line in lines)


async def test_only_a_get_of_the_file_counts_as_fetched() -> None:
    """A HEAD of the file, or a GET of another path, leaves ``fetched`` unset."""
    served = LoopbackFile(f"{SLUG}.ics", DATA)
    try:
        head = urllib.request.Request(served.url, method="HEAD")
        await asyncio.to_thread(lambda: urllib.request.urlopen(head, timeout=5).close())
        other = await asyncio.to_thread(get, served.url + ".bak")
        assert other.status == 404
        assert not served.fetched.is_set()
        await asyncio.to_thread(get, served.url)
        # Set by the server's thread once its answer is written, which the client can
        # have read first: wait for it rather than read it at once (#582).
        assert await asyncio.to_thread(served.fetched.wait, 5)
    finally:
        await asyncio.to_thread(served.close)


# ------------------------------------------------------------------ Android: a saved file


async def test_android_saves_the_file_and_says_how_to_open_it(
    page: FakePage, svc: Services
) -> None:
    """The save dialog gets the file's name and bytes; the SnackBar names no folder."""
    page.platform = ft.PagePlatform.ANDROID
    await add_to_calendar(svc, SLUG, DATA)
    assert picker(svc).saved == [(f"{SLUG}.ics", DATA)]
    assert said(page) == [
        f"Saved {SLUG}.ics. Open it from the Files app to add it to your calendar."
    ]
    assert said(page) == [saved_text(f"{SLUG}.ics")]
    assert launcher(svc).launched == []  # no loopback on Android


async def test_android_says_nothing_when_the_save_is_cancelled(
    page: FakePage, svc: Services
) -> None:
    """A cancel (``None``) is the user's choice and needs no answer."""
    page.platform = ft.PagePlatform.ANDROID
    picker(svc).answer = None
    await add_to_calendar(svc, SLUG, DATA)
    assert said(page) == []


async def test_android_says_so_when_the_dialog_fails_and_logs_the_class_only(
    page: FakePage, svc: Services, caplog: pytest.LogCaptureFixture
) -> None:
    """A failed save dialog says so; the log names the error's class, not its text."""
    page.platform = ft.PagePlatform.ANDROID
    picker(svc).error = RuntimeError(f"save_file({SLUG}.ics) failed")
    await add_to_calendar(svc, SLUG, DATA)
    assert said(page) == [NOT_OPENED]
    assert "RuntimeError" in caplog.text
    assert "save_file(" not in caplog.text  # D-72
