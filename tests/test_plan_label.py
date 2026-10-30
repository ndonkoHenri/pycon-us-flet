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


def card_parts(plan: plan_view.Plan) -> tuple[ft.Card, ft.Column, ft.Column]:
    """The label card, the ``Column`` that bounds its words and the one that measures them."""
    card = cast(ft.Card, cast(ft.Semantics, plan.node("plan.label").content).content)
    words = cast(ft.Container, card.content).content
    assert isinstance(words, ft.Column)
    (lines,) = words.controls
    assert isinstance(lines, ft.Column) and lines.on_size_change
    return card, words, lines


async def test_a_short_card_keeps_its_own_height(render: Render) -> None:
    """``?pin=103abc`` at the default size: no bound and no scroll, so no stretch.

    A scrolling ``Column`` takes the whole of its bound in Flet (its content's least
    height is the bound), so a card that always scrolled stood ``label_room()`` tall
    with two short lines in it, over the plan (D-444, PR #798's review).
    """
    plan = await render("?pin=103abc")
    await plan.lay_out()
    _, _, lines = card_parts(plan)
    await plan.event(lines, "size_change", {"w": 300.0, "h": 44.0})
    card, words, _ = card_parts(plan)
    assert (card.max_height, words.scroll) == (None, None)


async def test_a_tall_card_scrolls_in_the_room_under_its_pin(render: Render) -> None:
    """``?pin=103abc`` at the largest text: the card is ``label_room()`` high and scrolls."""
    plan = await render("?pin=103abc")
    card, words, _ = card_parts(plan)
    assert (card.max_height, words.scroll) == (None, None)  # not before layout
    await plan.lay_out()
    (pin,) = [p for p in PINS if p.key == "103abc"]
    room = screen.label_room(BOX, fitted(BOX, (2048, 1583)), pin)
    assert room is not None
    _, _, lines = card_parts(plan)
    await plan.event(lines, "size_change", {"w": 300.0, "h": room})
    card, words, _ = card_parts(plan)
    assert (card.max_height, words.scroll) == (room, ft.ScrollMode.AUTO)


@pytest.mark.parametrize(
    ("measured", "expected"), [(48.0, False), (76.0, False), (76.5, True)]
)
def test_the_words_scroll_only_past_the_room(measured: float, expected: bool) -> None:
    """Words and their 12 dp padding above and below scroll only past the room."""
    assert screen.scrolls(100.0, measured) is expected
    assert screen.scrolls(None, measured) is False


@pytest.mark.parametrize("measured", [44.0, 1000.0])
async def test_the_card_is_one_node_labelled_by_its_words(
    render: Render, measured: float
) -> None:
    """The identifier's node takes the words as its label and leaves their nodes out.

    Merged in, the scrolling ``Column`` made the identifier's node a scrollable one,
    which iOS shows as a scroll view without the identifier (#800, D-447): so the
    words are a label, the same whether the card scrolls or not.
    """
    plan = await render("?pin=103abc")
    await plan.lay_out()
    _, _, lines = card_parts(plan)
    await plan.event(lines, "size_change", {"w": 300.0, "h": measured})
    words = cast(ft.Semantics, plan.node("plan.label").content)
    assert words.label == "Room 103\nConcourse level · Talk track / Security track"
    assert words.exclude_semantics is True
    assert card_parts(plan)[1].scroll == (
        ft.ScrollMode.AUTO if measured > 100 else None
    )


async def test_the_viewers_app_bar_stays_still(render: Render) -> None:
    """The plan never scrolls under the bar: the card's words do, so it keeps its colour.

    Flutter's ``AppBar`` takes any scroll in the body at depth 0 for the page's; the
    card's tinted it on iOS at the largest text (#800, D-447).
    """
    plan = await render("?pin=103abc")
    assert plan.still_bars and all(plan.still_bars)
