"""Search's result list (`screens/search.py`): the results by type, sessions by day.

Its own module so that the screen stays under about 400 lines (D-66), as the Developer
screen's pickers are (D-187). `ResultList` is memoised, and so is each day of
sessions (`ui.day_groups.DayGroup`, keyed by its date), over the memoised session
and speaker rows (D-153): new results re-render only the days and rows they changed,
and a star tap one row.

A broad query finds most of the feed, so each type shows its first rows
(`FIRST_SESSIONS`, `FIRST_SPEAKERS`, every place, `FIRST_SPONSORS`) and a "Show all 326 sessions" row
renders the rest of its type on request (D-218): the first render of a one-letter
query stays near that of a query that finds a few dozen rows, and every result stays
one tap away.
"""

from collections.abc import Mapping

import flet as ft

from pycon_us.core.expo import BoothEntry
from pycon_us.core.models import Room
from pycon_us.core.rooms import count_line
from pycon_us.core.row_views import SessionView
from pycon_us.core.search import SearchResults, first_results
from pycon_us.core.speakers import SpeakerEntry
from pycon_us.locations import booth_href, drill_href
from pycon_us.screens.expo_list import UNPLACED
from pycon_us.screens.sponsors import SponsorRow
from pycon_us.services.errors import report_errors
from pycon_us.theme import Tokens
from pycon_us.ui.day_groups import DayGroup
from pycon_us.ui.favorite import ToggleFavorite
from pycon_us.ui.link_tile import LinkTile
from pycon_us.ui.rows import SpeakerRow
from pycon_us.ui.scaffold import SectionHeader
from pycon_us.ui.session_rows import Changes, changes_of
from pycon_us.ui.widths import LIST, sides, use_margin
from pycon_us.year_map import Pin

SCREEN = "search"
"""The screen's name in its semantics identifiers (decisions §M)."""

FIRST_SESSIONS = 50
"""How many sessions a search shows until "Show all" (D-218): about eight screens."""

FIRST_SPEAKERS = 20
"""How many speakers a search shows until "Show all" (D-218): about five screens."""

FIRST_SPONSORS = 20
"""How many sponsors a search shows until "Show all" (D-218): "sponsor" finds every one."""

WHOLE: frozenset[str] = frozenset()
"""No type shown whole: what every new search starts with (D-218)."""


def plural(count: int, noun: str) -> str:
    """Return "1 session", "12 sessions": a count and its noun."""
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def summary(results: SearchResults) -> str:
    """Return what a search found, in words: "12 sessions, 3 speakers, 2 places, 1 sponsor".

    Only the types that matched are named, rooms, venue spots and booths as places
    (D-351); the line is a polite live region, so a
    screen reader hears what typing did without leaving the field (ux.md §4.3).

    Args:
        results: A search's results, at least one match.
    """
    counts = (
        (results.session_count, "session"),
        (len(results.speakers), "speaker"),
        (results.place_count, "place"),
        (len(results.sponsors), "sponsor"),
    )
    return ", ".join(plural(count, noun) for count, noun in counts if count)


def show_all_label(count: int, noun: str) -> str:
    """Return a "Show all" row's words: "Show all 326 sessions"."""
    return f"Show all {plural(count, noun)}"


