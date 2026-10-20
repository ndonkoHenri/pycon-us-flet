"""Tests for the ``Layout`` store: the window's width class, bar or rail (#387; D-277).

The store notifies its readers only when the window crosses ``WIDE_DP``, so a resize
within a class re-renders no screen. What a rotation and a resize do on a device is
checked on the emulator and the simulators (the PR).
"""

from types import SimpleNamespace
from typing import Any, cast

import flet as ft
import pytest

from pycon_us.layout import (
    WIDE_DP,
    Layout,
    follow_width,
    is_wide,
    layout_for,
    side_insets,
    use_layout,
)
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


def test_the_store_notifies_on_a_crossing_and_on_room_over_the_reading_width() -> None:
    """Under 720 dp only a crossing of 600 dp notifies; over it, each new room does.

    D-305: a phone in portrait never re-renders on a resize; a tablet's margins follow.
    """
    layout = Layout()
    changes: list[str | None] = []

    def listen(_sender: object, field: str | None) -> None:
        """Record the field each notification names."""
        changes.append(field)

    assert isinstance(layout, ft.Observable)
    layout.subscribe(listen)  # held weakly: a local function, not a lambda

    layout.set_width(411)  # still a phone
    layout.set_width(500)
    assert changes == []
    layout.set_width(700)  # the rail, and still no cap
    assert (layout.wide, layout.room, changes) == (True, 0.0, ["wide"])
    layout.set_width(914)  # wider than a reading screen: the room counts
    assert (layout.room, changes) == (914.0, ["wide", "room"])
    layout.set_width(914)  # the same width notifies nothing
    assert changes == ["wide", "room"]
    layout.set_width(599)  # back under both
    assert (layout.wide, layout.room) == (False, 0.0)
    assert changes == ["wide", "room", "wide", "room"]


@pytest.mark.parametrize(
    ("width", "insets", "room"),
    [
        (None, 0.0, 0.0),
        (402.0, 0.0, 0.0),  # a phone in portrait: no cap
        (720.0, 0.0, 0.0),  # exactly a reading width: nothing to cap
        (834.0, 0.0, 834.0),  # an iPad in portrait
        (874.0, 124.0, 750.0),  # an iPhone in landscape, beside its island
        (800.0, 124.0, 0.0),  # insets that leave under 720 dp
    ],
)
def test_the_room_is_the_width_less_the_insets_once_over_720_dp(
    width: float | None, insets: float, room: float
) -> None:
    """``room`` is what the SafeArea leaves the body, and 0 where no cap applies."""
    layout = Layout()
    layout.set_width(width, insets)
    assert layout.room == room


def test_side_insets_add_the_left_and_right_padding() -> None:
    """Both sides' safe-area insets count; the top and bottom do not; no media is 0."""
    media = cast(
        ft.PageMediaData,
        SimpleNamespace(padding=ft.Padding.only(left=62, top=24, right=62, bottom=20)),
    )
    assert side_insets(media) == 124.0
    assert side_insets(None) == 0.0


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


def test_follow_width_takes_the_insets_from_each_media_change() -> None:
    """A media change re-reads the page's insets: a rotation sends it apart (D-305)."""
    page = FakePage()
    page.width = 874.0
    layout = Layout()
    with bound(page):
        follow_width(cast(ft.Page, page), layout)
        assert layout.room == 874.0  # no media yet
        page.media = cast(
            ft.PageMediaData,
            SimpleNamespace(padding=ft.Padding.only(left=62, right=62)),
        )
        cast(Any, page.on_media_change)(page.media)
        assert layout.room == 750.0


def test_layout_for_seeds_the_class_and_the_room_from_the_page() -> None:
    """The first screen has the right navigation and margins (D-277, D-305)."""
    page = FakePage()
    page.width = 1366.0
    layout = layout_for(cast(ft.Page, page))
    assert (layout.wide, layout.room) == (True, 1366.0)


def test_use_layout_needs_a_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without a ``LayoutCtx`` provider, ``use_layout`` says so instead of guessing."""
    monkeypatch.setattr(ft, "use_context", lambda ctx: None)
    with pytest.raises(RuntimeError, match="LayoutCtx"):
        use_layout()
