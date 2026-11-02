"""Tests for the reminders primer (``ui/reminder_primer.py``; D-61, D-395, #448).

The OS's answer so far (``Scheduler.access()``, ux.md §4.8) on each platform, and the
primer in a real Flet session of starred rows (``tests/row_sessions.py``) over the
fakes of ``tests/fakes.py``: the first star that adds shows it once, Allow asks the OS
and turns session reminders on when it allows, Not now and a dismissal remember "not
now", and nothing shows without E3, when the OS has answered, or after Undo.
"""

import dataclasses
import logging
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any, cast

import flet as ft
import pytest
from flet_notifications import NotificationException, Notifications
from flet_permission_handler import PermissionHandler, PermissionStatus

from pycon_us.config import YearData
from pycon_us.reminder_settings import ReminderSettings
from pycon_us.services import Services
from pycon_us.services.pref_keys import REMINDERS
from pycon_us.services.reminders import Access, Scheduler
from pycon_us.ui import focus_back
from pycon_us.ui.reminder_primer import PRIMER, PRIMER_LEAD
from pycon_us.ui.snack_bars import NOT_SAVED
from tests import harness, now_view, row_sessions
from tests.fakes import MemoryNotifications, MemoryPermissions
from tests.filter_sheet import descendants
from tests.row_sessions import Rendered, rendering
from tests.sessions import memory_services, text_of


def scheduler(
    notifications: MemoryNotifications,
    permissions: MemoryPermissions | None = None,
    *,
    android: bool = False,
) -> Scheduler:
    """Return a ``Scheduler`` over the fakes, typed as over the real services."""
    return Scheduler(
        cast(Notifications, notifications),
        cast(PermissionHandler | None, permissions),
        android=android,
    )


# ------------------------------------------------------------------ the OS's answer


@pytest.mark.parametrize(
    ("status", "access"),
    [
        (PermissionStatus.GRANTED, "allowed"),
        (PermissionStatus.LIMITED, "allowed"),
        (PermissionStatus.PROVISIONAL, "allowed"),
        (PermissionStatus.DENIED, "askable"),
        (PermissionStatus.PERMANENTLY_DENIED, "blocked"),
        (PermissionStatus.RESTRICTED, "blocked"),
        (None, "unknown"),
    ],
)
async def test_android_maps_the_permission_handlers_status(
    status: PermissionStatus | None, access: Access
) -> None:
    """On Android the handler's status decides, mapped as ux.md §4.8 says."""
    os = MemoryNotifications()
    assert await scheduler(os, MemoryPermissions(status), android=True).access() == (
        access
    )
    assert "are_notifications_enabled" not in os.calls


@pytest.mark.parametrize(("enabled", "access"), [(True, "allowed"), (False, "askable")])
async def test_ios_asks_e3_whose_no_may_still_be_asked(
    enabled: bool, access: Access
) -> None:
    """On iOS the handler always says denied (F17, F245): E3's yes or no answers."""
    os = MemoryNotifications()
    os.enabled = enabled
    permissions = MemoryPermissions(PermissionStatus.DENIED)
    assert await scheduler(os, permissions).access() == access
    assert permissions.reads == 0


