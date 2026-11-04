"""Tests for the SnackBar a screen reader keeps until it is off (D-356, #343).

The star's "Removed from My schedule · Undo" in a real Flet session
(`tests/row_sessions.py`), with the watch's 4 s and its reads shortened; and the
screen reader's "Added to My schedule" (D-355), which is not kept, so not watched.
"""

import asyncio
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any, cast

import flet as ft
import pytest

from pycon_us.ui import snack_bars
from pycon_us.ui.favorite import ADDED, REMOVED
from tests import row_sessions
from tests.fakes import MemorySemantics
from tests.row_sessions import Rendered, rendering
from tests.sessions import text_of

TICK = 0.01
"""The watch's first wait and its reads, in seconds, instead of 4 s and 2 s."""


@pytest.fixture
async def rendered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Rendered]:
    """Starred rows in a real Flet session, TalkBack on, the watch's waits shortened."""
    monkeypatch.setattr(snack_bars, "SNACK_BAR_MS", TICK * 1000)
    monkeypatch.setattr(snack_bars, "READ_EVERY_S", TICK)
    async with rendering(tmp_path, monkeypatch) as shown:
        shown.session.page.on_close = shown.services.close  # as App does (D-147)
        shown.prefs.screen_reader = True
        semantics(shown).features["accessible_navigation"] = True
        yield shown


def semantics(shown: Rendered) -> MemorySemantics:
    """The session's fake `SemanticsService`, whose flags the test sets."""
    return cast(MemorySemantics, shown.services.semantics)


async def removed(shown: Rendered) -> ft.SnackBar:
    """Save a session, then remove it: return the kept "Removed" SnackBar."""
    await shown.tap_star(row_sessions.TALK)
    await shown.tap_star(row_sessions.TALK)
    snack = shown.snack_bars[-1]
    assert text_of(snack.content) == REMOVED
    assert snack.open and snack.persist
    return snack


async def wait_ticks(count: int = 5) -> None:
    """A window for something that must not happen: a few of the watch's reads."""
    await asyncio.sleep(TICK * count)


async def until(holds: Callable[[], object], *, timeout: float = 30.0) -> None:
    """Poll until `holds()` is true, or fail after `timeout` seconds (#237).

    A poll rather than a fixed wait, so a loaded host only makes it slower; the
    deadline is generous because a passing test never reaches it.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not holds():
        assert loop.time() < deadline, "the watch did not get there in time"
        await asyncio.sleep(TICK)


async def test_it_stays_while_the_screen_reader_is_on(rendered: Rendered) -> None:
    """D-184 holds while TalkBack is on: the flags are read again, the bar stays."""
    snack = await removed(rendered)
    await until(lambda: semantics(rendered).reads >= 2)  # read again, not once
    assert snack.open


async def test_it_closes_once_no_screen_reader_is_on(
    rendered: Rendered, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#343: TalkBack turned off in front closes the bar, which has had its 4 s."""
    snack = await removed(rendered)
    sent: list[ft.SnackBar] = []

    def update(bar: ft.SnackBar) -> None:
        """Record the SnackBar sent to the client again."""
        sent.append(bar)

    monkeypatch.setattr(ft.SnackBar, "update", update)
    semantics(rendered).features["accessible_navigation"] = False
    await until(lambda: not snack.open)
    # Flet removes the SnackBar whose open goes false (snack_bar.dart).
    assert not snack.open and sent == [snack]
    assert not rendered.prefs.screen_reader  # the store follows the read too


async def test_it_waits_out_the_snack_bars_own_time_first(
    rendered: Rendered, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A screen reader off at once still leaves the bar its 4 s, as anyone gets."""
    monkeypatch.setattr(snack_bars, "SNACK_BAR_MS", 60_000)
    semantics(rendered).features["accessible_navigation"] = False
    snack = await removed(rendered)
    reads = semantics(rendered).reads
    await wait_ticks()
    assert snack.open and semantics(rendered).reads == reads


async def test_the_watch_ends_when_the_bar_has_gone(rendered: Rendered) -> None:
    """Undo's "Added" replaces the bar (D-355); once it has gone, nothing reads."""
    snack = await removed(rendered)
    await cast(Callable[[], Any], cast(ft.SnackBarAction, snack.action).on_click)()
    await rendered.settle()
    added = rendered.snack_bars[-1]
    assert text_of(added.content) == ADDED and added is not snack
    # Flet reports the bar the new one replaced as gone (snack_bar.dart).
    snack.open = False
    await until(lambda: not snack_bars._WATCHES)  # its task has returned
    reads = semantics(rendered).reads
    await wait_ticks()
    assert semantics(rendered).reads == reads


async def test_a_screen_readers_added_bar_is_not_watched(rendered: Rendered) -> None:
    """D-355's "Added to My schedule" has no Undo: it is not kept, so not watched."""
    await rendered.tap_star(row_sessions.TALK)
    added = rendered.snack_bars[-1]
    assert text_of(added.content) == ADDED
    assert added.open and added.action is None and not added.persist
    assert not snack_bars._WATCHES
    reads = semantics(rendered).reads
    await wait_ticks()
    assert semantics(rendered).reads == reads


async def test_a_removal_after_an_add_is_watched(
    rendered: Rendered, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The kept "Removed" that follows an "Added" closes once TalkBack is off."""
    await rendered.tap_star(row_sessions.TALK)
    assert text_of(rendered.snack_bars[-1].content) == ADDED
    await rendered.tap_star(row_sessions.TALK)
    snack = rendered.snack_bars[-1]
    assert text_of(snack.content) == REMOVED and snack.persist
    monkeypatch.setattr(ft.SnackBar, "update", lambda bar: None)
    semantics(rendered).features["accessible_navigation"] = False
    await until(lambda: not snack.open)
    await until(lambda: not snack_bars._WATCHES)


async def test_the_watch_ends_when_the_session_closes(rendered: Rendered) -> None:
    """A replaced session's bar is not watched on: its loop returns (D-147)."""
    snack = await removed(rendered)
    rendered.services.close()
    await until(lambda: not snack_bars._WATCHES)
    assert snack.open


async def test_it_waits_while_the_app_is_in_the_background(
    rendered: Rendered,
) -> None:
    """No read in the background: the resume reads the flags itself (D-34)."""
    await removed(rendered)
    rendered.services.foreground.clear()
    await wait_ticks(2)
    reads = semantics(rendered).reads
    await wait_ticks()
    assert semantics(rendered).reads == reads
