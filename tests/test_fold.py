"""`ui.fold.FoldTile`: one screen-reader stop per fold, its state said in its label (#332).

Flutter's `ExpansionTile` put a focus-blocked live region labelled "Collapsed" around
its header on Android, and TalkBack gave that label a stop of its own (D-354). The
app's own fold is a `ListTile` merged with its identifier, whose chevron says the
state; the screens' tests check how each one opens and stays open.
"""

import math
from collections.abc import Callable
from typing import cast

import flet as ft

from pycon_us.ui.fold import COLLAPSED, EXPANDED, FoldTile
from tests.folds import Fold, as_fold
from tests.trees import descendants


def build(*, expanded: bool, changes: list[bool] | None = None) -> Fold:
    """Return the parts of a fold of two rows, recording each change in `changes`."""
    seen = [] if changes is None else changes
    found = as_fold(
        FoldTile(
            ft.Text("Earlier days (2 sessions)"),
            [ft.Text("One"), ft.Text("Two")],
            expanded=expanded,
            on_change=seen.append,
            style=ft.Animation(200),
            identifier="my_schedule.earlier_days",
            leading=ft.Icon(ft.Icons.HISTORY),
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
            controls_padding=ft.Padding.only(left=40),
        )
    )
    assert found is not None
    return found


def test_the_header_is_one_node_with_its_identifier() -> None:
    """D-214, D-354: the identifier and the header merge into one node, a live region.

    No `Semantics` sits between the merge and the tile but the live region, so
    nothing but the header can take a stop of its own; the rows are outside it.
    """
    fold = build(expanded=False)
    merge = fold.root.content.controls[0]  # type: ignore[union-attr]
    assert isinstance(merge, ft.MergeSemantics)
    assert merge.content is fold.node
    assert fold.node.disabled is False  # said enabled, as the tile is (F42)
    nodes = [c for c in descendants(merge) if isinstance(c, ft.Semantics)]
    assert nodes == [fold.node, fold.node.content]
    assert not any(isinstance(c, ft.ExpansionTile) for c in descendants(fold.root))


def test_folded_it_says_collapsed_and_hides_its_rows() -> None:
    """Read "<title>, Collapsed"; the rows are not shown, nor in the screen reader's tree."""
    fold = build(expanded=False)
    assert fold.said == COLLAPSED
    assert fold.body.visible is False
    assert fold.box.padding is None
    assert fold.box.bgcolor is None
    assert fold.header.bgcolor is None
    chevron = cast(ft.Icon, fold.header.trailing)
    assert chevron.rotate == ft.Rotate(0)
    assert fold.header.icon_color == ft.Colors.ON_SURFACE_VARIANT


def test_open_it_says_expanded_and_shows_its_rows_on_its_fill() -> None:
    """Read "<title>, Expanded"; the chevron turns up and the icons take `primary`."""
    fold = build(expanded=True)
    assert fold.said == EXPANDED
    assert fold.body.visible is True
    assert [cast(ft.Text, c).value for c in fold.controls] == ["One", "Two"]
    assert fold.box.padding == ft.Padding.only(left=40)
    # The header's fill is its own, drawn as ink, so its ripple shows.
    assert fold.header.bgcolor == fold.box.bgcolor == ft.Colors.SURFACE_CONTAINER_LOW
    chevron = cast(ft.Icon, fold.header.trailing)
    assert chevron.rotate == ft.Rotate(math.pi)
    assert fold.header.icon_color == ft.Colors.PRIMARY
    assert fold.animation == ft.Animation(200)


def test_a_tap_on_the_header_asks_for_the_other_state() -> None:
    """Controlled (D-157): a tap reports the new state, which the screen passes back."""
    changes: list[bool] = []
    for expanded in (False, True):
        fold = build(expanded=expanded, changes=changes)
        handler = cast(Callable[[object], None], fold.header.on_click)
        handler(None)
    assert changes == [True, False]
