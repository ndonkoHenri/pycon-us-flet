"""Tests for E3's scheduling (``services/reminders.py``'s ``Scheduler``; #447, D-389).

Against ``tests/fakes.py``'s ``MemoryNotifications``, which keeps the pending reminders
by id as the OS does: what an apply cancels and schedules, in which Android mode, what
it does with each failure, and how a newer request supersedes an apply in flight
(D-220, D-221, D-222, D-120).
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import cast
from zoneinfo import ZoneInfo

import pytest
from flet_notifications import (
    AndroidScheduleMode,
    NotificationEvent,
    NotificationException,
    Notifications,
)
from flet_permission_handler import PermissionHandler, PermissionStatus

from pycon_us import capabilities
from pycon_us.services.reminders import Reminder, Scheduler, start
from tests.fakes import MemoryNotifications, MemoryPermissions, Scheduled
from tests.sessions import settle

ZONE = ZoneInfo("America/Los_Angeles")
"""2026's conference zone."""

AT = datetime(2027, 5, 14, 9, 0, tzinfo=ZONE)
"""When the first reminder of a plan fires."""

EXACT = AndroidScheduleMode.EXACT_ALLOW_WHILE_IDLE
"""The mode of an exact reminder (D-221)."""

INEXACT = AndroidScheduleMode.INEXACT_ALLOW_WHILE_IDLE
"""The mode of an inexact one."""


def reminders(*ids: int) -> list[Reminder]:
    """Return a plan of one reminder per id, a minute apart from ``AT``."""
    return [
        Reminder(
            id=reminder_id,
            at=AT + timedelta(minutes=index),
            title=f"Talk {reminder_id}",
            body="Starts at 9:10 AM · Room 103ABC",
            route=f"/my-schedule/session/{reminder_id}",
        )
        for index, reminder_id in enumerate(ids)
    ]


def scheduler(
    notifications: MemoryNotifications,
    permissions: MemoryPermissions | None = None,
    *,
    android: bool = True,
) -> Scheduler:
    """Return a ``Scheduler`` over the fakes, typed as over the real services."""
    return Scheduler(
        cast(Notifications, notifications),
        cast(PermissionHandler | None, permissions),
        android=android,
    )


@pytest.fixture
def os() -> MemoryNotifications:
    """The OS's pending reminders, with exact alarms allowed."""
    return MemoryNotifications()


async def test_it_cancels_the_pending_then_schedules_the_plan(
    os: MemoryNotifications,
) -> None:
    """One cancel of the pending ones first, then each reminder with its text and route."""
    os.pending[999] = Scheduled(AT, "Unsaved", None, None, INEXACT)  # an unsaved talk's
    assert await scheduler(os).apply(reminders(142, 8050), exact=False)
    assert os.calls == ["cancel_all_pending", "schedule", "schedule"]
    assert os.pending == {
        142: Scheduled(
            AT,
            "Talk 142",
            "Starts at 9:10 AM · Room 103ABC",
            "/my-schedule/session/142",
            INEXACT,
        ),
        8050: Scheduled(
            AT + timedelta(minutes=1),
            "Talk 8050",
            "Starts at 9:10 AM · Room 103ABC",
            "/my-schedule/session/8050",
            INEXACT,
        ),
    }


@pytest.mark.parametrize(("exact", "mode"), [(True, EXACT), (False, INEXACT)])
async def test_it_is_exact_only_when_allowed(
    os: MemoryNotifications, exact: bool, mode: AndroidScheduleMode
) -> None:
    """Every reminder is exact when Android allows it, and inexact otherwise (D-221)."""
    await scheduler(os).apply(reminders(142, 143), exact=exact)
    assert {r.mode for r in os.pending.values()} == {mode}


async def test_applying_twice_gives_the_same_pending_reminders(
    os: MemoryNotifications,
) -> None:
    """Applying is idempotent: the same plan again leaves the same reminders (D-222)."""
    plan = reminders(142, 143, 8050)
    await scheduler(os).apply(plan, exact=True)
    first = dict(os.pending)
    await scheduler(os).apply(plan, exact=True)
    assert os.pending == first


async def test_a_moved_session_keeps_its_id_and_takes_the_new_time(
    os: MemoryNotifications,
) -> None:
    """A moved session's reminder is replaced under its id: one, at the new time."""
    await scheduler(os).apply(reminders(142), exact=True)
    moved = [Reminder(142, AT + timedelta(minutes=15), "Talk 142", "", "/x")]
    await scheduler(os).apply(moved, exact=True)
    assert list(os.pending) == [142]
    assert os.pending[142].when == AT + timedelta(minutes=15)


