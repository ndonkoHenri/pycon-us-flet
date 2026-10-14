"""Tests for the Schedule screen: day tabs, slot lists, positions and Jump to now (#86, #89).

``Schedule`` renders in a real Flet session (``tests/sessions.py``) under the store
providers, so the memoised path (D-153), the two renders (D-156), the tabs' echo and the
jumps run as Flet runs them. Two seams stand in for the device: ``AppScaffold`` returns
the app bar's actions, the body and the "Now" button in a ``Column`` (the View and its
bar are ``tests/test_scaffold.py``'s), and ``ListView.scroll_to`` is recorded instead of
sent to a client, answering a keyed scroll with the scroll end Flutter would report (or with
nothing, for a list already in place) and reading ``self.page`` first, as Flet does, so a
list that has left the page raises Flet's error. ``Services.run_every`` is recorded, so a
test moves the minute tick by hand (``Shown.at``). The tests wait for what they expect to
happen (``Shown.until``), never for a fixed time, so a loaded host only makes them slower
(#237). Whether a jump lands, how the tabs read at 200 % and what TalkBack says are device
checks (#86, #89).
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

import flet as ft
import pytest
from flet.messaging.session import Session

from pycon_us import clock
from pycon_us.config import load_year
from pycon_us.core.timeline import NOW_KEY, now_place, timeline
from pycon_us.favorites import Favorites, FavoritesCtx
from pycon_us.prefs import Prefs, PrefsCtx
from pycon_us.screens import schedule as screen
from pycon_us.screens import schedule_days, schedule_now
from pycon_us.services import Services, ServicesCtx
from pycon_us.services.storage import THEME, Storage
from pycon_us.state import Conference, ConferenceCtx, Problem, ViewMemory
from pycon_us.ui import scrolling
from pycon_us.ui import session_rows as rows
from tests.fakes import (
    MemoryClipboard,
    MemoryHaptics,
    MemoryLauncher,
    MemoryPrefs,
    MemorySemantics,
)
from tests.feeds import processed
from tests.sessions import find, rendering, settle
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

TALK = "142"
"""A Saturday talk: "Python for Humans - …", 10:30-11:00 AM, in the 10:30 slot."""


@dataclass
class Shown:
    """A Flet session showing the Schedule, and what it did."""

    session: Session
    memory: ViewMemory
    prefs: Prefs
    favorites: Favorites
    conference: Conference
    scrolls: list[tuple[ft.ListView, dict[str, Any]]]
    navigated: list[str]
    strips: list[bool]
    storage: Storage
    retaps: list[Any] = field(default_factory=list)
    """Each render's re-tap action (``AppScaffold(on_retap=...)``)."""
    rows: list[str] = field(default_factory=list)
    """The session ids whose row bodies ran, in order."""
    slots: list[str] = field(default_factory=list)
    """The time labels of the slot bodies that ran, in order."""
    announced: list[str] = field(default_factory=list)
    """What the screen asked a screen reader to say (``announce_message``)."""
    leave: Callable[[], None] = lambda: None
    """Replace the Schedule with another screen, as a bottom-tab switch does (D-142)."""
    moves: bool = True
    """Whether a keyed scroll ends with a scroll end; False: the list is already there."""
    hold: asyncio.Event | None = None
    """When set to an event, each ``scroll_to`` waits for it before it returns."""
    ticks: list[Callable[[], object]] = field(default_factory=list)
    """The minute ticks' actions (``Services.run_every``), called by ``at``."""
    rerender: Callable[[], None] = lambda: None
    """Re-render the Schedule's parent, keeping the Schedule mounted, as Back does."""

    async def until(self, holds: Callable[[], object], *, timeout: float = 5.0) -> None:
        """Settle until ``holds()`` is true, or fail after ``timeout`` seconds (#237).

        A poll rather than a fixed wait, so a loaded host only makes it slower.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while not holds():
            assert loop.time() < deadline, "the screen did not get there in time"
            await asyncio.sleep(0.01)
        await settle()

    async def at(self, moment: datetime) -> None:
        """Move the clock to ``moment`` and run the minute ticks, as time passing."""
        clock.set_test_now(moment)
        for action in self.ticks:
            action()
        await settle()

    def keyed(self) -> list[str]:
        """The keys of the keyed scrolls so far: the jumps, in order."""
        return [
            kwargs["scroll_key"].value
            for _, kwargs in self.scrolls
            if kwargs.get("scroll_key") is not None
        ]

    @property
    def tabs(self) -> ft.Tabs:
        (tabs,) = find(self.session, ft.Tabs)
        return tabs

    def list_of(self, day: date) -> ft.ListView:
        found = find(
            self.session, ft.ListView, lambda c: c.key == f"day-{day.isoformat()}"
        )
        assert len(found) == 1, day
        return found[0]

    def node(self, identifier: str) -> ft.Semantics:
        found = find(self.session, ft.Semantics, lambda c: c.identifier == identifier)
        assert len(found) == 1, identifier
        return found[0]

    @property
    def fab(self) -> ft.FloatingActionButton | None:
        found = find(self.session, ft.FloatingActionButton)
        return found[0] if found else None

    async def change_day(self, day: date) -> None:
        """What Flutter sends when a tab or a swipe has settled on a day."""
        index = DAYS.index(day)
        self.session.apply_patch(self.tabs._i, {"selected_index": index})  # first
        await self.session.dispatch_event(self.tabs._i, "change", index)
        await settle()

    async def scroll_end(self, day: date, pixels: float) -> None:
        """What Flutter sends when a scroll of the day's list ends."""
        await self.session.dispatch_event(
            self.list_of(day)._i, "scroll", _scroll_end(pixels)
        )
        await settle()

    async def scroll_away(self, day: date = FRIDAY) -> None:
        """Scroll the day's list back to its top, far from where a jump landed."""
        await self.scroll_end(day, 0.0)

    async def press_now(self) -> None:
        assert self.fab is not None
        await self.session.dispatch_event(self.fab._i, "click", None)
        await settle()

    async def tap_star(self, session_id: str) -> None:
        (star,) = find(
            self.session,
            ft.Semantics,
            lambda c: c.identifier == f"schedule.favorite.{session_id}",
        )
        await self.session.dispatch_event(star.content._i, "click", None)  # pyright: ignore[reportOptionalMemberAccess]
        await settle()


