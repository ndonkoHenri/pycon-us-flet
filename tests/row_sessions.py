"""The session rows harness: a list owner of ``SessionRow``s and ``NoticeRow``s (D-184).

``tests/test_session_rows.py`` tests the rows through it, and ``tests/test_sessions.py``
puts its ``Owner`` under the screens it opens to test ``showing()`` itself. The session
is ``tests/sessions.py``'s ``showing()``; the sessions are the recorded 2026 feed's.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import flet as ft
import pytest

from pycon_us.config import load_year
from pycon_us.favorites import use_favorites
from pycon_us.services import use_services
from pycon_us.state import Conference, use_conference
from pycon_us.theme import LIGHT_TOKENS
from pycon_us.ui.badges import use_favorite_toggle
from pycon_us.ui.semantics import semantics_key
from pycon_us.ui.session_rows import (
    NoticeRow,
    SessionRow,
    is_notice,
    use_session_views,
)
from tests.fakes import MemoryHaptics, MemoryPrefs
from tests.feeds import processed
from tests.sessions import Shown, showing

YEAR = load_year(2026)

TALK = "142"
"""A talk with one speaker: "Python for Humans - …", 10:30-11:00 AM, Grand Ballroom A."""

CHARLA = "76"
"""A charla: badges "Charla" and "En Español"."""

TUTORIAL = "19"
"""A tutorial that needs registration."""

NOTICE = "196"
"""Registration Desk Opens, 7:30 AM: a notice with a description."""

COFFEE = "break-Expo Hall AB-2026-05-15T08:00:00-07:00"
"""A collapsed break with nothing to read."""

LIST = (TALK, CHARLA, TUTORIAL, NOTICE, COFFEE)


@ft.component
def Owner(session_ids: tuple[str, ...]) -> ft.Control:
    """A list owner as the screens write one: it subscribes, its rows do not."""
    conference = use_conference()
    favorites = use_favorites()
    on_toggle = use_favorite_toggle(favorites)
    views = use_session_views(conference, session_ids, use_24h=False)
    info = use_services().year.conference
    return ft.Column(
        [
            NoticeRow(view, screen="test")
            if is_notice(view.session, info)
            else SessionRow(
                view,
                view.session.id in favorites.ids,
                on_toggle,
                LIGHT_TOKENS,
                screen="test",
            )
            for view in views
        ]
    )


@dataclass
class Rendered(Shown):
    """A Flet session showing ``Owner``, and what its rows did."""

    @property
    def prefs_service(self) -> MemoryPrefs:
        return cast(MemoryPrefs, self.services.storage.prefs)

    @property
    def haptics(self) -> MemoryHaptics:
        return cast(MemoryHaptics, self.services.haptics)

    @property
    def renders(self) -> list[str]:
        """The session ids whose row bodies ran, in order (S2's ``ROW_RENDERS``)."""
        return self.rows

    def star(self, session_id: str) -> ft.IconButton:
        button = self.node(f"test.favorite.{session_id}").content
        assert isinstance(button, ft.IconButton)
        return button

    def filled(self, session_id: str) -> bool:
        """Whether the session's star is drawn filled."""
        return self.star(session_id).icon == ft.Icons.STAR

    def notice(self, session_id: str) -> ft.Semantics:
        return self.node(f"test.notice.{semantics_key(session_id)}")

    async def tap_star(self, session_id: str) -> None:
        await self.click(self.star(session_id))


@asynccontextmanager
async def rendering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Rendered]:
    """Yield ``Owner(LIST)`` rendered outside a Router, under the store providers.

    The test module's ``rendered`` fixture enters it with its own ``tmp_path`` and
    ``monkeypatch``, as ``tests/session_detail.py``'s modules enter its ``rendering``.
    """
    async with showing(
        lambda: Owner(LIST),
        year=YEAR,
        conference=Conference(data=processed(2026), source="bundled", version=1),
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        view_path="",  # what ft.use_view_path() says outside a Router
    ) as shown:
        yield Rendered(**vars(shown))  # Shown's fields, as they are
