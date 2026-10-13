"""Tests for the Developer screen: the fake clock, the feed URL and the flags (#88; D-73).

``Developer`` runs outside a renderer: its hooks and ``AppScaffold`` are replaced, and a
fake page is bound as Flet binds a session's page. The parsing helpers are pure. How the
screen looks, and the pickers on a device, are checked on devices (the PR).
"""

import inspect
import json
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from zoneinfo import ZoneInfo

import flet as ft
import pytest
from flet.components.hooks.use_ref import MutableRef

from pycon_us import capabilities, clock
from pycon_us import prefs as prefs_module
from pycon_us.config import load_year
from pycon_us.prefs import Prefs
from pycon_us.screens import developer, now
from pycon_us.screens.developer import (
    Developer,
    parse_feed_url,
    picked_date,
    zone_line,
)
from pycon_us.services import Services
from pycon_us.services.storage import Storage
from pycon_us.state import Conference, ViewMemory
from pycon_us.theme import LIGHT_TOKENS
from tests.fakes import (
    FakePage,
    MemoryClipboard,
    MemoryHaptics,
    MemoryLauncher,
    MemoryPrefs,
    MemorySemantics,
    bound,
)

PACIFIC = ZoneInfo("America/Los_Angeles")
FEED = "http://127.0.0.1:8000/conference-2026.json"


@pytest.fixture(autouse=True)
def real_time() -> Iterator[None]:
    """Each test starts on real time and leaves the process on it."""
    clock.start_fake_clock(None)
    yield
    clock.start_fake_clock(None)


@pytest.fixture
def page() -> Iterator[FakePage]:
    fake = FakePage()
    with bound(fake):
        yield fake


@pytest.fixture
def svc(tmp_path: Path) -> Services:
    storage = Storage(prefs=MemoryPrefs(), directory=tmp_path, year=2026)
    return Services(
        year=load_year(2026),
        storage=storage,
        memory=ViewMemory(),
        semantics=MemorySemantics(),
        haptics=MemoryHaptics(),
        launcher=MemoryLauncher(),
        clipboard=MemoryClipboard(),
    )


@pytest.fixture
def prefs(monkeypatch: pytest.MonkeyPatch) -> Prefs:
    monkeypatch.setattr(prefs_module, "DEVELOPER_ALWAYS", False)  # a packaged build
    return Prefs(dev={"unlocked": True})


@pytest.fixture
def conference() -> Conference:
    return Conference()


class States:
    """``ft.use_state`` and ``ft.use_ref`` for one component: kept in call order."""

    def __init__(self) -> None:
        self.values: list[Any] = []
        self.index = 0
        self.ref = MutableRef(None)

    def use_state(self, initial: Any) -> tuple[Any, Callable[[Any], None]]:
        if self.index == len(self.values):
            self.values.append(initial() if callable(initial) else initial)
        index = self.index
        self.index += 1

        def set_value(value: Any) -> None:
            self.values[index] = value

        return self.values[index], set_value


@pytest.fixture
def render(
    monkeypatch: pytest.MonkeyPatch,
    svc: Services,
    prefs: Prefs,
    conference: Conference,
    page: FakePage,
) -> Callable[[], dict[str, Any]]:
    """Render ``Developer`` and return what it passed to ``AppScaffold``."""
    states = States()
    monkeypatch.setattr(ft, "use_state", states.use_state)
    monkeypatch.setattr(ft, "use_ref", lambda initial=None: states.ref)
    monkeypatch.setattr(developer, "use_services", lambda: svc)
    monkeypatch.setattr(developer, "use_prefs", lambda: prefs)
    monkeypatch.setattr(developer, "use_conference", lambda: conference)
    monkeypatch.setattr(developer, "use_tokens", lambda: LIGHT_TOKENS)
    monkeypatch.setattr(developer, "AppScaffold", lambda **kwargs: kwargs)

    def render() -> dict[str, Any]:
        states.index = 0
        return cast(dict[str, Any], inspect.unwrap(Developer)())

    return render


def by_identifier(scaffold: dict[str, Any]) -> dict[str, ft.Control]:
    """The controls under each ``developer.*`` identifier."""
    found: dict[str, ft.Control] = {}

    def visit(control: Any) -> None:
        if isinstance(control, ft.Semantics) and control.identifier:
            found[control.identifier] = cast(ft.Control, control.content)
        for name in ("content", "controls"):
            child = getattr(control, name, None)
            for item in child if isinstance(child, list) else [child]:
                if isinstance(item, ft.Control):
                    visit(item)

    visit(scaffold["body"])
    return found


def field(scaffold: dict[str, Any], identifier: str) -> ft.TextField:
    control = by_identifier(scaffold)[identifier]
    assert isinstance(control, ft.TextField)
    return control


