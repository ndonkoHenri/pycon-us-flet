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

import flet as ft

from pycon_us.core.search import search_index
from pycon_us.core.speakers import (
    LetterGroup,
    directory,
    filter_directory,
    letter_groups,
)
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.state import use_conference
from pycon_us.theme import use_tokens
from pycon_us.ui.fields import SearchField, found_count, use_field_query
from pycon_us.ui.rows import SpeakerRow
from pycon_us.ui.scaffold import AppScaffold, SectionHeader
from pycon_us.ui.states import NO_DATA_BODY, EmptyState, SkeletonList
from pycon_us.ui.widths import LIST, capped, sides, use_margin

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
    margin = use_margin(LIST)  # its width class (D-305)
    conference = use_conference()
    field = use_field_query()
    tokens = use_tokens()
    query = field.value
    data = conference.data
    # Once per feed version: a keystroke re-renders this screen, never rebuilds these.
    entries = ft.use_memo(lambda: directory(data) if data else (), [conference.version])
    index = ft.use_memo(
        lambda: search_index(data) if data else None, [conference.version]
    )

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
                on_action=field.clear,  # the focus goes back to the field (D-182)
                identifier=f"{SCREEN}.no_match",
            )
        ]
        if found and found is not entries:  # a filter applies and finds someone
            count = found_count(
                f"{len(found)} speaker" + ("" if len(found) == 1 else "s"),
                identifier=f"{SCREEN}.count",
            )
    return AppScaffold(
        title="Speakers",
        body=ft.Column(
            [
                # The count goes after the field, in a column of their own: put
                # between the field and the list, it would move the list to another
                # place in the body, and Flet would rebuild it and every row (D-153).
                capped(
                    ft.Column(
                        [
                            SearchField(
                                value=field.value,
                                on_change=field.changed,
                                on_clear=field.clear,
                                ref=field.ref,
                                focusable=field.focusable,
                                hint=FILTER_HINT,
                                label=FILTER_HINT,
                                clear_tooltip=CLEAR_FILTER,
                                identifier=f"{SCREEN}.filter",
                                high_contrast=tokens.high_contrast,
                            ),
                            *([count] if count else []),
                        ],
                        spacing=0,
                        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    ),
                    margin,
                ),
                ft.ListView(rows, expand=True, padding=sides(margin)),
            ],
            spacing=0,
            expand=True,
            # The field takes the screen's width; a Column would size it to its own.
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
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
