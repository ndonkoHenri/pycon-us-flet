"""Tests for keeping the reader's place in today's Schedule list (D-250, #333).

The Schedule renders through ``tests/test_schedule.py``'s ``shown`` fixture, on Friday
at 2:10 PM, where it opens on the 2:00 PM slot. ``device`` stands in for today's list on
a device: it lays each item out at ``ROW_DP`` a row (and the 1 dp divider) or
``LINE_DP`` for the now line, answers a keyed scroll as ``Scrollable.ensureVisible``
does on that layout, and an offset or a delta as ``jumpTo``, and reports the scroll's
start, update and end before it answers, as Flutter does. The delta after a keyed jump
reports nothing: Flet drops an end within ``scroll_interval`` of the last (F70). The
tests send the height reports and the user's scrolls themselves, and can hold the reply
to a keyed scroll (``Device.hold``). How it looks on a
device, the one-frame flicker between the two jumps included, is a device check.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

import flet as ft
import pytest
from flet.messaging.session import Session

from pycon_us.core.feed import process
from pycon_us.memory import ViewMemory
from pycon_us.state import Conference
from pycon_us.ui import scrolling
from tests import sessions, test_schedule
from tests.feeds import changed, settings
from tests.sessions import find
from tests.test_schedule import FRIDAY, SATURDAY, Shown, friday_at, inside
from tests.test_schedule_filter import click, open_sheet, show_button, tap_chip

# The Schedule's fixtures, shared by name, as in tests/test_schedule_filter.py.
now = test_schedule.now
memory = test_schedule.memory
conference = test_schedule.conference
shown = test_schedule.shown

ROW_DP, LINE_DP = 100.0, 30.0
"""The heights the stand-in device lays out: a row, and the now line."""

TWO_PM = "slot-2026-05-15T14:00:00-07:00"
"""Friday's 2:00 PM slot, on at 2:10 PM: an AI talk, a talk and a charla (#333)."""

TWO_45 = "slot-2026-05-15T14:45:00-07:00"
"""Friday's 2:45 PM slot, which has no open space."""

THREE_PM = "slot-2026-05-15T15:00:00-07:00"
"""Friday's 3:00 PM slot, a sponsor presentation: the first after 2:00 PM that hiding
AI, talks and charlas leaves."""


@dataclass
class Device:
    """Today's list on the stand-in device: its offset, the scrolls it will not report,
    and an event the next keyed scroll's reply waits for, once it has moved."""

    pixels: float = 0.0
    silent: int = 0
    hold: asyncio.Event | None = None


@pytest.fixture(autouse=True)
def encoded(monkeypatch: pytest.MonkeyPatch) -> None:
    """The sheet is a dialog: its updates need encoded messages (sessions.ENCODE)."""
    monkeypatch.setattr(sessions, "ENCODE", True)


@pytest.fixture
def device(
    shown: Callable[..., Awaitable[Shown]],
    monkeypatch: pytest.MonkeyPatch,
    now: list[datetime | None],
) -> Device:
    """Friday at 2:10 PM, with today's list answered as the stand-in device does."""
    now[0] = friday_at(14, 10)
    on_device = Device()

    async def scroll_to(self: ft.ListView, **kwargs: Any) -> None:
        session = cast(Session, self.page.session)  # pyright: ignore[reportOptionalMemberAccess]
        schedule = sessions.current(Shown)
        schedule.scrolls.append((self, kwargs))
        if self is not schedule.list_of(FRIDAY):
            return
        if "scroll_key" in kwargs:
            to = _keyed_top(schedule, kwargs["scroll_key"].value)
        elif "offset" in kwargs:
            to = kwargs["offset"]
        else:  # a delta right after the keyed jump: Flet drops its events (F70)
            on_device.pixels += kwargs["delta"]
            return
        if to == on_device.pixels:  # ensureVisible and jumpTo send nothing then
            pass
        elif on_device.silent:
            on_device.pixels = to
            on_device.silent -= 1
        else:
            on_device.pixels = to
            for kind in ("start", "update", "end"):
                await session.dispatch_event(self._i, "scroll", _event(kind, to))
        if "scroll_key" in kwargs and on_device.hold is not None:
            hold, on_device.hold = on_device.hold, None
            await hold.wait()

    monkeypatch.setattr(ft.ListView, "scroll_to", scroll_to)
    return on_device


