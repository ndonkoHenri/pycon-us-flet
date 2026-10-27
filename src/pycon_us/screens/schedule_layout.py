"""What the Schedule measures of its day lists, and the places it records (D-331, D-371).

The knowledge half of ``screens/schedule_place.py``'s ``PlaceKeeper``, which adds the
jumps that put a place back:

- ``layout_probe()``, above the day pages, reports a time's width and the screen's, so
  a text-size change (or a rotation) shows; ``LayoutRecord.relaid()`` turns it into
  stale places;
- ``LayoutRecord`` keeps each day list's item heights, records the place at each scroll
  end (``scrolled()``) and carries the places across a filter change (``lay_out()``,
  ``refilter()``), with the pure helpers ``divider_above()``, ``unchanged_keys()`` and
  ``known_empties()``.
"""

import asyncio
import logging
import time
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import date

import flet as ft

from pycon_us.core.list_place import Place, carried, place_at
from pycon_us.core.timeline import NOW_KEY, Slot
from pycon_us.memory import ViewMemory

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


def divider_above(keys: Sequence[str], key: str) -> float:
    """Return the divider over an item's anchor, in dp, as ``DayList`` draws it.

    Every slot but the first has one, except the slot right under the now line; the
    now line has none.
    """
    index = keys.index(key) if key in keys else 0
    if key == NOW_KEY or index == 0 or keys[index - 1] == NOW_KEY:
        return 0.0
    return DIVIDER


def unchanged_keys(
    before: Sequence[str],
    after: Sequence[str],
    slots_before: Mapping[str, Slot],
    slots_after: Mapping[str, Slot],
) -> frozenset[str]:
    """Return the items of a day list whose height a filter change kept.

    The now line, and each slot with the same sessions and the same divider above it
    (``divider_above()``): ``Slot``s compare their sessions by identity.

    Args:
        before: The list's items before the change, in order.
        after: The list's items after it, in order.
        slots_before: The list's slots by key before the change.
        slots_after: The list's slots by key after it.
    """
    return frozenset(
        key
        for key in after
        if key == NOW_KEY
        or (
            key in slots_before
            and slots_before[key] == slots_after.get(key)
            and divider_above(before, key) == divider_above(after, key)
        )
    )


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


class LayoutRecord:
    """What the Schedule knows of its day lists' layout, and the places it records.

    ``PlaceKeeper`` (``schedule_place.py``) adds the jumps that use it; plain, so a
    report re-renders nothing. The places themselves live in ``ViewMemory``, so a tab
    return finds them (D-18).

    Attributes:
        memory: The process's ``ViewMemory``.
        heights: Each day's reported item heights by key, in dp, for the current
            layout and text size.
        keys: Each day's items in order, as the last render laid them out.
        slots: Each day's slots by key, as the last render laid them out.
        layout: What the lists were laid out from: the feed version and the filter.
        refiltered: A filter change waits for the shown list's put-back
            (``put_back_refiltered()``).
        reported: Set by every height report: Flutter has laid out a change.
        text: The probe's time width, in dp; 0 until reported.
        width: The screen's width, in dp; 0 until reported.
        above: Whether slots put their time above their rows (D-216).
        moving: The days whose list is scrolling: a put-back would fight the user.
        jumping: The days whose list a put-back has asked to move, until its scroll
            end: a scroll that starts at any other time is the user's.
        last_end: When each day list's last scroll end came (``time.monotonic()``).
        round: Counts put-backs and what supersedes them (a layout change, a jump to
            now), so an older put-back still waiting stops.
    """

    def __init__(self, memory: ViewMemory) -> None:
        """Start with nothing measured."""
        self.memory = memory
        self.heights: dict[date, dict[str, float]] = {}
        self.keys: Mapping[date, tuple[str, ...]] = {}
        self.slots: Mapping[date, Mapping[str, Slot]] = {}
        self.layout: tuple[int, tuple[str, ...]] | None = None
        self.refiltered = False
        self.reported = asyncio.Event()
        self.text = 0.0
        self.width = 0.0
        self.above = False
        self.moving: set[date] = set()
        self.jumping: set[date] = set()
        self.last_end: dict[date, float] = {}
        self.round = 0

    def lay_out(
        self,
        version: int,
        excluded: tuple[str, ...],
        keys: Mapping[date, tuple[str, ...]],
        slots: Mapping[date, Mapping[str, Slot]],
    ) -> None:
        """Note what the render laid out: the feed version, the filter and the items.

        Another feed forgets every height but the 0 dp ones of items it still lays out
        (``known_empties()``), and its places say nothing of it. Another filter of the
        same feed keeps the heights of the items it left as they were and carries each
        place into the new list, to be put back (``refilter()``, D-371).

        Args:
            version: The feed's version.
            excluded: The filter, ``Prefs.excluded_tracks``.
            keys: Each day's items in order (``schedule._keys()``).
            slots: Each day's slots by key.
        """
        layout = (version, excluded)
        if self.layout is not None and layout != self.layout:
            if version == self.layout[0]:
                self.refilter(layout, keys, slots)
            else:
                self.heights = known_empties(self.heights, keys)
        self.layout = layout
        self.keys = keys
        self.slots = slots

    def refilter(
        self,
        layout: tuple[int, tuple[str, ...]],
        keys: Mapping[date, tuple[str, ...]],
        slots: Mapping[date, Mapping[str, Slot]],
    ) -> None:
        """Carry each day's place into the list a filter change lays out (#333, D-371).

        Its item, or the next one still shown (``carried()``), stale, so the list is
        built in full and put back by key; a place from an older layout, which says
        nothing, is left as it is. The heights of the items the change kept stay
        (``unchanged_keys()``): Flutter reports no size that did not change.
        """
        kept: dict[date, dict[str, float]] = known_empties(self.heights, keys)
        places = self.memory.schedule_places
        for day, after in keys.items():
            before = self.keys.get(day, ())
            old, new = self.slots.get(day, {}), slots.get(day, {})
            same = unchanged_keys(before, after, old, new)
            heights = self.heights.get(day, {})
            kept.setdefault(day, {}).update(
                (key, heights[key]) for key in same if key in heights
            )
            place = places.get(day)
            if place is None or place.layout != self.layout:
                continue
            starts = {key: slot.start for key, slot in (*old.items(), *new.items())}
            moved = carried(place, before, after, same, starts)
            if moved is None:
                del places[day]
            else:
                places[day] = replace(moved, layout=layout)
        self.heights = kept
        self.round += 1  # a put-back still waiting is for the old list
        self.refiltered = True
        self.reported.clear()

    def measured(self, day: date, key: str, height: float) -> None:
        """Keep an item's reported height; Flutter has laid out a change."""
        self.heights.setdefault(day, {})[key] = height
        self.reported.set()

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
        for its put-back is kept at a put-back's own end, as the heights may still be on
        their way, and dropped when the user starts a scroll (``jumping``, D-371).
        """
        if e.event_type in (ft.ScrollType.START, ft.ScrollType.UPDATE):
            self.moving.add(day)
            if day not in self.jumping and self.pending(day) is not None:
                # The user's scroll wins (D-371): its end records the new place.
                del self.memory.schedule_places[day]
            return
        if e.event_type != ft.ScrollType.END:
            return
        self.moving.discard(day)
        self.jumping.discard(day)
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