def _scroll_end(pixels: float) -> dict[str, object]:
    return {
        "event_type": "end",
        "pixels": pixels,
        "min_scroll_extent": 0.0,
        "max_scroll_extent": 20_000.0,
        "viewport_dimension": 700.0,
    }


@pytest.fixture
def now() -> list[datetime | None]:
    """The frozen clock: set ``now[0]`` before the screen renders; None lifts it."""
    return [DURING]


@pytest.fixture
def memory() -> ViewMemory:
    return ViewMemory()


@pytest.fixture
def conference() -> Conference:
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
    opened: list[Any] = []
    # Generous: the stand-in reports a scroll end at once, so a passing test never waits
    # this long, and a loaded host cannot make a jump ask twice (#237). A test of a list
    # that never moves sets its own.
    monkeypatch.setattr(scrolling, "LANDING_S", 5.0)
    monkeypatch.setattr(screen, "SETTLE_S", 5.0)

    async def show(*, moves: bool = True, **settings: Any) -> Shown:
        """Render the Schedule with these ``Prefs``; ``moves`` as ``Shown.moves``."""
        clock.set_test_now(now[0])
        storage = Storage(prefs=MemoryPrefs(), directory=tmp_path, year=2026)
        semantics = MemorySemantics()
        svc = Services(
            year=YEAR,
            storage=storage,
            memory=memory,
            semantics=semantics,
            haptics=MemoryHaptics(),
            launcher=MemoryLauncher(),
            clipboard=MemoryClipboard(),
        )
        favorites, prefs = Favorites(), Prefs(loaded=True, **settings)
        await favorites.load(storage)
        scrolls: list[tuple[ft.ListView, dict[str, Any]]] = []
        navigated: list[str] = []
        strips: list[bool] = []
        result = Shown(
            cast(Session, None),
            memory,
            prefs,
            favorites,
            conference,
            scrolls,
            navigated,
            strips,
            storage,
            announced=semantics.announced,
            moves=moves,
        )

        async def scroll_to(self: ft.ListView, **kwargs: Any) -> None:
            # Flet's _invoke_method reads it first: a list off the page raises.
            session = cast(Session, self.page.session)  # pyright: ignore[reportOptionalMemberAccess]
            scrolls.append((self, kwargs))
            if result.hold is not None:
                await result.hold.wait()
            if kwargs.get("scroll_key") is not None and result.moves:  # where it ended
                asyncio.get_running_loop().call_soon(
                    lambda: asyncio.ensure_future(
                        session.dispatch_event(self._i, "scroll", _scroll_end(4000.0))
                    )
                )

        @ft.component
        def Strip(*, auto_refresh: bool = False) -> ft.Control:
            strips.append(auto_refresh)
            return ft.Text("strip")

        def scaffold(**kwargs: Any) -> ft.Control:
            result.retaps.append(kwargs.get("on_retap"))
            fab = kwargs.get("fab")
            actions = kwargs.get("actions") or []  # Search, and the filter (#87)
            return ft.Column(
                [*actions, kwargs["body"], *([fab] if fab else [])], expand=True
            )

        def counted_phrase(*args: Any, **kwargs: Any) -> str:
            result.rows.append(cast(Any, args[-1]).session.id)
            return phrase(*args, **kwargs)

        def counted_slot(label: str, slot_rows: Any, *, above: bool) -> ft.Control:
            result.slots.append(label)
            return layout(label, slot_rows, above=above)

        async def run_every(_: Services, seconds: float, action: Any) -> None:
            result.ticks.append(action)

        phrase, layout = rows.spoken_phrase, schedule_days.slot_layout
        monkeypatch.setattr(ft.ListView, "scroll_to", scroll_to)
        monkeypatch.setattr(Services, "run_every", run_every)
        monkeypatch.setattr(screen, "StatusStrip", Strip)
        monkeypatch.setattr(screen, "AppScaffold", scaffold)
        monkeypatch.setattr(rows, "spoken_phrase", counted_phrase)
        monkeypatch.setattr(schedule_days, "slot_layout", counted_slot)

        @ft.component
        def Elsewhere() -> ft.Control:
            return ft.Text("another tab")

        @ft.component
        def Root() -> ft.Control:
            here, set_here = ft.use_state(True)
            _, set_renders = ft.use_state(0)
            result.leave = lambda: set_here(False)
            result.rerender = lambda: set_renders(lambda n: n + 1)
            body = screen.Schedule if here else Elsewhere
            return ServicesCtx(
                svc,
                lambda: ConferenceCtx(
                    conference,
                    lambda: PrefsCtx(prefs, lambda: FavoritesCtx(favorites, body)),
                ),
            )

        context = rendering(Root)
        result.session = await context.__aenter__()
        opened.append(context)
        result.session.page.navigate = navigated.append  # pyright: ignore[reportAttributeAccessIssue]
        await settle()
        return result

    yield cast(Callable[[], Awaitable[Shown]], show)
    for context in opened:
        await context.__aexit__(None, None, None)
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
    schedule = await shown()
    assert schedule.tabs.selected_index == DAYS.index(FRIDAY)


