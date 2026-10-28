"""Fakes for code that runs outside a renderer: the page, its device and the hooks (#623).

``FakePage`` stands in for ``ft.Page`` and ``bound()`` binds it as Flet binds a session's
page; ``android_device()`` and ``ios_device()`` make the device a page reports; ``Hooks``
answers the hooks a builder calls, and ``phone_margin()`` stands in for
``use_margin()``. The services' fakes are ``tests/fakes.py``'s.
"""

import dataclasses
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, cast

import flet as ft

# Private: Flet has no public way to bind a page (its own pytest plugin sets this too).
# Checked against the .flet-ref pin 08b89cce5 (#445); switch when #160's binding lands.
from flet.controls.context import _context_page

from pycon_us.theme import LIGHT_TOKENS, Tokens


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
        self.package: ft.PackageInfo | None = None
        self.package_error: Exception | None = None
        self.package_reads = 0
        self.controls: dict[int, ft.BaseControl] = {}

    def get_control(self, id: int) -> ft.BaseControl | None:
        """Return the control mounted under ``id``: ``controls``, which the test fills."""
        return self.controls.get(id)

    async def get_device_info(self) -> ft.DeviceInfo | None:
        """Return ``device``, or raise ``device_error``, as the Flutter side would."""
        if self.device_error is not None:
            raise self.device_error
        return self.device

    async def get_package_info(self) -> ft.PackageInfo:
        """Return ``package``, or raise ``package_error``, counting the reads."""
        self.package_reads += 1
        if self.package_error is not None:
            raise self.package_error
        assert self.package is not None, "the test sets the package info first"
        return self.package

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


def phone_margin(cap: float) -> float:
    """``use_margin()``'s stand-in: a phone's, no side margin at any width class (D-305)."""
    return 0.0
