"""The session picker (``…/staff/door/session``): what Door check checks in for (#764).

DOOR-01 and DOOR-02, on a pushed page as the Lead scanner's sponsor picker (D-425,
D-433; its parts are ``ui/staff_picker.py``'s), for accounts that may open Door check
(anyone else, and a deep link, sees "Not available for this account"). Ionic showed an
empty "Category" header when its call failed, sorted dates in a hard-coded 2026 and hid
the choice behind the camera once scanning started.

Here, single-select category chips from the catalog's door part (``door.category.<id>``;
a second tap clears), then, once one is chosen, a search field (``door.session.search``),
"All sessions in this category" (``door.session.all``) and the category's sessions
under a level-2 heading per day in ``product_sort_key()`` order, the undated ones last
under "Other sessions" (``door.session.<id>``, one node read "All about decorators,
Wednesday 9:00 AM, selected"). A tap saves the choice (``STAFF_DOOR_SESSION``) and goes
back; Cancel (a close icon) and Back leave it as it was. The catalog is fetched each time
the page opens and never kept (``fetch_door_catalog()``): a spinner meanwhile,
"Couldn't load sessions" with Retry offline or on an error (D-120), "No sessions
available" for none, "No sessions match “x”" with Clear search.
"""

from collections.abc import Awaitable, Callable

import flet as ft

from pycon_us.account import use_account
from pycon_us.core.check_in import Catalog, Category
from pycon_us.core.door_sessions import (
    DoorChoice,
    DoorSession,
    by_day,
    choose_all,
    choose_session,
    door_sessions,
    filter_sessions,
)
from pycon_us.core.staff_tools import ToolKey, may_open
from pycon_us.core.timefmt import day_heading, weekday_name
from pycon_us.door_choice import (
    fetch_door_catalog,
    read_door_session,
    save_door_session,
)
from pycon_us.prefs import use_prefs
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.theme import use_tokens
from pycon_us.ui.fields import SearchField, use_field_query
from pycon_us.ui.scaffold import SectionHeader
from pycon_us.ui.scan_screen import NotAvailable
from pycon_us.ui.semantics import named
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

SEGMENT = "session"
"""The picker's segment under Door check's route, ``…/staff/door/session``."""

TITLE = "Choose session"
"""The app bar's title, and the scan screen's button that opens the page."""

PREFIX = "door.session"
"""The page's identifiers' start (decisions §M)."""

SEARCH_HINT = "Search sessions"
LOADING = "Loading sessions"
NOT_LOADED = "Couldn't load sessions"
NONE_AVAILABLE = "No sessions available"
NONE_AVAILABLE_BODY = "Ask the organisers to add the sessions you check in for."
ALL_SESSIONS = "All sessions in this category"
OTHER_SESSIONS = "Other sessions"
"""The heading over the sessions whose name gives no date."""


@ft.component
def SessionPicker() -> ft.Control:
    """The picker, or "Not available" for an account that may not open Door check.

    Re-checked on every render, as Door check is (architecture §12.4): an account
    without ``door_check``, a signed-out session or no mock URL (D-51) sees no list.
    """
    prefs = use_prefs()
    account = use_account()
    allowed = (
        prefs.private_api_enabled
        and account.signed_in
        and may_open(ToolKey.DOOR, account.role_flags)
    )
    if not allowed:
        return NotAvailable(title=TITLE)
    return SessionList(owner=account.owner)


def no_choice() -> DoorChoice | None:
    """Return None: nothing chosen, or not read yet (``SessionList``'s first state)."""
    return None


def no_category() -> int | None:
    """Return None: no category chosen (``SessionList``'s first state, typed)."""
    return None


@ft.component
def SessionList(*, owner: str) -> ft.Control:
    """The category chips and the chosen category's sessions, or the list's state.

    The saved choice's category is chosen as the page opens, its row ticked.

    Args:
        owner: The signed-in account; its saved choice is the one ticked.
    """
    svc = use_services()
    tokens = use_tokens()
    margin = use_margin(LIST)  # its width class (D-305)
    field = use_field_query()
    loaded, retry = use_fetch(fetch_door_catalog, what="Sessions")
    picking = use_pick(save_door_session)
    chosen, set_chosen = ft.use_state(no_choice)
    category, set_category = ft.use_state(no_category)

    @report_errors
    async def read_chosen() -> None:
        choice = await read_door_session(svc.storage)
        set_chosen(choice)
        if choice is not None:  # a category tapped meanwhile stays
            set_category(lambda now: choice.category_id if now is None else now)

    ft.use_effect(read_chosen, [owner])

    @report_errors
    def tap_category(e: ft.Event[ft.Chip]) -> None:
        tapped = e.control.data
        set_category(None if tapped == category else tapped)  # a second tap clears

    head: list[ft.Control] = []
    items: list[ft.Control] = []
    catalog = loaded.value
    if loaded.status == "loading":
        items.append(spinner(LOADING))
    elif catalog is None:  # failed: offline or an error (D-120)
        items.append(not_loaded(NOT_LOADED, PREFIX, retry))
    elif not catalog.categories:
        items.append(none_available())
    else:
        head.append(category_chips(catalog, category, tap_category))
        current = next((c for c in catalog.categories if c.id == category), None)
        if current is not None:
            year = svc.year.conference.year
            sessions = door_sessions(catalog, current.id, year)
            if sessions:
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
                found = filter_sessions(sessions, field.value)
                searching = bool(field.value.strip())
                items.extend(
                    session_items(
                        current, sessions, found, searching, chosen, picking.pick
                    )
                )
                if not found:
                    items.append(no_match("sessions", field.value, PREFIX, field.clear))
            else:
                items.append(none_available())
    return picker_page(
        title=TITLE,
        prefix=PREFIX,
        cancel=picking.cancel,
        margin=margin,
        head=head,
        items=items,
    )


