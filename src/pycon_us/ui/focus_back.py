"""Give the focus back to the button that opened another app's window (D-372, #302).

A dialog, a sheet or a menu is a route of Flutter's `Navigator`, which gives the
screen reader's focus back to its opener by itself (D-225, D-242). The in-app browser,
the share sheet and a maps app are other windows, not routes: back from one, TalkBack's
focus was on no node, and a screen reader user started again from the top (WCAG 2.4.3).

``focus_back()`` wraps the call that opens such a window. Once the app has left and
come back (``services.presence``), and ``SETTLE_SECONDS`` later, it calls the opener's
``focus()``: Flutter then reports the button as focused (``TYPE_VIEW_FOCUSED`` on
Android), and TalkBack moves its focus there (F192). Only buttons have ``focus()`` at
the pin: a row (``ListTile``) and an overflow menu (``PopupMenuButton``) have none, so
their windows still return to no node until U182.
"""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

import flet as ft

from pycon_us.services import Services
from pycon_us.services.storage import SERVICE_ERRORS

logger = logging.getLogger(__name__)

LEAVE_WITHIN = 3.0
"""How long, in seconds, the app may take to leave once the call has returned: a
launch returns before the browser is up, a share once the sheet has closed. Past it,
nothing opened (no app for the link) and nothing waits for a return (``Presence``)."""

SETTLE_SECONDS = 1.0
"""How long after the return the focus moves, in seconds. TalkBack settles on the
app's window first, putting its own focus on the app bar's Back or on no node: a focus
sent before that is lost. On the Android 16 emulator, 0.5 s lost that race in 2 of 10
trips; 1 s won all 8 (F192). It also leaves time to draw a button re-enabled meanwhile
(Share is disabled while its sheet is up, and a disabled button takes no focus)."""


@runtime_checkable
class Focusable(Protocol):
    """A control that can take the focus: Flet's buttons at the pin (``focus()``)."""

    async def focus(self) -> None:
        """Move the focus to the control."""


@contextlib.asynccontextmanager
async def focus_back(
    svc: Services, opener: ft.BaseControl | None
) -> AsyncIterator[None]:
    """Wrap a call that opens another app's window; after it, focus ``opener`` again.

    Call it from the event handler. The focus moves only when the app has left and
    come back since the call began (``Presence.back_since()``): a window that never
    opened (a launch with no app for the link, a share that failed) leaves the focus
    where it is. It waits through the time the other window is up, so the caller's
    handler returns only then. An exception from the call passes through, and nothing
    is focused; nor is anything when the session closes meanwhile (D-147).

    The control focused is the one mounted on the return, found by the opener's id
    (``page.get_control()``): a render meanwhile (Share re-enabled, a feed refresh)
    builds a new control that takes over the id, and the event's own is left
    detached, its ``focus()`` refused (F192).

    Args:
        svc: The session's services: the app's presence.
        opener: The control that was tapped, the event's ``control``; None to leave
            the focus alone. A control without ``focus()`` (a ``ListTile``, U182) is
            left alone too.
    """
    page = ft.context.page
    returns = svc.presence.returns
    yield
    if opener is None:
        return
    if not await svc.presence.back_since(returns, leave_within=LEAVE_WITHIN):
        return
    # Sleeps SETTLE_SECONDS, or less when the session closes meanwhile: a replaced
    # session stops its work (D-147), and a focus() sent after its close would wait
    # for an answer that never comes.
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(svc.closed.wait(), SETTLE_SECONDS)
    if svc.closed.is_set():
        return
    try:
        current = page.get_control(opener._i)
        if not isinstance(current, Focusable):
            return  # gone from the page meanwhile, or never focusable
        await current.focus()
    except SERVICE_ERRORS as error:
        # No answer from Flutter, or detached meanwhile: nothing to say.
        logger.info("Could not give the focus back: %s", type(error).__name__)
