"""The folds screens share: `FoldTile`, the app's own fold, and `toggle_button()`.

One fold for every list that tucks part of itself away until it is tapped: session
detail's other rooms (D-186), My schedule's "Earlier days" and "Earlier today"
(D-191) and Lightning talks' doubts (D-205). Each is controlled, as D-157 asks of text
fields: the screen keeps whether it is open and passes it back on every render.

Not Flutter's `ExpansionTile`, whose Android header sits in a focus-blocked live
region labelled "Collapsed": TalkBack gave that label to the list item or card around
it, a stop that said only the state, before the header's own (#332, D-354). Here the
header is one `ListTile`, merged with the fold's identifier, whose chevron says the
state, so the fold is one stop: "Earlier days (6 sessions), Collapsed".

`toggle_button()` is the text button that shows the rest of a list in place, or less
of it: a job card's "Show all 15 roles" (SPON-06) and Now's "Show all 10 sessions"
(D-327).
"""

import math
from collections.abc import Callable

import flet as ft

from pycon_us.prefs import Prefs
from pycon_us.services.errors import report_errors
from pycon_us.ui.semantics import named

EXPAND_MS = 200
"""A fold's opening and closing, an M3 small change (ux.md §3.8); 0 under reduced motion."""

# The fold's state, said after its title: Flutter's own words for `ExpansionTile`.
COLLAPSED = "Collapsed"
EXPANDED = "Expanded"


def expand_style(prefs: Prefs) -> ft.Animation:
    """Return a fold's animation: `EXPAND_MS` long, none under reduced motion (D-173).

    Args:
        prefs: The preferences, for `Prefs.motion_ms()`.
    """
    return ft.Animation(prefs.motion_ms(EXPAND_MS), ft.AnimationCurve.EASE_IN_OUT)


def FoldTile(
    title: ft.Control,
    controls: list[ft.Control],
    *,
    expanded: bool,
    on_change: Callable[[bool], None],
    style: ft.Animation,
    identifier: str,
    leading: ft.Control | None = None,
    bgcolor: ft.ColorValue | None = None,
    controls_padding: ft.PaddingValue | None = None,
    lines: bool = False,
    live: bool = True,
) -> ft.Container:
    """Return a controlled fold: `expanded` comes from the screen's state.

    The header is a `ListTile` with a chevron that turns as it opens, its icons in
    `primary` while open and `on_surface_variant` while folded, as Material's
    `ExpansionTile`. It is one node with `identifier` (`named()`, D-214), read
    "<title>, Collapsed" or "<title>, Expanded": the chevron's label carries the
    state, since Android's bridge reports no expanded state (D-354). A live region,
    so the new state is said when a double tap changes it.

    What it holds is shown only while open, as wide as the fold, and its height
    grows and shrinks with `style`.

    Args:
        title: What the header says, folded or not.
        controls: What it holds when expanded.
        expanded: Whether it is open.
        on_change: Where the screen keeps whether it is open.
        style: Its animation (`expand_style()`).
        identifier: The header's semantics identifier, e.g.
            `my_schedule.earlier_days` (D-33).
        leading: The icon before the title.
        bgcolor: Its fill while open.
        controls_padding: The padding around what it holds.
        lines: Draw lines above and below it while open, in `outline`: the edge of
            a `bgcolor` that high contrast's one surface hides (D-306).
        live: The header is a live region. False while a sheet opens: TalkBack speaks a
            live region as it appears, over the sheet's title (#1074).
    """

    @report_errors
    def toggle(_: ft.Event[ft.ListTile]) -> None:
        on_change(not expanded)

    fill = bgcolor if expanded else None
    header = ft.ListTile(
        leading=leading,
        title=title,
        trailing=ft.Icon(
            ft.Icons.EXPAND_MORE,
            semantics_label=EXPANDED if expanded else COLLAPSED,
            rotate=ft.Rotate(math.pi if expanded else 0),
            animate_rotation=style,
        ),
        icon_color=ft.Colors.PRIMARY if expanded else ft.Colors.ON_SURFACE_VARIANT,
        # The tile's own fill, drawn as ink, so its ripple shows on it.
        bgcolor=fill,
        on_click=toggle,
    )
    line = ft.BorderSide(1, ft.Colors.OUTLINE)
    return ft.Container(
        ft.Column(
            [
                named(identifier, ft.Semantics(live_region=live, content=header)),
                ft.Container(
                    # Hidden, out of the screen reader's tree too, while folded.
                    ft.Column(
                        controls,
                        spacing=0,
                        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                        visible=expanded,
                    ),
                    padding=controls_padding if expanded else None,
                    bgcolor=fill,
                    animate_size=style,
                ),
            ],
            spacing=0,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        ),
        # A border with no fill hides no ink.
        border=ft.Border(top=line, bottom=line) if expanded and lines else None,
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
        identifier: Its semantics identifier, e.g. `jobs.more.<id>` (D-33).
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
