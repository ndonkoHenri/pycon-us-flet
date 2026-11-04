"""Swag pickup (`/more/staff/swag`): the shared scan screen, looking up what's left.

A mount of `ui/scan_screen.py`'s `ScanScreen` (SHIRT-01, SHIRT-02, SHIRT-04's
offline half; D-416). It re-checks its rule on every render (architecture §12.4): an
account without `door_check`, a signed-out session or no mock URL (D-51) sees "Not
available for this account". It is mounted at `/now/staff/swag` too and records
itself as the last tool opened (D-421); More and Now list it (`BUILT_TOOLS`, #769).

The **categories** head the screen, in the context slot rather than a pushed page:
swag has a handful. A wrapping row of filter chips from `swag_catalog()` of the
`redeemable` catalog, fetched as the screen opens (a progress line meanwhile,
"Couldn't load categories" with Retry on a failure, D-120; `ui/staff_picker.py`'s
`use_fetch()`); until it has loaded, a connection that returns restarts the fetch.
The choice is the staff key `staff_swag_categories()`, read from storage as the
screen opens, as the Lead scanner's sponsor is (D-425), so it survives a restart and
goes at a sign-out (D-414); ids no longer in the catalog are ignored.

Swag pickup is **online only** (D-56): while `use_online()` says offline (checked
every 5 s), and while no category is chosen, scanning is paused with the reason under
the field, so a HID scanner's submit is dropped with its text (D-420, D-471). A badge
is looked up by `swag.look_up()`; items left open `ui/swag_sheet.py`'s hand-out sheet,
pre-ticked, and the panel says how the hand-out went (#769). Scanning is paused while
the sheet is open ("Paused while the hand-out is open").
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import partial
from typing import cast

import flet as ft

from pycon_us.account import use_account
from pycon_us.check_in_api import fetch_catalog
from pycon_us.core.check_in import Category, swag_catalog
from pycon_us.core.staff_tools import TOOLS, ToolKey
from pycon_us.locations import is_top_view
from pycon_us.services import use_services
from pycon_us.services.api import ApiClient
from pycon_us.services.errors import report_errors
from pycon_us.services.pref_keys import staff_swag_categories
from pycon_us.swag import look_up
from pycon_us.ui.hooks import use_mounted
from pycon_us.ui.online import use_online
from pycon_us.ui.scan_screen import NotAvailable, ScanScreen, use_tool_allowed
from pycon_us.ui.semantics import named
from pycon_us.ui.snack_bars import say_if_unsaved
from pycon_us.ui.staff_picker import Loaded, use_fetch
from pycon_us.ui.swag_sheet import use_swag_sheet

type OnToggle = Callable[[Category, bool], Awaitable[None]]
"""Saves a category chosen (True) or no longer chosen (False)."""

TITLE = next(tool.title for tool in TOOLS if tool.key is ToolKey.SWAG)
"""The app bar's title, "Swag pickup", as the staff entry points name it."""

CHOOSE = "Choose what to hand out"
OFFLINE = "Swag pickup needs a connection"
HAND_OUT_OPEN = "Paused while the hand-out is open"
"""Why scanning is paused: no category chosen, no connection (D-56), or the sheet."""

LOADING = "Loading categories"
NOT_LOADED = "Couldn't load categories"
NONE_AVAILABLE = "No swag categories available"
RETRY = "Retry"
"""The categories' states (D-120)."""


@dataclass(frozen=True)
class Chosen:
    """The category ids chosen, as read for an account.

    Attributes:
        owner: The account they were read for; another's never stand (D-423).
        ids: The ids chosen, those no longer in the catalog included.
    """

    owner: str
    ids: frozenset[int]


async def fetch_categories(api: ApiClient) -> tuple[Category, ...]:
    """Return the swag categories, in the catalog's order.

    Args:
        api: The signed client.
    """
    return swag_catalog(await fetch_catalog(api)).categories


@ft.component
def SwagPickup() -> ft.Control:
    """Swag pickup, or its "Not available" state for an account it refuses."""
    allowed = use_tool_allowed(ToolKey.SWAG)
    account = use_account()
    memory = use_services().memory
    if not allowed:
        return NotAvailable(title=TITLE, source=__name__)
    memory.staff_tool = ToolKey.SWAG  # plain: Now's card reads it when it renders
    return SwagTool(owner=account.owner)


