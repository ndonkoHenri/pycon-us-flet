"""Tests for the My schedule tab (#94; NEW-01, SCHED-07, SCHED-08; ux.md §5.6).

The screen runs in a real Flet session (``tests/sessions.py``'s ``showing()``), as the
rows do in ``test_session_rows.py``: the store providers above it, a star tap as a
dispatched click, Flet's own scheduler re-rendering what changed. ``AppScaffold`` is
the harness's stand-in and the status strip a placeholder (both have their own
tests), and the minute tick is a hook the test moves by hand, with ``clock.now()``
fixed. The fold itself is a pure function, tested in ``test_agenda.py``.
"""

from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast

import flet as ft
import pytest

from pycon_us import clock
from pycon_us.change_log import ChangeLog
from pycon_us.config import load_year
from pycon_us.core.change_batches import Batch
from pycon_us.core.diff import Change, ChangeKind, Listing
from pycon_us.core.row_views import spoken_phrase
from pycon_us.favorites import Favorites
from pycon_us.prefs import Prefs
from pycon_us.screens import my_schedule as screen
from pycon_us.screens import my_schedule_extras as extras
from pycon_us.screens.my_schedule import MySchedule
from pycon_us.state import Conference
from pycon_us.ui import fold, states
from pycon_us.ui import session_rows as rows
from pycon_us.ui.buttons import LABEL_PADDING
from pycon_us.ui.favorite import REMOVED, UNDO
from tests import sessions
from tests.fakes import MemoryPrefs
from tests.feeds import processed
from tests.folds import Fold, as_fold, fold_named

YEAR = load_year(2026)
ZONE = YEAR.conference.zone
FAVORITES = "pycon.2026.favorites"

# Wednesday, May 13: two tutorials at 9:00 that overlap, one after lunch.
MCP, DECORATORS, RAG = "2", "19", "188"
# Thursday, May 14: a 9:00-12:30 tutorial and two workshops inside it.
NOTEBOOKS, CHEESE_SHOP, INFERENCE = "106", "111", "22"
# Friday, May 15: the welcome at 9:00 and the keynote at 9:45, back to back but one.
WELCOME, KEYNOTE = "151", "153"
# Saturday, May 16: a talk alone in its slot.
TALK = "142"
# Sunday, May 17: an open space, which the Schedule hides by default (D-20).
OPEN_SPACE = "9028"

SAVED = (
    MCP,
    DECORATORS,
    RAG,
    NOTEBOOKS,
    CHEESE_SHOP,
    INFERENCE,
    WELCOME,
    KEYNOTE,
    TALK,
    OPEN_SPACE,
)

BEFORE = datetime(2026, 5, 1, 12, 0, tzinfo=ZONE)
"""Before the conference: nothing has ended."""

THURSDAY = datetime(2026, 5, 14, 10, 45, tzinfo=ZONE)
"""Wednesday has ended; on Thursday the 9:30 workshop has, the tutorial has not."""

LAST_EVENING = datetime(2026, 5, 17, 20, 0, tzinfo=ZONE)
"""Sunday evening, the conference's last day: everything saved has ended."""

AFTER = datetime(2026, 6, 1, 12, 0, tzinfo=ZONE)
"""After the conference: everything has ended."""

NBSP = "\N{NO-BREAK SPACE}"


def name(session_id: str) -> str:
    """The name of session ``session_id`` in the 2026 feed."""
    return processed(2026).sessions[session_id].name


