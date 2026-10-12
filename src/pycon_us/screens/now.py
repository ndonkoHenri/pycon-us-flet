"""Now, the start screen (``/now``): a stub until P1's dashboard (SCHED-25, D-14).

It links to the other tab roots until the bottom bar lands (#75), and logs when the
first screen has rendered with the feed (D-112's content line).
"""

import logging

import flet as ft

from pycon_us.screens.stub import nav_tile, note, search_button, stub_view
from pycon_us.services import use_services
from pycon_us.services.storage import THEME
from pycon_us.state import use_conference

logger = logging.getLogger(__name__)

OTHER_ROOTS = (
    ("Schedule", "/schedule"),
    ("My schedule", "/my-schedule"),
    ("Map", "/map"),
    ("More", "/more"),
)
"""The other tab roots, in the bar's order (D-13)."""


@ft.component
def Now() -> ft.View:
    """The Now root: links to the other roots, and the search."""
    svc = use_services()
    conference = use_conference()

    async def log_shown() -> None:
        # D-112's content line: a SharedPreferences round trip after the render, so the
        # patch has reached Flutter when it is logged.
        await svc.storage.get(THEME)
        logger.info(
            "Content shown: %s feed, version %d", conference.source, conference.version
        )

    ft.use_effect(log_shown, [conference.version])
    return stub_view(
        title="Now",
        actions=[search_button(svc.memory, "all")],
        controls=[
            note("The other tabs, until the bottom bar lands:"),
            *(nav_tile(label, root) for label, root in OTHER_ROOTS),
        ],
    )
