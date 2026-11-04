"""Tests for the time column of a list's slots (D-158, D-200, D-216).

`TimeGutter` and `TimeAbove` are plain builders, checked as control trees.
`GutterProbe` renders in a real Flet session (`tests/sessions.py`), where its size
events are dispatched as Flutter sends them; that Flutter reports the sizes this way is
checked on devices (the PR).
"""

from typing import cast

import flet as ft
import pytest

from pycon_us.prefs import Prefs, PrefsCtx, use_prefs
from pycon_us.ui.time_gutter import (
    MAX_GUTTER_SHARE,
    GutterProbe,
    TimeAbove,
    TimeGutter,
    TimeSlot,
    slot_layout,
    slot_width,
    time_above,
)
from tests.sessions import find, rendering, settle

PHONE = 402.0
"""An iPhone 17's width in portrait, in dp."""


def test_the_gutter_is_a_level_3_heading_read_once() -> None:
    """The gutter is a level-3 heading labelled with its time, its texts excluded."""
    gutter = TimeGutter("9:25 AM")
    assert isinstance(gutter, ft.Semantics)
    level = (gutter.header, gutter.heading_level)
    assert level == (True, 3)  # a slot under its day; TalkBack needs it (D-211)
    assert (gutter.label, gutter.exclude_semantics) == (
        "9:25 AM",
        True,  # else "9:25 AM, 9:25, AM"
    )


def gutter_columns(gutter: ft.Control) -> list[ft.Column]:
    """Return the columns stacked in `gutter`, checking it has no fixed width."""
    container = cast(ft.Semantics, gutter).content
    assert isinstance(container, ft.Container)
    assert container.width is None  # no fixed width: it grows with the text
    stack = container.content
    assert isinstance(stack, ft.Stack)
    return [cast(ft.Column, c) for c in stack.controls]


def texts(column: ft.Column) -> list[str | None]:
    """Return the values of the texts in `column`, in order."""
    return [cast(ft.Text, t).value for t in column.controls]


def test_an_invisible_widest_time_sets_the_gutter_s_width() -> None:
    """The shown time sits over an invisible "10:00 AM", the widest, two lines each."""
    widest, shown = gutter_columns(TimeGutter("7:30 PM"))
    assert (texts(widest), widest.opacity) == (["10:00", "AM"], 0)
    assert texts(shown) == ["7:30", "PM"]


def test_a_24_hour_gutter_has_one_line() -> None:
    """A 24-hour time is one line, over an invisible "00:00", the widest."""
    widest, shown = gutter_columns(TimeGutter("19:30"))
    assert texts(widest) == ["00:00"]
    assert texts(shown) == ["19:30"]


# ------------------------------------------------------- the layout rule (D-216)


@pytest.mark.parametrize(
    ("gutter", "width", "above"),
    [
        # The gutter's widths as GutterProbe measured them (#224).
        (60.0, 411.4, False),  # Android at 100 %: 15 %, the gutter as always
        (72.6, PHONE, False),  # iOS's largest standard size: 18 %
        (83.0, PHONE, True),  # iOS's first Accessibility size: 21 %
        (90.5, 411.4, True),  # Android's 200 %: 22 %, titles cut after a few words
        (135.3, PHONE, True),  # iOS's largest Larger Text: a third, words broke
        (135.3, 874.0, False),  # the same in landscape: the rows have room beside it
    ],
)
def test_the_time_goes_above_the_rows_when_the_gutter_takes_over_a_fifth(
    gutter: float, width: float, above: bool
) -> None:
    """The time goes above the rows when the gutter takes over 20 % of the width."""
    assert time_above(gutter, width) is above


def test_a_gutter_of_exactly_a_fifth_stays_beside_the_rows() -> None:
    """At exactly a fifth of the width the gutter stays; just over, the time goes up."""
    assert MAX_GUTTER_SHARE == 0.2
    assert time_above(80.0, 400.0) is False
    assert time_above(80.5, 400.0) is True


