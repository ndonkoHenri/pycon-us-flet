"""More (``/more``): one flat, sectioned list instead of Ionic's drawer (D-15, ux.md §2.2).

A section shows once its pages exist, so no row is dead. In P0 that is **Programme**,
whose pages are stubs until P1, and **You**: Settings (P2, THEME-01), which took over
the Appearance rows that stood in for it here (D-169, D-286), then About this app and
Developer, which is always there when not embedded and, in a packaged build, once
unlocked in About this app (D-73, D-187). **Expo & sponsors** came with the Sponsors
page (#395), **At the venue** with Wi-Fi (D-280) and Help & safety (D-281), and
**About** with About the PSF (D-283); their other rows join with their P2 pages; the
profile row and Staff tools, first in the list, with P3's mock account (D-16, D-51).
Every row pushes its page, so Back returns here (D-17).
"""

from typing import NamedTuple

import flet as ft

from pycon_us.prefs import use_prefs
from pycon_us.services import use_services
from pycon_us.ui.navigation import use_scroll_to_top
from pycon_us.ui.rows import LinkTile
from pycon_us.ui.scaffold import AppScaffold, SectionHeader, search_button


class MoreEntry(NamedTuple):
    """A row of the More list: a page under ``/more`` (ux.md §2.2)."""

    title: str
    location: str
    icon: ft.IconData

    @property
    def identifier(self) -> str:
        """The semantics identifier UI tests find it by: ``more.<page>`` (section M)."""
        return "more." + self.location.removeprefix("/more/").replace("-", "_")


PROGRAMME = (
    MoreEntry("Speakers", "/more/speakers", ft.Icons.PEOPLE_OUTLINE),
    MoreEntry("Tracks & session types", "/more/tracks", ft.Icons.SELL_OUTLINED),
    MoreEntry("Keynotes", "/more/keynotes", ft.Icons.CO_PRESENT_OUTLINED),
    MoreEntry("Open spaces", "/more/open-spaces", ft.Icons.FORUM_OUTLINED),
    MoreEntry("Lightning talks", "/more/lightning-talks", ft.Icons.BOLT_OUTLINED),
    MoreEntry("Sprints", "/more/sprints", ft.Icons.ROCKET_LAUNCH_OUTLINED),
)
"""The Programme section, in the list's order (ux.md §2.2; icons §3.7)."""

EXPO_AND_SPONSORS = (
    MoreEntry("Sponsors", "/more/sponsors", ft.Icons.STOREFRONT_OUTLINED),
)
"""The Expo & sponsors section; Expo hall and Job listings join it with their pages."""

AT_THE_VENUE = (
    MoreEntry("Wi-Fi", "/more/wifi", ft.Icons.WIFI),
    MoreEntry("Help & safety", "/more/help", ft.Icons.SUPPORT_OUTLINED),
)
"""The At the venue section, in the list's order (ux.md §2.2; icons §3.7)."""

ABOUT = (MoreEntry("About the PSF", "/more/psf", ft.Icons.VOLUNTEER_ACTIVISM_OUTLINED),)
"""The About section, in the list's order (ux.md §2.2; icons §3.7)."""

SETTINGS = MoreEntry("Settings", "/more/settings", ft.Icons.SETTINGS_OUTLINED)
ABOUT_APP = MoreEntry("About this app", "/more/app", ft.Icons.INFO_OUTLINE)
DEVELOPER = MoreEntry(
    "Developer options", "/more/developer", ft.Icons.DEVELOPER_MODE_OUTLINED
)

MORE_PAGES = (
    *PROGRAMME,
    *EXPO_AND_SPONSORS,
    *AT_THE_VENUE,
    *ABOUT,
    SETTINGS,
    ABOUT_APP,
    DEVELOPER,
)
"""Every page the list links to; later phases add theirs with their sections."""


@ft.component
def More() -> ft.View:
    """The More root: its sections, the search, and a re-tap that scrolls to the top."""
    list_ref, scroll_to_top = use_scroll_to_top()
    svc = use_services()
    prefs = use_prefs()
    you = [SETTINGS, ABOUT_APP]
    if prefs.developer:
        you.append(DEVELOPER)
    return AppScaffold(
        title="More",
        actions=[search_button(svc.memory, "all")],
        body=ft.ListView(
            [
                SectionHeader("Programme"),
                *(link(entry) for entry in PROGRAMME),
                SectionHeader("Expo & sponsors"),
                *(link(entry) for entry in EXPO_AND_SPONSORS),
                SectionHeader("At the venue"),
                *(link(entry) for entry in AT_THE_VENUE),
                SectionHeader("About"),
                *(link(entry) for entry in ABOUT),
                SectionHeader("You"),
                *(link(entry) for entry in you),
            ],
            expand=True,
            ref=list_ref,
        ),
        on_retap=scroll_to_top,
    )


def link(entry: MoreEntry) -> ft.Control:
    """Return the row of one More page.

    Args:
        entry: The page.
    """
    return LinkTile(
        entry.title, entry.location, icon=entry.icon, identifier=entry.identifier
    )