def _event(kind: str, pixels: float, **more: object) -> dict[str, object]:
    return {
        "event_type": kind,
        "pixels": pixels,
        "min_scroll_extent": 0.0,
        "max_scroll_extent": 20_000.0,
        "viewport_dimension": 700.0,
        **more,
    }


def _items(schedule: Shown) -> list[tuple[str, ft.Column, float]]:
    """Today's items in order: each key, the control that reports, and its height."""
    reporting = find(
        schedule.session, ft.Column, lambda c: c.on_size_change is not None
    )
    rows = schedule.nodes("schedule.session.") + schedule.nodes("schedule.notice.")
    found = []
    for item in schedule.list_of(FRIDAY).controls:
        (column,) = [c for c in reporting if c is item or inside(c, item)]
        (anchor,) = find(
            schedule.session,
            ft.Container,
            lambda c, column=column: (
                isinstance(c.key, ft.ScrollKey) and inside(c, column)
            ),
        )
        key = str(cast(ft.ScrollKey, anchor.key).value)
        divider = column.controls[0]
        lead = 1.0 if isinstance(divider, ft.Divider) and divider.visible else 0.0
        count = len([row for row in rows if inside(row, column)])
        found.append((key, column, lead + ROW_DP * count if count else LINE_DP))
    return found


def _top(schedule: Shown, key: str) -> float:
    """Where an item starts on the stand-in device, divider included."""
    top = 0.0
    for each, _, height in _items(schedule):
        if each == key:
            return top
        top += height
    raise AssertionError(key)


def _keyed_top(schedule: Shown, key: str) -> float:
    """Where a keyed jump puts the list: the item's anchor, under its divider."""
    (column,) = [c for k, c, _ in _items(schedule) if k == key]
    divider = column.controls[0]
    lead = 1.0 if isinstance(divider, ft.Divider) and divider.visible else 0.0
    return _top(schedule, key) + lead


async def lay_out(schedule: Shown, *, first: int | None = None) -> None:
    """Report today's items' heights, as Flutter does after a frame; ``first`` of them."""
    for _, column, height in _items(schedule)[:first]:
        await schedule.event(column, "size_change", {"w": 400.0, "h": height})


async def user_scroll(schedule: Shown, device: Device, pixels: float) -> None:
    """The user's drag to ``pixels``, as Flutter reports it."""
    friday = schedule.list_of(FRIDAY)
    await schedule.event(friday, "scroll", _event("start", device.pixels))
    user = _event("user", device.pixels, direction="forward")
    await schedule.event(friday, "scroll", user)
    device.pixels = pixels
    await schedule.event(friday, "scroll", _event("update", pixels))
    await schedule.event(friday, "scroll", _event("end", pixels))
    await schedule.event(friday, "scroll", _event("user", pixels, direction="idle"))


async def show_all(schedule: Shown) -> None:
    """Tap the summary's "Show all"."""
    (node,) = find(
        schedule.session, ft.Semantics, lambda c: c.identifier == "schedule.show_all"
    )
    assert node.content is not None
    await click(schedule, node.content)


async def hide(schedule: Shown, *chips: str, reports: bool = True) -> None:
    """Hide tracks through the sheet, then close it with "Show N sessions".

    With ``reports``, today's list reports its new heights under the open sheet, as
    a device does when today shows.
    """
    await open_sheet(schedule)
    for key in chips:
        await tap_chip(schedule, key)
    if reports:
        await lay_out(schedule)
    await click(schedule, show_button(schedule))


