"""The status strip's fixtures and lookups, for its two test modules (#285, #264).

``test_status_strip.py`` (the line, the layout, the live region and the refreshes) and
``test_status_strip_ticks.py`` (the minute tick, ``use_minute()`` and the automatic
refreshes) render the strip's body outside a renderer: the hooks it calls
(``ft.use_effect``, ``ft.use_state`` and the store hooks) are answered by ``Hooks``.
The services, the page and the store are ``tests/chrome.py``'s; a module takes both
modules' fixtures by assigning them to its own names, as that module's docstring says:
``chrome.year``, ``chrome.svc`` and ``chrome.conference`` too, which this ``hooks``
takes by name.
"""

import asyncio
import inspect
from collections.abc import Iterator
from zoneinfo import ZoneInfo

import flet as ft
import pytest

from pycon_us.services import Services, api
from pycon_us.state import Conference
from pycon_us.theme import DARK_TOKENS
from pycon_us.ui import status_strip
from pycon_us.ui.status_strip import StatusStrip
from tests.fakes import Hooks

PACIFIC = ZoneInfo("America/Los_Angeles")


@pytest.fixture
def hooks(
    monkeypatch: pytest.MonkeyPatch, svc: Services, conference: Conference
) -> Hooks:
    """Answer the strip's hooks, with the dark scheme's tokens."""
    hooks = Hooks()
    monkeypatch.setattr(ft, "use_effect", hooks.use_effect)
    monkeypatch.setattr(ft, "use_state", hooks.use_state)
    monkeypatch.setattr(status_strip, "use_services", lambda: svc)
    monkeypatch.setattr(status_strip, "use_conference", lambda: conference)
    monkeypatch.setattr(status_strip, "use_tokens", lambda: DARK_TOKENS)
    return hooks


def render_strip(*, auto_refresh: bool = False) -> ft.Semantics:
    """Run the strip's body once and return the strip."""
    # The body, without @ft.component.
    strip = inspect.unwrap(StatusStrip)(auto_refresh=auto_refresh)
    assert isinstance(strip, ft.Semantics)
    return strip


def strip_parts(strip: ft.Semantics) -> tuple[ft.Text, ft.TextButton, ft.ProgressBar]:
    """The strip's line, Refresh and bar, checking the layout that holds them."""
    box = strip.content
    assert isinstance(box, ft.Container)
    column = box.content
    assert isinstance(column, ft.Column)
    padded, slot = column.controls
    assert isinstance(slot, ft.Container)
    assert slot.height == 2  # kept while the bar hides: nothing moves (ux.md §3.9)
    progress = slot.content
    assert isinstance(padded, ft.Container)
    assert isinstance(padded.content, ft.Row)
    # Room around a line that wraps at 200 % text (ux.md §3.9).
    assert padded.padding == ft.Padding.only(left=16, top=4, right=8, bottom=4)
    line_box, button_box = padded.content.controls
    assert isinstance(line_box, ft.Container)
    assert isinstance(button_box, ft.Container)
    line_row, button = line_box.content, button_box.content
    assert isinstance(line_row, ft.Row)
    icon, text = line_row.controls
    assert isinstance(icon, ft.Icon)
    assert isinstance(text, ft.Text)
    assert isinstance(button, ft.TextButton)
    assert isinstance(progress, ft.ProgressBar)
    return text, button, progress


class Network:
    """Stands in for ``api.fetch_feed``: counts requests, each held until released.

    Released, it answers with an empty body, which ``feed.process`` rejects: a failed
    refresh, which is enough to end it; or it raises ``error`` when one is set.
    """

    def __init__(self) -> None:
        """Start with no request, both events clear and no error to raise."""
        self.requests = 0
        self.arrived = asyncio.Event()
        self.released = asyncio.Event()
        self.error: Exception | None = None

    async def fetch_feed(self, url: str, **_: object) -> bytes:
        """Count the request, then hold it until ``released`` is set.

        Then raise ``error`` when one is set, or answer with an empty body.
        """
        self.requests += 1
        self.arrived.set()
        await self.released.wait()
        if self.error is not None:
            raise self.error
        return b""


@pytest.fixture
def network(monkeypatch: pytest.MonkeyPatch) -> Iterator[Network]:
    """Replace ``api.fetch_feed`` with a ``Network`` until the test ends."""
    fake = Network()
    monkeypatch.setattr(api, "fetch_feed", fake.fetch_feed)
    yield fake
    fake.released.set()  # a held refresh ends with the test
