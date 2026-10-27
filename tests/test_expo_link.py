"""Tests for the expo at a booth: ``?booth=N``, More's Expo hall and the camera (#405).

``…/plan/expo?booth=613`` opens the hall with that booth selected and its card, and a
number the plan doesn't draw opens the List under a live line (EXPO-05). A booth picked
from a link or a List row is brought into view above its card (D-377): the camera's
maths is pure (``screens/expo_camera.py``), and in a session ``FakeViewer`` stands in
for the viewer as in ``test_expo_hall.py``. How the move looks, and what TalkBack and
VoiceOver say of the line, are checked on devices (the PR).
"""

import asyncio
from typing import Any, cast

import flet as ft
import pytest

from pycon_us.config import load_year
from pycon_us.locations import booth_href, parent_of, query_of
from pycon_us.memory import ViewMemory
from pycon_us.screens import expo_pane
from pycon_us.screens.booth_card import BAND, card_layout, covered
from pycon_us.screens.expo_camera import FIT, booth_rect, in_view, shows
from pycon_us.ui.zoom import Size, Transform, fitted, max_scale
from pycon_us.year_map import Booth
from tests import links, test_expo_list
from tests.test_expo_list import ListShown
from tests.viewers import FakeViewer

YEAR = load_year(2026)
PLAN = YEAR.map.plan("expo")
assert PLAN is not None
NATURAL = (float(PLAN.width), float(PLAN.height))
BOX = (382.0, 560.0)
"""The hall's viewer on an iPhone 17 in portrait, in dp."""

BODY = 100.0
"""A one-exhibitor card body's measured height at the default text size, in dp."""

TOP = max_scale(NATURAL[0], fitted(BOX, NATURAL)[0])

open_at = links.open_at  # the fixtures, under this module's names
render = test_expo_list.render


def booth(number: str) -> Booth:
    """The 2026 booth of a number."""
    return next(each for each in YEAR.map.booths if each.number == number)


def free(box: Size = BOX, body: float = BODY) -> float:
    """How far down the viewer is in sight above a card of ``body``'s height."""
    return box[1] - covered(box[1], body)


async def lay_out(shown: Any, body: float = BODY) -> None:
    """Report the top hall's size, then its card body's, as Flutter does."""
    sized: Any = shown.find(ft.InteractiveViewer)[-1]
    while not (isinstance(sized, ft.Container) and sized.on_size_change):
        sized = sized.parent
    await shown.event(sized, "size_change", {"w": BOX[0], "h": BOX[1]})
    for measured in [c for c in shown.find(ft.Column) if c.on_size_change]:
        await shown.event(measured, "size_change", {"w": 300.0, "h": body})


def landed(viewer: FakeViewer) -> Transform:
    """The fake viewer's transform now."""
    return Transform(viewer.scale, viewer.x, viewer.y)


# ------------------------------------------------------------------ links


def test_booth_href_pushes_the_hall_at_a_booth_and_back_returns_to_its_opener() -> None:
    """A sponsor's expo link goes back to the sponsor; the Map's to the Map (D-17)."""
    sponsor = "/more/sponsors/sponsor/bloomberg"
    location = booth_href(sponsor, "613")
    assert location == f"{sponsor}/plan/expo?booth=613"
    assert query_of(location) == {"booth": "613"}
    assert parent_of(location) == sponsor
    assert parent_of(booth_href("/map", "613")) == "/map"
    assert booth_href("/map", "6 1/3") == "/map/plan/expo?booth=6%201%2F3"  # D-42
    assert query_of(booth_href("/map", "6 1/3")) == {"booth": "6 1/3"}


def test_more_s_expo_hall_returns_to_more() -> None:
    """``/more/plan/expo`` is one pushed View: Back returns to More."""
    assert parent_of("/more/plan/expo") == "/more"


# ------------------------------------------------------------------ seeding


def test_a_link_to_a_booth_on_the_plan_selects_it_on_the_map() -> None:
    """The booth is selected and the Map shown, as a List row's tap does."""
    memory = ViewMemory(expo_view="list", expo_booth="726")
    assert expo_pane.seed(memory, "613", {"613", "726"}) == ("613", "")
    assert (memory.expo_booth, memory.expo_view) == ("613", "map")


