"""Room detail's sessions and harness, for its three test modules (#312).

``test_room.py`` (the highlight), ``test_room_days.py`` (the day lists and "Now in this
room") and ``test_room_location.py`` (an unknown room, a sprint-only room and the
location card) run ``RoomDetail`` in a real Flet session, as session detail does in
``test_session.py``: ``tests/harness.py``'s ``showing()`` puts the store providers
above it and replaces ``AppScaffold`` by a column that keeps the title and the body, and
the scroll to the row is a recorder, since no Flutter answers it here. The sessions are
the recorded 2026 feed's, and the clock is fixed in conference time. The highlight's
wait is held until a test ends it (``tests/timers.py``), so a slow host never ends it
before the test looks (#270). A module takes the fixtures by assigning them to its own
names, as ``docs/testing-and-quality.md`` §3.1 says.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import cast
from urllib.parse import quote
from zoneinfo import ZoneInfo

import flet as ft
import pytest

from pycon_us import clock
from pycon_us.config import load_year
from pycon_us.core.models import ConferenceData
from pycon_us.memory import ViewMemory
from pycon_us.prefs import Prefs
from pycon_us.screens import room as screen
from pycon_us.screens import room_days
from pycon_us.state import Conference
from pycon_us.ui import location_card
from tests import harness
from tests.feeds import processed
from tests.timers import HeldSleeps

YEAR = load_year(2026)
PACIFIC = ZoneInfo("America/Los_Angeles")
ROOM = "grand-ballroom-a"
VIEW = f"/schedule/session/31/room/{ROOM}"
"""The room's View path, pushed from a session: links push on top of it."""

TACHYON = "31"
"""Grand Ballroom A, Saturday 3:15 PM: far down Saturday's list."""

SUNDAY_TALK = "108"
"""Grand Ballroom A, Sunday 1:45 PM."""

HUMANS = "142"
"""Grand Ballroom A, Saturday 10:30 to 11:00 AM."""

LIGHTNING = "163"
"""Saturday's 8:00 AM lightning talks: given in the Arena, streamed here."""

SATURDAY_MORNING = datetime(2026, 5, 16, 10, 40, tzinfo=PACIFIC)
"""During "Python for Humans" in Grand Ballroom A."""

SHARED_SLOT = ("9163", "9126")
"""Room 102C's two sessions that start at 2:00 PM on Saturday: one slot, two rows."""


@dataclass
class Scroll:
    """One scroll the screen asked for."""

    key: str
    duration: int


@dataclass
class Room(harness.Shown):
    """The harness's ``Shown`` (``tests/harness.py``) on one ``RoomDetail``."""

    scrolls: list[Scroll] = field(default_factory=list)
    """The scrolls the room asked for, in order."""
    toggles: list[Callable[[bool], None]] = field(default_factory=list)
    """The setter that mounts the room or leaves it, once its first render has run."""
    sleeps: HeldSleeps = field(default_factory=HeldSleeps)
    """The screen's sleeps: the highlight stays on until the test releases its wait."""

    @property
    def tabs(self) -> ft.Tabs:
        """The screen's one ``Tabs``, the day tabs."""
        (found,) = self.find(ft.Tabs)
        return found

    def anchor(self) -> ft.Container:
        """The highlighted row's ``ScrollKey``: an empty anchor atop its box."""
        (found,) = [
            c for c in self.find(ft.Container) if isinstance(c.key, ft.ScrollKey)
        ]
        return found

    def lit_box(self) -> ft.Container:
        """The box around the highlighted row and its anchor: its fill."""
        box = cast(ft.Control, self.anchor().parent).parent
        assert isinstance(box, ft.Container)
        return box

    async def wait(self, seconds: float) -> None:
        """Let ``seconds`` pass: for tests that check nothing more happened."""
        await asyncio.sleep(seconds)
        await self.settle()

    async def until(self, holds: Callable[[], bool], *, timeout: float = 30.0) -> None:
        """Settle until ``holds()`` is true, or fail after ``timeout`` seconds.

        A poll rather than a fixed wait, so a loaded host only makes it slower; the
        deadline is generous because a passing test never reaches it (#237).
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while not holds():
            assert loop.time() < deadline, "the screen did not get there in time"
            await asyncio.sleep(0.01)
        await self.settle()

    async def fade(self) -> None:
        """End the highlight's wait, as its time passing would; see the row unlit."""
        await self.sleeps.release()
        await self.until(lambda: self.lit_box().bgcolor == room_days.UNLIT)

    def day_lists(self) -> list[ft.ListView]:
        """The day pages, in tab order."""
        (pages,) = self.find(ft.TabBarView)
        return [cast(ft.ListView, page) for page in pages.controls]

    async def show(self, shown: bool) -> None:
        """Mount the room again, or leave it (Back), in the same Flet session."""
        self.toggles[0](shown)
        await self.settle()


