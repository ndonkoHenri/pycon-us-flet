"""Tests for the Developer screen's test reminders (`screens/developer_reminders.py`; DEV-06).

`TestReminders` is rendered by hand over a real `Scheduler` on `tests/fakes.py`'s
`MemoryNotifications` and `MemoryPermissions`: each outcome for its state (scheduled
exact or inexact, refused, muted, denied, not available), what is handed to the OS, and
the rows' identifiers (#451, D-402). How the section looks is checked on devices.
"""

import inspect
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast

import flet as ft
import pytest
from flet_notifications import (
    AndroidScheduleMode,
    NotificationException,
    Notifications,
)
from flet_permission_handler import PermissionHandler, PermissionStatus

from pycon_us import clock
from pycon_us.prefs import Prefs
from pycon_us.reminder_settings import ReminderSettings
from pycon_us.screens import developer_reminders
from pycon_us.screens.developer_reminders import KINDS, UNAVAILABLE, TestReminders
from pycon_us.services.reminders import TEST_ID, Scheduler
from pycon_us.theme import LIGHT_TOKENS
from tests.data_section import Rendered, identified, row, subtitle, tap
from tests.fakes import MemoryNotifications, MemoryPermissions

ROWS = {f"developer.test_reminder.{kind.key}" for kind in KINDS}
"""The four rows' identifiers."""


@pytest.fixture
def os() -> MemoryNotifications:
    """The OS's pending reminders: notifications shown and exact alarms allowed."""
    return MemoryNotifications()


@pytest.fixture
def permissions() -> MemoryPermissions:
    """Android's notification permission, granted."""
    return MemoryPermissions(PermissionStatus.GRANTED)


@pytest.fixture
def prefs() -> Prefs:
    """Every kind of reminder on: sessions 10 minutes before, every moment."""
    return Prefs(reminders=ReminderSettings(session_lead=10), loaded=True)


@pytest.fixture
def scheduler(os: MemoryNotifications, permissions: MemoryPermissions) -> Scheduler:
    """An Android `Scheduler` over the fakes, typed as over the real services."""
    return Scheduler(
        cast(Notifications, os),
        cast(PermissionHandler, permissions),
        android=True,
    )


def renderer(
    monkeypatch: pytest.MonkeyPatch, scheduler: Scheduler | None, prefs: Prefs
) -> Callable[[], ft.Column]:
    """Return a function that renders `TestReminders` by hand and returns its column."""
    rendered = Rendered()
    svc = SimpleNamespace(reminders=scheduler)
    monkeypatch.setattr(ft, "use_state", rendered.use_state)
    monkeypatch.setattr(developer_reminders, "use_services", lambda: svc)
    monkeypatch.setattr(developer_reminders, "use_prefs", lambda: prefs)
    monkeypatch.setattr(developer_reminders, "use_tokens", lambda: LIGHT_TOKENS)

    def render() -> ft.Column:
        rendered.index = 0
        column = inspect.unwrap(TestReminders)()
        assert isinstance(column, ft.Column)
        return column

    return render


@pytest.fixture
def render(
    monkeypatch: pytest.MonkeyPatch, scheduler: Scheduler, prefs: Prefs
) -> Callable[[], ft.Column]:
    """Render the section of a build with E3."""
    return renderer(monkeypatch, scheduler, prefs)


def outcome(column: ft.Column) -> str | None:
    """The words of the line under the rows, or None while it is hidden."""
    line = column.controls[-1]
    assert isinstance(line, ft.Semantics) and line.live_region is True
    assert line.identifier == "developer.reminder_outcome"
    if not line.visible:
        return None
    text = cast(ft.Row, cast(ft.Container, line.content).content).controls[1]
    assert isinstance(text, ft.Text)
    return str(text.value)


def outcome_ok(column: ft.Column) -> bool:
    """Whether the outcome line shows the success check, not the warning."""
    line = identified(column)["developer.reminder_outcome"]
    found: list[Any] = []

    def visit(control: Any) -> None:
        if isinstance(control, ft.Icon):
            found.append(control.icon)
        for name in ("content", "controls"):
            child = getattr(control, name, None)
            for item in child if isinstance(child, list) else [child]:
                if isinstance(item, ft.Control):
                    visit(item)

    visit(line)
    return found == [ft.Icons.CHECK_CIRCLE_OUTLINE]


def test_each_row_and_the_outcome_carry_their_identifiers(
    render: Callable[[], ft.Column],
) -> None:
    """A row per kind of reminder and the outcome line, each found by its identifier."""
    assert set(identified(render())) == ROWS | {"developer.reminder_outcome"}


def test_the_outcome_is_hidden_until_a_test(render: Callable[[], ft.Column]) -> None:
    """Before a tap, the outcome line says nothing and is hidden."""
    assert outcome(render()) is None


