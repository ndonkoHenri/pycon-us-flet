"""`LinkTile`: the row that opens a link, a page or a copy of a phone number or address.

It opens its target by the link rule (INFO-14, `ui.links`): an in-app page is pushed
and its row ends in `CHEVRON_RIGHT`; a web page, a profile or a map leaves the app and
its row ends in `OPEN_IN_NEW`; a phone or email row has a Copy button beside it.
The speaker rows are `ui.rows`'s.
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
from pycon_us.ui.semantics import merged, named

PLAIN_TOP = 16
"""A row without a subtitle: its leading icon's distance from the top (`TITLE_HEIGHT`)."""

SUBTITLED_TOP = 14
"""A row with a subtitle: its title's and its icons' distance from the top (`_tile`)."""


def LinkTile(
    title: str | ft.Text,
    target: str,
    *,
    icon: ft.IconData | ft.Control | None = None,
    subtitle: str | ft.Control | None = None,
    identifier: str | None = None,
    app: bool = False,
    copy_identifier: str | None = None,
    stacked: bool = False,
) -> ft.Control:
    """Return a row that opens `target` by the link rule: a page or a link.

    A Material `ListTile`, so it is at least 56 dp tall (72 with a subtitle), more
    than the 48 dp target (D-33), and grows with the text. It is one node for screen
    readers, read as its title and subtitle: a button for a page; a link for anything
    else, whose `OPEN_IN_NEW` icon is read as "Opens in browser" (or "Opens in
    another app"). A phone or email row has a Copy button beside it, a stop of its
    own, as a session row's star is (ux.md §3.9).

    An in-app row is built here. An external one needs the session's services when it
    is tapped, so it is a component, which reads them (`use_services()`).

    Args:
        title: The row's text, in sentence case; a phone or email row says what a tap
            does ("Call the Code of Conduct hotline"). A `Text` for a title cut at
            some lines, as a session's name is (room detail's "Now in this room").
        target: Where a tap goes: a page (`/more/speakers`), for a detail
            `drill_href(view_path, ...)` so Back returns to this row's View, or a URL
            (`link_kind()`).
        icon: A leading icon, outlined (D-27); none for rows of names. A control
            stands as it is: a brand's mark beside a link to it (`brand_icon()`,
            D-264).
        subtitle: A second line, if any: for a phone or email row, the number or the
            address. A control for lines of their own (the Map's "Now:" line), read
            with the title as one phrase.
        identifier: The row's semantics identifier for UI tests, e.g.
            `more.speakers` (decisions §M); a Copy button gets `<identifier>.copy`.
        app: A web address opens in the app that handles it: a social profile, a map.
        copy_identifier: The Copy button's identifier, where the screen names it
            otherwise than `<identifier>.copy` (Help & safety's `help.copy.<kind>`).
        stacked: A link whose words matter more than its icons, at large text
            (`Prefs.time_above`): no leading icon, and the `OPEN_IN_NEW` icon under the
            title rather than beside it, so a long word stays whole (D-497). The node
            reads as before, title then "Opens in browser". Ignored on a row with a
            `subtitle`, or with no such icon (a page, a phone, an email).

    Raises:
        ValueError: `target` is not a link the app opens (`link_kind()`).
    """
    kind = link_kind(target, app=app)
    if kind is not LinkKind.PAGE:
        return _ExternalLinkTile(
            title,
            target,
            kind,
            icon=icon,
            subtitle=subtitle,
            identifier=identifier,
            copy_identifier=copy_identifier,
            stacked=stacked,
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
    title: str | ft.Text,
    target: str,
    kind: LinkKind,
    *,
    icon: ft.IconData | ft.Control | None,
    subtitle: str | ft.Control | None,
    identifier: str | None,
    copy_identifier: str | None = None,
    stacked: bool = False,
) -> ft.Control:
    """The external form of `LinkTile`: a link that leaves the app, maybe with Copy."""
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
    if stacked and trailing is not None and subtitle is None:
        # At the words' start: a ListTile's subtitle would centre a bare icon.
        icon, subtitle, trailing = None, ft.Row([trailing]), None
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
    button = ft.IconButton(
        ft.Icons.CONTENT_COPY_OUTLINED, tooltip=tooltip, on_click=copy
    )
    # One node either way, named by the tooltip (D-190, F55, D-234).
    if copy_identifier is None and identifier is not None:
        copy_identifier = f"{identifier}.copy"
    copy_button = (
        named(copy_identifier, button)
        if copy_identifier is not None
        else merged(button)
    )
    return ft.Row(
        [
            ft.Container(row, expand=True),
            # 12 dp from the edge puts the 24 dp icon of the 48 dp button where a
            # ListTile's trailing icon sits, so the column of icons lines up; from the
            # top it sits level with the leading icon (_tile), so at 200 % text it
            # stays beside the first line instead of the block's middle.
            ft.Container(
                copy_button,
                padding=ft.Padding.only(top=icon_top(subtitle) - 12, right=12),
            ),
        ],
        spacing=0,
        vertical_alignment=ft.CrossAxisAlignment.START,
    )


def _tile(
    title: str | ft.Text,
    icon: ft.IconData | ft.Control | None,
    subtitle: str | ft.Control | None,
    trailing: ft.Control | None,
    on_click: Callable[[], Any],
) -> ft.ListTile:
    """A link row's `ListTile`, its icons beside the title's first line at any height.

    M3's default centres the icons against the whole block, which at 200 % puts them
    beside the middle of a four-line title, far from the line they belong to. Without a
    subtitle, `TITLE_HEIGHT` centres a 56 dp row's icons and keeps them 16 dp from
    the top of a taller one. With a subtitle it would not do: it centres the trailing
    icon of a 72 dp row and moves both icons when the row grows (the Map's "Now:" line
    comes and goes with the minute), while the title moves the other way. So a row with
    a subtitle puts its icons and its title `SUBTITLED_TOP` from the top (`TOP`
    and `min_vertical_padding`): the 24 dp title line and the 24 dp icons share one
    centre, 26 dp down, at every height, and a two-line row stays 72 dp (14 + 24 + 20
    + 14).
    """
    if subtitle is None:
        alignment, padding = ft.ListTileTitleAlignment.TITLE_HEIGHT, None
    else:
        alignment, padding = ft.ListTileTitleAlignment.TOP, SUBTITLED_TOP
    return ft.ListTile(
        leading=ft.Icon(icon) if isinstance(icon, ft.IconData) else icon,
        title=title,
        subtitle=subtitle,
        trailing=trailing,
        on_click=on_click,
        title_alignment=alignment,
        min_vertical_padding=padding,
    )


def icon_top(subtitle: str | ft.Control | None) -> int:
    """Return how far `_tile` puts its leading icon from the row's top, in dp."""
    return PLAIN_TOP if subtitle is None else SUBTITLED_TOP
