"""The content widths: reading screens 720 dp, lists 840 dp, centred (D-09, D-305).

On a phone the content takes the whole width. On a tablet, or a phone in landscape,
each screen caps it by its width class: ``READING`` for detail pages, About, Developer,
the info pages and a licence's text, ``LIST`` for every other screen, and ``FULL`` for the floor viewer.
Flet has no max-width constraint (D-165), so a screen gets the cap as side margins,
``use_margin()``, from the ``Layout`` store's room: a list puts them in its own
padding (``sides()``), so it scrolls from the margins too, and a screen's fixed chrome
above a list (the status strip, the day tabs, the filter summary) sits in
``capped()``. The margins are on ``surface``, the page's own colour.
"""

import math

import flet as ft

from pycon_us.layout import LIST_DP, READING_DP, use_layout
from pycon_us.locations import TAB_ROOTS
from pycon_us.ui.navigation import RAIL_WIDTH

READING = float(READING_DP)
"""A reading screen's width class: a session, a speaker, a sponsor, the info pages,
About this app, Developer options and a licence's text (ux.md §8)."""

LIST = float(LIST_DP)
"""A list's width class, every screen's but a reading one's or the floor viewer's."""

FULL = math.inf
"""The floor viewer's width class: a plan takes the whole width (ux.md §6.1)."""


def side_margin(room: float, cap: float, *, rail: float = 0.0) -> float:
    """Return each side's margin that centres content at most ``cap`` dp wide.

    Args:
        room: The body's width in dp (``Layout.room``); 0 under any cap.
        cap: The screen's width class: ``READING``, ``LIST`` or ``FULL``.
        rail: The rail's width beside the body, on a tab root from 600 dp.
    """
    return max(0.0, (room - rail - cap) / 2)


def use_margin(cap: float) -> float:
    """Return the screen's side margin for its width class, and follow the window.

    A hook: the screen calls it once per render and hands the margin to its list and
    its fixed chrome. On a tab root from 600 dp the rail's ``RAIL_WIDTH`` comes off
    the room first (D-277); at large text the rail is wider, so the content there is
    a little narrower than the cap, never wider.

    Args:
        cap: The screen's width class: ``READING``, ``LIST`` or ``FULL``.
    """
    layout = use_layout()
    # Both hooks on every render (D-70): a hook behind ``layout.wide`` shifted the
    # caller's hooks at a rotation across 600 dp, and the render's error stopped all
    # of the session's renders (#606, U111).
    view_path = ft.use_view_path()
    rail = RAIL_WIDTH if layout.wide and view_path in TAB_ROOTS else 0
    return side_margin(layout.room, cap, rail=rail)


def sides(margin: float, *, top: float = 0, bottom: float = 0) -> ft.Padding:
    """Return a list's padding: ``margin`` on both sides, ``top`` and ``bottom``.

    Args:
        margin: Each side's margin, from ``use_margin()``.
        top: The space above the list's first item, in dp.
        bottom: The space below its last item, in dp.
    """
    return ft.Padding.only(left=margin, top=top, right=margin, bottom=bottom)


def capped(content: ft.Control, margin: float) -> ft.Control:
    """Return fixed content (no scroll of its own) between the screen's side margins.

    Always the same container, ``margin`` 0 on a phone, so a rotation changes its
    padding and keeps the content's place in the tree (D-18).

    Args:
        content: The strip, the day tabs, a summary: what sits above a list.
        margin: Each side's margin, from ``use_margin()``.
    """
    return ft.Container(content, padding=ft.Padding.symmetric(horizontal=margin))