@dataclass
class Shown(sessions.Shown):
    """The harness's ``Shown`` (``tests/sessions.py``) on My schedule."""

    strips: list[dict[str, Any]] = field(default_factory=list)
    """The arguments of each ``StatusStrip`` the screen placed."""
    slots: list[str] = field(default_factory=list)
    """The slots day sections built, by gutter label: a day body builds each of its."""
    minutes: list[Callable[[int], None]] = field(default_factory=list)
    """The minute hook's setter on each render: ``tick()`` calls the last one."""

    @property
    def prefs_service(self) -> MemoryPrefs:
        """The ``MemoryPrefs`` behind the session's storage."""
        return cast(MemoryPrefs, self.storage.prefs)

    @property
    def controls(self) -> list[ft.Control]:
        """Every mounted control, in the session's index."""
        return self.find(ft.Control)

    def tick(self) -> None:
        """A minute passing: the minute hook's state changes, so the screen re-renders."""
        self.minutes[-1](len(self.minutes))

    def phrase(self, session_id: str) -> str:
        """The spoken phrase of the row of ``session_id``: its node's label."""
        return str(self.node(f"my_schedule.session.{session_id}").label)

    def shown(self) -> list[str]:
        """The rows on screen, in reading order, outside the folded tiles."""
        root = self.root()
        return [
            str(c.identifier).removeprefix("my_schedule.session.")
            for c in _walk(root)
            if isinstance(c, ft.Semantics)
            and str(c.identifier).startswith("my_schedule.session.")
        ]

    def headers(self) -> list[str]:
        """The day headers outside the folds, in reading order (not the gutters)."""
        return [
            str(c.content.content.value)
            for c in _walk(self.root())
            if isinstance(c, ft.Semantics)
            and c.header
            and isinstance(c.content, ft.Container)
            and isinstance(c.content.content, ft.Text)
        ]

    def fold(self, identifier: str) -> Fold:
        """The ``FoldTile`` whose header is ``my_schedule.<identifier>``."""
        return fold_named(self.controls, f"my_schedule.{identifier}")

    def folded(self, identifier: str) -> list[str]:
        """The rows inside a fold, shown or not, in reading order."""
        return [
            str(c.identifier).removeprefix("my_schedule.session.")
            for c in _walk(self.fold(identifier).controls)
            if isinstance(c, ft.Semantics)
            and str(c.identifier).startswith("my_schedule.session.")
        ]

    def root(self) -> ft.ListView:
        """The screen's one ``ListView``."""
        (found,) = self.find(ft.ListView)
        return found

    async def tap_star(self, session_id: str) -> None:
        """Click the star of the row of ``session_id``."""
        star = self.node(f"my_schedule.favorite.{session_id}").content
        assert isinstance(star, ft.IconButton)
        await self.click(star)

    async def toggle_fold(self, identifier: str, expanded: bool) -> None:
        """Open or close the fold ``identifier`` with a tap on its header."""
        found = self.fold(identifier)
        assert found.expanded is not expanded
        await self.click(found.header)


_PARTS = ("content", "leading", "title", "subtitle", "trailing")


def _walk(node: Any, *, folds: bool = False) -> Iterator[ft.Control]:
    """Yield the controls under ``node`` in reading order, through components' bodies.

    A component's rendered body is its ``_b`` (Flet's ``Component``, at the D-81
    pin). A fold's header is yielded, what it holds only if ``folds`` is set.
    """
    if isinstance(node, list):
        for item in node:
            yield from _walk(item, folds=folds)
        return
    if isinstance(node, ft.Component):
        yield from _walk(node._b, folds=folds)
        return
    if not isinstance(node, ft.Control):
        return
    yield node
    if not folds and (found := as_fold(node)):
        yield from _walk(found.node)
        return
    for part in _PARTS:
        yield from _walk(getattr(node, part, None), folds=folds)
    yield from _walk(list(getattr(node, "controls", None) or []), folds=folds)


@dataclass
class Setup:
    """What a test sets before the screen renders."""

    saved: tuple[str, ...] = SAVED
    now: datetime = THURSDAY
    loaded: bool = True
    data: bool = True
    problem: Any = None
    reduce_motion: bool = False
    batches: tuple[Batch, ...] = ()


@pytest.fixture
def setup() -> Setup:
    """The default ``Setup``, which a test's own fixtures change."""
    return Setup()


@pytest.fixture
async def shown(
    setup: Setup, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Shown]:
    """Show My schedule in a Flet session as ``setup`` says.

    The day sections' slots, the status strips and the minute hook's setters are
    recorded on the ``Shown``, and the skeleton is a placeholder.
    """
    if setup.data:
        conference = Conference(data=processed(2026), source="bundled", version=1)
    else:
        conference = Conference(problem=setup.problem)
    clock.set_test_now(setup.now)

    def use_minute() -> int:
        minute, set_minute = ft.use_state(0)
        sessions.current(Shown).minutes.append(set_minute)
        return minute

    time_slot = screen.TimeSlot

    def counted_slot(label: str, *args: Any, **kwargs: Any) -> ft.Control:
        sessions.current(Shown).slots.append(label)
        return time_slot(label, *args, **kwargs)

    def strip(**kwargs: Any) -> ft.Control:
        sessions.current(Shown).strips.append(kwargs)
        return ft.Text("strip")

    monkeypatch.setattr(screen, "TimeSlot", counted_slot)
    monkeypatch.setattr(screen, "use_minute", use_minute)
    monkeypatch.setattr(screen, "StatusStrip", strip)
    monkeypatch.setattr(states, "SkeletonList", lambda: ft.Text("skeleton"))

    try:
        async with sessions.showing(
            MySchedule,
            screen,
            year=YEAR,
            conference=conference,
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            view_path="",  # no Router: what ft.use_view_path() says outside one
            prefs=Prefs(loaded=True, reduce_motion=setup.reduce_motion),
            favorites=None if setup.loaded else Favorites(),  # not read yet
            saved=setup.saved,
            kind=Shown,
            change_log=ChangeLog(batches=setup.batches),
        ) as shown:
            yield shown
    finally:
        clock.set_test_now(None)


