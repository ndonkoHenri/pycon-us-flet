"""What the Schedule shows for each day: its tab, its list and its slots, and "Now".

``screens/schedule.py`` owns the screen: the stores, the positions and the jumps. Here
is what it places (D-31, D-153..D-156, D-192):

- ``day_tab()``, a day's one-line tab, read as its full date, today's with a dot;
- ``DayList``, a ``TabBarView`` page, memoised and given only its day's slots and
  favourites, so a star tap re-renders one day list, one slot and one row (D-153);
- ``SlotItem``, memoised and keyed by its slot key, with the ``ScrollKey`` a jump scrolls
  to (D-155): the ``TimeGutter`` beside the slot's ``SessionRow``s and ``NoticeRow``s,
  or its time above them at the largest text sizes (D-216);
- today's ``NowLine`` among the slots (``screens/schedule_now.py``, D-204);
- at the largest text sizes, the Schedule's head above the slots, so it scrolls away
  (``screens/schedule_head.py``, D-345);
- the empty days: a sprint day, which has no sessions, and a day the filter empties;
- ``now_button()``, the "Now" button over today's list (SCHED-15).

A day list is a lazy ``ListView``; today's builds every slot (``FULL_LIST_EXTENT``), so
Jump to now reaches any of them (D-154). Each list reports where a scroll ended, which
the Schedule keeps in ``ViewMemory`` and a jump waits for.
"""

from collections.abc import Awaitable, Callable, Mapping
from datetime import date
from typing import Literal

import flet as ft

from pycon_us.core.row_views import SessionView
from pycon_us.core.timefmt import day_heading, day_tab_label, time_label, weekday_name
from pycon_us.core.timeline import Slot
from pycon_us.screens.schedule_head import HEAD_KEY, Head, ScheduleHead
from pycon_us.screens.schedule_now import NowLine, NowMark
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.theme import Tokens
from pycon_us.ui.favorite import ToggleFavorite
from pycon_us.ui.scrolling import FULL_LIST_EXTENT, SCROLL_EVENT_MS, anchored
from pycon_us.ui.session_rows import (
    NO_CHANGES,
    Changes,
    NoticeRow,
    SessionRow,
    changes_of,
    is_notice,
)
from pycon_us.ui.states import EmptyState
from pycon_us.ui.time_gutter import slot_layout
from pycon_us.ui.widths import LIST, sides, use_margin

SCREEN = "schedule"
"""The screen's name in its rows' semantics identifiers (decisions §M)."""

SPRINTS = "/more/sprints"
"""Where a sprint day's empty state leads (SCHED-01, EVT-05)."""

FAB_CLEARANCE = 88
"""Room under a list's last slot for the "Now" button: its 56 dp and 16 dp around it,
so the last row's star is never under it (ux.md §2.4)."""

TAB_HEIGHT = 56
"""A day tab's height in dp, above Flutter's 46 for a text tab: the tab bar cannot grow
with the text, and Flet cannot read the text scale (U16), so it is sized for the largest
iOS size (about 310 %), where a one-line label's glyphs need about 52 dp."""

TAB_MS = 100
"""How long a day switch made from Python slides (Flet's default for ``Tabs``); the
Schedule's and a room's tabs (D-194)."""

TODAY_DOT = 6
"""The diameter of the dot that marks today's tab, in dp (ux.md §5.2)."""

JUMP_TOOLTIP = "Jump to the current time"
"""What the "Now" button does: its tooltip, said after its label (ux.md §5.2)."""

type Empty = Literal["sprint", "filtered"]
"""Why a day shows no slots: a sprint day has no sessions; a filter hid all of them."""

type Scrolled = Callable[[date, ft.OnScrollEvent], None]
"""The Schedule's one scroll handler: a day list passes its day and the event."""


