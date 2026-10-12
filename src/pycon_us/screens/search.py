"""Search (``/search?scope=<scope>``): a stub of the global modal until P1 (NEW-02, D-19).

It shows its scope and where it was opened from, and a few sample results of that scope
that push details on top of it, so search → result → Back returns to the results.
"""

from itertools import islice

import flet as ft

from pycon_us.locations import drill_href, use_query
from pycon_us.screens.stub import nav_tile, note, stub_view
from pycon_us.services import use_services
from pycon_us.state import use_conference

SAMPLES = 3
"""How many results of each kind the stub shows."""


@ft.component
def Search() -> ft.View:
    """The global search: its scope, its opener and sample results."""
    view_path = ft.use_view_path()
    scope = use_query().get("scope", "all")
    svc = use_services()
    conference = use_conference()
    data = conference.data
    results: list[ft.Control] = []
    if data is not None:
        if scope in ("all", "sessions"):
            results += [
                nav_tile(s.name, drill_href(view_path, "session", s.id))
                for s in islice(data.sessions.values(), SAMPLES)
            ]
        if scope in ("all", "speakers"):
            results += [
                nav_tile(s.name, drill_href(view_path, "speaker", s.id))
                for s in islice(data.speakers.values(), SAMPLES)
            ]
        if scope in ("all", "rooms"):
            results += [
                nav_tile(r.name, drill_href(view_path, "room", r.slug))
                for r in islice(data.rooms.values(), SAMPLES)
            ]
    return stub_view(
        title="Search",
        controls=[
            note(f"Scope: {scope}. Opened from {svc.memory.search_base}."),
            *results,
        ],
    )
