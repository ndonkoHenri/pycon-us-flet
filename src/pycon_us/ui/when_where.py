"""Session detail's "When and where" card, and the status line that keeps it current.

Time and place answer the attendee's first question (ux.md §1, §5.5), so they come
before everything else about a session: the day and time, where the session stands now
("Starts in 25 min", "Happening now", "Ended"), the Pacific Time note when the device's
clock differs (D-35), then one room tile that pushes room detail and, folded into a
`FoldTile` (D-354), the other rooms of a multi-room session (SESS-02). Each tile reads
as one phrase (D-33).

A session in one room with a pin shows that room's `LocationCard` under the card
(D-349): the room tile says what else is on there (room detail), the card where it is
(the floor viewer); one node with both destinations could not be one phrase. A Job
Fair row (`core.expo.is_job_fair()`, SESS-10) then shows the job fair plan's card, the
one the Map's Job fair pane and Job listings show (D-254): where the tables are.

`StatusLine` is a leaf component with its own minute tick, as `StatusStrip` is
(D-175): the time passing re-renders the line, not the screen around it.
"""

from datetime import datetime
from urllib.parse import quote

import flet as ft

from pycon_us import clock
from pycon_us.config import ConferenceInfo, YearData
from pycon_us.core.expo import is_job_fair
from pycon_us.core.models import Room, Session
from pycon_us.core.row_views import Places, session_view
from pycon_us.core.timefmt import day_heading, on_screen, time_status, zone_note
from pycon_us.locations import drill_href
from pycon_us.prefs import use_prefs
from pycon_us.services import use_services
from pycon_us.theme import use_tokens
from pycon_us.ui.fold import FoldTile, expand_style
from pycon_us.ui.location_card import job_fair_card, room_card
from pycon_us.ui.rows import LinkTile
from pycon_us.ui.semantics import named
from pycon_us.ui.status_strip import use_minute


def room_href(view_path: str, room: Room, session_id: str) -> str:
    """Return the location that pushes a room's detail, highlighting the session.

    Room detail reads `?highlight=` once, to mark the row it came from (ROOM-03).

    Args:
        view_path: The session's View path (`ft.use_view_path()`).
        room: The room.
        session_id: The session shown.
    """
    href = drill_href(view_path, "room", room.slug)
    return f"{href}?highlight={quote(session_id, safe='')}"


def WhenAndWhere(
    session: Session,
    where: Places,
    year: YearData,
    *,
    view_path: str,
    use_24h: bool,
    screen: str,
) -> ft.Control:
    """Return the "When and where" card, then the room's and the job fair's cards.

    The room's `LocationCard` when it has one; the job fair plan's on a Job Fair row.

    An outlined card (ux.md §5.5) of 56 dp+ list tiles, so each is a 48 dp target
    (D-33) that grows with the text. A place the feed has no room for is shown but
    opens nothing; a session with neither place nor rooms (a notice) has the time only.

    Args:
        session: The session.
        where: Its places, from `row_views.places()`.
        year: The year's data: the zone and its name, the room's pin and the plans.
        view_path: The View's own path, so a room opens on top of it (D-17).
        use_24h: The device's 24-hour setting.
        screen: The screen's name in the identifiers, `<screen>.when` and so on.
    """
    tiles = [_time_tile(session, year.conference, use_24h, screen)]
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
        tiles.append(OtherRooms(session, where, view_path, screen))
    card = ft.Card(
        variant=ft.CardVariant.OUTLINED,
        margin=ft.Margin.symmetric(horizontal=16),
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,  # the tiles' ink stays inside
        content=ft.Column(tiles, spacing=0),
    )
    # One room only: a multi-room session's rooms are its tiles (D-349).
    room = (
        room_card(year.map, where.room.name, identifier=f"{screen}.location")
        if where.room is not None and not where.others
        else None
    )
    job_fair = (
        job_fair_card(year.map, identifier=f"{screen}.job_fair.location")
        if is_job_fair(session)
        else None
    )
    located = [
        ft.Container(found, padding=ft.Padding.symmetric(horizontal=16))
        for found in (room, job_fair)
        if found is not None
    ]
    section = (
        ft.Column(
            [card, *located],
            spacing=12,  # one section: closer than the 24 dp between sections
        )
        if located
        else card
    )
    # Keyed, so the removed note a refresh puts above it (D-186) leaves it mounted
    # instead of shifting it: the location card's pulse never restarts (D-349).
    section.key = f"when.{session.id}"
    return section


