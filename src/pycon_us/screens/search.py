"""Search (``/search?scope=<scope>``): the one search, over every day (NEW-02, D-19).

A global modal route, opened from Now, Schedule, Map and More with a preset scope
(``search_button()``), which also records where Back from search returns. A pill field
pinned under the app bar takes the focus as the View opens; scope chips (All, Sessions,
Speakers, Rooms) sit under it. The field updates at every keystroke (D-157), and the
search itself runs once the typing pauses for 250 ms (D-46), or at once on the keyboard's
action key or a scope change, through ``core.search`` over an index built once per feed
version (D-180). Results come grouped by type, sessions by day, each row pushing its
detail on top of search (``/search/session/42``); Back returns to the results with the
query intact, since this View stays mounted below the detail and the query and scope are
also in ``ViewMemory`` (D-18, D-141).

The result list (``screens/search_results.py``) memoises its path as the Schedule's
does (D-153): a keystroke before the pause re-renders the field and nothing under the
list, and a star tap one row. Search covers all days and ignores the Schedule's filters
(D-20), and a miss says so.
"""

import asyncio

import flet as ft

from pycon_us.core.search import SCOPES, SearchResults, search, search_index
from pycon_us.core.speakers import directory
from pycon_us.favorites import use_favorites
from pycon_us.locations import use_query
from pycon_us.screens.search_results import SCREEN, ResultList, summary
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.state import use_conference
from pycon_us.theme import use_tokens
from pycon_us.ui.badges import use_favorite_toggle
from pycon_us.ui.fields import SearchField
from pycon_us.ui.scaffold import AppScaffold, StatusStrip
from pycon_us.ui.session_rows import use_session_views
from pycon_us.ui.states import NO_DATA_BODY, EmptyState, SkeletonList

DEBOUNCE_SECONDS = 0.25
"""How long the typing must pause before the search runs (D-46)."""

HINT = "Search sessions, speakers, rooms"
"""The field's hint, which also names it while it is empty (ux.md §4.3)."""

LABEL = "Search"
"""The field's name for screen readers once it holds text."""

CLEAR = "Clear search"
"""The Clear button's tooltip, its accessible name (D-27)."""

COVERS = "Search covers all days and ignores your filters."
"""What search looks at, said before typing and on a miss (ux.md §4.6, D-20)."""

SCOPE_LABELS = {
    "all": "All",
    "sessions": "Sessions",
    "speakers": "Speakers",
    "rooms": "Rooms",
}
"""Each scope's chip, in ``SCOPES``' order (D-19)."""

IDLE_TITLES = {
    "all": "Find sessions, speakers and rooms",
    "sessions": "Find sessions",
    "speakers": "Find speakers",
    "rooms": "Find rooms",
}
"""What the screen says before the first word, by scope."""


def scope_of(requested: str | None, remembered: str) -> str:
    """Return the scope a Search View starts with (D-180).

    Args:
        requested: The ``?scope=`` the opener passed, or None when the View mounted
            without one (a deep entry below a result).
        remembered: ``ViewMemory.search_scope``.

    Returns:
        ``requested`` when it is a scope, ``all`` for an unknown one, and the
        remembered scope when none was passed.
    """
    if requested is None:
        return remembered if remembered in SCOPES else "all"
    return requested if requested in SCOPES else "all"


