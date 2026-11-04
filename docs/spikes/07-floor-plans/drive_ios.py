"""Drive the S7 reproducer on an iOS simulator with Maestro and measure it (#361).

Run from this folder with the debug build installed and launched:

    S7_UDID=<udid> uv run python drive_ios.py <step> [<arg> ...] [/ <step> ...]

Steps (each prints `S7-DRIVE` lines):

- `tap <text>`: Maestro's `tapOn` the text (the free local CLI, never Cloud).
- `point <x> <y>`: a tap at a point, in points.
- `swipe <x1> <y1> <x2> <y2>`: one drag, in points.
- `pans <n>`: n drags across the plan, in four directions.
- `mem <label>`: the app's `phys_footprint` and its peak (`footprint`), in MB.
"""

import os
import re
import subprocess
import sys
import tempfile

UDID = os.environ.get("S7_UDID", "")
APP = "io.github.ndonkohenri.pyconus.s7plans"
PROCESS = "floor-plans-spike"


def say(event: str, **values: object) -> None:
    """Print one driver line."""
    print(
        f"S7-DRIVE {event} " + " ".join(f"{k}={v}" for k, v in values.items()),
        flush=True,
    )


def maestro(commands: str) -> None:
    """Run a few Maestro commands against the app on UDID."""
    flow = f"appId: {APP}\n---\n{commands}\n"
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as file:
        file.write(flow)
    subprocess.run(
        ["maestro", "--device", UDID, "test", file.name],
        capture_output=True,
        text=True,
        check=False,
    )


def pid() -> str:
    """Return the app's process id on the host."""
    return subprocess.run(
        ["pgrep", "-n", PROCESS], capture_output=True, text=True, check=False
    ).stdout.strip()


def mem(label: str) -> None:
    """Print the app's footprint and its peak, in MB."""
    foot = subprocess.run(
        ["footprint", pid()], capture_output=True, text=True, check=False
    ).stdout
    now = re.search(r"phys_footprint:\s+([\d.]+) MB", foot)
    peak = re.search(r"phys_footprint_peak:\s+([\d.]+) MB", foot)
    say(
        "mem",
        label=label,
        footprint_mb=now[1] if now else None,
        peak_mb=peak[1] if peak else None,
    )


def main() -> None:
    """Run the steps named on the command line, separated by `/`."""
    words = sys.argv[1:]
    while words:
        cut = words.index("/") if "/" in words else len(words)
        run(words[0], words[1:cut])
        words = words[cut + 1 :]


def run(step: str, args: list[str]) -> None:
    """Run one step."""
    if step == "tap":
        maestro(f'- tapOn: ".*{" ".join(args)}.*"')
    elif step == "point":
        maestro(f'- tapOn:\n    point: "{args[0]},{args[1]}"')
    elif step == "swipe":
        x1, y1, x2, y2 = args
        maestro(
            f'- swipe:\n    start: "{x1},{y1}"\n    end: "{x2},{y2}"\n    duration: 400'
        )
    elif step == "pans":
        moves = [
            (330, 500, 70, 500),
            (70, 500, 330, 500),
            (200, 650, 200, 350),
            (200, 350, 200, 650),
        ]
        steps = "\n".join(
            f'- swipe:\n    start: "{a},{b}"\n    end: "{c},{d}"\n    duration: 400'
            for i in range(int(args[0]))
            for a, b, c, d in [moves[i % 4]]
        )
        maestro(steps)
    elif step == "mem":
        mem(args[0] if args else "now")


if __name__ == "__main__":
    main()
