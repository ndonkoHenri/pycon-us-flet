"""Tests for the Schedule screen: day tabs, slot lists, positions and Jump to now (#86).

``Schedule`` renders in a real Flet session (``tests/sessions.py``) under the store
providers, so the memoised path (D-153), the two renders (D-156), the tabs' echo and the
jumps run as Flet runs them. Two seams stand in for the device: ``AppScaffold`` returns
the body and the "Now" button in a ``Column`` (the View and its bar are
``tests/test_scaffold.py``'s), and ``ListView.scroll_to`` is recorded instead of sent to
a client, answering a keyed scroll with the scroll end Flutter would report. Whether a
jump lands, how the tabs read at 200 % and what TalkBack says are device checks (#86).
"""

import asyncio
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
from pycon_us.core.timeline import current_slot_key, timeline
from pycon_us.favorites import Favorites, FavoritesCtx
from pycon_us.prefs import Prefs, PrefsCtx
from pycon_us.screens import schedule as screen
from pycon_us.screens import schedule_days
from pycon_us.services import Services, ServicesCtx
from pycon_us.services.storage import Storage
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
    """The gutter labels of the slot bodies that ran, in order."""

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
def now() -> list[datetime]:
    """The frozen clock: set ``now[0]`` before the screen renders."""
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
    now: list[datetime],
    memory: ViewMemory,
    conference: Conference,
) -> AsyncIterator[Callable[[], Awaitable[Shown]]]:
    """Return a function that renders the Schedule; every render is closed at the end."""
    opened: list[Any] = []
    monkeypatch.setattr(scrolling, "LANDING_S", 0.2)
    monkeypatch.setattr(screen, "SETTLE_S", 0.05)

    async def show(**settings: Any) -> Shown:
        clock.set_test_now(now[0])
        storage = Storage(prefs=MemoryPrefs(), directory=tmp_path, year=2026)
        svc = Services(
            year=YEAR,
            storage=storage,
            memory=memory,
            semantics=MemorySemantics(),
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
        )

        async def scroll_to(self: ft.ListView, **kwargs: Any) -> None:
            scrolls.append((self, kwargs))
            if kwargs.get("scroll_key") is not None:  # Flutter reports where it ended
                session = cast(Session, self.page.session)  # pyright: ignore[reportOptionalMemberAccess]
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
            return ft.Column([kwargs["body"], *([fab] if fab else [])], expand=True)

        def counted_phrase(*args: Any) -> str:
            result.rows.append(cast(Any, args[-1]).session.id)
            return phrase(*args)

        def counted_gutter(label: str) -> ft.Control:
            result.slots.append(label)
            return gutter(label)

        phrase, gutter = rows.spoken_phrase, schedule_days.TimeGutter
        monkeypatch.setattr(ft.ListView, "scroll_to", scroll_to)
        monkeypatch.setattr(screen, "StatusStrip", Strip)
        monkeypatch.setattr(screen, "AppScaffold", scaffold)
        monkeypatch.setattr(rows, "spoken_phrase", counted_phrase)
        monkeypatch.setattr(schedule_days, "TimeGutter", counted_gutter)

        @ft.component
        def Root() -> ft.Control:
            return ServicesCtx(
                svc,
                lambda: ConferenceCtx(
                    conference,
                    lambda: PrefsCtx(
                        prefs, lambda: FavoritesCtx(favorites, screen.Schedule)
                    ),
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
    assert _spoken(schedule, 2) == "Friday, May 15, today"  # then "Tab 3 of 7"
    assert friday.label is None  # merged into the tab's node with the identifier
    assert _has_dot(schedule, friday)  # today's mark
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
        lambda c: isinstance(c.key, ft.ScrollKey) and inside(c, friday),
    )
    keys = sorted(str(cast(ft.ScrollKey, item.key).value) for item in items)
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
    memory.jumped_to_now = True  # the jump already ran in this process
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
    key = current_slot_key(timeline(processed(2026), FRIDAY, ("Open Space",)), DURING)
    ((target, kwargs),) = schedule.scrolls
    assert target is schedule.list_of(FRIDAY)
    assert kwargs["scroll_key"].value == key == "slot-2026-05-15T10:30:00-07:00"
    assert kwargs["duration"] == scrolling.JUMP_MS
    assert memory.jumped_to_now

    again = await shown()  # a tab return or a new session: never a second jump
    assert again.scrolls == [] or "scroll_key" not in again.scrolls[0][1]


async def test_under_reduced_motion_the_jump_is_instant(
    shown: Callable[..., Awaitable[Shown]],
) -> None:
    schedule = await shown(reduce_motion=True)
    ((_, kwargs),) = schedule.scrolls
    assert kwargs["duration"] == 0  # D-34, D-173


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
    memory.schedule_day, memory.jumped_to_now = SATURDAY, True
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
    await asyncio.sleep(0.02)
    await settle()
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
