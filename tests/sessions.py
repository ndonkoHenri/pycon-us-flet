"""A real Flet session with no client, for tests that render components (D-153, D-184).

Flet's own component tests render this way: a ``Session`` on a connection that sends to
nothing (and, for dialogs, encodes each message as a transport does: ``ENCODE``),
``page.render(...)`` with the page bound as Flet binds it, and Flet's scheduler
re-rendering what changed.

Two levels, one module (#204, #253, #286):

- ``rendering(root)`` renders any component in a new session, or as the page's Views
  (``views=True``), as the app renders its Router.
- ``showing(screen, *modules, ...)`` renders a screen over a feed under the store
  providers (``provide()``) with the memory fakes' services (``memory_services()``):
  each module's ``AppScaffold`` is replaced by a row of its actions over its body (and
  its floating button under it), so all are in the tree, ``page.navigate`` is
  recorded and each row body is counted, each in the ``Shown`` of the screen it
  belongs to, however many are open. Every screen's tests use it (#286); what is one
  screen's own (a held clock, minute ticks, recorded scrolls) stays in its test
  module, in a ``Shown`` subclass (``kind``) that its stand-ins find with ``current()``.

It reaches into Flet internals (``_context_page``, ``Session.index``,
``Session.dispatch_event``, ``Control._i``, ``page._dialogs``, the msgpack encoder of
``messaging/protocol.py``): a Flet pin bump (D-81) that renames one breaks this module,
not the components: look here first.
"""

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import flet as ft
import msgpack
import pytest
from flet.controls.context import _context_page
from flet.messaging.connection import Connection
from flet.messaging.protocol import Message, configure_encode_object_for_msgpack
from flet.messaging.session import Session
from flet.pubsub.pubsub_hub import PubSubHub

from pycon_us.config import YearData
from pycon_us.core.row_views import SessionView
from pycon_us.favorites import Favorites, FavoritesCtx
from pycon_us.memory import ViewMemory
from pycon_us.prefs import Prefs, PrefsCtx
from pycon_us.services import Services, ServicesCtx
from pycon_us.services.storage import Storage
from pycon_us.services.storage import favorites as favorites_key
from pycon_us.state import Conference, ConferenceCtx
from pycon_us.theme import LIGHT_TOKENS, TokensCtx
from pycon_us.ui import session_rows
from tests.fakes import (
    MemoryClipboard,
    MemoryHaptics,
    MemoryLauncher,
    MemoryPrefs,
    MemorySemantics,
    MemoryShare,
)

_ENCODE = configure_encode_object_for_msgpack(ft.BaseControl)

ENCODE = False
"""Encode each message as a transport does. Off by default, since encoding a long list
costs time a timed test (a jump's wait) may not have on a loaded host; a test of
``ft.use_dialog`` turns it on (``monkeypatch.setattr(sessions, "ENCODE", True)``)."""


def pack(payload: object) -> None:
    """Encode ``payload`` as a transport does, and send the bytes nowhere (``ENCODE``).

    Encoding is what records the lists and fields a control was last sent with, which
    the next patch of that control is diffed against (``protocol.py``); a control that
    is only ever updated in place, such as the page's dialog list (``ft.use_dialog``),
    patches nothing until it has been encoded once.
    """
    if ENCODE:
        msgpack.packb(payload, default=_ENCODE)


def connection() -> Connection:
    """Return a connection to no client, encoding each message when ``ENCODE`` is on."""
    conn = Connection()
    conn.pubsubhub = PubSubHub()

    def send(message: Message) -> None:
        pack([message.action, message.body])

    conn.send_message = send  # pyright: ignore[reportAttributeAccessIssue]
    return conn


async def settle() -> None:
    """Let handlers, store writes, effects and Flet's re-renders run to the end."""
    for _ in range(20):
        await asyncio.sleep(0)


