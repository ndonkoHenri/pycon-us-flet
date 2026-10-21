"""Tests for the job fair's tables on the floor viewer (#464; MAP-04, D-254, D-312).

``PlanViewer`` runs in a real Flet session over the 2026 ``map.toml`` and the recorded
feed, with ``test_plan.py``'s harness. How the selection looks over the print, and
that each area covers its printed table on screen, are checked on devices (the PR).
"""

from typing import cast

import flet as ft
import pytest

from pycon_us.memory import ViewMemory
from pycon_us.screens import plan_tables
from pycon_us.state import Conference
from pycon_us.ui import zoom
from tests.feeds import processed
from tests.test_plan import BOX, YEAR, Plan, Render, render  # noqa: F401  (the fixture)
from tests.trees import texts

VIEW = "/map/room/room-104c/plan/job-fair"
"""The job fair plan's View path in ``test_plan.py``'s harness."""

FEED = Conference(data=processed(2026), source="bundled", version=1)
"""The store holding the recorded 2026 feed."""


@pytest.fixture
def show(render: Render) -> Render:  # noqa: F811
    """``test_plan.py``'s ``render``: the floor viewer at a route, in a Flet session."""
    return render


def areas(plan: Plan) -> dict[str, ft.Semantics]:
    """The tables' tap areas on the plan, by table number."""
    return {
        str(node.identifier).removeprefix("plan.table."): node
        for node in plan.nodes("plan.table.")
    }


def selected(plan: Plan) -> list[str]:
    """The numbers of the tables whose areas say they are selected."""
    return [number for number, node in areas(plan).items() if node.selected]


def card_texts(plan: Plan) -> list[str]:
    """The texts of the table's card, in reading order."""
    return texts(plan.node("plan.table_card"))


async def test_the_query_selects_its_table_with_the_feed_s_sponsors(
    show: Render,
) -> None:
    """``?table=T7``: T7 is selected, amber, and its card lists Chainguard and Red Hat.

    The print shows Temporal at T7; the feed wins (D-254).
    """
    plan = await show("?table=T7", plan_id="job-fair", conference=FEED)
    await plan.lay_out()
    assert len(areas(plan)) == 20
    assert selected(plan) == ["T7"]
    node = areas(plan)["T7"]
    assert node.button and node.label == "Table T7, Chainguard, Red Hat"
    box = cast(ft.Container, node.content)
    assert box.bgcolor == ft.Colors.with_opacity(
        plan_tables.FILL_OPACITY, plan_tables.AMBER
    )
    assert card_texts(plan) == ["Table T7", "Chainguard", "Red Hat"]
    assert plan.image.semantics_label == (
        "Job fair & community showcase floor plan, Table T7 selected"
    )
    assert plan.memory.plan_tables == {VIEW: "T7"}


async def test_an_area_is_placed_from_its_ratios_on_the_fitted_plan(
    show: Render,
) -> None:
    """T1's area is its ``map.toml`` rectangle times the plan's fitted size."""
    plan = await show(plan_id="job-fair")
    await plan.lay_out()
    width, height = zoom.fitted(BOX, (1700, 1438))
    table = YEAR.map.table("T1")
    assert table is not None
    (area,) = [c for c in plan.find(ft.Container) if c.content is areas(plan)["T1"]]
    assert (area.left, area.top, area.width, area.height) == (
        table.x * width,
        table.y * height,
        table.w * width,
        table.h * height,
    )


async def test_the_plan_with_tables_has_no_double_tap(show: Render) -> None:
    """A double tap would delay every table's tap (D-312); the buttons still zoom."""
    plan = await show(plan_id="job-fair")
    await plan.lay_out()
    assert plan.find(ft.GestureDetector) == []
    assert plan.nodes("plan.zoom_in")


async def test_a_tap_selects_a_table_and_a_sponsor_row_pushes_the_sponsor(
    show: Render,
) -> None:
    """A tap on T2 selects it in place; its card's Bloomberg row pushes the sponsor."""
    plan = await show("?table=T7", plan_id="job-fair", conference=FEED)
    await plan.lay_out()
    await plan.click(cast(ft.Container, areas(plan)["T2"].content))
    assert selected(plan) == ["T2"]
    assert card_texts(plan) == ["Table T2", "Bloomberg"]
    assert plan.memory.plan_tables == {VIEW: "T2"}
    (row,) = plan.nodes("plan.table_sponsor.bloomberg")
    assert row.button and row.label == "Bloomberg, sponsor details"
    container = next(
        c for c in plan.find(ft.Container) if c.content is row and c.on_click
    )
    await plan.click(container)
    assert plan.went == [f"{VIEW}/sponsor/bloomberg"]


async def test_a_table_without_a_sponsor_says_so(show: Render) -> None:
    """T13 is printed but the feed puts nobody there: "No sponsor listed at T13"."""
    plan = await show("?table=T13", plan_id="job-fair", conference=FEED)
    await plan.lay_out()
    assert areas(plan)["T13"].label == "Table T13, no sponsor listed"
    assert card_texts(plan) == ["Table T13", "No sponsor listed at T13"]


async def test_a_feed_table_off_the_plan_opens_the_plan_saying_so(
    show: Render,
) -> None:
    """``?table=T21``, which has no rectangle: nothing selected, and the card says why."""
    plan = await show("?table=T21", plan_id="job-fair", conference=FEED)
    await plan.lay_out()
    assert selected(plan) == []
    assert card_texts(plan) == [
        "Table T21 isn't on the plan yet",
        "No sponsor listed at T21",
    ]


async def test_without_the_feed_a_table_is_named_alone(show: Render) -> None:
    """Before the feed: "Table T7", on the plan and in the card, no sponsor claimed."""
    plan = await show("?table=T7", plan_id="job-fair")
    await plan.lay_out()
    assert areas(plan)["T7"].label == "Table T7"
    assert card_texts(plan) == ["Table T7"]


async def test_a_view_below_the_top_keeps_its_table_and_back_forgets_it(
    show: Render,
) -> None:
    """Without its query the table comes from memory (D-18); leaving removes it."""
    memory = ViewMemory(plan_tables={VIEW: "T10"})
    plan = await show(plan_id="job-fair", memory=memory)
    await plan.lay_out()
    assert selected(plan) == ["T10"]
    await plan.show(False)
    assert plan.memory.plan_tables == {}


@pytest.mark.parametrize("query", ["?table=T7", ""])
async def test_other_plans_have_no_tables(show: Render, query: str) -> None:
    """The Concourse level ignores ``?table=``: no areas, no card, its double tap."""
    plan = await show(query, conference=FEED)
    await plan.lay_out()
    assert areas(plan) == {}
    assert plan.nodes("plan.table_card") == []
    assert len(plan.find(ft.GestureDetector)) == 1
    assert plan.memory.plan_tables == {}


def test_table_href_pushes_the_job_fair_plan_with_the_table() -> None:
    """The way in from the pane and sponsor detail: ``…/plan/job-fair?table=T8``."""
    assert plan_tables.table_href("/map", "T8") == "/map/plan/job-fair?table=T8"
    assert plan_tables.show_table_label("T8") == "Show table T8 on the plan"
