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
from typing import Protocol

from pycon_us.services import Services
from pycon_us.services.storage import SERVICE_ERRORS

logger = logging.getLogger(__name__)

LEAVE_WITHIN = 3.0
"""How long, in seconds, the app may take to leave once the call has returned: a
launch returns before the browser is up, a share once the sheet has closed. Past it,
nothing opened (no app for the link) and nothing waits for a return (``Presence``)."""

SETTLE_SECONDS = 0.5
"""How long after the return the focus moves, in seconds, so the button re-enabled
meanwhile (Share is disabled while its sheet is up, and a disabled button takes no
focus) has been drawn, and TalkBack is back on the app's window. #302's throwaway
build, which waited for no return, moved nothing 0.5 s after the share call and moved
both focuses 2.5 s after it (F192)."""


class Focusable(Protocol):
    """A control that can take the focus: Flet's buttons at the pin (``focus()``)."""

    async def focus(self) -> None:
        """Move the focus to the control."""


@contextlib.asynccontextmanager
async def focus_back(svc: Services, opener: Focusable | None) -> AsyncIterator[None]:
    """Wrap a call that opens another app's window; after it, focus ``opener`` again.

    The focus moves only when the app has left and come back since the call began
    (``Presence.back_since()``): a window that never opened (a launch with no app for
    the link, a share that failed) leaves the focus where it is. It waits through
    the time the other window is up, so the caller's handler returns only then. An
    exception from the call passes through, and nothing is focused.

    Args:
        svc: The session's services: the app's presence.
        opener: The button that was tapped (the event's ``control``); None for a
            control without ``focus()``, which is left as it is (U182).
    """
    returns = svc.presence.returns
    yield
    if opener is None:
        return
    if not await svc.presence.back_since(returns, leave_within=LEAVE_WITHIN):
        return
    await asyncio.sleep(SETTLE_SECONDS)
    try:
        await opener.focus()
    except SERVICE_ERRORS as error:
        # Gone from the page meanwhile (RuntimeError), or no answer: nothing to say.
        logger.info("Could not give the focus back: %s", type(error).__name__)
