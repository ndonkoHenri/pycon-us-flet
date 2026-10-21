"""Lightning talks (``/more/lightning-talks``): what they are, how to sign up, and when.

The Tracks hub opens the same page as its child, ``/more/tracks/lightning-talks``, so
Back returns to the hub (D-207).

One page where Ionic had two near-identical menu entries, a static page and a track
list (EVT-03, SHELL-10). From the top:

- a filled card with the year's copy (``content.toml``'s ``[lightning_talks]``, D-45):
  what a lightning talk is, when and where they happen, and "Sign up for a lightning
  talk", which opens the site's sign-up in the in-app browser (the link rule, INFO-14);
- "Think you can't do one?", a fold that starts collapsed, with the doubts people
  give and their answers (``ui.fold.FoldTile``, the app's one fold, D-191);
- "More about lightning talks", the site's page, in the in-app browser;
- the lightning talks themselves by day, ``SessionRow``s with their stars (D-184), the
  track page's memoised day items (``ui.day_groups``, D-153), without the "Lightning
  talks" badge every row would repeat (D-199).

A year without the copy (2025) shows its sessions alone. Without data the sessions
load and fail as the Schedule's do (ux.md §4.1); the copy, which is bundled, stays.
"""

from collections.abc import Callable
from urllib.parse import urlsplit

import flet as ft

from pycon_us.core.timeline import track_sessions
from pycon_us.favorites import use_favorites
from pycon_us.prefs import use_prefs
from pycon_us.services import Services, use_services
from pycon_us.services.errors import report_errors
from pycon_us.state import use_conference
from pycon_us.theme import use_tokens
from pycon_us.ui.buttons import ICON_PADDING
from pycon_us.ui.day_groups import DayGroup
from pycon_us.ui.favorite import use_favorite_toggle
from pycon_us.ui.fold import FoldTile, expand_style
from pycon_us.ui.links import OPENS_IN, LinkKind, external, open_link
from pycon_us.ui.rows import LinkTile
from pycon_us.ui.scaffold import AppScaffold
from pycon_us.ui.session_rows import changes_of, use_recent_changes, use_session_views
from pycon_us.ui.states import EmptyState, NoDataState
from pycon_us.ui.widths import LIST, sides, use_margin
from pycon_us.year_pages import LightningTalksInfo

SCREEN = "lightning_talks"
"""The screen's name in its semantics identifiers (decisions §M)."""

TRACK = "Lightning-talks"
"""The lightning talks' track key, as feed processing names the feed's kind (DATA-14)."""

TITLE = "Lightning talks"
"""The page's name: its app bar's title and its More row (ux.md §4.9's spelling)."""

SIGN_UP = "Sign up for a lightning talk"
DOUBTS = "Think you can't do one?"


@ft.component
def LightningTalks() -> ft.View:
    """The Lightning talks page: the year's copy, the sign-up, and the talks by day."""
    page = ft.context.page
    svc = use_services()
    margin = use_margin(LIST)  # its width class (D-305)
    conference = use_conference()
    favorites = use_favorites()
    prefs = use_prefs()
    on_toggle = use_favorite_toggle(favorites)
    tokens = use_tokens()
    doubts_open, set_doubts_open = ft.use_state(False)  # collapsed (EVT-03)
    info = svc.year.conference
    copy = svc.year.content.lightning_talks
    data = conference.data
    # Once per feed version (and memoised per feed by the query itself, D-178).
    days = ft.use_memo(
        lambda: track_sessions(data, TRACK) if data else (), [conference.version]
    )
    ids = ft.use_memo(lambda: [s.id for day in days for s in day.sessions], [days])
    all_views = use_session_views(
        conference,
        ids,
        use_24h=bool(page.media and page.media.always_use_24_hour_format),
    )
    views = ft.use_memo(lambda: {v.session.id: v for v in all_views}, [all_views])
    changes = use_recent_changes()
    # The badge every row would repeat; one object, so the day items still skip.
    omit = ft.use_memo(lambda: frozenset({info.track_name(TRACK)}), [])

    @report_errors
    async def refresh() -> None:
        await conference.refresh(svc.storage, svc.year, closed=svc.closed)

    items: list[ft.Control] = []
    if copy is not None:
        items += [
            copy_card(copy, svc),
            doubts_fold(
                copy,
                expanded=doubts_open,
                on_change=set_doubts_open,
                style=expand_style(prefs),
            ),
            LinkTile(
                "More about lightning talks",
                copy.info_url,
                icon=ft.Icons.INFO_OUTLINE,
                subtitle=urlsplit(copy.info_url).hostname,
                identifier=f"{SCREEN}.more_info",
            ),
        ]
    if data is None:
        items.append(
            NoDataState(
                conference.problem,
                on_retry=refresh,
                retrying=conference.status(info) == "refreshing",
                identifier=f"{SCREEN}.no_data",
            )
        )
    elif not days:
        items.append(
            EmptyState(
                "No lightning talks in the schedule yet",
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
                changes_of(changes, (s.id for s in day.sessions)),
                on_toggle,
                tokens,
                screen=SCREEN,
                level=2,
                omit=omit,
            )
            for day in days
        )
    return AppScaffold(
        title=TITLE,
        body=ft.ListView(items, expand=True, padding=sides(margin, bottom=8)),
    )


