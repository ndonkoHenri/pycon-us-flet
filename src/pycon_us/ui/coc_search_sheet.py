"""The CoC name search's look: the sheet, its rows and Find by name (#761; MASK-02).

ux.md §7.3, D-439. A full-height modal `BottomSheet` over the scan screen, as the
queue sheet:

- a level-1 heading "Find attendee" with Close (`coc.search.close`);
- "Search by name" (`coc.search`), focused as it opens, pinned above the rows;
- before typing, "Type a name to search the attendee list."; no match, "No
  attendees match “x”" with Clear search; otherwise a live line ("3 attendees", or
  "Showing 25. Refine your search." past the cap, `coc.search.more`) and the rows,
  one stop each (`coc.search.row.<index>`, never the access code): the name,
  "Badge: Maggie" when it differs, and the count in words with its level's icon,
  read as "Margaret Test, badge Maggie, 3 incidents on record".

`find_button()` is "Find by name" (`coc.find`), an `OutlinedButton` under the
badge field, disabled with its reason. Built from data only: `ui/coc_search.py`'s
`use_find()` keeps the search and the handlers.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import flet as ft

from pycon_us.core.conduct import (
    LIMIT,
    Attendee,
    Matches,
    count_words,
    display_name,
)
from pycon_us.services.errors import report_errors
from pycon_us.theme import Tokens
from pycon_us.theme_hc import hc_sheet_shape
from pycon_us.ui.coc_review_dialog import count_row
from pycon_us.ui.fields import SearchField, found_count
from pycon_us.ui.queue_rows import note, title_row
from pycon_us.ui.semantics import named
from pycon_us.ui.staff_picker import CLEAR_SEARCH, ROW_PADDING, no_match

FIND = "Find by name"
TITLE = "Find attendee"
SEARCH_LABEL = "Search by name"
BEFORE = "Type a name to search the attendee list."
MORE = f"Showing {LIMIT}. Refine your search."
PREFIX = "coc.search"
"""The sheet's identifiers' start (decisions §M)."""


@dataclass(frozen=True)
class Finding:
    """The open search: what was typed, and what the rows were found for.

    Attributes:
        typed: The field's text as Flutter last reported it.
        query: `typed` once typing paused: what the rows match.
        clears: Counts Clear search, so each one sends the empty text once.
        opening: This opening's token: a dismissal carries it, so a late one for an
            earlier sheet closes nothing.
    """

    typed: str = ""
    query: str = ""
    clears: int = 0
    opening: object = field(default_factory=object, compare=False)


@dataclass(frozen=True)
class SheetActions:
    """What the sheet's controls call.

    Attributes:
        changed: The field's text changed.
        clear: Clear search, and the field's Clear button.
        pick: A row's tap, with its attendee.
        close: Close.
        dismissed: A dismissal (a swipe, Back), with the token of the opening it closed.
    """

    changed: Callable[[ft.Event[ft.TextField]], object]
    clear: Callable[..., Awaitable[None]]
    pick: Callable[[Attendee], Awaitable[None]]
    close: Callable[[], object]
    dismissed: Callable[[object], object]


def phrase(attendee: Attendee) -> str:
    """Return a row's one phrase: "Margaret Test, badge Maggie, 3 incidents on record".

    Args:
        attendee: The row's attendee.
    """
    parts = [display_name(attendee)]
    badge = badge_of(attendee)
    if badge:
        parts.append(f"badge {badge}")
    parts.append(count_words_lower(attendee.incidents))
    return ", ".join(parts)


def badge_of(attendee: Attendee) -> str:
    """Return the badge's name when it differs from the name shown, else `""`."""
    name = display_name(attendee)
    return attendee.badge_name if attendee.badge_name != name else ""


def count_words_lower(incidents: int) -> str:
    """Return the count in words for the middle of a phrase: "no incidents on record"."""
    words = count_words(incidents)
    return words[0].lower() + words[1:]


def attendee_row(
    index: int,
    attendee: Attendee,
    on_pick: Callable[[Attendee], Awaitable[None]],
    tokens: Tokens,
) -> ft.Control:
    """Return one result: the name, "Badge: Maggie", the count with its level's icon.

    One node, a button read as `phrase()`; at least 48 dp tall (D-33). Its
    identifier is its place in the list, never the access code (D-72); its key is
    the attendee object's, so a tap from a row new results replaced is dropped.

    Args:
        index: Its place in the rows, from 0.
        attendee: The attendee.
        on_pick: Opens the review for it.
        tokens: The scheme's tokens, for the level's colour.
    """
    lines: list[ft.Control] = [
        ft.Text(display_name(attendee), theme_style=ft.TextThemeStyle.BODY_LARGE)
    ]
    badge = badge_of(attendee)
    if badge:
        lines.append(
            ft.Text(
                f"Badge: {badge}",
                theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                color=ft.Colors.ON_SURFACE_VARIANT,
            )
        )
    lines.append(count_row(attendee.incidents, tokens))

    @report_errors
    async def pick() -> None:
        await on_pick(attendee)

    return ft.MergeSemantics(  # the phrase and the tap's action: one node
        content=ft.Container(
            ft.Semantics(
                label=phrase(attendee),
                identifier=f"{PREFIX}.row.{index}",
                button=True,
                exclude_semantics=True,  # the phrase replaces the texts
                content=ft.Column(lines, spacing=2),
            ),
            ink=True,
            on_click=pick,
            padding=ft.Padding.symmetric(horizontal=16, vertical=ROW_PADDING),
        ),
        # The attendee's, not the place's: new results never take over a row, so a
        # tap sent from the row they replaced reaches no one (opaque, D-72).
        key=str(id(attendee)),
    )


