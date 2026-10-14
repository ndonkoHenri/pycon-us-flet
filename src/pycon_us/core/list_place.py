"""Where the reader is in today's Schedule list, as a key, so a filter change keeps it (D-250).

Pure: the Schedule measures and scrolls (``screens/schedule_place.py``). A list keeps
its pixel offset, not the rows at that offset, so a filter change that adds or removes
rows above the top shows other rows (#333, F70). The place is therefore the item at the
top and how far into it, which a keyed jump puts back:

- ``ListItem`` and ``list_items()``: today's list as ``DayList`` lays it out, its slots
  with the now line among them;
- ``Place`` and ``place_at()``: the item at the top of a list scrolled to an offset, from
  the heights its items reported; ``place_of()``, an item's top, where a jump to now
  leaves it;
- ``target_of()``: where that place is in the list as the filter now leaves it, and
  ``top_of()``, where an item starts once every item above it has reported.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from pycon_us.core.timeline import NOW_KEY, Slot

DIVIDER = 1.0
"""The divider above a slot's time, in dp: a keyed jump leaves it above the top, so a
place this close to a slot's top is its top."""


@dataclass(frozen=True)
class ListItem:
    """One item of today's list: a slot or the now line.

    Attributes:
        key: The slot's key (``Slot.key``) or ``NOW_KEY``.
        start: The slot's start; None for the now line.
        sessions: The ids of the slot's rows, in order; empty for the now line.
    """

    key: str
    start: datetime | None
    sessions: tuple[str, ...]


def list_items(slots: Sequence[Slot], line: int | None) -> tuple[ListItem, ...]:
    """Return today's list as ``DayList`` lays it out: the now line before ``slots[line]``.

    Args:
        slots: The day's slots as the filter leaves them (``timeline()``).
        line: The now line's index (``NowPlace.line``); None draws no line.
    """
    items = [
        ListItem(slot.key, slot.start, tuple(s.id for s in slot.sessions))
        for slot in slots
    ]
    if line is not None:
        items.insert(line, ListItem(NOW_KEY, None, ()))
    return tuple(items)


@dataclass(frozen=True)
class Place:
    """The item at the top of today's list, and how far the top is into it.

    Attributes:
        key: The item's key.
        start: The slot's start, to find the next slot when the filter hides it; None
            for the now line.
        sessions: The ids of the slot's rows then: while they are the same, the
            distance into it still finds the rows that were at the top.
        into: How far the list's top was below the item's top, in dp.
    """

    key: str
    start: datetime | None
    sessions: tuple[str, ...]
    into: float


def place_at(
    items: Sequence[ListItem], heights: Mapping[str, float], pixels: float
) -> Place | None:
    """Return the item at the top of a list scrolled to ``pixels``.

    The first item whose bottom is below the list's top.

    Args:
        items: The list as laid out (``list_items()``).
        heights: Each item's reported height by key, in dp.
        pixels: The list's offset, in dp.

    Returns:
        The place; None when an item above it has not reported its height yet, or the
        offset is past the last item.
    """
    top = 0.0
    for item in items:
        height = heights.get(item.key)
        if height is None:
            return None
        if top + height > pixels:
            return Place(item.key, item.start, item.sessions, pixels - top)
        top += height
    return None


def place_of(items: Sequence[ListItem], key: str) -> Place | None:
    """Return the top of the item ``key``, where a keyed jump puts it; None if absent."""
    item = next((item for item in items if item.key == key), None)
    return Place(item.key, item.start, item.sessions, 0.0) if item else None


def top_of(
    items: Sequence[ListItem], heights: Mapping[str, float], key: str
) -> float | None:
    """Return the offset at which the item ``key`` starts, from the heights above it.

    Returns:
        The offset in dp; None when ``key`` is absent or an item above it has not
        reported its height.
    """
    top = 0.0
    for item in items:
        if item.key == key:
            return top
        height = heights.get(item.key)
        if height is None:
            return None
        top += height
    return None


def target_of(items: Sequence[ListItem], place: Place) -> tuple[str, float] | None:
    """Return where the place is in the list now: an item's key and a distance into it.

    The same item while the filter shows it, as far in while its rows are the same,
    else at its time; when the filter hid the slot, the next one shown after it, else
    the day's last.

    Returns:
        The item's key and the distance into it, in dp; None when the list has no slot.
    """
    same = next((item for item in items if item.key == place.key), None)
    if same is not None:
        kept = same.sessions == place.sessions and place.into > DIVIDER
        return same.key, place.into if kept else 0.0
    slots = [item for item in items if item.start is not None]
    if place.start is None or not slots:
        return None
    start = place.start
    after = next((s for s in slots if s.start is not None and s.start >= start), None)
    return (after or slots[-1]).key, 0.0
