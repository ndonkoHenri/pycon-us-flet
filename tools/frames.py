"""Read a screen recording: when a pixel changes colour, when the screen changes.

Usage, from the repo's root (uv fetches the readers, which nothing else needs):

    uv run --no-project --with av --with numpy --with pillow python -m tools.frames VIDEO
        --point X,Y [--tolerance 2]         # each colour change at a pixel
        [--region X,Y,W,H] [--threshold 1]  # each change in a region; the whole frame by default
        [--dump DIR]                        # saves the frame at each change

Times are seconds from the recording's start, and positions are the video's pixels, which it
prints first. Recording lines are in `docs/testing-and-quality.md` §8. Recording slows a
start, so only compare recordings with each other.
"""

import argparse
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

Colour = tuple[int, int, int]


def hex_colour(colour: Colour) -> str:
    """Return a colour as `#rrggbb`."""
    return "#{:02x}{:02x}{:02x}".format(*colour)


def colour_changes(
    samples: Iterable[tuple[float, Colour]], tolerance: int
) -> Iterator[tuple[float, Colour]]:
    """Yield the first sample and each that differs from the last one yielded.

    Compared with the last one yielded, not the previous frame, so a slow fade still shows.

    Args:
        samples: Each frame's time and the colour at the point.
        tolerance: How far a channel may move and count as the same: video coding wobbles.
    """
    last = None
    for time, colour in samples:
        if last is None or any(
            abs(a - b) > tolerance for a, b in zip(colour, last, strict=False)
        ):
            last = colour
            yield time, colour


def pair(text: str) -> tuple[int, ...]:
    """Return the integers of a comma-separated option such as `540,1200`."""
    return tuple(int(part) for part in text.split(","))


def _frames(path: str) -> Iterator[tuple[float, Any]]:
    """Yield each frame's time and its pixels as an RGB array."""
    import av  # pyright: ignore[reportMissingImports]

    with av.open(path) as video:
        for frame in video.decode(video=0):
            yield float(frame.time), frame.to_ndarray(format="rgb24")


def _save(pixels: Any, folder: Path, time: float) -> None:
    """Save a frame as `<time>.png` in `folder`."""
    from PIL import Image

    folder.mkdir(parents=True, exist_ok=True)
    Image.fromarray(pixels).save(folder / f"{time:08.3f}.png")


def _at_point(
    frames: Iterator[tuple[float, Any]],
    point: tuple[int, ...],
    tolerance: int,
    dump: Path | None,
) -> None:
    """Print each colour change at the pixel, saving its frame if asked."""
    x, y = point
    held: dict[float, Any] = {}  # the frame of the latest sample, to save it

    def samples() -> Iterator[tuple[float, Colour]]:
        """Yield each frame's colour at the pixel, holding the frame to save it."""
        for time, pixels in frames:
            held.clear()
            held[time] = pixels
            red, green, blue = pixels[y, x]
            yield time, (int(red), int(green), int(blue))

    for time, colour in colour_changes(samples(), tolerance):
        print(f"{time:8.3f}  {hex_colour(colour)}")
        if dump:
            _save(held[time], dump, time)


def _in_region(
    frames: Iterator[tuple[float, Any]],
    box: tuple[int, ...],
    threshold: float,
    dump: Path | None,
) -> None:
    """Print each frame whose region differs from the last one printed, saving it if asked."""
    last = None
    for time, pixels in frames:
        x, y, width, height = box or (0, 0, pixels.shape[1], pixels.shape[0])
        region = pixels[y : y + height, x : x + width].astype("int16")
        if last is None or abs(region - last).mean() > threshold:
            last = region
            print(f"{time:8.3f}  changed")
            if dump:
                _save(pixels, dump, time)


def main(argv: list[str] | None = None) -> None:
    """Run the command line."""
    parser = argparse.ArgumentParser(prog="tools.frames", description=__doc__)
    parser.add_argument("video")
    parser.add_argument("--point", type=pair, help="X,Y: report this pixel's colour")
    parser.add_argument(
        "--region", type=pair, default=(), help="X,Y,W,H of the screen to watch"
    )
    parser.add_argument(
        "--tolerance", type=int, default=2, help="per channel, for --point"
    )
    parser.add_argument(
        "--threshold", type=float, default=1.0, help="mean change, for --region"
    )
    parser.add_argument("--dump", type=Path, help="save the frame at each change here")
    args = parser.parse_args(argv)
    if args.point and args.region:
        parser.error("--point or --region, not both")
    if args.region and len(args.region) != 4:
        parser.error("--region is X,Y,W,H")
    frames = _frames(args.video)
    first = next(frames, None)
    if first is None:
        sys.exit(f"frames.py: no frames in {args.video}")
    print(f"{first[1].shape[1]} x {first[1].shape[0]} px")

    def all_frames() -> Iterator[tuple[float, Any]]:
        """Yield the frame already read, then the rest."""
        yield first
        yield from frames

    if args.point:
        _at_point(all_frames(), args.point, args.tolerance, args.dump)
    else:
        _in_region(all_frames(), args.region, args.threshold, args.dump)


if __name__ == "__main__":
    main()
