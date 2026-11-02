"""Schedule (``/schedule``): the programme by day and time slot (SCHED-01, SCHED-02).

Day tabs over swipeable day lists (D-31): an ``ft.Tabs`` whose content starts with its
``TabBar`` (no ``AppBar.bottom``, U10), then the head (the filter summary, the status
strip and "Times are Pacific Time (PDT)" while the device's clock differs from the
conference's, D-20, D-32, D-240), then a ``TabBarView`` with one page per conference
day, sprint days included. At the largest text sizes the head tops each day's list
instead, so it scrolls away (``screens/schedule_head.py``, D-345). The tabs, the pages and the "Now" button come from ``screens/schedule_days.py``: each page
is a ``DayList`` of ``SlotItem``s, memoised down to the rows (D-153). The first render
fills only the shown day, the second the others (D-156).

The day opens on today during the conference, else on the first day; the day picked and
each list's offset live in ``ViewMemory``, so a tab return or a new session finds them
(D-18); a text-size or filter change puts each list back on the item at its top, by key
(D-331, D-371, ``screens/schedule_place.py``); what the day lists hold, and their
put-back, are ``screens/schedule_slots.py``'s. A detail pushed over the Schedule keeps
it mounted, and so its place.

Jump to now (D-155, D-204) lands on the slot that is on, else on today's now line
(``now_place()``): by itself on the first display of each today in the process, be it
when the Schedule opens or when the user swipes to today, and again with the "Now"
button, which switches to today first when another day shows, and tells a screen reader
where it landed: VoiceOver through an announcement, TalkBack through a live region
(``landing_note()``, D-241). The button hides while the list is near where a jump left
it, and while today's first jump is on its way; a screen reader keeps it (D-204). A
minute tick (``use_minute()``) keeps today's dot, the button and the now line with the
clock; the day shown stays put across midnight. Without any data (no snapshot or
cache, NEW-03) the screen shows the skeleton until the first fetch has failed, then
"Can't load the schedule", which stays during a retry (D-32, ux.md §4.1).
"""

import asyncio
import logging
from datetime import date
from typing import cast

import flet as ft

from pycon_us import clock
from pycon_us.core.queries import days
from pycon_us.core.timefmt import day_heading, time_label, today, zone_note
from pycon_us.core.timeline import now_place
from pycon_us.favorites import use_favorites
from pycon_us.prefs import use_prefs
from pycon_us.screens.changes_review import ScheduleOverflow
from pycon_us.screens.schedule_days import SCREEN, DayList, now_button
from pycon_us.screens.schedule_filter import use_track_filter
from pycon_us.screens.schedule_head import Head, ScheduleHead
from pycon_us.screens.schedule_layout import layout_probe
from pycon_us.screens.schedule_now import (
    PENDING,
    SAID_S,
    InView,
    Landing,
    NowMark,
    Signals,
    jumps_by_itself,
    landing_note,
    shows_now,
    spoken_place,
)
from pycon_us.screens.schedule_place import PlaceKeeper
from pycon_us.screens.schedule_slots import (
    default_day,
    empty_reason,
    filter_tracks,
    list_ref,
    slot_keys,
    use_day_slots,
    use_put_back,
)
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.services.pref_keys import THEME
from pycon_us.services.storage import SERVICE_ERRORS
from pycon_us.state import use_conference
from pycon_us.theme import use_tokens
from pycon_us.ui.day_tabs import TAB_MS, day_tab
from pycon_us.ui.favorite import use_favorite_toggle
from pycon_us.ui.navigation import RETAP_SCROLL_MS
from pycon_us.ui.scaffold import AppScaffold, search_button
from pycon_us.ui.scrolling import JUMP_MS, jump_to_key
from pycon_us.ui.session_rows import changes_of, use_recent_changes, use_session_views
from pycon_us.ui.states import NoDataState
from pycon_us.ui.status_strip import strip_view, use_minute, use_strip
from pycon_us.ui.widths import LIST, capped, sides, use_margin

logger = logging.getLogger(__name__)

SETTLE_S = 1.0
"""How long the "Now" button waits for the switch to today to settle, in seconds."""


