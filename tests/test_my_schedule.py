"""Tests for the My schedule tab (#94; NEW-01, SCHED-07, SCHED-08; ux.md §5.6).

The screen runs in a real Flet session (``tests/sessions.py``), as the rows do in
``test_session_rows.py``: the store providers above it, a star tap as a dispatched
click, Flet's own scheduler re-rendering what changed. ``AppScaffold`` is replaced by
its body and the status strip by a placeholder (both have their own tests), and the
minute tick by a hook the test moves by hand, with ``clock.now()`` fixed. The fold
itself is a pure function, tested in ``test_agenda.py``.
"""

from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import flet as ft
import pytest
from flet.messaging.session import Session

from pycon_us import clock
from pycon_us.config import load_year
from pycon_us.core.row_views import SessionView
from pycon_us.favorites import Favorites, FavoritesCtx
from pycon_us.prefs import Prefs, PrefsCtx
from pycon_us.screens import my_schedule as screen
from pycon_us.screens.my_schedule import MySchedule
from pycon_us.services import Services, ServicesCtx
from pycon_us.services.storage import Storage
from pycon_us.state import Conference, ConferenceCtx, ViewMemory
from pycon_us.ui import fold, states
from pycon_us.ui import session_rows as rows
from pycon_us.ui.badges import REMOVED, UNDO
from tests.fakes import (
    MemoryClipboard,
    MemoryHaptics,
    MemoryLauncher,
    MemoryPrefs,
    MemorySemantics,
)
from tests.feeds import processed
from tests.sessions import rendering, settle

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
    return processed(2026).sessions[session_id].name


@dataclass
class Shown:
    """A Flet session showing ``MySchedule``, and what its rows did."""

    session: Session
    favorites: Favorites
    prefs_service: MemoryPrefs
    tick: Callable[[], None]
    navigated: list[str]
    renders: list[str] = field(default_factory=list)
    """The session ids whose row bodies ran, in order."""
    strips: list[dict[str, Any]] = field(default_factory=list)
    """The arguments of each ``StatusStrip`` the screen placed."""
    slots: list[str] = field(default_factory=list)
    """The slots day sections built, by gutter label: a day body builds each of its."""

    @property
    def controls(self) -> list[ft.Control]:
        """Every mounted control, in the session's index."""
        return [c for c in self.session.index.values() if isinstance(c, ft.Control)]

    def semantics(self, identifier: str) -> list[ft.Semantics]:
        return [
            c
            for c in self.controls
            if isinstance(c, ft.Semantics) and c.identifier == identifier
        ]

    def node(self, identifier: str) -> ft.Semantics:
        (found,) = self.semantics(identifier)
        return found

    def phrase(self, session_id: str) -> str:
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

    def fold(self, identifier: str) -> ft.ExpansionTile:
        title = self.node(f"my_schedule.{identifier}")
        tile = title.parent
        assert isinstance(tile, ft.ExpansionTile)
        return tile

    def folded(self, identifier: str) -> list[str]:
        """The rows inside a fold tile, in reading order."""
        return [
            str(c.identifier).removeprefix("my_schedule.session.")
            for c in _walk(self.fold(identifier).controls or [])
            if isinstance(c, ft.Semantics)
            and str(c.identifier).startswith("my_schedule.session.")
        ]

    def root(self) -> ft.ListView:
        (found,) = [c for c in self.controls if isinstance(c, ft.ListView)]
        return found

    def texts(self) -> list[str]:
        return [str(c.value) for c in self.controls if isinstance(c, ft.Text)]

    async def settle(self) -> None:
        await settle()

    async def tap_star(self, session_id: str) -> None:
        star = self.node(f"my_schedule.favorite.{session_id}").content
        assert isinstance(star, ft.IconButton)
        await self.session.dispatch_event(star._i, "click", None)
        await self.settle()

    async def toggle_fold(self, identifier: str, expanded: bool) -> None:
        await self.session.dispatch_event(self.fold(identifier)._i, "change", expanded)
        await self.settle()

    @property
    def snack_bars(self) -> list[ft.SnackBar]:
        return [
            d for d in self.session.page._dialogs.controls if isinstance(d, ft.SnackBar)
        ]


_PARTS = ("content", "leading", "title", "subtitle", "trailing")


