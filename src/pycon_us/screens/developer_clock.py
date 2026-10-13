"""The Developer screen's fake-clock pickers: a date picker, then a time picker (D-187).

``clock_picker()`` returns the button at the end of the fake-clock field. It opens a
Material ``DatePicker``; the day picked opens a ``TimePicker``; the time picked hands
the moment, in conference time, to the screen, which fills the field. Apart from
``developer.py`` so that the screen stays under about 400 lines (D-66).
"""

from collections.abc import Callable
from datetime import date, datetime, time, tzinfo

import flet as ft

from pycon_us import clock
from pycon_us.config import ConferenceInfo
from pycon_us.services.errors import report_errors


def clock_picker(
    page: ft.Page,
    *,
    text: str,
    info: ConferenceInfo,
    on_pick: Callable[[datetime], None],
) -> ft.IconButton:
    """Return the fake-clock field's button, which picks a date and then a time.

    Both pickers open on the field's moment, or on the first day at 09:00 (the field's
    hint) while it is empty or unreadable.

    Args:
        page: The session's page, which shows the pickers as dialogs.
        text: The fake-clock field's text, as rendered.
        info: The conference: its zone, its first day and its year.
        on_pick: Called with the picked moment, aware, in the conference's zone.
    """
    zone = info.zone
    first_morning = datetime.combine(info.first_day, time(9))
    # The date picker's day, until the time is picked: a closure variable, not a hook,
    # since the time picker comes from the date picker's handler and shares its closure.
    day: date | None = None

    @report_errors
    def pick_time(e: ft.Event[ft.TimePicker]) -> None:
        if day is not None and e.control.value is not None:
            on_pick(datetime.combine(day, e.control.value, zone))

    @report_errors
    def pick_day(e: ft.Event[ft.DatePicker]) -> None:
        nonlocal day
        if e.control.value is None:
            return
        day = picked_date(e.control.value)
        start = shown_start(text, zone, first_morning)
        page.show_dialog(
            ft.TimePicker(
                value=start.time(),
                help_text=f"Fake clock time, {info.time_zone_name}",
                on_change=pick_time,
            )
        )

    @report_errors
    def pick() -> None:
        start = shown_start(text, zone, first_morning)
        page.show_dialog(
            ft.DatePicker(
                value=start.date(),
                first_date=date(info.year - 1, 1, 1),
                last_date=date(info.year + 1, 12, 31),
                help_text="Fake clock date",
                on_change=pick_day,
            )
        )

    return ft.IconButton(
        ft.Icons.EDIT_CALENDAR_OUTLINED,
        tooltip="Pick a date and time",
        on_click=pick,
    )


def picked_date(value: datetime | date) -> date:
    """Return the day a ``DatePicker`` reports: it sends the device's local midnight in UTC.

    Args:
        value: ``DatePicker.value`` after a pick.
    """
    if isinstance(value, datetime):
        return (
            value.astimezone().date() if value.utcoffset() is not None else value.date()
        )
    return value


def shown_start(text: str, zone: tzinfo, default: datetime) -> datetime:
    """Return where the pickers open, in naive conference time.

    Args:
        text: The fake-clock field's text; its instant when it parses.
        zone: The conference's zone.
        default: For an empty or unreadable field: the first morning, which a test or
            a demo wants far more often than today.
    """
    try:
        moment = clock.parse_fake_clock(text, zone)
    except ValueError:
        moment = None
    if moment is None:
        return default
    return moment.astimezone(zone).replace(tzinfo=None)
