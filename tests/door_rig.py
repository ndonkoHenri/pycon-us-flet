"""Door check's test rig: its fixtures and readers, over the mock's own transport.

Shared by ``tests/test_staff_door.py`` (the route and the picker) and
``tests/test_door_preload.py`` (the attendee list): ``show`` renders ``DoorCheck`` or
its picker in a real Flet session (``tests/harness.py``), signed with the seeded staff
account's key, so what the screens fetch is what the mock's ``handle()`` answers; a
``Switch`` takes the transport offline. One test's sessions share one
SharedPreferences and one outbox, so a second render is a relaunch.
"""

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, cast

import flet as ft
import httpx
import pytest

from pycon_us.account import Account
from pycon_us.config import YearData, load_year
from pycon_us.core.door_sessions import DoorChoice, to_stored
from pycon_us.dev_options import DEV_MOCK_API_URL
from pycon_us.memory import ViewMemory
from pycon_us.prefs import Prefs
from pycon_us.screens.door_session import SessionPicker
from pycon_us.screens.staff_door import DoorCheck
from pycon_us.services import Services
from pycon_us.services.outbox_db import OutboxDb
from pycon_us.services.pref_keys import staff_door_session
from pycon_us.services.private_api import PrivateApi
from pycon_us.state import Conference
from pycon_us.ui import scan_screen, staff_picker
from tests import harness
from tests.api_clients import BASE_URL, Login
from tests.fakes import MemoryPrefs
from tests.harness import Shown, showing
from tests.mock_calls import account as seeded
from tests.mock_calls import state_at
from tests.picker_rig import Switch
from tools.mock_api.transport import mock_transport

VIEW = "/more/staff/door"
PICKER = f"{VIEW}/session"
ASYNC = DoorChoice(1, (11,), "Async in depth \N{MIDDLE DOT} Wed 1:30 PM")

type Show = Callable[..., Awaitable[Shown]]


def staff(
    *,
    door_check: bool = True,
    lead_retrieval: bool = False,
    mask_violation: bool = False,
) -> Account:
    """A signed-in ``Account`` with only the given flags; door staff by default."""
    return Account(
        restored=True,
        signed_in=True,
        email="staff@example.com",
        door_check=door_check,
        lead_retrieval=lead_retrieval,
        mask_violation=mask_violation,
    )


@pytest.fixture
def stored() -> dict[str, Any]:
    """The SharedPreferences values every session of a test shares, as a device's."""
    return {}


@pytest.fixture
def switch() -> Switch:
    """The transport every test's sessions share, over a freshly seeded mock."""
    return Switch(mock_transport(state_at()))


@pytest.fixture
async def show(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stored: dict[str, Any],
    switch: Switch,
) -> AsyncIterator[Show]:
    """Return a function that renders Door check, or its picker, for an account.

    ``view`` picks the page (``VIEW`` or ``PICKER``); ``chosen`` stores a choice first,
    as an earlier pick left it; ``transport`` replaces ``switch``; ``outbox``
    replaces the test's own (``tmp_path / "outbox"``, shared by its renders); ``prefs``
    replaces the default settings.
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
    directory = tmp_path / "outbox"
    directory.mkdir()
    shared = OutboxDb(directory, 2026)
    async with AsyncExitStack() as stack:
        stack.callback(shared.close)

        async def render(
            view: str,
            account: Account | None = None,
            *,
            chosen: DoorChoice | None = None,
            transport: httpx.AsyncBaseTransport | None = None,
            outbox: OutboxDb | None = None,
            prefs: Prefs | None = None,
        ) -> Shown:
            """Render ``view`` signed in as ``account``, door staff by default."""
            private_api = PrivateApi(
                transport or switch, credentials=Login(who.key, who.secret)
            )
            await private_api.connect(BASE_URL, 2026)
            if chosen is not None:
                stored[staff_door_session(2026).key] = json.dumps(to_stored(chosen))
            prefs = prefs or Prefs(loaded=True)
            prefs.dev = {DEV_MOCK_API_URL: BASE_URL}
            shown = await stack.enter_async_context(
                showing(
                    SessionPicker if view == PICKER else DoorCheck,
                    scan_screen,
                    staff_picker,
                    year=load_year(2026),
                    conference=Conference(),
                    tmp_path=tmp_path,
                    monkeypatch=monkeypatch,
                    view_path=view,
                    route=view,
                    prefs=prefs,
                    account=account or staff(),
                    private_api=private_api,
                    outbox=shared if outbox is None else outbox,
                )
            )
            stack.push_async_callback(private_api.connect, None, 2026)
            return shown

        yield render


async def tap(shown: Shown, identifier: str) -> None:
    """Tap the row, the chip or the button that ``identifier`` names."""
    node = shown.node(identifier)
    target = node.content if identifier.startswith("door.category.") else node.parent
    await shown.click(cast(ft.Control, target))


async def stored_choice(shown: Shown) -> dict[str, Any]:
    """The choice as storage holds it."""
    return await shown.storage.get(staff_door_session(2026))


def helper(shown: Shown) -> str | None:
    """The scan field's helper line: why scanning is paused, or None."""
    (field,) = shown.find(ft.TextField)
    return cast(str | None, field.helper)


def chip_text(shown: Shown) -> str | None:
    """What the session chip shows, or None without the chip."""
    nodes = shown.nodes("door.session_chip")
    if not nodes:
        return None
    (node,) = nodes
    row = node.content
    assert isinstance(row, ft.Row)
    (text,) = [c for c in row.controls if isinstance(c, ft.Text)]
    return str(text.value)


def preload_line(shown: Shown) -> str | None:
    """What the attendee list's line says, as read (``door.preload``), or None."""
    nodes = shown.nodes("door.preload")
    return str(nodes[0].label) if nodes else None
