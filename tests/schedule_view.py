"""The Schedule's harness, times and shared helpers, for its test modules (#623).

`test_schedule.py` (the day tabs, the now line and the states without data),
`test_schedule_lists.py` (the day lists), `test_schedule_jump.py` (positions and
Jump to now) and `test_schedule_button.py` (the jump's policy and the "Now" button)
share it, as do `test_schedule_filter.py`, `test_schedule_place.py`,
`test_schedule_place_turns.py` and `test_schedule_refilter.py`. A module takes the
fixtures by assigning them to its own names, as `docs/testing-and-quality.md` §3.1
says.

`Schedule` renders in a real Flet session under the store providers
(`tests/harness.py`'s `showing()`), so the memoised path (D-153), the two renders
(D-156), the tabs' echo and the jumps run as Flet runs them. Two seams stand in for the
device: `AppScaffold` is the harness's `Column` of the app bar's actions, the body
and the "Now" button (the View and its bar are tested with `tests/chrome.py`), and
`ListView.scroll_to` is recorded instead of sent to a client, answering a keyed scroll
with the scroll end Flutter would report (or with nothing, for a list already in place)
and reading `self.page` first, as Flet does, so a list that has left the page raises
Flet's error. `Services.run_every` is recorded, so a test moves the minute tick by
hand (`Shown.at`). Each jump is recorded too (`Shown.jumps`): a jump may ask for its
scroll more than once (D-155), so the tests check which jumps ran and where they went,
not how many scrolls they asked for. The tests wait for what they expect to happen
(`Shown.until`, and every render returns only once no jump it started is still on its
way), never for a fixed time, so a loaded host only makes them slower (#237).
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from functools import partial
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

import flet as ft
import pytest
from flet.messaging.session import Session

from pycon_us import clock
from pycon_us.config import load_year
from pycon_us.memory import ViewMemory
from pycon_us.prefs import Prefs
from pycon_us.screens import schedule as screen
from pycon_us.screens import schedule_days, schedule_head
from pycon_us.services import Services
from pycon_us.state import Conference
from pycon_us.theme import Tokens
from pycon_us.ui import scrolling, status_strip
from tests import harness
from tests.fakes import MemorySemantics
from tests.feeds import processed
from tests.sessions import find

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
"""Friday's 10:30 AM slot, on at `DURING`: where a jump to now goes then."""

TALK = "142"
"""A Saturday talk: "Python for Humans - …", 10:30-11:00 AM, in the 10:30 slot."""


@dataclass
class Shown(harness.Shown):
    """The harness's `Shown` on the Schedule: its scrolls, jumps and minute ticks.

    It is `tests/sessions.py`'s, with what the Schedule's stand-ins record.
    """

    scrolls: list[tuple[ft.ListView, dict[str, Any]]] = field(default_factory=list)
    """Each `ListView.scroll_to` asked: the list and its arguments."""
    strips: list[bool] = field(default_factory=list)
    """Each `use_strip()`'s `auto_refresh`, as the screen asked for it."""
    slots: list[str] = field(default_factory=list)
    """The time labels of the slot bodies that ran, in order."""
    leave: Callable[[], None] = lambda: None
    """Replace the Schedule with another screen, as a bottom-tab switch does (D-142)."""
    moves: bool = True
    """Whether a scroll ends with a scroll end, a keyed one at 4,000 dp and one to an
    offset there; False: the list is already there."""
    late: bool = False
    """Whether the first keyed scroll's end comes too late, as on a loaded host (#237)."""
    hold: asyncio.Event | None = None
    """When set to an event, each `scroll_to` waits for it before it returns."""
    ticks: list[Callable[[], object]] = field(default_factory=list)
    """The minute ticks' actions (`Services.run_every`), called by `at`."""
    rerender: Callable[[], None] = lambda: None
    """Re-render the Schedule's parent, keeping the Schedule mounted, as Back does."""
    jumps: list[tuple[str, scrolling.Jump]] = field(default_factory=list)
    """Each jump that ended (`jump_to_key`): its target key and how it ended."""
    jumping: int = 0
    """How many jumps are on their way."""

    @property
    def announced(self) -> list[str]:
        """What the screen asked a screen reader to say (`announce_message`)."""
        return cast(MemorySemantics, self.services.semantics).announced

    async def until(
        self, holds: Callable[[], object], *, timeout: float = 30.0
    ) -> None:
        """Settle until `holds()` is true, or fail after `timeout` seconds (#237).

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
        """Move the clock to `moment` and run the minute ticks, as time passing."""
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
        """The screen's one `Tabs`."""
        (tabs,) = self.find(ft.Tabs)
        return tabs

    def list_of(self, day: date) -> ft.ListView:
        """The one mounted `ListView` of `day`."""
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

    async def drag(self, day: date = FRIDAY) -> None:
        """What Flutter sends when the user's finger starts moving the day's list."""
        await self.event(
            self.list_of(day),
            "scroll",
            {**_scroll_end(0.0), "event_type": "user", "direction": "reverse"},
        )

    async def scroll_away(self, day: date = FRIDAY) -> None:
        """Scroll the day's list back to its top, far from where a jump landed."""
        await self.scroll_end(day, 0.0)

    async def press_now(self) -> None:
        """Tap the "Now" or "Today" button, which must be showing."""
        assert self.fab is not None
        await self.click(self.fab)

    async def tap_star(self, session_id: str) -> None:
        """Tap the star on `session_id`'s row."""
        star = self.node(f"schedule.favorite.{session_id}").content
        assert star is not None
        await self.click(star)


