"""Tests for the session rows: ``SessionRow`` and ``NoticeRow`` (D-184).

Rows run in a real Flet session (``Rendered``, from ``tests/row_sessions.py``): a list
owner like the screens' renders memoised rows under the store providers, a star tap is
a dispatched click, and Flet's own scheduler re-renders what changed, so a test sees
what a device would get. How tall a row is, how it wraps at 200 % and what TalkBack
reads are checked on devices (#81's PR); here, the semantics a screen reader is given.

The session is ``tests/sessions.py``'s ``showing()``, which reaches into Flet internals
as Flet's own component tests do (SnackBars from ``page._dialogs``, clicks through
``Session.dispatch_event(control._i, ...)``). A Flet pin bump (D-81) that renames one
of them breaks that module, not the rows: look there first.
"""

import asyncio
from collections.abc import AsyncIterator, Callable, Iterator, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import flet as ft
import pytest

from pycon_us import clock
from pycon_us.change_log import RECENT_FOR
from pycon_us.core.change_batches import Batch
from pycon_us.core.diff import Change, ChangeKind
from pycon_us.theme import DARK_TOKENS, LIGHT_TOKENS
from pycon_us.ui import session_rows as rows
from pycon_us.ui.badges import CHANGED
from pycon_us.ui.favorite import (
    ADD_LABEL,
    FAVORITE_LABEL,
    NOT_SAVED,
    REMOVE_LABEL,
    REMOVED,
    UNDO,
)
from pycon_us.ui.row_lines import elapsed_bar
from pycon_us.ui.session_rows import is_notice
from tests.feeds import processed
from tests.row_sessions import (
    CHARLA,
    COFFEE,
    LIST,
    NOTICE,
    OWNER_RENDERS,
    TALK,
    TUTORIAL,
    YEAR,
    Rendered,
    rendering,
)
from tests.test_theme import NEUTRAL_RAMP, contrast_ratio


@pytest.fixture
async def rendered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Rendered]:
    """``Owner(LIST)`` in a real Flet session (``tests/row_sessions.py``)."""
    async with rendering(tmp_path, monkeypatch) as shown:
        yield shown


# ------------------------------------------------------------------ the memoised path


async def test_each_row_renders_once_when_the_list_first_shows(
    rendered: Rendered,
) -> None:
    """The list's first show renders each of its rows exactly once."""
    assert sorted(rendered.renders) == sorted(LIST)


async def test_a_star_tap_re_renders_exactly_one_row(rendered: Rendered) -> None:
    """D-153: the owner re-renders, but every other row skips its body (F34)."""
    rendered.renders.clear()
    await rendered.tap_star(CHARLA)
    assert rendered.favorites.ids == {CHARLA}
    assert rendered.renders == [CHARLA]
    assert rendered.filled(CHARLA)
    assert not rendered.filled(TALK)

    rendered.renders.clear()
    await rendered.tap_star(CHARLA)  # and back
    assert rendered.renders == [CHARLA]
    assert rendered.favorites.ids == frozenset()


async def test_the_handler_is_the_same_object_on_every_render(
    rendered: Rendered,
) -> None:
    """Every row gets the same star handler object across renders and taps.

    With ``use_callback(..., [])`` the handler never changes, so memoised rows stay
    skipped.
    """
    handlers: set[int] = set()
    original = rows._SessionRow

    def spy(*args: Any, **kwargs: Any) -> ft.Control:
        handlers.add(id(args[2]))
        return original(*args, **kwargs)

    rows._SessionRow = spy  # pyright: ignore[reportAttributeAccessIssue]
    try:
        await rendered.tap_star(TALK)
        await rendered.tap_star(TUTORIAL)
    finally:
        rows._SessionRow = original  # pyright: ignore[reportAttributeAccessIssue]
    assert len(handlers) == 1  # use_callback(..., []): memoised rows stay skipped


# ------------------------------------------------------------------ Changed (D-315)

DETECTED = datetime(2026, 5, 15, 17, 0, tzinfo=UTC)
"""When the tests' batch was recorded."""


@pytest.fixture
def frozen_clock() -> Iterator[None]:
    """Freeze ``clock.now()`` an hour after ``DETECTED``; real time again after."""
    clock.set_test_now(DETECTED + timedelta(hours=1))
    yield
    clock.set_test_now(None)


def badge_labels(rendered: Rendered, session_id: str) -> list[str]:
    """The labels of the badges a session row shows, in order."""
    column = rendered.node(f"test.session.{session_id}").content
    badges = cast(ft.Column, column).controls[0]
    assert isinstance(badges, ft.Row)
    return [
        cast(ft.Text, cast(ft.Container, b).content).value or ""
        for b in badges.controls
    ]


async def record(rendered: Rendered, *changes: tuple[str, ChangeKind]) -> None:
    """Record one batch of ``(session id, kind)`` changes, as a refresh would."""
    batch = Batch(
        DETECTED, tuple(Change(key, kind, None, None) for key, kind in changes)
    )
    rendered.change_log.batches = (batch,)  # the store notifies its subscribers
    await rendered.settle()


