"""Semantics helpers shared by screens: ``named()``, an identifier on a control's own node.

UI flows find a control by its semantics identifier (``<screen>.<element>[.<key>]``,
D-33). D-190 settled how to attach one to a button or a row: merged, so that the
identifier and the control are one node (D-195).
"""

import flet as ft


def named(identifier: str, control: ft.Control) -> ft.Control:
    """Return ``control`` carrying ``identifier``, merged into one node with it.

    Merged because an identifier's ``Semantics`` alone is a node of its own: around a
    button it is an empty extra stop for TalkBack (seen in ``uiautomator dump``, D-190).

    Args:
        identifier: For UI flows, e.g. ``developer.reset_app``.
        control: The button or row that the identifier names.
    """
    return ft.MergeSemantics(
        content=ft.Semantics(identifier=identifier, content=control)
    )
