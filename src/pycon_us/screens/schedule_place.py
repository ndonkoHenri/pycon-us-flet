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
  back when it shows again (``restore()``), built in full until then (``pending()``),
  so its item is built for the jump (D-154).
"""

import asyncio
import logging
from collections.abc import Hashable, Mapping
from dataclasses import replace
from datetime import date

import flet as ft

from pycon_us.core.list_place import Place, place_at, rescaled
from pycon_us.core.timeline import NOW_KEY
from pycon_us.memory import ViewMemory
from pycon_us.ui.scrolling import jump_to_key

logger = logging.getLogger(__name__)

PROBE_TEXT = "10:00"
"""What the probe lays out: the gutter's widest time, in the gutter's type (D-216)."""

DIVIDER = 1.0
"""The divider above a slot's time, in dp: a keyed jump puts the slot's anchor, under
it, at the top (``schedule_days.SlotItem``)."""

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
        round: Counts put-backs, so a newer one stops an older one still waiting.
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
        self.round = 0

    def lay_out(self, layout: Hashable, keys: Mapping[date, tuple[str, ...]]) -> None:
        """Note what the render laid out; another feed or filter forgets the heights."""
        if layout != self.layout:
            self.heights.clear()
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
            places[day] = replace(found, layout=self.layout)

    def relaid(
        self,
        *,
        text: float | None = None,
        width: float | None = None,
        above: bool | None = None,
    ) -> bool:
        """Note a measurement; return whether it made the places' offsets stale.

        The first complete measurement only records the basis. After that, a change of
        the text size, the width or the time's position forgets every height and marks
        every place to be put back by key (``pending()``).

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
        self.heights.clear()
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
        it undoes. Nothing while the list scrolls (the place is
        then forgotten), or when the day has no place to put back.

        Args:
            day: The list's day.
            list_ref: The list's ref.
            ended: The screen's scroll-end signal (``Signals.ended``).

        Returns:
            Whether a place waited for it, so the screen re-renders the list lazy again.
        """
        place = self.pending(day)
        if place is None:
            return False
        if day in self.moving:
            del self.memory.schedule_places[day]
            return True
        self.round += 1
        mine = self.round
        jump = await jump_to_key(list_ref, place.key, duration=0, ended=ended, tries=1)
        if jump == "still" and mine == self.round and list_ref.current is not None:
            old_top = place.pixels - place.into
            await list_ref.current.scroll_to(offset=old_top, duration=0)
            jump = await jump_to_key(list_ref, place.key, duration=0, ended=ended)
        if mine != self.round:  # a newer change took over
            return False
        if jump != "landed":  # no end, so no offset to count from
            self.memory.schedule_places.pop(day, None)
            return True
        landed = self.memory.schedule_offsets.get(day, 0.0)  # its end recorded it
        height = self.heights.get(day, {}).get(place.key, place.height)
        into = rescaled(place, height)
        target = landed - divider_above(self.keys.get(day, ()), place.key) + into
        if target != landed and list_ref.current is not None:
            await list_ref.current.scroll_to(offset=target, duration=0)
        self.memory.schedule_offsets[day] = target
        self.memory.schedule_places[day] = replace(
            place, into=into, height=height, pixels=target, stale=False
        )
        logger.info("Put the place back: %s, %.0f dp in", place.key, into)
        return True

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
