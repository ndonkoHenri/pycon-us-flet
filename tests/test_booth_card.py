"""Tests for the booth card under the expo plan (#403; EXPO-03, D-254).

The Map's Expo pane runs as `tests/test_expo_hall.py` runs it, over the 2026 feed:
a tap on a booth shows its card at the bottom of the hall, under the zoom buttons. How
the card looks, that it wraps at 200 % text and what TalkBack and VoiceOver say are
checked on devices (the PR).
"""

from typing import Any, cast

import flet as ft
import pytest

from pycon_us.core.expo import ExpoBooth
from pycon_us.prefs import Prefs
from pycon_us.screens import booth_card, expo, expo_layout
from tests import links, test_expo_hall
from tests.feeds import processed
from tests.test_expo_hall import BOX, ExpoShown, Render
from tests.viewers import FakeViewer

render = test_expo_hall.render  # the fixture, under this module's name
open_at = links.open_at


def card(shown: ExpoShown) -> ft.Semantics:
    """The card's head, `expo.card`: one node in a live region."""
    return shown.node(f"{expo.SCREEN}.card")


def row_labels(shown: ExpoShown) -> list[str]:
    """A shared booth's rows' labels, in the card's order."""
    placed = []
    for node in shown.nodes(f"{expo.SCREEN}.card.sponsor."):
        row = cast(ft.Control, cast(ft.Control, node.parent).parent)
        rows = cast(ft.Column, row.parent)
        placed.append((rows.controls.index(row), str(node.label)))
    return [label for _, label in sorted(placed)]


def sponsor_of(name: str) -> Any:
    """The 2026 feed's sponsor of this name."""
    data = processed(2026)
    return next(
        s for level in data.sponsor_levels for s in level.sponsors if s.name == name
    )


async def test_a_booth_of_one_shows_its_sponsor_level_and_roles(render: Render) -> None:
    """Booth 613: Bloomberg, "Booth 613 · Visionary", the roles line, Sponsor details."""
    shown = await render(reduce_motion=True)
    await shown.lay_out()
    await shown.tap("613")
    head = card(shown)
    assert (
        head.label == "Booth 613, Bloomberg, Visionary sponsor, hiring, 15 open roles"
    )
    assert head.live_region is True
    texts = shown.texts()
    assert {"Bloomberg", "Booth 613 · Visionary", "Hiring · 15 open roles"} <= set(
        texts
    )
    assert shown.nodes(f"{expo.SCREEN}.card.sponsor.") == []  # no rows for one
    details = shown.node(f"{expo.SCREEN}.card.details")
    await shown.click(cast(ft.FilledTonalButton, details.content))
    assert shown.went[-1] == "/map/sponsor/bloomberg"


async def test_a_shared_booth_lists_every_exhibitor_by_name(render: Render) -> None:
    """Booth 726: "Booth 726 · Community", four rows in name order, no Sponsor details."""
    shown = await render(reduce_motion=True)
    await shown.lay_out()
    await shown.tap("726")
    assert card(shown).label == "Booth 726, Community, 4 exhibitors"
    assert {"Booth 726 · Community", "4 exhibitors"} <= set(shown.texts())
    assert shown.nodes(f"{expo.SCREEN}.card.details") == []
    assert row_labels(shown) == [
        "Inland Empire Python Users Group, Community sponsor",
        "PyBeach, Community sponsor",
        "San Diego Python, Community sponsor",
        "SoCal Python, Community sponsor",
    ]
    pybeach = shown.node(f"{expo.SCREEN}.card.sponsor.pybeach")
    assert pybeach.button
    await shown.click(cast(ft.Container, pybeach.parent))
    assert shown.went[-1] == "/map/sponsor/pybeach"


async def test_a_booth_without_an_exhibitor_shows_its_label(render: Render) -> None:
    """Booth 407: its label and a place icon, no sponsor action and no roles line."""
    shown = await render(reduce_motion=True)
    await shown.lay_out()
    await shown.tap("407")
    assert card(shown).label == "Booth 407, Python Software Foundation"
    assert {"Python Software Foundation", "Booth 407"} <= set(shown.texts())
    assert shown.nodes(f"{expo.SCREEN}.card.details") == []
    assert shown.nodes(f"{expo.SCREEN}.card.sponsor.") == []
    icons = [icon.icon for icon in shown.find(ft.Icon)]
    assert ft.Icons.PLACE_OUTLINED in icons


