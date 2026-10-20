"""Tests for the Schedule screen: day tabs, slot lists, positions and Jump to now (#86, #89).

``Schedule`` renders in a real Flet session under the store providers
(``tests/sessions.py``'s ``showing()``), so the memoised path (D-153), the two renders
(D-156), the tabs' echo and the jumps run as Flet runs them. Two seams stand in for the
device: ``AppScaffold`` is the harness's ``Column`` of the app bar's actions, the body
and the "Now" button (the View and its bar are tested with ``tests/chrome.py``), and
``ListView.scroll_to`` is recorded instead of sent to a client, answering a keyed scroll
with the scroll end Flutter would report (or with nothing, for a list already in place)
and reading ``self.page`` first, as Flet does, so a list that has left the page raises
Flet's error. ``Services.run_every`` is recorded, so a test moves the minute tick by
hand (``Shown.at``). Each jump is recorded too (``Shown.jumps``): a jump may ask for its
scroll more than once (D-155), so the tests check which jumps ran and where they went,
not how many scrolls they asked for. The tests wait for what they expect to happen
(``Shown.until``, and every render returns only once no jump it started is still on its
way), never for a fixed time, so a loaded host only makes them slower (#237). Whether a
jump lands, how the tabs read at 200 % and what TalkBack says are device checks (#86,
#89).
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from functools import partial
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

import flet as ft
import httpx
import pytest
from flet.messaging.session import Session

from pycon_us import clock
from pycon_us.config import load_year
from pycon_us.core.timeline import NOW_KEY, now_place, timeline
from pycon_us.feed_refresh import Problem
from pycon_us.memory import ViewMemory
from pycon_us.prefs import Prefs
from pycon_us.screens import schedule as screen
from pycon_us.screens import schedule_days, schedule_now
from pycon_us.services import Services
from pycon_us.services.storage import THEME, Storage
from pycon_us.state import Conference
from pycon_us.ui import scrolling
from tests import sessions
from tests.fakes import MemoryPrefs, MemorySemantics
from tests.feeds import changed, processed
from tests.sessions import find, settle
from tests.trees import only, texts

YEAR = load_year(2026)
PACIFIC = ZoneInfo("America/Los_Angeles")
DAYS = tuple(date(2026, 5, 13) + timedelta(days=n) for n in range(7))
"""Wed 13 (tutorials) to Tue 19 (the second sprint day)."""

WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, MONDAY = (
    DAYS[0],
    DAYS[1],
    DAYS[2],
    DAYS[3],
    DAYS[5],
)
DURING = datetime(2026, 5, 15, 10, 40, tzinfo=PACIFIC)
"""Friday, the busiest day, during the morning break."""

BEFORE = datetime(2026, 4, 1, 12, 0, tzinfo=PACIFIC)
"""Six weeks before the conference."""

TEN_30 = "slot-2026-05-15T10:30:00-07:00"
"""Friday's 10:30 AM slot, on at ``DURING``: where a jump to now goes then."""

TALK = "142"
"""A Saturday talk: "Python for Humans - …", 10:30-11:00 AM, in the 10:30 slot."""


@dataclass
class Shown(sessions.Shown):
    """The harness's ``Shown`` on the Schedule: its scrolls, jumps and minute ticks.

    It is ``tests/sessions.py``'s, with what the Schedule's stand-ins record.
    """

    scrolls: list[tuple[ft.ListView, dict[str, Any]]] = field(default_factory=list)
    """Each ``ListView.scroll_to`` asked: the list and its arguments."""
    strips: list[bool] = field(default_factory=list)
    """Each ``StatusStrip``'s ``auto_refresh``, as the screen placed it."""
    slots: list[str] = field(default_factory=list)
    """The time labels of the slot bodies that ran, in order."""
    leave: Callable[[], None] = lambda: None
    """Replace the Schedule with another screen, as a bottom-tab switch does (D-142)."""
    moves: bool = True
    """Whether a keyed scroll ends with a scroll end; False: the list is already there."""
    late: bool = False
    """Whether the first keyed scroll's end comes too late, as on a loaded host (#237)."""
    hold: asyncio.Event | None = None
    """When set to an event, each ``scroll_to`` waits for it before it returns."""
    ticks: list[Callable[[], object]] = field(default_factory=list)
    """The minute ticks' actions (``Services.run_every``), called by ``at``."""
    rerender: Callable[[], None] = lambda: None
    """Re-render the Schedule's parent, keeping the Schedule mounted, as Back does."""
    jumps: list[tuple[str, scrolling.Jump]] = field(default_factory=list)
    """Each jump that ended (``jump_to_key``): its target key and how it ended."""
    jumping: int = 0
    """How many jumps are on their way."""

    @property
    def announced(self) -> list[str]:
        """What the screen asked a screen reader to say (``announce_message``)."""
        return cast(MemorySemantics, self.services.semantics).announced

    async def until(
        self, holds: Callable[[], object], *, timeout: float = 30.0
    ) -> None:
        """Settle until ``holds()`` is true, or fail after ``timeout`` seconds (#237).

        A poll rather than a fixed wait, so a loaded host only makes it slower; the
        deadline is generous because a passing test never reaches it.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while not holds():
            assert loop.time() < deadline, "the screen did not get there in time"
            await asyncio.sleep(0.01)
        await self.settle()

    async def at(self, moment: datetime) -> None:
        """Move the clock to ``moment`` and run the minute ticks, as time passing."""
        clock.set_test_now(moment)
        for action in self.ticks:
            action()
        await self.settle()

    def jumped(self) -> list[str]:
        """The targets of the jumps that ended, in order.

        One per jump, however many times it asked for its scroll.
        """
        return [key for key, _ in self.jumps]

    def forget(self) -> None:
        """Forget the scrolls and jumps so far, to see what the next step does."""
        self.scrolls.clear()
        self.jumps.clear()

    def keyed(self) -> list[str]:
        """The keys of the keyed scroll asks so far, a jump's second ask included."""
        return [
            kwargs["scroll_key"].value
            for _, kwargs in self.scrolls
            if kwargs.get("scroll_key") is not None
        ]

    @property
    def tabs(self) -> ft.Tabs:
        """The screen's one ``Tabs``."""
        (tabs,) = self.find(ft.Tabs)
        return tabs

    def list_of(self, day: date) -> ft.ListView:
        """The one mounted ``ListView`` of ``day``."""
        found = [c for c in self.find(ft.ListView) if c.key == f"day-{day.isoformat()}"]
        assert len(found) == 1, day
        return found[0]

    @property
    def fab(self) -> ft.FloatingActionButton | None:
        """The "Now" or "Today" button, or None while it is hidden."""
        found = self.find(ft.FloatingActionButton)
        return found[0] if found else None

    async def change_day(self, day: date) -> None:
        """What Flutter sends when a tab or a swipe has settled on a day."""
        index = DAYS.index(day)
        self.session.apply_patch(self.tabs._i, {"selected_index": index})  # first
        await self.event(self.tabs, "change", index)

    async def scroll_end(self, day: date, pixels: float) -> None:
        """What Flutter sends when a scroll of the day's list ends."""
        await self.event(self.list_of(day), "scroll", _scroll_end(pixels))

    async def scroll_away(self, day: date = FRIDAY) -> None:
        """Scroll the day's list back to its top, far from where a jump landed."""
        await self.scroll_end(day, 0.0)

    async def press_now(self) -> None:
        """Tap the "Now" or "Today" button, which must be showing."""
        assert self.fab is not None
        await self.click(self.fab)

    async def tap_star(self, session_id: str) -> None:
        """Tap the star on ``session_id``'s row."""
        star = self.node(f"schedule.favorite.{session_id}").content
        assert star is not None
        await self.click(star)


