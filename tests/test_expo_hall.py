"""Tests for the expo hall: the Map's Expo pane and ``…/plan/expo`` (#402; EXPO-01, MAP-01).

The Map runs in a real Flet session (``tests/sessions.py``) over the 2026 feed and
``map.toml``, on its Expo pane. No Flutter lays it out or answers its viewer here, so
the tests report the viewer's size as ``on_size_change`` would and ``FakeViewer``
stands in for the viewer's methods. The pulse's waits are held until a test releases
them (``tests/timers.py``), and each booth body's run is counted through its phrase.
How the booths look, that a tap lands on them at 1x and at the maximum zoom, and what
TalkBack and VoiceOver say are checked on devices (the PR).
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, cast

import flet as ft
import pytest

from pycon_us.config import load_year
from pycon_us.core.expo import ExpoBooth
from pycon_us.memory import ViewMemory
from pycon_us.prefs import Prefs
from pycon_us.screens import expo, map_plans, plan
from pycon_us.screens import map as screen
from pycon_us.state import Conference
from pycon_us.theme import LIGHT_TOKENS
from pycon_us.ui import zoom
from tests import harness, links
from tests.feeds import processed
from tests.timers import HeldSleeps
from tests.viewers import FakeViewer

YEAR = load_year(2026)
BOX = (382.0, 560.0)
"""The Expo pane's size under the tab bar on an iPhone 17 in portrait, in dp."""

type Box = tuple[float, float, float, float]
"""A booth's ``left``, ``top``, ``width`` and ``height`` on the fitted plan."""


@dataclass
class ExpoShown(harness.Shown):
    """The harness's ``Shown`` on the Map's Expo pane, with what its booths did."""

    viewer: FakeViewer = field(default_factory=FakeViewer)
    sleeps: HeldSleeps = field(default_factory=HeldSleeps)
    renders: list[str] = field(default_factory=list)
    """The number of each booth whose body ran, in order."""

    @property
    def zoom_layer(self) -> ft.InteractiveViewer:
        """The plan's one ``InteractiveViewer``."""
        (found,) = self.find(ft.InteractiveViewer)
        return found

    def booth(self, number: str) -> ft.Semantics:
        """A booth's node, ``expo.booth.<number>``."""
        return self.node(f"{expo.SCREEN}.booth.{number}")

    def boxes(self) -> dict[str, Box]:
        """Each booth's positioned ``Container`` box, by number, in the layer's order.

        Each booth is a component in the layer's ``Stack``, rendering the ``Container``
        that holds its node, so the order is its component's place in the ``Stack``.
        """
        placed: list[tuple[int, str, Box]] = []
        for node in self.nodes(f"{expo.SCREEN}.booth."):
            box = cast(ft.Container, node.parent)
            spot = cast(ft.Control, box.parent)
            layer = cast(ft.Stack, spot.parent)
            number = str(node.identifier).removeprefix(f"{expo.SCREEN}.booth.")
            left, top, width, height = (
                float(edge or 0) for edge in (box.left, box.top, box.width, box.height)
            )
            edges = (left, top, width, height)
            placed.append((layer.controls.index(spot), number, edges))
        return {number: box for _, number, box in sorted(placed)}

    async def lay_out(self, box: tuple[float, float] = BOX) -> None:
        """Report the viewer's size, as Flutter does after its first layout."""
        (sized,) = [c for c in self.find(ft.Container) if c.on_size_change]
        await self.event(sized, "size_change", {"w": box[0], "h": box[1]})

    async def tap(self, number: str) -> None:
        """Tap a booth, as Flutter's hit test sends it to the booth's ``Container``."""
        await self.click(cast(ft.Container, self.booth(number).content))

    async def transformed(self) -> None:
        """Report the fake viewer's transform, as ``on_transform_changed`` does."""
        v = self.viewer
        data = {"s": v.scale, "tx": v.x, "ty": v.y, "tz": 0.0, "m": []}
        await self.event(self.zoom_layer, "transform_changed", data)

    async def pick(self, slug: str) -> None:
        """Pick a Map tab as the user does: Flutter moves it, then reports it."""
        (tabs,) = self.find(ft.Tabs)
        index = [pane.slug for pane in screen.PANES].index(slug)
        self.session.apply_patch(tabs._i, {"selected_index": index})
        await self.session.dispatch_event(tabs._i, "change", index)
        await self.settle()


type Render = Callable[..., Awaitable[ExpoShown]]

