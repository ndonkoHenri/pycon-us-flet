"""Session detail (``…/session/<id>``): time and place first (SESS-01..03; ux.md §5.5).

The app bar holds the star (D-30) and, when the session has a public page, an overflow
with "Open on us.pycon.org": Add to calendar joins it in P2, so no dead item waits
there, and a session without a page has no overflow at all (D-60). The page's heading
is the title under the badges, so the app bar's title stays empty. Then the "When and
where" card (``ui.when_where``), and for a session that needs registration a card that
says so and links the year's registration page.

An unknown id shows the not-found state under the back arrow, so Back pops one level
(D-186). A session that a newer feed drops while its detail is open keeps the content
it last showed, under a "Removed from the latest schedule" note (ux.md §4.1).

Still to come, in ux.md §5.5's order: the speakers' rows and the description (#91;
until then the speakers are plain links), then Share in the app bar and the posters
list (#92).
"""

from collections.abc import Mapping
from typing import cast
from urllib.parse import urlsplit

import flet as ft

from pycon_us.config import ConferenceInfo
from pycon_us.core.models import Session, Speaker
from pycon_us.core.row_views import places
from pycon_us.favorites import use_favorites
from pycon_us.locations import drill_href
from pycon_us.screens.stub import nav_tile, not_found
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.state import use_conference
from pycon_us.theme import Tokens, use_tokens
from pycon_us.ui.badges import (
    FavoriteButton,
    TrackBadge,
    badge_row,
    badge_specs,
    use_favorite_toggle,
)
from pycon_us.ui.links import OPENS_IN, LinkKind, open_link
from pycon_us.ui.rows import LinkTile
from pycon_us.ui.scaffold import AppScaffold, SectionHeader
from pycon_us.ui.session_rows import is_notice
from pycon_us.ui.when_where import WhenAndWhere

SCREEN = "session"
"""The screen's name in its semantics identifiers (decisions §M)."""

NOT_FOUND = "This session isn't in the current schedule"
"""The empty state of an unknown id (ux.md §4.6)."""

REMOVED = "Removed from the latest schedule"
"""The note over a session a newer feed dropped (D-47's words, never "cancelled")."""

SECTION_GAP = 24
"""The space between the page's sections (ux.md §3.6); 8 dp within one."""

REGISTRATION_TITLE = "Register separately"
"""The registration card's title: what to do, as the badge above already says why."""

REGISTRATION_TEXT = "Your conference ticket doesn't sign you up for this session."
"""What the registration card says under its title (DATA-09): true of a paid
tutorial and of a summit with a free sign-up alike."""


@ft.component
def SessionDetail(session_id: str) -> ft.View:
    """One session: its header, when and where it is, and its registration.

    Args:
        session_id: The session id, unquoted (D-42).
    """
    page = ft.context.page
    view_path = ft.use_view_path()
    conference = use_conference()
    favorites = use_favorites()
    on_toggle = use_favorite_toggle(favorites)
    svc = use_services()
    tokens = use_tokens()
    # The session as this View last showed it: a refresh that drops it keeps it here.
    shown = ft.use_ref(cast(Session | None, None))
    info = svc.year.conference
    data = conference.data
    current = data.sessions.get(session_id) if data else None
    if current is not None:
        shown.current = current
    elif shown.current is not None and shown.current.id != session_id:
        # The same View given another id in place (a deep link at the same depth):
        # what it showed before belongs to a different session.
        shown.current = None
    session = shown.current
    if session is None:
        return AppScaffold(
            title="Not found",
            body=ft.ListView(
                [
                    not_found(
                        NOT_FOUND,
                        icon=ft.Icons.EVENT_BUSY_OUTLINED,
                        action="Open schedule",
                        location="/schedule",
                        identifier=f"{SCREEN}.not_found",
                    )
                ],
                expand=True,
            ),
        )

    @report_errors
    async def star() -> None:
        await on_toggle(session.id)

    @report_errors
    async def open_site() -> None:
        await open_link(svc, session.url)

    # Share (#92) goes between the star and the overflow (ux.md §5.5).
    actions: list[ft.Control] = []
    if not is_notice(session, info):  # breaks and notices have no star (D-31)
        actions.append(
            FavoriteButton(
                session.id in favorites.ids,
                star,
                color=tokens.favorite,
                identifier=f"{SCREEN}.favorite",
            )
        )
    if session.url:
        actions.append(_overflow(session.url, open_site))
    controls: list[ft.Control] = []
    if current is None:  # a newer feed dropped it while it was open
        controls.append(_removed_note())
    controls.append(_header(session, info, tokens))
    controls.append(
        WhenAndWhere(
            session,
            places(session, data.rooms if data else {}),
            info,
            view_path=view_path,
            use_24h=bool(page.media and page.media.always_use_24_hour_format),
            screen=SCREEN,
        )
    )
    if session.pre_registered:
        controls.append(_registration(info.registration_url))
    speakers = _speaker_links(session, data.speakers if data else {}, view_path)
    if speakers:  # one block: the list's spacing goes between sections only
        controls.append(ft.Column(speakers, spacing=0))
    # The description (#91) and the posters (#92) follow here.
    body = ft.ListView(
        controls,
        expand=True,
        spacing=SECTION_GAP,
        padding=ft.Padding.only(top=8, bottom=24),
    )
    return AppScaffold(title="", body=body, actions=actions)


