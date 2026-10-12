"""Tests for the last-resort error net and the logging setup (D-71, D-72).

``report_errors`` is checked on sync and async callables against a fake page bound as
Flet binds a session's page to a handler's context; that Flet then keeps the session
alive is checked on devices (the PR).
"""

import asyncio
import inspect
import logging
import sys
from collections.abc import Iterator

import flet as ft
import httpx
import pytest
from flet.utils import get_param_count

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
    monkeypatch.setattr(errors, "is_embedded", lambda: True)


def snack_text(page: FakePage) -> str:
    (dialog,) = page.dialogs
    assert isinstance(dialog, ft.SnackBar)
    assert dialog.behavior == ft.SnackBarBehavior.FLOATING
    assert isinstance(dialog.content, ft.Text)
    return str(dialog.content.value)


def fail(event: object) -> None:
    raise ValueError("bad value")


async def fail_async(event: object) -> None:
    await asyncio.sleep(0)
    raise ValueError("bad value")


# ------------------------------------------------------------------ report_errors


def test_a_sync_handler_that_raises_is_logged_with_its_traceback_and_returns_none(
    page: FakePage, caplog: pytest.LogCaptureFixture
) -> None:
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
    assert await report_errors(fail_async)(object()) is None

    (record,) = [r for r in caplog.records if r.name == errors.__name__]
    assert record.getMessage() == f"Unexpected error in {__name__}.fail_async"
    assert record.exc_info is not None
    assert record.exc_info[0] is ValueError


def test_a_caught_error_tells_the_user_without_details_in_a_packaged_build(
    page: FakePage, embedded: None
) -> None:
    report_errors(fail)(object())
    assert snack_text(page) == "Something went wrong"


async def test_an_async_caught_error_tells_the_user_too(
    page: FakePage, embedded: None
) -> None:
    await report_errors(fail_async)(object())
    assert snack_text(page) == MESSAGE


def test_a_caught_error_shows_the_exception_when_not_embedded(
    page: FakePage, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(errors, "is_embedded", lambda: False)
    report_errors(fail)(object())
    assert snack_text(page) == "Something went wrong: ValueError: bad value"


def test_a_handler_that_succeeds_returns_its_value_and_shows_nothing(
    page: FakePage, caplog: pytest.LogCaptureFixture
) -> None:
    def cleanup() -> None:
        pass

    def effect(a: int, *, b: int) -> object:
        assert (a, b) == (1, 2)
        return cleanup  # a sync effect's cleanup must reach Flet (F2)

    assert report_errors(effect)(1, b=2) is cleanup
    assert page.dialogs == []
    assert caplog.records == []


async def test_an_async_handler_that_succeeds_returns_its_value(page: FakePage) -> None:
    async def handler(a: int) -> int:
        return a + 1

    assert await report_errors(handler)(1) == 2
    assert page.dialogs == []


async def test_cancelled_error_is_re_raised_and_not_reported(
    page: FakePage, caplog: pytest.LogCaptureFixture
) -> None:
    async def cancelled() -> None:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await report_errors(cancelled)()
    assert page.dialogs == []
    assert caplog.records == []


async def test_cancelling_a_wrapped_effect_task_still_cancels_it(
    page: FakePage,
) -> None:
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
    def interrupted() -> None:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        report_errors(interrupted)()
    assert page.dialogs == []


def test_the_wrapper_keeps_what_flet_reads_to_call_a_handler() -> None:
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
    # No page in the context: ft.context.page raises, as in a replaced session (F30).
    assert report_errors(fail)(object()) is None

    messages = [r.getMessage() for r in caplog.records]
    assert messages == [
        f"Unexpected error in {__name__}.fail",
        "Could not show the error message",
    ]


# ------------------------------------------------------------------ setup_logging


@pytest.fixture
def clean_logging(monkeypatch: pytest.MonkeyPatch) -> Iterator[logging.Logger]:
    """Undo what setup_logging() does to the process-wide loggers after the test."""
    monkeypatch.delenv("FLET_LOG_LEVEL", raising=False)
    root = logging.getLogger()
    level, handlers = root.level, list(root.handlers)
    quiet = {name: logging.getLogger(name).level for name in QUIET_LOGGERS}
    yield root
    for handler in root.handlers:
        if handler not in handlers:
            root.removeHandler(handler)
    root.setLevel(level)
    for name, old in quiet.items():
        logging.getLogger(name).setLevel(old)


def ours(root: logging.Logger) -> list[logging.Handler]:
    return [h for h in root.handlers if h.get_name() == HANDLER_NAME]


def test_setup_logging_adds_one_stderr_handler_at_info(
    clean_logging: logging.Logger,
) -> None:
    setup_logging()
    setup_logging()  # a second call changes nothing

    (handler,) = ours(clean_logging)
    assert isinstance(handler, logging.StreamHandler)
    assert handler.stream is sys.stderr
    assert clean_logging.level == logging.INFO


def test_log_lines_carry_the_time_level_logger_and_message(
    clean_logging: logging.Logger,
) -> None:
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
    monkeypatch.setenv("FLET_LOG_LEVEL", value)  # flet run -v / -vv
    setup_logging()
    assert clean_logging.level == level


async def test_request_urls_with_personal_data_stay_out_of_the_log(
    clean_logging: logging.Logger, caplog: pytest.LogCaptureFixture
) -> None:
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
