"""About the PSF (``/more/psf``): the PSF's mission, Donate, and where to go next.

The Python Software Foundation runs PyCon US. From the top (INFO-06, D-283):

- its mission, once, where Ionic showed it twice (its own card, then again in the
  feed's block under it);
- "Donate to the PSF", a ``FilledButton`` that opens the donation page in the in-app
  browser, marked as a link as an external row is (``links.external()``);
- "Get involved", "Python resources" and "Follow the PSF": level-2 sections of
  external ``LinkTile``s, each with its outlined icon or its brand's mark
  (``brand_icon()``, D-264); a social profile opens in its own app (INFO-14).

Everything comes from the year's ``content.toml`` (``[psf]``, D-45), so the page shows
at once and offline. A year without the table shows the feed's own ``about-psf``
block, and without that an empty state (``InfoBody``, D-263).
"""

from typing import cast

import flet as ft

from pycon_us.services import Services, use_services
from pycon_us.services.errors import report_errors
from pycon_us.ui.brands import brand_icon
from pycon_us.ui.buttons import ICON_PADDING
from pycon_us.ui.info_page import GUTTER, InfoBody
from pycon_us.ui.links import OPENS_IN, LinkKind, external, open_link
from pycon_us.ui.rows import LinkTile
from pycon_us.ui.scaffold import AppScaffold, SectionHeader
from pycon_us.ui.semantics import semantics_key
from pycon_us.ui.states import EmptyState
from pycon_us.year_links import PSF_SECTIONS, PsfInfo, PsfLink

SCREEN = "psf"
"""The page's name in its semantics identifiers (decisions §M)."""

TITLE = "About the PSF"
"""The page's name: its app bar's title and its More row."""

MISSION = "Mission"
DONATE = "Donate to the PSF"

SECTIONS = {
    "get_involved": "Get involved",
    "python_resources": "Python resources",
    "follow": "Follow the PSF",
}
"""Each section's heading, by its key in the year data (``year_links.PSF_SECTIONS``)."""

NO_PSF = "Nothing about the PSF yet"
NO_PSF_BODY = "It shows here as soon as the conference publishes it."
"""The empty state's way out: the next refresh may bring the feed's block (ux.md §4.6)."""


@ft.component
def AboutPsf() -> ft.View:
    """The About the PSF page: the year's mission, Donate and links, else the feed's."""
    svc = use_services()
    psf = svc.year.content.psf
    blocks = [] if psf is None else psf_blocks(svc, psf)
    empty = EmptyState(
        NO_PSF,
        icon=ft.Icons.INFO_OUTLINE,
        # No button: the app refreshes the feed on its own (D-175).
        body=NO_PSF_BODY,
        identifier=f"{SCREEN}.empty",
    )
    return AppScaffold(
        title=TITLE,
        source=__name__,
        body=InfoBody(blocks, block="about-psf", screen=SCREEN, empty=empty),
    )


def psf_blocks(svc: Services, psf: PsfInfo) -> list[ft.Control]:
    """Return the page's blocks: the mission, Donate, then each section's links.

    A section with no links has no heading either.

    Args:
        svc: The session's services, for the launcher.
        psf: The year's ``[psf]`` table.
    """
    blocks: list[ft.Control] = [
        SectionHeader(MISSION),
        mission(psf.mission),
        donate_button(svc, psf.donate_url),
    ]
    for section in PSF_SECTIONS:
        links = [link for link in psf.links if link.section == section]
        if links:
            blocks.append(SectionHeader(SECTIONS[section]))
            blocks.extend(link_row(link) for link in links)
    return blocks


def mission(text: str) -> ft.Control:
    """Return the mission statement: one paragraph in ``BODY_LARGE``, in the gutter.

    Args:
        text: The mission, as the PSF words it.
    """
    return ft.Semantics(
        identifier=f"{SCREEN}.mission",
        container=True,  # one node holds the text's, so the identifier has a home
        content=ft.Container(
            ft.Text(text, theme_style=ft.TextThemeStyle.BODY_LARGE),
            padding=ft.Padding.symmetric(horizontal=GUTTER),
        ),
    )


def donate_button(svc: Services, url: str) -> ft.Control:
    """Return "Donate to the PSF": a filled button that opens the donation page.

    It leaves the app, so its icon is ``OPEN_IN_NEW`` and its name ends with "Opens
    in browser", on the text, since an icon's label is read before the text (D-186);
    it is a link for screen readers, as an external row is (``links.external()``).
    It keeps its own width, at the gutter's start, and wraps at large text.

    Args:
        svc: The session's services, for the launcher.
        url: The donation page, from the year data.
    """

    @report_errors
    async def donate(e: ft.Event[ft.Button]) -> None:
        await open_link(svc, url, opener=e.control)

    button = ft.FilledButton(
        ft.Text(DONATE, semantics_label=f"{DONATE}\n{OPENS_IN[LinkKind.WEB]}"),
        icon=ft.Icons.OPEN_IN_NEW,
        on_click=donate,
        style=ft.ButtonStyle(padding=ICON_PADDING),
    )
    return ft.Container(
        ft.Column(
            [external(f"{SCREEN}.donate", button)],
            horizontal_alignment=ft.CrossAxisAlignment.START,
        ),
        padding=ft.Padding.only(left=GUTTER, top=16, right=GUTTER, bottom=8),
    )


def link_row(link: PsfLink) -> ft.Control:
    """Return one of the page's links: an external ``LinkTile`` with its mark or icon.

    It reads "Opens in browser", or, for a profile, "Opens in another app" (INFO-14).

    Args:
        link: The link, from the year data.
    """
    leading: ft.IconData | ft.Control | None = None
    if link.brand is not None:
        leading = brand_icon(link.brand)
    elif link.icon is not None:
        leading = cast(ft.IconData, getattr(ft.Icons, link.icon))
    return LinkTile(
        link.label,
        link.url,
        icon=leading,
        identifier=f"{SCREEN}.link.{semantics_key(link.label)}",
        app=link.app,
    )
