"""Tests for the floor viewer's label card at large text (#793, D-444).

At iOS's largest text with Bold Text the card grew over half the Concourse plan and
hid Room 103's pin at fit. Its height is now bound by what the fitted plan leaves
under the pin (``plan_label.label_room()``), and its words scroll inside it. The viewer
sizes below are the floor viewer's body on the devices #793 names; that the card
scrolls and stays one node is checked on them (the PR).
"""

from typing import cast

import flet as ft
import pytest

from pycon_us.screens import plan_label as screen
from pycon_us.ui.zoom_geometry import Size, fitted
from pycon_us.year_map import Pin
from tests import plan_view
from tests.plan_view import BOX, YEAR, Render

render = plan_view.render

VIEWERS = {
    "harness": BOX,
    # The body under the app bar, measured on iOS 26.5 at the largest text (#793).
    "iphone17": (402.0, 709.0),
    # 720 x 1600 px at 280 dpi, less the status bar, the app bar and the nav bar.
    "avd-720px": (720 / 1.75, 778.0),
}
"""The floor viewer's size, in dp, in portrait."""

PINS = list(YEAR.map.pins)


def ring_bottom(box: Size, pin: Pin) -> float:
    """Where the pin's ring, at its widest, ends on screen at the fitted plan."""
    plan = YEAR.map.plan(pin.plan)
    assert plan is not None
    shown = fitted(box, (plan.width, plan.height))
    return (box[1] - shown[1]) / 2 + pin.y / 100 * shown[1] + screen.PIN_BOX / 2


@pytest.mark.parametrize("viewer", VIEWERS)
@pytest.mark.parametrize("pin", PINS, ids=[pin.key for pin in PINS])
def test_the_card_at_its_tallest_ends_under_the_pin(viewer: str, pin: Pin) -> None:
    """Every 2026 pin stays in sight at fit above the card at its greatest height."""
    box = VIEWERS[viewer]
    plan = YEAR.map.plan(pin.plan)
    assert plan is not None
    room = screen.label_room(box, fitted(box, (plan.width, plan.height)), pin)
    assert room is not None
    assert room > screen.LABEL_MIN  # the floor never puts the card over a pin
    assert box[1] - screen.EDGE - room >= ring_bottom(box, pin) - 1e-9


def test_a_pin_low_on_a_short_viewer_still_leaves_the_card_a_line() -> None:
    """In landscape a low pin leaves less than a line: the card keeps ``LABEL_MIN``."""
    (pin,) = [p for p in PINS if p.key == "halla"]
    box = (800.0, 300.0)
    assert screen.label_room(box, fitted(box, (1583, 2048)), pin) == screen.LABEL_MIN


def test_no_bound_before_the_viewer_is_laid_out() -> None:
    """Before ``on_size_change`` there is no pin on screen to keep clear."""
    (pin,) = [p for p in PINS if p.key == "103abc"]
    assert screen.label_room((0.0, 0.0), (0.0, 0.0), pin) is None


async def test_the_card_scrolls_in_the_room_under_its_pin(render: Render) -> None:
    """``?pin=103abc``: the card is bound by ``label_room()`` and its words scroll."""
    plan = await render("?pin=103abc")
    card = cast(ft.Card, plan.node("plan.label").content)
    assert card.max_height is None  # not before the viewer is laid out
    await plan.lay_out()
    (pin,) = [p for p in PINS if p.key == "103abc"]
    card = cast(ft.Card, plan.node("plan.label").content)
    assert card.max_height == screen.label_room(BOX, fitted(BOX, (2048, 1583)), pin)
    words = cast(ft.Container, card.content).content
    assert isinstance(words, ft.Column)
    assert words.scroll == ft.ScrollMode.AUTO