async def test_the_first_day_is_selected_outside_the_conference(
    shown: Callable[[], Awaitable[Shown]], now: list[datetime]
) -> None:
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


async def test_a_remembered_day_wins_over_today(
    shown: Callable[[], Awaitable[Shown]], memory: ViewMemory
) -> None:
    memory.schedule_day = SATURDAY
    schedule = await shown()
    assert schedule.tabs.selected_index == DAYS.index(SATURDAY)


def _tab_text(schedule: Shown, index: int) -> str:
    node = schedule.node(f"schedule.day_tab.{index}")
    (text,) = find(schedule.session, ft.Text, lambda c: inside(c, node))
    return str(text.value)


def _spoken(schedule: Shown, index: int) -> str:
    node = schedule.node(f"schedule.day_tab.{index}")
    (text,) = find(schedule.session, ft.Text, lambda c: inside(c, node))
    return str(text.semantics_label)


def _has_dot(schedule: Shown, node: ft.Semantics) -> bool:
    return bool(find(schedule.session, ft.Container, lambda c: inside(c, node)))


async def test_a_day_change_is_remembered_and_its_echo_changes_nothing(
    shown: Callable[[], Awaitable[Shown]], memory: ViewMemory
) -> None:
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
    # A jump puts the slot's time under the tab bar, not a second line (ux.md §5.2);
    # the first slot has none, and the now line stands for the next one's (D-204).
    dividers = find(
        schedule.session, ft.Divider, lambda c: c.visible and inside(c, friday)
    )
    assert len(dividers) == len(items) - 2
    assert not any(inside(d, item) for d in dividers for item in items)
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
    assert all(isinstance(c.content, ft.Row) for c in slots())  # the gutter
    schedule.prefs.time_above = True  # what GutterProbe measures at that size
    await settle()
    assert {str(cast(ft.ScrollKey, c.key).value) for c in slots()} == beside
    for slot in slots():
        column = slot.content
        assert isinstance(column, ft.Column)
        heading = column.controls[0]
        assert isinstance(heading, ft.Semantics) and heading.header
    friday = schedule.list_of(FRIDAY)
    assert not find(  # no gutter left in the day
        schedule.session, ft.Stack, lambda c: inside(c, friday)
    )


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
    schedule = await shown()
    state = schedule.node("schedule.sprint_day.2026-05-18")
    assert texts(state)[0] == "Monday is a sprint day"
    button = only(schedule.list_of(MONDAY), ft.FilledTonalButton)
    assert button.content == "See the sprints"
    await schedule.session.dispatch_event(button._i, "click", None)
    await settle()
    assert schedule.navigated == ["/more/sprints"]


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
    schedule = await shown()
    place = now_place(timeline(processed(2026), FRIDAY, ("Open Space",)), DURING)
    ((target, kwargs),) = schedule.scrolls
    assert target is schedule.list_of(FRIDAY)
    assert (
        kwargs["scroll_key"].value == place.target == "slot-2026-05-15T10:30:00-07:00"
    )
    assert kwargs["duration"] == scrolling.JUMP_MS
    assert memory.jumped_on == FRIDAY

    again = await shown()  # a tab return or a new session: never a second jump
    assert again.scrolls == [] or "scroll_key" not in again.scrolls[0][1]


