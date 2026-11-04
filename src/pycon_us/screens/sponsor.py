"""Sponsor detail (`…/sponsor/<slug>`): who, where to find them, about, open roles.

SPON-03, SPON-05 (#396). Ionic rendered the description as HTML, which ran its
paragraphs together, linked almost none of the roles (Bloomberg: 15 roles, 0 links)
and showed an empty card for an unknown slug. This page, top to bottom (ux.md §6.5):

- **The intro**, centred: the logo on a 240 × 96 white plate (`logo_tile()`, D-262,
  decorative: the name follows), the name as the page's level-1 heading (the app bar's
  title stays empty, D-186, D-211), the level as a plain line, "Visionary sponsor",
  rather than §6.5's first `Chip`, which would be a control that does nothing, and
  where to find them, as buttons in a wrapping row, each only when the sponsor has
  one: "Find booth 613", a tonal button, pushes the expo hall at the booth
  (`locations.booth_href()`, #409; a booth the plan doesn't draw opens the List
  with its line), and "Job fair table T2", an outlined one, pushes the job fair plan
  with the table selected (`…/plan/job-fair?table=T2`, #464). Both push on the
  sponsor, so Back returns here. In a year without an expo hall the booth is a plain
  line, "Booth 613". "Website" follows only when the feed gives the sponsor one
  (`external_url`; the live feed never has).
- **About** (level 2): the feed's plain text, selectable, its line breaks kept;
  left out when the feed has none.
- **Open roles** (level 2): each role of the sponsor's listings
  (`jobs.listings_of`, D-278) as a `LinkTile` with `WORK_OUTLINE` that opens the
  in-app browser; a long-form listing (SerpApi) shows its Markdown instead; left out
  without a listing, or with only a placeholder (OpenEDG's "N/A").

An unknown slug shows the not-found state on its own level, with All sponsors as the
way out (D-186, ux.md §4.6); without data the page loads and fails as the others do
(ux.md §4.1).
"""

import flet as ft

from pycon_us.core.jobs import listings_of
from pycon_us.core.links import feed_link
from pycon_us.core.models import ConferenceData, Sponsor
from pycon_us.core.sponsors import sponsor_by_slug
from pycon_us.locations import booth_href
from pycon_us.prefs import use_prefs
from pycon_us.screens.plan_tables import table_href
from pycon_us.services import Services, use_services
from pycon_us.services.errors import report_errors
from pycon_us.state import use_conference
from pycon_us.ui.buttons import ICON_PADDING
from pycon_us.ui.link_tile import LinkTile
from pycon_us.ui.links import (
    OPENS_IN,
    LinkKind,
    external,
    feed_markdown,
    link_kind,
    open_link,
)
from pycon_us.ui.logos import logo_tile
from pycon_us.ui.page_title import PageTitle
from pycon_us.ui.scaffold import AppScaffold, SectionHeader
from pycon_us.ui.semantics import named
from pycon_us.ui.states import NoDataState, not_found
from pycon_us.ui.widths import READING, sides, use_margin

SCREEN = "sponsor"
"""The screen's name in its semantics identifiers (decisions §M)."""

NOT_FOUND = "We couldn't find this sponsor"
"""The empty state of an unknown slug (ux.md §4.6)."""

PLATE_HEIGHT = 96
"""The logo plate's height, in dp (ux.md §6.5)."""

PLATE_WIDTH = 240
"""The logo plate's width, in dp (ux.md §6.5)."""

WEBSITE = "Website"
"""The website button's words."""


@ft.component
def SponsorDetail(sponsor_slug: str) -> ft.View:
    """One sponsor: its logo, name, level and places, then About and Open roles.

    Args:
        sponsor_slug: The sponsor's slug, unquoted.
    """
    svc = use_services()
    view_path = ft.use_view_path()
    margin = use_margin(READING)  # its width class (D-305)
    conference = use_conference()
    prefs = use_prefs()
    data = conference.data

    if data is None:
        no_data = NoDataState(conference, svc, f"{SCREEN}.no_data")
        # No name to show yet: the bar names the page, its level-1 heading (D-211).
        return AppScaffold(
            title="Sponsor",
            source=__name__,
            body=ft.ListView([no_data], expand=True, padding=sides(margin)),
        )
    sponsor = sponsor_by_slug(data, sponsor_slug)
    if sponsor is None:
        return AppScaffold(
            title="Not found",
            source=__name__,
            body=ft.ListView(
                [
                    not_found(
                        NOT_FOUND,
                        icon=ft.Icons.DOMAIN_DISABLED_OUTLINED,
                        action="All sponsors",
                        location="/more/sponsors",
                        identifier=f"{SCREEN}.not_found",
                    )
                ],
                expand=True,
                padding=sides(margin),
            ),
        )
    items: list[ft.Control] = [
        intro(sponsor, svc, view_path, large_text=prefs.time_above)
    ]
    if sponsor.description.strip():
        items.append(SectionHeader("About", level=2))
        items.append(about(sponsor.description))
    items.extend(open_roles(data, sponsor, svc))
    body = ft.ListView(items, expand=True, padding=sides(margin, bottom=24))
    # The heading in the intro names the page, so the app bar's title stays empty.
    return AppScaffold(title="", source=__name__, body=body)


