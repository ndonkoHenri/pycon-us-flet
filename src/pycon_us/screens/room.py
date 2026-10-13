"""Room detail (``…/room/<slug>``): a stub until P1 (ROOM-02..04).

It lists the room's sessions by day, in time slots (D-31): a ``TimeGutter`` beside the
slot's rows, ``SessionRow``s with their stars and ``NoticeRow``s for its breaks and
meals. A tap pushes the session, one drill level. P1's room detail (#101) brings day
tabs and the highlight (ux.md §5.9). An unknown slug shows a not-found state under the
back arrow.
"""

from datetime import datetime
from itertools import groupby

import flet as ft

from pycon_us.core.queries import SessionView, by_day
from pycon_us.core.timefmt import day_heading, time_label
from pycon_us.favorites import use_favorites
from pycon_us.screens.stub import note, stub_body
from pycon_us.services import use_services
from pycon_us.state import use_conference
from pycon_us.theme import use_tokens
from pycon_us.ui.badges import use_favorite_toggle
from pycon_us.ui.rows import (
    NoticeRow,
    SessionRow,
    TimeGutter,
    is_notice,
    use_session_views,
)
from pycon_us.ui.scaffold import AppScaffold, SectionHeader

SCREEN = "room"
"""The screen's name in its rows' semantics identifiers (decisions §M)."""


@ft.component
def RoomDetail(room_slug: str) -> ft.View:
    """One room: its sessions by day and time slot.

    Args:
        room_slug: The room's slug (``slugs.slugify_room``), unquoted.
    """
    page = ft.context.page
    conference = use_conference()
    favorites = use_favorites()
    on_toggle = use_favorite_toggle(favorites)
    tokens = use_tokens()
    info = use_services().year.conference
    use_24h = bool(page.media and page.media.always_use_24_hour_format)
    data = conference.data
    room = data.rooms.get(room_slug) if data else None
    views = use_session_views(
        conference, room.session_ids if room else (), use_24h=use_24h
    )
    if room is None:
        return AppScaffold(
            title="Not found",
            body=stub_body([note(f"No room {room_slug!r} in this year's schedule.")]),
        )

    controls: list[ft.Control] = []
    for day, day_views in by_day(views, info.zone):
        controls.append(SectionHeader(day_heading(day)))
        for index, (start, slot) in enumerate(groupby(day_views, _start)):
            label = time_label(start, info.zone, use_24h=use_24h)
            rows = [
                NoticeRow(v, screen=SCREEN)
                if is_notice(v.session, info)
                else SessionRow(
                    v, v.session.id in favorites.ids, on_toggle, tokens, screen=SCREEN
                )
                for v in slot
            ]
            controls.append(_slot(label, rows, divider=index > 0))
    return AppScaffold(title=room.name, body=stub_body(controls))


def _start(view: SessionView) -> datetime:
    # The time group's start, as the Schedule's slots use it (DATA-13): the Job Fair
    # sits in the 10:00 slot and its row says 9:30 (DATA-11, D-41).
    return view.session.start


def _slot(label: str, rows: list[ft.Control], *, divider: bool) -> ft.Control:
    """One time slot (D-31): the gutter beside its rows, under a divider after the first."""
    slot = ft.Row(
        [TimeGutter(label), ft.Column(rows, spacing=0, expand=True)],
        spacing=0,
        vertical_alignment=ft.CrossAxisAlignment.START,
    )
    return ft.Column([ft.Divider(height=1), slot], spacing=0) if divider else slot
