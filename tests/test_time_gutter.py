"""Tests for the time gutter: ``TimeGutter`` (D-158, D-200)."""

from typing import cast

import flet as ft

from pycon_us.ui.time_gutter import TimeGutter


def test_the_gutter_is_a_level_3_heading_read_once() -> None:
    gutter = TimeGutter("9:25 AM")
    assert isinstance(gutter, ft.Semantics)
    level = (gutter.header, gutter.heading_level)
    assert level == (True, 3)  # a slot under its day; TalkBack needs it (D-211)
    assert (gutter.label, gutter.exclude_semantics) == (
        "9:25 AM",
        True,  # else "9:25 AM, 9:25, AM"
    )


def gutter_columns(gutter: ft.Control) -> list[ft.Column]:
    container = cast(ft.Semantics, gutter).content
    assert isinstance(container, ft.Container)
    assert container.width is None  # no fixed width: it grows with the text
    stack = container.content
    assert isinstance(stack, ft.Stack)
    return [cast(ft.Column, c) for c in stack.controls]


def texts(column: ft.Column) -> list[str | None]:
    return [cast(ft.Text, t).value for t in column.controls]


def test_an_invisible_widest_time_sets_the_gutter_s_width() -> None:
    widest, shown = gutter_columns(TimeGutter("7:30 PM"))
    assert (texts(widest), widest.opacity) == (["10:00", "AM"], 0)
    assert texts(shown) == ["7:30", "PM"]


def test_a_24_hour_gutter_has_one_line() -> None:
    widest, shown = gutter_columns(TimeGutter("19:30"))
    assert texts(widest) == ["00:00"]
    assert texts(shown) == ["19:30"]
