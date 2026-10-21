"""Map (``/map``): Rooms, Floor plans and Job fair as tabs, one pane shown (MAP-01..04).

The tab bar is the body's first row (U10's interim) and the selected pane alone sits
under it, each pane with its own key, with no swipeable ``TabBarView``: its pages took
a zoomed plan's horizontal pans (D-312, S7; U110). ``ViewMemory.map_tab`` keeps the
pane and ``ViewMemory.map_offsets`` each pane's scroll, so another bottom tab and back
finds both (D-18); ``/map?tab=job-fair`` opens a pane, an unknown value Rooms, and
a pick puts its own ``?tab=`` in the route, so a return or a new session finds it. A
re-tap of the Map tab scrolls the pane shown (D-166). The overflow's "3D venue tour"
opens ``map.toml``'s ``tour_url`` in the in-app browser (MAP-03, D-182). A year
without plans shows the rooms alone, without a tab bar; Job fair needs the year's
``job-fair`` plan (ux.md §5.8, §6.3). The expo pane joins ``PANES`` with #402.

The panes: Rooms in ``screens/map_rooms.py``, Floor plans in ``screens/map_plans.py``,
Job fair in ``screens/map_job_fair.py``.
"""

from dataclasses import dataclass

import flet as ft

from pycon_us.locations import is_top_view, query_of
from pycon_us.memory import ViewMemory
from pycon_us.prefs import use_prefs
from pycon_us.screens.map_job_fair import JOB_FAIR, JobFairPane
from pycon_us.screens.map_plans import FLOOR_PLANS, floor_plans, plans_pane
from pycon_us.screens.map_rooms import ROOMS, SCREEN, RoomsPane
from pycon_us.screens.schedule_days import TAB_HEIGHT, TAB_MS
from pycon_us.services import Services, use_services
from pycon_us.services.errors import report_errors
from pycon_us.services.storage import THEME
from pycon_us.ui.links import open_link
from pycon_us.ui.menus import menu_item, overflow_menu
from pycon_us.ui.navigation import use_scroll_to_top
from pycon_us.ui.scaffold import AppScaffold, search_button
from pycon_us.ui.widths import LIST, capped, use_margin
from pycon_us.year_map import JOB_FAIR_PLAN, MapData

TOUR = "3D venue tour"
"""The overflow item that opens the venue's 3D tour (MAP-03)."""


@dataclass(frozen=True)
class Pane:
    """One of the Map's panes, as its tab names it.

    Attributes:
        slug: Its ``?tab=`` value, ``ViewMemory.map_tab`` and identifier key.
        label: The tab's text.
    """

    slug: str
    label: str


PANES = (
    Pane(ROOMS, "Rooms"),
    Pane(FLOOR_PLANS, "Floor plans"),
    Pane(JOB_FAIR, "Job fair"),
)
"""The Map's panes in their tabs' order (ux.md §5.8); the expo joins with #402."""


def tab_href(slug: str) -> str:
    """Return the location that opens the Map on a pane, e.g. ``/map?tab=floor-plans``.

    Args:
        slug: A ``Pane.slug``.
    """
    return f"/{SCREEN}?tab={slug}"


def panes_of(data: MapData) -> tuple[Pane, ...]:
    """Return the panes the year has: each plan pane only when the year has its plans.

    Floor plans needs a floor plan (``floor_plans()``), Job fair the ``job-fair`` plan.

    Args:
        data: The year's ``map.toml``.
    """
    has = {
        FLOOR_PLANS: bool(floor_plans(data.plans)),
        JOB_FAIR: data.plan(JOB_FAIR_PLAN) is not None,
    }
    return tuple(pane for pane in PANES if has.get(pane.slug, True))


def asked_pane(memory: ViewMemory, route: str, view_path: str) -> None:
    """Remember the pane ``?tab=`` names, when the route addresses the Map itself.

    An unknown value is Rooms. A route that addresses another View (a floor viewer on
    top of the Map, a search over it) says nothing of the Map's pane.

    Args:
        memory: The process's ``ViewMemory``.
        route: ``page.route``, query included.
        view_path: The Map's View path.
    """
    if not is_top_view(route, view_path):
        return
    asked = query_of(route).get("tab")
    if asked is not None:
        memory.map_tab = asked if asked in {pane.slug for pane in PANES} else ROOMS