# ------------------------------------------------------------------ the agenda


@pytest.fixture
def before(setup: Setup) -> None:
    """Set the time before the conference, when nothing has ended."""
    setup.now = BEFORE


@pytest.mark.usefixtures("before")
async def test_saved_sessions_show_by_day_and_slot_in_schedule_order(
    shown: Shown,
) -> None:
    """Every saved session shows under its day header, in the Schedule's order."""
    assert shown.headers() == [
        "Wednesday, May 13",
        "Thursday, May 14",
        "Friday, May 15",
        "Saturday, May 16",
        "Sunday, May 17",
    ]
    assert shown.shown() == [
        MCP,  # 9:00, Room 101A
        DECORATORS,  # 9:00, Room 101B
        RAG,
        NOTEBOOKS,  # 9:00
        CHEESE_SHOP,  # 9:30
        INFERENCE,  # 11:30
        WELCOME,
        KEYNOTE,
        TALK,
        OPEN_SPACE,  # hidden on the Schedule by default, shown here (D-20)
    ]


@pytest.mark.usefixtures("before")
async def test_each_start_is_one_slot_with_its_gutter(shown: Shown) -> None:
    """Saved sessions with one start share one slot and its time gutter."""
    gutters = [
        str(c.label)
        for c in _walk(shown.root())
        if isinstance(c, ft.Semantics) and c.header and c.label
    ]
    # Wednesday's two 9:00 tutorials share one gutter.
    assert gutters[:3] == ["9:00 AM", "1:30 PM", "9:00 AM"]


@pytest.mark.usefixtures("before")
async def test_every_saved_row_has_a_filled_star(shown: Shown) -> None:
    """A saved row's star is toggled on."""
    star = shown.node(f"my_schedule.favorite.{TALK}")
    assert star.toggled is True


async def test_the_strip_shows_the_data_s_state_but_never_refreshes_by_itself(
    shown: Shown,
) -> None:
    """D-40: only Now and Schedule refresh every 15 min while they show."""
    assert shown.strips and all(kwargs == {} for kwargs in shown.strips)
    assert shown.root().controls[0] == ft.Text("strip")


# ------------------------------------------------------------------ overlaps


@pytest.mark.usefixtures("before")
async def test_both_rows_of_a_clash_say_so_in_words_and_with_an_icon(
    shown: Shown,
) -> None:
    """P1 exit criterion 1; D-33: an icon and text, never colour alone."""
    assert shown.phrase(MCP).endswith(f"Overlaps with “{name(DECORATORS)}”.")
    assert shown.phrase(DECORATORS).endswith(f"Overlaps with “{name(MCP)}”.")
    line = f"Overlaps with “{name(DECORATORS)}”"
    (text,) = [c for c in shown.controls if isinstance(c, ft.Text) and c.value == line]
    row = cast(ft.Control, text.parent).parent
    assert isinstance(row, ft.Row)
    icon = cast(ft.Container, row.controls[0]).content
    assert isinstance(icon, ft.Icon) and icon.icon == ft.Icons.WARNING_AMBER


@pytest.mark.usefixtures("before")
async def test_a_session_inside_a_long_one_names_its_clash(shown: Shown) -> None:
    """A tutorial names both workshops inside it, and a workshop the tutorial."""
    assert shown.phrase(NOTEBOOKS).endswith(
        f"Overlaps with “{name(CHEESE_SHOP)}” and “{name(INFERENCE)}”."
    )
    assert shown.phrase(CHEESE_SHOP).endswith(f"Overlaps with “{name(NOTEBOOKS)}”.")


