"""Tests for the fake clock's pickers on the Developer screen (#88; D-187).

``clock_picker()`` runs on a fake page bound as Flet binds a session's page, and each
pick is reported as Flutter reports it. How the screen fills its field from them is
``test_developer.py``'s; how they look on a device is checked on devices (the PR).
"""

from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime, time
from types import SimpleNamespace
from typing import Any, cast
from zoneinfo import ZoneInfo

import flet as ft
import pytest

from pycon_us.config import load_year
from pycon_us.screens.developer_clock import clock_picker, picked_date
from tests.fake_page import FakePage, bound

PACIFIC = ZoneInfo("America/Los_Angeles")
INFO = load_year(2026).conference


@pytest.fixture
def page() -> Iterator[FakePage]:
    """A fake page, bound as Flet binds a session's page."""
    fake = FakePage()
    with bound(fake):
        yield fake


def open_pickers(page: FakePage, text: str, picked: list[datetime]) -> ft.DatePicker:
    """Tap the field's button and return the date picker it opens."""
    button = clock_picker(
        cast(ft.Page, page), text=text, info=INFO, on_pick=picked.append
    )
    assert button.icon == ft.Icons.EDIT_CALENDAR_OUTLINED
    cast(Callable[[], None], button.on_click)()
    day_picker = page.dialogs[-1]
    assert isinstance(day_picker, ft.DatePicker)
    return day_picker


def choose(picker: ft.DatePicker | ft.TimePicker, value: object) -> None:
    """Pick ``value`` as Flutter reports it: the picker's value first, then ``on_change``."""
    picker.value = cast(Any, value)
    cast(Callable[[object], None], picker.on_change)(SimpleNamespace(control=picker))


@pytest.mark.parametrize(
    ("text", "day", "at"),
    [
        ("", date(2026, 5, 13), time(9)),  # empty: the first morning, as the hint
        ("next Friday", date(2026, 5, 13), time(9)),  # unreadable: the same
        ("2026-05-16T01:30:00+00:00", date(2026, 5, 15), time(18, 30)),  # in PDT
    ],
)
def test_the_pickers_open_on_the_field_s_moment_in_conference_time(
    page: FakePage, text: str, day: date, at: time
) -> None:
    """The pickers open on the field's moment in Pacific Time, else the first morning.

    The day picker spans 2025 to 2027; the time picker it opens shows the field's time.
    """
    day_picker = open_pickers(page, text, [])
    assert day_picker.value == day
    assert day_picker.first_date == date(2025, 1, 1)
    assert day_picker.last_date == date(2027, 12, 31)
    choose(day_picker, datetime(2026, 5, 15).astimezone().astimezone(UTC))
    time_picker = page.dialogs[-1]
    assert isinstance(time_picker, ft.TimePicker)
    assert time_picker.value == at


def test_the_picked_day_and_time_are_handed_on_in_conference_time(
    page: FakePage, machine_tz: str
) -> None:
    """In any machine zone, a picked day and time reach ``on_pick`` in Pacific Time.

    The time picker's help text names Pacific Time too.
    """
    picked: list[datetime] = []
    day_picker = open_pickers(page, "", picked)
    # Flutter reports the device's local midnight of the day, in UTC.
    choose(day_picker, datetime(2026, 5, 16).astimezone().astimezone(UTC))
    time_picker = page.dialogs[-1]
    assert isinstance(time_picker, ft.TimePicker)
    assert time_picker.help_text == "Fake clock time, Pacific Time"
    choose(time_picker, time(10, 15))
    assert picked == [datetime(2026, 5, 16, 10, 15, tzinfo=PACIFIC)]


def test_a_dismissed_picker_picks_nothing(page: FakePage) -> None:
    """Dismissing either picker picks nothing; a dismissed day opens no time picker."""
    picked: list[datetime] = []
    choose(open_pickers(page, "", picked), None)
    assert len(page.dialogs) == 1  # no time picker
    choose(open_pickers(page, "", picked), date(2026, 5, 15))
    time_picker = page.dialogs[-1]
    assert isinstance(time_picker, ft.TimePicker)
    choose(time_picker, None)
    assert picked == []


def test_a_picked_day_is_the_device_s_day(machine_tz: str) -> None:
    """A pick reported as the device's midnight in UTC, or as a date, is that date."""
    local_midnight = datetime(2026, 5, 15).astimezone()
    assert picked_date(local_midnight.astimezone(UTC)) == date(2026, 5, 15)
    assert picked_date(date(2026, 5, 15)) == date(2026, 5, 15)