@ft.component
def Map() -> ft.View:
    """The Map root: a tab bar over the one pane picked: Rooms, Floor plans or Job fair."""
    list_ref, scroll_to_top = use_scroll_to_top()
    margin = use_margin(LIST)  # its width class (D-305)
    page = ft.context.page
    view_path = ft.use_view_path()
    svc = use_services()
    prefs = use_prefs()
    memory = svc.memory
    _, set_switches = ft.use_state(0)  # a pick re-renders; the memory holds the pane
    seen = ft.use_ref("")
    # Each route once, so a pane the user picks is not undone by the same query; a
    # route, since the floor viewer's way out pops it onto the Map (``?tab=``).
    if page.route != seen.current:
        seen.current = page.route
        asked_pane(memory, page.route, view_path)
    panes = panes_of(svc.year.map)
    slugs = [pane.slug for pane in panes]
    tab = memory.map_tab if memory.map_tab in slugs else ROOMS

    @report_errors
    async def put_back() -> None:
        offset = memory.map_offsets.get(tab)
        if not offset:
            return
        # A round trip: Flutter has built the pane before it scrolls (D-156).
        await svc.storage.get(THEME)
        if list_ref.current is not None:
            await list_ref.current.scroll_to(offset=offset, duration=0)

    # A pane that shows again, after a pick or a return to the tab, is a new list
    # at its top: put it where its last scroll ended (D-18).
    ft.use_effect(put_back, [tab], cleanup=_cancel_on_unmount)

    @report_errors
    def scrolled(e: ft.OnScrollEvent) -> None:
        if e.event_type == ft.ScrollType.END:
            memory.map_offsets[tab] = e.pixels

    @report_errors
    def changed(e: ft.Event[ft.Tabs]) -> None:
        memory.map_tab = slugs[e.control.selected_index]
        set_switches(lambda n: n + 1)
        # The route follows the pick: a stale ``?tab=`` left in it would come back as
        # Search's way back (``search_base``) or a new session's start
        # (``last_location``) and undo the pick (D-18). Same View, no stack to grow:
        # Back goes by ``parent_of()``, not by a history of routes (D-141).
        page.navigate(tab_href(memory.map_tab))

    pane: ft.Control
    if tab == FLOOR_PLANS:
        pane = plans_pane(
            svc.year.map.plans, view_path, list_ref, scrolled, margin=margin
        )
    elif tab == JOB_FAIR:
        pane = JobFairPane(list_ref, scrolled)
    else:
        pane = RoomsPane(list_ref, scrolled)
    actions = [search_button(memory, "rooms")]
    if svc.year.map.tour_url:
        actions.append(tour_menu(svc, svc.year.map.tour_url))
    body = pane
    if len(panes) > 1:
        body = map_tabs(
            panes,
            slugs.index(tab),
            pane,
            changed,
            margin=margin,
            tab_ms=prefs.motion_ms(TAB_MS),
        )
    return AppScaffold(title="Map", actions=actions, body=body, on_retap=scroll_to_top)


def map_tabs(
    panes: tuple[Pane, ...],
    selected: int,
    pane: ft.Control,
    on_change: ft.ControlEventHandler[ft.Tabs],
    *,
    margin: float,
    tab_ms: int,
) -> ft.Control:
    """Return the tab bar over the one pane shown, with no ``TabBarView`` (D-312).

    Flutter's tab bar reads each tab as its label, its place and its selection
    ("Floor plans, Tab 2 of 2, selected"); its identifier is ``map.tab.<slug>``. One
    line each, in a 56 dp tab that keeps the largest iOS text (``TAB_HEIGHT``), and
    a scrollable bar, as four panes (#23) fit no phone at large text.

    Args:
        panes: The year's panes, in order.
        selected: The index of the pane shown.
        pane: The pane shown, keyed by its slug.
        on_change: Called when the user picks a tab.
        margin: The screen's side margin (``use_margin()``).
        tab_ms: How long the indicator slides (``prefs.motion_ms()``).
    """
    tabs: list[ft.Control] = [
        ft.Tab(
            height=TAB_HEIGHT,
            # Unlabelled: Flutter merges the identifier into the tab's node (D-166).
            label=ft.Semantics(
                identifier=f"{SCREEN}.tab.{p.slug}", content=ft.Text(p.label)
            ),
        )
        for p in panes
    ]
    return ft.Tabs(
        length=len(panes),
        selected_index=selected,
        animation_duration=ft.Duration(milliseconds=tab_ms),
        on_change=on_change,
        expand=True,
        content=ft.Column(
            [
                capped(
                    ft.TabBar(
                        tabs, scrollable=True, tab_alignment=ft.TabAlignment.START
                    ),
                    margin,
                ),
                pane,
            ],
            spacing=0,
            expand=True,
        ),
    )


def tour_menu(svc: Services, url: str) -> ft.Control:
    """Return the overflow with "3D venue tour", which opens ``url`` (MAP-03).

    A web page by the link rule: the in-app browser, never an iframe pane, which took
    pans in Ionic (D-182). Read "3D venue tour, Opens in browser".

    Args:
        svc: The session's services, for the launcher.
        url: The year's tour (``MapData.tour_url``).
    """

    @report_errors
    async def open_tour() -> None:
        await open_link(svc, url)

    return overflow_menu(
        f"{SCREEN}.overflow",
        [
            menu_item(
                ft.Icons.VIEW_IN_AR_OUTLINED,
                TOUR,
                open_tour,
                identifier=f"{SCREEN}.tour",
                link=True,
            )
        ],
    )


def _cancel_on_unmount() -> None:
    """The scroll's cleanup: nothing to undo, but it makes Flet cancel its task (F2).

    Without one, a scroll still waiting when the user leaves would reach a list that
    has left the page.
    """
