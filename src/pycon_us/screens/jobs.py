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
(2025), and has no filter. Each card is a memoised component keyed by its listing id
(D-153), so a keystroke re-renders no card that stays. Above the cards, the job fair
plan's card (``job_fair_card()``, SPON-10, D-254) pushes the floor viewer at
``/more/jobs/plan/job-fair``: the tables where the listings' sponsors meet people.

**The filter** (SPON-07): the pinned ``SearchField`` "Filter jobs" the Speakers and
Sprints lists use (D-189), under the strip, keeps the listings whose text holds every
word, in the sponsor's name, the role titles or the visible text, never the markup
(``core.jobs.filter_listings()``, D-46), where Ionic's matched raw HTML: ``nofollow``
found Bloomberg. The field follows every keystroke (D-243), and the list follows once
the typing pauses for 250 ms, as search does; a Clear empties both at once. The live
count line says "3 listings" (D-226); a miss says "No roles match “rust”" with Clear
filter, which puts the focus back in the field (D-182). The page stays mounted under a
sponsor's detail, so Back finds the filter as it was. At large text (``Prefs.time_above``,
D-216) the strip, the field and the count head the list and scroll away with it, as the
Schedule's head does (D-345): pinned, they took half the screen at the largest sizes
(#649).
"""

import asyncio

import flet as ft

from pycon_us.core.html_md import to_text
from pycon_us.core.jobs import filter_listings, sponsor_of
from pycon_us.core.models import JobListing
from pycon_us.core.sprints import needs_more
from pycon_us.locations import drill_href
from pycon_us.prefs import use_prefs
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.state import use_conference
from pycon_us.theme import use_tokens
from pycon_us.ui.fields import SearchField, found_count, use_field_query
from pycon_us.ui.fold import toggle_button
from pycon_us.ui.links import feed_markdown
from pycon_us.ui.location_card import job_fair_card
from pycon_us.ui.logos import logo_tile
from pycon_us.ui.rows import LinkTile
from pycon_us.ui.scaffold import AppScaffold
from pycon_us.ui.states import EmptyState, NoDataState
from pycon_us.ui.status_strip import StatusStrip
from pycon_us.ui.widths import LIST, capped, sides, use_margin

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

FILTER_HINT = "Filter jobs"
"""The filter field's hint, and its name for screen readers, which stays with text in it."""

CLEAR_FILTER = "Clear filter"
"""The label of the two controls that empty the filter: the field's and the no-match state's."""

DEBOUNCE_SECONDS = 0.25
"""How long the typing pauses before the list follows the field (SPON-07)."""


@ft.component
def Jobs() -> ft.View:
    """The Job listings page: the strip and the filter, then a card per listing."""
    svc = use_services()
    prefs = use_prefs()
    margin = use_margin(LIST)  # its width class (D-305)
    conference = use_conference()
    tokens = use_tokens()
    field = use_field_query()
    query, set_query = ft.use_state("")  # the field's text once the typing pauses
    data = conference.data
    text = field.value

    @report_errors
    async def settle() -> None:
        # Restarted by every keystroke: Flet cancels the wait in progress (F2).
        await asyncio.sleep(DEBOUNCE_SECONDS)
        set_query(text)

    ft.use_effect(settle, [text])

    @report_errors
    async def clear() -> None:
        set_query("")  # at once, not after the pause
        await field.clear()  # the Clear went: the focus goes back to the field

    @report_errors
    async def refresh() -> None:
        await conference.refresh(svc.storage, svc.year, closed=svc.closed)

    pinned: list[ft.Control] = [StatusStrip()]
    items: list[ft.Control] = []
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
        found = filter_listings(data.job_listings, query)
        pinned.append(
            SearchField(
                value=text,
                on_change=field.changed,
                on_clear=clear,
                ref=field.ref,
                focusable=field.focusable,
                hint=FILTER_HINT,
                label=FILTER_HINT,
                clear_tooltip=CLEAR_FILTER,
                identifier=f"{SCREEN}.filter",
                high_contrast=tokens.high_contrast,
            )
        )
        if found and found is not data.job_listings:  # a filter applies, finds some
            pinned.append(
                found_count(count_line(len(found)), identifier=f"{SCREEN}.count")
            )
        # The plan heads the list whatever the filter keeps: it is where they all are.
        plan = job_fair_card(svc.year.map, identifier=f"{SCREEN}.job_fair.location")
        if plan is not None:
            items.append(
                ft.Container(
                    plan, padding=ft.Padding.only(left=16, right=16, top=8, bottom=6)
                )
            )
        for listing in found:
            sponsor = sponsor_of(data, listing)
            items.append(ListingCard(listing, sponsor.slug if sponsor else None))
        if not found:
            items.append(
                EmptyState(
                    f"No roles match \N{LEFT DOUBLE QUOTATION MARK}{query.strip()}"
                    "\N{RIGHT DOUBLE QUOTATION MARK}",
                    icon=ft.Icons.SEARCH_OFF,
                    action=CLEAR_FILTER,
                    on_action=clear,  # the focus goes back to the field (D-182)
                    identifier=f"{SCREEN}.no_match",
                )
            )
    # The strip, the field and its count in a column of their own, so the list keeps
    # its place in the body, and the field its place in the column, as the strip and
    # the count come and go (D-153).
    head = ft.Column(
        pinned, spacing=0, horizontal_alignment=ft.CrossAxisAlignment.STRETCH
    )
    if prefs.time_above:
        items.insert(0, head)  # at large text it scrolls away with the list (#649)
        head = ft.Column([])  # an empty column keeps the list's place in the body
    return AppScaffold(
        title=TITLE,
        body=ft.Column(
            [
                capped(head, margin),  # between the list's margins (D-305)
                ft.ListView(items, expand=True, padding=sides(margin, bottom=24)),
            ],
            spacing=0,
            expand=True,
            # The field takes the screen's width; a Column would size it to its own.
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        ),
    )


def count_line(count: int) -> str:
    """Return the filter's count line: "1 listing", "3 listings"."""
    return f"{count} listing" + ("" if count == 1 else "s")


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
