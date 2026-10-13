"""Schedule (``/schedule``): the programme by day and time slot (SCHED-01, SCHED-02).

Day tabs over swipeable day lists (D-31): an ``ft.Tabs`` whose content starts with its
``TabBar`` (no ``AppBar.bottom``, U10), then the status strip, then a ``TabBarView`` with
one page per conference day, sprint days included. Each page is a ``DayList`` of
``SlotItem``s (``screens/schedule_days.py``), memoised down to the rows (D-153). The
first render fills only the shown day, the second the others (D-156).

The day opens on today during the conference, else on the first day; the day picked and
each list's offset live in ``ViewMemory``, so a tab return or a new session finds them
(D-18). A detail pushed over the Schedule keeps it mounted, and so its place.

Jump to now (D-155) lands on the current slot (``current_slot_key()``) once per process,
on the first display of today, and again with the "Now" button, which switches to today
first when another day shows. Without any data (no snapshot or cache, NEW-03) the
screen shows the skeleton until the first fetch has failed, then "Can't load the
schedule", which stays during a retry (D-32, ux.md §4.1).
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date

import flet as ft

from pycon_us import clock
from pycon_us.config import ConferenceInfo
from pycon_us.core.models import ConferenceData
from pycon_us.core.queries import days
from pycon_us.core.timefmt import day_heading, day_tab_label, today
from pycon_us.core.timeline import Slot, current_slot_key, timeline
from pycon_us.favorites import use_favorites
from pycon_us.prefs import use_prefs
from pycon_us.screens.schedule_days import SCREEN, DayList, Empty
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.services.storage import THEME
from pycon_us.state import Conference, use_conference
from pycon_us.theme import use_tokens
from pycon_us.ui.badges import NOT_SAVED, SNACK_BAR_MS, use_favorite_toggle
from pycon_us.ui.navigation import RETAP_SCROLL_MS
from pycon_us.ui.scaffold import AppScaffold, StatusStrip, search_button
from pycon_us.ui.scrolling import JUMP_MS, jump_to_key
from pycon_us.ui.session_rows import use_session_views
from pycon_us.ui.states import NO_DATA_BODY, EmptyState, SkeletonList

logger = logging.getLogger(__name__)

TAB_MS = 100
"""How long a day switch made from Python slides (Flet's default for ``Tabs``)."""

TAB_HEIGHT = 56
"""A day tab's height in dp, above Flutter's 46 for a text tab: the tab bar cannot grow
with the text, and Flet cannot read the text scale (U16), so it is sized for the largest
iOS size (about 310 %), where a one-line label's glyphs need about 52 dp."""

TODAY_DOT = 6
"""The diameter of the dot that marks today's tab, in dp (ux.md §5.2)."""

SETTLE_S = 1.0
"""How long the "Now" button waits for the switch to today to settle, in seconds."""


@dataclass(eq=False)
class Signals:
    """What the Schedule's handlers tell its jumps; one per mounted screen.

    Attributes:
        ended: Set when the shown list's scroll ends (``jump_to_key()``).
        settled: Set when ``Tabs`` reports a day, which it does once a switch has
            finished sliding, the one asked for from Python included.
    """

    ended: asyncio.Event = field(default_factory=asyncio.Event)
    settled: asyncio.Event = field(default_factory=asyncio.Event)


@ft.component
def Schedule() -> ft.View:
    """The Schedule root: day tabs, the status strip and one slot list per day."""
    page = ft.context.page
    svc = use_services()
    memory = svc.memory
    conference = use_conference()
    favorites = use_favorites()
    prefs = use_prefs()
    on_toggle = use_favorite_toggle(favorites)
    tokens = use_tokens()
    info = svc.year.conference
    use_24h = bool(page.media and page.media.always_use_24_hour_format)
    data = conference.data
    current = today(clock.now(), info.zone)  # the Developer fake clock moves it (D-43)
    all_days = days(data, info.first_day, info.last_day) if data else ()
    picked, set_picked = ft.use_state(memory.schedule_day)
    shown = picked if picked in all_days else _default_day(all_days, current)
    rest, set_rest = ft.use_state(False)  # the other days are rendered (D-156)
    jump, set_jump = ft.use_state(0)  # a "Now" tap from another day's tab
    refs = ft.use_memo(dict[date, ft.Ref[ft.ListView]], [])
    signals = ft.use_memo(Signals, [])
    excluded = prefs.excluded_tracks
    slots = ft.use_memo(
        lambda: (
            {day: timeline(data, day, excluded) for day in all_days} if data else {}
        ),
        [conference.version, excluded],
    )
    day_ids = ft.use_memo(
        lambda: {
            day: frozenset(s.id for slot in day_slots for s in slot.sessions)
            for day, day_slots in slots.items()
        },
        [slots],
    )
    ids = tuple(data.sessions) if data else ()
    views = use_session_views(conference, ids, use_24h=use_24h)
    by_id = ft.use_memo(lambda: {v.session.id: v for v in views}, [views])
    today_slots = slots.get(current, ())

    @report_errors
    async def jump_to_now() -> None:
        await _jump_to_now(
            _ref(refs, current),
            today_slots,
            duration=prefs.motion_ms(JUMP_MS),
            ended=signals.ended,
        )

    @report_errors
    async def opened() -> None:
        jumps = not memory.jumped_to_now and shown == current and bool(today_slots)
        # A round trip: Flutter has applied the first render's patch (D-155, D-156).
        await svc.storage.get(THEME)
        set_rest(True)
        if jumps:
            memory.jumped_to_now = True  # once per process (D-18)
            await jump_to_now()
        elif shown is not None:
            await _restore(_ref(refs, shown), memory.schedule_offsets.get(shown))

    ft.use_effect(opened, [])

    @report_errors
    async def jump_after_switch() -> None:
        if not jump:
            return
        try:  # the switch to today has slid in, so its list is built
            await asyncio.wait_for(signals.settled.wait(), SETTLE_S)
        except TimeoutError:
            logger.info("Jump to now: the switch to today did not report back")
        await jump_to_now()

    ft.use_effect(jump_after_switch, [jump])

    @report_errors
    async def changed(e: ft.Event[ft.Tabs]) -> None:
        signals.settled.set()
        day = all_days[e.control.selected_index]
        if day == shown:  # the echo of a switch made from Python
            return
        memory.schedule_day = day
        set_picked(day)
        await _restore(_ref(refs, day), memory.schedule_offsets.get(day))

    @report_errors
    async def now_pressed() -> None:
        if shown == current:
            await jump_to_now()
            return
        signals.settled.clear()
        memory.schedule_day = current
        set_picked(current)
        set_jump(lambda n: n + 1)

    @report_errors
    async def scroll_to_top() -> None:
        target = _ref(refs, shown).current if shown else None
        if target is not None:
            await target.scroll_to(offset=0, duration=prefs.motion_ms(RETAP_SCROLL_MS))

    @report_errors
    def scrolled(day: date, e: ft.OnScrollEvent) -> None:
        if e.event_type == ft.ScrollType.END:
            memory.schedule_offsets[day] = e.pixels
            signals.ended.set()

    on_scroll = ft.use_callback(scrolled, [])

    @report_errors
    async def clear_filters() -> None:
        if not await prefs.save(svc.storage, excluded_tracks=()):
            page.show_dialog(
                ft.SnackBar(
                    ft.Text(NOT_SAVED),
                    behavior=ft.SnackBarBehavior.FLOATING,
                    duration=SNACK_BAR_MS,
                )
            )

    on_clear_filters = ft.use_callback(clear_filters, [])

    @report_errors
    async def try_again() -> None:
        await conference.refresh(svc.storage, svc.year, closed=svc.closed)

    if data is None or shown is None:
        return AppScaffold(
            title="Schedule",
            actions=[search_button(memory, "sessions")],
            body=ft.ListView(
                [StatusStrip(auto_refresh=True), _no_data(conference, info, try_again)],
                expand=True,
            ),
        )

    pages: list[ft.Control] = []
    for day in all_days:
        if day != shown and not rest:
            pages.append(ft.Container(key=day.isoformat()))  # the second render's
            continue
        pages.append(
            DayList(
                day,
                slots[day],
                by_id,
                favorites.ids & day_ids[day],  # only this day's (D-153)
                on_toggle,
                tokens,
                use_24h=use_24h,
                full=day == current,  # the one list a jump targets (D-154)
                clearance=bool(today_slots),
                empty=_empty(data, day, slots[day]),
                list_ref=_ref(refs, day),
                on_scroll=on_scroll,
                on_clear_filters=on_clear_filters,
            )
        )
    tabs = ft.Tabs(
        length=len(all_days),
        selected_index=all_days.index(shown),
        animation_duration=ft.Duration(milliseconds=prefs.motion_ms(TAB_MS)),
        on_change=changed,
        expand=True,
        content=ft.Column(
            [
                ft.TabBar(
                    [
                        _day_tab(index, day, is_today=day == current)
                        for index, day in enumerate(all_days)
                    ],
                    # One-line labels in a scrollable bar: seven days fit no phone,
                    # and the bar's fixed height clips a second line at 200 % (S2).
                    scrollable=True,
                    tab_alignment=ft.TabAlignment.START,
                ),
                StatusStrip(auto_refresh=True),
                ft.TabBarView(pages, expand=True),
            ],
            spacing=0,
            expand=True,
        ),
    )
    return AppScaffold(
        title="Schedule",
        actions=[search_button(memory, "sessions")],
        body=tabs,
        on_retap=scroll_to_top,
        fab=_now_button(on_today=shown == current, on_click=now_pressed)
        if today_slots
        else None,
    )


def _ref(refs: dict[date, ft.Ref[ft.ListView]], day: date) -> ft.Ref[ft.ListView]:
    """Return the day list's ref, one per day for the screen's life (F38)."""
    return refs.setdefault(day, ft.Ref[ft.ListView]())


async def _jump_to_now(
    list_ref: ft.Ref[ft.ListView],
    slots: tuple[Slot, ...],
    *,
    duration: int,
    ended: asyncio.Event,
) -> None:
    """Scroll today's list to the current slot (``current_slot_key()``, D-155)."""
    key = current_slot_key(slots, clock.now())
    if key is not None:
        await jump_to_key(list_ref, key, duration=duration, ended=ended)


async def _restore(list_ref: ft.Ref[ft.ListView], offset: float | None) -> None:
    """Put a day list back where its last scroll ended (D-18).

    A day list that shows again is a new list on the device, at the top: the tab
    bar's pages keep nothing of a page they no longer show.
    """
    if offset and list_ref.current is not None:
        await list_ref.current.scroll_to(offset=offset, duration=0)


def _default_day(all_days: tuple[date, ...], current: date) -> date | None:
    """Return the day the Schedule opens on: today during the conference, else day 1."""
    if current in all_days:
        return current
    return all_days[0] if all_days else None


def _empty(data: ConferenceData, day: date, shown: tuple[Slot, ...]) -> Empty | None:
    """Return why a day shows no slots: no sessions at all, or the filter (D-178)."""
    if shown:
        return None
    return "filtered" if timeline(data, day, ()) else "sprint"


def _day_tab(index: int, day: date, *, is_today: bool) -> ft.Tab:
    """Return a day's tab: "Fri 15", today with a dot, read "Friday, May 15, today".

    The text's semantics label says the day in full; Flutter's tab bar puts its own
    position label before it and adds the selection, so TalkBack reads "Tab 3 of 7,
    Friday, May 15, today, selected" (D-192).
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
        label = ft.Row(
            [label, dot],
            spacing=4,
            tight=True,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )
    return ft.Tab(
        height=TAB_HEIGHT,
        # Unlabelled: Flutter merges the identifier into the tab's node (D-166).
        label=ft.Semantics(identifier=f"{SCREEN}.day_tab.{index}", content=label),
    )


def _now_button(
    *, on_today: bool, on_click: Callable[[], Awaitable[None]]
) -> ft.FloatingActionButton:
    """Return the "Now" button (SCHED-15): "Today" while another day shows."""
    return ft.FloatingActionButton(
        content=ft.Semantics(
            identifier=f"{SCREEN}.jump_now",
            content=ft.Text("Now" if on_today else "Today"),
        ),
        icon=ft.Icons.SCHEDULE,
        tooltip="Jump to the current time",
        on_click=on_click,
    )


def _no_data(
    conference: Conference,
    info: ConferenceInfo,
    try_again: Callable[[], Awaitable[None]],
) -> ft.Control:
    """Return the state without any data: the skeleton, or the failure with Try again."""
    if conference.problem is None:
        return SkeletonList()  # the first fetch runs, or is about to (NEW-03)
    return EmptyState(
        "Can't load the schedule",
        icon=ft.Icons.CLOUD_OFF_OUTLINED,
        body=NO_DATA_BODY[conference.problem],
        action="Try again",
        on_action=try_again,
        # A retry keeps the state in place, so a screen reader's focus stays on the
        # button; the strip's bar shows the work. A quiet refresh leaves it enabled,
        # so a tap joins it (D-181).
        disabled=conference.status(info) == "refreshing",
        identifier="schedule.no_data",
    )