@ft.component
def Schedule() -> ft.View:
    """The Schedule root: day tabs, the status strip and one slot list per day."""
    page = ft.context.page
    svc = use_services()
    margin = use_margin(LIST)  # its width class (D-305)
    memory = svc.memory
    conference = use_conference()
    favorites = use_favorites()
    prefs = use_prefs()
    on_toggle = use_favorite_toggle(favorites)
    tokens = use_tokens()
    info = svc.year.conference
    use_24h = bool(page.media and page.media.always_use_24_hour_format)
    data = conference.data
    use_minute()  # today, its now line and the button follow the clock (D-204)
    # The strip's state is the screen's: at the largest sizes the memoised day lists
    # show it, and only a value may go there (F150, D-345).
    strip = use_strip(auto_refresh=True)
    now = clock.now()  # the Developer fake clock moves it (D-43)
    current = today(now, info.zone)
    all_days = days(data, info.first_day, info.last_day) if data else ()
    picked, set_picked = ft.use_state(memory.schedule_day)
    # The default day is pinned at the first display, so midnight never moves it.
    opened_on = ft.use_memo(lambda: current, [data is None])
    shown = picked if picked in all_days else default_day(all_days, opened_on)
    rest, set_rest = ft.use_state(False)  # the other days are rendered (D-156)
    jump, set_jump = ft.use_state(0)  # a "Now" tap from another day's tab
    in_view, set_in_view = ft.use_state(cast(InView, PENDING))  # opened() settles it
    said, set_said = ft.use_state("")  # where an asked jump landed, for TalkBack
    refs = ft.use_memo(dict[date, ft.Ref[ft.ListView]], [])
    signals = ft.use_memo(Signals, [])
    keeper = ft.use_memo(lambda: PlaceKeeper(memory), [])
    _, set_relaid = ft.use_state(0)  # a list built in full for its put-back (D-331)

    @report_errors
    def relay() -> None:
        set_relaid(lambda n: n + 1)  # a list built in full is built lazy again

    excluded = prefs.excluded_tracks
    day_slots = use_day_slots(data, all_days, excluded, conference.version)
    slots, day_ids = day_slots.slots, day_slots.ids
    ids = tuple(data.sessions) if data else ()
    views = use_session_views(conference, ids, use_24h=use_24h)
    by_id = ft.use_memo(lambda: {v.session.id: v for v in views}, [views])
    changes = use_recent_changes()
    today_slots = slots.get(current, ())
    place = now_place(today_slots, now) if today_slots else None
    keeper.lay_out(
        conference.version,
        excluded,
        slot_keys(slots, current, place, head=prefs.time_above),
        day_slots.by_key,
    )
    tracks = ft.use_memo(lambda: filter_tracks(data, all_days), [conference.version])
    count = sum(
        len(slot.sessions) for day_slots in slots.values() for slot in day_slots
    )
    track_filter = use_track_filter(info, tracks, count)  # the filter sheet (D-20)

    @report_errors
    async def jump_to_now(*, asked: bool) -> None:
        if not today_slots:
            return
        memory.jumped_on = current  # asked or not, today's jump is done (D-18, D-204)
        keeper.supersede(current)  # a jump that moves records the new place (D-331)
        if asked:
            set_said("")  # the same words again are a change only after a silence
        else:
            signals.landing = None
            set_in_view(PENDING)
        # The clock's place: the landing's render lays the line out at it too.
        at = clock.now()
        target = now_place(today_slots, at)
        ended = await jump_to_key(
            list_ref(refs, current),
            target.target,
            duration=prefs.motion_ms(JUMP_MS),
            ended=signals.ended,
        )
        if ended == "failed":
            set_in_view(None)
            return
        # "landed" recorded the offset at its scroll end; "still" left it as it was.
        pixels = memory.schedule_offsets.get(current, 0.0)
        landing = Landing(current, target, conference.version, excluded, pixels)
        signals.landing = landing
        set_in_view(landing)
        # The user's own tap: a screen reader hears where the list went, since the
        # tab switch and the scroll are silent. The first display's jump is not asked.
        if not (asked and prefs.screen_reader):
            return
        where = spoken_place(target, today_slots, at, info.zone, use_24h=use_24h)
        words = f"{day_heading(current)}, {where}"
        if not prefs.announcements:  # Android: Flutter reports none there (F13, D-241)
            set_said(words)
            return
        try:
            await svc.semantics.announce_message(words)
        except SERVICE_ERRORS:  # the list is in place; a lost phrase is no error
            logger.warning("Could not announce the jump", exc_info=True)

    @report_errors
    async def fade() -> None:
        if said:  # TalkBack has read it by then; empty, the note is no stop (D-241)
            await asyncio.sleep(SAID_S)
            set_said("")

    # A new landing restarts the wait: Flet cancels the previous run on a change.
    ft.use_effect(fade, [said])

    @report_errors
    async def opened() -> None:
        if shown is None:  # no data yet: the first display is the render that has it
            return
        jumps = jumps_by_itself(shown, current, today_slots, memory)
        if not jumps:
            set_in_view(None)
        # A round trip: Flutter has applied the first render's patch (D-155, D-156).
        await svc.storage.get(THEME)
        set_rest(True)
        if jumps:
            await jump_to_now(asked=False)
        elif await keeper.restore(shown, list_ref(refs, shown), signals.ended):
            relay()

    # Runs again once, when the first data arrives (no snapshot or cache, NEW-03).
    ft.use_effect(opened, [shown is None])

    @report_errors
    async def jump_after_switch() -> None:
        if not jump:
            return
        try:  # the switch to today has slid in, so its list is built
            await asyncio.wait_for(signals.settled.wait(), SETTLE_S)
        except TimeoutError:
            logger.info("Jump to now: the switch to today did not report back")
        await jump_to_now(asked=True)

    # A jump still waiting when the user switches tabs (D-142) is cancelled with the
    # screen (F2), so it never scrolls a list that has left the page.
    ft.use_effect(jump_after_switch, [jump])

    @report_errors
    async def changed(e: ft.Event[ft.Tabs]) -> None:
        signals.settled.set()
        day = all_days[e.control.selected_index]
        if day == shown:  # the echo of a switch made from Python
            return
        memory.schedule_day = day
        set_picked(day)
        if jumps_by_itself(day, current, today_slots, memory):  # opened elsewhere
            await jump_to_now(asked=False)
        elif await keeper.restore(day, list_ref(refs, day), signals.ended):
            relay()

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
        target = list_ref(refs, shown).current if shown else None
        if target is not None:
            await target.scroll_to(offset=0, duration=prefs.motion_ms(RETAP_SCROLL_MS))

    # A text-size, width, time-position or filter change puts the list back (D-331).
    text_measured, width_measured = use_put_back(
        keeper,
        shown,
        refs,
        signals.ended,
        relay,
        time_above=prefs.time_above,
        excluded=excluded,
    )

    on_measure = ft.use_callback(keeper.measured, [])

    @report_errors
    def scrolled(day: date, e: ft.OnScrollEvent) -> None:
        keeper.scrolled(day, e)
        if e.event_type != ft.ScrollType.END:
            return
        memory.schedule_offsets[day] = e.pixels
        signals.ended.set()
        landing = signals.landing
        if landing is not None and landing.day == day:
            set_in_view(
                landing if landing.near(e.pixels, e.viewport_dimension) else None
            )

    on_scroll = ft.use_callback(scrolled, [])

    @report_errors
    async def try_again() -> None:
        await conference.refresh(svc.storage, svc.year, closed=svc.closed)

    if data is None or shown is None:
        return AppScaffold(
            title="Schedule",
            source=None,  # in its overflow
            actions=[
                search_button(memory, "sessions"),
                ScheduleOverflow(source=__name__),
            ],
            body=ft.ListView(
                [
                    strip_view(strip, tokens),
                    NoDataState(
                        conference.problem,
                        on_retry=try_again,
                        retrying=conference.status(info) == "refreshing",
                        identifier="schedule.no_data",
                    ),
                ],
                expand=True,
                padding=sides(margin),
            ),
        )

    head = Head(
        track_filter.summary,
        # The device's offset now: the packaged app's Python reads the device's
        # zone (F60), and the minute tick follows a DST change.
        zone_note(now, info.zone, info.time_zone_name, now.astimezone().utcoffset()),
        strip,
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
                changes_of(changes, day_ids[day]),  # and its changes (D-315)
                on_toggle,
                tokens,
                use_24h=use_24h,
                time_above=prefs.time_above,
                # The one list a jump targets (D-154), and a list waiting to be put
                # back by key after a text-size or filter change (D-331, D-371).
                full=day == current or keeper.pending(day) is not None,
                clearance=bool(today_slots),
                empty=empty_reason(data, day, slots[day]),
                now=NowMark(place.line, time_label(now, info.zone, use_24h=use_24h))
                if day == current and place is not None
                else None,
                # At the largest sizes it scrolls away with the slots (D-345).
                head=head if prefs.time_above else None,
                list_ref=list_ref(refs, day),
                on_scroll=on_scroll,
                on_measure=on_measure,
                on_clear_filters=track_filter.show_all,
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
                # First, so Flutter reports it before the lists' items (D-331).
                layout_probe(text_measured, width_measured),
                # The fixed chrome keeps to the list's width (D-305).
                capped(
                    ft.TabBar(
                        [
                            day_tab(index, day, is_today=day == current, screen=SCREEN)
                            for index, day in enumerate(all_days)
                        ],
                        # One-line labels in a scrollable bar: seven days fit no
                        # phone, and the bar's fixed height clips a second line at
                        # 200 % (S2).
                        scrollable=True,
                        tab_alignment=ft.TabAlignment.START,
                    ),
                    margin,
                ),
                # At the largest sizes the head is in the lists; a placeholder keeps
                # the day pages' place in the column (#313).
                ft.Container()
                if prefs.time_above
                else capped(ScheduleHead(head, track_filter.show_all, tokens), margin),
                ft.Stack(
                    [landing_note(said), ft.TabBarView(pages)],
                    fit=ft.StackFit.EXPAND,
                    expand=True,
                ),
            ],
            spacing=0,
            expand=True,
        ),
    )
    # A screen reader keeps the button, so a tap never removes the focused control.
    at_now = (
        not prefs.screen_reader
        and shown == current
        and shows_now(in_view, current, place, conference.version, excluded)
    )
    return AppScaffold(
        title="Schedule",
        source=None,  # in its overflow
        actions=[
            search_button(memory, "sessions"),
            track_filter.button,
            ScheduleOverflow(source=__name__),  # Schedule changes (D-255)
        ],
        body=tabs,
        on_retap=scroll_to_top,
        fab=now_button(on_today=shown == current, on_click=now_pressed, margin=margin)
        if today_slots and not at_now
        else None,
    )