async def test_a_test_schedules_8999_in_5_s_with_the_kind_s_route(
    render: Callable[[], ft.Column], os: MemoryNotifications
) -> None:
    """Allowed and on: id 8999, exact, about 5 s from now, its payload the kind's route."""
    before = datetime.now(UTC)
    await tap(render, "developer.test_reminder.lightning")
    reminder = os.pending[TEST_ID]
    assert reminder.payload == "/more/lightning-talks"
    assert reminder.mode == AndroidScheduleMode.EXACT_ALLOW_WHILE_IDLE
    assert 4.9 <= (reminder.when - before).total_seconds() <= 6
    column = render()
    assert outcome(column) == (
        "Scheduled: it shows in about 5 s. Tapping it opens Lightning talks."
    )
    assert outcome_ok(column)


@pytest.mark.parametrize(
    ("key", "route"),
    [
        ("session", "/my-schedule"),
        ("open_space", "/more/open-spaces"),
        ("keynote", "/more/keynotes"),
    ],
)
async def test_each_kind_opens_its_own_page(
    render: Callable[[], ft.Column], os: MemoryNotifications, key: str, route: str
) -> None:
    """Each kind's test reminder carries the route its real reminders are about."""
    await tap(render, f"developer.test_reminder.{key}")
    assert os.pending[TEST_ID].payload == route


async def test_it_is_due_by_the_real_clock_not_the_fake_one(
    render: Callable[[], ft.Column], os: MemoryNotifications
) -> None:
    """With a fake clock set, the reminder is still due 5 s from the real time."""
    clock.start_fake_clock(datetime(2026, 5, 15, 9, 0, tzinfo=UTC))
    try:
        await tap(render, "developer.test_reminder.keynote")
    finally:
        clock.start_fake_clock(None)
    delay = os.pending[TEST_ID].when - datetime.now(UTC)
    assert 0 < delay.total_seconds() <= 6


