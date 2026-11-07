"""The app bar's overflow menus: `overflow_menu()`, `menu_item()`, View source.

Session detail, the Sprints page and a track's page each have one (D-186, D-202,
D-209), built here the same way (D-233). An item is never `PopupMenuItem.icon`
with a text: Flet lays that icon and the text out in a `Row` without `Expanded`,
so at 200 % text the label ran off the menu's edge instead of wrapping (F47, #260).

Once `SOURCE_URL` is set, every screen's overflow ends in View source, which opens
the screen's own module on GitHub (`view_source_items()`, NEW-09, D-461).
"""

import re

import flet as ft

from pycon_us import SOURCE_URL, __version__
from pycon_us.services import Services
from pycon_us.services.errors import report_errors
from pycon_us.ui.links import OPENS_IN, LinkKind, open_link
from pycon_us.ui.semantics import named

MORE_OPTIONS = "More options"
"""The overflow button's tooltip, which is also its name for screen readers."""

ITEM_HEIGHT = 48
"""The menu's own row height (Flutter's `PopupMenuItem.height`), which a tile would
make 56."""

ICON_GAP = 12
"""Between an item's icon and its label: Material 3's menu gap, not a list's 16."""

VIEW_SOURCE = "View source"
"""The item that opens a screen's module on GitHub (NEW-09)."""

BREAK = "\u200b"
"""A zero-width space: where a line may break, with nothing drawn or said."""

HOST_DOT = re.compile(r"\.(?=\w)")
"""A dot inside a host name, as in "pycon-archive.python.org"; not a sentence's last."""


def breakable(label: str) -> str:
    """Return `label` with a line break allowed after each dot inside a word.

    A host name is one word to Flutter's line breaker, which breaks after a hyphen but
    not after a dot: at 200 % on iOS "Open on pycon-archive.python.org" broke inside
    "org" (#895). After each dot it now breaks between the host's parts.

    Args:
        label: The item's words, e.g. "Open on pycon-archive.python.org".
    """
    return HOST_DOT.sub("." + BREAK, label)


def overflow_menu(identifier: str, items: list[ft.PopupMenuItem]) -> ft.Control:
    """Return the app bar's overflow button ("More options") with `items`.

    Merged with its identifier, as `named()` makes it: bare, the tooltip sat on
    the identifier's node and the button under it was unnamed (F50, D-214).

    Args:
        identifier: For UI flows, e.g. `session.overflow`.
        items: The menu's items, each from `menu_item()`.
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
    disabled: bool = False,
) -> ft.PopupMenuItem:
    """Return one item of an overflow menu: `icon` beside `label`, which wraps.

    The content is a `ListTile`, which Flutter documents as a `PopupMenuItem`'s
    child (the item takes its padding away): its title wraps inside the menu, at
    most 280 dp wide, and the theme's `TITLE_HEIGHT` keeps the icon beside the
    title's first line (D-188), where a `Row` would centre it on the block (F47).
    `min_height` keeps the menu's 48 dp row and `horizontal_spacing` its 12 dp
    gap. The tile has no `on_click`: the item takes the tap and closes the menu.

    The identifier's `Semantics` needs no merge of its own: Flutter's item wraps
    its content in a `MergeSemantics`, which takes the identifier, the tile and
    the label into the item's one node (D-230).

    Args:
        icon: The item's icon, read by nobody: the label says it all.
        label: What the item does, e.g. "Open on us.pycon.org".
        on_click: Called on a tap, after the menu has closed.
        identifier: For UI flows, e.g. `session.open_site`.
        link: Whether the item leaves the app for a web page: then it is a link,
            read "<label>, Opens in browser" (ux.md §4.7, D-186). Said after the
            label's words, not by the icon, which would be read first.
        disabled: Whether the item is greyed out and takes no tap, e.g. while what
            it started is still running. The item's node then reads as disabled;
            the tile is disabled with it, since a tile sets its own text colour
            and would otherwise look enabled.
    """
    title: ft.Control = ft.Text(label)
    if link:
        title = ft.Semantics(
            link=True,
            # The breaks are for the eye alone: the node reads the plain label.
            content=ft.Text(
                breakable(label),
                semantics_label=f"{label}\n{OPENS_IN[LinkKind.WEB]}",
            ),
        )
    tile = ft.ListTile(
        leading=ft.Icon(icon),
        title=title,
        horizontal_spacing=ICON_GAP,
        min_height=ITEM_HEIGHT,
        disabled=disabled,
    )
    return ft.PopupMenuItem(
        content=ft.Semantics(identifier=identifier, content=tile),
        on_click=on_click,
        disabled=disabled,
    )


def source_link(source_url: str, module: str) -> str:
    """Return the page that shows `module` in the source of this build (D-461).

    The version's tag, not `main`: the link shows the code of the build in the
    attendee's hand, and a later rename can't break it.

    Args:
        source_url: `SOURCE_URL`, once the repository is public.
        module: The module's `__name__`, e.g. `pycon_us.screens.now`.
    """
    path = module.replace(".", "/")
    return f"{source_url.rstrip('/')}/blob/v{__version__}/src/{path}.py"


def view_source_items(svc: Services, module: str | None) -> list[ft.PopupMenuItem]:
    """Return View source for `module`, or nothing while the repository is private.

    A list, so that a menu takes it with `*` and stays as it was while
    `SOURCE_URL` is None (D-88, D-461). A web link like any other (ux.md §4.7), also
    offline: the in-app browser's own page says there is no connection.

    Args:
        svc: The session's services, for the launcher.
        module: The screen's `__name__`; None gives no item.
    """
    if SOURCE_URL is None or module is None:
        return []
    url = source_link(SOURCE_URL, module)

    @report_errors
    async def view_source() -> None:
        await open_link(svc, url)

    return [
        menu_item(
            ft.Icons.CODE,  # About this app's Source code row's
            VIEW_SOURCE,
            view_source,
            identifier="app.view_source",
            link=True,
        )
    ]


def source_menu(svc: Services, module: str | None) -> list[ft.Control]:
    """Return the overflow of a screen with no menu of its own, or nothing while hidden.

    `AppScaffold`'s, so a screen with no overflow doesn't gain an empty one.

    Args:
        svc: The session's services, for the launcher.
        module: The screen's `__name__`, or None for no menu (`AppScaffold`'s
            `source`).
    """
    items = view_source_items(svc, module)
    return [overflow_menu("app.overflow", items)] if items else []
