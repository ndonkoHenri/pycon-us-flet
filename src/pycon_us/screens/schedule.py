"""Schedule (``/schedule``): a stub that shows what the start sequence published.

Until P1's day tabs (SCHED-01..04), it shows the status strip, where the feed came from
and when, a Refresh button, every conference day with its session count, and a few
sessions as ``SessionRow``s with their stars, so "bundled first, a refresh replaces it"
is visible on a phone (DATA-35, D-38) and the star works from a tab root. Without any
data (no snapshot or cache, NEW-03) it shows the skeleton until the first fetch has
failed, then "Can't load the schedule", which stays during a retry (D-32, ux.md §4.1).
"""

from collections.abc import Iterator
from datetime import date, tzinfo
from itertools import islice

import flet as ft

from pycon_us.core.models import ConferenceData, Session
from pycon_us.core.queries import days
from pycon_us.core.row_views import by_day
from pycon_us.core.timefmt import day_label, local_date, time_label
from pycon_us.favorites import use_favorites
from pycon_us.screens.stub import note, stub_body
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.state import Conference, Problem, use_conference
from pycon_us.theme import use_tokens
from pycon_us.ui.badges import use_favorite_toggle
from pycon_us.ui.navigation import use_scroll_to_top
from pycon_us.ui.scaffold import AppScaffold, SectionHeader, search_button
from pycon_us.ui.session_rows import SessionRow, use_session_views
from pycon_us.ui.states import EmptyState, SkeletonList

SOURCE_LABELS = {
    "none": "No schedule yet",
    "bundled": "Schedule bundled with the app",
    "cache": "Schedule saved on this device",
    "network": "Schedule downloaded",
}

NO_DATA_BODY: dict[Problem, str] = {
    "offline": "Connect to the internet and try again.",
    "server": "The schedule couldn't be read. Try again in a few minutes.",
}
"""The way out after a failed first fetch, by why it failed (D-146, ux.md §4.6)."""

SAMPLE_SIZE = 5
"""How many sessions with speakers the stub shows, for the drill and the star."""

SCREEN = "schedule"
"""The screen's name in its rows' semantics identifiers (decisions §M)."""


@ft.component
def Schedule() -> ft.View:
    """The Schedule root: the data's status, source and age, its days and a few sessions."""
    list_ref, scroll_to_top = use_scroll_to_top()
    page = ft.context.page
    svc = use_services()
    conference = use_conference()
    favorites = use_favorites()
    on_toggle = use_favorite_toggle(favorites)
    tokens = use_tokens()

    @report_errors
    async def refresh() -> None:
        await conference.refresh(svc.storage, svc.year, closed=svc.closed)

    info = svc.year.conference
    # As the strip's Refresh: enabled during a quiet refresh, so a tap joins it (D-181).
    asked = conference.status(info) == "refreshing"
    use_24h = bool(page.media and page.media.always_use_24_hour_format)
    data = conference.data
    counts = _session_counts(data)
    samples = [s.id for s in islice(_with_speakers(data), SAMPLE_SIZE)]
    views = use_session_views(conference, samples, use_24h=use_24h)
    samples_by_day: list[ft.Control] = []
    # A row says only its time: its day is the heading above it.
    for day, day_views in by_day(views, info.zone):
        samples_by_day.append(
            SectionHeader(f"Sessions with speakers, {day_label(day)}")
        )
        samples_by_day.extend(
            SessionRow(
                view, view.session.id in favorites.ids, on_toggle, tokens, screen=SCREEN
            )
            for view in day_views
        )
    rows: list[ft.Control]
    if data is None and conference.problem is None:
        rows = [SkeletonList()]  # the first fetch runs, or is about to (NEW-03)
    elif data is None:
        rows = [
            EmptyState(
                "Can't load the schedule",
                icon=ft.Icons.CLOUD_OFF_OUTLINED,
                body=NO_DATA_BODY[conference.problem or "offline"],
                action="Try again",
                on_action=refresh,
                # A retry keeps the state in place, so a screen reader's focus stays
                # on the button; the strip's bar shows the work.
                disabled=asked,
                identifier="schedule.no_data",
            )
        ]
    else:
        rows = [
            ft.Semantics(  # the shell smoke flow finds it (testing §5.4)
                identifier="schedule.source",
                content=note(SOURCE_LABELS[conference.source]),
            ),
            note(_fetched(conference, info.zone, use_24h)),
            ft.Container(
                ft.FilledTonalButton(
                    "Refresh",
                    icon=ft.Icons.REFRESH,
                    on_click=refresh,
                    disabled=asked,
                ),
                padding=ft.Padding.symmetric(horizontal=16, vertical=8),
            ),
            SectionHeader("Days"),
            *(
                ft.ListTile(
                    title=day_label(day), subtitle=f"{counts.get(day, 0)} sessions"
                )
                for day in days(data, info.first_day, info.last_day)
            ),
            *samples_by_day,
        ]
    return AppScaffold(
        title="Schedule",
        actions=[search_button(svc.memory, "sessions")],
        body=stub_body(
            rows,
            status=True,
            auto_refresh=True,
            ref=list_ref,
        ),
        on_retap=scroll_to_top,
    )


def _fetched(conference: Conference, zone: tzinfo, use_24h: bool) -> str:
    if conference.fetched_at is None:
        return "Never fetched"
    day = day_label(local_date(conference.fetched_at, zone))
    return f"Fetched {day}, {time_label(conference.fetched_at, zone, use_24h=use_24h)}"


def _session_counts(data: ConferenceData | None) -> dict[date, int]:
    if data is None:
        return {}
    return {day.date: sum(len(g.session_ids) for g in day.groups) for day in data.days}


def _with_speakers(data: ConferenceData | None) -> Iterator[Session]:
    """Yield the timeline's sessions that have speakers in the directory, in order."""
    if data is None:
        return
    for day in data.days:
        for group in day.groups:
            for session_id in group.session_ids:
                session = data.sessions[session_id]
                if session.speaker_ids:
                    yield session
