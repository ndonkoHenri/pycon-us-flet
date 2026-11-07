"""Tests for `ui/menus.py`: the overflow menu and its items (F47, D-233).

The screens' own tests click the items (`test_session_actions.py`, `test_sprints.py`,
`test_track_add_all.py`); these hold the item's shape, which is what makes its
label wrap at 200 % text, and a scan keeps every menu item on it.
"""

import ast
from pathlib import Path
from typing import cast

import flet as ft
import pytest

import pycon_us
from pycon_us.ui.menus import (
    BREAK,
    ICON_GAP,
    ITEM_HEIGHT,
    MORE_OPTIONS,
    menu_item,
    overflow_menu,
)
from tests.sessions import menu_text

LABEL = "Sprint info on us.pycon.org"
"""A label longer than the menu's width at 200 % text."""


async def go() -> None:
    """An item's handler, never called here."""


def tile_of(item: ft.PopupMenuItem) -> ft.ListTile:
    """The item's tile, under its identifier's `Semantics`."""
    return cast(ft.ListTile, cast(ft.Semantics, item.content).content)


def test_an_items_label_is_a_tile_title_that_wraps_beside_its_icon() -> None:
    """An item's label is a tile's title that wraps, with its icon as `leading`.

    F47: `PopupMenuItem.icon` sits in a `Row` whose text cannot wrap, so the item
    has no `icon`; the icon sits beside the title's first line by the theme's
    `TITLE_HEIGHT` (D-188).
    """
    item = menu_item(ft.Icons.PLAYLIST_ADD, LABEL, go, identifier="track.add_all")
    assert item.icon is None
    tile = tile_of(item)
    assert isinstance(tile, ft.ListTile)
    icon = cast(ft.Icon, tile.leading)
    assert isinstance(icon, ft.Icon) and icon.icon == ft.Icons.PLAYLIST_ADD
    assert menu_text(item).value == LABEL
    assert menu_text(item).max_lines is None  # never cut: it wraps
    assert tile.title_alignment is None  # the theme's TITLE_HEIGHT applies


def test_an_item_keeps_the_menus_row_height_and_icon_gap() -> None:
    """A tile alone would be 56 dp high with a 16 dp gap; the menu's are 48 and 12."""
    tile = tile_of(menu_item(ft.Icons.PLAYLIST_ADD, LABEL, go, identifier="x.y"))
    assert (tile.min_height, tile.horizontal_spacing) == (ITEM_HEIGHT, ICON_GAP)
    assert (ITEM_HEIGHT, ICON_GAP) == (48, 12)


def test_the_item_takes_the_tap_so_the_menu_closes() -> None:
    """A tap on the tile would run without closing the menu; the item's closes it."""
    item = menu_item(ft.Icons.PLAYLIST_ADD, LABEL, go, identifier="x.y")
    assert item.on_click is go
    assert tile_of(item).on_click is None


def test_an_item_carries_its_identifier_for_ui_flows() -> None:
    """D-33, D-230: on the item's content, which the item's own merge takes in."""
    item = menu_item(ft.Icons.OPEN_IN_NEW, LABEL, go, identifier="sprints.info")
    assert cast(ft.Semantics, item.content).identifier == "sprints.info"


def test_a_link_item_is_a_link_read_opens_in_browser_after_its_words() -> None:
    """ux.md §4.7, D-186: it leaves the app; the words come before "Opens in browser"."""
    item = menu_item(
        ft.Icons.OPEN_IN_NEW, LABEL, go, identifier="sprints.info", link=True
    )
    title = cast(ft.Semantics, tile_of(item).title)
    assert isinstance(title, ft.Semantics) and title.link
    assert menu_text(item).value.replace(BREAK, "") == LABEL
    assert menu_text(item).semantics_label == f"{LABEL}\nOpens in browser"


@pytest.mark.parametrize(
    ("label", "shown"),
    [
        (
            "Open on pycon-archive.python.org",
            "Open on pycon-archive.\u200bpython.\u200borg",
        ),
        ("Open on us.pycon.org", "Open on us.\u200bpycon.\u200borg"),
        ("Opens the page.", "Opens the page."),  # a sentence's last dot: nothing after
        ("View source", "View source"),
    ],
)
def test_a_link_s_host_may_break_after_each_dot(label: str, shown: str) -> None:
    """A long host wraps between its parts, never inside "org" (#895).

    The breaks are drawn as nothing; the node still reads the plain label.
    """
    item = menu_item(ft.Icons.OPEN_IN_NEW, label, go, identifier="x", link=True)
    assert menu_text(item).value == shown
    assert menu_text(item).semantics_label == f"{label}\nOpens in browser"


def test_an_item_that_stays_in_the_app_is_no_link() -> None:
    """Without `link`, the title is a plain `Text` with no "Opens in browser"."""
    item = menu_item(ft.Icons.PLAYLIST_ADD, LABEL, go, identifier="track.add_all")
    title = tile_of(item).title
    assert isinstance(title, ft.Text)  # no link Semantics around it
    assert title.semantics_label is None


def test_the_overflow_is_the_more_options_button_merged_with_its_identifier() -> None:
    """F50, D-214: merged, the button is one node named by its tooltip."""
    items = [menu_item(ft.Icons.PLAYLIST_ADD, LABEL, go, identifier="track.add_all")]
    merged = overflow_menu("track.menu", items)
    assert isinstance(merged, ft.MergeSemantics)
    node = cast(ft.Semantics, merged.content)
    assert node.identifier == "track.menu"
    menu = cast(ft.PopupMenuButton, node.content)
    assert isinstance(menu, ft.PopupMenuButton)
    assert (menu.icon, menu.tooltip) == (ft.Icons.MORE_VERT, MORE_OPTIONS)
    assert MORE_OPTIONS == "More options"
    assert menu.items == items


SOURCES = sorted(Path(pycon_us.__file__).parent.rglob("*.py"))
"""Every module of the app."""


def menu_item_calls(path: Path) -> list[ast.Call]:
    """Return each `PopupMenuItem(...)` call in `path`, spelled with `ft.` or not."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            getattr(node.func, "attr", None) == "PopupMenuItem"
            or getattr(node.func, "id", None) == "PopupMenuItem"
        )
    ]


def test_every_menu_item_is_built_by_menu_item() -> None:
    """#260: an item built elsewhere could set `icon=` and clip its label (F47)."""
    building = {path.name for path in SOURCES if menu_item_calls(path)}
    assert building == {"menus.py"}


def test_no_menu_item_sets_an_icon_beside_its_content() -> None:
    """F47: Flet's `Row([icon, SizedBox, content])` has no `Expanded`."""
    found = [
        f"{path.name}:{call.lineno}"
        for path in SOURCES
        for call in menu_item_calls(path)
        if any(keyword.arg == "icon" for keyword in call.keywords)
    ]
    assert found == []


def test_a_disabled_item_takes_no_tap_and_looks_disabled() -> None:
    """The item and its tile are disabled together: the tile sets its own text colour."""
    item = menu_item(
        ft.Icons.EVENT_AVAILABLE_OUTLINED,
        "Add to calendar",
        go,
        identifier="session.add_to_calendar",
        disabled=True,
    )
    assert item.disabled and tile_of(item).disabled
    enabled = menu_item(ft.Icons.PLAYLIST_ADD, LABEL, go, identifier="x.y")
    assert not enabled.disabled and not tile_of(enabled).disabled
