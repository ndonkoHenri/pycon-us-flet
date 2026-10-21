"""The Schedule keeps the reader's place in each day list across a text-size change (D-331).

A list keeps its pixel offset, and a lazy list keeps the offset of its first built item
by index (F70), so when the text grows the rows above the top grow and earlier rows
show: a slot or more (#337). Flet gives Python no text scale and no event for it (U16),
so the Schedule measures the change itself and puts the place back by key:

- ``layout_probe()``, above the day pages, lays out an invisible "10:00" and reports its
  width and the screen's: a text-size change (or a rotation) changes one of them. It
  sits before the pages, so Flutter lays it out, and reports it, before their items;
- each slot and the now line report their height (``on_size_change``) to
  ``PlaceKeeper.measured()``. Nothing renders from the heights, so D-153's memo holds;
- at each scroll end, ``PlaceKeeper.scrolled()`` records the item at the top and how far
  into it (``core/list_place.place_at()``), in ``ViewMemory.schedule_places``;
- when the measured widths or the time's position (D-216) change, the places' offsets
  are stale (``relaid()``): the shown list is put back at once, by a keyed jump to its
  item and then as far into it as before, scaled (``put_back()``); another day is put
  back when it shows again (``restore()``). Each list is built in full until it is put
  back (``pending()``), so its item is built for the jump (D-154);
- put-backs take turns, and each jump waits for its own scroll end, as every jump
  waits on the one signal, and comes long enough after the list's last end that Flet
  sends its own (F182, D-364).
"""

import asyncio
import contextlib
import logging
import time
from collections.abc import Hashable, Mapping
from dataclasses import replace
from datetime import date

import flet as ft

from pycon_us.core.list_place import Place, place_at, rescaled
from pycon_us.core.timeline import NOW_KEY
from pycon_us.memory import ViewMemory
from pycon_us.ui import scrolling
from pycon_us.ui.scrolling import JUMP_TRIES, SCROLL_EVENT_MS, Jump, jump_to_key

logger = logging.getLogger(__name__)

PROBE_TEXT = "10:00"
"""What the probe lays out: the gutter's widest time, in the gutter's type (D-216)."""

DIVIDER = 1.0
"""The divider above a slot's time, in dp: a keyed jump puts the slot's anchor, under
it, at the top (``schedule_days.SlotItem``)."""

END_GAP_S = SCROLL_EVENT_MS / 1000 + 0.05
"""How long after a list's last scroll end a put-back's next jump waits, in seconds.

Flet sends a list's scroll end only when its last one was at least ``scroll_interval``
before, and drops it otherwise (F182, U162): the jump would move the list and never
say so."""

type Measured = ft.EventHandler[ft.LayoutSizeChangeEvent[ft.LayoutControl]]
"""The probe's handler of one width."""


def layout_probe(on_text: Measured, on_width: Measured) -> ft.Control:
    """Return the Schedule's probe: 0 dp high, it reports a time's width and its own.

    The time is "10:00" in the gutter's type at opacity 0, which Flutter leaves out of
    the semantics; in a row it takes its own width, which changes with the text size,
    and the row the screen's, which changes with a rotation.

    Args:
        on_text: Given the time's width.
        on_width: Given the screen's width.
    """
    time = ft.Container(
        ft.Column(
            [ft.Text(PROBE_TEXT, theme_style=ft.TextThemeStyle.TITLE_SMALL)],
            opacity=0,
        ),
        on_size_change=on_text,
    )
    return ft.Container(ft.Row([time]), height=0, on_size_change=on_width)


def divider_above(keys: tuple[str, ...], key: str) -> float:
    """Return the divider over an item's anchor, in dp, as ``DayList`` draws it.

    Every slot but the first has one, except the slot right under the now line; the
    now line has none.
    """
    index = keys.index(key) if key in keys else 0
    if key == NOW_KEY or index == 0 or keys[index - 1] == NOW_KEY:
        return 0.0
    return DIVIDER


