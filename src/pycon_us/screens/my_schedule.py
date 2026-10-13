"""My schedule (``/my-schedule``): the saved sessions in time order, with their clashes.

The personal agenda (NEW-01, SCHED-07, SCHED-08; ux.md §5.6): a ``SectionHeader`` per
day and gutter slots that hold only saved sessions (D-31), from
``agenda.my_schedule()``. Two saved sessions that overlap both say so, with an icon and
words (D-33), while the clash can still change a plan. What has ended folds away by
``clock.now()``: the days before today into one tile at the top, today's ended sessions
into a tile under today's header (``agenda.fold_ended()``), re-folded every minute
while the screen shows (D-40). A star tap removes the session at once, with Undo (ux.md
§4.4). The Schedule's filters never apply (D-20): a saved open space always shows.

The list memoises its whole path (D-153): day sections given values that stay equal
while nothing in the day changes, rows keyed by session id given views built once per
feed version. A star tap re-renders the day it is in; the other rows skip their bodies.
"""

from collections.abc import Callable, Mapping, Sequence
from datetime import date
from functools import partial
from typing import cast

import flet as ft

from pycon_us import clock
from pycon_us.core.agenda import AgendaDay, fold_ended, my_schedule
from pycon_us.core.models import Session
from pycon_us.core.row_views import SessionView
from pycon_us.core.timefmt import day_heading, time_label, today
from pycon_us.favorites import use_favorites
from pycon_us.prefs import use_prefs
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.state import use_conference
from pycon_us.theme import Tokens, use_tokens
from pycon_us.ui.badges import ToggleFavorite, use_favorite_toggle
from pycon_us.ui.navigation import use_scroll_to_top
from pycon_us.ui.scaffold import AppScaffold, SectionHeader, StatusStrip, use_minute
from pycon_us.ui.session_rows import SessionRow, TimeSlot, use_session_views
from pycon_us.ui.states import EmptyState, NoDataState

SCREEN = "my_schedule"
"""The screen's name in its semantics identifiers (decisions §M)."""

EMPTY = "Nothing saved yet"
EMPTY_BODY = "Tap the star on any session to add it to My schedule. It works offline."
BROWSE = "Browse the schedule"

DROPPED = "None of your saved sessions is in the schedule"
DROPPED_BODY = (
    "The schedule has changed since you saved them. "
    "If it lists them again, they come back here."
)

UNAVAILABLE = "Couldn't open My schedule"
UNAVAILABLE_BODY = (
    "Your saved sessions are still on this device. "
    "Close and reopen the app to see them."
)

ALL_OVER = "All your saved sessions are over"
SEE_TODAY = "See what's on today"
CONFERENCE_OVER = "{name} is over. Your saved sessions stay here."

EXPAND_MS = 200
"""A fold tile's expand and collapse (Flutter's default), 0 under reduced motion."""


