"""What the staff tools' "scan for X" pickers share, and the chip and buttons that open them.

The Lead scanner's sponsor picker (``screens/lead_sponsor.py``, D-425) and Door check's
session picker (``screens/door_session.py``, D-433) are one pattern: a pushed page that
fetches its list each time it opens (``use_fetch()``: a spinner, then the list, or
"Couldn't load …" with Retry, D-120), a close icon named "Cancel" that goes back as
Back does, rows that read as one phrase with the chosen one ticked (``choice_row()``),
and a tap that saves the choice and goes back (``use_pick()``), staying with "Couldn't
save your change" when the save fails, since the tool reads the choice from storage.

On the tool's scan screen, the choice heads the screen as an outlined chip that reopens
the picker (``context_chip()``), and with none the screen is paused with a tonal button
(``tool_button()``); ``Reading`` is the empty page while the tool reads its keys.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

import flet as ft

from pycon_us.locations import is_top_view, parent_of
from pycon_us.services import use_services
from pycon_us.services.api import ApiClient, ApiError, NetworkError
from pycon_us.services.errors import report_errors
from pycon_us.services.storage import Storage
from pycon_us.ui.buttons import LABEL_PADDING
from pycon_us.ui.scaffold import AppScaffold
from pycon_us.ui.semantics import named
from pycon_us.ui.snack_bars import say_if_unsaved
from pycon_us.ui.states import EmptyState
from pycon_us.ui.widths import LIST, capped, sides, use_margin

logger = logging.getLogger(__name__)

CANCEL = "Cancel"
CLEAR_SEARCH = "Clear search"
RETRY = "Retry"
NOT_LOADED_BODY = "Check your connection, then try again."
ROW_PADDING = 12
"""A choice row's top and bottom padding: with a 24 dp line, the 48 dp touch target."""

type Status = Literal["loading", "failed", "loaded"]


@dataclass(frozen=True)
class Loaded[T]:
    """Where a picker's fetch is.

    Attributes:
        status: Loading, failed (offline or an error) or loaded.
        value: What was fetched, once loaded.
    """

    status: Status
    value: T | None = None


def use_fetch[T](
    fetch: Callable[[ApiClient], Awaitable[T]], *, what: str
) -> tuple[Loaded[T], Callable[[], None]]:
    """Fetch a picker's list as it opens, and again at each Retry (a hook).

    A plain function that calls hooks, so the page calls it once per render, before
    any early return (D-70).

    Args:
        fetch: Asks the mock for the list, signed in.
        what: The list's name in the log, "Sponsors".

    Returns:
        Where the fetch is, and Retry, which fetches again.
    """
    svc = use_services()
    loaded, set_loaded = ft.use_state(Loaded[T]("loading"))
    tries, set_tries = ft.use_state(0)

    @report_errors
    async def load() -> None:
        set_loaded(Loaded[T]("loading"))
        api = svc.api
        try:
            if api is None:  # the URL went meanwhile; the page's guard follows
                raise NetworkError("no mock client")
            value = await fetch(api)
        except (NetworkError, ApiError) as error:
            logger.info("%s not loaded: %s", what, type(error).__name__)
            set_loaded(Loaded[T]("failed"))
            return
        set_loaded(Loaded("loaded", value))

    ft.use_effect(load, [tries])

    @report_errors
    def retry() -> None:
        set_tries(lambda n: n + 1)

    return loaded, retry


@dataclass(frozen=True)
class Picking[T]:
    """A picker's two ways back to its tool.

    Attributes:
        pick: Saves a choice and goes back; stable across renders (``use_callback``),
            so memoised rows can take it.
        cancel: Goes back and saves nothing, as Back does.
    """

    pick: Callable[[T], Awaitable[None]]
    cancel: Callable[[ft.Event[ft.IconButton]], None]


