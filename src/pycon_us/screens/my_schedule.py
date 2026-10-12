"""My schedule (``/my-schedule``): a stub until favourites land in P1 (NEW-01)."""

import flet as ft

from pycon_us.screens.stub import note, stub_body
from pycon_us.ui.navigation import use_scroll_to_top
from pycon_us.ui.scaffold import AppScaffold


@ft.component
def MySchedule() -> ft.View:
    """The My schedule root: the data's status and a placeholder."""
    list_ref, scroll_to_top = use_scroll_to_top()
    return AppScaffold(
        title="My schedule",
        body=stub_body(
            [note("Saved sessions arrive in P1.")], status=True, ref=list_ref
        ),
        on_retap=scroll_to_top,
    )