def facts_line(sponsor: Sponsor, *, hall: bool) -> str | None:
    """Return the sponsor's booth as a plain line, "Booth 613", or None.

    None without a booth, and in a year with an expo hall, where the booth is the
    Find booth button instead (`find_booth_button()`); the job fair table is
    always a button (`job_fair_button()`).

    Args:
        sponsor: The sponsor.
        hall: The year has an expo hall to open (`YearMap.booths`).
    """
    return f"Booth {sponsor.booth}" if sponsor.booth and not hall else None


def intro(
    sponsor: Sponsor, svc: Services, view_path: str, *, large_text: bool
) -> ft.Control:
    """Return the page's intro: the logo, the name, the level, the facts, the actions.

    Centred. The name is the page's heading (level 1), a `PageTitle` selectable to
    copy (D-26), where a long name wraps (D-186). The level and the facts are plain
    lines, each a node of its own. The places' buttons and the website follow, each
    only when the sponsor has one.

    Args:
        sponsor: The sponsor.
        svc: The session's services, for the website's launch.
        view_path: The page's View path, so the plans are pushed on top of it.
        large_text: The text is large for the width (`Prefs.time_above`): the
            name steps down (D-328).
    """
    lines: list[ft.Control] = [
        logo_tile(sponsor.name, sponsor.logo_url, size=PLATE_HEIGHT, width=PLATE_WIDTH),
        PageTitle(
            sponsor.name,
            identifier=f"{SCREEN}.title",
            large_text=large_text,
            centred=True,
            selectable=True,
        ),
        # A node of its own: a plain line became the column's own label, which TalkBack
        # read before the name, the heading inside it (#1085).
        ft.Semantics(
            container=True,
            content=_centred(
                f"{sponsor.level} sponsor", color=ft.Colors.ON_SURFACE_VARIANT
            ),
        ),
    ]
    hall = bool(svc.year.map.booths)  # no hall, no Find booth: none is dead
    facts = facts_line(sponsor, hall=hall)
    if facts is not None:
        lines.append(ft.Semantics(container=True, content=_centred(facts)))
    places: list[ft.Control] = []
    if sponsor.booth and hall:
        places.append(find_booth_button(sponsor.booth, view_path))
    if sponsor.job_fair_table:
        places.append(job_fair_button(sponsor.job_fair_table, view_path))
    if places:
        # A wrapping row: at 200 % text the two buttons stack, nothing clips.
        lines.append(
            ft.Row(
                places,
                wrap=True,
                spacing=8,
                run_spacing=8,
                alignment=ft.MainAxisAlignment.CENTER,
            )
        )
    website = feed_link(sponsor.external_url, svc.year.conference.site_url)
    if website is not None and link_kind(website) is LinkKind.WEB:
        lines.append(website_button(website, svc))
    return ft.Container(
        ft.Column(lines, spacing=8, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.Padding.only(left=16, top=8, right=16, bottom=8),
    )


def _centred(text: str, *, color: ft.ColorValue | None = None) -> ft.Text:
    """A centred line of the intro in `BODY_LARGE`."""
    return ft.Text(
        text,
        theme_style=ft.TextThemeStyle.BODY_LARGE,
        color=color,
        text_align=ft.TextAlign.CENTER,
    )


def find_booth_button(number: str, view_path: str) -> ft.Control:
    """Return "Find booth 613", a tonal button that shows the booth in the expo hall.

    It pushes `…/plan/expo?booth=613` on the sponsor (`booth_href()`, #405), so
    Back returns here; a booth the plan doesn't draw opens the hall's List with its
    line. ux.md §6.5's `STOREFRONT_OUTLINED` (identifier `sponsor.find_booth`).
    Material pads its 40 dp to a 48 dp tap on phones (ux.md §9).

    Args:
        number: The sponsor's booth, as the feed writes it.
        view_path: The page's View path.
    """
    target = booth_href(view_path, number)

    @report_errors
    def go() -> None:
        ft.context.page.navigate(target)

    button = ft.FilledTonalButton(
        f"Find booth {number}",
        icon=ft.Icons.STOREFRONT_OUTLINED,
        on_click=go,
        style=ft.ButtonStyle(padding=ICON_PADDING),
        elevation=0,  # with a style, Flet lifts it to 1 (D-344)
    )
    return named(f"{SCREEN}.find_booth", button)


def job_fair_button(number: str, view_path: str) -> ft.Control:
    """Return "Job fair table T2", an outlined button that shows the table on the plan.

    It pushes `…/plan/job-fair?table=T2` on the sponsor (#464), so Back returns
    here; ux.md §6.5's `GROUPS_OUTLINED` (identifier `sponsor.job_fair_table`).

    Args:
        number: The sponsor's table, as the feed writes it.
        view_path: The page's View path.
    """
    target = table_href(view_path, number)

    @report_errors
    def go() -> None:
        ft.context.page.navigate(target)

    button = ft.OutlinedButton(
        f"Job fair table {number}",
        icon=ft.Icons.GROUPS_OUTLINED,
        on_click=go,
        style=ft.ButtonStyle(padding=ICON_PADDING),
    )
    return named(f"{SCREEN}.job_fair_table", button)


def website_button(url: str, svc: Services) -> ft.Control:
    """Return "Website", an outlined button that opens the sponsor's site in the app.

    A link for screen readers, read "Website, Opens in browser", as the other buttons
    that leave the app (`links.external()`).

    Args:
        url: The site, an absolute address (`feed_link()`).
        svc: The session's services, for the launcher.
    """

    @report_errors
    async def go(e: ft.Event[ft.OutlinedButton]) -> None:
        await open_link(svc, url, opener=e.control)

    button = ft.OutlinedButton(
        ft.Text(WEBSITE, semantics_label=f"{WEBSITE}\n{OPENS_IN[LinkKind.WEB]}"),
        icon=ft.Icons.OPEN_IN_NEW,
        on_click=go,
        style=ft.ButtonStyle(padding=ICON_PADDING),
    )
    return ft.Container(
        external(f"{SCREEN}.website", button), padding=ft.Padding.only(top=8)
    )


def about(description: str) -> ft.Control:
    """Return the sponsor's description: plain text, selectable, its line breaks kept.

    The feed's sponsor descriptions are plain text (SPON-03), so a `Text` shows them
    as written, where Ionic's HTML ran the paragraphs together.

    Args:
        description: The feed's text.
    """
    return ft.Semantics(
        identifier=f"{SCREEN}.about",
        container=True,  # one node holds the text's, so the identifier has a home
        content=ft.Container(
            ft.Text(
                description.strip(),
                theme_style=ft.TextThemeStyle.BODY_LARGE,
                selectable=True,  # long text is selectable (D-26)
            ),
            padding=ft.Padding.symmetric(horizontal=16),
        ),
    )


def open_roles(
    data: ConferenceData, sponsor: Sponsor, svc: Services
) -> list[ft.Control]:
    """Return the Open roles section, or nothing when the sponsor lists none.

    Each role is a `LinkTile` that opens the in-app browser (ux.md §4.7), in its
    listing's order; a long-form listing shows its Markdown (D-278). A placeholder
    listing has neither, so a sponsor with only one gets no section.

    Args:
        data: The processed feed.
        sponsor: The sponsor.
        svc: The session's services, for a Markdown listing's links.
    """
    rows: list[ft.Control] = []
    for listing in listings_of(data, sponsor):
        if listing.roles:
            first = len(rows)  # roles count on across listings: sponsor.role.<n>
            rows.extend(
                LinkTile(
                    role.title,
                    role.url,
                    icon=ft.Icons.WORK_OUTLINE,
                    identifier=f"{SCREEN}.role.{first + index}",
                )
                for index, role in enumerate(listing.roles)
            )
        elif listing.description_md:
            rows.append(
                feed_markdown(
                    listing.description_md,
                    svc,
                    identifier=f"{SCREEN}.listing.{listing.id}",
                )
            )
    if not rows:
        return []
    return [SectionHeader("Open roles", level=2), *rows]
