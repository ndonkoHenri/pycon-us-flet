"""The Lead scanner (``/more/staff/lead``): the shared scan screen, parse-only for now.

The first mount of ``ui/scan_screen.py``'s ``ScanScreen`` (LEAD-01, LEAD-09, LEAD-14;
D-416). It re-checks its rule on every render (architecture §12.4): an account
without ``lead_retrieval`` or ``door_check``, a signed-out session or no mock URL
(D-51) sees "Not available for this account", so a deep link cannot bypass it. Until
#39 brings lead capture, a badge is only read: "Badge read" with the code, both
validators and "Not recorded yet"; nothing is sent or queued.
"""

import flet as ft

from pycon_us.account import use_account
from pycon_us.core.badges import Badge, ScanOutcome, ScanResult
from pycon_us.core.staff_tools import TOOLS, ToolKey, may_open
from pycon_us.prefs import use_prefs
from pycon_us.ui.scan_screen import NotAvailable, ScanScreen

TITLE = next(tool.title for tool in TOOLS if tool.key is ToolKey.LEAD)
"""The app bar's title, "Lead scanner", as the staff entry points name it."""

BADGE_READ = "Badge read"
NOT_RECORDED = "Not recorded yet"
"""The parse-only result's word and its last line (D-416): no lead is captured."""


@ft.component
def LeadScanner() -> ft.Control:
    """The Lead scanner, or its "Not available" state for an account it refuses."""
    prefs = use_prefs()
    account = use_account()
    allowed = (
        prefs.private_api_enabled
        and account.signed_in
        and may_open(ToolKey.LEAD, account.role_flags)
    )
    if not allowed:
        return NotAvailable(title=TITLE)
    return ScanScreen(title=TITLE, on_badge=badge_read)


async def badge_read(badge: Badge) -> ScanResult:
    """Return what the parse-only handler shows: the badge as read, not recorded.

    Args:
        badge: The parsed badge.
    """
    return ScanResult(
        ScanOutcome.ACCEPTED,
        BADGE_READ,
        badge.code,
        (
            f"Door validator: {badge.door_validator or 'none'}",
            f"Lead validator: {badge.lead_validator or 'none'}",
            NOT_RECORDED,
        ),
    )
