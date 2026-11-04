"""Tests for `ui/semantics.py`'s `announce()`, every announcement's one way out.

It caps the wait for an answer iOS may never give (D-420, F276), and its logs hold the
error's class, never the words (D-72). The sites' guards are in their own tests.
"""

import asyncio
import logging

import flet as ft
import pytest

from pycon_us.ui import semantics as ui_semantics
from pycon_us.ui.semantics import announce
from tests.fakes import MemorySemantics

WORDS = "Incident recorded for Grace Hopper"
"""Words a Code of Conduct tool could say, which must never reach a log."""


@pytest.fixture
def logged(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    """The log capture, with the helper's logger at DEBUG so that nothing escapes it."""
    caplog.set_level(logging.DEBUG, logger=ui_semantics.__name__)
    return caplog


async def test_an_announcement_never_answered_returns_within_the_cap(
    monkeypatch: pytest.MonkeyPatch, logged: pytest.LogCaptureFixture
) -> None:
    """F276: the words are sent, no answer comes, and the wait ends with a debug line."""
    monkeypatch.setattr(ui_semantics, "ANNOUNCE_WAIT_S", 0.01)
    semantics = MemorySemantics()
    semantics.answers = False
    # The outer wait only fails this test, were the cap to go, instead of hanging it.
    await asyncio.wait_for(announce(semantics, WORDS), 5)
    assert semantics.announced == [WORDS]
    assert [record.levelno for record in logged.records] == [logging.DEBUG]
    assert WORDS not in logged.text


async def test_a_timeout_from_flet_logs_at_debug_without_the_words(
    logged: pytest.LogCaptureFixture,
) -> None:
    """D-72: Flet's own timeout can repeat the arguments; only the debug line is logged."""
    semantics = MemorySemantics()
    semantics.announce_error = TimeoutError(WORDS)
    await announce(semantics, WORDS)
    assert [record.levelno for record in logged.records] == [logging.DEBUG]
    assert WORDS not in logged.text


async def test_a_failed_announcement_logs_only_the_error_s_class(
    logged: pytest.LogCaptureFixture,
) -> None:
    """D-72: a platform error repeating the words is a warning naming its class alone."""
    semantics = MemorySemantics()
    semantics.announce_error = RuntimeError(WORDS)
    await announce(semantics, WORDS)
    assert [record.getMessage() for record in logged.records] == [
        "Could not announce: RuntimeError"
    ]
    assert logged.records[0].levelno == logging.WARNING
    assert logged.records[0].exc_info is None  # a traceback would repeat the message
    assert WORDS not in logged.text


async def test_an_error_outside_the_service_errors_is_raised(
    logged: pytest.LogCaptureFixture,
) -> None:
    """Only `SERVICE_ERRORS` are the platform's: a bug still reaches `report_errors`."""
    semantics = MemorySemantics()
    semantics.announce_error = KeyError("bug")
    with pytest.raises(KeyError):
        await announce(semantics, WORDS)
    assert logged.records == []


@pytest.mark.parametrize(
    ("kwargs", "level"),
    [
        ({}, ft.Assertiveness.POLITE),
        ({"assertiveness": ft.Assertiveness.ASSERTIVE}, ft.Assertiveness.ASSERTIVE),
    ],
    ids=["polite-by-default", "assertive-when-asked"],
)
async def test_an_announcement_goes_at_the_level_asked(
    kwargs: dict[str, ft.Assertiveness], level: ft.Assertiveness
) -> None:
    """Polite unless the caller chooses, as `scan_feedback` does for what needs acting on."""
    semantics = MemorySemantics()
    await announce(semantics, WORDS, **kwargs)
    assert semantics.levels == [level]
