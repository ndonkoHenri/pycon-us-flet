"""The Schedule's head: the filter summary, the status strip and the zone note (D-345).

Under the day tabs the Schedule says what the filter hides (D-20), whether its data is
fresh (D-32) and that its times are Pacific Time (D-240). At sizes up to the largest
standard text these lines stay fixed between the tabs and the day pages. At the
Accessibility sizes, where a slot's time goes above its rows (``Prefs.time_above``,
D-216, the signal D-328 uses), they took most of what the app bar, the tabs and the
bottom bar left (#331), so they head each day's list instead and scroll away with it,
as "Now in this room" does on a room's page (D-194).

``Head`` is the head's words, a plain value, so a memoised day list given it stays
skipped while they are the same (D-153); ``ScheduleHead`` places them, and ``ListHead``
puts them at the top of a day list as one of its items: keyed, and reporting its height,
as the slots do, so a text-size change keeps the reader's place there too (D-331).
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

import flet as ft

from pycon_us.screens.schedule_filter import summary_line
from pycon_us.services.errors import report_errors
from pycon_us.ui.scrolling import anchored
from pycon_us.ui.status_strip import StatusStrip, zone_note_line

HEAD_KEY = "head"
"""The head's key among a day list's slots, which are keyed by their slot keys."""


@dataclass(frozen=True)
class Head:
    """What the Schedule's head says.

    Attributes:
        summary: The filter summary, "Hidden: Open space" (``summary_text()``), or
            None while nothing is hidden.
        zone_note: "Times are Pacific Time (PDT)" (``timefmt.zone_note()``), or None
            while the device is on conference time.
    """

    summary: str | None
    zone_note: str | None


@ft.component
def ScheduleHead(head: Head, on_show_all: Callable[[], object]) -> ft.Control:
    """Return the summary, the strip and the zone note, one under the other.

    Each line is always one control, an empty placeholder while it says nothing, so
    the controls after it keep their places (#313). The strip refreshes the feed when
    a refresh is due (D-40): in a day list each day's head has a strip, and
    ``Conference.start_refresh_if_due()`` starts at most one refresh at a time.

    Args:
        head: The words.
        on_show_all: What "Show all" does: hide no track (``TrackFilter.show_all``).
    """
    return ft.Column(
        [
            summary_line(head.summary, on_show_all) if head.summary else ft.Container(),
            StatusStrip(auto_refresh=True),
            zone_note_line(head.zone_note),
        ],
        spacing=0,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )


@ft.component
def ListHead(
    head: Head,
    on_show_all: Callable[[], object],
    day: date,
    on_measure: Callable[[date, str, float], None],
) -> ft.Control:
    """Return the head as a day list's first item (D-345).

    Under an anchor keyed ``HEAD_KEY``, so a place at the head can be put back by a
    keyed jump, and reporting its height, so the places below it count it (D-331).

    Args:
        head: The words.
        on_show_all: What "Show all" does.
        day: The list's day, in the height's report.
        on_measure: The Schedule's height handler, a stable callable (D-331).
    """

    @report_errors
    def measured(e: ft.LayoutSizeChangeEvent[ft.LayoutControl]) -> None:
        on_measure(day, HEAD_KEY, e.height)

    return ft.Container(
        anchored(HEAD_KEY, ScheduleHead(head, on_show_all)), on_size_change=measured
    )
