"""Tests for the hand-out sheet on Swag pickup (#769; SHIRT-03, SHIRT-04).

The screen runs in a real Flet session over the mock's own transport, as in
`tests/test_staff_swag.py`, whose fixtures these share, with both categories chosen
and the mock's state at hand. A scan with items left opens the sheet and waits for it,
so the submit runs as a task (as Flet runs every event) while the test taps the sheet;
taps are what Flutter reports: a checkbox's new value, then the event.
"""

import asyncio
from collections.abc import Callable
from typing import Any, cast

import flet as ft
import httpx
import pytest
from flet.utils.object_model import patch_dataclass

from pycon_us.screens.staff_swag import HAND_OUT_OPEN
from pycon_us.services.endpoints import REDEEM
from pycon_us.services.pref_keys import staff_swag_categories
from pycon_us.swag import ALREADY, NOT_CONFIRMED, READY, RESCAN
from pycon_us.ui import scan_feedback, scan_screen
from pycon_us.ui.swag_sheet import PICKED_UP, SENDING
from tests import test_staff_swag
from tests.api_clients import Recorder
from tests.filter_sheet import descendants
from tests.harness import Shown
from tests.mock_calls import state_at
from tests.scan_rig import panel
from tests.test_staff_swag import Show, Switch
from tools.mock_api.state import MockState, Redemption
from tools.mock_api.transport import mock_transport

online, show = test_staff_swag.online, test_staff_swag.show

ADA = "MOCK0001:v4l1d01"
GRACE = "MOCK0002:v4l1d02"


@pytest.fixture
def state() -> MockState:
    """The mock's freshly seeded state, which the test reads and changes."""
    return state_at()


@pytest.fixture
def recorder(state: MockState) -> Recorder:
    """The mock's transport over `state`, keeping every request the screen sends."""
    return Recorder(mock_transport(state))


@pytest.fixture
def switch(recorder: Recorder) -> Switch:
    """The transport `show` renders over: the recorder, online."""
    return Switch(recorder)


@pytest.fixture
def stored() -> dict[str, Any]:
    """The device's SharedPreferences, with both swag categories chosen."""
    return {staff_swag_categories(2026).key: ["3", "4"]}


