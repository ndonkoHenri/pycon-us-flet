"""The Now tab's fixed times, sessions and harness, for its three test modules (#312).

`test_now.py` (the header's words), `test_now_screen.py` (the sections each season
shows) and `test_now_card.py` (the next-session card, time passing and the states
without data) share the 2026 feed's times and sessions named here. The screen runs in a
real Flet session, as the session rows' tests do (`tests/sessions.py` names the Flet
internals the harness uses), with the clock held by the test: Flet's scheduler
re-renders what changed, so a test sees which row bodies ran (D-153). A module takes the
fixtures by assigning them to its own names, as `docs/testing-and-quality.md` §3.1
says.
"""

from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import flet as ft
import pytest
from flet.components.component import Component

from pycon_us import clock
from pycon_us.account import Account
from pycon_us.change_log import ChangeLog
from pycon_us.config import load_year
from pycon_us.core.models import ConferenceData
from pycon_us.memory import ViewMemory
from pycon_us.prefs import Prefs
from pycon_us.screens import now as screen
from pycon_us.services import Services
from pycon_us.staff import Staff
from pycon_us.state import Conference
from pycon_us.ui import status_strip
from tests import harness
from tests.feeds import processed

YEAR = load_year(2026)
INFO = YEAR.conference
PACIFIC = ZoneInfo("America/Los_Angeles")

TALK = "142"
"""Python for Humans, 10:30-11:00 AM on Saturday, May 16, in Grand Ballroom A."""

AT_11 = ("105", "4", "9113", "9040", "9072", "15", "102", "41", "9059", "9086")
"""What is on at 11:10 AM on Friday, May 15, in the Schedule's order: the 11:00 talks
(30 min) and open spaces (1 h)."""

FIRST_AT_11 = ("105", "4", "15")
"""What Happening now shows of AT_11 before "Show all" (D-327): its first three talks;
the open spaces come after the others."""

OPEN_SPACE = "9086"
"""pytest for system tests, an open space at 11:00 AM on Friday: last of AT_11, and
hidden on the Schedule by default (D-20)."""

KEYNOTE = "153"
"""Lin Qiao's keynote, 9:45-10:30 AM on Friday: alone until the 10:00 open spaces."""


JOB_FAIR = "178"
"""The Job Fair & Community Showcase on Sunday: its row says 9:30 AM, its slot is the
10:00 one (DATA-11), and it ends at 1:00 PM."""


def may(day: int, hour: int, minute: int = 0) -> datetime:
    """That time on that day of May 2026, in Pacific Time."""
    return datetime(2026, 5, day, hour, minute, tzinfo=PACIFIC)


@pytest.fixture(scope="module")
def data() -> ConferenceData:
    """The recorded 2026 feed, processed once for the module."""
    return processed(2026)


# ------------------------------------------------------------------ the screen


@dataclass
class Ticks:
    """Stands in for `Services.run_every`: keeps each loop's action to call by hand."""

    actions: list[Callable[[], object]] = field(default_factory=list)

    async def run_every(self, seconds: float, action: Callable[[], object]) -> None:
        """Keep `action` for the test to run, instead of looping."""
        self.actions.append(action)


@dataclass
class Shown(harness.Shown):
    """The harness's `Shown` (`tests/harness.py`) on Now, with the test's clock."""

    clock: list[datetime] = field(default_factory=list)
    """The time `clock.now()` answers: `clock[0]`."""
    ticks: Ticks = field(default_factory=Ticks)

    @property
    def body(self) -> ft.ListView:
        """The screen's one `ListView`."""
        (body,) = self.find(ft.ListView)
        return body

    def all(self) -> list[ft.Control]:
        """Every control on screen, in reading order, components entered."""
        return list(_walk(self.body))

    def has(self, identifier: str) -> bool:
        """Whether a `Semantics` with `identifier` is on screen."""
        return any(
            isinstance(c, ft.Semantics) and c.identifier == identifier
            for c in self.all()
        )

    def headings(self) -> list[str]:
        """The section headings (level 2) under the status header, in order."""
        return [
            _texts(c)[0]
            for c in self.all()
            if isinstance(c, ft.Semantics)
            and c.header
            and c.heading_level == 2
            and c.identifier != "now.header"
        ]

    def listed(self, prefix: str = "now.session.") -> list[str]:
        """The session rows' keys, in order: `now.session.<key>`."""
        return [
            str(c.identifier).removeprefix(prefix)
            for c in self.all()
            if isinstance(c, ft.Semantics) and str(c.identifier).startswith(prefix)
        ]

    def texts(self) -> list[str]:
        """The texts on screen in reading order, plain strings too (`_texts`)."""
        return _texts(self.body)

    def fold_button(self, section: str) -> ft.TextButton:
        """The "Show all" button of `section` (`happening`, `up_next`)."""
        expanded = self.node(f"now.show_all.{section}").content
        assert isinstance(expanded, ft.Semantics)
        assert isinstance(expanded.content, ft.TextButton)
        return expanded.content

    async def show_all(self, section: str = "happening") -> None:
        """Tap a section's "Show all" button, so it lists all its sessions (D-327)."""
        await self.click(self.fold_button(section))

    async def at(self, now: datetime) -> None:
        """Move the clock to `now` and run every minute tick, as a minute passing."""
        self.clock[0] = now
        for action in self.ticks.actions:
            action()
        await self.settle()


