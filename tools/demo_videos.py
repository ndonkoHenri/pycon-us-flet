"""Record the demo videos on a fresh iOS simulator, or lay a clip's frames out to read.

Usage, from the repo's root (uv fetches the video readers, which nothing else needs):

    uv run --with av --with numpy --with pillow python -m tools.demo_videos record
        [--out DIR] [--clips NAME ...] [--build] [--model "iPhone 17"]
    uv run --with av --with numpy --with pillow python -m tools.demo_videos sheets CLIP DIR
        [--fps 2]

`record` makes a simulator of its own and restarts this checkout's mock, clean, then films `maestro/demo/` and writes
each clip, trimmed, to `--out`, then deletes the simulator and stops the mock. `--build`
builds the app first; without it the present build must hold this tree's Python.

The app's fake clock starts at the launch and keeps running, so a clip that outlasts a minute
shows "Now · 9:42" in the app. The status bar follows it: while a clip is filmed, the tool sets
the status bar's time to the fake clock's minute each time that minute changes (`fake_minute()`),
so the two agree in every frame. The app never freezes its clock for this (#1016).

The Developer options never appear because nothing ever opens or unlocks them: each scene
writes the fake clock and the mock's URL straight into the app's stored preferences, with no
`unlocked` key, so neither More nor About this app has a Developer row (`prefs.developer`).
`sheets` is how a person checks that, frame by frame, before a clip is shared.
"""

import argparse
import json
import os
import plistlib
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from fractions import Fraction
from itertools import pairwise
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FLOWS = ROOT / "maestro" / "demo"
BUNDLE = "io.github.ndonkohenri.confcompanion"
APP = ROOT / "build" / "ios-simulator" / "pycon-us.app"
DEFAULT_OUT = Path.home() / "Movies" / "pycon-us-flet-demo"

FAKE_NOW = "2026-05-15T09:41:00-07:00"
"""Friday, four minutes before the keynote: the moment a clip's first frame shows."""

STATUS_BAR = "--batteryState charged --batteryLevel 100 --cellularBars 4 --wifiBars 3"
"""What the status bar shows besides its time, which `fake_minute()` supplies."""

CLOCK_LEAD = 10.0
"""Seconds from the app starting its fake clock to a clip's first frame: the ready flow, the
settle and the take's opening. The stored clock starts this long before `FAKE_NOW`, so the
clip begins on it (measured on an iPhone 17 simulator, #1016)."""

BOOT_LAG = 3.0
"""Seconds from `simctl launch` returning to the app starting its fake clock: Python boots
and the stored settings are read first (measured on an iPhone 17 simulator, #1016)."""

FIRST_LAUNCH_SECONDS = 25.0
"""The warm-up launch stays up this long, so the live feed is cached before any take."""

SETTLE_SECONDS = 6.0
"""How long a launched app settles before recording, so its first refresh is over."""

HEAD_STILL = 2.0
"""Seconds of the first screen kept before anything moves."""

TAIL_STILL = 2.0
"""Seconds of the last screen kept after everything stops."""

LONGEST_STILL = 4.0
"""A still stretch longer than this is Maestro or a busy host, not a pause in a flow..."""

SHORTENED_STILL = 3.0
"""...and is cut down to this."""

OUTPUT_FPS = 30


@dataclass(frozen=True)
class Clip:
    """One finished video.

    Attributes:
        name: The file's name without `.mp4`; it says what the clip shows.
        flows: The flows filmed, in order, in one recording.
        large_text_between: Raise the text size between the flows, on camera.
        setup: A flow run before the recording starts.
        mock: Whether the scene needs the mock API's URL stored.
    """

    name: str
    flows: tuple[str, ...]
    large_text_between: bool = False
    setup: str | None = None
    mock: bool = False


CLIPS = (
    Clip("getting-around-the-conference", ("getting_around.yaml",)),
    Clip("making-it-yours", ("making_it_yours.yaml",)),
    Clip("finding-things", ("finding_things.yaml",)),
    Clip(
        "dark-mode-and-large-text",
        ("dark_mode.yaml", "large_text.yaml"),
        large_text_between=True,
    ),
    Clip(
        "staff-tools-mock-data",
        ("staff_tools.yaml",),
        setup="subflows/staff_setup.yaml",
        mock=True,
    ),
)