@pytest.mark.usefixtures("before")
async def test_a_row_without_a_clash_says_nothing_of_one(shown: Shown) -> None:
    """Rows without a clash say nothing of one: only five rows have the line."""
    for session_id in (RAG, WELCOME, KEYNOTE, TALK):
        assert "Overlaps" not in shown.phrase(session_id)
    lines = [text for text in shown.texts() if text.startswith("Overlaps")]
    assert len(lines) == 5  # Wednesday's pair and Thursday's three, nothing more


@pytest.mark.usefixtures("before")
async def test_more_clashes_are_counted_on_a_line_the_cut_never_hides(
    shown: Shown,
) -> None:
    """D-188's "Now:" line: the name may be cut at three lines, the count never is."""
    line = f"Overlaps with “{name(CHEESE_SHOP)}”"
    (text,) = [c for c in shown.controls if isinstance(c, ft.Text) and c.value == line]
    assert text.max_lines == 3
    lines = cast(ft.Column, text.parent).controls
    assert [cast(ft.Text, c).value for c in lines] == [line, f"and 1{NBSP}more"]
    assert cast(ft.Text, lines[1]).max_lines is None
    # The phrase names every clash in full.
    assert shown.phrase(NOTEBOOKS).endswith(
        f"Overlaps with “{name(CHEESE_SHOP)}” and “{name(INFERENCE)}”."
    )


def test_the_phrase_names_three_clashes_in_a_list() -> None:
    """The spoken phrase lists three clashes as “A”, “B” and “C”."""
    view = rows.session_views(processed(2026), (TALK,), ZONE, use_24h=False)[0]
    assert spoken_phrase([], view, overlaps=("A", "B", "C")).endswith(
        "Overlaps with “A”, “B” and “C”."
    )


async def test_a_clash_that_has_ended_is_not_shown(shown: Shown) -> None:
    """An ended clash is not named, and folded rows carry no clash line.

    Thursday 10:45: the 9:30 workshop is over, so the tutorial names only 11:30's.
    Neither an ended clash nor a folded row can change a plan any more.
    """
    assert shown.phrase(NOTEBOOKS).endswith(f"Overlaps with “{name(INFERENCE)}”.")
    assert f"and 1{NBSP}more" not in shown.texts()
    for folded in (MCP, DECORATORS, CHEESE_SHOP):
        assert "Overlaps" not in shown.phrase(folded)


# ------------------------------------------------------------------ what has ended


async def test_earlier_days_and_today_s_ended_sessions_fold_away(
    shown: Shown,
) -> None:
    """Thursday 10:45: Wednesday is over, and so is Thursday's 9:30 workshop."""
    earlier_days = shown.fold("earlier_days")
    title = cast(ft.Text, earlier_days.title)
    assert title.value == f"Earlier days (3{NBSP}sessions)"
    assert earlier_days.expanded is False  # folded until tapped
    assert earlier_days.said == "Collapsed"
    assert earlier_days.animation.duration == fold.EXPAND_MS
    assert shown.folded("earlier_days") == [MCP, DECORATORS, RAG]
    assert f"Earlier today (1{NBSP}session)" in shown.texts()
    assert shown.folded("earlier_today") == [CHEESE_SHOP]
    # Today's header comes first, then what is still on or to come.
    assert shown.headers()[:2] == ["Thursday, May 14", "Friday, May 15"]
    assert shown.shown() == [NOTEBOOKS, INFERENCE, WELCOME, KEYNOTE, TALK, OPEN_SPACE]


@pytest.fixture
def reduced(setup: Setup) -> None:
    """Turn reduced motion on before the screen renders."""
    setup.reduce_motion = True


@pytest.mark.usefixtures("reduced")
async def test_the_folds_open_without_animation_under_reduced_motion(
    shown: Shown,
) -> None:
    """D-173: the tiles' animation is ``prefs.motion_ms()`` long, 0 here."""
    for identifier in ("earlier_days", "earlier_today"):
        assert shown.fold(identifier).animation.duration == 0


async def test_a_fold_stays_open_across_renders(shown: Shown) -> None:
    """Controlled: the next render passes the state back instead of the default."""
    await shown.toggle_fold("earlier_days", True)
    assert shown.fold("earlier_days").expanded is True
    shown.tick()  # a minute later: a re-render
    await shown.settle()
    assert shown.fold("earlier_days").expanded is True
    assert shown.fold("earlier_today").expanded is False
    await shown.toggle_fold("earlier_days", False)
    assert shown.fold("earlier_days").expanded is False


