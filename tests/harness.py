"""The screen harness: a screen over a feed in a real Flet session (#253, #286, #623).

``showing(screen, *modules, ...)`` renders a screen over a feed under the store
providers (``tests/sessions.py``'s ``provide()``) with the memory fakes' services
(``memory_services()``): each module's ``AppScaffold`` is replaced by a row of its
actions over its body (and its floating button under it), so all are in the tree,
``page.navigate`` is recorded and each row body is counted, each in the ``Shown`` of the
screen it belongs to, however many are open. Every screen's tests use it (#286); what
is one screen's own (a held clock, minute ticks, recorded scrolls) stays in its test
module, in a ``Shown`` subclass (``kind``) that its stand-ins find with ``current()``.

Like ``tests/sessions.py``, it reaches into Flet internals (``_context_page``,
``Session.index``, ``Session.dispatch_event``, ``Control._i``, ``page._dialogs``): a
Flet pin bump (D-81) that renames one breaks these two modules, not the components.
"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import flet as ft
import pytest
from flet.controls.context import _context_page
from flet.messaging.session import Session

from pycon_us.account import Account
from pycon_us.change_log import ChangeLog
from pycon_us.config import YearData
from pycon_us.core.row_views import SessionView
from pycon_us.favorites import Favorites
from pycon_us.layout import Layout
from pycon_us.memory import ViewMemory
from pycon_us.prefs import Prefs
from pycon_us.services import Services
from pycon_us.services.private_api import PrivateApi
from pycon_us.services.storage import Storage
from pycon_us.services.storage import favorites as favorites_key
from pycon_us.state import Conference
from pycon_us.ui import session_rows
from tests.fakes import (
    MemoryLauncher,
)
from tests.sessions import connection, find, memory_services, provide, rendering, settle


@dataclass
class Shown:
    """A Flet session showing one screen, and what happened on it."""

    session: Session
    services: Services
    """The services the screen was given: its storage, haptics, launcher and memory."""
    conference: Conference
    prefs: Prefs
    favorites: Favorites
    went: list[str]
    """What ``page.navigate`` was asked for, in order."""
    titles: list[str]
    """The titles ``AppScaffold`` was given, in order."""
    view_path: str | None
    """What ``ft.use_view_path()`` answers on this screen; None: its Router answers."""
    rows: list[str] = field(default_factory=list)
    """The session ids whose row bodies (sessions and notices) ran, in order."""
    retaps: list[Callable[[], object] | None] = field(default_factory=list)
    """The re-tap action ``AppScaffold`` was given on each render, in order."""
    change_log: ChangeLog = field(default_factory=ChangeLog)
    """The ``ChangeLog`` store the screen was given: empty unless the test filled it."""
    layout: Layout = field(default_factory=Layout)
    """The ``Layout`` store the screen was given: a phone's in portrait, to turn."""

    @property
    def launcher(self) -> MemoryLauncher:
        """The in-memory launcher that records each URL the screen opened."""
        return cast(MemoryLauncher, self.services.launcher)

    @property
    def memory(self) -> ViewMemory:
        """The view memory the screen was given."""
        return self.services.memory

    @property
    def storage(self) -> Storage:
        """The storage the screen was given, writing under the test's ``tmp_path``."""
        return self.services.storage

    def find[T: ft.BaseControl](self, kind: type[T]) -> list[T]:
        """Return the screen's mounted controls of a type, in no set order."""
        return find(self.session, kind)

    def nodes(self, key: str) -> list[ft.Semantics]:
        """The ``Semantics`` that ``key`` names, in no set order (D-33's identifiers).

        A key ending in a dot names a family: ``"track.session."`` finds every row's
        node. Any other key is a whole identifier: ``"session.room"`` finds the room
        tile's node, never the folded rooms' ``"session.room.<key>"``.
        """
        if key.endswith("."):
            return find(
                self.session,
                ft.Semantics,
                lambda c: str(c.identifier or "").startswith(key),
            )
        return find(self.session, ft.Semantics, lambda c: c.identifier == key)

    def node(self, identifier: str) -> ft.Semantics:
        """The mounted ``Semantics`` with this identifier: one, and current."""
        found = find(self.session, ft.Semantics, lambda c: c.identifier == identifier)
        assert len(found) == 1, identifier
        return found[0]

    def texts(self) -> list[str]:
        """Return the value of every mounted ``Text``, in no set order."""
        return [str(t.value) for t in self.find(ft.Text)]

    @property
    def snack_bars(self) -> list[ft.SnackBar]:
        """The ``SnackBar``s in the page's dialog list, open or closed."""
        return [
            d for d in self.session.page._dialogs.controls if isinstance(d, ft.SnackBar)
        ]

    async def settle(self) -> None:
        """Let handlers, store writes, effects and re-renders run to the end."""
        await settle()

    async def click(self, control: ft.BaseControl) -> None:
        """Dispatch a click to ``control`` as the client would; let it run out."""
        await self.event(control, "click", None)

    async def event(self, control: ft.BaseControl, name: str, data: Any = None) -> None:
        """Dispatch an event to ``control`` as the client would; let it run out."""
        await self.session.dispatch_event(control._i, name, data)
        await settle()