def _walk(node: Any, *, folds: bool = False) -> Iterator[ft.Control]:
    """Yield the controls under ``node`` in reading order, through components' bodies.

    A component's rendered body is its ``_b`` (Flet's ``Component``, at the D-81
    pin). Fold tiles are yielded but not entered unless ``folds`` is set.
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
    if isinstance(node, ft.ExpansionTile) and not folds:
        yield from _walk(node.title)
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


@pytest.fixture
def setup() -> Setup:
    return Setup()


@pytest.fixture
async def shown(
    setup: Setup, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Shown]:
    prefs_service = MemoryPrefs()
    prefs_service.values[FAVORITES] = list(setup.saved)
    storage = Storage(prefs=prefs_service, directory=tmp_path, year=2026)
    svc = Services(
        year=YEAR,
        storage=storage,
        memory=ViewMemory(),
        semantics=MemorySemantics(),
        haptics=MemoryHaptics(),
        launcher=MemoryLauncher(),
        clipboard=MemoryClipboard(),
    )
    if setup.data:
        conference = Conference(data=processed(2026), source="bundled", version=1)
    else:
        conference = Conference(problem=setup.problem)
    favorites = Favorites()
    prefs = Prefs(loaded=True, reduce_motion=setup.reduce_motion)
    if setup.loaded:
        await favorites.load(storage)
    clock.set_test_now(setup.now)

    ticks: list[Callable[[int], None]] = []

    def use_minute() -> int:
        minute, set_minute = ft.use_state(0)
        ticks.append(set_minute)
        return minute

    navigated: list[str] = []
    renders: list[str] = []
    slots: list[str] = []
    strips: list[dict[str, Any]] = []
    phrase = rows.spoken_phrase

    def counted(*args: Any, **kwargs: Any) -> str:
        renders.append(cast(SessionView, args[-1]).session.id)
        return phrase(*args, **kwargs)

    # Each row body says its phrase once: counting the calls counts the bodies.
    monkeypatch.setattr(rows, "spoken_phrase", counted)
    time_slot = screen.TimeSlot

    def counted_slot(label: str, *args: Any, **kwargs: Any) -> ft.Control:
        slots.append(label)
        return time_slot(label, *args, **kwargs)

    monkeypatch.setattr(screen, "TimeSlot", counted_slot)
    monkeypatch.setattr(screen, "use_minute", use_minute)

    def strip(**kwargs: Any) -> ft.Control:
        strips.append(kwargs)
        return ft.Text("strip")

    monkeypatch.setattr(screen, "StatusStrip", strip)
    monkeypatch.setattr(states, "SkeletonList", lambda: ft.Text("skeleton"))
    monkeypatch.setattr(screen, "AppScaffold", lambda **kwargs: kwargs["body"])

    @ft.component
    def Root() -> ft.Control:
        return ServicesCtx(
            svc,
            lambda: ConferenceCtx(
                conference,
                lambda: PrefsCtx(
                    prefs, lambda: FavoritesCtx(favorites, lambda: MySchedule())
                ),
            ),
        )

    try:
        async with rendering(Root) as session:
            # Only a tap navigates, so the first render has not needed it.
            monkeypatch.setattr(session.page, "navigate", navigated.append)
            yield Shown(
                session,
                favorites,
                prefs_service,
                tick=lambda: ticks[-1](len(ticks)),
                navigated=navigated,
                renders=renders,
                strips=strips,
                slots=slots,
            )
    finally:
        clock.set_test_now(None)


# ------------------------------------------------------------------ the agenda


@pytest.fixture
def before(setup: Setup) -> None:
    setup.now = BEFORE


@pytest.mark.usefixtures("before")
async def test_saved_sessions_show_by_day_and_slot_in_schedule_order(
    shown: Shown,
) -> None:
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
    gutters = [
        str(c.label)
        for c in _walk(shown.root())
        if isinstance(c, ft.Semantics) and c.header and c.label
    ]
    # Wednesday's two 9:00 tutorials share one gutter.
    assert gutters[:3] == ["9:00 AM", "1:30 PM", "9:00 AM"]


@pytest.mark.usefixtures("before")
async def test_every_saved_row_has_a_filled_star(shown: Shown) -> None:
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
    assert shown.phrase(NOTEBOOKS).endswith(
        f"Overlaps with “{name(CHEESE_SHOP)}” and “{name(INFERENCE)}”."
    )
    assert shown.phrase(CHEESE_SHOP).endswith(f"Overlaps with “{name(NOTEBOOKS)}”.")


@pytest.mark.usefixtures("before")
async def test_a_row_without_a_clash_says_nothing_of_one(shown: Shown) -> None:
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
    view = rows.session_views(processed(2026), (TALK,), ZONE, use_24h=False)[0]
    assert rows.spoken_phrase([], view, overlaps=("A", "B", "C")).endswith(
        "Overlaps with “A”, “B” and “C”."
    )


async def test_a_clash_that_has_ended_is_not_shown(shown: Shown) -> None:
    """Thursday 10:45: the 9:30 workshop is over, so the tutorial names only 11:30's,
    and folded rows carry no clash line: neither can change a plan any more."""
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
    title = cast(ft.Text, cast(ft.Semantics, earlier_days.title).content)
    assert title.value == f"Earlier days (3{NBSP}sessions)"
    assert earlier_days.expanded is False  # folded until tapped
    style = cast(ft.AnimationStyle, earlier_days.animation_style)
    assert style.duration == fold.EXPAND_MS
    assert shown.folded("earlier_days") == [MCP, DECORATORS, RAG]
    assert f"Earlier today (1{NBSP}session)" in shown.texts()
    assert shown.folded("earlier_today") == [CHEESE_SHOP]
    # Today's header comes first, then what is still on or to come.
    assert shown.headers()[:2] == ["Thursday, May 14", "Friday, May 15"]
    assert shown.shown() == [NOTEBOOKS, INFERENCE, WELCOME, KEYNOTE, TALK, OPEN_SPACE]


@pytest.fixture
def reduced(setup: Setup) -> None:
    setup.reduce_motion = True


@pytest.mark.usefixtures("reduced")
async def test_the_folds_open_without_animation_under_reduced_motion(
    shown: Shown,
) -> None:
    """D-173: the tiles' animation is ``prefs.motion_ms()`` long, 0 here."""
    for identifier in ("earlier_days", "earlier_today"):
        style = cast(ft.AnimationStyle, shown.fold(identifier).animation_style)
        assert style.duration == 0


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
    clock.set_test_now(datetime(2026, 5, 14, 12, 30, tzinfo=ZONE))  # both end now
    shown.tick()
    await shown.settle()
    assert shown.folded("earlier_today") == [NOTEBOOKS, CHEESE_SHOP, INFERENCE]
    assert f"Earlier today (3{NBSP}sessions)" in shown.texts()
    assert shown.shown() == [WELCOME, KEYNOTE, TALK, OPEN_SPACE]


