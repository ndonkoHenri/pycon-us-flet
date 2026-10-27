"""The booth card: who is at the selected booth, under the expo plan (EXPO-03, D-254).

``ExpoHall`` (``screens/expo.py``) shows it at the bottom of its ``Stack``, under the
zoom buttons, so the plan stays in use (a modal sheet would block it, D-29). It is a
``Card`` in one of three forms (ux.md §6.2):

- **One exhibitor:** its logo on the white tile (initials offline, ``logo_tile()``), the
  name, "Booth 613 · Visionary", "Hiring · 15 open roles" when it has a job listing
  (a line, not a second button to the same page), and ``FilledTonalButton("Sponsor
  details")``, which pushes ``…/sponsor/<slug>`` (D-17), so Back returns to the booth.
- **A shared booth:** headed "Booth 726 · Community" (the level only when every
  exhibitor has it) over "4 exhibitors", then one 48 dp row per exhibitor in name order,
  each pushing its sponsor.
- **No exhibitor:** the booth's ``map.toml`` label (or its number before the feed is
  there) beside a ``PLACE_OUTLINED`` icon where a logo would be (no PSF logo, D-36), and
  no sponsor action.

Its head is one node in a live region, so a screen reader hears each newly selected
booth: "Booth 613, Bloomberg, Visionary sponsor, hiring, 15 open roles". A 48 dp Close
clears the selection. A body taller than half the pane (many exhibitors, the largest
text) scrolls in a box half the pane high, Close pinned beside it, so the zoom buttons
and most of the plan stay in sight (D-370). In a pane too short for that under the
buttons' column (landscape), the buttons go in a row and the box is what is left;
so they do under a tall card that would leave the plan too thin a band (``card_layout()``). The card is a memoised component given
values only (D-153, F150): the body's measured height lives in ``ExpoHall``, above it.
"""

from collections.abc import Callable

import flet as ft

from pycon_us.core.expo import ExpoBooth
from pycon_us.core.jobs import listings_of
from pycon_us.core.models import ConferenceData, Sponsor
from pycon_us.locations import drill_href
from pycon_us.screens.map_job_fair import roles_phrase
from pycon_us.services.errors import report_errors
from pycon_us.ui.logos import logo_tile
from pycon_us.ui.semantics import named
from pycon_us.ui.zoom import BUTTON_DP

SCREEN = "expo"
"""The screen's name in the card's identifiers: ``expo.card``, ``expo.card.close``."""

DETAILS = "Sponsor details"
"""The one exhibitor's button."""

CLOSE = "Close"
"""The close button's tooltip, its accessible name (D-27)."""

HIRING = "Hiring"
"""The start of the roles line."""

LEAD = 56
"""The logo tile or place icon beside the head, in dp."""

ROW_LOGO = 40
"""A shared booth's row logo, in dp: with 4 dp above and below, a 48 dp row."""

EDGE = 16
"""The bottom column's inset from the pane's edges, and its gap between buttons and card."""

CARD_PADDING = (8, 16)
"""The card's padding above and below its body, in dp."""

BODY_TOP = 8
"""The body's own padding above its measured content, inside the scroll box, in dp."""

COLUMN_DP = 3 * BUTTON_DP + 2 * 8
"""The zoom buttons' height in their column (``zoom_buttons()``): 160 dp."""

ROW_DP = BUTTON_DP
"""The zoom buttons' height in a row: 48 dp."""

# Around the body box: the insets above and below the column, the gap, the card's padding.
_AROUND = 3 * EDGE + sum(CARD_PADDING)

ROW_UNDER = 2 * (COLUMN_DP + _AROUND)
"""A pane shorter than this, in dp, puts the zoom buttons in a row (D-370).

At this height half the pane is exactly what the buttons' column leaves the body.
"""


BAND = COLUMN_DP - ROW_DP
"""The least plan the column leaves above a tall card before the buttons go in a row.

112 dp, what the row gives back: a booth brought into view needs a band to land in
(D-377), and at the fitted plan a 2026 booth is under 42 dp high.
"""


def card_layout(pane: float, measured: float) -> tuple[bool, float | None]:
    """Return whether the zoom buttons go in a row, and the card body's scroll box.

    The box is half the pane, or less when the buttons, the gap, the card's padding
    and the pane's insets leave less, so the zoom buttons always stay in the pane
    (D-370): a Stack clips what goes past its top. The buttons go in a row in a short
    pane, and also when a tall card under their column would leave less than
    ``BAND`` of the plan above it (D-377).

    Args:
        pane: The pane's height (the viewer's measured height); 0 before it is known.
        measured: The body's measured content height; 0 before it is known.

    Returns:
        ``(row, box)``: ``row`` puts the buttons in a row; ``box`` is None while the
        body, with its own top padding, fits.
    """
    row = 0 < pane < ROW_UNDER or (
        pane > 0 and measured > 0 and pane - _cover(pane, measured, row=False) < BAND
    )
    return row, _box(pane, measured, row=row)


