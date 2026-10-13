"""Search's result list (``screens/search.py``): the results by type, sessions by day.

Its own module so that the screen stays under about 400 lines (D-66), as the Developer
screen's pickers are (D-187). ``ResultList`` is memoised, and so is each day of
sessions (``ui.day_groups.DayGroup``, keyed by its date), over the memoised session
and speaker rows (D-153): new results re-render only the days and rows they changed,
and a star tap one row.
"""

from collections.abc import Mapping

import flet as ft

from pycon_us.core.models import Room
from pycon_us.core.rooms import session_count
from pycon_us.core.row_views import SessionView
from pycon_us.core.search import SearchResults
from pycon_us.core.speakers import SpeakerEntry
from pycon_us.locations import drill_href
from pycon_us.theme import Tokens
from pycon_us.ui.badges import ToggleFavorite
from pycon_us.ui.day_groups import DayGroup
from pycon_us.ui.rows import LinkTile, SpeakerRow
from pycon_us.ui.scaffold import SectionHeader

SCREEN = "search"
"""The screen's name in its semantics identifiers (decisions §M)."""


def plural(count: int, noun: str) -> str:
    """Return "1 session", "12 sessions": a count and its noun."""
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def summary(results: SearchResults) -> str:
    """Return what a search found, in words: "12 sessions, 3 speakers, 1 room".

    Only the types that matched are named; the line is a polite live region, so a
    screen reader hears what typing did without leaving the field (ux.md §4.3).

    Args:
        results: A search's results, at least one match.
    """
    counts = (
        (results.session_count, "session"),
        (len(results.speakers), "speaker"),
        (len(results.rooms), "room"),
    )
    return ", ".join(plural(count, noun) for count, noun in counts if count)


@ft.memo
@ft.component
def ResultList(
    results: SearchResults,
    views: Mapping[str, SessionView],
    entries: Mapping[str, SpeakerEntry],
    saved: frozenset[str],
    on_toggle: ToggleFavorite,
    tokens: Tokens,
    state: ft.Control | None,
) -> ft.Control:
    """The list under the field: the results by type, or the screen's state.

    Memoised: while the typing has not paused, every prop is the same object and the
    body is skipped (F34). Its items are memoised too, so new results re-render only
    the days and rows that changed (D-153).

    A type gets its heading ("Speakers", level 2, the day headings under it level 3)
    only when the results hold more than one type: alone, it would only repeat the
    count line above the list ("7 sessions") and stack two headings over the first
    row, so the day headings take level 2 then. The count line already says each
    type's count, so the type headings leave it out. A type heading is a step up from
    a day's (``TITLE_MEDIUM`` in ``on_surface``, with a divider before every type but
    the first), so that on screen too it opens a kind of result, not one more day.

    Args:
        results: The last search's results.
        views: Every session's row view, by id, built once per feed version.
        entries: Every directory speaker's entry, by id, built once per feed version.
        saved: ``Favorites.ids``.
        on_toggle: The list's one star handler.
        tokens: The scheme's tokens (D-150).
        state: What shows instead of results (the hint, a miss, no data), or None.
    """
    view_path = ft.use_view_path()
    if state is not None:
        return ft.ListView([state], expand=True)
    titled = sum(map(bool, (results.sessions, results.speakers, results.rooms))) > 1
    day_level = 3 if titled else 2
    sections: list[tuple[str, list[ft.Control]]] = []
    if results.sessions:
        days = [
            DayGroup(
                group,
                views,
                saved & {s.id for s in group.sessions},
                on_toggle,
                tokens,
                screen=SCREEN,
                level=day_level,
                # Right under its type heading, the first day sits close to it.
                top=0 if titled and i == 0 else 16,
            )
            for i, group in enumerate(results.sessions)
        ]
        sections.append(("Sessions", days))
    if results.speakers:
        speakers = [SpeakerRow(entries[s.id], screen=SCREEN) for s in results.speakers]
        sections.append(("Speakers", speakers))
    if results.rooms:
        rooms = [room_row(room, view_path) for room in results.rooms]
        sections.append(("Rooms", rooms))
    items: list[ft.Control] = []
    for i, (name, rows) in enumerate(sections):
        if titled:
            if i:
                items.append(ft.Divider(height=1))
            items.append(type_heading(name))
        items.extend(rows)
    return ft.ListView(items, expand=True)


def type_heading(name: str) -> ft.Control:
    """Return the heading of one type of result ("Sessions"), a level-2 heading.

    Args:
        name: The type, as the scope chip says it.
    """
    return SectionHeader(
        name,
        level=2,
        theme_style=ft.TextThemeStyle.TITLE_MEDIUM,
        color=ft.Colors.ON_SURFACE,
    )


def room_row(room: Room, view_path: str) -> ft.Control:
    """Return a room result: its name and session count, pushing the room's detail.

    The Map's row without its "Now:" lines (D-188): search answers "where is it",
    and the room's detail says what is on.

    Args:
        room: The room.
        view_path: This View's path, so the detail is pushed on top of search.
    """
    return LinkTile(
        room.name,
        drill_href(view_path, "room", room.slug),
        icon=ft.Icons.PLACE_OUTLINED,
        subtitle=session_count(len(room.session_ids)),
        identifier=f"{SCREEN}.room.{room.slug}",
    )
