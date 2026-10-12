"""Map (``/map``): a stub listing the rooms until P1's Rooms pane (ROOM-01, MAP-01)."""

import flet as ft

from pycon_us.locations import drill_href
from pycon_us.screens.stub import nav_tile, search_button, stub_view
from pycon_us.services import use_services
from pycon_us.state import use_conference


@ft.component
def Map() -> ft.View:
    """The Map root: every room, in the feed's room order, each opening its detail."""
    view_path = ft.use_view_path()
    svc = use_services()
    conference = use_conference()
    rooms = conference.data.rooms.values() if conference.data else ()
    return stub_view(
        title="Map",
        actions=[search_button(svc.memory, "rooms")],
        controls=[
            nav_tile(
                room.name,
                drill_href(view_path, "room", room.slug),
                subtitle=f"{len(room.session_ids)} sessions",
            )
            for room in rooms
        ],
    )