async def test_an_unread_status_is_unknown_and_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failed read never raises: it is logged and reads as unknown."""
    os = MemoryNotifications()
    os.errors["are_notifications_enabled"] = NotificationException("operation_failed")
    with caplog.at_level(logging.WARNING, logger="pycon_us.services.reminders"):
        assert await scheduler(os).access() == "unknown"
    assert "notification permission unread" in caplog.text


async def test_the_request_asks_for_alerts_and_sounds_only() -> None:
    """E3 asks on both platforms, without a badge the app never sets (F17)."""
    os = MemoryNotifications()
    assert await scheduler(os).request_permission(asked=False)
    assert os.requests == [
        {
            "alert": True,
            "sound": True,
            "badge": False,
            "critical": False,
            "provisional": False,
        }
    ]


@pytest.mark.parametrize(
    ("asked", "android", "access"),
    [
        (True, True, "refused"),  # Android may have answered without a prompt (F259)
        (False, True, "askable"),  # Android shows its prompt twice
        (True, False, "askable"),  # iOS reads E3's answer, not the handler's
    ],
)
async def test_android_refusing_again_while_denied_reads_refused(
    asked: bool, android: bool, access: Access
) -> None:
    """A refusal after an earlier ask, with the status still denied, reads refused."""
    os = MemoryNotifications()
    os.enabled = os.grant = False
    permissions = MemoryPermissions(PermissionStatus.DENIED)
    shown = scheduler(os, permissions, android=android)
    assert await shown.access() == "askable"
    assert not await shown.request_permission(asked=asked)
    assert await shown.access() == access
    permissions.status = PermissionStatus.GRANTED  # turned on in system settings
    assert await shown.access() == ("allowed" if android else "askable")


async def test_a_failed_request_never_reads_blocked() -> None:
    """A request the bridge fails is no answer from Android: the OS may still ask."""
    os = MemoryNotifications()
    os.errors["request_permissions"] = NotificationException("operation_failed")
    shown = scheduler(os, MemoryPermissions(PermissionStatus.DENIED), android=True)
    assert not await shown.request_permission(asked=True)
    assert await shown.access() == "askable"


async def test_a_failed_request_reads_as_refused(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A request the bridge fails is logged and counts as a no."""
    os = MemoryNotifications()
    os.errors["request_permissions"] = NotificationException("operation_failed")
    with caplog.at_level(logging.WARNING, logger="pycon_us.services.reminders"):
        assert not await scheduler(os).request_permission(asked=False)
    assert "request failed" in caplog.text


# ------------------------------------------------------------------ the primer


@pytest.fixture
def os() -> MemoryNotifications:
    """The OS: notifications not asked yet, and a user who allows them when asked."""
    os = MemoryNotifications()
    os.enabled = False
    return os


@pytest.fixture
async def shown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, os: MemoryNotifications
) -> AsyncIterator[Rendered]:
    """Starred rows in a build with E3 (iOS's status path): the primer unasked."""

    def with_e3(year: YearData, directory: Path, memory: object = None) -> Services:
        svc = memory_services(year, directory)
        return dataclasses.replace(svc, reminders=scheduler(os))

    monkeypatch.setattr(harness, "memory_services", with_e3)
    async with rendering(tmp_path, monkeypatch) as rendered:
        yield rendered


def sheets(shown: Rendered) -> list[ft.BottomSheet]:
    """The bottom sheets in the page's dialog list, open or closed."""
    dialogs = shown.session.page._dialogs.controls  # pyright: ignore[reportPrivateUsage]
    return [d for d in dialogs if isinstance(d, ft.BottomSheet)]


def in_sheet(sheet: ft.BottomSheet, identifier: str) -> ft.Control:
    """The control under the sheet's semantics node ``identifier``."""
    [node] = [
        c
        for c in descendants(sheet)
        if isinstance(c, ft.Semantics) and c.identifier == identifier
    ]
    assert node.content is not None
    return node.content


def primer(shown: Rendered) -> ft.BottomSheet:
    """The one primer shown, open, saying ``PRIMER``."""
    [sheet] = sheets(shown)
    assert sheet.open
    assert text_of(in_sheet(sheet, "reminder.primer")) == PRIMER
    return sheet


async def answer(shown: Rendered, button: str) -> None:
    """Tap the primer's ``allow`` or ``not_now`` button."""
    control = in_sheet(primer(shown), f"reminder.primer.{button}")
    assert isinstance(control, ft.Button | ft.TextButton)
    await shown.click(control)


async def stored(shown: Rendered) -> ReminderSettings:
    """The reminder settings as written to storage (``pycon.reminders``)."""
    return ReminderSettings.from_stored(await shown.storage.get(REMINDERS))


