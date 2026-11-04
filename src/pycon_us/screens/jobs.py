"""Job listings (`/more/jobs`): a card per sponsor's listing, its roles linked (SPON-06).

The page (ux.md §6.6) is one outlined card per listing, in feed order, under the status
strip: a header that pushes the sponsor's detail, then the listing's roles as `LinkTile`s
or, for a long-form listing, its text cut with "More". Above the cards sit the job fair
plan's card (`job_fair_card()`, D-254) and, once the conference is over, a line saying
the roles may have closed (D-482).

- **Data:** the listings are the feed's snapshot, which the app never edits or checks
  (D-135). `core/jobs.py` reads them (D-278); `core.jobs.filter_listings()` keeps those
  whose sponsor name, role titles or visible text hold every word (SPON-07, D-46).
- **Refresh:** the `Conference` store's (D-145): the status strip's Refresh or a pull
  on the list (D-449); it never deletes the cache, so a failed one keeps the schedule
  (SPON-08). Without data the page loads and fails as the Sponsors list does.
- **Rendering:** each card is a memoised component keyed by its listing id (D-153). The
  filter's field follows every keystroke and the list follows when the typing pauses
  (D-243); at large text the strip, the field and the count scroll with the list (D-216,
  D-345).
"""

import asyncio
from datetime import date

import flet as ft

from pycon_us import clock
from pycon_us.config import ConferenceInfo
from pycon_us.core.html_md import to_text
from pycon_us.core.jobs import filter_listings, sponsor_of
from pycon_us.core.models import JobListing
from pycon_us.core.sprints import needs_more
from pycon_us.core.timefmt import today
from pycon_us.locations import drill_href
from pycon_us.prefs import use_prefs
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.state import use_conference
from pycon_us.theme import use_tokens
from pycon_us.ui.fields import SearchField, found_count, use_field_query
from pycon_us.ui.fold import toggle_button
from pycon_us.ui.link_tile import LinkTile
from pycon_us.ui.links import feed_markdown
from pycon_us.ui.location_card import job_fair_card
from pycon_us.ui.logos import logo_tile
from pycon_us.ui.scaffold import AppScaffold
from pycon_us.ui.scrolling import pullable
from pycon_us.ui.states import EmptyState, NoDataState
from pycon_us.ui.status_strip import StatusStrip, use_refresh
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
    refresh = use_refresh()
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

    pinned: list[ft.Control] = [StatusStrip()]
    items: list[ft.Control] = []
    if data is None:
        items.append(NoDataState(conference, svc, f"{SCREEN}.no_data"))
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
        info = svc.year.conference
        closed = closed_line(info, today(clock.now(), info.zone))
        if closed is not None:
            items.append(closed_note(closed))
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
        source=__name__,
        body=ft.Column(
            [
                capped(head, margin),  # between the list's margins (D-305)
                # A pull runs the strip's refresh (SPON-08, D-449).
                pullable(
                    ft.ListView(items, expand=True, padding=sides(margin, bottom=24)),
                    refresh,
                ),
            ],
            spacing=0,
            expand=True,
            # The field takes the screen's width; a Column would size it to its own.
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        ),
    )


def closed_line(info: ConferenceInfo, day: date) -> str | None:
    """Return the line over the listings once the conference is over, else None.

    The roles' links come from a snapshot of the feed that nobody re-checks, so after
    the last day (`info.last_day`, the sprints') the page says that some may have
    closed (#869, D-482).

    Args:
        info: The year's facts: its name and its last day.
        day: Today in the conference's zone (`timefmt.today()`).
    """
    if day <= info.last_day:
        return None
    return f"These roles were listed for {info.name}, and some have closed."


def closed_note(line: str) -> ft.Control:
    """Return the closed line as the list's first row, a muted paragraph (`jobs.closed`).

    Args:
        line: `closed_line()`'s words.
    """
    return ft.Semantics(
        identifier=f"{SCREEN}.closed",
        content=ft.Container(
            ft.Text(
                line,
                theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            padding=ft.Padding.only(left=16, right=16, top=8, bottom=2),
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
    plate says nothing (`logo_tile()`).

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
