"""The Lead scanner (`/more/staff/lead`): the shared scan screen, capturing leads.

The first mount of `ScanScreen` (`ui/scan_screen.py`, D-416; LEAD-01, LEAD-09, LEAD-14).
The screen's wording and flows are ux.md §7.3.

- **Access:** re-checked on every render (architecture §12.4): an account without
  `lead_retrieval` or `door_check`, a signed-out session or no mock URL (D-51) sees "Not
  available for this account", so a deep link cannot bypass it. It is mounted at
  `/now/staff/lead` too, for Now's Scan badges card, and records itself as the last tool
  opened (D-421).
- **Consent:** read from storage as the scanner opens (`SCANNER_CONSENT`, LEAD-04);
  until it is given `lead_consent.py`'s page shows and the scan screen is not mounted,
  so a HID scanner's typing goes nowhere (D-423).
- **Capture:** through the outbox (`lead_capture.capture()`, D-426): queued, sent by the
  sync worker, the row's state read back as the result, for the sponsor chosen when it
  was scanned (STORE-11).
- **Sponsor:** staff who scan for one (`scans_for_sponsor()`, LEAD-05, LEAD-06) choose it
  on `lead_sponsor.py`'s picker. The choice is read with the consent and again whenever
  the location changes (D-425); scanning waits for that read, so no row takes the old
  one (#873).
- **Note and leads:** a result's "Add note" and "Open lead" open `ui/lead_note_sheet.py`
  for that lead, with scanning paused (#742, D-459); "Leads (42)" pushes
  `staff_leads.py`'s list as a page, not a tab, so a HID scanner never types into its
  search (#743, D-428).
"""

from dataclasses import dataclass, replace
from functools import partial
from typing import cast

import flet as ft

from pycon_us.account import use_account
from pycon_us.core.badges import ScanOutcome
from pycon_us.core.lead_sponsors import LeadSponsor
from pycon_us.core.staff_tools import TOOLS, ToolKey, scans_for_sponsor
from pycon_us.lead_capture import capture
from pycon_us.lead_list import lead_count
from pycon_us.locations import is_top_view
from pycon_us.screens import lead_sponsor, staff_leads
from pycon_us.screens.lead_consent import LeadConsent
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.services.pref_keys import SCANNER_CONSENT
from pycon_us.staff import use_staff
from pycon_us.staff_sponsor import read_sponsor
from pycon_us.ui.lead_note_sheet import OpenNote, use_note_sheet
from pycon_us.ui.scan_result import Shown
from pycon_us.ui.scan_screen import NotAvailable, ScanScreen, use_tool_allowed
from pycon_us.ui.staff_picker import Reading, use_arrival
from pycon_us.ui.tool_controls import context_chip, tool_button

TITLE = next(tool.title for tool in TOOLS if tool.key is ToolKey.LEAD)
"""The app bar's title, "Lead scanner", as the staff entry points name it."""

NO_SPONSOR = "Choose a sponsor to start scanning"
"""Why the scan screen is paused for staff with no sponsor chosen (LEAD-05)."""

CHECKING_SPONSOR = "Checking the sponsor\N{HORIZONTAL ELLIPSIS}"
"""Why the scan screen is paused while the sponsor is read again (#873, D-425)."""

NOTE_OPEN = "Paused while the note is open"
"""Why the scan screen is paused while the note sheet is open (#742)."""

ADD_NOTE = "Add note"
OPEN_LEAD = "Open lead"
"""The result's button: on a lead captured or queued, and on a duplicate (LEAD-07)."""


@dataclass(frozen=True)
class Read:
    """The staff keys as `LeadTool` last read them.

    Attributes:
        owner: The account they were read for; another's never stand (D-423).
        arrival: `LeadTool`'s token for the location they were read at; another's
            means a new read is on its way (D-425).
        consent: Whether it agreed to scan only with consent.
        sponsor: The sponsor it scans for, or None (staff only, LEAD-05).
    """

    owner: str
    arrival: object
    consent: bool
    sponsor: LeadSponsor | None


@ft.component
def LeadScanner() -> ft.Control:
    """The Lead scanner, or its "Not available" state for an account it refuses."""
    allowed = use_tool_allowed(ToolKey.LEAD)
    account = use_account()
    memory = use_services().memory
    if not allowed:
        return NotAvailable(title=TITLE, source=__name__)
    memory.staff_tool = ToolKey.LEAD  # plain: Now's card reads it when it renders
    return LeadTool(
        owner=account.owner, for_sponsor=scans_for_sponsor(account.role_flags)
    )