def _scroll_end(pixels: float) -> dict[str, object]:
    """A scroll end event's data at ``pixels``, as Flutter sends it."""
    return {
        "event_type": "end",
        "pixels": pixels,
        "min_scroll_extent": 0.0,
        "max_scroll_extent": 20_000.0,
        "viewport_dimension": 700.0,
    }


def _assert_asks(schedule: Shown, day: date, key: str, duration: int) -> None:
    """Assert that every keyed scroll ask so far went to ``key`` on the day's list.

    A jump asks once, or again when its scroll end comes late (D-155): how many asks
    a loaded host sees is not the jump's behaviour, where they go is (#237).
    """
    asks = [(t, kwargs) for t, kwargs in schedule.scrolls if "scroll_key" in kwargs]
    assert asks
    day_list = schedule.list_of(day)
    for target, kwargs in asks:
        assert target is day_list
        assert kwargs["scroll_key"].value == key
        assert kwargs["duration"] == duration


@pytest.fixture
def now() -> list[datetime | None]:
    """The frozen clock: set ``now[0]`` before the screen renders; None lifts it."""
    return [DURING]


@pytest.fixture
def memory() -> ViewMemory:
    """A fresh ``ViewMemory``, which a test may fill before the render."""
    return ViewMemory()


@pytest.fixture
def conference() -> Conference:
    """The recorded 2026 feed as the bundled ``Conference``."""
    return Conference(data=processed(2026), source="bundled", version=1)


@pytest.fixture
async def shown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    now: list[datetime | None],
    memory: ViewMemory,
    conference: Conference,
) -> AsyncIterator[Callable[[], Awaitable[Shown]]]:
    """Return a function that renders the Schedule; every render is closed at the end."""
    # Generous: the stand-in reports a scroll end at once and a test reports the tabs'
    # switch, so a passing test never waits this long. A test of a list that never
    # moves sets its own.
    monkeypatch.setattr(scrolling, "LANDING_S", 30.0)
    monkeypatch.setattr(screen, "SETTLE_S", 30.0)

    async def scroll_to(self: ft.ListView, **kwargs: Any) -> None:
        # Flet's _invoke_method reads it first: a list off the page raises.
        session = cast(Session, self.page.session)  # pyright: ignore[reportOptionalMemberAccess]
        result = sessions.current(Shown)
        result.scrolls.append((self, kwargs))
        if result.hold is not None:
            await result.hold.wait()
        if kwargs.get("scroll_key") is None or not result.moves:
            return
        if result.late:
            # The first ask's wait ends at once, before its end could come; the
            # next waits as long as any other, so the outcome never hangs on time.
            first = len(result.keyed()) == 1
            monkeypatch.setattr(scrolling, "LANDING_S", 0.0 if first else 30.0)
            if first:
                return
        asyncio.get_running_loop().call_soon(  # where it ended
            lambda: asyncio.ensure_future(
                session.dispatch_event(self._i, "scroll", _scroll_end(4000.0))
            )
        )

    @ft.component
    def Strip(*, auto_refresh: bool = False) -> ft.Control:
        sessions.current(Shown).strips.append(auto_refresh)
        return ft.Text("strip")

    def counted_slot(label: str, slot_rows: Any, *, above: bool) -> ft.Control:
        sessions.current(Shown).slots.append(label)
        return layout(label, slot_rows, above=above)

    async def run_every(_: Services, seconds: float, action: Any) -> None:
        sessions.current(Shown).ticks.append(action)

    async def recorded_jump(
        list_ref: ft.Ref[ft.ListView], key: str, **kwargs: Any
    ) -> scrolling.Jump:
        result = sessions.current(Shown)
        result.jumping += 1
        try:
            ended = await scrolling.jump_to_key(list_ref, key, **kwargs)
        finally:
            result.jumping -= 1
        result.jumps.append((key, ended))
        return ended

    layout = schedule_days.slot_layout
    monkeypatch.setattr(ft.ListView, "scroll_to", scroll_to)
    monkeypatch.setattr(Services, "run_every", run_every)
    monkeypatch.setattr(screen, "jump_to_key", recorded_jump)
    monkeypatch.setattr(screen, "StatusStrip", Strip)
    monkeypatch.setattr(schedule_days, "slot_layout", counted_slot)

    @ft.component
    def Elsewhere() -> ft.Control:
        return ft.Text("another tab")

    @ft.component
    def Opened() -> ft.Control:
        here, set_here = ft.use_state(True)
        _, set_renders = ft.use_state(0)
        result = sessions.current(Shown)
        result.leave = lambda: set_here(False)
        result.rerender = lambda: set_renders(lambda n: n + 1)
        return screen.Schedule() if here else Elsewhere()

    try:
        async with AsyncExitStack() as stack:

            async def show(
                *,
                moves: bool = True,
                late: bool = False,
                hold: asyncio.Event | None = None,
                wait: bool = True,
                **settings: Any,
            ) -> Shown:
                """Render the Schedule with these ``Prefs`` settings.

                ``moves``, ``late`` and ``hold`` are as in ``Shown``.

                With ``wait`` it returns once no jump is on its way, so the next step
                never meets one (#237). The first display's jump, when there is one, has
                ended by then: ``settle()`` has already started it, since the effect's
                chain up to the jump is pure asyncio here (``MemoryPrefs`` answers
                inline), with no timer or thread hop. A test that expects that jump also
                checks ``jumps`` right after.
                """
                clock.set_test_now(now[0])
                result = await stack.enter_async_context(
                    sessions.showing(
                        Opened,
                        screen,
                        year=YEAR,
                        conference=conference,
                        tmp_path=tmp_path,
                        monkeypatch=monkeypatch,
                        view_path="",  # no Router: what ft.use_view_path() says outside
                        prefs=Prefs(loaded=True, **settings),
                        memory=memory,
                        kind=partial(Shown, moves=moves, late=late, hold=hold),
                    )
                )
                if wait:
                    await result.until(lambda: not result.jumping)
                return result

            yield cast(Callable[[], Awaitable[Shown]], show)
    finally:
        clock.set_test_now(None)