def _scroll_end(pixels: float) -> dict[str, object]:
    """A scroll end event's data at `pixels`, as Flutter sends it."""
    return {
        "event_type": "end",
        "pixels": pixels,
        "min_scroll_extent": 0.0,
        "max_scroll_extent": 20_000.0,
        "viewport_dimension": 700.0,
    }


def _assert_asks(schedule: Shown, day: date, key: str, duration: int) -> None:
    """Assert that every keyed scroll ask so far went to `key` on the day's list.

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
    """The frozen clock: set `now[0]` before the screen renders; None lifts it."""
    return [DURING]


@pytest.fixture
def memory() -> ViewMemory:
    """A fresh `ViewMemory`, which a test may fill before the render."""
    return ViewMemory()


@pytest.fixture
def conference() -> Conference:
    """The recorded 2026 feed as the bundled `Conference`."""
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
        result = harness.current(Shown)
        result.scrolls.append((self, kwargs))
        if result.hold is not None:
            await result.hold.wait()
        if not result.moves:
            return
        if kwargs.get("scroll_key") is None:  # an offset jump ends where it was asked
            pixels = float(kwargs["offset"])
            asyncio.get_running_loop().call_soon(
                lambda: asyncio.ensure_future(
                    session.dispatch_event(self._i, "scroll", _scroll_end(pixels))
                )
            )
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

    def recorded_strip(*, auto_refresh: bool = False) -> status_strip.Strip:
        harness.current(Shown).strips.append(auto_refresh)
        # The real strip, but a minute tick (`Shown.at`) starts no feed refresh.
        return status_strip.use_strip(auto_refresh=False)

    def strip_stand_in(strip: status_strip.Strip, tokens: Tokens) -> ft.Control:
        return ft.Text("strip")

    def counted_slot(label: str, slot_rows: Any, *, above: bool) -> ft.Control:
        harness.current(Shown).slots.append(label)
        return layout(label, slot_rows, above=above)

    async def run_every(_: Services, seconds: float, action: Any) -> None:
        harness.current(Shown).ticks.append(action)

    async def recorded_jump(
        list_ref: ft.Ref[ft.ListView], key: str, **kwargs: Any
    ) -> scrolling.Jump:
        result = harness.current(Shown)
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
    monkeypatch.setattr(screen, "use_strip", recorded_strip)
    monkeypatch.setattr(screen, "strip_view", strip_stand_in)
    monkeypatch.setattr(schedule_head, "strip_view", strip_stand_in)
    monkeypatch.setattr(schedule_days, "slot_layout", counted_slot)

    @ft.component
    def Elsewhere() -> ft.Control:
        return ft.Text("another tab")

    @ft.component
    def Opened() -> ft.Control:
        here, set_here = ft.use_state(True)
        _, set_renders = ft.use_state(0)
        result = harness.current(Shown)
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
                """Render the Schedule with these `Prefs` settings.

                `moves`, `late` and `hold` are as in `Shown`.

                With `wait` it returns once no jump is on its way, so the next step
                never meets one (#237). The first display's jump, when there is one, has
                ended by then: `settle()` has already started it, since the effect's
                chain up to the jump is pure asyncio here (`MemoryPrefs` answers
                inline), with no timer or thread hop. A test that expects that jump also
                checks `jumps` right after.
                """
                clock.set_test_now(now[0])
                result = await stack.enter_async_context(
                    harness.showing(
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


def _spoken(schedule: Shown, index: int) -> str:
    """What a screen reader says for day tab `index`."""
    node = schedule.node(f"schedule.day_tab.{index}")
    (text,) = find(schedule.session, ft.Text, lambda c: inside(c, node))
    return str(text.semantics_label)


def inside(control: ft.BaseControl, ancestor: ft.BaseControl) -> bool:
    """Whether `control` is mounted under `ancestor`, components included."""
    node = control.parent
    while node is not None:
        if node is ancestor:
            return True
        node = node.parent
    return False


def friday_at(hour: int, minute: int = 0) -> datetime:
    """Friday, May 15 2026 at `hour`:`minute`, Pacific Time."""
    return datetime(2026, 5, 15, hour, minute, tzinfo=PACIFIC)


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
