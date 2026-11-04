"""Turn a raw simulator recording into a clip, and lay a clip's frames out to read.

The video half of `tools/demo_videos.py`, which films the flows and calls it. `render()`
cuts the recording down to the stretches where the screen changes and writes them at a
constant frame rate; `sheets()` saves contact sheets of a finished clip and lists its
dark frames and flashes for a person to check before it is shared. Both read video
with `av`, `numpy` and `pillow`, which nothing else needs (`uv run --with av --with
numpy --with pillow ...`, as `demo_videos.py` says), so they are imported inside the
functions that use them.
"""

from fractions import Fraction
from itertools import pairwise
from pathlib import Path
from typing import Any

HEAD_STILL = 2.0
"""Seconds of the first screen kept before anything moves."""

TAIL_STILL = 2.0
"""Seconds of the last screen kept after everything stops."""

LONGEST_STILL = 4.0
"""A still stretch longer than this is Maestro or a busy host, not a pause in a flow..."""

SHORTENED_STILL = 3.0
"""...and is cut down to this."""

OUTPUT_FPS = 30


def still_cuts(changes: list[float], duration: float) -> list[tuple[float, float]]:
    """Return the stretches of the recording to keep, given when the screen changed.

    Args:
        changes: The seconds at which the picture changed, ascending, without the first frame.
        duration: The recording's length in seconds.

    Returns:
        `(start, end)` pairs: at most `HEAD_STILL` before the first change and
        `TAIL_STILL` after the last, and each still stretch over `LONGEST_STILL` cut
        down to `SHORTENED_STILL`.
    """
    if not changes:
        return [(0.0, min(duration, HEAD_STILL))]
    start = max(0.0, changes[0] - HEAD_STILL)
    kept = []
    for before, after in pairwise(changes):
        if after - before > LONGEST_STILL:
            kept.append((start, before + SHORTENED_STILL))
            start = after
    kept.append((start, min(duration, changes[-1] + TAIL_STILL)))
    return kept


def _gray(frame: Any) -> Any:
    """Return a frame's luminance at a quarter of its size, to compare with another's."""
    return frame.to_ndarray(format="gray")[::4, ::4]


def _changes(raw: Path) -> tuple[list[float], float]:
    """Return when the recording's picture changes, and its length in seconds."""
    import av  # pyright: ignore[reportMissingImports]
    import numpy as np

    changes = []
    last = None
    end = 0.0
    with av.open(str(raw)) as video:
        stream = video.streams.video[0]
        first = None
        for frame in video.decode(stream):
            first = frame.time if first is None else first
            end = frame.time - first
            gray = _gray(frame).astype(np.int16)
            # A count of changed pixels, so a ticking line of small text still counts.
            if last is not None and np.mean(np.abs(gray - last) > 16) > 0.0001:
                changes.append(end)
            last = gray
        # The file can outlast its last frame, which then holds to the end.
        whole = (video.duration or 0) / av.time_base
    return changes, max(end, whole)


def render(raw: Path, out: Path) -> float:
    """Write the kept stretches of `raw` to `out` at a constant frame rate.

    Args:
        raw: The recording, whose frames come only when the screen changes.
        out: The finished clip: H.264, yuv420p, which every player opens.

    Returns:
        The clip's length in seconds.
    """
    import av  # pyright: ignore[reportMissingImports]

    changes, duration = _changes(raw)
    wanted = _output_times(still_cuts(changes, duration))
    with (
        av.open(str(raw)) as video,
        av.open(str(out), "w", options={"movflags": "+faststart"}) as output,
    ):
        stream = video.streams.video[0]
        encoder = output.add_stream("libx264", rate=OUTPUT_FPS)
        encoder.width = stream.width
        encoder.height = stream.height
        encoder.pix_fmt = "yuv420p"
        encoder.time_base = Fraction(1, OUTPUT_FPS)
        encoder.options = {"crf": "23", "preset": "medium"}
        index = 0
        held = None
        first = None
        for frame in video.decode(stream):
            first = frame.time if first is None else first
            time_in = frame.time - first
            while held is not None and index < len(wanted) and wanted[index] < time_in:
                index = _emit(output, encoder, held, index)
            held = frame
        while held is not None and index < len(wanted):
            index = _emit(output, encoder, held, index)
        output.mux(encoder.encode())
    return len(wanted) / OUTPUT_FPS


def _output_times(kept: list[tuple[float, float]]) -> list[float]:
    """Return the recording's time for each frame of the clip."""
    times = []
    for start, end in kept:
        count = round((end - start) * OUTPUT_FPS)
        times.extend(start + step / OUTPUT_FPS for step in range(count))
    return times


def _emit(output: Any, encoder: Any, frame: Any, index: int) -> int:
    """Encode `frame` as the clip's frame `index`; return the next index."""
    picture = frame.reformat(format="yuv420p")
    picture.pts = index
    picture.time_base = Fraction(1, OUTPUT_FPS)
    output.mux(encoder.encode(picture))
    return index + 1


def sheets(clip: Path, folder: Path, fps: float) -> None:
    """Save contact sheets of `clip` and print the frames a person must look at.

    Prints the dark frames, and each flash: a picture that differs from half a second
    before it while the pictures on both sides of it agree, which a sheet can miss.

    Args:
        clip: A finished video.
        folder: Where the sheets go.
        fps: Frames per second on the sheets.
    """
    import av  # pyright: ignore[reportMissingImports]
    import numpy as np
    from PIL import Image, ImageDraw

    folder.mkdir(parents=True, exist_ok=True)
    height, columns, rows = 520, 10, 2
    samples, dark, grays = [], [], []
    with av.open(str(clip)) as video:
        for frame in video.decode(video.streams.video[0]):
            gray = _gray(frame).astype(np.int16)
            grays.append((frame.time, gray))
            if gray.mean() < 25:
                dark.append(round(frame.time, 2))
            if frame.time * fps >= len(samples):
                width = height * frame.width // frame.height
                image = frame.to_image().resize((width, height))
                samples.append((frame.time, image))
    print(f"{clip.name}: {grays[-1][0]:.1f} s, {len(samples)} samples")
    print(f"dark frames: {dark or 'none'}")
    print(f"flashes: {_flashes(grays) or 'none'}")
    per_sheet = columns * rows
    width = samples[0][1].width
    for start in range(0, len(samples), per_sheet):
        sheet = Image.new("RGB", (columns * (width + 4), rows * (height + 4)), "#888")
        draw = ImageDraw.Draw(sheet)
        for offset, (moment, image) in enumerate(samples[start : start + per_sheet]):
            x, y = (offset % columns) * (width + 4), (offset // columns) * (height + 4)
            sheet.paste(image, (x, y))
            draw.rectangle([x, y, x + 40, y + 14], fill="#000")
            draw.text((x + 2, y + 1), f"{moment:.1f}", fill="#ff0")
        sheet.save(folder / f"{clip.stem}-{start // per_sheet:02d}.jpg", quality=80)


def _flashes(grays: list[tuple[float, Any]], window: int = 15) -> list[float]:
    """Return when a picture stands apart from those `window` frames either side."""
    import numpy as np

    found: list[float] = []
    for index in range(window, len(grays) - window):
        before, here, after = (grays[index + d][1] for d in (-window, 0, window))
        apart = np.abs(here - before).mean()
        if apart > 12 and np.abs(after - before).mean() < 2:
            moment = round(grays[index][0], 2)
            if not found or moment - found[-1] > 1:
                found.append(moment)
    return found
