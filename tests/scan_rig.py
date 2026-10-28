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
from pycon_us.ui import scan_feedback, scan_screen
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
                    title="Lead scanner", on_badge=rig.on_badge, paused=rig.paused
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
    """What the result panel's live region says."""
    node = shown.node("scan.result")
    assert node.live_region and node.container  # said as it changes (ux.md §9)
    return str(node.label)