async def into_two_pm(
    shown: Callable[..., Awaitable[Shown]], device: Device, into: float
) -> Shown:
    """Open the Schedule laid out, scrolled by hand ``into`` dp into 2:00 PM."""
    schedule = await shown()
    await lay_out(schedule)
    await user_scroll(schedule, device, _top(schedule, TWO_PM) + into)
    schedule.forget()
    return schedule


def _asks(schedule: Shown) -> list[tuple[str, object]]:
    """What today's list was asked, in order: ("key", k), ("delta", d), ("offset", o)."""
    friday = schedule.list_of(FRIDAY)
    asked: list[tuple[str, object]] = []
    for target, kwargs in schedule.scrolls:
        if target is friday:
            if kwargs.get("scroll_key") is not None:
                asked.append(("key", kwargs["scroll_key"].value))
            elif "delta" in kwargs:
                asked.append(("delta", kwargs["delta"]))
            else:
                asked.append(("offset", kwargs["offset"]))
    return asked


# ------------------------------------------------------------------ the filter sheet


async def test_hiding_ai_after_the_first_jump_keeps_2_pm_at_the_top(
    shown: Callable[..., Awaitable[Shown]], device: Device
) -> None:
    """#333's steps: the list opens on 2:00 PM; AI off keeps it there, not 2:45 PM."""
    schedule = await shown()
    await lay_out(schedule)
    assert schedule.jumped() == [TWO_PM]
    schedule.forget()
    await hide(schedule, "ai")
    assert _asks(schedule) == [("key", TWO_PM)]  # its rows changed: at its time
    assert device.pixels == _keyed_top(schedule, TWO_PM)
    assert schedule.jumps == []  # a put-back, never a jump to now (D-204)


async def test_closing_the_sheet_keeps_an_unchanged_slot_as_far_in(
    shown: Callable[..., Awaitable[Shown]], device: Device, memory: ViewMemory
) -> None:
    """Summit is only above 2:00 PM. Every height is in by then, so it is one offset
    jump, not a keyed jump and a delta, which can show the slot's time for a frame."""
    schedule = await into_two_pm(shown, device, 150.0)
    await hide(schedule, "summit")
    assert _asks(schedule) == [("offset", _top(schedule, TWO_PM) + 150.0)]
    assert memory.schedule_offsets[FRIDAY] == device.pixels


async def test_a_hidden_slot_gives_way_to_the_next_shown_one(
    shown: Callable[..., Awaitable[Shown]], device: Device
) -> None:
    schedule = await into_two_pm(shown, device, 150.0)
    await hide(schedule, "ai", "talk", "charla")
    assert _asks(schedule) == [("key", THREE_PM)]


async def test_a_change_that_only_removes_slots_is_put_back_without_a_report(
    shown: Callable[..., Awaitable[Shown]], device: Device
) -> None:
    """The 9:45 AM keynote goes whole: nothing reports, the sheet's close is enough."""
    schedule = await into_two_pm(shown, device, 150.0)
    await hide(schedule, "keynote", reports=False)
    assert _asks(schedule) == [("offset", _top(schedule, TWO_PM) + 150.0)]


async def test_a_close_before_the_reports_is_put_back_again_at_them(
    shown: Callable[..., Awaitable[Shown]], device: Device, memory: ViewMemory
) -> None:
    """ "Show N sessions" tapped before the device reported Summit's change: the offset
    jump read the old heights. Flet sends a size after the frame that laid it out, so
    the reports that follow put the place back again, by key (D-250)."""
    schedule = await into_two_pm(shown, device, 150.0)
    await hide(schedule, "summit", reports=False)
    assert _asks(schedule) == [("offset", _top(schedule, TWO_PM) + 250.0)]  # stale
    await lay_out(schedule)
    assert _asks(schedule)[1:] == [("key", TWO_PM), ("delta", 150.0)]  # once
    assert device.pixels == _keyed_top(schedule, TWO_PM) + 150.0
    assert memory.schedule_offsets[FRIDAY] == device.pixels


