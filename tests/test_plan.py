"""Tests for the floor viewer (#388; ROOM-05, MAP-05, INFO-13; ux.md §6.1).

``PlanViewer`` runs in a real Flet session (``tests/sessions.py``) over the 2026
``map.toml``, with ``tests/plan_view.py``'s harness. No Flutter lays it out or answers its viewer here, so the tests report
the viewer's size as ``on_size_change`` would, and ``FakeViewer`` stands in for the
``InteractiveViewer``'s methods with the pin's behaviour (F76: ``zoom()`` keeps the
translation, ``pan()`` moves in the plan's units). The pin's pulse waits are held until
a test releases them (``tests/timers.py``). How the plan, the pin and the card look,
and that the pin is on its room on screen, are checked on devices (the PR).
"""

from typing import cast

import flet as ft
import pytest

from pycon_us.memory import ViewMemory
from pycon_us.screens import plan as screen
from pycon_us.ui import zoom, zoom_geometry
from tests import plan_view
from tests.plan_view import BOX, VIEW, Plan, Render
from tests.sessions import menu_text
from tests.trees import descendants, texts
from tests.viewers import FakeViewer

render = plan_view.render


async def test_a_pin_is_placed_on_its_room_and_named_by_the_plan(
    render: Render,
) -> None:
    """``?pin=104c``: one pin centred on 84 %, 27 % of the fitted plan, and its words."""
    plan = await render("?pin=104c")
    assert plan.pins() == []  # not before the plan has a size
    await plan.lay_out()
    shown = zoom_geometry.fitted(BOX, (2048, 1583))
    (pin,) = plan.pins()
    assert (pin.left, pin.top) == zoom_geometry.centred_on(
        84.0, 27.0, shown, screen.PIN_BOX
    )
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
    top = zoom_geometry.max_scale(
        2048, zoom_geometry.fitted(landscape, (2048, 1583))[0]
    )
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


async def test_the_label_card_is_read_before_the_zoom_buttons(render: Render) -> None:
    """The buttons are one semantics node after the card, so it reads first (#729).

    Flutter orders a node's children by position: loose buttons put Zoom in, above
    the shorter card, first. One container beside the card sorts after it.
    """
    plan = await render("?pin=104c")
    await plan.lay_out()
    (body,) = [s for s in plan.find(ft.Stack) if s.fit == ft.StackFit.EXPAND]
    card, buttons = cast(ft.Row, body.controls[1]).controls
    assert plan.node("plan.label") in descendants(card)
    assert isinstance(buttons, ft.Semantics)
    assert buttons.container
    identifiers = [
        node.identifier
        for node in descendants(buttons)
        if isinstance(node, ft.Semantics) and node.identifier
    ]
    assert identifiers == ["plan.zoom_in", "plan.zoom_out", "plan.reset"]


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