def fake_start(lead: float = 0.0) -> datetime:
    """Return the instant the stored fake clock starts at, `lead` s before `FAKE_NOW`.

    Args:
        lead: Seconds the app's clock runs before the clip's first frame.
    """
    return datetime.fromisoformat(FAKE_NOW) - timedelta(seconds=lead)


def fake_minute(elapsed: float, lead: float = 0.0) -> str:
    """Return the fake clock's time as a status bar shows it, `elapsed` s after its start.

    Args:
        elapsed: Seconds since the app started its fake clock; below 0 reads as 0.
        lead: The lead the clock was stored with (`fake_start()`).
    """
    moment = fake_start(lead) + timedelta(seconds=max(elapsed, 0.0))
    return f"{moment.hour}:{moment.minute:02d}"


def seconds_to_next_minute(elapsed: float, lead: float = 0.0) -> float:
    """Return how long, from `elapsed`, until the fake clock's minute changes.

    Args:
        elapsed: Seconds since the app started its fake clock; below 0 reads as 0.
        lead: The lead the clock was stored with (`fake_start()`).
    """
    seconds = fake_start(lead).second + max(elapsed, 0.0)
    return 60.0 - seconds % 60.0


def scene_prefs(mock_url: str | None, lead: float = 0.0) -> dict[str, Any]:
    """Return a scene's stored preferences, keyed as SharedPreferences writes them.

    Welcome is already seen, the reminders primer already answered, and the Developer
    options hold only what the scene needs. `unlocked` is left out on purpose.

    Args:
        mock_url: The mock API's URL, or None when the clip's scene has no private API.
        lead: Seconds the clock runs before the first frame: it starts that early.
    """
    dev = {"fake_now": fake_start(lead).isoformat()} | (
        {"mock_api_url": mock_url} if mock_url else {}
    )
    return {
        "flutter.pycon.onboarded": True,
        "flutter.pycon.reminders": json.dumps({"primer": "not_now"}),
        "flutter.pycon.dev": json.dumps(dev),
    }


def merged_prefs(stored: dict[str, Any], scene: dict[str, Any]) -> dict[str, Any]:
    """Return `stored` with every app key replaced by the scene's; others are the OS's."""
    kept = {k: v for k, v in stored.items() if not k.startswith("flutter.pycon.")}
    return kept | scene


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


def _run(*command: str, **options: Any) -> str:
    """Run a command, stopping on its failure; return what it printed."""
    done = subprocess.run(
        command, check=True, text=True, stdout=subprocess.PIPE, **options
    )
    return done.stdout.strip()


def _simctl(*args: str) -> str:
    """Run `xcrun simctl` with `args`."""
    return _run("xcrun", "simctl", *args)


class FlowFailed(Exception):
    """A flow failed; the message holds the end of its output."""


