"""The Lead scanner (``/more/staff/lead``): the shared scan screen, parse-only for now.

The first mount of ``ui/scan_screen.py``'s ``ScanScreen`` (LEAD-01, LEAD-09, LEAD-14;
D-416). It re-checks its rule on every render (architecture §12.4): an account
without ``lead_retrieval`` or ``door_check``, a signed-out session or no mock URL
(D-51) sees "Not available for this account", so a deep link cannot bypass it.

Past the rule, the account's consent (``SCANNER_CONSENT``, LEAD-04) is read from
storage as the scanner opens, and until it is given ``lead_consent.py``'s page shows
instead (D-423): the scan screen is not mounted, so a HID scanner's typing goes
nowhere. Until #39 brings lead capture, a badge is only read: "Badge read" with the
code, both validators and "Not recorded yet"; nothing is sent or queued.
"""

import flet as ft

from pycon_us.account import use_account
from pycon_us.core.badges import Badge, ScanOutcome, ScanResult
from pycon_us.core.staff_tools import TOOLS, ToolKey, may_open
from pycon_us.prefs import use_prefs
from pycon_us.screens.lead_consent import LeadConsent
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.services.storage import SCANNER_CONSENT
from pycon_us.ui.scaffold import AppScaffold
from pycon_us.ui.scan_screen import NotAvailable, ScanScreen
from pycon_us.ui.widths import LIST, sides, use_margin

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
    return LeadTool(owner=account.owner)


@ft.component
def LeadTool(*, owner: str) -> ft.Control:
    """The scan screen once ``owner`` has consented; else the consent page (LEAD-04).

    The answer counts only for the owner it was read for: another account's never
    stands for this one's, even for a render (D-423). Until it is read, an empty page
    under the title; the read takes a moment.

    Args:
        owner: The signed-in account (``Account.owner``).
    """
    svc = use_services()
    margin = use_margin(LIST)  # its width class (D-305), for the page while it reads
    # Whose consent was read, and what it said: None until the first read.
    read, set_read = ft.use_state(not_read)

    @report_errors
    async def read_consent() -> None:
        consent = await svc.storage.get(SCANNER_CONSENT)  # a failure reads False
        set_read((owner, consent))

    ft.use_effect(read_consent, [owner])
    if read is None or read[0] != owner:
        return AppScaffold(
            title=TITLE, body=ft.ListView(expand=True, padding=sides(margin))
        )
    if not read[1]:
        return LeadConsent(title=TITLE, on_given=lambda: set_read((owner, True)))
    return ScanScreen(title=TITLE, on_badge=badge_read)


def not_read() -> tuple[str, bool] | None:
    """Return None: the consent not read yet, ``LeadTool``'s first state (typed)."""
    return None


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
