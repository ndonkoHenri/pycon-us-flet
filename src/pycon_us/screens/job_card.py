"""One Job listings card: its header, its roles or text, cut with "Show all" or "More".

`screens/jobs.py` lays the cards out. A header pushes the sponsor's detail, and each role
is a `LinkTile`. At large text (`Prefs.time_above`) a header's words go under its logo and
a role's title takes the row's width (`LinkTile`'s `stacked`), so a long word stays
whole (D-497).
"""

import flet as ft

from pycon_us.core.html_md import to_text
from pycon_us.core.models import JobListing
from pycon_us.core.sprints import needs_more
from pycon_us.locations import drill_href
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.ui.fold import toggle_button
from pycon_us.ui.link_tile import LinkTile
from pycon_us.ui.links import feed_markdown
from pycon_us.ui.logos import logo_tile

SCREEN = "jobs"
"""The page's name in the cards' semantics identifiers (decisions §M)."""

SHOWN_ROLES = 5
"""How many roles a card shows before "Show all N roles" (SPON-06)."""

PLATE = 48
"""The header's logo plate, in dp: square, as a Sponsors row's."""

NO_ROLES = "No roles listed"
"""What a placeholder listing's card says under its header."""


def ListingCard(
    listing: JobListing, slug: str | None, *, large_text: bool = False
) -> ft.Control:
    """Return one listing's card, a memoised component keyed by its id.

    Given the same listing and slug it skips its body (D-153, F34), so a refresh that
    keeps the feed re-renders no card. Its "Show all" and "More" states are its own.

    Args:
        listing: The listing, the same object for one feed version.
        slug: Its sponsor's slug, which the header links to; None for no sponsor.
        large_text: The text is large for the width (`Prefs.time_above`): the header's
            words go under its logo and a role's title takes the row's width, so words
            stay whole (D-497).
    """
    # As SessionRow's: ft.component's typing leaves out the key= its wrapper takes.
    return _ListingCard(listing, slug, large_text, key=listing.id)  # pyright: ignore[reportCallIssue]


@ft.memo
@ft.component
def _ListingCard(listing: JobListing, slug: str | None, large_text: bool) -> ft.Control:
    """The body of `ListingCard`; it runs when its listing or a toggle changes."""
    svc = use_services()
    view_path = ft.use_view_path()
    page = ft.context.page
    expanded, set_expanded = ft.use_state(False)

    @report_errors
    def toggle() -> None:
        set_expanded(not expanded)

    @report_errors
    def go() -> None:
        if slug is not None:
            page.navigate(drill_href(view_path, "sponsor", slug))

    controls: list[ft.Control] = [
        header(listing, go if slug is not None else None, large_text=large_text)
    ]
    key = listing.id
    if listing.roles:
        shown = listing.roles if expanded else listing.roles[:SHOWN_ROLES]
        controls.extend(
            LinkTile(
                role.title,
                role.url,
                icon=ft.Icons.WORK_OUTLINE,
                identifier=f"{SCREEN}.role.{key}.{index}",
                stacked=large_text,
            )
            for index, role in enumerate(shown)
        )
        if len(listing.roles) > SHOWN_ROLES:
            word = "Show fewer roles" if expanded else roles_label(len(listing.roles))
            controls.append(
                toggle_button(word, expanded, toggle, f"{SCREEN}.all_roles.{key}")
            )
    elif listing.description_md:
        text = to_text(listing.description)
        long = needs_more(text, listing.description_md)
        if expanded:
            body = feed_markdown(listing.description_md, svc, inset=0)
        else:
            body = ft.Text(
                text,
                theme_style=ft.TextThemeStyle.BODY_LARGE,  # as the Markdown sets it
                style=ft.TextStyle(height=1.5),
                max_lines=4 if long else None,
                # Not ELLIPSIS uncut: Flutter would drop all but a first long line.
                overflow=ft.TextOverflow.ELLIPSIS if long else ft.TextOverflow.CLIP,
            )
        controls.append(ft.Container(body, padding=ft.Padding.symmetric(horizontal=16)))
        if long:
            word = "Less" if expanded else "More"
            label = f"{word} about {listing.sponsor_name}'s listing"
            controls.append(
                toggle_button(word, expanded, toggle, f"{SCREEN}.more.{key}", label)
            )
    else:
        controls.append(
            ft.Container(
                ft.Text(NO_ROLES, color=ft.Colors.ON_SURFACE_VARIANT),
                padding=ft.Padding.only(left=16, right=16, bottom=16),
            )
        )
    return ft.Card(
        ft.Column(
            controls, spacing=0, horizontal_alignment=ft.CrossAxisAlignment.STRETCH
        ),
        variant=ft.CardVariant.OUTLINED,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,  # the header's ink stays inside
        # Not one node: the header, each role and each button are stops of their own.
        semantic_container=False,
        margin=ft.Margin.symmetric(horizontal=16, vertical=6),
    )


def roles_label(count: int) -> str:
    """Return the button that shows a card's hidden roles: "Show all 15 roles"."""
    return f"Show all {count} roles"


def header(
    listing: JobListing,
    on_click: ft.ControlEventHandler | None,
    *,
    large_text: bool = False,
) -> ft.Control:
    """Return a card's header: the logo, the name and level, and a chevron to detail.

    One node, a level-2 heading so a screen reader goes card by card (D-211), and a
    button when it links to the sponsor; its phrase replaces the texts', and the
    plate says nothing (`logo_tile()`).

    Args:
        listing: The listing, which carries its sponsor's name, logo and level.
        on_click: Pushes the sponsor's detail; None when the feed has no such sponsor.
        large_text: The text is large for the width (`Prefs.time_above`): the words
            go under the logo and the chevron, as the spotlight's do (#649, D-497).
    """
    level = f"{listing.sponsor_level} sponsor"
    tile = logo_tile(listing.sponsor_name, listing.sponsor_logo_url, size=PLATE)
    chevron = [ft.Icon(ft.Icons.CHEVRON_RIGHT)] if on_click is not None else []
    words = ft.Column(
        [
            ft.Text(listing.sponsor_name, theme_style=ft.TextThemeStyle.TITLE_MEDIUM),
            ft.Text(
                level,
                theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
        ],
        spacing=2,
        expand=not large_text,
        tight=large_text,
    )
    content: ft.Control = (
        ft.Column(
            [
                ft.Row(
                    [tile, *chevron],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                words,
            ],
            spacing=12,
            tight=True,
        )
        if large_text
        else ft.Row(
            [tile, words, *chevron],
            spacing=16,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
    )
    return ft.MergeSemantics(  # the phrase and the tap's action: one node
        content=ft.Container(
            ft.Semantics(
                label=f"{listing.sponsor_name}, {level}",
                identifier=f"{SCREEN}.listing.{listing.id}",
                header=True,
                heading_level=2,
                button=on_click is not None,
                exclude_semantics=True,
                content=content,
            ),
            ink=on_click is not None,
            on_click=on_click,
            padding=16,
        )
    )
