"""Tests for the Schedule's positions and Jump to now (D-18, D-155, #89).

The screen renders in ``tests/schedule_view.py``'s harness: ``ListView.scroll_to`` is
recorded and answered with the scroll end Flutter would report, and each jump is
recorded (``Shown.jumps``), so a test checks which jumps ran and where they went (#237).
Whether a jump lands is a device check (#89). When a jump runs is in
``test_schedule_button.py``.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, cast

import flet as ft
import pytest

from pycon_us.core.timeline import now_place, timeline
from pycon_us.memory import ViewMemory
from pycon_us.screens import schedule as screen
from pycon_us.services.storage import THEME, Storage
from pycon_us.ui import scrolling
from tests import schedule_view
from tests.feeds import processed
from tests.schedule_view import (
    BEFORE,
    DAYS,
    DURING,
    FRIDAY,
    MONDAY,
    PACIFIC,
    SATURDAY,
    TEN_30,
    Shown,
    _assert_asks,
    inside,
)
from tests.sessions import find, settle
from tests.trees import texts

now = schedule_view.now
memory = schedule_view.memory
conference = schedule_view.conference
shown = schedule_view.shown


# ------------------------------------------------------------------ positions (D-18)


async def test_a_scroll_end_is_remembered_and_put_back_when_the_day_shows_again(
    shown: Callable[[], Awaitable[Shown]], memory: ViewMemory
) -> None:
    """A day's scroll end is remembered and put back at once when the day returns."""
    schedule = await shown()
    await schedule.scroll_end(FRIDAY, 1234.0)
    assert memory.schedule_offsets[FRIDAY] == 1234.0
    await schedule.change_day(SATURDAY)
    schedule.scrolls.clear()
    await schedule.change_day(FRIDAY)
    ((target, kwargs),) = schedule.scrolls
    assert target is schedule.list_of(FRIDAY)
    assert kwargs == {"offset": 1234.0, "duration": 0}


async def test_a_return_to_the_tab_restores_the_day_and_its_offset(
    shown: Callable[[], Awaitable[Shown]], memory: ViewMemory
) -> None:
    """A tab switch unmounts the root (D-142); ViewMemory outlives it (D-143)."""
    memory.jumped_on = FRIDAY  # the jump already ran today in this process
    memory.schedule_day, memory.schedule_offsets[SATURDAY] = SATURDAY, 900.0
    schedule = await shown()
    ((target, kwargs),) = schedule.scrolls
    assert target is schedule.list_of(SATURDAY)
    assert kwargs == {"offset": 900.0, "duration": 0}


# ------------------------------------------------------------------ Jump to now (D-155)


async def test_the_first_display_of_today_jumps_to_the_current_slot_once(
    shown: Callable[[], Awaitable[Shown]], memory: ViewMemory
) -> None:
    """Today's first display jumps once to the current slot; a later one never does.

    One jump, through D-156's second render. A late scroll end makes the jump ask again
    (D-155): a loaded host may see two asks, both to the same place (#237).
    """
    schedule = await shown()
    place = now_place(timeline(processed(2026), FRIDAY, ("Open Space",)), DURING)
    assert place.target == TEN_30
    assert schedule.jumps == [(place.target, "landed")]
    _assert_asks(schedule, FRIDAY, place.target, scrolling.JUMP_MS)
    assert memory.jumped_on == FRIDAY

    again = await shown()  # a tab return or a new session: never a second jump
    assert again.keyed() == [] and again.jumps == []


async def test_under_reduced_motion_the_jump_is_instant(
    shown: Callable[..., Awaitable[Shown]],
) -> None:
    """Under reduced motion, the first display's jump goes to now with instant asks."""
    schedule = await shown(reduce_motion=True)
    assert schedule.jumped() == [TEN_30]
    _assert_asks(schedule, FRIDAY, TEN_30, 0)  # D-34: each ask instant