async def type_into(
    render: Callable[[], dict[str, Any]], identifier: str, text: str
) -> None:
    """Type as Flutter reports it: the field's value first, then ``on_change``."""
    text_field = field(render(), identifier)
    text_field.value = text
    cast(Callable[[object], None], text_field.on_change)(
        SimpleNamespace(control=text_field)
    )


async def press(render: Callable[[], dict[str, Any]], identifier: str) -> None:
    button = by_identifier(render())[identifier]
    assert isinstance(button, ft.FilledButton | ft.OutlinedButton)
    await cast(Any, button.on_click)()


def outcome(render: Callable[[], dict[str, Any]]) -> str | None:
    """The line under the buttons, or None while it is hidden."""
    line = next(
        c
        for c in cast(ft.ListView, render()["body"]).controls
        if isinstance(c, ft.Semantics) and c.identifier == "developer.outcome"
    )
    assert line.live_region is True
    if not line.visible:
        return None
    assert isinstance(line.content, ft.Container)
    assert isinstance(line.content.content, ft.Text)
    return str(line.content.content.value)


# ------------------------------------------------------------------ the screen


def test_the_controls_carry_the_identifiers_ui_flows_use(
    render: Callable[[], dict[str, Any]],
) -> None:
    scaffold = render()
    assert set(by_identifier(scaffold)) == {
        "developer.fake_clock",
        "developer.feed_url",
        "developer.reset",
        "developer.apply",
        "developer.outcome",
    }
    assert scaffold["title"] == "Developer options"


def test_a_warning_tone_chip_marks_the_screen(
    render: Callable[[], dict[str, Any]],
) -> None:
    scaffold = render()
    assert "actions" not in scaffold  # at 200 % text it pushed the title out
    top = cast(ft.ListView, scaffold["body"]).controls[0]
    assert isinstance(top, ft.Container) and isinstance(top.content, ft.Column)
    chip = top.content.controls[0]
    assert isinstance(chip, ft.Container)
    assert chip.border == ft.Border.all(1, LIGHT_TOKENS.warning)
    assert chip.on_click is None  # a mark, not a control
    assert isinstance(chip.content, ft.Row)
    icon, label = chip.content.controls
    assert isinstance(icon, ft.Icon) and icon.color == LIGHT_TOKENS.warning
    assert isinstance(label, ft.Text) and label.value == "Developer"
    assert label.color == LIGHT_TOKENS.warning


def test_the_fields_show_what_is_in_effect(
    render: Callable[[], dict[str, Any]], prefs: Prefs
) -> None:
    prefs.dev = {
        "unlocked": True,
        "fake_now": "2026-05-15T16:00:00+00:00",
        "feed_url": FEED,
    }
    scaffold = render()
    assert field(scaffold, "developer.fake_clock").value == "2026-05-15 09:00"  # PDT
    assert field(scaffold, "developer.feed_url").value == FEED


async def test_apply_starts_the_fake_clock_and_the_feed_url_and_keeps_them(
    render: Callable[[], dict[str, Any]],
    prefs: Prefs,
    conference: Conference,
    svc: Services,
    page: FakePage,
) -> None:
    await type_into(render, "developer.fake_clock", "2026-05-15 09:00")
    await type_into(render, "developer.feed_url", FEED)
    await press(render, "developer.apply")
    start = datetime(2026, 5, 15, 9, 0, tzinfo=PACIFIC)
    assert timedelta(0) <= clock.now() - start < timedelta(seconds=5)  # runs forward
    assert conference._feed_url == FEED  # the next refresh's URL
    stored = json.loads(cast(MemoryPrefs, svc.storage.prefs).values["pycon.dev"])
    assert stored == {"unlocked": True, "fake_now": start.isoformat(), "feed_url": FEED}
    assert prefs.fake_now == start
    # In place, not a SnackBar: one would show on More under this View (#197).
    assert page.dialogs == []
    assert outcome(render) == "Applied: a fake clock in Pacific Time and your feed URL."
    await type_into(render, "developer.feed_url", "")
    assert outcome(render) is None  # an edit clears it


async def test_the_clock_is_set_before_the_save_re_renders_the_screens(
    render: Callable[[], dict[str, Any]], prefs: Prefs
) -> None:
    # App subscribes to Prefs, so the save re-renders the tree (D-150); every screen
    # that renders then must already read the new time (D-184).
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


async def test_options_that_cannot_be_saved_hold_for_the_session_and_say_so(
    render: Callable[[], dict[str, Any]], svc: Services, page: FakePage
) -> None:
    cast(MemoryPrefs, svc.storage.prefs).fail_writes = True
    await type_into(render, "developer.fake_clock", "2026-05-15 09:00")
    await press(render, "developer.apply")
    assert clock.now().astimezone(PACIFIC).date() == date(2026, 5, 15)
    assert outcome(render) == (  # D-120
        "Applied: a fake clock in Pacific Time and the year's feed. "
        "Couldn't save your change: it ends when you close the app."
    )


