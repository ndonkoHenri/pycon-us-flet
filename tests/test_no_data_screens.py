"""Tests for ``NoDataState`` on every screen that shows the feed (#902; D-181, NEW-03).

Each of the 17 screens runs in a real Flet session (``tests/harness.py``'s ``showing()``)
with no data, so a screen that goes back to its own disabled rule, title or skeleton
label fails here by name. What the state itself says is ``test_states.py``'s.
"""

import importlib
import pkgutil
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from types import ModuleType
from typing import Any

import flet as ft
import pytest

from pycon_us import screens
from pycon_us.config import load_year
from pycon_us.screens import (
    jobs,
    keynotes,
    lightning_talks,
    map_job_fair,
    map_rooms,
    my_schedule,
    now,
    open_spaces,
    schedule,
    search,
    speaker,
    speakers,
    sponsor,
    sponsors,
    sprints,
    track,
    tracks,
)
from pycon_us.services import Services
from pycon_us.state import Conference
from pycon_us.ui.states import NO_DATA_BODY
from tests.harness import Shown, showing
from tests.trees import texts

YEAR = load_year(2026)
SCHEDULE_TITLE = "Can't load the schedule"
SCHEDULE_LOADING = "Loading schedule"


@dataclass(frozen=True)
class FeedScreen:
    """A screen that shows the feed, and what it says without any."""

    module: ModuleType
    """The screen's module, whose ``AppScaffold``, if any, the harness replaces."""
    make: Callable[[], ft.Control]
    """Makes the screen's component."""
    identifier: str
    """The failed state's semantics identifier."""
    title: str = SCHEDULE_TITLE
    """The failed state's title."""
    loading: str = SCHEDULE_LOADING
    """What the skeleton says to screen readers."""


def rooms_pane() -> ft.Control:
    """The Map's Rooms pane, as the Map places it."""
    return map_rooms.RoomsPane(ft.Ref[ft.ListView](), lambda _: None)


def job_fair_pane() -> ft.Control:
    """The Map's Job fair pane, as the Map places it."""
    return map_job_fair.JobFairPane(ft.Ref[ft.ListView](), lambda _: None)


SCREENS = (
    FeedScreen(jobs, jobs.Jobs, "jobs.no_data"),
    FeedScreen(keynotes, keynotes.Keynotes, "keynotes.no_data"),
    FeedScreen(
        lightning_talks, lightning_talks.LightningTalks, "lightning_talks.no_data"
    ),
    FeedScreen(my_schedule, my_schedule.MySchedule, "my_schedule.no_data"),
    FeedScreen(open_spaces, open_spaces.OpenSpaces, "open_spaces.no_data"),
    FeedScreen(schedule, schedule.Schedule, "schedule.no_data"),
    FeedScreen(speaker, partial(speaker.SpeakerDetail, "any"), "speaker.no_data"),
    FeedScreen(sponsor, partial(sponsor.SponsorDetail, "any"), "sponsor.no_data"),
    FeedScreen(sponsors, sponsors.Sponsors, "sponsors.no_data"),
    FeedScreen(
        map_job_fair,
        job_fair_pane,
        "map.job_fair.no_data",
        "Can't load the tables",
        "Loading tables",
    ),
    FeedScreen(
        map_rooms, rooms_pane, "map.no_data", "Can't load the rooms", "Loading rooms"
    ),
    FeedScreen(now, now.Now, "now.no_data"),
    FeedScreen(search, search.Search, "search.no_data"),
    FeedScreen(
        speakers,
        speakers.Speakers,
        "speakers.no_data",
        "Can't load the speakers",
        "Loading speakers",
    ),
    FeedScreen(
        sprints,
        sprints.Sprints,
        "sprints.no_data",
        "Can't load the sprints",
        "Loading sprint projects",
    ),
    FeedScreen(track, partial(track.TrackDetail, "charlas"), "track.no_data"),
    FeedScreen(
        tracks,
        tracks.Tracks,
        "tracks.no_data",
        "Can't load the tracks",
        "Loading tracks",
    ),
)
"""Every screen that uses ``NoDataState``; ``test_the_table_...`` keeps it complete."""

every_screen = pytest.mark.parametrize(
    "screen", SCREENS, ids=[s.identifier.removesuffix(".no_data") for s in SCREENS]
)

type Show = Callable[[FeedScreen, Conference], Awaitable[Shown]]


@pytest.fixture
async def show(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Show]:
    """Return a function that shows a screen over a ``Conference``.

    The minute ticks don't run: a real strip's would start refreshes, the network.
    """

    async def no_ticks(*_: Any) -> None:
        """Stand in for ``Services.run_every``: the tick never comes."""

    monkeypatch.setattr(Services, "run_every", no_ticks)
    async with AsyncExitStack() as stack:

        async def render(screen: FeedScreen, conference: Conference) -> Shown:
            # A Map pane has no scaffold of its own: the Map's holds it.
            scaffolded = hasattr(screen.module, "AppScaffold")
            return await stack.enter_async_context(
                showing(
                    screen.make,
                    *([screen.module] if scaffolded else []),
                    year=YEAR,
                    conference=conference,
                    tmp_path=tmp_path,
                    monkeypatch=monkeypatch,
                    view_path="/more",
                )
            )

        yield render


def test_the_table_lists_every_screen_that_uses_the_state() -> None:
    """A new screen with ``NoDataState`` has to join the table, and its rule's tests."""
    using = {
        name
        for _, name, _ in pkgutil.iter_modules(screens.__path__)
        if hasattr(importlib.import_module(f"{screens.__name__}.{name}"), "NoDataState")
    }
    assert using == {s.module.__name__.rpartition(".")[2] for s in SCREENS}


@every_screen
@pytest.mark.parametrize(
    ("asked", "disabled"), [(False, False), (True, True)], ids=["quiet", "asked"]
)
async def test_try_again_is_disabled_only_while_the_user_s_refresh_runs(
    show: Show, screen: FeedScreen, asked: bool, disabled: bool
) -> None:
    """D-181: a quiet refresh leaves it enabled, so a tap joins it; the state stays."""
    conference = Conference(problem="offline")
    conference.refreshing, conference._asked = True, asked
    shown = await show(screen, conference)
    shown.node(screen.identifier)  # still there: a screen reader keeps its place
    (button,) = shown.find(ft.FilledTonalButton)
    assert button.disabled is disabled


@every_screen
async def test_a_failed_first_fetch_names_what_failed_and_try_again_refreshes(
    show: Show, screen: FeedScreen, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The screen keeps its own title; the body says why; the button asks for a refresh."""
    refreshes: list[str] = []

    async def refresh(*_: Any, **__: Any) -> None:
        """Count a refresh, the one thing ``Try again`` does."""
        refreshes.append("refresh")

    # On the class: assigning to the store would notify, also when the patch is undone.
    monkeypatch.setattr(Conference, "refresh", refresh)
    shown = await show(screen, Conference(problem="server"))
    assert texts(shown.node(screen.identifier)) == [
        screen.title,
        NO_DATA_BODY["server"],
    ]
    (button,) = shown.find(ft.FilledTonalButton)
    assert button.content == "Try again"
    assert not button.disabled
    await shown.click(button)
    assert refreshes == ["refresh"]


@every_screen
async def test_before_a_fetch_has_failed_the_skeleton_says_what_is_loading(
    show: Show, screen: FeedScreen
) -> None:
    """NEW-03: no state and no button yet, only the screen's own loading label."""
    shown = await show(screen, Conference())
    assert screen.loading in [node.label for node in shown.find(ft.Semantics)]
    assert shown.nodes(screen.identifier) == []