# ------------------------------------------------------------------ day tabs (SCHED-01)


async def test_every_conference_day_is_a_one_line_tab_read_in_full(
    shown: Callable[[], Awaitable[Shown]],
) -> None:
    """S2: a second line clipped at 200 %; the spoken label keeps the month."""
    schedule = await shown()
    assert schedule.tabs.length == len(DAYS)
    labels = [_tab_text(schedule, i) for i in range(7)]
    assert labels == [
        "Wed 13",
        "Thu 14",
        "Fri 15",
        "Sat 16",
        "Sun 17",
        "Mon 18",
        "Tue 19",
    ]
    friday = schedule.node("schedule.day_tab.2")
    assert _spoken(schedule, 2) == "Friday, May 15, today"  # after "Tab 3 of 7"
    assert friday.label is None  # merged into the tab's node with the identifier
    assert _has_dot(schedule, friday)  # today's mark
    (row,) = find(schedule.session, ft.Row, lambda c: inside(c, friday))
    assert row.vertical_alignment == ft.CrossAxisAlignment.CENTER  # at every size
    saturday = schedule.node("schedule.day_tab.3")
    assert _spoken(schedule, 3) == "Saturday, May 16"
    assert not _has_dot(schedule, saturday)
    (bar,) = find(schedule.session, ft.TabBar)
    assert bar.scrollable


async def test_today_is_selected_during_the_conference(
    shown: Callable[[], Awaitable[Shown]],
) -> None:
    """During the conference, the Schedule opens on today's tab."""
    schedule = await shown()
    assert schedule.tabs.selected_index == DAYS.index(FRIDAY)


async def test_the_first_day_is_selected_outside_the_conference(
    shown: Callable[[], Awaitable[Shown]], now: list[datetime]
) -> None:
    """Before the conference, the first day is selected and no tab says "today"."""
    now[0] = BEFORE
    schedule = await shown()
    assert schedule.tabs.selected_index == 0
    assert all("today" not in _spoken(schedule, i) for i in range(len(DAYS)))


async def test_the_developer_fake_clock_picks_today(
    shown: Callable[[], Awaitable[Shown]], now: list[datetime | None]
) -> None:
    """D-187: the fake clock moves ``clock.now()``, and with it the Schedule's today."""
    now[0] = None  # no test override: the fake clock answers
    clock.start_fake_clock(datetime(2026, 5, 16, 23, 30, tzinfo=PACIFIC))
    try:
        schedule = await shown()
        assert schedule.tabs.selected_index == DAYS.index(SATURDAY)
        assert _spoken(schedule, DAYS.index(SATURDAY)) == "Saturday, May 16, today"
    finally:
        clock.start_fake_clock(None)


async def test_a_device_in_another_zone_gets_the_pacific_time_note(
    shown: Callable[[], Awaitable[Shown]], machine_tz: str
) -> None:
    """D-35, D-240: the times are conference time; say so only when the device differs."""
    schedule = await shown()
    notes = find(
        schedule.session,
        ft.Semantics,
        lambda c: c.identifier == "schedule.zone_note",
    )
    if machine_tz == "America/Los_Angeles":
        assert notes == []
    else:
        (note,) = notes
        assert texts(note) == ["Times are Pacific Time (PDT)"]


async def test_the_zone_note_keeps_its_place_under_the_strip_in_every_zone(
    shown: Callable[[], Awaitable[Shown]], machine_tz: str
) -> None:
    """#313: a line that comes and goes would shift the day pages and rebuild them."""
    schedule = await shown()
    column = cast(ft.Column, schedule.tabs.content)
    assert len(column.controls) == 5
    pages = cast(ft.Stack, column.controls[-1])  # the day pages over the landing note
    assert isinstance(pages.controls[-1], ft.TabBarView)


async def test_a_remembered_day_wins_over_today(
    shown: Callable[[], Awaitable[Shown]], memory: ViewMemory
) -> None:
    """A day remembered in ``ViewMemory`` is selected over today."""
    memory.schedule_day = SATURDAY
    schedule = await shown()
    assert schedule.tabs.selected_index == DAYS.index(SATURDAY)