@ft.component
def Search() -> ft.View:
    """The global search: the field, the scope chips and the grouped results."""
    svc = use_services()
    memory = svc.memory
    conference = use_conference()
    favorites = use_favorites()
    on_toggle = use_favorite_toggle(favorites)
    tokens = use_tokens()
    options = use_query()
    page = ft.context.page
    use_24h = bool(page.media and page.media.always_use_24_hour_format)
    scope, set_scope = ft.use_state(
        lambda: scope_of(options.get("scope"), memory.search_scope)
    )
    text, set_text = ft.use_state(memory.search_query)  # the field, every keystroke
    query, set_query = ft.use_state(memory.search_query)  # what was searched
    memory.search_scope = scope
    data = conference.data
    # Once per feed version: never per keystroke (D-180).
    index = ft.use_memo(
        lambda: search_index(data) if data else None, [conference.version]
    )
    entries = ft.use_memo(
        lambda: {e.speaker.id: e for e in directory(data)} if data else {},
        [conference.version],
    )
    all_views = use_session_views(
        conference, tuple(data.sessions) if data else (), use_24h=use_24h
    )
    views = ft.use_memo(lambda: {v.session.id: v for v in all_views}, [all_views])
    results = ft.use_memo(
        lambda: search(index, query, scope) if index else SearchResults(),
        [index, query, scope],
    )
    # A miss in one scope, when All would find something: the way out of the miss.
    elsewhere = ft.use_memo(
        lambda: bool(
            index
            and scope != "all"
            and results.empty
            and not search(index, query, "all").empty
        ),
        [index, query, scope],
    )

    @report_errors
    async def settle() -> None:
        # Restarted by every keystroke: Flet cancels the run in progress (F2).
        await asyncio.sleep(DEBOUNCE_SECONDS)
        set_query(text)

    ft.use_effect(settle, [text], cleanup=_stop_waiting)

    @report_errors
    def changed(e: ft.Event[ft.TextField]) -> None:
        memory.search_query = e.control.value
        set_text(e.control.value)

    @report_errors
    def submitted(e: ft.Event[ft.TextField]) -> None:
        set_query(e.control.value)  # the keyboard's action key: no need to wait

    # A fresh Ref each render, as in the Speakers filter: it holds this render's field.
    field_ref: ft.Ref[ft.TextField] = ft.Ref()

    @report_errors
    async def clear() -> None:
        memory.search_query = ""
        set_text("")
        set_query("")
        # The Clear button goes away once the field is empty: put the focus back in
        # the field, ready to type again, rather than lose a screen reader's place.
        if field_ref.current is not None:
            await field_ref.current.focus()

    @report_errors
    def picked(e: ft.Event[ft.Chip]) -> None:
        # A tap on the selected chip keeps its scope: one scope is always on.
        memory.search_scope = e.control.data
        set_scope(e.control.data)
        set_query(text)  # the typed words, in the new scope, at once

    @report_errors
    def show_all() -> None:
        memory.search_scope = "all"
        set_scope("all")

    @report_errors
    async def refresh() -> None:
        await conference.refresh(svc.storage, svc.year, closed=svc.closed)

    state: ft.Control | None = None
    if data is None and conference.problem is None:
        state = ft.Column([StatusStrip(), SkeletonList("Loading schedule")], spacing=0)
    elif data is None:
        state = ft.Column(
            [
                StatusStrip(),  # its bar shows a retry; the button stays in place
                EmptyState(
                    "Can't load the schedule",
                    icon=ft.Icons.CLOUD_OFF_OUTLINED,
                    body=NO_DATA_BODY[conference.problem or "offline"],
                    action="Try again",
                    on_action=refresh,
                    disabled=conference.refreshing,  # in place, so focus stays
                    identifier=f"{SCREEN}.no_data",
                ),
            ],
            spacing=0,
        )
    elif not query.split():
        state = EmptyState(
            IDLE_TITLES[scope],
            icon=ft.Icons.SEARCH,
            body=COVERS,
            identifier=f"{SCREEN}.idle",
        )
    elif results.empty:
        state = EmptyState(
            f"No results for \N{LEFT DOUBLE QUOTATION MARK}{query.strip()}"
            "\N{RIGHT DOUBLE QUOTATION MARK}",
            icon=ft.Icons.SEARCH_OFF,
            body=COVERS,
            # Where no button can help, the sentence is the way out (ux.md §4.6).
            action="Show all results" if elsewhere else None,
            on_action=show_all if elsewhere else None,
            identifier=f"{SCREEN}.no_match",
        )
    count = None if state is not None else _found_count(summary(results))
    return AppScaffold(
        title="Search",
        body=ft.Column(
            [
                # The field, the chips and the count stay put above the list, in a
                # column of their own: the count coming and going never moves the
                # list to another place in the body, where Flet would rebuild it.
                ft.Column(
                    [
                        SearchField(
                            value=text,
                            on_change=changed,
                            on_clear=clear,
                            ref=field_ref,
                            hint=HINT,
                            label=LABEL,
                            clear_tooltip=CLEAR,
                            identifier=f"{SCREEN}.field",
                            autofocus=True,
                            on_submit=submitted,
                            keyboard_type=ft.KeyboardType.WEB_SEARCH,
                        ),
                        _scope_chips(scope, picked),
                        *([count] if count else []),
                    ],
                    spacing=0,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                ),
                ResultList(
                    results, views, entries, favorites.ids, on_toggle, tokens, state
                ),
            ],
            spacing=0,
            expand=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        ),
    )


def _stop_waiting() -> None:
    """The debounce effect's cleanup: nothing to undo.

    Its presence is what makes Flet cancel a pending wait when the View unmounts (F2),
    and it is passed as ``cleanup=``, since a returned one would be lost at the next
    render (F39).
    """


def _scope_chips(scope: str, on_pick: ft.ControlEventHandler[ft.Chip]) -> ft.Control:
    """Return the scope chips, one per scope, the current one selected with its check.

    One row that scrolls sideways when it is wider than the screen (large text):
    wrapped, the chips took three rows at the largest text, and with the keyboard up
    the field and the chips no longer fitted above it. The row's ends are spacers, so
    the first chip starts at the 16 dp gutter and the last can scroll clear of the
    edge. Each chip is one node for screen readers, read as its label, "selected" when
    it is, and a button.

    Args:
        scope: The current scope.
        on_pick: Switches to the tapped chip's scope (its ``data``), keeping the query.
    """
    return ft.Container(
        ft.Row(
            [
                ft.Container(width=8),  # with the 8 dp spacing: the 16 dp gutter
                *(
                    ft.MergeSemantics(
                        ft.Semantics(
                            identifier=f"{SCREEN}.scope.{key}",
                            content=ft.Chip(
                                label=label,
                                selected=key == scope,
                                show_checkmark=True,  # not colour alone (D-33)
                                data=key,
                                on_select=on_pick,
                            ),
                        )
                    )
                    for key, label in SCOPE_LABELS.items()
                ),
                ft.Container(width=8),
            ],
            spacing=8,
            scroll=ft.ScrollMode.AUTO,
        ),
        padding=ft.Padding.symmetric(vertical=4),
    )


def _found_count(line: str) -> ft.Control:
    """Return the line that says what the search found, a polite live region.

    Args:
        line: ``summary()`` of the results.
    """
    return ft.Semantics(
        live_region=True,
        identifier=f"{SCREEN}.count",
        content=ft.Container(
            ft.Text(
                line,
                theme_style=ft.TextThemeStyle.BODY_SMALL,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            padding=ft.Padding.only(left=16, top=4, right=16),
        ),
    )
