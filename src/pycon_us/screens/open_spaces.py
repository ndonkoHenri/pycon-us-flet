"""Open spaces (``/more/open-spaces``): the open spaces by day and time (EVT-01, EVT-02).

The Tracks hub opens the same page as its child, ``/more/tracks/open-spaces``, so Back
returns to the hub (D-207).

The app bar's ``+`` proposes one: "Propose an open space" opens the site's sign-up,
from the year data (``content.toml``'s ``[open_spaces]``, D-45), in the in-app browser
(the link rule, INFO-14). Under it, day tabs over swipeable day lists, a tab for each
day the feed has open spaces on, named by its date (the Schedule's ``day_tab()``):
Ionic called every day after Saturday "Sunday". The page opens on today when it has
open spaces, else on the first day.

Each day's list starts with the year's intro line, so it scrolls away with the list,
then its time slots (D-31): the ``TimeGutter`` beside ``SessionRow``s with their
stars (D-184), without the "Open space" badge every row would repeat (D-199). A tap
pushes the session, one drill level (D-17). Each day is a memoised list given only its
own saved ids, so a star tap re-renders one day and in it one row (D-153). The
Schedule's filter, which hides open spaces by default, never applies here (D-20).

Without data the page loads and fails as the Schedule does (ux.md §4.1); a feed with
no open spaces yet says so, with "Propose one".
"""

from collections.abc import Sequence
from datetime import date
from typing import cast

import flet as ft

from pycon_us import clock
from pycon_us.core.row_views import SessionView, by_slot
from pycon_us.core.timefmt import time_label, today
from pycon_us.core.timeline import DaySessions, track_sessions
from pycon_us.favorites import use_favorites
from pycon_us.prefs import use_prefs
from pycon_us.screens.schedule_days import TAB_MS, day_tab
from pycon_us.services import Services, use_services
from pycon_us.services.errors import report_errors
from pycon_us.state import use_conference
from pycon_us.theme import Tokens, use_tokens
from pycon_us.ui.badges import ToggleFavorite, use_favorite_toggle
from pycon_us.ui.links import OPENS_IN, LinkKind, external, open_link
from pycon_us.ui.scaffold import AppScaffold
from pycon_us.ui.session_rows import SessionRow, use_session_views
from pycon_us.ui.states import EmptyState, NoDataState
from pycon_us.ui.time_gutter import TimeSlot

SCREEN = "open_spaces"
"""The screen's name in its semantics identifiers (decisions §M)."""

TRACK = "Open Space"
"""The open spaces' track key, as feed processing names them (DATA-05)."""

TITLE = "Open spaces"
"""The page's name: its app bar's title and its More row (ux.md §4.9's spelling)."""

PROPOSE = "Propose an open space"


@ft.component
def OpenSpaces() -> ft.View:
    """The Open spaces page: a tab per day, each day's open spaces in time slots."""
    page = ft.context.page
    svc = use_services()
    conference = use_conference()
    favorites = use_favorites()
    prefs = use_prefs()
    on_toggle = use_favorite_toggle(favorites)
    tokens = use_tokens()
    picked, set_picked = ft.use_state(cast(date | None, None))
    info = svc.year.conference
    copy = svc.year.content.open_spaces
    use_24h = bool(page.media and page.media.always_use_24_hour_format)
    data = conference.data
    # Once per feed version (and memoised per feed by the query itself, D-178).
    groups = ft.use_memo(
        lambda: track_sessions(data, TRACK) if data else (), [conference.version]
    )
    ids = ft.use_memo(lambda: [s.id for day in groups for s in day.sessions], [groups])
    all_views = use_session_views(conference, ids, use_24h=use_24h)
    # Each day's views as one tuple, the same object until the views change, so the
    # memoised day lists skip a render that leaves their day as it was.
    days = ft.use_memo(lambda: day_views(all_views, groups), [all_views, groups])
    # The badge every row would repeat; one object, so the day lists still skip.
    omit = ft.use_memo(lambda: frozenset({info.track_name(TRACK)}), [])

    @report_errors
    async def refresh() -> None:
        await conference.refresh(svc.storage, svc.year, closed=svc.closed)

    actions = [propose_button(copy.propose_url, svc)] if copy else None
    if data is None:
        body: ft.Control = ft.ListView(
            [
                NoDataState(
                    conference.problem,
                    on_retry=refresh,
                    retrying=conference.status(info) == "refreshing",
                    identifier=f"{SCREEN}.no_data",
                )
            ],
            expand=True,
        )
        return AppScaffold(title=TITLE, actions=actions, body=body)
    if not days:
        url = copy.propose_url if copy else None
        return AppScaffold(title=TITLE, actions=actions, body=none_yet(url, svc))

    dates = [day for day, _ in days]
    current = today(clock.now(), info.zone)
    # The tab the user picked stays picked across renders (a star tap, a refresh).
    shown = (
        picked
        if picked is not None and picked in dates
        else opening_day(dates, current)
    )

    @report_errors
    def changed(e: ft.Event[ft.Tabs]) -> None:
        set_picked(dates[e.control.selected_index])

    pages: list[ft.Control] = [
        DayList(
            day,
            views,
            favorites.ids & {view.session.id for view in views},
            on_toggle,
            tokens,
            use_24h=use_24h,
            time_above=prefs.time_above,
            intro=copy.intro if copy else "",
            omit=omit,
        )
        for day, views in days
    ]
    tabs = ft.Tabs(
        length=len(dates),
        selected_index=dates.index(shown),
        animation_duration=ft.Duration(milliseconds=prefs.motion_ms(TAB_MS)),
        on_change=changed,
        expand=True,
        content=ft.Column(
            [
                ft.TabBar(
                    [
                        day_tab(i, day, is_today=day == current, screen=SCREEN)
                        for i, day in enumerate(dates)
                    ],
                    scrollable=True,  # three days fit no phone at large text
                    tab_alignment=ft.TabAlignment.START,
                ),
                ft.TabBarView(pages, expand=True),
            ],
            spacing=0,
            expand=True,
        ),
    )
    return AppScaffold(title=TITLE, actions=actions, body=tabs)