def _tab_text(schedule: Shown, index: int) -> str:
    """The visible text of day tab ``index``."""
    node = schedule.node(f"schedule.day_tab.{index}")
    (text,) = find(schedule.session, ft.Text, lambda c: inside(c, node))
    return str(text.value)


def _spoken(schedule: Shown, index: int) -> str:
    """What a screen reader says for day tab ``index``."""
    node = schedule.node(f"schedule.day_tab.{index}")
    (text,) = find(schedule.session, ft.Text, lambda c: inside(c, node))
    return str(text.semantics_label)


def _has_dot(schedule: Shown, node: ft.Semantics) -> bool:
    """Whether the tab ``node`` holds today's mark, a dot."""
    return bool(find(schedule.session, ft.Container, lambda c: inside(c, node)))


async def test_a_day_change_is_remembered_and_its_echo_changes_nothing(
    shown: Callable[[], Awaitable[Shown]], memory: ViewMemory
) -> None:
    """A day change is kept in ``ViewMemory``; its echo re-renders no slot or row."""
    schedule = await shown()
    await schedule.change_day(SATURDAY)
    assert memory.schedule_day == SATURDAY
    assert schedule.tabs.selected_index == DAYS.index(SATURDAY)
    schedule.rows.clear()
    schedule.slots.clear()
    await schedule.change_day(SATURDAY)  # the echo of a switch set from Python
    assert (schedule.rows, schedule.slots) == ([], [])


# ------------------------------------------------------------------ the day lists


