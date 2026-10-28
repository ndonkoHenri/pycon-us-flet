"""The Schedule's day lists as data: their slots, their keys and their put-back.

``screens/schedule.py`` owns the screen; here is what it derives for its day lists
(D-153, D-178, D-331, D-371):

- ``use_day_slots()``, each day's slots under the track filter, their session ids and
  their slots by key, memoised per feed version and filter;
- ``slot_keys()``, each list's item keys in order, as ``PlaceKeeper`` counts a place;
- ``default_day()``, ``filter_tracks()`` and ``empty_reason()``, the day the Schedule
  opens on, the tracks the filter offers and why a day shows no slots;
- ``use_put_back()``, which puts the shown list back on its item after a text-size,
  width, time-position or filter change (``screens/schedule_place.py``).
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date

import flet as ft

from pycon_us.core.models import ConferenceData
from pycon_us.core.timeline import NOW_KEY, NowPlace, Slot, timeline
from pycon_us.screens.schedule_days import Empty
from pycon_us.screens.schedule_head import HEAD_KEY
from pycon_us.screens.schedule_place import PlaceKeeper
from pycon_us.services.errors import report_errors

type Measured = Callable[[ft.LayoutSizeChangeEvent[ft.LayoutControl]], Awaitable[None]]
"""A handler of ``layout_probe()``'s reports: the text's width, or the screen's."""


@dataclass(frozen=True)
class DaySlots:
    """Each day's slots, from ``use_day_slots()``; memoised, so equal across renders.

    Attributes:
        slots: Each day's slots under the track filter, in schedule order.
        ids: Each day's session ids, the slots' sessions (D-153).
        by_key: Each day's slots by slot key, for ``PlaceKeeper.lay_out()``.
    """

    slots: dict[date, tuple[Slot, ...]]
    ids: dict[date, frozenset[str]]
    by_key: dict[date, dict[str, Slot]]


def use_day_slots(
    data: ConferenceData | None,
    all_days: tuple[date, ...],
    excluded: tuple[str, ...],
    version: int,
) -> DaySlots:
    """Return each day's slots, memoised per feed version and filter (D-153).

    A hook: call it unconditionally, at the top of the Schedule (D-70).

    Args:
        data: The processed feed; None before any.
        all_days: The conference days, sprint days included.
        excluded: The track keys the filter hides (``Prefs.excluded_tracks``).
        version: ``Conference.version``, which changes with the feed.
    """
    slots = ft.use_memo(
        lambda: (
            {day: timeline(data, day, excluded) for day in all_days} if data else {}
        ),
        [version, excluded],
    )
    ids = ft.use_memo(
        lambda: {
            day: frozenset(s.id for slot in day_slots for s in slot.sessions)
            for day, day_slots in slots.items()
        },
        [slots],
    )
    by_key = ft.use_memo(
        lambda: {
            day: {slot.key: slot for slot in day_slots}
            for day, day_slots in slots.items()
        },
        [slots],
    )
    return DaySlots(slots, ids, by_key)


def list_ref(refs: dict[date, ft.Ref[ft.ListView]], day: date) -> ft.Ref[ft.ListView]:
    """Return the day list's ref, one per day for the screen's life (F38)."""
    return refs.setdefault(day, ft.Ref[ft.ListView]())


def slot_keys(
    slots: dict[date, tuple[Slot, ...]],
    current: date,
    place: NowPlace | None,
    *,
    head: bool,
) -> dict[date, tuple[str, ...]]:
    """Return each day list's item keys in order: its slots, today's now line among them.

    With ``head``, at the largest text sizes, each list starts with the head (D-345).
    """
    first = (HEAD_KEY,) if head else ()
    keys = {
        day: (*first, *(slot.key for slot in day_slots))
        for day, day_slots in slots.items()
    }
    if place is not None:
        today = keys[current]
        line = place.line + len(first)
        keys[current] = (*today[:line], NOW_KEY, *today[line:])
    return keys


def default_day(all_days: tuple[date, ...], current: date) -> date | None:
    """Return the day the Schedule opens on: today during the conference, else day 1."""
    if current in all_days:
        return current
    return all_days[0] if all_days else None


def filter_tracks(
    data: ConferenceData | None, all_days: tuple[date, ...]
) -> frozenset[str]:
    """Return the track keys of the sessions the Schedule can show, on any day.

    The filter offers these and no other (D-20): a chip for a track without sessions
    would change nothing.
    """
    if data is None:
        return frozenset()
    return frozenset(
        s.track
        for day in all_days
        for slot in timeline(data, day, ())
        for s in slot.sessions
    )


def empty_reason(
    data: ConferenceData, day: date, shown: tuple[Slot, ...]
) -> Empty | None:
    """Return why a day shows no slots: no sessions at all, or the filter (D-178)."""
    if shown:
        return None
    return "filtered" if timeline(data, day, ()) else "sprint"


def use_put_back(
    keeper: PlaceKeeper,
    shown: date | None,
    refs: dict[date, ft.Ref[ft.ListView]],
    ended: asyncio.Event,
    relay: Callable[[], None],
    *,
    time_above: bool,
    excluded: tuple[str, ...],
) -> tuple[Measured, Measured]:
    """Put the shown list back on its item after a relayout or a filter change.

    A hook: call it unconditionally, in the Schedule's render (D-70). Its effects
    follow the time going above the rows (D-216) and the filter (D-371); the handlers
    it returns follow ``layout_probe()``'s widths (D-331).

    Args:
        keeper: The Schedule's ``PlaceKeeper``.
        shown: The day shown; None before any data.
        refs: The day lists' refs (``list_ref()``).
        ended: Set when the shown list's scroll ends (``Signals.ended``).
        relay: Renders the Schedule again: a list built in full for its put-back is
            built lazy again after it.
        time_above: Whether a slot's time is above its rows (``Prefs.time_above``).
        excluded: The track keys the filter hides.

    Returns:
        The handlers of the text's width and of the screen's.
    """

    @report_errors
    async def relaid(
        *,
        text: float | None = None,
        width: float | None = None,
        above: bool | None = None,
    ) -> None:
        if not keeper.relaid(text=text, width=width, above=above):
            return
        # The text size changed: every list with a stale place is built in full, so
        # its item is built for the keyed jump (D-331), the shown one included, as
        # text that shrank can leave its item far below the built range (#600). The
        # shown list goes back now, by key, and is lazy again after; the others when
        # they show again.
        relay()
        if shown is not None and await keeper.put_back(
            shown, list_ref(refs, shown), ended
        ):
            relay()

    @report_errors
    async def text_measured(e: ft.LayoutSizeChangeEvent[ft.LayoutControl]) -> None:
        await relaid(text=e.width)

    @report_errors
    async def width_measured(e: ft.LayoutSizeChangeEvent[ft.LayoutControl]) -> None:
        await relaid(width=e.width)

    @report_errors
    async def time_moved() -> None:
        await relaid(above=time_above)

    # The time going above the rows at the largest sizes (D-216) relays them out too.
    ft.use_effect(time_moved, [time_above])

    @report_errors
    async def refiltered() -> None:
        # The filter changed: the shown list goes back to its place once Flutter has
        # laid it out, built in full until then, and is lazy again after (D-371).
        if shown is not None and await keeper.put_back_refiltered(
            shown, list_ref(refs, shown), ended
        ):
            relay()

    # A chip applies at once (D-20), so this runs under the open sheet; a newer change
    # cancels the run still waiting.
    ft.use_effect(refiltered, [excluded])
    return text_measured, width_measured
