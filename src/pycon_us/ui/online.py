"""Whether the device has a connection, for a button that needs one (``use_online()``).

The Account page's Speaker Discord is disabled offline, with the reason (AUTH-10).
``Services.connectivity``'s one change handler belongs to the staff sync (F257), so
this hook asks ``get_connectivity()`` every few seconds instead, and only while the
page that calls it needs to know.
"""

import asyncio
import contextlib

import flet as ft

from pycon_us.services import Services
from pycon_us.services.errors import report_errors
from pycon_us.services.storage import SERVICE_ERRORS

ONLINE_POLL = 5.0
"""Seconds between two connectivity checks while a page watches."""


def use_online(svc: Services, *, watch: bool) -> bool:
    """Return whether the device has a connection, checked every ``ONLINE_POLL`` s.

    A hook (D-70): call it on every render. Only while ``watch`` and the app is in
    front; True when unknown (no ``Connectivity``, or a check that failed), so a
    button is never disabled for nothing. ``Services.connectivity``'s one change
    handler belongs to the staff sync (F257), so this asks instead of listening.

    Args:
        svc: The session's services.
        watch: Whether anything on the page depends on it.
    """
    online, set_online = ft.use_state(True)

    @report_errors
    async def keep_checking() -> None:
        connectivity = svc.connectivity
        if not watch or connectivity is None:
            return
        while not svc.closed.is_set():
            await svc.foreground.wait()
            with contextlib.suppress(*SERVICE_ERRORS):
                kinds = await connectivity.get_connectivity()
                set_online(any(k is not ft.ConnectivityType.NONE for k in kinds))
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(svc.closed.wait(), ONLINE_POLL)

    ft.use_effect(keep_checking, [watch])
    return online