def opening_day(dates: Sequence[date], current: date) -> date:
    """Return the day the page opens on: today when it has open spaces, else the first.

    Args:
        dates: The days with open spaces, in order; at least one.
        current: Today, in conference time (``clock.now()``, D-43).
    """
    return current if current in dates else dates[0]


def day_views(
    views: Sequence[SessionView], groups: Sequence[DaySessions]
) -> tuple[tuple[date, tuple[SessionView, ...]], ...]:
    """Return each day's row views, in the order ``track_sessions()`` lists them.

    Args:
        views: Every open space's view, built once per feed version.
        groups: The open spaces by day, in schedule order.
    """
    by_id = {view.session.id: view for view in views}
    return tuple(
        (group.day, tuple(by_id[s.id] for s in group.sessions if s.id in by_id))
        for group in groups
    )


def propose_button(url: str, svc: Services) -> ft.Control:
    """Return the app bar's "Propose an open space": the site's sign-up (EVT-02).

    An icon button whose tooltip shows what it does; for screen readers it is a link
    named "Propose an open space" then "Opens in browser" (ux.md §4.7), so the tooltip
    stays out of the semantics, where iOS would read it after the name (D-184).

    Args:
        url: The year's sign-up (``OpenSpacesInfo.propose_url``).
        svc: The session's services, for the launcher.
    """

    @report_errors
    async def propose() -> None:
        await open_link(svc, url)

    button = ft.IconButton(
        ft.Icons.ADD,
        tooltip=ft.Tooltip(message=PROPOSE, exclude_from_semantics=True),
        on_click=propose,
    )
    return external(
        f"{SCREEN}.propose",
        ft.Semantics(label=f"{PROPOSE}\n{OPENS_IN[LinkKind.WEB]}", content=button),
    )


def none_yet(url: str | None, svc: Services) -> ft.Control:
    """Return the page of a feed without open spaces: why, and "Propose one".

    Open spaces are proposed during the conference, so before it the feed has none:
    the way out is to propose one, when the year says where (ux.md §4.6).

    Args:
        url: The year's sign-up, or None for a year without one: no button then, and
            the sentence says the app shows them on its own (D-175).
        svc: The session's services, for the launcher.
    """
    on_action = None
    if url is not None:

        @report_errors
        async def propose() -> None:
            await open_link(svc, url)

        on_action = propose
    return ft.ListView(
        [
            EmptyState(
                "No open spaces yet",
                icon=ft.Icons.FORUM_OUTLINED,
                body="Attendees propose them during the conference. They show here "
                "as soon as the schedule lists them.",
                action="Propose one" if on_action is not None else None,
                on_action=on_action,
                link_id=f"{SCREEN}.propose_one",
                identifier=f"{SCREEN}.none",
            )
        ],
        expand=True,
    )


def DayList(
    day: date,
    views: tuple[SessionView, ...],
    saved: frozenset[str],
    on_toggle: ToggleFavorite,
    tokens: Tokens,
    *,
    use_24h: bool,
    time_above: bool,
    intro: str,
    omit: frozenset[str],
) -> ft.Control:
    """Return one day's page: the intro line, then the day's open spaces by slot.

    A memoised component keyed by the day (D-153): a star tap re-renders the day whose
    ``saved`` changed and in it the one row (``SessionRow`` is memoised too).

    Args:
        day: The conference-local date.
        views: The day's row views, in schedule order; the same object per feed.
        saved: The saved ids among this day's open spaces only.
        on_toggle: The page's one star handler (``use_favorite_toggle()``).
        tokens: The scheme's tokens (D-150).
        use_24h: Whether the device uses the 24-hour clock.
        time_above: Put each slot's time above its rows (``Prefs.time_above``,
            D-214).
        intro: The year's intro line; empty for none.
        omit: Badge labels the page already says: "Open space".
    """
    return _DayList(
        day,
        views,
        saved,
        on_toggle,
        tokens,
        use_24h=use_24h,
        time_above=time_above,
        intro=intro,
        omit=omit,
        key=day.isoformat(),  # pyright: ignore[reportCallIssue]  # as SessionRow's
    )


@ft.memo
@ft.component
def _DayList(
    day: date,
    views: tuple[SessionView, ...],
    saved: frozenset[str],
    on_toggle: ToggleFavorite,
    tokens: Tokens,
    *,
    use_24h: bool,
    time_above: bool,
    intro: str,
    omit: frozenset[str],
) -> ft.Control:
    """The body of ``DayList``; it runs only when its props change (F34)."""
    zone = use_services().year.conference.zone
    items: list[ft.Control] = []
    if intro:
        items.append(
            ft.Container(
                ft.Text(
                    intro,
                    theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                padding=ft.Padding.symmetric(horizontal=16, vertical=12),
            )
        )
    for start, slot in by_slot(views):
        rows = [
            SessionRow(
                view,
                view.session.id in saved,
                on_toggle,
                tokens,
                screen=SCREEN,
                omit=omit,
            )
            for view in slot
        ]
        label = time_label(start, zone, use_24h=use_24h)
        # A divider above every slot but a first one with nothing above it.
        items.append(TimeSlot(label, rows, divider=bool(items), above=time_above))
    return ft.ListView(
        items,
        key=f"day-{day.isoformat()}",
        expand=True,
        padding=ft.Padding.only(bottom=8),
    )
