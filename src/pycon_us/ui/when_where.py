"""Session detail's "When and where" card, and the status line that keeps it current.

Time and place answer the attendee's first question (ux.md §1, §5.5), so they come
before everything else about a session: the day and time, where the session stands now
("Starts in 25 min", "Happening now", "Ended"), the Pacific Time note when the device's
clock differs (D-35), then one room tile that pushes room detail and, folded into an
``ExpansionTile``, the other rooms of a multi-room session (SESS-02). Each tile reads as
one phrase (D-33).

``StatusLine`` is a leaf component with its own minute tick, as ``StatusStrip`` is
(D-175): the time passing re-renders the line, not the screen around it.
"""

from collections.abc import Callable
from datetime import datetime
from urllib.parse import quote

import flet as ft

from pycon_us import clock
from pycon_us.config import ConferenceInfo
from pycon_us.core.models import Room, Session
from pycon_us.core.row_views import Places, session_view
from pycon_us.core.timefmt import day_heading, time_status, zone_note
from pycon_us.locations import drill_href
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.theme import use_tokens
from pycon_us.ui.rows import LinkTile
from pycon_us.ui.scaffold import TICK_SECONDS, current_minute, stop_ticks

EXPAND_MS = 200
"""The folded rooms' opening, an M3 small change (ux.md §3.8); 0 under reduced motion."""


def room_href(view_path: str, room: Room, session_id: str) -> str:
    """Return the location that pushes a room's detail, highlighting the session.

    Room detail reads ``?highlight=`` once, to mark the row it came from (ROOM-03).

    Args:
        view_path: The session's View path (``ft.use_view_path()``).
        room: The room.
        session_id: The session shown.
    """
    href = drill_href(view_path, "room", room.slug)
    return f"{href}?highlight={quote(session_id, safe='')}"


def WhenAndWhere(
    session: Session,
    where: Places,
    info: ConferenceInfo,
    *,
    view_path: str,
    use_24h: bool,
    motion_ms: Callable[[int], int],
    screen: str,
) -> ft.Control:
    """Return the "When and where" card: the time tile, then the room tiles.

    An outlined card (ux.md §5.5) of 56 dp+ list tiles, so each is a 48 dp target
    (D-33) that grows with the text. A place the feed has no room for is shown but
    opens nothing; a session with neither place nor rooms (a notice) has the time only.

    Args:
        session: The session.
        where: Its places, from ``row_views.places()``.
        info: The year's facts: the zone and its name.
        view_path: The View's own path, so a room opens on top of it (D-17).
        use_24h: The device's 24-hour setting.
        motion_ms: ``Prefs.motion_ms``, for the rooms' unfolding (D-173).
        screen: The screen's name in the identifiers, ``<screen>.when`` and so on.
    """
    tiles = [_time_tile(session, info, use_24h, screen)]
    if where.room is not None:
        tiles.append(
            LinkTile(
                where.label,
                room_href(view_path, where.room, session.id),
                icon=ft.Icons.PLACE_OUTLINED,
                identifier=f"{screen}.room",
            )
        )
    elif where.label:
        tiles.append(_place_tile(where.label, screen))
    if where.others:
        tiles.append(_other_rooms(session, where, view_path, motion_ms, screen))
    return ft.Card(
        variant=ft.CardVariant.OUTLINED,
        margin=ft.Margin.symmetric(horizontal=16),
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,  # the tiles' ink stays inside
        content=ft.Column(tiles, spacing=0),
    )


