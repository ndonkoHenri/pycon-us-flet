"""The expo List: every exhibitor by booth or by name, filtered, a tap to the Map (#404).

``ExpoPane`` (``screens/expo_pane.py``) shows it under its Map | List switch. It keeps
its filter, its order and its scroll in ``ViewMemory``, so a trip to the Map and back
finds it as it was (D-18).

The List has one row per exhibitor (D-254, ``core.expo.list_rows()``): by booth number
in natural order, a shared booth's exhibitors together by name, or by name with the
"Sort by name" chip; a booth without an exhibitor is a row by its label. Each row is
one node, "Booth 726, PyBeach, Community sponsor", and a tap switches to the Map with
its booth selected and its card shown. The sponsors whose booth has no rectangle on the
plan follow under "Not on the map yet", as the Sponsors page's rows, each pushing its
sponsor. The filter is pinned above the list with its count (D-226) and matches names
and booth numbers, folded (D-46). Rows are memoised components of values (D-153, F150).
"""

from collections.abc import Callable

import flet as ft

from pycon_us.core.expo import (
    ExpoRow,
    by_name,
    expo_booths,
    filter_rows,
    filter_sponsors,
    list_rows,
)
from pycon_us.screens.booth_card import place_tile
from pycon_us.screens.expo import placed_booths
from pycon_us.screens.sponsors import TILE_PLATE, SponsorRow
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.services.pref_keys import THEME
from pycon_us.state import use_conference
from pycon_us.theme import use_tokens
from pycon_us.ui.fields import SearchField, found_count, use_field_query
from pycon_us.ui.logos import logo_tile
from pycon_us.ui.scaffold import SectionHeader
from pycon_us.ui.scrolling import SCROLL_EVENT_MS
from pycon_us.ui.semantics import named
from pycon_us.ui.states import EmptyState
from pycon_us.ui.widths import LIST, capped, sides, use_margin

SCREEN = "expo"
"""The screen's name in the identifiers: ``expo.filter``, ``expo.row.613.bloomberg``."""

FILTER_HINT = "Filter by name or booth"
"""The filter field's hint, and its name for screen readers once it holds text."""

CLEAR_FILTER = "Clear filter"
"""The label of the two controls that empty the filter."""

SORT_BY_NAME = "Sort by name"
"""The chip that orders the List by name instead of by booth."""

UNPLACED = "Not on the map yet"
"""The heading over the sponsors whose booth the plan does not draw."""

type OnPick = Callable[[str], None]
"""Shows the booth of a number on the Map: ``ExpoPane``'s one handler for every row."""


def row_line(row: ExpoRow) -> str:
    """Return the line under a row's name: "Booth 726 · Community", or "Booth 407".

    Before the feed a row is named by its number alone, so it has no line.

    Args:
        row: One row of the List.
    """
    if row.sponsor is not None:
        return f"Booth {row.number} \N{MIDDLE DOT} {row.sponsor.level}"
    return f"Booth {row.number}" if row.name else ""


def row_phrase(row: ExpoRow) -> str:
    """Return what a screen reader says of a row (D-254, ux.md §6.2).

    Args:
        row: One row of the List.

    Returns:
        "Booth 726, PyBeach, Community sponsor"; "Booth 407, Python Software
        Foundation" for a booth without an exhibitor; "Booth 613" before the feed.
    """
    parts = [f"Booth {row.number}", row.name]
    if row.sponsor is not None:
        parts.append(f"{row.sponsor.level} sponsor")
    return ", ".join(part for part in parts if part)


def found_line(found: int) -> str:
    """Return the filter's count line: "1 match", "4 matches"."""
    return f"{found} match" + ("" if found == 1 else "es")


