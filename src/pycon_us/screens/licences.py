"""Licences (``/more/app/licences``): what each build ships, under whose licence (INFO-03).

The list opens with the app's own licence and its ``NOTICE``, then one row per bundled
component by section, each saying its licence and copyright; a row opens the full text
at ``/more/app/licences/<key>``, read from the files bundled with the app, so every
text opens offline (``pycon_us.licences``, D-296). Ionic showed none. The texts are
selectable and reflow to the screen at any text size (``paragraphs()``).
"""

from urllib.parse import unquote

import flet as ft

from pycon_us.licences import COMPONENTS, GROUPS, Component, paragraphs, read_text
from pycon_us.ui.info_page import GUTTER
from pycon_us.ui.rows import LinkTile
from pycon_us.ui.scaffold import AppScaffold, SectionHeader
from pycon_us.ui.states import not_found
from pycon_us.ui.widths import LIST, READING, sides, use_margin

SCREEN = "licences"
"""The list's name in its semantics identifiers: ``licences.<key>`` (decisions §M)."""

TEXT_SCREEN = "licence"
"""The text page's name in its semantics identifiers: ``licence.header``."""

TITLE = "Licences"
"""The list's title, and its row on About this app."""

LOCATION = "/more/app/licences"
"""The list's location, under About this app, so Back returns there (D-207's pattern)."""

NOT_FOUND = "This licence isn't in the app"
"""The empty state of an unknown key (ux.md §4.6)."""

FIXED_STYLE = ft.TextStyle(
    font_family="monospace",  # Android's alias; iOS has no such family
    font_family_fallback=["Menlo"],  # so iOS takes its system monospace font
)
"""A block laid out in columns, such as Python's table of releases, keeps them."""


def licence_href(component: Component) -> str:
    """Return the location of a component's text, below the list."""
    return f"{LOCATION}/{component.key}"


@ft.component
def Licences() -> ft.View:
    """The Licences list: the app and its notices, then each component by section."""
    margin = use_margin(LIST)  # its width class (D-305)
    rows: list[ft.Control] = []
    for group in GROUPS:
        rows.append(SectionHeader(group.title))
        rows.extend(
            LinkTile(
                c.name,
                licence_href(c),
                subtitle=f"{c.licence}\n{c.copyright}",
                identifier=f"{SCREEN}.{c.key}",
            )
            for c in group.components
        )
    return AppScaffold(
        title=TITLE,
        source=__name__,
        body=ft.ListView(rows, expand=True, padding=sides(margin, bottom=GUTTER)),
    )


@ft.component
def LicencePage() -> ft.View:
    """``/more/app/licences/<key>``: the route's screen, ``LicenceText`` for its key.

    Route params arrive quoted, as a link wrote them, and are unquoted here (D-42).
    """
    # Not ``key=``: a component's ``key`` keyword is its identity, which Flet keeps.
    return LicenceText(licence=unquote(ft.use_route_params().get("licence", "")))


@ft.component
def LicenceText(licence: str) -> ft.View:
    """One component's licence: its licence and copyright, then its full text.

    Args:
        licence: The component's key from the route (``Component.key``), unquoted.
    """
    margin = use_margin(READING)  # its width class (D-305)
    component = COMPONENTS.get(licence)
    # Read and split once per page: a re-render (a theme change) reads no file.
    blocks = ft.use_memo(
        lambda: paragraphs(read_text(component)) if component else [], [licence]
    )
    if component is None:
        return AppScaffold(
            title="Not found",
            source=__name__,
            body=ft.ListView(
                [
                    not_found(
                        NOT_FOUND,
                        icon=ft.Icons.DESCRIPTION_OUTLINED,
                        action="All licences",
                        location=LOCATION,
                        identifier=f"{TEXT_SCREEN}.not_found",
                    )
                ],
                expand=True,
                padding=sides(margin),
            ),
        )
    items: list[ft.Control] = [header(component)]
    items.extend(paragraph(block.text, fixed=block.fixed) for block in blocks)
    return AppScaffold(
        title=component.name,
        source=__name__,
        body=ft.ListView(
            items,
            expand=True,
            spacing=12,
            # The gutter inside the margins, which centre the text at 720 dp.
            padding=sides(margin + GUTTER, top=16, bottom=GUTTER),
        ),
    )


def header(component: Component) -> ft.Control:
    """Return the text's opening: its licence and its copyright, one node for readers."""
    return ft.Semantics(
        identifier=f"{TEXT_SCREEN}.header",
        container=True,
        content=ft.Column(
            spacing=4,
            controls=[
                ft.Text(
                    component.licence,
                    theme_style=ft.TextThemeStyle.TITLE_MEDIUM,
                    color=ft.Colors.ON_SURFACE,
                ),
                ft.Text(
                    component.copyright,
                    theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
            ],
        ),
    )


def paragraph(text: str, *, fixed: bool) -> ft.Control:
    """Return one block of the text: selectable, so it can be copied (D-26).

    A fixed block is not wrapped but scrolls sideways: Python's table of releases is
    80 columns wide, and wrapped on a phone its columns no longer line up.

    Args:
        text: The block, as ``paragraphs()`` gives it.
        fixed: Shown line for line in a monospace font (columns, rules).
    """
    block = ft.Text(
        text,
        selectable=True,
        no_wrap=fixed,
        theme_style=ft.TextThemeStyle.BODY_MEDIUM,
        color=ft.Colors.ON_SURFACE,
        style=FIXED_STYLE if fixed else None,
    )
    if not fixed:
        return block
    return ft.Row([block], scroll=ft.ScrollMode.AUTO)
