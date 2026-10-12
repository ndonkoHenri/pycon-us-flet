"""Session detail (``…/session/<id>``): a stub until P1 (SESS-01..12).

It links to the session's speakers and rooms, one drill level each, so a chain such as
session → speaker → session → room is a real stack (D-17). An unknown id shows a
not-found state under the back arrow; #90 settles what P1 does (D-21, ux.md §4.1).
"""

import flet as ft

from pycon_us.core.slugs import slugify_room
from pycon_us.locations import drill_href
from pycon_us.screens.stub import nav_tile, note, stub_body
from pycon_us.state import use_conference
from pycon_us.ui.scaffold import AppScaffold, SectionHeader


@ft.component
def SessionDetail(session_id: str) -> ft.View:
    """One session: its track and place, then links to its speakers and rooms.

    Args:
        session_id: The session id, unquoted (D-42).
    """
    view_path = ft.use_view_path()
    conference = use_conference()
    data = conference.data
    session = data.sessions.get(session_id) if data else None
    if data is None or session is None:
        return AppScaffold(
            title="Not found",
            body=stub_body(
                [note(f"No session {session_id!r} in this year's schedule.")]
            ),
        )
    slugs = [slugify_room(name) for name in session.rooms]
    rooms = [slug for slug in slugs if slug in data.rooms]
    return AppScaffold(
        title=session.name,
        body=stub_body(
            [
                note(f"{session.track} · {session.display_location}"),
                *([SectionHeader("Speakers")] if session.speaker_ids else []),
                *(
                    nav_tile(
                        data.speakers[sid].name, drill_href(view_path, "speaker", sid)
                    )
                    for sid in session.speaker_ids
                ),
                *([SectionHeader("Rooms")] if rooms else []),
                *(
                    nav_tile(data.rooms[slug].name, drill_href(view_path, "room", slug))
                    for slug in rooms
                ),
            ]
        ),
    )
