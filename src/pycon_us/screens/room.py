"""Room detail (``…/room/<slug>``): what is on in one room, day by day (ROOM-02, ROOM-03).

The app bar names the room. Under it, day tabs over swipeable day lists, one tab per
day the room has sessions, today preselected (ux.md §5.9; the Schedule's tabs, the lists
in ``screens/room_days.py``). Today's list starts with "Now in this room" while something
is on there (``NowInRoom``, on the minute tick). Each day lists its time slots (D-31),
whose rows leave out the room's own name, since the title already says it
(``in_room``). A tap pushes the session, one drill level.

Opened from a session (``?highlight=<id>``, read once with ``use_query()`` until U9), the
room opens on that session's day, scrolls its row to the top once and lights it up for
``HIGHLIGHT_S`` (ROOM-03). Back from a detail pushed over the room finds it as it was:
the effect ran once, and the query is not read again. ``ViewMemory.room_highlights``
keeps a View rebuilt in a new session (D-143) from doing it again (D-18).

An unknown slug shows the not-found state under the back arrow (D-186).
"""

import asyncio
from collections.abc import Mapping
from datetime import date
from functools import partial
from typing import cast

import flet as ft

from pycon_us import clock
from pycon_us.core.models import Room
from pycon_us.core.rooms import room_now
from pycon_us.core.row_views import by_day, session_view
from pycon_us.core.timefmt import local_date, today
from pycon_us.favorites import use_favorites
from pycon_us.locations import drill_href, use_query
from pycon_us.prefs import use_prefs
from pycon_us.screens.room_days import SCREEN, day_list, row_key
from pycon_us.screens.schedule_days import TAB_MS, day_tab
from pycon_us.screens.stub import not_found
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.services.storage import THEME
from pycon_us.state import ViewMemory, use_conference
from pycon_us.theme import use_tokens
from pycon_us.ui.badges import use_favorite_toggle
from pycon_us.ui.rows import LinkTile
from pycon_us.ui.scaffold import AppScaffold, SectionHeader
from pycon_us.ui.scrolling import JUMP_MS, jump_to_key
from pycon_us.ui.session_rows import use_session_views
from pycon_us.ui.status_strip import use_minute

HIGHLIGHT_S = 2.0
"""How long the row the room was opened from stays lit, once it is in place (ROOM-03)."""

FADE_MS = 250
"""How long the highlight fades out (ux.md §3.8's fades); none under reduced motion."""


def highlight_of(query: Mapping[str, str], room: Room | None) -> str | None:
    """Return the session the room was opened from, when it is one of the room's.

    Ids are strings everywhere (D-42), so the query's value is compared as it is:
    Ionic compared a number with a string, and its highlight never showed (ROOM-03).

    Args:
        query: The View's options (``use_query()``), already unquoted.
        room: The room, or None when the feed has no such room.

    Returns:
        The session id, or None without ``?highlight=``, for an id that is not in this
        room (a stale or hand-made link), or without a room.
    """
    wanted = query.get("highlight", "")
    return wanted if room is not None and wanted in room.session_ids else None


def forget(memory: ViewMemory, view_path: str, session_id: str | None) -> None:
    """The highlight effect's cleanup: a room View that leaves forgets its highlight.

    It runs when the View leaves the stack (Back), so the next room tile highlights
    again. A replaced session never runs it (F30), so the View its successor rebuilds
    at the same location finds the entry and stays where it is (D-18). Its presence
    also makes Flet cancel a highlight still running (F2).

    Args:
        memory: The process's ``ViewMemory``.
        view_path: The room View's path.
        session_id: The session it highlights, or None.
    """
    if session_id is not None and memory.room_highlights.get(view_path) == session_id:
        del memory.room_highlights[view_path]


def opening_day(days: list[date], highlighted: date | None, current: date) -> date:
    """Return the day the room opens on: the highlighted row's, else today, else the first.

    Args:
        days: The days the room has sessions, in order; at least one.
        highlighted: The day of the session the room was opened from, if any.
        current: Today, in conference time (``clock.now()``, D-43).
    """
    if highlighted is not None and highlighted in days:
        return highlighted
    return current if current in days else days[0]