async def test_the_next_day_s_earlier_today_starts_collapsed(shown: Shown) -> None:
    """The open state belongs to the day: Friday's tile is not Thursday's."""
    await shown.toggle_fold("earlier_today", True)
    assert shown.fold("earlier_today").expanded is True
    clock.set_test_now(datetime(2026, 5, 15, 10, 0, tzinfo=ZONE))  # the welcome is over
    shown.tick()
    await shown.settle()
    assert shown.folded("earlier_today") == [WELCOME]
    assert shown.fold("earlier_today").expanded is False


async def test_the_minute_tick_folds_a_session_once_it_has_ended(
    shown: Shown,
) -> None:
    """The tick at 12:30 folds the sessions that end then into Earlier today."""
    clock.set_test_now(datetime(2026, 5, 14, 12, 30, tzinfo=ZONE))  # both end now
    shown.tick()
    await shown.settle()
    assert shown.folded("earlier_today") == [NOTEBOOKS, CHEESE_SHOP, INFERENCE]
    assert f"Earlier today (3{NBSP}sessions)" in shown.texts()
    assert shown.shown() == [WELCOME, KEYNOTE, TALK, OPEN_SPACE]


@pytest.fixture
def last_evening(setup: Setup) -> None:
    """Set the time to Sunday evening, when every saved session has ended."""
    setup.now = LAST_EVENING


@pytest.mark.usefixtures("last_evening")
async def test_when_everything_has_ended_it_says_so_and_offers_today(
    shown: Shown,
) -> None:
    """With every session ended, a heading says so and a button opens Now."""
    shown.node("my_schedule.all_over")
    assert "All your saved sessions are over" in shown.texts()
    # A level, or it is no heading for TalkBack or VoiceOver (F40).
    (title,) = [
        c
        for c in shown.controls
        if isinstance(c, ft.Semantics)
        and isinstance(c.content, ft.Text)
        and c.content.value == extras.ALL_OVER
    ]
    assert (title.header, title.heading_level) == (True, 2)
    assert shown.shown() == []
    (button,) = [c for c in shown.controls if isinstance(c, ft.FilledTonalButton)]
    assert button.content == "See what's on today"
    assert button.style is not None  # its sides stay 24 dp at large text (D-344)
    assert button.style.padding == LABEL_PADDING
    assert button.elevation == 0  # flat, as M3's tonal button
    await shown.session.dispatch_event(button._i, "click", None)
    await shown.settle()
    assert shown.went == ["/now"]


@pytest.fixture
def after(setup: Setup) -> None:
    """Set the time after the conference."""
    setup.now = AFTER


@pytest.mark.usefixtures("after")
async def test_after_the_conference_it_offers_no_today(shown: Shown) -> None:
    """Nothing is on today any more, so no button promises it."""
    shown.node("my_schedule.all_over")
    assert "PyCon US 2026 is over. Your saved sessions stay here." in shown.texts()
    assert shown.folded("earlier_days") == list(SAVED)
    assert shown.shown() == []
    assert not any(isinstance(c, ft.FilledTonalButton) for c in shown.controls)


@pytest.mark.usefixtures("after")
async def test_the_all_over_notice_sits_above_the_earlier_days_tile(
    shown: Shown,
) -> None:
    """Compact, not the full-screen empty state: the tile is still content."""
    root = shown.root().controls  # the strip, the quiet dropped notice (D-329), ...
    notice, tile = root[2], root[3]
    assert tile is shown.fold("earlier_days").root
    assert not any(
        isinstance(c, ft.Icon) and c.size == states.ICON_SIZE for c in _walk(notice)
    )


# ------------------------------------------------------------------ removal and Undo


@pytest.mark.usefixtures("before")
async def test_unstarring_removes_the_row_at_once_and_undo_brings_it_back(
    shown: Shown,
) -> None:
    """ux.md §4.4, §5.6: the row goes with the tap; Undo restores it."""
    await shown.tap_star(TALK)
    assert TALK not in shown.shown()
    assert TALK not in shown.favorites.ids
    assert shown.prefs_service.values[FAVORITES] == sorted(set(SAVED) - {TALK})
    (snack,) = shown.snack_bars
    assert cast(ft.Text, snack.content).value == REMOVED
    action = cast(ft.SnackBarAction, snack.action)
    assert action.label == UNDO

    await cast(Callable[[], Any], action.on_click)()
    await shown.settle()
    assert shown.shown()[-2:] == [TALK, OPEN_SPACE]
    assert shown.prefs_service.values[FAVORITES] == sorted(SAVED)


