"""My schedule's saved sessions, times and harness, for its three test modules (#312).

``test_my_schedule.py`` (the agenda and its overlaps), ``test_my_schedule_ended.py``
(what has ended, removal and Undo) and ``test_my_schedule_states.py`` (the states and
the dropped sessions' notice) run the screen in a real Flet session
(``tests/harness.py``'s ``showing()``), as the rows do in ``test_session_rows.py``: the
store providers above it, a star tap as a dispatched click, Flet's own scheduler
re-rendering what changed. ``AppScaffold`` is the harness's stand-in and the status
strip a placeholder (both have their own tests), and the minute tick is a hook the test
moves by hand, with ``clock.now()`` fixed. A module takes the fixtures by assigning them
to its own names, as ``docs/testing-and-quality.md`` §3.1 says.
"""

from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import flet as ft
import pytest

from pycon_us import clock
from pycon_us.change_log import ChangeLog
from pycon_us.config import load_year
from pycon_us.core.change_batches import Batch
from pycon_us.favorites import Favorites
from pycon_us.prefs import Prefs
from pycon_us.screens import my_schedule as screen
from pycon_us.screens.my_schedule import MySchedule
from pycon_us.state import Conference
from pycon_us.ui import states
from tests import harness
from tests.fakes import MemoryPrefs
from tests.feeds import processed
from tests.folds import Fold, as_fold, fold_named

YEAR = load_year(2026)
ZONE = YEAR.conference.zone
FAVORITES = "pycon.2026.favorites"

# Wednesday, May 13: two tutorials at 9:00 that overlap, one after lunch.
MCP, DECORATORS, RAG = "2", "19", "188"
# Thursday, May 14: a 9:00-12:30 tutorial and two workshops inside it.
NOTEBOOKS, CHEESE_SHOP, INFERENCE = "106", "111", "22"
# Friday, May 15: the welcome at 9:00 and the keynote at 9:45, back to back but one.
WELCOME, KEYNOTE = "151", "153"
# Saturday, May 16: a talk alone in its slot.
TALK = "142"
# Sunday, May 17: an open space, which the Schedule hides by default (D-20).
OPEN_SPACE = "9028"

SAVED = (
    MCP,
    DECORATORS,
    RAG,
    NOTEBOOKS,
    CHEESE_SHOP,
    INFERENCE,
    WELCOME,
    KEYNOTE,
    TALK,
    OPEN_SPACE,
)

BEFORE = datetime(2026, 5, 1, 12, 0, tzinfo=ZONE)
"""Before the conference: nothing has ended."""

THURSDAY = datetime(2026, 5, 14, 10, 45, tzinfo=ZONE)
"""Wednesday has ended; on Thursday the 9:30 workshop has, the tutorial has not."""

LAST_EVENING = datetime(2026, 5, 17, 20, 0, tzinfo=ZONE)
"""Sunday evening, the conference's last day: everything saved has ended."""

AFTER = datetime(2026, 6, 1, 12, 0, tzinfo=ZONE)
"""After the conference: everything has ended."""

NBSP = "\N{NO-BREAK SPACE}"


def name(session_id: str) -> str:
    """The name of session ``session_id`` in the 2026 feed."""
    return processed(2026).sessions[session_id].name


@dataclass
class Shown(harness.Shown):
    """The harness's ``Shown`` (``tests/harness.py``) on My schedule."""

    strips: list[dict[str, Any]] = field(default_factory=list)
    """The arguments of each ``StatusStrip`` the screen placed."""
    slots: list[str] = field(default_factory=list)
    """The slots day sections built, by gutter label: a day body builds each of its."""
    minutes: list[Callable[[int], None]] = field(default_factory=list)
    """The minute hook's setter on each render: ``tick()`` calls the last one."""

    @property
    def prefs_service(self) -> MemoryPrefs:
        """The ``MemoryPrefs`` behind the session's storage."""
        return cast(MemoryPrefs, self.storage.prefs)

    @property
    def controls(self) -> list[ft.Control]:
        """Every mounted control, in the session's index."""
        return self.find(ft.Control)

    def tick(self) -> None:
        """A minute passing: the minute hook's state changes, so the screen re-renders."""
        self.minutes[-1](len(self.minutes))

    def phrase(self, session_id: str) -> str:
        """The spoken phrase of the row of ``session_id``: its node's label."""
        return str(self.node(f"my_schedule.session.{session_id}").label)

    def shown(self) -> list[str]:
        """The rows on screen, in reading order, outside the folded tiles."""
        root = self.root()
        return [
            str(c.identifier).removeprefix("my_schedule.session.")
            for c in _walk(root)
            if isinstance(c, ft.Semantics)
            and str(c.identifier).startswith("my_schedule.session.")
        ]

    def headers(self) -> list[str]:
        """The day headers outside the folds, in reading order (not the gutters)."""
        return [
            str(c.content.content.value)
            for c in _walk(self.root())
            if isinstance(c, ft.Semantics)
            and c.header
            and isinstance(c.content, ft.Container)
            and isinstance(c.content.content, ft.Text)
        ]

    def fold(self, identifier: str) -> Fold:
        """The ``FoldTile`` whose header is ``my_schedule.<identifier>``."""
        return fold_named(self.controls, f"my_schedule.{identifier}")

    def folded(self, identifier: str) -> list[str]:
        """The rows inside a fold, shown or not, in reading order."""
        return [
            str(c.identifier).removeprefix("my_schedule.session.")
            for c in _walk(self.fold(identifier).controls)
            if isinstance(c, ft.Semantics)
            and str(c.identifier).startswith("my_schedule.session.")
        ]

    def root(self) -> ft.ListView:
        """The screen's one ``ListView``."""
        (found,) = self.find(ft.ListView)
        return found

    async def tap_star(self, session_id: str) -> None:
        """Click the star of the row of ``session_id``."""
        star = self.node(f"my_schedule.favorite.{session_id}").content
        assert isinstance(star, ft.IconButton)
        await self.click(star)

    async def toggle_fold(self, identifier: str, expanded: bool) -> None:
        """Open or close the fold ``identifier`` with a tap on its header."""
        found = self.fold(identifier)
        assert found.expanded is not expanded
        await self.click(found.header)


