r"""Encode a year's floor plans and their thumbnails for the app (D-312, #372).

Each plan is fitted to 2048 px on its longer side (Lanczos, never scaled up) and saved
as lossy WebP, quality 80, as spike S7 decided (``docs/spikes/07-floor-plans.md``);
its thumbnail is the fitted plan fitted again to 800 px, so a pin's percentages land
on the same spot in both. ``--cover`` paints a rectangle of the source in the plan's
background colour first: the way to hide a PyCon mark printed on a plan (D-36).
``--crop`` keeps one rectangle of the source, after the covers: the way to drop a
print's header with its logo (the job fair's, D-254). A plan smaller than 2048 px
after its crop keeps its own size, since the script never scales up.

Run it from the repository's root with each plan as ``<id>=<source image>``; it writes
``<id>.webp`` and ``<id>-thumb.webp`` into ``--out`` and prints each file's size, to be
copied into ``map.toml``'s ``width`` and ``height``. 2026's plans (``NOTICE``), the
expo's sun-and-palms mark covered too (#401) and the job fair's print cropped to the
floor, without its header (#407)::

    IMG=excluded/pycon-us-mobile/src/assets/img
    uv run python tools/encode_plans.py --out src/assets/maps/2026 \
        --cover campus=150,40,520,185 --cover campus=150,1566,500,1680 \
        --cover expo=30,230,545,650 \
        --crop job-fair=0,640,1700,2078 \
        campus=$IMG/floor-plans/campus-map.jpg \
        concourse=$IMG/floor-plans/floor-plan-1.jpg \
        upper=$IMG/floor-plans/floor-plan-2.jpg \
        arena=$IMG/floor-plans/floor-plan-3.jpg \
        seaside=$IMG/floor-plans/floor-plan-4.jpg \
        expo=$IMG/pycon-us-2026-floorplan-nologo.jpg \
        job-fair=$IMG/floor-plans/job-fair.jpg
"""

import argparse
import io
from pathlib import Path

from PIL import Image, ImageDraw

PLAN_SIDE = 2048
"""The longest side of a bundled plan, in pixels (D-312)."""

THUMB_SIDE = 800
"""The longest side of a plan's thumbnail, in pixels: a card shows it at most 382 dp wide."""

QUALITY = 80
"""Lossy WebP quality (D-312)."""


def fit(image: Image.Image, max_side: int) -> Image.Image:
    """Return ``image`` in RGB, scaled down (never up) so its longer side is ``max_side``.

    Args:
        image: The decoded plan.
        max_side: The longest side allowed, in pixels.

    Returns:
        The RGB image, resampled with Lanczos when it was larger.
    """
    image = image.convert("RGB")
    scale = max_side / max(image.size)
    if scale >= 1:
        return image
    size = (round(image.width * scale), round(image.height * scale))
    return image.resize(size, Image.Resampling.LANCZOS)


def cover(image: Image.Image, boxes: list[tuple[int, int, int, int]]) -> Image.Image:
    """Paint each box of ``image`` in the colour of its top-left pixel (the background).

    Args:
        image: The RGB source plan, at its own size.
        boxes: ``(left, top, right, bottom)`` rectangles in the source's pixels.

    Returns:
        A copy of the image with the boxes painted over.
    """
    image = image.copy()
    draw = ImageDraw.Draw(image)
    background = image.getpixel((0, 0))
    for box in boxes:
        draw.rectangle(box, fill=background)
    return image


def webp(image: Image.Image) -> bytes:
    """Encode ``image`` as lossy WebP at ``QUALITY``, with the slowest, smallest method."""
    buffer = io.BytesIO()
    image.save(buffer, "WEBP", quality=QUALITY, method=6)
    return buffer.getvalue()


def _box(text: str) -> tuple[str, tuple[int, int, int, int]]:
    """Read ``<id>=left,top,right,bottom``, the form of ``--cover`` and ``--crop``."""
    plan, _, numbers = text.partition("=")
    left, top, right, bottom = (int(n) for n in numbers.split(","))
    return plan, (left, top, right, bottom)


def _plan(text: str) -> tuple[str, Path]:
    """Read ``<id>=<source image>``, a plan to encode."""
    plan, _, source = text.partition("=")
    return plan, Path(source)


def main() -> None:
    """Encode every plan given and print its id, size and file sizes."""
    parser = argparse.ArgumentParser(
        description="Encode floor plans for the app (D-312)."
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cover", type=_box, action="append", default=[])
    parser.add_argument("--crop", type=_box, action="append", default=[])
    parser.add_argument("plans", type=_plan, nargs="+", metavar="ID=SOURCE")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for plan, source in args.plans:
        with Image.open(source) as opened:
            image = opened.convert("RGB")
        boxes = [box for name, box in args.cover if name == plan]
        image = cover(image, boxes)
        crop = next((box for name, box in args.crop if name == plan), None)
        if crop is not None:
            image = image.crop(crop)
        fitted = fit(image, PLAN_SIDE)
        thumb = fit(fitted, THUMB_SIDE)
        sizes = []
        for name, picture in ((plan, fitted), (f"{plan}-thumb", thumb)):
            data = webp(picture)
            (args.out / f"{name}.webp").write_bytes(data)
            sizes.append(f"{name}.webp {len(data) / 1024:.0f} KB")
        print(
            f"{plan}: width = {fitted.width}, height = {fitted.height}; "
            + ", ".join(sizes)
        )


if __name__ == "__main__":
    main()
