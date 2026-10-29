"""Tests for Door check's attendee-list preload (#765; DOOR-03, API-05; D-56, D-70).

``screens/staff_door.py`` with ``screens/door_preload.py`` run in a real Flet session
over the mock's own transport (``tests/door_rig.py``); a ``Gate`` holds each product's
call until the test lets it answer, so the loading states can be seen. Scanning is
paused while the list loads ("Loading attendee list… 1 of 2"), then the line under the
chip says "Ready, works offline · 3 attendees", or "Badges will be checked online" with
Retry, and scanning starts. A change of session or leaving the tool cancels the load;
nothing of the list is written anywhere.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import flet as ft
import httpx
import pytest

from pycon_us.core.door_sessions import DoorChoice, to_stored
from pycon_us.core.outbox import Status
from pycon_us.door_choice import read_door_session
from pycon_us.prefs import Prefs
from pycon_us.screens import staff_door
from pycon_us.screens.door_preload import ONLINE, RETRY
from pycon_us.screens.staff_door import BADGE_READ, NOT_CHECKED_IN, NOT_ON_LIST, ON_LIST
from pycon_us.services.outbox_db import OutboxDb
from pycon_us.services.storage import STAFF_DOOR_SESSION
from tests import door_rig
from tests.door_rig import ASYNC, VIEW, Show, helper, preload_line, staff
from tests.fakes import MemorySemantics
from tests.harness import Shown
from tests.picker_rig import Switch
from tests.scan_rig import enter, panel

stored, switch, show = door_rig.stored, door_rig.switch, door_rig.show

TUTORIALS = DoorChoice(1, (10, 11), "Tutorials \N{MIDDLE DOT} All sessions", True)
SUMMIT = DoorChoice(2, (20,), "Example Summit \N{MIDDLE DOT} Thu 10:00 AM")
LOADING = "Loading attendee list\N{HORIZONTAL ELLIPSIS}"
READY_THREE = "Ready, works offline, 3 attendees"
"""Tutorials' list as read: Ada and Linus bought one, Grace the other."""


class Gate(httpx.AsyncBaseTransport):
    """``inner``, but each product's inventory call waits until it is let through."""

    def __init__(self, inner: httpx.AsyncBaseTransport) -> None:
        """Hold every inventory call; nothing answered or cancelled yet."""
        self.inner = inner
        self.opened: dict[str, asyncio.Event] = {}
        self.answered: list[str] = []
        self.cancelled: list[str] = []

    def gate(self, product: int | str) -> asyncio.Event:
        """The event that lets ``product``'s call through."""
        return self.opened.setdefault(str(product), asyncio.Event())

    async def let(self, shown: Shown, *products: int) -> None:
        """Let these products' calls answer, then let the screen settle."""
        for product in products:
            self.gate(product).set()
        await shown.settle()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Wait at a product's gate, noting a cancel, then let ``inner`` answer."""
        path = request.url.path
        if "attendees_by_product_with_quantity" in path:
            product = path.rstrip("/").rsplit("/", 1)[1]
            try:
                await self.gate(product).wait()
            except asyncio.CancelledError:
                self.cancelled.append(product)
                raise
            self.answered.append(product)
        return await self.inner.handle_async_request(request)


@pytest.fixture
def gate(switch: Switch) -> Gate:
    """The test's mock transport, its inventory calls held at a gate."""
    return Gate(switch)


async def test_scanning_waits_for_the_list_with_its_progress(
    show: Show, gate: Gate
) -> None:
    """Paused at "0 of 2", then "1 of 2", then ready with 3 attendees, and scanning."""
    shown = await show(VIEW, chosen=TUTORIALS, transport=gate)
    assert helper(shown) == f"{LOADING} 0 of 2"
    assert preload_line(shown) == f"{LOADING} 0 of 2"
    await gate.let(shown, 11)
    assert helper(shown) == f"{LOADING} 1 of 2"
    await gate.let(shown, 10)
    assert preload_line(shown) == READY_THREE
    assert helper(shown) is None
    assert not shown.nodes("door.preload.retry")
    node = shown.node("door.preload")
    assert node.live_region  # read when it changes (ux.md §9)


async def test_a_single_session_loads_without_a_count(show: Show, gate: Gate) -> None:
    """One product: "Loading attendee list…" alone, then its one attendee."""
    shown = await show(VIEW, chosen=ASYNC, transport=gate)
    assert helper(shown) == LOADING
    await gate.let(shown, 11)
    assert preload_line(shown) == "Ready, works offline, 1 attendee"


async def test_offline_badges_go_online_and_retry_gets_to_ready(
    show: Show, switch: Switch
) -> None:
    """No connection: "checked online" with Retry, scanning on; Retry loads it."""
    switch.offline = True
    shown = await show(VIEW, chosen=TUTORIALS)
    assert preload_line(shown) == ONLINE
    assert helper(shown) is None  # scanning starts anyway: unknown badges go online
    retry = shown.node("door.preload.retry")
    button = retry.content
    assert isinstance(button, ft.TextButton)
    assert button.content == RETRY  # a named button
    switch.offline = False
    await shown.click(button)
    assert preload_line(shown) == READY_THREE
    assert not shown.nodes("door.preload.retry")