def day_tab(index: int, day: date, *, is_today: bool, screen: str = SCREEN) -> ft.Tab:
    """Return a day's tab: "Fri 15", today with a dot, read "Friday, May 15, today".

    The text's semantics label says the day in full; Flutter's tab bar puts its own
    position label before it and adds the selection, so TalkBack reads "Tab 3 of 7,
    Friday, May 15, today, selected" (D-192). Room detail's tabs are these too (D-194).

    Args:
        index: The tab's position, in its identifier ``<screen>.day_tab.<index>``.
        day: The conference-local date.
        is_today: Mark it as today, with a dot and ", today".
        screen: The screen's name in the identifier: the Schedule's, or ``room``.
    """
    spoken = f"{day_heading(day)}, today" if is_today else day_heading(day)
    label: ft.Control = ft.Text(day_tab_label(day), semantics_label=spoken)
    if is_today:
        # Beside the text, not a Badge over it: a badge's dot covered the last digit.
        dot = ft.Container(
            width=TODAY_DOT,
            height=TODAY_DOT,
            border_radius=TODAY_DOT / 2,
            bgcolor=ft.Colors.PRIMARY,
        )
        # Centred on the label, so it stays beside the digits at every text size.
        label = ft.Row(
            [label, dot],
            spacing=4,
            tight=True,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
    return ft.Tab(
        height=TAB_HEIGHT,
        # Unlabelled: Flutter merges the identifier into the tab's node (D-166).
        label=ft.Semantics(identifier=f"{screen}.day_tab.{index}", content=label),
    )


def DayList(
    day: date,
    slots: tuple[Slot, ...],
    views: Mapping[str, SessionView],
    favorites: frozenset[str],
    changes: Changes,
    on_toggle: ToggleFavorite,
    tokens: Tokens,
    *,
    use_24h: bool,
    time_above: bool,
    full: bool,
    clearance: bool,
    empty: Empty | None,
    now: NowMark | None,
    head: Head | None,
    list_ref: ft.Ref[ft.ListView],
    on_scroll: Scrolled,
    on_clear_filters: Callable[[], object],
) -> ft.Control:
    """Return one day's page: its slots, or the reason it has none (D-31, ux.md §4.6).

    A memoised component keyed by the day (D-153): with stable props it re-renders only
    when its slots, its own favourites or changes, the clock format, the slots' layout
    or the tokens change.

    Args:
        day: The conference-local date.
        slots: Its slots as the filter leaves them (``timeline()``), the same objects
            while the feed and the filter stay the same (D-178).
        views: Every session's row view by id, built once per feed version.
        favorites: The saved ids among this day's sessions only.
        changes: The recent changes of this day's sessions only (``changes_of()``).
        on_toggle: The screen's one star handler (``use_favorite_toggle()``).
        tokens: The scheme's tokens (D-150).
        use_24h: Whether the device uses the 24-hour clock.
        time_above: Put each slot's time above its rows (``Prefs.time_above``,
            D-216).
        full: Build every slot (today's list, D-154), so a jump reaches any of them.
        clearance: Leave room at the end for the "Now" button.
        empty: Why ``slots`` is empty, when it is.
        now: Today's now line; None on the other days.
        head: The Schedule's head, at the top of the list at the largest text sizes
            (D-345); None while it stays fixed above the day pages.
        list_ref: The day's list ref, which the jumps and the re-tap scroll.
        on_scroll: The screen's scroll handler, given this day.
        on_clear_filters: What "Clear filters" does on a day the filter emptied.
    """
    return _DayList(
        day,
        slots,
        views,
        favorites,
        changes,
        on_toggle,
        tokens,
        use_24h=use_24h,
        time_above=time_above,
        full=full,
        clearance=clearance,
        empty=empty,
        now=now,
        head=head,
        list_ref=list_ref,
        on_scroll=on_scroll,
        on_clear_filters=on_clear_filters,
        key=day.isoformat(),  # pyright: ignore[reportCallIssue]  # as SessionRow's
    )


@ft.memo
@ft.component
def _DayList(
    day: date,
    slots: tuple[Slot, ...],
    views: Mapping[str, SessionView],
    favorites: frozenset[str],
    changes: Changes,
    on_toggle: ToggleFavorite,
    tokens: Tokens,
    *,
    use_24h: bool,
    time_above: bool,
    full: bool,
    clearance: bool,
    empty: Empty | None,
    now: NowMark | None,
    head: Head | None,
    list_ref: ft.Ref[ft.ListView],
    on_scroll: Scrolled,
    on_clear_filters: Callable[[], object],
) -> ft.Control:
    """The body of ``DayList``; it runs only when the props change (F34).

    It also follows the screen's side margin (``use_margin()``, D-305), which changes
    only with the window.
    """
    page = ft.context.page
    zone = use_services().year.conference.zone
    margin = use_margin(LIST)

    @report_errors
    def see_sprints() -> None:
        page.navigate(SPRINTS)

    @report_errors
    def scrolled(e: ft.OnScrollEvent) -> None:
        on_scroll(day, e)

    items: list[ft.Control]
    if empty == "sprint":
        items = [
            EmptyState(
                f"{weekday_name(day)} is a sprint day",
                icon=ft.Icons.ROCKET_LAUNCH_OUTLINED,
                body="No talks on sprint days: people work on open-source projects "
                "together, and anyone can join one.",
                action="See the sprints",
                on_action=see_sprints,
                identifier=f"{SCREEN}.sprint_day.{day.isoformat()}",
            )
        ]
    elif empty == "filtered":
        items = [
            EmptyState(
                f"No sessions on {weekday_name(day)} match your filters",
                icon=ft.Icons.FILTER_ALT_OFF_OUTLINED,
                action="Clear filters",
                on_action=on_clear_filters,
                identifier=f"{SCREEN}.filtered_day.{day.isoformat()}",
            )
        ]
    else:
        items = [
            SlotItem(
                slot,
                views,
                favorites & {s.id for s in slot.sessions},
                changes_of(changes, (s.id for s in slot.sessions)),
                on_toggle,
                tokens,
                label=time_label(slot.start, zone, use_24h=use_24h),
                time_above=time_above,
                # The now line divides it from the slot above: one line, not two.
                divider=index > 0 and (now is None or index != now.index),
            )
            for index, slot in enumerate(slots)
        ]
        if now is not None:
            items.insert(now.index, NowLine(now.time))
    if head is not None:  # it scrolls away with the slots (D-345)
        items.insert(0, ScheduleHead(head, on_clear_filters, key=HEAD_KEY))  # pyright: ignore[reportCallIssue]
    return ft.ListView(
        items,
        key=f"day-{day.isoformat()}",
        ref=list_ref,
        expand=True,
        # Today's list builds every slot, so each ScrollKey is registered (D-154).
        cache_extent=FULL_LIST_EXTENT if full else None,
        padding=sides(margin, bottom=FAB_CLEARANCE if clearance else 8),
        scroll_interval=SCROLL_EVENT_MS,
        on_scroll=scrolled,
    )


def SlotItem(
    slot: Slot,
    views: Mapping[str, SessionView],
    favorites: frozenset[str],
    changes: Changes,
    on_toggle: ToggleFavorite,
    tokens: Tokens,
    *,
    label: str,
    time_above: bool,
    divider: bool,
) -> ft.Control:
    """Return one time slot (D-31): its time in the gutter beside its rows, or above.

    A memoised component keyed by the slot key (D-153); an anchor above its time and
    rows carries ``ScrollKey(slot.key)``, the target of a jump (D-155, D-242), and its
    divider sits above that anchor. Rows are in schedule order
    (by room, D-31); breaks and notices are ``NoticeRow``s, without a star.

    Args:
        slot: The slot, with its sessions in schedule order.
        views: Every session's row view by id.
        favorites: The saved ids among this slot's sessions only.
        changes: The recent changes of this slot's sessions only.
        on_toggle: The screen's one star handler.
        tokens: The scheme's tokens.
        label: The slot's time, e.g. "9:25 AM" (``timefmt.time_label()``).
        time_above: Put the time above the rows rather than in the gutter (D-216).
        divider: Draw a 1 dp divider above the slot (every slot but the first).
    """
    return _SlotItem(
        slot,
        views,
        favorites,
        changes,
        on_toggle,
        tokens,
        label=label,
        time_above=time_above,
        divider=divider,
        key=slot.key,  # pyright: ignore[reportCallIssue]  # as SessionRow's
    )


@ft.memo
@ft.component
def _SlotItem(
    slot: Slot,
    views: Mapping[str, SessionView],
    favorites: frozenset[str],
    changes: Changes,
    on_toggle: ToggleFavorite,
    tokens: Tokens,
    *,
    label: str,
    time_above: bool,
    divider: bool,
) -> ft.Control:
    """The body of ``SlotItem``; it runs only when the props change (F34)."""
    info = use_services().year.conference
    rows: list[ft.Control] = []
    for session in slot.sessions:
        view = views[session.id]
        if is_notice(session, info):
            rows.append(
                NoticeRow(
                    view,
                    tokens,
                    screen=SCREEN,
                    changed=changes.get(session.id, NO_CHANGES),
                )
            )
        else:
            rows.append(
                SessionRow(
                    view,
                    session.id in favorites,
                    on_toggle,
                    tokens,
                    screen=SCREEN,
                    changed=changes.get(session.id, NO_CHANGES),
                )
            )
    # The jump's target: a ScrollKey, not a plain key, which scroll_to never sees, on
    # an anchor above the slot, so the rows keep their nodes (D-242).
    keyed = anchored(slot.key, slot_layout(label, rows, above=time_above))
    # The divider stays above the anchor, so a jump puts the slot's time, not its
    # divider, under the tab bar's own line (one 1 dp line there, not two). Hidden
    # rather than left out: the slot keeps its place in the tree when the now line
    # takes or gives back the divider, so its rows are kept as they are (D-204).
    return ft.Column([ft.Divider(height=1, visible=divider), keyed], spacing=0)


def now_button(
    *, on_today: bool, on_click: Callable[[], Awaitable[None]], margin: float = 0
) -> ft.FloatingActionButton:
    """Return the "Now" button (SCHED-15): "Today" while another day shows.

    What it does is said after its label, from inside the button, which Flutter's
    button merges into its own node ("Now", then "Jump to the current time"). Flet's
    ``tooltip`` sits around the button, a node of its own beside it, and a View takes
    only a ``FloatingActionButton``, so no merge can go around it: the tooltip shown on
    a long press stays out of the semantics (F55, D-234). Said by the label's
    ``semantics_label``, as a link's "Opens in browser" is (ux.md §4.7): a
    ``Semantics``' ``tooltip`` would show a second tooltip too, and its ``hint_text``
    never reaches Flutter at the pin (#187).

    Args:
        on_today: Whether today's list shows: "Now", else "Today".
        on_click: The jump.
        margin: The screen's side margin (D-305): the button keeps to the list's
            right edge, its transparent margin passing taps through to the list.
    """
    label = "Now" if on_today else "Today"
    return ft.FloatingActionButton(
        content=ft.Semantics(
            identifier=f"{SCREEN}.jump_now",
            content=ft.Text(label, semantics_label=f"{label}\n{JUMP_TOOLTIP}"),
        ),
        icon=ft.Icons.SCHEDULE,
        tooltip=ft.Tooltip(JUMP_TOOLTIP, exclude_from_semantics=True),
        on_click=on_click,
        margin=ft.Margin.only(right=margin),
    )
