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
failed, then the no-data state (ux.md §4.1). A feed with no speakers yet says so.

For screen readers the field keeps its name while it holds text, a live region says how
many speakers a filter found, and clearing the filter puts the focus back in the field,
since both Clear controls go away when used (ux.md §5.7).
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
"""The filter field's hint, and its name for screen readers, which stays with text in it."""

NOT_ANNOUNCED = "No speakers announced yet"
"""The title of the state of a feed that lists no speakers, before the programme is out."""

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

    # A fresh Ref each render, as Flet's declarative examples do: it holds this
    # render's field, the one this render's handlers act on.
    field_ref: ft.Ref[ft.TextField] = ft.Ref()

    @report_errors
    async def clear() -> None:
        set_query("")
        # Both Clear controls go away once the filter is empty: put the focus in the
        # field, ready to type again, rather than lose a screen reader's place (D-182).
        if field_ref.current is not None:
            await field_ref.current.focus()

    @report_errors
    async def refresh() -> None:
        await conference.refresh(svc.storage, svc.year, closed=svc.closed)

    rows: list[ft.Control]
    count: ft.Control | None = None
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
    elif not entries:
        rows = [
            EmptyState(
                NOT_ANNOUNCED,
                icon=ft.Icons.PERSON_OFF_OUTLINED,
                # No button: the app refreshes the feed on its own (D-175).
                body="They show here as soon as the programme is out.",
                identifier=f"{SCREEN}.not_announced",
            )
        ]
    else:
        found = filter_directory(entries, index, query)
        rows = [LetterSection(group) for group in letter_groups(found)] or [
            EmptyState(
                f"No speakers match \N{LEFT DOUBLE QUOTATION MARK}{query.strip()}"
                "\N{RIGHT DOUBLE QUOTATION MARK}",
                icon=ft.Icons.PERSON_SEARCH_OUTLINED,
                action=CLEAR_FILTER,
                on_action=clear,
                identifier=f"{SCREEN}.no_match",
            )
        ]
        if found and found is not entries:  # a filter applies and finds someone
            count = _found_count(len(found))
    return AppScaffold(
        title="Speakers",
        body=ft.Column(
            [
                # The count goes after the field, in a column of their own: put
                # between the field and the list, it would move the list to another
                # place in the body, and Flet would rebuild it and every row (D-153).
                ft.Column(
                    [
                        _filter_field(query, changed, clear, field_ref),
                        *([count] if count else []),
                    ],
                    spacing=0,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                ),
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
    ref: ft.Ref[ft.TextField],
) -> ft.Control:
    """Return the filter field, pinned above the list so it is always in reach.

    Controlled (D-157): its value is the screen's state, which its ``on_change`` sets,
    so a re-render never wipes what the user typed (F33). A pill on
    ``surface_container_high`` without a line, focused or not, like Material's search
    bar (ux.md §3.6), with a Clear button once there is text. Autocorrect and Android's
    suggestions are off: they would "fix" names.

    The hint names the field only while it is empty, so the field's semantics node
    is merged with a label once there is text. A merge takes in every descendant, so
    the Clear button lies over the field, in a ``Stack``, rather than inside it as
    its suffix, where it would stop being a button of its own.

    Args:
        query: The filter as typed.
        on_change: Sets the screen's state from the field.
        on_clear: Empties the filter and puts the focus back in the field.
        ref: Set to the field, for ``on_clear``'s focus.
    """
    pill = ft.OutlineInputBorder(
        border_radius=28,  # full radius, as search fields have
        side=ft.BorderSide(0, ft.Colors.TRANSPARENT),
    )
    text_field = ft.MergeSemantics(
        ft.Semantics(
            identifier=f"{SCREEN}.filter",
            # Not while empty: the hint names the field then, and both would read it
            # twice.
            label=FILTER_HINT if query else None,
            content=ft.TextField(
                ref=ref,
                value=query,
                on_change=on_change,
                hint_text=FILTER_HINT,
                hint_max_lines=2,  # wraps at the largest text instead of clipping
                prefix_icon=ft.Icons.SEARCH,
                # Room for the Clear button above it, so text never runs under it.
                suffix_icon=ft.Container(width=48, height=48) if query else None,
                filled=True,
                fill_color=ft.Colors.SURFACE_CONTAINER_HIGH,
                # The focused entry too: else the theme draws a 2 dp primary ring.
                border={ft.ControlState.DEFAULT: pill, ft.ControlState.FOCUSED: pill},
                autocorrect=False,
                enable_suggestions=False,
            ),
        )
    )
    clear_button = ft.IconButton(
        ft.Icons.CLOSE, tooltip=CLEAR_FILTER, on_click=on_clear, right=4
    )
    return ft.Container(
        ft.Stack(
            [text_field, *([clear_button] if query else [])],
            alignment=ft.Alignment.CENTER_RIGHT,  # the button, level with the text
            fit=ft.StackFit.PASS_THROUGH,  # the field keeps the screen's width
        ),
        padding=ft.Padding.only(left=16, top=8, right=16, bottom=4),
    )


def _found_count(found: int) -> ft.Control:
    """Return the line that says how many speakers a filter found, a live region.

    A filter changes the list at every keystroke: the live region lets a screen reader
    hear what typing did without leaving the field (ux.md §9). Shown only while a
    filter finds someone; a miss has the no-match state, which announces itself.

    Args:
        found: How many speakers the filter found, at least one.
    """
    return ft.Semantics(
        live_region=True,
        identifier=f"{SCREEN}.count",
        content=ft.Container(
            ft.Text(
                f"{found} speaker" + ("" if found == 1 else "s"),
                theme_style=ft.TextThemeStyle.BODY_SMALL,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            padding=ft.Padding.only(left=16, top=4, right=16),
        ),
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