_PARTS = ("content", "leading", "title", "subtitle", "trailing")


def _walk(node: Any, *, folds: bool = False) -> Iterator[ft.Control]:
    """Yield the controls under ``node`` in reading order, through components' bodies.

    A component's rendered body is its ``_b`` (Flet's ``Component``, at the D-81
    pin). A fold's header is yielded, what it holds only if ``folds`` is set.
    """
    if isinstance(node, list):
        for item in node:
            yield from _walk(item, folds=folds)
        return
    if isinstance(node, ft.Component):
        yield from _walk(node._b, folds=folds)
        return
    if not isinstance(node, ft.Control):
        return
    yield node
    if not folds and (found := as_fold(node)):
        yield from _walk(found.node)
        return
    for part in _PARTS:
        yield from _walk(getattr(node, part, None), folds=folds)
    yield from _walk(list(getattr(node, "controls", None) or []), folds=folds)


@dataclass
class Setup:
    """What a test sets before the screen renders."""

    saved: tuple[str, ...] = SAVED
    now: datetime = THURSDAY
    loaded: bool = True
    data: bool = True
    problem: Any = None
    reduce_motion: bool = False
    batches: tuple[Batch, ...] = ()


@pytest.fixture
def setup() -> Setup:
    """The default ``Setup``, which a test's own fixtures change."""
    return Setup()


@pytest.fixture
async def shown(
    setup: Setup, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Shown]:
    """Show My schedule in a Flet session as ``setup`` says.

    The day sections' slots, the status strips and the minute hook's setters are
    recorded on the ``Shown``, and the skeleton is a placeholder.
    """
    if setup.data:
        conference = Conference(data=processed(2026), source="bundled", version=1)
    else:
        conference = Conference(problem=setup.problem)
    clock.set_test_now(setup.now)

    def use_minute() -> int:
        minute, set_minute = ft.use_state(0)
        harness.current(Shown).minutes.append(set_minute)
        return minute

    time_slot = screen.TimeSlot

    def counted_slot(label: str, *args: Any, **kwargs: Any) -> ft.Control:
        harness.current(Shown).slots.append(label)
        return time_slot(label, *args, **kwargs)

    def strip(**kwargs: Any) -> ft.Control:
        harness.current(Shown).strips.append(kwargs)
        return ft.Text("strip")

    monkeypatch.setattr(screen, "TimeSlot", counted_slot)
    monkeypatch.setattr(screen, "use_minute", use_minute)
    monkeypatch.setattr(screen, "StatusStrip", strip)
    monkeypatch.setattr(states, "SkeletonList", lambda: ft.Text("skeleton"))

    try:
        async with harness.showing(
            MySchedule,
            screen,
            year=YEAR,
            conference=conference,
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            view_path="",  # no Router: what ft.use_view_path() says outside one
            prefs=Prefs(loaded=True, reduce_motion=setup.reduce_motion),
            favorites=None if setup.loaded else Favorites(),  # not read yet
            saved=setup.saved,
            kind=Shown,
            change_log=ChangeLog(batches=setup.batches),
        ) as shown:
            yield shown
    finally:
        clock.set_test_now(None)


@pytest.fixture
def before(setup: Setup) -> None:
    """Set the time before the conference, when nothing has ended."""
    setup.now = BEFORE
