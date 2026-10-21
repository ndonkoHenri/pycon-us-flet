"""The folds screens share: ``FoldTile``, a controlled ``ExpansionTile``, and ``toggle_button()``.

One fold for every list that tucks part of itself away until it is tapped: session
detail's other rooms (D-186) and My schedule's "Earlier days" and "Earlier today"
(D-191). Each is controlled, as D-157 asks of text fields: Flutter reports the new
state, the screen keeps it, and its next render passes it back. Left to Flutter, the
next render would send the default and fold up a tile the user had just opened.

``toggle_button()`` is the text button that shows the rest of a list in place, or less
of it: a job card's "Show all 15 roles" (SPON-06) and Now's "Show all 10 sessions"
(D-327).
"""

from collections.abc import Callable

import flet as ft

from pycon_us.prefs import Prefs
from pycon_us.services.errors import report_errors
from pycon_us.ui.semantics import named

EXPAND_MS = 200
"""A fold's opening and closing, an M3 small change (ux.md §3.8); 0 under reduced motion."""


def expand_style(prefs: Prefs) -> ft.AnimationStyle:
    """Return a fold's animation: ``EXPAND_MS`` long, none under reduced motion (D-173).

    Flutter's ``ExpansionTile`` reads only the style's ``duration``, for both ways.

    Args:
        prefs: The preferences, for ``Prefs.motion_ms()``.
    """
    return ft.AnimationStyle(duration=prefs.motion_ms(EXPAND_MS))


def FoldTile(
    title: ft.Control,
    controls: list[ft.Control],
    *,
    expanded: bool,
    on_change: Callable[[bool], None],
    style: ft.AnimationStyle,
    leading: ft.Control | None = None,
    bgcolor: ft.ColorValue | None = None,
    controls_padding: ft.PaddingValue | None = None,
    lines: bool = False,
) -> ft.ExpansionTile:
    """Return a controlled fold tile: ``expanded`` comes from the screen's state.

    No divider lines above and below it when open (the default ``ExpansionTile``
    draws them) unless ``lines``, and what it holds is as wide as the tile.

    Args:
        title: What the tile says, folded or not.
        controls: What it holds when expanded.
        expanded: Whether it is open.
        on_change: Where the screen keeps whether it is open.
        style: Its animation (``expand_style()``).
        leading: The icon before the title.
        bgcolor: Its fill while open.
        controls_padding: The padding around what it holds.
        lines: Keep Material's lines above and below it while open, in the theme's
            divider colour (``outline`` in high contrast): the edge of a ``bgcolor``
            that HC's one surface hides (D-306).
    """

    @report_errors
    def changed(e: ft.Event[ft.ExpansionTile]) -> None:
        on_change(bool(e.data))

    no_border = ft.RoundedRectangleBorder()
    return ft.ExpansionTile(
        title=title,
        leading=leading,
        controls=controls,
        expanded=expanded,
        on_change=changed,
        animation_style=style,
        expanded_cross_axis_alignment=ft.CrossAxisAlignment.STRETCH,
        bgcolor=bgcolor,
        controls_padding=controls_padding,
        shape=None if lines else no_border,  # None: Flutter's lines while open
        collapsed_shape=no_border,
    )


def toggle_button(
    word: str,
    expanded: bool,
    on_click: ft.ControlEventHandler,
    identifier: str,
    label: str | None = None,
) -> ft.Control:
    """Return a text button that shows more of a list or card, or less, in place.

    Said "collapsed" or "expanded"; the visible words come first in its label, so
    "tap More" works for voice control users (WCAG 2.5.3).

    Args:
        word: Its visible words.
        expanded: Whether the list or card shows it all.
        on_click: Toggles it.
        identifier: Its semantics identifier, e.g. ``jobs.more.<id>`` (D-33).
        label: What a screen reader says, if more than the words.
    """
    button = ft.TextButton(
        content=ft.Text(word, semantics_label=label), on_click=on_click
    )
    return ft.Container(
        named(identifier, ft.Semantics(expanded=expanded, content=button)),
        # A text button's label sits 12 dp in: 4 + 12 lines it up with the text.
        padding=ft.Padding.only(left=4, top=4, right=4, bottom=4),
        alignment=ft.Alignment.CENTER_LEFT,
    )