@pytest.mark.parametrize(
    ("view_width", "slot"),
    [
        (0.0, 0.0),
        (402.0, 402.0),
        (599.0, 599.0),
        (600.0, 520.0),
        (874.0, 794.0),
        (920.0, 840.0),  # the rail leaves exactly a list's width
        (1366.0, 840.0),  # a tablet: the list is capped (D-305)
    ],
)
def test_from_600_dp_a_slot_is_the_rail_narrower_than_its_view(
    view_width: float, slot: float
) -> None:
    """From 600 dp the rail's 80 dp beside a root's body leave a slot less width."""
    assert slot_width(view_width) == slot


def test_beside_the_rail_a_gutter_that_fit_the_view_goes_above() -> None:
    """A gutter that fits a 700 dp View but not the slot beside the rail goes above.

    137 dp is under a fifth of 700 dp and over a fifth of the 620 dp left (D-277).
    """
    assert time_above(137.0, 700.0) is False
    assert time_above(137.0, slot_width(700.0)) is True


def test_on_a_tablet_the_gutter_is_measured_against_the_capped_list() -> None:
    """A gutter that fits a 1,366 dp View but not the 840 dp list goes above.

    170 dp is under a fifth of the 1,286 dp beside the rail and over a fifth of the
    840 dp a capped list leaves its slots (D-305).
    """
    assert time_above(170.0, 1366.0 - 80.0) is False
    assert time_above(170.0, slot_width(1366.0)) is True


def test_an_unmeasured_width_keeps_the_gutter() -> None:
    """Before the body's first size event, nothing is known: no layout switch."""
    assert time_above(150.0, 0.0) is False


def test_the_time_above_is_one_heading_read_once_on_one_line() -> None:
    """`TimeAbove` is a level-3 heading read once, one line in the gutter's type."""
    above = TimeAbove("9:25 AM")
    assert isinstance(above, ft.Semantics)
    assert (above.header, above.heading_level) == (True, 3)  # as the gutter (D-211)
    assert (above.label, above.exclude_semantics) == ("9:25 AM", True)
    container = above.content
    assert isinstance(container, ft.Container)
    text = container.content
    assert isinstance(text, ft.Text)
    assert text.value == "9:25\N{NO-BREAK SPACE}AM"  # "AM" keeps to its time
    assert text.theme_style == ft.TextThemeStyle.TITLE_SMALL  # the gutter's type
    # From the screen's edge, as the gutter's time; 20 dp above it against the rows'
    # own 12 dp below, so it sits with the rows it heads rather than midway.
    assert container.padding == ft.Padding.only(left=16, top=20, right=16)


def test_beside_the_gutter_the_rows_take_the_rest_of_the_width() -> None:
    """Beside the gutter, the rows are an expanding column in a top-aligned `Row`."""
    rows = [ft.Text("a"), ft.Text("b")]
    slot = slot_layout("9:25 AM", rows, above=False)
    assert isinstance(slot, ft.Row)
    gutter, column = slot.controls
    assert isinstance(gutter, ft.Semantics) and isinstance(gutter.content, ft.Container)
    assert isinstance(gutter.content.content, ft.Stack)  # the gutter, not the line
    assert isinstance(column, ft.Column)
    assert (column.controls, column.expand) == (rows, True)
    assert slot.vertical_alignment == ft.CrossAxisAlignment.START


def test_above_the_rows_they_take_the_slot_s_whole_width() -> None:
    """With the time above, the slot is a `Column`: the heading, then the rows."""
    rows = [ft.Text("a"), ft.Text("b")]
    slot = slot_layout("9:25 AM", rows, above=True)
    assert isinstance(slot, ft.Column)
    heading, column = slot.controls
    assert isinstance(heading, ft.Semantics) and heading.label == "9:25 AM"
    assert isinstance(column, ft.Column)
    assert column.controls == rows  # under the time: nothing beside them


