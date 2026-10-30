"""Where the expo hall's camera goes when it is laid out (EXPO-05, D-312, D-377).

A booth picked somewhere else, a List row or a ``?booth=`` link, arrives selected with
its card, and at the fitted plan it can sit under that card or the zoom buttons above
it. ``use_camera()`` places the camera once per hall: the pane's last zoom put back
(D-312), unless the picked booth is out of sight there, in which case it zooms in just
enough to bring the booth up into the band above the buttons, centred in it (D-377). A
booth in sight at the fitted plan leaves the camera there; a tap on the plan never
moves it, since the user is looking at the booth tapped.

Until U3's ``set_transform`` the move is ``Zoom.restore()``'s reset, zoom and pan, so
two or three frames show the steps; ``in_view()`` is pure and says where they land.
"""

import flet as ft

from pycon_us.memory import ViewMemory
from pycon_us.services.errors import report_errors
from pycon_us.ui.zoom import AT_FIT, Zoom
from pycon_us.ui.zoom_geometry import Size, Transform, fitted
from pycon_us.year_map import Booth

FIT = Transform(1.0, 0.0, 0.0)
"""The fitted plan's transform: where a newly laid out viewer is."""

type Rect = tuple[float, float, float, float]
"""A ``left``, ``top``, ``width`` and ``height``, in logical pixels."""


def booth_rect(booth: Booth, box: Size, natural: Size) -> Rect:
    """Return a booth's rectangle in the viewer's content: the plan centred in the box.

    Args:
        booth: The booth, its rectangle in ratios of the plan.
        box: The viewer's size.
        natural: The plan image's size, in pixels.
    """
    width, height = fitted(box, natural)
    left = (box[0] - width) / 2 + booth.x * width
    top = (box[1] - height) / 2 + booth.y * height
    return left, top, booth.w * width, booth.h * height


def shows(rect: Rect, at: Transform, width: float, free: float) -> bool:
    """Return whether a rectangle of the content is on screen, above ``free``.

    A content point ``p`` shows at ``s p + t`` (``ui.zoom_geometry.refocus()``).

    Args:
        rect: The rectangle, in the content's units.
        at: The viewer's transform.
        width: The viewer's width.
        free: How far down the viewer is in sight: above the buttons and the card.
    """
    left, top, w, h = rect
    x, y = at.scale * left + at.x, at.scale * top + at.y
    return x >= 0 and y >= 0 and x + at.scale * w <= width and y + at.scale * h <= free


def in_view(
    booth: Booth,
    box: Size,
    natural: Size,
    *,
    cover: float,
    top: float,
    start: Transform,
) -> Transform:
    """Return the transform that shows a booth above what covers the pane's bottom.

    ``start`` when the booth shows there, else the fitted plan when it shows there,
    else the least zoom that can put the booth's centre in the middle of the band
    above ``cover``. The viewer keeps its content over the whole box, so at scale
    ``s`` the translation stays in ``[box (1 - s), 0]`` on each axis; the centre ``c``
    reaches a point ``p`` above it once ``s >= (box - p) / (box - c)``. The zoom stops
    at ``top``, the viewer's maximum, and the translation is clamped as Flutter does.

    Args:
        booth: The booth to show.
        box: The viewer's size; laid out, so not zero.
        natural: The plan image's size, in pixels.
        cover: How much of the pane, from its bottom, the card and the zoom buttons
            take (``expo_layout.covered()``).
        top: The viewer's maximum zoom.
        start: Where the camera would go without the booth: the pane's last zoom.
    """
    free = box[1] - cover
    rect = booth_rect(booth, box, natural)
    if free <= 0 or shows(rect, start, box[0], free):
        return start  # nothing above the card to bring it into, or in sight already
    if shows(rect, FIT, box[0], free):
        return FIT
    centre = (rect[0] + rect[2] / 2, rect[1] + rect[3] / 2)
    target = (box[0] / 2, free / 2)
    scale = min(top, max(1.0, (box[1] - target[1]) / (box[1] - centre[1])))
    x, y = (
        min(0.0, max(side * (1 - scale), aim - scale * point))
        for side, aim, point in zip(box, target, centre, strict=True)
    )
    return Transform(scale, x, y)


def use_camera(
    zoom: Zoom,
    memory: ViewMemory,
    *,
    zoom_key: str,
    reveal: Booth | None,
    cover: float,
) -> None:
    """Place the hall's camera once, when it is laid out (a hook; D-312, D-377).

    The pane's last zoom is put back, or, for a booth picked elsewhere, ``in_view()``
    once the card under it is measured. Once per hall: a later render, a new card's
    height included, leaves the camera to the user.

    Args:
        zoom: The hall's zoom layer (``use_zoom()``).
        memory: The process's ``ViewMemory``, whose ``map_zooms`` keeps the zoom.
        zoom_key: The pane's slug in ``map_zooms``; empty for a View that keeps none.
        reveal: The booth a List row or a link picked, selected now; None otherwise.
        cover: ``expo_layout.covered()`` for the selected booth's card; 0 until its
            body is measured.
    """
    placed: list[bool] = ft.use_memo(list, [])  # one for the hall's life
    ready = zoom.box[0] > 0

    @report_errors
    async def place() -> None:
        if placed or not ready or (reveal is not None and not cover):
            return  # done, not laid out, or the card's height comes next
        placed.append(True)
        kept = memory.map_zooms.get(zoom_key) if zoom_key else None
        to = Transform(*kept) if kept else FIT
        if reveal is not None:
            to = in_view(
                reveal,
                zoom.box,
                zoom.natural,
                cover=cover,
                top=zoom.max_scale,
                start=to,
            )
        if to.scale > AT_FIT:
            await zoom.restore(to)

    # The card's height counts only for a booth to reveal: without one, a card measured
    # mid-move would change the dependencies and cancel the move for good (F2).
    ft.use_effect(place, [ready, reveal is not None and bool(cover)])
