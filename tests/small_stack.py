"""Deep JSON and a small stack to overflow on, the same way on every platform (#848, #891).

Python 3.14 limits recursion in C by the stack that is really there, so whether a depth
overflows on the main thread differs between macOS and Linux. On this stack the parser
stops at about 2,300 levels on both, and printing or dumping what it read before that.
"""

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

TOO_DEEP_TO_PARSE = 100_000
"""Levels that overflow the parser on a small stack, though not on Linux's main thread."""

DEPTHS = [int(100 * 1.05**step) for step in range(142)]
"""About 100 to 100,000 levels in steps of 5%, so a sweep goes through any window of
depths the parser takes and what comes after it doesn't: about a tenth of the depth wide,
and in a place that differs per platform."""


def on_a_small_stack[T](call: Callable[[], T]) -> T:
    """Return ``call()``'s result (or raise its error) from a thread with a small stack."""
    previous = threading.stack_size(512 * 1024)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(call).result()
    finally:
        threading.stack_size(previous)


def nested_lists(depth: int) -> bytes:
    """JSON arrays nested ``depth`` deep, the innermost one empty."""
    return b"[" * depth + b"]" * depth


def nested_objects(depth: int) -> bytes:
    """JSON objects nested ``depth`` deep: printing them takes more stack than parsing."""
    return b'{"a":' * depth + b"1" + b"}" * depth
