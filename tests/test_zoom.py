"""Tests for the zoom layer's maths (#388; ux.md §6.1, D-312, F76).

The plan's fitted size, its maximum zoom, where a pin goes and the pan that keeps a
zoom's focus in place are pure functions: here they are checked on a phone in portrait
and landscape and on a tablet, at 1x and at the maximum zoom, by following a pin's
point through the viewer's transform back to the image's pixel. That the pin lands on
its room on screen is checked on the emulator and the simulator (the PR).
"""

import flet as ft
import pytest

from pycon_us.ui.zoom import (
    Transform,
    Zoom,
    centred_on,
    fitted,
    into_bounds,
    max_scale,
    refocus,
)

LANDSCAPE_PLAN = (2048.0, 1583.0)
"""The Concourse plan's size in pixels (``map.toml``)."""

PORTRAIT_PLAN = (1583.0, 2048.0)
"""The Arena plan's size in pixels."""

BOXES = {
    "phone portrait": (382.0, 640.0),
    "phone landscape": (874.0, 330.0),
    "tablet": (820.0, 1100.0),
}
"""Viewer sizes in logical pixels: an iPhone 17's body both ways, and a tablet's."""


def test_fitted_contains_the_plan_and_keeps_its_ratio() -> None:
    """The fitted plan fills one side of the viewer, fits the other, keeps its ratio."""
    for box in BOXES.values():
        for natural in (LANDSCAPE_PLAN, PORTRAIT_PLAN):
            width, height = fitted(box, natural)
            assert width <= box[0] + 1e-9 and height <= box[1] + 1e-9
            assert width == pytest.approx(box[0]) or height == pytest.approx(box[1])
            assert width / height == pytest.approx(natural[0] / natural[1])


def test_fitted_is_empty_before_the_first_layout() -> None:
    """Before ``on_size_change`` reports a size, the plan has none, so nothing is placed."""
    assert fitted((0.0, 0.0), LANDSCAPE_PLAN) == (0.0, 0.0)


def test_max_scale_puts_one_image_pixel_on_one_logical_pixel() -> None:
    """S7's 5.36x for the 2048-px expo plan on a 382-dp plan; never under 1 (D-312)."""
    assert max_scale(2048, 382) == pytest.approx(5.361, abs=1e-3)
    assert max_scale(2048, 2400) == 1.0  # shown above its natural size
    assert max_scale(2048, 0) == 1.0  # before the first layout


def screen_point(
    x: float,
    y: float,
    box: tuple[float, float],
    natural: tuple[float, float],
    t: Transform,
) -> tuple[float, float]:
    """Where a plan's point (percent) is on screen: the centred plan, then the transform."""
    shown = fitted(box, natural)
    offset = ((box[0] - shown[0]) / 2, (box[1] - shown[1]) / 2)  # the plan is centred
    left, top = centred_on(x, y, shown, 48)
    centre = (offset[0] + left + 24, offset[1] + top + 24)
    return t.scale * centre[0] + t.x, t.scale * centre[1] + t.y


def image_pixel(
    screen: tuple[float, float],
    box: tuple[float, float],
    natural: tuple[float, float],
    t: Transform,
) -> tuple[float, float]:
    """The image pixel under a screen point: the transform and the fit, undone."""
    shown = fitted(box, natural)
    offset = ((box[0] - shown[0]) / 2, (box[1] - shown[1]) / 2)
    local = ((screen[0] - t.x) / t.scale, (screen[1] - t.y) / t.scale)
    ratio = natural[0] / shown[0]
    return (local[0] - offset[0]) * ratio, (local[1] - offset[1]) * ratio


@pytest.mark.parametrize("name", BOXES)
@pytest.mark.parametrize("natural", [LANDSCAPE_PLAN, PORTRAIT_PLAN])
def test_a_pin_lands_on_its_point_at_fit_and_at_maximum_zoom(
    name: str, natural: tuple[float, float]
) -> None:
    """Room 104C's pin (84 %, 27 %) is on its image pixel at 1x and at max zoom, panned."""
    box = BOXES[name]
    top_scale = max_scale(natural[0], fitted(box, natural)[0])
    for t in (Transform(1.0, 0.0, 0.0), Transform(top_scale, -300.0, -120.0)):
        on_screen = screen_point(84.0, 27.0, box, natural, t)
        pixel = image_pixel(on_screen, box, natural, t)
        assert pixel == pytest.approx((0.84 * natural[0], 0.27 * natural[1]))