async def test_under_reduced_motion_the_jump_is_instant(
    shown: Callable[..., Awaitable[Shown]],
) -> None:
    schedule = await shown(reduce_motion=True)
    assert schedule.scrolls  # a busy host may need a second ask: each one instant
    assert {kwargs["duration"] for _, kwargs in schedule.scrolls} == {0}  # D-34


async def test_outside_the_conference_nothing_jumps_and_there_is_no_now_button(
    shown: Callable[[], Awaitable[Shown]], now: list[datetime]
) -> None:
    now[0] = BEFORE
    schedule = await shown()
    assert schedule.scrolls == []
    assert schedule.fab is None


async def test_on_a_sprint_day_there_is_no_now_button(
    shown: Callable[[], Awaitable[Shown]], now: list[datetime]
) -> None:
    now[0] = datetime(2026, 5, 18, 11, 0, tzinfo=PACIFIC)
    schedule = await shown()
    assert schedule.tabs.selected_index == DAYS.index(MONDAY)
    assert schedule.fab is None
    assert schedule.scrolls == []


async def test_now_on_today_jumps_again(
    shown: Callable[[], Awaitable[Shown]],
) -> None:
    schedule = await shown()
    assert schedule.fab is None  # the jump put the slot on screen
    await schedule.scroll_away()
    assert schedule.fab is not None
    assert texts(cast(ft.Control, schedule.fab.content)) == ["Now"]
    schedule.scrolls.clear()
    await schedule.press_now()
    ((target, kwargs),) = schedule.scrolls
    assert target is schedule.list_of(FRIDAY)
    assert "scroll_key" in kwargs


