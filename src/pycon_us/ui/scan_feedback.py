"""What reaches staff who are not looking at the scan screen (LEAD-01, LEAD-09; D-65).

ux.md §7.2's haptics and spoken columns, and a screen that stays awake (#724):

- ``buzz()`` gives an outcome's haptics (``HAPTICS``): accepted and queued a light
  impact, a duplicate two medium ones, a denial a heavy one then a vibration, a code
  that is not a badge none; CoC's incident recorded a light impact, not recorded none.
- ``announce()`` says it where the platform takes announcements (``Prefs.announcements``,
  iOS): politely, assertively for a duplicate or a denial. There the result panel is no
  live region, so the result is said once; elsewhere (Android, where Flutter reports
  no announcements, F13) the panel's live region says it (D-241, D-420). Its answer
  is awaited at most ``ANNOUNCE_WAIT_S``: iOS never gives one under VoiceOver (F276).
- ``use_wake_lock()`` keeps the screen on while the calling screen is mounted and
  the app is in the foreground, and lets it sleep again in the background and on
  unmount.

A failed call is logged, never shown: the result is on the panel all the same.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable

import flet as ft

from pycon_us.core.badges import ScanOutcome, ScanResult
from pycon_us.services import Services, use_services
from pycon_us.services.errors import report_errors
from pycon_us.services.storage import SERVICE_ERRORS

logger = logging.getLogger(__name__)

type Effect = Callable[[ft.HapticFeedback], Awaitable[None]]
"""One haptic effect, a ``HapticFeedback`` method."""

HAPTICS: dict[ScanOutcome, tuple[Effect, ...]] = {
    ScanOutcome.ACCEPTED: (ft.HapticFeedback.light_impact,),
    ScanOutcome.DUPLICATE: (
        ft.HapticFeedback.medium_impact,
        ft.HapticFeedback.medium_impact,
    ),
    ScanOutcome.DENIED: (ft.HapticFeedback.heavy_impact, ft.HapticFeedback.vibrate),
    ScanOutcome.QUEUED: (ft.HapticFeedback.light_impact,),
    ScanOutcome.INVALID: (),
    ScanOutcome.RECORDED: (ft.HapticFeedback.light_impact,),
    ScanOutcome.NOT_RECORDED: (),
}
"""Each outcome's effects, in order (ux.md §7.2)."""

ASSERTIVE = frozenset({ScanOutcome.DUPLICATE, ScanOutcome.DENIED})
"""The outcomes said assertively: the ones staff must act on (ux.md §7.2)."""

GAP_S = 0.15
"""Seconds between two effects, so a duplicate's two pulses are felt as two."""

ANNOUNCE_WAIT_S = 0.5
"""How long an announcement is awaited. iOS never answers one while its accessibility
bridge runs (VoiceOver on, or a UI test), so Flet's call would wait forever and hold
the scan screen's single flight: every later scan was dropped (F276, U256)."""


async def buzz(haptics: ft.HapticFeedback, outcome: ScanOutcome) -> None:
    """Give an outcome's haptics (``HAPTICS``).

    Args:
        haptics: ``Services.haptics``.
        outcome: How the scan ended.
    """
    for index, effect in enumerate(HAPTICS[outcome]):
        if index:
            await asyncio.sleep(GAP_S)
        try:
            await effect(haptics)
        except SERVICE_ERRORS:  # a missed pulse is no error: the panel shows it
            logger.warning("Haptic feedback failed", exc_info=True)
            return


async def announce(semantics: ft.SemanticsService, result: ScanResult) -> None:
    """Say a result through the platform's announcements (iOS; ``ASSERTIVE``).

    Call it only where ``Prefs.announcements`` is true: the panel is then no live
    region, so the result is said once.

    Args:
        semantics: ``Services.semantics``.
        result: The result on the panel.
    """
    assertiveness = (
        ft.Assertiveness.ASSERTIVE
        if result.outcome in ASSERTIVE
        else ft.Assertiveness.POLITE
    )
    said = semantics.announce_message(result.spoken, assertiveness=assertiveness)
    try:
        # Sent at once; only the answer, which iOS may never give, is waited for.
        await asyncio.wait_for(said, ANNOUNCE_WAIT_S)
    except TimeoutError:
        logger.debug("No answer to the scan's announcement (F276)")
    except SERVICE_ERRORS:  # the panel shows it all the same
        logger.warning("Could not announce the scan's result", exc_info=True)


async def keep_awake(svc: Services) -> None:
    """Hold the wake lock while the app is in the foreground; never returns on its own.

    It lets go when the app goes to the background and takes it again on the resume
    (``Services.background``, ``Services.foreground``), and returns when the session
    closes (D-147). The effect that runs it is cancelled on unmount; its cleanup lets go.

    Args:
        svc: The session's services.
    """
    while True:
        await svc.foreground.wait()
        if svc.closed.is_set():
            return
        await set_awake(svc.wakelock, on=True)
        await svc.background.wait()
        await set_awake(svc.wakelock, on=False)


async def set_awake(wakelock: ft.Wakelock, *, on: bool) -> None:
    """Take or let go of the wake lock, logging a failure.

    Args:
        wakelock: ``Services.wakelock``.
        on: Keep the screen on (True) or let it sleep again.
    """
    try:
        await (wakelock.enable() if on else wakelock.disable())
    except SERVICE_ERRORS:  # the screen may dim; scanning still works
        logger.warning("Could not %s the wake lock", "take" if on else "release")


def use_wake_lock() -> None:
    """Keep the screen on while the calling component is mounted (ux.md §7.2).

    Call it on every render (D-70). The effect's ``async`` setup holds the lock
    (``keep_awake()``); Flet cancels it on unmount, and its ``async`` cleanup lets go
    (D-387).
    """
    svc = use_services()

    @report_errors
    async def hold() -> None:
        await keep_awake(svc)

    @report_errors
    async def release() -> None:
        await set_awake(svc.wakelock, on=False)

    ft.use_effect(hold, [], cleanup=release)
