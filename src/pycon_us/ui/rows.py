"""The rows lists are made of (decisions §M): so far ``LinkTile``, a row that opens a page.

P1 adds the session, notice and speaker rows, the time gutter and ``LocationCard`` here
(ux.md §3.9), and #83 gives ``LinkTile`` its external form: ``OPEN_IN_NEW``, a link for
screen readers, and the link rule for web pages, apps, ``tel:`` and ``mailto:`` (§4.7).
"""

import flet as ft

from pycon_us.services.errors import report_errors


def LinkTile(
    title: str,
    location: str,
    *,
    icon: ft.IconData | None = None,
    subtitle: str | None = None,
    identifier: str | None = None,
) -> ft.Control:
    """Return a row that pushes an in-app page: a title and a trailing chevron.

    A Material ``ListTile``, so it is at least 56 dp tall (72 with a subtitle), more
    than the 48 dp target (D-33), and grows with the text. ``CHEVRON_RIGHT`` marks an
    in-app page (ux.md §3.7). The row is one node for screen readers, read as its title
    and subtitle, a button; the icons are decorative.

    Args:
        title: The row's text, in sentence case.
        location: Where a tap goes: a page (``/more/speakers``) or, for a detail,
            ``drill_href(view_path, ...)``, so Back returns to this row's View.
        icon: A leading icon, outlined (D-27); none for rows of names.
        subtitle: A second line, if any.
        identifier: The node's semantics identifier for UI tests, e.g.
            ``more.speakers`` (decisions §M).
    """
    page = ft.context.page

    @report_errors
    def go() -> None:
        page.navigate(location)

    tile: ft.Control = ft.ListTile(
        leading=ft.Icon(icon) if icon is not None else None,
        title=title,
        subtitle=subtitle,
        trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT),
        on_click=go,
    )
    # An identifier without a label of its own joins the merged node (D-166).
    if identifier is not None:
        tile = ft.Semantics(identifier=identifier, content=tile)
    return ft.MergeSemantics(content=tile)