async def test_a_scroll_after_the_close_stops_its_repeat(
    shown: Callable[..., Awaitable[Shown]], device: Device
) -> None:
    schedule = await into_two_pm(shown, device, 150.0)
    await hide(schedule, "summit", reports=False)
    await user_scroll(schedule, device, 0.0)
    await lay_out(schedule)
    assert len(_asks(schedule)) == 1


async def test_a_closes_put_back_whose_end_was_dropped_keeps_its_offset(
    shown: Callable[..., Awaitable[Shown]], device: Device, memory: ViewMemory
) -> None:
    """Flet drops the jump's end (``scroll_interval``, F70): the offset a day switch
    puts back is still where the list is, not where the user's scroll ended."""
    schedule = await into_two_pm(shown, device, 150.0)
    device.silent = 1
    await hide(schedule, "summit")
    assert _asks(schedule) == [("offset", _top(schedule, TWO_PM) + 150.0)]
    assert memory.schedule_offsets[FRIDAY] == device.pixels


async def test_the_dismissal_after_the_button_puts_back_nothing_more(
    shown: Callable[..., Awaitable[Shown]], device: Device
) -> None:
    schedule = await into_two_pm(shown, device, 150.0)
    sheet = await open_sheet(schedule)
    await tap_chip(schedule, "summit")
    await lay_out(schedule)
    await click(schedule, show_button(schedule))
    await schedule.session.dispatch_event(sheet._i, "dismiss", None)
    await schedule.settle()
    assert _asks(schedule) == [("offset", _top(schedule, TWO_PM) + 150.0)]


@pytest.mark.parametrize("late", [False, True])
async def test_a_refresh_long_after_the_close_puts_nothing_back(
    shown: Callable[..., Awaitable[Shown]],
    device: Device,
    conference: Conference,
    late: bool,
) -> None:
    """The repeat is the close's own layout's: its first report takes it (``late``),
    and when the close was right no report comes, so a refresh's re-render and its
    reports minutes later must not run it (the Android check of d0119ec, row 9)."""
    schedule = await into_two_pm(shown, device, 150.0)
    await hide(schedule, "summit", reports=not late)
    if late:
        await lay_out(schedule)  # the close's layout, reported after it: once by key
    assert len(_asks(schedule)) == (3 if late else 1)
    schedule.forget()
    conference.data = process(changed(2026, _rename_a_friday_talk), settings(2026))
    conference.version += 1
    await schedule.settle()
    await lay_out(schedule)  # the refresh's reports
    assert schedule.scrolls == []


def _rename_a_friday_talk(document: dict[str, Any]) -> None:
    """Rename a talk in Friday's 3:30 PM slot, below the place: a feed that changed."""
    slot = next(s for s in document["schedule"] if s.get("conf_key") == 63)
    slot["name"] = "Renamed on the server"


# ------------------------------------------------------------------ "Show all" and the reports


async def test_show_all_puts_the_place_back_at_the_next_report(
    shown: Callable[..., Awaitable[Shown]], device: Device, memory: ViewMemory
) -> None:
    """Not before: until the device has laid the change out, a keyed jump is stale.
    The put-back's own end, read on the heights Python has then, is not the place."""
    schedule = await into_two_pm(shown, device, 150.0)
    await show_all(schedule)  # open spaces add rows above and in 2:00 PM
    assert _asks(schedule) == []
    await lay_out(schedule, first=1)  # one report; the rest still on their way
    assert _asks(schedule) == [("key", TWO_PM)]
    assert device.pixels == _keyed_top(schedule, TWO_PM)
    assert memory.schedule_place is not None
    assert memory.schedule_place.key == TWO_PM
    await lay_out(schedule)
    assert _asks(schedule) == [("key", TWO_PM)]  # once


