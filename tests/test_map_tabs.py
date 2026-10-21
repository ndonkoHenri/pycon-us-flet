"""Tests for the Map's tabs, its Floor plans pane and its app bar (#391; MAP-01..03).

``Map`` runs in a real Flet session (``tests/sessions.py``) over the 2026 feed and
``map.toml``. ``ListView.scroll_to`` is recorded instead of sent to a client. The Rooms
pane's rows are ``test_map.py``'s. How the tabs and cards look and read, and that the
pane keeps its place on the device, are checked on devices (the PR).
"""

import dataclasses
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, cast

import flet as ft
import pytest

from pycon_us.config import YearData, load_year
from pycon_us.locations import start_target
from pycon_us.memory import ViewMemory
from pycon_us.prefs import Prefs
from pycon_us.screens import map as screen
from pycon_us.screens import map_plans
from pycon_us.state import Conference
from pycon_us.year_map import MapData
from tests import links, sessions
from tests.feeds import processed
from tests.sessions import Shown, menu_text, text_of
from tests.trees import descendants

YEAR = load_year(2026)
PLAN_IDS = ["campus", "concourse", "upper", "arena", "seaside"]
"""The 2026 floor plans, in ``map.toml``'s order (MAP-02): the expo's and the job
fair's are not among them."""


@dataclasses.dataclass
class MapShown(Shown):
    """The harness's ``Shown`` on the Map, with the scrolls its lists were asked for."""

    scrolls: list[tuple[str, dict[str, Any]]] = dataclasses.field(default_factory=list)
    """Each ``scroll_to``: the list's key and its arguments."""

    @property
    def tabs(self) -> ft.Tabs:
        """The Map's one ``Tabs``."""
        (found,) = self.find(ft.Tabs)
        return found

    @property
    def pane(self) -> ft.ListView:
        """The one pane shown: the ``ListView`` under the tab bar."""
        (found,) = self.find(ft.ListView)
        return found

    def cards(self) -> list[str]:
        """The Floor plans cards' identifiers, in the pane's order."""
        return [
            str(node.identifier)
            for row in self.pane.controls
            for node in descendants(row)
            if isinstance(node, ft.Semantics)
            and str(node.identifier or "").startswith("map.plan.")
        ]

    async def pick(self, index: int) -> None:
        """Pick a tab as the user does: Flutter moves the selection, then reports it."""
        self.session.apply_patch(self.tabs._i, {"selected_index": index})
        await self.session.dispatch_event(self.tabs._i, "change", index)
        await self.settle()

    async def scroll_end(self, pixels: float) -> None:
        """What Flutter sends when a scroll of the pane shown ends at ``pixels``."""
        data = {
            "event_type": "end",
            "pixels": pixels,
            "min_scroll_extent": 0.0,
            "max_scroll_extent": 4000.0,
            "viewport_dimension": 700.0,
        }
        await self.event(self.pane, "scroll", data)


type Render = Callable[..., Awaitable[MapShown]]

open_at = links.open_at  # the fixture, under this module's name (tests/chrome.py)


@pytest.fixture
async def render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Render]:
    """Yield a function that opens the Map at a route and returns its ``MapShown``.

    The route is ``/map`` unless the test gives another (a query); the view memory and
    the year can be given too, a memory kept across sessions as the app keeps it.
    """
    shown_now: list[MapShown] = []

    async def scroll_to(self: ft.ListView, **kwargs: Any) -> None:
        shown_now[-1].scrolls.append((str(self.key), kwargs))

    monkeypatch.setattr(ft.ListView, "scroll_to", scroll_to)
    data = processed(2026)

    async def show(
        stack: AsyncExitStack,
        route: str = "/map",
        *,
        memory: ViewMemory | None = None,
        year: YearData = YEAR,
    ) -> MapShown:
        def make(*args: Any, **kwargs: Any) -> MapShown:
            made = MapShown(*args, **kwargs)
            shown_now.append(made)
            return made

        return await stack.enter_async_context(
            sessions.showing(
                screen.Map,
                screen,
                year=year,
                conference=Conference(data=data, source="bundled", version=1),
                tmp_path=tmp_path,
                monkeypatch=monkeypatch,
                view_path="/map",
                prefs=Prefs(loaded=True),
                memory=memory,
                route=route,
                kind=make,
            )
        )

    async with AsyncExitStack() as stack:

        async def opened(*args: Any, **kwargs: Any) -> MapShown:
            return await show(stack, *args, **kwargs)

        yield opened


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


def pane_shown(shown: links.Shown) -> str:
    """The key of the one Map pane in the app's Views: its slug."""
    slugs = {pane.slug for pane in screen.PANES}
    (pane,) = [lv for lv in shown.find(ft.ListView) if lv.key in slugs]
    return str(pane.key)


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
    # Where Start sends the new session (``routes.Start``, checked in test_routes).
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


# ------------------------------------------------------------------ the job fair


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


# ------------------------------------------------------------------ the app bar


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
