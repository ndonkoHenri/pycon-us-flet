"""Tests for where the expo hall's zoom buttons sit at the fitted plan (#791, D-443).

On the 720 x 1600, 280-dpi AVD the buttons' column covered the lower 11 px of booth
709 at 1x, and on the iPhone 17 the whole of it. The hall sizes are the ones measured
on those devices; the arithmetic is ``screens/expo_layout.py``'s and the booths'
rectangles ``screens/expo_camera.py``'s, so a change of either is caught here.
"""

import pytest

from pycon_us.config import load_year
from pycon_us.screens.expo_camera import Rect, booth_rect
from pycon_us.screens.expo_layout import (
    COLUMN_DP,
    EDGE,
    ROW_DP,
    card_layout,
    over_plan,
)
from pycon_us.ui.zoom import BUTTON_DP
from pycon_us.ui.zoom_geometry import Size, fitted

YEAR = load_year(2026)
PLAN = YEAR.map.plan("expo")
assert PLAN is not None
NATURAL = (float(PLAN.width), float(PLAN.height))

HALLS = {
    # 720 / 1.75 dp wide; Zoom in's top and booth 709's bounds in #790's tree.
    "avd-720px": (720 / 1.75, 561.3),
    # The plan at y 355-640 and the row's Zoom in at 696-744 on iOS 26.5 (#791).
    "iphone17": (402.0, 525.0),
}
"""The hall's viewer, in dp, on the devices #791 checked."""


def buttons_rect(box: Size) -> Rect:
    """Where the zoom buttons sit with no card: at the bottom right, ``EDGE`` in.

    In their column (48 x 160 dp) or their row (160 x 48 dp), as ``card_layout()``
    lays them out for the hall at the fitted plan.
    """
    row, _ = card_layout(box[1], 0.0, crowded=over_plan(box, fitted(box, NATURAL)))
    width, height = (COLUMN_DP, ROW_DP) if row else (BUTTON_DP, COLUMN_DP)
    return box[0] - EDGE - width, box[1] - EDGE - height, width, height


def overlap(a: Rect, b: Rect) -> bool:
    """Whether two rectangles share any area."""
    return (
        a[0] < b[0] + b[2]
        and b[0] < a[0] + a[2]
        and a[1] < b[1] + b[3]
        and b[1] < a[1] + a[3]
    )


@pytest.mark.parametrize("hall", HALLS)
@pytest.mark.parametrize("number", [each.number for each in YEAR.map.booths])
def test_no_booth_sits_under_the_zoom_buttons_at_1x(hall: str, number: str) -> None:
    """At the fitted plan, with no card, the zoom buttons cover no part of a booth."""
    box = HALLS[hall]
    booth = next(each for each in YEAR.map.booths if each.number == number)
    assert not overlap(booth_rect(booth, box, NATURAL), buttons_rect(box))


@pytest.mark.parametrize("hall", HALLS)
def test_a_phone_in_portrait_puts_the_zoom_buttons_in_a_row(hall: str) -> None:
    """The column would reach over the plan's corner there, so the buttons go in a row."""
    box = HALLS[hall]
    assert over_plan(box, fitted(box, NATURAL))
    assert card_layout(box[1], 0.0, crowded=True)[0]


def test_a_tall_pane_keeps_the_column() -> None:
    """A pane with room under the plan, a tablet's, keeps the column (D-370)."""
    box = (800.0, 1100.0)
    assert not over_plan(box, fitted(box, NATURAL))
    assert not card_layout(box[1], 0.0, crowded=False)[0]


def test_before_the_layout_nothing_is_crowded() -> None:
    """A viewer not laid out yet has no plan to cover."""
    assert not over_plan((0.0, 0.0), (0.0, 0.0))
