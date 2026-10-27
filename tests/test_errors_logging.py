"""Tests for the logging setup (D-72, D-163).

``setup_logging()`` runs on untouched loggers, whatever ran before; the last-resort error
net (D-71) is ``test_errors.py``'s.
"""

import io
import logging
import sys
from collections.abc import Iterator

import httpx
import pytest

from pycon_us.services import errors
from pycon_us.services.errors import (
    HANDLER_NAME,
    QUIET_LOGGERS,
    setup_logging,
)

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
