"""Now, the start screen (``/now``): a stub until P1's dashboard (SCHED-25, D-14).

It shows the data's status, and links to the other tab roots until the bottom bar lands
(#75).
"""

import flet as ft

from pycon_us.screens.stub import nav_tile, note, stub_body
from pycon_us.services import use_services
from pycon_us.ui.scaffold import AppScaffold, search_button

OTHER_ROOTS = (
    ("Schedule", "/schedule"),
    ("My schedule", "/my-schedule"),
    ("Map", "/map"),
    ("More", "/more"),
)
"""The other tab roots, in the bar's order (D-13)."""


@ft.component
def Now() -> ft.View:
    """The Now root: the data's status, links to the other roots, and the search."""
    svc = use_services()
    return AppScaffold(
        title="Now",
        actions=[search_button(svc.memory, "all")],
        body=stub_body(
            [
                note("The other tabs, until the bottom bar lands:"),
                *(nav_tile(label, root) for label, root in OTHER_ROOTS),
            ],
            status=True,
        ),
    )
