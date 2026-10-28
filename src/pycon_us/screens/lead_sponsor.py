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
"No sponsors available" for an empty one. A saved sponsor needs no list to scan.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

import flet as ft

from pycon_us.account import use_account
from pycon_us.core.lead_sponsors import LeadSponsor, filter_sponsors
from pycon_us.core.staff_tools import ToolKey, may_open, scans_for_sponsor
from pycon_us.locations import parent_of
from pycon_us.prefs import use_prefs
from pycon_us.services import use_services
from pycon_us.services.api import ApiError, NetworkError
from pycon_us.services.errors import report_errors
from pycon_us.staff_sponsor import fetch_sponsors, read_sponsor, save_sponsor
from pycon_us.theme import use_tokens
from pycon_us.ui.fields import SearchField, use_field_query
from pycon_us.ui.logos import logo_tile
from pycon_us.ui.scaffold import AppScaffold
from pycon_us.ui.scan_screen import NotAvailable
from pycon_us.ui.semantics import named
from pycon_us.ui.snack_bars import say_if_unsaved
from pycon_us.ui.states import EmptyState
from pycon_us.ui.widths import LIST, capped, sides, use_margin

logger = logging.getLogger(__name__)

SEGMENT = "sponsor"
"""The picker's segment under the Lead scanner's route, ``…/staff/lead/sponsor``."""

TITLE = "Choose sponsor"
"""The app bar's title, and the scan screen's button that opens the page."""

CANCEL = "Cancel"
SEARCH_HINT = "Search sponsors"
CLEAR_SEARCH = "Clear search"
LOADING = "Loading sponsors"
NOT_LOADED = "Couldn't load sponsors"
NOT_LOADED_BODY = "Check your connection, then try again."
RETRY = "Retry"
NONE_AVAILABLE = "No sponsors available"
NONE_AVAILABLE_BODY = "Ask the organisers to add the sponsors you scan for."

PLATE = 40
"""A row's logo plate, in dp: with its padding, a 56 dp row."""

type Status = Literal["loading", "failed", "loaded"]


