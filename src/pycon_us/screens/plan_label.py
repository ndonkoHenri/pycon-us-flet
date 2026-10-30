"""The floor viewer's label card: the pin's name, clear of the pin at any text size.

The card sits bottom-left over the plan, outside the zoom layer (ux.md §6.1 item 3).
At iOS's largest text with Bold Text it grew over half the Concourse plan and hid
Room 103's pin at fit (#793), so its height is bound by what the fitted plan leaves
under the pin, and its words scroll inside it, as the booth card's body does (D-370,
D-444).
"""

import flet as ft

from pycon_us.ui.semantics import named
from pycon_us.ui.zoom_geometry import Size
from pycon_us.year_map import Pin, Plan

SCREEN = "plan"
"""The floor viewer's name in its semantics identifiers (decisions §M)."""

PIN_BOX = 48
"""The pin's box, centred on its point: room for the ring at its widest."""

EDGE = 16
"""The card and the zoom buttons' inset from the body's edges, in dp."""

LABEL_MIN = 72
"""The label card's least height bound: above its height at the default text size."""


def label_room(box: Size, shown: Size, pin: Pin) -> float | None:
    """Return how tall the label card may grow: down from under the pin at fit.

    The plan is centred in the viewer and the card sits ``EDGE`` above its bottom, so
    a card no taller than the space from the pin's ring, at its widest, to there
    leaves the pin in sight at the fitted plan at any text size (#793, D-444). Fixed
    by the fitted plan, never the zoom, so the card does not resize while the user
    zooms. Never under ``LABEL_MIN``, so the card shows at least its first line.

    Args:
        box: The viewer's size; ``(0, 0)`` before its first layout.
        shown: The plan's fitted size (``ui.zoom_geometry.fitted()``).
        pin: The pin on the plan.

    Returns:
        The card's greatest height in dp, or None before the viewer is laid out.
    """
    if not box[1]:
        return None
    under = (box[1] - shown[1]) / 2 + pin.y / 100 * shown[1] + PIN_BOX / 2
    return max(LABEL_MIN, box[1] - EDGE - under)


def label_card(plan: Plan, pin: Pin, room: float | None = None) -> ft.Control:
    """Return the label card: the pin's name over its plan and what happens there.

    Outside the zoom layer, so it reads the same at any zoom; one node for screen
    readers ("Room 104C, Concourse level · Talk track"), ``plan.label``. Its words
    scroll inside it when they are taller than ``room`` (``label_room()``), as the
    booth card's body does (D-370).

    Args:
        plan: The plan shown.
        pin: The pin on it.
        room: The card's greatest height, or None before the viewer is laid out.
    """
    where = " · ".join(part for part in (plan.title, pin.sublabel) if part)
    lines = ft.Column(
        [
            ft.Text(pin.label, theme_style=ft.TextThemeStyle.TITLE_SMALL),
            ft.Text(where, theme_style=ft.TextThemeStyle.BODY_MEDIUM),
        ],
        spacing=2,
        tight=True,
        scroll=ft.ScrollMode.AUTO,
    )
    card = ft.Card(
        ft.Container(lines, padding=ft.Padding.symmetric(horizontal=16, vertical=12)),
        margin=0,
        max_height=room,
    )
    return named(f"{SCREEN}.label", card)