async def test_the_pickers_fill_the_clock_field_in_conference_time(
    render: Callable[[], dict[str, Any]], page: FakePage, machine_tz: str
) -> None:
    text_field = field(render(), "developer.fake_clock")
    assert isinstance(text_field.suffix_icon, ft.IconButton)
    assert text_field.suffix_icon.tooltip == "Pick a date and time"
    cast(Callable[[], None], text_field.suffix_icon.on_click)()
    day_picker = page.dialogs[-1]
    assert isinstance(day_picker, ft.DatePicker)
    # Flutter reports the device's local midnight of the day, in UTC.
    day_picker.value = datetime(2026, 5, 15).astimezone().astimezone(UTC)
    cast(Callable[[object], None], day_picker.on_change)(
        SimpleNamespace(control=day_picker)
    )
    time_picker = page.dialogs[-1]
    assert isinstance(time_picker, ft.TimePicker)
    time_picker.value = time(9, 30)
    cast(Callable[[object], None], time_picker.on_change)(
        SimpleNamespace(control=time_picker)
    )
    assert field(render(), "developer.fake_clock").value == "2026-05-15 09:30"


def test_before_the_unlock_a_packaged_build_shows_how_to_unlock(
    render: Callable[[], dict[str, Any]], prefs: Prefs
) -> None:
    prefs.dev = {}
    scaffold = render()
    assert by_identifier(scaffold) == {}  # no options to change


def test_the_capability_flags_are_shown_read_only(
    render: Callable[[], dict[str, Any]],
) -> None:
    body = render()["body"]
    assert isinstance(body, ft.ListView)
    rows = [
        (row.title, row.subtitle)
        for row in body.controls
        if isinstance(row, ft.ListTile) and row.title != "Time zone"
    ]
    # The constants, as fixed at import (D-63); in pytest, no packaged build bundles them.
    assert rows == [
        (name, "In this build" if on else "Not in this build")
        for name, on in [
            ("Secure storage", capabilities.SECURE_STORAGE),
            ("Permissions", capabilities.PERMISSIONS),
            ("Reminders", capabilities.REMINDERS),
            ("Badge scanner", capabilities.SCANNER),
        ]
    ]
    assert all(
        row.on_click is None for row in body.controls if isinstance(row, ft.ListTile)
    )


# ------------------------------------------------------------------ Now (Schedule: test_schedule.py)


def test_now_says_which_day_it_is_by_the_clock_in_conference_time(
    monkeypatch: pytest.MonkeyPatch, svc: Services, page: FakePage, machine_tz: str
) -> None:
    monkeypatch.setattr(now, "use_services", lambda: svc)
    monkeypatch.setattr(now, "use_scroll_to_top", lambda: (ft.Ref(), None))
    monkeypatch.setattr(now, "AppScaffold", lambda **kwargs: kwargs)
    monkeypatch.setattr(now, "stub_body", lambda controls, **_: controls)

    def today_line() -> str:
        line = inspect.unwrap(now.Now)()["body"][0]
        assert isinstance(line, ft.Semantics) and line.identifier == "now.today"
        assert isinstance(line.content, ft.Container)
        assert isinstance(line.content.content, ft.Text)
        return str(line.content.content.value)

    # 23:30 in Long Beach is already Saturday on Kiritimati: the conference's day counts.
    clock.start_fake_clock(datetime(2026, 5, 15, 23, 30, tzinfo=PACIFIC))
    assert today_line() == "Today in Pacific Time: Friday, May 15"
    clock.start_fake_clock(None)  # cleared: the next render is on real time
    assert today_line() != "Today in Pacific Time: Friday, May 15"


# ------------------------------------------------------------------ the helpers


@pytest.mark.parametrize("url", [FEED, "https://example.test/feed.json"])
def test_http_and_https_feed_urls_are_taken(url: str) -> None:
    assert parse_feed_url(f" {url} ") == url


@pytest.mark.parametrize(
    "text", ["us.pycon.org/feed.json", "ftp://example.test/f", "https://", "file:///x"]
)
def test_other_feed_urls_are_refused(text: str) -> None:
    with pytest.raises(ValueError, match="http:// or https://"):
        parse_feed_url(text)


def test_an_empty_feed_url_is_the_year_s() -> None:
    assert parse_feed_url("") is None


def test_a_picked_day_is_the_device_s_day(machine_tz: str) -> None:
    local_midnight = datetime(2026, 5, 15).astimezone()
    assert picked_date(local_midnight.astimezone(UTC)) == date(2026, 5, 15)
    assert picked_date(date(2026, 5, 15)) == date(2026, 5, 15)


def test_the_time_zone_row_names_the_conference_zone_and_the_device_offset() -> None:
    line = zone_line("Pacific Time", "America/Los_Angeles", datetime.now(UTC))
    assert line.startswith("Pacific Time (America/Los_Angeles). This device: UTC")