@pytest.mark.parametrize("above", [False, True])
def test_a_slot_s_divider_sits_above_either_layout(above: bool) -> None:
    """`TimeSlot` puts a 1 dp divider above either layout only when asked to."""
    rows = [ft.Text("a")]
    slot = TimeSlot("9:25 AM", rows, divider=True, above=above)
    assert isinstance(slot, ft.Column)
    divider, inner = slot.controls
    assert isinstance(divider, ft.Divider) and divider.height == 1
    assert isinstance(inner, ft.Column if above else ft.Row)
    alone = TimeSlot("9:25 AM", rows, divider=False, above=above)
    assert isinstance(alone, ft.Column if above else ft.Row)


# ------------------------------------------------------------- the probe (D-216)


class Probed:
    """A session showing `GutterProbe` under the Prefs provider, and its readers."""

    def __init__(self) -> None:
        """Start with default `Prefs` and no reader render counted."""
        self.prefs = Prefs()
        self.renders = 0

    def root(self) -> ft.Control:
        """Return the session's root: a reader of `time_above` and the probe."""

        @ft.component
        def Reader() -> ft.Control:
            # A list that reads the fact, as the Schedule does.
            self.renders += 1
            return ft.Text("above" if use_prefs().time_above else "beside")

        @ft.component
        def Root() -> ft.Control:
            return PrefsCtx(self.prefs, lambda: ft.Column([Reader(), GutterProbe()]))

        return Root()


async def test_the_probe_measures_the_widest_gutter_against_the_body() -> None:
    """The probe sets `time_above` from both widths; readers re-render on a flip only.

    It measures an invisible "10:00 AM" in the gutter's padding, and a zero-height,
    unpositioned box for the body's width (F51).
    """
    probed = Probed()
    async with rendering(probed.root) as session:
        (box,) = find(session, ft.Container, lambda c: c.height == 0)
        # Not positioned: with on_size_change, a Positioned breaks its Stack (F51).
        assert (box.left, box.top, box.right, box.bottom) == (None,) * 4
        (gutter,) = find(
            session,
            ft.Container,
            lambda c: c is not box and c.on_size_change is not None,
        )
        assert gutter.padding == ft.Padding.only(left=16, top=12, right=8)
        column = cast(ft.Column, gutter.content)
        assert (texts(column), column.opacity) == (["10:00", "AM"], 0)

        async def size(control: ft.Container, width: float) -> None:
            data = {"w": width, "h": 0.0}
            await session.dispatch_event(control._i, "size_change", data)
            await settle()

        await size(gutter, 135.3)  # the largest Larger Text, the body still unknown
        assert (probed.prefs.time_above, probed.prefs.time_measured) == (False, False)
        await size(box, PHONE)  # a third of the width
        assert (probed.prefs.time_above, probed.prefs.time_measured) == (True, True)
        first = probed.renders
        await size(box, 403.0)  # a new width, the same answer: no reader re-renders
        assert probed.renders == first
        await size(box, 874.0)  # turned to landscape
        assert probed.prefs.time_above is False
        assert probed.renders == first + 1


async def test_a_new_screen_s_probe_leaves_the_answer_until_it_has_both_widths() -> (
    None
):
    """Each screen mounts a probe; one width alone must not flip the lists back."""
    probed = Probed()
    probed.prefs.time_above = True  # what the boot view's probe measured
    async with rendering(probed.root) as session:
        (box,) = find(session, ft.Container, lambda c: c.height == 0)
        (gutter,) = find(
            session,
            ft.Container,
            lambda c: c is not box and c.on_size_change is not None,
        )
        first = probed.renders
        data = {"w": 135.3, "h": 0.0}
        await session.dispatch_event(gutter._i, "size_change", data)
        await settle()
        assert probed.prefs.time_above is True
        assert probed.renders == first  # no list re-rendered with the gutter
