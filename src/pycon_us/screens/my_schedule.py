"""My schedule (``/my-schedule``): a stub until favourites land in P1 (NEW-01)."""

import flet as ft

from pycon_us.screens.stub import note, stub_body
from pycon_us.ui.scaffold import AppScaffold


@ft.component
def MySchedule() -> ft.View:
    """The My schedule root: the data's status and a placeholder."""
    return AppScaffold(
        title="My schedule",
        body=stub_body([note("Saved sessions arrive in P1.")], status=True),
    )
