"""The expo's Map | List switch: the hall or its List, under the Map's Expo tab (#404).

``ExpoPane`` is what the Map's Expo tab and ``…/plan/expo`` show: a ``SegmentedButton``
over the hall (``screens/expo.py``) or the List (``screens/expo_list.py``). 61 small
targets on a raster are hard to reach with a screen reader or at large text, so the List
is an equal way to a booth (EXPO-01, EXPO-04), and the pane opens on it while a screen
reader is on (``Prefs.screen_reader``, Flutter's ``accessible_navigation``) until the
user picks a view. ``ViewMemory.expo_view`` keeps the pick for both places (D-18). A
List row's tap switches to the Map with its booth selected, so its card shows.
"""

import flet as ft

from pycon_us.memory import ViewMemory
from pycon_us.prefs import Prefs, use_prefs
from pycon_us.screens.expo import ExpoHall
from pycon_us.screens.expo_list import SCREEN, ExpoList
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.ui.widths import LIST, capped, use_margin

MAP = "map"
"""The Map view's value: ``ViewMemory.expo_view`` and its segment's."""

LIST_VIEW = "list"
"""The List view's value."""

VIEWS = {MAP: ("Map", ft.Icons.MAP_OUTLINED), LIST_VIEW: ("List", ft.Icons.LIST)}
"""Each view's segment: its label and icon, in the switch's order."""


def view_of(memory: ViewMemory, prefs: Prefs) -> str:
    """Return the view the pane shows: the user's pick, else the List under a reader.

    Args:
        memory: The process's ``ViewMemory``.
        prefs: The ``Prefs`` store, read for ``screen_reader``.
    """
    if memory.expo_view in VIEWS:
        return memory.expo_view
    return LIST_VIEW if prefs.screen_reader else MAP


@ft.component
def ExpoPane(zoom_key: str = "") -> ft.Control:
    """The expo: the Map | List switch over the hall or the List (EXPO-01, #404).

    Args:
        zoom_key: The hall's ``zoom_key``: the Map pane's slug, or the View's path
            for ``…/plan/expo``.
    """
    svc = use_services()
    prefs = use_prefs()
    margin = use_margin(LIST)
    memory = svc.memory
    _, set_switches = ft.use_state(0)  # a switch re-renders; the memory holds it
    view = view_of(memory, prefs)

    @report_errors
    def switched(e: ft.Event[ft.SegmentedButton]) -> None:
        memory.expo_view = e.control.selected[0]
        set_switches(lambda n: n + 1)

    @report_errors
    def picked(number: str) -> None:
        memory.expo_booth = number
        memory.expo_view = MAP
        set_switches(lambda n: n + 1)

    on_pick = ft.use_callback(picked, [])
    # Keyed, so Flet never moves one view's state into the other (F130).
    body = (
        ExpoHall(zoom_key, key=MAP)  # pyright: ignore[reportCallIssue]
        if view == MAP
        else ExpoList(on_pick, key=LIST_VIEW)  # pyright: ignore[reportCallIssue]
    )
    return ft.Column(
        [capped(view_switch(view, switched), margin), body],
        spacing=0,
        expand=True,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )


def view_switch(
    view: str, on_change: ft.ControlEventHandler[ft.SegmentedButton]
) -> ft.Control:
    """Return the Map | List ``SegmentedButton``, as wide as the screen's content.

    Each segment is read as its label, a button and its state; its identifier is
    ``expo.view.<view>``, merged into the segment's node as the Map's tabs' are.

    Args:
        view: The view shown, ``MAP`` or ``LIST_VIEW``.
        on_change: Called with the segment the user picks.
    """
    return ft.Container(
        ft.SegmentedButton(
            segments=[
                ft.Segment(
                    value=value,
                    icon=icon,
                    label=ft.Semantics(
                        identifier=f"{SCREEN}.view.{value}", content=ft.Text(label)
                    ),
                )
                for value, (label, icon) in VIEWS.items()
            ],
            selected=[view],
            on_change=on_change,
        ),
        padding=ft.Padding.only(left=16, top=8, right=16, bottom=4),
    )
