"""Settings' Data section: is my schedule current, and in which zone are its times.

``DataSection`` is the last section of Settings before About this app (ux.md §6.9,
P2-62): **Refresh now**, whose second line says where the schedule on screen came from
and its age, the bundled snapshot named as such (D-292), and which asks for a refresh
(D-181) and says in place how it ended (D-29, D-210), a failed one keeping the schedule
(D-32); and, only while the device's clock differs from the conference's, the zone row,
"Times are Pacific Time (PDT)" and the device's own offset (D-35, D-240). Apart from
``settings.py`` so that the store's changes and the minute's tick re-render this
section and not the page (D-175).
"""

from datetime import timedelta

import flet as ft

from pycon_us import clock
from pycon_us.core.timefmt import utc_offset_label, zone_note
from pycon_us.services import use_services
from pycon_us.services.errors import report_errors
from pycon_us.state import use_conference
from pycon_us.theme import use_tokens
from pycon_us.ui.actions import NO_OUTCOME, action_row, outcome_line, refreshed
from pycon_us.ui.scaffold import SectionHeader
from pycon_us.ui.semantics import named
from pycon_us.ui.status_strip import schedule_line, use_minute

UPDATING = "Updating the schedule…"
"""Refresh now's second line while the refresh it asked for runs, as the strip says it."""


@ft.component
def DataSection(slot: int) -> ft.Control:
    """The Data section: its heading, Refresh now, its outcome and the zone row.

    A component of its own: the outcome is its state, and it re-renders with the
    feed's store, so a refresh that lands, asked for here or not, updates the line,
    and each minute (``use_minute()``), so the age and the zone row keep up.

    Args:
        slot: The width the leading icons are centred in: Settings' radio width, so
            the titles start where Appearance's do (#503's review).
    """
    svc = use_services()
    conference = use_conference()
    tokens = use_tokens()
    use_minute()
    info = svc.year.conference
    outcome, set_outcome = ft.use_state(NO_OUTCOME)

    @report_errors
    async def refresh_now() -> None:
        set_outcome(NO_OUTCOME)
        await conference.refresh(svc.storage, svc.year, closed=svc.closed)
        set_outcome(refreshed(conference.problem))

    refreshing = conference.status(info) == "refreshing"  # as every Refresh (D-181)
    now = clock.now()
    # The device's offset now: the packaged app's Python reads the device's zone
    # (F60), and the minute's tick follows a DST change, as the Schedule's note does.
    offset = now.astimezone().utcoffset()
    rows: list[ft.Control] = [
        SectionHeader("Data"),  # level 2, a section of the page (D-211)
        action_row(
            "settings.data.refresh",
            ft.Icons.REFRESH,
            "Refresh now",
            UPDATING
            if refreshing
            else schedule_line(conference.source, conference.fetched_at),
            refresh_now,
            disabled=refreshing,
            # Something moves while it runs (ux.md §4), the words say what.
            trailing=ft.ProgressRing(width=20, height=20, stroke_width=2)
            if refreshing
            else None,
            slot=slot,
        ),
        ft.Semantics(
            identifier="settings.data.outcome",
            live_region=True,  # a screen reader says how the refresh ended
            visible=bool(outcome[0]),
            content=outcome_line(*outcome, tokens=tokens, slot=slot),
        ),
    ]
    note = zone_note(now, info.zone, info.time_zone_name, offset)
    if note is not None:
        rows.append(zone_row(note, offset, slot=slot))
    return ft.Column(rows, spacing=0)


def zone_row(note: str, offset: timedelta | None, *, slot: int) -> ft.Control:
    """Return the row that names the times' zone while the device's differs (D-35).

    One node with its identifier, read as both lines. Not a button: there is nothing
    to change, the app's times are always the conference's.

    Args:
        note: ``zone_note()``'s words, e.g. "Times are Pacific Time (PDT)".
        offset: The device's UTC offset now, said on the second line.
        slot: The width the icon is centred in.
    """
    device = utc_offset_label(offset) if offset is not None else "another time zone"
    return named(
        "settings.data.zone",
        ft.ListTile(
            leading=ft.Container(
                ft.Icon(ft.Icons.PUBLIC),  # decorative: the words say it
                width=slot,
                alignment=ft.Alignment.CENTER,
            ),
            title=note,
            subtitle=f"This device is on {device}",
            title_alignment=ft.ListTileTitleAlignment.TOP,
            min_vertical_padding=14,
        ),
    )
