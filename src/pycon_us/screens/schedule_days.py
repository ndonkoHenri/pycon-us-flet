"""The Schedule's day lists: one memoised list per day, one memoised item per slot.

``screens/schedule.py`` owns the screen: the day tabs, the stores and the jumps. Here is
what it places in each ``TabBarView`` page (D-31, D-153..D-156):

- ``DayList``, memoised and given only its day's slots and favourites, so a star tap
  re-renders one day list, one slot and one row (D-153);
- ``SlotItem``, memoised and keyed by its slot key, with the ``ScrollKey`` a jump scrolls
  to (D-155): the ``TimeGutter`` beside the slot's ``SessionRow``s and ``NoticeRow``s;
- the empty days: a sprint day, which has no sessions, and a day the filter empties.

A day list is a lazy ``ListView``; today's builds every slot (``FULL_LIST_EXTENT``), so
Jump to now reaches any of them (D-154). Each list reports where a scroll ended, which
the Schedule keeps in ``ViewMemory`` and a jump waits for.
"""

from collections.abc import Callable, Mapping
from datetime import date
from typing import Literal

import flet as ft

from pycon_us.core.row_views import SessionView
from pycon_us.core.timefmt import time_label, weekday_name
from pycon_us.core.timeline import Slot
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.theme import Tokens
from pycon_us.ui.badges import ToggleFavorite
from pycon_us.ui.scrolling import FULL_LIST_EXTENT, SCROLL_EVENT_MS
from pycon_us.ui.session_rows import NoticeRow, SessionRow, TimeGutter, is_notice
from pycon_us.ui.states import EmptyState

SCREEN = "schedule"
"""The screen's name in its rows' semantics identifiers (decisions §M)."""

SPRINTS = "/more/sprints"
"""Where a sprint day's empty state leads (SCHED-01, EVT-05)."""

FAB_CLEARANCE = 88
"""Room under a list's last slot for the "Now" button: its 56 dp and 16 dp around it,
so the last row's star is never under it (ux.md §2.4)."""

type Empty = Literal["sprint", "filtered"]
"""Why a day shows no slots: a sprint day has no sessions; a filter hid all of them."""

type Scrolled = Callable[[date, ft.OnScrollEvent], None]
"""The Schedule's one scroll handler: a day list passes its day and the event."""


def DayList(
    day: date,
    slots: tuple[Slot, ...],
    views: Mapping[str, SessionView],
    favorites: frozenset[str],
    on_toggle: ToggleFavorite,
    tokens: Tokens,
    *,
    use_24h: bool,
    full: bool,
    clearance: bool,
    empty: Empty | None,
    list_ref: ft.Ref[ft.ListView],
    on_scroll: Scrolled,
    on_clear_filters: Callable[[], object],
) -> ft.Control:
    """Return one day's page: its slots, or the reason it has none (D-31, ux.md §4.6).

    A memoised component keyed by the day (D-153): with stable props it re-renders only
    when its slots, its own favourites, the clock format or the tokens change.

    Args:
        day: The conference-local date.
        slots: Its slots as the filter leaves them (``timeline()``), the same objects
            while the feed and the filter stay the same (D-178).
        views: Every session's row view by id, built once per feed version.
        favorites: The saved ids among this day's sessions only.
        on_toggle: The screen's one star handler (``use_favorite_toggle()``).
        tokens: The scheme's tokens (D-150).
        use_24h: Whether the device uses the 24-hour clock.
        full: Build every slot (today's list, D-154), so a jump reaches any of them.
        clearance: Leave room at the end for the "Now" button.
        empty: Why ``slots`` is empty, when it is.
        list_ref: The day's list ref, which the jumps and the re-tap scroll.
        on_scroll: The screen's scroll handler, given this day.
        on_clear_filters: What "Clear filters" does on a day the filter emptied.
    """
    return _DayList(
        day,
        slots,
        views,
        favorites,
        on_toggle,
        tokens,
        use_24h=use_24h,
        full=full,
        clearance=clearance,
        empty=empty,
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
    on_toggle: ToggleFavorite,
    tokens: Tokens,
    *,
    use_24h: bool,
    full: bool,
    clearance: bool,
    empty: Empty | None,
    list_ref: ft.Ref[ft.ListView],
    on_scroll: Scrolled,
    on_clear_filters: Callable[[], object],
) -> ft.Control:
    """The body of ``DayList``; it runs only when the props change (F34)."""
    page = ft.context.page
    zone = use_services().year.conference.zone

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
                body="No talks on sprint days: people work on open-source projects together, "
                "and anyone can join one.",
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
                on_toggle,
                tokens,
                label=time_label(slot.start, zone, use_24h=use_24h),
                divider=index > 0,
            )
            for index, slot in enumerate(slots)
        ]
    return ft.ListView(
        items,
        key=f"day-{day.isoformat()}",
        ref=list_ref,
        expand=True,
        # Today's list builds every slot, so each ScrollKey is registered (D-154).
        cache_extent=FULL_LIST_EXTENT if full else None,
        padding=ft.Padding.only(bottom=FAB_CLEARANCE if clearance else 8),
        scroll_interval=SCROLL_EVENT_MS,
        on_scroll=scrolled,
    )


def SlotItem(
    slot: Slot,
    views: Mapping[str, SessionView],
    favorites: frozenset[str],
    on_toggle: ToggleFavorite,
    tokens: Tokens,
    *,
    label: str,
    divider: bool,
) -> ft.Control:
    """Return one time slot (D-31): its time in the gutter, beside its rows.

    A memoised component keyed by the slot key (D-153); its control carries
    ``ScrollKey(slot.key)``, the target of a jump (D-155). Rows are in schedule order
    (by room, D-31); breaks and notices are ``NoticeRow``s, without a star.

    Args:
        slot: The slot, with its sessions in schedule order.
        views: Every session's row view by id.
        favorites: The saved ids among this slot's sessions only.
        on_toggle: The screen's one star handler.
        tokens: The scheme's tokens.
        label: The gutter's time, e.g. "9:25 AM" (``timefmt.time_label()``).
        divider: Draw a 1 dp divider above the slot (every slot but the first).
    """
    return _SlotItem(
        slot,
        views,
        favorites,
        on_toggle,
        tokens,
        label=label,
        divider=divider,
        key=slot.key,  # pyright: ignore[reportCallIssue]  # as SessionRow's
    )


@ft.memo
@ft.component
def _SlotItem(
    slot: Slot,
    views: Mapping[str, SessionView],
    favorites: frozenset[str],
    on_toggle: ToggleFavorite,
    tokens: Tokens,
    *,
    label: str,
    divider: bool,
) -> ft.Control:
    """The body of ``SlotItem``; it runs only when the props change (F34)."""
    info = use_services().year.conference
    rows: list[ft.Control] = []
    for session in slot.sessions:
        view = views[session.id]
        if is_notice(session, info):
            rows.append(NoticeRow(view, screen=SCREEN))
        else:
            rows.append(
                SessionRow(
                    view, session.id in favorites, on_toggle, tokens, screen=SCREEN
                )
            )
    content: ft.Control = ft.Row(
        [TimeGutter(label), ft.Column(rows, spacing=0, expand=True)],
        spacing=0,
        vertical_alignment=ft.CrossAxisAlignment.START,
    )
    if divider:
        content = ft.Column([ft.Divider(height=1), content], spacing=0)
    # The jump's target: a ScrollKey, not a plain key, which scroll_to never sees.
    return ft.Container(content, key=ft.ScrollKey(slot.key))