@ft.memo
@ft.component
def ResultList(
    results: SearchResults,
    views: Mapping[str, SessionView],
    entries: Mapping[str, SpeakerEntry],
    saved: frozenset[str],
    changes: Changes,
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
    a day's (`TITLE_MEDIUM` in `on_surface`, with a divider before every type but
    the first), so that on screen too it opens a kind of result, not one more day.

    Each type shows its first rows (`first_results()`: `FIRST_SESSIONS`,
    `FIRST_SPEAKERS`, every place, `FIRST_SPONSORS`), then a "Show all" row when it found more, which
    renders the rest of that type (D-218). Which types are shown whole is this list's
    own state, held with the results it was asked of: a search that finds other
    results starts cut again, and so does the old query typed again after it; the
    count line above always says the full counts.

    Args:
        results: The last search's results.
        views: Every session's row view, by id, built once per feed version.
        entries: Every directory speaker's entry, by id, built once per feed version.
        saved: `Favorites.ids`.
        changes: Every session's recent changes (`use_recent_changes()`).
        on_toggle: The list's one star handler.
        tokens: The scheme's tokens (D-150).
        state: What shows instead of results (the hint, a miss, no data), or None.
    """
    view_path = ft.use_view_path()
    margin = use_margin(LIST)  # its width class (D-305)
    # The types the user asked to see whole, and the results they asked it of: other
    # results start cut again (D-218). Equal results are the same search, so a
    # keystroke that changes nothing keeps what was opened.
    asked, set_asked = ft.use_state((results, WHOLE))
    whole = asked[1] if asked[0] == results else WHOLE
    shown = ft.use_memo(
        lambda: first_results(
            results,
            sessions=None if "sessions" in whole else FIRST_SESSIONS,
            speakers=None if "speakers" in whole else FIRST_SPEAKERS,
            sponsors=None if "sponsors" in whole else FIRST_SPONSORS,
        ),
        [results, whole],
    )

    @report_errors
    async def forget() -> None:
        # Once other results show, what was opened goes: typing the old query again
        # (clearing "a", then "a") is a new search and starts cut, not opened.
        if asked[1] and asked[0] != results:
            set_asked((results, WHOLE))

    ft.use_effect(forget, [results])

    @report_errors
    def show_whole(e: ft.Event[ft.ListTile]) -> None:
        set_asked((results, whole | {e.control.data}))  # the row's type

    if state is not None:
        return ft.ListView([state], expand=True, padding=sides(margin))
    kinds = (results.sessions, results.speakers, results.place_count, results.sponsors)
    titled = sum(map(bool, kinds)) > 1
    day_level = 3 if titled else 2
    sections: list[tuple[str, list[ft.Control]]] = []
    if shown.sessions:
        days: list[ft.Control] = [
            DayGroup(
                group,
                views,
                saved & {s.id for s in group.sessions},
                changes_of(changes, (s.id for s in group.sessions)),
                on_toggle,
                tokens,
                screen=SCREEN,
                level=day_level,
                # Right under its type heading, the first day sits close to it.
                top=0 if titled and i == 0 else 16,
            )
            for i, group in enumerate(shown.sessions)
        ]
        if shown.session_count < results.session_count:
            days.append(show_all_row("sessions", results.session_count, show_whole))
        sections.append(("Sessions", days))
    if shown.speakers:
        speakers = [SpeakerRow(entries[s.id], screen=SCREEN) for s in shown.speakers]
        if len(shown.speakers) < len(results.speakers):
            speakers.append(show_all_row("speakers", len(results.speakers), show_whole))
        sections.append(("Speakers", speakers))
    if shown.place_count:
        places = [room_row(room, view_path) for room in shown.rooms]
        places += [spot_row(pin, view_path) for pin in shown.spots]
        places += [booth_row(entry, view_path) for entry in shown.booths]
        sections.append(("Places", places))
    if shown.sponsors:
        sponsors = [SponsorRow(s, screen=SCREEN) for s in shown.sponsors]
        if len(shown.sponsors) < len(results.sponsors):
            sponsors.append(show_all_row("sponsors", len(results.sponsors), show_whole))
        sections.append(("Sponsors", sponsors))
    items: list[ft.Control] = []
    for i, (name, rows) in enumerate(sections):
        if titled:
            if i:
                items.append(ft.Divider(height=1))
            items.append(type_heading(name))
        items.extend(rows)
    return ft.ListView(items, expand=True, padding=sides(margin))


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


def show_all_row(
    kind: str, count: int, on_click: ft.ControlEventHandler[ft.ListTile]
) -> ft.Control:
    """Return the row under a cut type that renders the rest of it (D-218).

    A real row, not a small text button: a Material `ListTile` (56 dp, wider than
    the 48 dp target) whose words say the full count, "Show all 326 sessions", in
    `primary` with `EXPAND_MORE` at its end, where the rows' chevrons and stars
    sit, so it reads as an action rather than one more result. Its text starts on the
    session rows' 16 dp line, and in `BODY_LARGE` it is no day heading
    (`TITLE_SMALL` in `primary`). One node for screen readers, read as its words
    and "button"; the icon says nothing. The rows it renders take its place.

    Args:
        kind: `sessions`, `speakers` or `sponsors`: its identifier's key and
            its noun.
        count: How many the type found, every row included.
        on_click: Renders the rest of the type, which it reads from the row's
            `data`.
    """
    return ft.MergeSemantics(
        content=ft.Semantics(
            identifier=f"{SCREEN}.show_all.{kind}",
            button=True,
            content=ft.ListTile(
                title=ft.Text(
                    show_all_label(count, kind.removesuffix("s")),
                    theme_style=ft.TextThemeStyle.BODY_LARGE,
                    color=ft.Colors.PRIMARY,
                ),
                trailing=ft.Icon(ft.Icons.EXPAND_MORE, color=ft.Colors.PRIMARY),
                data=kind,
                on_click=on_click,
            ),
        )
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
        subtitle=count_line(room),
        identifier=f"{SCREEN}.room.{room.slug}",
    )


def spot_row(pin: Pin, view_path: str) -> ft.Control:
    """Return a venue spot result: its label and sublabel, opening its floor plan.

    A tap pushes the floor viewer at the spot's pin (`…/plan/<plan>?pin=<key>`), as
    a `LocationCard` does, so Back returns to the results (D-351). Its leading icon
    is the pin's rather than the rooms' place mark: it opens a plan, not a detail.

    Args:
        pin: The venue spot (`MapData.venue_spots()`).
        view_path: This View's path, so the plan is pushed on top of search.
    """
    return LinkTile(
        pin.label,
        f"{drill_href(view_path, 'plan', pin.plan)}?pin={pin.key}",
        icon=ft.Icons.PIN_DROP_OUTLINED,
        subtitle=pin.sublabel or None,
        identifier=f"{SCREEN}.place.{pin.key}",
    )


def booth_title(entry: BoothEntry) -> str:
    """Return a booth result's title: "Booth 613 · Bloomberg", or "Booth 412" alone."""
    if not entry.name:
        return f"Booth {entry.number}"
    return f"Booth {entry.number} \N{MIDDLE DOT} {entry.name}"


