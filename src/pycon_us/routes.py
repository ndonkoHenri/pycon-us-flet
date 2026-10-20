"""The route table: tab roots, More pages, the global search and the recursive drill.

``ROUTES`` follows decisions §M and architecture §5.2 in the shape S4 confirmed (D-141):
each tab root, More page and ``/search`` ends with ``DRILL``, a recursive child that
pushes one View per ``<kind>/<id>`` pair, so ``/schedule/session/42/speaker/17`` is
three Views and Back pops one (D-17). ``/`` is ``Start``, which sends a session on;
an unknown location is ``NotFound``, through ``UNKNOWN``, the table's last route
(D-270). Back itself is ``main.py``'s ``page.on_view_pop`` with
``locations.parent_of()`` (D-19).
"""

from collections.abc import Callable
from urllib.parse import unquote

import flet as ft

from pycon_us.locations import DRILL_KINDS, is_top_view, start_target
from pycon_us.screens.about_app import AboutApp
from pycon_us.screens.developer import Developer
from pycon_us.screens.help import Help
from pycon_us.screens.jobs import Jobs
from pycon_us.screens.keynotes import Keynotes
from pycon_us.screens.licences import LicencePage, Licences
from pycon_us.screens.lightning_talks import LightningTalks
from pycon_us.screens.map import Map
from pycon_us.screens.more import More
from pycon_us.screens.my_schedule import MySchedule
from pycon_us.screens.now import Now
from pycon_us.screens.open_spaces import OpenSpaces
from pycon_us.screens.plan import PlanViewer
from pycon_us.screens.psf import AboutPsf
from pycon_us.screens.room import RoomDetail
from pycon_us.screens.schedule import Schedule
from pycon_us.screens.search import Search
from pycon_us.screens.session import SessionDetail
from pycon_us.screens.settings import Settings
from pycon_us.screens.social import Social
from pycon_us.screens.speaker import SpeakerDetail
from pycon_us.screens.speakers import Speakers
from pycon_us.screens.sponsor import SponsorDetail
from pycon_us.screens.sponsors import Sponsors
from pycon_us.screens.sprints import Sprints
from pycon_us.screens.track import TrackPage
from pycon_us.screens.tracks import Tracks
from pycon_us.screens.wifi import Wifi
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.theme import BOOT_COLOR
from pycon_us.ui.scaffold import AppScaffold
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


NOT_FOUND = "This page isn't in the app"
"""The unknown location's empty state (ux.md §4.6)."""

NOT_FOUND_BODY = "The link may be old or mistyped."
"""What the state says under its title: a likely why, without the path (D-270)."""


@ft.component
def NotFound() -> ft.View:
    """An unknown location, such as a link to a page the app doesn't have (D-270).

    Its own View, so it can do what the Router's ``not_found`` wrapper cannot
    (``router.py:731-741``, F89): Back goes to Now, as on a root, rather than closing
    the app after a cold link (``AppScaffold(unknown=True)``). Built like a detail's
    not-found state (D-186), but never naming the location: a link's path means
    nothing to the person who tapped it.
    """
    page = ft.context.page

    @report_errors
    def go_to_now() -> None:
        page.navigate("/now")

    return AppScaffold(
        title="Not found",
        unknown=True,
        body=ft.ListView(
            [
                EmptyState(
                    NOT_FOUND,
                    icon=ft.Icons.LINK_OFF_OUTLINED,
                    body=NOT_FOUND_BODY,
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

UNKNOWN = ft.Route(path=":unknown*", component=NotFound)
"""The last route: every location no other route matches, at any depth (D-270, F89).

A splat matches zero or more segments, and the Router tries routes in order, so
only a location the table doesn't have gets here: ``/nope``, ``/now/nope``,
``/now/session/42/nope``. Its View is the whole stack.
"""


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
        pushed(
            "tracks",
            Tracks,
            # The hub's pages of their own, More's pages again (year_tracks.HUB_PAGES,
            # D-207): under the hub, Back returns to it. Before the slug route, which
            # would match them too.
            pushed("sprints", Sprints),
            pushed("lightning-talks", LightningTalks),
            pushed("open-spaces", OpenSpaces),
            pushed("keynotes", Keynotes),
            pushed(":slug", TrackPage),
        ),
        pushed("keynotes", Keynotes),
        pushed("open-spaces", OpenSpaces),
        pushed("lightning-talks", LightningTalks),
        pushed("sprints", Sprints),
        pushed("sponsors", Sponsors),
        pushed("settings", Settings),
        pushed(
            "app",
            AboutApp,
            # Under About this app, so Back returns there (D-207's pattern, D-296).
            pushed("licences", Licences, pushed(":licence", LicencePage)),
        ),
        pushed("developer", Developer),
        pushed("wifi", Wifi),
        pushed("jobs", Jobs),
        pushed("help", Help),
        pushed("psf", AboutPsf),
        pushed("social", Social),
    ),
    UNKNOWN,  # last: it matches anything (D-270)
]
"""Every route of P0 and P1's More pages; later phases add theirs (architecture §5.2).

``/search`` is a global modal (D-19): the Router builds it over the last non-modal
location, and our ``page.on_view_pop`` returns each Back one step.
"""
