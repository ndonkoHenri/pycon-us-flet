"""Swag pickup (``/more/staff/swag``): the shared scan screen, looking up what's left.

A mount of ``ui/scan_screen.py``'s ``ScanScreen`` (SHIRT-01, SHIRT-02, SHIRT-04's
offline half; D-416). It re-checks its rule on every render (architecture §12.4): an
account without ``door_check``, a signed-out session or no mock URL (D-51) sees "Not
available for this account". It is mounted at ``/now/staff/swag`` too and records
itself as the last tool opened (D-421); until #769 adds its entries, a deep link is
the only way in.

The **categories** head the screen, in the context slot rather than a pushed page:
swag has a handful. A wrapping row of filter chips from ``swag_catalog()`` of the
``redeemable`` catalog, fetched as the screen opens (a progress line meanwhile,
"Couldn't load categories" with Retry on a failure, D-120). The choice is the staff key
``STAFF_SWAG_CATEGORIES``, read from storage as the screen opens, as the Lead
scanner's sponsor is (D-425), so it survives a restart and goes at a sign-out (D-414);
ids no longer in the catalog are ignored.

Swag pickup is **online only** (D-56): while ``use_online()`` says offline (checked
every 5 s), and while no category is chosen, scanning is paused with the reason under
the field, so a HID scanner's submit is dropped and its text kept (D-420). A badge is
looked up by ``swag.look_up()``; #769 brings the hand-out sheet and the redeem.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import partial
from typing import Literal

import flet as ft

from pycon_us.account import use_account
from pycon_us.check_in_api import fetch_catalog
from pycon_us.core.check_in import Category, swag_catalog
from pycon_us.core.staff_tools import TOOLS, ToolKey, may_open
from pycon_us.locations import is_top_view
from pycon_us.prefs import use_prefs
from pycon_us.services import use_services
from pycon_us.services.api import ApiError, NetworkError
from pycon_us.services.errors import report_errors
from pycon_us.services.storage import STAFF_SWAG_CATEGORIES
from pycon_us.swag import look_up
from pycon_us.ui.online import use_online
from pycon_us.ui.scan_screen import NotAvailable, ScanScreen
from pycon_us.ui.semantics import named
from pycon_us.ui.snack_bars import say_if_unsaved

type OnToggle = Callable[[Category, bool], Awaitable[None]]
"""Saves a category chosen (True) or no longer chosen (False)."""

logger = logging.getLogger(__name__)

TITLE = next(tool.title for tool in TOOLS if tool.key is ToolKey.SWAG)
"""The app bar's title, "Swag pickup", as the staff entry points name it."""

CHOOSE = "Choose what to hand out"
OFFLINE = "Swag pickup needs a connection"
"""Why scanning is paused: no category chosen, or no connection (D-56)."""

LOADING = "Loading categories"
NOT_LOADED = "Couldn't load categories"
NONE_AVAILABLE = "No swag categories available"
RETRY = "Retry"
"""The categories' states (D-120)."""

type Status = Literal["loading", "failed", "loaded"]


@dataclass(frozen=True)
class Loaded:
    """Where the catalog's fetch is.

    Attributes:
        status: Loading, failed (offline or an error) or loaded.
        categories: The swag categories, once loaded, in the catalog's order.
    """

    status: Status
    categories: tuple[Category, ...] = ()


@dataclass(frozen=True)
class Chosen:
    """The category ids chosen, as read for an account.

    Attributes:
        owner: The account they were read for; another's never stand (D-423).
        ids: The ids chosen, those no longer in the catalog included.
    """

    owner: str
    ids: frozenset[int]


@ft.component
def SwagPickup() -> ft.Control:
    """Swag pickup, or its "Not available" state for an account it refuses."""
    prefs = use_prefs()
    account = use_account()
    memory = use_services().memory
    allowed = (
        prefs.private_api_enabled
        and account.signed_in
        and may_open(ToolKey.SWAG, account.role_flags)
    )
    if not allowed:
        return NotAvailable(title=TITLE)
    memory.staff_tool = ToolKey.SWAG  # plain: Now's card reads it when it renders
    return SwagTool(owner=account.owner)