class Stage:
    """The simulator of one run, and what is done on it."""

    def __init__(self, udid: str, mock_url: str) -> None:
        """Keep the simulator's id and the mock's URL as this simulator reaches it."""
        self.udid = udid
        self.mock_url = mock_url
        self.clock_started = time.monotonic()

    def set_time(self, text: str) -> None:
        """Show `text` as the status bar's time, with the rest as `STATUS_BAR` says."""
        _simctl(
            "status_bar", self.udid, "override", "--time", text, *STATUS_BAR.split()
        )

    def follow_clock(self, stop: threading.Event) -> None:
        """Set the status bar's time to the fake clock's minute, and again at each change.

        Runs until `stop` is set; a failed `simctl` call is told and the next minute
        tries again, since a clip is worth finishing with a stale minute.
        """
        shown = None
        while not stop.is_set():
            elapsed = time.monotonic() - self.clock_started
            minute = fake_minute(elapsed, CLOCK_LEAD)
            wait = (
                seconds_to_next_minute(elapsed, CLOCK_LEAD) + 0.05
            )  # just after the change
            if minute != shown:
                try:
                    self.set_time(minute)
                    shown = minute
                except subprocess.CalledProcessError as failure:
                    print(f"status bar not set to {minute}: {failure}", flush=True)
                    wait = 1.0
            stop.wait(wait)

    def flow(self, name: str) -> None:
        """Run a flow of `maestro/demo`; a failure stops the run."""
        env = os.environ | {"MAESTRO_CLI_NO_ANALYTICS": "1"}
        command = ["maestro", "--device", self.udid, "test", str(FLOWS / name)]
        done = subprocess.run(
            command, check=False, text=True, env=env, capture_output=True
        )
        if done.returncode:
            raise FlowFailed(f"{name}:\n{done.stdout[-1500:]}")

    def launch(self, clip: Clip | None) -> None:
        """Start the app afresh on the clip's scene; never records."""
        self._store(
            scene_prefs(self.mock_url if clip and clip.mock else None, CLOCK_LEAD)
        )
        self._start()

    def restart_clock(self, clip: Clip) -> None:
        """Start the app again with only its fake clock stored anew, never recording.

        After a clip's setup, which can take minutes: the clock has run on since the
        launch, and the clip must begin on `FAKE_NOW`. What the setup stored, such as
        the staff sign-in, stays.
        """
        scene = scene_prefs(self.mock_url if clip.mock else None, CLOCK_LEAD)
        key = "flutter.pycon.dev"
        self._store({key: scene[key]}, replace_all=False)
        self._start("subflows/staff_ready.yaml")

    def _store(self, scene: dict[str, Any], *, replace_all: bool = True) -> None:
        """Stop the app and write `scene` into its stored preferences.

        Args:
            scene: The keys to store, as `scene_prefs()` has them.
            replace_all: Replace every app key, as a fresh scene does; else only these.
        """
        subprocess.run(
            ["xcrun", "simctl", "terminate", self.udid, BUNDLE],
            check=False,
            capture_output=True,
        )
        data = Path(_simctl("get_app_container", self.udid, BUNDLE, "data"))
        path = data / "Library" / "Preferences" / f"{BUNDLE}.plist"
        path.parent.mkdir(parents=True, exist_ok=True)
        stored = plistlib.loads(path.read_bytes()) if path.exists() else {}
        merged = merged_prefs(stored, scene) if replace_all else stored | scene
        path.write_bytes(plistlib.dumps(merged))
        # The daemon holds the old values; restarted, it reads the file again.
        _simctl(
            "spawn",
            self.udid,
            "launchctl",
            "kickstart",
            "-k",
            "user/foreground/com.apple.cfprefsd.xpc.daemon",
        )

    def _start(self, ready: str = "subflows/ready.yaml") -> None:
        """Launch the app and wait for its first screen, as the flow `ready` says."""
        _simctl("launch", self.udid, BUNDLE)
        # The app's fake clock starts when its Python has booted, a moment after this.
        self.clock_started = time.monotonic() + BOOT_LAG
        self.flow(ready)

    def take(self, clip: Clip, raw: Path) -> None:
        """Film the clip into `raw`, with the app already on its first screen."""
        self.set_time(fake_minute(time.monotonic() - self.clock_started, CLOCK_LEAD))
        recorder = subprocess.Popen(
            [
                "xcrun",
                "simctl",
                "io",
                self.udid,
                "recordVideo",
                "--codec=h264",
                "--force",
                str(raw),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        stop = threading.Event()
        follower = threading.Thread(target=self.follow_clock, args=(stop,), daemon=True)
        follower.start()
        try:
            time.sleep(1.5)
            for index, flow in enumerate(clip.flows):
                if index and clip.large_text_between:
                    _simctl("ui", self.udid, "content_size", "accessibility-large")
                self.flow(flow)
            time.sleep(1.0)
        finally:
            stop.set()
            follower.join(timeout=10)
            recorder.send_signal(signal.SIGINT)  # finalises the file
            try:
                recorder.wait(timeout=60)
            except subprocess.TimeoutExpired:
                recorder.kill()
            finally:
                _simctl("ui", self.udid, "content_size", "large")


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


def _build() -> None:
    """Build the app for the simulator with this checkout's pub cache (§5.8)."""
    env = os.environ | {
        "PUB_CACHE": str(ROOT / "build/pub-cache"),
        "LANG": "en_US.UTF-8",
    }
    _run("uv", "run", "flet", "build", "ios-simulator", "--yes", cwd=ROOT, env=env)


def _check_build() -> None:
    """Stop unless the present build exists and holds this tree's Python (§5.8)."""
    bundle = APP / "serious_python_darwin_serious_python_darwin.bundle" / "app"
    if not bundle.is_dir():
        sys.exit(f"demo_videos: no build at {APP}: pass --build")
    built = ROOT / "build" / "python-app"
    done = subprocess.run(
        ["diff", "-rq", "-x", ".keep", str(built), str(bundle)],
        check=False,
        capture_output=True,
    )
    if done.returncode:
        sys.exit("demo_videos: the build doesn't hold this tree's Python: pass --build")


def record(out: Path, names: list[str] | None, build: bool, model: str) -> None:
    """Film the clips on a new simulator, and leave nothing of this run running.

    Args:
        out: Where the finished clips go.
        names: The clips to film; all of them when None.
        build: Build the app first.
        model: The simulator's device type.
    """
    clips = [c for c in CLIPS if names is None or c.name in names]
    if not clips:
        sys.exit(f"demo_videos: no such clips; these exist: {[c.name for c in CLIPS]}")
    if build:
        _build()
    _check_build()
    out.mkdir(parents=True, exist_ok=True)
    raws = ROOT / "build" / "demo" / "raw"
    raws.mkdir(parents=True, exist_ok=True)
    failed: list[str] = []
    python = sys.executable
    name = f"demo-videos-{os.getpid()}"
    device = (python, "-m", "tools.device")
    mock = (python, "-m", "tools.mock_api.own")
    try:
        udid = _run(*device, "up", "ios", "--name", name, "--model", model, cwd=ROOT)
        _run(*mock, "stop", cwd=ROOT)  # clean: door check-ins live in the mock's memory
        _run(*mock, "start", cwd=ROOT)
        url = _run(*mock, "url", "ios", cwd=ROOT).splitlines()[-1].strip()
        _simctl("ui", udid, "appearance", "light")
        _simctl("install", udid, str(APP))
        stage = Stage(udid, url)
        stage.set_time(
            fake_minute(CLOCK_LEAD, CLOCK_LEAD)
        )  # the clips' own followers take it from here
        stage.launch(None)
        stage.flow("subflows/warm_up.yaml")
        time.sleep(FIRST_LAUNCH_SECONDS)
        for clip in clips:
            try:
                stage.launch(clip)
                if clip.setup:
                    stage.flow(clip.setup)
                    stage.restart_clock(clip)
                time.sleep(SETTLE_SECONDS)
                raw = raws / f"{clip.name}.mp4"
                stage.take(clip, raw)
                final = out / f"{clip.name}.mp4"
                seconds = render(raw, final)
            except (
                FlowFailed,
                subprocess.CalledProcessError,
                OSError,
                ValueError,
            ) as failure:
                # A flow, simctl or the video's reader; the other clips can still be made.
                failed.append(clip.name)
                print(f"{clip.name} failed: {failure}", flush=True)
                continue
            size = final.stat().st_size >> 20
            print(f"{final}: {seconds:.1f} s, {size} MB", flush=True)
    finally:
        # By name, which also finds a simulator whose boot failed. Neither step may skip the other.
        for command in ((*mock, "stop"), (*device, "down", name, "--delete")):
            subprocess.run(command, check=False, cwd=ROOT)
    if failed:
        sys.exit(f"demo_videos: not made: {failed}")


def main(argv: list[str] | None = None) -> None:
    """Parse the command line and run the command."""
    parser = argparse.ArgumentParser(description="Record the demo videos.")
    commands = parser.add_subparsers(dest="command", required=True)
    film = commands.add_parser("record", help="film the clips on a new simulator")
    film.add_argument("--out", type=Path, default=DEFAULT_OUT)
    film.add_argument("--clips", nargs="+", help="by name; every clip by default")
    film.add_argument("--build", action="store_true", help="build the app first")
    film.add_argument("--model", default="iPhone 17")
    look = commands.add_parser("sheets", help="contact sheets of a clip, to read")
    look.add_argument("clip", type=Path)
    look.add_argument("folder", type=Path)
    look.add_argument("--fps", type=float, default=2.0)
    args = parser.parse_args(argv)
    if args.command == "record":
        record(args.out, args.clips, args.build, args.model)
    else:
        sheets(args.clip, args.folder, args.fps)


if __name__ == "__main__":
    main()
