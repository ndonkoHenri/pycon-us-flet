"""A real Flet session with no client, for tests that render components (D-153, D-184).

Flet's own component tests render this way: a ``Session`` on a connection that sends to
nothing (and, for dialogs, encodes each message as a transport does: ``ENCODE``),
``page.render(...)`` with the page bound as Flet binds it, and Flet's scheduler
re-rendering what changed.
``tests/test_session_rows.py``, ``tests/test_schedule.py`` and
``tests/test_my_schedule.py`` use it. It reaches into Flet internals
(``_context_page``, ``Session.index``, ``Session.dispatch_event``, the msgpack encoder
of ``messaging/protocol.py``): a Flet pin bump (D-81) that renames one breaks this
module, not the components: look here first.
"""

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import flet as ft
import msgpack
from flet.controls.context import _context_page
from flet.messaging.connection import Connection
from flet.messaging.protocol import Message, configure_encode_object_for_msgpack
from flet.messaging.session import Session
from flet.pubsub.pubsub_hub import PubSubHub

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
    """Return a connection to no client; it encodes each message when ``ENCODE`` is on."""
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
async def rendering(root: Callable[[], ft.Control]) -> AsyncIterator[Session]:
    """Render the component ``root`` in a new session; close it on the way out.

    Args:
        root: A component taking no arguments, usually the store providers around
            the component under test.

    Yields:
        The session, with its first render applied and its first effects run.
    """
    session = Session(connection())
    page = session.page
    _context_page.set(page)  # pyright: ignore[reportArgumentType]
    try:
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
