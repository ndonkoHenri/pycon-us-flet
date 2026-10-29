"""The scan screen's test rig: a recording handler, a held clock and a live session.

Shared by ``tests/test_scan_screen.py`` and ``tests/test_scan_feedback.py``: the screen
runs in a real Flet session (``tests/harness.py``) around ``Rig.on_badge``; entry is
what Flutter reports: the field's value, a change event, then the submit event with
the text. The clock is ``ui/scan_screen.py``'s ``clock()``, held by the rig.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from pathlib import Path

import flet as ft
import pytest

from pycon_us.config import load_year
from pycon_us.core.badges import Badge, ScanOutcome, ScanResult
from pycon_us.prefs import Prefs
from pycon_us.staff import Staff
from pycon_us.state import Conference
from pycon_us.ui import scan_clear, scan_feedback, scan_screen
from pycon_us.ui.scan_result import READY
from pycon_us.ui.scan_screen import ScanScreen
from tests import harness

VIEW = "/more/staff/lead"

ACCEPTED = ScanResult(ScanOutcome.ACCEPTED, "Checked in", "Ada Lovelace")

type Show = Callable[..., Awaitable[harness.Shown]]


class Rig:
    """What the screen under test was given and did: its handler's calls and focus."""

    def __init__(self) -> None:
        """Start with nothing handled, a clock at 100 s and the handler answering."""
        self.badges: list[Badge] = []
        self.focused = 0
        self.now = 100.0
        self.result = ACCEPTED
        self.gate: asyncio.Event | None = None
        self.paused: str | None = None
        self.clear_after: float | None = None
        self.clear_in_background = False

    async def on_badge(self, badge: Badge) -> ScanResult:
        """Record the badge; wait for ``gate`` when one is set; return ``result``."""
        self.badges.append(badge)
        if self.gate is not None:
            await self.gate.wait()
        return self.result


@pytest.fixture
def rig(monkeypatch: pytest.MonkeyPatch) -> Rig:
    """A rig whose clock is the screen's, which counts the field's focus calls.

    Two haptic pulses follow each other at once, so a test never waits for the gap.
    """
    held = Rig()

    async def focus(_: ft.TextField) -> None:
        held.focused += 1

    monkeypatch.setattr(ft.TextField, "focus", focus)
    monkeypatch.setattr(scan_screen, "clock", lambda: held.now)
    monkeypatch.setattr(scan_feedback, "GAP_S", 0)
    return held


class Timer:
    """Stands in for the clear's timer (``ui/scan_clear.py``'s ``wait``): held until ``ring``."""

    def __init__(self) -> None:
        """Start with no timer asked for, and none rung."""
        self.waits: list[float] = []
        self.rung = asyncio.Event()

    async def wait(self, seconds: float) -> None:
        """Record the seconds asked for, then wait for ``ring()``."""
        self.waits.append(seconds)
        await self.rung.wait()

    def ring(self) -> None:
        """Let the timers waiting now end; a later one waits for the next ring."""
        self.rung.set()
        self.rung = asyncio.Event()


@pytest.fixture
def timer(monkeypatch: pytest.MonkeyPatch) -> Timer:
    """The clear's timer, held: a test rings it instead of waiting 15 s."""
    held = Timer()
    monkeypatch.setattr(scan_clear, "wait", held.wait)
    return held


async def pause(shown: harness.Shown) -> None:
    """Send the app to the background as ``app.py`` does on ``pause`` (D-420)."""
    shown.services.foreground.clear()
    shown.services.background.set()
    await shown.settle()


async def resume(shown: harness.Shown) -> None:
    """Bring the app back as ``on_resume()`` does."""
    shown.services.background.clear()
    shown.services.foreground.set()
    await shown.settle()


@pytest.fixture
async def show(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rig: Rig
) -> AsyncIterator[Show]:
    """Return a function that renders the scan screen around the rig's handler."""
    async with AsyncExitStack() as stack:

        async def render(
            screen: Callable[[], ft.Control] | None = None,
            *,
            prefs: Prefs | None = None,
            staff: Staff | None = None,
        ) -> harness.Shown:
            """Render ``screen``, by default a scan screen titled "Lead scanner".

            Args:
                screen: The component to render instead of the default screen.
                prefs: The ``Prefs`` store (announcements on, say).
                staff: The ``Staff`` store the sync chip counts.
            """

            @ft.component
            def Scan() -> ft.Control:
                return ScanScreen(
                    title="Lead scanner",
                    on_badge=rig.on_badge,
                    paused=rig.paused,
                    clear_after=rig.clear_after,
                    clear_in_background=rig.clear_in_background,
                )

            return await stack.enter_async_context(
                harness.showing(
                    screen or Scan,
                    scan_screen,
                    year=load_year(2026),
                    conference=Conference(),
                    tmp_path=tmp_path,
                    monkeypatch=monkeypatch,
                    view_path=VIEW,
                    route=VIEW,
                    prefs=prefs,
                    staff=staff,
                )
            )

        yield render


def entry(shown: harness.Shown) -> ft.TextField:
    """The mounted badge code field."""
    (found,) = shown.find(ft.TextField)
    return found


async def enter(shown: harness.Shown, text: str) -> None:
    """Type ``text`` as Flutter reports it, then press Enter (a HID scanner's way)."""
    field = entry(shown)
    shown.session.apply_patch(field._i, {"value": text})
    await shown.event(field, "change", text)
    await shown.event(field, "submit", text)


def panel(shown: harness.Shown) -> str:
    """What the result panel says: a live region while a result shows (ux.md §9).

    "Ready to scan", before the first result or after a clear, is no live region, so
    a clear is not said (#762).
    """
    node = shown.node("scan.result")
    label = str(node.label)
    assert node.container
    assert node.live_region is not label.startswith(f"{READY}\n")
    return label
