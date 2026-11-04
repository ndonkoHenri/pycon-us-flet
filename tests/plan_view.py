"""The floor viewer's harness, for its test modules (#623).

`test_plan.py` (the pin, the zoom and the gestures) and `test_plan_tables.py` (the
job fair's tables) open `PlanViewer` in a real Flet session (`tests/sessions.py`)
over the 2026 `map.toml`, with its pulse waits held (`tests/timers.py`) and
`FakeViewer` standing in for the `InteractiveViewer`'s methods. A module takes the
`render` fixture by assigning it to its own name, as `docs/testing-and-quality.md`
§3.1 says.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import flet as ft
import pytest

from pycon_us.config import load_year
from pycon_us.memory import ViewMemory
from pycon_us.prefs import Prefs
from pycon_us.screens import plan as screen
from pycon_us.state import Conference
from tests import harness
from tests.timers import HeldSleeps
from tests.viewers import FakeViewer

YEAR = load_year(2026)
VIEW = "/map/room/room-104c/plan/concourse"
"""The floor viewer's View path, pushed from a room."""

BOX = (382.0, 640.0)
"""The viewer's size on an iPhone 17 in portrait, in logical pixels."""


@dataclass
class Plan(harness.Shown):
    """The harness's `Shown` on one `PlanViewer`."""

    viewer: FakeViewer = field(default_factory=FakeViewer)
    sleeps: HeldSleeps = field(default_factory=HeldSleeps)
    toggles: list[Callable[[bool], None]] = field(default_factory=list)
    """The setter that mounts the viewer or leaves it (Back)."""

    @property
    def zoom_layer(self) -> ft.InteractiveViewer:
        """The plan's one `InteractiveViewer`."""
        (found,) = self.find(ft.InteractiveViewer)
        return found

    @property
    def image(self) -> ft.Image:
        """The plan's `Image`."""
        (found,) = self.find(ft.Image)
        return found

    def pins(self) -> list[ft.Stack]:
        """The pins drawn on the plan: the `Stack`s scaled back against the zoom."""
        return [s for s in self.find(ft.Stack) if s.scale is not None]

    def button(self, name: str) -> ft.IconButton:
        """A zoom button, under its merged identifier `plan.<name>`."""
        return cast(ft.IconButton, self.node(f"plan.{name}").content)

    async def lay_out(self, box: tuple[float, float] = BOX) -> None:
        """Report the viewer's size, as Flutter does after its first layout."""
        (sized,) = [c for c in self.find(ft.Container) if c.on_size_change]
        await self.event(sized, "size_change", {"w": box[0], "h": box[1]})

    async def transformed(self) -> None:
        """Report the fake viewer's transform, as `on_transform_changed` does."""
        v = self.viewer
        data = {"s": v.scale, "tx": v.x, "ty": v.y, "tz": 0.0, "m": []}
        await self.event(self.zoom_layer, "transform_changed", data)

    async def until_held(self, *, timeout: float = 30.0) -> None:
        """Settle until the pulse waits on a held sleep, or fail after `timeout` s.

        A poll rather than a fixed wait, so a loaded host only makes it slower.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while self.sleeps.held != 1:
            assert loop.time() < deadline, "the pin did not start its pulse"
            await asyncio.sleep(0.01)
        await self.settle()

    async def show(self, shown: bool) -> None:
        """Mount the viewer again, or leave it (Back), in the same Flet session."""
        self.toggles[0](shown)
        await self.settle()


type Render = Callable[..., Awaitable[Plan]]


@pytest.fixture
async def render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Render]:
    """Yield a function that opens `PlanViewer` at a route and returns its `Plan`.

    The plan is the Concourse level unless `plan_id` names another; reduced motion,
    the view memory and the `Conference` (no feed by default) can be set too. The pulse's waits are held and the viewer's
    methods are `FakeViewer`'s.
    """
    sleeps = HeldSleeps()
    monkeypatch.setattr(screen, "asyncio", sleeps)  # the plan module's name only
    viewer = FakeViewer()
    viewer.install(monkeypatch)

    async def show(
        stack: AsyncExitStack,
        query: str = "",
        *,
        plan_id: str = "concourse",
        reduce_motion: bool = False,
        memory: ViewMemory | None = None,
        conference: Conference | None = None,
    ) -> Plan:
        toggles: list[Callable[[bool], None]] = []

        @ft.component
        def Opened() -> ft.Control:
            shown, set_shown = ft.use_state(True)
            toggles[:] = [set_shown]
            return screen.PlanViewer(plan_id) if shown else ft.Text("Back on the room")

        view = VIEW.replace("concourse", plan_id)

        def make(*args: Any, **kwargs: Any) -> Plan:
            return Plan(*args, viewer=viewer, sleeps=sleeps, toggles=toggles, **kwargs)

        return await stack.enter_async_context(
            harness.showing(
                Opened,
                screen,
                year=YEAR,
                conference=conference or Conference(),
                tmp_path=tmp_path,
                monkeypatch=monkeypatch,
                view_path=view,
                prefs=Prefs(loaded=True, reduce_motion=reduce_motion),
                memory=memory,
                route=f"{view}{query}",
                kind=make,
            )
        )

    async with AsyncExitStack() as stack:

        async def opened(*args: Any, **kwargs: Any) -> Plan:
            return await show(stack, *args, **kwargs)

        yield opened
