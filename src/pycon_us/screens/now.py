"""Now, the start screen (``/now``): a stub until P1's dashboard (SCHED-25, D-14).

It shows the data's status and today's date by ``clock.now()``, so the Developer fake
clock shows here (D-184); the other tab roots are in the bottom bar (D-13).
"""

import flet as ft

from pycon_us import clock
from pycon_us.core.timefmt import day_heading, today
from pycon_us.screens.stub import note, stub_body
from pycon_us.services import use_services
from pycon_us.ui.navigation import use_scroll_to_top
from pycon_us.ui.scaffold import AppScaffold, search_button


@ft.component
def Now() -> ft.View:
    """The Now root: the data's status, today's date and the search."""
    svc = use_services()
    list_ref, scroll_to_top = use_scroll_to_top()
    info = svc.year.conference
    day = day_heading(today(clock.now(), info.zone))
    return AppScaffold(
        title="Now",
        actions=[search_button(svc.memory, "all")],
        body=stub_body(
            [
                ft.Semantics(
                    identifier="now.today",
                    content=note(f"Today in {info.time_zone_name}: {day}"),
                ),
                note("What's on now and your next session arrive in P1."),
            ],
            status=True,
            auto_refresh=True,
            ref=list_ref,
        ),
        on_retap=scroll_to_top,
    )
