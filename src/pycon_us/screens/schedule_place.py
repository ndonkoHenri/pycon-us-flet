"""Keeping the reader's place in today's Schedule list across a change of layout (D-250).

The list keeps its pixel offset, not its rows (#333): a filter change that adds or
removes rows above the top, or a text-size change that makes every row taller, shows
other rows at the same offset. ``screens/schedule.py`` therefore records an
``Anchor`` (``core/list_place.py``) at each scroll end of today's list, from the
heights its slots and now line report (``on_size_change``, F51; today's list builds
them all, D-154), and puts that slot back at the top:

- after today's slots change, from a filter change or a refresh, once the slots it
  changed have reported their new heights; a change that only removes whole slots
  reports none;
- after any item of today's list reports a new height: a text-size change, a
  rotation, the now line taking a slot's divider;
- when today's list shows again, from a tab switch or a day switch (``put_back()``).

It is an instant offset jump, never a jump to now (D-192, D-204), and never on
another day's list, which is lazy and keeps its slot in place by itself. Nor while
today's list is scrolling, under the user's finger, in a fling or in a jump to now:
the jump would cut it short, and where it ends is the place from then on. A scroll
start or update counts for ``MOVING_S`` at most, since Flet can drop its end, so a
restore it holds waits that long; the user's drag counts until Flutter reports it
idle or it ends, since a finger held still sends no update.
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
from pycon_us.ui.scrolling import LEFT_THE_PAGE, SCROLL_EVENT_MS

logger = logging.getLogger(__name__)

RELAID_S = 0.05
"""How long after a height report the Schedule waits for the rest of them, in seconds:
the items of one layout report from one frame's callbacks, one after the other."""

RELISTED_S = 0.25
"""How long after today's slots change (a filter change, a refresh) the Schedule waits
for the slots it changed to report, in seconds: such a change lays today's whole list
out again, one frame of up to about 80 ms on the emulator (D-154), and a change that
only removes whole slots reports nothing."""