async def test_show_all_keeps_an_unchanged_slot_as_far_in(
    shown: Callable[..., Awaitable[Shown]], device: Device, memory: ViewMemory
) -> None:
    """2:45 PM has no open space, the slots above gain some. The first report is no
    proof the others are in, so a keyed jump, which Flutter works out, then the
    distance into the slot. Flet drops the delta's end: the offset a day switch
    puts back is still where the list is."""
    schedule = await shown()
    await lay_out(schedule)
    await user_scroll(schedule, device, _top(schedule, TWO_45) + 150.0)
    schedule.forget()
    await show_all(schedule)
    await lay_out(schedule, first=1)
    assert _asks(schedule) == [("key", TWO_45), ("delta", 150.0)]
    assert device.pixels == _keyed_top(schedule, TWO_45) + 150.0
    assert memory.schedule_offsets[FRIDAY] == device.pixels


async def test_a_put_back_whose_ends_were_dropped_comes_back_by_key(
    shown: Callable[..., Awaitable[Shown]], device: Device, memory: ViewMemory
) -> None:
    """Flet drops the keyed jump's end too: where it went is Flutter's, so today's
    offset, laid out for the old filter, is dropped and today comes back by key."""
    schedule = await shown()
    await lay_out(schedule)
    await user_scroll(schedule, device, _top(schedule, TWO_45) + 150.0)
    await show_all(schedule)
    device.silent = 1
    await lay_out(schedule, first=1)
    assert FRIDAY not in memory.schedule_offsets
    pixels = device.pixels
    await schedule.change_day(SATURDAY)
    schedule.forget()
    device.pixels = 0.0  # a page that shows again is a new list, at its top
    await schedule.change_day(FRIDAY)
    assert _asks(schedule) == [("key", TWO_45), ("delta", 150.0)]
    assert device.pixels == pixels


async def test_a_put_back_whose_ends_were_dropped_comes_back_by_key_on_a_new_mount(
    shown: Callable[..., Awaitable[Shown]], device: Device
) -> None:
    schedule = await shown()
    await lay_out(schedule)
    await user_scroll(schedule, device, _top(schedule, TWO_45) + 150.0)
    await show_all(schedule)
    device.silent = 1
    await lay_out(schedule, first=1)
    pixels = device.pixels
    schedule.leave()
    await schedule.settle()
    schedule.forget()
    device.pixels = 0.0  # a new list, at its top
    schedule.come_back()
    await schedule.until(lambda: schedule.find(ft.Tabs) and _asks(schedule))
    assert _asks(schedule) == [("key", TWO_45), ("delta", 150.0)]
    assert device.pixels == pixels


async def _held_show_all(
    shown: Callable[..., Awaitable[Shown]], device: Device
) -> tuple[Shown, asyncio.Event, asyncio.Task[None]]:
    """ "Show all" scrolled 150 dp into 2:45 PM, its keyed jump's reply held."""
    schedule = await shown()
    await lay_out(schedule)
    await user_scroll(schedule, device, _top(schedule, TWO_45) + 150.0)
    schedule.forget()
    await show_all(schedule)
    device.hold = hold = asyncio.Event()
    reports = asyncio.create_task(lay_out(schedule, first=1))
    await schedule.until(lambda: device.hold is None)
    assert _asks(schedule) == [("key", TWO_45)]
    return schedule, hold, reports


