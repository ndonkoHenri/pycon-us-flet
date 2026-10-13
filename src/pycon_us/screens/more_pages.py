"""Stubs of the More pages that have no screen yet (``/more/<page>``, ux.md §2.2).

Each P1 issue replaces its page's stub with a screen module of its own (``speakers.py``,
``tracks.py``, ``open_spaces.py`` and ``lightning_talks.py`` already have one), so this module shrinks to nothing.
"""

import flet as ft

from pycon_us.screens.more import MORE_PAGES
from pycon_us.screens.stub import note, stub_body
from pycon_us.ui.scaffold import AppScaffold

TITLES = {entry.location: entry.title for entry in MORE_PAGES}


@ft.component
def MorePage() -> ft.View:
    """A More page without a screen yet: its title, from ``MORE_PAGES``."""
    view_path = ft.use_view_path()
    return AppScaffold(
        title=TITLES.get(view_path, "More"), body=stub_body([note("Arrives in P1.")])
    )