open_at = links.open_at  # the fixture, under this module's name (tests/chrome.py)


@pytest.fixture
async def render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Render]:
    """Yield a function that opens the Map's Expo pane and returns its ``ExpoShown``.

    Reduced motion and the view memory can be set. The pulse's waits are held, the
    viewer's methods are ``FakeViewer``'s, and each booth body's phrase is counted.
    """
    sleeps = HeldSleeps()
    monkeypatch.setattr(expo, "asyncio", sleeps)  # the expo module's name only
    viewer = FakeViewer()
    viewer.install(monkeypatch)
    phrase = expo.booth_phrase

    def counted(item: ExpoBooth) -> str:
        harness.current(ExpoShown).renders.append(item.booth.number)
        return phrase(item)

    monkeypatch.setattr(expo, "booth_phrase", counted)

    async def show(
        stack: AsyncExitStack,
        *,
        reduce_motion: bool = False,
        memory: ViewMemory | None = None,
        data: bool = True,
    ) -> ExpoShown:
        def make(*args: Any, **kwargs: Any) -> ExpoShown:
            return ExpoShown(*args, viewer=viewer, sleeps=sleeps, **kwargs)

        conference = (
            Conference(data=processed(2026), source="bundled", version=1)
            if data
            else Conference()
        )
        return await stack.enter_async_context(
            harness.showing(
                screen.Map,
                screen,
                year=YEAR,
                conference=conference,
                tmp_path=tmp_path,
                monkeypatch=monkeypatch,
                view_path="/map",
                prefs=Prefs(loaded=True, reduce_motion=reduce_motion),
                memory=memory,
                route="/map?tab=expo",
                kind=make,
            )
        )

    async with AsyncExitStack() as stack:

        async def opened(*args: Any, **kwargs: Any) -> ExpoShown:
            return await show(stack, *args, **kwargs)

        yield opened


def hit(point: tuple[float, float], boxes: dict[str, Box]) -> str | None:
    """The booth Flutter's hit test finds at a point of the plan: the last one drawn."""
    found = None
    for number, (left, top, width, height) in boxes.items():
        if left <= point[0] <= left + width and top <= point[1] <= top + height:
            found = number  # a later child is drawn over, and hit-tested before
    return found


async def test_the_expo_tab_shows_the_plan_with_every_booth(render: Render) -> None:
    """``?tab=expo`` opens the pane: the plan, named, under 61 booths in number order."""
    shown = await render()
    assert shown.memory.map_tab == "expo"
    assert shown.find(ft.ListView) == []  # no list: the plan fills the pane
    assert shown.find(ft.GestureDetector) == []  # no double tap delays a booth (D-312)
    image = shown.zoom_layer.content
    assert isinstance(image, ft.Container)
    assert shown.find(ft.Image)[0].semantics_label == "Expo hall floor plan"
    await shown.lay_out()
    numbers = list(shown.boxes())
    assert len(numbers) == len(YEAR.map.booths) == 61
    assert numbers[:3] == ["112", "113", "116"]  # natural order, as the List's (D-254)


async def test_a_booth_reads_as_a_button_named_by_who_is_there(render: Render) -> None:
    """One sponsor, a shared booth, a labelled one; numbers alone without the feed."""
    shown = await render()
    await shown.lay_out()
    assert shown.booth("613").label == "Booth 613, Bloomberg"
    assert shown.booth("726").label == "Booth 726, 4 exhibitors"
    assert shown.booth("407").label == "Booth 407, Python Software Foundation"
    assert shown.booth("613").button
    assert shown.booth("613").selected is None  # unselected booths say nothing of it


async def test_without_the_feed_the_booths_are_there_by_number(render: Render) -> None:
    """Offline before the first fetch the plan still has its booths (offline first)."""
    shown = await render(data=False)
    await shown.lay_out()
    assert len(shown.boxes()) == 61
    assert shown.booth("613").label == "Booth 613"
    assert shown.booth("606").label == "Booth 606, Attendee lounge"