async def test_the_first_star_shows_the_primer_after_saving(shown: Rendered) -> None:
    """A star that adds shows the primer, the session already saved (D-61)."""
    await shown.tap_star(row_sessions.TALK)
    primer(shown)
    assert shown.favorites.ids == {row_sessions.TALK}
    assert shown.filled(row_sessions.TALK)


async def test_allow_then_the_os_allows_turns_session_reminders_on(
    shown: Rendered, os: MemoryNotifications
) -> None:
    """Allow closes the sheet, asks the OS, and its yes turns on 10 minutes."""
    await shown.tap_star(row_sessions.TALK)
    sheet = primer(shown)
    await answer(shown, "allow")
    assert not sheet.open
    assert os.calls.count("request_permissions") == 1
    reminders = shown.prefs.reminders
    assert (reminders.primer, reminders.session_lead) == ("accepted", PRIMER_LEAD)
    assert await stored(shown) == reminders


async def test_allow_then_the_os_refuses_keeps_them_off(
    shown: Rendered, os: MemoryNotifications
) -> None:
    """The OS's no keeps session reminders off; the answer is still never asked again."""
    os.grant = False
    await shown.tap_star(row_sessions.TALK)
    await answer(shown, "allow")
    reminders = shown.prefs.reminders
    assert (reminders.primer, reminders.session_lead) == ("accepted", 0)
    assert shown.favorites.ids == {row_sessions.TALK}  # a denial never blocks it


async def test_not_now_asks_nothing_and_never_shows_again(
    shown: Rendered, os: MemoryNotifications
) -> None:
    """Not now keeps the favourite, asks the OS nothing, and is remembered."""
    await shown.tap_star(row_sessions.TALK)
    sheet = primer(shown)
    await answer(shown, "not_now")
    assert not sheet.open
    assert "request_permissions" not in os.calls
    assert shown.prefs.reminders == ReminderSettings(primer="not_now")
    assert shown.favorites.ids == {row_sessions.TALK}
    await shown.tap_star(row_sessions.CHARLA)  # the next first add shows nothing
    assert sheets(shown) == [sheet]


async def test_a_dismissal_counts_as_not_now(
    shown: Rendered, os: MemoryNotifications
) -> None:
    """A tap outside, a drag down or Back answers "not now", once."""
    await shown.tap_star(row_sessions.TALK)
    await shown.event(primer(shown), "dismiss", None)
    assert shown.prefs.reminders.primer == "not_now"
    assert "request_permissions" not in os.calls


async def test_a_buttons_close_is_one_answer(
    shown: Rendered, os: MemoryNotifications
) -> None:
    """The dismissal Flutter reports after Allow's close answers nothing more."""
    await shown.tap_star(row_sessions.TALK)
    sheet = primer(shown)
    await answer(shown, "allow")
    await shown.event(sheet, "dismiss", None)
    assert shown.prefs.reminders.primer == "accepted"
    assert os.calls.count("request_permissions") == 1


async def test_a_removal_and_its_undo_show_no_primer(shown: Rendered) -> None:
    """Only a star's add shows it: never a removal, nor the Undo that saves again."""
    shown.favorites.ids = frozenset({row_sessions.TALK})
    await shown.tap_star(row_sessions.TALK)
    undo = shown.snack_bars[-1].action
    assert isinstance(undo, ft.SnackBarAction)
    await shown.click(undo)
    assert shown.favorites.ids == {row_sessions.TALK}
    assert sheets(shown) == []


async def test_an_os_that_allows_already_has_nothing_to_ask(
    shown: Rendered, os: MemoryNotifications
) -> None:
    """Allowed already, as on Android 12: no primer, and nothing changes (ux.md §4.8)."""
    os.enabled = True
    await shown.tap_star(row_sessions.TALK)
    assert sheets(shown) == []
    assert shown.prefs.reminders == ReminderSettings()


async def test_two_quick_stars_show_one_primer(shown: Rendered) -> None:
    """A second first add while the primer is up shows no second sheet."""
    await shown.tap_star(row_sessions.TALK)
    await shown.tap_star(row_sessions.CHARLA)
    primer(shown)


