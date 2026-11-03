"""Tests for the CoC incident tool's screen, ``screens/staff_coc.py`` (#759; MASK-01).

The route runs in a real Flet session (``tests/harness.py``) over the mock's own
transport, signed with a seeded account's key, so the directory is what the mock's
``handle()`` answers. The tool re-checks its rule on every render (architecture
§12.4); its status line goes loading, "4 attendees" with Reload, "Couldn't load the
attendee list" with Retry, or "Not available" on a 403; offline pauses scanning; a
scan opens the review dialog (its tests: ``tests/test_coc_review.py``); and the directory lives in the
screen alone: nothing is stored, and a remount fetches it again (D-56, D-432).
"""

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, cast

import flet as ft
import httpx
import pytest

from pycon_us.account import Account
from pycon_us.config import YearData, load_year
from pycon_us.core.staff_tools import ToolKey
from pycon_us.dev_options import DEV_MOCK_API_URL
from pycon_us.memory import ViewMemory
from pycon_us.prefs import Prefs
from pycon_us.screens import staff_coc
from pycon_us.screens.staff_coc import (
    LOADING,
    NOT_LOADED,
    OFFLINE,
    TITLE,
    CocScanner,
)
from pycon_us.services import Services
from pycon_us.services.private_api import PrivateApi
from pycon_us.state import Conference
from pycon_us.ui import scan_screen
from pycon_us.ui.scan_screen import NOT_AVAILABLE
from tests import harness
from tests.api_clients import BASE_URL, Login
from tests.fakes import MemoryPrefs
from tests.harness import Shown, showing
from tests.mock_calls import account as seeded
from tests.mock_calls import state_at
from tests.scan_rig import enter, panel
from tools.mock_api.state import MockState
from tools.mock_api.transport import mock_transport

VIEW = "/more/staff/coc"
ATTENDEES = "/2026/api/v1/mask_violations/attendees/"

type Show = Callable[..., Awaitable[Shown]]


class Switch(httpx.AsyncBaseTransport):
    """The mock's transport, which records each path, can wait and can go offline."""

    def __init__(self, inner: httpx.AsyncBaseTransport) -> None:
        """Answer through ``inner``, online, at once."""
        self.inner = inner
        self.offline = False
        self.gate: asyncio.Event | None = None
        self.paths: list[str] = []
        self.cancelled = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Record the path; wait for ``gate``; then fail offline, else let ``inner`` answer.

        A request cancelled while it waits is counted in ``cancelled``.
        """
        self.paths.append(request.url.path)
        if self.gate is not None:
            try:
                await self.gate.wait()
            except asyncio.CancelledError:
                self.cancelled += 1
                raise
        if self.offline:
            raise httpx.ConnectError("offline", request=request)
        return await self.inner.handle_async_request(request)


def coc(
    *,
    mask_violation: bool = True,
    door_check: bool = False,
    lead_retrieval: bool = False,
) -> Account:
    """A signed-in ``Account`` with only the given role flags; CoC staff by default."""
    return Account(
        signed_in=True,
        email="coc@example.com",
        mask_violation=mask_violation,
        door_check=door_check,
        lead_retrieval=lead_retrieval,
    )


@pytest.fixture
def stored() -> dict[str, Any]:
    """The SharedPreferences values every session of a test shares, as a device's."""
    return {}


def seeded_mock(attendees: int = 0) -> httpx.AsyncBaseTransport:
    """The mock's transport over a fresh seed, on the real clock.

    The real clock, so a request is signed in the mock's window and a fetch is one
    request (no skew retry), which the tests count.
    """
    return mock_transport(MockState.from_seed(now=time.time, attendees=attendees))


@pytest.fixture
def switch() -> Switch:
    """The transport every test's sessions share, over a freshly seeded mock."""
    return Switch(seeded_mock())


