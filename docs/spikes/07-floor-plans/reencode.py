"""Re-encode the year's floor plans to 2048 px or less (#361, docs/spikes/07-floor-plans.md).

Keep this for next year: point ``--source`` at the new plans and run it again. It
writes the formats the spike compared into ``--compare`` (when given) and, into
``--out``, the chosen one (lossy WebP, quality 80, D-312) next to a JPEG (quality 85,
4:4:4) for comparison, plus the expo plan's source as ``expo-source.jpg``: the
reproducer's ``src/assets/plans/``. The app's ``assets/plans/`` takes the ``.webp`` files.

    uv run --with pillow==12.0.0 python reencode.py \
        --source ../../../excluded/pycon-us-mobile/src/assets/img \
        --out src/assets/plans --compare build/compare
"""

import argparse
import io
from pathlib import Path

from PIL import Image

MAX_SIDE = 2048

# Our name -> the 2026 file under the Ionic app's src/assets/img/.
PLANS = {
    "concourse": "floor-plans/floor-plan-1.jpg",
    "upper": "floor-plans/floor-plan-2.jpg",
    "arena": "floor-plans/floor-plan-3.jpg",
    "seaside": "floor-plans/floor-plan-4.jpg",
    "campus": "floor-plans/campus-map.jpg",
    "job-fair": "floor-plans/job-fair.jpg",
    "expo": "pycon-us-2026-floorplan-nologo.jpg",
}


def fit(image: Image.Image, max_side: int = MAX_SIDE) -> Image.Image:
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


def encodings(image: Image.Image) -> dict[str, bytes]:
    """Encode ``image`` in every format the spike compared.

    Args:
        image: The fitted RGB plan.

    Returns:
        Bytes by variant name (``jpeg70``, ``jpeg85``, ``jpeg92``, ``png``, ``webp80``,
        ``webp-lossless``).
    """
    variants = {
        "jpeg70": ("JPEG", {"quality": 70, "subsampling": 0}),
        "jpeg85": ("JPEG", {"quality": 85, "subsampling": 0}),
        "jpeg92": ("JPEG", {"quality": 92, "subsampling": 0}),
        "png": ("PNG", {"optimize": True}),
        "webp80": ("WEBP", {"quality": 80, "method": 6}),
        "webp-lossless": ("WEBP", {"lossless": True, "method": 6}),
    }
    out = {}
    for name, (fmt, options) in variants.items():
        buffer = io.BytesIO()
        image.save(buffer, fmt, **options)
        out[name] = buffer.getvalue()
    return out


def main() -> None:
    """Re-encode every plan and print each variant's size and decoded memory."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--compare", type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    print(
        "plan        source        fitted      decoded  "
        + "  ".join(
            f"{n:>13}"
            for n in ("jpeg70", "jpeg85", "jpeg92", "png", "webp80", "webp-lossless")
        )
    )
    for name, rel in PLANS.items():
        with Image.open(args.source / rel) as source:
            fitted = fit(source)
            source_size = f"{source.width}x{source.height}"
        variants = encodings(fitted)
        (args.out / f"{name}.webp").write_bytes(variants["webp80"])
        (args.out / f"{name}.jpg").write_bytes(variants["jpeg85"])
        if name == "expo":
            (args.out / "expo-source.jpg").write_bytes((args.source / rel).read_bytes())
        if args.compare:
            args.compare.mkdir(parents=True, exist_ok=True)
            for variant, data in variants.items():
                ext = {"J": "jpg", "P": "png", "W": "webp"}[variant[0].upper()]
                (args.compare / f"{name}-{variant}.{ext}").write_bytes(data)
        decoded_mb = fitted.width * fitted.height * 4 / 2**20
        sizes = "  ".join(f"{len(d) / 1024:>10.0f} KB" for d in variants.values())
        print(
            f"{name:<10} {source_size:>11} {fitted.width:>5}x{fitted.height:<5} {decoded_mb:>6.1f} MB  {sizes}"
        )


if __name__ == "__main__":
    main()
