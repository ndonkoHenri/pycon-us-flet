"""Tests for ``jump_to_key()``: one keyed scroll, confirmed by the list's scroll end (D-155).

A stand-in list answers ``scroll_to`` as the device would in each case: a scroll that
ends (the item was built), nothing (not built yet, or already in place), Flutter's
``TimeoutException`` for a list that never registered its methods, or Flet's error for a
list that has left the page. Whether the jump lands on a device is #86's device check.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, cast

import flet as ft
import pytest

from pycon_us.ui import scrolling
from pycon_us.ui.scrolling import JUMP_TRIES, anchored, jump_to_key

KEY = "slot-2026-05-15T14:00:00-07:00"


LEFT = RuntimeError("ListView(79) Control must be added to the page first")
"""What Flet raises for a call on a list no longer under the page (``BaseControl.page``)."""


@dataclass
class List:
    """A list whose ``scroll_to`` ends a scroll from the ``ends``-th call on.

    It raises ``error`` from the ``fails``-th call on instead.
    """

    ended: asyncio.Event
    ends: int | None = 1
    error: Exception | None = None
    fails: int = 1
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def scroll_to(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)
        if self.error is not None and len(self.calls) >= self.fails:
            raise self.error
        if self.ends is not None and len(self.calls) >= self.ends:
            # Set before the jump starts its wait, so a scroll that ends never races
            # ``LANDING_S`` on a loaded host (#270): it lands whatever the wait's length.
            self.ended.set()


@pytest.fixture(autouse=True)
def quick(monkeypatch: pytest.MonkeyPatch) -> None:
    """Short waits: only an ask that gets no scroll end waits them out."""
    monkeypatch.setattr(scrolling, "LANDING_S", 0.1)


def ref_to(target: object) -> ft.Ref[ft.ListView]:
    """A ref whose ``current`` is the stand-in (``ft.Ref`` holds a weak reference)."""
    return cast(ft.Ref[ft.ListView], SimpleNamespace(current=target))


async def test_a_jump_that_ends_a_scroll_lands_on_the_first_try() -> None:
    ended = asyncio.Event()
    target = List(ended)
    assert await jump_to_key(ref_to(target), KEY, duration=0, ended=ended) == "landed"
    (call,) = target.calls
    assert call["scroll_key"].value == KEY and call["duration"] == 0


async def test_an_item_not_built_yet_is_asked_for_again() -> None:
    """F7: the first ask is a silent no-op until Flutter has built the item."""
    ended = asyncio.Event()
    target = List(ended, ends=2)
    assert await jump_to_key(ref_to(target), KEY, duration=0, ended=ended) == "landed"
    assert len(target.calls) == 2


async def test_a_list_that_never_moves_is_still_after_a_few_tries(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An item already in place never scrolls: the caller decides what that means."""
    ended = asyncio.Event()
    target = List(ended, ends=None)
    with caplog.at_level(logging.INFO):
        jump = await jump_to_key(ref_to(target), KEY, duration=0, ended=ended)
    assert jump == "still"
    assert len(target.calls) == JUMP_TRIES
    assert "did not move" in caplog.text


async def test_flutter_s_timeout_is_logged_and_ends_the_jump(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A list that never registered its methods: Flet raises Flutter's error."""
    ended = asyncio.Event()
    error = RuntimeError("TimeoutException after 0:00:10.000000: Timeout waiting")
    target = List(ended, error=error)
    jump = await jump_to_key(ref_to(target), KEY, duration=400, ended=ended)
    assert jump == "failed"
    assert len(target.calls) == 1
    assert "not shown in time" in caplog.text


async def test_a_list_that_left_the_page_ends_the_jump_quietly(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The user switched tabs (D-142) while a jump from a handler waited to land."""
    ended = asyncio.Event()
    target = List(ended, ends=None, error=LEFT, fails=2)
    with caplog.at_level(logging.INFO):
        jump = await jump_to_key(ref_to(target), KEY, duration=0, ended=ended)
    assert jump == "failed"
    assert len(target.calls) == 2  # and no third ask
    assert "the list left the page" in caplog.text
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


async def test_any_other_error_is_not_swallowed() -> None:
    ended = asyncio.Event()
    target = List(ended, error=RuntimeError("Calling scroll_to of inexistent control"))
    with pytest.raises(RuntimeError, match="inexistent"):
        await jump_to_key(ref_to(target), KEY, duration=0, ended=ended)


async def test_a_list_that_was_never_built_is_not_scrolled() -> None:
    jump = await jump_to_key(ref_to(None), KEY, duration=0, ended=asyncio.Event())
    assert jump == "failed"


def test_an_anchor_carries_the_key_above_its_content_and_holds_nothing() -> None:
    """D-242: Flet mounts a control with a ScrollKey again at each build (F62), so the
    key goes on an empty 0 dp box above the item, never on a box around its rows."""
    row = ft.Text("A row")
    item = anchored(KEY, row)
    assert isinstance(item, ft.Column) and item.spacing == 0
    anchor, content = item.controls
    assert isinstance(anchor, ft.Container)
    assert anchor.key == ft.ScrollKey(KEY)
    assert anchor.content is None and anchor.height == 0
    assert content is row
    # The item keeps the list's full width, as a box around it did.
    assert item.horizontal_alignment == ft.CrossAxisAlignment.STRETCH
