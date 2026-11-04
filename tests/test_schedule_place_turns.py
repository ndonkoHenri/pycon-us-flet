"""Tests for the Schedule's put-backs taking turns across layout changes (D-364, #600).

At the largest text sizes a text-size change is two layout changes a few ms apart: one
put-back moves a list at a time, a newer change or a jump to now supersedes the one on
its way, each jump waits for its own scroll end, and the shown list is built in full
before its keyed jump. The harness and the helpers are `tests/test_schedule_place.py`'s,
as are the place's own tests (D-331).
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import date
from time import monotonic
from types import SimpleNamespace
from typing import cast

import flet as ft
import pytest

from pycon_us.memory import ViewMemory
from pycon_us.screens.schedule_head import HEAD_KEY
from pycon_us.screens.schedule_place import END_GAP_S, PlaceKeeper
from pycon_us.ui import scrolling
from tests import schedule_view
from tests.schedule_view import FRIDAY, SATURDAY, Shown
from tests.test_schedule_place import (
    HEIGHT,
    _at_saturday_s_fourth_slot,
    _measure,
    _probe,
    _report,
)

# The Schedule's fixtures, shared by name: pytest finds fixtures among a module's names.
now = schedule_view.now
memory = schedule_view.memory
conference = schedule_view.conference
shown = schedule_view.shown


async def test_a_newer_layout_change_waits_for_the_put_back_on_its_way(
    shown: Callable[[], Awaitable[Shown]], memory: ViewMemory
) -> None:
    """#600: at the largest sizes a text-size change is two layout changes in a row.

    The second comes while the first put-back's keyed jump moves (Flet runs each event
    as its own task). It asks nothing until that jump's end has come, as every jump
    waits on the one scroll-end signal: the first put-back then stops without scrolling
    into the slot, and the second jumps from its own end, with the heights reported in
    the final layout.
    """
    schedule = await shown()
    key = await _at_saturday_s_fourth_slot(schedule)
    schedule.hold = asyncio.Event()
    time, _ = _probe(schedule)
    first = asyncio.ensure_future(
        schedule.session.dispatch_event(time._i, "size_change", {"w": 52.0, "h": 26.0})
    )
    await schedule.until(lambda: schedule.scrolls)
    second = asyncio.ensure_future(_measure(schedule, 60.0))
    await schedule.until(lambda: (memory.schedule_basis or (0.0,))[0] == 60.0)
    assert len(schedule.scrolls) == 1  # the second waits for the first jump's end
    await _report(schedule, SATURDAY, HEIGHT * 1.3)
    schedule.hold.set()
    await first
    await second
    await schedule.until(lambda: not memory.schedule_places[SATURDAY].stale)
    asks = [kwargs for _, kwargs in schedule.scrolls]
    assert schedule.keyed() == [key, key]
    assert asks[2:] == [{"offset": 4000.0 - 1 + 65.0, "duration": 0}]  # the second's
    place = memory.schedule_places[SATURDAY]
    assert (place.key, place.into, place.pixels) == (key, 65.0, 4064.0)


async def test_a_slot_that_has_not_reported_its_new_height_shows_from_its_top(
    shown: Callable[[], Awaitable[Shown]], memory: ViewMemory
) -> None:
    """#600: the old height would scale the distance past the slot, so it is not used.

    The keyed jump has landed before the slot reported its height at the new size: the
    list stays at the slot's top (its anchor under the divider), not a guess inside it.
    """
    schedule = await shown()
    key = await _at_saturday_s_fourth_slot(schedule)
    await _measure(schedule, 52.0)
    await schedule.until(lambda: not memory.schedule_places[SATURDAY].stale)
    assert schedule.keyed() == [key]
    assert [kw for _, kw in schedule.scrolls if "offset" in kw] == [
        {"offset": 4000.0 - 1, "duration": 0}
    ]
    assert memory.schedule_places[SATURDAY].into == 0.0


async def test_the_time_moving_above_the_rows_puts_the_slot_s_top_back(
    shown: Callable[[], Awaitable[Shown]], memory: ViewMemory
) -> None:
    """#600: a distance into a slot beside its time says nothing of rows under it.

    The time goes above the rows at the largest sizes (D-216), so the slot is put back
    at its top, even with its height reported in the new layout; the place it leaves
    records that layout, so the next put-back in it scales the distance again.
    """
    schedule = await shown()
    key = await _at_saturday_s_fourth_slot(schedule)
    assert not memory.schedule_places[SATURDAY].above
    schedule.hold = asyncio.Event()
    schedule.prefs.time_above = True  # what GutterProbe measures at that size
    await schedule.until(lambda: schedule.scrolls)
    await _report(schedule, SATURDAY, HEIGHT * 1.3)
    schedule.hold.set()
    await schedule.until(lambda: not memory.schedule_places[SATURDAY].stale)
    assert schedule.keyed() == [key]
    place = memory.schedule_places[SATURDAY]
    assert (place.key, place.into, place.pixels, place.above) == (
        key,
        0.0,
        4000.0 - 1,
        True,
    )


async def test_a_jump_to_now_during_the_old_top_jump_stops_the_put_back(
    shown: Callable[..., Awaitable[Shown]],
    memory: ViewMemory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Codex's #572 review: superseded while the jump to the slot's old top waits.

    Today's slot left the built range, so the put-back jumps to its old top; "Now" is
    tapped while that jump waits on the device. Once it returns, the put-back asks for
    no keyed jump to its slot: only the jump to now moves the list, and no place from
    before it comes back.
    """
    monkeypatch.setattr(scrolling, "LANDING_S", 0.01)  # no end ever comes here
    schedule = await shown(moves=False)  # Friday, today
    await _measure(schedule, 40.0)
    await _report(schedule, FRIDAY, HEIGHT)
    await schedule.drag()
    await schedule.scroll_end(FRIDAY, 3 * HEIGHT + 50)
    key = memory.schedule_places[FRIDAY].key
    schedule.forget()
    keyed = schedule.hold = asyncio.Event()
    time, _ = _probe(schedule)
    put_back = asyncio.ensure_future(
        schedule.session.dispatch_event(time._i, "size_change", {"w": 30.0, "h": 18.0})
    )
    await schedule.until(lambda: schedule.scrolls)  # the first keyed jump, held
    old_top = schedule.hold = asyncio.Event()
    keyed.set()
    await schedule.until(lambda: any("offset" in kw for _, kw in schedule.scrolls))
    asked = len(schedule.scrolls)  # the jump to the old top waits on the device
    schedule.hold = None
    await schedule.press_now()
    await schedule.until(lambda: schedule.jumps)
    (now_key,) = schedule.jumped()
    assert now_key != key
    old_top.set()
    await put_back
    await schedule.settle()
    later = [kwargs for _, kwargs in schedule.scrolls[asked:]]
    assert later  # the jump to now's asks
    assert {kwargs["scroll_key"].value for kwargs in later} == {now_key}
    assert FRIDAY not in memory.schedule_places


