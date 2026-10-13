"""A track's page (``/more/tracks/<slug>``): its sessions by day (SCHED-21, SCHED-22).

An intro shows the track's badge as the schedule does, "New track" when it is new
this year, the track's plural name as the page's heading (the app bar's title stays
empty, as on session detail, D-186) and its legend line (EVT-04). Then
every session of the track, by day under level-2 day headings (F40), as ``SessionRow``s
with their stars (D-184), without the badges the intro already shows (D-199):
``track_sessions()``'s list, so the Posters track lists each
poster rather than the Posters row, and the Schedule's filter never applies, so the
open spaces it hides by default show on their own page (D-20, D-178). No paging: each
day is one memoised item of a lazy list (``ui.day_groups``, D-153), so a star tap
re-renders one day and one row.

The slug is the registry's (``conference.toml``, DATA-29), never derived from a track
key: an unknown one shows the not-found state under the back arrow, with the hub as
the way out (D-186). Without data the page loads and fails as the hub does (ux.md
§4.1).

The app bar's overflow holds "Add all to My schedule" (SCHED-24, D-207): every
session the page lists, on every day, straight to a SnackBar with Undo. It is not
offered on the notices and breaks, which have no stars (D-31). The open spaces never
reach this page: their slug is the Open spaces page's own route (D-205), which has no
overflow.
"""

from collections.abc import Awaitable, Callable, Sequence
from urllib.parse import unquote

import flet as ft

from pycon_us.config import Track
from pycon_us.core.timeline import DaySessions, track_sessions
from pycon_us.favorites import use_favorites
from pycon_us.screens.stub import not_found
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.state import use_conference
from pycon_us.theme import Tokens, use_tokens
from pycon_us.ui.badges import (
    NEW_TRACK,
    SPANISH,
    TrackBadge,
    badge_row,
    use_add_all,
    use_favorite_toggle,
)
from pycon_us.ui.day_groups import DayGroup
from pycon_us.ui.scaffold import AppScaffold
from pycon_us.ui.semantics import named
from pycon_us.ui.session_rows import NOTICE_GROUP, use_session_views
from pycon_us.ui.states import NO_DATA_BODY, EmptyState, SkeletonList

SCREEN = "track"
"""The screen's name in its semantics identifiers (decisions §M)."""

NOT_FOUND = "This track isn't in the current schedule"
"""The empty state of an unknown slug (ux.md §4.6)."""

ADD_ALL = "Add all to My schedule"
"""The overflow's item that saves the whole track (SCHED-24, D-207)."""


@ft.component
def TrackPage() -> ft.View:
    """``/more/tracks/<slug>``: the route's screen, ``TrackDetail`` for its slug.

    Route params arrive quoted, as a link wrote them, and are unquoted here (D-42).
    """
    return TrackDetail(slug=unquote(ft.use_route_params().get("slug", "")))


@ft.component
def TrackDetail(slug: str) -> ft.View:
    """One track: its intro, then its sessions by day, each with its star.

    Args:
        slug: The track's slug from the route (``Track.slug``), unquoted.
    """
    page = ft.context.page
    svc = use_services()
    conference = use_conference()
    favorites = use_favorites()
    on_toggle = use_favorite_toggle(favorites)
    add_all = use_add_all(favorites)
    tokens = use_tokens()
    track = svc.year.conference.track_for_slug(slug)
    data = conference.data
    # Once per feed version (and memoised per feed by the query itself, D-178): the
    # page re-renders on every star tap, and its day items compare these objects.
    days = ft.use_memo(
        lambda: track_sessions(data, track.key) if data and track else (),
        [conference.version, slug],
    )
    ids = ft.use_memo(lambda: [s.id for day in days for s in day.sessions], [days])
    all_views = use_session_views(
        conference,
        ids,
        use_24h=bool(page.media and page.media.always_use_24_hour_format),
    )
    views = ft.use_memo(lambda: {v.session.id: v for v in all_views}, [all_views])
    # The same frozenset per feed version, so the memoised day items still skip.
    shared = ft.use_memo(
        lambda: shared_badges(track, days) if track else frozenset[str](), [days]
    )

    @report_errors
    async def refresh() -> None:
        await conference.refresh(svc.storage, svc.year, closed=svc.closed)

    if track is None:
        return AppScaffold(
            title="Not found",
            body=ft.ListView(
                [
                    not_found(
                        NOT_FOUND,
                        icon=ft.Icons.LABEL_OFF_OUTLINED,
                        action="All tracks",
                        location="/more/tracks",
                        identifier=f"{SCREEN}.not_found",
                    )
                ],
                expand=True,
            ),
        )
    items: list[ft.Control] = [intro(track, tokens, spanish=SPANISH in shared)]
    if data is None and conference.problem is None:
        items.append(SkeletonList())  # the first fetch runs (NEW-03)
    elif data is None:
        items.append(
            EmptyState(
                "Can't load the schedule",
                icon=ft.Icons.CLOUD_OFF_OUTLINED,
                body=NO_DATA_BODY[conference.problem or "offline"],
                action="Try again",
                on_action=refresh,
                disabled=conference.refreshing,  # in place, so focus stays (D-182)
                identifier=f"{SCREEN}.no_data",
            )
        )
    elif not days:
        items.append(
            EmptyState(
                "No sessions in this track yet",
                icon=ft.Icons.EVENT_BUSY_OUTLINED,
                # No button: the app refreshes the feed on its own (D-175).
                body="They show here as soon as the schedule lists them.",
                identifier=f"{SCREEN}.empty",
            )
        )
    else:
        items.extend(
            DayGroup(
                day,
                views,
                favorites.ids & {s.id for s in day.sessions},
                on_toggle,
                tokens,
                screen=SCREEN,
                level=2,
                omit=shared,
            )
            for day in days
        )
    actions: list[ft.Control] = []
    if ids and offers_add_all(track):

        @report_errors  # every handler a screen defines has the net (D-163)
        async def add() -> None:
            await add_all(ids)

        actions.append(_menu(add))
    # The heading below names the page, so the app bar's title stays empty (D-186).
    return AppScaffold(title="", body=ft.ListView(items, expand=True), actions=actions)