MOVING_S = 2 * SCROLL_EVENT_MS / 1000
"""How long after a scroll start or update of today's list it counts as scrolling, in
seconds: a scroll sends an update at least every ``SCROLL_EVENT_MS`` while it moves,
and Flet drops an end that comes within that time of the last one, which would
otherwise leave the list scrolling for good. A restore it holds waits until then."""

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
        laid_out: The last ``items`` that had all reported a height: the list the
            device shows until a new slot among ``items`` reports (#338's review).
        listed: The items the slots effect last saw; None before its first run.
        changes: How many layout changes have come; a wait ends in a restore only
            when no newer change came during it.
        moved_at: When today's list last reported a scroll start or update, by the
            event loop's clock; None after its scroll end.
        user_scrolling: Whether the user's own scroll of today's list, a drag or its
            fling, is on its way, by its last direction report (``ScrollType.USER``):
            a finger held still sends no update, and Flutter reports idle only once
            the finger has lifted and the fling has stopped.
        jumping: How many jumps to now are on their way: a keyed scroll reports its
            start only once Flutter has begun it.
    """

    day: date | None = None
    shown: bool = False
    items: tuple[ListItem, ...] = ()
    heights: dict[str, float] = field(default_factory=dict)
    laid_out: tuple[ListItem, ...] = ()
    listed: tuple[ListItem, ...] | None = None
    changes: int = 0
    moved_at: float | None = None
    user_scrolling: bool = False
    jumping: int = 0

    def moved(self) -> None:
        """Record that today's list is scrolling: a scroll start or update came."""
        self.moved_at = asyncio.get_running_loop().time()

    def still(self) -> bool:
        """Whether today's list is at rest: no scroll and no jump on its way."""
        return not (self.jumping or self.user_scrolling or self.moving_for())

    def moving_for(self) -> float:
        """How long the last scroll start or update still counts, in seconds.

        0.0 without one since the last scroll end, or once ``MOVING_S`` has passed.
        """
        if self.moved_at is None:
            return 0.0
        since = asyncio.get_running_loop().time() - self.moved_at
        return max(0.0, MOVING_S - since)

    def ended_at(self, memory: ViewMemory, pixels: float) -> None:
        """Record where a scroll of today's list ended as the reader's place."""
        self.moved_at = None
        self.user_scrolling = False  # in case Flet dropped the idle report
        # Even while a change waits for its restore: the end of a jump to now, or of
        # the user's own scroll, is the place from then on. Read on the list the user
        # saw: a slot that has not reported yet has not been laid out on the device,
        # and the restore once it reports puts this place back.
        self._caught_up()
        memory.schedule_anchor = anchor_at(self.laid_out, self.heights, pixels)

    def measured(self, key: str, height: float) -> bool:
        """Record an item's reported height; return whether it is a new one."""
        if self.heights.get(key) == height:
            return False
        self.heights[key] = height
        self._caught_up()
        return True

    def _caught_up(self) -> None:
        """Take ``items`` as laid out once each of them has reported a height."""
        if all(item.key in self.heights for item in self.items):
            self.laid_out = self.items


def use_today_place(
    memory: ViewMemory,
    list_of: Callable[[date], ft.Ref[ft.ListView]],
    today: date,
    *,
    shown_today: bool,
    slots: tuple[Slot, ...],
    line: int | None,
) -> tuple[TodayLayout, Measured]:
    """Keep the reader's place in today's list: the Schedule's hook (D-250).

    Args:
        memory: Where the anchor and the offsets are kept.
        list_of: A day list's ref, the same for the screen's life.
        today: Today, the day whose list is built in full.
        shown_today: Whether today's list is the one on screen.
        slots: Today's slots as the filter leaves them.
        line: The now line's index among them.

    Returns:
        The screen's ``TodayLayout``, which its scroll handler and ``put_back()``
        read, and the stable height handler today's list reports to.
    """
    layout = ft.use_memo(TodayLayout, [])
    items = ft.use_memo(lambda: list_items(slots, line), [slots, line])
    # Plain fields the stable handlers read: the list as this render lays it out.
    layout.day, layout.shown, layout.items = today, shown_today, items

    # A lambda, not a handler: what a report or a change of slots awaits.
    keep: Callable[[], Awaitable[bool]] = lambda: keep_place(
        layout, memory, list_of(layout.day or today)
    )

    @report_errors
    async def measured(key: str, height: float) -> None:
        if layout.measured(key, height):
            await after_change(layout, RELAID_S, keep)

    @report_errors
    async def relisted() -> None:
        # Any change of today's slots, not only a filter's: a refresh can remove a
        # whole slot above the top and leave every other height as it was (#333).
        # Not at the first run, on mount: nothing has changed yet.
        before, layout.listed = layout.listed, items
        if before is not None and before != items and layout.shown:
            await after_change(layout, RELISTED_S, keep)

    ft.use_effect(relisted, [items], cleanup=_cancel_on_unmount)
    return layout, ft.use_callback(measured, [])


def _cancel_on_unmount() -> None:
    """The slots effect's cleanup: it makes Flet cancel a wait on unmount (F2, F39)."""


async def after_change(
    layout: TodayLayout, wait: float, keep: Callable[[], Awaitable[object]]
) -> None:
    """Restore the reader's place ``wait`` seconds after a layout change.

    A newer change during the wait takes over, so a burst of reports ends in one
    restore, with every height in. A list that may still be scrolling only because
    its end was dropped (``MOVING_S``) holds the restore until it counts as still; one
    the user scrolls, or a jump to now, has none: its end records the place (D-250).
    """
    layout.changes += 1
    change = layout.changes
    await asyncio.sleep(wait)
    while change == layout.changes:
        left = layout.moving_for()
        if not left or layout.user_scrolling or layout.jumping:
            await keep()
            return
        await asyncio.sleep(left)


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
        a height still unreported, while another day shows, or while the list is
        scrolling: the scroll's end records the place it chose (D-250).
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
        or not layout.still()
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
    # The jump stopped any scroll; its own end may be dropped (MOVING_S).
    layout.moved_at = None
    layout.user_scrolling = False
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
