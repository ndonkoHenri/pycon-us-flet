"""Tests for the focus given back after another app's window (D-372, #302).

`services.presence.Presence` says when the app has left and come back, as the
lifecycle handler reports it; `ui.focus_back.focus_back()` focuses the opener then,
and `open_link()` passes its opener through it. The lifecycle handler's calls are
tested in `test_app.py`; what TalkBack does with the focus is checked on an emulator
(F192).
"""

import asyncio
import logging
from collections.abc import Iterator
from pathlib import Path

import flet as ft
import pytest

from pycon_us.config import load_year
from pycon_us.memory import ViewMemory
from pycon_us.services import Services
from pycon_us.services.presence import Presence
from pycon_us.services.storage import Storage
from pycon_us.ui import focus_back as module
from pycon_us.ui.focus_back import focus_back
from pycon_us.ui.links import open_link
from tests.fake_page import FakePage, bound
from tests.fakes import (
    MemoryClipboard,
    MemoryHaptics,
    MemoryLauncher,
    MemoryPrefs,
    MemorySemantics,
)

WEB = "https://us.pycon.org/2026/"


@pytest.fixture
def focused(monkeypatch: pytest.MonkeyPatch) -> list[ft.IconButton]:
    """Record each `IconButton.focus()` call's button instead of reaching Flutter."""
    calls: list[ft.IconButton] = []

    async def focus(self: ft.IconButton) -> None:
        calls.append(self)

    monkeypatch.setattr(ft.IconButton, "focus", focus)
    return calls


def mounted(page: FakePage, control: ft.BaseControl) -> ft.BaseControl:
    """Put `control` in the page's index, as Flet mounts it; return it."""
    page.controls[control._i] = control
    return control


