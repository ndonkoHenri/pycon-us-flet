"""Tests for the Developer screen's Apply and Reset, and its pickers (#88; D-73).

The fixtures and lookups are ``tests/developer_screen.py``'s; the controls, the fields and
the flags are ``test_developer.py``'s. The pickers on a device are checked on devices
(the PR).
"""

import json
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from types import SimpleNamespace
from typing import Any, cast

import flet as ft
import pytest

from pycon_us import clock
from pycon_us.prefs import Prefs
from pycon_us.services import Services, changes_file
from pycon_us.state import Conference
from pycon_us.theme import LIGHT_TOKENS
from tests import developer_screen
from tests.developer_screen import (
    FEED,
    PACIFIC,
    clock_picker_button,
    field,
    outcome,
    outcome_icon,
    outcome_row,
    press,
    type_into,
)
from tests.fakes import FakePage, MemoryPrefs

real_time, page, svc, prefs, conference, render = (
    developer_screen.real_time,
    developer_screen.page,
    developer_screen.svc,
    developer_screen.prefs,
    developer_screen.conference,
    developer_screen.render,
)


async def test_apply_starts_the_fake_clock_and_the_feed_url_and_keeps_them(
    render: Callable[[], dict[str, Any]],
    prefs: Prefs,
    conference: Conference,
    svc: Services,
    page: FakePage,
) -> None:
    """Apply runs the fake clock and sets the feed URL, stores both and says so.

    The line under the buttons, not a SnackBar, says it with a success icon, and the
    next edit hides it.
    """
    await type_into(render, "developer.fake_clock", "2026-05-15 09:00")
    await type_into(render, "developer.feed_url", FEED)
    await press(render, "developer.apply")
    start = datetime(2026, 5, 15, 9, 0, tzinfo=PACIFIC)
    assert timedelta(0) <= clock.now() - start < timedelta(seconds=5)  # runs forward
    assert conference._feed_url == FEED  # the next refresh's URL
    stored = json.loads(cast(MemoryPrefs, svc.storage.prefs).values["pycon.dev"])
    assert stored == {"unlocked": True, "fake_now": start.isoformat(), "feed_url": FEED}
    assert prefs.fake_now == start
    # In place, under the buttons, not a SnackBar (D-29, D-210).
    assert page.dialogs == []
    assert outcome(render) == "Applied: a fake clock in Pacific Time and your feed URL."
    row = outcome_row(render)
    assert row is not None
    assert outcome_icon(row).color == LIGHT_TOKENS.success
    await type_into(render, "developer.feed_url", "")
    assert outcome(render) is None  # an edit clears it


async def test_the_clock_is_set_before_the_save_re_renders_the_screens(
    render: Callable[[], dict[str, Any]], prefs: Prefs
) -> None:
    """Apply sets the fake clock before the save tells Prefs' subscribers.

    App subscribes to Prefs, so the save re-renders the tree (D-150); every screen that
    renders then must already read the new time (D-187).
    """
    seen: list[datetime] = []

    def listener(_sender: object, name: str | None) -> None:
        if name == "dev":
            seen.append(clock.now())

    assert isinstance(prefs, ft.Observable)
    prefs.subscribe(listener)
    await type_into(render, "developer.fake_clock", "2026-05-15T09:00:00-07:00")
    await press(render, "developer.apply")
    [at_save] = seen
    assert at_save.date() == date(2026, 5, 15)