@pytest.mark.parametrize("at", ["fit", "max"])
async def test_every_booth_centre_hits_its_own_booth(render: Render, at: str) -> None:
    """Each of the 61 centres finds its own booth, at 1x and at the maximum zoom.

    A screen point under the viewer's transform goes back to the plan, where Flutter's
    hit test takes the last booth drawn that holds it: an overlap or a booth placed
    off its rectangle fails here by number.
    """
    shown = await render()
    await shown.lay_out()
    boxes = shown.boxes()
    shown_size = zoom.fitted(BOX, (2048, 1448))
    offset = ((BOX[0] - shown_size[0]) / 2, (BOX[1] - shown_size[1]) / 2)
    top = zoom.max_scale(2048, shown_size[0])
    t = (
        zoom.Transform(1.0, 0.0, 0.0)
        if at == "fit"
        else zoom.Transform(top, -900, -600)
    )
    for item in YEAR.map.booths:
        left, top_edge, width, height = expo.booth_box(item, shown_size)
        assert boxes[item.number] == pytest.approx((left, top_edge, width, height))
        centre = (offset[0] + left + width / 2, offset[1] + top_edge + height / 2)
        screen_point = (t.scale * centre[0] + t.x, t.scale * centre[1] + t.y)
        local = (
            (screen_point[0] - t.x) / t.scale - offset[0],
            (screen_point[1] - t.y) / t.scale - offset[1],
        )
        assert hit(local, boxes) == item.number


async def test_a_tap_selects_its_booth_without_zooming(render: Render) -> None:
    """Amber fill and a 2 dp dark outline, said as selected; no camera move (U3)."""
    shown = await render(reduce_motion=True)
    await shown.lay_out()
    await shown.tap("613")
    node = shown.booth("613")
    assert node.selected is True
    drawn = cast(ft.Container, node.content)
    assert drawn.bgcolor == ft.Colors.with_opacity(
        expo.FILL_OPACITY, LIGHT_TOKENS.booth_fill
    )
    assert drawn.border == ft.Border.all(expo.OUTLINE_DP, LIGHT_TOKENS.booth_outline)
    assert shown.viewer.calls == []  # selected where it is, not zoomed to
    assert shown.memory.expo_booth == "613"
    await shown.tap("726")
    assert shown.booth("613").selected is None
    assert shown.booth("726").selected is True


async def test_a_selection_re_renders_two_booths_and_a_zoom_none(
    render: Render,
) -> None:
    """The layer and its booths are memoised on values (D-153, F150)."""
    shown = await render(reduce_motion=True)
    await shown.lay_out()
    await shown.tap("613")
    shown.renders.clear()
    await shown.tap("726")
    assert sorted(shown.renders) == ["613", "726"]
    shown.renders.clear()
    shown.viewer.scale = 2.0
    await shown.transformed()
    assert shown.renders == []


async def test_a_selected_booth_pulses_twice_then_stays(render: Render) -> None:
    """Up and back twice, through ``prefs.motion_ms()``, then the plain fill (D-34)."""
    shown = await render()
    await shown.lay_out()
    await shown.tap("613")
    flashes = []
    for _ in range(2 * expo.PULSES):
        await shown.settle()
        drawn = cast(ft.Container, shown.booth("613").content)
        flashes.append(drawn.bgcolor)
        await shown.sleeps.release()
    await shown.settle()
    fill = LIGHT_TOKENS.booth_fill
    up = ft.Colors.with_opacity(expo.FLASH_OPACITY, fill)
    still = ft.Colors.with_opacity(expo.FILL_OPACITY, fill)
    assert flashes == [up, still, up, still]
    assert shown.sleeps.asked == [expo.PULSE_MS / 1000] * 4
    assert shown.sleeps.held == 0


async def test_reduced_motion_selects_without_a_pulse(render: Render) -> None:
    """No pulse and no animated fill under reduced motion (D-173)."""
    shown = await render(reduce_motion=True)
    await shown.lay_out()
    await shown.tap("613")
    assert shown.sleeps.asked == []
    drawn = cast(ft.Container, shown.booth("613").content)
    assert drawn.animate == ft.Animation(0, ft.AnimationCurve.EASE_OUT)


async def test_switching_panes_keeps_the_booth_and_the_zoom(render: Render) -> None:
    """Rooms and back: the booth still selected, the zoom put back (D-18, D-312)."""
    shown = await render(reduce_motion=True)
    await shown.lay_out()
    await shown.tap("613")
    shown.viewer.scale, shown.viewer.x, shown.viewer.y = 3.0, -300.0, -150.0
    await shown.transformed()
    assert shown.memory.map_zooms["expo"] == (3.0, -300.0, -150.0)
    await shown.pick("rooms")
    assert shown.find(ft.InteractiveViewer) == []
    shown.viewer.scale, shown.viewer.x, shown.viewer.y = 1.0, 0.0, 0.0  # a new viewer
    shown.viewer.calls.clear()
    await shown.pick("expo")
    assert shown.viewer.calls == []  # not before the pane is laid out
    await shown.lay_out()
    assert [name for name, _ in shown.viewer.calls] == ["reset", "zoom", "pan"]
    assert (shown.viewer.scale, shown.viewer.x, shown.viewer.y) == pytest.approx(
        (3.0, -300.0, -150.0)
    )
    assert shown.booth("613").selected is True