@pytest.fixture
async def show(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    switch: Switch,
    stored: dict[str, Any],
) -> AsyncIterator[Show]:
    """Return a function that renders the tool for an account over ``switch``.

    It signs with the seeded ``coc`` account's key (``role`` picks another); its
    sessions keep their preferences in ``stored``, so a second render is a relaunch;
    ``mock_url`` False leaves the mock URL unset.
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
    async with AsyncExitStack() as stack:

        async def render(
            account: Account | None = None,
            *,
            role: str = "coc",
            mock_url: bool = True,
            settle: bool = True,
        ) -> Shown:
            """Render the route signed in as ``account``, ``coc()`` by default.

            ``settle`` False returns before the fetch has ended (a gated transport).
            """
            who = seeded(state_at(), role)
            private_api = PrivateApi(switch, credentials=Login(who.key, who.secret))
            await private_api.connect(BASE_URL, 2026)
            prefs = Prefs(loaded=True)
            if mock_url:
                prefs.dev = {DEV_MOCK_API_URL: BASE_URL}
            shown = await stack.enter_async_context(
                showing(
                    CocScanner,
                    scan_screen,
                    year=load_year(2026),
                    conference=Conference(),
                    tmp_path=tmp_path,
                    monkeypatch=monkeypatch,
                    view_path=VIEW,
                    route=VIEW,
                    prefs=prefs,
                    account=account or coc(),
                    private_api=private_api,
                )
            )
            stack.push_async_callback(private_api.connect, None, 2026)
            if settle:
                await shown.settle()
            return shown

        yield render


def status(shown: Shown) -> str:
    """What the status line's live region says."""
    node = shown.node("coc.directory")
    assert node.live_region and node.container  # said as it changes (ux.md §9)
    return str(node.label)


def helper(shown: Shown) -> str | None:
    """The badge field's line: why scanning is paused, or None."""
    (field,) = shown.find(ft.TextField)
    return cast(str | None, field.helper)


def button(shown: Shown, identifier: str) -> ft.IconButton | ft.TextButton:
    """The status line's button that ``identifier`` names."""
    found = shown.node(identifier).content
    assert isinstance(found, ft.IconButton | ft.TextButton)
    return found


@pytest.mark.parametrize(
    ("account", "mock_url"),
    [
        (coc(mask_violation=False), True),
        (coc(mask_violation=False, door_check=True, lead_retrieval=True), True),
        (Account(), True),
        (coc(), False),
    ],
    ids=["no flag", "door and lead only", "signed out", "no mock URL"],
)
async def test_only_a_coc_account_with_a_mock_url_reaches_it(
    show: Show, switch: Switch, account: Account, mock_url: bool
) -> None:
    """Without ``mask_violation``, signed out or with no mock URL: "Not available"."""
    shown = await show(account, mock_url=mock_url)
    assert NOT_AVAILABLE in shown.texts()
    assert not shown.nodes("scan.entry")
    assert switch.paths == []  # nothing fetched
    assert shown.memory.staff_tool != ToolKey.COC


async def test_it_loads_then_counts_the_mock_s_attendees(
    show: Show, switch: Switch
) -> None:
    """A ring and "Loading attendee list…", then "4 attendees" with Reload."""
    switch.gate = asyncio.Event()
    shown = await show(settle=False)
    await shown.settle()
    assert shown.titles[-1] == TITLE
    assert status(shown) == LOADING
    assert shown.find(ft.ProgressRing)
    assert not shown.nodes("coc.directory.reload")
    switch.gate.set()
    await shown.settle()
    assert status(shown) == "4 attendees"
    assert not shown.find(ft.ProgressRing)
    reload = button(shown, "coc.directory.reload")
    assert reload.tooltip == "Reload attendee list" and not reload.disabled
    assert helper(shown) is None  # scanning
    assert shown.memory.staff_tool == ToolKey.COC  # Now's card's next tool (D-421)


async def test_a_large_directory_is_counted_with_a_separator(
    show: Show, switch: Switch
) -> None:
    """The mock's ``--attendees 3000``: "3,004 attendees"."""
    switch.inner = seeded_mock(attendees=3000)
    shown = await show()
    assert status(shown) == "3,004 attendees"


