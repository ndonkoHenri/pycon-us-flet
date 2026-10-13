"""Now (``/now``), the start screen: "what should I do next?" (SCHED-25, SCHED-26; D-14).

From the top (ux.md §5.1): the status header (``now_header``), the status strip, which
refreshes the feed every 15 min while Now shows (D-175), then by season:

- before the conference, the key dates and "Build your schedule";
- on its days, **Your next session** (``agenda.next_for_me()``: the saved session to go
  to next, with its star, its countdown and "Show room", and its elapsed bar once it
  is on), **Happening now** (the other sessions on, saved ones first, each with an
  elapsed bar), **Up next** (the next slot, ``NowNext.up_next``) and a link to the
  Schedule;
- on the sprint days, the Sprints page; afterwards, the schedule to look back at.

Schedule filters never apply (D-20). The screen recomputes on the minute tick
(``use_minute()``): every 60 s while it is mounted and the app is in the foreground,
and at once on a resume (D-40, D-175), from ``clock.now()``, so the Developer fake clock
drives it (D-187). Its rows are the memoised session rows, their views built once per
feed version (D-153, D-184), and a row pushes its session over Now, so Back returns
here (D-17). Without data, the skeleton, then "Can't load the schedule" (D-32).
"""

from collections.abc import Callable, Mapping
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
from pycon_us.core.row_views import SessionView, places
from pycon_us.core.timefmt import (
    local_date,
    time_status,
    today,
)
from pycon_us.core.timeline import Slot
from pycon_us.favorites import use_favorites
from pycon_us.prefs import use_prefs
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
from pycon_us.ui.scaffold import (
    AppScaffold,
    SectionHeader,
    StatusStrip,
    search_button,
    use_minute,
)
from pycon_us.ui.session_rows import (
    NoticeRow,
    SessionRow,
    is_notice,
    use_session_views,
)
from pycon_us.ui.states import NO_DATA_BODY, EmptyState, SkeletonList
from pycon_us.ui.when_where import StatusLine, room_href

SCREEN = "now"
"""The screen's name in its semantics identifiers (decisions §M)."""

NEXT = "now.next"
"""The identifiers' prefix of the next-session card's row: ``now.next.session.<key>``,
``now.next.favorite.<key>``."""

NOTHING_ON = "Nothing in session right now"
"""Happening now between two slots of a day (ux.md §5.1)."""

type Row = Callable[..., ft.Control]
"""Builds one session's row: ``row(session, screen=..., elapsed=...)``."""


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
    if answer.phase is Phase.AFTER and day <= info.last_day:  # the sprints come
        sections.append(sprints_link(info))
    if current is Season.SPRINTS:
        return sections

    upcoming = answer.up_next
    mine = next_for_me(data, saved, now)
    if mine is not None:
        sections += _next_session(mine, now, data, row, view_path)
    elif upcoming is not None:
        has_saved = any(session_id in data.sessions for session_id in saved)
        sections += _nothing_next(has_saved, tonight=answer.phase is Phase.AFTER_DAY)
    # The card already shows your session; when it is all that is on, the card's
    # "Happening now" says it, and an empty section would claim nothing is.
    others = tuple(s for s in answer.happening if mine is None or s.id != mine.id)
    if answer.phase is Phase.DAY and (others or not answer.happening):
        sections += _happening(others, now, row, saved, live)
    if upcoming is not None:
        sections += _up_next(upcoming, now, row, info, use_24h=use_24h)
        # Only a navigation: the Schedule (#86) opens on today during the conference.
        rest_of_today = local_date(upcoming.start, info.zone) == day
        label = (
            "See the rest of today in Schedule"
            if rest_of_today
            else "Open the schedule"
        )
        sections.append(_button(label, "/schedule", "schedule", text=True))
    return sections


def _next_session(
    session: Session, now: datetime, data: ConferenceData, row: Row, view_path: str
) -> list[ft.Control]:
    """Your next session: its row, star and bar, then its countdown and "Show room"."""
    page = ft.context.page
    room = places(session, data.rooms).room
    on = session.start <= now < session.end  # as next_for_me() counts it

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
            _named(
                f"{SCREEN}.show_room",
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
        ),
    )
    return [
        SectionHeader("Your next session", level=2),
        card,
    ]


def _nothing_next(has_saved: bool, *, tonight: bool) -> list[ft.Control]:
    """No saved session is on or due within 3 hours: say so, and where to look.

    ``tonight``: the day is over (phase ``after_day``), when "the next 3 hours" would
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
            identifier=f"{SCREEN}.next_session",
        )
    else:
        tile = LinkTile(
            "Nothing saved yet",
            "/schedule",
            icon=ft.Icons.STAR_BORDER,
            subtitle="Tap the star on a session, and your next one shows here",
            identifier=f"{SCREEN}.next_session",
        )
    return [SectionHeader("Your next session", level=2), tile]


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
    slot: Slot, now: datetime, row: Row, info: ConferenceInfo, *, use_24h: bool
) -> list[ft.Control]:
    """Up next: the next slot's start, its countdown on its own day, then its rows."""
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
    controls.append(ft.Column([row(session) for session in slot.sessions], spacing=0))
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
        _named(f"{SCREEN}.{name}", button),
        # At the list's start, as its rows' text: a text button's label sits 8 dp
        # inside it, so 8 dp in puts the label 16 dp in.
        padding=ft.Padding.only(left=8 if text else 16, top=8, right=16),
        alignment=ft.Alignment.CENTER_LEFT,
    )


def _note(text: str, identifier: str) -> ft.Control:
    """A line of supporting text in the list's side padding."""
    return ft.Container(
        _named(
            identifier,
            ft.Text(
                text,
                theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
        ),
        padding=ft.Padding.symmetric(horizontal=16, vertical=4),
    )


def _named(identifier: str, control: ft.Control) -> ft.Control:
    """Give ``control`` a semantics identifier on its own node (decisions §M).

    Merged: an identifier's ``Semantics`` alone is a node of its own, an empty extra
    stop for TalkBack around the button (seen in ``uiautomator dump``).
    """
    return ft.MergeSemantics(
        content=ft.Semantics(identifier=identifier, content=control)
    )
