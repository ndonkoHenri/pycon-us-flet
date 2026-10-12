"""My schedule (``/my-schedule``): a stub until favourites land in P1 (NEW-01)."""

import flet as ft

from pycon_us.screens.stub import note, stub_view


@ft.component
def MySchedule() -> ft.View:
    """The My schedule root: its title only."""
    return stub_view(
        title="My schedule", controls=[note("Saved sessions arrive in P1.")]
    )
