"""More (``/more``): a stub of the flat list until P1 (D-15, ux.md §2.2).

It links to every More page the route table has, and keeps the Appearance control that
exercises ``Prefs.save()`` and the theme until Settings exists (P2, THEME-01).
"""

from typing import cast

import flet as ft

from pycon_us.prefs import Appearance, use_prefs
from pycon_us.screens.stub import nav_tile, note, stub_body
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.ui.navigation import use_scroll_to_top
from pycon_us.ui.scaffold import AppScaffold, SectionHeader, search_button

MORE_PAGES = (
    ("Speakers", "/more/speakers"),
    ("Tracks & session types", "/more/tracks"),
    ("Keynotes", "/more/keynotes"),
    ("Open spaces", "/more/open-spaces"),
    ("Lightning talks", "/more/lightning-talks"),
    ("Sprints", "/more/sprints"),
    ("About this app", "/more/app"),
    ("Developer", "/more/developer"),
)
"""The More pages of P1, in the list's order (ux.md §2.2); later phases add theirs."""

APPEARANCE_LABELS: dict[Appearance, str] = {
    "system": "System",
    "light": "Light",
    "dark": "Dark",
}


@ft.component
def More() -> ft.View:
    """The More root: its pages, the Appearance setting and the PSF note (D-36)."""
    list_ref, scroll_to_top = use_scroll_to_top()
    page = ft.context.page
    svc = use_services()
    prefs = use_prefs()

    @report_errors
    async def choose_appearance(e: ft.Event[ft.SegmentedButton]) -> None:
        theme = cast(Appearance, e.control.selected[0])
        if not await prefs.save(svc.storage, theme=theme):
            page.show_dialog(
                ft.SnackBar(
                    ft.Text("Couldn't save your change"),
                    behavior=ft.SnackBarBehavior.FLOATING,
                )
            )

    return AppScaffold(
        title="More",
        actions=[search_button(svc.memory, "all")],
        body=stub_body(
            [
                *(nav_tile(label, location) for label, location in MORE_PAGES),
                SectionHeader("Appearance"),
                ft.Container(
                    ft.SegmentedButton(
                        selected=[prefs.theme],  # controlled (D-157)
                        segments=[
                            ft.Segment(value=value, label=ft.Text(label))
                            for value, label in APPEARANCE_LABELS.items()
                        ],
                        on_change=choose_appearance,
                    ),
                    padding=ft.Padding.symmetric(horizontal=16, vertical=8),
                ),
                note("Not an official PSF app."),
            ],
            ref=list_ref,
        ),
        on_retap=scroll_to_top,
    )
