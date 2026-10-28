"""Which optional native pieces this build can use: constants, fixed at import (D-63).

An extension counts only in a packaged build that bundles it. The companion app
(``flet run --android/--ios``) runs Python on the laptop and is never embedded, so it
always gets the interim and is never sent a control its client may lack (F14). One
module per capability imports the extension and owns its fallback; screens never
import an extension (architecture §13). Core Flet gaps are not detected at run time:
the PR that bumps the pinned Flet swaps their interim (D-64).
"""

from importlib.util import find_spec

from flet.utils import is_embedded


def available(module: str) -> bool:
    """Return whether this is a packaged build and ``module`` can be imported.

    ``find_spec`` locates the module without importing it, so checking costs no
    import time (D-110).

    Args:
        module: A top-level module name, e.g. ``"flet_secure_storage"``.
    """
    return is_embedded() and find_spec(module) is not None


SECURE_STORAGE = available("flet_secure_storage")
"""Credentials in the platform keystore (P3); otherwise kept in memory for the session."""

PERMISSIONS = available("flet_permission_handler")
"""Permission status, the camera request and the app's settings page (P2, D-61)."""

REMINDERS = available("flet_notifications")
"""Scheduled local notifications, E3 (P2, D-220): the monorepo's ``flet-notifications``;
otherwise the interim (D-60)."""

REMINDERS_LIVE = False
"""Whether screens offer reminders: not yet, even where ``REMINDERS`` is true. The app
schedules them since #447 (D-389), but Settings has no live controls until #449, whose
PR sets this to ``REMINDERS``. Until then Settings keeps D-60's interim and Welcome
promises no reminders (D-287), so a build that bundles E3 never promises what it can't
do (#677's review). The primer on the first favourite follows ``REMINDERS`` instead,
since what it asks for is the OS permission the scheduled reminders need (D-395)."""

SCANNER = available("flet_barcode_scanner")
"""The camera badge scanner, E1 (P3, D-65); otherwise manual and HID entry. The module
name is a placeholder until the extension is published."""

ALL = (
    ("Secure storage", SECURE_STORAGE),
    ("Permissions", PERMISSIONS),
    ("Reminders", REMINDERS),
    ("Badge scanner", SCANNER),
)
"""Every capability with its display name: the Developer screen's rows and the
diagnostics text's list (D-271)."""