def known_empties(
    heights: Mapping[date, Mapping[str, float]], keys: Mapping[date, tuple[str, ...]]
) -> dict[date, dict[str, float]]:
    """Return the 0 dp heights of the items still laid out, to keep when heights go stale.

    An empty item (the head with nothing to say, D-345) stays 0 dp at any size and with
    any feed, and Flutter reports no size that did not change, so its 0 is kept: else
    every place under it would wait for a report that never comes.

    Args:
        heights: Each day's reported item heights by key, in dp.
        keys: Each day's items in order, as laid out now.
    """
    return {
        day: {
            key: 0.0
            for key, height in day_heights.items()
            if not height and key in keys.get(day, ())
        }
        for day, day_heights in heights.items()
    }


class PlaceKeeper:
    """What the Schedule knows of its day lists' layout, and the jumps that use it.

    One per mounted Schedule (``ft.use_memo``); plain, so a report re-renders nothing.
    The places themselves live in ``ViewMemory``, so a tab return finds them (D-18).

    Attributes:
        memory: The process's ``ViewMemory``.
        heights: Each day's reported item heights by key, in dp, for the current
            layout and text size.
        keys: Each day's items in order, as the last render laid them out.
        layout: What the lists were laid out from: the feed version and the filter.
        text: The probe's time width, in dp; 0 until reported.
        width: The screen's width, in dp; 0 until reported.
        above: Whether slots put their time above their rows (D-216).
        moving: The days whose list is scrolling: a put-back would fight the user.
        last_end: When each day list's last scroll end came (``time.monotonic()``).
        round: Counts put-backs and what supersedes them (a layout change, a jump to
            now), so an older put-back still waiting stops.
        turn: Held by the put-back that is moving a list: one at a time (#600, D-364).
    """

    def __init__(self, memory: ViewMemory) -> None:
        """Start with nothing measured."""
        self.memory = memory
        self.heights: dict[date, dict[str, float]] = {}
        self.keys: Mapping[date, tuple[str, ...]] = {}
        self.layout: Hashable = None
        self.text = 0.0
        self.width = 0.0
        self.above = False
        self.moving: set[date] = set()
        self.last_end: dict[date, float] = {}
        self.round = 0
        self.turn = asyncio.Lock()

    def lay_out(self, layout: Hashable, keys: Mapping[date, tuple[str, ...]]) -> None:
        """Note what the render laid out; another feed or filter forgets the heights.

        All but the 0 dp heights of items it still lays out (``known_empties()``).
        """
        if layout != self.layout:
            self.heights = known_empties(self.heights, keys)
            self.layout = layout
        self.keys = keys

    def measured(self, day: date, key: str, height: float) -> None:
        """Keep an item's reported height."""
        self.heights.setdefault(day, {})[key] = height

    def pending(self, day: date) -> Place | None:
        """Return the day's place when it waits to be put back by key, else None."""
        place = self.memory.schedule_places.get(day)
        if place is None or not place.stale or place.layout != self.layout:
            return None
        return place

    def scrolled(self, day: date, e: ft.OnScrollEvent) -> None:
        """Follow a day list's scroll: a start marks it moving, an end records the place.

        Counted from the top when every item above has reported, as on today's list
        (D-154), else from the place before, as a lazy list's items report while the
        user scrolls through them; unknown, the place is forgotten. A place that waits
        for its put-back is kept: the heights may still be on their way.
        """
        if e.event_type in (ft.ScrollType.START, ft.ScrollType.UPDATE):
            self.moving.add(day)
            return
        if e.event_type != ft.ScrollType.END:
            return
        self.moving.discard(day)
        self.last_end[day] = time.monotonic()
        places = self.memory.schedule_places
        kept = places.get(day)
        if kept is not None and kept.layout != self.layout:
            kept = None
        if kept is not None and kept.stale:
            return
        keys, heights = self.keys.get(day, ()), self.heights.get(day, {})
        found = place_at(keys, heights, e.pixels) or place_at(
            keys, heights, e.pixels, near=kept
        )
        if found is None:
            places.pop(day, None)
        else:
            places[day] = replace(found, layout=self.layout, above=self.above)

    def relaid(
        self,
        *,
        text: float | None = None,
        width: float | None = None,
        above: bool | None = None,
    ) -> bool:
        """Note a measurement; return whether it made the places' offsets stale.

        The first complete measurement only records the basis. After that, a change of
        the text size, the width or the time's position forgets every height but the
        0 dp ones, which no change of size reports again, and marks every place to be
        put back by key (``pending()``).

        Args:
            text: The probe's time width, in dp.
            width: The screen's width, in dp.
            above: Whether slots put their time above their rows.
        """
        self.text = self.text if text is None else text
        self.width = self.width if width is None else width
        self.above = self.above if above is None else above
        if not (self.text and self.width):
            return False
        basis = (self.text, self.width, self.above)
        before, self.memory.schedule_basis = self.memory.schedule_basis, basis
        if before is None or before == basis:
            return False
        self.round += 1  # a put-back still waiting scales for the old layout
        self.heights = known_empties(self.heights, self.keys)
        places = self.memory.schedule_places
        for day, place in places.items():
            places[day] = replace(place, stale=True)
        logger.info("The layout changed: %d places to put back", len(places))
        return bool(places)

    async def put_back(
        self, day: date, list_ref: ft.Ref[ft.ListView], ended: asyncio.Event
    ) -> bool:
        """Put a day list back at its place: a keyed jump, then as far into the item.

        A keyed jump reaches only a built item (F7). When the text shrank, the item at
        the top can fall out of the built range: then the list first jumps to the item's
        old offset, which is near it, and the keyed jump follows. Instant, as the change
        it undoes. Nothing while the list scrolls (the place is then forgotten), or when
        the day has no place to put back.

        Put-backs take turns (#600, D-364): every jump waits on the one scroll-end
        signal, so a put-back waits for the one before it to stop, and each jump waits
        for its own end, so no end answers a later jump; each comes ``END_GAP_S`` after
        the list's last end, so Flet sends its end (F182). At the largest sizes a text-size
        change is two layout changes, the text's width and then the time's position
        (D-216): the first put-back stops at its jump's end, and the second jumps in
        the final layout. A newer change (``round``) stops a put-back after any wait,
        before it moves the list again.

        Args:
            day: The list's day.
            list_ref: The list's ref.
            ended: The screen's scroll-end signal (``Signals.ended``).

        Returns:
            Whether a place waited for it, so the screen re-renders the list lazy again.
        """
        if self.pending(day) is None:
            return False
        self.round += 1
        mine = self.round
        async with self.turn:
            place = self.pending(day)
            if mine != self.round or place is None:  # superseded while it waited
                return False
            if day in self.moving:
                del self.memory.schedule_places[day]
                return True
            jump = await self._keyed(mine, day, place.key, list_ref, ended)
            if jump == "still":
                jump = await self._from_old_top(mine, day, place, list_ref, ended)
            if mine != self.round:  # a newer change took over
                return False
            if jump != "landed":  # no end, so no offset to count from
                self.memory.schedule_places.pop(day, None)
                return True
            return await self._go_into(mine, day, place, list_ref, ended)

    async def _go_into(
        self,
        mine: int,
        day: date,
        place: Place,
        list_ref: ft.Ref[ft.ListView],
        ended: asyncio.Event,
    ) -> bool:
        """Scroll from the item's top, where the keyed jump landed, as far into it.

        Returns:
            Whether the place was put back: False when a newer change took over.
        """
        landed = self.memory.schedule_offsets.get(day, 0.0)  # its end recorded it
        height = self.heights.get(day, {}).get(place.key)
        into = self._into(place, height)
        target = landed - divider_above(self.keys.get(day, ()), place.key) + into
        if target != landed and list_ref.current is not None:
            await self._to_offset(mine, day, list_ref.current, target, ended)
            if mine != self.round:
                return False
        self.memory.schedule_offsets[day] = target
        self.memory.schedule_places[day] = replace(
            place,
            into=into,
            height=place.height if height is None else height,
            pixels=target,
            stale=False,
            above=self.above,
        )
        logger.info("Put the place back: %s, %.0f dp in", place.key, into)
        return True

    def _into(self, place: Place, height: float | None) -> float:
        """Return how far into the place's item to put the top, in dp.

        As far in as before, scaled to the item's height in this layout
        (``rescaled()``). The item's top when the time has moved above its rows or back
        since (D-216), as the distance measured rows laid out the other way; or when
        the item has not reported its height in this layout yet, as a height from
        another layout would scale it past the item (#600, D-364).

        Args:
            place: The place to put back.
            height: The item's reported height in this layout, or None.
        """
        if height is None or place.above != self.above:
            return 0.0
        return rescaled(place, height)

    async def _from_old_top(
        self,
        mine: int,
        day: date,
        place: Place,
        list_ref: ft.Ref[ft.ListView],
        ended: asyncio.Event,
    ) -> Jump:
        """Jump to the place's old top, then ask for the keyed jump again, a try at a time.

        The item fell out of the built range (F7), and its old offset is near it. Each
        step waits on the device, and a newer change (a jump to now, another layout)
        may take over meanwhile: then it stops at once, before it moves the list again,
        and ``put_back()`` sees the change in ``round``.

        Args:
            mine: The put-back's ``round``.
            day: The list's day.
            place: The place to put back.
            list_ref: The list's ref.
            ended: The screen's scroll-end signal (``Signals.ended``).

        Returns:
            How the last keyed jump ended; "still" when it asked none.
        """
        if mine != self.round or list_ref.current is None:
            return "still"
        old_top = place.pixels - place.into
        await self._to_offset(mine, day, list_ref.current, old_top, ended)
        for _ in range(JUMP_TRIES):
            if mine != self.round:
                return "still"
            jump = await self._keyed(mine, day, place.key, list_ref, ended)
            if jump != "still":
                return jump
        return "still"

    async def ended_apart(self, day: date) -> None:
        """Wait until a scroll end of the day's list would reach Python (F182).

        ``END_GAP_S`` after its last end, as Flet drops an end that comes sooner. It
        yields at least once, so a render asked before the jump (the list built in
        full, ``schedule.py``) reaches the device first.
        """
        last = self.last_end.get(day, -END_GAP_S)
        await asyncio.sleep(max(0.0, last + END_GAP_S - time.monotonic()))

    async def _keyed(
        self,
        mine: int,
        day: date,
        key: str,
        list_ref: ft.Ref[ft.ListView],
        ended: asyncio.Event,
    ) -> Jump:
        """Jump to the item with this key, once, so that its end reaches Python.

        "still" without a jump when a newer change took over (``round``) during the wait.
        """
        await self.ended_apart(day)
        if mine != self.round:
            return "still"
        return await jump_to_key(list_ref, key, duration=0, ended=ended, tries=1)

    async def _to_offset(
        self,
        mine: int,
        day: date,
        list_view: ft.ListView,
        offset: float,
        ended: asyncio.Event,
    ) -> None:
        """Jump to an offset, and wait for that scroll's end (#600, D-364).

        So its end cannot answer a keyed jump asked after it: every jump waits on the
        one signal. A list already there sends no end: the wait gives up after
        ``LANDING_S``. Nothing when a newer change took over (``round``) during the wait.
        """
        await self.ended_apart(day)
        if mine != self.round:
            return
        ended.clear()
        await list_view.scroll_to(offset=offset, duration=0)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(ended.wait(), scrolling.LANDING_S)

    def supersede(self, day: date) -> None:
        """Forget the day's place, as a jump to now takes its list elsewhere.

        A put-back still waiting stops, and the jump's scroll end records the new place:
        else a stale place would wait for a put-back that never comes, and keep every
        later scroll end from counting (``scrolled()``).
        """
        self.round += 1
        self.memory.schedule_places.pop(day, None)

    async def restore(
        self, day: date, list_ref: ft.Ref[ft.ListView], ended: asyncio.Event
    ) -> bool:
        """Put a day list that shows again where it was (D-18, D-331).

        By key when a text-size change made its offset stale (``put_back()``), else at
        the offset where its last scroll ended. A day list that shows again is a new
        list on the device, at the top: the tab bar's pages keep nothing of a page they
        no longer show.

        Returns:
            Whether it was put back by key, so the screen re-renders the list lazy.
        """
        if self.pending(day) is not None:
            return await self.put_back(day, list_ref, ended)
        offset = self.memory.schedule_offsets.get(day)
        if offset and list_ref.current is not None:
            await list_ref.current.scroll_to(offset=offset, duration=0)
        return False
