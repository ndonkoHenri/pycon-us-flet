"""Floor plan (``…/plan/<plan>``): a stub until the plans land in P2 (MAP-02, MAP-03).

A plan id comes from ``map.toml`` (a floor, ``expo`` or ``job-fair``); ``?pin=`` or
``?booth=`` will mark a place on it (ux.md §2.5).
"""

import flet as ft

from pycon_us.locations import use_query
from pycon_us.screens.stub import note, stub_view


@ft.component
def PlanViewer(plan_id: str) -> ft.View:
    """One floor plan: its id and view options, until P2.

    Args:
        plan_id: The plan id, unquoted.
    """
    options = use_query()
    shown = ", ".join(f"{key}={value}" for key, value in options.items()) or "none"
    return stub_view(
        title="Floor plan",
        controls=[note(f"Plan {plan_id!r} arrives in P2. View options: {shown}.")],
    )