_OPEN: dict[ft.Page, Shown] = {}
"""The screens ``showing()`` has open, by page: a test may open several at once."""


def _shown_now() -> Shown | None:
    """The open screen whose session is rendering or handling an event now.

    Flet binds a session's page to the context for each of its renders and events
    (``_context_page``: its scheduler task, ``Session.dispatch_event``), so the page in
    the context names the screen a scaffold, a View path or a row body belongs to.
    """
    page = _context_page.get()
    return _OPEN.get(page) if page is not None else None


def current[S: Shown](kind: type[S]) -> S:
    """The open screen whose session is rendering or handling an event now.

    For a test module's own stand-ins (a recorded scroll, a counted slot): each
    records in the ``Shown`` of the screen that called it, however many are open.

    Args:
        kind: The ``Shown`` subclass the screen was opened with (``showing(kind=)``).
    """
    shown = _shown_now()
    assert isinstance(shown, kind), "no screen of that kind is rendering now"
    return shown


def _scaffold(
    *,
    title: str,
    body: ft.Control,
    actions: list[ft.Control] | None = None,
    on_retap: Callable[[], object] | None = None,
    fab: ft.FloatingActionButton | None = None,
) -> ft.Control:
    """Stand in for ``AppScaffold``: the actions in a row, the body, the button under.

    The row holds the actions as an app bar does; the title and the re-tap action are
    recorded in the ``Shown`` of the screen that rendered it.
    """
    if shown := _shown_now():
        shown.titles.append(title)
        shown.retaps.append(on_retap)
    return ft.Column(
        [ft.Row(actions or []), body, *([fab] if fab else [])], expand=True
    )


class _RowCounter:
    """A row phrase that appends each row body's id to its own screen's ``rows``.

    Each session or notice row body says its phrase once: counting the calls counts
    the bodies (S2's ``ROW_RENDERS``, D-153).
    """

    def __init__(self, phrase: Callable[..., str]) -> None:
        """Wrap the row phrase function ``phrase``, which it still calls."""
        self.phrase = phrase

    def __call__(self, *args: Any, **kwargs: Any) -> str:
        """Record the row's session id in its screen's ``rows``, then say the phrase."""
        if shown := _shown_now():
            shown.rows.append(cast(SessionView, args[-1]).session.id)
        return self.phrase(*args, **kwargs)