def results(
    finding: Finding,
    matches: Matches,
    actions: SheetActions,
    tokens: Tokens,
) -> list[ft.Control]:
    """Return what is under the field: the hint, the no-match state, or the rows.

    Args:
        finding: The search: its query once typing paused.
        matches: What `search()` found for it.
        actions: The handlers: Clear search and a row's tap.
        tokens: The scheme's tokens.
    """
    if not finding.query.strip():
        return [ft.Container(note(BEFORE, identifier=f"{PREFIX}.hint"), padding=16)]
    if not matches.rows:
        return [no_match("attendees", finding.query, PREFIX, actions.clear)]
    count = len(matches.rows)
    line = MORE if matches.more else f"{count} attendee" + ("" if count == 1 else "s")
    found = f"{PREFIX}.more" if matches.more else f"{PREFIX}.count"
    return [
        found_count(line, identifier=found),
        *(
            attendee_row(i, attendee, actions.pick, tokens)
            for i, attendee in enumerate(matches.rows)
        ),
    ]


def find_sheet(
    finding: Finding,
    matches: Matches,
    entry: tuple[ft.Ref[ft.TextField], str],
    actions: SheetActions,
    *,
    tokens: Tokens,
    reduce_motion: bool = False,
) -> ft.BottomSheet:
    """Return the full-height search sheet (ux.md §7.3): the field pinned, rows under.

    Args:
        finding: The search.
        matches: What it found.
        entry: The field's `Ref`, made for each opening and Clear, and its text as
            Flutter last reported it (D-243): never sent back over typing.
        actions: The handlers.
        tokens: The scheme's tokens; in high contrast a 1 dp edge draws the sheet.
        reduce_motion: The sheet appears without its slide (D-34, D-173).
    """
    ref, text = entry
    head = ft.Container(
        title_row(actions.close, title=TITLE, identifier=f"{PREFIX}.close"),
        padding=ft.Padding.only(left=16, right=16),
    )
    search_field = SearchField(
        value=text,
        on_change=actions.changed,
        on_clear=actions.clear,
        ref=ref,
        hint=SEARCH_LABEL,
        label=SEARCH_LABEL,
        clear_tooltip=CLEAR_SEARCH,
        identifier=PREFIX,
        autofocus=True,  # typing starts as it opens
        high_contrast=tokens.high_contrast,
    )
    return ft.BottomSheet(
        ft.Container(  # clear of the home bar; the parts keep their 16 dp gutters
            padding=ft.Padding.only(bottom=16),
            content=ft.Column(
                [
                    head,
                    search_field,
                    ft.ListView(
                        results(finding, matches, actions, tokens),
                        expand=True,  # the sheet takes the screen's height
                    ),
                ],
                spacing=0,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
        ),
        show_drag_handle=True,
        scrollable=True,  # up to the screen's height: room for the rows at 200 %
        use_safe_area=True,
        shape=hc_sheet_shape(tokens.high_contrast),
        on_dismiss=lambda _: actions.dismissed(finding.opening),
        # Its slide is motion: none under reduced motion (D-34, D-173).
        animation_style=ft.AnimationStyle.no_animation() if reduce_motion else None,
    )


def find_button(reason: str | None, on_click: Callable[[], object]) -> ft.Control:
    """Return "Find by name", in the buttons under the badge field; disabled while `reason` holds.

    A disabled button's tooltip is not read, so its name says why (#759's words:
    "Loading attendee list…", "CoC capture needs a connection").

    Args:
        reason: Why the search can't open now, or None.
        on_click: Opens the search.
    """
    button: ft.Control = ft.OutlinedButton(
        FIND,
        icon=ft.Icons.PERSON_SEARCH,
        on_click=on_click,
        disabled=reason is not None,
    )
    if reason is not None:
        button = ft.Semantics(
            label=f"{FIND}. {reason}",
            button=True,
            disabled=True,
            exclude_semantics=True,
            content=button,
        )
    return ft.Container(
        named("coc.find", button),
        key="coc.find",  # kept apart from a result's buttons in ScanScreen's row
    )
