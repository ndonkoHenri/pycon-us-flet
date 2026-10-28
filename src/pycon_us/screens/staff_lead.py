"""The Lead scanner (``/more/staff/lead``): the shared scan screen, parse-only for now.

The first mount of ``ui/scan_screen.py``'s ``ScanScreen`` (LEAD-01, LEAD-09, LEAD-14;
D-416). It re-checks its rule on every render (architecture §12.4): an account
without ``lead_retrieval`` or ``door_check``, a signed-out session or no mock URL
(D-51) sees "Not available for this account", so a deep link cannot bypass it. It is
mounted at ``/now/staff/lead`` too, for Now's Scan badges card, and records itself as
the last tool opened, which that card opens next (D-421).

Past the rule, the account's consent (``SCANNER_CONSENT``, LEAD-04) is read from
storage as the scanner opens, and until it is given ``lead_consent.py``'s page shows
instead (D-423): the scan screen is not mounted, so a HID scanner's typing goes
nowhere. Until #39 brings lead capture, a badge is only read: "Badge read" with the
code, both validators and "Not recorded yet"; nothing is sent or queued.

Staff who scan for a sponsor (``scans_for_sponsor()``, LEAD-05, LEAD-06) choose it on
``lead_sponsor.py``'s picker, pushed at ``…/staff/lead/sponsor``. The choice
(``STAFF_SPONSOR``) is read with the consent, and again whenever the location changes,
so it is current when the picker goes back (D-425). With none, the picker opens by
itself once, and the scan screen is paused ("Choose a sponsor to start scanning")
with a "Choose sponsor" button; with one, a "For: Example Corp" chip
(``lead.sponsor_chip``) heads the screen and opens the picker. A sponsor's own account
sees neither.
"""

from dataclasses import dataclass

import flet as ft

from pycon_us.account import use_account
from pycon_us.core.badges import Badge, ScanOutcome, ScanResult
from pycon_us.core.lead_sponsors import LeadSponsor
from pycon_us.core.staff_tools import TOOLS, ToolKey, may_open, scans_for_sponsor
from pycon_us.locations import is_top_view
from pycon_us.prefs import use_prefs
from pycon_us.screens import lead_sponsor
from pycon_us.screens.lead_consent import LeadConsent
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.services.storage import SCANNER_CONSENT
from pycon_us.staff_sponsor import read_sponsor
from pycon_us.ui.buttons import LABEL_PADDING
from pycon_us.ui.scaffold import AppScaffold
from pycon_us.ui.scan_screen import NotAvailable, ScanScreen
from pycon_us.ui.semantics import named
from pycon_us.ui.widths import LIST, sides, use_margin

TITLE = next(tool.title for tool in TOOLS if tool.key is ToolKey.LEAD)
"""The app bar's title, "Lead scanner", as the staff entry points name it."""

BADGE_READ = "Badge read"
NOT_RECORDED = "Not recorded yet"
"""The parse-only result's word and its last line (D-416): no lead is captured."""

NO_SPONSOR = "Choose a sponsor to start scanning"
"""Why the scan screen is paused for staff with no sponsor chosen (LEAD-05)."""


@dataclass(frozen=True)
class Read:
    """The staff keys as ``LeadTool`` last read them.

    Attributes:
        owner: The account they were read for; another's never stand (D-423).
        consent: Whether it agreed to scan only with consent.
        sponsor: The sponsor it scans for, or None (staff only, LEAD-05).
    """

    owner: str
    consent: bool
    sponsor: LeadSponsor | None


@ft.component
def LeadScanner() -> ft.Control:
    """The Lead scanner, or its "Not available" state for an account it refuses."""
    prefs = use_prefs()
    account = use_account()
    memory = use_services().memory
    allowed = (
        prefs.private_api_enabled
        and account.signed_in
        and may_open(ToolKey.LEAD, account.role_flags)
    )
    if not allowed:
        return NotAvailable(title=TITLE)
    memory.staff_tool = ToolKey.LEAD  # plain: Now's card reads it when it renders
    return LeadTool(
        owner=account.owner, for_sponsor=scans_for_sponsor(account.role_flags)
    )