@asynccontextmanager
async def rendering(
    root: Callable[[], ft.Control],
    session: Session | None = None,
    *,
    views: bool = False,
) -> AsyncIterator[Session]:
    """Render the component ``root`` in a session; close it on the way out.

    Args:
        root: A component taking no arguments, usually the store providers around
            the component under test.
        session: The session to render in, when the caller prepares its page first
            (``showing()`` records ``page.navigate``); a new one by default.
        views: Render ``root`` as the page's Views (``page.render_views``), as the
            app renders its Router; else as the page's content.

    Yields:
        The session, with its first render applied and its first effects run.
    """
    session = session or Session(connection())
    page = session.page
    _context_page.set(page)  # pyright: ignore[reportArgumentType]
    try:
        if views:
            page.render_views(root)
        else:
            page.render(root)
        pack(session.get_page_patch())  # the REGISTER_CLIENT response's page
        await settle()
        yield session
    finally:
        session.close()
        await settle()
        # Not a token reset: a fixture may close it from another task's context.
        _context_page.set(None)


def find[T: ft.BaseControl](
    session: Session, kind: type[T], test: Callable[[T], bool] = lambda _: True
) -> list[T]:
    """Return the mounted controls of a type that pass ``test``, in no set order."""
    return [c for c in session.index.values() if isinstance(c, kind) and test(c)]


# ------------------------------------------------------------------ a screen over a feed


def memory_services(
    year: YearData, directory: Path, memory: ViewMemory | None = None
) -> Services:
    """Return a session's services with the memory fakes of ``tests/fakes.py``.

    Args:
        year: The year data the services carry.
        directory: Where the storage writes (a test's ``tmp_path``).
        memory: The view memory, when a test keeps one across sessions, as the app
            keeps it across a View rebuilt in a new session; a new one by default.
    """
    return Services(
        year=year,
        storage=Storage(
            prefs=MemoryPrefs(), directory=directory, year=year.conference.year
        ),
        memory=ViewMemory() if memory is None else memory,
        semantics=MemorySemantics(),
        haptics=MemoryHaptics(),
        launcher=MemoryLauncher(),
        clipboard=MemoryClipboard(),
        share=MemoryShare(),
    )


def provide(
    svc: Services,
    conference: Conference,
    prefs: Prefs,
    favorites: Favorites,
    body: Callable[[], ft.Control],
) -> ft.Control:
    """Return ``body`` under the store providers, in ``App``'s order.

    The light tokens' provider comes last, right around ``body``.
    """
    return ServicesCtx(
        svc,
        lambda: ConferenceCtx(
            conference,
            lambda: PrefsCtx(
                prefs,
                lambda: FavoritesCtx(favorites, lambda: TokensCtx(LIGHT_TOKENS, body)),
            ),
        ),
    )


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
    """
    _route(monkeypatch, modules)
    svc = memory_services(year, tmp_path, memory)
    if saved:
        await svc.storage.set(favorites_key(svc.storage.year), list(saved))
    if favorites is None:
        favorites = Favorites()
        await favorites.load(svc.storage)
    prefs = Prefs(loaded=True) if prefs is None else prefs
    session = Session(connection())
    if route is not None:
        session.page.route = route
    shown = kind(session, svc, conference, prefs, favorites, [], [], view_path)
    monkeypatch.setattr(session.page, "navigate", shown.went.append)
    _OPEN[session.page] = shown

    @ft.component
    def Root() -> ft.Control:
        return provide(svc, conference, prefs, favorites, screen)

    try:
        async with rendering(Root, session, views=view_path is None):
            yield shown
    finally:
        svc.close()  # a status line's ticks end (D-147)
        del _OPEN[session.page]


def text_of(control: object) -> str:
    """The first ``Text`` value under ``control``, following ``content``."""
    while control is not None and not isinstance(control, ft.Text):
        control = getattr(control, "content", None)
    return str(control.value) if control is not None else ""


def menu_text(item: ft.PopupMenuItem) -> ft.Text:
    """An overflow item's label: the ``Text`` of ``menu_item()``'s tile (D-233).

    Under the identifier's ``Semantics``, the tile's title, or the link's
    ``Semantics`` around it.
    """
    tile = cast(ft.ListTile, cast(ft.Semantics, item.content).content)
    title = tile.title
    return cast(ft.Text, title.content if isinstance(title, ft.Semantics) else title)