@pytest.mark.usefixtures("before")
async def test_removing_one_side_of_a_clash_clears_the_other_s_line(
    shown: Shown,
) -> None:
    """Unstarring one side of a clash drops the overlap from the other's phrase."""
    await shown.tap_star(DECORATORS)
    assert "Overlaps" not in shown.phrase(MCP)


@pytest.mark.usefixtures("before")
async def test_a_removal_re_renders_no_other_row(shown: Shown) -> None:
    """D-153: the views stay the same objects, so every other row skips its body."""
    shown.rows.clear()
    await shown.tap_star(TALK)
    assert shown.rows == []
    (snack,) = shown.snack_bars
    await cast(Callable[[], Any], cast(ft.SnackBarAction, snack.action).on_click)()
    await shown.settle()
    assert shown.rows == [TALK]  # only the row that came back


@pytest.mark.usefixtures("before")
async def test_a_removal_re_renders_only_its_own_day(shown: Shown) -> None:
    """D-153: the other days' sections get equal props and skip their bodies."""
    shown.slots.clear()
    await shown.tap_star(DECORATORS)
    assert shown.slots == ["9:00 AM", "1:30 PM"]  # Wednesday's two slots


@pytest.mark.usefixtures("before")
async def test_a_clash_removed_re_renders_only_the_row_whose_line_changed(
    shown: Shown,
) -> None:
    """Unstarring one side of a clash re-renders only the other side's row."""
    shown.rows.clear()
    await shown.tap_star(DECORATORS)
    assert shown.rows == [MCP]


# ------------------------------------------------------------------ states


@pytest.fixture
def nothing_saved(setup: Setup) -> None:
    """Save no session."""
    setup.saved = ()


@pytest.mark.usefixtures("nothing_saved")
async def test_nothing_saved_says_how_and_opens_the_schedule(shown: Shown) -> None:
    """ux.md §4.6, SCHED-08."""
    shown.node("my_schedule.empty")
    assert "Nothing saved yet" in shown.texts()
    (button,) = [c for c in shown.controls if isinstance(c, ft.FilledTonalButton)]
    assert button.content == "Browse the schedule"
    await shown.session.dispatch_event(button._i, "click", None)
    await shown.settle()
    assert shown.went == ["/schedule"]


@pytest.fixture
def dropped(setup: Setup) -> None:
    """Save only an id the feed does not list."""
    setup.saved = ("no-such-session",)


@pytest.mark.usefixtures("dropped")
async def test_saved_sessions_the_feed_dropped_are_not_nothing_saved(
    shown: Shown,
) -> None:
    """Saved ids the feed dropped get their own state, not "Nothing saved yet".

    D-172 keeps ids the feed no longer lists: saying "Nothing saved yet" would be
    untrue.
    """
    shown.node("my_schedule.dropped")
    assert not shown.nodes("my_schedule.dropped_notice")  # the state says it all
    assert "None of your saved sessions is in the schedule" in shown.texts()
    assert "Nothing saved yet" not in shown.texts()
    (button,) = [c for c in shown.controls if isinstance(c, ft.FilledTonalButton)]
    assert button.content == "Browse the schedule"


@pytest.fixture
def unread(setup: Setup) -> None:
    """Give the screen favorites that were never read."""
    setup.loaded = False


@pytest.mark.usefixtures("unread")
async def test_a_failed_read_is_not_an_empty_list(shown: Shown) -> None:
    """D-172: after the gate, ``loaded`` False means the saved list could not be read."""
    shown.node("my_schedule.unavailable")
    assert "Couldn't open My schedule" in shown.texts()
    assert "Nothing saved yet" not in shown.texts()
    assert not any(isinstance(c, ft.FilledTonalButton) for c in shown.controls)


@pytest.fixture
def no_data(setup: Setup) -> None:
    """Start without conference data or a fetch problem."""
    setup.data = False


@pytest.mark.usefixtures("no_data")
async def test_without_data_the_skeleton_shows_until_the_first_fetch_fails(
    shown: Shown,
) -> None:
    """Without data, before a fetch has failed, the screen shows the skeleton."""
    assert "skeleton" in shown.texts()


