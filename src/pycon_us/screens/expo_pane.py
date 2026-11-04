"""The expo's Map | List switch: the hall or its List, under the Map's Expo tab (#404).

`ExpoPane` is what the Map's Expo tab and `…/plan/expo` show: a `SegmentedButton`
over the hall (`screens/expo.py`) or the List (`screens/expo_list.py`). 61 small
targets on a raster are hard to reach with a screen reader or at large text, so the List
is an equal way to a booth (EXPO-01, EXPO-04), and the pane opens on it while a screen
reader is on (`Prefs.screen_reader`, Flutter's `accessible_navigation`) until the
user picks a view. `ViewMemory.expo_view` keeps the pick for both places (D-18). A
List row's tap switches to the Map with its booth selected, so its card shows, and
brought into view above the card (D-377).

`…/plan/expo?booth=613` (`ExpoPlan`'s `link`) seeds the pane once, as a row's tap
does (EXPO-05, D-164); a number the plan doesn't draw opens the List under a live line,
"Booth 139 isn't on the map yet", until the user switches or picks, filtered to that
number from its top, so whatever was typed before, the booth's exhibitor is what it
shows (#643).
"""

from collections.abc import Collection

import flet as ft

from pycon_us.memory import ViewMemory
from pycon_us.prefs import Prefs, use_prefs
from pycon_us.screens.expo import ExpoHall
from pycon_us.screens.expo_list import SCREEN, ExpoList
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.ui.widths import LIST, capped, use_margin

MAP = "map"
"""The Map view's value: `ViewMemory.expo_view` and its segment's."""

LIST_VIEW = "list"
"""The List view's value."""

VIEWS = {MAP: ("Map", ft.Icons.MAP_OUTLINED), LIST_VIEW: ("List", ft.Icons.LIST)}
"""Each view's segment: its label and icon, in the switch's order."""


def seed(memory: ViewMemory, number: str, placed: Collection[str]) -> tuple[str, str]:
    """Open the pane at a link's booth: selected on the Map, or the List (EXPO-05).

    A booth on the plan is selected and shown on the Map, as a List row's tap does.
    Any other number is the List's: its filter becomes the number and its scroll its
    top, so the List shows the booth's exhibitor whatever was typed before (#643);
    the remembered view is left alone, as the line is not the user's pick.

    Args:
        memory: The process's `ViewMemory`.
        number: `?booth=`'s number; empty for none.
        placed: The numbers of the booths the plan draws.

    Returns:
        `(reveal, missing)`: the booth to bring into view, or the number the plan
        doesn't draw; both empty without a link.
    """
    if not number:
        return "", ""
    if number not in placed:
        # Not cleared: the exhibitor would sit under "Not on the map yet", at the end.
        memory.expo_query = number
        memory.expo_offset = 0.0
        return "", number
    memory.expo_booth = number
    memory.expo_view = MAP
    return number, ""


def missing_line(number: str) -> str:
    """Return the line over the List for a link's booth that the plan doesn't draw."""
    return f"Booth {number} isn't on the map yet"


def view_of(memory: ViewMemory, prefs: Prefs) -> str:
    """Return the view the pane shows: the user's pick, else the List under a reader.

    Args:
        memory: The process's `ViewMemory`.
        prefs: The `Prefs` store, read for `screen_reader`.
    """
    if memory.expo_view in VIEWS:
        return memory.expo_view
    return LIST_VIEW if prefs.screen_reader else MAP


@ft.component
def ExpoPane(zoom_key: str = "", link: str = "") -> ft.Control:
    """The expo: the Map | List switch over the hall or the List (EXPO-01, #404).

    Args:
        zoom_key: The hall's `zoom_key`: the Map pane's slug, or the View's path
            for `…/plan/expo`.
        link: `?booth=`'s number, for `…/plan/expo` (EXPO-05); empty for none.
    """
    svc = use_services()
    prefs = use_prefs()
    margin = use_margin(LIST)
    memory = svc.memory
    # Once, as the pane mounts, before the hall reads the memory: the link's booth.
    placed = {booth.number for booth in svc.year.map.booths}
    picks, set_picks = ft.use_state(lambda: seed(memory, link, placed))
    reveal, missing = picks
    _, set_switches = ft.use_state(0)  # a switch re-renders; the memory holds it
    view = LIST_VIEW if missing else view_of(memory, prefs)

    @report_errors
    def switched(e: ft.Event[ft.SegmentedButton]) -> None:
        memory.expo_view = e.control.selected[0]
        set_picks(("", ""))
        set_switches(lambda n: n + 1)  # the same picks re-render nothing

    @report_errors
    def picked(number: str) -> None:
        memory.expo_booth = number
        memory.expo_view = MAP
        set_picks((number, ""))
        set_switches(lambda n: n + 1)

    on_pick = ft.use_callback(picked, [])
    # Keyed, so Flet never moves one view's state into the other (F130).
    body = (
        ExpoHall(zoom_key, reveal, key=MAP)  # pyright: ignore[reportCallIssue]
        if view == MAP
        else ExpoList(on_pick, key=LIST_VIEW)  # pyright: ignore[reportCallIssue]
    )
    top = [capped(view_switch(view, switched), margin)]
    if missing:
        top.append(capped(missing_note(missing), margin))
    return ft.Column(
        [*top, body],
        spacing=0,
        expand=True,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )


def view_switch(
    view: str, on_change: ft.ControlEventHandler[ft.SegmentedButton]
) -> ft.Control:
    """Return the Map | List `SegmentedButton`, as wide as the screen's content.

    Each segment is read as its label, a button and its state; its identifier is
    `expo.view.<view>`, merged into the segment's node as the Map's tabs' are.

    Args:
        view: The view shown, `MAP` or `LIST_VIEW`.
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


def missing_note(number: str) -> ft.Control:
    """Return the line over the List for a link's booth the plan doesn't draw.

    A polite live region, so a screen reader says why the List opened (ux.md §9).

    Args:
        number: The link's booth number.
    """
    note = ft.Text(
        missing_line(number),
        theme_style=ft.TextThemeStyle.BODY_MEDIUM,
        color=ft.Colors.ON_SURFACE_VARIANT,
    )
    return ft.Semantics(
        live_region=True,
        identifier=f"{SCREEN}.missing",
        content=ft.Container(
            note, padding=ft.Padding.symmetric(horizontal=16, vertical=4)
        ),
    )