@ft.component
def LeadTool(*, owner: str, for_sponsor: bool) -> ft.Control:
    """The scan screen once `owner` has consented; else the consent page (LEAD-04).

    The answer counts only for the owner it was read for: another account's never
    stands for this one's, even for a render (D-423). Until it is read, an empty page
    under the title; the read takes a moment. The keys are read again at each change
    of location, so the sponsor chosen on the picker shows when it goes back (D-425);
    a consent kept for the session after a failed save stays given.

    Args:
        owner: The signed-in account (`Account.owner`).
        for_sponsor: It scans for a sponsor it chooses (`scans_for_sponsor()`).
    """
    page = ft.context.page
    view_path = ft.use_view_path()
    arrival = use_arrival(owner)  # changes as the picker opens and goes back
    svc = use_services()
    staff = use_staff()
    read, set_read = ft.use_state(cast(Read | None, None))  # None until the first read
    asked = ft.use_ref(False)  # the picker opened by itself: only once
    count = ft.use_memo(  # "Leads (42)", read again as the outbox changes (D-69)
        lambda: lead_count(svc.outbox, owner), [owner, staff.revision, svc.outbox]
    )

    @report_errors
    async def read_keys() -> None:
        consent = await svc.storage.get(SCANNER_CONSENT)  # a failure reads False
        sponsor = await read_sponsor(svc.storage)
        set_read(
            lambda last: Read(owner, arrival, consent or given(last, owner), sponsor)
        )

    ft.use_effect(read_keys, [arrival])
    current = read if read is not None and read.owner == owner else None
    needs_sponsor = (
        for_sponsor
        and current is not None
        and current.consent
        and current.sponsor is None
    )

    @report_errors
    def open_picker() -> None:
        page.navigate(f"{view_path}/{lead_sponsor.SEGMENT}")

    @report_errors
    def open_leads(_: ft.Event[ft.FilledTonalButton]) -> None:
        page.navigate(f"{view_path}/{staff_leads.SEGMENT}")

    @report_errors
    def ask() -> None:
        if needs_sponsor and not asked.current and is_top_view(page.route, view_path):
            asked.current = True
            open_picker()

    ft.use_effect(ask, [needs_sponsor])
    sponsor = current.sponsor if for_sponsor and current is not None else None
    # The sponsor chosen now: the row keeps it (STORE-11).
    on_badge = partial(
        capture, svc.outbox, staff, svc.kick_sync, owner=owner, sponsor=sponsor
    )
    sheet = use_note_sheet(owner=owner)
    # Back from the picker, the old sponsor stands until the new read lands; scanning
    # waits, as a row keeps the sponsor it is scanned for for good (D-56).
    rereading = current is not None and current.arrival is not arrival
    paused = NOTE_OPEN if sheet.is_open else None
    note_actions = partial(lead_actions, open_note=sheet.open)
    leads = leads_button(count, open_leads)

    if current is None:
        return Reading(title=TITLE, source=__name__)
    if not current.consent:
        return LeadConsent(
            title=TITLE, on_given=lambda: set_read(replace(current, consent=True))
        )
    if not for_sponsor:
        return ScanScreen(
            title=TITLE,
            source=__name__,
            on_badge=on_badge,
            paused=paused,
            result_actions=note_actions,
            actions=[leads],
        )
    if current.sponsor is None:
        return ScanScreen(
            title=TITLE,
            source=__name__,
            on_badge=on_badge,
            paused=NO_SPONSOR,
            actions=[choose_button(open_picker), leads],
        )
    return ScanScreen(
        title=TITLE,
        source=__name__,
        on_badge=on_badge,
        context=sponsor_chip(current.sponsor, open_picker),
        paused=CHECKING_SPONSOR if rereading else paused,
        result_actions=note_actions,
        actions=[leads],
    )


def sponsor_chip(sponsor: LeadSponsor, on_click: ft.ControlEventHandler) -> ft.Control:
    """Return the "For: Example Corp" chip that heads the scan screen (LEAD-06).

    One node, a button read "Scanning for Example Corp, change sponsor"; it opens the
    picker (`context_chip()`, whose text wraps at 200 %).

    Args:
        sponsor: The sponsor chosen.
        on_click: Opens the picker.
    """
    return context_chip(
        text=f"For: {sponsor.name}",
        spoken=f"Scanning for {sponsor.name}, change sponsor",
        icon=ft.Icons.STOREFRONT_OUTLINED,
        identifier="lead.sponsor_chip",
        on_click=on_click,
    )


def choose_button(on_click: ft.ControlEventHandler) -> ft.Control:
    """Return "Choose sponsor", under the paused field while none is chosen."""
    return tool_button(
        "lead.sponsor.choose",
        lead_sponsor.TITLE,
        ft.Icons.STOREFRONT_OUTLINED,
        on_click,
    )


def leads_button(count: int | None, on_click: ft.ControlEventHandler) -> ft.Control:
    """Return "Leads (42)", under the field, which opens the leads list (#743, D-428).

    Args:
        count: The account's leads; None when the outbox can't be read: "Leads".
        on_click: Pushes the list.
    """
    return tool_button(
        "lead.leads",
        staff_leads.button_label(count),
        ft.Icons.CONTACTS_OUTLINED,
        on_click,
    )


def lead_actions(shown: Shown, open_note: OpenNote) -> list[ft.Control]:
    """Return the result's button: "Add note" on a lead, "Open lead" on a duplicate.

    A lead captured or queued gets "Add note"; "Already in your leads" gets "Open
    lead", the same sheet with the note saved for it. A refused or unsaved scan, and
    "Not a badge code", get none.

    Args:
        shown: The result on the panel.
        open_note: Opens the note sheet for a code, the name if any, and the sponsor
            the result's lead was scanned for.
    """
    result = shown.result
    if not result.code:
        return []
    name = result.title if result.title != result.code else None

    @report_errors
    def opened(_: ft.Event[ft.FilledTonalButton]) -> None:
        open_note(result.code, name, result.sponsor)

    match result.outcome:
        case ScanOutcome.ACCEPTED | ScanOutcome.QUEUED:
            return [
                tool_button(
                    "lead.add_note", ADD_NOTE, ft.Icons.NOTE_ADD_OUTLINED, opened
                )
            ]
        case ScanOutcome.DUPLICATE:
            return [
                tool_button("lead.open_lead", OPEN_LEAD, ft.Icons.EDIT_NOTE, opened)
            ]
        case _:
            return []


def given(last: Read | None, owner: str) -> bool:
    """Whether `owner`'s consent was given in this visit, kept after a failed save.

    Args:
        last: The keys as last read, or None.
        owner: The signed-in account.
    """
    return last is not None and last.owner == owner and last.consent
