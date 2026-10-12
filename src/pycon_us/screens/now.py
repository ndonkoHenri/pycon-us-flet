"""Now, the start screen (``/now``): a stub until P1's dashboard (SCHED-25, D-14).

It shows the data's status; the other tab roots are in the bottom bar (D-13).
"""

import flet as ft

from pycon_us.screens.stub import note, stub_body
from pycon_us.services import use_services
from pycon_us.ui.navigation import use_scroll_to_top
from pycon_us.ui.scaffold import AppScaffold, search_button


@ft.component
def Now() -> ft.View:
    """The Now root: the data's status and the search."""
    svc = use_services()
    list_ref, scroll_to_top = use_scroll_to_top()
    return AppScaffold(
        title="Now",
        actions=[search_button(svc.memory, "all")],
        body=stub_body(
            [note("What's on now and your next session arrive in P1.")],
            status=True,
            auto_refresh=True,
            ref=list_ref,
        ),
        on_retap=scroll_to_top,
    )