async def test_now_from_another_day_switches_first_then_jumps_once_it_settled(
    shown: Callable[[], Awaitable[Shown]], memory: ViewMemory
) -> None:
    """D-155's second flow: the jump waits for the tabs to report the switch."""
    memory.schedule_day, memory.jumped_on = SATURDAY, FRIDAY
    schedule = await shown()
    assert texts(
        cast(ft.Control, cast(ft.FloatingActionButton, schedule.fab).content)
    ) == ["Today"]
    schedule.scrolls.clear()
    await schedule.press_now()
    assert schedule.tabs.selected_index == DAYS.index(FRIDAY)
    assert memory.schedule_day == FRIDAY
    assert schedule.scrolls == []  # not before the switch has slid in
    await schedule.change_day(FRIDAY)  # Flutter's echo of the switch
    await schedule.until(lambda: schedule.scrolls)
    ((target, kwargs),) = schedule.scrolls
    assert target is schedule.list_of(FRIDAY)
    assert kwargs["scroll_key"].value == "slot-2026-05-15T10:30:00-07:00"


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
    """A tap's jump runs in its handler, which no unmount cancels: it stops at the
    first ask that finds the list off the page, and no error reaches the next screen."""
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
        await asyncio.wait_for(tap, 5)
    assert len(schedule.scrolls) == 1  # the second ask found the list gone
    assert schedule.scrolls[0][0] is friday
    assert "the list left the page" in caplog.text
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


