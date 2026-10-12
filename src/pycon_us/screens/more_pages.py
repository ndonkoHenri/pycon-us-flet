"""Stubs of the More pages that have no screen yet (``/more/<page>``, ux.md §2.2).

Each P1 issue replaces its page's stub with a screen module of its own (``speakers.py``
already has one), so this module shrinks to nothing.
"""

from urllib.parse import unquote

import flet as ft

from pycon_us.screens.more import MORE_PAGES
from pycon_us.screens.stub import note, stub_view

TITLES = {location: label for label, location in MORE_PAGES}


@ft.component
def MorePage() -> ft.View:
    """A More page without a screen yet: its title, from ``MORE_PAGES``."""
    view_path = ft.use_view_path()
    return stub_view(
        title=TITLES.get(view_path, "More"), controls=[note("Arrives in P1.")]
    )


@ft.component
def Track() -> ft.View:
    """``/more/tracks/<slug>``: one track's sessions, from P1 (SCHED-21)."""
    slug = unquote(ft.use_route_params().get("slug", ""))
    return stub_view(title="Track", controls=[note(f"Track {slug!r} arrives in P1.")])
