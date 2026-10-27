"""Tests for the focus given back after another app's window (D-372, #302).

``services.presence.Presence`` says when the app has left and come back, as the
lifecycle handler reports it; ``ui.focus_back.focus_back()`` focuses the opener then,
and ``open_link()`` passes its opener through it. The lifecycle handler's calls are
tested in ``test_app.py``; what TalkBack does with the focus is checked on an emulator
(F192).
"""

import asyncio
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from pycon_us.config import load_year
from pycon_us.memory import ViewMemory
from pycon_us.services import Services
from pycon_us.services.presence import Presence
from pycon_us.services.storage import Storage
from pycon_us.ui import focus_back as module
from pycon_us.ui.focus_back import focus_back
from pycon_us.ui.links import open_link
from tests.fakes import (
    FakePage,
    MemoryClipboard,
    MemoryHaptics,
    MemoryLauncher,
    MemoryPrefs,
    MemorySemantics,
    bound,
)

WEB = "https://us.pycon.org/2026/"


class Opener:
    """A button's stand-in that counts its ``focus()`` calls, or raises ``error``."""

    def __init__(self, error: Exception | None = None) -> None:
        """Start never focused; ``error`` is what each ``focus()`` raises."""
        self.focused = 0
        self.error = error

    async def focus(self) -> None:
        """Count the call, or raise ``error`` as an unmounted control's call does."""
        if self.error is not None:
            raise self.error
        self.focused += 1


@pytest.fixture(autouse=True)
def quick(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shorten the waits, so a test that expects no return ends in a moment."""
    monkeypatch.setattr(module, "LEAVE_WITHIN", 0.05)
    monkeypatch.setattr(module, "SETTLE_SECONDS", 0)


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
    """No departure within ``leave_within``: nothing opened, so no return is due."""
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
    """Away when the wait begins: it lasts past ``leave_within``, until the resume."""
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


async def test_back_from_another_window_the_opener_is_focused(svc: Services) -> None:
    """After the app has left and come back, the opener gets the focus once."""
    opener = Opener()
    async with focus_back(svc, opener):
        asyncio.create_task(away_and_back(svc.presence))
    assert opener.focused == 1


async def test_a_window_that_never_opened_moves_no_focus(svc: Services) -> None:
    """The app never left (no app for the link): the focus stays where it is."""
    opener = Opener()
    async with focus_back(svc, opener):
        pass
    assert opener.focused == 0


async def test_a_failed_call_moves_no_focus(svc: Services) -> None:
    """An exception from the call passes through, and nothing is focused."""
    opener = Opener()
    with pytest.raises(RuntimeError):
        async with focus_back(svc, opener):
            svc.presence.leave()
            svc.presence.come_back()
            raise RuntimeError("no activity")
    assert opener.focused == 0


async def test_an_opener_gone_from_the_page_is_logged_not_raised(
    svc: Services, caplog: pytest.LogCaptureFixture
) -> None:
    """A focus that fails (the button left the page) is logged at info, and ends there."""
    opener = Opener(RuntimeError("IconButton Control must be added to the page first"))
    with caplog.at_level(logging.INFO, logger="pycon_us.ui.focus_back"):
        async with focus_back(svc, opener):
            svc.presence.leave()
            svc.presence.come_back()
    assert caplog.messages == ["Could not give the focus back: RuntimeError"]


async def test_without_an_opener_nothing_waits(svc: Services) -> None:
    """A row or a menu item (no ``focus()``, U182) passes None, and nothing waits."""
    async with focus_back(svc, None):
        svc.presence.leave()  # never comes back: a wait would not end
    assert svc.presence.returns == 0


# ------------------------------------------------------------------ open_link


async def test_open_link_focuses_its_opener_back_from_the_browser(
    page: FakePage, svc: Services
) -> None:
    """A web link opened from a button gives the button the focus on the return."""
    opener = Opener()
    trip = asyncio.create_task(away_and_back(svc.presence))  # runs during the call
    await open_link(svc, WEB, opener=opener)
    await trip
    assert isinstance(svc.launcher, MemoryLauncher)
    assert svc.launcher.launched and opener.focused == 1


async def test_a_link_that_did_not_open_focuses_nothing(
    page: FakePage, svc: Services
) -> None:
    """A launch the platform refuses says so, and moves no focus."""
    assert isinstance(svc.launcher, MemoryLauncher)
    svc.launcher.error = RuntimeError("ACTIVITY_NOT_FOUND")
    opener = Opener()
    await open_link(svc, WEB, opener=opener)
    assert opener.focused == 0 and page.dialogs
