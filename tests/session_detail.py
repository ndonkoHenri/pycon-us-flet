"""The session detail harness: ``SessionDetail`` in a real Flet session (ux.md §5.5).

``tests/test_session.py``, its parts and ``tests/test_session_extras.py`` share it. The session is
``tests/harness.py``'s ``showing()``, under a component that can re-render the detail
in place with another id, or without it. The sessions are the recorded 2026 feed's.
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

import flet as ft
import pytest

from pycon_us import clock
from pycon_us.config import load_year
from pycon_us.screens import session as screen
from pycon_us.state import Conference
from pycon_us.ui import location_card
from tests.fakes import MemoryShare
from tests.feeds import processed
from tests.harness import Shown, showing
from tests.timers import HeldSleeps

YEAR = load_year(2026)
PACIFIC = ZoneInfo("America/Los_Angeles")
VIEW = "/schedule/session/x"
"""The View path the screen is rendered at: links push on top of it."""

TALK = "142"
"""Python for Humans, Sat May 16 10:30-11:00 AM, Grand Ballroom A; a public page."""

BREAK = (
    "break-Room 103ABC, Room 104AB, Room 104C, Grand Ballroom A, Grand Ballroom B"
    "-2026-05-16T10:05:00-07:00"
)
"""A break in five rooms with no one place to show (DATA-16)."""


@dataclass
class Detail(Shown):
    """A Flet session showing one ``SessionDetail``."""

    opened: list[Callable[[str | None], None]] = field(default_factory=list)
    """The shown id's setter, once the detail's first render has run."""

    @property
    def pushed(self) -> list[str]:
        """The View paths the detail asked ``page.navigate`` for, in order."""
        return self.went

    @property
    def share(self) -> MemoryShare:
        """The share service the detail was given, which records each share."""
        return cast(MemoryShare, self.services.share)

    def text(self, identifier: str) -> list[str]:
        """The visible text under the node ``identifier``, in reading order."""
        return words(self.node(identifier))

    async def show(self, session_id: str | None) -> None:
        """Re-render the detail in place with another id, or leave it (``None``)."""
        self.opened[0](session_id)
        await self.settle()


type Render = Callable[[str], Awaitable[Detail]]


@asynccontextmanager
async def rendering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Render]:
    """Yield render(session_id): the detail of that session at ``VIEW``.

    Each test module's ``render`` fixture enters it with its own ``tmp_path`` and
    ``monkeypatch``; leaving it closes every session it rendered. The location card's
    pulse waits on its own ``HeldSleeps``, never released here.
    """
    monkeypatch.setattr(location_card, "asyncio", HeldSleeps())
    try:
        async with AsyncExitStack() as stack:

            async def show(session_id: str) -> Detail:
                opened: list[Callable[[str | None], None]] = []

                @ft.component
                def Opened() -> ft.Control:
                    # Detail.show() changes the id in place, or leaves the detail (None).
                    shown_id, set_shown_id = ft.use_state(cast(str | None, session_id))
                    opened[:] = [set_shown_id]
                    if shown_id is None:
                        return ft.Text("Elsewhere")
                    return screen.SessionDetail(shown_id)

                shown = await stack.enter_async_context(
                    showing(
                        Opened,
                        screen,
                        year=YEAR,
                        conference=Conference(
                            data=processed(2026), source="bundled", version=1
                        ),
                        tmp_path=tmp_path,
                        monkeypatch=monkeypatch,
                        view_path=VIEW,
                    )
                )
                # Shown's fields as they are: the rows and the navigation still record.
                return Detail(**vars(shown), opened=opened)

            yield show
    finally:
        clock.set_test_now(None)


def words(control: ft.Control) -> list[str]:
    """The visible text under ``control`` in reading order, components and tiles included.

    Unlike ``trees.texts``, it reads a ``ListTile``'s string title and what a component
    (the status line) rendered.
    """
    found: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, ft.Control) and node.visible is False:
            return
        if isinstance(node, ft.Text):
            found.append(str(node.value))
        if isinstance(node, str):
            found.append(node)
            return
        if isinstance(node, ft.Component):
            body = node._b
            for child in body if isinstance(body, list) else [body]:
                walk(child)
        for name in ("content", "leading", "title", "subtitle", "trailing"):
            child = getattr(node, name, None)
            if isinstance(child, (ft.Control, str)) and not isinstance(node, ft.Text):
                walk(child)
        for child in getattr(node, "controls", None) or ():
            walk(child)

    walk(control)
    return found


def headings(detail: Detail) -> list[tuple[str, int | None]]:
    """The page's headings, in order, with their levels."""
    return [
        (" ".join(words(n)), n.heading_level)
        for n in detail.session.index.values()
        if isinstance(n, ft.Semantics) and n.header
    ]


def at(text: str) -> datetime:
    """An instant in conference time, e.g. ``at("2026-05-16 10:05")``."""
    return datetime.fromisoformat(text).replace(tzinfo=PACIFIC)


TUTORIAL = "19"
"""A tutorial: registration required."""

LIGHTNING = "175"
"""Lightning talks: shown in the Arena, streamed to four rooms (D-124)."""

KEYNOTE = "176"
"""A keynote: no public page in the feed; its people are year data (D-217)."""

WELCOME = "151"
"""The Friday welcome, a plenary: no speakers in the feed, no keynote data."""

JOB_FAIR = "178"
"""Sun May 17, shown from 9:30 though grouped at its 10:00 start (DATA-11)."""

PANEL = "110"
"""Beyond the Hype: six speakers, five of them without a photo in the feed."""

OPEN_SPACE = "9086"
"""pytest for system tests: its Markdown links ``[pytest](pytest.org)`` (D-140)."""


@pytest.fixture
async def render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Render]:
    """Provide an async function that renders a session's detail at ``VIEW`` by id."""
    async with rendering(tmp_path, monkeypatch) as show:
        yield show
