"""The rows lists are made of (decisions §M): so far ``LinkTile``, a row that opens a link.

P1 adds the session, notice and speaker rows, the time gutter and ``LocationCard`` here
(ux.md §3.9).

``LinkTile`` opens its target by the link rule (INFO-14, ``ui.links``): an in-app page
is pushed and its row ends in ``CHEVRON_RIGHT``; a web page, a profile or a map leaves
the app and its row ends in ``OPEN_IN_NEW``; a phone or email row has a Copy button
beside it.
"""

from collections.abc import Callable
from typing import Any

import flet as ft

from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.ui.links import (
    COPY_TOOLTIPS,
    OPENS_IN,
    LinkKind,
    copy_contact,
    link_kind,
    open_link,
)


def LinkTile(
    title: str,
    target: str,
    *,
    icon: ft.IconData | None = None,
    subtitle: str | None = None,
    identifier: str | None = None,
    app: bool = False,
) -> ft.Control:
    """Return a row that opens ``target`` by the link rule: a page or a link.

    A Material ``ListTile``, so it is at least 56 dp tall (72 with a subtitle), more
    than the 48 dp target (D-33), and grows with the text. It is one node for screen
    readers, read as its title and subtitle: a button for a page; a link for anything
    else, whose ``OPEN_IN_NEW`` icon is read as "Opens in browser" (or "Opens in
    another app"). A phone or email row has a Copy button beside it, a stop of its
    own, as a session row's star is (ux.md §3.9).

    An in-app row is built here. An external one needs the session's services when it
    is tapped, so it is a component, which reads them (``use_services()``).

    Args:
        title: The row's text, in sentence case; a phone or email row says what a tap
            does ("Call the Code of Conduct hotline").
        target: Where a tap goes: a page (``/more/speakers``), for a detail
            ``drill_href(view_path, ...)`` so Back returns to this row's View, or a URL
            (``link_kind()``).
        icon: A leading icon, outlined (D-27); none for rows of names.
        subtitle: A second line, if any: for a phone or email row, the number or the
            address.
        identifier: The row's semantics identifier for UI tests, e.g.
            ``more.speakers`` (decisions §M); a Copy button gets ``<identifier>.copy``.
        app: A web address opens in the app that handles it: a social profile, a map.

    Raises:
        ValueError: ``target`` is not a link the app opens (``link_kind()``).
    """
    kind = link_kind(target, app=app)
    if kind is not LinkKind.PAGE:
        return _ExternalLinkTile(
            title, target, kind, icon=icon, subtitle=subtitle, identifier=identifier
        )
    page = ft.context.page

    @report_errors
    def go() -> None:
        page.navigate(target)

    tile = _tile(title, icon, subtitle, ft.Icon(ft.Icons.CHEVRON_RIGHT), go)
    # An identifier without a label of its own joins the merged node (D-166).
    if identifier is not None:
        tile = ft.Semantics(identifier=identifier, content=tile)
    return ft.MergeSemantics(content=tile)


@ft.component
def _ExternalLinkTile(
    title: str,
    target: str,
    kind: LinkKind,
    *,
    icon: ft.IconData | None,
    subtitle: str | None,
    identifier: str | None,
) -> ft.Control:
    """The external form of ``LinkTile``: a link that leaves the app, maybe with Copy."""
    svc = use_services()

    @report_errors
    async def launch() -> None:
        await open_link(svc, target, app=kind is LinkKind.APP)

    @report_errors
    async def copy() -> None:
        await copy_contact(svc, target)

    opens_in = OPENS_IN.get(kind)
    trailing = None
    if opens_in is not None:
        trailing = ft.Icon(ft.Icons.OPEN_IN_NEW, semantics_label=opens_in)
    row = ft.MergeSemantics(
        content=ft.Semantics(
            identifier=identifier,
            link=True,
            content=_tile(title, icon, subtitle, trailing, launch),
        )
    )
    tooltip = COPY_TOOLTIPS.get(kind)
    if tooltip is None:
        return row
    copy_button: ft.Control = ft.IconButton(
        ft.Icons.CONTENT_COPY_OUTLINED, tooltip=tooltip, on_click=copy
    )
    if identifier is not None:
        copy_button = ft.Semantics(identifier=f"{identifier}.copy", content=copy_button)
    return ft.Row(
        [
            ft.Container(row, expand=True),
            # 12 dp from the edge puts the 24 dp icon of the 48 dp button where a
            # ListTile's trailing icon sits, so the column of icons lines up; 4 dp from
            # the top puts it 16 dp down, level with the leading icon (_tile), so at
            # 200 % text it stays beside the first line instead of the block's middle.
            ft.Container(copy_button, padding=ft.Padding.only(top=4, right=12)),
        ],
        spacing=0,
        vertical_alignment=ft.CrossAxisAlignment.START,
    )


def _tile(
    title: str,
    icon: ft.IconData | None,
    subtitle: str | None,
    trailing: ft.Control | None,
    on_click: Callable[[], Any],
) -> ft.ListTile:
    """A link row's ``ListTile``, its icons beside the title's first line.

    ``TITLE_HEIGHT`` centres a one-line row's icons and puts them 16 dp from the top
    once a row grows past 72 dp (two lines at 200 % text), where M3's default centres
    them against the whole block, far from the title they belong to.
    """
    return ft.ListTile(
        leading=ft.Icon(icon) if icon is not None else None,
        title=title,
        subtitle=subtitle,
        trailing=trailing,
        on_click=on_click,
        title_alignment=ft.ListTileTitleAlignment.TITLE_HEIGHT,
    )
