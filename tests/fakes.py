"""Fakes shared by the tests: stand-ins for the Flutter side of Flet services and the page."""

import dataclasses
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, cast

import flet as ft

# Private: Flet has no public way to bind a page (its own pytest plugin sets this too).
# Checked against the .flet-ref pin 15854a0ac; switch when #160's binding lands.
from flet.controls.context import _context_page


class MemoryPrefs(ft.SharedPreferences):
    """SharedPreferences backed by a dict instead of the Flutter side.

    Only the transport is replaced, so Flet's own type check in ``set`` still runs.
    """

    def init(self) -> None:
        self.values: dict[str, Any] = {}
        self.fail_writes = False
        self.error: Exception | None = None

    async def _invoke_method(
        self,
        method_name: str,
        arguments: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
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
        raise AssertionError(f"unexpected call {method_name}")


class MemorySemantics(ft.SemanticsService):
    """SemanticsService whose accessibility features come from a dict, not the platform.

    Announcements are recorded in ``announced`` instead of reaching a screen reader.
    """

    def init(self) -> None:
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
        self.effects: list[str] = []
        self.error: Exception | None = None

    async def _invoke_method(
        self,
        method_name: str,
        arguments: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        if self.error is not None:
            raise self.error
        self.effects.append(method_name)


class MemoryLauncher(ft.UrlLauncher):
    """UrlLauncher that records what it was asked to open instead of opening it."""

    def init(self) -> None:
        self.launched: list[tuple[str, ft.LaunchMode]] = []
        self.error: Exception | None = None

    async def launch_url(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, url: str, *, mode: ft.LaunchMode = ft.LaunchMode.PLATFORM_DEFAULT
    ) -> None:
        if self.error is not None:
            raise self.error
        self.launched.append((url, mode))


class MemoryClipboard(ft.Clipboard):
    """Clipboard that keeps what was copied instead of reaching the platform."""

    def init(self) -> None:
        self.value: str | None = None
        self.error: Exception | None = None

    async def set(self, value: str) -> None:
        if self.error is not None:
            raise self.error
        self.value = value


class FakePage:
    """The few ``ft.Page`` fields the start sequence, the scaffold and ``report_errors`` use.

    Tests pass it as ``cast(ft.Page, FakePage())``: a real page needs a session.
    """

    def __init__(self, brightness: ft.Brightness = ft.Brightness.LIGHT) -> None:
        self.route = "/"
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
        self.dialogs: list[ft.DialogControl] = []
        self.platform = ft.PagePlatform.IOS
        self.device: ft.DeviceInfo | None = None
        self.device_error: Exception | None = None

    async def get_device_info(self) -> ft.DeviceInfo | None:
        """Return ``device``, or raise ``device_error``, as the Flutter side would."""
        if self.device_error is not None:
            raise self.device_error
        return self.device

    def show_dialog(self, dialog: ft.DialogControl) -> None:
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


def android_device(sdk: int) -> ft.AndroidDeviceInfo:
    """An Android device on API level ``sdk``; every other field is blank."""
    blank: dict[object, object] = {str: "", int: 0, bool: False}
    fields = {
        field.name: blank.get(field.type, [])
        for field in dataclasses.fields(ft.AndroidDeviceInfo)
        if field.name != "version"
    }
    version = ft.AndroidBuildVersion(
        code_name="REL", incremental="", release="", sdk=sdk
    )
    return ft.AndroidDeviceInfo(**fields, version=version)  # pyright: ignore[reportArgumentType]
