"""More (``/more``): one flat, sectioned list instead of Ionic's drawer (D-15, ux.md §2.2).

A section shows once its pages exist, so no row is dead. In P0 that is **Programme**,
whose pages are stubs until P1, and **You**: the Appearance control, which stands in for
Settings until P2 (THEME-01) and keeps exercising ``Prefs.save()`` and the theme (#72),
then About this app and Developer, which is always there when not embedded and, in a
packaged build, once unlocked in About this app (D-73, D-187). **Expo & sponsors**
came with the Sponsors page (#395), **At the venue** with Wi-Fi (D-280) and Help &
safety (D-281), and **About** with About the PSF (D-283); their other rows join with
their P2 pages; the profile row and Staff tools, first in the list, with P3's mock
account (D-16, D-51).
Every row pushes its page, so Back returns here (D-17).
"""

from typing import NamedTuple, cast

import flet as ft

from pycon_us.prefs import Appearance, use_prefs
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.ui.navigation import use_scroll_to_top
from pycon_us.ui.rows import LinkTile
from pycon_us.ui.scaffold import AppScaffold, SectionHeader, search_button
from pycon_us.ui.semantics import named


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

ABOUT_APP = MoreEntry("About this app", "/more/app", ft.Icons.INFO_OUTLINE)
DEVELOPER = MoreEntry(
    "Developer options", "/more/developer", ft.Icons.DEVELOPER_MODE_OUTLINED
)

MORE_PAGES = (
    *PROGRAMME,
    *EXPO_AND_SPONSORS,
    *AT_THE_VENUE,
    *ABOUT,
    ABOUT_APP,
    DEVELOPER,
)
"""Every page the list links to; later phases add theirs with their sections."""

APPEARANCE_LABELS: dict[Appearance, str] = {
    "system": "System",
    "light": "Light",
    "dark": "Dark",
}


@ft.component
def More() -> ft.View:
    """The More root: its sections, the search, and a re-tap that scrolls to the top."""
    list_ref, scroll_to_top = use_scroll_to_top()
    page = ft.context.page
    svc = use_services()
    prefs = use_prefs()

    @report_errors
    async def choose_appearance(e: ft.Event[ft.RadioGroup]) -> None:
        theme = cast(Appearance, e.control.value)
        if not await prefs.save(svc.storage, theme=theme):
            page.show_dialog(
                ft.SnackBar(
                    ft.Text("Couldn't save your change"),
                    behavior=ft.SnackBarBehavior.FLOATING,
                )
            )

    you = (ABOUT_APP, DEVELOPER) if prefs.developer else (ABOUT_APP,)
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
                appearance(prefs.theme, choose_appearance),
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


def appearance(
    selected: Appearance, on_change: ft.ControlEventHandler[ft.RadioGroup]
) -> ft.Control:
    """Return the Appearance setting: System, Light or Dark (D-23; Settings in P2).

    Radio rows, as Settings will have them (ux.md §6.9): the whole row is the target
    and reads as one control, and the rows reflow at any text size, where three
    segments in one row clipped "System" at 200 % on a 360 dp wide phone.

    Args:
        selected: ``Prefs.theme``; the group is controlled (D-157).
        on_change: Saves the choice.
    """
    # A heading, as a SectionHeader is, so screen readers can jump to the group (D-33);
    # level 3, a group inside "You" (D-211). Merged, since a ListTile is a node of its
    # own: unmerged, the heading was an unlabelled node around it (UiAutomation, #205).
    label = ft.MergeSemantics(
        content=ft.Semantics(
            header=True,
            heading_level=3,
            content=ft.ListTile(
                leading=ft.Icon(ft.Icons.PALETTE_OUTLINED),
                title="Appearance",
            ),
        )
    )
    options: list[ft.Control] = [
        named(
            f"more.appearance.{value}",
            ft.ListTile(
                leading=ft.Radio(value=value),
                title=text,
                toggle_inputs=True,  # a tap anywhere on the row selects it
            ),
        )
        for value, text in APPEARANCE_LABELS.items()
    ]
    return ft.Semantics(
        identifier="more.appearance",
        container=True,
        content=ft.Column(
            [
                label,
                ft.RadioGroup(
                    value=selected,
                    on_change=on_change,
                    content=ft.Column(options, spacing=0),
                ),
            ],
            spacing=0,
        ),
    )
