"""Room detail (``…/room/<slug>``): a stub until P1 (ROOM-02..04).

It links to the room's sessions, one drill level each. An unknown slug shows a
not-found state under the back arrow (#90 settles P1's).
"""

import flet as ft

from pycon_us.locations import drill_href
from pycon_us.screens.stub import nav_tile, note, stub_body
from pycon_us.state import use_conference
from pycon_us.ui.scaffold import AppScaffold


@ft.component
def RoomDetail(room_slug: str) -> ft.View:
    """One room: links to its sessions, by start.

    Args:
        room_slug: The room's slug (``slugs.slugify_room``), unquoted.
    """
    view_path = ft.use_view_path()
    conference = use_conference()
    data = conference.data
    room = data.rooms.get(room_slug) if data else None
    if data is None or room is None:
        return AppScaffold(
            title="Not found",
            body=stub_body([note(f"No room {room_slug!r} in this year's schedule.")]),
        )
    return AppScaffold(
        title=room.name,
        body=stub_body(
            [
                nav_tile(data.sessions[sid].name, drill_href(view_path, "session", sid))
                for sid in room.session_ids
            ]
        ),
    )
