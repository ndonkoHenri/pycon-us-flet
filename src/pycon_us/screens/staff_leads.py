"""The leads list (``…/staff/lead/leads``): every lead the account captured (#743).

LEAD-06, LEAD-08; D-428. Ionic kept only the 50 most recent leads, showed a status as
a coloured dot and compared sponsor names. Here a pushed page over the Lead scanner,
opened by its "Leads (42)" button, so the scan screen stays as the four tools share it
(D-416) and a HID scanner never types into this page's search: a search field
(``lead.leads.search``) matching the name or the code; for staff who scan for a sponsor
(``scans_for_sponsor()``) with one chosen, a filter chip "Only Example Corp"
(``lead.leads.only_sponsor``) that compares sponsor ids; while either narrows the list
and finds some, a live count line (``lead.leads.count``, "3 leads"); then a lazy ``ListView`` of
every lead, newest first, with no cap: an attendee scanned for two sponsors is two rows
(D-459). A row (``lead.leads.row.<code>``, with ``.<sponsor id>`` on a staff account's)
is one stop read "Ada, Confirmed, 5 minutes ago, has a note": its status icon and words
(``status_text()``, with ``WARNING_AMBER`` beside a flagged row's, D-410), the first
name or, without one, the code (a pending lead shows only its code), the time ago, the
sponsor on a staff account's rows, and a note icon. A tap opens the note sheet for the
lead (``ui/lead_note_sheet.py``); its Save changes the outbox, so the row follows.

The rows are read again whenever the outbox changes (``Staff.revision``, D-69), so a
queued lead turns Confirmed while the page shows, and the times move each minute
(``use_minute()``, D-175). States: "No leads yet", "No leads match" and, when the
outbox can't be read, "Couldn't read your leads on this device." (D-120). It re-checks
the Lead scanner's rule on every render (architecture §12.4), so a deep link from an
account without it sees "Not available for this account".
"""

import time
from collections.abc import Callable

import flet as ft
from flet.components.hooks.use_ref import MutableRef

from pycon_us.account import use_account
from pycon_us.core.lead_sponsors import LeadSponsor, snapshot
from pycon_us.core.lead_views import LeadView, filter_leads, lead_view, phrase
from pycon_us.core.staff_tools import ToolKey, scans_for_sponsor
from pycon_us.lead_list import leads
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.staff import use_staff
from pycon_us.staff_sponsor import read_sponsor
from pycon_us.theme import Tokens, use_tokens
from pycon_us.ui.fields import SearchField, found_count, use_field_query
from pycon_us.ui.lead_note_sheet import OpenNote, use_note_sheet
from pycon_us.ui.queue_rows import status_icon
from pycon_us.ui.scaffold import AppScaffold
from pycon_us.ui.scan_screen import NotAvailable, use_tool_allowed
from pycon_us.ui.states import EmptyState
from pycon_us.ui.status_strip import use_minute
from pycon_us.ui.widths import LIST, capped, sides, use_margin

SEGMENT = "leads"
"""The page's segment under the Lead scanner's route, ``…/staff/lead/leads``."""

TITLE = "Leads"
"""The app bar's title; the scanner's button adds the count, "Leads (42)"."""

SEARCH_HINT = "Search leads"
CLEAR_SEARCH = "Clear search"
NO_LEADS = "No leads yet"
NO_LEADS_BODY = "Scan a badge to capture a lead."
NO_MATCH = "No leads match"
NOT_READ = "Couldn't read your leads on this device."


def button_label(count: int | None) -> str:
    """Return the scanner's button: "Leads (42)", or "Leads" when the count is unknown."""
    return TITLE if count is None else f"{TITLE} ({count})"


def count_line(count: int) -> str:
    """Return the filter's count line, a live region: "1 lead", "3 leads"."""
    return f"{count} lead" + ("" if count == 1 else "s")


def only_label(sponsor: LeadSponsor) -> str:
    """Return the filter chip's label: "Only Example Corp"."""
    return f"Only {sponsor.name}"


@ft.component
def LeadsPage() -> ft.Control:
    """The leads list, or "Not available" for an account the Lead scanner refuses."""
    allowed = use_tool_allowed(ToolKey.LEAD)
    account = use_account()
    if not allowed:
        return NotAvailable(title=TITLE, source=__name__)
    return LeadList(
        owner=account.owner, for_sponsor=scans_for_sponsor(account.role_flags)
    )