async def test_a_changed_row_shows_the_badge_and_says_what_changed(
    rendered: Rendered, frozen_clock: None
) -> None:
    """A moved and retimed talk shows Changed and says "Time and room changed"."""
    rendered.renders.clear()
    await record(rendered, (TALK, ChangeKind.ROOM), (TALK, ChangeKind.TIME))
    assert badge_labels(rendered, TALK) == ["Talk", CHANGED]
    phrase = rendered.node(f"test.session.{TALK}").label or ""
    assert phrase.startswith("Talk, Time and room changed. Python for Humans")
    assert rendered.renders == [TALK]  # the other rows skip their bodies (D-153)


async def test_additions_and_removals_badge_no_row(
    rendered: Rendered, frozen_clock: None
) -> None:
    """D-255: only a time, room or title change is badged."""
    await record(rendered, (TALK, ChangeKind.ADDED), (CHARLA, ChangeKind.REMOVED))
    assert badge_labels(rendered, TALK) == ["Talk"]
    assert badge_labels(rendered, CHARLA) == ["Charla", "En Español"]


async def test_the_badge_goes_a_minute_past_its_24_hours(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, frozen_clock: None
) -> None:
    """The tick removes the badge once its batch is 24 h old, re-rendering one row.

    The tick is the strip's 60 s loop, made 10 ms here before the list mounts.
    """
    monkeypatch.setattr(rows, "TICK_SECONDS", 0.01)
    async with rendering(tmp_path, monkeypatch) as rendered:
        await record(rendered, (TALK, ChangeKind.TITLE))
        assert CHANGED in badge_labels(rendered, TALK)
        clock.set_test_now(DETECTED + RECENT_FOR - timedelta(seconds=1))
        await asyncio.sleep(0.05)  # ticks a second before the end: still shown
        assert CHANGED in badge_labels(rendered, TALK)
        rendered.renders.clear()

        clock.set_test_now(DETECTED + RECENT_FOR + timedelta(minutes=1))
        for _ in range(300):
            await asyncio.sleep(0.01)
            if CHANGED not in badge_labels(rendered, TALK):
                break
        assert badge_labels(rendered, TALK) == ["Talk"]
        assert rendered.renders == [TALK]


async def test_a_tick_after_a_batch_that_ends_no_mark_renders_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, frozen_clock: None
) -> None:
    """D-315: a tick compares with the marks the batch's render showed, not older ones.

    So after a recorded batch, ticks whose time ends no mark leave the owner alone
    (D-194's leaf rule).
    """
    monkeypatch.setattr(rows, "TICK_SECONDS", 0.01)
    async with rendering(tmp_path, monkeypatch) as rendered:
        await record(rendered, (TALK, ChangeKind.ROOM))
        OWNER_RENDERS.clear()
        await asyncio.sleep(0.1)  # about ten ticks, the clock frozen
        assert OWNER_RENDERS == []


def notice_badges(rendered: Rendered, session_id: str) -> list[str]:
    """The labels of the badges a notice row shows over its title, in order."""
    row = cast(ft.Row, rendered.notice(session_id).content)
    column = cast(ft.Column, row.controls[1])
    first = column.controls[0]
    if not isinstance(first, ft.Row):
        return []
    return [
        cast(ft.Text, cast(ft.Container, b).content).value or "" for b in first.controls
    ]


async def test_a_changed_notice_shows_the_badge_until_its_24_hours_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, frozen_clock: None
) -> None:
    """A moved informational session is badged and says "Room changed", then not.

    Registration Desk Opens is diffed like any session (D-255): its notice row shows
    Changed a second before the 24 h end, and neither badge nor words a minute after.
    """
    monkeypatch.setattr(rows, "TICK_SECONDS", 0.01)
    async with rendering(tmp_path, monkeypatch) as rendered:
        rendered.renders.clear()
        await record(rendered, (NOTICE, ChangeKind.ROOM))
        assert rendered.renders == [NOTICE]
        assert notice_badges(rendered, NOTICE) == [CHANGED]
        phrase = rendered.notice(NOTICE).label or ""
        assert phrase.startswith("Notice, Room changed. Registration Desk Opens")

        clock.set_test_now(DETECTED + RECENT_FOR - timedelta(seconds=1))
        await asyncio.sleep(0.05)
        assert notice_badges(rendered, NOTICE) == [CHANGED]

        clock.set_test_now(DETECTED + RECENT_FOR + timedelta(minutes=1))
        for _ in range(300):
            await asyncio.sleep(0.01)
            if not notice_badges(rendered, NOTICE):
                break
        assert notice_badges(rendered, NOTICE) == []
        phrase = rendered.notice(NOTICE).label or ""
        assert phrase.startswith("Notice. Registration Desk Opens")


# ------------------------------------------------------------------ the star (D-30)