class _StandIn:
    """A stand-in day list: records each jump; a keyed one lands at 4,000 dp."""

    def __init__(self, memory: ViewMemory, ended: asyncio.Event) -> None:
        """Start with no jump asked."""
        self.memory, self.ended = memory, ended
        self.asks: list[dict[str, object]] = []

    async def scroll_to(self, **kwargs: object) -> None:
        """Record the jump; a keyed one ends at 4,000 dp, as the screen records it."""
        self.asks.append(kwargs)
        if "scroll_key" in kwargs:
            self.memory.schedule_offsets[SATURDAY] = 4000.0
            self.ended.set()


async def _superseded_in_wait(
    memory: ViewMemory, monkeypatch: pytest.MonkeyPatch, held: int
) -> tuple[bool, list[dict[str, object]]]:
    """Put Saturday's place back, with a jump to now during its `held`-th end-gap wait.

    Returns:
        What the put-back returned, and every jump it asked after the jump to now.
    """
    monkeypatch.setattr(scrolling, "LANDING_S", 0.01)
    keeper = PlaceKeeper(memory)
    keeper.lay_out(1, (), {SATURDAY: (HEAD_KEY, "a", "b")}, {})
    for key, height in ((HEAD_KEY, 0.0), ("a", HEIGHT), ("b", HEIGHT)):
        keeper.measured(SATURDAY, key, height)
    keeper.relaid(text=40.0, width=400.0, above=False)
    end = SimpleNamespace(event_type=ft.ScrollType.END, pixels=HEIGHT + 50)
    keeper.scrolled(SATURDAY, cast(ft.OnScrollEvent, end))
    assert keeper.relaid(text=52.0)
    keeper.measured(SATURDAY, "b", HEIGHT * 1.3)
    gate, waiting, waits = asyncio.Event(), asyncio.Event(), [0]

    async def ended_apart(day: date) -> None:
        """Hold the `held`-th wait until the gate opens; pass the others."""
        waits[0] += 1
        if waits[0] == held:
            waiting.set()
            await gate.wait()

    monkeypatch.setattr(keeper, "ended_apart", ended_apart)
    ended = asyncio.Event()
    stand_in = _StandIn(memory, ended)
    list_ref = ft.Ref[ft.ListView]()
    list_ref.current = cast(ft.ListView, stand_in)
    put_back = asyncio.ensure_future(keeper.put_back(SATURDAY, list_ref, ended))
    await waiting.wait()
    asked = len(stand_in.asks)
    keeper.supersede(SATURDAY)  # the jump to now
    gate.set()
    done = await put_back
    return done, stand_in.asks[asked:]