def _route(monkeypatch: pytest.MonkeyPatch, modules: tuple[ModuleType, ...]) -> None:
    """Send each scaffold, View path and row body to the screen it belongs to.

    One stand-in per name, installed once, routing by the session in the context: a
    stand-in per screen would chain the second screen's records through the first's.
    """
    for module in modules:
        monkeypatch.setattr(module, "AppScaffold", _scaffold)
    if not isinstance(session_rows.spoken_phrase, _RowCounter):
        for name in ("spoken_phrase", "notice_phrase"):
            monkeypatch.setattr(
                session_rows, name, _RowCounter(getattr(session_rows, name))
            )
        use_view_path = ft.use_view_path

        def view_path() -> str:
            shown = _shown_now()
            if shown is None or shown.view_path is None:
                return use_view_path()
            return shown.view_path

        monkeypatch.setattr(ft, "use_view_path", view_path)


@asynccontextmanager
async def showing[S: Shown = Shown](
    screen: Callable[[], ft.Control],
    *modules: ModuleType,
    year: YearData,
    conference: Conference,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    view_path: str | None,
    prefs: Prefs | None = None,
    favorites: Favorites | None = None,
    saved: tuple[str, ...] = (),
    memory: ViewMemory | None = None,
    route: str | None = None,
    kind: Callable[..., S] = Shown,
    change_log: ChangeLog | None = None,
    layout: Layout | None = None,
    account: Account | None = None,
    private_api: PrivateApi | None = None,
) -> AsyncIterator[S]:
    """Render ``screen`` under the store providers; close the session on the way out.

    Args:
        screen: The screen's component, or a component around it.
        *modules: The modules whose ``AppScaffold`` is replaced: the screen's.
        year: The year data the services carry.
        conference: The ``Conference`` store, with or without data.
        tmp_path: Where the storage writes.
        monkeypatch: To replace the scaffold, the View path and the phrases.
        view_path: The View's path, which the rows' links start from; None when
            ``screen`` is a real ``ft.Router``, which answers it: the screen is then
            rendered as the page's Views, as the app renders it.
        prefs: The ``Prefs`` store, for other settings; by default a loaded one with
            the defaults.
        favorites: The ``Favorites`` store as the test set it up (not loaded yet,
            say); by default a new one, loaded from the storage.
        saved: The session ids the storage holds as favourites before the screen
            opens, as an earlier session left them.
        memory: The view memory, when the test keeps one across sessions.
        route: The page's route before the first render, for a screen that reads
            its query (a room's highlight); the page's own by default.
        kind: What makes the ``Shown``: a test module's subclass that adds what is
            its screen's own, or a ``functools.partial`` of one.
        change_log: The ``ChangeLog`` store, with the batches the test recorded; an
            empty one by default.
        layout: The ``Layout`` store, for a test that turns the window; a phone's in
            portrait by default.
        account: The ``Account`` store, for a screen that signs in or shows who is
            signed in; a signed-out one by default.
        private_api: The services' private-API holder, for a screen that talks to
            the mock (its transport); one without a client by default.
    """
    _route(monkeypatch, modules)
    svc = memory_services(year, tmp_path, memory)
    if private_api is not None:
        svc = replace(svc, private_api=private_api)
    if saved:
        await svc.storage.set(favorites_key(svc.storage.year), list(saved))
    if favorites is None:
        favorites = Favorites()
        await favorites.load(svc.storage)
    prefs = Prefs(loaded=True) if prefs is None else prefs
    session = Session(connection())
    if route is not None:
        session.page.route = route
    change_log = ChangeLog() if change_log is None else change_log
    layout = Layout() if layout is None else layout
    shown = kind(
        session,
        svc,
        conference,
        prefs,
        favorites,
        [],
        [],
        view_path,
        change_log=change_log,
        layout=layout,
    )
    monkeypatch.setattr(session.page, "navigate", shown.went.append)
    _OPEN[session.page] = shown

    @ft.component
    def Root() -> ft.Control:
        return provide(
            svc, conference, prefs, favorites, screen, change_log, layout, account
        )

    try:
        async with rendering(Root, session, views=view_path is None):
            yield shown
    finally:
        svc.close()  # a status line's ticks end (D-147)
        # ...at their next turn of the loop: a tick task still pending holds its
        # component, and with it the page, until it has run (use_recent_changes()).
        await settle()
        del _OPEN[session.page]
