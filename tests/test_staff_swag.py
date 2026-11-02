"""Tests for Swag pickup's screen, ``screens/staff_swag.py`` (SHIRT-01, SHIRT-02, SHIRT-04).

The screen runs in a real Flet session (``tests/harness.py``) over the mock's own
transport, signed with the seeded staff account's key, so the categories and lookups
are what the mock's ``handle()`` answers. The connection the screen sees is a stand-in
for ``use_online()`` the test flips. Pinned: the chips' states, the stored choice and
its relaunch, the pauses (no category, offline), a scan's result, the fetch tried again
when the connection returns, and the rule.
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, cast

import flet as ft
import httpx
import pytest

from pycon_us.account import Account
from pycon_us.config import YearData, load_year
from pycon_us.core.check_in import Catalog
from pycon_us.core.staff_tools import ToolKey
from pycon_us.dev_options import DEV_MOCK_API_URL
from pycon_us.memory import ViewMemory
from pycon_us.prefs import Prefs
from pycon_us.screens import staff_swag
from pycon_us.screens.staff_swag import (
    CHOOSE,
    LOADING,
    NOT_LOADED,
    OFFLINE,
    TITLE,
    SwagPickup,
)
from pycon_us.services import Services
from pycon_us.services.api import ApiClient
from pycon_us.services.pref_keys import staff_swag_categories
from pycon_us.services.private_api import PrivateApi
from pycon_us.state import Conference
from pycon_us.swag import NO_CONNECTION, NOTHING, READY
from pycon_us.ui import scan_screen
from pycon_us.ui.scan_screen import NOT_AVAILABLE
from pycon_us.ui.snack_bars import NOT_SAVED
from tests import harness
from tests.api_clients import BASE_URL, Login
from tests.fakes import MemoryPrefs
from tests.harness import Shown, showing
from tests.mock_calls import account as seeded
from tests.mock_calls import state_at
from tests.scan_rig import enter, panel
from tools.mock_api.transport import mock_transport

VIEW = "/more/staff/swag"

type Show = Callable[..., Awaitable[Shown]]


class Switch(httpx.AsyncBaseTransport):
    """The mock's transport, or no connection while ``offline`` is set."""

    def __init__(self, inner: httpx.AsyncBaseTransport) -> None:
        """Answer through ``inner``, online."""
        self.inner = inner
        self.offline = False

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Raise ``ConnectError`` offline, else let ``inner`` answer."""
        if self.offline:
            raise httpx.ConnectError("offline", request=request)
        return await self.inner.handle_async_request(request)


class HungOnce(httpx.AsyncBaseTransport):
    """The mock, but its first request hangs until ``release``, then times out."""

    def __init__(self, inner: httpx.AsyncBaseTransport) -> None:
        """Answer through ``inner``, the first request excepted."""
        self.inner = inner
        self.release = asyncio.Event()
        self.hung = False
        self.cancelled = False

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Hang the first request and record its cancelling; let ``inner`` answer the rest."""
        if self.hung:
            return await self.inner.handle_async_request(request)
        self.hung = True
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        raise httpx.ReadTimeout("no reply", request=request)


class Online:
    """The connection the screen sees: a hook in place of ``use_online()``."""

    def __init__(self) -> None:
        """Start online, with no screen rendered yet."""
        self.value = True
        self.setter: Callable[[bool], None] | None = None

    def hook(self, _svc: Services, *, watch: bool) -> bool:
        """Return the connection as a state, so a flip re-renders the screen."""
        assert watch  # Swag pickup always watches (D-56)
        online, set_online = ft.use_state(self.value)
        self.setter = set_online
        return online

    async def flip(self, shown: Shown, value: bool) -> None:
        """Turn the connection on or off as the 5 s check would see it."""
        self.value = value
        assert self.setter is not None
        self.setter(value)
        await shown.settle()


def staff(*, door_check: bool = True, signed_in: bool = True) -> Account:
    """An ``Account``: door staff, signed in, by default."""
    return Account(
        signed_in=signed_in,
        email="staff@example.com",
        door_check=door_check,
    )


@pytest.fixture
def switch() -> Switch:
    """The transport every test's sessions share, over a freshly seeded mock."""
    return Switch(mock_transport(state_at()))


