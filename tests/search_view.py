"""The search screen's harness, for its three test modules (#312).

``test_search_screen.py`` (the scope, the field and the typing),
``test_search_screen_results.py`` (the results, their taps and the empty states) and
``test_search_screen_show_all.py`` (the first rows of each type and Show all) run the
screen in a real Flet session under the real Router with ``manage_views``, as the app
renders it (``tests/harness.py``'s ``showing()`` with ``view_path=None``): a small
route table with a Schedule stand-in, the global modal ``/search`` and a drill whose
detail is a plain View, so a result tap, Back and a fresh open go through the Router's
own view stack (S4, D-141). Navigation is ``page.navigate`` replaced by what Flutter
does next: the page's route changes and the Router hears of it. A keystroke is the
field's value patched in and its change event dispatched, as Flutter sends them
(``tests/test_speakers_screen.py``). The debounce's wait is held until a test ends it
(``Shown.pause()``, ``tests/timers.py``), so on a slow host no search runs between two
keystrokes (#270). A module takes the fixtures by assigning them to its own names, as
``docs/testing-and-quality.md`` §3.1 says.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import flet as ft
import pytest

from pycon_us.config import load_year
from pycon_us.core.search import SearchResults, search, search_index
from pycon_us.screens import search as screen
from pycon_us.screens import search_scopes
from pycon_us.services import use_services
from pycon_us.state import Conference
from pycon_us.ui import scaffold
from tests import harness
from tests.fakes import MemoryHaptics
from tests.feeds import processed
from tests.timers import HeldSleeps

YEAR = load_year(2026)
DATA = processed(2026)
INDEX = search_index(DATA, YEAR.map.venue_spots(), YEAR.map.booths)


# ------------------------------------------------------------------ the harness


@ft.component
def Opener() -> ft.View:
    """A tab root with a Search button, as the Schedule's (D-19)."""
    memory = use_services().memory
    return ft.View(
        route="/schedule",
        controls=[scaffold.search_button(memory, "sessions")],
    )


@ft.component
def Detail() -> ft.View:
    """A pushed detail: its path, so a test can tell which one shows."""
    return ft.View(route=ft.use_view_path(), controls=[ft.Text(ft.use_view_path())])


DRILL = ft.Route(path=":kind/:ident", recursive=True, component=Detail)
ROUTES = [
    ft.Route(path="schedule", component=Opener, children=[DRILL]),
    ft.Route(path="search", component=screen.Search, modal=True, children=[DRILL]),
]


@dataclass
class Shown(harness.Shown):
    """The harness's ``Shown`` (``tests/harness.py``) on the app's Views.

    It also records what the search screen asked for: its searches, the focus, its
    scope row's jumps and its sleeps.
    """

    searches: list[tuple[str, str]] = field(default_factory=list)
    """Each ``search(index, query, scope)`` the screen ran, as (query, scope)."""
    focused: list[ft.TextField] = field(default_factory=list)
    """The fields asked to take the focus; no Flutter answers here."""
    jumps: list[tuple[str, int]] = field(default_factory=list)
    """Each keyed jump of the scope row (``search_scopes``), as (key, duration)."""
    sleeps: HeldSleeps = field(default_factory=HeldSleeps)
    """The screen's sleeps: the debounce waits until ``pause()`` releases it."""

    @property
    def page(self) -> ft.Page:
        """The session's page."""
        return cast(ft.Page, self.session.page)

    @property
    def haptics(self) -> MemoryHaptics:
        """The ``MemoryHaptics`` of the session's services."""
        return cast(MemoryHaptics, self.services.haptics)

    def live(self) -> list[ft.BaseControl]:
        """The controls on the page now (the index keeps some that left it)."""
        return [c for c in self.session.index.values() if c.page is not None]

    def find[T: ft.BaseControl](self, kind: type[T]) -> list[T]:
        """The controls of ``kind`` on the page now."""
        return [c for c in self.live() if isinstance(c, kind)]

    def node(self, identifier: str) -> ft.Semantics:
        """The one semantics node on the page with ``identifier``."""
        found = [c for c in self.find(ft.Semantics) if c.identifier == identifier]
        assert len(found) == 1, identifier
        return found[0]

    def has(self, identifier: str) -> bool:
        """Whether a semantics node on the page has ``identifier``."""
        return any(c.identifier == identifier for c in self.find(ft.Semantics))

    @property
    def views(self) -> list[str]:
        """The routes of the Views the Router stacks, bottom first."""
        node: Any = self.page.views
        # page.views is the root component; the providers' bodies lead to the
        # Router's, a list of Views (or components rendering one each).
        while not isinstance(node, list):
            node = node._b
        routes = []
        for view in node:
            while not isinstance(view, ft.View):
                view = view._b
            routes.append(str(view.route))
        return routes

    @property
    def field(self) -> ft.TextField:
        """The screen's one ``TextField``."""
        (text_field,) = self.find(ft.TextField)
        return text_field

    @property
    def results(self) -> list[str]:
        """The identifiers of the result rows and headings, in the list's order."""
        (body,) = self.find(ft.ListView)
        found: list[str] = []

        def walk(control: object) -> None:
            if isinstance(control, ft.Semantics) and control.header:
                found.append(f"h{control.heading_level}:{_text(control)}")
            identifier = getattr(control, "identifier", None)
            if isinstance(identifier, str) and identifier.startswith("search."):
                found.append(identifier)
            for name in ("content", "_b"):
                child = getattr(control, name, None)
                for item in child if isinstance(child, list) else [child]:
                    if isinstance(item, ft.BaseControl):
                        walk(item)
            for child in getattr(control, "controls", None) or ():
                walk(child)

        walk(body)
        return found

    async def pause(self) -> None:
        """The typing pauses: end the debounce's wait, then let the re-render through."""
        await self.sleeps.release()
        await self.settle()

    async def go(self, location: str) -> None:
        """Navigate as ``page.navigate`` does through Flutter: a new route, heard."""
        self.page.route = location
        # The Router's own handler, which reads only the event's route.
        handler: Any = self.page.on_route_change
        handler(SimpleNamespace(route=location))
        await self.settle()

    async def type(self, text: str) -> None:
        """Type into the field as Flutter reports it: the value, then the event."""
        text_field = self.field
        self.session.apply_patch(text_field._i, {"value": text})
        await self.event(text_field, "change")

    def chip(self, scope: str) -> ft.Chip:
        """The scope chip for ``scope``."""
        return cast(ft.Chip, self.node(f"search.scope.{scope}").content)


