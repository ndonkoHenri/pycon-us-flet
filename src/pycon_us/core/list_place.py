"""Where the reader is in today's Schedule list, so a change of layout keeps it (D-250).

Pure arithmetic over the list's items and their measured heights; the Schedule
measures and scrolls (``screens/schedule_place.py``). A list keeps its pixel offset, not the rows at that offset: when a filter change adds
or removes rows above the top of the screen, or the OS text size changes every row's
height, the same offset shows other rows (#333). Today's list builds every slot
(D-154), so each slot and the now line report their height (``on_size_change``, F51),
and the Schedule can tell which slot is at the top of the list and put it back there:

- ``ListItem`` and ``list_items()``: today's list as it is laid out, slot by slot,
  with the now line among them;
- ``Anchor`` and ``anchor_at()``: where a scroll left the list, the first slot in view
  and how far into it;
- ``offset_of()``: the offset that puts that slot back at the top once the layout has
  changed, or the next shown slot at or after it when the filter hid it;
- ``has_divider()``: which slots draw the 1 dp divider above their time, so a slot's
  measured height and the place its key lands agree with the day list's.

The other days' lists are lazy: Flutter keeps the first item it has built at its
offset and lays the rest out after it, so their slot in view stays put and they need
none of this.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from pycon_us.core.timeline import NOW_KEY, Slot

DIVIDER = 1
"""The height of the divider above a slot's time, in dp (``ft.Divider(height=1)``)."""


def has_divider(index: int, line: int | None) -> bool:
    """Return whether the slot at ``index`` draws a divider above its time.

    Every slot but the first does, except the one just after today's now line: the
    line divides it from the slot above, one line rather than two (D-204).

    Args:
        index: The slot's position in its day's list.
        line: The now line's index (``NowMark.index``), on today's list; else None.
    """
    return index > 0 and index != line


@dataclass(frozen=True)
class ListItem:
    """One item of today's list as it is laid out: a slot or the now line.

    Attributes:
        key: The item's key: the slot's (``Slot.key``) or ``NOW_KEY``.
        start: The slot's start; None for the now line.
        sessions: The ids of the slot's rows, in order; empty for the now line.
        lead: The divider above the slot's time, which a keyed jump leaves above the
            top (D-242): ``DIVIDER`` or 0.
    """

    key: str
    start: datetime | None
    sessions: tuple[str, ...]
    lead: float


def list_items(slots: Sequence[Slot], line: int | None) -> tuple[ListItem, ...]:
    """Return today's list as the day list lays it out: its slots and the now line.

    Args:
        slots: The day's slots as the filter leaves them (``timeline()``).
        line: The now line's index (``NowPlace.line``); None draws no line.
    """
    items = [
        ListItem(
            slot.key,
            slot.start,
            tuple(s.id for s in slot.sessions),
            DIVIDER if has_divider(index, line) else 0,
        )
        for index, slot in enumerate(slots)
    ]
    if line is not None:
        items.insert(line, ListItem(NOW_KEY, None, (), 0))
    return tuple(items)


@dataclass(frozen=True)
class Anchor:
    """Where the reader is in today's list: the first slot in view, and how far in.

    Attributes:
        key: The slot's key (``Slot.key``).
        start: The slot's start, to find the next slot when the filter hides it.
        sessions: The ids of its rows then: while they are the same, the distance
            into the slot still locates the rows that were in view.
        into: How far the list's top was below the slot's top, in dp; negative when
            the now line above the slot showed too.
    """

    key: str
    start: datetime
    sessions: tuple[str, ...]
    into: float


def anchor_at(
    items: Sequence[ListItem], heights: Mapping[str, float], pixels: float
) -> Anchor | None:
    """Return the slot at the top of a list scrolled to ``pixels``, and how far in.

    The first slot whose bottom is below the list's top; past the last slot (the now
    line at the day's end, the padding), the last slot.

    Args:
        items: The list as laid out (``list_items()``).
        heights: Each item's measured height by key, in dp.
        pixels: The list's offset, in dp.

    Returns:
        The anchor; None when the list has no slot or an item above the anchor has
        not reported its height yet.
    """
    top = 0.0
    last: Anchor | None = None
    for item in items:
        height = heights.get(item.key)
        if height is None:
            return None
        if item.start is not None:
            last = Anchor(item.key, item.start, item.sessions, pixels - top)
            if top + height > pixels:
                return last
        top += height
    return last


def offset_of(
    items: Sequence[ListItem], heights: Mapping[str, float], anchor: Anchor
) -> float | None:
    """Return the offset that puts the anchor's slot back at the top of the list.

    The same slot, as far in as it was while its rows are the same; when the filter
    changed its rows, its time, under its divider, since the rows that showed may
    have moved within it; when the filter hid it, the next slot shown after it, or
    the day's last slot.

    Args:
        items: The list as laid out now (``list_items()``).
        heights: Each item's measured height by key, in dp, as laid out now.
        anchor: Where the reader was (``anchor_at()``).

    Returns:
        The offset in dp, never negative; None when the list has no slot or an item
        above the target has not reported its height yet.
    """
    slots = [item for item in items if item.start is not None]
    if not slots:
        return None
    target = next(
        (s for s in slots if s.start is not None and s.start >= anchor.start),
        slots[-1],
    )
    top = 0.0
    for item in items:
        if item is target:
            break
        height = heights.get(item.key)
        if height is None:
            return None
        top += height
    if target.key != anchor.key:
        into = target.lead
    elif target.sessions != anchor.sessions:
        into = min(anchor.into, target.lead)
    else:
        into = anchor.into
    return max(0.0, top + into)
