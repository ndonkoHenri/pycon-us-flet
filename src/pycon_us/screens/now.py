"""Now (``/now``), the start screen: "what should I do next?" (SCHED-25, SCHED-26; D-14).

From the top (ux.md §5.1): the status header (``now_header``), the status strip, which
refreshes the feed every 15 min while Now shows (D-175), then by season:

- before the conference, the key dates and "Build your schedule";
- on its days, **Your next session** (``now_card``: ``agenda.next_for_me()``'s saved
  session to go to next, with its star, its countdown and "Show room", and its elapsed
  bar once it is on), **Happening now** (the other sessions on, saved ones first, each
  with an elapsed bar), **Up next** (the next slot, ``NowNext.up_next``, but the
  card's session) and a link to the Schedule;
- on the last evening and the sprint days, the Sprints page; afterwards, the schedule
  to look back at.

Schedule filters never apply (D-20). The screen recomputes on the minute tick
(``use_minute()``): every 60 s while it is mounted and the app is in the foreground,
and at once on a resume (D-40, D-175), from ``clock.now()``, so the Developer fake clock
drives it (D-187). Its rows are the memoised session rows, their views built once per
feed version (D-153, D-184), and a row pushes its session over Now, so Back returns
here (D-17). Without data, the skeleton, then "Can't load the schedule" (D-32).
"""

from collections.abc import Mapping
from datetime import datetime
from functools import partial

import flet as ft

from pycon_us import clock
from pycon_us.config import ConferenceInfo
from pycon_us.core.agenda import (
    NowNext,
    Phase,
    elapsed_percent,
    next_for_me,
    now_next,
)
from pycon_us.core.models import ConferenceData, Session
from pycon_us.core.row_views import SessionView
from pycon_us.core.timefmt import (
    local_date,
    time_status,
    today,
)
from pycon_us.core.timeline import Slot
from pycon_us.favorites import use_favorites
from pycon_us.prefs import use_prefs
from pycon_us.screens.now_card import Row, next_session, nothing_next
from pycon_us.screens.now_header import (
    Season,
    StatusHeader,
    header_copy,
    key_dates,
    spoken,
    sprints_link,
    up_next_when,
)
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.state import use_conference
from pycon_us.theme import Tokens, use_tokens
from pycon_us.ui.badges import ToggleFavorite, use_favorite_toggle
from pycon_us.ui.navigation import use_scroll_to_top
from pycon_us.ui.rows import LinkTile
from pycon_us.ui.scaffold import AppScaffold, SectionHeader, search_button
from pycon_us.ui.semantics import named
from pycon_us.ui.session_rows import (
    NoticeRow,
    SessionRow,
    is_notice,
    use_session_views,
)
from pycon_us.ui.states import NO_DATA_BODY, EmptyState, SkeletonList
from pycon_us.ui.status_strip import StatusStrip, use_minute

SCREEN = "now"
"""The screen's name in its semantics identifiers (decisions §M)."""

NOTHING_ON = "Nothing in session right now"
"""Happening now between two slots of a day (ux.md §5.1)."""