@ft.component
def LeadList(*, owner: str, for_sponsor: bool) -> ft.Control:
    """The search, the staff filter and the account's leads, or the list's state.

    Args:
        owner: The signed-in account (``Account.owner``): only its rows show (D-414).
        for_sponsor: It scans for a sponsor it chooses: the rows name their sponsor,
            and the chosen one gets the filter chip.
    """
    svc = use_services()
    staff = use_staff()  # re-renders as the outbox changes
    tokens = use_tokens()
    margin = use_margin(LIST)  # its width class (D-305)
    field = use_field_query()
    use_minute()  # "5 minutes ago" keeps up while the page shows
    sheet = use_note_sheet(owner=owner)
    sponsor, set_sponsor = ft.use_state(no_sponsor)
    only, set_only = ft.use_state(False)
    mounted = ft.use_ref(True)  # cleared on unmount: a late read then does nothing
    opener: MutableRef[OpenNote] = ft.use_ref(
        lambda: sheet.open  # a callable is use_ref's initialiser: wrapped, not called
    )
    opener.current = sheet.open  # the latest, which the stable callback below calls
    found = ft.use_memo(
        lambda: leads(svc.outbox, owner), [owner, staff.revision, svc.outbox]
    )

    @report_errors
    def unmount() -> None:
        """Mark the page gone, so the sponsor's read still running stays quiet."""
        mounted.current = False

    ft.use_effect(lambda: None, [], cleanup=unmount)

    @report_errors
    async def read_chosen() -> None:
        chosen = await read_sponsor(svc.storage) if for_sponsor else None
        if mounted.current:
            set_sponsor(chosen)

    ft.use_effect(read_chosen, [owner, for_sponsor])

    @report_errors
    def open_lead(view: LeadView) -> None:
        if opener.current is not None:  # always set: the render sets it
            scanned_for = snapshot(view.sponsor_id, view.sponsor_name)
            opener.current(view.code, view.name, scanned_for)

    on_open = ft.use_callback(open_lead, [])

    @report_errors
    def toggle(_: ft.Event[ft.Container]) -> None:
        set_only(not only)

    head: list[ft.Control] = []
    items: list[ft.Control] = []
    if found is None:
        items.append(
            EmptyState(
                NOT_READ,
                icon=ft.Icons.ERROR_OUTLINE,
                identifier="lead.leads.failed",
            )
        )
    elif not found:
        items.append(
            EmptyState(
                NO_LEADS,
                icon=ft.Icons.CONTACTS_OUTLINED,
                body=NO_LEADS_BODY,
                identifier="lead.leads.empty",
            )
        )
    else:
        head.append(
            SearchField(
                value=field.value,
                on_change=field.changed,
                on_clear=field.clear,
                ref=field.ref,
                focusable=field.focusable,
                hint=SEARCH_HINT,
                label=SEARCH_HINT,
                clear_tooltip=CLEAR_SEARCH,
                identifier="lead.leads.search",
                high_contrast=tokens.high_contrast,
            )
        )
        if sponsor is not None:
            head.append(only_chip(sponsor, only, toggle))
        now = time.time()
        views = [lead_view(row, has_note, now) for row, has_note in found]
        kept = filter_leads(
            views, field.value, sponsor.id if sponsor is not None and only else None
        )
        items.extend(LeadRow(view, tokens, on_open) for view in kept)
        if kept and (field.value.strip() or only):  # a filter applies, finds some
            head.append(
                found_count(count_line(len(kept)), identifier="lead.leads.count")
            )
        if not kept:
            searched = bool(field.value.strip())
            items.append(
                EmptyState(
                    NO_MATCH,
                    icon=ft.Icons.SEARCH_OFF,
                    action=CLEAR_SEARCH if searched else None,
                    on_action=field.clear if searched else None,
                    identifier="lead.leads.no_match",
                )
            )
    return AppScaffold(
        title=TITLE,
        source=__name__,
        body=ft.Column(
            [
                # The field and chip in a column of their own, so the list keeps its
                # place as the states come and go (D-153).
                capped(
                    ft.Column(
                        head,
                        spacing=8,
                        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    ),
                    margin,
                ),
                # Lazy: Flutter builds only the rows on screen; no cap (LEAD-08).
                ft.ListView(items, expand=True, padding=sides(margin, bottom=24)),
            ],
            spacing=0,
            expand=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        ),
    )


