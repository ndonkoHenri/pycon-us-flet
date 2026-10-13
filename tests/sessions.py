"""A real Flet session with no client, for tests that render components (D-153, D-184).

Flet's own component tests render this way: a ``Session`` on a connection that sends to
nothing, ``page.render(...)`` with the page bound as Flet binds it, and Flet's scheduler
re-rendering what changed. ``tests/test_session_rows.py``, ``tests/test_schedule.py``
and ``tests/test_my_schedule.py`` use it. It reaches into Flet internals
(``_context_page``, ``Session.index``, ``Session.dispatch_event``): a Flet pin bump
(D-81) that renames one breaks this module, not the components: look here first.
"""

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import flet as ft
from flet.controls.context import _context_page
from flet.messaging.connection import Connection
from flet.messaging.session import Session
from flet.pubsub.pubsub_hub import PubSubHub


def connection() -> Connection:
    """Return a connection to no client, as Flet's own component tests use."""
    conn = Connection()
    conn.pubsubhub = PubSubHub()
    conn.send_message = lambda message: None  # pyright: ignore[reportAttributeAccessIssue]
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
        session.get_page_patch()
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