@ft.component
def Now() -> ft.View:
    """The Now root: where the conference stands, and what to do next."""
    list_ref, scroll_to_top = use_scroll_to_top()
    page = ft.context.page
    view_path = ft.use_view_path()
    svc = use_services()
    conference = use_conference()
    favorites = use_favorites()
    on_toggle = use_favorite_toggle(favorites)
    tokens = use_tokens()
    prefs = use_prefs()
    use_minute()  # recompute every minute while Now shows, and at once on a resume
    info = svc.year.conference
    use_24h = bool(page.media and page.media.always_use_24_hour_format)
    data = conference.data
    # Every session's view, once per feed version: the rows Now shows change with the
    # minute, and a view that stays the same object lets its row skip its body (F34).
    views = use_session_views(
        conference, tuple(data.sessions) if data else (), use_24h=use_24h
    )
    by_id = ft.use_memo(lambda: {v.session.id: v for v in views}, [views])

    @report_errors
    async def refresh() -> None:
        await conference.refresh(svc.storage, svc.year, closed=svc.closed)

    row = partial(_row, by_id, info, favorites.ids, on_toggle, tokens)

    rows: list[ft.Control]
    if data is None and conference.problem is None:
        # The first fetch runs, or is about to (NEW-03); the strip says so.
        rows = [StatusStrip(auto_refresh=True), SkeletonList("Loading schedule")]
    elif data is None:
        rows = [
            StatusStrip(auto_refresh=True),  # its bar shows a retry
            EmptyState(
                "Can't load the schedule",
                icon=ft.Icons.CLOUD_OFF_OUTLINED,
                body=NO_DATA_BODY[conference.problem or "offline"],
                action="Try again",
                on_action=refresh,
                disabled=conference.refreshing,
                identifier=f"{SCREEN}.no_data",
            ),
        ]
    else:
        now = clock.now()
        answer = now_next(data, now)
        copy = header_copy(
            answer,
            now,
            data,
            info,
            use_24h=use_24h,
            device_offset=now.astimezone().utcoffset(),
        )
        rows = [
            StatusHeader(info.name, copy, dark=prefs.dark),
            StatusStrip(auto_refresh=True),
            *_sections(
                copy.season,
                answer,
                now,
                data,
                info,
                row,
                saved=favorites.ids,
                view_path=view_path,
                live=tokens.live,
                use_24h=use_24h,
            ),
        ]
    return AppScaffold(
        title="Now",
        actions=[search_button(svc.memory, "all")],
        body=ft.ListView(
            rows, expand=True, ref=list_ref, padding=ft.Padding.only(bottom=16)
        ),
        on_retap=scroll_to_top,
    )


def _row(
    by_id: Mapping[str, SessionView],
    info: ConferenceInfo,
    saved: frozenset[str],
    on_toggle: ToggleFavorite,
    tokens: Tokens,
    session: Session,
    *,
    screen: str = SCREEN,
    elapsed: int | None = None,
) -> ft.Control:
    """One session's memoised row (D-184): a notice's, or a session's with its star."""
    view = by_id[session.id]
    if is_notice(session, info):  # breaks and notices: no star, no bar (D-31)
        return NoticeRow(view, screen=screen)
    return SessionRow(
        view, session.id in saved, on_toggle, tokens, screen=screen, elapsed=elapsed
    )


def _sections(
    current: Season,
    answer: NowNext,
    now: datetime,
    data: ConferenceData,
    info: ConferenceInfo,
    row: Row,
    *,
    saved: frozenset[str],
    view_path: str,
    live: str,
    use_24h: bool,
) -> list[ft.Control]:
    """Return what Now shows under the header and the strip, in the given season."""
    day = today(now, info.zone)
    sections: list[ft.Control] = []
    if current is Season.COUNTDOWN:
        sections += key_dates(info)
        sections.append(_button("Build your schedule", "/schedule", "build_schedule"))
        return sections
    if current is Season.OVER:
        sections.append(
            LinkTile(
                "Look back at the schedule",
                "/schedule",
                icon=ft.Icons.CALENDAR_MONTH_OUTLINED,
                identifier=f"{SCREEN}.schedule",
            )
        )
        return sections
    if answer.phase is Phase.AFTER:  # the last evening and the sprint days
        sections.append(sprints_link(info))
        return sections

    upcoming = answer.up_next
    mine = next_for_me(data, saved, now)
    if mine is not None:
        sections += next_session(mine, now, data, row, view_path)
    else:
        has_saved = any(session_id in data.sessions for session_id in saved)
        sections += nothing_next(has_saved, tonight=answer.phase is Phase.AFTER_DAY)
    # The card already shows your session; when it is all that is on, or all that is
    # next, the card says so, and an empty Happening now would claim nothing is.
    others = _without(answer.happening, mine)
    if answer.phase is Phase.DAY and (others or not answer.happening):
        sections += _happening(others, now, row, saved, live)
    if upcoming is not None and (later := _without(upcoming.sessions, mine)):
        sections += _up_next(upcoming, later, now, row, info, use_24h=use_24h)
    # Only a navigation: the Schedule (#86) opens on today during the conference. With
    # no slot after this one, the rest of today is the slot that is on.
    rest_of_today = upcoming is None or local_date(upcoming.start, info.zone) == day
    label = (
        "See the rest of today in Schedule" if rest_of_today else "Open the schedule"
    )
    sections.append(_button(label, "/schedule", "schedule", text=True))
    return sections


