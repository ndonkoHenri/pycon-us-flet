"""Now's "Your next session": the card, or the tile that says why there is none (ux.md §5.1).

``next_session()`` shows ``agenda.next_for_me()``'s answer in a filled card: the
session's row with its star and, once the row's own time has come, its elapsed bar,
then session detail's status line and "Show room". ``nothing_next()`` says why there is
no card and where to look. ``named()`` gives Now's buttons and notes their identifiers.
Apart from ``now.py`` so that the screen stays under about 400 lines (D-66, D-190).
"""

from collections.abc import Callable
from datetime import datetime

import flet as ft

from pycon_us.core.agenda import elapsed_percent
from pycon_us.core.models import ConferenceData, Session
from pycon_us.core.row_views import places
from pycon_us.services.errors import report_errors
from pycon_us.ui.rows import LinkTile
from pycon_us.ui.scaffold import SectionHeader
from pycon_us.ui.when_where import StatusLine, room_href

NEXT = "now.next"
"""The identifiers' prefix of the next-session card's row: ``now.next.session.<key>``,
``now.next.favorite.<key>``."""

HEADING = "Your next session"

type Row = Callable[..., ft.Control]
"""Builds one session's row: ``row(session, screen=..., elapsed=...)``."""


def next_session(
    session: Session, now: datetime, data: ConferenceData, row: Row, view_path: str
) -> list[ft.Control]:
    """Your next session: its row, star and bar, then its countdown and "Show room"."""
    page = ft.context.page
    room = places(session, data.rooms).room
    # From the start the row shows, as its status and its bar count (D-186): the Job
    # Fair says 9:30 and is "Happening now" from then, though its slot starts at 10:00.
    on = session.display_start <= now < session.end

    @report_errors
    def show_room() -> None:
        assert room is not None  # the button shows only with a room
        page.navigate(room_href(view_path, room, session.id))

    actions: list[ft.Control] = [
        # Its own minute tick: "Starts in 12 min", then "Happening now" in live.
        StatusLine(session.display_start, session.end)
    ]
    if room is not None:
        actions.append(
            named(
                "now.show_room",
                ft.TextButton(
                    "Show room", icon=ft.Icons.PLACE_OUTLINED, on_click=show_room
                ),
            )
        )
    card = ft.Card(
        variant=ft.CardVariant.FILLED,
        margin=ft.Margin.symmetric(horizontal=16),
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,  # the row's ink stays inside
        content=ft.Column(
            [
                row(
                    session,
                    screen=NEXT,
                    elapsed=elapsed_percent(session, now) if on else None,
                ),
                ft.Container(
                    # Wrapping: at large text the button moves under the status
                    # whole, instead of squeezing "Happening now" into two lines.
                    ft.Row(
                        actions,
                        wrap=True,
                        spacing=8,
                        run_spacing=0,
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    # Under the row's own 12 dp; the button's end 8 dp from the card's.
                    padding=ft.Padding.only(left=16, right=8, bottom=4),
                ),
            ],
            spacing=0,
            # A wrapping row is only as wide as its content: stretched, its
            # SPACE_BETWEEN puts the button at the card's end.
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        ),
    )
    return [SectionHeader(HEADING, level=2), card]


def nothing_next(has_saved: bool, *, tonight: bool) -> list[ft.Control]:
    """No saved session is on or due within 3 hours: say so, and where to look.

    Args:
        has_saved: Whether any saved session is in the feed.
        tonight: The day is over (phase ``after_day``), when "the next 3 hours" would
            be true but odd; what is saved is for a later day.
    """
    if has_saved:
        tile = LinkTile(
            "Nothing more saved for today"
            if tonight
            else "Nothing saved for the next 3 hours",
            "/my-schedule",
            icon=ft.Icons.STAR_BORDER,
            subtitle="See your saved sessions in My schedule",
            identifier="now.next_session",
        )
    else:
        tile = LinkTile(
            "Nothing saved yet",
            "/schedule",
            icon=ft.Icons.STAR_BORDER,
            subtitle="Tap the star on a session, and your next one shows here",
            identifier="now.next_session",
        )
    return [SectionHeader(HEADING, level=2), tile]


def named(identifier: str, control: ft.Control) -> ft.Control:
    """Give ``control`` a semantics identifier on its own node (decisions §M).

    Merged: an identifier's ``Semantics`` alone is a node of its own, an empty extra
    stop for TalkBack around the button (seen in ``uiautomator dump``).
    """
    return ft.MergeSemantics(
        content=ft.Semantics(identifier=identifier, content=control)
    )
