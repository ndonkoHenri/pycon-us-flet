r"""Measure an Android app's cold start the way `docs/testing-and-quality.md` §8 says.

Usage, with the release APK installed and its scene set:

    uv run python -m tools.cold_start --serial emulator-5594 -n 10
    uv run python -m tools.cold_start --serial emulator-5594 -n 10 \\
        --package io.github.ndonkohenri.pyconus.s2 \\
        --uri s2spike://s2/tree/today/deferred --marker "S2 acked"

Each start is `am force-stop`, 2 s, `logcat -c`, `am start -W`, 6 s with no `adb`
traffic, then one `logcat -d -v epoch`: polling during a start adds about 70 ms. The marker
is timed from logcat's `START u0` line (D-112). The first start of a run is left out, and
Maestro's on-device driver is stopped first, since it makes Flutter report a screen reader
(F72). Don't run it while builds run; read the numbers against the reproducer in one window
(D-453).
"""

import argparse
import re
import statistics
import subprocess
import sys
import time

from tools.device import refuse_owners

PACKAGE = "io.github.ndonkohenri.confcompanion"
URI = "confcompanion://app/schedule"
MARKER = "Content shown"
"""The app's line once the cached content has rendered: a proxy, 0.2-0.3 s after the pixels."""

SETTLE_SECONDS = 2.0
QUIET_SECONDS = 6.0
MAESTRO_PACKAGES = ("dev.mobile.maestro", "dev.mobile.maestro.test")

_EPOCH = re.compile(r"^\s*(\d+\.\d+)\s")
_TOTAL_TIME = re.compile(r"^TotalTime:\s*(\d+)", re.MULTILINE)


def marker_ms(log: str, marker: str) -> float | None:
    """Return the ms from logcat's `START u0` to the first line with `marker`, or None.

    Args:
        log: The output of `logcat -d -v epoch`.
        marker: A regular expression for the line that ends the start.
    """
    start = None
    for line in log.splitlines():
        stamp = _EPOCH.match(line)
        if stamp is None:
            continue
        if start is None:
            if "START u0" in line:
                start = float(stamp.group(1))
        elif re.search(marker, line):
            return round((float(stamp.group(1)) - start) * 1000, 1)
    return None


def total_time(output: str) -> int | None:
    """Return `TotalTime` from what `am start -W` printed, or None without one."""
    found = _TOTAL_TIME.search(output)
    return int(found.group(1)) if found else None


def summary(name: str, values: list[float]) -> str:
    """Return a line with the median and the range of `values`, in ms."""
    if not values:
        return f"{name}: no readings"
    return (
        f"{name}: median {statistics.median(values):,.1f} ms "
        f"({min(values):,.1f}-{max(values):,.1f}), n = {len(values)}"
    )


def _adb(serial: str, *args: str) -> str:
    """Run `adb` on `serial` and return its output."""
    return subprocess.run(
        ["adb", "-s", serial, *args], check=True, capture_output=True, text=True
    ).stdout


def one_start(serial: str, package: str, uri: str) -> tuple[str, str]:
    """Run one cold start and return what `am start -W` printed, and the log."""
    _adb(serial, "shell", "am", "force-stop", package)
    time.sleep(SETTLE_SECONDS)
    _adb(serial, "logcat", "-c")
    # No -n: the intent filter picks the activity (D-269).
    started = _adb(
        serial,
        "shell",
        "am",
        "start",
        "-W",
        "-a",
        "android.intent.action.VIEW",
        "-d",
        uri,
    )
    time.sleep(QUIET_SECONDS)
    return started, _adb(serial, "logcat", "-d", "-v", "epoch")


def main(argv: list[str] | None = None) -> None:
    """Run the starts and print the medians."""
    parser = argparse.ArgumentParser(prog="tools.cold_start", description=__doc__)
    parser.add_argument("--serial", required=True)
    parser.add_argument("-n", type=int, default=10, help="starts kept (default 10)")
    parser.add_argument("--package", default=PACKAGE)
    parser.add_argument("--uri", default=URI)
    parser.add_argument("--marker", default=MARKER, help="a regex for the ending line")
    args = parser.parse_args(argv)
    refuse_owners(args.serial)
    for package in MAESTRO_PACKAGES:
        _adb(args.serial, "shell", "am", "force-stop", package)

    one_start(
        args.serial, args.package, args.uri
    )  # the first after an install: left out
    totals: list[float] = []
    markers: list[float] = []
    for run in range(1, args.n + 1):
        started, log = one_start(args.serial, args.package, args.uri)
        total = total_time(started)
        marker = marker_ms(log, args.marker)
        print(f"{run}: TotalTime {total}, marker {marker}", file=sys.stderr)
        if total is not None:
            totals.append(total)
        if marker is None:
            print(f"{run}: no line matched {args.marker!r}", file=sys.stderr)
        else:
            markers.append(marker)
    print(summary("TotalTime", totals))
    print(summary(args.marker, markers))


if __name__ == "__main__":
    main()
