"""Tests for the star's feedback (ux.md §4.4, §4.5): its click and its last SnackBar.

The selection click the star and search's chips share (ux.md §4.5, D-193), and the
star's last SnackBar, which an edit that says nothing closes (D-251, #334): those tests
star rows in a real Flet session (``tests/row_sessions.py``). The badges' tests are in
``tests/test_badges.py`` (D-267).
"""

import asyncio
import gc
import logging
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any, cast
from weakref import ref

import flet as ft
import pytest

from pycon_us.ui import favorite
from pycon_us.ui.favorite import REMOVED, selection_click
from tests import row_sessions
from tests.fakes import MemoryHaptics, MemoryPrefs
from tests.row_sessions import Rendered, rendering
from tests.sessions import text_of


async def test_selection_click_gives_the_click() -> None:
    """The selection click plays one ``selection_click`` haptic effect."""
    haptics = MemoryHaptics()
    await selection_click(haptics)
    assert haptics.effects == ["selection_click"]


@pytest.mark.parametrize("error", [TimeoutError(), RuntimeError("no engine")])
async def test_a_failed_click_is_logged_not_raised(
    error: Exception, caplog: pytest.LogCaptureFixture
) -> None:
    """A haptic click that times out or fails logs a warning instead of raising."""
    haptics = MemoryHaptics()
    haptics.error = error
    with caplog.at_level(logging.WARNING, logger="pycon_us.ui.favorite"):
        await selection_click(haptics)  # a missed click is no error message
    assert "Haptic feedback failed" in caplog.text


# ------------------------------------------------------------------ the last SnackBar


@pytest.fixture
async def rendered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Rendered]:
    """A list of starred rows in a real Flet session, a screen reader on (D-184)."""
    async with rendering(tmp_path, monkeypatch) as shown:
        shown.prefs.screen_reader = True  # the Undo SnackBar stays until used
        yield shown


def updates(monkeypatch: pytest.MonkeyPatch) -> list[ft.SnackBar]:
    """Record each SnackBar sent to the client again: a closed one must be sent."""
    sent: list[ft.SnackBar] = []

    def update(snack: ft.SnackBar) -> None:
        sent.append(snack)

    monkeypatch.setattr(ft.SnackBar, "update", update)
    return sent


async def removed(rendered: Rendered, session_id: str) -> ft.SnackBar:
    """Save the session, then remove it: return the "Removed" SnackBar, showing."""
    await rendered.tap_star(session_id)
    await rendered.tap_star(session_id)
    snack = rendered.snack_bars[-1]
    assert text_of(snack.content) == REMOVED
    assert snack.open and snack.persist
    return snack


