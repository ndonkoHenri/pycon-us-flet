"""Tests for the last-resort error net and the logging setup (D-71, D-72).

``report_errors`` is checked on sync and async callables against a fake page bound as
Flet binds a session's page to a handler's context; that Flet then keeps the session
alive is checked on devices (the PR).
"""

import ast
import asyncio
import inspect
import io
import logging
import sys
from collections.abc import Iterator
from pathlib import Path

import flet as ft
import httpx
import pytest
from flet.utils import get_param_count

import pycon_us
from pycon_us.services import errors
from pycon_us.services.errors import (
    HANDLER_NAME,
    MESSAGE,
    QUIET_LOGGERS,
    report_errors,
    setup_logging,
)
from tests.fakes import FakePage, bound


@pytest.fixture
def page() -> Iterator[FakePage]:
    """A fake page bound to ``ft.context.page``, as during a handler or an effect."""
    fake = FakePage()
    with bound(fake):
        yield fake


@pytest.fixture
def embedded(monkeypatch: pytest.MonkeyPatch) -> None:
    """A packaged build with Developer locked."""
    monkeypatch.setattr(errors, "is_embedded", lambda: True)
    monkeypatch.setattr(errors, "_details", False)


def snack_text(page: FakePage) -> str:
    """The text of the one SnackBar shown, which floats."""
    (dialog,) = page.dialogs
    assert isinstance(dialog, ft.SnackBar)
    assert dialog.behavior == ft.SnackBarBehavior.FLOATING
    assert isinstance(dialog.content, ft.Text)
    return str(dialog.content.value)


def fail(event: object) -> None:
    """A handler that raises ``ValueError("bad value")``."""
    raise ValueError("bad value")


async def fail_async(event: object) -> None:
    """An async handler that raises ``ValueError("bad value")`` after a yield."""
    await asyncio.sleep(0)
    raise ValueError("bad value")


# ------------------------------------------------------------------ report_errors


def test_a_sync_handler_that_raises_is_logged_with_its_traceback_and_returns_none(
    page: FakePage, caplog: pytest.LogCaptureFixture
) -> None:
    """A raising sync handler returns None and logs an error naming it, with traceback.

    The traceback carries the exception's text.
    """
    assert report_errors(fail)(object()) is None

    (record,) = [r for r in caplog.records if r.name == errors.__name__]
    assert record.levelno == logging.ERROR
    assert record.getMessage() == f"Unexpected error in {__name__}.fail"
    assert record.exc_info is not None
    assert record.exc_info[0] is ValueError
    assert "bad value" in caplog.text  # the traceback is in the log


async def test_an_async_handler_that_raises_is_logged_with_its_traceback_and_returns_none(
    page: FakePage, caplog: pytest.LogCaptureFixture
) -> None:
    """A raising async handler returns None and logs an error naming it, with traceback.

    The logged exception is the handler's ``ValueError``.
    """
    assert await report_errors(fail_async)(object()) is None

    (record,) = [r for r in caplog.records if r.name == errors.__name__]
    assert record.getMessage() == f"Unexpected error in {__name__}.fail_async"
    assert record.exc_info is not None
    assert record.exc_info[0] is ValueError


def test_a_caught_error_tells_the_user_without_details_in_a_packaged_build(
    page: FakePage, embedded: None
) -> None:
    """In a packaged build, a caught error shows "Something went wrong" alone."""
    report_errors(fail)(object())
    assert snack_text(page) == "Something went wrong"


async def test_an_async_caught_error_tells_the_user_too(
    page: FakePage, embedded: None
) -> None:
    """In a packaged build, a caught async error shows the same plain message."""
    await report_errors(fail_async)(object())
    assert snack_text(page) == MESSAGE


