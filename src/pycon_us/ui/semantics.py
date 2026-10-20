"""Semantics helpers shared by screens: ``named()``, ``merged()`` and ``semantics_key()``.

UI flows find a control by its semantics identifier (``<screen>.<element>[.<key>]``,
D-33). D-190 settled how to attach one to a button or a row: merged, so that the
identifier and the control are one node (D-198), which says whether the control is
disabled (D-214). ``merged()`` makes a button with a tooltip one node named by the
tooltip, where it needs no identifier (F55, D-234). ``semantics_key()`` turns an id
into the identifier's key (decisions §M; D-200): it is ``core.slugs``', which has no
Flet, so the year-data loader can use it too (D-283), and is re-exported here.
"""

import flet as ft

from pycon_us.core.slugs import semantics_key

__all__ = ["merged", "named", "semantics_key"]


def named(identifier: str, control: ft.Control) -> ft.Control:
    """Return ``control`` carrying ``identifier``, merged into one node with it.

    Merged because an identifier's ``Semantics`` alone is a node of its own: around a
    button it is an empty extra stop for TalkBack (seen in ``uiautomator dump``, D-190).

    The ``Semantics`` takes ``control``'s ``disabled``: Flet's says it is enabled
    unless it is disabled itself, whatever the control under it says, and the merged
    node kept that "enabled", so a disabled row read as enabled (F42, D-214). Read
    from the control, so callers pass no keyword for it. Only from ``control``
    itself, though: a ``Semantics`` passed in place of the button (to add a label or
    ``expanded``) says "enabled" in turn, so give it the button's ``disabled`` too.

    The one way to put an identifier on a button, chip or row (ux.md §9). A merge
    takes in every descendant, so a control with a button inside it (a field with a
    picker) needs another shape, as ``SearchField``'s (D-189).

    Args:
        identifier: For UI flows, e.g. ``developer.reset_app``.
        control: The button or row that the identifier names.
    """
    return ft.MergeSemantics(
        content=ft.Semantics(
            identifier=identifier, disabled=control.disabled, content=control
        )
    )


def merged(button: ft.Control) -> ft.MergeSemantics:
    """Return ``button`` merged into one node with its tooltip, which names it.

    Flet puts a control's ``tooltip`` around the whole control, where Flutter's own
    ``IconButton(tooltip=...)`` puts it inside the button's node: so the tooltip is a
    node of its own over the button, and the button under it has no name (F55). The
    merge makes the two one node, a button named by its tooltip, as Flutter's own
    would be (D-234). For a button that also carries an identifier, ``named()``
    merges both.

    Args:
        button: A button whose ``tooltip`` is its name, e.g. the app bar's Back arrow.
    """
    return ft.MergeSemantics(content=button)