async def test_close_clears_the_booth_and_its_card(render: Render) -> None:
    """Close deselects: no card, no selected booth; the zoom buttons stay."""
    shown = await render(reduce_motion=True)
    await shown.lay_out()
    await shown.tap("613")
    close = shown.node(f"{expo.SCREEN}.card.close")
    assert cast(ft.IconButton, close.content).tooltip == booth_card.CLOSE
    await shown.click(cast(ft.IconButton, close.content))
    assert shown.memory.expo_booth == ""
    assert shown.nodes(f"{expo.SCREEN}.card") == []
    assert shown.booth("613").selected is None
    assert shown.nodes(f"{expo.SCREEN}.zoom_in")


async def test_the_zoom_buttons_sit_above_the_card(render: Render) -> None:
    """One bottom column: the zoom buttons first, then the card, both in reach."""
    shown = await render(reduce_motion=True)
    await shown.lay_out()
    await shown.tap("613")
    (bottom,) = [c for c in shown.find(ft.Column) if c.bottom == 16]
    first, second = bottom.controls
    assert isinstance(first, ft.Row)
    assert shown.nodes(f"{expo.SCREEN}.zoom_in")
    assert not isinstance(second, ft.Row)


@pytest.mark.parametrize("number", ["613", "726"])
@pytest.mark.parametrize("height", [200.0, 400.0])
async def test_a_body_taller_than_half_the_pane_scrolls(
    render: Render, number: str, height: float
) -> None:
    """A body taller than half the pane scrolls in a box half its height; Close stays.

    Many exhibitors or the largest text (D-254, D-370): the zoom buttons above the
    card and most of the plan stay in sight, and Close is outside the scroll.
    """
    shown = await render(reduce_motion=True)
    await shown.lay_out()
    await shown.tap(number)
    (measured,) = [c for c in shown.find(ft.Column) if c.on_size_change]
    await shown.event(measured, "size_change", {"w": 300.0, "h": height})
    (measured,) = [c for c in shown.find(ft.Column) if c.on_size_change]
    box = cast(ft.Column, cast(ft.Control, measured.parent).parent)
    half = BOX[1] / 2
    if height > half:
        assert (box.height, box.scroll) == (half, ft.ScrollMode.AUTO)
    else:
        assert (box.height, box.scroll) == (None, None)
    close = shown.node(f"{expo.SCREEN}.card.close")
    beside = cast(ft.Row, cast(ft.Control, close.parent).parent)
    assert beside.controls[0] is box  # Close is the scroll's sibling, not inside it


def zoom_in_top(pane: float, body: float) -> float:
    """Where Zoom in's top sits in a pane, in dp from its top, for a measured body.

    The bottom column's own arithmetic, from its parts: the bottom inset, the card's
    padding, the body's box (or its content and top padding when it fits), the gap
    and the buttons. Below 0, the Stack clips the button.
    """
    row, box = expo_layout.card_layout(pane, body)
    shown = box if box is not None else body + expo_layout.BODY_TOP
    buttons = expo_layout.ROW_DP if row else expo_layout.COLUMN_DP
    edge = expo_layout.EDGE
    return pane - edge - sum(expo_layout.CARD_PADDING) - shown - edge - buttons


@pytest.mark.parametrize("pane", [200.0, 300.0, 360.0, 463.0, 464.0, 560.0, 900.0])
@pytest.mark.parametrize("body", [40.0, 150.0, 1000.0])
def test_the_zoom_buttons_stay_in_the_pane(pane: float, body: float) -> None:
    """Whatever the pane and the body, Zoom in keeps an inset above it (D-370).

    A landscape pane 300 dp high put the column's Zoom in 66 dp above the pane, with
    a half-pane box under it; the buttons go in a row there, and the box takes what
    is left when that is less than half the pane.
    """
    assert zoom_in_top(pane, body) >= expo_layout.EDGE
    row, box = expo_layout.card_layout(pane, body)
    if pane < expo_layout.ROW_UNDER:
        assert row
    elif not row:  # the column, unless it leaves the plan too thin a band (D-377)
        assert pane - expo_layout.covered(pane, body) >= expo_layout.BAND
    if box is not None:
        assert box <= pane / 2


