"""Tests for the job fair card on Job Fair sessions and Job listings (#408, D-254).

One card in three places: the Map's Job fair pane (``tests/test_map_job_fair.py``), the
two Job Fair rows' detail (SESS-10) and the top of Job listings (SPON-10). Each pushes
the floor viewer at ``plan/job-fair`` on its own View, so Back returns to the page.
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import replace
from pathlib import Path
from typing import cast

import flet as ft
import pytest

from pycon_us.config import load_year
from pycon_us.core.expo import is_job_fair
from pycon_us.core.models import ConferenceData
from pycon_us.locations import parent_of
from pycon_us.screens import jobs
from pycon_us.state import Conference
from pycon_us.ui import location_card
from tests import harness
from tests.feeds import processed
from tests.harness import Shown
from tests.session_detail import TALK, VIEW, Render, rendering
from tests.test_session_location import ROOM_104C, drop
from tests.timers import HeldSleeps

LABEL = "Open the Job fair & community showcase floor plan"
"""What a screen reader says of the card: where a tap leads."""

EVENT = "227"
"""The Job Fair event in Expo Hall AB, "… & Poster Sessions"."""

PLENARY = "178"
"""The plenary that marks the Job Fair's time in the Schedule."""

JOBS_VIEW = "/more/jobs"

type ShowJobs = Callable[[ConferenceData | None], Awaitable[Shown]]
"""Show Job listings, after publishing the given feed when there is one."""


@pytest.fixture
async def render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Render]:
    """Provide an async function that renders a session's detail at ``VIEW`` by id."""
    async with rendering(tmp_path, monkeypatch) as show:
        yield show


def tap_of(shown: Shown, identifier: str) -> ft.Container:
    """A location card's tap target: the container around its one node."""
    tap = shown.node(identifier).parent
    assert isinstance(tap, ft.Container) and tap.on_click is not None
    return tap


def test_the_job_fair_rows_are_the_names_with_job_fair_in_both_years() -> None:
    """2026's two rows and 2025's ("Job Fair and …"), and no other session (SESS-10)."""
    for year, expected in ((2026, {EVENT, PLENARY}), (2025, {"1783", "153"})):
        data = processed(year)
        assert {s.id for s in data.sessions.values() if is_job_fair(s)} == expected


@pytest.mark.parametrize("session_id", [EVENT, PLENARY])
async def test_a_job_fair_row_shows_the_card_under_its_room_s(
    render: Render, session_id: str
) -> None:
    """Under When and where: Expo Hall AB's card, then the job fair plan's."""
    detail = await render(session_id)
    room = detail.node("session.location")
    card = detail.node("session.job_fair.location")
    assert card.label == LABEL and card.button
    section = next(
        c
        for c in ancestors(card)
        if isinstance(c, ft.Column) and c.spacing == 12 and len(c.controls) == 3
    )
    assert section.controls[1] in ancestors(room)
    assert section.controls[2] in ancestors(card)


async def test_the_session_s_card_pushes_the_plan_on_the_session(
    render: Render,
) -> None:
    """A tap pushes ``…/plan/job-fair``, without a pin; Back returns to the session."""
    detail = await render(EVENT)
    await detail.click(tap_of(detail, "session.job_fair.location"))
    assert detail.pushed == [f"{VIEW}/plan/job-fair"]
    assert parent_of(detail.pushed[0]) == VIEW


@pytest.mark.parametrize("session_id", [TALK, ROOM_104C])
async def test_another_session_has_no_job_fair_card(
    render: Render, session_id: str
) -> None:
    """A talk keeps its room's card alone."""
    detail = await render(session_id)
    assert detail.nodes("session.location")
    assert detail.nodes("session.job_fair.location") == []


async def test_a_dropped_job_fair_row_keeps_its_card(render: Render) -> None:
    """A row a refresh drops keeps its content, the card too (D-186)."""
    detail = await render(EVENT)
    drop(detail, EVENT)
    await detail.settle()
    assert detail.nodes("session.removed")
    assert detail.nodes("session.job_fair.location")


async def test_an_unknown_id_shows_not_found_without_a_card(render: Render) -> None:
    """Not found on its own level, as before (D-186)."""
    detail = await render("nope")
    assert detail.nodes("session.not_found")
    assert detail.nodes("session.job_fair.location") == []


def ancestors(control: ft.BaseControl) -> list[ft.BaseControl]:
    """The controls ``control`` is in, from its parent up to the page."""
    found: list[ft.BaseControl] = []
    parent = control.parent
    while parent is not None:
        found.append(parent)
        parent = parent.parent
    return found


# ------------------------------------------------------------------ Job listings


@pytest.fixture
async def show_jobs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[ShowJobs]:
    """Provide an async function that shows Job listings with the given feed."""
    monkeypatch.setattr(jobs, "asyncio", HeldSleeps())  # the filter's debounce
    monkeypatch.setattr(location_card, "asyncio", HeldSleeps())
    async with harness.showing(
        jobs.Jobs,
        jobs,
        year=load_year(2026),
        conference=Conference(data=processed(2026), source="bundled", version=1),
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        view_path=JOBS_VIEW,
    ) as shown:

        async def with_data(data: ConferenceData | None = None) -> Shown:
            if data is not None:
                shown.conference.data, shown.conference.version = data, 2
                await shown.settle()
            return shown

        yield with_data


async def test_job_listings_open_with_the_card_above_the_listings(
    show_jobs: ShowJobs,
) -> None:
    """The first item of the list, before the first listing's card (SPON-10)."""
    shown = await show_jobs(None)
    card = shown.node("jobs.job_fair.location")
    assert card.label == LABEL
    (listing,) = shown.find(ft.ListView)
    first = listing.controls[0]
    assert first in ancestors(card)
    assert shown.nodes("jobs.listing.") and all(
        first not in ancestors(n) for n in shown.nodes("jobs.listing.")
    )


async def test_the_jobs_card_pushes_the_plan_on_job_listings(
    show_jobs: ShowJobs,
) -> None:
    """``/more/jobs/plan/job-fair``: Back returns to the listings."""
    shown = await show_jobs(None)
    await shown.click(tap_of(shown, "jobs.job_fair.location"))
    assert shown.went == [f"{JOBS_VIEW}/plan/job-fair"]
    assert parent_of(shown.went[0]) == JOBS_VIEW


async def test_a_year_without_listings_has_no_card(show_jobs: ShowJobs) -> None:
    """A feed without listings says "No job listings yet", with no card above."""
    shown = await show_jobs(None)
    data = cast(ConferenceData, shown.conference.data)
    await show_jobs(replace(data, job_listings=()))
    assert shown.nodes("jobs.empty")
    assert shown.nodes("jobs.job_fair.location") == []