def covered(pane: float, measured: float) -> float:
    """Return how much of the pane, from its bottom, the card and the zoom buttons take.

    The bottom column as ``card_layout()`` lays it out, with an inset above it too:
    what lies higher is in sight (D-377).

    Args:
        pane: The pane's height (the viewer's measured height).
        measured: The card body's measured content height.
    """
    row, _ = card_layout(pane, measured)
    return _cover(pane, measured, row=row)


def _box(pane: float, measured: float, *, row: bool) -> float | None:
    """Return the card body's scroll box with the buttons laid out so, None if it fits."""
    room = pane - (ROW_DP if row else COLUMN_DP) - _AROUND
    box = max(0.0, min(pane / 2, room))
    return box if pane and measured + BODY_TOP > box else None


def _cover(pane: float, measured: float, *, row: bool) -> float:
    """Return what the bottom column covers with the buttons laid out so, in dp."""
    box = _box(pane, measured, row=row)
    body = box if box is not None else BODY_TOP + measured
    return _AROUND + max(body, BUTTON_DP) + (ROW_DP if row else COLUMN_DP)


type OnBodySize = Callable[[ft.LayoutSizeChangeEvent], None]
"""``ExpoHall``'s handler for the card body's measured size."""


def hiring_line(data: ConferenceData | None, sponsor: Sponsor) -> str:
    """Return "Hiring · 15 open roles", "Hiring" for a long-form listing, or "".

    A sponsor is hiring when sponsor detail has an Open roles section for it: a listing
    with roles or with text. A placeholder listing has neither (``core.jobs``).

    Args:
        data: The processed feed, or None before the first fetch.
        sponsor: The booth's one exhibitor.
    """
    if data is None:
        return ""
    listings = [
        listing
        for listing in listings_of(data, sponsor)
        if listing.roles or listing.description_md
    ]
    if not listings:
        return ""
    roles = roles_phrase(sum(len(listing.roles) for listing in listings))
    return f"{HIRING} \N{MIDDLE DOT} {roles}" if roles else HIRING


def shared_level(item: ExpoBooth) -> str:
    """Return the level every exhibitor of a booth shares, or "" when they differ."""
    levels = {sponsor.level for sponsor in item.sponsors}
    return levels.pop() if len(levels) == 1 else ""


def card_title(item: ExpoBooth) -> tuple[str, str]:
    """Return the head's title and the line under it ("" for none).

    Args:
        item: The selected booth and its exhibitors.

    Returns:
        ("Bloomberg", "Booth 613 · Visionary"); ("Booth 726 · Community", "4
        exhibitors"); ("Python Software Foundation", "Booth 407"); ("Booth 613", "")
        before the feed is there.
    """
    booth = f"Booth {item.booth.number}"
    dot = " \N{MIDDLE DOT} "
    if len(item.sponsors) == 1:
        return item.sponsors[0].name, f"{booth}{dot}{item.sponsors[0].level}"
    if item.sponsors:
        level = shared_level(item)
        title = f"{booth}{dot}{level}" if level else booth
        return title, f"{len(item.sponsors)} exhibitors"
    if item.booth.label:
        return item.booth.label, booth
    return booth, ""


def card_phrase(item: ExpoBooth, hiring: str) -> str:
    """Return what a screen reader says of the card's head, in its live region.

    Args:
        item: The selected booth and its exhibitors.
        hiring: ``hiring_line()``'s answer for a booth of one exhibitor, else "".

    Returns:
        "Booth 613, Bloomberg, Visionary sponsor, hiring, 15 open roles"; "Booth 726,
        Community, 4 exhibitors"; "Booth 407, Python Software Foundation".
    """
    parts = [f"Booth {item.booth.number}"]
    if len(item.sponsors) == 1:
        sponsor = item.sponsors[0]
        parts += [sponsor.name, f"{sponsor.level} sponsor"]
        parts += hiring.lower().split(" \N{MIDDLE DOT} ") if hiring else []
    elif item.sponsors:
        parts += [shared_level(item), f"{len(item.sponsors)} exhibitors"]
    else:
        parts.append(item.booth.label)
    return ", ".join(part for part in parts if part)


def BoothCard(
    item: ExpoBooth,
    *,
    hiring: str,
    view_path: str,
    body_box: float | None,
    on_close: Callable[[], None],
    on_body_size: OnBodySize,
) -> ft.Control:
    """Return the card of the selected booth: a memoised component keyed by its number.

    Args:
        item: The selected booth and its exhibitors.
        hiring: ``hiring_line()`` for a booth of one exhibitor, else "".
        view_path: The hall's View path, on top of which a sponsor is pushed.
        body_box: The height of the box the card's body scrolls in; None while it
            fits in half the pane.
        on_close: ``ExpoHall``'s handler that clears the selection.
        on_body_size: ``ExpoHall``'s handler for the body's measured size.
    """
    # ft.component's typing (its ParamSpec) leaves out the key= its wrapper takes.
    return _BoothCard(
        item,
        hiring=hiring,
        view_path=view_path,
        body_box=body_box,
        on_close=on_close,
        on_body_size=on_body_size,
        key=item.booth.number,  # pyright: ignore[reportCallIssue]
    )