async def test_the_shown_day_renders_first_and_the_others_after_a_round_trip(
    shown: Callable[[], Awaitable[Shown]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-156: the first render has one day list; the second all of them."""
    first: list[int] = []
    original = schedule_days._DayList

    def spy(*args: Any, **kwargs: Any) -> ft.Control:
        first.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(schedule_days, "_DayList", spy)
    schedule = await shown()
    (view,) = find(schedule.session, ft.TabBarView)
    pages = list(view.controls)
    assert len(pages) == len(DAYS)
    assert len(find(schedule.session, ft.ListView)) == len(DAYS)  # after the second
    assert first[0] == 1  # and the first render built only the shown day's list


async def test_each_slot_is_one_keyed_item_beside_its_gutter(
    shown: Callable[[], Awaitable[Shown]],
) -> None:
    """D-31, D-155: a ScrollKey per slot, the filter's slots only, in time order."""
    schedule = await shown()
    friday = schedule.list_of(FRIDAY)
    items = find(
        schedule.session,
        ft.Container,
        lambda c: (
            isinstance(c.key, ft.ScrollKey)
            and c.key != ft.ScrollKey(NOW_KEY)  # today's now line
            and inside(c, friday)
        ),
    )
    keys = sorted(str(cast(ft.ScrollKey, item.key).value) for item in items)
    # D-242: each key is on an empty anchor above its slot, so no row is under a key
    # and every row keeps its nodes, the screen reader's focus after Back (F62).
    assert all(item.content is None and item.height == 0 for item in items)
    slots = [_slot(item) for item in items]
    assert not any(
        inside(node, item)
        for node in find(schedule.session, ft.Semantics, lambda c: inside(c, friday))
        for item in items
    )
    # A jump puts the slot's time under the tab bar, not a second line (ux.md §5.2);
    # the first slot has none, and the now line stands for the next one's (D-204).
    dividers = find(
        schedule.session, ft.Divider, lambda c: c.visible and inside(c, friday)
    )
    assert len(dividers) == len(items) - 2
    assert not any(inside(d, slot) for d in dividers for slot in slots)
    expected = timeline(processed(2026), FRIDAY, Prefs().excluded_tracks)
    assert keys == sorted(slot.key for slot in expected)
    shown_ids = {
        str(node.identifier).rsplit(".", 1)[1]
        for node in find(schedule.session, ft.Semantics, lambda c: inside(c, friday))
        if node.identifier and ".session." in node.identifier
    }
    assert shown_ids  # and no open space, which the default filter hides (D-20)
    sessions = processed(2026).sessions
    assert all(sessions[i].track != "Open Space" for i in shown_ids if i in sessions)


async def test_at_the_largest_text_each_slot_puts_its_time_above_its_rows(
    shown: Callable[[], Awaitable[Shown]],
) -> None:
    """D-216: the rows get the whole width; the jump's keys stay on the slots."""
    schedule = await shown()

    def slots() -> list[ft.Container]:
        friday = schedule.list_of(FRIDAY)  # the list the last render mounted
        return find(
            schedule.session,
            ft.Container,
            lambda c: (
                isinstance(c.key, ft.ScrollKey)
                and c.key != ft.ScrollKey(NOW_KEY)
                and inside(c, friday)
            ),
        )

    beside = {str(cast(ft.ScrollKey, c.key).value) for c in slots()}
    assert all(isinstance(_slot(c), ft.Row) for c in slots())  # the gutter
    schedule.prefs.time_above = True  # what GutterProbe measures at that size
    await settle()
    assert {str(cast(ft.ScrollKey, c.key).value) for c in slots()} == beside
    for slot in slots():
        column = _slot(slot)
        assert isinstance(column, ft.Column)
        heading = column.controls[0]
        assert isinstance(heading, ft.Semantics) and heading.header
    friday = schedule.list_of(FRIDAY)
    assert not find(  # no gutter left in the day
        schedule.session, ft.Stack, lambda c: inside(c, friday)
    )


def _slot(anchor: ft.Container) -> ft.Control:
    """The slot a ``ScrollKey`` anchor marks: the control after it (D-242)."""
    _, slot = cast(ft.Column, anchor.parent).controls
    return slot


def inside(control: ft.BaseControl, ancestor: ft.BaseControl) -> bool:
    """Whether ``control`` is mounted under ``ancestor``, components included."""
    node = control.parent
    while node is not None:
        if node is ancestor:
            return True
        node = node.parent
    return False


async def test_only_today_s_list_builds_every_slot(
    shown: Callable[[], Awaitable[Shown]],
) -> None:
    """D-154: the jump's list; every other list stays lazy."""
    schedule = await shown()
    extents = {day: schedule.list_of(day).cache_extent for day in DAYS}
    assert extents.pop(FRIDAY) == scrolling.FULL_LIST_EXTENT
    assert set(extents.values()) == {None}
    assert all(not schedule.list_of(d).build_controls_on_demand is False for d in DAYS)


async def test_outside_the_conference_no_list_is_built_in_full(
    shown: Callable[[], Awaitable[Shown]], now: list[datetime]
) -> None:
    """Before the conference, every day list stays lazy."""
    now[0] = BEFORE
    schedule = await shown()
    assert {schedule.list_of(day).cache_extent for day in DAYS} == {None}


async def test_a_star_tap_re_renders_one_slot_and_one_row(
    shown: Callable[[], Awaitable[Shown]],
) -> None:
    """D-153: the screen re-renders, but every other day, slot and row is skipped."""
    schedule = await shown()
    schedule.rows.clear()
    schedule.slots.clear()
    await schedule.tap_star(TALK)
    assert schedule.favorites.ids == {TALK}
    assert schedule.rows == [TALK]
    assert schedule.slots == ["10:30 AM"]


async def test_a_sprint_day_says_so_and_links_to_the_sprints(
    shown: Callable[[], Awaitable[Shown]],
) -> None:
    """Monday's list says it is a sprint day, and its button opens the Sprints page."""
    schedule = await shown()
    state = schedule.node("schedule.sprint_day.2026-05-18")
    assert texts(state)[0] == "Monday is a sprint day"
    button = only(schedule.list_of(MONDAY), ft.FilledTonalButton)
    assert button.content == "See the sprints"
    await schedule.session.dispatch_event(button._i, "click", None)
    await settle()
    assert schedule.went == ["/more/sprints"]


async def test_a_day_the_filter_empties_offers_to_clear_the_filters(
    shown: Callable[[], Awaitable[Shown]], conference: Conference
) -> None:
    """ux.md §4.6: never a blank day, and not the sprint day's state either."""
    wednesday = {
        s.track
        for slot in timeline(processed(2026), WEDNESDAY, ())
        for s in slot.sessions
    }
    schedule = await shown()
    await schedule.prefs.save(schedule.storage, excluded_tracks=tuple(wednesday))
    await settle()
    state = schedule.node("schedule.filtered_day.2026-05-13")
    assert texts(state)[0] == "No sessions on Wednesday match your filters"
    button = only(schedule.list_of(WEDNESDAY), ft.FilledTonalButton)
    assert button.content == "Clear filters"
    await schedule.session.dispatch_event(button._i, "click", None)
    await settle()
    assert schedule.prefs.excluded_tracks == ()
    assert (
        find(
            schedule.session,
            ft.Semantics,
            lambda c: c.identifier == "schedule.filtered_day.2026-05-13",
        )
        == []
    )


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
    """D-70 rule 3, F2: the effect's cleanup is what makes Flet cancel its task."""
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
    """Without TalkBack, a "Now" tap jumps and leaves the landing note empty.

    Nothing extra without a screen reader; VoiceOver hears the announcement, since a
    live region would move its focus off the button (F13).
    """
    schedule = await shown(**settings)
    await schedule.scroll_away()
    await schedule.press_now()
    assert schedule.jumps and _note(schedule) == ""


# ------------------------------------------------------------------ the jump's policy (#89)


def friday_at(hour: int, minute: int = 0) -> datetime:
    """Friday, May 15 2026 at ``hour``:``minute``, Pacific Time."""
    return datetime(2026, 5, 15, hour, minute, tzinfo=PACIFIC)


async def test_swiping_to_today_after_opening_on_another_day_jumps_once(
    shown: Callable[[], Awaitable[Shown]], memory: ViewMemory
) -> None:
    """D-204: today's first display jumps, wherever the Schedule opened."""
    memory.schedule_day = SATURDAY
    schedule = await shown()
    assert schedule.keyed() == []  # Saturday is not today
    await schedule.change_day(FRIDAY)
    assert schedule.jumps == [(TEN_30, "landed")]
    assert memory.jumped_on == FRIDAY
    await schedule.scroll_end(FRIDAY, 2000.0)  # the user scrolls on
    await schedule.change_day(SATURDAY)
    schedule.scrolls.clear()
    await schedule.change_day(FRIDAY)
    assert schedule.keyed() == []  # the second display is put back, not moved
    ((_, kwargs),) = schedule.scrolls
    assert kwargs == {"offset": 2000.0, "duration": 0}


async def test_a_today_tap_from_another_day_is_that_day_s_one_jump(
    shown: Callable[[], Awaitable[Shown]], memory: ViewMemory
) -> None:
    """D-204: a Today tap counts as today's jump: one asked jump, none unasked after."""
    memory.schedule_day = SATURDAY  # jumped_on is None: today has not shown yet
    schedule = await shown()
    await schedule.press_now()
    await schedule.change_day(FRIDAY)  # Flutter's echo of the switch
    await schedule.until(lambda: schedule.jumps and not schedule.jumping)
    assert schedule.jumps == [(TEN_30, "landed")]  # once, not twice
    assert memory.jumped_on == FRIDAY
    await schedule.scroll_end(FRIDAY, 2000.0)
    await schedule.change_day(SATURDAY)
    schedule.scrolls.clear()
    await schedule.change_day(FRIDAY)
    assert schedule.keyed() == []  # the next display is put back, not moved


async def test_a_re_render_as_on_back_from_a_detail_never_jumps(
    shown: Callable[[], Awaitable[Shown]],
) -> None:
    """#313: a detail pushed over the Schedule keeps it mounted; Back re-renders it."""
    schedule = await shown()
    schedule.scrolls.clear()
    renders = len(schedule.retaps)  # one per Schedule render
    schedule.rerender()
    await settle()
    assert len(schedule.retaps) > renders  # it did re-render
    assert schedule.scrolls == []


async def test_a_refresh_never_jumps(
    shown: Callable[[], Awaitable[Shown]], conference: Conference
) -> None:
    """#313: a new feed version re-renders the lists, never moves them."""
    schedule = await shown()
    schedule.scrolls.clear()
    conference.data = processed(2026)
    conference.version += 1
    await settle()
    assert schedule.scrolls == []


async def test_a_filter_change_never_jumps(
    shown: Callable[[], Awaitable[Shown]],
) -> None:
    """#313: the filter re-renders the slots it changed, never moves the list."""
    schedule = await shown()
    schedule.scrolls.clear()
    await schedule.prefs.save(schedule.storage, excluded_tracks=("Charla",))
    await settle()
    assert schedule.scrolls == []


async def test_a_minute_never_jumps_not_even_when_a_slot_starts(
    shown: Callable[[], Awaitable[Shown]],
) -> None:
    """Minute ticks never scroll the list, not even the one at which a slot starts."""
    schedule = await shown()
    schedule.scrolls.clear()
    await schedule.at(friday_at(10, 41))
    await schedule.at(friday_at(11, 0))  # the 11:00 AM slot starts
    assert schedule.scrolls == []


async def test_each_new_today_jumps_once_by_itself(
    shown: Callable[[], Awaitable[Shown]], memory: ViewMemory
) -> None:
    """A new conference day's first display jumps, and a second one that day does not.

    D-204: a process that lives across days jumps on each conference day's first
    display, as after a fake-clock change; never twice the same day.
    """
    memory.jumped_on = THURSDAY
    schedule = await shown()
    assert schedule.jumped() == [TEN_30]
    again = await shown()  # a tab return the same day
    assert again.keyed() == [] and again.jumps == []


async def test_midnight_moves_today_s_dot_and_button_never_the_day_shown(
    shown: Callable[[], Awaitable[Shown]], now: list[datetime | None]
) -> None:
    """At midnight the shown day stays, while the dot and full list move to the new day.

    D-204: the day picked at the first display stays; the new today waits for the user,
    and jumps on its first display.
    """
    now[0] = friday_at(23, 58)
    schedule = await shown()
    assert schedule.tabs.selected_index == DAYS.index(FRIDAY)
    await schedule.scroll_away()
    schedule.forget()
    await schedule.at(datetime(2026, 5, 16, 0, 1, tzinfo=PACIFIC))
    assert schedule.tabs.selected_index == DAYS.index(FRIDAY)  # not moved
    assert _spoken(schedule, DAYS.index(SATURDAY)) == "Saturday, May 16, today"
    assert _spoken(schedule, DAYS.index(FRIDAY)) == "Friday, May 15"
    assert texts(
        cast(ft.Control, cast(ft.FloatingActionButton, schedule.fab).content)
    ) == ["Today"]
    assert schedule.list_of(SATURDAY).cache_extent == scrolling.FULL_LIST_EXTENT
    assert schedule.list_of(FRIDAY).cache_extent is None
    assert schedule.scrolls == []
    await schedule.change_day(SATURDAY)
    assert schedule.jumped() == [NOW_KEY]  # before the day's first slot: the line


# ------------------------------------------------------------------ the button (#89)


async def test_the_button_hides_within_half_a_screen_of_where_the_jump_landed(
    shown: Callable[[], Awaitable[Shown]],
) -> None:
    """D-204: within half a screen (700 px here) of where the jump landed (4,000 px)."""
    schedule = await shown()
    assert schedule.fab is None
    await schedule.scroll_end(FRIDAY, 4300.0)
    assert schedule.fab is None
    await schedule.scroll_end(FRIDAY, 3600.0)
    assert schedule.fab is not None
    await schedule.scroll_end(FRIDAY, 3800.0)  # back near the landing
    assert schedule.fab is None


async def test_the_button_waits_for_the_first_jump_on_a_list_already_in_place(
    shown: Callable[..., Awaitable[Shown]],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The button stays hidden while the first jump tries a list already in place.

    A list already in place sends no scroll end, so the jump answers only after its
    tries: the button must not show for those seconds and then vanish (D-204).
    """
    monkeypatch.setattr(scrolling, "LANDING_S", 0.02)
    asked = asyncio.Event()  # the first ask is held: the jump stays on its way (#270)
    with caplog.at_level(logging.INFO):
        schedule = await shown(moves=False, hold=asked, wait=False, reduce_motion=True)
        await schedule.until(lambda: schedule.keyed())
        assert schedule.jumping == 1
        assert schedule.fab is None  # the jump is on its way
        asked.set()
        await schedule.until(lambda: schedule.jumps)
    assert schedule.jumps == [(TEN_30, "still")]
    assert "did not move" in caplog.text
    assert len(schedule.scrolls) == scrolling.JUMP_TRIES
    assert schedule.fab is None  # "still": the place is in view
    await schedule.scroll_end(FRIDAY, 3000.0)
    assert schedule.fab is not None  # the landing was kept, so a scroll away counts


async def test_a_screen_reader_keeps_the_button_so_a_tap_never_drops_its_focus(
    shown: Callable[..., Awaitable[Shown]],
) -> None:
    """With a screen reader, the button shows after the jump and stays after a tap.

    ux.md §5.2 item 5: a control that hides under the focus sends the reader elsewhere,
    over the announcement of where the list went.
    """
    schedule = await shown(screen_reader=True, announcements=True)
    assert schedule.fab is not None  # after the first display's jump too
    await schedule.press_now()
    assert schedule.announced == ["Friday, May 15, 10:30 AM"]
    assert schedule.fab is not None


async def test_a_tap_after_a_slot_started_since_the_tick_goes_there_and_hides(
    shown: Callable[[], Awaitable[Shown]],
) -> None:
    """A tap after a slot started, before the tick, jumps there and hides the button.

    The tap reads the clock, and so does the render its landing causes: the line moves
    with the jump and the button hides at once, not at the next tick.
    """
    schedule = await shown()
    await schedule.scroll_away()
    clock.set_test_now(friday_at(11, 0))  # the 11:00 AM slot starts before the tick
    schedule.forget()
    await schedule.press_now()
    assert schedule.jumped() == ["slot-2026-05-15T11:00:00-07:00"]
    keys = _list_items(schedule, FRIDAY)
    assert keys[keys.index(NOW_KEY) - 1] == "slot-2026-05-15T11:00:00-07:00"
    assert schedule.fab is None


async def test_a_slot_starting_brings_the_button_back(
    shown: Callable[[], Awaitable[Shown]],
) -> None:
    """The list stays put; what it shows is no longer now, so "Now" offers to move."""
    schedule = await shown()
    assert schedule.fab is None
    await schedule.at(friday_at(10, 59))
    assert schedule.fab is None  # still the 10:30 AM break
    await schedule.at(friday_at(11, 0))
    assert schedule.fab is not None


@pytest.mark.parametrize("change", ["refresh", "filter"])
async def test_a_refresh_or_a_filter_change_brings_the_button_back(
    shown: Callable[[], Awaitable[Shown]], conference: Conference, change: str
) -> None:
    """Either changes the heights above the place, so its offset no longer locates it."""
    schedule = await shown()
    assert schedule.fab is None
    if change == "refresh":
        conference.data = processed(2026)
        conference.version += 1
    else:
        await schedule.prefs.save(schedule.storage, excluded_tracks=("Charla",))
    await settle()
    assert schedule.fab is not None


async def test_a_refresh_that_brings_the_same_feed_re_renders_nothing(
    shown: Callable[[], Awaitable[Shown]], conference: Conference, tmp_path: Path
) -> None:
    """A refresh with the same feed re-renders no slot or row and keeps "Now" hidden.

    #290, D-224: the start refresh over the cache re-rendered every slot, remounting
    each ``ScrollKey`` box, and brought "Now" back over the now line; a changed feed
    still brings it back (D-204).
    """
    storage = Storage(prefs=MemoryPrefs(), directory=tmp_path, year=2026)
    await conference.load_local(storage, YEAR)  # the snapshot, as a first start
    schedule = await shown()
    assert schedule.jumped() == [TEN_30]
    assert schedule.fab is None
    schedule.rows.clear()
    schedule.slots.clear()

    snapshot = YEAR.read_snapshot().raw
    await conference.refresh(storage, YEAR, transport=_serving(snapshot))
    await settle()

    assert conference.source == "network"  # the refresh did end well
    assert (schedule.slots, schedule.rows) == ([], [])
    assert schedule.fab is None

    await conference.refresh(storage, YEAR, transport=_serving(changed(2026, _rename)))
    await settle()
    assert schedule.fab is not None


def _serving(body: bytes) -> httpx.MockTransport:
    """A transport that answers every request with ``body``."""
    return httpx.MockTransport(lambda _: httpx.Response(200, content=body))


def _rename(document: dict[str, Any]) -> None:
    """Rename talk 142 in a feed's JSON: a feed that changed."""
    slot = next(s for s in document["schedule"] if s.get("conf_key") == int(TALK))
    slot["name"] = "Renamed on the server"


async def test_another_day_always_offers_today(
    shown: Callable[[], Awaitable[Shown]],
) -> None:
    """On a day other than today, the button shows and says "Today"."""
    schedule = await shown()
    assert schedule.fab is None
    await schedule.change_day(SATURDAY)
    assert texts(
        cast(ft.Control, cast(ft.FloatingActionButton, schedule.fab).content)
    ) == ["Today"]


# ------------------------------------------------------------------ the now line (#89)


def _now_line(schedule: Shown) -> ft.Semantics:
    """The now line's ``Semantics`` node."""
    return schedule.node("schedule.now_line")


def _list_items(schedule: Shown, day: date) -> list[str]:
    """The keys of a day list's items, in order: slots and the now line."""
    keys: list[str] = []
    for item in schedule.list_of(day).controls:
        (box,) = find(
            schedule.session,
            ft.Container,
            lambda c, item=item: (
                isinstance(c.key, ft.ScrollKey) and (c is item or inside(c, item))
            ),
        )
        keys.append(str(cast(ft.ScrollKey, box.key).value))
    return keys


async def test_today_s_now_line_sits_after_the_last_slot_that_started(
    shown: Callable[[], Awaitable[Shown]],
) -> None:
    """ux.md §5.2 item 4: a 2 dp primary line, "Now · 10:40 AM", read "Current time"."""
    schedule = await shown()
    now_key = ft.ScrollKey(NOW_KEY)
    keys = _list_items(schedule, FRIDAY)
    line = keys.index(NOW_KEY)
    assert keys[line - 1] == TEN_30
    assert keys[line + 1] == "slot-2026-05-15T11:00:00-07:00"
    node = _now_line(schedule)
    assert node.label == "Current time 10:40 AM"
    assert node.exclude_semantics and not node.live_region
    assert texts(node) == ["Now · 10:40 AM"]
    (anchor,) = find(schedule.session, ft.Container, lambda c: c.key == now_key)
    assert anchor.content is None and not inside(node, anchor)  # D-242
    (bar,) = find(schedule.session, ft.Container, lambda c: inside(c, node))
    assert (bar.height, bar.bgcolor) == (schedule_now.NOW_LINE, ft.Colors.PRIMARY)
    assert NOW_KEY not in _list_items(schedule, SATURDAY)  # today's list only


async def test_a_minute_re_renders_the_line_alone_and_a_slot_start_moves_it(
    shown: Callable[[], Awaitable[Shown]],
) -> None:
    """A minute re-renders the now line alone; a slot start moves it below that slot.

    D-153: no row re-renders; a move re-renders only the two slots whose divider the
    line takes or gives back.
    """
    schedule = await shown()
    schedule.rows.clear()
    schedule.slots.clear()
    await schedule.at(friday_at(10, 41))
    assert texts(_now_line(schedule)) == ["Now · 10:41 AM"]
    assert (schedule.rows, schedule.slots) == ([], [])
    await schedule.at(friday_at(11, 0))
    keys = _list_items(schedule, FRIDAY)
    assert keys[keys.index(NOW_KEY) - 1] == "slot-2026-05-15T11:00:00-07:00"
    assert schedule.rows == []
    assert sorted(schedule.slots) == ["11:00 AM", "11:30 AM"]


async def test_between_slots_the_jump_lands_on_the_now_line(
    shown: Callable[..., Awaitable[Shown]], now: list[datetime | None]
) -> None:
    """Between slots, the jump lands on the now line and a tap announces the time.

    D-204: at 2:35 PM nothing is on; the line sits above 2:45 PM's slot, and a screen
    reader hears the time, as the line itself says it.
    """
    now[0] = friday_at(14, 35)
    schedule = await shown(screen_reader=True, announcements=True)
    assert schedule.jumped() == [NOW_KEY]
    keys = _list_items(schedule, FRIDAY)
    assert keys[keys.index(NOW_KEY) + 1] == "slot-2026-05-15T14:45:00-07:00"
    await schedule.scroll_away()
    await schedule.press_now()
    assert schedule.announced == ["Friday, May 15, current time 2:35 PM"]


async def test_after_the_day_the_line_ends_the_list_and_now_goes_there(
    shown: Callable[[], Awaitable[Shown]], now: list[datetime | None]
) -> None:
    """The button keeps its label: the line at the end shows now is past the day."""
    now[0] = friday_at(21, 0)
    schedule = await shown()
    assert _list_items(schedule, FRIDAY)[-1] == NOW_KEY
    assert schedule.jumped() == [NOW_KEY]
    await schedule.scroll_away()
    assert texts(
        cast(ft.Control, cast(ft.FloatingActionButton, schedule.fab).content)
    ) == ["Now"]


# ------------------------------------------------------------------ without data (D-32)


async def test_the_strip_refreshes_every_15_minutes_with_or_without_data(
    shown: Callable[[], Awaitable[Shown]], conference: Conference
) -> None:
    """D-40, D-175: Now and Schedule pass auto_refresh=True."""
    schedule = await shown()
    assert schedule.strips and set(schedule.strips) == {True}
    conference.data = None
    conference.version += 1
    await settle()
    assert set(schedule.strips) == {True}


async def test_without_data_the_skeleton_shows_until_the_first_fetch_ends(
    shown: Callable[[], Awaitable[Shown]], conference: Conference
) -> None:
    """Without data, the Schedule shows the loading skeleton and no day tabs."""
    conference.data, conference.source = None, "none"
    schedule = await shown()
    assert find(schedule.session, ft.Semantics, lambda c: c.label == "Loading schedule")
    assert find(schedule.session, ft.Tabs) == []


async def test_the_first_data_is_the_first_display_it_renders_today_first_and_jumps(
    shown: Callable[[], Awaitable[Shown]],
    conference: Conference,
    memory: ViewMemory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """NEW-03, then the first fetch: D-156's two renders and the one jump still hold."""
    lists: list[date] = []
    spy = schedule_days._DayList

    def counted(day: date, *args: Any, **kwargs: Any) -> ft.Control:
        lists.append(day)
        return spy(day, *args, **kwargs)

    monkeypatch.setattr(schedule_days, "_DayList", counted)
    conference.data, conference.source = None, "none"
    schedule = await shown()
    assert schedule.scrolls == [] and memory.jumped_on is None

    conference.data, conference.source = processed(2026), "network"
    conference.version += 1
    await schedule.until(lambda: schedule.jumps and not schedule.jumping)
    assert lists[0] == FRIDAY and set(lists) == set(DAYS)  # today alone, then the rest
    assert schedule.jumps == [(TEN_30, "landed")]  # one jump, through both renders
    _assert_asks(schedule, FRIDAY, TEN_30, scrolling.JUMP_MS)
    assert memory.jumped_on == FRIDAY  # so a tab return does not jump (SCHED-16)


@pytest.mark.parametrize(
    ("problem", "body"),
    [
        ("offline", "Connect to the internet and try again."),
        ("server", "The schedule couldn't be read. Try again in a few minutes."),
    ],
)
async def test_a_failed_first_fetch_says_so_and_offers_try_again(
    shown: Callable[[], Awaitable[Shown]],
    conference: Conference,
    monkeypatch: pytest.MonkeyPatch,
    problem: Problem,
    body: str,
) -> None:
    """A failed first fetch says why, and "Try again" starts a refresh."""
    refreshes: list[str] = []

    async def refresh(*_: Any, **__: Any) -> None:
        refreshes.append("refresh")

    # On the class: assigning to the store would notify, also when the patch is undone.
    monkeypatch.setattr(Conference, "refresh", refresh)
    conference.data, conference.problem = None, problem
    schedule = await shown()
    state = schedule.node("schedule.no_data")
    assert texts(state) == ["Can't load the schedule", body]
    (button,) = find(schedule.session, ft.FilledTonalButton)
    assert button.content == "Try again" and not button.disabled
    await schedule.session.dispatch_event(button._i, "click", None)
    await settle()
    assert refreshes == ["refresh"]


@pytest.mark.parametrize(("asked", "disabled"), [(False, False), (True, True)])
async def test_try_again_is_disabled_only_while_the_user_s_refresh_runs(
    shown: Callable[[], Awaitable[Shown]],
    conference: Conference,
    asked: bool,
    disabled: bool,
) -> None:
    """D-181: a quiet refresh leaves it enabled, so a tap joins it."""
    conference.data, conference.problem, conference.refreshing = None, "offline", True
    conference._asked = asked
    schedule = await shown()
    (button,) = find(schedule.session, ft.FilledTonalButton)
    assert button.disabled is disabled
    assert texts(schedule.node("schedule.no_data"))[0] == "Can't load the schedule"