async def test_a_now_tap_on_a_list_already_in_place_is_still_said(
    shown: Callable[..., Awaitable[Shown]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """No scroll, so no scroll end: today's list builds every slot (D-154), so a list
    that never moves is on the slot already, and the user still hears where."""
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
    """F13: Flutter reports no announcements on Android, so nothing is said there."""
    schedule = await shown(**settings)
    await schedule.scroll_away()
    schedule.scrolls.clear()
    await schedule.press_now()
    assert schedule.scrolls and schedule.announced == []


# ------------------------------------------------------------------ the jump's policy (#89)


def friday_at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 5, 15, hour, minute, tzinfo=PACIFIC)


async def test_swiping_to_today_after_opening_on_another_day_jumps_once(
    shown: Callable[[], Awaitable[Shown]], memory: ViewMemory
) -> None:
    """D-204: today's first display jumps, wherever the Schedule opened."""
    memory.schedule_day = SATURDAY
    schedule = await shown()
    assert schedule.keyed() == []  # Saturday is not today
    await schedule.change_day(FRIDAY)
    assert schedule.keyed() == ["slot-2026-05-15T10:30:00-07:00"]
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
    await schedule.until(lambda: schedule.scrolls)
    await settle()
    assert schedule.keyed() == ["slot-2026-05-15T10:30:00-07:00"]  # once, not twice
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
    schedule = await shown()
    schedule.scrolls.clear()
    await schedule.at(friday_at(10, 41))
    await schedule.at(friday_at(11, 0))  # the 11:00 AM slot starts
    assert schedule.scrolls == []


async def test_each_new_today_jumps_once_by_itself(
    shown: Callable[[], Awaitable[Shown]], memory: ViewMemory
) -> None:
    """D-204: a process that lives across days jumps on each conference day's first
    display, as after a fake-clock change; never twice the same day."""
    memory.jumped_on = THURSDAY
    schedule = await shown()
    assert schedule.keyed() == ["slot-2026-05-15T10:30:00-07:00"]
    again = await shown()  # a tab return the same day
    assert again.keyed() == []


async def test_midnight_moves_today_s_dot_and_button_never_the_day_shown(
    shown: Callable[[], Awaitable[Shown]], now: list[datetime | None]
) -> None:
    """D-204: the day picked at the first display stays; the new today waits for the
    user, and jumps on its first display."""
    now[0] = friday_at(23, 58)
    schedule = await shown()
    assert schedule.tabs.selected_index == DAYS.index(FRIDAY)
    await schedule.scroll_away()
    schedule.scrolls.clear()
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
    assert schedule.keyed() == [NOW_KEY]  # before the day's first slot: the line


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
    """A list already in place sends no scroll end, so the jump answers only after its
    tries: the button must not show for those seconds and then vanish (D-204)."""
    monkeypatch.setattr(scrolling, "LANDING_S", 0.2)
    with caplog.at_level(logging.INFO):
        schedule = await shown(moves=False, reduce_motion=True)
        assert schedule.fab is None  # the jump is on its way
        await schedule.until(lambda: "did not move" in caplog.text)
    assert len(schedule.scrolls) == scrolling.JUMP_TRIES
    assert schedule.fab is None  # "still": the place is in view
    await schedule.scroll_end(FRIDAY, 3000.0)
    assert schedule.fab is not None  # the landing was kept, so a scroll away counts


async def test_a_screen_reader_keeps_the_button_so_a_tap_never_drops_its_focus(
    shown: Callable[..., Awaitable[Shown]],
) -> None:
    """ux.md §5.2 item 5: a control that hides under the focus sends the reader
    elsewhere, over the announcement of where the list went."""
    schedule = await shown(screen_reader=True, announcements=True)
    assert schedule.fab is not None  # after the first display's jump too
    await schedule.press_now()
    assert schedule.announced == ["Friday, May 15, 10:30 AM"]
    assert schedule.fab is not None


async def test_a_tap_after_a_slot_started_since_the_tick_goes_there_and_hides(
    shown: Callable[[], Awaitable[Shown]],
) -> None:
    """The tap reads the clock, and so does the render its landing causes: the line
    moves with the jump and the button hides at once, not at the next tick."""
    schedule = await shown()
    await schedule.scroll_away()
    clock.set_test_now(friday_at(11, 0))  # the 11:00 AM slot starts before the tick
    schedule.scrolls.clear()
    await schedule.press_now()
    assert schedule.keyed() == ["slot-2026-05-15T11:00:00-07:00"]
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


async def test_another_day_always_offers_today(
    shown: Callable[[], Awaitable[Shown]],
) -> None:
    schedule = await shown()
    assert schedule.fab is None
    await schedule.change_day(SATURDAY)
    assert texts(
        cast(ft.Control, cast(ft.FloatingActionButton, schedule.fab).content)
    ) == ["Today"]


# ------------------------------------------------------------------ the now line (#89)


def _now_line(schedule: Shown) -> ft.Semantics:
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
    keys = _list_items(schedule, FRIDAY)
    line = keys.index(NOW_KEY)
    assert keys[line - 1] == "slot-2026-05-15T10:30:00-07:00"
    assert keys[line + 1] == "slot-2026-05-15T11:00:00-07:00"
    node = _now_line(schedule)
    assert node.label == "Current time 10:40 AM"
    assert node.exclude_semantics and not node.live_region
    assert texts(node) == ["Now · 10:40 AM"]
    (bar,) = find(schedule.session, ft.Container, lambda c: inside(c, node))
    assert (bar.height, bar.bgcolor) == (schedule_now.NOW_LINE, ft.Colors.PRIMARY)
    assert NOW_KEY not in _list_items(schedule, SATURDAY)  # today's list only


async def test_a_minute_re_renders_the_line_alone_and_a_slot_start_moves_it(
    shown: Callable[[], Awaitable[Shown]],
) -> None:
    """D-153: no row re-renders; a move re-renders only the two slots whose divider
    the line takes or gives back."""
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
    """D-204: at 2:35 PM nothing is on; the line sits above 2:45 PM's slot, and a
    screen reader hears the time, as the line itself says it."""
    now[0] = friday_at(14, 35)
    schedule = await shown(screen_reader=True, announcements=True)
    assert schedule.keyed() == [NOW_KEY]
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
    assert schedule.keyed() == [NOW_KEY]
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
    await schedule.until(lambda: schedule.scrolls)
    assert lists[0] == FRIDAY and set(lists) == set(DAYS)  # today alone, then the rest
    ((target, kwargs),) = schedule.scrolls
    assert target is schedule.list_of(FRIDAY)
    assert kwargs["scroll_key"].value == "slot-2026-05-15T10:30:00-07:00"
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