@ft.memo
@ft.component
def _BoothCard(
    item: ExpoBooth,
    *,
    hiring: str,
    view_path: str,
    body_box: float | None,
    on_close: Callable[[], None],
    on_body_size: OnBodySize,
) -> ft.Control:
    """The body of ``BoothCard()``: it runs only when its props change (F34)."""
    parts: list[ft.Control] = [_head(item, hiring)]
    if len(item.sponsors) == 1:
        target = drill_href(view_path, "sponsor", item.sponsors[0].slug)

        @report_errors
        def details() -> None:
            ft.context.page.navigate(target)

        parts.append(
            ft.Row(
                [
                    named(
                        f"{SCREEN}.card.details",
                        ft.FilledTonalButton(DETAILS, on_click=details),
                    )
                ]
            )
        )
    elif item.sponsors:
        mixed = not shared_level(item)
        rows = [_exhibitor(s, view_path, mixed=mixed) for s in item.sponsors]
        parts.append(ft.Column(rows, spacing=0))

    @report_errors
    def close() -> None:
        on_close()

    closer = ft.IconButton(ft.Icons.CLOSE, tooltip=CLOSE, on_click=close)
    # The same two Columns either way: one that measures the body's own height and
    # one that bounds and scrolls it once that is more than half the pane. Close
    # stays outside them, in reach however far the body scrolls.
    body = ft.Column(
        [
            ft.Container(
                ft.Column(parts, spacing=12, tight=True, on_size_change=on_body_size),
                padding=ft.Padding.only(top=8),
            )
        ],
        height=body_box,
        scroll=ft.ScrollMode.AUTO if body_box else None,
        expand=True,
    )
    return ft.Card(
        ft.Container(
            ft.Row(
                [body, named(f"{SCREEN}.card.close", closer)],
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            padding=ft.Padding.only(left=16, top=8, right=8, bottom=16),
        ),
        margin=0,
    )


def _head(item: ExpoBooth, hiring: str) -> ft.Control:
    """The card's head: the logo or place icon, the title and its lines; one node."""
    title, line = card_title(item)
    texts: list[ft.Control] = [
        ft.Text(title, theme_style=ft.TextThemeStyle.TITLE_MEDIUM)
    ]
    for each in (line, hiring if len(item.sponsors) == 1 else ""):
        if each:
            texts.append(
                ft.Text(
                    each,
                    theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                )
            )
    lead: list[ft.Control] = []
    if len(item.sponsors) == 1:
        sponsor = item.sponsors[0]
        lead.append(logo_tile(sponsor.name, sponsor.logo_url, size=LEAD))
    elif not item.sponsors:
        lead.append(place_tile())
    return ft.Semantics(
        label=card_phrase(item, hiring),
        identifier=f"{SCREEN}.card",
        container=True,
        live_region=True,  # a new selection is said, as the card changes in place
        exclude_semantics=True,  # the phrase replaces the texts
        content=ft.Row(
            [*lead, ft.Column(texts, spacing=2, tight=True, expand=True)],
            spacing=16,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )


def place_tile(size: float = LEAD) -> ft.Control:
    """A booth without an exhibitor's icon, where a logo would be (D-254, D-36).

    Args:
        size: The tile's side, in dp: the card's 56, or the expo List's row plate.
    """
    return ft.Container(
        ft.Icon(ft.Icons.PLACE_OUTLINED, color=ft.Colors.ON_SURFACE_VARIANT),
        width=size,
        height=size,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        border_radius=12,
        alignment=ft.Alignment.CENTER,
    )


def _exhibitor(sponsor: Sponsor, view_path: str, *, mixed: bool) -> ft.Control:
    """One exhibitor of a shared booth: logo, name, chevron; a tap pushes its sponsor.

    One node, a button read "PyBeach, Community sponsor"; its level is shown under the
    name only when the booth's exhibitors differ (``mixed``), as the head says it
    otherwise.
    """
    target = drill_href(view_path, "sponsor", sponsor.slug)

    @report_errors
    def go() -> None:
        ft.context.page.navigate(target)

    texts: list[ft.Control] = [
        ft.Text(sponsor.name, theme_style=ft.TextThemeStyle.BODY_LARGE)
    ]
    if mixed:
        texts.append(
            ft.Text(
                sponsor.level,
                theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                color=ft.Colors.ON_SURFACE_VARIANT,
            )
        )
    return ft.MergeSemantics(  # the phrase and the tap's action: one node
        content=ft.Container(
            ft.Semantics(
                label=f"{sponsor.name}, {sponsor.level} sponsor",
                identifier=f"{SCREEN}.card.sponsor.{sponsor.slug}",
                button=True,
                exclude_semantics=True,
                content=ft.Row(
                    [
                        logo_tile(sponsor.name, sponsor.logo_url, size=ROW_LOGO),
                        ft.Column(texts, spacing=2, expand=True),
                        ft.Icon(ft.Icons.CHEVRON_RIGHT),
                    ],
                    spacing=16,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ),
            ink=True,
            on_click=go,
            padding=ft.Padding.only(top=4, right=8, bottom=4),
        )
    )