async def test_adding_fills_the_star_with_a_click_and_no_snack_bar(
    rendered: Rendered,
) -> None:
    """Adding a session saves it, gives a selection click and shows no SnackBar."""
    await rendered.tap_star(TALK)
    assert rendered.prefs_service.values["pycon.2026.favorites"] == [TALK]
    assert rendered.haptics.effects == ["selection_click"]
    assert rendered.snack_bars == []


async def test_removing_says_so_and_undo_saves_the_session_again(
    rendered: Rendered,
) -> None:
    """Removing shows a floating SnackBar whose Undo saves the session again.

    Without a screen reader it goes after 4 s, and Undo shows no SnackBar of its own.
    """
    await rendered.tap_star(TALK)
    await rendered.tap_star(TALK)
    (snack,) = rendered.snack_bars
    assert cast(ft.Text, snack.content).value == REMOVED
    assert snack.behavior == ft.SnackBarBehavior.FLOATING
    assert snack.persist is False  # no screen reader: it goes after 4 s
    action = cast(ft.SnackBarAction, snack.action)
    assert action.label == UNDO

    await cast(Callable[[], Any], action.on_click)()
    await rendered.settle()
    assert rendered.favorites.ids == {TALK}
    assert rendered.prefs_service.values["pycon.2026.favorites"] == [TALK]
    assert rendered.filled(TALK)
    assert len(rendered.snack_bars) == 1  # Undo itself says nothing more


async def test_with_a_screen_reader_the_undo_snack_bar_waits_to_be_used(
    rendered: Rendered,
) -> None:
    """D-184: a screen-reader user cannot reach Undo within 4 s."""
    rendered.prefs.screen_reader = True
    await rendered.tap_star(TALK)
    await rendered.tap_star(TALK)
    added, snack = rendered.snack_bars  # the add says "Added" to it first (D-355)
    assert snack.persist is True and not added.persist


async def test_an_add_that_was_not_saved_says_so_without_undo(
    rendered: Rendered,
) -> None:
    """An add that fails to save fills the star, then says so without an Undo."""
    rendered.prefs_service.fail_writes = True
    await rendered.tap_star(TALK)
    assert rendered.filled(TALK)  # shown first, as the store does (D-172)
    (snack,) = rendered.snack_bars
    assert cast(ft.Text, snack.content).value == NOT_SAVED
    assert snack.action is None


async def test_a_removal_that_was_not_saved_says_so_once_and_keeps_undo(
    rendered: Rendered,
) -> None:
    """A removal that fails to save shows one SnackBar saying so, with Undo."""
    await rendered.tap_star(TALK)
    rendered.prefs_service.fail_writes = True
    await rendered.tap_star(TALK)
    (snack,) = rendered.snack_bars  # one SnackBar for one tap (ux.md §4.4)
    assert cast(ft.Text, snack.content).value == NOT_SAVED
    assert cast(ft.SnackBarAction, snack.action).label == UNDO


async def test_a_failed_click_does_not_stop_the_star(rendered: Rendered) -> None:
    """A haptic click that fails still saves the session and shows no SnackBar."""
    rendered.haptics.error = TimeoutError()
    await rendered.tap_star(TALK)
    assert rendered.favorites.ids == {TALK}
    assert rendered.snack_bars == []  # neither the click nor "Something went wrong"


async def test_the_star_is_one_named_toggle_for_screen_readers(
    rendered: Rendered,
) -> None:
    """S2: the IconButton alone was a nameless Button without a state in TalkBack."""
    node = rendered.node(f"test.favorite.{TALK}")
    assert (node.label, node.button, node.toggled) == (FAVORITE_LABEL, True, False)
    assert isinstance(node.parent, ft.MergeSemantics)
    button = rendered.star(TALK)
    assert (button.icon, button.icon_color) == (ft.Icons.STAR_BORDER, None)

    await rendered.tap_star(TALK)
    node = rendered.node(f"test.favorite.{TALK}")
    # The same name; only the state changes: "Save to My schedule, switch, on".
    assert (node.label, node.toggled) == (FAVORITE_LABEL, True)
    button = rendered.star(TALK)
    assert (button.icon, button.icon_color) == (ft.Icons.STAR, LIGHT_TOKENS.favorite)


async def test_the_star_s_state_is_said_once(rendered: Rendered) -> None:
    """VoiceOver read the tooltip after the label, and a "selected" after the "on"."""
    await rendered.tap_star(TALK)
    button = rendered.star(TALK)
    assert button.selected is None  # IconButton.selected adds Semantics(selected:)
    tooltip = button.tooltip
    assert isinstance(tooltip, ft.Tooltip) and tooltip.exclude_from_semantics


async def test_the_star_s_tooltip_says_what_a_tap_does(rendered: Rendered) -> None:
    """D-27, D-30: "Add to My schedule", then "Remove from My schedule"."""
    assert cast(ft.Tooltip, rendered.star(TALK).tooltip).message == ADD_LABEL
    await rendered.tap_star(TALK)
    assert cast(ft.Tooltip, rendered.star(TALK).tooltip).message == REMOVE_LABEL


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
