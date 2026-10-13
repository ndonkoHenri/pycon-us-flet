"""A More page rendered in a real Flet session, for the programme pages' tests (#105).

``tests/test_open_spaces.py``, ``tests/test_lightning_talks.py`` and
``tests/test_track_add_all.py`` render their screen over a feed with the store providers written out above it, as the other screens' tests
do (``tests/test_tracks.py``): ``AppScaffold`` is replaced by its actions over its
body, so both are in the tree, and ``page.navigate`` and the launcher are recorded.
Each row body's phrase is counted, so a test can tell which rows re-rendered.
"""

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

import flet as ft
import pytest
from flet.controls.context import _context_page
from flet.messaging.session import Session

from pycon_us.config import YearData
from pycon_us.favorites import Favorites, FavoritesCtx
from pycon_us.prefs import Prefs, PrefsCtx
from pycon_us.services import Services, ServicesCtx
from pycon_us.services.storage import Storage
from pycon_us.state import Conference, ConferenceCtx, ViewMemory
from pycon_us.theme import LIGHT_TOKENS, TokensCtx
from pycon_us.ui import session_rows
from tests.fakes import (
    MemoryClipboard,
    MemoryHaptics,
    MemoryLauncher,
    MemoryPrefs,
    MemorySemantics,
)
from tests.sessions import connection, settle


@dataclass
class Page:
    """A Flet session showing one More page, and what happened on it."""

    session: Session
    favorites: Favorites
    launcher: MemoryLauncher
    went: list[str]
    titles: list[str]
    services: Services
    """The services the page was given: its storage, haptics and memory."""
    rows: list[str] = field(default_factory=list)
    """The session ids whose row bodies ran, in order."""

    def find[T: ft.BaseControl](self, kind: type[T]) -> list[T]:
        return [c for c in self.session.index.values() if isinstance(c, kind)]

    def nodes(self, prefix: str) -> list[ft.Semantics]:
        return [
            c
            for c in self.find(ft.Semantics)
            if str(c.identifier or "").startswith(prefix)
        ]

    def node(self, identifier: str) -> ft.Semantics:
        found = [c for c in self.find(ft.Semantics) if c.identifier == identifier]
        assert len(found) == 1, identifier
        return found[0]

    def texts(self) -> list[str]:
        return [str(t.value) for t in self.find(ft.Text)]

    @property
    def snack_bars(self) -> list[ft.SnackBar]:
        return [
            d for d in self.session.page._dialogs.controls if isinstance(d, ft.SnackBar)
        ]

    async def click(self, control: ft.BaseControl) -> None:
        await self.session.dispatch_event(control._i, "click", None)
        await settle()

    async def event(self, control: ft.BaseControl, name: str, data: Any) -> None:
        await self.session.dispatch_event(control._i, name, data)
        await settle()


@asynccontextmanager
async def showing(
    screen: Callable[[], ft.Control],
    module: ModuleType,
    *,
    year: YearData,
    conference: Conference,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    view_path: str,
) -> AsyncIterator[Page]:
    """Render ``screen`` under the store providers; close the session on the way out.

    Args:
        screen: The page's component.
        module: Its module, whose ``AppScaffold`` is replaced.
        year: The year data the services carry.
        conference: The ``Conference`` store, with or without data.
        tmp_path: Where the storage writes.
        monkeypatch: To replace the scaffold, the View path and the phrase.
        view_path: The View's path, which the rows' links start from.
    """
    titles: list[str] = []

    def scaffold(
        *, title: str, body: ft.Control, actions: list[ft.Control] | None = None
    ) -> ft.Control:
        titles.append(title)
        return ft.Column([*(actions or []), body], expand=True)

    monkeypatch.setattr(module, "AppScaffold", scaffold)
    monkeypatch.setattr(ft, "use_view_path", lambda: view_path)
    storage = Storage(
        prefs=MemoryPrefs(), directory=tmp_path, year=year.conference.year
    )
    launcher = MemoryLauncher()
    svc = Services(
        year=year,
        storage=storage,
        memory=ViewMemory(),
        semantics=MemorySemantics(),
        haptics=MemoryHaptics(),
        launcher=launcher,
        clipboard=MemoryClipboard(),
    )
    favorites = Favorites()
    await favorites.load(storage)
    session = Session(connection())
    page = session.page
    went: list[str] = []
    monkeypatch.setattr(page, "navigate", went.append)
    shown = Page(session, favorites, launcher, went, titles, svc)
    phrase = session_rows.spoken_phrase

    def counted_phrase(labels: Any, view: Any, **kwargs: Any) -> str:
        shown.rows.append(view.session.id)
        return phrase(labels, view, **kwargs)

    # Each row body says its phrase once: counting the calls counts the bodies.
    monkeypatch.setattr(session_rows, "spoken_phrase", counted_phrase)

    @ft.component
    def Root() -> ft.Control:
        return ServicesCtx(
            svc,
            lambda: ConferenceCtx(
                conference,
                lambda: PrefsCtx(
                    Prefs(loaded=True),
                    lambda: FavoritesCtx(
                        favorites, lambda: TokensCtx(LIGHT_TOKENS, screen)
                    ),
                ),
            ),
        )

    _context_page.set(page)  # pyright: ignore[reportArgumentType]
    try:
        page.render(Root)
        session.get_page_patch()
        await settle()
        yield shown
    finally:
        session.close()
        await asyncio.sleep(0)
        _context_page.set(None)


def text_of(control: object) -> str:
    """The first ``Text`` value under ``control``, following ``content``."""
    while control is not None and not isinstance(control, ft.Text):
        control = getattr(control, "content", None)
    return str(control.value) if control is not None else ""