async def test_a_pane_at_fit_is_not_put_back(render: Render) -> None:
    """Nothing to restore at 1x: the viewer is left alone on return."""
    memory = ViewMemory(map_tab="expo", map_zooms={"expo": (1.0, 0.0, 0.0)})
    shown = await render(memory=memory)
    await shown.lay_out()
    assert shown.viewer.calls == []


async def test_the_zoom_buttons_are_the_expo_s_own(render: Render) -> None:
    """Zoom in, out and reset, merged with ``expo.zoom_in`` and the others (D-214)."""
    shown = await render()
    await shown.lay_out()
    for name in ("zoom_in", "zoom_out", "reset"):
        assert isinstance(shown.node(f"expo.{name}").parent, ft.MergeSemantics)


async def test_a_retap_on_the_expo_pane_does_nothing(render: Render) -> None:
    """No list to scroll: the Map gives the bar no re-tap action there (D-166)."""
    shown = await render()
    assert shown.retaps[-1] is None


def test_a_year_without_booths_has_no_expo_tab() -> None:
    """The Expo pane is there only when ``map.toml`` has booths."""
    no_booths = replace(YEAR.map, booths=())
    slugs = [pane.slug for pane in screen.panes_of(no_booths)]
    assert slugs == ["rooms", map_plans.FLOOR_PLANS, "job-fair"]
    assert screen.EXPO in [pane.slug for pane in screen.panes_of(YEAR.map)]


@pytest.mark.parametrize("booths", [True, False], ids=["booths", "no booths"])
async def test_plan_expo_is_the_hall_in_a_year_with_booths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, booths: bool
) -> None:
    """``…/plan/expo`` pushes the hall with its booths; without booths, the plan alone."""
    year = YEAR if booths else replace(YEAR, map=replace(YEAR.map, booths=()))
    async with harness.showing(
        plan.ExpoPlan,
        plan,
        year=year,
        conference=Conference(),
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        view_path="/more/sponsors/sponsor/bloomberg/plan/expo",
    ) as shown:
        (sized,) = [c for c in shown.find(ft.Container) if c.on_size_change]
        await shown.event(sized, "size_change", {"w": BOX[0], "h": BOX[1]})
        assert shown.titles[-1] == "Expo hall"
        assert len(shown.nodes("expo.booth.")) == (61 if booths else 0)
        assert bool(shown.nodes("plan.zoom_in")) == (not booths)


async def test_back_from_a_pushed_hall_shows_the_booth_selected_there(
    open_at: links.Open, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Expo pane stays mounted under ``/map/plan/expo``; Back shows the new booth.

    Both halls share ``ViewMemory.expo_booth`` (D-312): the pane below rereads it when
    the route comes back to it, not only when it mounts.
    """
    FakeViewer().install(monkeypatch)
    prefs = Prefs(loaded=True, reduce_motion=True)
    shown = await open_at("/map?tab=expo", prefs=prefs)

    async def lay_out_top() -> None:
        """Report the top hall's size, as Flutter does after its first layout."""
        sized: Any = shown.find(ft.InteractiveViewer)[-1]
        while not (isinstance(sized, ft.Container) and sized.on_size_change):
            sized = sized.parent
        await shown.event(sized, "size_change", {"w": BOX[0], "h": BOX[1]})

    def booths(number: str) -> list[ft.Semantics]:
        """The mounted nodes of a booth, the pane's first: one per hall."""
        return shown.nodes(f"{expo.SCREEN}.booth.{number}")

    await lay_out_top()
    await shown.click(cast(ft.Container, booths("613")[-1].content))
    await shown.go("/map/plan/expo")
    assert shown.routes() == ["/", "/map/plan/expo"]
    await lay_out_top()
    await shown.click(cast(ft.Container, booths("726")[-1].content))
    assert shown.memory.expo_booth == "726"
    await shown.back()
    assert shown.routes() == ["/"]
    assert [node.selected for node in booths("613")] == [None]
    assert [node.selected for node in booths("726")] == [True]
