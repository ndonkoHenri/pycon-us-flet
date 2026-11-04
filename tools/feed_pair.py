"""Serve a change-log feed pair from this machine, for the change log's device check (#460).

The pair is the recorded feed of the active year and a copy with named edits, built by
`tests/feeds.py` (D-255), served at one feed URL by `tests/ui/feeds.py`'s
`PairFeed`: the old feed until it is swapped, then the new one. In Developer options,
set the feed URL it prints and Refresh now (no batch: the first refresh from a new URL
is not diffed), save the session, swap, and Refresh now: the app records the change as
it would a real one (testing-and-quality.md §9.2):

    uv run python -m tools.feed_pair --move 123 "Room 103ABC" --move 142 "Room 101B"
    curl -X POST http://127.0.0.1:8460/swap    # serve the new feed; /reset: the old one
    curl -X POST http://127.0.0.1:8460/hold    # keep feed requests open; /release answers them

It prints the changes the app will find, the feed URL on the Android emulator and on the
iOS simulator, and the Maestro command of `maestro/journeys/change_log.yaml`, then
serves until Ctrl-C. Both addresses are the Mac's loopback, so a physical phone cannot
reach them.
"""

import argparse
import sys
import threading
from collections.abc import Sequence

from pycon_us.config import YEAR, load_year
from pycon_us.core.diff import diff
from pycon_us.core.feed import process
from tests.feeds import Edit, add, move, pair, remove, rename, retime
from tests.ui.feeds import PairFeed

DEFAULT_PORT = 8460
"""The port it serves on by default, the one the change-log flow assumes."""

EMULATOR_HOST = "10.0.2.2"
"""The laptop's loopback as the Android emulator reaches it."""

SIMULATOR_HOST = "127.0.0.1"
"""The laptop's loopback as the iOS simulator reaches it (it shares the Mac's network)."""


def parser() -> argparse.ArgumentParser:
    """Return the command line's parser: the edits, each repeatable, and the port."""
    parser = argparse.ArgumentParser(
        description="Serve the recorded feed, then a copy with edits, at one feed URL."
    )
    edits = parser.add_argument_group("edits (at least one; applied in this order)")
    edits.add_argument(
        "--move",
        nargs=2,
        action="append",
        default=[],
        metavar=("KEY", "ROOM"),
        help="move a slot to another room",
    )
    edits.add_argument(
        "--retime",
        nargs=3,
        action="append",
        default=[],
        metavar=("KEY", "START", "END"),
        help="give a slot new ISO 8601 times, with their offsets",
    )
    edits.add_argument(
        "--rename",
        nargs=2,
        action="append",
        default=[],
        metavar=("KEY", "NAME"),
        help="rename a slot",
    )
    edits.add_argument(
        "--add",
        nargs=3,
        action="append",
        default=[],
        metavar=("KEY", "LIKE", "NAME"),
        help="add slot KEY, a copy of slot LIKE named NAME",
    )
    edits.add_argument(
        "--remove",
        action="append",
        default=[],
        metavar="KEY",
        help="remove a slot from the schedule",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"the port to serve on (default: {DEFAULT_PORT})",
    )
    return parser


def edits_of(args: argparse.Namespace) -> list[Edit]:
    """Return the named edits the arguments ask for, moves first and removals last.

    Raises:
        ValueError: A slot key is not a number.
    """
    return [
        *(move(int(key), room) for key, room in args.move),
        *(retime(int(key), start, end) for key, start, end in args.retime),
        *(rename(int(key), name) for key, name in args.rename),
        *(add(int(key), int(like), name) for key, like, name in args.add),
        *(remove(int(key)) for key in args.remove),
    ]


def expected(old: bytes, new: bytes) -> list[str]:
    """Return a line per change the app's diff finds from `old` to `new`.

    The app's own parser and diff, with the active year's feed settings, so the
    edits are checked before a device is: an edit of a break finds nothing.
    """
    settings = load_year(YEAR).feed_settings
    changes = diff(process(old, settings), process(new, settings))
    return [f"  {change.kind} of {change.id}: {change.title}" for change in changes]


def report(changes: Sequence[str], port: int) -> list[str]:
    """Say what the app will find, where it reaches the feed and how to swap it.

    Returns:
        The report's lines.
    """
    path = f"conference-{YEAR}.json"
    control = f"http://{SIMULATOR_HOST}:{port}"
    flow = "maestro/journeys/change_log.yaml"
    return [
        f"Serving the recorded {YEAR} feed, then, once swapped, a copy the app diffs as:",
        *changes,
        "In Developer options, set the feed URL, Apply, then Refresh now:",
        f"  Android emulator: http://{EMULATOR_HOST}:{port}/{path}",
        f"  iOS simulator:    http://{SIMULATOR_HOST}:{port}/{path}",
        f"Swap to the new feed: curl -X POST {control}/swap   (old again: /reset)",
        "Maestro, on your own device:",
        f"  maestro --device <id> test -e FEED_URL=<its URL above> -e CONTROL_URL={control}",
        f"    {flow}",
        "Serving until Ctrl-C.",
    ]


def wait() -> None:
    """Block until Ctrl-C (`KeyboardInterrupt`); the server runs on its own thread."""
    threading.Event().wait()


def main(argv: Sequence[str] | None = None) -> int:
    """Build the pair, say what it holds, and serve it until Ctrl-C.

    Args:
        argv: The command-line arguments; `sys.argv[1:]` when None.

    Returns:
        The exit status: 0 after Ctrl-C, 1 when the edits find no change.
    """
    cli = parser()
    args = cli.parse_args(argv)
    try:
        edits = edits_of(args)
    except ValueError as error:
        cli.error(f"a slot key must be a number: {error}")
    if not edits:
        cli.error("give at least one edit, such as --move 123 'Room 103ABC'")
    try:
        old, new = pair(YEAR, *edits)
    except StopIteration:  # tests.feeds.slot() found no slot with that conf_key
        cli.error(f"an edit names a slot key the recorded {YEAR} feed does not have")
    changes = expected(old, new)
    if not changes:
        print("Nothing served: the app finds no change in that pair.", file=sys.stderr)
        return 1
    feed = PairFeed(old, new, args.port)
    feed.serve()
    print("\n".join(report(changes, feed.port)), flush=True)
    try:
        wait()
    except KeyboardInterrupt:
        pass
    finally:
        feed.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