@pytest.fixture(autouse=True)
def quick(quick_focus_back: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Move the focus as soon as the app is back, and allow a trip's 10 ms to leave."""
    monkeypatch.setattr(module, "SETTLE_SECONDS", 0)
    monkeypatch.setattr(module, "LEAVE_WITHIN", 0.2)


@pytest.fixture
def svc(tmp_path: Path) -> Services:
    """The session's services, with an in-memory launcher."""
    return Services(
        year=load_year(2026),
        storage=Storage(prefs=MemoryPrefs(), directory=tmp_path, year=2026),
        memory=ViewMemory(),
        semantics=MemorySemantics(),
        haptics=MemoryHaptics(),
        launcher=MemoryLauncher(),
        clipboard=MemoryClipboard(),
    )


@pytest.fixture
def page(svc: Services) -> Iterator[FakePage]:
    """A fake page, bound as Flet binds a session's page, until the test ends."""
    fake = FakePage()
    with bound(fake):
        yield fake


async def away_and_back(presence: Presence) -> None:
    """Leave and come back a moment later, as the browser's open and close do."""
    await asyncio.sleep(0.01)
    presence.leave()
    await asyncio.sleep(0.01)
    presence.come_back()


# ------------------------------------------------------------------ Presence


async def test_a_return_after_the_read_ends_the_wait() -> None:
    """The wait ends with True once the app has left and come back since the read."""
    presence = Presence()
    returns = presence.returns
    back = asyncio.create_task(presence.back_since(returns, leave_within=1))
    await away_and_back(presence)
    assert await back


async def test_an_app_that_never_leaves_ends_the_wait_with_false() -> None:
    """No departure within `leave_within`: nothing opened, so no return is due."""
    presence = Presence()
    assert not await presence.back_since(presence.returns, leave_within=0.01)


async def test_a_return_before_the_wait_counts() -> None:
    """A share sheet that closed before its call returned: the return already counts."""
    presence = Presence()
    returns = presence.returns
    presence.leave()
    presence.come_back()
    assert await asyncio.wait_for(presence.back_since(returns, leave_within=0), 1)


async def test_while_away_the_wait_lasts_until_the_return() -> None:
    """Away when the wait begins: it lasts past `leave_within`, until the resume."""
    presence = Presence()
    returns = presence.returns
    presence.leave()
    back = asyncio.create_task(presence.back_since(returns, leave_within=0))
    await asyncio.sleep(0.05)
    assert not back.done()
    presence.come_back()
    assert await back


async def test_a_closed_session_ends_the_wait_with_false() -> None:
    """A session replaced while away wakes its waiters, which focus nothing (D-147)."""
    presence = Presence()
    returns = presence.returns
    presence.leave()
    back = asyncio.create_task(presence.back_since(returns, leave_within=0))
    presence.close()
    assert not await back


# ------------------------------------------------------------------ focus_back


async def test_back_from_another_window_the_opener_is_focused(
    page: FakePage, svc: Services, focused: list[ft.IconButton]
) -> None:
    """After the app has left and come back, the opener gets the focus once."""
    opener = mounted(page, ft.IconButton(ft.Icons.SHARE))
    async with focus_back(svc, opener):
        away = asyncio.create_task(away_and_back(svc.presence))
    await away
    assert focused == [opener]


async def test_the_control_mounted_on_the_return_is_the_one_focused(
    page: FakePage, svc: Services, focused: list[ft.IconButton]
) -> None:
    """A render meanwhile mounts a new button under the opener's id: it gets the focus.

    The event's own button is then detached, and its `focus()` refused (F192).
    """
    opener = ft.IconButton(ft.Icons.SHARE)
    rebuilt = ft.IconButton(ft.Icons.SHARE)
    rebuilt._i = opener._i  # what Flet's reconciler does (`_migrate_state`)
    mounted(page, rebuilt)
    async with focus_back(svc, opener):
        away = asyncio.create_task(away_and_back(svc.presence))
    await away
    assert focused == [rebuilt]


async def test_a_window_that_never_opened_moves_no_focus(
    page: FakePage, svc: Services, focused: list[ft.IconButton]
) -> None:
    """The app never left (no app for the link): the focus stays where it is."""
    opener = mounted(page, ft.IconButton(ft.Icons.SHARE))
    async with focus_back(svc, opener):
        pass
    assert focused == []


async def test_a_failed_call_moves_no_focus(
    page: FakePage, svc: Services, focused: list[ft.IconButton]
) -> None:
    """An exception from the call passes through, and nothing is focused."""
    opener = mounted(page, ft.IconButton(ft.Icons.SHARE))
    with pytest.raises(RuntimeError):
        async with focus_back(svc, opener):
            svc.presence.leave()
            svc.presence.come_back()
            raise RuntimeError("no activity")
    assert focused == []


async def test_a_session_closed_while_settling_moves_no_focus(
    page: FakePage,
    svc: Services,
    focused: list[ft.IconButton],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A close during the settling delay ends the wait at once, and focuses nothing.

    A replaced session stops its work (D-147): a `focus()` sent after the close
    would wait for an answer Flet never cancels.
    """
    monkeypatch.setattr(module, "SETTLE_SECONDS", 60)
    opener = mounted(page, ft.IconButton(ft.Icons.SHARE))

    async def trip() -> None:
        async with focus_back(svc, opener):
            svc.presence.leave()
            svc.presence.come_back()

    task = asyncio.create_task(trip())
    await asyncio.sleep(0.05)  # back, and settling
    assert not task.done()
    svc.close()
    await asyncio.wait_for(task, 1)
    assert focused == []


@pytest.mark.parametrize(
    "control",
    [None, ft.ListTile(title=ft.Text("Website"))],
    ids=["gone from the page", "no focus() (U182)"],
)
async def test_an_opener_that_cannot_take_the_focus_is_left_alone(
    page: FakePage, svc: Services, control: ft.BaseControl | None
) -> None:
    """An opener no longer mounted, or a row without `focus()`, ends it quietly."""
    opener = ft.ListTile(title=ft.Text("Website"))
    if control is not None:
        control._i = opener._i
        mounted(page, control)
    async with focus_back(svc, opener):
        svc.presence.leave()
        svc.presence.come_back()


async def test_a_refused_focus_is_logged_not_raised(
    page: FakePage,
    svc: Services,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A focus Flutter does not answer is logged at info with its class, and ends there."""

    async def refuse(self: ft.IconButton) -> None:
        raise TimeoutError("focus")

    monkeypatch.setattr(ft.IconButton, "focus", refuse)
    opener = mounted(page, ft.IconButton(ft.Icons.SHARE))
    with caplog.at_level(logging.INFO, logger="pycon_us.ui.focus_back"):
        async with focus_back(svc, opener):
            svc.presence.leave()
            svc.presence.come_back()
    assert caplog.messages == ["Could not give the focus back: TimeoutError"]


async def test_without_an_opener_nothing_waits(page: FakePage, svc: Services) -> None:
    """A row or a menu item passes None (U182), and nothing waits for a return."""
    async with focus_back(svc, None):
        svc.presence.leave()  # never comes back: a wait would not end
    assert svc.presence.returns == 0


# ------------------------------------------------------------------ open_link


async def test_open_link_focuses_its_opener_back_from_the_browser(
    page: FakePage, svc: Services, focused: list[ft.IconButton]
) -> None:
    """A web link opened from a button gives the button the focus on the return."""
    opener = mounted(page, ft.IconButton(ft.Icons.ADD))
    trip = asyncio.create_task(away_and_back(svc.presence))  # runs during the call
    await open_link(svc, WEB, opener=opener)
    await trip
    assert isinstance(svc.launcher, MemoryLauncher)
    assert svc.launcher.launched and focused == [opener]


async def test_a_link_that_did_not_open_focuses_nothing(
    page: FakePage, svc: Services, focused: list[ft.IconButton]
) -> None:
    """A launch the platform refuses says so, and moves no focus."""
    assert isinstance(svc.launcher, MemoryLauncher)
    svc.launcher.error = RuntimeError("ACTIVITY_NOT_FOUND")
    opener = mounted(page, ft.IconButton(ft.Icons.ADD))
    await open_link(svc, WEB, opener=opener)
    assert focused == [] and page.dialogs