async def test_an_exact_alarm_refused_is_scheduled_inexact_and_logged(
    os: MemoryNotifications, caplog: pytest.LogCaptureFixture
) -> None:
    """A refused exact alarm becomes inexact, as does the rest of the plan; never raised."""
    os.refuse_exact = True
    with caplog.at_level(logging.WARNING, logger="pycon_us.services.reminders"):
        assert await scheduler(os).apply(reminders(142, 143), exact=True)
    assert {r.mode for r in os.pending.values()} == {INEXACT}
    assert set(os.pending) == {142, 143}
    assert caplog.text.count("exact refused") == 1


async def test_failures_are_logged_and_the_rest_is_scheduled(
    os: MemoryNotifications, caplog: pytest.LogCaptureFixture
) -> None:
    """A failed cancel or reminder is logged; the others are scheduled (D-120)."""
    os.errors["cancel_all_pending"] = TimeoutError()
    os.failing_ids.add(143)
    with caplog.at_level(logging.WARNING, logger="pycon_us.services.reminders"):
        assert not await scheduler(os).apply(reminders(142, 143, 144), exact=False)
    assert set(os.pending) == {142, 144}
    assert "cancelling the pending ones failed" in caplog.text
    assert "143 not scheduled" in caplog.text


@pytest.mark.parametrize(
    ("plugin", "status", "warned"),
    [
        (True, PermissionStatus.GRANTED, False),
        (False, PermissionStatus.DENIED, False),
        (True, PermissionStatus.DENIED, True),
        (False, PermissionStatus.GRANTED, True),
    ],
)
async def test_exact_is_the_plugins_answer_checked_against_the_permission(
    os: MemoryNotifications,
    caplog: pytest.LogCaptureFixture,
    plugin: bool,
    status: PermissionStatus,
    warned: bool,
) -> None:
    """The plugin decides; a permission status that disagrees is a warning (D-220)."""
    os.exact = plugin
    with caplog.at_level(logging.WARNING, logger="pycon_us.services.reminders"):
        allowed = await scheduler(os, MemoryPermissions(status)).exact_allowed()
    assert allowed is plugin
    assert ("by the permission handler" in caplog.text) is warned


async def test_the_permission_is_not_compared_off_android(
    os: MemoryNotifications,
) -> None:
    """Off Android, which alone restricts exact alarms, only the plugin is asked."""
    permissions = MemoryPermissions(PermissionStatus.DENIED)
    assert await scheduler(os, permissions, android=False).exact_allowed()
    assert permissions.reads == 0


async def test_an_unanswered_exact_check_reads_as_inexact(
    os: MemoryNotifications, caplog: pytest.LogCaptureFixture
) -> None:
    """A failed check is logged and schedules inexact, which needs no access."""
    os.errors["can_schedule_exact_alarms"] = NotificationException("operation_failed")
    with caplog.at_level(logging.WARNING, logger="pycon_us.services.reminders"):
        assert not await scheduler(os).exact_allowed()
    assert "exact alarms unknown" in caplog.text


async def test_a_newer_request_supersedes_the_apply_in_flight(
    os: MemoryNotifications,
) -> None:
    """A request during an apply stops it; the loop applies the newer plan, which wins."""
    plans = iter([reminders(142, 143, 144), reminders(150)])
    closed = asyncio.Event()
    sched = scheduler(os)
    os.gate = asyncio.Event()  # the first schedule() waits
    sched.request()
    loop = asyncio.create_task(sched.keep_applied(lambda: next(plans), closed))
    await settle()
    assert os.calls == [
        "are_notifications_enabled",
        "can_schedule_exact_alarms",
        "cancel_all_pending",
        "schedule",
    ]
    sched.request()  # a favourite changed meanwhile
    os.gate.set()
    await settle()
    # The first apply stopped after its call in flight; the second replaced it all.
    assert os.calls.count("schedule") == 2
    assert list(os.pending) == [150]
    closed.set()
    sched.request()
    await asyncio.wait_for(loop, 1)


