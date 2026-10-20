"""A logo on a white tile, with the initials when there is none: ``logo_tile()``.

Logos are drawn for a white page: a dark mark on a transparent ground vanishes on the
dark surface. So a logo sits on a white tile in both schemes, with a hairline
``outline_variant`` edge, wherever the app shows one: a sprint project's card (EVT-05,
D-202) and, from P2, the Sponsors list and detail, Job listings and Now's sponsor
spotlight (ux.md §5.1, §6.5, §6.6). One builder, so the tile is drawn one way (D-262).
"""

import flet as ft

from pycon_us.core.speakers import initials
from pycon_us.theme import SEED

INK = SEED
"""The initials' colour on the white tile in both schemes: the brand indigo, 8.6:1."""

INSET = 6
"""The white margin between the tile's edge and its logo or initials, in dp."""

CORNER = 12
"""The tile's corner radius, in dp."""


def logo_tile(
    name: str, logo_url: str | None, *, size: float, width: float | None = None
) -> ft.Control:
    """Return the logo of ``name`` on a white tile, or its initials when there is none.

    The logo fits inside the tile's inset (``BoxFit.CONTAIN``). The initials stand in
    when there is no logo and when it cannot load (offline, a broken URL), in the brand
    indigo; a ``CircleAvatar`` holds them because it does not scale its text, so they
    fit the tile at any text size. The tile is decorative for screen readers: the name
    is always said beside it, so nothing under it is a node.

    Args:
        name: Whose logo it is: a project's or a sponsor's name, for the initials.
        logo_url: The logo's URL, or None when the feed has none.
        size: The tile's height in dp, and its width unless ``width`` is given.
        width: A wider plate's width in dp, as sponsor detail's 240 × 96 (ux.md §6.5);
            the initials keep to the height.
    """
    monogram = ft.CircleAvatar(
        content=ft.Text(initials(name), weight=ft.FontWeight.W_500),
        bgcolor=ft.Colors.TRANSPARENT,
        color=INK,
        radius=size / 2 - INSET,
    )
    content: ft.Control = monogram
    if logo_url:
        content = ft.Image(src=logo_url, fit=ft.BoxFit.CONTAIN, error_content=monogram)
    return ft.Semantics(
        exclude_semantics=True,
        content=ft.Container(
            content,
            width=size if width is None else width,
            height=size,
            padding=INSET,
            bgcolor=ft.Colors.WHITE,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            border_radius=CORNER,
            alignment=ft.Alignment.CENTER,
        ),
    )
