"""The geometry of a zoomed floor plan: pure functions the tests pin (D-312, F76, #588).

``ui/zoom.py``'s layer shows a plan fitted in its viewer; here is where it lands
(``fitted()``), how far it zooms (``max_scale()``), where a point of it is
(``centred_on()``), and the pans that keep a zoom's focus in place (``refocus()``) and
bring a resized viewer back inside its bounds (``into_bounds()``).
"""

from dataclasses import dataclass

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


def into_bounds(now: Transform, box: Size) -> tuple[float, float]:
    """Return the ``pan()`` that brings the viewer back inside its bounds after a resize.

    The viewer's content fills it, so at scale ``s`` the content is ``s`` times the
    box and its translation ``t`` stays in ``[box (1 - s), 0]`` on each axis: then no
    blank shows beyond the content's edges. Flutter checks that bound on a gesture,
    not on a resize, so a rotation can leave ``t`` outside it (#588). A pan of ``dx``
    moves ``t`` by ``s dx`` (F76).

    Args:
        now: The transform after the resize (read back).
        box: The viewer's new size.

    Returns:
        The ``dx`` and ``dy`` to give ``pan()``: ``(0, 0)`` when already in bounds.
    """
    deltas = []
    for t, side in ((now.x, box[0]), (now.y, box[1])):
        inside = min(0.0, max(side * (1 - now.scale), t))
        deltas.append((inside - t) / now.scale)
    return deltas[0], deltas[1]