@ft.component
def MySchedule() -> ft.View:
    """The My schedule root: the status strip, then the agenda or the state it is in."""
    list_ref, scroll_to_top = use_scroll_to_top()
    page = ft.context.page
    svc = use_services()
    conference = use_conference()
    favorites = use_favorites()
    on_toggle = use_favorite_toggle(favorites)
    tokens = use_tokens()
    prefs = use_prefs()
    use_minute()  # the fold follows the clock
    earlier_days_open, set_earlier_days_open = ft.use_state(False)
    # The date whose "Earlier today" is open, so the next day's tile starts collapsed.
    earlier_today_open, set_earlier_today_open = ft.use_state(cast(date | None, None))
    info = svc.year.conference
    use_24h = bool(page.media and page.media.always_use_24_hour_format)
    data = conference.data
    saved = favorites.ids
    agenda = ft.use_memo(
        lambda: my_schedule(data, saved) if data else None,
        [conference.version, saved],
    )
    # Every session's view, not only the saved ones': the views then stay the same
    # objects when a star tap changes the saved set, so the other rows skip (D-153).
    views = use_session_views(
        conference, tuple(data.sessions) if data else (), use_24h=use_24h
    )
    by_id = ft.use_memo(lambda: {view.session.id: view for view in views}, [views])

    @report_errors
    async def refresh() -> None:
        await conference.refresh(svc.storage, svc.year, closed=svc.closed)

    @report_errors
    def browse() -> None:
        page.navigate("/schedule")

    @report_errors
    def see_today() -> None:
        page.navigate("/now")

    content: list[ft.Control]
    if not favorites.loaded:  # the read failed: not the same as nothing saved (D-172)
        content = [
            EmptyState(
                UNAVAILABLE,
                icon=ft.Icons.ERROR_OUTLINE,
                body=UNAVAILABLE_BODY,  # no button can help: only a relaunch does
                identifier=f"{SCREEN}.unavailable",
            )
        ]
    elif agenda is None or data is None:
        content = [
            NoDataState(
                conference.problem,
                on_retry=refresh,
                retrying=conference.status(info) == "refreshing",
                identifier=f"{SCREEN}.no_data",
            )
        ]
    elif not agenda.days and saved:  # saved, but no longer in the feed (D-172)
        content = [
            EmptyState(
                DROPPED,
                icon=ft.Icons.EVENT_BUSY_OUTLINED,
                body=DROPPED_BODY,
                action=BROWSE,
                on_action=browse,
                identifier=f"{SCREEN}.dropped",
            )
        ]
    elif not agenda.days:
        content = [
            EmptyState(
                EMPTY,
                icon=ft.Icons.STAR_BORDER,
                body=EMPTY_BODY,
                action=BROWSE,
                on_action=browse,
                identifier=f"{SCREEN}.empty",
            )
        ]
    else:
        day = partial(
            _day, views=by_id, on_toggle=on_toggle, tokens=tokens, use_24h=use_24h
        )
        expand = _expand_style(prefs.motion_ms(EXPAND_MS))
        now = clock.now()
        folded = fold_ended(agenda, now, info.zone)
        content = []
        if not folded.ahead:
            if today(now, info.zone) <= data.days[-1].date:  # Now has a day to show
                content.append(_all_over(see_today))
            else:
                content.append(_all_over(body=CONFERENCE_OVER.format(name=info.name)))
        if folded.earlier_days:
            inside: list[ft.Control] = []
            for earlier in folded.earlier_days:
                # Folded rows carry no clash line: it can no longer change a plan.
                inside += [SectionHeader(day_heading(earlier.day)), day(earlier, {})]
            content.append(
                _fold(
                    f"Earlier days ({_sessions(folded.earlier_days)})",
                    inside,
                    expanded=earlier_days_open,
                    on_change=set_earlier_days_open,
                    style=expand,
                    identifier=f"{SCREEN}.earlier_days",
                )
            )
        ended = folded.earlier_today
        ahead = list(folded.ahead)
        if ended is not None:

            @report_errors
            def set_open(is_open: bool, shown: date = ended.day) -> None:
                set_earlier_today_open(shown if is_open else None)

            # Today's header, its ended sessions folded, then the rest of today.
            content += [
                SectionHeader(day_heading(ended.day)),
                _fold(
                    f"Earlier today ({_sessions([ended])})",
                    [day(ended, {}, "ended")],
                    expanded=earlier_today_open == ended.day,
                    on_change=set_open,
                    style=expand,
                    identifier=f"{SCREEN}.earlier_today",
                ),
            ]
            if ahead and ahead[0].day == ended.day:
                content.append(day(ahead.pop(0), folded.overlaps))
        for later in ahead:
            content += [
                SectionHeader(day_heading(later.day)),
                day(later, folded.overlaps),
            ]
    return AppScaffold(
        title="My schedule",
        body=ft.ListView(
            [StatusStrip(), *content],
            expand=True,
            ref=list_ref,
            padding=ft.Padding.only(bottom=16),
        ),
        on_retap=scroll_to_top,
    )


def _all_over(
    on_see_today: Callable[[], None] | None = None, *, body: str | None = None
) -> ft.Control:
    """Return the notice that heads the list when every saved session has ended.

    Compact and start-aligned, its text on the fold tile's text column, rather than
    the full-screen empty state: the "Earlier days" tile under it is still content and
    should not be pushed to the middle of the screen (ux.md §5.6).

    Args:
        on_see_today: What "See what's on today" does, while today is a conference
            day; None after the conference, when Now has nothing on today.
        body: A second line, after the conference.
    """
    texts: list[ft.Control] = [
        ft.Semantics(  # a container of its own, as EmptyState's title (D-182)
            header=True,
            container=True,
            content=ft.Text(ALL_OVER, theme_style=ft.TextThemeStyle.TITLE_SMALL),
        )
    ]
    if body is not None:
        texts.append(
            ft.Text(
                body,
                theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                color=ft.Colors.ON_SURFACE_VARIANT,
            )
        )
    column: list[ft.Control] = [
        ft.Semantics(
            identifier=f"{SCREEN}.all_over",
            container=True,
            live_region=True,
            content=ft.Column(texts, spacing=4),
        )
    ]
    if on_see_today is not None:
        column.append(ft.FilledTonalButton(SEE_TODAY, on_click=on_see_today))
    return ft.Container(
        ft.Row(
            [
                ft.Icon(
                    ft.Icons.EVENT_AVAILABLE_OUTLINED,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                ),
                ft.Column(column, spacing=12, expand=True),
            ],
            spacing=16,  # the text on the fold tile's text column, 56 dp in
            vertical_alignment=ft.CrossAxisAlignment.START,
        ),
        padding=ft.Padding.only(left=16, top=16, right=16, bottom=8),
    )