def _first[T: ft.BaseControl](control: object, kind: type[T]) -> T | None:
    """The first ``kind`` under ``control``, following ``content``."""
    while control is not None and not isinstance(control, kind):
        control = getattr(control, "content", None)
    return control


def _text(control: object) -> str:
    """The first ``Text`` value under ``control``."""
    while control is not None and not isinstance(control, ft.Text):
        control = getattr(control, "content", None)
    return str(control.value) if control is not None else ""


type Render = Callable[[Conference], Awaitable[Shown]]


@pytest.fixture
async def render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Render]:
    """Provide ``show(conference)``: the app's Views at the Schedule stand-in."""

    def counted_search(index: Any, query: str, scope: str = "all") -> SearchResults:
        harness.current(Shown).searches.append((query, scope))
        return search(index, query, scope)

    async def focus(self: ft.TextField) -> None:
        harness.current(Shown).focused.append(self)

    async def jump(_row: Any, key: str, *, duration: int, **_: Any) -> str:
        harness.current(Shown).jumps.append((key, duration))
        return "landed"

    monkeypatch.setattr(screen, "search", counted_search)
    monkeypatch.setattr(search_scopes, "jump_to_key", jump)
    monkeypatch.setattr(ft.TextField, "focus", focus)
    sleeps = HeldSleeps()
    monkeypatch.setattr(screen, "asyncio", sleeps)  # the search module's only

    async with AsyncExitStack() as stack:

        async def show(conference: Conference) -> Shown:
            shown = await stack.enter_async_context(
                harness.showing(
                    lambda: ft.Router(ROUTES, manage_views=True),
                    year=YEAR,
                    conference=conference,
                    tmp_path=tmp_path,
                    monkeypatch=monkeypatch,
                    view_path=None,  # a real Router, rendered as the page's Views
                    route="/schedule",
                    kind=partial(Shown, sleeps=sleeps),
                )
            )

            def navigate(location: str) -> None:
                asyncio.get_running_loop().create_task(shown.go(location))

            monkeypatch.setattr(shown.page, "navigate", navigate)
            return shown

        yield show


@pytest.fixture
async def opened(render: Render) -> Shown:
    """Search opened from the Schedule stand-in with its scope, as a tap would."""
    shown = await render(Conference(data=DATA, source="bundled", version=1))
    (button,) = shown.find(ft.IconButton)
    await shown.event(button, "click")
    await shown.settle()
    assert shown.views == ["/schedule", "/search"]
    shown.searches.clear()
    return shown


def session_ids(query: str, scope: str = "all") -> list[str]:
    """The session ids ``core.search`` finds, in its order."""
    return [s.id for day in search(INDEX, query, scope).sessions for s in day.sessions]


def _all_text(control: object) -> str:
    """Every ``Text`` value under ``control``, joined by spaces."""
    found: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, ft.Text):
            found.append(str(node.value))
        for name in ("content", "_b"):
            child = getattr(node, name, None)
            for item in child if isinstance(child, list) else [child]:
                if isinstance(item, ft.BaseControl):
                    walk(item)
        for child in getattr(node, "controls", None) or ():
            walk(child)

    walk(control)
    return " ".join(found)
