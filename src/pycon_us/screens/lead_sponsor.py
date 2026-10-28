"""The sponsor picker (``…/staff/lead/sponsor``): whom door staff scan leads for (LEAD-05).

Ionic asked with a radio alert that had no Cancel and could not be dismissed, was
unusable with a long list, and found the chosen sponsor by its quote-stripped name.
Here a pushed page, for staff who scan for a sponsor (``scans_for_sponsor()``; anyone
else, and a deep link, sees "Not available for this account"): a search field
(``lead.sponsor.search``) that matches the name or booth, then one row per sponsor
(``lead.sponsor.<id>``): its logo (``logo_tile()``, the initials without one), its name
and "Booth 101", the current one ticked. One node each, read "Example Corp, Booth 101,
selected". A tap saves the choice (``STAFF_SPONSOR``) and goes back; a save that fails
stays here and says so, since the scanner would not see it (D-120, D-425). Cancel (a close
icon in the app bar) and Back leave the choice as it was.

The list is asked for each time the page opens and never kept (``fetch_sponsors()``):
a spinner meanwhile, "Couldn't load sponsors" with Retry offline or on an error (D-120),
"No sponsors available" for an empty one. A saved sponsor needs no list to scan. The
page's parts are ``ui/staff_picker.py``'s, which Door check's session picker shares.
"""

from collections.abc import Awaitable, Callable

import flet as ft

from pycon_us.account import use_account
from pycon_us.core.lead_sponsors import LeadSponsor, filter_sponsors
from pycon_us.core.staff_tools import ToolKey, may_open, scans_for_sponsor
from pycon_us.prefs import use_prefs
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.staff_sponsor import fetch_sponsors, read_sponsor, save_sponsor
from pycon_us.theme import use_tokens
from pycon_us.ui.fields import SearchField, use_field_query
from pycon_us.ui.logos import logo_tile
from pycon_us.ui.scan_screen import NotAvailable
from pycon_us.ui.staff_picker import (
    CLEAR_SEARCH,
    choice_row,
    no_match,
    not_loaded,
    picker_page,
    spinner,
    use_fetch,
    use_pick,
)
from pycon_us.ui.states import EmptyState
from pycon_us.ui.widths import LIST, use_margin

SEGMENT = "sponsor"
"""The picker's segment under the Lead scanner's route, ``…/staff/lead/sponsor``."""

TITLE = "Choose sponsor"
"""The app bar's title, and the scan screen's button that opens the page."""

PREFIX = "lead.sponsor"
"""The page's identifiers' start (decisions §M)."""

SEARCH_HINT = "Search sponsors"
LOADING = "Loading sponsors"
NOT_LOADED = "Couldn't load sponsors"
NONE_AVAILABLE = "No sponsors available"
NONE_AVAILABLE_BODY = "Ask the organisers to add the sponsors you scan for."

PLATE = 40
"""A row's logo plate, in dp: with its padding, a 56 dp row."""


@ft.component
def SponsorPicker() -> ft.Control:
    """The picker, or "Not available" for an account that doesn't scan for a sponsor.

    Re-checked on every render, as the scanner is (architecture §12.4): a sponsor's
    own account, a signed-out session or no mock URL (D-51) never sees the list.
    """
    prefs = use_prefs()
    account = use_account()
    flags = account.role_flags
    allowed = (
        prefs.private_api_enabled
        and account.signed_in
        and may_open(ToolKey.LEAD, flags)
        and scans_for_sponsor(flags)
    )
    if not allowed:
        return NotAvailable(title=TITLE)
    return SponsorList(owner=account.owner)


@ft.component
def SponsorList(*, owner: str) -> ft.Control:
    """The search field and the sponsors, or the list's loading, failed or empty state.

    Args:
        owner: The signed-in account; its saved sponsor is the one ticked.
    """
    svc = use_services()
    tokens = use_tokens()
    margin = use_margin(LIST)  # its width class (D-305)
    field = use_field_query()
    loaded, retry = use_fetch(fetch_sponsors, what="Sponsors")
    picking = use_pick(save_sponsor)
    chosen, set_chosen = ft.use_state("")  # the saved sponsor's id

    @report_errors
    async def read_chosen() -> None:
        sponsor = await read_sponsor(svc.storage)
        set_chosen(sponsor.id if sponsor is not None else "")

    ft.use_effect(read_chosen, [owner])

    head: list[ft.Control] = []
    items: list[ft.Control] = []
    if loaded.status == "loading":
        items.append(spinner(LOADING))
    elif loaded.value is None:  # failed: offline or an error (D-120)
        items.append(not_loaded(NOT_LOADED, PREFIX, retry))
    elif not loaded.value:
        items.append(
            EmptyState(
                NONE_AVAILABLE,
                icon=ft.Icons.STOREFRONT_OUTLINED,
                body=NONE_AVAILABLE_BODY,
                identifier=f"{PREFIX}.empty",
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
                identifier=f"{PREFIX}.search",
                high_contrast=tokens.high_contrast,
            )
        )
        found = filter_sponsors(loaded.value, field.value)
        items.extend(
            SponsorRow(sponsor, sponsor.id == chosen, picking.pick) for sponsor in found
        )
        if not found:
            items.append(no_match("sponsors", field.value, PREFIX, field.clear))
    return picker_page(
        title=TITLE,
        prefix=PREFIX,
        cancel=picking.cancel,
        margin=margin,
        head=head,
        items=items,
    )


def phrase(sponsor: LeadSponsor, selected: bool) -> str:
    """Return what a screen reader says for a row: "Example Corp, Booth 101, selected"."""
    parts = [sponsor.name]
    if sponsor.booth:
        parts.append(f"Booth {sponsor.booth}")
    if selected:
        parts.append("selected")
    return ", ".join(parts)


def SponsorRow(
    sponsor: LeadSponsor,
    selected: bool,
    on_pick: Callable[[LeadSponsor], Awaitable[None]],
) -> ft.Control:
    """Return one sponsor's row, a memoised component keyed by its id (D-153).

    So a keystroke re-renders only the rows it brings back; 150 rows stay quick.

    Args:
        sponsor: The sponsor.
        selected: It is the saved choice.
        on_pick: Saves it and goes back; stable across renders (``use_callback``).
    """
    # As SessionRow's: ft.component's typing leaves out the key= its wrapper takes.
    return _SponsorRow(sponsor, selected, on_pick, key=sponsor.id)  # pyright: ignore[reportCallIssue]


@ft.memo
@ft.component
def _SponsorRow(
    sponsor: LeadSponsor,
    selected: bool,
    on_pick: Callable[[LeadSponsor], Awaitable[None]],
) -> ft.Control:
    """The body of ``SponsorRow``: plate, name and booth, a tick when selected."""

    @report_errors
    async def pick() -> None:
        await on_pick(sponsor)

    lines: list[ft.Control] = [
        ft.Text(sponsor.name, theme_style=ft.TextThemeStyle.BODY_LARGE)
    ]
    if sponsor.booth:
        lines.append(
            ft.Text(
                f"Booth {sponsor.booth}",
                theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                color=ft.Colors.ON_SURFACE_VARIANT,
            )
        )
    return choice_row(
        identifier=f"{PREFIX}.{sponsor.id}",
        phrase=phrase(sponsor, selected),
        lines=lines,
        selected=selected,
        on_click=pick,
        leading=logo_tile(sponsor.name, sponsor.logo_url, size=PLATE),
    )