def _day(
    day: AgendaDay,
    overlaps: Mapping[Session, tuple[Session, ...]],
    part: str = "to_come",
    *,
    views: Mapping[str, SessionView],
    on_toggle: ToggleFavorite,
    tokens: Tokens,
    use_24h: bool,
) -> ft.Control:
    """Return ``day``'s slots as a memoised ``_Day``, keyed by the day and the part.

    Args:
        day: The day, or the part of today that has ended or is to come.
        overlaps: The clashes still to come (``FoldedAgenda.overlaps``); empty for a
            folded day.
        part: Which part of the day it is, so today's two parts keep their own
            component when the fold moves a session from one to the other.
        views: Every session's row view, by id.
        on_toggle: The list's one star handler.
        tokens: The scheme's tokens (D-150).
        use_24h: Whether the device uses the 24-hour clock.
    """
    # Only the day's own names: a clash elsewhere leaves this day's props equal.
    notes = {
        session.id: tuple(other.name for other in overlaps[session])
        for slot in day.slots
        for session in slot.sessions
        if session in overlaps
    }
    # As SessionRow: ft.component's typing leaves out the key= its wrapper takes.
    return _Day(
        day,
        views,
        notes,
        on_toggle,
        tokens,
        use_24h,
        key=f"{day.day.isoformat()}-{part}",  # pyright: ignore[reportCallIssue]
    )


@ft.memo
@ft.component
def _Day(
    day: AgendaDay,
    views: Mapping[str, SessionView],
    notes: Mapping[str, tuple[str, ...]],
    on_toggle: ToggleFavorite,
    tokens: Tokens,
    use_24h: bool,
) -> ft.Control:
    """A day's slots: each start's ``TimeGutter`` beside its saved sessions (D-31).

    Memoised (D-153): it runs only when the day's slots, their clashes, the clock
    format or the scheme change. Every row is saved, so every star is filled; a tap
    removes the row, with Undo.
    """
    zone = use_services().year.conference.zone  # a plain value: subscribes to nothing
    slots: list[ft.Control] = []
    for index, slot in enumerate(day.slots):
        # No lookup can miss: the views cover every session of the feed version the
        # agenda comes from (both memos key on ``conference.version``).
        rows = [
            SessionRow(
                views[session.id],
                True,
                on_toggle,
                tokens,
                screen=SCREEN,
                overlaps=notes.get(session.id, ()),
            )
            for session in slot.sessions
        ]
        label = time_label(slot.start, zone, use_24h=use_24h)
        slots.append(TimeSlot(label, rows, divider=index > 0))
    return ft.Column(slots, spacing=0)


def _fold(
    title: str,
    controls: list[ft.Control],
    *,
    expanded: bool,
    on_change: Callable[[bool], None],
    style: ft.AnimationStyle,
    identifier: str,
) -> ft.Control:
    """Return a tile that folds what has ended away: collapsed until it is tapped.

    Controlled (as D-157 asks of text fields): Flutter reports the new state, the
    screen keeps it, and its next render passes it back. Left to Flutter, the next
    render would send the default and collapse a tile the user had just opened.

    Args:
        title: "Earlier days (6 sessions)".
        controls: What it holds when expanded.
        expanded: Whether it is open.
        on_change: Where the screen keeps whether it is open.
        style: Its expand and collapse animation.
        identifier: Its semantics identifier, merged into the tile's own node.
    """

    @report_errors
    def changed(e: ft.Event[ft.ExpansionTile]) -> None:
        on_change(bool(e.data))

    return ft.ExpansionTile(
        # Quieter than the day header above it: a fold of what is over (ux.md §5.6).
        title=ft.Semantics(
            identifier=identifier,
            content=ft.Text(
                title,
                theme_style=ft.TextThemeStyle.BODY_MEDIUM,
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
        ),
        leading=ft.Icon(ft.Icons.HISTORY, color=ft.Colors.ON_SURFACE_VARIANT),
        controls=controls,
        expanded=expanded,
        on_change=changed,
        animation_style=style,
        expanded_cross_axis_alignment=ft.CrossAxisAlignment.STRETCH,
        # Open, a tonal fill sets what has ended apart from what is still to come
        # (today's ended 9:30 workshop sits above the 9:00 tutorial that is still on),
        # in place of the default lines above and below.
        bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
        shape=ft.RoundedRectangleBorder(),
        collapsed_shape=ft.RoundedRectangleBorder(),
    )


def _expand_style(ms: int) -> ft.AnimationStyle:
    """Return a fold tile's animation: ``ms`` long, none under reduced motion (D-173)."""
    if not ms:
        return ft.AnimationStyle.no_animation()
    duration = ft.Duration(milliseconds=ms)
    return ft.AnimationStyle(duration=duration, reverse_duration=duration)


def _sessions(days: Sequence[AgendaDay]) -> str:
    """Return how many sessions some days hold: "1 session", "6 sessions".

    A no-break space keeps the count on its noun's line when the title wraps.
    """
    count = sum(len(slot.sessions) for day in days for slot in day.slots)
    noun = "session" if count == 1 else "sessions"
    return f"{count}\N{NO-BREAK SPACE}{noun}"
