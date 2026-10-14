"""Keeping the reader's place in today's Schedule list across a filter change (D-250).

The list keeps its offset, not its rows (#333, F70), so ``TodayPlace`` keeps the item at
the top as a key (``core/list_place.py``) and puts it back with a keyed jump, which
Flutter works out from its own layout. Only at moments when the change is laid out and
the user is not scrolling:

- the filter sheet closes after a change: the sheet is modal, so the list could not
  move. Its chips' changes are usually laid out and reported under it, but a close
  that comes before the last change's reports uses stale heights, so the first report
  of today's items after it puts the place back again, by key. That repeat is the
  close's own layout's: the first report takes it, and so does a newer render of
  today's items (a refresh, the now line), whose reports are its own;
- after another change, "Show all" or "Clear filters", at the next height report of
  today's items, which Flutter sends after the frame that laid the change out. Any
  scroll of the list, a jump to now and the re-tap cancel it.

A newer scroll (the user's drag, a jump to now, the re-tap) also stops a put-back on
its way between its two jumps (``TodayPlace.turn``). When Flet drops every scroll end
of a keyed put-back (``scroll_interval``, F70), where it went is unknown: today's offset
is dropped, and without one today comes back by key (``comes_back_by_key()``).

A change made while another day shows waits for today to show again. The place is read
only where the user's own scroll ends, never where the app's jumps end. No timers: a
moment that never comes leaves the list where it is, never somewhere the user left.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date

import flet as ft

from pycon_us.core.list_place import (
    ListItem,
    Place,
    list_items,
    place_at,
    place_of,
    target_of,
    top_of,
)
from pycon_us.core.timeline import Slot
from pycon_us.memory import ViewMemory
from pycon_us.services.errors import report_errors
from pycon_us.ui.scrolling import LEFT_THE_PAGE

logger = logging.getLogger(__name__)

type Measured = Callable[[str, float], Awaitable[None]]
"""The Schedule's height handler for today's list: an item's key and height."""


def reporting(
    key: str, on_size: Measured | None
) -> Callable[[ft.LayoutSizeChangeEvent[ft.LayoutControl]], Awaitable[None]] | None:
    """Return an item's ``on_size_change``, which tells ``on_size`` its height.

    Flet sends a size after the frame that laid it out (``MeasureSize``, F51), at the
    item's first layout and at each change. None without a handler: the other days
    report nothing.
    """
    if on_size is None:
        return None
    report = on_size

    @report_errors
    async def measured(e: ft.LayoutSizeChangeEvent[ft.LayoutControl]) -> None:
        await report(key, e.height)

    return measured


