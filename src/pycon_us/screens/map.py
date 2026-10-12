"""Map (``/map``): a stub listing the rooms until P1's Rooms pane (ROOM-01, MAP-01)."""

import flet as ft

from pycon_us.locations import drill_href
from pycon_us.screens.stub import nav_tile, stub_body
from pycon_us.services import use_services
from pycon_us.state import use_conference
from pycon_us.ui.navigation import use_scroll_to_top
from pycon_us.ui.scaffold import AppScaffold, search_button


@ft.component
def Map() -> ft.View:
    """The Map root: every room, in the feed's room order, each opening its detail."""
    list_ref, scroll_to_top = use_scroll_to_top()
    view_path = ft.use_view_path()
    svc = use_services()
    conference = use_conference()
    rooms = conference.data.rooms.values() if conference.data else ()
    return AppScaffold(
        title="Map",
        actions=[search_button(svc.memory, "rooms")],
        body=stub_body(
            [
                nav_tile(
                    room.name,
                    drill_href(view_path, "room", room.slug),
                    subtitle=f"{len(room.session_ids)} sessions",
                )
                for room in rooms
            ],
            ref=list_ref,
        ),
        on_retap=scroll_to_top,
    )