@pytest.fixture
def last_evening(setup: Setup) -> None:
    setup.now = LAST_EVENING


@pytest.mark.usefixtures("last_evening")
async def test_when_everything_has_ended_it_says_so_and_offers_today(
    shown: Shown,
) -> None:
    shown.node("my_schedule.all_over")
    assert "All your saved sessions are over" in shown.texts()
    # A level, or it is no heading for TalkBack or VoiceOver (F40).
    (title,) = [
        c
        for c in shown.controls
        if isinstance(c, ft.Semantics)
        and isinstance(c.content, ft.Text)
        and c.content.value == screen.ALL_OVER
    ]
    assert (title.header, title.heading_level) == (True, 2)
    assert shown.shown() == []
    (button,) = [c for c in shown.controls if isinstance(c, ft.FilledTonalButton)]
    assert button.content == "See what's on today"
    await shown.session.dispatch_event(button._i, "click", None)
    await shown.settle()
    assert shown.navigated == ["/now"]


@pytest.fixture
def after(setup: Setup) -> None:
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
    root = shown.root().controls
    notice, tile = root[1], root[2]
    assert isinstance(tile, ft.ExpansionTile)
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
    await shown.tap_star(DECORATORS)
    assert "Overlaps" not in shown.phrase(MCP)


@pytest.mark.usefixtures("before")
async def test_a_removal_re_renders_no_other_row(shown: Shown) -> None:
    """D-153: the views stay the same objects, so every other row skips its body."""
    shown.renders.clear()
    await shown.tap_star(TALK)
    assert shown.renders == []
    (snack,) = shown.snack_bars
    await cast(Callable[[], Any], cast(ft.SnackBarAction, snack.action).on_click)()
    await shown.settle()
    assert shown.renders == [TALK]  # only the row that came back


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
    shown.renders.clear()
    await shown.tap_star(DECORATORS)
    assert shown.renders == [MCP]


# ------------------------------------------------------------------ states


@pytest.fixture
def nothing_saved(setup: Setup) -> None:
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
    assert shown.navigated == ["/schedule"]


@pytest.fixture
def dropped(setup: Setup) -> None:
    setup.saved = ("no-such-session",)


@pytest.mark.usefixtures("dropped")
async def test_saved_sessions_the_feed_dropped_are_not_nothing_saved(
    shown: Shown,
) -> None:
    """D-172 keeps ids the feed no longer lists: saying "Nothing saved yet" would be
    untrue."""
    shown.node("my_schedule.dropped")
    assert "None of your saved sessions is in the schedule" in shown.texts()
    assert "Nothing saved yet" not in shown.texts()
    (button,) = [c for c in shown.controls if isinstance(c, ft.FilledTonalButton)]
    assert button.content == "Browse the schedule"


@pytest.fixture
def unread(setup: Setup) -> None:
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
    setup.data = False


@pytest.mark.usefixtures("no_data")
async def test_without_data_the_skeleton_shows_until_the_first_fetch_fails(
    shown: Shown,
) -> None:
    assert "skeleton" in shown.texts()


@pytest.fixture
def failed_fetch(setup: Setup) -> None:
    setup.data, setup.problem = False, "offline"


@pytest.mark.usefixtures("failed_fetch")
async def test_without_data_a_failed_fetch_offers_try_again(shown: Shown) -> None:
    shown.node("my_schedule.no_data")
    assert "Can't load the schedule" in shown.texts()
