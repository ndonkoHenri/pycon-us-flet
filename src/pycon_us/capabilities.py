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

REMINDERS = available("flet_local_notifications")
"""Scheduled local notifications, E3 (P2, D-60). The module name is a placeholder until
flet-dev/flet#6948 names its package."""

SCANNER = available("flet_barcode_scanner")
"""The camera badge scanner, E1 (P3, D-65); otherwise manual and HID entry. The module
name is a placeholder until the extension is published."""
