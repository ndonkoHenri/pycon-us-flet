"""Give the focus back to the button that opened another app's window (D-372, #302).

A dialog, a sheet or a menu is a route of Flutter's `Navigator`, which gives the
screen reader's focus back to its opener by itself (D-225, D-242). The in-app browser,
the share sheet and a maps app are other windows, not routes: back from one, TalkBack's
focus was on no node, and a screen reader user started again from the top (WCAG 2.4.3).

`focus_back()` wraps the call that opens such a window. Once the app has left and
come back (`services.presence`), and `SETTLE_SECONDS` later, it calls the opener's
`focus()`: Flutter then reports the button as focused (`TYPE_VIEW_FOCUSED` on
Android), and TalkBack moves its focus there (F192). Only buttons have `focus()` at
the pin: a row (`ListTile`) and an overflow menu (`PopupMenuButton`) have none, so
their windows still return to no node until U182.

`star_of()` and `refocus_star()` serve the reminders primer (D-395): its sheet is
a route, but on Now the first star's add moves the session into Your next session,
so the star that opened it is replaced by the card's and Flutter has no node to give
the focus back to (D-225's "what keeps it working"); the card's star gets it instead.
"""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import flet as ft

from pycon_us.services import Services
from pycon_us.services.storage import SERVICE_ERRORS
from pycon_us.ui.semantics import semantics_key

logger = logging.getLogger(__name__)

LEAVE_WITHIN = 3.0
"""How long, in seconds, the app may take to leave once the call has returned: a
launch returns before the browser is up, a share once the sheet has closed. Past it,
nothing opened (no app for the link) and nothing waits for a return (`Presence`)."""

SETTLE_SECONDS = 1.0
"""How long after the return the focus moves, in seconds. TalkBack settles on the
app's window first, putting its own focus on the app bar's Back or on no node: a focus
sent before that is lost. On the Android 16 emulator, 0.5 s lost that race in 2 of 10
trips; 1 s won all 8 (F192). It also leaves time to draw a button re-enabled meanwhile
(Share is disabled while its sheet is up, and a disabled button takes no focus)."""


@runtime_checkable
class Focusable(Protocol):
    """A control that can take the focus: Flet's buttons at the pin (`focus()`)."""

    async def focus(self) -> None:
        """Move the focus to the control."""


@contextlib.asynccontextmanager
async def focus_back(
    svc: Services, opener: ft.BaseControl | None
) -> AsyncIterator[None]:
    """Wrap a call that opens another app's window; after it, focus `opener` again.

    Call it from the event handler. The focus moves only when the app has left and
    come back since the call began (`Presence.back_since()`): a window that never
    opened (a launch with no app for the link, a share that failed) leaves the focus
    where it is. It waits through the time the other window is up, so the caller's
    handler returns only then. An exception from the call passes through, and nothing
    is focused; nor is anything when the session closes meanwhile (D-147).

    The control focused is the one mounted on the return, found by the opener's id
    (`page.get_control()`): a render meanwhile (Share re-enabled, a feed refresh)
    builds a new control that takes over the id, and the event's own is left
    detached, its `focus()` refused (F192).

    Args:
        svc: The session's services: the app's presence.
        opener: The control that was tapped, the event's `control`; None to leave
            the focus alone. A control without `focus()` (a `ListTile`, U182) is
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


@dataclass(frozen=True)
class Star:
    """The star a session's add was tapped on, found before a render can replace it."""

    control: ft.IconButton
    session_id: str


def star_of(page: ft.Page, session_id: str) -> Star | None:
    """Return the session's star mounted on the top View, or None (D-30's star).

    Found by its identifier, `<screen>.favorite.<key>` (`FavoriteButton`): on Now
    a session's star is `now.favorite.<key>` in a section and
    `now.next.favorite.<key>` in the card, and a screen shows a session once. A
    View covered by another can show the same session (the Schedule under search):
    the top View is the one mounted last, since a View only ever goes on top.

    Args:
        page: The session's page.
        session_id: The session whose star to find.
    """
    suffix = f".favorite.{semantics_key(session_id)}"
    found = [
        (_view_order(control), button)
        for control in list(page.session.index.values())
        if isinstance(control, ft.Semantics)
        and str(control.identifier or "").endswith(suffix)
        and isinstance(button := control.content, ft.IconButton)
    ]
    if not found:
        return None
    _, button = max(found, key=lambda pair: pair[0])
    return Star(button, session_id)


def _view_order(control: ft.BaseControl) -> int:
    """The id of the `View` that holds `control`, which grows with each new View.

    -1 outside a View (a test's tree): then any of the controls found will do.
    """
    parent = control.parent
    while parent is not None and not isinstance(parent, ft.View):
        parent = parent.parent
    return -1 if parent is None else parent._i


async def refocus_star(svc: Services, page: ft.Page, star: Star) -> None:
    """Give the focus to the star that replaced `star`, once a sheet it opened closed.

    While `star` is mounted, nothing: Flutter's `Navigator` gives its node the
    focus back by itself, and a second focus would race it (D-225). When a render
    removed it (Now's first add, D-395), `SETTLE_SECONDS` later, after Flutter's own
    refocus has found no node, it focuses the session's star mounted then, if any.

    Args:
        svc: The session's services: whether the session has closed (D-147).
        page: The session's page.
        star: The star that was tapped, from `star_of()` before the add.
    """
    if page.get_control(star.control._i) is not None:
        return
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(svc.closed.wait(), SETTLE_SECONDS)
    if svc.closed.is_set() or (current := star_of(page, star.session_id)) is None:
        return
    try:
        await current.control.focus()
    except SERVICE_ERRORS as error:
        logger.info("Could not focus the star: %s", type(error).__name__)