def copy_card(copy: LightningTalksInfo, svc: Services) -> ft.Control:
    """Return the card that says what a lightning talk is, with the sign-up button.

    A filled card (M3's ``surface_container_highest``), its heading a level-2 heading
    (F40) and its paragraphs in ``BODY_LARGE``, as descriptions are (ux.md §3.6); for
    screen readers the heading, the paragraphs and the button are nodes of their own,
    the heading read first and alone (D-211). The
    button leaves the app, so its icon is ``OPEN_IN_NEW`` and its name ends with
    "Opens in browser", on the text: an icon's label is read before the text (D-186);
    it is a link, as an external row is (``links.external()``).

    Args:
        copy: The year's copy.
        svc: The session's services, for the launcher.
    """

    @report_errors
    async def sign_up() -> None:
        await open_link(svc, copy.signup_url)

    # The heading and the paragraphs each a node of its own, as About's app name and
    # its lines (D-211): in one node, the whole card read as one heading.
    heading = ft.Semantics(
        header=True,
        heading_level=2,
        container=True,
        content=ft.Text(copy.heading, theme_style=ft.TextThemeStyle.TITLE_MEDIUM),
    )
    paragraphs = ft.Semantics(
        container=True,
        content=ft.Column(
            [
                ft.Text(paragraph, theme_style=ft.TextThemeStyle.BODY_LARGE)
                for paragraph in copy.intro
            ],
            spacing=12,
        ),
    )
    button = ft.FilledButton(
        ft.Text(SIGN_UP, semantics_label=f"{SIGN_UP}\n{OPENS_IN[LinkKind.WEB]}"),
        icon=ft.Icons.OPEN_IN_NEW,
        on_click=sign_up,
        style=ft.ButtonStyle(padding=ICON_PADDING),
    )
    return ft.Container(
        ft.Card(
            ft.Container(
                ft.Column(
                    [
                        heading,
                        paragraphs,
                        # Its own row, so it keeps its width and wraps at large text.
                        ft.Container(
                            external(f"{SCREEN}.sign_up", button),
                            padding=ft.Padding.only(top=4),
                        ),
                    ],
                    spacing=12,
                    horizontal_alignment=ft.CrossAxisAlignment.START,
                ),
                padding=16,
            ),
            variant=ft.CardVariant.FILLED,
            margin=0,
            # Not one node: Flutter's Card merges what it holds into its own (D-211).
            semantic_container=False,
        ),
        padding=ft.Padding.only(left=16, top=8, right=16, bottom=8),
    )


def doubts_fold(
    copy: LightningTalksInfo,
    *,
    expanded: bool,
    on_change: Callable[[bool], None],
    style: ft.AnimationStyle,
) -> ft.Control:
    """Return "Think you can't do one?": the doubts and their answers, folded.

    The app's fold (``FoldTile``, D-191), controlled by the page's state, so a
    re-render (a star tap below) never folds it up again. Each doubt reads as one
    node: what people say, then the answer.

    Args:
        copy: The year's copy, with its doubts.
        expanded: Whether it is open; it starts collapsed (EVT-03).
        on_change: Where the page keeps whether it is open.
        style: Its animation (``expand_style()``), none under reduced motion.
    """
    answers: list[ft.Control] = [
        ft.Semantics(
            container=True,  # one stop: the doubt, then its answer
            content=ft.Container(
                ft.Column(
                    [
                        ft.Text(doubt.doubt, theme_style=ft.TextThemeStyle.TITLE_SMALL),
                        ft.Text(
                            doubt.answer,
                            theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                            color=ft.Colors.ON_SURFACE_VARIANT,
                        ),
                    ],
                    spacing=2,
                ),
                padding=ft.Padding.only(left=56, right=16, bottom=12),
            ),
        )
        for doubt in copy.doubts
    ]
    fold = FoldTile(
        ft.Text(DOUBTS),  # a row's title, as the link row under it
        answers,
        expanded=expanded,
        on_change=on_change,
        style=style,
        leading=ft.Icon(ft.Icons.LIGHTBULB_OUTLINE),
    )
    # Around the tile, not on its title, which it split from the tile's button, read
    # "Collapsed" alone on Android; not merged, which would take in the answers. An
    # empty node of its own, the price of an identifier on a fold (F50, D-214).
    return ft.Semantics(identifier=f"{SCREEN}.doubts", content=fold)