@ft.component
def RoomDetail(room_slug: str) -> ft.View:
    """One room: what is on there now, then its sessions by day and time slot.

    Args:
        room_slug: The room's slug (``slugs.slugify_room``), unquoted.
    """
    page = ft.context.page
    view_path = ft.use_view_path()
    svc = use_services()
    memory = svc.memory
    conference = use_conference()
    favorites = use_favorites()
    prefs = use_prefs()
    on_toggle = use_favorite_toggle(favorites)
    tokens = use_tokens()
    query = use_query()
    info = svc.year.conference
    use_24h = bool(page.media and page.media.always_use_24_hour_format)
    data = conference.data
    room = data.rooms.get(room_slug) if data else None
    views = use_session_views(
        conference,
        room.session_ids if room else (),
        use_24h=use_24h,
        in_room=room_slug,
    )
    target = highlight_of(query, room)
    # Decided once, when the View mounts: a View rebuilt where it already lit the row
    # up (a new session, D-143) leaves the list where it is (D-18).
    reveal, _ = ft.use_state(
        lambda: target if memory.room_highlights.get(view_path) != target else None
    )
    lit, set_lit = ft.use_state(reveal is not None)
    picked, set_picked = ft.use_state(cast(date | None, None))
    list_ref = ft.use_memo(ft.Ref[ft.ListView], [])
    ended = ft.use_memo(asyncio.Event, [])

    @report_errors
    async def light_up() -> None:
        if reveal is None:
            return
        memory.room_highlights[view_path] = reveal
        # A round trip: Flutter has applied the render that shows the row (D-156).
        await svc.storage.get(THEME)
        loop = asyncio.get_running_loop()
        shown_at = loop.time()
        jump = await jump_to_key(
            list_ref, row_key(reveal), duration=prefs.motion_ms(JUMP_MS), ended=ended
        )
        # Lit for HIGHLIGHT_S once in place: after the scroll, or from the start when
        # the row was in place already and nothing scrolled.
        waited = 0.0 if jump == "landed" else loop.time() - shown_at
        await asyncio.sleep(max(0.0, HIGHLIGHT_S - waited))
        set_lit(False)

    ft.use_effect(light_up, [], cleanup=partial(forget, memory, view_path, target))

    @report_errors
    def scrolled(e: ft.OnScrollEvent) -> None:
        if e.event_type == ft.ScrollType.END:
            ended.set()

    if data is None or room is None:
        return AppScaffold(
            title="Not found",
            body=ft.ListView(
                [
                    not_found(
                        "This room isn't in the current schedule",
                        icon=ft.Icons.WRONG_LOCATION_OUTLINED,
                        action="All rooms",
                        location="/map",
                        identifier=f"{SCREEN}.not_found",
                    )
                ],
                expand=True,
            ),
        )

    groups = dict(by_day(views, info.zone))
    days = list(groups)
    current = today(clock.now(), info.zone)
    # The day of the session the room was opened from, also in a rebuilt View.
    highlighted = local_date(data.sessions[target].start, info.zone) if target else None
    shown = (
        picked
        if picked is not None and picked in groups
        else opening_day(days, highlighted, current)
    )

    @report_errors
    def changed(e: ft.Event[ft.Tabs]) -> None:
        set_picked(days[e.control.selected_index])

    pages: list[ft.Control] = [
        day_list(
            group,
            info,
            favorites=favorites.ids,
            on_toggle=on_toggle,
            tokens=tokens,
            use_24h=use_24h,
            reveal=reveal,
            lit=lit,
            fade_ms=prefs.motion_ms(FADE_MS),
            # "Now" is today's: at the head of its list, it scrolls away with it, so
            # at the largest text the slots keep the screen (D-194).
            head=NowInRoom(room, use_24h=use_24h) if day == current else None,
            # Only the list that scrolls to the row needs every row built (D-154).
            list_ref=list_ref if reveal and day == highlighted else None,
            on_scroll=scrolled if reveal and day == highlighted else None,
        )
        for day, group in groups.items()
    ]
    bar: list[ft.Control] = [
        ft.TabBar(
            [
                day_tab(i, day, is_today=day == current, screen=SCREEN)
                for i, day in enumerate(days)
            ],
            scrollable=True,  # five days fit no phone at large text
            tab_alignment=ft.TabAlignment.START,
        ),
        ft.TabBarView(pages, expand=True),
    ]
    tabs = ft.Tabs(
        length=len(days),
        selected_index=days.index(shown),
        animation_duration=ft.Duration(milliseconds=prefs.motion_ms(TAB_MS)),
        on_change=changed,
        expand=True,
        content=ft.Column(bar, spacing=0, expand=True),
    )
    return AppScaffold(
        title=room.name,
        body=tabs,
    )


