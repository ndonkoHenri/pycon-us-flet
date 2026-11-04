"""When the status strip is a live region: only just after its line changes (D-498, #1102).

`use_just_changed()` runs in a real Flet session (`tests/sessions.py`), since the strip's
other tests answer its hooks with one shared state (`tests/strip.py`). What TalkBack says
of it is heard on a device (the PR).
"""

import asyncio
from collections.abc import Callable

import flet as ft
import pytest

from pycon_us.ui import status_strip
from tests.sessions import rendering, settle


async def test_only_a_change_makes_the_strip_live_and_only_for_a_while(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A strip that opens with its line isn't live; a new line is, then stops being."""
    monkeypatch.setattr(status_strip, "SAID_SECONDS", 0.05)
    live: list[bool] = []
    change: list[Callable[[str], None]] = []

    @ft.component
    def Watch() -> ft.Control:
        """Hold a line and record what the hook says of it at each render."""
        line, set_line = ft.use_state("Offline")
        change[:] = [set_line]
        live.append(status_strip.use_just_changed(line))
        return ft.Text(line)

    async with rendering(Watch):
        await settle()
        assert live[-1] is False  # as a screen opens, or comes back on Back

        change[0]("Updating…")
        await settle()
        assert live[-1] is True  # in the render with the new words

        change[0]("Offline")  # a refresh that failed: back to the words it opened with
        await settle()
        assert live[-1] is True  # its outcome is said

        await asyncio.sleep(0.1)
        await settle()
        assert live[-1] is False
