"""Keeping the reader's place in today's Schedule list across a change of layout (D-250).

The list keeps its pixel offset, not its rows (#333): a filter change that adds or
removes rows above the top, or a text-size change that makes every row taller, shows
other rows at the same offset. ``screens/schedule.py`` therefore records an
``Anchor`` (``core/list_place.py``) at each scroll end of today's list, from the
heights its slots and now line report (``on_size_change``, F51; today's list builds
them all, D-154), and puts that slot back at the top:

- after a filter change, once the slots it changed have reported their new heights;
- after any item of today's list reports a new height: a text-size change, a
  rotation, the now line taking a slot's divider;
- when today's list shows again, from a tab switch or a day switch (``put_back()``).

It is an instant offset jump, never a jump to now (D-192, D-204), and never on
another day's list, which is lazy and keeps its slot in place by itself.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date

import flet as ft

from pycon_us.core.list_place import ListItem, anchor_at, list_items, offset_of
from pycon_us.core.timeline import Slot
from pycon_us.memory import ViewMemory
from pycon_us.services.errors import report_errors
from pycon_us.ui.scrolling import LEFT_THE_PAGE

logger = logging.getLogger(__name__)

RELAID_S = 0.05
"""How long after a height report the Schedule waits for the rest of them, in seconds:
the items of one layout report from one frame's callbacks, one after the other."""

FILTERED_S = 0.25
"""How long after a filter change the Schedule waits for the slots it changed to
report, in seconds: a filter change lays today's whole list out again, one frame of
up to about 80 ms on the emulator (D-154), and a change that only removes whole slots
reports nothing."""

type Measured = Callable[[str, float], Awaitable[None]]
"""What a slot or the now line of today's list calls with its key and new height."""


@dataclass(eq=False)
class TodayLayout:
    """What the Schedule knows of today's list as laid out; one per mounted screen.

    Plain, not state: a report or a scroll end re-renders nothing.

    Attributes:
        day: Today, the day of the list built in full.
        shown: Whether today's list is the one on screen: another day's page is not
            built, so today's list cannot be scrolled then.
        items: Today's slots and now line as last rendered (``list_items()``).
        heights: Each item's height by key, as last reported, in dp.
        excluded: The filter the list was last rendered with; None before the first.
        changes: How many layout changes have come; a wait ends in a restore only
            when no newer change came during it.
    """

    day: date | None = None
    shown: bool = False
    items: tuple[ListItem, ...] = ()
    heights: dict[str, float] = field(default_factory=dict)
    excluded: tuple[str, ...] | None = None
    changes: int = 0

    def ended_at(self, memory: ViewMemory, pixels: float) -> None:
        """Record where a scroll of today's list ended as the reader's place."""
        # Even while a change waits for its restore: the end of a jump to now, or of
        # the user's own scroll, is the place from then on.
        memory.schedule_anchor = anchor_at(self.items, self.heights, pixels)

    def measured(self, key: str, height: float) -> bool:
        """Record an item's reported height; return whether it is a new one."""
        if self.heights.get(key) == height:
            return False
        self.heights[key] = height
        return True


def use_today_place(
    memory: ViewMemory,
    list_of: Callable[[date], ft.Ref[ft.ListView]],
    today: date,
    *,
    shown_today: bool,
    slots: tuple[Slot, ...],
    line: int | None,
    excluded: tuple[str, ...],
) -> tuple[TodayLayout, Measured]:
    """Keep the reader's place in today's list: the Schedule's hook (D-250).

    Args:
        memory: Where the anchor and the offsets are kept.
        list_of: A day list's ref, the same for the screen's life.
        today: Today, the day whose list is built in full.
        shown_today: Whether today's list is the one on screen.
        slots: Today's slots as the filter leaves them.
        line: The now line's index among them.
        excluded: The filter, whose change restores the place.

    Returns:
        The screen's ``TodayLayout``, which its scroll handler and ``put_back()``
        read, and the stable height handler today's list reports to.
    """
    layout = ft.use_memo(TodayLayout, [])
    items = ft.use_memo(lambda: list_items(slots, line), [slots, line])
    # Plain fields the stable handlers read: the list as this render lays it out.
    layout.day, layout.shown, layout.items = today, shown_today, items

    # A lambda, not a handler: what a report or a filter change awaits.
    keep: Callable[[], Awaitable[bool]] = lambda: keep_place(
        layout, memory, list_of(layout.day or today)
    )

    @report_errors
    async def measured(key: str, height: float) -> None:
        if layout.measured(key, height):
            await after_change(layout, RELAID_S, keep)

    @report_errors
    async def refiltered() -> None:
        before, layout.excluded = layout.excluded, excluded
        if before is not None and before != excluded and layout.shown:
            await after_change(layout, FILTERED_S, keep)

    ft.use_effect(refiltered, [excluded], cleanup=_cancel_on_unmount)
    return layout, ft.use_callback(measured, [])


def _cancel_on_unmount() -> None:
    """The filter effect's cleanup: it makes Flet cancel a wait on unmount (F2, F39)."""


async def after_change(
    layout: TodayLayout, wait: float, keep: Callable[[], Awaitable[object]]
) -> None:
    """Restore the reader's place ``wait`` seconds after a layout change.

    A newer change during the wait takes over, so a burst of reports ends in one
    restore, with every height in.
    """
    layout.changes += 1
    change = layout.changes
    await asyncio.sleep(wait)
    if change == layout.changes:
        await keep()


async def keep_place(
    layout: TodayLayout, memory: ViewMemory, list_ref: ft.Ref[ft.ListView]
) -> bool:
    """Put the reader's slot back at the top of today's list, at once (D-250).

    Args:
        layout: Today's list as laid out and measured.
        memory: Where the reader's anchor and the list's offset are kept.
        list_ref: Today's list.

    Returns:
        Whether it asked the list to scroll: False without an anchor on today, with
        a height still unreported, or while another day shows.
    """
    anchor = memory.schedule_anchor
    day = layout.day
    target = list_ref.current
    if (
        not layout.shown
        or day is None
        or target is None
        or anchor is None
        or anchor.start.date() != day
    ):
        return False
    offset = offset_of(layout.items, layout.heights, anchor)
    if offset is None:
        return False
    # Where it lands is the place now: a hidden slot gives way to the next one.
    memory.schedule_anchor = anchor_at(layout.items, layout.heights, offset) or anchor
    memory.schedule_offsets[day] = offset
    try:
        await target.scroll_to(offset=offset, duration=0)
    except RuntimeError as error:  # the user left the tab while it waited (D-142)
        if LEFT_THE_PAGE not in str(error):
            raise
        logger.info("Keep the place: the list left the page")
        return False
    logger.info("Kept the place: %s at %.0f dp", anchor.key, offset)
    return True


async def put_back(
    layout: TodayLayout, memory: ViewMemory, list_ref: ft.Ref[ft.ListView], day: date
) -> None:
    """Put a day list that shows again where the reader left it (D-18, D-250).

    Today's by its anchor, so a text size changed meanwhile still finds the slot; any
    other day, or today before a scroll has ended, by its last scroll end's offset. A
    day list that shows again is a new list on the device, at the top: the tab bar's
    pages keep nothing of a page they no longer show.
    """
    if day == layout.day and await keep_place(layout, memory, list_ref):
        return
    offset = memory.schedule_offsets.get(day)
    if offset and list_ref.current is not None:
        await list_ref.current.scroll_to(offset=offset, duration=0)