def _without(
    sessions: tuple[Session, ...], mine: Session | None
) -> tuple[Session, ...]:
    """``sessions`` but your next session, which the card shows."""
    return tuple(s for s in sessions if mine is None or s.id != mine.id)


def _happening(
    happening: tuple[Session, ...],
    now: datetime,
    row: Row,
    saved: frozenset[str],
    live: str,
) -> list[ft.Control]:
    """Happening now: the sessions on but yours, saved ones first, each with its bar."""
    dot = ft.Container(width=8, height=8, border_radius=4, bgcolor=live)
    header = SectionHeader("Happening now", level=2, leading=dot)
    if not happening:
        return [header, _note(NOTHING_ON, f"{SCREEN}.nothing_on")]
    # Stable: within each group, the slot's order (schedule_order) stays.
    ordered = sorted(happening, key=lambda session: session.id not in saved)
    return [
        header,
        ft.Column(
            [
                row(session, elapsed=elapsed_percent(session, now))
                for session in ordered
            ],
            spacing=0,
        ),
    ]


def _up_next(
    slot: Slot,
    sessions: tuple[Session, ...],
    now: datetime,
    row: Row,
    info: ConferenceInfo,
    *,
    use_24h: bool,
) -> list[ft.Control]:
    """Up next: the next slot's start, its countdown on its own day, then its rows.

    ``sessions`` are the slot's rows but your next session, which the card shows.
    """
    heading = f"Up next · {up_next_when(slot, now, info, use_24h=use_24h)}"
    controls: list[ft.Control] = [
        SectionHeader(heading, level=2, spoken=spoken(heading))
    ]
    # A slot has no end of its own: its start twice says only "Starts in 18 min".
    status = time_status(slot.start, slot.start, now, info.zone)
    if status is not None:
        controls.append(
            ft.Container(
                ft.Text(
                    status.label,
                    semantics_label=status.spoken,
                    theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                padding=ft.Padding.only(left=16, right=16),
            )
        )
    controls.append(ft.Column([row(session) for session in sessions], spacing=0))
    return controls


def _button(label: str, location: str, name: str, *, text: bool = False) -> ft.Control:
    """A button that opens another tab: a tonal one, or a text one (``text``)."""
    page = ft.context.page

    @report_errors
    def go() -> None:
        page.navigate(location)

    button: ft.Control
    if text:
        button = ft.TextButton(
            label, icon=ft.Icons.CALENDAR_MONTH_OUTLINED, on_click=go
        )
    else:
        button = ft.FilledTonalButton(label, on_click=go)
    return ft.Container(
        named(f"{SCREEN}.{name}", button),
        # At the list's start, as its rows' text: a text button's label sits 8 dp
        # inside it, so 8 dp in puts the label 16 dp in.
        padding=ft.Padding.only(left=8 if text else 16, top=8, right=16),
        alignment=ft.Alignment.CENTER_LEFT,
    )


def _note(text: str, identifier: str) -> ft.Control:
    """A line of supporting text in the list's side padding."""
    return ft.Container(
        named(
            identifier,
            ft.Text(
                text,
                theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
        ),
        padding=ft.Padding.symmetric(horizontal=16, vertical=4),
    )