def test_a_caught_error_shows_the_exception_when_not_embedded(
    page: FakePage, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Outside a packaged build, the message adds the exception's type and text."""
    monkeypatch.setattr(errors, "is_embedded", lambda: False)
    report_errors(fail)(object())
    assert snack_text(page) == "Something went wrong: ValueError: bad value"


def test_a_packaged_build_shows_the_exception_once_developer_is_unlocked(
    page: FakePage, embedded: None
) -> None:
    """In a packaged build, unlocking Developer adds the exception; locking drops it."""
    errors.show_details(True)  # bootstrap() and the unlock in About this app (D-187)
    report_errors(fail)(object())
    errors.show_details(False)  # #107's Reset app locks it again
    report_errors(fail)(object())
    first, second = page.dialogs
    assert isinstance(first, ft.SnackBar) and isinstance(second, ft.SnackBar)
    assert isinstance(first.content, ft.Text) and isinstance(second.content, ft.Text)
    assert first.content.value == "Something went wrong: ValueError: bad value"
    assert second.content.value == MESSAGE


def test_a_handler_that_succeeds_returns_its_value_and_shows_nothing(
    page: FakePage, caplog: pytest.LogCaptureFixture
) -> None:
    """A sync handler that succeeds gets its arguments and returns its value.

    Nothing is shown or logged.
    """

    def cleanup() -> None:
        pass

    def effect(a: int, *, b: int) -> object:
        assert (a, b) == (1, 2)
        return cleanup  # a sync effect's cleanup must reach Flet (F2)

    assert report_errors(effect)(1, b=2) is cleanup
    assert page.dialogs == []
    assert caplog.records == []


async def test_an_async_handler_that_succeeds_returns_its_value(page: FakePage) -> None:
    """An async handler that succeeds returns its value and shows nothing."""

    async def handler(a: int) -> int:
        return a + 1

    assert await report_errors(handler)(1) == 2
    assert page.dialogs == []


async def test_cancelled_error_is_re_raised_and_not_reported(
    page: FakePage, caplog: pytest.LogCaptureFixture
) -> None:
    """A ``CancelledError`` from a handler is raised again, neither shown nor logged."""

    async def cancelled() -> None:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await report_errors(cancelled)()
    assert page.dialogs == []
    assert caplog.records == []


async def test_cancelling_a_wrapped_effect_task_still_cancels_it(
    page: FakePage,
) -> None:
    """Cancelling a wrapped effect's task, as Flet does, cancels it; nothing shows."""
    started = asyncio.Event()

    async def effect() -> None:
        started.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(report_errors(effect)())
    await started.wait()
    task.cancel()  # what Flet does to an effect's task on a re-run or unmount (F2)
    with pytest.raises(asyncio.CancelledError):
        await task
    assert task.cancelled()
    assert page.dialogs == []


def test_base_exceptions_other_than_exception_pass_through(page: FakePage) -> None:
    """A ``KeyboardInterrupt`` passes through the net, and nothing is shown."""

    def interrupted() -> None:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        report_errors(interrupted)()
    assert page.dialogs == []


def test_the_wrapper_keeps_what_flet_reads_to_call_a_handler() -> None:
    """The wrapper keeps the handler's async-ness, parameter count, name and doc.

    ``inspect.unwrap`` also finds the handler behind it.
    """

    async def no_args() -> None:
        pass

    def one_arg(e: ft.Event[ft.Button]) -> None:
        pass

    wrapped_async = report_errors(no_args)
    wrapped_sync = report_errors(one_arg)

    assert inspect.iscoroutinefunction(wrapped_async)
    assert not inspect.iscoroutinefunction(wrapped_sync)
    # Flet calls a handler with the event only when it declares a parameter.
    assert get_param_count(wrapped_async) == 0
    assert get_param_count(wrapped_sync) == 1
    assert inspect.unwrap(wrapped_sync) is one_arg
    assert wrapped_sync.__name__ == "one_arg"
    assert wrapped_sync.__doc__ == one_arg.__doc__


def test_generator_functions_are_refused_when_wrapped() -> None:
    """Wrapping a generator or an async generator function raises ``TypeError``."""

    def generator():
        yield

    async def async_generator():
        yield

    with pytest.raises(TypeError, match="generator"):
        report_errors(generator)
    with pytest.raises(TypeError, match="generator"):
        report_errors(async_generator)


def test_an_error_with_no_page_to_show_it_on_is_still_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An error with no page to show it on is logged, then the failure to show it.

    No page is in the context: ``ft.context.page`` raises, as in a replaced session
    (F30).
    """
    assert report_errors(fail)(object()) is None

    messages = [r.getMessage() for r in caplog.records]
    assert messages == [
        f"Unexpected error in {__name__}.fail",
        "Could not show the error message",
    ]


SRC = Path(pycon_us.__file__).parent.parent
NETTED = [
    SRC / "main.py",
    SRC / "pycon_us" / "routes.py",
    *sorted((SRC / "pycon_us" / "screens").glob("*.py")),
    *sorted((SRC / "pycon_us" / "ui").glob("*.py")),
]
"""Modules whose nested functions are all handlers or effect setups (D-163).

``app.py`` is left out on purpose: its nested ``router()`` is a provider's child
builder, not a handler, so review checks that module's wrapping instead.
"""


@pytest.mark.parametrize("path", NETTED, ids=lambda p: p.name)
def test_every_handler_and_effect_a_screen_defines_is_wrapped(path: Path) -> None:
    """Every function nested in another, in a netted module, has ``report_errors``.

    Screens, the route table and main() define functions only to hand them to Flet as
    handlers or effects, so one without the net would end the session when it raises.
    Top-level functions are not checked.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    unwrapped = [
        f"{outer.name}.{inner.name}"
        for outer in ast.walk(tree)
        if isinstance(outer, ast.FunctionDef | ast.AsyncFunctionDef)
        for inner in ast.walk(outer)
        if inner is not outer
        and isinstance(inner, ast.FunctionDef | ast.AsyncFunctionDef)
        and not any(
            isinstance(d, ast.Name) and d.id == "report_errors"
            for d in inner.decorator_list
        )
    ]
    assert unwrapped == []


# ------------------------------------------------------------------ setup_logging


def ours(root: logging.Logger) -> list[logging.Handler]:
    """The handlers on ``root`` that ``setup_logging()`` added."""
    return [h for h in root.handlers if h.get_name() == HANDLER_NAME]


@pytest.fixture
def clean_logging(monkeypatch: pytest.MonkeyPatch) -> Iterator[logging.Logger]:
    """Start from loggers setup_logging() has not touched, and restore them afterwards.

    The loggers are process-wide, so a test that ran setup_logging() earlier, or an
    import of ``main``, would otherwise decide what these tests see.
    """
    monkeypatch.delenv("FLET_LOG_LEVEL", raising=False)
    root = logging.getLogger()
    level, earlier = root.level, ours(root)
    quiet = {name: logging.getLogger(name).level for name in QUIET_LOGGERS}
    for handler in earlier:
        root.removeHandler(handler)
    for name in QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.NOTSET)
    yield root
    # Only our handler: pytest adds and removes its own capture handlers per phase.
    for handler in ours(root):
        root.removeHandler(handler)
    for handler in earlier:
        root.addHandler(handler)
    root.setLevel(level)
    for name, old in quiet.items():
        logging.getLogger(name).setLevel(old)


