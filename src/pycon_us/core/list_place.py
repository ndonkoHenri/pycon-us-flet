"""Where the reader is in a Schedule day list, as a key, so a text-size or filter change keeps it.

Pure: ``screens/schedule_place.py`` measures and scrolls. A list keeps its pixel offset,
not the rows at that offset, so when the text grows every row above the top grows with
it and earlier rows show (#337, F70). The place is therefore the item at the top and how
far into it, which a keyed jump puts back once the list has its new heights:

- ``Place``: that item's key, how far into it the top was, its height then, the offset
  where it was found, and whether the slots had their time above their rows;
- ``place_at()``: the place at an offset, from the heights the items reported, counted
  from the list's top or from a place found at another offset;
- ``rescaled()``: how far into the item to put the top once it has its new height
  (D-331);
- ``carried()``: the place in the list a filter change lays out, its item or the next one
  still shown (D-371).
"""

from collections.abc import Collection, Hashable, Mapping, Sequence
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Place:
    """The item at the top of a day list, and how far the list's top is into it.

    Attributes:
        key: The item's key: a slot's ``Slot.key``, or the now line's ``NOW_KEY``.
        into: How far the list's top was below the item's top, in dp.
        height: The item's height then, in dp, so the distance can grow with it.
        pixels: The list's offset at that place.
        layout: What the list was laid out from (the feed version and the filter): a
            place from another layout says nothing about this one.
        stale: A text-size change has moved the rows since: ``pixels`` and ``height``
            are from before it, until the place is put back.
        above: Whether the slots had their time above their rows (D-216): ``into``
            measured rows laid out that way, so it says nothing of the other (#600).
    """

    key: str
    into: float
    height: float
    pixels: float
    layout: Hashable = None
    stale: bool = False
    above: bool = False


def place_at(
    keys: Sequence[str],
    heights: Mapping[str, float],
    pixels: float,
    *,
    near: Place | None = None,
) -> Place | None:
    """Return the item at the top of a list scrolled to ``pixels``.

    Counted from the list's top, or from ``near``, a place found at another offset of
    the same layout: then only the items between the two offsets need their heights,
    which a lazy list has reported as the user scrolled through them.

    Args:
        keys: The list's items, in order.
        heights: Each item's reported height by key, in dp.
        pixels: The list's offset, in dp.
        near: A place known at another offset of this layout, not stale; None counts
            from the top.

    Returns:
        The place, its ``layout`` that of ``near``; None when an item on the way has
        not reported its height, ``near``'s item is gone, or the offset is past the
        last item.
    """
    if near is None:
        index, into = 0, pixels
    elif near.key in keys:
        index, into = keys.index(near.key), near.into + pixels - near.pixels
    else:
        return None
    while into < 0:  # above the item: walk up
        if index == 0:
            into = 0.0  # pulled past the top
            break
        index -= 1
        height = heights.get(keys[index])
        if height is None:
            return None
        into += height
    while index < len(keys):
        height = heights.get(keys[index])
        if height is None:
            return None
        if into < height:
            layout = near.layout if near else None
            return Place(keys[index], into, height, pixels, layout)
        into -= height
        index += 1
    return None


def rescaled(place: Place, height: float) -> float:
    """Return how far into the place's item to put the top now that it is ``height``.

    As far in proportionally, so the same rows of a slot stay at the top when its
    text grows (D-331); always inside the item.

    Args:
        place: The place, with the item's height when it was found.
        height: The item's height now, in dp.
    """
    if place.height <= 0 or height <= 0:
        return 0.0
    return max(0.0, min(place.into * height / place.height, height - 1))


def carried(
    place: Place,
    before: Sequence[str],
    after: Sequence[str],
    unchanged: Collection[str],
) -> Place | None:
    """Return the place in the list a filter change lays out, waiting to be put back.

    The same item when it is still shown, as far in when its rows are unchanged, else
    at its top; when it is hidden, the top of the next item that is still shown (#333,
    D-371). Stale, so the Schedule puts it back by key (``PlaceKeeper.pending()``).

    Args:
        place: The place in the list before the change.
        before: The list's items before the change, in order.
        after: The list's items after it, in order.
        unchanged: The items whose rows, and so whose heights, the change kept.

    Returns:
        The place, its ``layout`` still ``place``'s; None when no item at or after
        ``place``'s is still shown.
    """
    if place.key in after:
        into = place.into if place.key in unchanged else 0.0
        return replace(place, into=into, stale=True)
    index = before.index(place.key) if place.key in before else len(before)
    for key in before[index + 1 :]:
        if key in after:
            return replace(place, key=key, into=0.0, stale=True)
    return None