async def test_now_stops_a_put_back_on_its_way(
    shown: Callable[..., Awaitable[Shown]],
    device: Device,
    memory: ViewMemory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Now, tapped between the keyed jump and its reply: no delta after Now's jump."""
    schedule, hold, reports = await _held_show_all(shown, device)
    monkeypatch.setattr(scrolling, "LANDING_S", 0.0)
    await schedule.press_now()
    await schedule.until(lambda: schedule.jumps)
    hold.set()
    await reports
    assert _asks(schedule) == [("key", TWO_45), ("key", TWO_PM)]
    assert memory.schedule_offsets[FRIDAY] == device.pixels


async def test_a_drag_stops_a_put_back_on_its_way(
    shown: Callable[..., Awaitable[Shown]], device: Device
) -> None:
    schedule, hold, reports = await _held_show_all(shown, device)
    friday = schedule.list_of(FRIDAY)
    await schedule.event(friday, "scroll", _event("start", device.pixels))
    user = _event("user", device.pixels, direction="forward")
    await schedule.event(friday, "scroll", user)
    hold.set()
    await reports
    assert _asks(schedule) == [("key", TWO_45)]


async def test_show_all_while_the_list_moves_puts_nothing_back(
    shown: Callable[..., Awaitable[Shown]], device: Device
) -> None:
    schedule = await into_two_pm(shown, device, 150.0)
    friday = schedule.list_of(FRIDAY)
    await schedule.event(friday, "scroll", _event("start", device.pixels))
    await show_all(schedule)
    await lay_out(schedule)
    assert _asks(schedule) == []


async def test_a_scroll_start_cancels_a_pending_put_back(
    shown: Callable[..., Awaitable[Shown]], device: Device
) -> None:
    schedule = await into_two_pm(shown, device, 150.0)
    await show_all(schedule)
    friday = schedule.list_of(FRIDAY)
    await schedule.event(friday, "scroll", _event("start", device.pixels))
    await lay_out(schedule)
    assert _asks(schedule) == []


async def test_now_cancels_a_pending_put_back(
    shown: Callable[..., Awaitable[Shown]],
    device: Device,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even when Flet drops the jump's own scroll events."""
    schedule = await into_two_pm(shown, device, 150.0)
    await show_all(schedule)
    monkeypatch.setattr(scrolling, "LANDING_S", 0.0)
    device.silent = scrolling.JUMP_TRIES
    await schedule.press_now()
    await schedule.until(lambda: schedule.jumps)
    jumped = len(_asks(schedule))
    await lay_out(schedule)
    assert len(_asks(schedule)) == jumped


async def test_a_jump_to_now_leaves_its_target_as_the_place(
    shown: Callable[..., Awaitable[Shown]], device: Device, memory: ViewMemory
) -> None:
    """Its end is not read as the place: only the user's scroll's end is."""
    schedule = await shown()
    await lay_out(schedule)
    await user_scroll(schedule, device, 0.0)  # far from now: the button shows
    await schedule.press_now()
    await schedule.until(lambda: schedule.jumps)
    place = memory.schedule_place
    assert place is not None
    assert (place.key, place.into) == (TWO_PM, 0.0)


# ------------------------------------------------------------------ another day


async def test_a_change_made_on_another_day_is_put_back_when_today_shows(
    shown: Callable[..., Awaitable[Shown]], device: Device, memory: ViewMemory
) -> None:
    """By key, once the switch has settled, since its heights may not all be in;
    today's old offset, laid out for the old filter, is not put back."""
    schedule = await into_two_pm(shown, device, 150.0)
    await schedule.change_day(SATURDAY)
    await hide(schedule, "summit", reports=False)  # today is not on the device
    assert _asks(schedule) == []
    assert FRIDAY not in memory.schedule_offsets
    device.pixels = 0.0  # a page that shows again is a new list, at its top
    await lay_out(schedule, first=1)  # it mounts as it slides in: too early to jump
    assert _asks(schedule) == []
    await schedule.change_day(FRIDAY)  # the other reports may still be on their way
    assert _asks(schedule) == [("key", TWO_PM), ("delta", 150.0)]
    assert device.pixels == _keyed_top(schedule, TWO_PM) + 150.0


async def test_without_a_change_today_comes_back_at_its_offset(
    shown: Callable[..., Awaitable[Shown]], device: Device, memory: ViewMemory
) -> None:
    schedule = await into_two_pm(shown, device, 150.0)
    offset = memory.schedule_offsets[FRIDAY]
    await schedule.change_day(SATURDAY)
    await schedule.change_day(FRIDAY)
    assert _asks(schedule) == [("offset", offset)]