async def test_a_slow_exact_alarm_check_still_leaves_it_5_s_ahead(
    render: Callable[[], ft.Column],
    os: MemoryNotifications,
    scheduler: Scheduler,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Its time is taken after the exact-alarm check: a 6 s check doesn't make it past.

    The real clock is controlled, the check moves it on 6 s, and the OS refuses a time
    already past, as E3 does.
    """
    now = [datetime(2026, 5, 15, 9, 0, tzinfo=UTC)]

    class RealClock(datetime):
        """`datetime` whose `now()` is the controlled time."""

        @classmethod
        def now(cls, tz: Any = None) -> RealClock:  # type: ignore[override]
            """Return the controlled time."""
            return cast(RealClock, now[0])

    async def slow_check() -> bool:
        """Allow exact alarms after 6 s of the controlled clock."""
        now[0] += timedelta(seconds=6)
        return True

    schedule = os.schedule

    async def refuse_past(id: int, *, when: datetime, **kwargs: Any) -> None:
        """Refuse a time already past, as E3 does; else schedule it."""
        if when <= now[0]:
            raise NotificationException("invalid_date: in the past")
        await schedule(id, when=when, **kwargs)

    monkeypatch.setattr(developer_reminders, "datetime", RealClock)
    monkeypatch.setattr(scheduler, "exact_allowed", slow_check)
    monkeypatch.setattr(os, "schedule", refuse_past)
    await tap(render, "developer.test_reminder.keynote")
    assert os.pending[TEST_ID].when - now[0] == timedelta(seconds=5)
    assert str(outcome(render())).startswith("Scheduled: it shows in about 5 s.")


async def test_without_exact_alarms_it_is_inexact_and_says_it_may_be_late(
    render: Callable[[], ft.Column], os: MemoryNotifications
) -> None:
    """Exact alarms not allowed: scheduled inexact, with a warning that says so."""
    os.exact = False
    await tap(render, "developer.test_reminder.open_space")
    assert os.pending[TEST_ID].mode == AndroidScheduleMode.INEXACT_ALLOW_WHILE_IDLE
    column = render()
    assert outcome(column) == (
        "Scheduled, but Alarms & reminders isn't allowed, so it may come late. "
        "Tapping it opens Open spaces."
    )
    assert not outcome_ok(column)


async def test_an_exact_alarm_refused_is_scheduled_inexact(
    render: Callable[[], ft.Column], os: MemoryNotifications
) -> None:
    """Android refuses the exact alarm it said it allowed: inexact all the same."""
    os.refuse_exact = True
    await tap(render, "developer.test_reminder.open_space")
    assert os.pending[TEST_ID].mode == AndroidScheduleMode.INEXACT_ALLOW_WHILE_IDLE
    assert str(outcome(render())).startswith("Scheduled, but")


async def test_a_refused_reminder_says_it_was_not_scheduled(
    render: Callable[[], ft.Column], os: MemoryNotifications
) -> None:
    """The OS refuses the reminder: nothing pending, and the line says so."""
    os.failing_ids = {TEST_ID}
    await tap(render, "developer.test_reminder.keynote")
    assert TEST_ID not in os.pending
    assert outcome(render()) == (
        "Couldn't schedule it: the system refused. The log says why."
    )


@pytest.mark.parametrize(
    ("settings", "key", "words"),
    [
        (
            ReminderSettings(session_lead=0),
            "session",
            "Not scheduled: session reminders are off in Settings.",
        ),
        (
            ReminderSettings(lightning=False),
            "lightning",
            "Not scheduled: lightning talk reminders are off in Settings.",
        ),
        (
            ReminderSettings(open_space=False),
            "open_space",
            "Not scheduled: open space reminders are off in Settings.",
        ),
        (
            ReminderSettings(keynote=False),
            "keynote",
            "Not scheduled: keynote reminders are off in Settings.",
        ),
    ],
)
async def test_a_kind_turned_off_is_muted(
    monkeypatch: pytest.MonkeyPatch,
    scheduler: Scheduler,
    os: MemoryNotifications,
    settings: ReminderSettings,
    key: str,
    words: str,
) -> None:
    """A kind the user turned off schedules nothing and says it is off."""
    render = renderer(monkeypatch, scheduler, Prefs(reminders=settings, loaded=True))
    await tap(render, f"developer.test_reminder.{key}")
    assert os.pending == {}
    assert outcome(render()) == words


@pytest.mark.parametrize(
    ("status", "words"),
    [
        (
            PermissionStatus.DENIED,
            "Not scheduled: this app's notifications aren't allowed yet.",
        ),
        (
            PermissionStatus.PERMANENTLY_DENIED,
            "Not scheduled: this app's notifications are off in system settings.",
        ),
        (None, "Not scheduled: couldn't read whether notifications are allowed."),
    ],
)
async def test_notifications_not_allowed_are_denied(
    render: Callable[[], ft.Column],
    os: MemoryNotifications,
    permissions: MemoryPermissions,
    status: PermissionStatus | None,
    words: str,
) -> None:
    """The OS doesn't show the app's notifications: nothing scheduled, and why."""
    permissions.status = status
    await tap(render, "developer.test_reminder.lightning")
    assert os.pending == {}
    column = render()
    assert outcome(column) == words
    assert not outcome_ok(column)


async def test_denied_is_said_before_muted(
    monkeypatch: pytest.MonkeyPatch,
    scheduler: Scheduler,
    os: MemoryNotifications,
    permissions: MemoryPermissions,
) -> None:
    """Both denied and off: the OS's answer comes first, since Settings can't fix it."""
    permissions.status = PermissionStatus.PERMANENTLY_DENIED
    off = Prefs(reminders=ReminderSettings(session_lead=0), loaded=True)
    render = renderer(monkeypatch, scheduler, off)
    await tap(render, "developer.test_reminder.session")
    assert outcome(render()) == (
        "Not scheduled: this app's notifications are off in system settings."
    )


async def test_ios_reads_whether_notifications_show_from_e3(
    monkeypatch: pytest.MonkeyPatch, os: MemoryNotifications, prefs: Prefs
) -> None:
    """On iOS, E3's answer decides: notifications off is denied, on schedules."""
    ios = Scheduler(cast(Notifications, os), None, android=False)
    render = renderer(monkeypatch, ios, prefs)
    os.enabled = False
    await tap(render, "developer.test_reminder.keynote")
    assert os.pending == {}
    assert str(outcome(render())).endswith("aren't allowed yet.")
    os.enabled = True
    await tap(render, "developer.test_reminder.keynote")
    assert os.pending[TEST_ID].payload == "/more/keynotes"


def test_without_e3_every_row_is_disabled_and_says_why(
    monkeypatch: pytest.MonkeyPatch, prefs: Prefs
) -> None:
    """The companion app: each row disabled, its second line "Not available…"."""
    column = renderer(monkeypatch, None, prefs)()
    for identifier in ROWS:
        assert row(column, identifier).disabled is True
        assert subtitle(column, identifier) == UNAVAILABLE
    assert outcome(column) is None


def test_with_e3_each_row_says_what_a_tap_on_its_reminder_opens(
    render: Callable[[], ft.Column],
) -> None:
    """Each enabled row's second line names when it shows and what it opens."""
    column = render()
    assert subtitle(column, "developer.test_reminder.session") == (
        "Shows in 5 s; tapping it opens My schedule"
    )
    assert row(column, "developer.test_reminder.session").disabled is False
