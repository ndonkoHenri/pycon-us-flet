"""Tests for the hand-out sheet's late client events and unmount (#769, #781's review).

Flutter reports a sheet's dismissal after its exit animation, so it may come after the
next sheet opened; the pinned Flet reads ``dismissible`` only as the sheet opens, so a
dismissal may come while Hand out is sending (#782); and a lookup may answer after the
screen is gone. The screen tests share ``tests/test_swag_sheet.py``'s fixtures and
helpers; the unmount one renders the hook alone, as ``tests/test_flet_effects.py`` does.
"""

import asyncio
from collections.abc import Callable
from pathlib import Path

import flet as ft
import httpx

from pycon_us import swag
from pycon_us.config import load_year
from pycon_us.core.badges import ScanResult
from pycon_us.core.check_in import AttendeeProducts, Item
from pycon_us.favorites import Favorites
from pycon_us.prefs import Prefs
from pycon_us.screens.staff_swag import HAND_OUT_OPEN
from pycon_us.services.endpoints import REDEEM
from pycon_us.state import Conference
from pycon_us.ui.swag_sheet import SENDING, use_swag_sheet
from tests import test_swag_sheet
from tests.api_clients import Recorder
from tests.scan_rig import panel
from tests.sessions import memory_services, provide, rendering, settle
from tests.test_staff_swag import Show, Switch
from tests.test_swag import badge
from tests.test_swag_sheet import (
    ADA,
    GRACE,
    button,
    helper,
    in_sheet,
    scan,
    sheet,
    until,
    words,
)

online, show = test_swag_sheet.online, test_swag_sheet.show
state, recorder, switch = (
    test_swag_sheet.state,
    test_swag_sheet.recorder,
    test_swag_sheet.switch,
)
stored, now = test_swag_sheet.stored, test_swag_sheet.now


async def test_a_late_dismissal_of_the_last_sheet_leaves_the_next_one_open(
    show: Show, now: list[float]
) -> None:
    """Ada's sheet's dismissal, arriving under Grace's sheet, closes nothing."""
    shown = await show()
    first = await scan(shown, ADA)
    ada_sheet = sheet(shown)
    assert ada_sheet is not None
    await shown.click(in_sheet(shown, "swag.cancel"))
    await first
    now[0] += 5
    second = await scan(shown, GRACE)
    await shown.event(ada_sheet, "dismiss")  # after its exit animation
    assert sheet(shown) is not None
    assert not second.done()
    assert helper(shown) == HAND_OUT_OPEN
    await shown.click(in_sheet(shown, "swag.cancel"))
    await second


async def test_a_dismissal_while_sending_keeps_the_pause_until_the_answer(
    show: Show, switch: Switch, recorder: Recorder
) -> None:
    """Back or the scrim during a held redeem: still paused; the answer then shows."""
    shown = await show()
    submit = await scan(shown, GRACE)
    held = asyncio.Event()

    class Slow(httpx.AsyncBaseTransport):
        """The recorder, answering a redeem once ``held`` is set."""

        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            """Wait for ``held`` on a redeem, then let the recorder answer."""
            if request.url.path.endswith(REDEEM.path):
                await held.wait()
            return await recorder.handle_async_request(request)

    switch.inner = Slow()
    sending = asyncio.create_task(shown.click(button(shown)))
    await until(shown, lambda: words(button(shown)) == SENDING)
    open_sheet = sheet(shown)
    assert open_sheet is not None
    shown.session.apply_patch(open_sheet._i, {"open": False})  # as the client closes it
    await shown.event(open_sheet, "dismiss")
    assert helper(shown) == HAND_OUT_OPEN
    assert not submit.done()
    held.set()
    await sending
    await submit
    assert panel(shown).startswith("Handed out 1 item")
    assert helper(shown) is None


async def test_an_offer_after_unmount_returns_none_at_once(tmp_path: Path) -> None:
    """A lookup that answers after the screen is gone ends its scan, opening nothing."""
    handlers: list[swag.OfferHandler] = []
    setters: list[Callable[[bool], None]] = []
    svc = memory_services(load_year(2026), tmp_path)

    @ft.component
    def Child() -> ft.Control:
        """Return nothing to see; keep the hook's ``offer``."""
        handlers.append(use_swag_sheet().offer)
        return ft.Text("swag")

    @ft.component
    def Root() -> ft.Control:
        """Return the child under the stores while ``mounted``, else nothing."""
        mounted, set_mounted = ft.use_state(True)
        setters.append(set_mounted)
        body = provide(svc, Conference(), Prefs(loaded=True), Favorites(), Child)
        return ft.Column([body] if mounted else [])

    offer = swag.Offer(
        badge(1),
        0.0,
        AttendeeProducts("MOCK0001", "Ada", (("T-Shirt", (Item(30, "T", 2, 2),)),)),
    )
    async with rendering(Root):
        setters[-1](False)
        await settle()
        result: ScanResult | None = await asyncio.wait_for(handlers[-1](offer), 1)
        assert result is None
    svc.close()