@ft.component
def SwagTool(*, owner: str) -> ft.Control:
    """The scan screen headed by the category chips, paused until it can scan.

    Args:
        owner: The signed-in account (``Account.owner``).
    """
    page = ft.context.page
    view_path = ft.use_view_path()
    svc = use_services()
    online = use_online(svc, watch=True)
    loaded, set_loaded = ft.use_state(Loaded("loading"))
    tries, set_tries = ft.use_state(0)  # Retry asks again
    chosen, set_chosen = ft.use_state(not_read)
    mounted = ft.use_ref(True)  # cleared on unmount: a late reply is then dropped
    current = chosen.ids if chosen is not None and chosen.owner == owner else None
    latest = ft.use_ref(frozenset[int]())  # what a toggle builds on (#756)
    latest.current = current or frozenset()

    @report_errors
    def unmount() -> None:
        """Mark the screen gone, so a fetch or save still running stays quiet."""
        mounted.current = False

    ft.use_effect(lambda: None, [], cleanup=unmount)

    @report_errors
    async def load() -> None:
        set_loaded(Loaded("loading"))
        api = svc.api
        try:
            if api is None:  # the URL went meanwhile; the guard follows
                raise NetworkError("no mock client")
            catalog = swag_catalog(await fetch_catalog(api))
        except (NetworkError, ApiError) as error:
            logger.info("Swag categories not loaded: %s", type(error).__name__)
            if mounted.current:
                set_loaded(Loaded("failed"))
            return
        if mounted.current:
            set_loaded(Loaded("loaded", catalog.categories))

    ft.use_effect(load, [tries])

    @report_errors
    def reload_when_online() -> None:
        if online and loaded.status == "failed":
            set_tries(lambda n: n + 1)

    ft.use_effect(reload_when_online, [online])

    @report_errors
    async def read_chosen() -> None:
        stored = await svc.storage.get(STAFF_SWAG_CATEGORIES)  # a failure reads []
        ids = frozenset(int(i) for i in stored if i.isdigit())
        if mounted.current:
            set_chosen(Chosen(owner, ids))

    ft.use_effect(read_chosen, [owner])

    @report_errors
    async def toggle(category: Category, selected: bool) -> None:
        before = latest.current or frozenset()
        ids = before | {category.id} if selected else before - {category.id}
        latest.current = ids
        set_chosen(Chosen(owner, ids))
        saved = await svc.storage.set(
            STAFF_SWAG_CATEGORIES, [str(i) for i in sorted(ids)]
        )
        if mounted.current and is_top_view(page.route, view_path):
            say_if_unsaved(page, saved)  # chosen for this visit all the same

    @report_errors
    def retry() -> None:
        set_tries(lambda n: n + 1)

    categories = tuple(c for c in loaded.categories if c.id in (current or ()))
    paused = OFFLINE if not online else CHOOSE if not categories else None
    return ScanScreen(
        title=TITLE,
        on_badge=partial(look_up, svc.api, categories=categories),
        context=category_area(loaded, current or frozenset(), toggle, retry),
        paused=paused,
    )


def category_area(
    loaded: Loaded,
    chosen: frozenset[int],
    on_toggle: OnToggle,
    on_retry: ft.ControlEventHandler[ft.TextButton],
) -> ft.Control:
    """Return the chips, or the catalog's loading, failed or empty state.

    Args:
        loaded: Where the catalog's fetch is.
        chosen: The ids chosen.
        on_toggle: Called with a category and whether it is now selected.
        on_retry: Asks for the catalog again.
    """
    match loaded.status:
        case "loading":
            return ft.Semantics(
                label=LOADING,
                identifier="swag.categories.loading",
                content=ft.ProgressBar(),
            )
        case "failed":
            return ft.Row(
                [
                    ft.Text(
                        NOT_LOADED,
                        theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                        color=ft.Colors.ERROR,
                    ),
                    named(
                        "swag.categories.retry",
                        ft.TextButton(RETRY, icon=ft.Icons.REFRESH, on_click=on_retry),
                    ),
                ],
                wrap=True,
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        case _ if not loaded.categories:
            return ft.Text(
                NONE_AVAILABLE,
                theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                color=ft.Colors.ON_SURFACE_VARIANT,
            )
        case _:
            return ft.Row(
                [
                    category_chip(c, c.id in chosen, on_toggle)
                    for c in loaded.categories
                ],
                wrap=True,
                spacing=8,
                run_spacing=8,
            )


def category_chip(
    category: Category, selected: bool, on_toggle: OnToggle
) -> ft.Control:
    """Return a category's filter chip: one 48 dp stop, read with its state.

    Its identifier is ``swag.category.<id>``; Flutter's chip says "selected".

    Args:
        category: The swag category.
        selected: Whether it is chosen.
        on_toggle: Called with the category and its new state.
    """

    @report_errors
    async def selected_now(e: ft.Event[ft.Chip]) -> None:
        # Flutter flips the chip and sends its new state before the event (chip.dart).
        await on_toggle(category, bool(e.control.selected))

    return named(
        f"swag.category.{category.id}",
        ft.Chip(
            label=category.name,
            leading=None
            if selected
            else ft.Icon(ft.Icons.REDEEM_OUTLINED, size=18, apply_text_scaling=True),
            selected=selected,
            show_checkmark=True,
            on_select=selected_now,
        ),
    )


def not_read() -> Chosen | None:
    """Return None: the choice not read yet, ``SwagTool``'s first state (typed)."""
    return None