async def test_saving_a_session_again_closes_its_removed_snack_bar(
    rendered: Rendered, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#334: a screen reader must not go on saying "Removed" about a saved session."""
    snack = await removed(rendered, row_sessions.TALK)
    sent = updates(monkeypatch)
    await rendered.tap_star(row_sessions.TALK)
    assert rendered.favorites.ids == {row_sessions.TALK}
    # Flet removes the SnackBar whose open goes false (snack_bar.dart).
    assert not snack.open and sent == [snack]
    assert rendered.snack_bars == [snack]  # and the add shows none of its own


async def test_undo_closes_the_removed_snack_bar(rendered: Rendered) -> None:
    """Undo saves the session again and closes its SnackBar, showing no new one."""
    snack = await removed(rendered, row_sessions.TALK)
    await cast(Callable[[], Any], cast(ft.SnackBarAction, snack.action).on_click)()
    await rendered.settle()
    assert rendered.favorites.ids == {row_sessions.TALK}
    assert not snack.open
    assert rendered.snack_bars == [snack]


async def test_saving_another_session_closes_it_too(rendered: Rendered) -> None:
    """Any edit that says nothing: the bar would not say which session it removed."""
    snack = await removed(rendered, row_sessions.TALK)
    await rendered.tap_star(row_sessions.TUTORIAL)
    assert not snack.open


async def test_a_removal_snack_bar_stays_until_the_next_edit(
    rendered: Rendered,
) -> None:
    """D-184 is unchanged: nothing closes it but an edit, Undo or Flet itself."""
    snack = await removed(rendered, row_sessions.TALK)
    await rendered.settle()
    assert snack.open
    # A second removal shows its own; Flet's show replaces the first on the device.
    second = await removed(rendered, row_sessions.TUTORIAL)
    assert second is not snack and second.open


async def test_an_edit_leaves_a_snack_bar_that_is_not_the_stars_alone(
    rendered: Rendered,
) -> None:
    """Never the top dialog (ux.md §4.5): only the star's own SnackBar closes."""
    snack = await removed(rendered, row_sessions.TALK)
    other = ft.SnackBar(ft.Text("Something went wrong"))
    rendered.session.page.show_dialog(other)
    await rendered.tap_star(row_sessions.TALK)
    assert not snack.open and other.open
    await rendered.tap_star(row_sessions.TUTORIAL)  # with no star SnackBar left
    assert other.open


async def test_a_snack_bar_that_has_gone_is_not_closed_again(
    rendered: Rendered, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A star SnackBar that Flet already closed is not sent again by the next edit."""
    snack = await removed(rendered, row_sessions.TALK)
    snack.open = False  # as Flet reports a SnackBar that timed out or was swiped
    sent = updates(monkeypatch)
    await rendered.tap_star(row_sessions.TALK)
    assert rendered.favorites.ids == {row_sessions.TALK}
    assert sent == []


def hold_first(
    monkeypatch: pytest.MonkeyPatch, service: type[MemoryHaptics | MemoryPrefs]
) -> asyncio.Event:
    """Hold the service's first call until the returned event is set; later ones run."""
    gate = asyncio.Event()
    calls = 0
    original = service._invoke_method

    async def held(self: Any, *args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == 1:
            await gate.wait()
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(service, "_invoke_method", held)
    return gate


async def test_an_older_add_leaves_a_newer_removals_snack_bar(
    rendered: Rendered, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fast double tap: the add, still in its haptic click, reports after the removal."""
    gate = hold_first(monkeypatch, MemoryHaptics)
    star = rendered.star(row_sessions.TALK)
    # Flet runs each event as its own task (flet_socket_server.py), so taps overlap.
    add = asyncio.create_task(rendered.session.dispatch_event(star._i, "click", None))
    await rendered.settle()
    assert rendered.favorites.ids == {row_sessions.TALK}
    await rendered.tap_star(row_sessions.TALK)
    snack = rendered.snack_bars[-1]
    assert text_of(snack.content) == REMOVED and snack.open
    gate.set()
    await add
    await rendered.settle()
    assert rendered.favorites.ids == frozenset()
    assert snack.open
    assert favorite._SHOWN[rendered.session.page]() is snack  # the next edit closes it


async def test_an_older_undo_leaves_a_newer_removals_snack_bar(
    rendered: Rendered, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An Undo still awaiting its write reports after a newer removal."""
    first = await removed(rendered, row_sessions.TALK)
    gate = hold_first(monkeypatch, MemoryPrefs)
    on_undo = cast(Callable[[], Any], cast(ft.SnackBarAction, first.action).on_click)
    undo = asyncio.create_task(on_undo())
    await rendered.settle()
    assert rendered.favorites.ids == {row_sessions.TALK}
    await rendered.tap_star(row_sessions.TALK)
    second = rendered.snack_bars[-1]
    assert second is not first and text_of(second.content) == REMOVED
    gate.set()
    await undo
    await rendered.settle()
    assert second.open


async def test_an_older_removal_shows_nothing_over_a_newer_add(
    rendered: Rendered, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The removal's write answers first, then the add that saved the session again."""
    await rendered.tap_star(row_sessions.TALK)  # saved, with no SnackBar
    write = hold_first(monkeypatch, MemoryPrefs)
    click = hold_first(monkeypatch, MemoryHaptics)
    star = rendered.star(row_sessions.TALK)
    removal = asyncio.create_task(
        rendered.session.dispatch_event(star._i, "click", None)
    )
    await rendered.settle()
    add = asyncio.create_task(rendered.session.dispatch_event(star._i, "click", None))
    await rendered.settle()
    assert rendered.favorites.ids == {row_sessions.TALK}
    write.set()
    await removal
    click.set()
    await add
    await rendered.settle()
    assert rendered.favorites.ids == {row_sessions.TALK}
    assert not any(snack.open for snack in rendered.snack_bars)


async def test_a_page_with_an_undo_snack_bar_is_released_when_its_session_ends(
    tmp_path: Path,
) -> None:
    """The last SnackBar is held weakly: its Undo holds the page, which must go."""
    patches = pytest.MonkeyPatch()  # its own: the test's would hold the page
    try:
        async with rendering(tmp_path, patches) as shown:
            shown.prefs.screen_reader = True
            await removed(shown, row_sessions.TALK)
            page = ref(shown.session.page)
            assert page() in favorite._SHOWN
            del shown
    finally:
        patches.undo()
    gc.collect()
    assert page() is None  # and with it, its entry in the registry
