"""Schedule (``/schedule``): the programme by day and time slot (SCHED-01, SCHED-02).

Day tabs over swipeable day lists (D-31): an ``ft.Tabs`` whose content starts with its
``TabBar`` (no ``AppBar.bottom``, U10), then the status strip, then a ``TabBarView`` with
one page per conference day, sprint days included. The tabs, the pages and the "Now"
button come from ``screens/schedule_days.py``: each page is a ``DayList`` of
``SlotItem``s, memoised down to the rows (D-153). The first render fills only the shown
day, the second the others (D-156).

The day opens on today during the conference, else on the first day; the day picked and
each list's offset live in ``ViewMemory``, so a tab return or a new session finds them
(D-18). A detail pushed over the Schedule keeps it mounted, and so its place.

Jump to now (D-155) lands on the current slot (``current_slot_key()``) once per process,
on the first display of today, and again with the "Now" button, which switches to today
first when another day shows, and tells a screen reader where it landed. Without any
data (no snapshot or cache, NEW-03) the screen shows the skeleton until the first fetch
has failed, then "Can't load the schedule", which stays during a retry (D-32, ux.md
§4.1).
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date

import flet as ft

from pycon_us import clock
from pycon_us.core.models import ConferenceData
from pycon_us.core.queries import days
from pycon_us.core.timefmt import day_heading, time_label, today
from pycon_us.core.timeline import Slot, current_slot_key, timeline
from pycon_us.favorites import use_favorites
from pycon_us.prefs import use_prefs
from pycon_us.screens.schedule_days import DayList, Empty, day_tab, now_button
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.services.storage import SERVICE_ERRORS, THEME
from pycon_us.state import use_conference
from pycon_us.theme import use_tokens
from pycon_us.ui.badges import NOT_SAVED, SNACK_BAR_MS, use_favorite_toggle
from pycon_us.ui.navigation import RETAP_SCROLL_MS
from pycon_us.ui.scaffold import AppScaffold, StatusStrip, search_button
from pycon_us.ui.scrolling import JUMP_MS, jump_to_key
from pycon_us.ui.session_rows import use_session_views
from pycon_us.ui.states import NoDataState

logger = logging.getLogger(__name__)

TAB_MS = 100
"""How long a day switch made from Python slides (Flet's default for ``Tabs``)."""

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
    async def jump_to_now(*, asked: bool) -> None:
        landed = await _jump_to_now(
            _ref(refs, current),
            today_slots,
            duration=prefs.motion_ms(JUMP_MS),
            ended=signals.ended,
        )
        # The user's own tap: a screen reader hears where the list went, since the
        # tab switch and the scroll are silent. The first display's jump is not asked.
        if asked and landed is not None and prefs.screen_reader and prefs.announcements:
            when = time_label(landed.start, info.zone, use_24h=use_24h)
            try:
                await svc.semantics.announce_message(f"{day_heading(current)}, {when}")
            except SERVICE_ERRORS:  # the list is in place; a lost phrase is no error
                logger.warning("Could not announce the jump", exc_info=True)

    @report_errors
    async def opened() -> None:
        if shown is None:  # no data yet: the first display is the render that has it
            return
        jumps = not memory.jumped_to_now and shown == current and bool(today_slots)
        # A round trip: Flutter has applied the first render's patch (D-155, D-156).
        await svc.storage.get(THEME)
        set_rest(True)
        if jumps:
            memory.jumped_to_now = True  # once per process (D-18)
            await jump_to_now(asked=False)
        else:
            await _restore(_ref(refs, shown), memory.schedule_offsets.get(shown))

    # Runs again once, when the first data arrives (no snapshot or cache, NEW-03).
    ft.use_effect(opened, [shown is None], cleanup=_cancel_on_unmount)

    @report_errors
    async def jump_after_switch() -> None:
        if not jump:
            return
        try:  # the switch to today has slid in, so its list is built
            await asyncio.wait_for(signals.settled.wait(), SETTLE_S)
        except TimeoutError:
            logger.info("Jump to now: the switch to today did not report back")
        await jump_to_now(asked=True)

    ft.use_effect(jump_after_switch, [jump], cleanup=_cancel_on_unmount)

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
            await jump_to_now(asked=True)
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
                [
                    StatusStrip(auto_refresh=True),
                    NoDataState(
                        conference.problem,
                        on_retry=try_again,
                        retrying=conference.status(info) == "refreshing",
                        identifier="schedule.no_data",
                    ),
                ],
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
                        day_tab(index, day, is_today=day == current)
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
        fab=now_button(on_today=shown == current, on_click=now_pressed)
        if today_slots
        else None,
    )


def _cancel_on_unmount() -> None:
    """The jump effects' cleanup: nothing to undo, but it makes Flet cancel their task.

    Flet cancels an effect's task on unmount only when the effect has a cleanup (F2,
    F39), as the strip's ticks rely on (``ui/scaffold.stop_ticks``). Without one, a jump
    still waiting when the user switches tabs (D-142) would scroll a list that has left
    the page, and its error would reach whatever screen shows then.
    """


def _ref(refs: dict[date, ft.Ref[ft.ListView]], day: date) -> ft.Ref[ft.ListView]:
    """Return the day list's ref, one per day for the screen's life (F38)."""
    return refs.setdefault(day, ft.Ref[ft.ListView]())


async def _jump_to_now(
    list_ref: ft.Ref[ft.ListView],
    slots: tuple[Slot, ...],
    *,
    duration: int,
    ended: asyncio.Event,
) -> Slot | None:
    """Scroll today's list to the current slot (``current_slot_key()``, D-155).

    Returns:
        The slot the list is on: the one it landed on, or the one it was already on
        (no scroll on any try: today's list builds every slot, D-154). None when there
        is no slot or the jump failed.
    """
    key = current_slot_key(slots, clock.now())
    if key is None:
        return None
    if await jump_to_key(list_ref, key, duration=duration, ended=ended) == "failed":
        return None
    return next(slot for slot in slots if slot.key == key)


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