def _time_tile(
    session: Session, info: ConferenceInfo, use_24h: bool, screen: str
) -> ft.Control:
    """The day and time, where the session stands and the zone: one phrase."""
    view = session_view(session, info.zone, use_24h=use_24h)
    day = day_heading(session.day)
    # The status follows the start the tile shows: the Job Fair opens at 9:30, though
    # the Schedule groups it at 10:00 (DATA-11).
    lines: list[ft.Control] = [StatusLine(session.display_start, session.end)]
    # The device's offset at the session's own start, so a DST change between today
    # and then gives no note, and a real difference names the session's zone (PDT).
    device_offset = session.start.astimezone().utcoffset()
    note = zone_note(session.start, info.zone, info.time_zone_name, device_offset)
    if note is not None:
        lines.append(_supporting(note))
    return named(
        f"{screen}.when",
        ft.ListTile(
            leading=ft.Icon(ft.Icons.SCHEDULE),
            # The day, then the time on a line of its own, so a long day never
            # pushes the range onto two lines; a range wider than its line, at
            # the largest text sizes, breaks after its dash only (D-229).
            # The status and the note are in the title too, styled as supporting
            # lines: a subtitle would keep a two-line tile's height when both are
            # absent (another day, on Pacific time), with a blank under the range.
            title=ft.Column(
                [
                    ft.Text(day),
                    ft.Text(
                        on_screen(view.when),
                        semantics_label=view.spoken_when,
                    ),
                    ft.Column(lines, spacing=2),
                ],
                spacing=0,
            ),
            title_alignment=ft.ListTileTitleAlignment.TITLE_HEIGHT,
        ),
    )


def _place_tile(label: str, screen: str) -> ft.Control:
    """A place the feed has no room for: shown, opening nothing."""
    return named(
        f"{screen}.room",
        ft.ListTile(
            leading=ft.Icon(ft.Icons.PLACE_OUTLINED),
            title=label,
            title_alignment=ft.ListTileTitleAlignment.TITLE_HEIGHT,
        ),
    )


@ft.component
def OtherRooms(
    session: Session, where: Places, view_path: str, screen: str
) -> ft.Control:
    """The other rooms, folded: lightning talks and breaks list up to seven.

    A component, so it holds whether it is open: a `FoldTile` (D-157's rule for
    inputs), since one whose `expanded` was left to Flutter folded up again when the
    user came back from a room's detail.

    Args:
        session: The session.
        where: Its places, with at least one other room.
        view_path: The View's own path.
        screen: The screen's name in the identifiers.
    """
    prefs = use_prefs()
    is_open, set_open = ft.use_state(False)
    return FoldTile(
        ft.Text(where.others_label),
        [
            LinkTile(
                room.name,
                room_href(view_path, room, session.id),
                identifier=f"{screen}.room.{room.slug}",
            )
            for room in where.others
        ],
        expanded=is_open,
        on_change=set_open,
        style=expand_style(prefs),
        identifier=f"{screen}.other_rooms",
        # Under the room tile, a blank as wide as its icon lines the two titles up;
        # alone (a break in many rooms), the place icon.
        leading=ft.Container(width=24)
        if where.label
        else ft.Icon(ft.Icons.PLACE_OUTLINED),
        # Each room's title under the tile's title: 16 + 24 + 16 dp in.
        controls_padding=ft.Padding.only(left=40),
    )


@ft.component
def StatusLine(start: datetime, end: datetime) -> ft.Control:
    """Where a session stands now: "Starts in 25 min", "Happening now" or "Ended".

    It ticks with `use_minute()` while it is mounted and the app is in the foreground
    (D-40) and re-renders itself only; it reads `clock.now()`, so the Developer fake
    clock moves it too (D-43). It shows nothing when `time_status()` has nothing to
    say, and screen readers hear the words ("Starts in 25 minutes").

    Args:
        start: When the session starts, as its time tile shows it
            (`Session.display_start`).
        end: When it ends.
    """
    svc = use_services()
    tokens = use_tokens()
    use_minute()
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
    """A tile's supporting line, in `on_surface_variant` (ux.md §3.9)."""
    return ft.Text(
        text,
        theme_style=ft.TextThemeStyle.BODY_MEDIUM,
        color=ft.Colors.ON_SURFACE_VARIANT,
    )