async def test_one_failed_session_checks_badges_online(show: Show) -> None:
    """A product that fails while the other loads is still "checked online"."""

    def answer(request: httpx.Request) -> httpx.Response:
        """Refuse product 11's list; send product 10's two buyers."""
        if request.url.path.endswith("/11/"):
            return httpx.Response(500, json={})
        return httpx.Response(200, json=[{"id": "MOCK0001", "quantity": 1}])

    shown = await show(VIEW, chosen=TUTORIALS, transport=httpx.MockTransport(answer))
    assert preload_line(shown) == ONLINE
    assert shown.nodes("door.preload.retry")


async def test_changing_the_session_mid_load_cancels_it(
    show: Show, gate: Gate, stored: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The old calls are cancelled, and only the new session's list shows."""
    location = [VIEW]
    monkeypatch.setattr(ft, "use_route_location", lambda: location[0])
    account = staff()
    shown = await show(VIEW, account, chosen=TUTORIALS, transport=gate)
    await gate.let(shown, 10)
    assert helper(shown) == f"{LOADING} 1 of 2"
    stored[STAFF_DOOR_SESSION.key] = json.dumps(to_stored(SUMMIT))
    location[0] = f"{VIEW}?picked"  # back from the picker: the key is read again
    account.nickname = "Picked"
    await shown.settle()
    assert gate.cancelled == ["11"]
    assert helper(shown) == LOADING
    await gate.let(shown, 11, 20)
    assert "11" not in gate.answered  # the first call may go twice: the clock skew
    assert preload_line(shown) == "Ready, works offline, 1 attendee"  # Linus


async def test_scanning_waits_while_the_choice_is_read_again(
    show: Show, stored: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Back from the picker, no badge is checked against the old list meanwhile."""
    location = [VIEW]
    monkeypatch.setattr(ft, "use_route_location", lambda: location[0])
    account = staff()
    shown = await show(VIEW, account, chosen=TUTORIALS)
    assert preload_line(shown) == READY_THREE
    held = asyncio.Event()

    async def slow_read(storage: Any) -> DoorChoice | None:
        """Read the choice only once the test lets it through."""
        await held.wait()
        return await read_door_session(storage)

    monkeypatch.setattr(staff_door, "read_door_session", slow_read)
    stored[STAFF_DOOR_SESSION.key] = json.dumps(to_stored(SUMMIT))
    location[0] = f"{VIEW}?picked"  # back from the picker: the key is read again
    account.nickname = "Picked"  # re-renders the tool, as the route change does
    await shown.settle()
    assert helper(shown) == LOADING
    await enter(shown, "MOCK0002:v4l1d02")  # Grace: on Tutorials' list, not Summit's
    assert BADGE_READ not in panel(shown)  # dropped: nothing was looked up
    held.set()
    await shown.settle()
    assert preload_line(shown) == "Ready, works offline, 1 attendee"  # Linus
    await enter(shown, "MOCK0002:v4l1d02")
    assert NOT_ON_LIST in panel(shown)


async def test_leaving_mid_load_cancels_it_quietly(
    show: Show, gate: Gate, caplog: pytest.LogCaptureFixture
) -> None:
    """A sign-out unmounts the tool: its calls are cancelled and nothing is logged."""
    account = staff()
    shown = await show(VIEW, account, chosen=TUTORIALS, transport=gate)
    with caplog.at_level(logging.WARNING):
        account.signed_in = False
        await shown.settle()
        await gate.let(shown, 10, 11)
    assert sorted(gate.cancelled) == ["10", "11"]
    assert gate.answered == []
    assert caplog.records == []


async def test_a_scan_says_whether_the_badge_is_on_the_list(show: Show) -> None:
    """Until admission (#766), "Badge read" with the name, or the code, and no check-in."""
    shown = await show(VIEW, chosen=TUTORIALS)
    await enter(shown, "MOCK0002:v4l1d02")
    assert (
        panel(shown)
        == f"{BADGE_READ}\nGrace Sample\n{ON_LIST}\n{NOT_CHECKED_IN}\nScan 1"
    )
    await enter(shown, "MOCK0004:v4l1d04")
    assert (
        panel(shown)
        == f"{BADGE_READ}\nMOCK0004\n{NOT_ON_LIST}\n{NOT_CHECKED_IN}\nScan 2"
    )


async def test_the_list_is_never_written(
    show: Show, stored: dict[str, Any], tmp_path: Path
) -> None:
    """No pref, no file and no outbox row holds anything of the list (D-56)."""
    database = OutboxDb(tmp_path)
    shown = await show(VIEW, chosen=TUTORIALS, outbox=database)
    assert preload_line(shown) == READY_THREE
    await enter(shown, "MOCK0002:v4l1d02")
    assert set(stored) == {STAFF_DOOR_SESSION.key}
    assert database.rows("staff@example.com", list(Status)) == []
    database.close()
    for path in tmp_path.rglob("*"):
        if path.is_file():
            data = path.read_bytes()
            assert b"Grace" not in data
            assert b"peanuts" not in data


async def test_with_announcements_the_outcome_is_said_once(show: Show) -> None:
    """iOS: "Ready" is announced, not each count, and the line is no live region."""
    prefs = Prefs(loaded=True, announcements=True)
    shown = await show(VIEW, chosen=TUTORIALS, prefs=prefs)
    assert preload_line(shown) == READY_THREE
    semantics = shown.services.semantics
    assert isinstance(semantics, MemorySemantics)
    assert semantics.announced == [READY_THREE]
    assert not shown.node("door.preload").live_region
