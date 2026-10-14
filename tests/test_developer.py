"""Tests for the Developer screen: the fake clock, the feed URL and the flags (#88; D-73).

``Developer`` runs outside a renderer: its hooks and ``AppScaffold`` are replaced, and a
fake page is bound as Flet binds a session's page. The parsing helpers are pure; the
pickers on their own are ``test_developer_clock.py``'s. How the screen looks, and the
pickers on a device, are checked on devices (the PR).
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

from pycon_us import capabilities, clock
from pycon_us import prefs as prefs_module
from pycon_us.config import load_year
from pycon_us.memory import ViewMemory
from pycon_us.prefs import Prefs
from pycon_us.screens import developer
from pycon_us.screens.developer import Developer, zone_line
from pycon_us.services import Services
from pycon_us.services.storage import Storage
from pycon_us.state import Conference
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
OTHER_FEED = "http://127.0.0.1:8001/conference-2026.json"


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
    """``ft.use_state`` for one component: the values, kept in call order."""

    def __init__(self) -> None:
        self.values: list[Any] = []
        self.index = 0

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
    monkeypatch.setattr(developer, "use_services", lambda: svc)
    monkeypatch.setattr(developer, "use_prefs", lambda: prefs)
    monkeypatch.setattr(developer, "use_conference", lambda: conference)
    monkeypatch.setattr(developer, "use_tokens", lambda: LIGHT_TOKENS)
    monkeypatch.setattr(developer, "AppScaffold", lambda **kwargs: kwargs)
    # The Data section is a component of its own: test_developer_data.py's.
    monkeypatch.setattr(developer, "DataActions", lambda: ft.Container())

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


def merged_identifiers(scaffold: dict[str, Any]) -> set[str]:
    """The identifiers merged into their control's node: ``MergeSemantics(Semantics)``."""
    found: set[str] = set()

    def visit(control: Any) -> None:
        if isinstance(control, ft.MergeSemantics):
            inner = control.content
            if isinstance(inner, ft.Semantics) and inner.identifier:
                found.add(inner.identifier)
        for name in ("content", "controls", "suffix_icon"):
            child = getattr(control, name, None)
            for item in child if isinstance(child, list) else [child]:
                if isinstance(item, ft.Control):
                    visit(item)

    visit(scaffold["body"])
    return found


def clock_picker_button(text_field: ft.TextField) -> ft.IconButton:
    """The fake-clock field's picker, merged with its identifier (D-214)."""
    merged = text_field.suffix_icon
    assert isinstance(merged, ft.MergeSemantics)
    node = merged.content
    assert isinstance(node, ft.Semantics)
    assert node.identifier == "developer.clock_picker"
    assert isinstance(node.content, ft.IconButton)
    return node.content


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


def outcome_row(render: Callable[[], dict[str, Any]]) -> ft.Row | None:
    """The line under the buttons, its icon and its words, or None while it is hidden."""
    line = next(
        c
        for c in cast(ft.ListView, render()["body"]).controls
        if isinstance(c, ft.Semantics) and c.identifier == "developer.outcome"
    )
    assert line.live_region is True
    if not line.visible:
        return None
    assert isinstance(line.content, ft.Container)
    assert isinstance(line.content.content, ft.Row)
    return line.content.content


def outcome(render: Callable[[], dict[str, Any]]) -> str | None:
    """The words of the line under the buttons, or None while it is hidden."""
    row = outcome_row(render)
    if row is None:
        return None
    _, text = row.controls
    assert isinstance(text, ft.Text)
    assert text.text_align == ft.TextAlign.START  # as the page's other text
    return str(text.value)


def outcome_icon(row: ft.Row) -> ft.Icon:
    """The outcome line's icon, in the slot that lines its words up with the tiles."""
    slot = row.controls[0]
    # A ListTile's leading slot and gap: the words start where the tiles' do (56 dp).
    assert isinstance(slot, ft.Container) and slot.width == 24 and row.spacing == 16
    assert isinstance(slot.content, ft.Icon)
    return slot.content


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


def test_the_buttons_and_the_url_field_are_one_node_with_their_identifier(
    render: Callable[[], dict[str, Any]],
) -> None:
    # A bare Semantics(identifier) around a control dumped as an empty, focusable
    # View beside the button on Android (#236); merged, the control's own node
    # carries it (D-190).
    assert merged_identifiers(render()) == {
        "developer.reset",
        "developer.apply",
        "developer.feed_url",
        "developer.clock_picker",
    }
    nodes = by_identifier(render())
    assert isinstance(nodes["developer.reset"], ft.OutlinedButton)
    assert isinstance(nodes["developer.apply"], ft.FilledButton)
    assert isinstance(nodes["developer.feed_url"], ft.TextField)


def test_the_clock_field_keeps_its_picker_a_button_of_its_own(
    render: Callable[[], dict[str, Any]],
) -> None:
    # A merge takes in every descendant: around the clock field it would make the
    # picker part of the field's node (D-189), so that identifier stays bare (U34).
    scaffold = render()
    assert "developer.fake_clock" not in merged_identifiers(scaffold)
    assert clock_picker_button(field(scaffold, "developer.fake_clock"))


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
    label = chip.content  # text only: a fixed-size icon looked lost at 200 % text
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


