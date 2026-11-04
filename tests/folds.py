"""Helpers that read a `ui.fold.FoldTile` in a built tree: its header, state and rows."""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import cast

import flet as ft

from pycon_us.ui import fold


@dataclass(frozen=True)
class Fold:
    """A `FoldTile`'s parts: its identifier's node, its header and what it holds."""

    root: ft.Container
    node: ft.Semantics
    header: ft.ListTile
    box: ft.Container
    body: ft.Column

    @property
    def identifier(self) -> str:
        """The header's semantics identifier."""
        return str(self.node.identifier)

    @property
    def title(self) -> ft.Control:
        """What the header says, folded or not."""
        return cast(ft.Control, self.header.title)

    @property
    def said(self) -> str:
        """The state the header's chevron says: "Collapsed" or "Expanded"."""
        return str(cast(ft.Icon, self.header.trailing).semantics_label)

    @property
    def expanded(self) -> bool:
        """Whether it is open: it says so, and shows what it holds."""
        assert self.body.visible is (self.said == fold.EXPANDED)
        return self.said == fold.EXPANDED

    @property
    def animation(self) -> ft.Animation:
        """How its height grows and shrinks, and its chevron turns."""
        chevron = cast(ft.Icon, self.header.trailing)
        assert chevron.animate_rotation == self.box.animate_size
        return cast(ft.Animation, self.box.animate_size)

    @property
    def controls(self) -> list[ft.Control]:
        """What it holds, shown or not."""
        return list(self.body.controls)


def as_fold(control: ft.BaseControl) -> Fold | None:
    """Return `control`'s parts when it is a `FoldTile`, else None."""
    if not isinstance(control, ft.Container) or not isinstance(
        column := control.content, ft.Column
    ):
        return None
    match column.controls:
        case [ft.MergeSemantics(content=ft.Semantics() as node), ft.Container() as box]:
            pass
        case _:
            return None
    live = node.content
    if (
        not node.identifier
        or not isinstance(live, ft.Semantics)
        or not live.live_region
    ):
        return None
    header, body = live.content, box.content
    if not isinstance(header, ft.ListTile) or not isinstance(body, ft.Column):
        return None
    return Fold(control, node, header, box, body)


def folds(controls: Iterable[ft.BaseControl]) -> list[Fold]:
    """Return the `FoldTile`s among `controls`, in their order."""
    return [found for control in controls if (found := as_fold(control))]


def fold_named(controls: Iterable[ft.BaseControl], identifier: str) -> Fold:
    """Return the one `FoldTile` among `controls` whose header is `identifier`."""
    (found,) = [f for f in folds(controls) if f.identifier == identifier]
    return found