@pytest.fixture(autouse=True)
def now(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """The scan screen's clock, which a test moves past the 4 s cooldown.

    A duplicate's two haptic pulses follow each other at once, so no scan waits.
    """
    held = [100.0]
    monkeypatch.setattr(scan_screen, "clock", lambda: held[0])
    monkeypatch.setattr(scan_feedback, "GAP_S", 0)
    return held


def sheet(shown: Shown) -> ft.BottomSheet | None:
    """The open hand-out sheet, or None."""
    dialogs = shown.session.page._dialogs.controls  # pyright: ignore[reportPrivateUsage]
    found = [d for d in dialogs if isinstance(d, ft.BottomSheet) and d.open]
    assert len(found) <= 1
    return found[0] if found else None


def in_sheet(shown: Shown, identifier: str) -> Any:
    """The control under the open sheet's semantics node `identifier`."""
    current = sheet(shown)
    assert current is not None
    return next(
        c.content
        for c in descendants(current)
        if isinstance(c, ft.Semantics) and c.identifier == identifier
    )


def row(shown: Shown, product_id: int) -> tuple[str, str | None, bool | None, bool]:
    """An item row's title, the line under it, its checkbox's value and whether disabled."""
    tile = cast(ft.ListTile, in_sheet(shown, f"swag.item.{product_id}"))
    box = cast(ft.Checkbox, tile.leading)
    return (
        str(tile.title),
        cast(str | None, tile.subtitle),
        box.value,
        bool(tile.disabled),
    )


def button(shown: Shown) -> ft.FilledButton:
    """The sheet's Hand out button."""
    return cast(ft.FilledButton, in_sheet(shown, "swag.hand_out"))


def words(control: ft.FilledButton) -> str:
    """A button's words, its ring left out."""
    texts = [c for c in descendants(control) if isinstance(c, ft.Text)]
    return " ".join(str(t.value) for t in texts)


def helper(shown: Shown) -> str | None:
    """The scan field's helper line: why scanning is paused, or None."""
    return cast(str | None, field(shown).helper)


def field(shown: Shown) -> ft.TextField:
    """The scan screen's badge code field."""
    return cast(ft.TextField, shown.node("scan.entry").content)


async def until(shown: Shown, done: Callable[[], bool]) -> None:
    """Let the session run until `done`, as the mock's answers take a few turns."""
    for _ in range(50):
        if done():
            return
        await shown.settle()
    raise AssertionError("never happened")


async def scan(shown: Shown, text: str) -> asyncio.Task[None]:
    """Enter `text` and press Enter; return the submit, running until the sheet closes."""
    entry = field(shown)
    shown.session.apply_patch(entry._i, {"value": text})
    await shown.event(entry, "change", text)
    submit = asyncio.create_task(shown.event(entry, "submit", text))
    await until(shown, lambda: sheet(shown) is not None or submit.done())
    return submit


async def untick(shown: Shown, product_id: int) -> None:
    """Untick an item: its new value, then the change event."""
    box = cast(ft.Checkbox, row_tile(shown, product_id).leading)
    patch_dataclass(box, {"value": False})
    await shown.event(box, "change", False)


def row_tile(shown: Shown, product_id: int) -> ft.ListTile:
    """An item's row in the open sheet."""
    return cast(ft.ListTile, in_sheet(shown, f"swag.item.{product_id}"))


def redeems(recorder: Recorder) -> int:
    """How many `redeem` POSTs the screen sent."""
    return sum(r.url.path.endswith(REDEEM.path) for r in recorder.sent)


def ada_redeemed(state: MockState) -> list[tuple[int, int]]:
    """Ada's products and quantities the mock recorded, sorted."""
    return sorted(
        (r.product_id, r.quantity)
        for r in state.redemptions
        if r.access_code == "MOCK0001"
    )


async def test_items_left_open_pre_ticked_and_one_tap_hands_them_all_out(
    show: Show,
    state: MockState,
    now: list[float],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ada: both ticked, "Hand out 3 items"; a tap: "Handed out 3 items"; rescan: done."""
    focused: list[ft.TextField] = []

    async def focus(control: ft.TextField) -> None:
        """Count the focus put back in the field."""
        focused.append(control)

    shown = await show()
    monkeypatch.setattr(ft.TextField, "focus", focus)
    submit = await scan(shown, ADA)
    assert helper(shown) == HAND_OUT_OPEN
    assert row(shown, 30) == ("2× T-Shirt (M)", None, True, False)
    assert row(shown, 40) == ("1× Swag Bag", None, True, False)
    assert words(button(shown)) == "Hand out 3 items"
    texts = [str(c.value) for c in descendants(sheet(shown)) if isinstance(c, ft.Text)]
    assert texts[:2] == ["Hand out to Ada Example", "Swag Bag"]  # categories A-Z
    await shown.click(button(shown))
    await submit
    assert sheet(shown) is None
    assert panel(shown).startswith("Handed out 3 items\nAda Example\n")
    assert ada_redeemed(state) == [(30, 2), (40, 1)]
    assert helper(shown) is None and focused  # back in the field
    now[0] += 5
    assert (await scan(shown, ADA)).done()  # nothing left: no sheet
    assert panel(shown).startswith(f"{ALREADY}\nAda Example")


async def test_an_unticked_item_lowers_the_count_and_stays_available(
    show: Show, state: MockState, now: list[float]
) -> None:
    """The bag unticked: "Hand out 2 items"; the next scan still offers the bag."""
    shown = await show()
    submit = await scan(shown, ADA)
    await untick(shown, 40)
    assert row(shown, 40)[2] is False
    assert words(button(shown)) == "Hand out 2 items"
    await untick(shown, 30)
    assert words(button(shown)) == "Hand out 0 items" and button(shown).disabled
    box = cast(ft.Checkbox, row_tile(shown, 30).leading)
    patch_dataclass(box, {"value": True})
    await shown.event(box, "change", True)
    await shown.click(button(shown))
    await submit
    assert panel(shown).startswith("Handed out 2 items")
    assert ada_redeemed(state) == [(30, 2)]
    now[0] += 5
    await scan(shown, ADA)
    assert row(shown, 40) == ("1× Swag Bag", None, True, False)
    assert words(button(shown)) == "Hand out 1 item"


async def test_picked_up_items_are_disabled_and_say_why(
    show: Show, state: MockState
) -> None:
    """The bag taken, one T-shirt taken: "Picked up", and "1 already picked up"."""
    state.redemptions += [
        Redemption("MOCK0001", 40, 1, "before"),
        Redemption("MOCK0001", 30, 1, "before"),
    ]
    shown = await show()
    await scan(shown, ADA)
    assert row(shown, 40) == ("1× Swag Bag", PICKED_UP, False, True)
    assert row(shown, 30) == ("1× T-Shirt (M)", "1 already picked up", True, False)
    assert words(button(shown)) == "Hand out 1 item"


async def test_a_lost_answer_says_not_confirmed_and_a_rescan_shows_the_truth(
    show: Show, state: MockState, recorder: Recorder, now: list[float]
) -> None:
    """`lost_response` with the sheet open: "Not confirmed", rescan; sent once."""
    shown = await show()
    submit = await scan(shown, GRACE)
    state.faults.inject("lost_response")
    await shown.click(button(shown))
    await submit
    assert panel(shown).startswith(f"{NOT_CONFIRMED}\nGrace Sample\n{RESCAN}")
    assert redeems(recorder) == 1
    now[0] += 5
    assert (await scan(shown, GRACE)).done()
    assert panel(shown).startswith(ALREADY)  # the mock did record it


async def test_a_double_tap_sends_once_with_the_ring_meanwhile(
    show: Show, switch: Switch, recorder: Recorder
) -> None:
    """Two taps before the answer: one POST; "Handing out…" and disabled meanwhile."""
    shown = await show()
    submit = await scan(shown, GRACE)
    held = asyncio.Event()

    class Slow(httpx.AsyncBaseTransport):
        """The recorder, answering a redeem once `held` is set."""

        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            """Wait for `held` on a redeem, then let the recorder answer."""
            if request.url.path.endswith(REDEEM.path):
                await held.wait()
            return await recorder.handle_async_request(request)

    switch.inner = Slow()
    hand_out = button(shown)
    first = asyncio.create_task(shown.click(hand_out))
    await until(shown, lambda: words(button(shown)) == SENDING)
    assert button(shown).disabled
    await shown.click(hand_out)  # the stale control, as a tap already on its way
    held.set()
    await first
    await submit
    assert redeems(recorder) == 1
    assert panel(shown).startswith("Handed out 1 item")


async def test_cancel_sends_nothing_and_keeps_the_lookup_on_the_panel(
    show: Show, recorder: Recorder
) -> None:
    """Cancel: no POST, "Ready to hand out" and the lines; a dismissal is the same."""
    shown = await show()
    submit = await scan(shown, ADA)
    await shown.click(in_sheet(shown, "swag.cancel"))
    await submit
    assert sheet(shown) is None
    assert panel(shown).startswith(f"{READY}\nAda Example")
    assert redeems(recorder) == 0
    assert helper(shown) is None


async def test_a_hid_submit_while_the_sheet_is_open_is_dropped(
    show: Show, now: list[float]
) -> None:
    """Grace's badge under Ada's sheet: dropped with its text; the sheet stays Ada's."""
    shown = await show()
    submit = await scan(shown, ADA)
    now[0] += 5
    entry = field(shown)
    shown.session.apply_patch(entry._i, {"value": GRACE})
    await shown.event(entry, "submit", GRACE)
    assert field(shown).value == ""
    sheet_now = sheet(shown)
    assert sheet_now is not None
    assert "Hand out to Ada Example" in [
        str(c.value) for c in descendants(sheet_now) if isinstance(c, ft.Text)
    ]
    await shown.click(in_sheet(shown, "swag.cancel"))
    await submit