def _overflow(url: str, on_open: ft.ControlEventHandler) -> ft.Control:
    """The app bar's overflow: "Open on us.pycon.org", the host named from the URL."""
    label = f"Open on {urlsplit(url).hostname}"
    menu = ft.PopupMenuButton(
        icon=ft.Icons.MORE_VERT,
        tooltip="More options",
        items=[
            ft.PopupMenuItem(
                # It leaves the app: a link, read "Opens in browser" after its text
                # (ux.md §4.7). Said by the text, not the icon, which comes first and
                # was read first ("Opens in browser, Open on us.pycon.org").
                content=ft.Semantics(
                    link=True,
                    content=ft.Text(
                        label, semantics_label=f"{label}\n{OPENS_IN[LinkKind.WEB]}"
                    ),
                ),
                icon=ft.Icons.OPEN_IN_NEW,
                on_click=on_open,
            )
        ],
    )
    return ft.Semantics(identifier=f"{SCREEN}.overflow", content=menu)


def _header(session: Session, info: ConferenceInfo, tokens: Tokens) -> ft.Control:
    """The badges, then the title: the page's heading, selectable to copy (D-26)."""
    title = ft.Semantics(
        header=True,
        heading_level=1,
        identifier=f"{SCREEN}.title",
        content=ft.Text(
            session.name, theme_style=ft.TextThemeStyle.HEADLINE_SMALL, selectable=True
        ),
    )
    # A badge that repeats the title (a break's "Break") says nothing more.
    badges = [
        TrackBadge(label, colors)
        for label, colors in badge_specs(session, info, tokens)
        if label.casefold() != session.name.casefold()
    ]
    column: list[ft.Control] = [badge_row(badges), title] if badges else [title]
    return ft.Container(
        ft.Column(column, spacing=8), padding=ft.Padding.symmetric(horizontal=16)
    )


def _registration(url: str) -> ft.Control:
    """The registration guidance of a tutorial or summit (DATA-09, SESS-01)."""
    text = ft.Row(
        [
            ft.Icon(ft.Icons.INFO_OUTLINE, color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Column(
                [
                    ft.Text(
                        REGISTRATION_TITLE, theme_style=ft.TextThemeStyle.TITLE_SMALL
                    ),
                    ft.Text(
                        REGISTRATION_TEXT,
                        theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ],
                spacing=4,
                expand=True,
            ),
        ],
        spacing=16,
        vertical_alignment=ft.CrossAxisAlignment.START,
    )
    rows: list[ft.Control] = [
        ft.Semantics(
            container=True,
            identifier=f"{SCREEN}.registration",
            content=ft.Container(
                text,
                padding=ft.Padding.only(
                    left=16, top=16, right=16, bottom=8 if url else 16
                ),
            ),
        )
    ]
    if url:  # the year's registration page (conference.toml), in the browser view
        rows.append(
            LinkTile(
                "Check your registration",
                url,
                # An icon of its own, so its title lines up with the text above.
                icon=ft.Icons.HOW_TO_REG_OUTLINED,
                identifier=f"{SCREEN}.registration.link",
            )
        )
    return ft.Card(
        variant=ft.CardVariant.FILLED,
        margin=ft.Margin.symmetric(horizontal=16),
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        content=ft.Column(rows, spacing=0),
    )


def _speaker_links(
    session: Session, speakers: Mapping[str, Speaker], view_path: str
) -> list[ft.Control]:
    """The speakers as links, one drill level each, until #91's rows (SPKR-01)."""
    found = [sid for sid in session.speaker_ids if sid in speakers]
    if not found:
        return []
    links = [
        nav_tile(speakers[sid].name, drill_href(view_path, "speaker", sid))
        for sid in found
    ]
    # The list's gap already stands above it, so the header adds none of its own.
    return [SectionHeader("Speakers", level=2, top=0), *links]


def _removed_note() -> ft.Control:
    """The inline note over a session a newer feed dropped (ux.md §4.1)."""
    on_container = ft.Colors.ON_TERTIARY_CONTAINER
    return ft.Semantics(
        identifier=f"{SCREEN}.removed",
        container=True,
        live_region=True,  # it appears after a refresh, while the page is open
        content=ft.Container(
            ft.Row(
                [
                    ft.Icon(ft.Icons.EVENT_BUSY_OUTLINED, color=on_container),
                    ft.Column(
                        [
                            ft.Text(
                                REMOVED,
                                theme_style=ft.TextThemeStyle.TITLE_SMALL,
                                color=on_container,
                            ),
                            ft.Text(
                                "This is how it was before the update.",
                                theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                                color=on_container,
                            ),
                        ],
                        spacing=4,
                        expand=True,
                    ),
                ],
                spacing=16,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            bgcolor=ft.Colors.TERTIARY_CONTAINER,
            border_radius=12,
            padding=16,
            margin=ft.Margin.symmetric(horizontal=16),
        ),
    )