def helper(text_field: ft.TextField) -> ft.Text:
    """A field's helper, a ``Text`` in Material's helper style."""
    text = text_field.helper
    assert isinstance(text, ft.Text)
    assert text.theme_style == ft.TextThemeStyle.BODY_SMALL
    assert text.color == ft.Colors.ON_SURFACE_VARIANT
    return text


def test_the_fields_say_the_clock_s_format_and_wrap_at_large_text(
    render: Callable[[], dict[str, Any]],
) -> None:
    scaffold = render()
    clock_field = field(scaffold, "developer.fake_clock")
    assert helper(clock_field).value == (
        "YYYY-MM-DD HH:MM, in Pacific Time. Empty for real time."
    )
    for text_field in (clock_field, field(scaffold, "developer.feed_url")):
        assert text_field.max_lines == 3  # wraps instead of hiding the end
        assert text_field.hint_max_lines == 1  # an empty field keeps one line
        # Not multiline: it would swap in the multiline keyboard, whose Return types
        # a line break, for the date-time and URL keyboards.
        assert text_field.multiline is False
    assert clock_field.keyboard_type == ft.KeyboardType.DATETIME


def test_the_helpers_are_shown_in_full_at_the_largest_text(
    render: Callable[[], dict[str, Any]],
) -> None:
    # A string helper is cut at helper_max_lines, and null is one line: at three, the
    # largest text cut the clock's at "Empty for r…", the way back to real time (#280).
    scaffold = render()
    for identifier in ("developer.fake_clock", "developer.feed_url"):
        text_field = field(scaffold, identifier)
        assert text_field.helper_max_lines is None  # the Text helper ignores it
        text = helper(text_field)
        assert text.max_lines is None
        assert text.overflow in (None, ft.TextOverflow.CLIP)  # no ellipsis


def test_reset_and_apply_keep_their_padding_at_large_text(
    render: Callable[[], dict[str, Any]],
) -> None:
    # Flutter shrinks a button's side padding as the text grows: at the largest text
    # the labels touched the rounded ends (#280), as the Schedule sheet's Show did.
    nodes = by_identifier(render())
    for identifier in ("developer.reset", "developer.apply"):
        button = nodes[identifier]
        assert isinstance(button, ft.OutlinedButton | ft.FilledButton)
        assert button.style is not None
        assert button.style.padding == ft.Padding.symmetric(horizontal=24, vertical=8)
    apply = nodes["developer.apply"]
    # With a style, Flet lifts every state to the button's elevation: M3's lies flat.
    assert isinstance(apply, ft.FilledButton) and apply.elevation == 0


def test_the_url_field_keeps_apply_in_sight_above_the_keyboard(
    render: Callable[[], dict[str, Any]],
) -> None:
    # Focused, the field scrolls its helper and the Reset and Apply row under it into
    # sight, so a URL can be typed and applied without closing the keyboard (#108).
    scaffold = render()
    url_padding = field(scaffold, "developer.feed_url").scroll_padding
    assert url_padding == ft.Padding.only(
        left=20, top=20, right=20, bottom=developer.APPLY_IN_SIGHT
    )
    # The clock field keeps Flutter's 20 dp: Apply is far below it.
    clock_padding = field(scaffold, "developer.fake_clock").scroll_padding
    assert clock_padding == ft.Padding.only(left=20, top=20, right=20, bottom=20)


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
    # App subscribes to Prefs, so the save re-renders the tree (D-150); every screen
    # that renders then must already read the new time (D-187).
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


async def test_leaving_a_developer_feed_url_drops_the_feed_it_may_have_cached(
    render: Callable[[], dict[str, Any]], svc: Services, page: FakePage
) -> None:
    # An offline start would publish the cache as the schedule (D-187).
    await svc.storage.write_feed(b"{}")
    await press(render, "developer.reset")
    assert svc.storage.feed_path.exists()  # the year's feed: kept
    await type_into(render, "developer.feed_url", FEED)
    await press(render, "developer.apply")
    assert svc.storage.feed_path.exists()  # a feed URL in use: kept
    await type_into(render, "developer.feed_url", OTHER_FEED)
    await press(render, "developer.apply")
    assert svc.storage.feed_path.exists()  # from one feed URL to another: kept
    await type_into(render, "developer.feed_url", "")
    await press(render, "developer.apply")
    assert not svc.storage.feed_path.exists()  # Apply back to the year's feed
    await svc.storage.write_feed(b"{}")
    await type_into(render, "developer.feed_url", FEED)
    await press(render, "developer.apply")
    await press(render, "developer.reset")
    assert not svc.storage.feed_path.exists()  # Reset


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
    row = outcome_row(render)
    assert row is not None
    assert outcome_icon(row).color == LIGHT_TOKENS.warning


async def test_the_pickers_fill_the_clock_field_in_conference_time(
    render: Callable[[], dict[str, Any]], page: FakePage, machine_tz: str
) -> None:
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


# ------------------------------------------------------------------ the helpers


def test_the_time_zone_row_names_the_conference_zone_and_the_device_offset() -> None:
    line = zone_line("Pacific Time", "America/Los_Angeles", datetime.now(UTC))
    assert line.startswith("Pacific Time (America/Los_Angeles). This device: UTC")