def test_a_link_to_a_booth_off_the_plan_leaves_the_memory_for_the_list() -> None:
    """A number the plan doesn't draw is the List's line; no link changes nothing."""
    memory = ViewMemory(expo_booth="726")
    assert expo_pane.seed(memory, "139", {"613", "726"}) == ("", "139")
    assert expo_pane.seed(memory, "", {"613", "726"}) == ("", "")
    assert memory == ViewMemory(expo_booth="726")
    assert expo_pane.missing_line("139") == "Booth 139 isn't on the map yet"


# ------------------------------------------------------------------ the camera


def test_a_booth_in_sight_keeps_the_camera_where_it_was() -> None:
    """In sight at the start, the start; else in sight at fit, the fitted plan."""
    high = booth("342")
    cover = covered(BOX[1], BODY)
    kept = Transform(1.5, -60.0, -100.0)  # the pane's last zoom, 342 in it
    assert in_view(high, BOX, NATURAL, cover=cover, top=TOP, start=kept) == kept
    out = Transform(TOP, 0.0, 0.0)  # the top-left corner, far from 342
    assert in_view(high, BOX, NATURAL, cover=cover, top=TOP, start=out) == FIT
    assert in_view(booth("407"), BOX, NATURAL, cover=cover, top=TOP, start=FIT) != FIT


@pytest.mark.parametrize("number", [each.number for each in YEAR.map.booths])
def test_any_booth_lands_above_its_card_at_the_least_zoom(number: str) -> None:
    """Every 2026 booth shows above a card, the translation in the viewer's bounds."""
    cover = covered(BOX[1], BODY)
    rect = booth_rect(booth(number), BOX, NATURAL)
    to = in_view(booth(number), BOX, NATURAL, cover=cover, top=TOP, start=FIT)
    assert shows(rect, to, BOX[0], BOX[1] - cover)
    assert 1.0 <= to.scale <= TOP
    for t, side in ((to.x, BOX[0]), (to.y, BOX[1])):
        assert side * (1 - to.scale) - 1e-9 <= t <= 0.0
    if to != FIT:  # the least zoom: its centre goes to the band's middle
        centre = to.scale * (rect[1] + rect[3] / 2) + to.y
        assert centre == pytest.approx((BOX[1] - cover) / 2)


@pytest.mark.parametrize("box", [(360.0, 464.0), BOX], ids=["short", "iphone"])
@pytest.mark.parametrize("body", [280.0, 1000.0])
def test_a_tall_card_leaves_a_band_every_booth_lands_in(box: Size, body: float) -> None:
    """A tall card puts the zoom buttons in a row, so each booth still shows above it.

    Under the buttons' column, a 280 dp body in a 360 x 464 pane covered the whole
    pane and booth 407 stayed under the card; the row gives back 112 dp (D-377).
    """
    row, _ = card_layout(box[1], body)
    assert row
    cover = covered(box[1], body)
    assert box[1] - cover >= BAND
    top = max_scale(NATURAL[0], fitted(box, NATURAL)[0])
    for each in YEAR.map.booths:
        to = in_view(each, box, NATURAL, cover=cover, top=top, start=FIT)
        assert shows(booth_rect(each, box, NATURAL), to, box[0], box[1] - cover)


def test_no_band_above_the_card_leaves_the_camera_alone() -> None:
    """A card and buttons as tall as the pane leave nothing to bring a booth into."""
    kept = Transform(2.0, -10.0, -10.0)
    assert (
        in_view(booth("407"), BOX, NATURAL, cover=BOX[1], top=TOP, start=kept) == kept
    )


# ------------------------------------------------------------------ sessions


