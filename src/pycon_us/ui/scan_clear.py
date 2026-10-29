"""Clearing the scan screen's result: after a while, and in the background (#762).

A result about a person is on a phone that is often held up or handed around (O-7,
MASK-05). A tool may ask ``ScanScreen`` to clear its result ``clear_after`` seconds
after it shows, which is when the reply arrives, never when the request leaves (Ionic
started its 5 s when the request left, so a slow reply could vanish unseen), and when
the app goes to the background (``Services.background``, set on ``pause``, D-420). The
panel then says "Ready to scan" again and the result leaves the screen's state, not
just the view; a reply that lands while the app is in the background is not shown at
all (the tool's own work, such as recording, still completes). A clear is no result: no haptics, no announcement, and the panel is no
live region while it is empty, so TalkBack says nothing either.

Flet has no secure-screen flag (``FLAG_SECURE``, the iOS app-switcher blur; U270), and
the OS may take its app-switcher snapshot before the clear lands: this is the interim.
"""

import asyncio
from collections.abc import Callable

import flet as ft
from flet.components.hooks.use_ref import MutableRef

from pycon_us.services import Services, use_services
from pycon_us.services.errors import report_errors

type Action = Callable[[], None]
"""What to do when the app goes to the background."""


async def wait(seconds: float) -> None:
    """Sleep ``seconds``: the clear's timer, which the tests hold."""
    await asyncio.sleep(seconds)


def use_clear_after(
    serial: int, after: float | None, clear: Callable[[int], None]
) -> None:
    """Clear the result ``serial`` once it has been shown for ``after`` seconds.

    Call it on every render (D-70). The timer is the effect's coroutine: a new result
    restarts it, and Flet cancels it on unmount, so a late clear never lands.

    Args:
        serial: The shown result's serial, 0 while none is shown.
        after: The seconds a result stays, or None to keep it until the next.
        clear: Drops the result with that serial, if it is still the one shown.
    """

    @report_errors
    async def timer() -> None:
        if serial and after is not None:
            await wait(after)
            clear(serial)

    ft.use_effect(timer, [serial, after])


def use_on_background(action: Action | None) -> None:
    """Call ``action`` each time the app goes to the background, while mounted.

    Call it on every render (D-70), with None for nothing. The loop starts once and
    reads the latest action from a ref (#756); Flet cancels it on unmount.

    Args:
        action: What to do on each ``pause``, or None.
    """
    svc = use_services()
    latest: MutableRef[Action | None] = ft.use_ref(action)
    latest.current = action
    on = action is not None

    @report_errors
    async def watch() -> None:
        if on:
            await on_each_pause(svc, latest)

    ft.use_effect(watch, [on])


async def on_each_pause(svc: Services, latest: MutableRef[Action | None]) -> None:
    """Call ``latest``'s action on each ``pause``; return when the session closes.

    Args:
        svc: The session's services: ``background`` is set from ``pause`` to
            ``resume``, ``foreground`` the other way round (D-40, D-420).
        latest: The action, as the last render left it.
    """
    while True:
        await svc.background.wait()
        if svc.closed.is_set():  # close() sets both, to end the loops (D-147)
            return
        if latest.current is not None:
            latest.current()
        await svc.foreground.wait()
        if svc.closed.is_set():
            return