async def test_reload_fetches_the_directory_again(show: Show, switch: Switch) -> None:
    """Reload asks the mock again; the count comes back."""
    shown = await show()
    await shown.click(button(shown, "coc.directory.reload"))
    assert switch.paths.count(ATTENDEES) == 2
    assert status(shown) == "4 attendees"


async def test_no_answer_says_so_and_retry_loads(show: Show, switch: Switch) -> None:
    """Offline at the fetch: "Couldn't load the attendee list"; Retry loads once back."""
    switch.offline = True
    shown = await show()
    assert status(shown) == NOT_LOADED
    switch.offline = False
    await shown.click(button(shown, "coc.directory.retry"))
    assert status(shown) == "4 attendees"


async def test_an_error_answer_is_the_same_failure(show: Show, switch: Switch) -> None:
    """A 500 is said as "Couldn't load the attendee list", with Retry (D-120)."""
    switch.inner = httpx.MockTransport(lambda _: httpx.Response(500, json={}))
    shown = await show()
    assert status(shown) == NOT_LOADED
    assert shown.nodes("coc.directory.retry")


async def test_a_refusal_says_not_available_and_pauses(show: Show) -> None:
    """The mock's 403 (the flag gone on the server): "Not available", no scanning."""
    shown = await show(role="staff")
    assert status(shown) == NOT_AVAILABLE
    assert helper(shown) == NOT_AVAILABLE
    assert not shown.nodes("coc.directory.retry")


async def test_offline_pauses_scanning_and_disables_the_buttons(
    show: Show, switch: Switch, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No connection: "CoC capture needs a connection"; Reload and Retry disabled."""
    monkeypatch.setattr(staff_coc, "use_online", lambda svc, *, watch: False)
    shown = await show()
    assert helper(shown) == OFFLINE
    reload = button(shown, "coc.directory.reload")
    assert reload.disabled and OFFLINE in str(reload.tooltip)
    await enter(shown, "MOCK0003:x")
    assert not shown.nodes("scan.result") or "Linus" not in panel(shown)


async def test_offline_retry_is_disabled_with_the_reason(
    show: Show, switch: Switch, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After a failed fetch offline, Retry is disabled and says why."""
    monkeypatch.setattr(staff_coc, "use_online", lambda svc, *, watch: False)
    switch.offline = True
    shown = await show()
    node = shown.node("coc.directory.retry")
    assert node.disabled  # read as disabled (named(), F42)
    named = node.content
    assert isinstance(named, ft.Semantics)  # a disabled button's tooltip isn't read
    assert named.label == f"Retry. {OFFLINE}" and named.disabled
    assert isinstance(named.content, ft.TextButton) and named.content.disabled


async def test_the_directory_is_dropped_on_leaving_and_never_stored(
    show: Show, switch: Switch, stored: dict[str, Any]
) -> None:
    """Leaving the tool cancels its fetch and drops the directory; re-entry refetches.

    In one session: losing ``mask_violation`` mid-fetch unmounts the tool and cancels
    the request, so no late answer lands; regaining it fetches the changed mock anew;
    a sign-out drops it again; nothing ever reaches storage (D-432, D-56).
    """
    account = coc()
    switch.gate = asyncio.Event()
    shown = await show(account, settle=False)
    await shown.settle()
    assert status(shown) == LOADING
    account.mask_violation = False  # the flag revoked while the fetch waits
    await shown.settle()
    assert switch.cancelled == 1  # the effect was cancelled: its answer never lands
    assert NOT_AVAILABLE in shown.texts()
    assert not shown.nodes("coc.directory")
    switch.inner = seeded_mock(attendees=3000)  # the server's list changed
    switch.gate.set()
    account.mask_violation = True  # back in the tool: a new mount
    await shown.settle()
    assert status(shown) == "3,004 attendees"
    assert switch.paths.count(ATTENDEES) == 2
    account.signed_in = False  # Account.sign_out() clears the flags too
    await shown.settle()
    assert not shown.nodes("coc.directory")
    account.signed_in = True
    await shown.settle()
    assert status(shown) == "3,004 attendees"
    assert switch.paths.count(ATTENDEES) == 3  # fetched again, not kept
    assert stored == {}
