"""F150's harness (#601): nothing under a skipped memoised component re-renders alone.

A component under an ``ft.memo`` component finds its contexts through a weak reference
to the instance that first rendered it. Once a render above has skipped that memoised
component and Python's cycle collector has freed the instance, a component inside that
re-renders by itself (its own ``use_state``, a store it subscribed to) finds no
provider: ``use_services()`` and the other store hooks raise, and Flet's updates
scheduler, which does not catch an update's error, stops for the rest of the session
(F150, U111 #597).

Each test opens the app (``tests/links.py``'s ``open_at``: the real Router and screens
over the 2026 feed, with saved sessions and a change log) at a location with memoised
parts, before, during and after the conference, at the default and the largest text.
It lists every component under a memoised one that could re-render on its own (one
holding state, an effect or a subscription), re-renders the app from its root so each
memoised part with equal props is skipped, runs the collector, then re-renders each of
those components by itself, as its tick, toggle or store would. The scheduler must
still run after each, and none may exist: under a memoised component, values only
(F150's rule). On #586's parent commit, the Schedule at the largest text fails here:
its status strip ticked inside the day lists.
"""

import gc
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import flet as ft
import pytest
from flet.components.component import Component
from flet.components.hooks.use_effect import EffectHook
from flet.components.hooks.use_state import StateHook
from flet.messaging.session import Session

from pycon_us import clock
from pycon_us.change_log import ChangeLog
from pycon_us.core.change_batches import Batch
from pycon_us.core.diff import Change, ChangeKind, Listing
from pycon_us.prefs import Prefs
from tests import links, sessions
from tests.links import Open, Shown

open_at = links.open_at

PACIFIC = ZoneInfo("America/Los_Angeles")

MOMENTS = {
    "before": datetime(2026, 4, 1, 12, 0, tzinfo=PACIFIC),
    "during": datetime(2026, 5, 15, 10, 40, tzinfo=PACIFIC),
    "after": datetime(2026, 6, 1, 12, 0, tzinfo=PACIFIC),
}
"""The conference's seasons: each shows its own parts (Now's sections, the now line)."""

SAVED = ("142", "42", "99", "153")
"""Favourites the storage holds before the app opens, so My Schedule has days."""

LOCATIONS = [
    "/now",
    "/schedule",
    "/my-schedule",
    "/more/speakers",
    "/more/keynotes",
    "/more/open-spaces",
    "/more/lightning-talks",
    "/more/sprints",
    "/more/sponsors",
    "/more/jobs",
    "/more/help",
    "/more/venue",
    "/schedule/session/42/speaker/17",
    "/map/room/grand-ballroom-a",
    "/more/sponsors/sponsor/bloomberg",
    "/schedule/changes/2026",
    "/search",
]
"""Every location with a memoised part: each ``ft.memo`` component in ``src/`` is
under one of them (the audit in #601's PR). Map, Tracks, a track, Wi-Fi and a floor
plan have none."""


@pytest.fixture(params=list(MOMENTS))
def moment(request: pytest.FixtureRequest) -> Iterator[datetime]:
    """Hold the clock in each season of the conference in turn; lift it afterwards."""
    clock.set_test_now(MOMENTS[request.param])
    yield MOMENTS[request.param]
    clock.set_test_now(None)


def change_log(at: datetime) -> ChangeLog:
    """A change log whose unseen batch moved and renamed two saved sessions."""
    start = datetime(2026, 5, 16, 10, 30, tzinfo=PACIFIC)
    before = Listing("Python for Humans", start, start + timedelta(minutes=30), "104A")
    after = Listing("Building Y", start, start + timedelta(minutes=30), "103ABC")
    batch = Batch(
        at - timedelta(minutes=30),
        (
            Change("142", ChangeKind.ROOM, before, after),
            Change("42", ChangeKind.TITLE, before, after),
        ),
    )
    return ChangeLog(batches=(batch,))


def mounted(session: Session) -> list[Component]:
    """The session's mounted components, in no set order."""
    return [
        c
        for c in session.index.values()
        if isinstance(c, Component) and c._state.mounted and not c._stale
    ]


def memo_above(component: Component) -> Component | None:
    """The nearest memoised component above ``component``, by the render links."""
    ref = component._parent_component
    while ref is not None and (parent := ref()) is not None:
        if parent.memoized:
            return parent
        ref = parent._parent_component
    return None


def own_updates(component: Component) -> list[str]:
    """What could re-render ``component`` on its own: its state, effects, stores."""
    hooks = component._state.hooks
    found = [f"state {h.value!r}"[:50] for h in hooks if isinstance(h, StateHook)]
    found += ["effect" for h in hooks if isinstance(h, EffectHook)]
    found += ["subscription" for _ in component._state.observable_subscriptions]
    return found