type Render = Callable[..., Awaitable[Room]]


@pytest.fixture
async def render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Render]:
    """Yield a function that opens ``RoomDetail`` at a route and returns its ``Room``.

    The room is ``ROOM`` unless ``slug`` names another; the clock, reduced motion, the
    view memory and the feed can be set too. The screen's sleeps are held and its
    scrolls recorded.
    """
    sleeps = HeldSleeps()
    monkeypatch.setattr(screen, "asyncio", sleeps)  # the room module's name only
    # The location card's pulse waits on its own, never released here.
    monkeypatch.setattr(location_card, "asyncio", HeldSleeps())

    async def scroll(
        list_ref: ft.Ref[ft.ListView],
        key: str,
        *,
        duration: int,
        ended: asyncio.Event,
    ) -> str:
        assert list_ref.current is not None  # the day list that shows the row
        harness.current(Room).scrolls.append(Scroll(key, duration))
        return "landed"

    monkeypatch.setattr(screen, "jump_to_key", scroll)

    async def show(
        stack: AsyncExitStack,
        route: str,
        *,
        slug: str = ROOM,
        now: datetime = SATURDAY_MORNING,
        reduce_motion: bool = False,
        memory: ViewMemory | None = None,
        data: ConferenceData | None = None,
    ) -> Room:
        clock.set_test_now(now)
        toggles: list[Callable[[bool], None]] = []

        @ft.component
        def Opened() -> ft.Control:
            shown, set_shown = ft.use_state(True)
            toggles[:] = [set_shown]
            if not shown:
                return ft.Text("Back on the session")
            return screen.RoomDetail(slug)

        return await stack.enter_async_context(
            harness.showing(
                Opened,
                screen,
                year=YEAR,
                conference=Conference(
                    data=data or processed(2026), source="bundled", version=1
                ),
                tmp_path=tmp_path,
                monkeypatch=monkeypatch,
                view_path=VIEW,
                prefs=Prefs(loaded=True, reduce_motion=reduce_motion),
                memory=memory,
                route=route,
                kind=partial(Room, toggles=toggles, sleeps=sleeps),
            )
        )

    try:
        async with AsyncExitStack() as stack:
            yield partial(show, stack)
    finally:
        clock.set_test_now(None)


def highlighted(session_id: str) -> str:
    """The location a session's room tile pushes (``when_where.room_href``)."""
    return f"{VIEW}?highlight={quote(session_id, safe='')}"


def phrase_of(room: Room, session_id: str) -> str:
    """Return the spoken phrase of the session's row in the room."""
    return str(room.node(f"room.session.{session_id}").label)


def ancestors(control: ft.BaseControl) -> list[ft.BaseControl]:
    """The controls ``control`` is in, from its parent up to the page."""
    found: list[ft.BaseControl] = []
    parent = control.parent
    while parent is not None:
        found.append(parent)
        parent = parent.parent
    return found
