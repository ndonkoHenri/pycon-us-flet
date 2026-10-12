"""Schedule (``/schedule``): a stub that shows what the start sequence published.

Until P1's day tabs (SCHED-01..04), it shows the status strip, where the feed came from
and when, a Refresh button, every conference day with its session count, and a few
sessions to open, so "bundled first, a refresh replaces it" is visible on a phone
(DATA-35, D-38).
"""

from collections.abc import Iterator
from datetime import date, tzinfo
from itertools import islice

import flet as ft

from pycon_us.core.models import ConferenceData, Session
from pycon_us.core.queries import days
from pycon_us.core.timefmt import day_label, local_date, time_label
from pycon_us.locations import drill_href
from pycon_us.screens.stub import nav_tile, note, stub_body
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.state import Conference, use_conference
from pycon_us.ui.scaffold import AppScaffold, SectionHeader, search_button

SOURCE_LABELS = {
    "none": "No schedule yet",
    "bundled": "Schedule bundled with the app",
    "cache": "Schedule saved on this device",
    "network": "Schedule downloaded",
}

SAMPLE_SIZE = 5
"""How many sessions with speakers the stub links to, for the drill."""


@ft.component
def Schedule() -> ft.View:
    """The Schedule root: the data's status, source and age, its days and a few sessions."""
    page = ft.context.page
    view_path = ft.use_view_path()
    svc = use_services()
    conference = use_conference()

    @report_errors
    async def refresh() -> None:
        await conference.refresh(svc.storage, svc.year, closed=svc.closed)

    info = svc.year.conference
    use_24h = bool(page.media and page.media.always_use_24_hour_format)
    data = conference.data
    counts = _session_counts(data)
    return AppScaffold(
        title="Schedule",
        actions=[search_button(svc.memory, "sessions")],
        body=stub_body(
            [
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
                        disabled=conference.refreshing,
                    ),
                    padding=ft.Padding.symmetric(horizontal=16, vertical=8),
                ),
                SectionHeader("Days"),
                *(
                    ft.ListTile(
                        title=day_label(day), subtitle=f"{counts.get(day, 0)} sessions"
                    )
                    for day in (
                        days(data, info.first_day, info.last_day) if data else ()
                    )
                ),
                SectionHeader("Sessions with speakers"),
                *(
                    nav_tile(
                        session.name,
                        drill_href(view_path, "session", session.id),
                        subtitle=", ".join(session.speaker_names),
                    )
                    for session in islice(_with_speakers(data), SAMPLE_SIZE)
                ),
            ],
            status=True,
        ),
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
