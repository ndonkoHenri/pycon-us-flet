"""Run the staff tour once per text size and appearance, for a person to read the images.

Usage, with the packaged build installed on a device of your own::

    uv run python -m tools.sweep --device <id> [--modes max dark contrast ...]

It starts this checkout's mock, or keeps the one running, and leaves it up for the next run
(``uv run python -m tools.mock_api.own stop`` ends it). For each mode, ``default max`` unless
named, it signs in afresh at the default text size, since a chosen session or category would
hide its picker, sets the device (``tools/device.py``) and runs
``maestro/sweeps/staff_tour.yaml``. Images land under ``build/sweep/<mode>/``, in each run's
``takeScreenshot/``. A mode that fails doesn't stop the rest, and the device goes back to its
defaults at the end. No images are judged here: look at each one
(``docs/testing-and-quality.md`` §7.2).
"""

import argparse
import subprocess
import sys
from pathlib import Path

from tools import device
from tools.mock_api import own

MODES = {
    "default": [],
    "max": ["--text", "max", "--bold"],
    "dark": ["--dark"],
    "contrast": ["--contrast"],
    "dark-contrast": ["--dark", "--contrast"],
    "max-dark-contrast": ["--text", "max", "--bold", "--dark", "--contrast"],
}
"""Each mode's ``tools.device prefs`` options: checklist items 3 and 4 of §9."""

TOUR_SECONDS = 900
"""How long one tour may take on a busy host, so one stuck run can't hold the rest."""


def maestro_command(
    serial: str, platform: str, port: int, flow: str, output: Path
) -> list[str]:
    """Return the line that runs a sweep flow against this checkout's mock."""
    return [
        *["maestro", "--device", serial, "test"],
        *["-e", f"MOCK_URL={own.url(port, platform)}"],
        *["--test-output-dir", str(output)],
        f"maestro/sweeps/{flow}.yaml",
    ]


def run_flow(command: list[str]) -> bool:
    """Run a flow and return whether it passed; a hung one counts as failed."""
    try:
        return (
            subprocess.run(command, check=False, timeout=TOUR_SECONDS).returncode == 0
        )
    except subprocess.TimeoutExpired:
        return False


def main(argv: list[str] | None = None) -> None:
    """Run the sign-in and the tour in each mode, and say which passed."""
    parser = argparse.ArgumentParser(prog="tools.sweep", description=__doc__)
    parser.add_argument("--device", required=True, help="a serial or a udid")
    parser.add_argument(
        "--modes", nargs="+", choices=sorted(MODES), default=["default", "max"]
    )
    parser.add_argument("--output", type=Path, default=Path("build/sweep"))
    args = parser.parse_args(argv)
    device.refuse_owners(args.device)
    platform = "android" if device.is_emulator(args.device) else "ios"
    port = own.start(own.ROOT / "build" / "mock", [])

    def flow(name: str, folder: Path) -> bool:
        """Run one sweep flow, with its output in ``folder``."""
        return run_flow(maestro_command(args.device, platform, port, name, folder))

    def run_mode(mode: str) -> bool:
        """Run one mode's sign-in and tour; a device that refuses a setting fails the mode."""
        try:
            device.main(["prefs", args.device, "--reset"])
            if not flow("sign_in", args.output / mode / "sign-in"):
                return False
            device.main(["prefs", args.device, *MODES[mode]])
        except (SystemExit, subprocess.CalledProcessError) as error:
            print(f"sweep.py: {mode}: {error}", file=sys.stderr)
            return False
        return flow("staff_tour", args.output / mode)

    passed = {}
    try:
        for mode in args.modes:
            passed[mode] = run_mode(mode)
    finally:
        device.main(["prefs", args.device, "--reset"])
    for mode, ok in passed.items():
        print(
            f"{mode}: {'reached every state' if ok else 'FAILED'}: {args.output / mode}"
        )
    if not all(passed.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