@dataclass(frozen=True)
class Loaded:
    """Where the list's fetch is.

    Attributes:
        status: Loading, failed (offline or an error) or loaded.
        sponsors: The sponsors, once loaded.
    """

    status: Status
    sponsors: tuple[LeadSponsor, ...] = ()


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
    page = ft.context.page
    view_path = ft.use_view_path()
    svc = use_services()
    tokens = use_tokens()
    margin = use_margin(LIST)  # its width class (D-305)
    field = use_field_query()
    loaded, set_loaded = ft.use_state(Loaded("loading"))
    tries, set_tries = ft.use_state(0)  # Retry asks again
    chosen, set_chosen = ft.use_state("")  # the saved sponsor's id

    @report_errors
    async def load() -> None:
        set_loaded(Loaded("loading"))
        api = svc.api
        try:
            if api is None:  # the URL went meanwhile; the guard follows
                raise NetworkError("no mock client")
            sponsors = await fetch_sponsors(api)
        except (NetworkError, ApiError) as error:
            logger.info("Sponsors not loaded: %s", type(error).__name__)
            set_loaded(Loaded("failed"))
            return
        set_loaded(Loaded("loaded", sponsors))

    ft.use_effect(load, [tries])

    @report_errors
    async def read_chosen() -> None:
        sponsor = await read_sponsor(svc.storage)
        set_chosen(sponsor.id if sponsor is not None else "")

    ft.use_effect(read_chosen, [owner])

    @report_errors
    async def pick(sponsor: LeadSponsor) -> None:
        saved = await save_sponsor(svc.storage, sponsor)
        say_if_unsaved(page, saved)
        if saved:  # else stay: the scanner reads the choice from storage (D-425)
            page.navigate(parent_of(view_path, svc.memory.search_base))

    on_pick = ft.use_callback(pick, [view_path])

    @report_errors
    def cancel(_: ft.Event[ft.IconButton]) -> None:
        page.navigate(parent_of(view_path, svc.memory.search_base))  # as Back

    @report_errors
    def retry() -> None:
        set_tries(tries + 1)

    head: list[ft.Control] = []
    items: list[ft.Control] = []
    match loaded.status:
        case "loading":
            items.append(spinner())
        case "failed":
            items.append(
                EmptyState(
                    NOT_LOADED,
                    icon=ft.Icons.CLOUD_OFF_OUTLINED,
                    body=NOT_LOADED_BODY,
                    action=RETRY,
                    on_action=retry,
                    identifier="lead.sponsor.failed",
                )
            )
        case "loaded" if not loaded.sponsors:
            items.append(
                EmptyState(
                    NONE_AVAILABLE,
                    icon=ft.Icons.STOREFRONT_OUTLINED,
                    body=NONE_AVAILABLE_BODY,
                    identifier="lead.sponsor.empty",
                )
            )
        case "loaded":
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
                    identifier="lead.sponsor.search",
                    high_contrast=tokens.high_contrast,
                )
            )
            found = filter_sponsors(loaded.sponsors, field.value)
            items.extend(
                SponsorRow(sponsor, sponsor.id == chosen, on_pick) for sponsor in found
            )
            if not found:
                items.append(
                    EmptyState(
                        no_match(field.value),
                        icon=ft.Icons.SEARCH_OFF,
                        action=CLEAR_SEARCH,
                        on_action=field.clear,  # the focus goes back to the field
                        identifier="lead.sponsor.no_match",
                    )
                )
    return AppScaffold(
        title=TITLE,
        actions=[
            # An icon, as M3's full-screen dialogs close: a text button's label grew
            # with the text and squeezed the title to "Choose sp…" at 200 %.
            named(
                "lead.sponsor.cancel",
                ft.IconButton(ft.Icons.CLOSE, tooltip=CANCEL, on_click=cancel),
            )
        ],
        body=ft.Column(
            [
                # The field in a column of its own, so the list keeps its place as
                # the states come and go (D-153).
                capped(
                    ft.Column(
                        head,
                        spacing=0,
                        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    ),
                    margin,
                ),
                ft.ListView(items, expand=True, padding=sides(margin, bottom=24)),
            ],
            spacing=0,
            expand=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        ),
    )


def no_match(query: str) -> str:
    """Return the no-match state's title: "No sponsors match “acme”"."""
    return (
        f"No sponsors match \N{LEFT DOUBLE QUOTATION MARK}{query.strip()}"
        "\N{RIGHT DOUBLE QUOTATION MARK}"
    )


def spinner() -> ft.Control:
    """Return the loading state: a ring, read as "Loading sponsors"."""
    return ft.Container(
        ft.Semantics(
            label=LOADING,
            container=True,
            exclude_semantics=True,
            content=ft.ProgressRing(),
        ),
        padding=48,
        alignment=ft.Alignment.TOP_CENTER,
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

    texts: list[ft.Control] = [
        ft.Text(sponsor.name, theme_style=ft.TextThemeStyle.BODY_LARGE)
    ]
    if sponsor.booth:
        texts.append(
            ft.Text(
                f"Booth {sponsor.booth}",
                theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                color=ft.Colors.ON_SURFACE_VARIANT,
            )
        )
    return ft.MergeSemantics(  # the phrase and the tap's action: one node
        content=ft.Container(
            ft.Semantics(
                label=phrase(sponsor, selected),
                identifier=f"lead.sponsor.{sponsor.id}",
                button=True,
                exclude_semantics=True,  # the phrase replaces the texts
                content=ft.Row(
                    [
                        logo_tile(sponsor.name, sponsor.logo_url, size=PLATE),
                        ft.Column(texts, spacing=2, expand=True),
                        # Kept, transparent when not chosen, so the texts never move.
                        ft.Icon(
                            ft.Icons.CHECK,
                            color=ft.Colors.PRIMARY
                            if selected
                            else ft.Colors.TRANSPARENT,
                        ),
                    ],
                    spacing=16,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ),
            ink=True,
            on_click=pick,
            bgcolor=ft.Colors.SECONDARY_CONTAINER if selected else None,
            padding=ft.Padding.symmetric(horizontal=16, vertical=8),
        )
    )
