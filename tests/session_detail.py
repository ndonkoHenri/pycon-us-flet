"""The session detail harness: ``SessionDetail`` in a real Flet session (ux.md §5.5).

``tests/test_session.py`` and ``tests/test_session_extras.py`` share it, as
``tests/sessions.py`` serves the row tests. The store providers are written out above
the screen, ``AppScaffold`` is replaced by a column that keeps the title, the actions
and the body, and taps are dispatched clicks. The sessions are the recorded 2026
feed's.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

import flet as ft
import pytest
from flet.controls.context import _context_page
from flet.messaging.session import Session

from pycon_us import clock
from pycon_us.config import load_year
from pycon_us.favorites import Favorites, FavoritesCtx
from pycon_us.prefs import Prefs, PrefsCtx
from pycon_us.screens import session as screen
from pycon_us.services import Services, ServicesCtx
from pycon_us.services.storage import Storage
from pycon_us.state import Conference, ConferenceCtx, ViewMemory
from pycon_us.theme import LIGHT_TOKENS, TokensCtx
from tests.fakes import (
    MemoryClipboard,
    MemoryHaptics,
    MemoryLauncher,
    MemoryPrefs,
    MemorySemantics,
    MemoryShare,
)
from tests.feeds import processed
from tests.sessions import connection

YEAR = load_year(2026)
PACIFIC = ZoneInfo("America/Los_Angeles")
VIEW = "/schedule/session/x"
"""The View path the screen is rendered at: links push on top of it."""

TALK = "142"
"""Python for Humans, Sat May 16 10:30-11:00 AM, Grand Ballroom A; a public page."""

BREAK = (
    "break-Room 103ABC, Room 104AB, Room 104C, Grand Ballroom A, Grand Ballroom B"
    "-2026-05-16T10:05:00-07:00"
)
"""A break in five rooms with no one place to show (DATA-16)."""


@dataclass
class Detail:
    """A Flet session showing one ``SessionDetail``."""

    session: Session
    conference: Conference
    favorites: Favorites
    launcher: MemoryLauncher
    share: MemoryShare
    pushed: list[str]
    titles: list[str]
    reopen: Callable[[str | None], None]

    def nodes(self, identifier: str) -> list[ft.Semantics]:
        return [
            c
            for c in self.session.index.values()
            if isinstance(c, ft.Semantics) and c.identifier == identifier
        ]

    def node(self, identifier: str) -> ft.Semantics:
        (found,) = self.nodes(identifier)
        return found

    def text(self, identifier: str) -> list[str]:
        return words(self.node(identifier))

    async def settle(self) -> None:
        for _ in range(20):
            await asyncio.sleep(0)

    async def show(self, session_id: str | None) -> None:
        """Re-render the same Root with another id in place, or with no detail."""
        self.reopen(session_id)
        await self.settle()

    async def click(self, control: ft.Control) -> None:
        await self.session.dispatch_event(control._i, "click", None)
        await self.settle()

    @property
    def snack_bars(self) -> list[ft.SnackBar]:
        return [
            d for d in self.session.page._dialogs.controls if isinstance(d, ft.SnackBar)
        ]


type Render = Callable[[str], Awaitable[Detail]]


@asynccontextmanager
async def rendering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Render]:
    """Yield render(session_id): the detail of that session at ``VIEW``.

    Each test module's ``render`` fixture enters it with its own ``tmp_path`` and
    ``monkeypatch``; leaving it closes every session it rendered.
    """
    shown: list[tuple[Session, Services]] = []
    titles: list[str] = []

    def scaffold(
        *, title: str, body: ft.Control, actions: list[ft.Control] | None = None
    ) -> ft.Control:
        titles.append(title)
        return ft.Column([ft.Row(actions or []), body])

    monkeypatch.setattr(screen, "AppScaffold", scaffold)
    monkeypatch.setattr(ft, "use_view_path", lambda: VIEW)

    async def show(session_id: str) -> Detail:
        storage = Storage(prefs=MemoryPrefs(), directory=tmp_path, year=2026)
        launcher = MemoryLauncher()
        share = MemoryShare()
        svc = Services(
            year=YEAR,
            storage=storage,
            memory=ViewMemory(),
            semantics=MemorySemantics(),
            haptics=MemoryHaptics(),
            launcher=launcher,
            clipboard=MemoryClipboard(),
            share=share,
        )
        conference = Conference(data=processed(2026), source="bundled", version=1)
        favorites, prefs = Favorites(), Prefs(loaded=True)
        await favorites.load(storage)
        reopen: list[Callable[[str | None], None]] = []

        @ft.component
        def Root() -> ft.Control:
            # Detail.show() changes the id in place, or leaves the detail (None).
            shown_id, set_shown_id = ft.use_state(cast(str | None, session_id))
            reopen[:] = [set_shown_id]
            return ServicesCtx(
                svc,
                lambda: ConferenceCtx(
                    conference,
                    lambda: PrefsCtx(
                        prefs,
                        lambda: FavoritesCtx(
                            favorites,
                            lambda: TokensCtx(
                                LIGHT_TOKENS,
                                lambda: (
                                    screen.SessionDetail(shown_id)
                                    if shown_id is not None
                                    else ft.Text("Elsewhere")
                                ),
                            ),
                        ),
                    ),
                ),
            )

        flet_session = Session(connection())
        page = flet_session.page
        pushed: list[str] = []
        monkeypatch.setattr(page, "navigate", pushed.append)
        # Bound as Flet binds it while a handler runs; the test runs in a context of
        # its own (a task), so the binding goes with it.
        _context_page.set(page)  # pyright: ignore[reportArgumentType]
        shown.append((flet_session, svc))
        page.render(Root)
        flet_session.get_page_patch()
        detail = Detail(
            flet_session,
            conference,
            favorites,
            launcher,
            share,
            pushed,
            titles,
            lambda sid: reopen[0](sid),
        )
        await detail.settle()
        return detail

    try:
        yield show
    finally:
        for flet_session, svc in shown:
            svc.close()  # the status line's ticks end (D-147)
            flet_session.close()
        await asyncio.sleep(0)
        clock.set_test_now(None)


def words(control: ft.Control) -> list[str]:
    """The visible text under ``control`` in reading order, components and tiles included.

    Unlike ``trees.texts``, it reads a ``ListTile``'s string title and what a component
    (the status line) rendered.
    """
    found: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, ft.Control) and node.visible is False:
            return
        if isinstance(node, ft.Text):
            found.append(str(node.value))
        if isinstance(node, str):
            found.append(node)
            return
        if isinstance(node, ft.Component):
            body = node._b
            for child in body if isinstance(body, list) else [body]:
                walk(child)
        for name in ("content", "leading", "title", "subtitle", "trailing"):
            child = getattr(node, name, None)
            if isinstance(child, (ft.Control, str)) and not isinstance(node, ft.Text):
                walk(child)
        for child in getattr(node, "controls", None) or ():
            walk(child)

    walk(control)
    return found


def headings(detail: Detail) -> list[tuple[str, int | None]]:
    """The page's headings, in order, with their levels."""
    return [
        (" ".join(words(n)), n.heading_level)
        for n in detail.session.index.values()
        if isinstance(n, ft.Semantics) and n.header
    ]


def at(text: str) -> datetime:
    """An instant in conference time, e.g. ``at("2026-05-16 10:05")``."""
    return datetime.fromisoformat(text).replace(tzinfo=PACIFIC)
