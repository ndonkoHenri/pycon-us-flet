"""Entry point of the app: ``flet run`` and ``flet build`` start here.

``[tool.flet.app] path = "src"`` points both commands at this file. ``main()`` runs once
per session; on Android a new session can start in the same Python process (F26, F29),
so what must outlive a session lives at module level here.
"""

import flet as ft

from pycon_us import APP_NAME
from pycon_us.app import BOOT_COLOR, NO_THEME_ANIMATION, App
from pycon_us.services.errors import setup_logging
from pycon_us.state import ViewMemory

setup_logging()  # once per process, before the first session logs anything (D-72)

MEMORY = ViewMemory()
"""One per process: a new session finds it as the last one left it (D-143)."""


def prepare_first_page(page: ft.Page) -> None:
    """Set up the page Flet sends before ``main()`` runs, which Flutter shows at once (F35).

    * The default View gets the boot purple: Flutter removes its boot screen as soon as
      the page arrives, and one frame of that View (white in light mode) showed between
      the purple boot screen and ``BootView`` (#72).
    * Theme changes land without animation until ``bootstrap()`` opens the boot gate,
      from the first frame on: ``App``'s theme effect applies the default settings on
      mount, before ``bootstrap()`` has read the stored ones (D-161).
    """
    page.views[0].bgcolor = BOOT_COLOR
    page.theme_animation_style = NO_THEME_ANIMATION


def main(page: ft.Page) -> None:
    """Render the app's views for this session; ``App`` does the rest."""
    page.title = APP_NAME
    page.render_views(App, MEMORY)


if __name__ == "__main__":
    ft.run(main, before_main=prepare_first_page)
