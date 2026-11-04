"""Schedule changes' harness, for its two test modules (NEW-04, D-255, #435).

`show` renders `screens/schedule_changes.py` in a real Flet session
(`tests/sessions.py`) under a `ChangeLog` seeded with the batches below, built by
hand, with the clock held at 10:42 AM on Saturday, May 16 in Long Beach and the seen
marks' 2 s wait held until the test releases it (`tests/timers.py`). The list can be
left in the same session. `test_schedule_changes.py` pins the list,
`test_schedule_changes_seen.py` the seen marks; each takes `show` by assignment
(`docs/testing-and-quality.md` §3.1).
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path
from typing import cast

import flet as ft
import pytest

from pycon_us.change_log import ChangeLog
from pycon_us.config import load_year
from pycon_us.core.change_batches import Batch
from pycon_us.core.diff import Change, ChangeKind, Listing
from pycon_us.prefs import Prefs
from pycon_us.screens import schedule_changes as screen
from pycon_us.screens import schedule_changes_seen as seen
from pycon_us.services.changes_file import read_batches
from pycon_us.state import Conference
from tests.feeds import processed
from tests.harness import Shown, showing
from tests.timers import HeldSleeps

YEAR = load_year(2026)
DATA = processed(2026)
LA = YEAR.conference.zone

NOW = datetime(2026, 5, 16, 17, 42, tzinfo=UTC)
"""10:42 AM on Saturday, May 16 in Long Beach."""

VIEW = "/now/changes/2026"
"""The list pushed on Now, as Now's card pushes it."""

SAVED = "142"
"""A saved session, moved in the newest batch and retimed in the older one."""


def listing(
    title: str = "Python for Humans", hour: int = 10, location: str = "Room 104A"
) -> Listing:
    """A session's listing on Saturday, May 16, from `hour`:30 for 30 minutes."""
    start = datetime(2026, 5, 16, hour, 30, tzinfo=LA)
    return Listing(title, start, start + timedelta(minutes=30), location)


NEWEST = Batch(
    NOW - timedelta(minutes=30),
    (
        Change(SAVED, ChangeKind.ROOM, listing(), listing(location="Room 103ABC")),
        Change("7", ChangeKind.TITLE, listing("Old name"), listing("Building Y")),
        Change("8", ChangeKind.REMOVED, listing("Gone talk"), None),
    ),
)
"""Today, 10:12 AM: a saved session moved, a rename and a removal."""

OLDER = Batch(
    NOW - timedelta(days=1, hours=2),
    (
        Change(SAVED, ChangeKind.TIME, listing(), listing(hour=11)),
        Change("9", ChangeKind.ADDED, None, listing("New talk", location="Hall B")),
    ),
    seen=True,
)
"""Yesterday, 8:42 AM, seen: the saved session retimed and an addition."""


@dataclass
class Changes(Shown):
    """The harness's `Shown` on Schedule changes, with its held wait and a way out."""

    sleeps: HeldSleeps = field(default_factory=HeldSleeps)
    """The seen marks' sleeps: the 2 s wait ends when the test releases it."""
    toggles: list[Callable[[bool], None]] = field(default_factory=list)
    """The setter that shows the list or leaves it, once its first render has run."""

    async def leave(self) -> None:
        """Leave the list (Back) in the same Flet session; let the cleanups run."""
        self.toggles[0](False)
        await self.settle()

    async def saved(self) -> list[bool]:
        """Each batch's seen mark in the log's file, once the log's writes have landed.

        A write runs in a thread, which `settle()` does not wait for.
        """
        await asyncio.gather(*self.change_log._saves)  # pyright: ignore[reportPrivateUsage]
        return [batch.seen for batch in await read_batches(self.storage, LA)]

    def unseen(self) -> list[bool]:
        """Each batch's seen mark in the log, `True` for unseen, in the log's order."""
        return [not batch.seen for batch in self.change_log.batches]

    def dots(self) -> dict[str, float]:
        """Each item's dot opacity, by the item's identifier."""
        return {
            str(node.identifier): _dot(node).opacity or 0.0
            for node in self.nodes("changes.change.")
        }


def _dot(node: ft.Semantics) -> ft.Container:
    """The unseen dot of an item's node: the second child of its leading `Stack`."""
    tile = cast(ft.ListTile, node.content)
    stack = cast(ft.Stack, tile.leading)
    return cast(ft.Container, stack.controls[1])


type Show = Callable[..., Awaitable[Changes]]


@pytest.fixture
async def show(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Show]:
    """Return a function that shows Schedule changes over the recorded 2026 feed.

    It takes the log's `batches`, the `saved` session ids, the drill id and the
    `Prefs` (a screen reader, reduced motion). The seen marks' wait is held.
    """
    monkeypatch.setattr(screen, "now", lambda: NOW)
    sleeps = HeldSleeps()
    monkeypatch.setattr(seen, "asyncio", sleeps)  # the seen module's name only
    async with AsyncExitStack() as stack:

        async def render(
            batches: tuple[Batch, ...] = (NEWEST, OLDER),
            *,
            saved: tuple[str, ...] = (SAVED,),
            year: str = "2026",
            prefs: Prefs | None = None,
        ) -> Changes:
            toggles: list[Callable[[bool], None]] = []

            @ft.component
            def Opened() -> ft.Control:
                shown, set_shown = ft.use_state(True)
                toggles[:] = [set_shown]
                if not shown:
                    return ft.Text("Back on Now")
                return screen.ScheduleChanges(year)

            return await stack.enter_async_context(
                showing(
                    Opened,
                    screen,
                    year=YEAR,
                    conference=Conference(data=DATA, source="bundled", version=1),
                    tmp_path=tmp_path,
                    monkeypatch=monkeypatch,
                    view_path=VIEW,
                    route=VIEW,  # the list is the top View (is_top_view())
                    prefs=prefs,
                    saved=saved,
                    change_log=ChangeLog(batches=batches),
                    kind=partial(Changes, sleeps=sleeps, toggles=toggles),
                )
            )

        yield render


def outline(page: Shown) -> list[str]:
    """The list's headings and item sentences, in reading order (the stars left out)."""
    (view,) = page.find(ft.ListView)
    said: list[str] = []

    def walk(control: object) -> None:
        if isinstance(control, ft.Semantics) and control.header:
            said.append(f"h{control.heading_level} {_text(control)}")
            return
        if isinstance(control, ft.Semantics) and str(control.identifier).startswith(
            "changes.change."
        ):
            said.append(str(control.label))
            return
        for name in ("content", "_b"):  # `_b`: a component's rendered body
            child = getattr(control, name, None)
            if isinstance(child, ft.BaseControl | ft.Component):
                walk(child)
        for child in getattr(control, "controls", None) or ():
            walk(child)

    for item in view.controls:
        walk(item)
    return said


def _text(control: object) -> str:
    """The first `Text` value under `control`."""
    while control is not None and not isinstance(control, ft.Text):
        control = getattr(control, "content", None)
    return str(control.value) if control is not None else ""
