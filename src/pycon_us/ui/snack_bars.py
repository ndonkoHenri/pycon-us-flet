"""How long a SnackBar shows, and the one a screen reader keeps until it is off (D-356).

A SnackBar shows for ``SNACK_BAR_MS`` (ux.md §4.5). With TalkBack or VoiceOver on, an
Undo or Review SnackBar stays until it is used, replaced or closed (``persist``,
D-184). Flutter settles that once, when the 4 s run out (``ScaffoldMessengerState``'s
timer reads ``SnackBar.persist`` and is not armed again), and the OS reports its flags
as a snapshot with no change event (F13, U17). So a screen reader turned off with the
app in front left such a SnackBar up for good (#343): ``keep_while_screen_reader()``
reads the flags again while one shows, and closes it once no screen reader is on.
"""

import asyncio
import contextlib
from weakref import ref

import flet as ft

from pycon_us.accessibility import read_accessibility
from pycon_us.prefs import Prefs
from pycon_us.services import Services
from pycon_us.services.errors import report_errors, say

NOT_SAVED = "Couldn't save your change"
"""The SnackBar when a change applies for the session but was not written (D-120)."""

SNACK_BAR_MS = 4000
"""How long a SnackBar shows (ux.md §4.5), unless a screen reader keeps it (D-184)."""

READ_EVERY_S = 2.0
"""How often the OS's flags are read again while a screen reader keeps a SnackBar."""

_WATCHES: set[asyncio.Task[None]] = set()
"""The running watches: the event loop holds its tasks only weakly."""


def say_if_unsaved(page: ft.Page, saved: bool) -> None:
    """Show "Couldn't save your change" when a setting was applied but not saved (D-120).

    The setting still applies for the session; the SnackBar says it ends on relaunch.
    Every setting a failed write can leave unsaved uses it.

    Args:
        page: The session's page.
        saved: What ``Prefs.save()`` returned.
    """
    if not saved:
        say(page, NOT_SAVED)


def keep_while_screen_reader(bar: ft.SnackBar, svc: Services, prefs: Prefs) -> None:
    """Close ``bar``, shown with ``persist`` for a screen reader, once none is on (D-356).

    After the bar's 4 s, the OS's flags are read again every ``READ_EVERY_S`` while it
    shows and the app is in front (``read_accessibility()``, so ``prefs`` follows them
    too). Once no screen reader is on, the bar closes, as it would have timed out for
    anyone: ``open = False`` and ``update()``, which Flet turns into
    ``removeCurrentSnackBar()`` (D-251). The watch ends as soon as the bar has gone
    (used, replaced or closed) or the session closes (D-147).

    Call it from a Flet handler or a store listener: the watch's task runs in the
    caller's context, whose page a store write needs to re-render. It holds the bar
    weakly, as the page's dialogs own it while it shows.

    Args:
        bar: The SnackBar, just shown with ``persist``.
        svc: The session's services: its ``SemanticsService``, foreground and close.
        prefs: The session's ``Prefs`` store.
    """
    watch = asyncio.get_running_loop().create_task(_watch(ref(bar), svc, prefs))
    _WATCHES.add(watch)
    watch.add_done_callback(_WATCHES.discard)


@report_errors
async def _watch(shown: ref[ft.SnackBar], svc: Services, prefs: Prefs) -> None:
    """Read the flags while ``shown`` shows, after its 4 s; close it once none is on."""
    wait = SNACK_BAR_MS / 1000
    while True:
        # Sleeps `wait`, or less when the session closes meanwhile.
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(svc.closed.wait(), wait)
        wait = READ_EVERY_S
        await svc.foreground.wait()  # a resume reads the flags itself (D-34)
        if svc.closed.is_set() or _showing(shown) is None:
            return
        await read_accessibility(svc.semantics, prefs)
        bar = _showing(shown)
        if bar is None:
            return
        if not prefs.screen_reader:
            bar.open = False
            bar.update()
            return
        del bar  # held weakly across the sleep


def _showing(shown: ref[ft.SnackBar]) -> ft.SnackBar | None:
    """Return the SnackBar while it shows; None once Flet reports it gone (D-251)."""
    bar = shown()
    return bar if bar is not None and bar.open else None
