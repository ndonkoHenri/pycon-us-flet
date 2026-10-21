"""Tests for the floor viewer (#388; ROOM-05, MAP-05, INFO-13; ux.md §6.1).

``PlanViewer`` runs in a real Flet session (``tests/sessions.py``) over the 2026
``map.toml``. No Flutter lays it out or answers its viewer here, so the tests report
the viewer's size as ``on_size_change`` would, and ``FakeViewer`` stands in for the
``InteractiveViewer``'s methods with the pin's behaviour (F76: ``zoom()`` keeps the
translation, ``pan()`` moves in the plan's units). The pin's pulse waits are held until
a test releases them (``tests/timers.py``). How the plan, the pin and the card look,
and that the pin is on its room on screen, are checked on devices (the PR).
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
from pycon_us.ui import zoom
from tests import sessions
from tests.sessions import menu_text
from tests.timers import HeldSleeps
from tests.trees import texts

YEAR = load_year(2026)
VIEW = "/map/room/room-104c/plan/concourse"
"""The floor viewer's View path, pushed from a room."""

BOX = (382.0, 640.0)
"""The viewer's size on an iPhone 17 in portrait, in logical pixels."""


@dataclass
class FakeViewer:
    """The ``InteractiveViewer``'s methods as the pin has them, and what was asked."""

    scale: float = 1.0
    x: float = 0.0
    y: float = 0.0
    calls: list[tuple[str, Any]] = field(default_factory=list)
    """Each method called, with its argument, in order."""
    after_zoom: Callable[[], Awaitable[None]] | None = None
    """What Flutter does once a zoom lands, e.g. report the transform (a render)."""

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Put this fake's methods on ``ft.InteractiveViewer`` for the test."""
        fake = self

        async def zoom_(viewer: ft.InteractiveViewer, factor: float) -> None:
            assert viewer.page  # a detached viewer raises, as on a device
            fake.calls.append(("zoom", factor))
            top = float(viewer.max_scale)
            fake.scale = min(top, max(1.0, fake.scale * factor))  # t stays (F76)
            if fake.after_zoom is not None:
                await fake.after_zoom()

        async def pan(viewer: ft.InteractiveViewer, dx: float, dy: float = 0) -> None:
            assert viewer.page
            fake.calls.append(("pan", (dx, dy)))
            fake.x += fake.scale * dx  # the plan's units (F76)
            fake.y += fake.scale * dy

        async def reset(
            viewer: ft.InteractiveViewer, animation_duration: Any = None
        ) -> None:
            fake.calls.append(("reset", animation_duration))
            fake.scale, fake.x, fake.y = 1.0, 0.0, 0.0

        async def get_transform(
            viewer: ft.InteractiveViewer,
        ) -> ft.InteractiveViewerTransform:
            assert viewer.page
            return ft.InteractiveViewerTransform(
                scale=fake.scale,
                translation_x=fake.x,
                translation_y=fake.y,
                translation_z=0.0,
                matrix=[],
            )

        monkeypatch.setattr(ft.InteractiveViewer, "zoom", zoom_)
        monkeypatch.setattr(ft.InteractiveViewer, "pan", pan)
        monkeypatch.setattr(ft.InteractiveViewer, "reset", reset)
        monkeypatch.setattr(ft.InteractiveViewer, "get_transform", get_transform)

    def plan_point(self, focus: tuple[float, float]) -> tuple[float, float]:
        """The plan's point under a point of the viewer."""
        return (focus[0] - self.x) / self.scale, (focus[1] - self.y) / self.scale


