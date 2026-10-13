"""Map (``/map``): the rooms list, P1's one pane (ROOM-01; ux.md §5.8, D-188).

Every room of the feed in natural order, each with its session count and, while
something is on in it, "Now: <title>" (``core.rooms.room_list``); then the places that
are not rooms, under "Other locations". A row pushes the room's detail, one drill level.
The list recomputes on the minute tick (``use_minute()``, D-175), from ``clock.now()``,
so the Developer fake clock drives it. Without data it shows the skeleton until the
first fetch has failed, then "Can't load the rooms" with Try again (D-32, ux.md §4.1).
Floor plans, the expo and the job fair join as panes in P2 (MAP-01); until then the
screen has no control for them.
"""

import flet as ft

from pycon_us import clock
from pycon_us.core.rooms import RoomEntry, RoomList, room_list, session_count
from pycon_us.locations import drill_href
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.state import use_conference
from pycon_us.theme import use_tokens
from pycon_us.ui.navigation import use_scroll_to_top
from pycon_us.ui.rows import LinkTile
from pycon_us.ui.scaffold import AppScaffold, SectionHeader, search_button
from pycon_us.ui.states import NO_DATA_BODY, EmptyState, SkeletonList
from pycon_us.ui.status_strip import StatusStrip, use_minute

SCREEN = "map"
"""The screen's name in its semantics identifiers (decisions §M)."""


@ft.component
def Map() -> ft.View:
    """The Map root: the rooms, then the other locations, each row opening its room."""
    list_ref, scroll_to_top = use_scroll_to_top()
    page = ft.context.page
    view_path = ft.use_view_path()
    svc = use_services()
    conference = use_conference()
    tokens = use_tokens()
    use_minute()  # "Now:" keeps up with the clock while the list shows

    @report_errors
    async def refresh() -> None:
        await conference.refresh(svc.storage, svc.year, closed=svc.closed)

    @report_errors
    def open_schedule() -> None:
        page.navigate("/schedule")

    data = conference.data
    rows: list[ft.Control]
    if data is None and conference.problem is None:
        # The first fetch runs, or is about to (NEW-03); the strip says so.
        rows = [StatusStrip(), SkeletonList("Loading rooms")]
    elif data is None:
        rows = [
            StatusStrip(),  # its bar shows a retry; the button below stays in place
            EmptyState(
                "Can't load the rooms",
                icon=ft.Icons.CLOUD_OFF_OUTLINED,
                body=NO_DATA_BODY[conference.problem or "offline"],
                action="Try again",
                on_action=refresh,
                disabled=conference.refreshing,
                identifier="map.no_data",
            ),
        ]
    elif not data.rooms:
        rows = [
            EmptyState(
                "No rooms yet",
                icon=ft.Icons.MEETING_ROOM_OUTLINED,
                body="Rooms appear here once the schedule lists them.",
                action="Open schedule",
                on_action=open_schedule,
                identifier="map.no_rooms",
            )
        ]
    else:
        listing = room_list(data, clock.now(), svc.year.content.other_locations)
        rows = room_rows(listing, view_path, live=tokens.live)
    return AppScaffold(
        title="Map",
        actions=[search_button(svc.memory, "rooms")],
        body=ft.ListView(rows, expand=True, ref=list_ref),
        on_retap=scroll_to_top,
    )


def room_rows(listing: RoomList, view_path: str, *, live: str) -> list[ft.Control]:
    """Return the list's rows: a heading per group, then a row per room.

    Args:
        listing: The rooms and the other locations (``room_list()``).
        view_path: This View's path, so a row's detail is pushed on top of it.
        live: The "happening now" colour (``Tokens.live``).
    """
    rows: list[ft.Control] = []
    for heading, entries in (
        ("Rooms", listing.rooms),
        ("Other locations", listing.other_locations),
    ):
        if entries:
            rows.append(SectionHeader(heading))
            rows.extend(room_row(entry, view_path, live=live) for entry in entries)
    return rows


def room_row(entry: RoomEntry, view_path: str, *, live: str) -> ft.Control:
    """Return one room's row: its name, its session count and what is on in it now.

    A ``LinkTile``, so it is one node for screen readers, read as one phrase ("Room
    103ABC, 26 sessions, Now: Building X"), and a tap pushes the room. The count keeps
    its place under the name in every row; the "Now:" lines, when there are any, come
    under it in the ``live`` colour, and their words say the same, so colour is never
    the only signal (D-33).

    The count is every session listed under the room, poster details included, as the
    room's detail lists them (ROOM-02) and as Ionic counted ("Expo Hall AB 35"), while
    "Now:" follows Now & Next's timeline-only rule (D-179): so Expo Hall AB counts 35
    where the Schedule shows 10 rows there.

    The title of the session on is cut at three lines, as a session row's title is
    (ux.md §3.6); "and 1 more" is a line of its own, so the cut never hides it.

    Args:
        entry: The room and the sessions on in it.
        view_path: This View's path.
        live: The "happening now" colour (``Tokens.live``).
    """
    room = entry.room
    count = ft.Text(session_count(len(room.session_ids)))
    subtitle: ft.Control = count
    if lines := now_lines(entry):
        title, *more = lines
        subtitle = ft.Column(
            [
                count,
                ft.Text(
                    title,
                    color=live,
                    max_lines=3,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
                *(ft.Text(line, color=live) for line in more),
            ],
            spacing=2,
        )
    return LinkTile(
        room.name,
        drill_href(view_path, "room", room.slug),
        icon=ft.Icons.PLACE_OUTLINED,
        subtitle=subtitle,
        identifier=f"{SCREEN}.room.{room.slug}",
    )


def now_lines(entry: RoomEntry) -> list[str]:
    """Return what is on in the room: ["Now: <title>"], or [] when nothing is.

    With several sessions on, the one that started last is named, and a second line
    counts the others: ["Now: Organizing IRL meetups", "and 1 more"].
    """
    if not entry.on_now:
        return []
    first, *rest = entry.on_now
    lines = [f"Now: {first.name}"]
    if rest:
        lines.append(f"and {len(rest)} more")
    return lines
