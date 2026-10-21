"""The zoom layer of a floor plan: ``use_zoom()``, ``zoom_layer()`` and ``zoom_buttons()``.

A plan is an ``Image(fit=CONTAIN)`` in a ``Stack`` with what is drawn on it (a pin, and
later the expo's booths), inside an ``InteractiveViewer(min_scale=1, max_scale=natural
/ displayed)``: zoom never goes below the fitted plan, and at most one image pixel fills
one logical pixel (D-312, S7). The viewer's size comes from ``on_size_change``; the
plan's fitted size, its maximum zoom and where a point of it lands follow from it
(``fitted()``, ``max_scale()``, ``centred_on()``), pure functions the tests pin.

Every viewer has the zoom buttons, the single-pointer way to zoom (WCAG 2.5.1). At the
pin, ``zoom()`` scales about the plan's top-left corner, so each zoom pans back to keep
its focus in place (``refocus()``, F76) until U56 (#472). A double tap (2x, or back to
fit) is only for plans with nothing to tap: its detector delays every single tap
(D-312). Every duration goes through ``prefs.motion_ms()`` (D-173).
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import flet as ft

from pycon_us.prefs import use_prefs
from pycon_us.services.errors import report_errors
from pycon_us.ui.semantics import named

ZOOM_STEP = 1.5
"""How much a zoom button zooms in, or out (its inverse)."""

DOUBLE_TAP_SCALE = 2.0
"""How much a double tap zooms in at the fitted plan (ux.md §6.1)."""

RESET_MS = 250
"""How long Reset view animates back to the fitted plan (ux.md §3.8's fades)."""

AT_FIT = 1.001
"""A scale under which the plan counts as fitted: the viewer reports float scales."""

BUTTON_DP = 48
"""A zoom button's size: the minimum touch target (D-33)."""

ZOOM_IN = "Zoom in"
ZOOM_OUT = "Zoom out"
RESET_VIEW = "Reset view"

type Size = tuple[float, float]
"""A width and a height, in logical pixels (or, for an image, pixels)."""


def fitted(box: Size, natural: Size) -> Size:
    """Return the plan's size in the viewer with ``BoxFit.CONTAIN``.

    Args:
        box: The viewer's size, in logical pixels; ``(0, 0)`` before its first layout.
        natural: The image's size, in pixels.

    Returns:
        The plan's displayed width and height; ``(0, 0)`` before the first layout.
    """
    if box[0] <= 0 or box[1] <= 0:
        return 0.0, 0.0
    scale = min(box[0] / natural[0], box[1] / natural[1])
    return natural[0] * scale, natural[1] * scale


def max_scale(natural_width: float, shown_width: float) -> float:
    """Return the viewer's maximum zoom: one image pixel to one logical pixel (D-312).

    Never under 1, so a plan shown at or above its natural size still keeps the
    viewer's ``min_scale <= max_scale``.

    Args:
        natural_width: The image's width, in pixels.
        shown_width: Its fitted width (``fitted()``), in logical pixels; 0 before the
            first layout.
    """
    return max(1.0, natural_width / shown_width) if shown_width > 0 else 1.0


def centred_on(x: float, y: float, shown: Size, extent: float) -> tuple[float, float]:
    """Return where a box ``extent`` dp square goes so its centre is on a plan's point.

    Args:
        x: The point's distance from the plan's left edge, in percent of its width
            (``map.toml``'s ``x``).
        y: Its distance from the top edge, in percent of the height.
        shown: The plan's fitted size (``fitted()``).
        extent: The box's side, in logical pixels.

    Returns:
        The box's ``left`` and ``top`` in the plan's ``Stack``.
    """
    return x / 100 * shown[0] - extent / 2, y / 100 * shown[1] - extent / 2


@dataclass(frozen=True)
class Transform:
    """The viewer's scale and translation, as ``get_transform()`` reads them."""

    scale: float
    x: float
    y: float


def refocus(before: Transform, after: Transform, focus: Size) -> tuple[float, float]:
    """Return the ``pan()`` that puts back under ``focus`` what was there before a zoom.

    ``zoom()`` scales about the plan's top-left corner and ``pan()`` moves in the
    plan's units, ``scale`` logical pixels each (F76): a screen point ``p`` shows the
    plan's point ``(p - t) / s``. So after the zoom the translation must become
    ``focus - s' (focus - t) / s``, which a pan of ``dx`` reaches as ``t' + s' dx``.

    Args:
        before: The transform before the zoom.
        after: The transform after it (clamped, so read back, never assumed).
        focus: The viewer's point to keep in place: its centre, or a double tap.

    Returns:
        The ``dx`` and ``dy`` to give ``pan()``.
    """
    deltas = []
    for f, t, t_after in ((focus[0], before.x, after.x), (focus[1], before.y, after.y)):
        point = (f - t) / before.scale
        deltas.append((f - after.scale * point - t_after) / after.scale)
    return deltas[0], deltas[1]


async def read(viewer: ft.InteractiveViewer) -> Transform:
    """Return the viewer's current transform.

    Args:
        viewer: A mounted viewer.
    """
    now = await viewer.get_transform()
    return Transform(now.scale, now.translation_x, now.translation_y)


@dataclass
class Zoom:
    """A zoom layer's state and actions, from ``use_zoom()``.

    Attributes:
        viewer: The ``InteractiveViewer``, once mounted.
        natural: The image's size, in pixels.
        box: The viewer's size, ``(0, 0)`` before its first layout.
        scale: The viewer's last reported scale, 1 at fit.
        reset_ms: Reset view's duration: ``RESET_MS``, or 0 under reduced motion.
        resized: The viewer's ``on_size_change`` handler.
        transformed: The viewer's ``on_transform_changed`` handler.
    """

    viewer: ft.Ref[ft.InteractiveViewer]
    natural: Size
    box: Size
    scale: float
    reset_ms: int
    resized: Callable[[ft.LayoutSizeChangeEvent], None]
    transformed: Callable[[ft.InteractiveViewerTransformEvent], None]

    @property
    def shown(self) -> Size:
        """The plan's fitted size in the viewer (``fitted()``)."""
        return fitted(self.box, self.natural)

    @property
    def max_scale(self) -> float:
        """The viewer's maximum zoom (``max_scale()``)."""
        return max_scale(self.natural[0], self.shown[0])

    @property
    def at_fit(self) -> bool:
        """Whether the plan is at its fitted size, so it cannot zoom out."""
        return self.scale < AT_FIT

    @property
    def at_max(self) -> bool:
        """Whether the plan is at its maximum zoom, so it cannot zoom in."""
        return self.scale * AT_FIT >= self.max_scale

    async def zoom_by(self, factor: float, focus: Size | None = None) -> None:
        """Zoom by ``factor``, keeping ``focus`` (by default the centre) in place.

        Args:
            factor: Over 1 zooms in, under 1 out; the viewer clamps the result.
            focus: The viewer's point that stays where it is.
        """
        viewer = self.viewer.current
        if viewer is None:  # not mounted yet: nothing to zoom
            return
        focus = focus or (self.box[0] / 2, self.box[1] / 2)
        before = await read(viewer)
        await viewer.zoom(factor)
        dx, dy = refocus(before, await read(viewer), focus)
        await viewer.pan(dx, dy)

    async def reset(self) -> None:
        """Go back to the fitted plan: animated, or at once under reduced motion."""
        viewer = self.viewer.current
        if viewer is None:
            return
        duration = ft.Duration(milliseconds=self.reset_ms) if self.reset_ms else None
        await viewer.reset(animation_duration=duration)


def use_zoom(natural: Size) -> Zoom:
    """Return a zoom layer's state for an image of ``natural`` size (a hook).

    Args:
        natural: The image's width and height, in pixels (``map.toml``'s).
    """
    prefs = use_prefs()
    viewer = ft.use_memo(ft.Ref[ft.InteractiveViewer], [])
    box, set_box = ft.use_state((0.0, 0.0))
    scale, set_scale = ft.use_state(1.0)

    @report_errors
    def resized(e: ft.LayoutSizeChangeEvent) -> None:
        set_box((e.width, e.height))

    @report_errors
    def transformed(e: ft.InteractiveViewerTransformEvent) -> None:
        set_scale(e.scale)

    return Zoom(
        viewer=viewer,
        natural=natural,
        box=box,
        scale=scale,
        reset_ms=prefs.motion_ms(RESET_MS),
        resized=resized,
        transformed=transformed,
    )


def zoom_layer(
    zoom: Zoom,
    src: str,
    label: str,
    layers: list[ft.Control],
    *,
    double_tap: bool,
) -> ft.Control:
    """Return the plan in its ``InteractiveViewer``, filling the space it is given.

    The plan's ``Stack`` is its fitted size, centred, so what ``layers`` place from
    the plan's percentages (``centred_on()``) lands on the plan at every zoom.

    Args:
        zoom: The layer's state (``use_zoom()``).
        src: The plan's image, relative to ``src/assets/`` (``Plan.image``). No
            ``cache_width``: the zoom is there for the detail it would drop (D-312).
        label: What a screen reader says of the plan, e.g. "Concourse level floor
            plan, Room 104C marked": the layers are not read.
        layers: What is drawn on the plan, positioned in the fitted plan's units.
        double_tap: Whether a double tap zooms in 2x, or back to fit: only on a plan
            with nothing to tap, since its detector delays every single tap (D-312).
    """
    width, height = zoom.shown
    image = ft.Image(
        src, width=width, height=height, fit=ft.BoxFit.CONTAIN, semantics_label=label
    )
    viewer: ft.Control = ft.InteractiveViewer(
        ref=zoom.viewer,
        min_scale=1,
        max_scale=zoom.max_scale,
        content=ft.Container(
            ft.Stack([image, *layers], width=width, height=height),
            alignment=ft.Alignment.CENTER,
        ),
        on_transform_changed=zoom.transformed,
        expand=True,
    )
    if double_tap:
        tapped_at: list[Size] = []

        @report_errors
        def down(e: ft.TapEvent) -> None:
            if e.local_position is not None:
                tapped_at[:] = [(e.local_position.x, e.local_position.y)]

        @report_errors
        async def double() -> None:
            if zoom.at_fit:
                await zoom.zoom_by(
                    DOUBLE_TAP_SCALE, tapped_at[0] if tapped_at else None
                )
            else:
                await zoom.reset()

        viewer = ft.GestureDetector(
            content=viewer, on_double_tap_down=down, on_double_tap=double, expand=True
        )
    return ft.Container(viewer, expand=True, on_size_change=zoom.resized)


def zoom_button(
    identifier: str,
    icon: ft.IconData,
    tooltip: str,
    on_click: Callable[[], Awaitable[None]],
    disabled: bool,
) -> ft.Control:
    """Return one zoom button: a 48 dp tonal icon button, named by its tooltip.

    Args:
        identifier: For UI flows, e.g. ``plan.zoom_in``; merged with the button.
        icon: The button's icon.
        tooltip: Its name, e.g. "Zoom in".
        on_click: What it does, wrapped in ``report_errors`` by the caller.
        disabled: Whether it can do nothing at this zoom.
    """
    return named(
        identifier,
        ft.FilledTonalIconButton(
            icon,
            tooltip=tooltip,
            on_click=on_click,
            disabled=disabled,
            width=BUTTON_DP,
            height=BUTTON_DP,
        ),
    )


def zoom_buttons(zoom: Zoom, screen: str) -> ft.Control:
    """Return the zoom buttons, in a column: zoom in, zoom out, reset view.

    The single-pointer alternative to a pinch (WCAG 2.5.1), 48 dp each, named by
    their tooltips and merged with their identifiers (``<screen>.zoom_in``,
    ``.zoom_out``, ``.reset``; D-214). A button that can do nothing at this zoom is
    disabled, and says so.

    Args:
        zoom: The layer's state (``use_zoom()``).
        screen: The screen's name in the identifiers, e.g. ``plan``.
    """

    @report_errors
    async def zoom_in() -> None:
        await zoom.zoom_by(ZOOM_STEP)

    @report_errors
    async def zoom_out() -> None:
        await zoom.zoom_by(1 / ZOOM_STEP)

    @report_errors
    async def reset() -> None:
        await zoom.reset()

    return ft.Column(
        [
            zoom_button(
                f"{screen}.zoom_in", ft.Icons.ZOOM_IN, ZOOM_IN, zoom_in, zoom.at_max
            ),
            zoom_button(
                f"{screen}.zoom_out", ft.Icons.ZOOM_OUT, ZOOM_OUT, zoom_out, zoom.at_fit
            ),
            zoom_button(
                f"{screen}.reset",
                ft.Icons.CENTER_FOCUS_STRONG,
                RESET_VIEW,
                reset,
                zoom.at_fit,
            ),
        ],
        spacing=8,
        tight=True,
    )