@pytest.fixture
def online(monkeypatch: pytest.MonkeyPatch) -> Online:
    """The connection the screen sees, online until a test flips it."""
    held = Online()
    monkeypatch.setattr(staff_swag, "use_online", held.hook)
    return held


@pytest.fixture
def fetches(monkeypatch: pytest.MonkeyPatch) -> list[ApiClient]:
    """The catalog fetches the screen started, one client each.

    Counted here, not at the transport: the mock's fixed clock makes a fetch send two
    requests, the first refused for its skew (``ApiClient.request``).
    """
    started: list[ApiClient] = []
    fetch = staff_swag.fetch_catalog

    async def counted(api: ApiClient) -> Catalog:
        """Record the fetch, then send it."""
        started.append(api)
        return await fetch(api)

    monkeypatch.setattr(staff_swag, "fetch_catalog", counted)
    return started


@pytest.fixture
def stored() -> dict[str, Any]:
    """The SharedPreferences values every session of a test shares, as a device's."""
    return {}


@pytest.fixture
async def show(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    switch: Switch,
    online: Online,
    stored: dict[str, Any],
) -> AsyncIterator[Show]:
    """Return a function that renders Swag pickup for an account over ``switch``.

    Its sessions share ``stored``, so a second render is a relaunch; ``mock_url``
    False leaves the mock URL unset (D-51).
    """

    async def focus(_: ft.TextField) -> None:
        """Stand in for the client's focus: nothing to do."""

    monkeypatch.setattr(ft.TextField, "focus", focus)
    memory_services = harness.memory_services

    def sharing(
        year: YearData, directory: Path, memory: ViewMemory | None = None
    ) -> Services:
        """Return the memory services over the test's one ``stored``."""
        svc = memory_services(year, directory, memory)
        cast(MemoryPrefs, svc.storage.prefs).values = stored
        return svc

    monkeypatch.setattr(harness, "memory_services", sharing)
    who = seeded(state_at(), "staff")
    async with AsyncExitStack() as stack:

        async def render(
            account: Account | None = None, *, mock_url: bool = True
        ) -> Shown:
            """Render the route signed in as ``account``, door staff by default."""
            private_api = PrivateApi(switch, credentials=Login(who.key, who.secret))
            await private_api.connect(BASE_URL, 2026)
            prefs = Prefs(loaded=True)
            if mock_url:
                prefs.dev = {DEV_MOCK_API_URL: BASE_URL}
            shown = await stack.enter_async_context(
                showing(
                    SwagPickup,
                    scan_screen,
                    year=load_year(2026),
                    conference=Conference(),
                    tmp_path=tmp_path,
                    monkeypatch=monkeypatch,
                    view_path=VIEW,
                    route=VIEW,
                    prefs=prefs,
                    account=account or staff(),
                    private_api=private_api,
                )
            )
            stack.push_async_callback(private_api.connect, None, 2026)
            return shown

        yield render


def chip(shown: Shown, ident: int) -> ft.Chip:
    """The chip of the category ``ident``, as its identifier names it."""
    return cast(ft.Chip, shown.node(f"swag.category.{ident}").content)


async def tap(shown: Shown, ident: int) -> None:
    """Tap a chip: Flutter flips it and reports its new state, then the event."""
    control = chip(shown, ident)
    selected = not control.selected
    shown.session.apply_patch(control._i, {"selected": selected})
    await shown.event(control, "select", selected)


def helper(shown: Shown) -> str | None:
    """The scan field's helper line: why scanning is paused, or None."""
    (field,) = shown.find(ft.TextField)
    return cast(str | None, field.helper)


async def test_the_chips_show_none_chosen_and_scanning_is_paused(
    show: Show,
) -> None:
    """The T-Shirt and Swag Bag chips, unselected; the field says to choose."""
    shown = await show()
    assert shown.titles[-1] == TITLE
    assert [chip(shown, i).label for i in (3, 4)] == ["T-Shirt", "Swag Bag"]
    assert not chip(shown, 3).selected and not chip(shown, 4).selected
    assert not shown.nodes("swag.category.1")  # the door's categories stay out
    assert helper(shown) == CHOOSE
    await enter(shown, "MOCK0001:v4l1d01")  # dropped while paused
    assert READY not in panel(shown)
    assert shown.services.memory.staff_tool == ToolKey.SWAG