def use_pick[T](save: Callable[[Storage, T], Awaitable[bool]]) -> Picking[T]:
    """Return the picker's pick and Cancel (a hook; call it before any early return).

    A pick saves, then goes back to the tool, which reads the choice from storage
    (D-425); a save that fails stays and says so. A slow save can end after Cancel or
    Back: then the user is elsewhere, and neither a SnackBar nor a jump back is theirs.

    Args:
        save: Saves a choice; returns whether it was saved.
    """
    page = ft.context.page
    view_path = ft.use_view_path()
    svc = use_services()
    mounted = ft.use_ref(True)  # cleared on unmount: a late save then does nothing

    @report_errors
    def unmount() -> None:
        """Mark the page gone, so a save still running stays quiet."""
        mounted.current = False

    ft.use_effect(lambda: None, [], cleanup=unmount)

    @report_errors
    async def pick(choice: T) -> None:
        saved = await save(svc.storage, choice)
        if not (mounted.current and is_top_view(page.route, view_path)):
            return
        say_if_unsaved(page, saved)
        if saved:  # else stay: the tool reads the choice from storage
            page.navigate(parent_of(view_path, svc.memory.search_base))

    @report_errors
    def cancel(_: ft.Event[ft.IconButton]) -> None:
        page.navigate(parent_of(view_path, svc.memory.search_base))  # as Back

    return Picking(ft.use_callback(pick, [view_path, save]), cancel)


