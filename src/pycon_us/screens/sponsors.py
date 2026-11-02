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
  inside the page's list, U32), and one to a row at large text (``logo_columns()``);
- the rest as rows with a 48 dp plate.

Tiers go by a level's place, never its name, so next year's levels need no code. Each
plate is ``ui/logos.py``'s ``logo_tile()`` (D-262): the logo, or the initials when
there is none or it cannot load (offline), at a fixed height, so nothing moves when a
logo arrives or fails. Each sponsor is one node, a button read "Bloomberg, Visionary
sponsor, booth 613" (D-33), and a tap pushes its detail, ``…/sponsor/<slug>`` (D-17).
Each item is a memoised component keyed by its slug (D-153), so a refresh that keeps
the feed re-renders none. Search lists sponsors as these rows (``SponsorRow``), whose
line says the level too, "Visionary · Booth 613" (#397). Without data the page loads
and fails as the Schedule does (ux.md §4.1); the status strip says how fresh the list
is (D-32).
"""

from typing import Literal

import flet as ft

from pycon_us.core.models import Sponsor, SponsorLevel
from pycon_us.locations import drill_href
from pycon_us.prefs import use_prefs
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.state import use_conference
from pycon_us.ui.logos import logo_tile
from pycon_us.ui.scaffold import AppScaffold, SectionHeader
from pycon_us.ui.states import EmptyState, NoDataState
from pycon_us.ui.status_strip import StatusStrip
from pycon_us.ui.widths import LIST, sides, use_margin

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

LOGO_COLUMNS_AT_LARGE_TEXT: ft.ResponsiveNumber = 12
"""A logo card's share at large text: the row's whole width, one card to a row. Half
a phone's width broke a name inside a word at the largest sizes, "Anaco / nda, Inc"
(#649); a whole one wraps it between its words."""

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


def logo_columns(large_text: bool) -> ft.ResponsiveNumber:
    """Return a logo card's share of its ``ResponsiveRow``'s 12 columns.

    Two or more cards to a row (``LOGO_COLUMNS``), or one when the text is large for
    the width (``Prefs.time_above``, D-216, the signal detail titles and the
    Schedule's head use, D-328, D-345), where a name in half a phone's width broke
    inside a word (#649).

    Args:
        large_text: The text is large for the width (``Prefs.time_above``).
    """
    return LOGO_COLUMNS_AT_LARGE_TEXT if large_text else LOGO_COLUMNS


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


def level_line(sponsor: Sponsor) -> str:
    """Return a sponsor row's line outside its level's section: "Visionary · Booth 613".

    Search lists sponsors without the level headings, so the line says the level too;
    a sponsor without a booth has the level alone.

    Args:
        sponsor: The sponsor.
    """
    booth = booth_line(sponsor)
    return f"{sponsor.level} \N{MIDDLE DOT} {booth}" if booth else sponsor.level


@ft.component
def Sponsors() -> ft.View:
    """The Sponsors page: the strip, then the intro and a section per level."""
    svc = use_services()
    prefs = use_prefs()
    margin = use_margin(LIST)  # its width class (D-305)
    conference = use_conference()
    data = conference.data

    items: list[ft.Control] = [StatusStrip()]
    if data is None:
        items.append(NoDataState(conference, svc, f"{SCREEN}.no_data"))
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
            items.extend(
                level_section(level, tier_of(position), large_text=prefs.time_above)
            )
    return AppScaffold(
        title=TITLE,
        source=__name__,
        body=ft.ListView(items, expand=True, padding=sides(margin, bottom=24)),
    )


def level_section(
    level: SponsorLevel, tier: Tier, *, large_text: bool
) -> list[ft.Control]:
    """Return one level's heading and its sponsors, drawn as its tier says.

    Args:
        level: The level and its sponsors, in feed order.
        tier: How its sponsors are drawn (``tier_of()``).
        large_text: The text is large for the width (``Prefs.time_above``): logo
            cards go one to a row (``logo_columns()``).
    """
    heading = SectionHeader(level.name)
    sponsors = [
        SponsorItem(sponsor, tier, large_text=large_text) for sponsor in level.sponsors
    ]
    if tier != "logo":
        return [heading, *sponsors]
    grid = ft.ResponsiveRow(sponsors, spacing=GAP, run_spacing=GAP)
    return [heading, ft.Container(grid, padding=ft.Padding.symmetric(horizontal=16))]


def SponsorItem(sponsor: Sponsor, tier: Tier, *, large_text: bool) -> ft.Control:
    """Return one sponsor as its tier draws it, a memoised component keyed by its slug.

    Given the same sponsor it skips its body (D-153, F34), so a refresh that keeps the
    feed re-renders no item.

    Args:
        sponsor: The sponsor, the same object for one feed version.
        tier: How it is drawn.
        large_text: The text is large for the width: a logo card takes a whole row
            (``logo_columns()``).
    """
    # As SessionRow's: ft.component's typing leaves out the key= its wrapper takes.
    return _SponsorItem(sponsor, tier, large_text, key=sponsor.slug)  # pyright: ignore[reportCallIssue]


@ft.memo
@ft.component
def _SponsorItem(sponsor: Sponsor, tier: Tier, large_text: bool) -> ft.Control:
    """The body of ``SponsorItem``; it runs only when one of its arguments changes."""
    view_path = ft.use_view_path()
    page = ft.context.page

    @report_errors
    def go() -> None:
        page.navigate(drill_href(view_path, "sponsor", sponsor.slug))

    texts = _texts(sponsor.name, booth_line(sponsor))
    if tier == "tile":
        return _row(sponsor, texts, go, screen=SCREEN)
    plate = FEATURE_PLATE if tier == "feature" else LOGO_PLATE
    card = _card(sponsor, plate, texts, go)
    if tier == "logo":
        card.col = logo_columns(large_text)  # the ResponsiveRow reads it from its child
    return card


def SponsorRow(sponsor: Sponsor, *, screen: str) -> ft.Control:
    """Return a sponsor as a row outside the Sponsors page: plate, name, level and booth.

    The Sponsors page's row (``_row()``), its line saying the level too
    (``level_line()``), as search lists it (#397): one node, read as
    ``sponsor_phrase()``, a button, and a tap pushes the sponsor's detail on top of
    the current View (D-17). A memoised component keyed by the slug (D-153), so new
    results re-render only the rows they add.

    Args:
        sponsor: The sponsor, the same object for one feed version.
        screen: The screen's name in the row's identifier, ``<screen>.sponsor.<slug>``.
    """
    # As SponsorItem's: ft.component's typing leaves out the key= its wrapper takes.
    return _SponsorRow(sponsor, screen, key=sponsor.slug)  # pyright: ignore[reportCallIssue]


@ft.memo
@ft.component
def _SponsorRow(sponsor: Sponsor, screen: str) -> ft.Control:
    """The body of ``SponsorRow``; it runs only when its sponsor changes."""
    view_path = ft.use_view_path()
    page = ft.context.page

    @report_errors
    def go() -> None:
        page.navigate(drill_href(view_path, "sponsor", sponsor.slug))

    return _row(sponsor, _texts(sponsor.name, level_line(sponsor)), go, screen=screen)


def _texts(name: str, line: str | None) -> list[ft.Control]:
    """Return a sponsor's name and the line under it, when there is one."""
    texts: list[ft.Control] = [
        ft.Text(name, theme_style=ft.TextThemeStyle.TITLE_MEDIUM)
    ]
    if line is not None:
        texts.append(
            ft.Text(
                line,
                theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                color=ft.Colors.ON_SURFACE_VARIANT,
            )
        )
    return texts


def _spoken(sponsor: Sponsor, content: ft.Control, screen: str) -> ft.Semantics:
    """Wrap ``content`` as the sponsor's one node: its phrase, a button, its identifier.

    The phrase replaces the texts, which would be read too, and the plate says nothing
    (``logo_tile()``).
    """
    return ft.Semantics(
        label=sponsor_phrase(sponsor),
        identifier=f"{screen}.sponsor.{sponsor.slug}",
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
                    SCREEN,
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
    sponsor: Sponsor,
    texts: list[ft.Control],
    go: ft.ControlEventHandler,
    *,
    screen: str,
) -> ft.MergeSemantics:
    """A row: a 48 dp plate, the name and its line, and a chevron to the detail.

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
                screen,
            ),
            ink=True,
            on_click=go,
            padding=ft.Padding.symmetric(horizontal=16, vertical=8),
        )
    )