async def test_a_choice_is_stored_scans_and_survives_a_relaunch(
    show: Show, stored: dict[str, Any]
) -> None:
    """Both chips chosen: stored as ids, Margaret nothing; kept next time.

    Items left open the hand-out sheet: ``tests/test_swag_sheet.py``.
    """
    shown = await show()
    await tap(shown, 3)
    await tap(shown, 4)
    assert stored[staff_swag_categories(2026).key] == ["3", "4"]
    assert chip(shown, 3).selected and chip(shown, 4).selected
    assert helper(shown) is None
    await enter(shown, "MOCK0004:v4l1d04")
    assert panel(shown).startswith(f"{NOTHING}\nMargaret Test")
    await tap(shown, 4)  # unchosen again
    assert stored[staff_swag_categories(2026).key] == ["3"]
    again = await show()
    assert chip(again, 3).selected and not chip(again, 4).selected
    assert helper(again) is None


async def test_ids_no_longer_in_the_catalog_are_ignored(
    show: Show, stored: dict[str, Any]
) -> None:
    """A stored door category or a gone id never counts as a choice: still paused."""
    stored[staff_swag_categories(2026).key] = ["1", "99", "x"]
    shown = await show()
    assert helper(shown) == CHOOSE
    await tap(shown, 4)
    assert stored[staff_swag_categories(2026).key] == ["1", "4", "99"]
    assert helper(shown) is None


async def test_offline_pauses_with_the_reason_and_resumes(
    show: Show, online: Online, stored: dict[str, Any]
) -> None:
    """Offline: "Swag pickup needs a connection", a scan dropped; back on, it scans."""
    stored[staff_swag_categories(2026).key] = ["3", "4"]
    shown = await show()
    await online.flip(shown, False)
    assert helper(shown) == OFFLINE
    await enter(shown, "MOCK0001:v4l1d01")
    (field,) = shown.find(ft.TextField)
    assert field.value == ""  # dropped with its text (D-420, D-471)
    assert READY not in panel(shown)
    await online.flip(shown, True)
    assert helper(shown) is None
    await enter(shown, "MOCK0004:v4l1d04")
    assert panel(shown).startswith(NOTHING)


async def test_a_lookup_without_an_answer_says_no_connection(
    show: Show, switch: Switch, stored: dict[str, Any]
) -> None:
    """The check said online but the call fails: "No connection", until the next scan."""
    stored[staff_swag_categories(2026).key] = ["3"]
    shown = await show()
    switch.offline = True
    await enter(shown, "MOCK0002:v4l1d02")
    assert panel(shown).startswith(f"{NO_CONNECTION}\nMOCK0002")


async def test_a_failed_catalog_says_so_and_retry_loads_it(
    show: Show, switch: Switch
) -> None:
    """Offline at the fetch: "Couldn't load categories", never no chips; Retry loads."""
    switch.offline = True
    shown = await show()
    assert NOT_LOADED in shown.texts()
    assert not shown.nodes("swag.category.")
    assert helper(shown) == CHOOSE
    switch.offline = False
    await shown.click(cast(ft.TextButton, shown.node("swag.categories.retry").content))
    assert NOT_LOADED not in shown.texts()
    assert shown.nodes("swag.category.3")


async def test_a_failed_catalog_logs_what_failed_and_no_more(
    show: Show, switch: Switch, caplog: pytest.LogCaptureFixture
) -> None:
    """The log names the list and the error's type, never the error's text (D-72)."""
    switch.offline = True
    with caplog.at_level(logging.INFO, logger="pycon_us"):
        await show()
    assert "Swag categories not loaded: NetworkError" in caplog.messages


async def test_a_failed_catalog_reloads_when_the_connection_returns(
    show: Show, switch: Switch, online: Online
) -> None:
    """Offline at the fetch, then back online: the chips come by themselves."""
    switch.offline = True
    shown = await show()
    await online.flip(shown, False)
    switch.offline = False
    await online.flip(shown, True)
    assert shown.nodes("swag.category.3")


