"""Job listings (``/more/jobs``): a card per sponsor's listing, its roles linked (SPON-06).

Ionic showed each listing's HTML under two styles of level badge, linked almost none of
its roles, had no empty, loading or failed state, and its pull-to-refresh deleted the
app's schedule cache, so a refresh offline lost the offline schedule (SPON-08). This
page (ux.md §6.6), under the status strip, holds one outlined card per listing, in feed
order:

- **The header**: the sponsor's logo on a 48 dp white plate (``logo_tile()``, D-262),
  its name and its level as sponsor detail says it, "Visionary sponsor", and a chevron.
  One node, a level-2 heading and a button read "Bloomberg, Visionary sponsor"
  (``jobs.listing.<id>``, D-33, D-211); a tap pushes the sponsor's detail,
  ``/more/jobs/sponsor/<slug>`` (D-17). A listing whose sponsor is not in the feed's
  levels has no link and no chevron.
- **Its roles** (``core/jobs.py``, D-278): the first five as ``LinkTile``s with
  ``WORK_OUTLINE`` that open the in-app browser (``jobs.role.<id>.<n>``), then "Show
  all 15 roles", which shows the rest in place and becomes "Show fewer roles".
- **A long-form listing** (SerpApi, marimo) instead shows its text cut at four lines
  with "More", which shows the whole Markdown and its links, as a sprint card does
  (``core.sprints.needs_more()``, D-202). A placeholder (OpenEDG's "N/A") says "No
  roles listed".

The refresh is the ``Conference`` store's (D-145): the status strip's, then a
``RefreshIndicator`` once U1 (#20) is pinned; it never deletes the cache, so a failed
one keeps the listings and the schedule. Without data the page loads and fails as the
Sponsors list does (ux.md §4.1); a feed without listings says "No job listings yet"
(2025). Each card is a memoised component keyed by its listing id (D-153). The job
fair card at the top comes with #408, the filter with #400.
"""

import flet as ft

from pycon_us.core.html_md import to_text
from pycon_us.core.jobs import sponsor_of
from pycon_us.core.models import JobListing
from pycon_us.core.sprints import needs_more
from pycon_us.locations import drill_href
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.state import use_conference
from pycon_us.ui.links import feed_markdown
from pycon_us.ui.logos import logo_tile
from pycon_us.ui.rows import LinkTile
from pycon_us.ui.scaffold import AppScaffold
from pycon_us.ui.semantics import named
from pycon_us.ui.states import EmptyState, NoDataState
from pycon_us.ui.status_strip import StatusStrip
from pycon_us.ui.widths import LIST, sides, use_margin

SCREEN = "jobs"
"""The page's name in its semantics identifiers (decisions §M)."""

TITLE = "Job listings"
"""The page's name: its app bar's title and its More row."""

SHOWN_ROLES = 5
"""How many roles a card shows before "Show all N roles" (SPON-06)."""

PLATE = 48
"""The header's logo plate, in dp: square, as a Sponsors row's."""

NO_ROLES = "No roles listed"
"""What a placeholder listing's card says under its header."""


@ft.component
def Jobs() -> ft.View:
    """The Job listings page: the strip, then a card per listing in feed order."""
    svc = use_services()
    margin = use_margin(LIST)  # its width class (D-305)
    conference = use_conference()
    data = conference.data

    @report_errors
    async def refresh() -> None:
        await conference.refresh(svc.storage, svc.year, closed=svc.closed)

    items: list[ft.Control] = [StatusStrip()]
    if data is None:
        items.append(
            NoDataState(
                conference.problem,
                on_retry=refresh,
                retrying=conference.status(svc.year.conference) == "refreshing",
                identifier=f"{SCREEN}.no_data",
            )
        )
    elif not data.job_listings:
        items.append(
            EmptyState(
                "No job listings yet",
                icon=ft.Icons.WORK_OUTLINE,
                # No button: the app refreshes the feed on its own (D-175).
                body="Sponsors' open roles show here as soon as the conference "
                "lists them.",
                identifier=f"{SCREEN}.empty",
            )
        )
    else:
        for listing in data.job_listings:
            sponsor = sponsor_of(data, listing)
            items.append(ListingCard(listing, sponsor.slug if sponsor else None))
    return AppScaffold(
        title=TITLE,
        body=ft.ListView(items, expand=True, padding=sides(margin, bottom=24)),
    )