async def test_a_jump_to_now_before_the_keyed_jump_stops_the_put_back(
    memory: ViewMemory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Codex's #620 review: superseded while the keyed jump waits for the end gap.

    Once the wait is over, the put-back asks for no jump and records no place.
    """
    done, later = await _superseded_in_wait(memory, monkeypatch, held=1)
    assert (done, later) == (False, [])
    assert SATURDAY not in memory.schedule_places


async def test_a_jump_to_now_before_the_jump_into_the_slot_stops_the_put_back(
    memory: ViewMemory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Codex's #620 review: superseded while the jump into the slot waits for the gap.

    The keyed jump has landed; once the wait is over, the put-back asks for no jump
    into the slot and records no place, so nothing moves the list after "Now".
    """
    done, later = await _superseded_in_wait(memory, monkeypatch, held=2)
    assert (done, later) == (False, [])
    assert SATURDAY not in memory.schedule_places


def test_an_empty_head_s_height_outlives_a_text_size_change(memory: ViewMemory) -> None:
    """An empty head (0 dp) still counts after a resize, so the next place is recorded.

    Flutter reports only a size that changed, so the empty head never reports again:
    the keeper keeps its 0, a scroll end below it records the slot, and the next
    text-size change marks that place to be put back. A quiet refresh with another feed
    version keeps the 0 too: the slots report again, the head does not, and the place
    is still recorded and put back after the next resize.
    """
    keeper = PlaceKeeper(memory)
    keeper.lay_out(1, (), {SATURDAY: (HEAD_KEY, "a", "b")}, {})
    for key, height in ((HEAD_KEY, 0.0), ("a", HEIGHT), ("b", HEIGHT)):
        keeper.measured(SATURDAY, key, height)
    keeper.relaid(text=40.0, width=400.0, above=True)
    assert not keeper.relaid(text=52.0)  # no place yet; only "a" and "b" report again
    keeper.measured(SATURDAY, "a", HEIGHT * 1.3)
    keeper.measured(SATURDAY, "b", HEIGHT * 1.3)
    end = SimpleNamespace(event_type=ft.ScrollType.END, pixels=HEIGHT * 1.3 + 50)
    keeper.scrolled(SATURDAY, cast(ft.OnScrollEvent, end))
    place = memory.schedule_places[SATURDAY]
    assert (place.key, place.into) == ("b", 50.0)
    assert keeper.relaid(text=60.0)
    assert keeper.pending(SATURDAY) == replace(place, stale=True)
    keeper.lay_out(2, (), {SATURDAY: (HEAD_KEY, "a", "b")}, {})
    keeper.measured(SATURDAY, "a", HEIGHT * 1.4)
    keeper.measured(SATURDAY, "b", HEIGHT * 1.4)
    end = SimpleNamespace(event_type=ft.ScrollType.END, pixels=HEIGHT * 1.4 + 30)
    keeper.scrolled(SATURDAY, cast(ft.OnScrollEvent, end))
    place = memory.schedule_places[SATURDAY]
    assert (place.key, place.into, place.layout) == ("b", 30.0, (2, ()))
    assert keeper.relaid(text=40.0)
    assert keeper.pending(SATURDAY) == replace(place, stale=True)


async def test_the_shown_list_is_built_in_full_before_its_keyed_jump(
    shown: Callable[[], Awaitable[Shown]], memory: ViewMemory
) -> None:
    """#600: text that shrank can leave the slot far from a lazy list's built range.

    Saturday is not today, so its list is lazy: a text-size change builds it in full
    before the put-back asks for the keyed jump, and lazy again once it is back.
    """
    schedule = await shown()
    await _at_saturday_s_fourth_slot(schedule)
    assert schedule.list_of(SATURDAY).cache_extent is None
    schedule.hold = asyncio.Event()
    time, _ = _probe(schedule)
    put_back = asyncio.ensure_future(
        schedule.session.dispatch_event(time._i, "size_change", {"w": 30.0, "h": 18.0})
    )
    await schedule.until(lambda: schedule.scrolls)
    assert schedule.list_of(SATURDAY).cache_extent == scrolling.FULL_LIST_EXTENT
    schedule.hold.set()
    await put_back
    await schedule.until(lambda: not memory.schedule_places[SATURDAY].stale)
    await schedule.until(lambda: schedule.list_of(SATURDAY).cache_extent is None)


async def test_a_put_back_s_jump_waits_until_flet_would_send_its_end(
    memory: ViewMemory,
) -> None:
    """F182: Flet drops a list's scroll end that comes within its interval of the last.

    So a put-back's next jump on that list waits `END_GAP_S` after the last end the
    list sent, longer than the list's `scroll_interval`; a list with no end yet
    waits for nothing.
    """
    assert END_GAP_S > scrolling.SCROLL_EVENT_MS / 1000
    keeper = PlaceKeeper(memory)
    end = SimpleNamespace(event_type=ft.ScrollType.END, pixels=0.0)
    keeper.scrolled(SATURDAY, cast(ft.OnScrollEvent, end))
    start = monotonic()
    await keeper.ended_apart(FRIDAY)
    assert monotonic() - start < END_GAP_S / 2
    await keeper.ended_apart(SATURDAY)
    assert monotonic() - keeper.last_end[SATURDAY] >= END_GAP_S * 0.95
