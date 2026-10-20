"""Sponsors (``/more/sponsors``): every sponsor of the year, tier by tier (SPON-01).

Ionic showed one flat list in one style behind a 10 s blocking loader, with nothing
when the feed had no sponsors, and a strip that rotated sponsors on every screen; the
strip is gone (D-37), and this page gives each level its weight instead (ux.md §6.5).
An intro line, then a level-2 heading per level, in the feed's ``level_order``
(``ConferenceData.sponsor_levels``), and the level's sponsors in feed order:

- the first level as full-width cards: a wide white plate with the logo, the name and
  the booth;
- the next two as logo cards, two to a phone's row, more on a wider screen
  (``ft.ResponsiveRow``, D-279: a ``GridView`` cannot size itself to its content
  inside the page's list, U32);
- the rest as rows with a 48 dp plate.

Tiers go by a level's place, never its name, so next year's levels need no code. Each
plate is ``ui/logos.py``'s ``logo_tile()`` (D-262): the logo, or the initials when
there is none or it cannot load (offline), at a fixed height, so nothing moves when a
logo arrives or fails. Each sponsor is one node, a button read "Bloomberg, Visionary
sponsor, booth 613" (D-33), and a tap pushes its detail, ``…/sponsor/<slug>`` (D-17).
Each item is a memoised component keyed by its slug (D-153), so a refresh that keeps
the feed re-renders none. Without data the page loads and fails as the Schedule does
(ux.md §4.1); the status strip says how fresh the list is (D-32).
"""

from typing import Literal

import flet as ft

from pycon_us.core.models import Sponsor, SponsorLevel
from pycon_us.locations import drill_href
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.state import use_conference
from pycon_us.ui.logos import logo_tile
from pycon_us.ui.scaffold import AppScaffold, SectionHeader
from pycon_us.ui.states import EmptyState, NoDataState
from pycon_us.ui.status_strip import StatusStrip

SCREEN = "sponsors"
"""The page's name in its semantics identifiers (decisions §M)."""

TITLE = "Sponsors"
"""The page's name: its app bar's title and its More row."""

INTRO = "PyCon US is possible thanks to these organizations."
"""The line above the levels (ux.md §6.5)."""

type Tier = Literal["feature", "logo", "tile"]
"""How a level's sponsors are drawn: full-width cards, logo cards or rows."""

FEATURE_LEVELS = 1
"""How many levels, from the top, get full-width cards."""

LOGO_LEVELS = 2
"""How many levels after those get logo cards; every level below gets rows."""

FEATURE_PLATE = 96
"""A full-width card's plate height, in dp."""

LOGO_PLATE = 72
"""A logo card's plate height, in dp."""

TILE_PLATE = 48
"""A row's plate, in dp: square (ux.md §6.5)."""

LOGO_COLUMNS: ft.ResponsiveNumber = {"xs": 6, "sm": 4, "md": 3}
"""A logo card's share of a ``ResponsiveRow``'s 12 columns, by Flet's breakpoints
(the page's width): two cards to a phone's row, three from 576 dp, four from 768 dp."""

GAP = 8
"""The space between logo cards, across and down, in dp: §3.6's grid within a group."""


def tier_of(position: int) -> Tier:
    """Return how the level at ``position`` (0 is the top) draws its sponsors.

    Args:
        position: The level's index in ``ConferenceData.sponsor_levels``.
    """
    if position < FEATURE_LEVELS:
        return "feature"
    if position < FEATURE_LEVELS + LOGO_LEVELS:
        return "logo"
    return "tile"


def sponsor_phrase(sponsor: Sponsor) -> str:
    """Return what a screen reader says for a sponsor: "Bloomberg, Visionary sponsor, booth 613".

    The level is said with each sponsor, as the heading above it is not read with it;
    a sponsor without a booth leaves the booth out.

    Args:
        sponsor: The sponsor.
    """
    phrase = f"{sponsor.name}, {sponsor.level} sponsor"
    return f"{phrase}, booth {sponsor.booth}" if sponsor.booth else phrase


def booth_line(sponsor: Sponsor) -> str | None:
    """Return the line under a sponsor's name, "Booth 613", or None without a booth."""
    return f"Booth {sponsor.booth}" if sponsor.booth else None


