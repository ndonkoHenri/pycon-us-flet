"""Tests for the content widths: 720 dp to read, 840 dp for lists, centred (#440; D-305).

What the margins look like on a tablet, in both orientations, is checked on the
emulator and the simulators (the PR).
"""

import flet as ft
import pytest

from pycon_us.layout import Layout
from pycon_us.screens.schedule_days import now_button
from pycon_us.ui import widths
from pycon_us.ui.navigation import RAIL_WIDTH
from pycon_us.ui.widths import (
    FULL,
    LIST,
    READING,
    capped,
    side_margin,
    sides,
    use_margin,
)


async def _jump() -> None:
    """The Now button's stand-in jump: nothing to do."""


def content_width(window: float, cap: float, *, root: bool) -> float:
    """The width a screen's content gets in a window ``window`` dp wide.

    Args:
        window: The window's width, with no insets.
        cap: The screen's width class.
        root: Whether it is a tab root, beside the rail from 600 dp.
    """
    layout = Layout()
    layout.set_width(window)
    rail = RAIL_WIDTH if root and layout.wide else 0
    return window - rail - 2 * side_margin(layout.room, cap, rail=rail)


@pytest.mark.parametrize(
    ("window", "reading", "listed", "full"),
    [
        (400.0, 400.0, 400.0, 400.0),  # a phone: unchanged
        (700.0, 700.0, 700.0, 700.0),  # under both caps: unchanged
        (1000.0, 720.0, 840.0, 1000.0),
        (1300.0, 720.0, 840.0, 1300.0),
    ],
)
def test_a_pushed_screen_s_content_is_capped_by_its_class(
    window: float, reading: float, listed: float, full: float
) -> None:
    """Reading screens get at most 720 dp, lists 840 dp, the floor viewer all of it."""
    assert content_width(window, READING, root=False) == reading
    assert content_width(window, LIST, root=False) == listed
    assert content_width(window, FULL, root=False) == full


@pytest.mark.parametrize(
    ("window", "listed"),
    [
        (400.0, 400.0),  # the bar: unchanged
        (700.0, 620.0),  # the rail's 80 dp off, no cap
        (1000.0, 840.0),
        (1300.0, 840.0),
    ],
)
def test_a_root_s_list_is_capped_beside_the_rail(window: float, listed: float) -> None:
    """On a tab root the rail comes off first; the list is then centred at 840 dp."""
    assert content_width(window, LIST, root=True) == listed


def test_the_margins_centre_the_content_in_the_body() -> None:
    """Each side gets half of what the cap leaves: 1,300 dp less 840 is 230 a side."""
    assert side_margin(1300.0, LIST) == 230.0
    assert side_margin(1300.0, LIST, rail=80.0) == 190.0
    assert side_margin(0.0, READING) == 0.0  # no room recorded: a phone


@pytest.mark.parametrize(
    ("path", "wide", "margin"),
    [
        ("/schedule", True, 190.0),  # a root: beside the rail
        ("/schedule/session/42", True, 230.0),  # pushed: no rail
        ("/schedule", False, 0.0),  # no room under 600 dp
    ],
)
def test_use_margin_takes_the_rail_off_on_tab_roots_only(
    monkeypatch: pytest.MonkeyPatch, path: str, wide: bool, margin: float
) -> None:
    """``use_margin`` reads the layout and the View: only a root has the rail beside it."""
    layout = Layout()
    layout.set_width(1300.0 if wide else 500.0)
    monkeypatch.setattr(widths, "use_layout", lambda: layout)
    monkeypatch.setattr(ft, "use_view_path", lambda: path)
    assert use_margin(LIST) == margin


def test_a_list_s_padding_puts_the_margin_on_both_sides() -> None:
    """``sides`` keeps the list's own top and bottom, so it scrolls from the margins."""
    assert sides(230.0, top=8, bottom=24) == ft.Padding.only(
        left=230, top=8, right=230, bottom=24
    )
    assert sides(0.0) == ft.Padding.only(left=0, top=0, right=0, bottom=0)


def test_fixed_chrome_sits_between_the_margins_in_one_container() -> None:
    """``capped`` is always one container, so a rotation keeps its content in place."""
    strip = ft.Text("Offline")
    box = capped(strip, 190.0)
    assert isinstance(box, ft.Container)
    assert box.content is strip
    assert box.padding == ft.Padding.symmetric(horizontal=190.0)


def test_the_now_button_keeps_to_the_list_s_right_edge() -> None:
    """The Schedule's FAB moves in by the margin, so it sits on the capped list."""
    button = now_button(on_today=True, on_click=_jump, margin=190.0)
    assert button.margin == ft.Margin.only(right=190.0)
