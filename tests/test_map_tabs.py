"""Tests for the Map's tabs and the panes' places (#391; MAP-01..03).

``Map`` runs in ``tests/map_view.py``'s harness over the 2026 feed and ``map.toml``,
``ListView.scroll_to`` recorded instead of sent to a client. Floor plans' cards, Job
fair and the app bar are ``test_map_panes.py``'s, the Rooms pane's rows
``test_map.py``'s. How the tabs look and read, and that the pane keeps its place on the
device, are checked on devices (the PR).
"""

import dataclasses
from collections.abc import Awaitable, Callable
from typing import cast

import flet as ft
import pytest

from pycon_us.locations import start_target
from pycon_us.memory import ViewMemory
from pycon_us.screens import map as screen
from pycon_us.year_map import MapData
from tests import links, map_view
from tests.map_view import PLAN_IDS, YEAR, Render, pane_shown
from tests.sessions import text_of

open_at = links.open_at  # the fixture, under this module's name (tests/chrome.py)
render = map_view.render  # the fixture, under this module's name


# ------------------------------------------------------------------ the tabs


async def test_the_map_opens_on_rooms_under_its_named_tabs(render: Render) -> None:
    """Rooms, Floor plans, Expo and Job fair are the first row, Rooms shown, no ``TabBarView``.

    Each tab carries ``map.tab.<slug>``; the pane shown is the rooms' keyed list,
    alone under the bar (D-312).
    """
    shown = await render()
    assert shown.tabs.length == 4
    assert shown.tabs.selected_index == 0
    labels = [text_of(tab.label) for tab in shown.find(ft.Tab)]
    assert sorted(labels) == ["Expo", "Floor plans", "Job fair", "Rooms"]
    assert {str(n.identifier) for n in shown.nodes("map.tab.")} == {
        "map.tab.rooms",
        "map.tab.floor-plans",
        "map.tab.expo",
        "map.tab.job-fair",
    }
    assert shown.find(ft.TabBarView) == []
    assert shown.pane.key == "rooms"
    assert shown.nodes("map.room.")
    assert shown.titles[-1] == "Map"


async def test_floor_plans_lists_a_card_per_plan_in_the_map_s_order(
    render: Render,
) -> None:
    """``?tab=floor-plans`` opens the pane: a card per plan, in ``map.toml``'s order."""
    shown = await render("/map?tab=floor-plans")
    assert shown.tabs.selected_index == 1
    assert shown.pane.key == "floor-plans"
    assert shown.cards() == [f"map.plan.{plan}" for plan in PLAN_IDS]
    assert shown.memory.map_tab == "floor-plans"


@pytest.mark.parametrize("route", ["/map?tab=nowhere", "/map?tab="])
async def test_an_unknown_tab_falls_back_to_rooms(render: Render, route: str) -> None:
    """A ``?tab=`` that names no pane opens Rooms, and the memory says Rooms."""
    memory = ViewMemory(map_tab="floor-plans")
    shown = await render(route, memory=memory)
    assert shown.pane.key == "rooms"
    assert memory.map_tab == "rooms"


async def test_a_picked_tab_stays_across_a_new_session(render: Render) -> None:
    """A tab the user picks shows its pane and is remembered: a return finds it (D-18).

    The second Map, in a new session with the same memory, stands in for another
    bottom tab and back (a tab root is built again) and for an activity recreation.
    """
    memory = ViewMemory()
    shown = await render(memory=memory)
    await shown.pick(1)
    assert shown.pane.key == "floor-plans"
    assert memory.map_tab == "floor-plans"
    again = await render(memory=memory)
    assert again.tabs.selected_index == 1
    assert again.pane.key == "floor-plans"


async def pick_in_app(shown: links.Shown, index: int) -> None:
    """Pick a Map tab in the app's Views as the user does, and let the route follow."""
    (tabs,) = shown.find(ft.Tabs)
    shown.session.apply_patch(tabs._i, {"selected_index": index})
    await shown.session.dispatch_event(tabs._i, "change", index)
    await shown.settle()


async def test_a_pick_puts_its_own_tab_in_the_route(render: Render) -> None:
    """A pick navigates to its pane's ``?tab=``: no stale query is left in the route."""
    shown = await render("/map?tab=floor-plans")
    await shown.pick(0)
    await shown.pick(1)
    assert shown.went == ["/map?tab=rooms", "/map?tab=floor-plans"]


