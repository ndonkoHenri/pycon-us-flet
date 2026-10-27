"""Tests for what a session row and a notice row are made of (SCHED-03, SCHED-04; D-184).

A ``SessionRow``'s text as one phrase, its badges, meta and speakers, a place that
wraps whole, no fixed heights, the push on a tap and the elapsed bar's contrast; then
which sessions are notices and how a ``NoticeRow`` reads, opens and lines up with the
gutter. Rows run in a real Flet session (``Rendered``, from ``tests/row_sessions.py``),
as in ``test_session_rows.py``, which tests the memoised path, the Changed badge and the
star. How tall a row is, how it wraps at 200 % and what TalkBack reads are checked on
devices (#81's PR).
"""

from collections.abc import Iterator, Sequence
from typing import cast

import flet as ft
import pytest

from pycon_us.theme import DARK_TOKENS, LIGHT_TOKENS
from pycon_us.ui.row_lines import elapsed_bar
from pycon_us.ui.session_rows import is_notice
from tests import row_sessions
from tests.feeds import processed
from tests.row_sessions import (
    CHARLA,
    COFFEE,
    NOTICE,
    TALK,
    YEAR,
    Rendered,
)
from tests.test_theme import NEUTRAL_RAMP, contrast_ratio

# The harness's fixture, under this module's name, where pytest looks it up.
rendered = row_sessions.rendered


# ------------------------------------------------------------------ SessionRow (SCHED-03)


async def test_a_row_s_text_is_one_node_read_as_one_phrase(
    rendered: Rendered,
) -> None:
    """A row's texts are one merged button node, read as one phrase with its tap."""
    node = rendered.node(f"test.session.{TALK}")
    assert node.label == (
        "Talk. Python for Humans - Designing Python Code Like a User Interface. "
        "10:30 to 11:00 AM, Grand Ballroom A. Justin Lee."
    )
    assert node.exclude_semantics  # the texts are not read again after the phrase
    assert node.button  # it opens the session: "…, button"
    tappable = node.parent
    assert isinstance(tappable, ft.Container) and tappable.on_click is not None
    assert isinstance(tappable.parent, ft.MergeSemantics)  # phrase and tap: one node


async def test_a_row_shows_badges_title_meta_and_speakers(
    rendered: Rendered,
) -> None:
    """A row stacks its badges, its title, its time and place, and its speakers.

    The badges wrap, and the title is TITLE_MEDIUM over three lines at most.
    """
    column = rendered.node(f"test.session.{CHARLA}").content
    assert isinstance(column, ft.Column)
    badges, title, meta, speakers = column.controls
    assert isinstance(badges, ft.Row) and badges.wrap
    assert [
        cast(ft.Text, cast(ft.Container, b).content).value for b in badges.controls
    ] == [
        "Charla",
        "En Español",
    ]
    assert isinstance(title, ft.Text)
    assert (title.theme_style, title.max_lines) == (ft.TextThemeStyle.TITLE_MEDIUM, 3)
    assert isinstance(meta, ft.Row)
    assert [cast(ft.Text, t).value for t in meta.controls] == [
        "10:30–11:00\u00a0AM\u00a0·",
        "Room 104C",
    ]
    assert cast(ft.Text, speakers).value == "Veronica Rodriguez Viveros"


async def test_a_place_that_does_not_fit_moves_down_whole(rendered: Rendered) -> None:
    """At 200 %, "AM · Room" / "104C" broke the place and left the dot dangling."""
    column = rendered.node(f"test.session.{CHARLA}").content
    meta = cast(ft.Column, column).controls[2]
    assert isinstance(meta, ft.Row) and meta.wrap  # time and place wrap as units
    time, place = (cast(ft.Text, t).value or "" for t in meta.controls)
    assert " " not in time  # "AM" and the "·" stay on the time's line
    assert time.endswith("·") and not place.startswith("·")


async def test_no_row_part_has_a_fixed_height(rendered: Rendered) -> None:
    """Rows reflow at 200 % text: only the layout sizes them."""

    def heights(control: ft.Control) -> Iterator[object]:
        yield getattr(control, "height", None)
        for child in _children(control):
            yield from heights(child)

    for session_id in (TALK, CHARLA):
        row = rendered.node(f"test.session.{session_id}")
        assert set(heights(row)) == {None}


