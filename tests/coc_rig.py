"""The CoC tool's test support: the mock transport, the `show` fixture and the dialog helpers.

The CoC tool's three test modules (`tests/test_staff_coc.py` for the screen,
`tests/test_coc_review.py` for the review dialog, `tests/test_coc_search.py` for the name
search) run it in a real Flet session over the mock's transport, signed with a seeded
account's key. They share this module, as the screens' tests share `tests/harness.py`,
instead of importing one another. A test module takes the fixtures by assigning them to
its own names (`show, switch, stored = coc_rig.show, ...`), where pytest looks one up, and
`show` needs `switch` and `stored` beside it (docs/testing-and-quality.md §3).
"""

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, cast

import flet as ft
import httpx
import pytest
from flet.utils.object_model import patch_dataclass

from pycon_us.account import Account
from pycon_us.config import YearData, load_year
from pycon_us.dev_options import DEV_MOCK_API_URL
from pycon_us.memory import ViewMemory
from pycon_us.prefs import Prefs
from pycon_us.screens.staff_coc import CocScanner
from pycon_us.services import Services
from pycon_us.services.private_api import PrivateApi
from pycon_us.state import Conference
from pycon_us.ui import scan_screen
from tests import harness
from tests.api_clients import BASE_URL, Login
from tests.fakes import MemoryPrefs
from tests.harness import Shown, showing
from tests.mock_calls import account as seeded
from tests.mock_calls import state_at
from tools.mock_api.state import MockState
from tools.mock_api.transport import mock_transport

VIEW = "/more/staff/coc"
ATTENDEES = "/2026/api/v1/mask_violations/attendees/"

type Show = Callable[..., Awaitable[Shown]]


class Switch(httpx.AsyncBaseTransport):
    """The mock's transport, which records each path, can wait and can go offline."""

    def __init__(self, inner: httpx.AsyncBaseTransport) -> None:
        """Answer through `inner`, online, at once."""
        self.inner = inner
        self.offline = False
        self.gate: asyncio.Event | None = None
        self.paths: list[str] = []
        self.cancelled = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Record the path; wait for `gate`; then fail offline, else let `inner` answer.

        A request cancelled while it waits is counted in `cancelled`.
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
    """A signed-in `Account` with only the given role flags; CoC staff by default."""
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
    """Return a function that renders the tool for an account over `switch`.

    It signs with the seeded `coc` account's key (`role` picks another); its
    sessions keep their preferences in `stored`, so a second render is a relaunch;
    `mock_url` False leaves the mock URL unset.
    """

    async def focus(_: ft.TextField) -> None:
        """Stand in for the client's focus: nothing to do."""

    monkeypatch.setattr(ft.TextField, "focus", focus)
    memory_services = harness.memory_services

    def sharing(
        year: YearData, directory: Path, memory: ViewMemory | None = None
    ) -> Services:
        """Return the memory services over the test's one `stored`."""
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
            """Render the route signed in as `account`, `coc()` by default.

            `settle` False returns before the fetch has ended (a gated transport).
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


@pytest.fixture
def mock(switch: Switch) -> MockState:
    """The mock's state behind `switch`, so a test reads its incidents and faults."""
    state = MockState.from_seed(now=time.time)
    switch.inner = mock_transport(state)
    return state


@pytest.fixture
def focused(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Counts the badge field's focus calls (the dialog's field is never focused)."""
    calls = [0]

    async def focus(_: ft.TextField) -> None:
        calls[0] += 1

    monkeypatch.setattr(ft.TextField, "focus", focus)
    return calls


def helper(shown: Shown) -> str | None:
    """The badge field's line: why scanning is paused, or None."""
    return cast(str | None, badge_field(shown).helper)


def badge_field(shown: Shown) -> ft.TextField:
    """The scan screen's badge code field (the closed dialog's field stays in the page)."""
    return cast(ft.TextField, shown.node("scan.entry").content)


async def enter(shown: Shown, text: str) -> None:
    """Type `text` in the badge field as Flutter reports it, then press Enter."""
    field = badge_field(shown)
    shown.session.apply_patch(field._i, {"value": text})
    await shown.event(field, "change", text)
    await shown.event(field, "submit", text)


def dialog(shown: Shown) -> ft.AlertDialog | None:
    """The open review dialog, or None."""
    dialogs = shown.session.page._dialogs.controls  # pyright: ignore[reportPrivateUsage]
    found = [d for d in dialogs if isinstance(d, ft.AlertDialog) and d.open]
    assert len(found) <= 1
    return found[0] if found else None


def walk(control: Any) -> Iterator[Any]:
    """Every control under `control`: its title, content, controls and actions."""
    yield control
    for name in ("title", "content"):
        child = getattr(control, name, None)
        if isinstance(child, ft.BaseControl):
            yield from walk(child)
    for name in ("controls", "actions"):
        for child in getattr(control, name, None) or ():
            if isinstance(child, ft.BaseControl):
                yield from walk(child)


def nodes(shown: Shown, identifier: str) -> list[ft.Semantics]:
    """The open dialog's semantics nodes named `identifier`."""
    current = dialog(shown)
    assert current is not None
    return [
        c
        for c in walk(current)
        if isinstance(c, ft.Semantics) and c.identifier == identifier
    ]


def in_dialog(shown: Shown, identifier: str) -> Any:
    """The control under the open dialog's semantics node `identifier`."""
    (node,) = nodes(shown, identifier)
    return node.content


def texts(shown: Shown) -> list[str]:
    """Every text in the open dialog."""
    current = dialog(shown)
    assert current is not None
    return [str(c.value) for c in walk(current) if isinstance(c, ft.Text)]


async def type_notes(shown: Shown, text: str) -> None:
    """Type the notes, as Flutter reports them."""
    field = in_dialog(shown, "coc.review.notes")
    patch_dataclass(field, {"value": text})
    await shown.event(field, "change", text)


async def tap(shown: Shown, identifier: str) -> None:
    """Tap the dialog's button `identifier`."""
    await shown.click(in_dialog(shown, identifier))
