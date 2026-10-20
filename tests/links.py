"""The app's own Views in a real Flet session, for the deep-link tests (P2-79, #439).

A deep link's path is an internal route (D-21, D-269): cold, it is the session's start
route; warm, a route change. ``open_at`` renders the app's ``ROUTES`` and screens with
``tests/sessions.py``'s ``showing()`` (``view_path=None``: a real Router, rendered as
the page's Views, as ``main.py`` renders it) over the 2026 feed, starting at a
location. ``Shown.go()`` changes the route as Flutter does for a warm link or a
``page.navigate``, and ``Shown.back()`` presses Back as the system does:

* a View that declines its pop (``can_pop=False``) is asked through
  ``on_confirm_pop`` (D-142, D-270);
* a View that can pop is popped by Flutter's Navigator, which reaches ``main.py``'s
  ``page.on_view_pop`` and so ``parent_of()`` (D-141, D-208, F46);
* Back on a one-View stack that can pop (Now) leaves the app (F29).

The test modules assign the fixture to their own name, as ``tests/chrome.py``'s are
(``open_at = links.open_at``).
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import flet as ft
import pytest

from pycon_us.config import load_year
from pycon_us.locations import parent_of
from pycon_us.routes import ROUTES
from pycon_us.state import Conference
from tests import sessions
from tests.feeds import processed

YEAR = load_year(2026)
DATA = processed(2026)

EXIT = "exit"
"""What ``Shown.back()`` returns when Back leaves the app (F29)."""


class Shown(sessions.Shown):
    """The app's Views in a session, with Back and route changes as Flutter sends them."""

    @property
    def page(self) -> ft.Page:
        """The session's page."""
        return self.session.page  # pyright: ignore[reportReturnType]

    def views(self) -> list[ft.View]:
        """The Views the Router stacks, bottom first."""
        node: Any = self.page.views
        while not isinstance(node, list):  # the providers lead to the Router's list
            node = node._b
        found = []
        for view in node:
            while not isinstance(view, ft.View):
                view = view._b
            found.append(view)
        return found

    def routes(self) -> list[str]:
        """The stacked Views' routes (their keys: ``/`` for every root), bottom first."""
        return [str(view.route) for view in self.views()]

    def has(self, identifier: str) -> bool:
        """Whether a mounted semantics node has ``identifier``."""
        return bool(self.nodes(identifier))

    async def go(self, location: str) -> None:
        """Change the route as a warm link or ``page.navigate`` does: set, then heard.

        Flutter updates ``page.route`` before it sends the event (``flet_backend.dart``,
        ``_sendRouteChangeEvent``); the handler is whatever the page has, the Router's
        or the one ``ui.modals`` put in front of it.
        """
        self.went.append(location)
        self.page.route = location
        handler: Any = self.page.on_route_change
        handler(SimpleNamespace(route=location))
        await self.settle()

    async def back(self) -> str:
        """Press Back once, as the system does; return where it went, or ``EXIT``."""
        views = self.views()
        top = views[-1]
        if not top.can_pop:
            confirmed: list[bool] = []

            async def confirm_pop(should_pop: bool) -> None:
                confirmed.append(should_pop)

            handler: Any = top.on_confirm_pop
            control = SimpleNamespace(confirm_pop=confirm_pop)
            await handler(SimpleNamespace(control=control))
            await self.settle()
            assert confirmed == [False]  # the View stays; the handler navigated
            return self.went[-1]
        if len(views) == 1:
            return EXIT  # nothing to pop: the activity finishes (F29)
        await self.go(parent_of(str(top.route), self.memory.search_base))
        return self.went[-1]


type Open = Callable[..., Awaitable[Shown]]


@pytest.fixture
async def open_at(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Open]:
    """Provide ``open_at(location)``: the app started at a location, as a cold link.

    ``page.navigate`` becomes what Flutter does next: the route changes and the page
    hears of it (``Shown.go()``). ``memory`` passes a ``ViewMemory`` that an earlier
    session of the process left (D-143, F29).
    """
    async with AsyncExitStack() as stack:

        async def open_(location: str, **kwargs: Any) -> Shown:
            shown = await stack.enter_async_context(
                sessions.showing(
                    lambda: ft.Router(ROUTES, manage_views=True),
                    year=YEAR,
                    conference=Conference(data=DATA, source="bundled", version=1),
                    tmp_path=tmp_path,
                    monkeypatch=monkeypatch,
                    view_path=None,
                    route=location,
                    kind=Shown,
                    **kwargs,
                )
            )

            def navigate(target: str) -> None:
                asyncio.get_running_loop().create_task(shown.go(target))

            monkeypatch.setattr(shown.page, "navigate", navigate)
            return shown

        yield open_