@ft.component
def Sponsors() -> ft.View:
    """The Sponsors page: the strip, then the intro and a section per level."""
    svc = use_services()
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
    elif not data.sponsor_levels:
        items.append(
            EmptyState(
                "No sponsors announced yet",
                icon=ft.Icons.STOREFRONT_OUTLINED,
                # No button: the app refreshes the feed on its own (D-175).
                body="They show here as soon as the conference lists them.",
                identifier=f"{SCREEN}.empty",
            )
        )
    else:
        items.append(
            ft.Container(
                ft.Text(
                    INTRO,
                    theme_style=ft.TextThemeStyle.BODY_LARGE,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                padding=ft.Padding.only(left=16, top=12, right=16),
            )
        )
        for position, level in enumerate(data.sponsor_levels):
            items.extend(level_section(level, tier_of(position)))
    return AppScaffold(
        title=TITLE,
        body=ft.ListView(items, expand=True, padding=ft.Padding.only(bottom=24)),
    )


def level_section(level: SponsorLevel, tier: Tier) -> list[ft.Control]:
    """Return one level's heading and its sponsors, drawn as its tier says.

    Args:
        level: The level and its sponsors, in feed order.
        tier: How its sponsors are drawn (``tier_of()``).
    """
    heading = SectionHeader(level.name)
    sponsors = [SponsorItem(sponsor, tier) for sponsor in level.sponsors]
    if tier != "logo":
        return [heading, *sponsors]
    grid = ft.ResponsiveRow(sponsors, spacing=GAP, run_spacing=GAP)
    return [heading, ft.Container(grid, padding=ft.Padding.symmetric(horizontal=16))]


def SponsorItem(sponsor: Sponsor, tier: Tier) -> ft.Control:
    """Return one sponsor as its tier draws it, a memoised component keyed by its slug.

    Given the same sponsor it skips its body (D-153, F34), so a refresh that keeps the
    feed re-renders no item.

    Args:
        sponsor: The sponsor, the same object for one feed version.
        tier: How it is drawn.
    """
    # As SessionRow's: ft.component's typing leaves out the key= its wrapper takes.
    return _SponsorItem(sponsor, tier, key=sponsor.slug)  # pyright: ignore[reportCallIssue]


@ft.memo
@ft.component
def _SponsorItem(sponsor: Sponsor, tier: Tier) -> ft.Control:
    """The body of ``SponsorItem``; it runs only when its sponsor or tier changes."""
    view_path = ft.use_view_path()
    page = ft.context.page

    @report_errors
    def go() -> None:
        page.navigate(drill_href(view_path, "sponsor", sponsor.slug))

    texts: list[ft.Control] = [
        ft.Text(sponsor.name, theme_style=ft.TextThemeStyle.TITLE_MEDIUM)
    ]
    booth = booth_line(sponsor)
    if booth is not None:
        texts.append(
            ft.Text(
                booth,
                theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                color=ft.Colors.ON_SURFACE_VARIANT,
            )
        )
    if tier == "tile":
        return _row(sponsor, texts, go)
    plate = FEATURE_PLATE if tier == "feature" else LOGO_PLATE
    card = _card(sponsor, plate, texts, go)
    if tier == "logo":
        card.col = LOGO_COLUMNS  # the ResponsiveRow reads it from its child
    return card


def _spoken(sponsor: Sponsor, content: ft.Control) -> ft.Semantics:
    """Wrap ``content`` as the sponsor's one node: its phrase, a button, its identifier.

    The phrase replaces the texts, which would be read too, and the plate says nothing
    (``logo_tile()``).
    """
    return ft.Semantics(
        label=sponsor_phrase(sponsor),
        identifier=f"{SCREEN}.sponsor.{sponsor.slug}",
        button=True,  # it opens the sponsor: "…, button" (D-33)
        exclude_semantics=True,
        content=content,
    )


def _card(
    sponsor: Sponsor, plate: int, texts: list[ft.Control], go: ft.ControlEventHandler
) -> ft.MergeSemantics:
    """A card: the logo on a plate as wide as the card, then the name and the booth.

    A full-width card in the list takes the list's gutters; a logo card takes the
    width its ``ResponsiveRow`` column gives it.
    """
    full = plate == FEATURE_PLATE
    return ft.MergeSemantics(  # the phrase and the tap's action: one node
        content=ft.Card(
            ft.Container(
                _spoken(
                    sponsor,
                    ft.Column(
                        [
                            logo_tile(
                                sponsor.name, sponsor.logo_url, size=plate, fill=True
                            ),
                            ft.Column(texts, spacing=2),
                        ],
                        spacing=12,
                    ),
                ),
                ink=True,
                on_click=go,
                padding=16 if full else 12,
            ),
            variant=ft.CardVariant.OUTLINED,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,  # the ink stays inside
            margin=ft.Margin.symmetric(horizontal=16, vertical=6) if full else 0,
        )
    )


def _row(
    sponsor: Sponsor, texts: list[ft.Control], go: ft.ControlEventHandler
) -> ft.MergeSemantics:
    """A row: a 48 dp plate, the name and the booth, and a chevron to the detail.

    Built like ``SpeakerRow`` rather than as a ``ListTile``, so it reads as one phrase
    with its level; nothing but the plate has a fixed size, so it grows with the text.
    """
    return ft.MergeSemantics(
        content=ft.Container(
            _spoken(
                sponsor,
                ft.Row(
                    [
                        logo_tile(sponsor.name, sponsor.logo_url, size=TILE_PLATE),
                        ft.Column(texts, spacing=2, expand=True),
                        ft.Icon(ft.Icons.CHEVRON_RIGHT),
                    ],
                    spacing=16,
                    # Centred, as a ListTile's: most of these rows are a name alone,
                    # which at the plate's top would leave half the row empty.
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ),
            ink=True,
            on_click=go,
            padding=ft.Padding.symmetric(horizontal=16, vertical=8),
        )
    )