def test_setup_logging_adds_one_stderr_handler_at_info(
    clean_logging: logging.Logger,
) -> None:
    """Setting up logging twice adds one stderr handler and sets the root to INFO."""
    setup_logging()
    setup_logging()  # a second call adds no handler

    (handler,) = ours(clean_logging)
    assert isinstance(handler, logging.StreamHandler)
    assert handler.stream is sys.stderr
    assert clean_logging.level == logging.INFO


def test_a_second_setup_logging_call_keeps_the_levels_set_since(
    clean_logging: logging.Logger,
) -> None:
    """A second setup keeps the levels set on the root and httpx since the first."""
    setup_logging()
    clean_logging.setLevel(logging.DEBUG)
    logging.getLogger("httpx").setLevel(logging.INFO)

    setup_logging()

    assert clean_logging.level == logging.DEBUG
    assert logging.getLogger("httpx").level == logging.INFO


def test_log_lines_carry_the_time_level_logger_and_message(
    clean_logging: logging.Logger,
) -> None:
    """A log line reads ``HH:MM:SS.mmm LEVEL logger: message``."""
    setup_logging()
    (handler,) = ours(clean_logging)
    record = logging.LogRecord(
        "pycon_us.state", logging.WARNING, "", 0, "x %d", (1,), None
    )
    line = handler.format(record)
    time, rest = line.split(" ", 1)
    assert rest == "WARNING pycon_us.state: x 1"
    assert len(time) == len("12:34:56.789") and time[2] == ":" and time[8] == "."