def _time_tile(
    session: Session, info: ConferenceInfo, use_24h: bool, screen: str
) -> ft.Control:
    """The day and time, where the session stands and the zone: one phrase."""
    view = session_view(session, info.zone, use_24h=use_24h)
    day = day_heading(session.day)
    lines: list[ft.Control] = [StatusLine(session.start, session.end)]
    # The device's offset at the session's own start, so a DST change between today
    # and then gives no note, and a real difference names the session's zone (PDT).
    device_offset = session.start.astimezone().utcoffset()
    note = zone_note(session.start, info.zone, info.time_zone_name, device_offset)
    if note is not None:
        lines.append(_supporting(note))
    return ft.MergeSemantics(
        content=ft.Semantics(
            identifier=f"{screen}.when",
            content=ft.ListTile(
                leading=ft.Icon(ft.Icons.SCHEDULE),
                title=ft.Text(
                    f"{day} · {view.when}", semantics_label=f"{day}, {view.spoken_when}"
                ),
                subtitle=ft.Column(lines, spacing=2),
                title_alignment=ft.ListTileTitleAlignment.TITLE_HEIGHT,
            ),
        )
    )


def _place_tile(label: str, screen: str) -> ft.Control:
    """A place the feed has no room for: shown, opening nothing."""
    return ft.MergeSemantics(
        content=ft.Semantics(
            identifier=f"{screen}.room",
            content=ft.ListTile(
                leading=ft.Icon(ft.Icons.PLACE_OUTLINED),
                title=label,
                title_alignment=ft.ListTileTitleAlignment.TITLE_HEIGHT,
            ),
        )
    )


def _other_rooms(
    session: Session,
    where: Places,
    view_path: str,
    motion_ms: Callable[[int], int],
    screen: str,
) -> ft.Control:
    """The other rooms, folded: lightning talks and breaks list up to seven."""
    no_border = ft.RoundedRectangleBorder()  # in a card: no divider lines when open
    return ft.Semantics(
        identifier=f"{screen}.other_rooms",
        content=ft.ExpansionTile(
            title=ft.Text(where.others_label),
            # Under the room tile, a blank as wide as its icon lines the two titles
            # up; alone (a break in many rooms), the place icon.
            leading=ft.Container(width=24)
            if where.label
            else ft.Icon(ft.Icons.PLACE_OUTLINED),
            shape=no_border,
            collapsed_shape=no_border,
            animation_style=ft.AnimationStyle(duration=motion_ms(EXPAND_MS)),
            # Each room's title under the tile's title: 16 + 24 + 16 dp in.
            controls_padding=ft.Padding.only(left=40),
            controls=[
                LinkTile(
                    room.name,
                    room_href(view_path, room, session.id),
                    identifier=f"{screen}.room.{room.slug}",
                )
                for room in where.others
            ],
        ),
    )


@ft.component
def StatusLine(start: datetime, end: datetime) -> ft.Control:
    """Where a session stands now: "Starts in 25 min", "Happening now" or "Ended".

    It ticks every ``TICK_SECONDS`` while it is mounted and the app is in the
    foreground (``Services.run_every``, D-40) and re-renders itself only; it reads
    ``clock.now()``, so the Developer fake clock moves it too (D-43). It shows nothing
    when ``time_status()`` has nothing to say, and screen readers hear the words
    ("Starts in 25 minutes").

    Args:
        start: When the session starts.
        end: When it ends.
    """
    svc = use_services()
    tokens = use_tokens()
    _, set_minute = ft.use_state(current_minute)

    @report_errors
    def tick() -> None:
        set_minute(current_minute())  # the same minute renders nothing new

    @report_errors
    async def keep_up() -> None:
        await svc.run_every(TICK_SECONDS, tick)

    # The cleanup is what makes Flet cancel the ticks on unmount (F2, F39).
    ft.use_effect(keep_up, [], cleanup=stop_ticks)
    status = time_status(start, end, clock.now(), svc.year.conference.zone)
    if status is None:
        return ft.Text("", visible=False)
    return ft.Text(
        status.label,
        semantics_label=status.spoken,
        theme_style=ft.TextThemeStyle.BODY_MEDIUM,
        color=tokens.live if status.happening else ft.Colors.ON_SURFACE_VARIANT,
    )


def _supporting(text: str) -> ft.Control:
    """A tile's supporting line, in ``on_surface_variant`` (ux.md §3.9)."""
    return ft.Text(
        text,
        theme_style=ft.TextThemeStyle.BODY_MEDIUM,
        color=ft.Colors.ON_SURFACE_VARIANT,
    )
