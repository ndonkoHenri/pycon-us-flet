"""The content every stub screen shares, until each screen gets its real one.

``stub_body()`` lists a stub's rows under a line naming the View's path and params, so a
screenshot shows which level of a stack it is; ``note()`` and ``nav_tile()`` are its
rows. The chrome around them is ``ui.scaffold.AppScaffold`` (#76). Each P1 screen
replaces its stub content with its own, so this module shrinks to nothing.
"""

import flet as ft

from pycon_us.ui.rows import LinkTile
from pycon_us.ui.scaffold import StatusStrip


def stub_body(
    controls: list[ft.Control],
    *,
    status: bool = False,
    ref: ft.Ref[ft.ListView] | None = None,
) -> ft.ListView:
    """Return a stub screen's body: its View path and params, then its rows.

    A plain function that calls hooks, so a screen calls it exactly once per render,
    in every branch (hooks are unconditional, D-70).

    Args:
        controls: The rows.
        status: Start with the ``StatusStrip``, as the screens that show the feed's
            state do (Now, Schedule, My schedule; ux.md §5).
        ref: A tab root's list ref from ``use_scroll_to_top()``, so a re-tap of its
            tab scrolls the list to the top (D-144).

    Returns:
        A ``ListView`` that fills the View.
    """
    view_path = ft.use_view_path()
    params = ft.use_route_params()
    shown = ", ".join(f"{key}={value}" for key, value in params.items())
    route_line = note(f"{view_path}  {shown}".rstrip(), small=True)
    strip: list[ft.Control] = [StatusStrip()] if status else []
    return ft.ListView([*strip, route_line, *controls], expand=True, ref=ref)


def note(text: str, *, small: bool = False) -> ft.Control:
    """Return a line of body text with the list's side padding.

    Args:
        text: The text; selectable, so a route can be copied.
        small: Use the small body style, for route details.
    """
    style = ft.TextThemeStyle.BODY_SMALL if small else ft.TextThemeStyle.BODY_MEDIUM
    return ft.Container(
        ft.Text(text, theme_style=style, selectable=True),
        padding=ft.Padding.symmetric(horizontal=16, vertical=8),
    )


def nav_tile(title: str, location: str, *, subtitle: str | None = None) -> ft.Control:
    """Return a row that navigates to a location: a drill link, a page or a root.

    A ``ui.rows.LinkTile`` without an icon, as stub lists of names use it.

    Args:
        title: The row's text.
        location: Where a tap goes; for a detail, ``drill_href(view_path, ...)``.
        subtitle: A second line, if any.
    """
    return LinkTile(title, location, subtitle=subtitle)