def offers_add_all(track: Track) -> bool:
    """Return whether the track's page offers "Add all to My schedule" (ux.md §5.10).

    Not on the notices and breaks (the ``logistics`` group), whose rows have no star
    to fill (D-31).

    Args:
        track: The page's track.
    """
    return track.group != NOTICE_GROUP


def _menu(on_add_all: Callable[[], Awaitable[None]]) -> ft.Control:
    """The app bar's overflow ("More options"): "Add all to My schedule" (D-207).

    The item's content is a ``ListTile``, not ``PopupMenuItem.icon``: Flet puts that
    icon and the text in a ``Row`` without ``Expanded``, so at 200 % text the label
    ran off the menu's edge (F46). A tile's title wraps, and the theme's
    ``TITLE_HEIGHT`` keeps the icon beside its first line (D-188). Flutter's item
    takes the tile's padding away; ``min_height`` keeps the menu's 48 dp row, and the
    12 dp gap is the menu's, not a list's 16.
    """
    label = ft.ListTile(
        leading=ft.Icon(ft.Icons.PLAYLIST_ADD),
        title=ft.Text(ADD_ALL),
        horizontal_spacing=12,
        min_height=48,
    )
    menu = ft.PopupMenuButton(
        icon=ft.Icons.MORE_VERT,
        tooltip="More options",
        items=[
            ft.PopupMenuItem(
                content=ft.Semantics(identifier=f"{SCREEN}.add_all", content=label),
                on_click=on_add_all,
            )
        ],
    )
    return named(f"{SCREEN}.menu", menu)


def shared_badges(track: Track, days: Sequence[DaySessions]) -> frozenset[str]:
    """Return the badge labels every row of the page shares, which the intro shows once.

    The track's own badge, and "En Español" when every session is given in Spanish
    (the charlas). A row that repeated them would spend a line, and a screen reader a
    sentence, on what the page already said, as session detail leaves out a badge
    that repeats its title (D-186). "Registration required" stays on its rows.

    Args:
        track: The page's track.
        days: Its sessions by day.
    """
    sessions = [session for day in days for session in day.sessions]
    spanish = bool(sessions) and all(session.spanish for session in sessions)
    return frozenset({track.short, *([SPANISH] if spanish else [])})


def intro(track: Track, tokens: Tokens, *, spanish: bool) -> ft.Control:
    """Return the page's intro: the badges, the track's name and its legend line.

    The name is the page's heading (level 1, F40) in ``HEADLINE_SMALL``, as on session
    detail (D-186), rather than the app bar's title: a long name ("Trailblazing Python
    Security") was cut there at large text, while here it wraps.

    Args:
        track: The track.
        tokens: The scheme's tokens, for the badge's colours (D-150).
        spanish: Whether every session is in Spanish: "En Español" joins the track's
            badge here, and leaves the rows (``shared_badges()``).
    """
    badges = [TrackBadge(track.short, tokens.track_badge(track.key))]
    if spanish:
        badges.append(TrackBadge(SPANISH, tokens.spanish))
    if track.new:
        badges.append(TrackBadge(NEW_TRACK, tokens.new_track))
    title = ft.Semantics(
        header=True,
        heading_level=1,
        identifier=f"{SCREEN}.title",
        content=ft.Text(track.plural, theme_style=ft.TextThemeStyle.HEADLINE_SMALL),
    )
    return ft.Container(
        ft.Column(
            [
                badge_row(badges),
                title,
                ft.Text(
                    track.legend,
                    theme_style=ft.TextThemeStyle.BODY_LARGE,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
            spacing=8,
        ),
        padding=ft.Padding.only(left=16, top=8, right=16),
    )