@ft.component
def SwagTool(*, owner: str) -> ft.Control:
    """The scan screen headed by the category chips, paused until it can scan.

    Args:
        owner: The signed-in account (`Account.owner`).
    """
    page = ft.context.page
    view_path = ft.use_view_path()
    svc = use_services()
    key = staff_swag_categories(svc.storage.year)
    online = use_online(svc, watch=True)
    loaded, retry = use_fetch(fetch_categories, what="Swag categories")
    chosen, set_chosen = ft.use_state(cast(Chosen | None, None))
    mounted = use_mounted()  # a late SnackBar is then dropped
    current = chosen.ids if chosen is not None and chosen.owner == owner else None
    latest = ft.use_ref(frozenset[int]())  # what a toggle builds on (#756)
    latest.current = current or frozenset()

    was_online = ft.use_ref(online)  # so opening the screen isn't a return

    @report_errors
    def reload_when_online() -> None:
        returned = online and not was_online.current
        was_online.current = online
        # Even while loading: a fetch sent before the return may still fail, and Flet
        # cancels it as the new one starts (D-70), so only the newest answer shows.
        if returned and loaded.status != "loaded":
            retry()

    ft.use_effect(reload_when_online, [online])

    @report_errors
    async def read_chosen() -> None:
        stored = await svc.storage.get(key)  # a failure reads []
        ids = frozenset(int(i) for i in stored if i.isdigit())
        set_chosen(Chosen(owner, ids))

    ft.use_effect(read_chosen, [owner])

    @report_errors
    async def toggle(category: Category, selected: bool) -> None:
        before = latest.current or frozenset()
        ids = before | {category.id} if selected else before - {category.id}
        latest.current = ids
        set_chosen(Chosen(owner, ids))
        saved = await svc.storage.set(key, [str(i) for i in sorted(ids)])
        if mounted.current and is_top_view(page.route, view_path):
            say_if_unsaved(page, saved)  # chosen for this visit all the same

    sheet = use_swag_sheet()
    categories = tuple(c for c in loaded.value or () if c.id in (current or ()))
    paused = (
        HAND_OUT_OPEN
        if sheet.is_open
        else OFFLINE
        if not online
        else CHOOSE
        if not categories
        else None
    )
    return ScanScreen(
        title=TITLE,
        source=__name__,
        on_badge=partial(look_up, svc.api, categories=categories, offer=sheet.offer),
        context=category_area(loaded, current, toggle, retry),
        paused=paused,
    )


def category_area(
    loaded: Loaded[tuple[Category, ...]],
    chosen: frozenset[int] | None,
    on_toggle: OnToggle,
    on_retry: ft.ControlEventHandler[ft.TextButton],
) -> ft.Control:
    """Return the chips, or the catalog's loading, failed or empty state.

    The chips wait for the stored choice too: a tap before it is read would build on
    nothing, and the read, coming after, would undo the tap (seen on the simulator).

    Args:
        loaded: Where the catalog's fetch is.
        chosen: The ids chosen, or None until they are read.
        on_toggle: Called with a category and whether it is now selected.
        on_retry: Asks for the catalog again.
    """
    categories = loaded.value or ()
    match loaded.status:
        case "loading":
            return loading_line()
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
        case _ if chosen is None:
            return loading_line()
        case _ if not categories:
            return ft.Text(
                NONE_AVAILABLE,
                theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                color=ft.Colors.ON_SURFACE_VARIANT,
            )
        case _:
            return ft.Row(
                [category_chip(c, c.id in chosen, on_toggle) for c in categories],
                wrap=True,
                spacing=8,
                run_spacing=8,
            )


def loading_line() -> ft.Control:
    """Return the progress line read "Loading categories"."""
    return ft.Semantics(
        label=LOADING,
        identifier="swag.categories.loading",
        content=ft.ProgressBar(),
    )


def category_chip(
    category: Category, selected: bool, on_toggle: OnToggle
) -> ft.Control:
    """Return a category's filter chip: one 48 dp stop, read with its state.

    Its identifier is `swag.category.<id>`; Flutter's chip says "selected".

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
