"""A stand-in for `ft.InteractiveViewer`'s methods, for the zoom layer's tests (#388).

No Flutter answers a viewer in a test session: `FakeViewer` keeps the transform as
Flutter does at the pin (F76: `zoom()` keeps the translation, `pan()` moves in the
plan's units) and records each call, for the floor viewer's and the expo's tests.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import flet as ft
import pytest


@dataclass
class FakeViewer:
    """The `InteractiveViewer`'s methods as the pin has them, and what was asked."""

    scale: float = 1.0
    x: float = 0.0
    y: float = 0.0
    calls: list[tuple[str, Any]] = field(default_factory=list)
    """Each method called, with its argument, in order."""
    after_zoom: Callable[[], Awaitable[None]] | None = None
    """What Flutter does once a zoom lands, e.g. report the transform (a render)."""
    hold: asyncio.Event | None = None
    """When set, `reset()` waits for it: Flutter's answer held while the app goes on."""

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Put this fake's methods on `ft.InteractiveViewer` for the test."""
        fake = self

        async def zoom_(viewer: ft.InteractiveViewer, factor: float) -> None:
            assert viewer.page  # a detached viewer raises, as on a device
            fake.calls.append(("zoom", factor))
            top = float(viewer.max_scale)
            fake.scale = min(top, max(1.0, fake.scale * factor))  # t stays (F76)
            if fake.after_zoom is not None:
                await fake.after_zoom()

        async def pan(viewer: ft.InteractiveViewer, dx: float, dy: float = 0) -> None:
            assert viewer.page
            fake.calls.append(("pan", (dx, dy)))
            fake.x += fake.scale * dx  # the plan's units (F76)
            fake.y += fake.scale * dy

        async def reset(
            viewer: ft.InteractiveViewer, animation_duration: Any = None
        ) -> None:
            fake.calls.append(("reset", animation_duration))
            if fake.hold is not None:
                await fake.hold.wait()
            fake.scale, fake.x, fake.y = 1.0, 0.0, 0.0

        async def get_transform(
            viewer: ft.InteractiveViewer,
        ) -> ft.InteractiveViewerTransform:
            assert viewer.page
            return ft.InteractiveViewerTransform(
                scale=fake.scale,
                translation_x=fake.x,
                translation_y=fake.y,
                translation_z=0.0,
                matrix=[],
            )

        monkeypatch.setattr(ft.InteractiveViewer, "zoom", zoom_)
        monkeypatch.setattr(ft.InteractiveViewer, "pan", pan)
        monkeypatch.setattr(ft.InteractiveViewer, "reset", reset)
        monkeypatch.setattr(ft.InteractiveViewer, "get_transform", get_transform)

    def plan_point(self, focus: tuple[float, float]) -> tuple[float, float]:
        """The plan's point under a point of the viewer."""
        return (focus[0] - self.x) / self.scale, (focus[1] - self.y) / self.scale