@ft.component
def ExpoList(on_pick: OnPick) -> ft.Control:
    """The List: the filter pinned over the rows, by booth or by name (ux.md §6.2).

    Args:
        on_pick: ``ExpoPane``'s handler that shows a booth on the Map.
    """
    svc = use_services()
    conference = use_conference()
    tokens = use_tokens()
    margin = use_margin(LIST)
    memory = svc.memory
    field = use_field_query(memory.expo_query)
    named_order, set_named_order = ft.use_state(memory.expo_by_name)
    list_ref = ft.use_memo(ft.Ref[ft.ListView], [])  # one for the List's life
    data = conference.data
    booths = svc.year.map.booths
    # Once per feed version: a keystroke filters, never rebuilds or sorts.
    by_booth = ft.use_memo(lambda: list_rows(placed_booths(data, booths)), [data])
    by_names = ft.use_memo(lambda: by_name(by_booth), [by_booth])
    unplaced = expo_booths(data, booths).unplaced if data is not None else ()

    @report_errors
    def changed(e: ft.Event[ft.TextField]) -> None:
        if field.changed(e):  # not a report a Clear's landing drops (D-243)
            memory.expo_query = e.control.value  # for the List's next showing

    @report_errors
    async def clear() -> None:
        memory.expo_query = ""
        await field.clear()  # the Clear button went: the focus goes back to the field

    @report_errors
    def sort() -> None:
        memory.expo_by_name = not named_order
        set_named_order(memory.expo_by_name)

    @report_errors
    def scrolled(e: ft.OnScrollEvent) -> None:
        if e.event_type == ft.ScrollType.END:
            memory.expo_offset = e.pixels

    @report_errors
    async def put_back() -> None:
        if not memory.expo_offset:
            return
        # A round trip: Flutter has built the list before it scrolls (D-156).
        await svc.storage.get(THEME)
        if list_ref.current is not None:
            await list_ref.current.scroll_to(offset=memory.expo_offset, duration=0)

    # The List that shows again is a new list at its top: put it where it was (D-18).
    ft.use_effect(put_back, [])

    ordered = by_names if named_order else by_booth
    rows = filter_rows(ordered, field.value)
    off_plan = filter_sponsors(unplaced, field.value)
    found = len(rows) + len(off_plan)
    pinned: list[ft.Control] = [
        SearchField(
            value=field.value,
            on_change=changed,
            on_clear=clear,
            ref=field.ref,
            focusable=field.focusable,
            hint=FILTER_HINT,
            label=FILTER_HINT,
            clear_tooltip=CLEAR_FILTER,
            identifier=f"{SCREEN}.filter",
            high_contrast=tokens.high_contrast,
        )
    ]
    if found and (rows is not ordered or off_plan is not unplaced):  # it narrows
        pinned.append(found_count(found_line(found), identifier=f"{SCREEN}.count"))
    # The chip scrolls with the rows: pinned, it took a row more from the list at
    # the largest text, under the app bar, the Map's tabs, the switch and the field.
    items: list[ft.Control] = [sort_chip(named_order, sort)]
    items.extend(list_row(row, on_pick) for row in rows)
    if off_plan:
        items.append(ft.Semantics(container=True, content=SectionHeader(UNPLACED)))
        items.extend(SponsorRow(sponsor, screen=SCREEN) for sponsor in off_plan)
    if not found:
        items.append(
            EmptyState(
                f"Nothing matches \N{LEFT DOUBLE QUOTATION MARK}{field.value.strip()}"
                "\N{RIGHT DOUBLE QUOTATION MARK}",
                icon=ft.Icons.SEARCH_OFF,
                action=CLEAR_FILTER,
                on_action=clear,  # the focus goes back to the field
                identifier=f"{SCREEN}.no_match",
            )
        )
    return ft.Column(
        [
            # Their own column, so the list keeps its place as the count comes and goes.
            capped(
                ft.Column(
                    pinned,
                    spacing=0,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                ),
                margin,
            ),
            ft.ListView(
                items,
                key=f"{SCREEN}.list",  # its own, so Flutter never reuses another (F130)
                ref=list_ref,
                expand=True,
                padding=sides(margin, bottom=24),
                scroll_interval=SCROLL_EVENT_MS,
                on_scroll=scrolled,
            ),
        ],
        spacing=0,
        expand=True,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )


def sort_chip(selected: bool, on_click: Callable[[], None]) -> ft.Control:
    """Return the "Sort by name" chip, checked while the List is in name order.

    Read as its label, "selected" when it is, and a button (``expo.sort``).

    Args:
        selected: Whether the List is sorted by name.
        on_click: Turns the name order on or off.
    """
    return ft.Container(
        ft.Row(
            [
                named(
                    f"{SCREEN}.sort",
                    ft.Chip(
                        label=SORT_BY_NAME,
                        selected=selected,
                        show_checkmark=True,  # not colour alone (D-33)
                        # A click, not on_select: Flutter would toggle the chip
                        # itself, and ``selected`` is only ours (search's chips).
                        on_click=on_click,
                    ),
                )
            ],
        ),
        padding=ft.Padding.only(left=16, top=4, right=16, bottom=4),
    )


def list_row(row: ExpoRow, on_pick: OnPick) -> ft.Control:
    """Return one row of the List: a memoised component keyed by ``row.key`` (D-153).

    Args:
        row: The exhibitor at its booth, or the booth without one.
        on_pick: ``ExpoPane``'s handler, the same function on every render.
    """
    # ft.component's typing (its ParamSpec) leaves out the key= its wrapper takes.
    return _ListRow(row, on_pick, key=row.key)  # pyright: ignore[reportCallIssue]


@ft.memo
@ft.component
def _ListRow(row: ExpoRow, on_pick: OnPick) -> ft.Control:
    """The body of ``list_row()``: logo or place, name and booth; a tap shows it.

    One node, a button read as ``row_phrase()``, built as a Sponsors row is so it
    grows with the text; it runs only when its props change (F34).
    """
    number = row.number

    @report_errors
    def pick() -> None:
        on_pick(number)

    sponsor = row.sponsor
    lead = (
        logo_tile(sponsor.name, sponsor.logo_url, size=TILE_PLATE)
        if sponsor is not None
        else place_tile(TILE_PLATE)
    )
    texts: list[ft.Control] = [
        ft.Text(
            row.name or f"Booth {number}", theme_style=ft.TextThemeStyle.TITLE_MEDIUM
        )
    ]
    if line := row_line(row):
        texts.append(
            ft.Text(
                line,
                theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                color=ft.Colors.ON_SURFACE_VARIANT,
            )
        )
    return ft.MergeSemantics(  # the phrase and the tap's action: one node
        content=ft.Container(
            ft.Semantics(
                label=row_phrase(row),
                identifier=f"{SCREEN}.row.{row.key}",
                button=True,
                exclude_semantics=True,  # the phrase replaces the texts
                content=ft.Row(
                    [
                        lead,
                        ft.Column(texts, spacing=2, expand=True),
                        # Where the tap goes: the booth on the plan.
                        ft.Icon(
                            ft.Icons.MAP_OUTLINED, color=ft.Colors.ON_SURFACE_VARIANT
                        ),
                    ],
                    spacing=16,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ),
            ink=True,
            on_click=pick,
            padding=ft.Padding.symmetric(horizontal=16, vertical=8),
        )
    )