async def test_the_loop_returns_once_the_session_closes(
    os: MemoryNotifications,
) -> None:
    """A request after ``closed`` ends the loop without applying (D-147)."""
    closed = asyncio.Event()
    sched = scheduler(os)
    loop = asyncio.create_task(sched.keep_applied(lambda: reminders(142), closed))
    closed.set()
    sched.request()
    await asyncio.wait_for(loop, 1)
    assert os.calls == []


async def test_a_failed_plan_cancels_nothing(os: MemoryNotifications) -> None:
    """A planner that could not plan (None) leaves the pending reminders in place."""
    os.pending[142] = Scheduled(AT, "Talk 142", None, None, EXACT)
    closed = asyncio.Event()
    sched = scheduler(os)
    sched.request()
    loop = asyncio.create_task(sched.keep_applied(lambda: None, closed))
    await settle()
    assert "cancel_all_pending" not in os.calls
    assert list(os.pending) == [142]
    closed.set()
    sched.request()
    await asyncio.wait_for(loop, 1)


def test_the_companion_keeps_the_interim() -> None:
    """Without E3 in the build, as in the companion app, there is no Scheduler (D-63)."""
    assert not capabilities.REMINDERS  # pytest is not an embedded build
    assert start(None) is None


# ------------------------------------------------------------------ taps (#450, D-396)


ROUTE = "/my-schedule/session/142"
"""A session reminder's payload: its route."""


def test_a_tap_before_the_app_routes_is_held_for_start(os: MemoryNotifications) -> None:
    """Without ``navigate`` (the boot gate shut), a tap's route waits in ``tapped``."""
    sched = scheduler(os)
    sched.on_tap(NotificationEvent(name="tap", control=None, id=142, payload=ROUTE))  # pyright: ignore[reportArgumentType]
    assert sched.tapped == ROUTE
    assert sched.take_tap() == ROUTE
    assert sched.take_tap() == ""  # taken once


def test_a_tap_once_the_app_routes_navigates_at_once(os: MemoryNotifications) -> None:
    """With ``navigate`` set, a tap opens its route and holds nothing."""
    went: list[str] = []
    sched = scheduler(os)
    sched.navigate = went.append
    sched.open_tapped(ROUTE)
    assert went == [ROUTE]
    assert sched.tapped == ""


@pytest.mark.parametrize("payload", [None, "", "session/142", "https://example.com"])
def test_a_payload_that_is_no_route_opens_nothing(
    os: MemoryNotifications, payload: str | None, caplog: pytest.LogCaptureFixture
) -> None:
    """A tap whose payload is not a path from ``/`` is logged and goes nowhere."""
    went: list[str] = []
    sched = scheduler(os)
    sched.open_tapped(payload)
    sched.navigate = went.append
    sched.open_tapped(payload)
    assert (sched.tapped, went) == ("", [])
    assert "a tap without a route" in caplog.text


async def test_reading_whether_notifications_show(os: MemoryNotifications) -> None:
    """``read_enabled()`` keeps the OS's answer in ``enabled``."""
    sched = scheduler(os)
    assert not sched.enabled  # unknown until read
    assert await sched.read_enabled()
    assert sched.enabled
    os.enabled = False
    assert not await sched.read_enabled()
    assert not sched.enabled


async def test_a_failed_or_slow_read_reads_as_off(
    os: MemoryNotifications, caplog: pytest.LogCaptureFixture
) -> None:
    """A failed read, or one past its timeout, is logged and reads as False."""
    sched = scheduler(os)
    sched.enabled = True
    os.errors["are_notifications_enabled"] = NotificationException("not initialized")
    assert not await sched.read_enabled()
    os.errors.clear()
    os.initialized = asyncio.Event()  # E3 that never answers
    assert not await sched.read_enabled(0.01)
    assert caplog.text.count("whether notifications show is unknown") == 2


async def test_each_apply_reads_whether_notifications_show_first(
    os: MemoryNotifications,
) -> None:
    """The loop re-reads ``enabled`` before each apply, so a resume sees a new answer."""
    closed = asyncio.Event()
    sched = scheduler(os)
    os.enabled = False
    sched.request()
    loop = asyncio.create_task(sched.keep_applied(list, closed))
    await settle()
    assert os.calls[0] == "are_notifications_enabled"
    assert not sched.enabled
    os.enabled = True  # allowed in the system settings meanwhile
    sched.request()
    await settle()
    assert sched.enabled
    closed.set()
    sched.request()
    await asyncio.wait_for(loop, 1)