def _children(control: Any) -> list[Any]:
    """The children of `control`, a component's rendered body included."""
    if isinstance(control, Component):
        body = control._b
        return body if isinstance(body, list) else [body]
    found: list[Any] = []
    for name in ("content", "leading", "title", "subtitle", "trailing"):
        child = getattr(control, name, None)
        if isinstance(child, ft.BaseControl):
            found.append(child)
    found.extend(getattr(control, "controls", None) or ())
    return found


def _walk(control: Any) -> Iterator[Any]:
    """Yield `control` and every control under it, in reading order."""
    yield control
    for child in _children(control):
        if child is not None:
            yield from _walk(child)


def _texts(control: Any) -> list[str]:
    """The texts under `control` in reading order, plain strings too.

    Plain strings are, for example, a `ListTile`'s title or a button's label.
    """
    found: list[str] = []
    for c in _walk(control):
        if isinstance(c, ft.Text):
            found.append(str(c.value))
        for name in ("title", "subtitle", "content"):
            if isinstance(text := getattr(c, name, None), str):
                found.append(text)
    return found


@pytest.fixture
async def render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Callable[..., Any]]:
    """Render Now at a time; every session shown is closed at the end."""
    async with AsyncExitStack() as stack:

        async def render(
            now: datetime,
            *,
            conference: Conference | None = None,
            saved: tuple[str, ...] = (),
            ticks: Ticks | None = None,
            memory: ViewMemory | None = None,
            change_log: ChangeLog | None = None,
            prefs: Prefs | None = None,
            account: Account | None = None,
            staff: Staff | None = None,
        ) -> Shown:
            """Render Now at `now`, with `saved` in My schedule.

            With `ticks` the minute loops are real; else `Shown.at` runs them.
            `memory` is the process's view memory, when a test keeps one;
            `change_log` the session's, when a test records batches; `prefs`
            the settings, large text say, when a test sets them; `account` and
            `staff` the stores, for the Scan badges card.
            """
            held = [now]
            ticker = ticks or Ticks()
            monkeypatch.setattr(clock, "now", lambda: held[0])
            # The strip is tested on its own (test_status_strip.py); a real one would
            # also start refreshes: the network.
            if screen.StatusStrip is status_strip.StatusStrip:
                monkeypatch.setattr(screen, "StatusStrip", lambda **_: ft.Text("strip"))
            if ticks is None:
                monkeypatch.setattr(Services, "run_every", ticker.run_every)
            if conference is None:
                conference = Conference(
                    data=processed(2026),
                    source="bundled",
                    version=1,
                    fetched_at=now,  # fresh: no strip
                )
            return await stack.enter_async_context(
                harness.showing(
                    screen.Now,
                    screen,
                    year=YEAR,
                    conference=conference,
                    tmp_path=tmp_path,
                    monkeypatch=monkeypatch,
                    view_path="/now",
                    saved=saved,
                    memory=memory,
                    change_log=change_log,
                    prefs=prefs,
                    account=account,
                    staff=staff,
                    kind=partial(Shown, clock=held, ticks=ticker),
                )
            )

        yield render


def next_cards(shown: Shown) -> list[ft.Card]:
    """The next-session cards on screen: the filled ones, not the sponsor spotlight."""
    return [
        c
        for c in shown.all()
        if isinstance(c, ft.Card) and c.variant == ft.CardVariant.FILLED
    ]


def header(shown: Shown) -> str:
    """The status header's spoken phrase."""
    return str(shown.node("now.header").label)