@ft.component
def NowInRoom(room: Room, *, use_24h: bool) -> ft.Control:
    """Return "Now in this room": the session on there now, linked, or nothing (ROOM-02).

    A leaf component on the minute tick (``use_minute()``, D-175), so the screen around
    it does not re-render every minute, and the Developer fake clock drives it. What is
    on follows Now & Next's rule (``rooms.room_now``, D-179), as the Map's "Now:" line.

    One ``LinkTile`` that opens the session: its name cut at three lines, as a row's
    title is (ux.md §3.6), its time in ``Tokens.live`` (and a place given elsewhere,
    the two in a wrapping row as a row's meta, D-184), and "and 1 more" on a line of
    its own when several are on (D-188's form), at the head of today's list. A pointer
    to the session's row below, which has the star (D-194). A divider closes it.

    Args:
        room: The room.
        use_24h: Whether the device uses the 24-hour clock.
    """
    view_path = ft.use_view_path()
    conference = use_conference()
    tokens = use_tokens()
    info = use_services().year.conference
    use_minute()
    data = conference.data
    on = room_now(data, room.slug, clock.now()) if data else ()
    if not on:
        return ft.Container()
    first, *rest = on
    view = session_view(first, info.zone, use_24h=use_24h, in_room=room.slug)
    when = view.when.replace(" ", "\N{NO-BREAK SPACE}")  # "AM" keeps to its time
    first_line: ft.Control = ft.Text(
        when, color=tokens.live, semantics_label=view.spoken_when
    )
    if view.place:  # streamed here from elsewhere: the lightning talks' Arena
        # Two texts in a wrapping row, as a row's meta (D-184): at large text the
        # place moves down whole and the "·" ends the time's line.
        time = ft.Text(
            f"{when}\N{NO-BREAK SPACE}·",
            color=tokens.live,
            semantics_label=f"{view.spoken_when},",
        )
        place = ft.Text(view.place, color=tokens.live)
        first_line = ft.Row([time, place], wrap=True, spacing=4, run_spacing=0)
    lines: list[ft.Control] = [first_line]
    if rest:
        lines.append(ft.Text(f"and {len(rest)}\N{NO-BREAK SPACE}more"))
    # As Now's "Happening now" (D-190): a live dot, and a heading screen readers know
    # (a level, F40).
    dot = ft.Container(width=8, height=8, border_radius=4, bgcolor=tokens.live)
    return ft.Column(
        [
            SectionHeader("Now in this room", level=2, leading=dot),
            LinkTile(
                ft.Text(first.name, max_lines=3, overflow=ft.TextOverflow.ELLIPSIS),
                drill_href(view_path, "session", first.id),
                subtitle=ft.Column(lines, spacing=2),
                identifier=f"{SCREEN}.now",
            ),
            # It closes the section here, so the first slot does not read as its
            # second item, and only while something is on (D-194).
            ft.Divider(height=1),
        ],
        spacing=0,
    )
