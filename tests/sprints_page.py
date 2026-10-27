"""The Sprints page tests' support: the 2026 projects, the harness, lookups (#106).

``test_sprints.py`` (the query and the Tracks hub's row) and ``test_sprints_page.py``
(the screen) share it. The screen runs in a real Flet session (``tests/sessions.py``'s
``showing()``); ``show`` counts the card bodies that ran (D-153). A module takes the
fixtures by assigning them to its own names, as ``docs/testing-and-quality.md`` §3.1
says.
"""

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import flet as ft
import pytest

from pycon_us.config import YearData, load_year
from pycon_us.core.models import Sprint
from pycon_us.core.sprints import projects
from pycon_us.screens import sprint_card
from pycon_us.screens import sprints as screen
from pycon_us.screens import tracks as hub_screen
from pycon_us.state import Conference
from tests import harness
from tests.feeds import processed

YEAR = load_year(2026)
INFO = YEAR.conference
DATA = processed(2026)
ALL = projects(DATA)
CARD = "sprints.project."
"""The prefix of a card's name heading's semantics identifier."""


def named(name: str) -> Sprint:
    """Return the 2026 project named ``name``."""
    (found,) = [sprint for sprint in ALL if sprint.name == name]
    return found


def names(listed: tuple[Sprint, ...]) -> list[str]:
    """Return the names of ``listed``, in order."""
    return [sprint.name for sprint in listed]


@dataclass
class Shown(harness.Shown):
    """The harness's ``Shown`` (``tests/harness.py``), and which cards ran."""

    cards: list[str] = field(default_factory=list)
    """The project ids whose card bodies ran, in order."""

    @property
    def listed(self) -> list[str]:
        """The project ids of the cards on screen, in order."""
        return [str(n.identifier).removeprefix(CARD) for n in self.nodes(CARD)]

    @property
    def launched(self) -> list[str]:
        """The URLs the screen launched, in order."""
        return [url for url, _ in self.launcher.launched]

    async def type(self, text: str) -> None:
        """Type into the filter as Flutter reports it: the value, then the event."""
        (text_field,) = self.find(ft.TextField)
        self.session.apply_patch(text_field._i, {"value": text})
        await self.event(text_field, "change", None)


@pytest.fixture
async def show(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Any]:
    """Return a function that renders a screen, Sprints by default, over the feed.

    It takes the screen, then a ``conference`` (the recorded 2026 one by default) and a
    ``year`` (2026's).
    """
    counted = sprint_card.cut_short

    def cut(sprint: Sprint) -> bool:
        harness.current(Shown).cards.append(sprint.id)
        return counted(sprint)

    # Each card body asks once: counting the calls counts the bodies (S2).
    monkeypatch.setattr(sprint_card, "cut_short", cut)

    async with AsyncExitStack() as stack:

        async def render(
            component: Any = screen.Sprints,
            conference: Conference | None = None,
            year: YearData = YEAR,
        ) -> Shown:
            return await stack.enter_async_context(
                harness.showing(
                    component,
                    screen,
                    hub_screen,
                    year=year,
                    conference=Conference(data=DATA, source="bundled", version=1)
                    if conference is None
                    else conference,
                    tmp_path=tmp_path,
                    monkeypatch=monkeypatch,
                    view_path="",  # no Router: what ft.use_view_path() says outside one
                    kind=Shown,
                )
            )

        yield render


@pytest.fixture
def focused(monkeypatch: pytest.MonkeyPatch) -> list[ft.TextField]:
    """The fields asked to take the focus; the harness has no Flutter to answer."""
    asked: list[ft.TextField] = []

    async def focus(self: ft.TextField) -> None:
        asked.append(self)

    monkeypatch.setattr(ft.TextField, "focus", focus)
    return asked


def year_with(**changes: Any) -> YearData:
    """Return 2026's year data with ``changes`` to its conference facts."""
    return replace(YEAR, conference=replace(INFO, **changes))


def with_sprints(*sprints: Sprint) -> Conference:
    """Return the 2026 feed's ``Conference`` with ``sprints`` alone."""
    return Conference(data=replace(DATA, sprints=sprints), source="bundled", version=1)


def text_of(control: object) -> str:
    """The first ``Text`` value under ``control``, following ``content``."""
    while control is not None and not isinstance(control, ft.Text):
        control = getattr(control, "content", None)
    return str(control.value) if control is not None else ""


def card_of(shown: Shown, sprint: Sprint) -> ft.Card:
    """Return the ``Card`` that holds ``sprint``'s name heading."""
    heading: ft.BaseControl | None = shown.node(f"{CARD}{sprint.id}")
    while heading is not None and not isinstance(heading, ft.Card):
        heading = heading.parent
    assert isinstance(heading, ft.Card)
    return heading


def under(control: ft.BaseControl, root: ft.BaseControl) -> bool:
    """Whether ``control`` is ``root`` or mounted under it."""
    node: ft.BaseControl | None = control
    while node is not None:
        if node is root:
            return True
        node = node.parent
    return False
