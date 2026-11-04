"""Keynotes (`/more/keynotes`): the conference's keynotes and panels, a card each.

The Tracks hub opens the same page as its child, `/more/tracks/keynotes`, so Back
returns to the hub (D-207); More keeps its own entry.

One card per session, in the order they happen (SPKR-04, ux.md §5.11): each keynote of
the feed, and each panel the year data names, with the people and words from
`content.toml` (D-217) and a time-and-room tile with the star
(`screens.keynote_card`). The feed has no keynote speaker in its directory, so these
cards are where the app says who is on stage. Without data the sessions load and fail
as the Schedule's do (ux.md §4.1).
"""

import flet as ft

from pycon_us.core.timeline import keynote_sessions
from pycon_us.favorites import use_favorites
from pycon_us.screens.keynote_card import SCREEN, KeynoteCard
from pycon_us.services import use_services
from pycon_us.state import use_conference
from pycon_us.theme import use_tokens
from pycon_us.ui.favorite import use_favorite_toggle
from pycon_us.ui.scaffold import AppScaffold
from pycon_us.ui.session_rows import use_session_views
from pycon_us.ui.states import EmptyState, NoDataState
from pycon_us.ui.widths import LIST, sides, use_margin
from pycon_us.year_keynotes import keynote_of

TRACK = "Keynote"
"""The keynotes' track key, as feed processing names the feed's kind (DATA-14); the
hub's Keynotes row is this track's (`year_tracks.HUB_PAGES`)."""

TITLE = "Keynotes"
"""The page's name: its app bar's title and its More row."""


@ft.component
def Keynotes() -> ft.View:
    """The Keynotes page: a card per keynote and panel, in the order they happen."""
    page = ft.context.page
    svc = use_services()
    margin = use_margin(LIST)  # its width class (D-305)
    conference = use_conference()
    favorites = use_favorites()
    on_toggle = use_favorite_toggle(favorites)
    tokens = use_tokens()
    keynotes = svc.year.content.keynotes
    data = conference.data
    # Once per feed version (and memoised per feed by the query itself, D-178).
    sessions = ft.use_memo(
        lambda: (
            keynote_sessions(data, TRACK, [k.session_id for k in keynotes])
            if data
            else ()
        ),
        [conference.version],
    )
    ids = ft.use_memo(lambda: [s.id for s in sessions], [sessions])
    views = use_session_views(
        conference,
        ids,
        use_24h=bool(page.media and page.media.always_use_24_hour_format),
    )

    items: list[ft.Control]
    if data is None:
        items = [NoDataState(conference, svc, f"{SCREEN}.no_data")]
    elif not views:
        items = [
            EmptyState(
                "No keynotes announced yet",
                icon=ft.Icons.CO_PRESENT_OUTLINED,
                # No button: the app refreshes the feed on its own (D-175).
                body="They show here as soon as the schedule lists them.",
                identifier=f"{SCREEN}.empty",
            )
        ]
    else:
        items = [
            KeynoteCard(
                view.session,
                keynote_of(keynotes, view.session.id),
                view,
                saved=view.session.id in favorites.ids,
                on_toggle=on_toggle,
                star_color=tokens.favorite,
                key=view.session.id,  # pyright: ignore[reportCallIssue]  # as SessionRow's
            )
            for view in views
        ]
    return AppScaffold(
        title=TITLE,
        source=__name__,
        body=ft.ListView(items, expand=True, padding=sides(margin, top=8, bottom=16)),
    )
