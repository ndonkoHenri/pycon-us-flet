"""Search's scope chips (``screens/search.py``): one row, the selected chip in sight.

All · Sessions · Speakers · Places · Sponsors (D-19, D-351) in one row that scrolls
sideways when it is wider than the screen (large text, ux.md §4.3). The row scrolls
to the selected chip as Search opens, at once, and after each change of scope,
over ``JUMP_MS`` (0 under reduced motion, D-34): opened from the Map on Places at
the largest text, the selected chip was past the right edge, so only the count line
said which scope the results were in (#794). The scroll is a keyed ``scroll_to``
(``ui.scrolling.jump_to_key()``), which puts the chip's start at the row's start as
far as the row can scroll (F295); the key sits on an empty anchor before each chip,
the gap that leads to it, so the chip itself is never mounted again (D-242). A drag
of the row stops a jump still waiting: its next try would snap the row back.
"""

import asyncio
from typing import Any

import flet as ft
from flet.components.hooks.use_ref import MutableRef

from pycon_us.prefs import use_prefs
from pycon_us.screens.search_results import SCREEN
from pycon_us.services.errors import report_errors
from pycon_us.ui.scrolling import JUMP_MS, jump_to_key
from pycon_us.ui.semantics import named

SCOPE_LABELS = {
    "all": "All",
    "sessions": "Sessions",
    "speakers": "Speakers",
    "places": "Places",
    "sponsors": "Sponsors",
}
"""Each scope's chip, in ``SCOPES``' order (D-19)."""

GUTTER = 16
"""The row's ends, in dp: the first chip starts at the screen's gutter, and the last
can scroll clear of the edge."""

GAP = 8
"""The space between two chips, in dp."""


def anchor_key(scope: str) -> str:
    """Return the ``ScrollKey`` value of the anchor before ``scope``'s chip.

    Args:
        scope: A key of ``SCOPE_LABELS``, e.g. ``places``.
    """
    return f"{SCREEN}.scope_anchor.{scope}"


@ft.component
def ScopeChips(scope: str, on_pick: ft.ControlEventHandler[ft.Chip]) -> ft.Control:
    """The scope chips, one per scope, the current one selected with its check and in sight.

    Wrapped, the chips took three rows at the largest text, and with the keyboard up
    the field and the chips no longer fitted above it; so one row that scrolls
    sideways. Each chip is one node for screen readers, read as its label, "selected"
    when it is, and a button, in the row's order: the anchors hold nothing to read.

    Args:
        scope: The current scope.
        on_pick: Switches to the tapped chip's scope (its ``data``), keeping the query.
    """
    prefs = use_prefs()
    row = ft.use_memo(ft.Ref[ft.Row], [])  # one ref for the row's lifetime (F38)
    ended = ft.use_memo(asyncio.Event, [])  # set at each scroll's end
    opened = ft.use_ref(False)
    jump: MutableRef[asyncio.Task[Any] | None] = ft.use_ref(None)  # the jump under way

    @report_errors
    async def show_selected() -> None:
        # Search opens on its scope at once; a pick slides the row to it (D-34).
        duration = prefs.motion_ms(JUMP_MS) if opened.current else 0
        opened.current = True
        jump.current = asyncio.current_task()
        await jump_to_key(row, anchor_key(scope), duration=duration, ended=ended)

    ft.use_effect(show_selected, [scope])

    @report_errors
    def scrolled(e: ft.OnScrollEvent) -> None:
        if e.event_type == ft.ScrollType.END:
            ended.set()  # how the jump knows it landed
            return
        dragged = e.event_type == ft.ScrollType.USER and e.direction in (
            ft.ScrollDirection.FORWARD,
            ft.ScrollDirection.REVERSE,
        )
        if dragged and jump.current is not None and not jump.current.done():
            # The user is scrolling the row: a waiting jump (a chip already in
            # place never reports an end) would snap it back, so it asks no more.
            jump.current.cancel()

    return ft.Container(
        ft.Row(
            [
                *(
                    ft.Row(
                        [
                            # The gap before the chip, so a keyed scroll leaves it
                            # (or the gutter, for the first) clear of the edge.
                            ft.Container(
                                key=ft.ScrollKey(anchor_key(key)),
                                width=GUTTER if index == 0 else GAP,
                            ),
                            named(
                                f"{SCREEN}.scope.{key}",
                                ft.Chip(
                                    label=label,
                                    selected=key == scope,
                                    show_checkmark=True,  # not colour alone (D-33)
                                    data=key,
                                    # A click, not on_select: Flutter would toggle
                                    # the chip itself, so a tap on the selected one
                                    # showed no scope selected; here ``selected`` is
                                    # only ours.
                                    on_click=on_pick,
                                ),
                            ),
                        ],
                        spacing=0,
                    )
                    for index, (key, label) in enumerate(SCOPE_LABELS.items())
                ),
                ft.Container(width=GUTTER),
            ],
            spacing=0,
            scroll=ft.ScrollMode.AUTO,
            on_scroll=scrolled,
            ref=row,
        ),
        padding=ft.Padding.symmetric(vertical=4),
    )
