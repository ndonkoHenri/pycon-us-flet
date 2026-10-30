"""Where the expo hall's bottom column goes: the zoom buttons and the booth card (D-370).

``ExpoHall`` (``screens/expo.py``) stacks the zoom buttons over the booth card
(``screens/booth_card.py``) in one bottom ``Column``, ``EDGE`` in from the pane's
edges. This module's pure arithmetic says whether the buttons go in their 160 dp
column or a 48 dp row, how high the card's body may grow before it scrolls, and how
much of the pane the column covers, so a booth brought into view lands above it
(D-377):

- **A row** in a pane too short for the column (landscape), under a card so tall the
  column would leave less than ``BAND`` of plan, and wherever the column would reach
  over the fitted plan: on a phone in portrait it covered part of booth 709 at 1x
  (#791, D-443).
- **The body's box** is half the pane, or what the buttons and insets leave.
"""

from pycon_us.ui.zoom import BUTTON_DP
from pycon_us.ui.zoom_geometry import Size

EDGE = 16
"""The bottom column's inset from the pane's edges, and its gap between buttons and card."""

CARD_PADDING = (8, 16)
"""The card's padding above and below its body, in dp."""

BODY_TOP = 8
"""The body's own padding above its measured content, inside the scroll box, in dp."""

COLUMN_DP = 3 * BUTTON_DP + 2 * 8
"""The zoom buttons' height in their column (``zoom_buttons()``): 160 dp."""

ROW_DP = BUTTON_DP
"""The zoom buttons' height in a row: 48 dp."""

# Around the body box: the insets above and below the column, the gap, the card's padding.
_AROUND = 3 * EDGE + sum(CARD_PADDING)

ROW_UNDER = 2 * (COLUMN_DP + _AROUND)
"""A pane shorter than this, in dp, puts the zoom buttons in a row (D-370).

At this height half the pane is exactly what the buttons' column leaves the body.
"""


BAND = COLUMN_DP - ROW_DP
"""The least plan the column leaves above a tall card before the buttons go in a row.

112 dp, what the row gives back: a booth brought into view needs a band to land in
(D-377), and at the fitted plan a 2026 booth is under 42 dp high.
"""


def over_plan(box: Size, shown: Size) -> bool:
    """Return whether the zoom buttons' column, at the fitted plan, reaches over it.

    The column sits at the pane's bottom right, ``EDGE`` in; the plan is centred in
    the viewer. On a phone in portrait the column reached over the plan's lower
    right corner: Zoom in covered part of booth 709 at 1x (#791, D-443).

    Args:
        box: The viewer's size; ``(0, 0)`` before its first layout.
        shown: The plan's fitted size (``ui.zoom_geometry.fitted()``).
    """
    if not (box[0] and shown[0]):
        return False  # not laid out yet
    left = box[0] - EDGE - BUTTON_DP
    top = box[1] - EDGE - COLUMN_DP
    return (box[0] + shown[0]) / 2 > left and (box[1] + shown[1]) / 2 > top


def card_layout(
    pane: float, measured: float, *, crowded: bool = False
) -> tuple[bool, float | None]:
    """Return whether the zoom buttons go in a row, and the card body's scroll box.

    The box is half the pane, or less when the buttons, the gap, the card's padding
    and the pane's insets leave less, so the zoom buttons always stay in the pane
    (D-370): a Stack clips what goes past its top. The buttons go in a row in a short
    pane, when their column would reach over the fitted plan (``crowded``, D-443),
    and when a tall card under their column would leave less than ``BAND`` of the
    plan above it (D-377).

    Args:
        pane: The pane's height (the viewer's measured height); 0 before it is known.
        measured: The body's measured content height; 0 before it is known.
        crowded: ``over_plan()`` for the viewer: the column would cover the plan.

    Returns:
        ``(row, box)``: ``row`` puts the buttons in a row; ``box`` is None while the
        body, with its own top padding, fits.
    """
    row = (
        0 < pane < ROW_UNDER
        or crowded
        or (
            pane > 0
            and measured > 0
            and pane - _cover(pane, measured, row=False) < BAND
        )
    )
    return row, _box(pane, measured, row=row)


def covered(pane: float, measured: float, *, crowded: bool = False) -> float:
    """Return how much of the pane, from its bottom, the card and the zoom buttons take.

    The bottom column as ``card_layout()`` lays it out, with an inset above it too:
    what lies higher is in sight (D-377).

    Args:
        pane: The pane's height (the viewer's measured height).
        measured: The card body's measured content height.
        crowded: ``over_plan()`` for the viewer, as ``card_layout()`` takes it.
    """
    row, _ = card_layout(pane, measured, crowded=crowded)
    return _cover(pane, measured, row=row)


def _box(pane: float, measured: float, *, row: bool) -> float | None:
    """Return the card body's scroll box with the buttons laid out so, None if it fits."""
    room = pane - (ROW_DP if row else COLUMN_DP) - _AROUND
    box = max(0.0, min(pane / 2, room))
    return box if pane and measured + BODY_TOP > box else None


def _cover(pane: float, measured: float, *, row: bool) -> float:
    """Return what the bottom column covers with the buttons laid out so, in dp."""
    box = _box(pane, measured, row=row)
    body = box if box is not None else BODY_TOP + measured
    return _AROUND + max(body, BUTTON_DP) + (ROW_DP if row else COLUMN_DP)
