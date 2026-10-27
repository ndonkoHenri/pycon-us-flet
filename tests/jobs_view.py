"""The Job listings page's harness, for its two test modules (#399, #400, #623).

``tests/test_jobs_page.py`` (the rules, the cards and the states) and
``tests/test_jobs_page_filter.py`` (the filter) take ``show``, ``sleeps`` and
``focused`` by assignment (§3.1). The page runs in a real Flet session
(``tests/harness.py``'s ``showing()``) on the recorded 2026 feed, with its debounce
held by ``tests/timers.py``.
"""

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, cast

import flet as ft
import pytest

from pycon_us.config import load_year
from pycon_us.core.models import JobListing
from pycon_us.screens import jobs as screen
from pycon_us.state import Conference
from tests import harness
from tests.feeds import processed
from tests.harness import Shown
from tests.timers import HeldSleeps

YEAR = load_year(2026)


DATA = processed(2026)


VIEW = "/more/jobs"
"""The page's View path, which a sponsor's detail is pushed on."""


CARD = "jobs.listing."
"""The prefix of a card header's semantics identifier."""


def listing(name: str) -> JobListing:
    """Return the 2026 listing of the sponsor named ``name``."""
    (found,) = [j for j in DATA.job_listings if j.sponsor_name == name]
    return found


def role_ids(shown: Shown, item: JobListing) -> list[str]:
    """The identifiers of a card's role rows, in the rows' order."""
    prefix = f"jobs.role.{item.id}."
    ids = [str(n.identifier) for n in shown.nodes(prefix)]
    return sorted(ids, key=lambda i: int(i.removeprefix(prefix)))


def toggle_of(shown: Shown, identifier: str) -> tuple[ft.Semantics, ft.TextButton]:
    """A card's toggle: the node that says its state, and its button."""
    toggle = cast(ft.Semantics, shown.node(identifier).content)
    return toggle, cast(ft.TextButton, toggle.content)


def cards(shown: Shown) -> list[str]:
    """The sponsors of the cards on the page, in the list's order."""
    by_id = {f"{CARD}{item.id}": item.sponsor_name for item in DATA.job_listings}
    return [
        by_id[str(n.identifier)]
        for n in shown.find(ft.Semantics)
        if n.identifier in by_id
    ]


async def type_into(shown: Shown, text: str) -> None:
    """Type into the filter as Flutter reports it: the value, then the event."""
    (text_field,) = shown.find(ft.TextField)
    shown.session.apply_patch(text_field._i, {"value": text})
    await shown.event(text_field, "change", None)


async def pause(shown: Shown, sleeps: HeldSleeps) -> None:
    """The typing pauses: end the debounce's wait, then let the re-render through."""
    await sleeps.release()
    await shown.settle()


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> HeldSleeps:
    """The page's debounce, held until a test's ``pause()`` (``tests/timers.py``)."""
    held = HeldSleeps()
    monkeypatch.setattr(screen, "asyncio", held)  # the jobs module's only
    return held


@pytest.fixture
def focused(monkeypatch: pytest.MonkeyPatch) -> list[ft.TextField]:
    """The fields asked to take the focus; the harness has no Flutter to answer."""
    asked: list[ft.TextField] = []

    async def focus(self: ft.TextField) -> None:
        asked.append(self)

    monkeypatch.setattr(ft.TextField, "focus", focus)
    return asked


@pytest.fixture
async def show(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sleeps: HeldSleeps
) -> AsyncIterator[Any]:
    """Return a function that shows the page, with a ``conference`` (2026 by default)."""
    async with AsyncExitStack() as stack:

        async def render(conference: Conference | None = None) -> Shown:
            return await stack.enter_async_context(
                harness.showing(
                    screen.Jobs,
                    screen,
                    year=YEAR,
                    conference=conference
                    or Conference(data=DATA, source="bundled", version=1),
                    tmp_path=tmp_path,
                    monkeypatch=monkeypatch,
                    view_path=VIEW,
                )
            )

        yield render
