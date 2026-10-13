"""The last-resort error net for handlers and effects, and the app's logging setup.

Expected failures are handled where they happen and become visible state (D-71,
architecture §16.1). ``report_errors`` is for the rest: an exception that escapes an
event handler ends the session, and one that escapes an async effect is seen by nobody
(F4, F37). Delete it once Flet makes handler errors non-fatal (U15).

``setup_logging()`` sends stdlib ``logging`` to stderr, which a packaged app tees to
logcat or the unified log and to ``console.log`` (F14, D-72). Never log secrets, keys,
signatures, emails or badge codes.
"""

import functools
import inspect
import logging
import os
from collections.abc import Callable, Coroutine
from typing import Any, overload

import flet as ft
from flet.utils import is_embedded

logger = logging.getLogger(__name__)

MESSAGE = "Something went wrong"
"""What the user reads when ``report_errors`` catches an exception (ux.md §4.5)."""

LOG_FORMAT = "%(asctime)s.%(msecs)03d %(levelname)s %(name)s: %(message)s"
"""Device time first: logcat and the unified log stamp lines, ``console.log`` does not."""

LOG_DATE_FORMAT = "%H:%M:%S"

HANDLER_NAME = "pycon_us.console"
"""Names the handler ``setup_logging()`` adds, so a second call finds it."""

QUIET_LOGGERS = ("httpx", "httpcore")
"""Kept at WARNING: httpx logs every request's URL at INFO, query string included, and
P3's private-API requests may carry what D-72 forbids in a log."""

_details = False
"""Whether a packaged build shows the exception text too: Developer is unlocked (D-73)."""


def show_details(on: bool) -> None:
    """Show the exception text in packaged builds too, or stop showing it (D-73, D-184).

    Without it, only an app that is not embedded (the companion app) shows the text.
    ``bootstrap()`` sets it from the stored unlock, and About this app when it unlocks.

    Args:
        on: Whether Developer is unlocked (``Prefs.developer_unlocked``).
    """
    global _details
    _details = on


@overload
def report_errors[**P, R](
    fn: Callable[P, Coroutine[Any, Any, R]],
) -> Callable[P, Coroutine[Any, Any, R | None]]: ...


@overload
def report_errors[**P, R](fn: Callable[P, R]) -> Callable[P, R | None]: ...


def report_errors(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap a handler or effect so an unexpected exception is reported, not fatal.

    The wrapper logs the exception with its traceback and the wrapped function's name,
    shows a floating "Something went wrong" SnackBar (with the exception when not
    embedded or once Developer is unlocked, D-73) and returns None; the session goes
    on. ``CancelledError`` and other ``BaseException``s propagate, so cancelling an
    effect still cancels it. The log
    holds the exception's message verbatim, so code that can raise must keep URLs,
    tokens and badge codes out of its messages (D-72).

    A coroutine function gets an ``async def`` wrapper and anything else a plain one,
    both made with ``functools.wraps``: Flet checks ``inspect.iscoroutinefunction``
    and counts parameters through ``__wrapped__`` to decide how to call a handler.

    Args:
        fn: The handler or effect to wrap.

    Returns:
        The wrapper.

    Raises:
        TypeError: ``fn`` is a generator or async generator function. Flet iterates a
            generator handler only when the handler itself is one, which a wrapper is
            not, so it would silently never run.
    """
    if inspect.isgeneratorfunction(fn) or inspect.isasyncgenfunction(fn):
        raise TypeError(f"report_errors cannot wrap a generator function: {fn!r}")
    where = f"{getattr(fn, '__module__', '')}.{getattr(fn, '__qualname__', repr(fn))}"

    if inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def run_async(*args: Any, **kwargs: Any) -> Any:
            try:
                return await fn(*args, **kwargs)
            except Exception as error:  # CancelledError is a BaseException: it passes
                logger.exception("Unexpected error in %s", where)
                _tell_user(error)
                return None

        return run_async

    @functools.wraps(fn)
    def run(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except Exception as error:
            logger.exception("Unexpected error in %s", where)
            _tell_user(error)
            return None

    return run


def _tell_user(error: Exception) -> None:
    detailed = _details or not is_embedded()
    text = f"{MESSAGE}: {type(error).__name__}: {error}" if detailed else MESSAGE
    try:
        ft.context.page.show_dialog(
            ft.SnackBar(ft.Text(text), behavior=ft.SnackBarBehavior.FLOATING)
        )
    except Exception:
        # No page in this context, or a session already replaced (F30): the log is all
        # that can be done, and the net itself must never raise.
        logger.warning("Could not show the error message", exc_info=True)


def setup_logging() -> None:
    """Send the app's log records to stderr, once per process.

    One handler on the root logger, at INFO, or at the level ``FLET_LOG_LEVEL`` names
    (``flet run -vv`` sets ``debug``; Flet's own handling of it does nothing once a
    handler exists). ``QUIET_LOGGERS`` stay at WARNING. A packaged app replaces
    ``sys.stderr`` with a tee to the platform log and ``console.log`` before the app is
    imported (F14), so the handler writes to both. Once the handler is there, a second
    call returns at once: it neither adds a handler nor resets a level set since.
    """
    root = logging.getLogger()
    if any(handler.get_name() == HANDLER_NAME for handler in root.handlers):
        return
    handler = logging.StreamHandler()  # sys.stderr as it is now: the tee
    handler.set_name(HANDLER_NAME)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
    root.addHandler(handler)
    level = logging.getLevelName(os.getenv("FLET_LOG_LEVEL", "info").strip().upper())
    root.setLevel(level if isinstance(level, int) else logging.INFO)
    for name in QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
