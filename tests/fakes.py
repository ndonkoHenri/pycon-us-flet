"""Fakes shared by the tests: stand-ins for the Flutter side of Flet services.

And ``QueuedWrite``, a feed cache write held in its worker thread; and stand-ins for
E3's ``Notifications`` and the permission handler, which take no page. The page, its
device and the hooks are ``tests/fake_page.py``'s (#623).
"""

import asyncio
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import flet as ft
import pytest
from flet_notifications import (
    AndroidScheduleMode,
    NotificationException,
    NotificationPermissionException,
)
from flet_permission_handler import Permission, PermissionStatus

from pycon_us.services import storage


class MemoryPrefs(ft.SharedPreferences):
    """SharedPreferences backed by a dict instead of the Flutter side.

    Only the transport is replaced, so Flet's own type check in ``set`` still runs.
    """

    def init(self) -> None:
        """Start empty, with writes and removes that succeed and no error."""
        self.values: dict[str, Any] = {}
        self.fail_writes = False
        self.fail_removes = False  # `remove` answers False, as a failed commit does
        self.error: Exception | None = None

    async def _invoke_method(
        self,
        method_name: str,
        arguments: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        """Answer ``get``, ``set``, ``get_keys`` and ``remove`` from ``values``.

        A set answers False while ``fail_writes`` is set, a remove while
        ``fail_removes`` is; ``error``, when given, is raised by every call.
        """
        assert arguments is not None
        if self.error is not None:
            raise self.error
        if method_name == "get":
            return self.values.get(arguments["key"])
        if method_name == "set":
            if self.fail_writes:
                return False
            self.values[arguments["key"]] = arguments["value"]
            return True
        if method_name == "get_keys":
            prefix = arguments["key_prefix"]
            return [key for key in self.values if key.startswith(prefix)]
        if method_name == "remove":
            if self.fail_removes:
                return False
            return self.values.pop(arguments["key"], None) is not None
        raise AssertionError(f"unexpected call {method_name}")


class MemorySemantics(ft.SemanticsService):
    """SemanticsService whose accessibility features come from a dict, not the platform.

    Announcements are recorded in ``announced`` instead of reaching a screen reader.
    """

    def init(self) -> None:
        """Start with every feature off, no error and nothing read or announced."""
        self.features: dict[str, bool] = dict.fromkeys(
            (
                "accessible_navigation",
                "bold_text",
                "disable_animations",
                "high_contrast",
                "invert_colors",
                "reduce_motion",
                "on_off_switch_labels",
                "supports_announcements",
            ),
            False,
        )
        self.error: Exception | None = None
        self.reads = 0
        self.announced: list[str] = []

    async def _invoke_method(
        self,
        method_name: str,
        arguments: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        """Record an announcement, or answer the features and count the read.

        ``error``, when given, is raised by a read, after it is counted.
        """
        if method_name == "announce_message":
            self.announced.append((arguments or {})["message"])
            return None
        if method_name != "get_accessibility_features":
            raise AssertionError(f"unexpected call {method_name}")
        self.reads += 1
        if self.error is not None:
            raise self.error
        return dict(self.features)


class MemoryHaptics(ft.HapticFeedback):
    """HapticFeedback that records the effects asked for instead of reaching a device."""

    def init(self) -> None:
        """Start with no effect recorded and no error."""
        self.effects: list[str] = []
        self.error: Exception | None = None

    async def _invoke_method(
        self,
        method_name: str,
        arguments: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        """Record the effect's method name, or raise ``error`` when given."""
        if self.error is not None:
            raise self.error
        self.effects.append(method_name)


class MemoryLauncher(ft.UrlLauncher):
    """UrlLauncher that records what it was asked to open instead of opening it."""

    def init(self) -> None:
        """Start with nothing launched and no error."""
        self.launched: list[tuple[str, ft.LaunchMode]] = []
        self.error: Exception | None = None

    async def launch_url(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, url: str, *, mode: ft.LaunchMode = ft.LaunchMode.PLATFORM_DEFAULT
    ) -> None:
        """Record the URL and its mode, or raise ``error`` when given."""
        if self.error is not None:
            raise self.error
        self.launched.append((url, mode))


class MemoryClipboard(ft.Clipboard):
    """Clipboard that keeps what was copied instead of reaching the platform."""

    def init(self) -> None:
        """Start with nothing copied and no error."""
        self.value: str | None = None
        self.error: Exception | None = None

    async def set(self, value: str) -> None:
        """Keep ``value`` as what was copied, or raise ``error`` when given."""
        if self.error is not None:
            raise self.error
        self.value = value


class MemoryShare(ft.Share):
    """Share that records the files and texts it was asked to share instead of a sheet."""

    def init(self) -> None:
        """Start with nothing shared, a successful status, no error and no gate."""
        self.shared: list[list[ft.ShareFile]] = []
        self.file_options: list[dict[str, Any]] = []  # each share_files' options
        self.texts: list[tuple[str, dict[str, Any]]] = []
        self.status = ft.ShareResultStatus.SUCCESS
        self.error: Exception | None = None
        # When given, a text's sheet stays up until the test sets the event.
        self.gate: asyncio.Event | None = None

    async def share_text(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, text: str, **options: Any
    ) -> ft.ShareResult:
        """Record the text and its options, then answer ``status`` once any gate is set.

        ``error``, when given, is raised before anything is recorded.
        """
        if self.error is not None:
            raise self.error
        self.texts.append((text, options))
        if self.gate is not None:
            await self.gate.wait()
        return ft.ShareResult(status=self.status, raw="")

    async def share_files(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, files: list[ft.ShareFile], **options: Any
    ) -> ft.ShareResult:
        """Record the files and their options and answer ``status``, or raise ``error``."""
        if self.error is not None:
            raise self.error
        self.shared.append(files)
        self.file_options.append(options)
        return ft.ShareResult(status=self.status, raw="")


class MemoryFilePicker(ft.FilePicker):
    """FilePicker whose save dialog records the file instead of reaching the platform."""

    def init(self) -> None:
        """Start with nothing saved, a save that succeeds, no error and no gate."""
        self.saved: list[tuple[str | None, bytes | None]] = []
        # What the dialog answers: an opaque document path, or None for a cancel.
        self.answer: str | None = "/document/12"
        self.error: Exception | None = None
        # When given, the dialog stays up until the test sets the event.
        self.gate: asyncio.Event | None = None

    async def save_file(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, **options: Any
    ) -> str | None:
        """Record the file's name and bytes, then answer ``answer`` once any gate is set.

        ``error``, when given, is raised before anything is recorded.
        """
        if self.error is not None:
            raise self.error
        self.saved.append((options.get("file_name"), options.get("src_bytes")))
        if self.gate is not None:
            await self.gate.wait()
        return self.answer


class MemoryPaths(ft.StoragePaths):
    """StoragePaths whose console log is a path the test chooses."""

    def init(self) -> None:
        """Start with an empty console log path and no error."""
        self.console_log = ""
        self.error: Exception | None = None

    async def get_console_log_filename(self) -> str:
        """Return ``console_log``, or raise ``error`` when given."""
        if self.error is not None:
            raise self.error
        return self.console_log


class QueuedWrite:
    """Holds the feed cache's write in its worker thread, before the writers' lock.

    That lock gives the threads turns, not order: a deletion asked for after the write
    takes the lock first unless ``Storage.delete_feed`` waits for the write (D-244).
    """

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Patch ``storage.write_atomic`` to hold each write until ``release()``.

        Each wait gives up after 5 s, so a test that never releases cannot hang.
        """
        self._queued = threading.Event()
        self._go = threading.Event()
        write = storage.write_atomic

        def held(path: Path, data: bytes) -> None:
            self._queued.set()
            self._go.wait(5)
            write(path, data)

        monkeypatch.setattr(storage, "write_atomic", held)

    async def queued(self) -> None:
        """Wait until a write's worker is held."""
        await asyncio.to_thread(self._queued.wait, 5)

    def release(self) -> None:
        """Let the held worker take the lock and write."""
        self._go.set()


@dataclass(frozen=True)
class Scheduled:
    """One reminder ``MemoryNotifications`` holds pending, as ``schedule()`` got it."""

    when: datetime
    title: str | None
    body: str | None
    payload: str | None
    mode: AndroidScheduleMode


class MemoryNotifications:
    """E3's ``Notifications`` without a page or a platform: pending reminders in a dict.

    Not a subclass: the service's methods check the page's platform before the
    bridge. It answers the calls ``services.reminders.Scheduler`` makes, records them
    in ``calls``, and fails as a test sets it.
    """

    def __init__(self) -> None:
        """Start with nothing pending, exact alarms allowed and every call succeeding."""
        self.pending: dict[int, Scheduled] = {}
        self.calls: list[str] = []
        self.exact = True  # what can_schedule_exact_alarms() answers
        self.refuse_exact = False  # an exact schedule raises, as without the access
        self.errors: dict[str, Exception] = {}  # method name -> what it raises
        self.failing_ids: set[int] = set()  # schedule() raises for these ids
        self.gate: asyncio.Event | None = None  # schedule() waits on it when given
        self.enabled = False  # whether the OS shows notifications, not asked yet
        self.grant = True  # what the user answers the OS's prompt
        self.requests: list[dict[str, bool]] = []  # request_permissions()' arguments

    def _call(self, method: str) -> None:
        """Record the call to ``method``, and raise its error when a test set one."""
        self.calls.append(method)
        if method in self.errors:
            raise self.errors[method]

    async def are_notifications_enabled(self) -> bool:
        """Answer ``enabled``."""
        self._call("are_notifications_enabled")
        return self.enabled

    async def request_permissions(
        self,
        *,
        alert: bool = True,
        sound: bool = True,
        badge: bool = True,
        critical: bool = False,
        provisional: bool = False,
    ) -> bool:
        """Record the request; the user answers ``grant``, which ``enabled`` becomes."""
        self._call("request_permissions")
        self.requests.append(
            {
                "alert": alert,
                "sound": sound,
                "badge": badge,
                "critical": critical,
                "provisional": provisional,
            }
        )
        self.enabled = self.grant
        return self.grant

    async def can_schedule_exact_alarms(self) -> bool:
        """Answer ``exact``."""
        self._call("can_schedule_exact_alarms")
        return self.exact

    async def cancel_all_pending(self) -> None:
        """Drop every pending reminder."""
        self._call("cancel_all_pending")
        self.pending.clear()

    async def schedule(
        self,
        id: int,
        *,
        when: datetime,
        title: str | None = None,
        body: str | None = None,
        payload: str | None = None,
        schedule_mode: AndroidScheduleMode,
    ) -> None:
        """Hold the reminder as pending under ``id``, replacing one with the same id."""
        self._call("schedule")
        if self.gate is not None:
            await self.gate.wait()
        exact = schedule_mode != AndroidScheduleMode.INEXACT_ALLOW_WHILE_IDLE
        if self.refuse_exact and exact:
            raise NotificationPermissionException("exact alarms are not permitted")
        if id in self.failing_ids:
            raise NotificationException(f"operation_failed: {id}")
        self.pending[id] = Scheduled(when, title, body, payload, schedule_mode)


class MemoryPermissions:
    """``flet-permission-handler``'s service, answering one status for every permission."""

    def __init__(self, status: PermissionStatus | None) -> None:
        """Answer ``status``, and count the reads in ``reads``."""
        self.status = status
        self.reads = 0

    async def get_status(self, permission: Permission) -> PermissionStatus | None:
        """Return ``status`` for any ``permission``."""
        self.reads += 1
        return self.status
