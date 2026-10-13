"""Scrolling a list to a keyed item: Jump to now and the lists that open at a place.

``scroll_to(scroll_key=...)`` reaches only an item Flutter has built (F7, F32), so a list
that must reach any of its items gets ``cache_extent=FULL_LIST_EXTENT``, which builds
them all (D-154): today's Schedule list, and My schedule's (#94). ``jump_to_key()`` is
the one jump (D-155): it handles the ways a keyed ``scroll_to`` fails quietly or late,
and says how it ended. The policy of when to jump (the Schedule's: once per conference
day, never on Back, a refresh or a filter change, D-18 and D-204) is the screen's.
"""

import asyncio
import logging
from typing import Literal

import flet as ft

logger = logging.getLogger(__name__)

FULL_LIST_EXTENT = 100_000
"""A list's ``cache_extent`` that builds every item, in logical pixels (D-154): more
than three times the busiest day at 200 % text (about 26,000 px, S2)."""

JUMP_MS = 400
"""How long a keyed jump takes (ux.md §3.8): to now on the Schedule, to the slot or
the now line, and to a row on a room's page; ``prefs.motion_ms()`` makes it 0 under
reduced motion (D-34)."""

SCROLL_EVENT_MS = 250
"""How often a list may send each kind of scroll event (``scroll_interval``): the
screens read only the end of a scroll, so the many updates of a fling need not all
cross to Python."""

JUMP_TRIES = 3
"""How many times ``jump_to_key()`` asks for the scroll before it gives up."""

LANDING_S = 0.5
"""How long after its duration a scroll may take to report its end, in seconds."""


type Jump = Literal["landed", "still", "failed"]
"""How a jump ended: a scroll ended; no scroll in ``JUMP_TRIES`` tries; or no list."""

LEFT_THE_PAGE = "added to the page first"
"""Part of the error Flet raises for a call on a control no longer under the page."""


async def jump_to_key(
    list_ref: ft.Ref[ft.ListView],
    key: str,
    *,
    duration: int,
    ended: asyncio.Event,
) -> Jump:
    """Scroll a list so the item with this ``ScrollKey`` is at the top (D-155).

    The list's ``on_scroll`` handler sets ``ended`` at each scroll's end, which is how
    the jump knows it landed: Flutter answers ``scroll_to`` before the scroll runs, and
    does nothing when the item has not been built yet, so the call alone proves
    nothing. Without an end in time the jump asks again, up to ``JUMP_TRIES`` times.
    An item already in place never scrolls either, so a list that stays still is
    "still", not "failed": on a list that builds every item (D-154) that means the
    item is in place.

    The jump fails, and asks no more, when there is no list to scroll:

    - the ref is unset (the list was never built, or is gone);
    - the list has left the page: the user switched tabs (D-142) while a jump started
      from a handler was waiting, and Flet raises a ``RuntimeError`` saying the
      control "must be added to the page first" (logged);
    - Flutter waited 10 s for a list that is not built yet (a tab still sliding in) to
      register its methods, then failed with a ``TimeoutException``, which Flet raises
      as a ``RuntimeError`` (logged as a warning).

    Any other error propagates.

    Args:
        list_ref: The list's ref.
        key: The item's ``ScrollKey`` value, e.g. a ``Slot.key``.
        duration: The scroll's length in milliseconds, already through
            ``prefs.motion_ms()``.
        ended: Set by the list's ``on_scroll`` when a scroll ends.

    Returns:
        "landed" when the list reported a scroll that ended, "still" when it reported
        none in ``JUMP_TRIES`` tries, "failed" when there was no list to scroll.
    """
    for attempt in range(1, JUMP_TRIES + 1):
        list_view = list_ref.current
        if list_view is None:
            return "failed"
        ended.clear()
        try:
            await list_view.scroll_to(scroll_key=ft.ScrollKey(key), duration=duration)
        except RuntimeError as error:
            if LEFT_THE_PAGE in str(error):
                logger.info("Jump to %s: the list left the page", key)
                return "failed"
            if "TimeoutException" not in str(error):
                raise
            logger.warning("Jump to %s: the list was not shown in time", key)
            return "failed"
        try:
            await asyncio.wait_for(ended.wait(), duration / 1000 + LANDING_S)
        except TimeoutError:
            continue  # not built yet, or already in place
        logger.info("Jumped to %s (try %d)", key, attempt)
        return "landed"
    logger.info("Jump to %s: the list did not move after %d tries", key, JUMP_TRIES)
    return "still"
