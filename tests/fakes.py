"""Fakes shared by the tests: stand-ins for the Flutter side of Flet services and the page.

And ``QueuedWrite``, a feed cache write held in its worker thread.
"""

import asyncio
import dataclasses
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

import flet as ft
import pytest

# Private: Flet has no public way to bind a page (its own pytest plugin sets this too).
# Checked against the .flet-ref pin 15854a0ac; switch when #160's binding lands.
from flet.controls.context import _context_page

from pycon_us.services import storage
from pycon_us.theme import LIGHT_TOKENS, Tokens


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


class FakePage:
    """The few ``ft.Page`` fields the start sequence, the scaffold and ``report_errors`` use.

    Tests pass it as ``cast(ft.Page, FakePage())``: a real page needs a session.
    """

    def __init__(self, brightness: ft.Brightness = ft.Brightness.LIGHT) -> None:
        """Start at ``/`` on iOS in ``brightness``, with nothing navigated or shown."""
        self.route = "/"
        self.width: float | None = None
        self.height: float | None = None
        self.navigated: list[str] = []
        self.media: ft.PageMediaData | None = None
        self.platform_brightness = brightness
        self.theme: ft.Theme | None = None
        self.dark_theme: ft.Theme | None = None
        self.theme_mode: ft.ThemeMode | None = None
        self.theme_animation_style: ft.AnimationStyle | None = None
        self.on_platform_brightness_change: Any = None
        self.on_app_lifecycle_state_change: Any = None
        self.on_close: Any = None
        self.on_media_change: Any = None
        self.on_resize: Any = None
        self.dialogs: list[ft.DialogControl] = []
        self.platform = ft.PagePlatform.IOS
        self.device: ft.DeviceInfo | None = None
        self.device_error: Exception | None = None
        self.controls: dict[int, ft.BaseControl] = {}

    def get_control(self, id: int) -> ft.BaseControl | None:
        """Return the control mounted under ``id``: ``controls``, which the test fills."""
        return self.controls.get(id)

    async def get_device_info(self) -> ft.DeviceInfo | None:
        """Return ``device``, or raise ``device_error``, as the Flutter side would."""
        if self.device_error is not None:
            raise self.device_error
        return self.device

    def show_dialog(self, dialog: ft.DialogControl) -> None:
        """Record ``dialog`` in ``dialogs`` instead of showing it."""
        self.dialogs.append(dialog)

    def navigate(self, location: str) -> None:
        """Go to a location, as ``page.navigate`` does: the route changes at once."""
        self.navigated.append(location)
        self.route = location


@contextmanager
def bound(page: FakePage) -> Iterator[ft.Page]:
    """Bind ``page`` to ``ft.context.page``, as Flet does while a handler or effect runs."""
    token = _context_page.set(cast(ft.Page, page))  # pyright: ignore[reportArgumentType]
    try:
        yield cast(ft.Page, page)
    finally:
        _context_page.reset(token)


def android_device(
    sdk: int,
    *,
    manufacturer: str = "",
    model: str = "",
    release: str = "",
    physical: bool = False,
) -> ft.AndroidDeviceInfo:
    """An Android device on API level ``sdk``, with the make, model and release given.

    Every other field is blank.
    """
    version = ft.AndroidBuildVersion(
        code_name="REL", incremental="", release=release, sdk=sdk
    )
    return ft.AndroidDeviceInfo(
        **blank_fields(
            ft.AndroidDeviceInfo,
            "version",
            "manufacturer",
            "model",
            "is_physical_device",
        ),
        version=version,
        manufacturer=manufacturer,
        model=model,
        is_physical_device=physical,
    )  # pyright: ignore[reportArgumentType]


def ios_device(
    model_name: str, system_version: str, *, physical: bool = False
) -> ft.IosDeviceInfo:
    """An iOS device of ``model_name`` on ``system_version``; every other field is blank."""
    utsname = ft.IosUtsname(
        machine="", node_name="", release="", sys_name="", version=""
    )
    return ft.IosDeviceInfo(
        **blank_fields(
            ft.IosDeviceInfo,
            "utsname",
            "model_name",
            "system_name",
            "system_version",
            "is_physical_device",
        ),
        utsname=utsname,
        model_name=model_name,
        system_name="iOS",
        system_version=system_version,
        is_physical_device=physical,
    )  # pyright: ignore[reportArgumentType]


def blank_fields(cls: type, *given: str) -> dict[str, object]:
    """Return a blank value for each field of ``cls`` with a default-less str, int, bool or list.

    The fields named in ``given``, and those with a default, are left out.
    """
    blank: dict[object, object] = {str: "", int: 0, bool: False}
    return {
        field.name: blank.get(field.type, [])
        for field in dataclasses.fields(cls)
        if field.name not in given
        and field.default is dataclasses.MISSING
        and field.default_factory is dataclasses.MISSING
    }


@dataclasses.dataclass
class Hooks:
    """The hooks the builders call, answered by the test instead of a renderer."""

    view_path: str = "/now"
    tokens: Tokens = LIGHT_TOKENS
    """What ``use_tokens()`` returns: the scheme on screen (D-150)."""
    effects: list[tuple[Callable[[], Any], list[Any] | None]] = dataclasses.field(
        default_factory=list
    )
    cleanups: list[Callable[[], Any] | None] = dataclasses.field(default_factory=list)
    state: Any = None
    wide: bool = False
    """The window class ``AppScaffold`` sees: True from 600 dp, the rail (D-277)."""
    renders: int = 0
    """How many re-renders a state setter asked for: only for a changed value."""

    def use_effect(
        self,
        setup: Callable[[], Any],
        dependencies: Any = None,
        cleanup: Callable[[], Any] | None = None,
    ) -> None:
        """Record the effect's setup, dependencies and cleanup without running them."""
        self.effects.append((setup, dependencies))
        self.cleanups.append(cleanup)

    def use_state(self, initial: Any) -> tuple[Any, Callable[[Any], None]]:
        """One state per test, set as Flet's setter sets it: unchanged, no render."""
        if self.state is None:
            self.state = initial() if callable(initial) else initial

        def set_state(value: Any) -> None:
            if value != self.state:
                self.state = value
                self.renders += 1

        return self.state, set_state

    def use_callback(self, fn: Callable[..., Any], dependencies: Any = None) -> Any:
        """Return ``fn`` itself: one render has nothing to keep it stable across."""
        return fn


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


def phone_margin(cap: float) -> float:
    """``use_margin()``'s stand-in: a phone's, no side margin at any width class (D-305)."""
    return 0.0