@pytest.mark.parametrize(
    ("value", "level"),
    [("debug", logging.DEBUG), ("info", logging.INFO), ("nonsense", logging.INFO)],
)
def test_flet_log_level_sets_the_level(
    clean_logging: logging.Logger,
    monkeypatch: pytest.MonkeyPatch,
    value: str,
    level: int,
) -> None:
    """The ``FLET_LOG_LEVEL`` variable sets the root's level; an unknown one is INFO."""
    monkeypatch.setenv("FLET_LOG_LEVEL", value)  # flet run -v / -vv
    setup_logging()
    assert clean_logging.level == level


async def test_request_urls_with_personal_data_stay_out_of_the_log(
    clean_logging: logging.Logger, caplog: pytest.LogCaptureFixture
) -> None:
    """Once set up, httpx logs no request URL, so its key, email and code stay out.

    The quiet loggers are at WARNING.
    """
    secret = "s3cr3t-key"
    email = "attendee@example.org"
    badge = "B4DGE-CODE"
    url = f"https://mock.test/api/v1/scan?email={email}&code={badge}&key={secret}"

    async def request() -> None:
        transport = httpx.MockTransport(lambda request: httpx.Response(200))
        async with httpx.AsyncClient(transport=transport) as client:
            await client.get(url)

    # Without the setup, httpx logs the whole URL at INFO: the check below can fail.
    caplog.set_level(logging.INFO)
    await request()
    assert badge in caplog.text
    caplog.clear()

    setup_logging()
    await request()
    for value in (secret, email, badge):
        assert value not in caplog.text
    for name in QUIET_LOGGERS:
        assert logging.getLogger(name).level == logging.WARNING


def test_an_email_address_never_reaches_the_shared_log(
    clean_logging: logging.Logger,
) -> None:
    """The handler writes each email address as ``<email>``, tracebacks included.

    A line can quote what the app does not control: a platform error that repeats a
    mailto: intent (D-182), or a skipped feed record. console.log, which Share log
    sends, holds what this handler writes (D-72, D-196).
    """
    setup_logging()
    (handler,) = ours(clean_logging)
    written = io.StringIO()
    assert isinstance(handler, logging.StreamHandler)
    handler.setStream(written)
    logger = logging.getLogger("pycon_us.test")
    logger.warning("Skipped a feed record: contact %s", "Ana.Lima+pycon@example.org")
    try:
        raise RuntimeError("No Activity found for mailto:coc%40us.pycon.org")
    except RuntimeError:
        logger.exception("Unexpected error in pycon_us.ui.links.open_link")
    line = written.getvalue()
    assert "example.org" not in line and "pycon.org" not in line
    assert "Skipped a feed record: contact <email>" in line
    assert "mailto:<email>" in line  # in the traceback too
    assert "pycon_us.ui.links.open_link" in line  # the rest is kept


@pytest.mark.parametrize(
    "text",
    ["@ft.component", "flet@1.1.0", "https://fosstodon.org/@pycon", "user@localhost"],
)
def test_text_that_is_not_an_address_is_kept(text: str) -> None:
    """Text with an ``@`` that is not an email address is kept as it is."""
    assert errors.EMAIL.sub(errors.REDACTED_EMAIL, text) == text