async def test_a_tap_on_a_row_pushes_its_session_on_this_view(
    rendered: Rendered, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tap on a row pushes its session under this View's path."""
    pushed: list[str] = []
    monkeypatch.setattr(rendered.session.page, "navigate", pushed.append)
    tappable = rendered.node(f"test.session.{TALK}").parent
    assert isinstance(tappable, ft.Container)
    await rendered.session.dispatch_event(tappable._i, "click", None)
    await rendered.settle()
    assert pushed == [f"/session/{TALK}"]  # drill_href on this View's path ("")


def _over(color: str, alpha: float, background: str) -> str:
    """``color`` at ``alpha`` painted over ``background``, as #RRGGBB."""
    mix = (
        round(
            alpha * int(color[i : i + 2], 16)
            + (1 - alpha) * int(background[i : i + 2], 16)
        )
        for i in (1, 3, 5)
    )
    return "#" + "".join(f"{channel:02X}" for channel in mix)


@pytest.mark.parametrize("dark", [False, True])
def test_the_elapsed_bar_shows_its_fill_and_its_end_on_every_surface(
    dark: bool,
) -> None:
    """WCAG 1.4.11: the fill reads 3:1 on its track, and the stop dot marks the end.

    The track itself is only a hint (about 1.4:1), on the list's ``surface`` and on
    the next-session card's ``surface_container_highest`` alike; M3's stop dot is what
    marks 100 % (#95).
    """
    live = DARK_TOKENS.live if dark else LIGHT_TOKENS.live
    padded = elapsed_bar(60, live)
    assert isinstance(padded, ft.Container)
    bar = padded.content
    assert isinstance(bar, ft.ProgressBar)
    assert bar.year_2023 is False  # the gap and the stop dot
    assert bar.stop_indicator_color == ft.Colors.ON_SURFACE_VARIANT
    role, alpha = str(bar.bgcolor).split(",")
    assert role == ft.Colors.ON_SURFACE
    ramp = NEUTRAL_RAMP[dark]
    for surface in (ramp["surface"], ramp["surfaceContainerHighest"]):
        track = _over(ramp["onSurface"], float(alpha), surface)
        assert contrast_ratio(live, track) >= 3
        assert contrast_ratio(track, surface) >= 1.3  # a visible rail
        assert contrast_ratio(ramp["onSurfaceVariant"], surface) >= 3  # the dot


# ------------------------------------------------------------------ NoticeRow (SCHED-04)


def test_breaks_and_announcements_are_notices_and_talks_are_not() -> None:
    """Informational sessions and breaks are notices; talks and events are not."""
    sessions = processed(2026).sessions
    info = YEAR.conference
    assert is_notice(sessions[NOTICE], info)  # Informational
    assert is_notice(sessions[COFFEE], info)  # Break
    assert not is_notice(sessions[TALK], info)
    assert not is_notice(sessions["227"], info)  # an Event is a session


async def test_a_notice_is_its_own_node_and_has_no_star(rendered: Rendered) -> None:
    """S2: without its own merge, a notice joined the slot's heading in TalkBack."""
    node = rendered.notice(COFFEE)
    assert node.label == "Break. Coffee, 8:00 to 9:00 AM, Expo Hall AB."
    assert node.exclude_semantics
    assert isinstance(cast(ft.Control, node.parent).parent, ft.MergeSemantics)
    stars = [
        c
        for c in rendered.session.index.values()
        if isinstance(c, ft.Semantics)
        and (c.identifier or "").startswith("test.favorite.")
    ]
    assert len(stars) == 3  # the three sessions; neither notice


async def test_a_notice_opens_only_when_it_has_something_to_read(
    rendered: Rendered,
) -> None:
    """A notice with text to read is a tappable button, and one without is neither."""
    with_text = rendered.notice(NOTICE)
    without = rendered.notice(COFFEE)
    assert with_text.button and not without.button
    opens, does_not = with_text.parent, without.parent
    assert isinstance(opens, ft.Container) and opens.on_click is not None
    assert isinstance(does_not, ft.Container) and does_not.on_click is None
    assert not does_not.ink


async def test_a_notice_s_title_starts_on_the_gutter_s_line(
    rendered: Rendered,
) -> None:
    """The gutter's time and a SessionRow's text start 12 dp down; so does a notice's."""
    tile = rendered.notice(COFFEE).parent
    assert isinstance(tile, ft.Container)
    margin, padding = cast(ft.Margin, tile.margin), cast(ft.Padding, tile.padding)
    assert margin.top + padding.top == 12


async def test_a_notice_s_icon_is_one_title_line_tall_at_every_text_size(
    rendered: Rendered,
) -> None:
    """D-373: the track icon scales with the text and tops the row, by the title."""
    row = cast(ft.Row, rendered.notice(COFFEE).content)
    icon, lines = row.controls
    assert isinstance(icon, ft.Icon) and isinstance(lines, ft.Column)
    assert (icon.size, icon.apply_text_scaling) == (20, True)  # a TITLE_SMALL line
    assert row.vertical_alignment == ft.CrossAxisAlignment.START
    title = lines.controls[0]
    assert isinstance(title, ft.Text)
    assert title.theme_style == ft.TextThemeStyle.TITLE_SMALL


def _children(control: ft.Control) -> Sequence[ft.Control]:
    """A control's direct children: its ``content`` and its ``controls``."""
    found: list[ft.Control] = []
    content = getattr(control, "content", None)
    if isinstance(content, ft.Control):
        found.append(content)
    found.extend(
        c for c in getattr(control, "controls", None) or [] if isinstance(c, ft.Control)
    )
    return found
