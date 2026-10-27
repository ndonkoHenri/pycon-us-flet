"""Tests for the Map's Floor plans cards, its Job fair pane and its app bar (MAP-01..03).

``Map`` runs in ``tests/map_view.py``'s harness over the 2026 feed and ``map.toml``.
The tabs and the panes' places are ``test_map_tabs.py``'s, the Rooms pane's rows
``test_map.py``'s. How the cards look and read is checked on devices (the PR).
"""

import dataclasses

import flet as ft

from pycon_us.memory import ViewMemory
from pycon_us.screens import map as screen
from pycon_us.screens import map_plans
from tests import links, map_view
from tests.map_view import PLAN_IDS, YEAR, Render, pane_shown
from tests.sessions import menu_text

open_at = links.open_at  # the fixture, under this module's name (tests/chrome.py)
render = map_view.render  # the fixture, under this module's name


async def test_a_card_reads_as_one_button_and_pushes_its_plan(render: Render) -> None:
    """A card is one node, its plan and what is on it, and a tap pushes the viewer.

    Its thumbnail is the bundled 16:10 crop, said by the card's phrase only, and its
    icon says it opens full screen (MAP-02).
    """
    shown = await render("/map?tab=floor-plans")
    node = shown.node("map.plan.concourse")
    assert node.label == (
        "Concourse level floor plan, Tutorials, talk tracks, registration, expo entry"
    )
    assert node.button and node.exclude_semantics
    (image,) = [
        i for i in shown.find(ft.Image) if i.src == "maps/2026/concourse-thumb.webp"
    ]
    assert image.aspect_ratio == map_plans.THUMB_RATIO
    assert image.fit == ft.BoxFit.COVER
    assert image.exclude_from_semantics
    icons = [i.icon for i in shown.find(ft.Icon)]
    assert icons.count(ft.Icons.OPEN_IN_FULL) == len(PLAN_IDS)  # no expo or job fair
    (tile,) = [c for c in shown.find(ft.Container) if c.content is node]
    await shown.click(tile)
    assert shown.went == ["/map/plan/concourse"]


def test_a_plan_without_a_subtitle_is_read_by_its_name() -> None:
    """A plan with nothing said of what is on it reads "<title> floor plan"."""
    plan = YEAR.map.plans[0]
    bare = dataclasses.replace(plan, subtitle="")
    assert map_plans.plan_phrase(bare) == "Campus overview floor plan"


async def test_job_fair_opens_with_its_card_and_the_tables(render: Render) -> None:
    """``?tab=job-fair`` opens the fourth pane: the plan's card over the tables (MAP-04).

    The card is ``LocationCard``'s plan-only form, one button read as where it leads,
    and a tap pushes the floor viewer at ``…/plan/job-fair``, without a pin (D-254).
    """
    shown = await render("/map?tab=job-fair")
    assert shown.tabs.selected_index == 3
    assert shown.pane.key == "job-fair"
    card = shown.node("map.job_fair.location")
    assert card.label == "Open the Job fair & community showcase floor plan"
    assert card.button
    assert shown.node("map.table.bloomberg").label == (
        "Table T2, Bloomberg, 15 open roles"
    )
    (tile,) = [c for c in shown.find(ft.Container) if c.content is card]
    await shown.click(tile)
    assert shown.went == ["/map/plan/job-fair"]


async def test_job_fair_keeps_its_scroll_across_pane_switches(
    render: Render,
) -> None:
    """Where the job fair's scroll ended is put back when its tab is picked again."""
    memory = ViewMemory()
    shown = await render("/map?tab=job-fair", memory=memory)
    await shown.scroll_end(300.0)
    await shown.pick(0)
    await shown.pick(3)
    assert shown.scrolls[-1] == ("job-fair", {"offset": 300.0, "duration": 0})
    assert memory.map_offsets["job-fair"] == 300.0


async def test_a_table_row_opens_its_sponsor_and_back_returns_to_the_pane(
    open_at: links.Open,
) -> None:
    """A row › sponsor › Back finds the Job fair pane again, as the user left it."""
    memory = ViewMemory()
    shown = await open_at("/map?tab=job-fair", memory=memory)
    (row,) = [
        c
        for c in shown.find(ft.Container)
        if isinstance(c.content, ft.Semantics)
        and c.content.identifier == "map.table.bloomberg"
    ]
    await shown.click(row)
    await shown.settle()
    assert shown.routes()[-1] == "/map/sponsor/bloomberg"
    # Back pops to the Map's own path (``parent_of()``, D-141); the pane is memory's.
    assert await shown.back() == "/map"
    assert pane_shown(shown) == "job-fair"


async def test_a_year_without_the_job_fair_plan_has_no_job_fair_tab(
    render: Render,
) -> None:
    """Without a ``job-fair`` plan there is no pane; ``?tab=job-fair`` opens Rooms."""
    plans = tuple(plan for plan in YEAR.map.plans if plan.id != "job-fair")
    year = dataclasses.replace(YEAR, map=dataclasses.replace(YEAR.map, plans=plans))
    assert [pane.slug for pane in screen.panes_of(year.map)] == [
        "rooms",
        "floor-plans",
        "expo",
    ]
    shown = await render("/map?tab=job-fair", year=year)
    assert shown.tabs.length == 3
    assert shown.pane.key == "rooms"


async def test_the_app_bar_searches_places_and_opens_the_tour(render: Render) -> None:
    """Search opens the places scope; the overflow's tour opens in the in-app browser.

    The tour item is a link, read "3D venue tour, Opens in browser" (MAP-03, D-182).
    """
    shown = await render()
    (search,) = [b for b in shown.find(ft.IconButton) if b.tooltip == "Search"]
    await shown.click(search)
    assert shown.went == ["/search?scope=places"]
    assert shown.memory.search_base == "/map"
    (item,) = shown.find(ft.PopupMenuItem)
    text = menu_text(item)
    assert text.value == screen.TOUR
    assert text.semantics_label == "3D venue tour\nOpens in browser"
    assert shown.node("map.overflow")
    await shown.click(item)
    assert shown.launcher.launched == [
        (YEAR.map.tour_url, ft.LaunchMode.IN_APP_BROWSER_VIEW)
    ]