async def test_a_short_pane_puts_the_zoom_buttons_in_a_row(render: Render) -> None:
    """A landscape pane lays the zoom buttons in a row and bounds the card under them."""
    shown = await render(reduce_motion=True)
    await shown.lay_out((700.0, 300.0))
    await shown.tap("726")
    (measured,) = [c for c in shown.find(ft.Column) if c.on_size_change]
    await shown.event(measured, "size_change", {"w": 600.0, "h": 400.0})
    zoom_in = shown.node(f"{expo.SCREEN}.zoom_in")
    buttons = cast(ft.Control, cast(ft.Control, zoom_in.parent).parent)
    assert isinstance(buttons, ft.Row) and len(buttons.controls) == 3
    (measured,) = [c for c in shown.find(ft.Column) if c.on_size_change]
    box = cast(ft.Column, cast(ft.Control, measured.parent).parent)
    assert (box.height, box.scroll) == (150.0, ft.ScrollMode.AUTO)


async def test_a_pulse_or_a_zoom_does_not_re_render_the_card(
    render: Render, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The card is memoised on values: only a new booth runs its body (D-153, F150)."""
    shown = await render()
    runs: list[str] = []
    phrase = booth_card.card_phrase

    def counted(item: ExpoBooth, hiring: str) -> str:
        runs.append(item.booth.number)
        return phrase(item, hiring)

    monkeypatch.setattr(booth_card, "card_phrase", counted)
    await shown.lay_out()
    await shown.tap("613")
    for _ in range(2 * expo.PULSES):
        await shown.sleeps.release()
    shown.viewer.scale = 2.0
    await shown.transformed()
    assert runs == ["613"]


def test_hiring_says_the_roles_or_only_that_it_hires() -> None:
    """Roles counted; a long-form listing is "Hiring"; a placeholder and no feed, none."""
    data = processed(2026)
    assert booth_card.hiring_line(data, sponsor_of("Bloomberg")) == (
        "Hiring · 15 open roles"
    )
    assert booth_card.hiring_line(data, sponsor_of("marimo")) == "Hiring"
    assert booth_card.hiring_line(data, sponsor_of("OpenEDG Python Institute")) == ""
    assert booth_card.hiring_line(None, sponsor_of("Bloomberg")) == ""


async def test_back_from_sponsor_details_keeps_the_booth_and_card(
    open_at: links.Open, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sponsor details pushes the sponsor; Back shows 613 still selected, with its card."""
    FakeViewer().install(monkeypatch)
    shown = await open_at("/map?tab=expo", prefs=Prefs(loaded=True, reduce_motion=True))
    sized: Any = shown.find(ft.InteractiveViewer)[-1]
    while not (isinstance(sized, ft.Container) and sized.on_size_change):
        sized = sized.parent  # the viewer's measured box (ui/zoom.py)
    await shown.event(sized, "size_change", {"w": BOX[0], "h": BOX[1]})
    node = shown.node(f"{expo.SCREEN}.booth.613")
    await shown.click(cast(ft.Container, node.content))
    details = shown.node(f"{expo.SCREEN}.card.details")
    await shown.click(cast(ft.FilledTonalButton, details.content))
    await shown.settle()
    assert shown.routes() == ["/", "/map/sponsor/bloomberg"]
    await shown.back()
    assert shown.routes() == ["/"]
    assert shown.node(f"{expo.SCREEN}.booth.613").selected is True
    assert str(shown.node(f"{expo.SCREEN}.card").label).startswith(
        "Booth 613, Bloomberg"
    )


async def test_sponsor_details_wraps_rather_than_overflowing(render: Render) -> None:
    """Its row bounds the button, so the label wraps at iOS's largest text (#1091)."""
    shown = await render(reduce_motion=True)
    await shown.lay_out()
    await shown.tap("613")
    details = shown.node(f"{expo.SCREEN}.card.details")
    # `named()` puts a `MergeSemantics` around its node.
    (row,) = [
        c
        for c in shown.find(ft.Row)
        if any(getattr(child, "content", None) is details for child in c.controls)
    ]
    assert row.wrap


@pytest.mark.parametrize("large_text", [False, True])
async def test_at_large_text_the_head_s_words_go_under_its_logo(
    render: Render, large_text: bool
) -> None:
    """Beside a logo and Close, "Bloomberg" broke inside itself at iOS's largest text (D-497)."""
    shown = await render(prefs=Prefs(loaded=True, time_above=large_text))
    await shown.lay_out()
    await shown.tap("613")
    assert isinstance(card(shown).content, ft.Column if large_text else ft.Row)
