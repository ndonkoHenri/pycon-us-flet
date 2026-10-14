"""The app bar's overflow menus: ``overflow_menu()`` and its items, ``menu_item()``.

Session detail, the Sprints page and a track's page each have one (D-186, D-202,
D-209), built here the same way (D-233). An item is never ``PopupMenuItem.icon``
with a text: Flet lays that icon and the text out in a ``Row`` without ``Expanded``,
so at 200 % text the label ran off the menu's edge instead of wrapping (F47, #260).
"""

import flet as ft

from pycon_us.ui.links import OPENS_IN, LinkKind
from pycon_us.ui.semantics import named

MORE_OPTIONS = "More options"
"""The overflow button's tooltip, which is also its name for screen readers."""

ITEM_HEIGHT = 48
"""The menu's own row height (Flutter's ``PopupMenuItem.height``), which a tile would
make 56."""

ICON_GAP = 12
"""Between an item's icon and its label: Material 3's menu gap, not a list's 16."""


def overflow_menu(identifier: str, items: list[ft.PopupMenuItem]) -> ft.Control:
    """Return the app bar's overflow button ("More options") with ``items``.

    Merged with its identifier, as ``named()`` makes it: bare, the tooltip sat on
    the identifier's node and the button under it was unnamed (F50, D-214).

    Args:
        identifier: For UI flows, e.g. ``session.overflow``.
        items: The menu's items, each from ``menu_item()``.
    """
    menu = ft.PopupMenuButton(
        icon=ft.Icons.MORE_VERT, tooltip=MORE_OPTIONS, items=items
    )
    return named(identifier, menu)


def menu_item(
    icon: ft.IconData,
    label: str,
    on_click: ft.ControlEventHandler[ft.PopupMenuItem],
    *,
    identifier: str,
    link: bool = False,
) -> ft.PopupMenuItem:
    """Return one item of an overflow menu: ``icon`` beside ``label``, which wraps.

    The content is a ``ListTile``, which Flutter documents as a ``PopupMenuItem``'s
    child (the item takes its padding away): its title wraps inside the menu, at
    most 280 dp wide, and the theme's ``TITLE_HEIGHT`` keeps the icon beside the
    title's first line (D-188), where a ``Row`` would centre it on the block (F47).
    ``min_height`` keeps the menu's 48 dp row and ``horizontal_spacing`` its 12 dp
    gap. The tile has no ``on_click``: the item takes the tap and closes the menu.

    The identifier's ``Semantics`` needs no merge of its own: Flutter's item wraps
    its content in a ``MergeSemantics``, which takes the identifier, the tile and
    the label into the item's one node (D-230).

    Args:
        icon: The item's icon, read by nobody: the label says it all.
        label: What the item does, e.g. "Open on us.pycon.org".
        on_click: Called on a tap, after the menu has closed.
        identifier: For UI flows, e.g. ``session.open_site``.
        link: Whether the item leaves the app for a web page: then it is a link,
            read "<label>, Opens in browser" (ux.md §4.7, D-186). Said after the
            label's words, not by the icon, which would be read first.
    """
    title: ft.Control = ft.Text(label)
    if link:
        title = ft.Semantics(
            link=True,
            content=ft.Text(
                label, semantics_label=f"{label}\n{OPENS_IN[LinkKind.WEB]}"
            ),
        )
    tile = ft.ListTile(
        leading=ft.Icon(icon),
        title=title,
        horizontal_spacing=ICON_GAP,
        min_height=ITEM_HEIGHT,
    )
    return ft.PopupMenuItem(
        content=ft.Semantics(identifier=identifier, content=tile), on_click=on_click
    )