async def test_a_late_scroll_end_makes_the_jump_ask_again_and_it_is_still_one_jump(
    shown: Callable[..., Awaitable[Shown]], memory: ViewMemory
) -> None:
    """A late scroll end makes two asks to one place, yet one landed jump.

    #237's "expected 1, got 2": on a loaded host the first ask's scroll end came after
    the jump's wait, so the jump asked again (D-155). Two asks to one place, one jump:
    the first display's effect runs once, and today's jump is done.
    """
    schedule = await shown(late=True, reduce_motion=True)
    assert schedule.keyed() == [TEN_30, TEN_30]
    assert schedule.jumps == [(TEN_30, "landed")]
    assert memory.jumped_on == FRIDAY
    assert schedule.fab is None  # it landed: the place is on screen


async def test_outside_the_conference_nothing_jumps_and_there_is_no_now_button(
    shown: Callable[[], Awaitable[Shown]], now: list[datetime]
) -> None:
    """Before the conference, the Schedule scrolls nowhere and has no "Now" button."""
    now[0] = BEFORE
    schedule = await shown()
    assert schedule.scrolls == []
    assert schedule.fab is None


async def test_on_a_sprint_day_there_is_no_now_button(
    shown: Callable[[], Awaitable[Shown]], now: list[datetime]
) -> None:
    """On a sprint day, today's tab is selected, with no scroll and no "Now" button."""
    now[0] = datetime(2026, 5, 18, 11, 0, tzinfo=PACIFIC)
    schedule = await shown()
    assert schedule.tabs.selected_index == DAYS.index(MONDAY)
    assert schedule.fab is None
    assert schedule.scrolls == []


async def test_now_on_today_jumps_again(
    shown: Callable[[], Awaitable[Shown]],
) -> None:
    """Scrolled away from now, "Now" shows, and a tap jumps to the current slot."""
    schedule = await shown()
    assert schedule.fab is None  # the jump put the slot on screen
    await schedule.scroll_away()
    assert schedule.fab is not None
    assert texts(cast(ft.Control, schedule.fab.content)) == ["Now"]
    schedule.forget()
    await schedule.press_now()
    assert schedule.jumps == [(TEN_30, "landed")]
    _assert_asks(schedule, FRIDAY, TEN_30, scrolling.JUMP_MS)


async def test_now_from_another_day_switches_first_then_jumps_once_it_settled(
    shown: Callable[[], Awaitable[Shown]], memory: ViewMemory
) -> None:
    """D-155's second flow: the jump waits for the tabs to report the switch."""
    memory.schedule_day, memory.jumped_on = SATURDAY, FRIDAY
    schedule = await shown()
    assert texts(
        cast(ft.Control, cast(ft.FloatingActionButton, schedule.fab).content)
    ) == ["Today"]
    schedule.forget()
    await schedule.press_now()
    assert schedule.tabs.selected_index == DAYS.index(FRIDAY)
    assert memory.schedule_day == FRIDAY
    assert schedule.scrolls == []  # not before the switch has slid in
    await schedule.change_day(FRIDAY)  # Flutter's echo of the switch
    await schedule.until(lambda: schedule.jumps)
    assert schedule.jumps == [(TEN_30, "landed")]
    _assert_asks(schedule, FRIDAY, TEN_30, scrolling.JUMP_MS)


async def test_the_re_tap_scrolls_the_shown_day_to_the_top(
    shown: Callable[[], Awaitable[Shown]],
) -> None:
    """D-166: the user's own tap, so D-18's "never move unasked" stands."""
    schedule = await shown()
    schedule.scrolls.clear()
    await cast(Callable[[], Awaitable[None]], schedule.retaps[-1])()
    ((target, kwargs),) = schedule.scrolls
    assert target is schedule.list_of(FRIDAY)
    assert kwargs == {"offset": 0, "duration": 300}