@pytest.fixture
def failed_fetch(setup: Setup) -> None:
    """Start without conference data, after a fetch failed offline."""
    setup.data, setup.problem = False, "offline"


@pytest.mark.usefixtures("failed_fetch")
async def test_without_data_a_failed_fetch_offers_try_again(shown: Shown) -> None:
    """Without data, a failed fetch shows the "Can't load the schedule" state."""
    shown.node("my_schedule.no_data")
    assert "Can't load the schedule" in shown.texts()


# ------------------------------------------------------------------ some dropped (D-329)

GONE, LOST = "gone-session", "lost-session"
"""Saved ids the 2026 feed does not list."""


def removal(session_id: str) -> Batch:
    """A batch, an hour before Thursday's clock, that removed ``session_id``."""
    start = datetime(2026, 5, 15, 11, 0, tzinfo=ZONE)
    last = Listing("A dropped talk", start, start + timedelta(minutes=30), "Room 104A")
    change = Change(session_id, ChangeKind.REMOVED, last, None)
    return Batch(THURSDAY - timedelta(hours=1), (change,))


@pytest.fixture
def one_dropped(setup: Setup) -> None:
    """Save every default session and one id the feed no longer lists."""
    setup.saved = (*SAVED, GONE)


@pytest.mark.usefixtures("one_dropped", "before")
async def test_a_notice_says_a_saved_session_is_no_longer_in_the_schedule(
    shown: Shown,
) -> None:
    """D-329: one live node says how many are gone; the rest of the list stays."""
    node = shown.node("my_schedule.dropped_notice")
    assert node.live_region
    texts = shown.texts()
    assert "1 saved session is no longer in the schedule" in texts
    assert "If the schedule lists it again, it comes back here." in texts
    assert shown.shown() == list(SAVED)
    # Under the status strip, before the first day's header.
    under_strip = list(_walk(shown.root().controls[1]))
    assert node in under_strip
    assert not shown.nodes("my_schedule.see_changes")  # the log has no removal
    shown.node("my_schedule.forget")


@pytest.mark.usefixtures("one_dropped", "before")
async def test_forget_unsaves_only_the_dropped_ids_with_undo(shown: Shown) -> None:
    """D-329: "Forget it" removes the dropped id, says so with Undo, and Undo restores."""
    forget = cast(ft.TextButton, shown.node("my_schedule.forget").content)
    assert forget.content == "Forget it"
    await shown.click(forget)
    assert shown.favorites.ids == frozenset(SAVED)
    assert shown.prefs_service.values[FAVORITES] == sorted(SAVED)
    assert not _words(shown.node("my_schedule.dropped_notice"))  # quiet again
    assert not shown.nodes("my_schedule.forget")
    (snack,) = shown.snack_bars
    assert cast(ft.Text, snack.content).value == REMOVED
    action = cast(ft.SnackBarAction, snack.action)
    assert action.label == UNDO

    await cast(Callable[[], Any], action.on_click)()
    await shown.settle()
    assert GONE in shown.favorites.ids
    assert _words(shown.node("my_schedule.dropped_notice"))


def _words(node: ft.Control) -> list[str]:
    """Return the texts under ``node`` (the live region or its merge), in order."""
    return [str(c.value) for c in _walk(node) if isinstance(c, ft.Text)]


@pytest.mark.usefixtures("one_dropped", "before")
async def test_the_notice_says_its_title_then_its_body_as_one_heading(
    shown: Shown,
) -> None:
    """D-329: one node whose label is the title, then the body, as the screen shows.

    A merge of the texts read the body first on Android: Flet's ``Semantics``
    always states ``enabled``, so a heading ``Semantics`` inside the live region
    conflicted with it and became a child node, whose label a merge puts after the
    live region's own. So the label is explicit and the texts are excluded.
    """
    node = cast(ft.Semantics, shown.node("my_schedule.dropped_notice"))
    title = "1 saved session is no longer in the schedule"
    body = "If the schedule lists it again, it comes back here."
    assert node.label == f"{title}\n{body}"
    assert _words(node) == [title, body]  # the screen's order too
    assert node.exclude_semantics
    assert node.container and node.live_region
    assert node.header and node.heading_level == 2
    inner = [c for c in _walk(node) if c is not node]
    assert not any(isinstance(c, ft.Semantics | ft.MergeSemantics) for c in inner)
    assert not any(isinstance(c, ft.TextButton) for c in inner)