@dataclass
class Plan(sessions.Shown):
    """The harness's ``Shown`` on one ``PlanViewer``."""

    viewer: FakeViewer = field(default_factory=FakeViewer)
    sleeps: HeldSleeps = field(default_factory=HeldSleeps)
    toggles: list[Callable[[bool], None]] = field(default_factory=list)
    """The setter that mounts the viewer or leaves it (Back)."""

    @property
    def zoom_layer(self) -> ft.InteractiveViewer:
        """The plan's one ``InteractiveViewer``."""
        (found,) = self.find(ft.InteractiveViewer)
        return found

    @property
    def image(self) -> ft.Image:
        """The plan's ``Image``."""
        (found,) = self.find(ft.Image)
        return found

    def pins(self) -> list[ft.Stack]:
        """The pins drawn on the plan: the ``Stack``s scaled back against the zoom."""
        return [s for s in self.find(ft.Stack) if s.scale is not None]

    def button(self, name: str) -> ft.IconButton:
        """A zoom button, under its merged identifier ``plan.<name>``."""
        return cast(ft.IconButton, self.node(f"plan.{name}").content)

    async def lay_out(self, box: tuple[float, float] = BOX) -> None:
        """Report the viewer's size, as Flutter does after its first layout."""
        (sized,) = [c for c in self.find(ft.Container) if c.on_size_change]
        await self.event(sized, "size_change", {"w": box[0], "h": box[1]})

    async def transformed(self) -> None:
        """Report the fake viewer's transform, as ``on_transform_changed`` does."""
        v = self.viewer
        data = {"s": v.scale, "tx": v.x, "ty": v.y, "tz": 0.0, "m": []}
        await self.event(self.zoom_layer, "transform_changed", data)

    async def until_held(self, *, timeout: float = 30.0) -> None:
        """Settle until the pulse waits on a held sleep, or fail after ``timeout`` s.

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
    """Yield a function that opens ``PlanViewer`` at a route and returns its ``Plan``.

    The plan is the Concourse level unless ``plan_id`` names another; reduced motion,
    the view memory and the ``Conference`` (no feed by default) can be set too. The pulse's waits are held and the viewer's
    methods are ``FakeViewer``'s.
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
            sessions.showing(
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


async def test_a_pin_is_placed_on_its_room_and_named_by_the_plan(
    render: Render,
) -> None:
    """``?pin=104c``: one pin centred on 84 %, 27 % of the fitted plan, and its words."""
    plan = await render("?pin=104c")
    assert plan.pins() == []  # not before the plan has a size
    await plan.lay_out()
    shown = zoom.fitted(BOX, (2048, 1583))
    (pin,) = plan.pins()
    assert (pin.left, pin.top) == zoom.centred_on(84.0, 27.0, shown, screen.PIN_BOX)
    assert pin.scale == 1.0
    assert plan.image.semantics_label == "Concourse level floor plan, Room 104C marked"
    assert plan.image.src == "maps/2026/concourse.webp"
    assert (plan.image.width, plan.image.height) == shown
    assert plan.titles[-1] == "Concourse level"
    assert texts(plan.node("plan.label")) == [
        "Room 104C",
        "Concourse level · Education Summit / Charlas / Open spaces",
    ]
    assert plan.memory.plan_pins == {VIEW: "104c"}


async def test_the_maximum_zoom_is_the_plans_natural_size(render: Render) -> None:
    """The viewer zooms from fit (never below) to one image pixel per dp (D-312)."""
    plan = await render()
    await plan.lay_out()
    layer = plan.zoom_layer
    assert layer.min_scale == 1
    assert layer.max_scale == pytest.approx(2048 / BOX[0])


async def test_the_pin_stays_one_size_on_screen_at_any_zoom(render: Render) -> None:
    """At 3x the pin scales back by a third, about its centre, so it stays on its room."""
    plan = await render("?pin=104c")
    await plan.lay_out()
    plan.viewer.scale = 3.0
    await plan.transformed()
    (pin,) = plan.pins()
    assert pin.scale == pytest.approx(1 / 3)


async def test_the_pin_pulses_twice_then_stays_still(render: Render) -> None:
    """Out and back twice, each half ``PULSE_MS``, then no more waits (D-34)."""
    plan = await render("?pin=104c")
    await plan.lay_out()
    rings: list[bool] = []
    for _ in range(2 * screen.PULSES):
        await plan.until_held()
        rings.append(ring_out(plan))
        await plan.sleeps.release()
        await plan.settle()
    assert rings == [True, False, True, False]
    assert plan.sleeps.asked == [screen.PULSE_MS / 1000] * 4
    assert plan.sleeps.held == 0


def ring_out(plan: Plan) -> bool:
    """Whether the pin's ring is out, mid-pulse."""
    (pin,) = plan.pins()
    halo = cast(ft.Container, pin.controls[0])
    return halo.scale == screen.RING_SCALE


async def test_reduced_motion_leaves_the_pin_still(render: Render) -> None:
    """Under reduced motion the pin shows at once and never pulses (D-173)."""
    plan = await render("?pin=104c", reduce_motion=True)
    await plan.lay_out()
    assert len(plan.pins()) == 1
    assert plan.sleeps.asked == []
    assert not ring_out(plan)


async def test_a_view_rebuilt_where_its_pin_pulsed_stays_still(render: Render) -> None:
    """A new session at the same location (D-143) finds the pin and does not pulse."""
    memory = ViewMemory(plan_pins={VIEW: "104c"})
    plan = await render("?pin=104c", memory=memory)
    await plan.lay_out()
    assert len(plan.pins()) == 1
    assert plan.sleeps.asked == []


async def test_a_view_below_the_top_keeps_its_pin_from_memory(render: Render) -> None:
    """Without its query (a View built below the top), the pin comes from memory."""
    memory = ViewMemory(plan_pins={VIEW: "info-desk"})
    plan = await render(memory=memory)
    await plan.lay_out()
    assert len(plan.pins()) == 1
    assert "Information desk" in plan.texts()


async def test_leaving_forgets_the_pin_so_the_next_opening_pulses(
    render: Render,
) -> None:
    """Back removes the View's entry; reopened, the pin pulses again (D-18, D-34)."""
    plan = await render("?pin=104c", reduce_motion=True)
    await plan.lay_out()
    assert plan.memory.plan_pins == {VIEW: "104c"}
    await plan.show(False)
    assert plan.memory.plan_pins == {}


@pytest.mark.parametrize("query", ["?pin=no-such-spot", "?pin=201a", ""])
async def test_no_pin_without_one_on_this_plan(render: Render, query: str) -> None:
    """An unknown pin, one on another plan (201a is on the Upper level) or none."""
    plan = await render(query)
    await plan.lay_out()
    assert plan.pins() == []
    assert plan.nodes("plan.label") == []
    assert plan.image.semantics_label == "Concourse level floor plan"
    assert plan.memory.plan_pins == {}


async def test_an_unknown_plan_offers_the_map(render: Render) -> None:
    """``plan/nowhere``: the not-found state, "Open the map" going to the Floor plans tab."""
    plan = await render(plan_id="nowhere")
    assert plan.titles[-1] == "Not found"
    assert screen.NOT_FOUND in plan.texts()
    (button,) = [
        b for b in plan.find(ft.FilledTonalButton) if b.content == screen.OPEN_MAP
    ]
    await plan.click(button)
    assert plan.went == ["/map?tab=floor-plans"]
    assert plan.find(ft.InteractiveViewer) == []


async def test_the_zoom_buttons_are_named_and_say_when_they_cannot_act(
    render: Render,
) -> None:
    """At fit, zoom out and reset are disabled; at the maximum, zoom in is (D-214)."""
    plan = await render()
    await plan.lay_out()
    for name, tooltip in (
        ("zoom_in", zoom.ZOOM_IN),
        ("zoom_out", zoom.ZOOM_OUT),
        ("reset", zoom.RESET_VIEW),
    ):
        node = plan.node(f"plan.{name}")
        assert isinstance(node.parent, ft.MergeSemantics)  # one node with its button
        assert plan.button(name).tooltip == tooltip
        assert plan.button(name).width == plan.button(name).height == zoom.BUTTON_DP
        assert node.disabled == (name != "zoom_in")
    plan.viewer.scale = float(plan.zoom_layer.max_scale)
    await plan.transformed()
    assert plan.button("zoom_in").disabled
    assert plan.node("plan.zoom_in").disabled
    assert not plan.button("zoom_out").disabled


async def test_zoom_in_keeps_the_centre_of_the_viewer_in_place(render: Render) -> None:
    """``zoom(1.5)`` scales about the corner (F76): the pan after it re-centres."""
    plan = await render()
    await plan.lay_out()
    centre = (BOX[0] / 2, BOX[1] / 2)
    before = plan.viewer.plan_point(centre)
    await plan.click(plan.button("zoom_in"))
    assert [name for name, _ in plan.viewer.calls] == ["zoom", "pan"]
    assert plan.viewer.calls[0] == ("zoom", zoom.ZOOM_STEP)
    assert plan.viewer.scale == pytest.approx(1.5)
    assert plan.viewer.plan_point(centre) == pytest.approx(before)
    await plan.transformed()
    await plan.click(plan.button("zoom_out"))
    assert plan.viewer.calls[2] == ("zoom", 1 / zoom.ZOOM_STEP)
    assert plan.viewer.scale == pytest.approx(1.0)


async def test_a_render_mid_zoom_does_not_lose_the_viewer(render: Render) -> None:
    """The zoom's own transform report re-renders the viewer; the pan still lands."""
    plan = await render()
    await plan.lay_out()
    plan.viewer.after_zoom = plan.transformed
    centre = (BOX[0] / 2, BOX[1] / 2)
    before = plan.viewer.plan_point(centre)
    await plan.click(plan.button("zoom_in"))
    assert [name for name, _ in plan.viewer.calls] == ["zoom", "pan"]
    assert plan.viewer.plan_point(centre) == pytest.approx(before)


async def test_a_double_tap_zooms_in_on_the_tap_then_back_to_fit(
    render: Render,
) -> None:
    """At fit, 2x about the tapped point; zoomed in, back to fit (ux.md §6.1)."""
    plan = await render()
    await plan.lay_out()
    (detector,) = plan.find(ft.GestureDetector)
    tap = (100.0, 200.0)
    before = plan.viewer.plan_point(tap)
    await plan.event(detector, "double_tap_down", {"l": {"x": tap[0], "y": tap[1]}})
    await plan.event(detector, "double_tap")
    assert plan.viewer.scale == pytest.approx(zoom.DOUBLE_TAP_SCALE)
    assert plan.viewer.plan_point(tap) == pytest.approx(before)
    await plan.transformed()
    await plan.event(detector, "double_tap")
    assert plan.viewer.calls[-1][0] == "reset"
    assert plan.viewer.scale == 1.0


async def test_a_pulse_between_a_double_taps_down_and_up_keeps_the_tap(
    render: Render,
) -> None:
    """The tapped point survives a render of the pin's pulse before the second up."""
    plan = await render("?pin=104c")
    await plan.lay_out()
    (detector,) = plan.find(ft.GestureDetector)
    tap = (100.0, 200.0)
    before = plan.viewer.plan_point(tap)
    await plan.event(detector, "double_tap_down", {"l": {"x": tap[0], "y": tap[1]}})
    await plan.until_held()
    await plan.sleeps.release()  # the ring goes out: a render, with new handlers
    await plan.settle()
    (detector,) = plan.find(ft.GestureDetector)
    await plan.event(detector, "double_tap")
    assert plan.viewer.scale == pytest.approx(zoom.DOUBLE_TAP_SCALE)
    assert plan.viewer.plan_point(tap) == pytest.approx(before)


async def test_a_rotation_brings_the_zoom_down_to_the_new_maximum(
    render: Render,
) -> None:
    """At portrait's maximum, landscape's lower one clamps the zoom, centred (D-312)."""
    plan = await render()
    await plan.lay_out()
    plan.viewer.scale = float(plan.zoom_layer.max_scale)
    await plan.transformed()
    landscape = (874.0, 330.0)
    await plan.lay_out(landscape)
    await plan.settle()
    top = zoom.max_scale(2048, zoom.fitted(landscape, (2048, 1583))[0])
    assert float(plan.zoom_layer.max_scale) == pytest.approx(top)
    assert plan.viewer.scale == pytest.approx(top)
    # The refocusing pan, then (this fake's pan clamps nothing) the pan into bounds.
    assert [name for name, _ in plan.viewer.calls][:2] == ["zoom", "pan"]
    assert_in_bounds(plan.viewer, landscape)


def assert_in_bounds(viewer: FakeViewer, box: tuple[float, float]) -> None:
    """Assert no blank shows beyond the box-sized content: ``box (1 - s) <= t <= 0``."""
    for t, side in ((viewer.x, box[0]), (viewer.y, box[1])):
        assert side * (1 - viewer.scale) - 1e-6 <= t <= 1e-6


async def test_a_rotation_pans_back_inside_the_new_bounds(render: Render) -> None:
    """Zoomed 2x at landscape's right edge, portrait pans to its right edge (#588)."""
    plan = await render()
    landscape = (874.0, 330.0)
    await plan.lay_out(landscape)
    plan.viewer.scale = 2.0
    plan.viewer.x = landscape[0] * (1 - 2.0)  # the right edge: -874
    await plan.transformed()
    await plan.lay_out()
    await plan.settle()
    assert plan.viewer.scale == pytest.approx(2.0)  # under portrait's maximum: kept
    assert [name for name, _ in plan.viewer.calls] == ["pan"]
    assert plan.viewer.x == pytest.approx(BOX[0] * (1 - 2.0))  # portrait's right edge
    assert_in_bounds(plan.viewer, BOX)


async def test_a_resize_in_bounds_pans_nothing(render: Render) -> None:
    """A zoomed plan that stays in bounds after a resize is left where it is."""
    plan = await render()
    await plan.lay_out((874.0, 330.0))
    plan.viewer.scale, plan.viewer.x, plan.viewer.y = 2.0, -100.0, -100.0
    await plan.transformed()
    await plan.lay_out()
    await plan.settle()
    assert plan.viewer.calls == []


@pytest.mark.parametrize("query", ["?pin=104c", ""])
async def test_the_card_and_buttons_take_no_gestures_beside_them(
    render: Render, query: str
) -> None:
    """No ``Container`` (always decorated, so hit) around them over the plan."""
    plan = await render(query)
    await plan.lay_out()
    (body,) = [s for s in plan.find(ft.Stack) if s.fit == ft.StackFit.EXPAND]
    row = body.controls[1]
    assert isinstance(row, ft.Row)
    assert (row.left, row.right, row.bottom) == (16, 16, 16)
    card = row.controls[0]
    assert isinstance(card, ft.Column)
    assert len(card.controls) == (1 if query else 0)


@pytest.mark.parametrize(("reduce_motion", "ms"), [(False, 250), (True, None)])
async def test_reset_view_animates_unless_motion_is_reduced(
    render: Render, reduce_motion: bool, ms: int | None
) -> None:
    """The button and the overflow item reset in 250 ms, at once under reduced motion."""
    plan = await render(reduce_motion=reduce_motion)
    await plan.lay_out()
    plan.viewer.scale = 2.0
    await plan.transformed()
    await plan.click(plan.button("reset"))
    (item,) = plan.find(ft.PopupMenuItem)
    assert str(menu_text(item).value) == zoom.RESET_VIEW
    await plan.click(item)
    expected = ft.Duration(milliseconds=ms) if ms else None
    assert plan.viewer.calls == [("reset", expected), ("reset", expected)]