@ft.component
def LeadTool(*, owner: str, for_sponsor: bool) -> ft.Control:
    """The scan screen once ``owner`` has consented; else the consent page (LEAD-04).

    The answer counts only for the owner it was read for: another account's never
    stands for this one's, even for a render (D-423). Until it is read, an empty page
    under the title; the read takes a moment. The keys are read again at each change
    of location, so the sponsor chosen on the picker shows when it goes back (D-425);
    a consent kept for the session after a failed save stays given.

    Args:
        owner: The signed-in account (``Account.owner``).
        for_sponsor: It scans for a sponsor it chooses (``scans_for_sponsor()``).
    """
    page = ft.context.page
    view_path = ft.use_view_path()
    location = ft.use_route_location()  # changes as the picker opens and goes back
    svc = use_services()
    read, set_read = ft.use_state(not_read)  # None until the first read
    asked = ft.use_ref(False)  # the picker opened by itself: only once

    @report_errors
    async def read_keys() -> None:
        consent = await svc.storage.get(SCANNER_CONSENT)  # a failure reads False
        sponsor = await read_sponsor(svc.storage)
        set_read(lambda last: Read(owner, consent or given(last, owner), sponsor))

    ft.use_effect(read_keys, [owner, location])
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
    def ask() -> None:
        if needs_sponsor and not asked.current and is_top_view(page.route, view_path):
            asked.current = True
            open_picker()

    ft.use_effect(ask, [needs_sponsor])
    if current is None:
        return Reading()
    if not current.consent:
        return LeadConsent(
            title=TITLE, on_given=lambda: set_read(Read(owner, True, current.sponsor))
        )
    if not for_sponsor:
        return ScanScreen(title=TITLE, on_badge=badge_read)
    if current.sponsor is None:
        return ScanScreen(
            title=TITLE,
            on_badge=badge_read,
            paused=NO_SPONSOR,
            actions=[choose_button(open_picker)],
        )
    return ScanScreen(
        title=TITLE,
        on_badge=badge_read,
        context=sponsor_chip(current.sponsor, open_picker),
    )


def sponsor_chip(sponsor: LeadSponsor, on_click: ft.ControlEventHandler) -> ft.Control:
    """Return the "For: Example Corp" chip that heads the scan screen (LEAD-06).

    One node, a button read "Scanning for Example Corp, change sponsor"; it opens the
    picker. Drawn as M3's outlined assist chip (8 dp corners, an ``outline_variant``
    edge, a leading icon) but built from a ``Container``: Flutter's ``Chip`` keeps its
    label on one line, which at the largest text cut "Example Corp" to "Example". Its
    text takes only the room it needs (``expand_loose``) and wraps past the width;
    the chip is at least 48 dp tall, its own target (ux.md §9).

    Args:
        sponsor: The sponsor chosen.
        on_click: Opens the picker.
    """
    return ft.Container(
        ft.MergeSemantics(  # the phrase and the tap's action: one node
            content=ft.Container(
                ft.Semantics(
                    label=f"Scanning for {sponsor.name}, change sponsor",
                    identifier="lead.sponsor_chip",
                    button=True,
                    exclude_semantics=True,  # the phrase replaces the text
                    content=ft.Row(
                        [
                            ft.Icon(
                                ft.Icons.STOREFRONT_OUTLINED,
                                size=18,
                                color=ft.Colors.PRIMARY,
                                apply_text_scaling=True,
                            ),
                            ft.Text(
                                f"For: {sponsor.name}",
                                theme_style=ft.TextThemeStyle.LABEL_LARGE,
                                expand=True,
                                expand_loose=True,
                            ),
                        ],
                        spacing=8,
                        tight=True,
                    ),
                ),
                ink=True,
                on_click=on_click,
                border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                border_radius=8,
                padding=ft.Padding.symmetric(horizontal=12, vertical=13),
            )
        ),
        alignment=ft.Alignment.CENTER_LEFT,
    )


def choose_button(on_click: ft.ControlEventHandler) -> ft.Control:
    """Return "Choose sponsor", under the paused field while none is chosen."""
    return ft.Container(
        named(
            "lead.sponsor.choose",
            ft.FilledTonalButton(
                lead_sponsor.TITLE,
                icon=ft.Icons.STOREFRONT_OUTLINED,
                on_click=on_click,
                style=ft.ButtonStyle(padding=LABEL_PADDING),
                elevation=0,  # M3's tonal button lies flat (D-344)
            ),
        ),
        alignment=ft.Alignment.CENTER_LEFT,
    )


@ft.component
def Reading() -> ft.Control:
    """The empty page under the title while the consent is read.

    A component of its own: ``AppScaffold`` calls hooks, which in ``LeadTool``'s
    loading branch only would change its hook order once the read ends (D-70).
    """
    margin = use_margin(LIST)  # its width class (D-305)
    return AppScaffold(
        title=TITLE, body=ft.ListView(expand=True, padding=sides(margin))
    )


def given(last: Read | None, owner: str) -> bool:
    """Whether ``owner``'s consent was given in this visit, kept after a failed save.

    Args:
        last: The keys as last read, or None.
        owner: The signed-in account.
    """
    return last is not None and last.owner == owner and last.consent


def not_read() -> Read | None:
    """Return None: the keys not read yet, ``LeadTool``'s first state (typed)."""
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