@pytest.mark.usefixtures("two_dropped_one_logged")
async def test_the_notice_label_follows_the_count(shown: Shown) -> None:
    """D-329: with two dropped, the label is the plural title, then the plural body."""
    node = cast(ft.Semantics, shown.node("my_schedule.dropped_notice"))
    assert node.label == (
        "2 saved sessions are no longer in the schedule\n"
        "If the schedule lists them again, they come back here."
    )


@pytest.mark.usefixtures("before")
async def test_the_live_region_is_there_before_a_session_is_dropped(
    shown: Shown,
) -> None:
    """D-329, F61: the quiet node is mounted and keeps its id when a drop appears.

    Android's engine sends a live region's change only for a node it had in its
    previous update, so the notice must not mount with its words.
    """
    quiet = shown.node("my_schedule.dropped_notice")
    assert quiet.live_region
    assert not _words(quiet)
    assert not shown.nodes("my_schedule.forget")
    assert "EVENT_BUSY_OUTLINED" not in [
        str(c.icon) for c in shown.find(ft.Icon) if c.visible
    ]

    await shown.favorites.add_many(shown.storage, [GONE])  # as a refresh would
    await shown.settle()
    spoken = shown.node("my_schedule.dropped_notice")
    assert spoken._i == quiet._i  # the same node, its label changed
    assert _words(spoken)[0] == "1 saved session is no longer in the schedule"
    shown.node("my_schedule.forget")


@pytest.mark.usefixtures("before")
async def test_the_quiet_node_is_hidden_and_shows_with_its_words(
    shown: Shown,
) -> None:
    """D-329, F95: hidden with no dropped session, shown with one, hidden after Forget.

    Empty is not quiet on Android: Flet's ``Semantics`` always states ``enabled``,
    a focusable flag, so only ``hidden`` keeps TalkBack from stopping on the blank
    node. The node keeps its id throughout, so its reveal is a label change (F61).
    """
    quiet = cast(ft.Semantics, shown.node("my_schedule.dropped_notice"))
    assert quiet.hidden is True
    assert not _words(quiet)
    assert not quiet.label

    await shown.favorites.add_many(shown.storage, [GONE])  # 0 -> 1, as a refresh
    await shown.settle()
    spoken = shown.node("my_schedule.dropped_notice")
    assert spoken._i == quiet._i
    assert spoken.hidden is False
    assert _words(spoken)[0] == "1 saved session is no longer in the schedule"
    assert cast(ft.Semantics, spoken).label  # the reveal changes the label (F61)

    await shown.click(cast(ft.TextButton, shown.node("my_schedule.forget").content))
    again = shown.node("my_schedule.dropped_notice")  # 1 -> 0
    assert again._i == quiet._i
    assert again.hidden is True
    assert not _words(again)
    assert not cast(ft.Semantics, again).label


@pytest.fixture
def two_dropped_one_logged(setup: Setup) -> None:
    """Save two ids the feed no longer lists, one of them removed in the change log."""
    setup.saved = (*SAVED, GONE, LOST)
    setup.batches = (removal(LOST),)


@pytest.mark.usefixtures("two_dropped_one_logged")
async def test_a_logged_removal_links_to_schedule_changes(shown: Shown) -> None:
    """D-329: with a removal in the log, "See what changed" pushes Schedule changes."""
    texts = shown.texts()
    assert "2 saved sessions are no longer in the schedule" in texts
    assert "If the schedule lists them again, they come back here." in texts
    forget = cast(ft.TextButton, shown.node("my_schedule.forget").content)
    assert forget.content == "Forget them"
    see = cast(ft.TextButton, shown.node("my_schedule.see_changes").content)
    assert see.content == "See what changed"
    await shown.click(see)
    assert shown.went == ["/changes/2026"]  # on top of the View (no Router here)


def test_only_a_removal_of_a_dropped_id_counts_as_logged() -> None:
    """D-329: another session's removal, or a dropped id's retiming, links nowhere."""
    assert extras.logged({GONE}, [removal(GONE)])
    assert not extras.logged({GONE}, [removal(LOST)])
    moved = removal(GONE).changes[0]
    retimed = Change(GONE, ChangeKind.TIME, moved.old, moved.old)
    assert not extras.logged({GONE}, [Batch(THURSDAY, (retimed,))])
    assert not extras.logged({GONE}, [])