async def test_a_pick_over_a_tab_link_survives_search_and_back(
    open_at: links.Open,
) -> None:
    """Rooms, picked on ``/map?tab=floor-plans``, is still shown after Search and Back.

    Search's way back is the route it was opened from (``search_base``): with the old
    query left in it, Back reopened Floor plans (D-18; Codex on #591).
    """
    memory = ViewMemory()
    shown = await open_at("/map?tab=floor-plans", memory=memory)
    assert pane_shown(shown) == "floor-plans"
    await pick_in_app(shown, 0)
    assert shown.page.route == "/map?tab=rooms"
    assert pane_shown(shown) == "rooms"
    (search,) = [b for b in shown.find(ft.IconButton) if b.tooltip == "Search"]
    await shown.click(search)
    await shown.settle()
    assert shown.routes()[-1] == "/search"
    assert await shown.back() == "/map?tab=rooms"
    assert pane_shown(shown) == "rooms"
    assert memory.map_tab == "rooms"


async def test_a_pick_over_a_tab_link_survives_a_new_session(
    open_at: links.Open,
) -> None:
    """A new session, which returns to the last location (D-143), keeps the pick."""
    memory = ViewMemory()
    shown = await open_at("/map?tab=floor-plans", memory=memory)
    await pick_in_app(shown, 0)
    assert memory.last_location == "/map?tab=rooms"
    # Where Start sends the new session (``routes.Start``, checked in test_routes_locations).
    target = start_target(memory.last_location, memory.search_base, onboarded=True)
    assert target == "/map?tab=rooms"
    again = await open_at(target, memory=memory)
    assert pane_shown(again) == "rooms"


async def test_a_pane_s_scroll_is_remembered_and_put_back(render: Render) -> None:
    """Where a pane's scroll ended is kept per pane and put back when it shows again.

    A pane that never scrolled is left at its top: nothing moves by itself (D-18).
    """
    memory = ViewMemory()
    shown = await render(memory=memory)
    assert shown.scrolls == []
    await shown.scroll_end(640.0)
    await shown.pick(1)
    await shown.scroll_end(120.0)
    assert memory.map_offsets == {"rooms": 640.0, "floor-plans": 120.0}
    assert shown.scrolls == []  # Floor plans had not scrolled before
    await shown.pick(0)
    assert shown.scrolls == [("rooms", {"offset": 640.0, "duration": 0})]
    again = await render(memory=memory)
    assert again.scrolls == [("rooms", {"offset": 640.0, "duration": 0})]


async def test_a_retap_scrolls_the_pane_shown_to_its_top(render: Render) -> None:
    """Re-tapping the Map tab scrolls the pane shown, whichever it is (D-166)."""
    shown = await render("/map?tab=floor-plans")
    retap = shown.retaps[-1]
    assert retap is not None
    await cast(Callable[[], Awaitable[None]], retap)()
    ((key, asked),) = shown.scrolls
    assert (key, asked["offset"]) == ("floor-plans", 0)


def test_a_route_to_another_view_says_nothing_of_the_pane() -> None:
    """Only a route that addresses the Map itself picks its pane."""
    memory = ViewMemory(map_tab="floor-plans")
    screen.asked_pane(memory, "/map/plan/upper?tab=rooms", "/map")
    screen.asked_pane(memory, "/search?scope=rooms&tab=rooms", "/map")
    screen.asked_pane(memory, "/map", "/map")  # no query: as it was
    assert memory.map_tab == "floor-plans"
    screen.asked_pane(memory, "/map?tab=rooms", "/map")
    assert memory.map_tab == "rooms"
    assert screen.tab_href("floor-plans") == "/map?tab=floor-plans"


async def test_a_year_without_plans_shows_the_rooms_without_tabs(
    render: Render,
) -> None:
    """With no plans, Floor plans is no pane: the rooms alone, no bar and no tour."""
    year = dataclasses.replace(YEAR, map=MapData())
    assert screen.panes_of(year.map) == (screen.PANES[0],)
    shown = await render("/map?tab=floor-plans", year=year)
    assert shown.find(ft.Tabs) == []
    assert shown.pane.key == "rooms"
    assert shown.find(ft.PopupMenuButton) == []


# ------------------------------------------------------------------ the cards


# ------------------------------------------------------------------ the job fair


# ------------------------------------------------------------------ the app bar