def test_centred_on_puts_the_box_centre_on_the_point() -> None:
    """A 48-dp box's centre is the point, in the fitted plan's units."""
    left, top = centred_on(50.0, 25.0, (400.0, 300.0), 48)
    assert (left + 24, top + 24) == (200.0, 75.0)


@pytest.mark.parametrize("factor", [1.5, 1 / 1.5, 2.0])
def test_refocus_keeps_the_focus_on_the_same_plan_point(factor: float) -> None:
    """After ``zoom()`` (about the top-left corner, F76) the pan puts the focus back."""
    before = Transform(1.8, -120.0, -60.0)
    focus = (191.0, 320.0)
    after = Transform(before.scale * factor, before.x, before.y)  # zoom keeps t
    dx, dy = refocus(before, after, focus)
    # pan() moves in the plan's units: scale logical pixels each.
    panned = Transform(
        after.scale, after.x + after.scale * dx, after.y + after.scale * dy
    )
    point_before = (
        (focus[0] - before.x) / before.scale,
        (focus[1] - before.y) / before.scale,
    )
    point_after = (
        (focus[0] - panned.x) / panned.scale,
        (focus[1] - panned.y) / panned.scale,
    )
    assert point_after == pytest.approx(point_before)


def test_refocus_reads_a_clamped_zoom_back() -> None:
    """A zoom clamped at the maximum moves the plan only by what the scale became."""
    before = Transform(5.0, -100.0, -100.0)
    after = Transform(5.0, -100.0, -100.0)  # already at the maximum: nothing changed
    assert refocus(before, after, (190.0, 300.0)) == pytest.approx((0.0, 0.0))


def panned(now: Transform, delta: tuple[float, float]) -> Transform:
    """The transform after ``pan(dx, dy)``: it moves ``scale`` logical pixels a unit (F76)."""
    return Transform(
        now.scale, now.x + now.scale * delta[0], now.y + now.scale * delta[1]
    )


def test_into_bounds_pulls_a_rotated_pan_back_to_the_content_edge() -> None:
    """Zoomed 2x at the right edge in landscape, portrait shows the right edge, no blank."""
    landscape, portrait = BOXES["phone landscape"], BOXES["phone portrait"]
    at_right = Transform(2.0, landscape[0] * (1 - 2.0), -100.0)  # -874: the right edge
    after = panned(at_right, into_bounds(at_right, portrait))
    assert after.x == pytest.approx(portrait[0] * (1 - 2.0))  # -382: the right edge
    assert after.y == pytest.approx(-100.0)  # in bounds on this axis: kept
    # The viewport's right edge is the content's right edge, not past it.
    assert (portrait[0] - after.x) / after.scale == pytest.approx(portrait[0])


def test_into_bounds_pulls_back_a_translation_past_the_top_left() -> None:
    """A positive translation (blank above or left of the content) goes back to 0."""
    now = Transform(1.5, 40.0, 25.0)
    assert panned(now, into_bounds(now, BOXES["tablet"])) == Transform(1.5, 0.0, 0.0)


def test_into_bounds_leaves_a_pan_in_bounds_alone() -> None:
    """A pan already inside the bounds is not moved: no jump on every resize."""
    for box in BOXES.values():
        assert into_bounds(Transform(3.0, -box[0], -box[1]), box) == (0.0, 0.0)


def test_into_bounds_undoes_any_pan_at_fit() -> None:
    """At 1x the only translation in bounds is none: the fitted plan, as Reset view."""
    now = Transform(1.0, -300.0, -50.0)
    after = panned(now, into_bounds(now, BOXES["phone portrait"]))
    assert (after.x, after.y) == pytest.approx((0.0, 0.0))


def zoom_at(scale: float) -> Zoom:
    """A zoom layer's state over the Concourse plan in a 382 x 640 viewer, at ``scale``."""
    return Zoom(
        viewer=ft.Ref[ft.InteractiveViewer](),
        natural=LANDSCAPE_PLAN,
        box=BOXES["phone portrait"],
        scale=scale,
        reset_ms=250,
        tapped_at=[],
        resized=lambda e: None,
        transformed=lambda e: None,
    )


def test_the_limits_tolerate_the_float_scale_a_viewer_reports() -> None:
    """A reported 1.0000004 is the fitted plan; a hair under the maximum is the maximum."""
    assert zoom_at(1.0000004).at_fit
    assert not zoom_at(1.2).at_fit
    top = zoom_at(1.0).max_scale
    assert top == pytest.approx(2048 / 382)
    assert zoom_at(top - 1e-6).at_max
    assert not zoom_at(top / 1.5).at_max