def only_chip(
    sponsor: LeadSponsor, selected: bool, on_toggle: ft.ControlEventHandler
) -> ft.Control:
    """Return the "Only Example Corp" filter chip, start-aligned (LEAD-06).

    One node, a button read "Only Example Corp" with whether it is selected. Drawn as
    M3's filter chip (8 dp corners, a filter icon, the check mark and a
    ``secondary_container`` fill once selected) but built from a ``Container``, as the
    scanner's sponsor chip (D-425): Flutter's ``Chip`` keeps its label on one line and
    cuts a long sponsor's name at 200 % text. Its text takes only the room it needs
    (``expand_loose``) and wraps past the width; the chip is at least 48 dp tall, its
    own target (ux.md §9). The edge stays when selected, so the state is never a fill
    alone (D-306).

    Args:
        sponsor: The sponsor the account scans for now.
        selected: The filter is on.
        on_toggle: Turns it on or off.
    """
    label = only_label(sponsor)
    return ft.Container(
        ft.MergeSemantics(  # the label, the state and the tap's action: one node
            content=ft.Container(
                ft.Semantics(
                    label=label,
                    identifier="lead.leads.only_sponsor",
                    button=True,
                    selected=selected,
                    exclude_semantics=True,  # the label replaces the text
                    content=ft.Row(
                        [
                            ft.Icon(
                                ft.Icons.CHECK if selected else ft.Icons.FILTER_LIST,
                                size=18,
                                color=ft.Colors.ON_SECONDARY_CONTAINER
                                if selected
                                else ft.Colors.PRIMARY,
                                apply_text_scaling=True,
                            ),
                            ft.Text(
                                label,
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
                on_click=on_toggle,
                bgcolor=ft.Colors.SECONDARY_CONTAINER if selected else None,
                border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                border_radius=8,
                padding=ft.Padding.symmetric(horizontal=12, vertical=13),
            )
        ),
        alignment=ft.Alignment.CENTER_LEFT,
        # The search field's 16 dp sides, so the chip lines up under it (ux.md §3.6).
        padding=ft.Padding.only(left=16, right=16, bottom=4),
    )


def LeadRow(
    view: LeadView, tokens: Tokens, on_open: Callable[[LeadView], None]
) -> ft.Control:
    """Return one lead's row, a memoised component keyed by ``LeadView.key`` (D-153).

    So a keystroke or a minute's tick re-renders only the rows it changes; a thousand
    rows stay quick.

    Args:
        view: The lead's lines.
        tokens: The scheme's tokens, for the status icon's colour.
        on_open: Opens the note sheet for it; stable across renders (``use_callback``).
    """
    # As SessionRow's: ft.component's typing leaves out the key= its wrapper takes.
    return _LeadRow(view, tokens, on_open, key=view.key)  # pyright: ignore[reportCallIssue]


@ft.memo
@ft.component
def _LeadRow(
    view: LeadView, tokens: Tokens, on_open: Callable[[LeadView], None]
) -> ft.Control:
    """The body of ``LeadRow``: status icon, title and lines, note icon; one node."""

    @report_errors
    def opened() -> None:
        on_open(view)

    status: list[ft.Control] = []
    if view.flagged:  # beside its words, which say it too (D-410)
        status.append(
            ft.Icon(
                ft.Icons.WARNING_AMBER,
                color=tokens.warning,
                size=18,
                apply_text_scaling=True,
            )
        )
    status.append(
        ft.Text(
            f"{view.words} · {view.ago}",
            theme_style=ft.TextThemeStyle.BODY_MEDIUM,
            color=ft.Colors.ON_SURFACE_VARIANT,
            expand=True,
        )
    )
    lines: list[ft.Control] = [
        ft.Text(view.title, theme_style=ft.TextThemeStyle.BODY_LARGE),
        ft.Row(status, spacing=4),
    ]
    if view.sponsor_name:
        lines.append(
            ft.Text(
                view.sponsor_name,
                theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                color=ft.Colors.ON_SURFACE_VARIANT,
            )
        )
    return ft.MergeSemantics(  # the phrase and the tap's action: one node
        content=ft.Container(
            ft.Semantics(
                label=phrase(view),
                identifier=f"lead.leads.row.{view.key}",
                button=True,
                exclude_semantics=True,  # the phrase replaces the texts
                content=ft.Row(
                    [
                        status_icon(view.status, tokens),
                        ft.Column(lines, spacing=2, expand=True),
                        # Kept, transparent without a note, so the texts never move.
                        ft.Icon(
                            ft.Icons.STICKY_NOTE_2_OUTLINED,
                            color=ft.Colors.ON_SURFACE_VARIANT
                            if view.has_note
                            else ft.Colors.TRANSPARENT,
                        ),
                    ],
                    spacing=16,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ),
            ink=True,
            on_click=opened,
            padding=ft.Padding.symmetric(horizontal=16, vertical=8),
        )
    )


def no_sponsor() -> LeadSponsor | None:
    """Return None: no sponsor read yet, ``LeadList``'s first state (typed)."""
    return None