@dataclass(eq=False)
class TodayPlace:
    """Today's list as the Schedule knows it between renders; one per mounted screen.

    Plain fields, so measuring and scrolling re-render nothing (D-153).

    Attributes:
        memory: Where the place, the pending put-back and the offsets live (D-18).
        day: Today; ``list_ref`` its list and ``items`` its items, from the last render.
        shown: Today's list is the day shown, its switch settled (``shows()``).
        excluded: The filter of the last render; ``opened_with`` the one the sheet
            opened with, while it is open.
        heights: Each item's height as the device last reported it, by key.
        moving: A scroll of the list has started and not ended.
        user: The user has scrolled the list since the app last did: only then does
            a scroll's end say where the reader is.
        ends: How many scroll ends the list has reported.
        turn: Counts what moves the list: each put-back, the user's drag (a non-idle
            ``USER`` event), the app's own scrolls and a day switch. A put-back
            stops between its jumps when the turn is no longer its own.
        again: The turn of the sheet's close's put-back: while it is still the turn,
            the first height report after the close puts the place back again, by
            key. That report takes it, and so does a newer render of today's items.
    """

    memory: ViewMemory
    day: date | None = None
    list_ref: ft.Ref[ft.ListView] = field(default_factory=ft.Ref[ft.ListView])
    items: tuple[ListItem, ...] = ()
    shown: bool = False
    excluded: tuple[str, ...] | None = None
    opened_with: tuple[str, ...] | None = None
    heights: dict[str, float] = field(default_factory=dict)
    moving: bool = False
    user: bool = False
    ends: int = 0
    turn: int = 0
    again: int = -1

    @report_errors
    async def measured(self, key: str, height: float) -> None:
        """An item reported its height: a pending put-back runs while today shows.

        So does a repeat of the sheet's close's put-back, which may have read heights
        from before the change's layout: Flet sends a size after the frame that laid
        it out, which can come after the close (D-250). The first report after the
        close takes the repeat, whether or not it runs, so a later one never does.
        """
        self.heights[key] = height
        repeat, self.again = self.again == self.turn, -1
        if self.shown and (self.memory.schedule_pending or repeat):
            await self.put_back()

    def scrolled(self, day: date, e: ft.OnScrollEvent) -> None:
        """A scroll event of a day's list: today's say whether it moves and who moved it.

        Flutter sends a non-idle ``USER`` event only for the user's drag or fling, never
        for the app's jumps (F70), so only the end of the user's scroll is the place.
        """
        if day != self.day:
            return
        if e.event_type == ft.ScrollType.END:
            self.moving = False
            self.ends += 1
            if self.user:
                self.memory.schedule_place = place_at(
                    self.items, self.heights, e.pixels
                )
            return
        self.memory.schedule_pending = False  # the user moved: nothing to put back
        if (
            e.event_type == ft.ScrollType.USER
            and e.direction == ft.ScrollDirection.IDLE
        ):
            return  # it comes after the end
        self.moving = True
        if e.event_type == ft.ScrollType.USER:
            self.user = True
            self.turn += 1  # the user's drag: a put-back on its way stops

    def scrolls_itself(self, to: Place | None) -> None:
        """The app is about to scroll today's list: to now (``to``) or to its top."""
        self.user = False
        self.turn += 1
        self.memory.schedule_pending = False
        self.memory.schedule_place = to

    def jumps_to(self, key: str) -> None:
        """A jump to now is about to put ``key`` at the top of today's list (D-204)."""
        self.scrolls_itself(place_of(self.items, key))

    def shows(self, day: date) -> None:
        """A day switch settled on ``day``; today's page is a new list on the device."""
        self.turn += 1
        self.shown = day == self.day
        if self.shown:
            self.user = False

    def lays_out(self, items: tuple[ListItem, ...]) -> None:
        """A render lays today's ``items`` out: a newer layout's reports are its own.

        So a change of them (a refresh, the now line) ends the sheet's close's repeat:
        when the close was right, no report follows it, and a refresh's reports minutes
        later must not put the place back (D-250).
        """
        if items is not self.items:
            self.again = -1
        self.items = items

    def comes_back_by_key(self) -> bool:
        """Whether today, showing again, is put back by key rather than by offset.

        A change while today was hidden drops its offset (``arm()``), and so does a
        keyed put-back whose scroll ends Flet all dropped; any scroll end of today's
        list records one again.
        """
        return self.day is not None and (
            self.memory.schedule_pending or self.day not in self.memory.schedule_offsets
        )

    def sheet_opened(self) -> None:
        """The filter sheet opened: its close says whether the filter changed."""
        self.opened_with = self.excluded

    @report_errors
    async def sheet_closed(self) -> None:
        """The sheet closed (its button, then its dismissal): put the place back once."""
        opened_with, self.opened_with = self.opened_with, None
        if opened_with is None or opened_with == self.excluded:
            return
        if self.shown:
            await self.put_back(measured=True)
        else:
            self.arm()

    def filtered(self, excluded: tuple[str, ...]) -> None:
        """A render laid out a new filter: outside the sheet, put the place back later."""
        before, self.excluded = self.excluded, excluded
        if before is not None and before != excluded and self.opened_with is None:
            self.arm()

    def arm(self) -> None:
        """Put the place back at the next settled moment: a report, or today showing.

        Hidden, today's offset was laid out for the old filter, so it is dropped: the
        put-back replaces it. Never while the list moves: its end is the place then.
        """
        if self.memory.schedule_place is None or self.day is None:
            return
        if not self.shown:
            self.memory.schedule_offsets.pop(self.day, None)
            self.memory.schedule_pending = True
        elif not self.moving:
            self.memory.schedule_pending = True

    async def put_back(self, *, measured: bool = False) -> None:
        """Put the place at the top: a keyed jump, then the distance into the slot.

        A frame between the two jumps shows the slot's time for that frame (D-250).
        So when the sheet has closed (``measured``), where the heights are usually
        current, a place inside the slot is one offset jump instead: a first try,
        which the next report repeats by key (``again``). Not when today's page has
        just slid in: its reports may still be on their way then.
        """
        self.memory.schedule_pending = False
        place, list_view = self.memory.schedule_place, self.list_ref.current
        target = target_of(self.items, place) if place is not None else None
        if target is None or list_view is None or self.day is None:
            return
        key, into = target
        top = top_of(self.items, self.heights, key) if measured and into else None
        self.user = False
        self.turn += 1
        turn, ends, day = self.turn, self.ends, self.day
        if measured:  # the next report repeats it, unless something moves the list
            self.again = turn
        try:
            if top is not None:
                await list_view.scroll_to(offset=top + into, duration=0)
            else:
                await list_view.scroll_to(scroll_key=ft.ScrollKey(key), duration=0)
            keyed = self.ends
            if top is None and into and self.turn == turn:
                await list_view.scroll_to(delta=into, duration=0)
        except RuntimeError as error:
            if LEFT_THE_PAGE not in str(error):
                raise
            logger.info("Put back %s: the list left the page", key)
            return
        if self.turn != turn:  # a newer scroll owns the list and its offset
            logger.info("Put back %s: a newer scroll took over", key)
            return
        # Flet drops an end within scroll_interval of the last of its type (F70), so
        # the offset a day switch puts back may not be where the put-back went.
        if self.ends != ends:
            if top is None and into and self.ends == keyed:  # the delta's end dropped
                self.memory.schedule_offsets[day] += into
        elif top is not None:
            self.memory.schedule_offsets[day] = top + into
        else:  # where the keyed jump went is Flutter's: today comes back by key
            self.memory.schedule_offsets.pop(day, None)
        logger.info("Put the place back: %s, %.0f dp in", key, into)


def use_today_place(
    memory: ViewMemory,
    day: date,
    list_ref: ft.Ref[ft.ListView],
    slots: tuple[Slot, ...],
    line: int | None,
    *,
    shown: bool,
    excluded: tuple[str, ...],
) -> TodayPlace:
    """The Schedule's ``TodayPlace``, updated with this render (a hook, D-70).

    A render can only hide today's list: it shows once its switch has settled
    (``TodayPlace.shows()``), not while it slides in, since a keyed jump also scrolls
    the day pages to reveal it.

    Args:
        memory: The process's ``ViewMemory``.
        day: Today.
        list_ref: Today's list's ref.
        slots: Today's slots as the filter leaves them.
        line: The now line's index among them; None without a line.
        shown: This render shows today's list.
        excluded: The filter this render lays out.
    """
    place = ft.use_memo(lambda: TodayPlace(memory), [])
    place.lays_out(ft.use_memo(lambda: list_items(slots, line), [slots, line]))
    place.day, place.list_ref, place.shown = day, list_ref, place.shown and shown

    @report_errors
    async def laid_out() -> None:  # after the render's patch went out
        place.filtered(excluded)

    ft.use_effect(laid_out, [excluded])
    return place
