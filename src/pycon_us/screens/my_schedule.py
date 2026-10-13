"""My schedule (``/my-schedule``): the saved sessions in time order, with their clashes.

The personal agenda (NEW-01, SCHED-07, SCHED-08; ux.md §5.6): a ``SectionHeader`` per
day and gutter slots that hold only saved sessions (D-31), from
``agenda.my_schedule()``. Two saved sessions that overlap both say so, with an icon and
words (D-33). What has ended folds away by ``clock.now()``: the days before today into
one tile at the top, today's ended sessions into a tile under today's header
(``agenda.fold_ended()``), re-folded every minute while the screen shows (D-40). A
star tap removes the session at once, with Undo (ux.md §4.4). The Schedule's filters
never apply (D-20): a saved open space always shows.

The list memoises its whole path (D-153): day sections given values that stay equal
while nothing in the day changes, rows keyed by session id given views built once per
feed version. A star tap re-renders the day it is in; the other rows skip their bodies.
"""

from collections.abc import Callable, Mapping, Sequence
from functools import partial

import flet as ft

from pycon_us import clock
from pycon_us.core.agenda import AgendaDay, fold_ended, my_schedule
from pycon_us.core.models import Session
from pycon_us.core.row_views import SessionView
from pycon_us.core.timefmt import day_heading, time_label
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

UNAVAILABLE = "Couldn't open My schedule"
UNAVAILABLE_BODY = (
    "Your saved sessions are still on this device. "
    "Close and reopen the app to see them."
)

ALL_OVER = "All your saved sessions are over"
SEE_TODAY = "See what's on today"

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
    earlier_today_open, set_earlier_today_open = ft.use_state(False)
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
    elif agenda is None:
        content = [
            NoDataState(
                conference.problem,
                on_retry=refresh,
                retrying=conference.status(info) == "refreshing",
                identifier=f"{SCREEN}.no_data",
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
            _day,
            views=by_id,
            overlaps=agenda.overlaps,
            on_toggle=on_toggle,
            tokens=tokens,
            use_24h=use_24h,
        )
        expand = _expand_style(prefs.motion_ms(EXPAND_MS))
        folded = fold_ended(agenda, clock.now(), info.zone)
        content = []
        if not folded.ahead:
            content.append(
                EmptyState(
                    ALL_OVER,
                    icon=ft.Icons.EVENT_AVAILABLE_OUTLINED,
                    action=SEE_TODAY,
                    on_action=see_today,
                    identifier=f"{SCREEN}.all_over",
                )
            )
        if folded.earlier_days:
            inside: list[ft.Control] = []
            for earlier in folded.earlier_days:
                inside += [SectionHeader(day_heading(earlier.day)), day(earlier)]
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
        today = folded.earlier_today
        ahead = list(folded.ahead)
        if today is not None:
            # Today's header, its ended sessions folded, then the rest of today.
            content += [
                SectionHeader(day_heading(today.day)),
                _fold(
                    f"Earlier today ({_sessions([today])})",
                    [day(today, "ended")],
                    expanded=earlier_today_open,
                    on_change=set_earlier_today_open,
                    style=expand,
                    identifier=f"{SCREEN}.earlier_today",
                ),
            ]
            if ahead and ahead[0].day == today.day:
                content.append(day(ahead.pop(0)))
        for later in ahead:
            content += [SectionHeader(day_heading(later.day)), day(later)]
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


def overlap_note(others: Sequence[Session]) -> str:
    """Return a row's overlap line: "Overlaps with “Typing deep dive”" (ux.md §5.6).

    One clash is named, two are both named, more name the first and count the rest,
    so the line stays short; each row of a clash says it, so the rest are named on
    their own rows.

    Args:
        others: The saved sessions the row overlaps, in agenda order (``Agenda.overlaps``).
    """
    names = [f"“{session.name}”" for session in others]
    if len(names) == 1:
        return f"Overlaps with {names[0]}"
    if len(names) == 2:
        return f"Overlaps with {names[0]} and {names[1]}"
    return f"Overlaps with {names[0]} and {len(names) - 1} more"


def _day(
    day: AgendaDay,
    part: str = "to_come",
    *,
    views: Mapping[str, SessionView],
    overlaps: Mapping[Session, tuple[Session, ...]],
    on_toggle: ToggleFavorite,
    tokens: Tokens,
    use_24h: bool,
) -> ft.Control:
    """Return ``day``'s slots as a memoised ``_Day``, keyed by the day and the part.

    Args:
        day: The day, or the part of today that has ended or is to come.
        part: Which part of the day it is, so today's two parts keep their own
            component when the fold moves a session from one to the other.
        views: Every session's row view, by id.
        overlaps: ``Agenda.overlaps``.
        on_toggle: The list's one star handler.
        tokens: The scheme's tokens (D-150).
        use_24h: Whether the device uses the 24-hour clock.
    """
    # Only the day's own lines: a clash elsewhere leaves this day's props equal.
    notes = {
        session.id: overlap_note(overlaps[session])
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
    notes: Mapping[str, str],
    on_toggle: ToggleFavorite,
    tokens: Tokens,
    use_24h: bool,
) -> ft.Control:
    """A day's slots: each start's ``TimeGutter`` beside its saved sessions (D-31).

    Memoised (D-153): it runs only when the day's slots, their overlap lines, the clock
    format or the scheme change. Every row is saved, so every star is filled; a tap
    removes the row, with Undo.
    """
    zone = use_services().year.conference.zone  # a plain value: subscribes to nothing
    slots: list[ft.Control] = []
    for index, slot in enumerate(day.slots):
        rows = [
            SessionRow(
                views[session.id],
                True,
                on_toggle,
                tokens,
                screen=SCREEN,
                overlap=notes.get(session.id, ""),
            )
            for session in slot.sessions
            if session.id in views
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
        title=ft.Semantics(identifier=identifier, content=ft.Text(title)),
        leading=ft.Icon(ft.Icons.HISTORY, color=ft.Colors.ON_SURFACE_VARIANT),
        controls=controls,
        expanded=expanded,
        on_change=changed,
        animation_style=style,
        expanded_cross_axis_alignment=ft.CrossAxisAlignment.STRETCH,
        # No lines above and below when open: the day headers inside separate it.
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
    """Return how many sessions some days hold: "1 session", "6 sessions"."""
    count = sum(len(slot.sessions) for day in days for slot in day.slots)
    return "1 session" if count == 1 else f"{count} sessions"
