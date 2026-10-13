"""The route table: tab roots, More pages, the global search and the recursive drill.

``ROUTES`` follows decisions §M and architecture §5.2 in the shape S4 confirmed (D-141):
each tab root, More page and ``/search`` ends with ``DRILL``, a recursive child that
pushes one View per ``<kind>/<id>`` pair, so ``/schedule/session/42/speaker/17`` is
three Views and Back pops one (D-17). ``/`` is ``Start``, which sends a session on;
an unknown location is ``NotFound``. Back itself is ``main.py``'s ``page.on_view_pop``
with ``locations.parent_of()`` (D-19).
"""

from collections.abc import Callable
from urllib.parse import unquote

import flet as ft

from pycon_us.locations import DRILL_KINDS, is_top_view, start_target
from pycon_us.screens.map import Map
from pycon_us.screens.more import More
from pycon_us.screens.more_pages import MorePage, Track
from pycon_us.screens.my_schedule import MySchedule
from pycon_us.screens.now import Now
from pycon_us.screens.plan import PlanViewer
from pycon_us.screens.room import RoomDetail
from pycon_us.screens.schedule import Schedule
from pycon_us.screens.search import Search
from pycon_us.screens.session import SessionDetail
from pycon_us.screens.speaker import SpeakerDetail
from pycon_us.screens.speakers import Speakers
from pycon_us.screens.sponsor import SponsorDetail
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.theme import BOOT_COLOR
from pycon_us.ui.states import EmptyState


@ft.component
def Drill() -> ft.View:
    """One detail level: the detail screen for this level's own kind and id (D-141).

    The Router gives each level the params of its own pair (F6). Ids arrive quoted, as
    ``drill_href()`` wrote them, and are unquoted here (D-42).
    """
    params = ft.use_route_params()
    ident = unquote(params["ident"])
    match params["kind"]:
        case "session":
            return SessionDetail(session_id=ident)
        case "speaker":
            return SpeakerDetail(speaker_id=ident)
        case "room":
            return RoomDetail(room_slug=ident)
        case "sponsor":
            return SponsorDetail(sponsor_slug=ident)
        case "plan":
            return PlanViewer(plan_id=ident)
        case kind:  # DRILL only matches DRILL_KINDS: a new kind needs its case here
            raise ValueError(f"no screen for the drill kind {kind!r}")


@ft.component
def Start() -> ft.View:
    """``/``: send the session to Now, or back to where the user was (D-143).

    A new session in the same process (F26, F29) finds ``ViewMemory.last_location``
    and rebuilds that stack; a deep link or ``--route`` start never comes here, except
    one straight to ``/search``: with no opener to remember, the Router builds the
    modal over ``/``, so ``Start`` mounts below it and must stay put, not replace the
    entry (``is_top_view()``); Back from search then goes to ``search_base``. It shows
    the boot purple for the moment it is on screen, and shares the tab roots' View
    key, so Now replaces it without a transition (D-142).
    """
    page = ft.context.page
    memory = use_services().memory

    @report_errors
    def go() -> None:
        if is_top_view(page.route, "/"):
            page.navigate(start_target(memory.last_location, memory.search_base))

    ft.use_effect(go, [])
    return ft.View(route="/", bgcolor=BOOT_COLOR, padding=0)


@ft.component
def NotFound() -> ft.Control:
    """An unknown location: what happened and a way to Now.

    The Router wraps it in a View of its own (F6), so it brings its own safe area.
    """
    page = ft.context.page

    @report_errors
    def go_to_now() -> None:
        page.navigate("/now")

    return ft.SafeArea(
        expand=True,
        content=ft.ListView(
            [
                EmptyState(
                    "Page not found",
                    icon=ft.Icons.LINK_OFF_OUTLINED,
                    body=f"Nothing in the app is at {page.route}.",
                    action="Go to Now",
                    on_action=go_to_now,
                    identifier="app.not_found",
                )
            ],
            expand=True,
        ),
    )


DRILL = ft.Route(
    path=f":kind({'|'.join(DRILL_KINDS)})/:ident", recursive=True, component=Drill
)
"""The drill: the last child of every page, so details open on top of any of them."""


def pushed(
    path: str, component: Callable[..., object], *children: ft.Route
) -> ft.Route:
    """Return a page's route: its own children first, then the drill (D-141).

    Args:
        path: The page's segment(s) below its parent, e.g. ``"speakers"``.
        component: The page's screen.
        *children: Pages below it, e.g. ``/more/tracks/<slug>``.
    """
    return ft.Route(path=path, component=component, children=[*children, DRILL])


ROUTES = [
    ft.Route(index=True, component=Start),
    ft.Route(path="search", component=Search, modal=True, children=[DRILL]),
    pushed("now", Now),
    pushed("schedule", Schedule),
    pushed("my-schedule", MySchedule),
    pushed("map", Map),
    pushed(
        "more",
        More,
        pushed("speakers", Speakers),
        pushed("tracks", MorePage, pushed(":slug", Track)),
        pushed("keynotes", MorePage),
        pushed("open-spaces", MorePage),
        pushed("lightning-talks", MorePage),
        pushed("sprints", MorePage),
        pushed("app", MorePage),
        pushed("developer", MorePage),
    ),
]
"""Every route of P0 and P1's More pages; later phases add theirs (architecture §5.2).

``/search`` is a global modal (D-19): the Router builds it over the last non-modal
location, and our ``page.on_view_pop`` returns each Back one step.
"""