def ListingCard(listing: JobListing, slug: str | None) -> ft.Control:
    """Return one listing's card, a memoised component keyed by its id.

    Given the same listing and slug it skips its body (D-153, F34), so a refresh that
    keeps the feed re-renders no card. Its "Show all" and "More" states are its own.

    Args:
        listing: The listing, the same object for one feed version.
        slug: Its sponsor's slug, which the header links to; None for no sponsor.
    """
    # As SessionRow's: ft.component's typing leaves out the key= its wrapper takes.
    return _ListingCard(listing, slug, key=listing.id)  # pyright: ignore[reportCallIssue]


@ft.memo
@ft.component
def _ListingCard(listing: JobListing, slug: str | None) -> ft.Control:
    """The body of ``ListingCard``; it runs when its listing or a toggle changes."""
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

    controls: list[ft.Control] = [header(listing, go if slug is not None else None)]
    key = listing.id
    if listing.roles:
        shown = listing.roles if expanded else listing.roles[:SHOWN_ROLES]
        controls.extend(
            LinkTile(
                role.title,
                role.url,
                icon=ft.Icons.WORK_OUTLINE,
                identifier=f"{SCREEN}.role.{key}.{index}",
            )
            for index, role in enumerate(shown)
        )
        if len(listing.roles) > SHOWN_ROLES:
            word = "Show fewer roles" if expanded else roles_label(len(listing.roles))
            controls.append(toggle_button(word, expanded, toggle, f"all_roles.{key}"))
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
            controls.append(toggle_button(word, expanded, toggle, f"more.{key}", label))
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


def header(listing: JobListing, on_click: ft.ControlEventHandler | None) -> ft.Control:
    """Return a card's header: the logo, the name and level, and a chevron to detail.

    One node, a level-2 heading so a screen reader goes card by card (D-211), and a
    button when it links to the sponsor; its phrase replaces the texts', and the
    plate says nothing (``logo_tile()``).

    Args:
        listing: The listing, which carries its sponsor's name, logo and level.
        on_click: Pushes the sponsor's detail; None when the feed has no such sponsor.
    """
    level = f"{listing.sponsor_level} sponsor"
    row: list[ft.Control] = [
        logo_tile(listing.sponsor_name, listing.sponsor_logo_url, size=PLATE),
        ft.Column(
            [
                ft.Text(
                    listing.sponsor_name, theme_style=ft.TextThemeStyle.TITLE_MEDIUM
                ),
                ft.Text(
                    level,
                    theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
            spacing=2,
            expand=True,
        ),
    ]
    if on_click is not None:
        row.append(ft.Icon(ft.Icons.CHEVRON_RIGHT))
    return ft.MergeSemantics(  # the phrase and the tap's action: one node
        content=ft.Container(
            ft.Semantics(
                label=f"{listing.sponsor_name}, {level}",
                identifier=f"{SCREEN}.listing.{listing.id}",
                header=True,
                heading_level=2,
                button=on_click is not None,
                exclude_semantics=True,
                content=ft.Row(
                    row, spacing=16, vertical_alignment=ft.CrossAxisAlignment.CENTER
                ),
            ),
            ink=on_click is not None,
            on_click=on_click,
            padding=16,
        )
    )


def toggle_button(
    word: str,
    expanded: bool,
    on_click: ft.ControlEventHandler,
    key: str,
    label: str | None = None,
) -> ft.Control:
    """Return a card's text button that shows more of it, or less, in place.

    Said "collapsed" or "expanded"; the visible words come first in its label, so
    "tap More" works for voice control users (WCAG 2.5.3).

    Args:
        word: Its visible words.
        expanded: Whether the card shows it all.
        on_click: Toggles the card.
        key: Its identifier after ``jobs.``.
        label: What a screen reader says, if more than the words.
    """
    button = ft.TextButton(
        content=ft.Text(word, semantics_label=label), on_click=on_click
    )
    return ft.Container(
        named(f"{SCREEN}.{key}", ft.Semantics(expanded=expanded, content=button)),
        # A text button's label sits 12 dp in: 4 + 12 lines it up with the text.
        padding=ft.Padding.only(left=4, top=4, right=4, bottom=4),
        alignment=ft.Alignment.CENTER_LEFT,
    )