def none_available() -> ft.Control:
    """Return the empty state: "No sessions available"."""
    return EmptyState(
        NONE_AVAILABLE,
        icon=ft.Icons.EVENT_BUSY_OUTLINED,
        body=NONE_AVAILABLE_BODY,
        identifier=f"{PREFIX}.empty",
    )


def category_chips(
    catalog: Catalog, category: int | None, on_click: ft.ControlEventHandler
) -> ft.Control:
    """Return the category chips, single-select, wrapping onto more lines (DOOR-01).

    Each chip is one node, read as its name, "selected" when it is, and a button.

    Args:
        catalog: The door's catalog.
        category: The chosen category's id, or None.
        on_click: Chooses the tapped chip's category (its ``data``), or clears it.
    """
    return ft.Container(
        ft.Row(
            [
                named(
                    f"door.category.{c.id}",
                    ft.Chip(
                        label=c.name,
                        selected=c.id == category,
                        show_checkmark=True,  # not colour alone (D-33)
                        data=c.id,
                        # A click, not on_select: Flutter would toggle the chip
                        # itself, and ``selected`` is only ours (search's chips).
                        on_click=on_click,
                    ),
                )
                for c in catalog.categories
            ],
            wrap=True,
            spacing=8,
            run_spacing=8,
        ),
        padding=ft.Padding.symmetric(horizontal=16, vertical=8),
    )


def session_items(
    category: Category,
    sessions: tuple[DoorSession, ...],
    found: tuple[DoorSession, ...],
    searching: bool,
    chosen: DoorChoice | None,
    on_pick: Callable[[DoorChoice], Awaitable[None]],
) -> list[ft.Control]:
    """Return "All sessions in this category", then the sessions found under their day.

    "All sessions" is left out while searching: it is not a session that matches.

    Args:
        category: The chosen category.
        sessions: Its sessions, in order: what "All sessions" chooses.
        found: Those the search keeps (all of them without a search).
        searching: The search field holds words.
        chosen: The saved choice, or None.
        on_pick: Saves a choice and goes back (``Picking.pick``).
    """
    mine = chosen if chosen is not None and chosen.category_id == category.id else None
    items: list[ft.Control] = []
    if not searching:

        @report_errors
        async def pick_all() -> None:
            await on_pick(choose_all(category, sessions))

        every = mine is not None and mine.all_sessions
        items.append(
            choice_row(
                identifier=f"{PREFIX}.all",
                phrase=f"{ALL_SESSIONS}, selected" if every else ALL_SESSIONS,
                lines=[ft.Text(ALL_SESSIONS, theme_style=ft.TextThemeStyle.BODY_LARGE)],
                selected=every,
                on_click=pick_all,
            )
        )
    single = mine.product_ids[0] if mine is not None and not mine.all_sessions else None
    for day, group in by_day(found):
        heading = day_heading(day) if day is not None else OTHER_SESSIONS
        items.append(SectionHeader(heading, level=2))
        items.extend(SessionRow(category.id, s, s.id == single, on_pick) for s in group)
    return items


def phrase(session: DoorSession, selected: bool) -> str:
    """Return a row's words: "All about decorators, Wednesday 9:00 AM, selected"."""
    parts = [session.title]
    if session.day is not None:
        parts.append(f"{weekday_name(session.day)} {session.time}")
    if selected:
        parts.append("selected")
    return ", ".join(parts)


def SessionRow(
    category: int,
    session: DoorSession,
    selected: bool,
    on_pick: Callable[[DoorChoice], Awaitable[None]],
) -> ft.Control:
    """Return one session's row, a memoised component keyed by its id (D-153).

    Args:
        category: Its category's id.
        session: The session.
        selected: It is the saved choice.
        on_pick: Saves a choice and goes back; stable across renders.
    """
    # As SessionRow's: ft.component's typing leaves out the key= its wrapper takes.
    return _SessionRow(category, session, selected, on_pick, key=session.id)  # pyright: ignore[reportCallIssue]


@ft.memo
@ft.component
def _SessionRow(
    category: int,
    session: DoorSession,
    selected: bool,
    on_pick: Callable[[DoorChoice], Awaitable[None]],
) -> ft.Control:
    """The body of ``SessionRow``: the title and the time, a tick when selected."""

    @report_errors
    async def pick() -> None:
        await on_pick(choose_session(category, session))

    lines: list[ft.Control] = [
        ft.Text(session.title, theme_style=ft.TextThemeStyle.BODY_LARGE)
    ]
    if session.time:
        lines.append(
            ft.Text(
                session.time,
                theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                color=ft.Colors.ON_SURFACE_VARIANT,
            )
        )
    return choice_row(
        identifier=f"{PREFIX}.{session.id}",
        phrase=phrase(session, selected),
        lines=lines,
        selected=selected,
        on_click=pick,
    )