async def test_a_connection_returning_during_a_fetch_restarts_it(
    show: Show, switch: Switch, online: Online, fetches: list[ApiClient]
) -> None:
    """Retry hangs, then back online: the chips come, the old fetch's failure never shows.

    The hanging fetch is cancelled, so it doesn't race the new one (#876).
    """
    switch.offline = True
    shown = await show()
    await online.flip(shown, False)
    assert NOT_LOADED in shown.texts()
    hung = HungOnce(switch.inner)
    switch.inner = hung
    switch.offline = False
    await shown.click(cast(ft.TextButton, shown.node("swag.categories.retry").content))
    assert shown.nodes("swag.categories.loading")
    await online.flip(shown, True)
    hung.release.set()  # were it still out, its timeout would land after the new answer
    await shown.settle()
    assert NOT_LOADED not in shown.texts()
    assert shown.nodes("swag.category.3")
    assert hung.cancelled
    assert len(fetches) == 3  # the opening's, Retry's, and the return's


async def test_a_connection_lost_during_a_fetch_leaves_it_out(
    show: Show, switch: Switch, online: Online, fetches: list[ApiClient]
) -> None:
    """Only the connection's return restarts a fetch: losing it asks for nothing."""
    hung = HungOnce(switch.inner)
    switch.inner = hung
    shown = await show()
    await online.flip(shown, False)
    assert len(fetches) == 1
    assert not hung.cancelled
    assert shown.nodes("swag.categories.loading")


async def test_a_connection_change_with_the_catalog_loaded_fetches_nothing(
    show: Show, online: Online, fetches: list[ApiClient]
) -> None:
    """One fetch as the screen opens; off and on again, the chips stay, no other."""
    shown = await show()
    assert len(fetches) == 1
    await online.flip(shown, False)
    await online.flip(shown, True)
    assert shown.nodes("swag.category.3")
    assert len(fetches) == 1


async def test_the_catalog_shows_a_progress_line_while_it_loads(
    show: Show, switch: Switch
) -> None:
    """A held reply: the labelled progress line, then the chips."""
    held = asyncio.Event()
    inner = switch.inner

    class Slow(httpx.AsyncBaseTransport):
        """The mock, answering once ``held`` is set."""

        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            """Wait for ``held``, then let the mock answer."""
            await held.wait()
            return await inner.handle_async_request(request)

    switch.inner = Slow()
    shown = await show()
    assert shown.node("swag.categories.loading").label == LOADING
    held.set()
    await shown.settle()
    assert not shown.nodes("swag.categories.loading")
    assert shown.nodes("swag.category.3")


async def test_the_chips_wait_for_the_stored_choice(
    show: Show, monkeypatch: pytest.MonkeyPatch, stored: dict[str, Any]
) -> None:
    """Until the choice is read, the progress line: a tap can't race the late read."""
    stored[staff_swag_categories(2026).key] = ["4"]
    held = asyncio.Event()
    answer = MemoryPrefs._invoke_method

    async def slow(
        self: MemoryPrefs, method_name: str, *args: Any, **kwargs: Any
    ) -> Any:
        """Hold the choice's read until ``held`` is set, as a slow first read would."""
        arguments = args[0] if args else kwargs.get("arguments")
        if method_name == "get" and arguments == {
            "key": staff_swag_categories(2026).key
        }:
            await held.wait()
        return await answer(self, method_name, *args, **kwargs)

    monkeypatch.setattr(MemoryPrefs, "_invoke_method", slow)
    shown = await show()
    assert shown.nodes("swag.categories.loading")
    assert not shown.nodes("swag.category.")
    held.set()
    await shown.settle()
    assert chip(shown, 4).selected and not chip(shown, 3).selected


async def test_a_failed_save_says_so_and_keeps_the_choice_for_the_visit(
    show: Show,
) -> None:
    """SharedPreferences refuses: "Couldn't save your change"; the chip stays chosen."""
    shown = await show()
    cast(MemoryPrefs, shown.storage.prefs).fail_writes = True
    await tap(shown, 3)
    assert chip(shown, 3).selected
    (bar,) = shown.snack_bars
    assert isinstance(bar.content, ft.Text) and bar.content.value == NOT_SAVED
    assert helper(shown) is None


@pytest.mark.parametrize(
    ("account", "mock_url"),
    [
        (staff(door_check=False), True),
        (staff(signed_in=False), True),
        (staff(), False),
    ],
)
async def test_a_refused_account_sees_not_available(
    show: Show, account: Account, mock_url: bool
) -> None:
    """No ``door_check``, signed out or no mock URL: no chips, no scan field (D-51)."""
    shown = await show(account, mock_url=mock_url)
    assert NOT_AVAILABLE in shown.texts()
    assert not shown.find(ft.TextField)
    assert not shown.nodes("swag.category.")
