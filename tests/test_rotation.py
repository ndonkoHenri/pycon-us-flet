"""A rotation across 600 dp keeps every screen re-rendering (#606).

A phone turned to landscape crosses M3's medium width class (D-09): the ``Layout``
store notifies, and every screen that reads it re-renders, the Views below the top
one too. A render that raises stops Flet's updates scheduler for the rest of the
session, without a log line (U111, #597): on #606's parent commit, ``use_margin()``
called ``ft.use_view_path()`` only in a wide window, so the crossing shifted the
caller's hooks, the Map under the floor viewer raised, and no screen rendered again.

Each test opens the app (``tests/links.py``'s ``open_at``: the real Router and screens
over the 2026 feed) and turns the window as an iPhone 17 does, 402 dp wide in portrait
and 874 dp in landscape. What the rail and the margins look like after a turn is
checked on the simulator (the PR).
"""

from typing import Any

import flet as ft
import pytest

from pycon_us.ui import zoom
from tests import links
from tests.links import Open, Shown
from tests.test_plan import FakeViewer

open_at = links.open_at

PORTRAIT = 402.0
"""An iPhone 17's width in portrait, in dp: a phone's class, the bottom bar."""

LANDSCAPE = 874.0
"""Its width in landscape: the medium class, the rail on a tab root (D-09)."""

PLAN_PORTRAIT = (402.0, 722.0)
"""The floor viewer's box in portrait on the iPhone 17 (#606's log)."""

PLAN_LANDSCAPE = (750.0, 326.0)
"""Its box in landscape, beside the notch and under the app bar."""

LOCATIONS = [
    "/now",
    "/now/wifi",
    "/schedule",
    "/my-schedule",
    "/map",
    "/map?tab=floor-plans",
    "/map/plan/concourse",
    "/map/room/grand-ballroom-a",
    "/more",
    "/more/speakers",
    "/more/tracks",
    "/more/tracks/talks",
    "/more/keynotes",
    "/more/open-spaces",
    "/more/lightning-talks",
    "/more/sprints",
    "/more/sponsors",
    "/more/sponsors/sponsor/bloomberg",
    "/more/settings",
    "/more/app",
    "/more/app/licences",
    "/more/developer",
    "/more/jobs",
    "/more/help",
    "/more/about",
    "/more/psf",
    "/more/social",
    "/more/venue",
    "/schedule/session/42",
    "/schedule/session/42/speaker/17",
    "/schedule/changes/2026",
    "/search",
    "/nope",
]
"""A location for each screen, root and pushed, with the Views each stacks below."""


def stopped(shown: Shown) -> str | None:
    """The error that stopped the session's updates scheduler, or None while it runs."""
    task: Any = shown.session._Session__updates_task  # pyright: ignore[reportAttributeAccessIssue]
    return repr(task.exception()) if task.done() else None


async def turn(shown: Shown, width: float) -> None:
    """Turn the window to ``width`` dp, as ``follow_width()`` hears a rotation."""
    shown.layout.set_width(width)
    await shown.settle()


@pytest.mark.parametrize("location", LOCATIONS)
async def test_a_rotation_and_back_stops_no_render(
    open_at: Open, location: str
) -> None:
    """Portrait, landscape, portrait: no screen's render raises, so Flet keeps going."""
    shown = await open_at(location)
    for width in (LANDSCAPE, PORTRAIT, LANDSCAPE):
        await turn(shown, width)
        assert stopped(shown) is None, f"at {width} dp"


class Viewer:
    """The floor viewer in the app's Views, with ``FakeViewer`` behind its methods."""

    def __init__(self, shown: Shown, fake: FakeViewer) -> None:
        """Hold the open app and the fake its viewer calls, which reports each zoom."""
        self.shown = shown
        self.fake = fake
        fake.after_zoom = self.transformed

    @property
    def layer(self) -> ft.InteractiveViewer:
        """The plan's one ``InteractiveViewer``."""
        (found,) = self.shown.find(ft.InteractiveViewer)
        return found

    @property
    def max_scale(self) -> float:
        """The maximum zoom the last render sent."""
        return float(self.layer.max_scale)

    def zoom_in_enabled(self) -> bool:
        """Whether the last render left Zoom in enabled."""
        button = self.shown.node("plan.zoom_in").content
        return not bool(button.disabled) if button is not None else False

    async def rotate(self, width: float, box: tuple[float, float]) -> None:
        """Turn the window, then report the viewer's new box, as Flutter does."""
        await turn(self.shown, width)
        (sized,) = [  # the zoom layer's box, around the double tap's detector
            c
            for c in self.shown.find(ft.Container)
            if isinstance(c.content, ft.GestureDetector)
            and isinstance(c.content.content, ft.InteractiveViewer)
        ]
        await self.shown.event(sized, "size_change", {"w": box[0], "h": box[1]})

    async def transformed(self) -> None:
        """Report the fake's transform, as ``on_transform_changed`` does."""
        f = self.fake
        data = {"s": f.scale, "tx": f.x, "ty": f.y, "tz": 0.0, "m": []}
        await self.shown.event(self.layer, "transform_changed", data)

    async def zoom_to_max(self) -> None:
        """Pinch to the maximum zoom."""
        self.fake.scale = self.max_scale
        await self.transformed()


def top(box: tuple[float, float]) -> float:
    """The Concourse plan's maximum zoom in a box (``ui.zoom``, D-312)."""
    natural = (2048.0, 1583.0)
    return zoom.max_scale(natural[0], zoom.fitted(box, natural)[0])


async def test_the_floor_viewer_re_renders_and_clamps_at_every_rotation(
    open_at: Open, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#606: each turn re-renders the floor viewer and runs its resize effect.

    The Map under it reads the layout too. At each landscape the zoom comes down to
    landscape's lower maximum (#581's clamp); back in portrait the viewer renders
    portrait's maximum, so Zoom in is enabled again, twice over.
    """
    fake = FakeViewer()
    fake.install(monkeypatch)
    shown = await open_at("/map/plan/concourse")
    viewer = Viewer(shown, fake)
    await viewer.rotate(PORTRAIT, PLAN_PORTRAIT)
    for _ in range(2):
        await viewer.zoom_to_max()
        assert not viewer.zoom_in_enabled()
        await viewer.rotate(LANDSCAPE, PLAN_LANDSCAPE)
        assert viewer.max_scale == pytest.approx(top(PLAN_LANDSCAPE))
        assert fake.scale == pytest.approx(top(PLAN_LANDSCAPE))  # clamped
        await viewer.rotate(PORTRAIT, PLAN_PORTRAIT)
        assert viewer.max_scale == pytest.approx(top(PLAN_PORTRAIT))
        assert viewer.zoom_in_enabled()
    assert stopped(shown) is None
