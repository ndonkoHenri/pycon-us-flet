"""Tests for the ``Layout`` store: the window's width class, bar or rail (#387; D-277).

The store notifies its readers only when the window crosses ``WIDE_DP``, so a resize
within a class re-renders no screen. What a rotation and a resize do on a device is
checked on the emulator and the simulators (the PR).
"""

from types import SimpleNamespace
from typing import Any, cast

import flet as ft
import pytest

from pycon_us.layout import WIDE_DP, Layout, follow_width, is_wide, use_layout
from tests.fakes import FakePage, bound


@pytest.mark.parametrize(
    ("width", "wide"),
    [
        (None, False),  # no width reported yet: a phone
        (0, False),
        (411.4, False),  # a phone in portrait
        (599.9, False),
        (600, True),  # M3's medium class starts here
        (914.3, True),  # a phone in landscape
        (1366, True),  # a tablet
    ],
)
def test_the_rail_shows_from_600_dp(width: float | None, wide: bool) -> None:
    """``is_wide`` is True from ``WIDE_DP`` on, and a missing width is a phone's."""
    assert WIDE_DP == 600
    assert is_wide(width) is wide


def test_the_store_notifies_on_crossing_600_dp_and_not_within_a_class() -> None:
    """Widths within a class notify nothing; each crossing of 600 dp notifies once."""
    layout = Layout()
    changes: list[str | None] = []

    def listen(_sender: object, field: str | None) -> None:
        changes.append(field)

    assert isinstance(layout, ft.Observable)
    layout.subscribe(listen)  # held weakly: a local function, not a lambda

    layout.set_width(411)  # still a phone
    layout.set_width(500)
    assert changes == []
    layout.set_width(914)  # rotated to landscape
    assert (layout.wide, changes) == (True, ["wide"])
    layout.set_width(1024)  # a wider window, the same class
    layout.set_width(600)
    assert changes == ["wide"]
    layout.set_width(599)  # back under
    assert (layout.wide, changes) == (False, ["wide", "wide"])


def test_follow_width_reads_the_page_and_follows_its_resizes() -> None:
    """``follow_width`` takes ``page.width`` at once, then each resize's width."""
    page = FakePage()
    page.width = 1180  # an iPad's width came before the handler was set
    layout = Layout()
    with bound(page):
        follow_width(cast(ft.Page, page), layout)
        assert layout.wide is True
        cast(Any, page.on_resize)(SimpleNamespace(width=744.0))  # Split View
        assert layout.wide is True
        cast(Any, page.on_resize)(SimpleNamespace(width=375.0))  # a third of it
        assert layout.wide is False


def test_use_layout_needs_a_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without a ``LayoutCtx`` provider, ``use_layout`` says so instead of guessing."""
    monkeypatch.setattr(ft, "use_context", lambda ctx: None)
    with pytest.raises(RuntimeError, match="LayoutCtx"):
        use_layout()