def booth_phrase(entry: BoothEntry) -> str:
    """Return what a screen reader says of a booth result's title (#406).

    Returns:
        "Booth 613, Bloomberg", as the expo's booths and List rows are read; "Booth
        412" for a booth without a name.
    """
    return ", ".join(part for part in (f"Booth {entry.number}", entry.name) if part)


def booth_row(entry: BoothEntry, view_path: str) -> ft.Control:
    """Return a booth result: its number and exhibitor, opening the expo at the booth.

    A tap pushes the expo hall with the booth selected and its card
    (`booth_href()`, D-377), so Back returns to the results; a booth the plan does
    not draw says so under its title, and opens the List under its line. One node,
    read "Booth 613, Bloomberg" (the middle dot is not read), then the line when
    there is one. Its icon is the Sponsors entry's: a booth, not a room's place mark.

    Args:
        entry: The exhibitor at its booth (`core.expo.booth_entries()`).
        view_path: This View's path, so the expo is pushed on top of search.
    """
    return LinkTile(
        ft.Text(booth_title(entry), semantics_label=booth_phrase(entry)),
        booth_href(view_path, entry.number),
        icon=ft.Icons.STOREFRONT_OUTLINED,
        subtitle=None if entry.placed else UNPLACED,
        identifier=f"{SCREEN}.booth.{entry.key}",
    )
