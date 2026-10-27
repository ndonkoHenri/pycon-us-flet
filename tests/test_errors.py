"""Tests for the last-resort error net (D-71).

``report_errors`` is checked on sync and async callables against a fake page bound as
Flet binds a session's page to a handler's context; that Flet then keeps the session
alive is checked on devices (the PR). The logging setup (D-72) is
``test_errors_logging.py``'s.
"""

import ast
import asyncio
import inspect
import logging
from collections.abc import Iterator
from pathlib import Path

import flet as ft
import pytest
from flet.utils import get_param_count

import pycon_us
from pycon_us.services import errors
from pycon_us.services.errors import (
    MESSAGE,
    report_errors,
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