async def test_an_unsaved_answer_says_so(shown: Rendered) -> None:
    """A failed write keeps the answer for the session and says so (D-120)."""
    await shown.tap_star(row_sessions.TALK)  # the favourite's own write succeeds
    shown.prefs_service.fail_writes = True
    await answer(shown, "not_now")
    assert shown.prefs.reminders.primer == "not_now"
    assert text_of(shown.snack_bars[-1].content) == NOT_SAVED


async def test_the_companion_app_shows_no_primer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without E3 (``Services.reminders`` None) a star shows nothing more (D-60)."""
    async with rendering(tmp_path, monkeypatch) as rendered:
        await rendered.tap_star(row_sessions.TALK)
        assert sheets(rendered) == []
        assert rendered.prefs.reminders == ReminderSettings()


# ------------------------------------------------------------------ the focus after it


@pytest.fixture
def focused(monkeypatch: pytest.MonkeyPatch) -> list[ft.IconButton]:
    """Record each ``IconButton.focus()`` call's button, at once after the answer."""
    calls: list[ft.IconButton] = []

    async def focus(self: ft.IconButton) -> None:
        calls.append(self)

    monkeypatch.setattr(ft.IconButton, "focus", focus)
    monkeypatch.setattr(focus_back, "SETTLE_SECONDS", 0)
    return calls


@pytest.fixture
def now_with_e3(monkeypatch: pytest.MonkeyPatch, os: MemoryNotifications) -> None:
    """Make ``render`` show Now in a build with E3 (iOS's status path)."""

    def with_e3(year: YearData, directory: Path, memory: object = None) -> Services:
        svc = memory_services(year, directory)
        return dataclasses.replace(svc, reminders=scheduler(os))

    monkeypatch.setattr(harness, "memory_services", with_e3)


render = now_view.render


@pytest.mark.parametrize("button", ["not_now", "allow"])
async def test_on_now_the_cards_star_gets_the_focus_back(
    now_with_e3: None,
    render: Callable[..., Any],
    focused: list[ft.IconButton],
    button: str,
) -> None:
    """The add moves the session into Your next session: its new star is focused.

    Up next's star is gone once the card shows the session, so Flutter has no node
    to give the focus back to (D-225); the card's star gets it once answered.
    """
    shown = await render(now_view.may(15, 11, 10))  # 27, at 11:30, is Up next's
    star = shown.node("now.favorite.27").content
    assert isinstance(star, ft.IconButton)
    await shown.click(star)
    assert shown.listed("now.next.session.") == ["27"]
    # Unmounted: no node for Flutter's refocus.
    assert shown.session.page.get_control(star._i) is None
    sheet = primer(cast(Rendered, shown))
    control = in_sheet(sheet, f"reminder.primer.{button}")
    await shown.click(control)
    assert focused == [shown.node("now.next.favorite.27").content]


async def test_a_star_still_mounted_is_left_to_flutter(
    shown: Rendered, focused: list[ft.IconButton]
) -> None:
    """A star that stayed (a Schedule row) gets the focus from Flutter, not twice."""
    await shown.tap_star(row_sessions.TALK)
    await answer(shown, "not_now")
    assert focused == []


async def test_a_sheet_taller_than_the_screen_scrolls_to_its_buttons(
    shown: Rendered,
) -> None:
    """At 200 % text in landscape the primer scrolls, so both buttons stay reachable.

    The sheet may take the screen's height (``scrollable``), not 9/16 of it, and its
    column scrolls inside a row of intrinsic height, so it is no taller than its
    content when that fits (ux.md §9).
    """
    await shown.tap_star(row_sessions.TALK)
    sheet = primer(shown)
    assert sheet.scrollable
    assert isinstance(sheet.content, ft.Container)
    row = sheet.content.content
    assert isinstance(row, ft.Row) and row.intrinsic_height
    [column] = row.controls
    assert isinstance(column, ft.Column)
    assert column.scroll == ft.ScrollMode.AUTO
    assert in_sheet(sheet, "reminder.primer.allow") in descendants(column)
