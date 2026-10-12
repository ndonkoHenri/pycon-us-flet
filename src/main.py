"""Entry point of the app: ``flet run`` and ``flet build`` start here.

``[tool.flet.app] path = "src"`` points both commands at this file. ``main()`` runs once
per session; on Android a new session can start in the same Python process (F26, F29),
so what must outlive a session lives at module level here.
"""

import logging

import flet as ft

from pycon_us import APP_NAME
from pycon_us.app import BOOT_COLOR, App
from pycon_us.state import ViewMemory

# INFO to stderr, which packaged apps capture in console.log (F14); #73 replaces this
# with setup_logging() and an asyncio exception handler.
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

MEMORY = ViewMemory()
"""One per process: a new session finds it as the last one left it (D-143)."""


def paint_first_view(page: ft.Page) -> None:
    """Give the page's default View the boot purple, before Flutter's first frame of it.

    Flet sends the page, with its default empty View, before ``main()`` runs, and Flutter
    removes its boot screen as soon as that arrives: one frame of the default View
    (white in light mode) showed between the purple boot screen and ``BootView`` (#72).
    """
    page.views[0].bgcolor = BOOT_COLOR


def main(page: ft.Page) -> None:
    """Render the app's views for this session; ``App`` does the rest."""
    page.title = APP_NAME
    page.render_views(App, MEMORY)


if __name__ == "__main__":
    ft.run(main, before_main=paint_first_view)
