"""A real Flet session with no client, for tests that render components (D-153, D-184).

Flet's own component tests render this way: a `Session` on a connection that sends to
nothing (and, for dialogs, encodes each message as a transport does: `ENCODE`),
`page.render(...)` with the page bound as Flet binds it, and Flet's scheduler
re-rendering what changed.

Two levels, two modules (#204, #253, #286, #623):

- `rendering(root)`, here, renders any component in a new session, or as the page's
  Views (`views=True`), as the app renders its Router; `provide()` puts the store
  providers around it and `memory_services()` gives the memory fakes' services.
- `showing(screen, *modules, ...)`, in `tests/harness.py`, renders a screen over a
  feed with them, each in the `Shown` of the screen it belongs to.

It reaches into Flet internals (`_context_page`, `Session.index`, the msgpack
encoder of `messaging/protocol.py`), as `tests/harness.py` does: a Flet pin bump
(D-81) that renames one breaks these two modules, not the components: look here first.
"""

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

import flet as ft
import msgpack
from flet.controls.context import _context_page
from flet.messaging.connection import Connection
from flet.messaging.protocol import Message, configure_encode_object_for_msgpack
from flet.messaging.session import Session
from flet.pubsub.pubsub_hub import PubSubHub

from pycon_us.account import Account, AccountCtx
from pycon_us.change_log import ChangeLog, ChangeLogCtx
from pycon_us.config import YearData
from pycon_us.favorites import Favorites, FavoritesCtx
from pycon_us.layout import Layout, LayoutCtx
from pycon_us.memory import ViewMemory
from pycon_us.prefs import Prefs, PrefsCtx
from pycon_us.services import Services, ServicesCtx
from pycon_us.services.storage import Storage
from pycon_us.staff import Staff, StaffCtx
from pycon_us.state import Conference, ConferenceCtx
from pycon_us.theme import LIGHT_TOKENS, TokensCtx
from tests.fakes import (
    MemoryClipboard,
    MemoryFilePicker,
    MemoryHaptics,
    MemoryLauncher,
    MemoryPrefs,
    MemorySemantics,
    MemoryShare,
    MemoryWakelock,
)

_ENCODE = configure_encode_object_for_msgpack(ft.BaseControl)

ENCODE = False
"""Encode each message as a transport does. Off by default, since encoding a long list
costs time a timed test (a jump's wait) may not have on a loaded host; a test of
`ft.use_dialog` turns it on (`monkeypatch.setattr(sessions, "ENCODE", True)`)."""


def pack(payload: object) -> None:
    """Encode `payload` as a transport does, and send the bytes nowhere (`ENCODE`).

    Encoding is what records the lists and fields a control was last sent with, which
    the next patch of that control is diffed against (`protocol.py`); a control that
    is only ever updated in place, such as the page's dialog list (`ft.use_dialog`),
    patches nothing until it has been encoded once.
    """
    if ENCODE:
        msgpack.packb(payload, default=_ENCODE)


def connection() -> Connection:
    """Return a connection to no client, encoding each message when `ENCODE` is on."""
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
    """Render the component `root` in a session; close it on the way out.

    Args:
        root: A component taking no arguments, usually the store providers around
            the component under test.
        session: The session to render in, when the caller prepares its page first
            (`showing()` records `page.navigate`); a new one by default.
        views: Render `root` as the page's Views (`page.render_views`), as the
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
    """Return the mounted controls of a type that pass `test`, in no set order."""
    return [c for c in session.index.values() if isinstance(c, kind) and test(c)]


# ------------------------------------------------------------------ a screen over a feed


def memory_services(
    year: YearData, directory: Path, memory: ViewMemory | None = None
) -> Services:
    """Return a session's services with the memory fakes of `tests/fakes.py`.

    Args:
        year: The year data the services carry.
        directory: Where the storage writes (a test's `tmp_path`).
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
        file_picker=MemoryFilePicker(),
        wakelock=MemoryWakelock(),
    )


def provide(
    svc: Services,
    conference: Conference,
    prefs: Prefs,
    favorites: Favorites,
    body: Callable[[], ft.Control],
    change_log: ChangeLog | None = None,
    layout: Layout | None = None,
    account: Account | None = None,
    staff: Staff | None = None,
) -> ft.Control:
    """Return `body` under the store providers, in `App`'s order.

    The change log is an empty one unless the test gives its own, the account a
    signed-out one and the staff outbox's store an empty one.

    The layout is a phone's (`Layout()`: under 600 dp, the bottom bar) unless the
    test gives its own, to turn, and the light tokens' provider comes last, right
    around `body`.
    """
    return ServicesCtx(
        svc,
        lambda: ConferenceCtx(
            conference,
            lambda: PrefsCtx(
                prefs,
                lambda: FavoritesCtx(
                    favorites,
                    lambda: AccountCtx(
                        Account() if account is None else account,
                        lambda: StaffCtx(
                            Staff() if staff is None else staff,
                            lambda: ChangeLogCtx(
                                ChangeLog() if change_log is None else change_log,
                                lambda: LayoutCtx(
                                    Layout() if layout is None else layout,
                                    lambda: TokensCtx(LIGHT_TOKENS, body),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )


def text_of(control: object) -> str:
    """The first `Text` value under `control`, following `content`."""
    while control is not None and not isinstance(control, ft.Text):
        control = getattr(control, "content", None)
    return str(control.value) if control is not None else ""


def menu_text(item: ft.PopupMenuItem) -> ft.Text:
    """An overflow item's label: the `Text` of `menu_item()`'s tile (D-233).

    Under the identifier's `Semantics`, the tile's title, or the link's
    `Semantics` around it.
    """
    tile = cast(ft.ListTile, cast(ft.Semantics, item.content).content)
    title = tile.title
    return cast(ft.Text, title.content if isinstance(title, ft.Semantics) else title)
