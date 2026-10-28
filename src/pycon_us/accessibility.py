"""The OS's accessibility flags, read into ``Prefs`` (D-23, D-34, D-184, D-356).

``App`` reads them at start and on resume, and ``ui/snack_bars.py`` while a screen
reader keeps a SnackBar; neither imports the other. Split from ``prefs.py`` at D-66's
~400 lines (#737).
"""

import logging

import flet as ft

from pycon_us.prefs import Prefs
from pycon_us.services.storage import SERVICE_ERRORS

logger = logging.getLogger(__name__)


async def read_accessibility(semantics: ft.SemanticsService, prefs: Prefs) -> None:
    """Copy the OS's accessibility flags into ``prefs`` (D-23, D-34, D-184).

    High contrast, reduced motion, whether a screen reader is on and whether the
    platform takes announcements. The platform reports a snapshot with no change
    event (F13, U17), so this runs at start, on resume and while a screen reader
    keeps a SnackBar (D-356). A failed read is logged and
    keeps the previous values.

    Args:
        semantics: The session's ``SemanticsService``.
        prefs: The store to update.
    """
    try:
        features = await semantics.get_accessibility_features()
    except SERVICE_ERRORS:
        logger.warning("Could not read the accessibility features", exc_info=True)
        return
    reduce_motion = features.reduce_motion or features.disable_animations
    if reduce_motion != prefs.reduce_motion:  # logged on change only: resumes are many
        logger.info("Reduced motion is %s", "on" if reduce_motion else "off")
    prefs.os_high_contrast = features.high_contrast
    prefs.reduce_motion = reduce_motion
    prefs.screen_reader = features.accessible_navigation
    prefs.announcements = features.supports_announcements
