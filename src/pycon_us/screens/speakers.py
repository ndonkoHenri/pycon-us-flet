"""Speakers (``/more/speakers``): the speaker directory, by letter, with a filter (SPKR-01).

Every directory speaker in D-46's order (by displayed name, folded), under a heading per
letter, each row with its first session and "+1 more" when there are more (DATA-21). A
filter field above the list narrows it as the user types, with search's matching: accents
and case ignored, every word anywhere in the name (SPKR-02, D-180). A row pushes the
speaker's detail (``…/speaker/<id>``, one drill level).

A long list stays cheap the way S2's day lists do (D-153, D-154): the entries are built
once per feed version, the list is a lazy ``ListView``, each letter is one memoised item
and each row a memoised component keyed by speaker id, so a keystroke re-renders only the
sections it changed and no row that stays. No paging and no loader: with data the whole
list shows at once; without any (NEW-03) the skeleton shows until the first fetch has
failed, then the no-data state (ux.md §4.1).
"""

from collections.abc import Callable
from typing import Any

import flet as ft

from pycon_us.core.search import search_index
from pycon_us.core.speakers import (
    LetterGroup,
    directory,
    filter_directory,
    letter_groups,
)
from pycon_us.screens.schedule import NO_DATA_BODY
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.state import use_conference
from pycon_us.ui.rows import SpeakerRow
from pycon_us.ui.scaffold import AppScaffold, SectionHeader
from pycon_us.ui.states import EmptyState, SkeletonList

SCREEN = "speakers"
"""The screen's name in its semantics identifiers (decisions §M)."""

FILTER_HINT = "Filter speakers"
"""The filter field's hint, which is also what a screen reader calls it."""

CLEAR_FILTER = "Clear filter"
"""The label of the two controls that empty the filter: the field's and the no-match state's."""


@ft.component
def Speakers() -> ft.View:
    """The Speakers page: a filter field over the directory, by letter."""
    svc = use_services()
    conference = use_conference()
    query, set_query = ft.use_state("")
    data = conference.data
    # Once per feed version: a keystroke re-renders this screen, never rebuilds these.
    entries = ft.use_memo(lambda: directory(data) if data else (), [conference.version])
    index = ft.use_memo(
        lambda: search_index(data) if data else None, [conference.version]
    )

    @report_errors
    def changed(e: ft.Event[ft.TextField]) -> None:
        set_query(e.control.value)

    @report_errors
    def clear() -> None:
        set_query("")

    @report_errors
    async def refresh() -> None:
        await conference.refresh(svc.storage, svc.year, closed=svc.closed)

    rows: list[ft.Control]
    if data is None and conference.problem is None:
        rows = [SkeletonList(label="Loading speakers")]  # the first fetch runs (NEW-03)
    elif data is None or index is None:
        rows = [
            EmptyState(
                "Can't load the speakers",
                icon=ft.Icons.CLOUD_OFF_OUTLINED,
                body=NO_DATA_BODY[conference.problem or "offline"],
                action="Try again",
                on_action=refresh,
                disabled=conference.refreshing,  # in place, so focus stays (D-182)
                identifier=f"{SCREEN}.no_data",
            )
        ]
    else:
        groups = letter_groups(filter_directory(entries, index, query))
        rows = [LetterSection(group) for group in groups] or [
            EmptyState(
                f"No speakers match \N{LEFT DOUBLE QUOTATION MARK}{query.strip()}"
                "\N{RIGHT DOUBLE QUOTATION MARK}",
                icon=ft.Icons.PERSON_SEARCH_OUTLINED,
                action=CLEAR_FILTER,
                on_action=clear,
                identifier=f"{SCREEN}.no_match",
            )
        ]
    return AppScaffold(
        title="Speakers",
        body=ft.Column(
            [
                _filter_field(query, changed, clear),
                ft.ListView(rows, expand=True),
            ],
            spacing=0,
            expand=True,
            # The field takes the screen's width; a Column would size it to its own.
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        ),
    )


def _filter_field(
    query: str,
    on_change: ft.ControlEventHandler[ft.TextField],
    on_clear: Callable[[], Any],
) -> ft.Control:
    """Return the filter field, pinned above the list so it is always in reach.

    Controlled (D-157): its value is the screen's state, which its ``on_change`` sets,
    so a re-render never wipes what the user typed (F33). A pill on
    ``surface_container_high``, like Material's search bar (ux.md §3.6), with a Clear
    button once there is text. Autocorrect is off: it would "fix" names.
    """
    clear_button = None
    if query:
        clear_button = ft.IconButton(
            ft.Icons.CLOSE, tooltip=CLEAR_FILTER, on_click=on_clear
        )
    return ft.Container(
        ft.Semantics(
            identifier=f"{SCREEN}.filter",
            content=ft.TextField(
                value=query,
                on_change=on_change,
                hint_text=FILTER_HINT,
                hint_max_lines=2,  # wraps at the largest text instead of clipping
                prefix_icon=ft.Icons.SEARCH,
                suffix_icon=clear_button,
                filled=True,
                fill_color=ft.Colors.SURFACE_CONTAINER_HIGH,
                border=ft.OutlineInputBorder(
                    border_radius=28,  # full radius, as search fields have
                    side=ft.BorderSide(0, ft.Colors.TRANSPARENT),
                ),
                autocorrect=False,
            ),
        ),
        padding=ft.Padding.only(left=16, top=8, right=16, bottom=4),
    )


def LetterSection(group: LetterGroup) -> ft.Control:
    """Return one letter of the list: its heading and its speakers, one list item.

    A memoised component keyed by the letter, as S2's slots are (D-153): a keystroke
    that leaves a letter's speakers as they were skips the whole section, and one
    that changes them re-renders the section but none of the rows that stay.

    Args:
        group: The letter and its entries; equal on every render while unchanged.
    """
    # As SessionRow's: ft.component's typing leaves out the key= its wrapper takes.
    return _LetterSection(group, key=group.letter)  # pyright: ignore[reportCallIssue]


@ft.memo
@ft.component
def _LetterSection(group: LetterGroup) -> ft.Control:
    """The body of ``LetterSection``; it runs only when its group changes (F34)."""
    return ft.Column(
        [
            # A node of its own: else the heading's flag and letter join the list
            # item's node, and a screen reader's focus outlines the whole section.
            ft.Semantics(container=True, content=SectionHeader(group.letter)),
            *(SpeakerRow(entry, screen=SCREEN) for entry in group.entries),
        ],
        spacing=0,
    )