async def test_apply_with_the_same_start_keeps_the_clock_running(
    render: Callable[[], dict[str, Any]],
    prefs: Prefs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Apply with the stored clock start unchanged does not set the clock back."""
    prefs.dev = {"unlocked": True, "fake_now": "2026-05-15T09:00:00-07:00"}
    started: list[datetime | None] = []
    monkeypatch.setattr(clock, "start_fake_clock", started.append)
    await type_into(render, "developer.feed_url", FEED)  # only the feed changes
    await press(render, "developer.apply")
    assert started == []  # not set back to 9:00


async def test_a_clock_or_url_that_does_not_parse_is_shown_and_nothing_applies(
    render: Callable[[], dict[str, Any]],
    prefs: Prefs,
    conference: Conference,
    page: FakePage,
) -> None:
    """Values that don't parse get field errors and apply nothing; typing clears one."""
    await type_into(render, "developer.fake_clock", "next Friday")
    await type_into(render, "developer.feed_url", "us.pycon.org/feed.json")
    await press(render, "developer.apply")
    scaffold = render()
    assert field(scaffold, "developer.fake_clock").error == (
        "Write it as YYYY-MM-DD HH:MM"
    )
    assert field(scaffold, "developer.feed_url").error == (
        "Use an http:// or https:// address"
    )
    assert prefs.dev == {"unlocked": True}
    assert conference._feed_url is None
    assert outcome(render) is None
    await type_into(render, "developer.fake_clock", "2026-05-15 09:00")
    assert field(render(), "developer.fake_clock").error is None  # typing clears it


async def test_reset_returns_to_real_time_and_the_year_s_feed(
    render: Callable[[], dict[str, Any]],
    prefs: Prefs,
    conference: Conference,
    page: FakePage,
) -> None:
    """Reset restores real time and the year's feed, empties the fields and says so."""
    await type_into(render, "developer.fake_clock", "2026-05-15 09:00")
    await type_into(render, "developer.feed_url", FEED)
    await press(render, "developer.apply")
    await press(render, "developer.reset")
    assert abs(clock.now() - datetime.now(UTC)) < timedelta(seconds=5)
    assert conference._feed_url is None
    assert prefs.dev == {"unlocked": True}  # Developer stays unlocked
    scaffold = render()
    assert field(scaffold, "developer.fake_clock").value == ""
    assert field(scaffold, "developer.feed_url").value == ""
    assert outcome(render) == "Back to real time and the year's feed."


async def test_apply_and_reset_drop_the_cache_and_the_log_when_the_feed_url_changes(
    render: Callable[[], dict[str, Any]],
    svc: Services,
    conference: Conference,
    page: FakePage,
) -> None:
    """Apply or Reset that changes the feed URL deletes the cache and the change log.

    Whichever way it goes: to a feed URL, back to the year's feed, or Reset. Apply that
    keeps the URL deletes nothing. The rule is the store's (Conference.set_feed_url,
    D-255): the feed has loaded, as it always has under the Developer screen.
    """
    await conference.load_local(svc.storage, svc.year)
    log = changes_file.changes_path(svc.storage)

    async def fill() -> None:
        """Write a cache and a change log, as refreshes would."""
        await svc.storage.write_feed(b"{}")
        await changes_file.write_batches(svc.storage, [])

    def kept() -> tuple[bool, bool]:
        """Whether the cache and the change log are there."""
        return svc.storage.feed_path.exists(), log.exists()

    await fill()
    await type_into(render, "developer.feed_url", FEED)
    await press(render, "developer.apply")
    assert kept() == (False, False)  # to a feed URL
    await fill()
    await press(render, "developer.apply")
    assert kept() == (True, True)  # the same URL: nothing changed
    await type_into(render, "developer.feed_url", "")
    await press(render, "developer.apply")
    assert kept() == (False, False)  # back to the year's feed
    await type_into(render, "developer.feed_url", FEED)
    await press(render, "developer.apply")
    await fill()
    await press(render, "developer.reset")
    assert kept() == (False, False)  # Reset


async def test_options_that_cannot_be_saved_hold_for_the_session_and_say_so(
    render: Callable[[], dict[str, Any]], svc: Services, page: FakePage
) -> None:
    """A failed save still applies the clock and says so, with a warning icon."""
    cast(MemoryPrefs, svc.storage.prefs).fail_writes = True
    await type_into(render, "developer.fake_clock", "2026-05-15 09:00")
    await press(render, "developer.apply")
    assert clock.now().astimezone(PACIFIC).date() == date(2026, 5, 15)
    assert outcome(render) == (  # D-120
        "Applied: a fake clock in Pacific Time and the year's feed. "
        "Couldn't save your change: it ends when you close the app."
    )
    row = outcome_row(render)
    assert row is not None
    assert outcome_icon(row).color == LIGHT_TOKENS.warning


async def test_the_pickers_fill_the_clock_field_in_conference_time(
    render: Callable[[], dict[str, Any]], page: FakePage, machine_tz: str
) -> None:
    """The day and time pickers fill the clock field in Pacific Time."""
    await press(render, "developer.apply")
    assert outcome(render) is not None
    button = clock_picker_button(field(render(), "developer.fake_clock"))
    assert button.tooltip == "Pick a date and time"
    cast(Callable[[], None], button.on_click)()
    day_picker = page.dialogs[-1]
    assert isinstance(day_picker, ft.DatePicker)
    assert day_picker.value == date(2026, 5, 13)  # empty: the first day, as the hint
    # Flutter reports the device's local midnight of the day, in UTC.
    day_picker.value = datetime(2026, 5, 15).astimezone().astimezone(UTC)
    cast(Callable[[object], None], day_picker.on_change)(
        SimpleNamespace(control=day_picker)
    )
    time_picker = page.dialogs[-1]
    assert isinstance(time_picker, ft.TimePicker)
    assert time_picker.value == time(9, 0)
    assert time_picker.help_text == "Fake clock time, Pacific Time"
    time_picker.value = time(9, 30)
    cast(Callable[[object], None], time_picker.on_change)(
        SimpleNamespace(control=time_picker)
    )
    assert field(render(), "developer.fake_clock").value == "2026-05-15 09:30"
    assert outcome(render) is None  # a fill is an edit: it clears the line
