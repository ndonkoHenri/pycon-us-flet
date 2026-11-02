"""Door check on a return from its picker with the reads held (#887; D-56, D-433).

Back from the picker, the session shown is the old one until the read of the stored
key lands, and a check-in is decided against that session's list. Flet cancels a read
still running when the location changes, so out and back the state still holds the read
from before the picker, made at the very location the screen is back at: only a token
of the arrival tells it from the new one. Each test holds the reads at a gate in a real
Flet session over the mock's own transport (``tests/door_rig.py``). The location and
the route are set by hand, as ``tests/test_door_preload.py``'s Back tests do.
"""

import asyncio
import json
from typing import Any

import flet as ft
import pytest

from pycon_us.core.door_sessions import DoorChoice, to_stored
from pycon_us.core.outbox import Row, Status
from pycon_us.door_check import CHECKED_IN, NOT_REGISTERED
from pycon_us.door_choice import read_door_session
from pycon_us.screens import staff_door
from pycon_us.screens.door_preload import LOADING
from pycon_us.services.pref_keys import staff_door_session
from pycon_us.services.storage import Storage
from tests import door_rig
from tests.door_rig import (
    PICKER,
    SUMMIT,
    TUTORIALS,
    VIEW,
    Show,
    chip_text,
    helper,
    staff,
)
from tests.harness import Shown
from tests.picker_rig import Go, going
from tests.scan_rig import enter, panel

stored, switch, show = door_rig.stored, door_rig.switch, door_rig.show

GRACE = "MOCK0002:v4l1d02"
"""On Tutorials' list, not Summit's."""

LINUS = "MOCK0003:v4l1d03"
"""On both lists."""


@pytest.fixture
def gate(monkeypatch: pytest.MonkeyPatch) -> asyncio.Event:
    """An open gate the choice's reads pass; a test clears it to hold them."""
    opened = asyncio.Event()
    opened.set()

    async def held(storage: Storage) -> DoorChoice | None:
        """Read the stored choice only once the gate is open: it is current then."""
        await opened.wait()
        return await read_door_session(storage)

    monkeypatch.setattr(staff_door, "read_door_session", held)
    return opened


@pytest.fixture
def go(monkeypatch: pytest.MonkeyPatch) -> Go:
    """Return a function that changes the location and the route from the scan screen's."""
    return going(monkeypatch, VIEW)


def rows(shown: Shown) -> list[Row]:
    """The door account's outbox rows, of any status."""
    outbox = shown.services.outbox
    assert outbox is not None
    return outbox.rows("staff@example.com", list(Status)) or []


async def test_a_scan_on_a_return_with_the_reads_held_checks_nobody_in(
    show: Show, stored: dict[str, Any], gate: asyncio.Event, go: Go
) -> None:
    """Grace, on the replaced session's list only, gets no row; then Summit's list rules.

    Before the read lands the field says why. Once it lands, she is not registered,
    and Linus's check-in is a row for Summit's product.
    """
    account = staff()
    shown = await show(VIEW, account, chosen=TUTORIALS)
    gate.clear()
    await go(shown, account, PICKER)
    stored[staff_door_session(2026).key] = json.dumps(to_stored(SUMMIT))
    await go(shown, account, VIEW)
    await enter(shown, GRACE)
    assert rows(shown) == []
    assert CHECKED_IN not in panel(shown)
    assert helper(shown) == LOADING
    gate.set()
    await shown.settle()
    assert chip_text(shown) == SUMMIT.label
    assert helper(shown) is None
    await enter(shown, GRACE)
    assert NOT_REGISTERED in panel(shown)
    assert rows(shown) == []
    await enter(shown, LINUS)
    (row,) = rows(shown)
    assert row.key == "MOCK0003"
    assert "product-redeem-20" in row.payload


async def test_a_cancel_with_the_reads_held_waits_too_then_takes_the_focus(
    show: Show, gate: asyncio.Event, go: Go, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The session stands, but scanning and the focus wait for the read (D-438)."""
    focused: list[ft.TextField] = []

    async def focus(field: ft.TextField) -> None:
        """Count the field's focus requests."""
        focused.append(field)

    monkeypatch.setattr(ft.TextField, "focus", focus)
    account = staff()
    shown = await show(VIEW, account, chosen=TUTORIALS)
    gate.clear()
    await go(shown, account, PICKER)
    focused.clear()
    await go(shown, account, VIEW)
    assert helper(shown) == LOADING
    assert focused == []
    gate.set()
    await shown.settle()
    assert helper(shown) is None
    assert len(focused) == 1
    await enter(shown, GRACE)
    (row,) = rows(shown)
    assert row.key == "MOCK0002"