async def test_a_link_opens_the_hall_with_its_booth_in_view_and_back_returns(
    open_at: links.Open, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``/map/plan/expo?booth=407``: selected, its card, above it; Back to the Map."""
    viewer = FakeViewer()
    viewer.install(monkeypatch)
    shown = await open_at("/map/plan/expo?booth=407")
    assert shown.routes() == ["/", "/map/plan/expo"]
    assert shown.node("expo.card").label == "Booth 407, Python Software Foundation"
    await lay_out(shown)
    assert shown.node("expo.booth.407").selected is True
    assert [name for name, _ in viewer.calls] == ["reset", "zoom", "pan"]
    rect = booth_rect(booth("407"), BOX, NATURAL)
    assert shows(rect, landed(viewer), BOX[0], free())
    viewer.calls.clear()
    await lay_out(shown, body=BODY + 20)  # a later card height moves nothing
    assert viewer.calls == []
    assert await shown.back() == "/map"


async def test_a_link_off_the_plan_opens_the_list_with_a_live_line(
    open_at: links.Open,
) -> None:
    """Phemeral's booth 139: the List, "isn't on the map yet", Back to the sponsor."""
    sponsor = "/more/sponsors/sponsor/phemeral"
    shown = await open_at(booth_href(sponsor, "139"))
    assert shown.memory.expo_view == ""  # not the user's pick
    note = shown.node("expo.missing")
    assert note.live_region is True
    assert "Booth 139 isn't on the map yet" in shown.texts()
    assert shown.has("expo.sponsor.phemeral")  # under "Not on the map yet"
    (switch,) = shown.find(ft.SegmentedButton)
    assert switch.selected == ["list"]
    shown.session.apply_patch(switch._i, {"selected": ["map"]})
    await shown.session.dispatch_event(switch._i, "change", ["map"])
    await shown.settle()
    assert not shown.has("expo.missing")
    assert shown.memory.expo_view == "map"
    assert await shown.back() == sponsor


async def test_more_s_expo_hall_pushes_the_hall_and_back_returns_to_more(
    open_at: links.Open, monkeypatch: pytest.MonkeyPatch
) -> None:
    """More › Expo hall: the hall on More, no booth picked; Back to More."""
    viewer = FakeViewer()
    viewer.install(monkeypatch)
    shown = await open_at("/more")
    await shown.click(cast(ft.Control, shown.node("more.expo").content))
    assert shown.routes() == ["/", "/more/plan/expo"]
    await lay_out(shown)
    assert len(shown.nodes("expo.booth.")) == 61
    assert not shown.has("expo.card")
    assert viewer.calls == []
    assert await shown.back() == "/more"
    assert shown.routes() == ["/"]


async def test_a_row_brings_its_booth_into_view_above_its_card(
    render: test_expo_list.Render, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A List row low on the plan: the hall zooms just enough to show it (D-377)."""
    viewer = FakeViewer()
    viewer.install(monkeypatch)
    shown: ListShown = await render(screen_reader=True)
    await shown.tap_row("407")
    assert viewer.calls == []  # not before the hall and its card are laid out
    await lay_out(shown)
    assert [name for name, _ in viewer.calls] == ["reset", "zoom", "pan"]
    expected = in_view(
        booth("407"), BOX, NATURAL, cover=covered(BOX[1], BODY), top=TOP, start=FIT
    )
    assert (viewer.scale, viewer.x, viewer.y) == pytest.approx(
        (expected.scale, expected.x, expected.y)
    )


async def test_a_row_in_sight_or_a_tap_on_the_plan_leaves_the_camera(
    render: test_expo_list.Render, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A booth in sight at fit stays put; a tap never moves the camera."""
    viewer = FakeViewer()
    viewer.install(monkeypatch)
    shown: ListShown = await render(screen_reader=True)
    row = next(key for key in shown.listed if key.startswith("row.638"))
    await shown.tap_row(row.removeprefix("row."))
    await lay_out(shown)
    assert viewer.calls == []
    await shown.click(cast(ft.Container, shown.node("expo.booth.407").content))
    await lay_out(shown)
    assert viewer.calls == []


async def test_a_card_measured_mid_restore_lets_the_kept_zoom_land(
    render: test_expo_list.Render, monkeypatch: pytest.MonkeyPatch
) -> None:
    """List to Map with a booth selected: the card's measure doesn't cancel the move.

    Flutter answers the viewer's calls later than the card's size arrives; the kept
    zoom (D-312) still lands once it does, as no booth is to be revealed.
    """
    viewer = FakeViewer(hold=asyncio.Event())
    viewer.install(monkeypatch)
    kept = (2.0, -100.0, -100.0)
    memory = ViewMemory(expo_view="list", expo_booth="726", map_zooms={"expo": kept})
    shown: ListShown = await render(memory=memory)
    await shown.show(expo_pane.MAP)
    await lay_out(shown)  # the viewer's size, then the card's, the reset held
    assert viewer.calls == [("reset", None)]
    assert viewer.hold is not None
    viewer.hold.set()
    await shown.settle()
    assert [name for name, _ in viewer.calls] == ["reset", "zoom", "pan"]
    assert landed(viewer) == pytest.approx(Transform(*kept))