def self_updaters(session: Session) -> list[tuple[Component, str]]:
    """Each mounted component under a memoised one that could re-render on its own.

    Each comes with why, as text: the memoised component's name, its own, and what
    could re-render it. Only the memoised one's name is kept: a reference to it would
    keep it from being collected, and so hide F150.
    """
    found = []
    for component in mounted(session):
        memo = memo_above(component)
        reasons = own_updates(component)
        if memo is not None and reasons:
            name = f"{memo.fn.__name__} > {component.fn.__name__}"
            found.append((component, f"{name}: {', '.join(reasons)}"))
    return found


def scheduler(session: Session) -> Any:
    """The session's updates scheduler task (``Session.__updates_task``, at the pin)."""
    return session._Session__updates_task  # pyright: ignore[reportAttributeAccessIssue]


def memo_parents(session: Session) -> list[Component]:
    """The components that render a memoised part with none above it: the screens."""
    found: dict[int, Component] = {}
    for component in mounted(session):
        ref = component._parent_component
        parent = ref() if ref is not None else None
        if component.memoized and parent is not None and memo_above(component) is None:
            found[id(parent)] = parent
    return list(found.values())


async def skip_memos(session: Session) -> None:
    """Re-render each memoised part's parent, so the parts with equal props skip.

    As a star tap or a minute tick re-renders a screen. Then run the collector: the
    instances that rendered the skipped parts' output are freed, as on a device once
    Python's cycle collector has run (F150).
    """
    for parent in memo_parents(session):
        parent._schedule_update()
    await sessions.settle()
    gc.collect()


async def stopped_by(session: Session, found: list[tuple[Component, str]]) -> list[str]:
    """Re-render each component of ``found`` by itself; return those that stopped Flet.

    Each that stops the updates scheduler is named with its error, and the scheduler is
    started again for the next.
    """
    stopped = []
    for component, why in found:
        if component._stale or not component._state.mounted:
            continue  # its memoised part re-rendered: its links are new
        component._schedule_update()
        await sessions.settle()
        if (task := scheduler(session)).done():
            stopped.append(f"{why}: {task.exception()!r}")
            session.start_updates_scheduler()
    return stopped


async def search(shown: Shown, query: str) -> None:
    """Submit ``query`` in the search field, as Flutter reports it: value, then event."""
    (field,) = shown.find(ft.TextField)
    shown.session.apply_patch(field._i, {"value": query})
    await shown.event(field, "submit", query)


@pytest.mark.parametrize("time_above", [False, True], ids=["text-100", "text-max"])
@pytest.mark.parametrize("location", LOCATIONS)
async def test_nothing_under_a_skipped_memo_re_renders_on_its_own(
    open_at: Open, location: str, time_above: bool, moment: datetime
) -> None:
    """F150: no component under a memoised one can re-render alone; none stops Flet.

    Each one that could is re-rendered by itself after a skip and a collection, and
    the scheduler must survive it; then the list of them must be empty.
    """
    prefs = Prefs(loaded=True, time_above=time_above, time_measured=True)
    shown = await open_at(
        location, saved=SAVED, prefs=prefs, change_log=change_log(moment)
    )
    if location == "/search":
        await search(shown, "python")
    assert any(c.memoized for c in mounted(shown.session)), "nothing memoised here"
    found = self_updaters(shown.session)
    await skip_memos(shown.session)
    assert await stopped_by(shown.session, found) == []
    assert [why for _, why in found] == []


Ctx = ft.create_context(None)
"""The context the harness's own check reads under a memoised component."""


async def test_the_harness_catches_a_ticking_component_under_a_skipped_memo() -> None:
    """The harness reproduces F150: a ticking reader of a context under a memo stops Flet.

    #597's repro: a component with its own state that reads a context, in a memoised
    component's output. After a skip and a collection, its own re-render finds no
    provider and the scheduler stops; ``stopped_by()`` names it.
    """

    @ft.component
    def Ticker() -> ft.Control:
        assert ft.use_context(Ctx) is not None, "no provider above"
        n, _ = ft.use_state(0)
        return ft.Text(str(n))

    @ft.memo
    @ft.component
    def Memo(x: int) -> ft.Control:
        return ft.Column([Ticker()])

    @ft.component
    def Root() -> ft.Control:
        return Ctx("value", lambda: Memo(1))

    async with sessions.rendering(Root) as session:
        found = self_updaters(session)
        assert [why for _, why in found] == ["Memo > Ticker: state 0"]
        await skip_memos(session)
        (stopped,) = await stopped_by(session, found)
        assert stopped.startswith("Memo > Ticker: state 0: AssertionError")