async def test_a_jump_still_waiting_stops_when_the_user_leaves_the_tab(
    shown: Callable[[], Awaitable[Shown]],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """F2, D-387: Flet cancels the effect's waiting task when the screen unmounts."""
    round_trip = asyncio.Event()
    get = Storage.get

    async def slow_get(self: Storage, pref: Any) -> Any:
        if pref is THEME:  # the first display's round trip (D-156)
            await round_trip.wait()
        return await get(self, pref)

    monkeypatch.setattr(Storage, "get", slow_get)
    schedule = await shown()
    friday = schedule.list_of(FRIDAY)  # held: the screen's weak ref may resolve it
    schedule.leave()
    await settle()
    assert find(schedule.session, ft.Tabs) == []
    with caplog.at_level(logging.ERROR):
        round_trip.set()
        await settle()  # the effect's task was cancelled: nothing is left to run
        await settle()
    assert schedule.scrolls == []
    assert friday.parent is None or not inside(friday, schedule.session.page)
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


async def test_a_now_tap_still_waiting_stops_quietly_when_the_user_leaves_the_tab(
    shown: Callable[..., Awaitable[Shown]],
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A waiting "Now" jump stops at its next ask once the user left, with no error.

    A tap's jump runs in its handler, which no unmount cancels: it stops at the first
    ask that finds the list off the page, and no error reaches the next screen.
    """
    monkeypatch.setattr(scrolling, "LANDING_S", 0.02)
    schedule = await shown(reduce_motion=True)
    await schedule.scroll_away()  # the button shows again
    schedule.moves = False  # already in place: no scroll end, so every try waits
    friday = schedule.list_of(FRIDAY)  # held: the screen's weak ref may resolve it
    schedule.scrolls.clear()
    schedule.hold = asyncio.Event()  # the first ask is held until the user has left
    with caplog.at_level(logging.INFO):
        tap = asyncio.ensure_future(schedule.press_now())
        await schedule.until(lambda: schedule.scrolls)
        schedule.leave()
        await settle()
        schedule.hold.set()
        await asyncio.wait_for(tap, 30)  # generous: a passing tap ends at once
    assert len(schedule.scrolls) == 1  # the second ask found the list gone
    assert schedule.scrolls[0][0] is friday
    assert "the list left the page" in caplog.text
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


async def test_a_now_tap_on_a_list_already_in_place_is_still_said(
    shown: Callable[..., Awaitable[Shown]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A "Now" tap on a list that never moves uses every try, then says where it is.

    No scroll, so no scroll end: today's list builds every slot (D-154), so a list that
    never moves is on the slot already, and the user still hears where.
    """
    monkeypatch.setattr(scrolling, "LANDING_S", 0.02)
    schedule = await shown(screen_reader=True, announcements=True, reduce_motion=True)
    await schedule.scroll_away()
    schedule.moves = False
    schedule.scrolls.clear()
    await schedule.press_now()
    assert len(schedule.scrolls) == scrolling.JUMP_TRIES
    assert schedule.announced == ["Friday, May 15, 10:30 AM"]


async def test_a_now_tap_tells_a_screen_reader_where_it_landed(
    shown: Callable[..., Awaitable[Shown]],
) -> None:
    """ux.md §5.2: the switch and the scroll are silent, so the landing is said once."""
    schedule = await shown(screen_reader=True, announcements=True)
    assert schedule.announced == []  # the first display's jump is not the user's
    await schedule.scroll_away()
    await schedule.press_now()
    assert schedule.announced == ["Friday, May 15, 10:30 AM"]


async def test_today_from_another_day_tells_a_screen_reader_once_it_landed(
    shown: Callable[..., Awaitable[Shown]], memory: ViewMemory
) -> None:
    """From another day, "Today" announces the landing only once the switch settled."""
    memory.schedule_day, memory.jumped_on = SATURDAY, FRIDAY
    schedule = await shown(screen_reader=True, announcements=True)
    await schedule.press_now()
    assert schedule.announced == []  # not before the switch has slid in
    await schedule.change_day(FRIDAY)
    await schedule.until(lambda: schedule.announced)
    assert schedule.announced == ["Friday, May 15, 10:30 AM"]


@pytest.mark.parametrize(
    "settings",
    [{}, {"screen_reader": True}, {"announcements": True}],
    ids=["neither", "no-announcements", "no-screen-reader"],
)
async def test_without_a_screen_reader_that_takes_announcements_nothing_is_said(
    shown: Callable[..., Awaitable[Shown]], settings: dict[str, bool]
) -> None:
    """F13: Flutter reports no announcements on Android, so none is sent there."""
    schedule = await shown(**settings)
    await schedule.scroll_away()
    schedule.scrolls.clear()
    await schedule.press_now()
    assert schedule.scrolls and schedule.announced == []


def _note(schedule: Shown) -> str:
    """The words of the landing note, the live region TalkBack hears (D-241)."""
    return schedule.node("schedule.landing").label or ""


async def test_the_landing_note_is_a_polite_live_region_with_nothing_to_stop_on(
    shown: Callable[..., Awaitable[Shown]],
) -> None:
    """The landing note is an empty live-region container with no action or focus.

    D-241: empty, the node has no label, action or state, so TalkBack's linear
    navigation passes it by; a container, so its label is its own node's.
    """
    schedule = await shown(screen_reader=True)
    note = schedule.node("schedule.landing")
    assert note.live_region and note.container
    assert not note.label  # the first display's jump is not the user's
    assert note.on_tap is None and not note.button and not note.focusable


async def test_without_announcements_a_now_tap_tells_talkback_through_the_note(
    shown: Callable[..., Awaitable[Shown]],
) -> None:
    """#223: Android takes no announcement (F13), so the note says where it landed."""
    schedule = await shown(screen_reader=True)
    await schedule.scroll_away()
    await schedule.press_now()
    assert _note(schedule) == "Friday, May 15, 10:30 AM"
    assert schedule.announced == []


async def test_today_from_another_day_fills_the_note_once_it_landed(
    shown: Callable[..., Awaitable[Shown]], memory: ViewMemory
) -> None:
    """From another day, "Today" fills the landing note only once the switch settled."""
    memory.schedule_day, memory.jumped_on = SATURDAY, FRIDAY
    schedule = await shown(screen_reader=True)
    await schedule.press_now()
    assert _note(schedule) == ""  # not before the switch has slid in
    await schedule.change_day(FRIDAY)
    await schedule.until(lambda: _note(schedule))
    assert _note(schedule) == "Friday, May 15, 10:30 AM"


async def test_a_second_tap_on_the_same_slot_empties_the_note_first(
    shown: Callable[..., Awaitable[Shown]],
) -> None:
    """A second tap empties the note while its jump runs, then says the same slot.

    Flutter sends a live region's change only when its label changes (D-241), so the
    same words again pass through empty while the jump is on its way.
    """
    schedule = await shown(screen_reader=True)
    await schedule.press_now()
    assert _note(schedule) == "Friday, May 15, 10:30 AM"
    schedule.hold = asyncio.Event()
    tap = asyncio.ensure_future(schedule.press_now())
    await schedule.until(lambda: schedule.jumping)
    assert _note(schedule) == ""
    schedule.hold.set()
    await asyncio.wait_for(tap, 30)  # generous: a passing tap ends at once
    await schedule.until(lambda: not schedule.jumping and _note(schedule))
    assert _note(schedule) == "Friday, May 15, 10:30 AM"


async def test_the_note_empties_once_talkback_has_read_it(
    shown: Callable[..., Awaitable[Shown]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-241: with words it is a stop in linear navigation, so only for ``SAID_S``."""
    monkeypatch.setattr(screen, "SAID_S", 0.01)
    schedule = await shown(screen_reader=True)
    await schedule.press_now()
    await schedule.until(lambda: _note(schedule) == "")


@pytest.mark.parametrize(
    "settings",
    [{}, {"announcements": True}, {"screen_reader": True, "announcements": True}],
    ids=["no-screen-reader", "no-screen-reader-ios", "voiceover"],
)
async def test_the_note_stays_empty_without_talkback(
    shown: Callable[..., Awaitable[Shown]], settings: dict[str, bool]
) -> None:
    """With no screen reader, or with announcements, "Now" leaves the note empty.

    D-241: the landing note is TalkBack's path, for a screen reader where Flutter
    reports no announcements (Android). Without a screen reader nothing is said, and
    VoiceOver hears the landing through ``announce_message()`` instead.
    """
    schedule = await shown(**settings)
    await schedule.scroll_away()
    await schedule.press_now()
    assert schedule.jumps and _note(schedule) == ""