def picker_page(
    *,
    title: str,
    prefix: str,
    cancel: Callable[[ft.Event[ft.IconButton]], None],
    margin: float,
    head: list[ft.Control],
    items: list[ft.Control],
) -> ft.Control:
    """Return a picker's page: the title, Cancel, a fixed head, then the list.

    Called at the end of the page's component, on every render (``AppScaffold`` calls
    hooks, D-70).

    Args:
        title: The app bar's title, "Choose sponsor".
        prefix: The page's identifiers' start, ``lead.sponsor``.
        cancel: ``Picking.cancel``.
        margin: The list's side margin (``use_margin(LIST)``, D-305).
        head: What stays above the list: the search field, the category chips.
        items: The list's items, or its state.
    """
    return AppScaffold(
        title=title,
        actions=[
            # An icon, as M3's full-screen dialogs close: a text button's label grew
            # with the text and squeezed the title to "Choose sp…" at 200 %.
            named(
                f"{prefix}.cancel",
                ft.IconButton(ft.Icons.CLOSE, tooltip=CANCEL, on_click=cancel),
            )
        ],
        body=ft.Column(
            [
                # The head in a column of its own, so the list keeps its place as the
                # states come and go (D-153).
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


def spinner(label: str) -> ft.Control:
    """Return the loading state: a ring, read as ``label`` ("Loading sponsors")."""
    return ft.Container(
        ft.Semantics(
            label=label,
            container=True,
            exclude_semantics=True,
            content=ft.ProgressRing(),
        ),
        padding=48,
        alignment=ft.Alignment.TOP_CENTER,
    )


def not_loaded(
    title: str, prefix: str, retry: ft.ControlEventHandler[ft.Button]
) -> ft.Control:
    """Return the failed state: "Couldn't load sponsors" with Retry (D-120).

    Args:
        title: Its title.
        prefix: The page's identifiers' start; the state is ``<prefix>.failed``.
        retry: Fetches again.
    """
    return EmptyState(
        title,
        icon=ft.Icons.CLOUD_OFF_OUTLINED,
        body=NOT_LOADED_BODY,
        action=RETRY,
        on_action=retry,
        identifier=f"{prefix}.failed",
    )


def no_match(
    noun: str, query: str, prefix: str, clear: ft.ControlEventHandler[ft.Button]
) -> ft.Control:
    """Return the no-match state: "No sponsors match “acme”" with Clear search.

    Args:
        noun: What the list holds, plural: "sponsors".
        query: What was typed.
        prefix: The page's identifiers' start; the state is ``<prefix>.no_match``.
        clear: Clears the field, whose focus goes back to it.
    """
    return EmptyState(
        no_match_title(noun, query),
        icon=ft.Icons.SEARCH_OFF,
        action=CLEAR_SEARCH,
        on_action=clear,
        identifier=f"{prefix}.no_match",
    )


def no_match_title(noun: str, query: str) -> str:
    """Return the no-match state's title: "No sponsors match “acme”"."""
    return (
        f"No {noun} match \N{LEFT DOUBLE QUOTATION MARK}{query.strip()}"
        "\N{RIGHT DOUBLE QUOTATION MARK}"
    )


def choice_row(
    *,
    identifier: str,
    phrase: str,
    lines: list[ft.Control],
    selected: bool,
    on_click: Callable[[], Awaitable[None]],
    leading: ft.Control | None = None,
) -> ft.Control:
    """Return a picker's row: one node read as ``phrase``, ticked when chosen.

    Args:
        identifier: For UI flows, ``lead.sponsor.1``.
        phrase: What a screen reader says: "Example Corp, Booth 101, selected".
        lines: The row's texts, top to bottom.
        selected: It is the saved choice.
        on_click: Picks it.
        leading: A mark before the texts: the sponsor's logo.
    """
    return ft.MergeSemantics(  # the phrase and the tap's action: one node
        content=ft.Container(
            ft.Semantics(
                label=phrase,
                identifier=identifier,
                button=True,
                exclude_semantics=True,  # the phrase replaces the texts
                content=ft.Row(
                    [
                        *([leading] if leading is not None else []),
                        ft.Column(lines, spacing=2, expand=True),
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
            on_click=on_click,
            bgcolor=ft.Colors.SECONDARY_CONTAINER if selected else None,
            # 12 dp each side of a 24 dp line or tick: a one-line row is 48 dp (D-33).
            padding=ft.Padding.symmetric(horizontal=16, vertical=ROW_PADDING),
        )
    )


def context_chip(
    *,
    text: str,
    spoken: str,
    icon: ft.IconData | ft.Control,
    identifier: str,
    on_click: ft.ControlEventHandler,
) -> ft.Control:
    """Return the chip that heads a tool's scan screen and reopens its picker.

    One node, a button read as ``spoken``. Drawn as M3's outlined assist chip (8 dp
    corners, an ``outline_variant`` edge, a leading icon) but built from a
    ``Container``: Flutter's ``Chip`` keeps its label on one line, which at the
    largest text cut "Example Corp" to "Example". Its text takes only the room it
    needs (``expand_loose``) and wraps past the width; the chip is at least 48 dp tall,
    its own target (ux.md §9).

    Args:
        text: What it shows, "For: Example Corp".
        spoken: What a screen reader says, "Scanning for Example Corp, change sponsor".
        icon: Its leading icon, drawn in ``primary``; or a control in its place (the
            sync chip's own icon or ring at large text, #752).
        identifier: For UI flows, ``lead.sponsor_chip``.
        on_click: Opens the picker.
    """
    return ft.Container(
        ft.MergeSemantics(  # the phrase and the tap's action: one node
            content=ft.Container(
                ft.Semantics(
                    label=spoken,
                    identifier=identifier,
                    button=True,
                    exclude_semantics=True,  # the phrase replaces the text
                    content=ft.Row(
                        [
                            icon
                            if isinstance(icon, ft.Control)
                            else ft.Icon(
                                icon,
                                size=18,
                                color=ft.Colors.PRIMARY,
                                apply_text_scaling=True,
                            ),
                            ft.Text(
                                text,
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


def tool_button(
    identifier: str, label: str, icon: ft.IconData, on_click: ft.ControlEventHandler
) -> ft.Control:
    """Return one of a tool's tonal buttons under the field, start-aligned.

    Args:
        identifier: For UI flows, e.g. ``lead.add_note``.
        label: Its words.
        icon: Its leading icon.
        on_click: What it does.
    """
    return ft.Container(
        named(
            identifier,
            ft.FilledTonalButton(
                label,
                icon=icon,
                on_click=on_click,
                style=ft.ButtonStyle(padding=LABEL_PADDING),
                elevation=0,  # M3's tonal button lies flat (D-344)
            ),
        ),
        alignment=ft.Alignment.CENTER_LEFT,
        # Keyed: "Leads (42)" is built here and kept by ScanScreen's own re-renders,
        # so a result's "Add note" landing in its place would otherwise take its id,
        # two buttons with one (U163, #622); differing keys make it a new control.
        key=identifier,
    )


@ft.component
def Reading(*, title: str) -> ft.Control:
    """The empty page under a tool's title while it reads its keys from storage.

    A component of its own: ``AppScaffold`` calls hooks, which in a tool's loading
    branch only would change its hook order once the read ends (D-70).

    Args:
        title: The tool's name, the app bar's title.
    """
    margin = use_margin(LIST)  # its width class (D-305)
    return AppScaffold(
        title=title, body=ft.ListView(expand=True, padding=sides(margin))
    )
