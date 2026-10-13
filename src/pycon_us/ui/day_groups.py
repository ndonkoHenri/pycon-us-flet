"""A day of session rows under its heading: one memoised list item (D-153).

A row says no day (D-184), so a list of sessions that spans days puts a heading per day
above its rows. ``DayGroup`` is that item for the lists made of ``DaySessions`` (D-185):
search's results (D-193) and the track pages (SCHED-22). It is memoised and keyed by
its day, as S2's slots are, so a star tap re-renders one day and in it one row, and a
list whose days stay the same re-renders none.
"""

from collections.abc import Mapping

import flet as ft

from pycon_us.core.row_views import SessionView
from pycon_us.core.timefmt import day_heading
from pycon_us.core.timeline import DaySessions
from pycon_us.services import use_services
from pycon_us.theme import Tokens
from pycon_us.ui.badges import ToggleFavorite
from pycon_us.ui.scaffold import SectionHeader
from pycon_us.ui.session_rows import NoticeRow, SessionRow, is_notice


def DayGroup(
    group: DaySessions,
    views: Mapping[str, SessionView],
    saved: frozenset[str],
    on_toggle: ToggleFavorite,
    tokens: Tokens,
    *,
    screen: str,
    level: int,
    top: int = 16,
    omit: frozenset[str] = frozenset(),
) -> ft.Control:
    """Return one day of sessions: its heading and its rows, one list item.

    A memoised component keyed by the day (D-153): a render that leaves a day's
    sessions as they were skips it, and a star tap re-renders only its day, whose
    ``saved`` changed, and in it only the one row. Breaks and notices are
    ``NoticeRow``s, the others ``SessionRow``s with their star (D-184).

    Args:
        group: The day and its sessions, in the Schedule's order.
        views: The row view of every session the list shows, by id; built once per
            feed version, so the same objects on every render.
        saved: The day's saved sessions (``Favorites.ids`` ∩ the day's ids).
        on_toggle: The list's one star handler.
        tokens: The scheme's tokens (D-150).
        screen: The screen's name in the rows' semantics identifiers, e.g. ``search``
            (decisions §M).
        level: The day heading's level in the page's outline (F40): 2 under the page's
            title, 3 under a heading of its own (search's "Sessions").
        top: The space above the day heading: 0 right under another heading.
        omit: Badge labels the page already shows, left out of every row: a track
            page's own badge (``badge_specs()``, D-199).
    """
    # As SessionRow's: ft.component's typing leaves out the key= its wrapper takes.
    return _DayGroup(
        group,
        views,
        saved,
        on_toggle,
        tokens,
        screen=screen,
        level=level,
        top=top,
        omit=omit,
        key=group.day.isoformat(),  # pyright: ignore[reportCallIssue]
    )


@ft.memo
@ft.component
def _DayGroup(
    group: DaySessions,
    views: Mapping[str, SessionView],
    saved: frozenset[str],
    on_toggle: ToggleFavorite,
    tokens: Tokens,
    *,
    screen: str,
    level: int,
    top: int,
    omit: frozenset[str],
) -> ft.Control:
    """The body of ``DayGroup``; it runs only when its props change (F34)."""
    info = use_services().year.conference
    rows = [
        NoticeRow(view, screen=screen)
        if is_notice(view.session, info)
        else SessionRow(
            view,
            view.session.id in saved,
            on_toggle,
            tokens,
            screen=screen,
            omit=omit,
        )
        for view in (views[session.id] for session in group.sessions)
    ]
    return ft.Column(
        [
            # A node of its own: else the heading joins the list item's node.
            ft.Semantics(
                container=True,
                content=SectionHeader(day_heading(group.day), level=level, top=top),
            ),
            *rows,
        ],
        spacing=0,
    )
