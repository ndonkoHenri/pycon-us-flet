"""Tests for room detail (#101; ROOM-02, ROOM-03; ux.md §5.9).

``RoomDetail`` runs in a real Flet session, as session detail does in
``test_session.py``: the store providers are written out above it, ``AppScaffold`` is
replaced by a column that keeps the title and the body, and the scroll to the row is a
recorder, since no Flutter answers it here. The sessions are the recorded 2026 feed's,
and the clock is fixed in conference time. How the page looks, at 200 % text and in
dark mode, is checked on devices (the PR); here, what it shows, says and does: the
highlight's parsing, its one scroll, "Now in this room" at fixed times and rows that
leave out the room's own name. The highlight's wait is held until a test ends it
(``tests/timers.py``), so a slow host never ends it before the test looks (#270).
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote
from zoneinfo import ZoneInfo

import flet as ft
import pytest
from flet.controls.context import _context_page
from flet.messaging.connection import Connection
from flet.messaging.session import Session
from flet.pubsub.pubsub_hub import PubSubHub

from pycon_us import clock
from pycon_us.config import load_year
from pycon_us.core.models import ConferenceData
from pycon_us.favorites import Favorites, FavoritesCtx
from pycon_us.locations import query_of
from pycon_us.memory import ViewMemory
from pycon_us.prefs import Prefs, PrefsCtx
from pycon_us.screens import room as screen
from pycon_us.screens import room_days
from pycon_us.services import Services, ServicesCtx
from pycon_us.services.storage import Storage
from pycon_us.state import Conference, ConferenceCtx
from pycon_us.theme import DARK_SCHEME, LIGHT_SCHEME, LIGHT_TOKENS, TokensCtx
from pycon_us.ui import scrolling, status_strip
from tests.fakes import (
    MemoryClipboard,
    MemoryHaptics,
    MemoryLauncher,
    MemoryPrefs,
    MemorySemantics,
)
from tests.feeds import processed
from tests.test_theme import contrast_ratio
from tests.timers import HeldSleeps
from tests.trees import descendants, texts

YEAR = load_year(2026)
PACIFIC = ZoneInfo("America/Los_Angeles")
ROOM = "grand-ballroom-a"
VIEW = f"/schedule/session/31/room/{ROOM}"
"""The room's View path, pushed from a session: links push on top of it."""

TACHYON = "31"
"""Grand Ballroom A, Saturday 3:15 PM: far down Saturday's list."""

SUNDAY_TALK = "108"
"""Grand Ballroom A, Sunday 1:45 PM."""

HUMANS = "142"
"""Grand Ballroom A, Saturday 10:30 to 11:00 AM."""

LIGHTNING = "163"
"""Saturday's 8:00 AM lightning talks: given in the Arena, streamed here."""

SATURDAY_MORNING = datetime(2026, 5, 16, 10, 40, tzinfo=PACIFIC)
"""During "Python for Humans" in Grand Ballroom A."""

SHARED_SLOT = ("9163", "9126")
"""Room 102C's two sessions that start at 2:00 PM on Saturday: one slot, two rows."""


@dataclass
class Scroll:
    """One scroll the screen asked for."""

    key: str
    duration: int


@dataclass
class Room:
    """A Flet session showing one ``RoomDetail``, and what it asked for."""

    session: Session
    memory: ViewMemory
    favorites: Favorites
    pushed: list[str]
    scrolls: list[Scroll]
    titles: list[str]
    toggle: Callable[[bool], None]
    services: list[Services] = field(default_factory=list)
    sleeps: HeldSleeps = field(default_factory=HeldSleeps)
    """The screen's sleeps: the highlight stays on until the test releases its wait."""

    def nodes(self, identifier: str) -> list[ft.Semantics]:
        return [
            c
            for c in self.session.index.values()
            if isinstance(c, ft.Semantics) and c.identifier == identifier
        ]

    def node(self, identifier: str) -> ft.Semantics:
        (found,) = self.nodes(identifier)
        return found

    @property
    def tabs(self) -> ft.Tabs:
        (found,) = [c for c in self.session.index.values() if isinstance(c, ft.Tabs)]
        return found

    def lit_box(self) -> ft.Container:
        """The box around the highlighted row: its ``ScrollKey`` and its fill."""
        (found,) = [
            c
            for c in self.session.index.values()
            if isinstance(c, ft.Container) and isinstance(c.key, ft.ScrollKey)
        ]
        return found

    async def settle(self) -> None:
        for _ in range(30):
            await asyncio.sleep(0)

    async def wait(self, seconds: float) -> None:
        """Let ``seconds`` pass: for tests that check nothing more happened."""
        await asyncio.sleep(seconds)
        await self.settle()

    async def until(self, holds: Callable[[], bool], *, timeout: float = 30.0) -> None:
        """Settle until ``holds()`` is true, or fail after ``timeout`` seconds.

        A poll rather than a fixed wait, so a loaded host only makes it slower; the
        deadline is generous because a passing test never reaches it (#237).
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while not holds():
            assert loop.time() < deadline, "the screen did not get there in time"
            await asyncio.sleep(0.01)
        await self.settle()

    async def fade(self) -> None:
        """End the highlight's wait, as its time passing would, and see the row unlit."""
        await self.sleeps.release()
        await self.until(lambda: self.lit_box().bgcolor == room_days.UNLIT)

    def day_lists(self) -> list[ft.ListView]:
        """The day pages, in tab order."""
        (pages,) = [
            c for c in self.session.index.values() if isinstance(c, ft.TabBarView)
        ]
        return [cast(ft.ListView, page) for page in pages.controls]

    async def show(self, shown: bool) -> None:
        """Mount the room again, or leave it (Back), in the same Flet session."""
        self.toggle(shown)
        await self.settle()


type Render = Callable[..., Awaitable[Room]]


@pytest.fixture
async def render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Render]:
    """Return render(route, ...): ``RoomDetail`` for ``ROOM`` opened at ``route``."""
    sessions: list[tuple[Session, Services]] = []
    sleeps = HeldSleeps()
    monkeypatch.setattr(screen, "asyncio", sleeps)  # the room module's name only

    async def show(
        route: str,
        *,
        slug: str = ROOM,
        now: datetime = SATURDAY_MORNING,
        reduce_motion: bool = False,
        memory: ViewMemory | None = None,
        data: ConferenceData | None = None,
    ) -> Room:
        clock.set_test_now(now)
        titles: list[str] = []
        scrolls: list[Scroll] = []

        def scaffold(*, title: str, body: ft.Control) -> ft.Control:
            titles.append(title)
            return ft.Column([body])

        async def scroll(
            list_ref: ft.Ref[ft.ListView],
            key: str,
            *,
            duration: int,
            ended: asyncio.Event,
        ) -> str:
            assert list_ref.current is not None  # the day list that shows the row
            scrolls.append(Scroll(key, duration))
            return "landed"

        monkeypatch.setattr(screen, "AppScaffold", scaffold)
        monkeypatch.setattr(screen, "jump_to_key", scroll)
        monkeypatch.setattr(ft, "use_view_path", lambda: VIEW)
        storage = Storage(prefs=MemoryPrefs(), directory=tmp_path, year=2026)
        svc = Services(
            year=YEAR,
            storage=storage,
            memory=memory or ViewMemory(),
            semantics=MemorySemantics(),
            haptics=MemoryHaptics(),
            launcher=MemoryLauncher(),
            clipboard=MemoryClipboard(),
        )
        conference = Conference(
            data=data or processed(2026), source="bundled", version=1
        )
        favorites = Favorites()
        prefs = Prefs(loaded=True, reduce_motion=reduce_motion)
        await favorites.load(storage)
        toggles: list[Callable[[bool], None]] = []

        @ft.component
        def Root() -> ft.Control:
            shown, set_shown = ft.use_state(True)
            toggles[:] = [set_shown]
            return ServicesCtx(
                svc,
                lambda: ConferenceCtx(
                    conference,
                    lambda: PrefsCtx(
                        prefs,
                        lambda: FavoritesCtx(
                            favorites,
                            lambda: TokensCtx(
                                LIGHT_TOKENS,
                                lambda: (
                                    screen.RoomDetail(slug)
                                    if shown
                                    else ft.Text("Back on the session")
                                ),
                            ),
                        ),
                    ),
                ),
            )

        flet_session = Session(_connection())
        page = flet_session.page
        page.route = route
        pushed: list[str] = []
        monkeypatch.setattr(page, "navigate", pushed.append)
        _context_page.set(page)  # pyright: ignore[reportArgumentType]
        sessions.append((flet_session, svc))
        page.render(Root)
        flet_session.get_page_patch()
        room = Room(
            flet_session,
            svc.memory,
            favorites,
            pushed,
            scrolls,
            titles,
            lambda shown: toggles[0](shown),
            [svc],
            sleeps,
        )
        await room.settle()
        return room

    try:
        yield show
    finally:
        for flet_session, svc in sessions:
            svc.close()  # the minute ticks end (D-147)
            flet_session.close()
        await asyncio.sleep(0)
        clock.set_test_now(None)


def _connection() -> Connection:
    """A connection to no client, as Flet's own component tests use."""
    conn = Connection()
    conn.pubsubhub = PubSubHub()
    conn.send_message = lambda message: None  # pyright: ignore[reportAttributeAccessIssue]
    return conn


def highlighted(session_id: str) -> str:
    """The location a session's room tile pushes (``when_where.room_href``)."""
    return f"{VIEW}?highlight={quote(session_id, safe='')}"


def phrase_of(room: Room, session_id: str) -> str:
    return str(room.node(f"room.session.{session_id}").label)


# ------------------------------------------------------------------ the highlight


def test_the_highlight_names_one_of_the_room_s_sessions() -> None:
    data = processed(2026)
    room = data.rooms[ROOM]
    assert screen.highlight_of({"highlight": TACHYON}, room) == TACHYON
    assert screen.highlight_of({}, room) is None
    assert screen.highlight_of({"highlight": ""}, room) is None
    # A session of another room: a stale or hand-made link highlights nothing.
    assert screen.highlight_of({"highlight": "191"}, room) is None
    assert screen.highlight_of({"highlight": TACHYON}, None) is None


def test_the_highlight_compares_ids_as_strings() -> None:
    """Ionic compared a number with a string, so its highlight never showed (ROOM-03)."""
    room = processed(2026).rooms[ROOM]
    query = query_of(highlighted(TACHYON))
    assert query == {"highlight": "31"}
    assert screen.highlight_of(query, room) == "31"
    assert screen.highlight_of({"highlight": "031"}, room) is None


def test_a_quoted_synthetic_id_reaches_the_room_whole() -> None:
    """A break's id holds spaces and colons (D-42); the tile quotes it, the query unquotes."""
    data = processed(2026)
    coffee = "break-Expo Hall AB-2026-05-15T08:00:00-07:00"
    query = query_of(f"/map/room/expo-hall-ab?highlight={quote(coffee, safe='')}")
    assert screen.highlight_of(query, data.rooms["expo-hall-ab"]) == coffee


@pytest.mark.parametrize(
    ("highlighted_day", "current", "expected"),
    [
        (date(2026, 5, 17), date(2026, 5, 16), date(2026, 5, 17)),  # the row's day
        (None, date(2026, 5, 16), date(2026, 5, 16)),  # today
        (None, date(2026, 10, 13), date(2026, 5, 15)),  # off season: the first day
        (date(2026, 5, 13), date(2026, 5, 13), date(2026, 5, 15)),  # neither listed
    ],
)
def test_the_room_opens_on_the_row_s_day_else_today_else_its_first_day(
    highlighted_day: date | None, current: date, expected: date
) -> None:
    days = [date(2026, 5, 15), date(2026, 5, 16), date(2026, 5, 17)]
    assert screen.opening_day(days, highlighted_day, current) == expected


async def test_opened_from_a_session_the_room_shows_its_day_and_scrolls_to_it_once(
    render: Render,
) -> None:
    room = await render(highlighted(TACHYON))
    assert room.tabs.selected_index == 1  # Friday, Saturday, Sunday
    assert room.scrolls == [Scroll("session-31", 400)]
    assert room.memory.room_highlights == {VIEW: TACHYON}


async def test_only_the_scrolled_day_s_list_builds_every_row(render: Render) -> None:
    """``scroll_to`` reaches only a built item (F32): that list is built in full (D-154)."""
    room = await render(highlighted(TACHYON))
    lists = room.day_lists()
    assert [lst.cache_extent for lst in lists] == [
        None,
        scrolling.FULL_LIST_EXTENT,
        None,
    ]
    assert [lst.on_scroll is not None for lst in lists] == [False, True, False]


async def test_the_row_is_lit_then_the_highlight_fades(render: Render) -> None:
    room = await render(highlighted(TACHYON))
    box = room.lit_box()
    assert box.key == ft.ScrollKey("session-31")
    assert box.bgcolor == room_days.HIGHLIGHT
    assert isinstance(box.animate, ft.Animation) and box.animate.duration == 250
    await room.until(lambda: room.sleeps.held == 1)
    assert room.sleeps.asked == [screen.HIGHLIGHT_S]  # all of it, once in place
    assert room.lit_box().bgcolor == room_days.HIGHLIGHT  # lit while it waits
    await room.fade()


async def test_a_row_alone_in_its_slot_is_lit_with_its_time(render: Render) -> None:
    """The tint spans the slot, the gutter's time too, as a selected item (D-194).

    The slot's divider stays above the box, as the Schedule's (ux.md §5.2): the jump
    puts the time under the tab bar's line, not a second line. 3:15 PM is not the
    day's first slot, so it has one.
    """
    room = await render(highlighted(TACHYON))
    box = room.lit_box()
    assert _inside(room.node(f"room.session.{TACHYON}"), box)
    assert any(
        isinstance(c, ft.Semantics) and c.header and c.label == "3:15 PM"
        for c in descendants(box)
    )
    assert not any(isinstance(c, ft.Divider) for c in descendants(box))
    slot = cast(ft.Column, box.parent)
    assert isinstance(slot.controls[0], ft.Divider) and slot.controls[1] is box


def _inside(node: ft.Control, ancestor: ft.Control) -> bool:
    """Whether ``node`` renders under ``ancestor``, through components too."""
    parent = node.parent
    while parent is not None:
        if parent is ancestor:
            return True
        parent = parent.parent
    return False


async def test_a_row_that_shares_its_slot_is_lit_alone(render: Render) -> None:
    first, other = SHARED_SLOT
    room = await render(
        highlighted(first),  # the fixture's View path; the slug is what counts
        slug="room-102c",
        now=datetime(2026, 5, 16, 14, 10, tzinfo=PACIFIC),
    )
    box = room.lit_box()
    assert getattr(box.content, "key", None) == first  # the row, keyed by its id
    assert not _inside(room.node(f"room.session.{other}"), box)


async def test_under_reduced_motion_the_scroll_jumps_and_the_highlight_just_goes(
    render: Render,
) -> None:
    room = await render(highlighted(TACHYON), reduce_motion=True)
    assert room.scrolls == [Scroll("session-31", 0)]
    assert room.lit_box().bgcolor == room_days.HIGHLIGHT
    assert room.lit_box().animate is None
    await room.until(lambda: room.sleeps.held == 1)
    assert room.sleeps.asked == [screen.HIGHLIGHT_S]
    await room.fade()


async def test_a_re_render_does_not_scroll_again(render: Render) -> None:
    """A star tap, a refresh, Back from a detail: the effect ran once (D-18)."""
    room = await render(highlighted(TACHYON))
    await room.favorites.toggle(room.services[0].storage, HUMANS)
    await room.wait(0.1)
    assert len(room.scrolls) == 1


async def test_a_view_rebuilt_in_a_new_session_does_not_scroll_or_light_up(
    render: Render,
) -> None:
    """D-143: a replaced session's View never unmounts (F30); its successor finds it.

    It still opens on the session's day, Sunday, where the user came for it.
    """
    first = await render(highlighted(SUNDAY_TALK))
    again = await render(highlighted(SUNDAY_TALK), memory=first.memory)
    assert again.scrolls == []
    assert again.tabs.selected_index == 2
    assert not any(
        isinstance(c, ft.Container) and isinstance(c.key, ft.ScrollKey)
        for c in again.session.index.values()
    )


async def test_after_leaving_the_room_the_next_room_tile_highlights_again(
    render: Render,
) -> None:
    room = await render(highlighted(TACHYON))
    await room.fade()
    await room.show(False)  # Back pops the room: it forgets its highlight
    assert room.memory.room_highlights == {}
    await room.show(True)  # the session's room tile, tapped again
    await room.until(lambda: len(room.scrolls) == 2)
    assert [scroll.key for scroll in room.scrolls] == ["session-31", "session-31"]


async def test_without_a_highlight_nothing_scrolls_and_today_shows(
    render: Render,
) -> None:
    room = await render(VIEW)
    assert room.scrolls == []
    assert room.tabs.selected_index == 1  # the clock says Saturday
    assert room.memory.room_highlights == {}
    assert not any(
        isinstance(c, ft.Container) and isinstance(c.key, ft.ScrollKey)
        for c in room.session.index.values()
    )
    # A room opened from the Map builds no list in full.
    assert {lst.cache_extent for lst in room.day_lists()} == {None}


async def test_a_highlight_of_another_room_s_session_is_ignored(
    render: Render,
) -> None:
    room = await render(highlighted("191"))  # a tutorial in Room 102C
    assert room.scrolls == []
    assert room.memory.room_highlights == {}


@pytest.mark.parametrize("dark", [False, True])
def test_the_lit_row_s_text_keeps_its_contrast(dark: bool) -> None:
    """Dark ``primary_container`` put the supporting text at 3.7:1 (D-194)."""
    scheme = DARK_SCHEME if dark else LIGHT_SCHEME
    fill = _blend(str(scheme.primary), str(scheme.surface), room_days.HIGHLIGHT_OPACITY)
    for text in (scheme.on_surface, scheme.on_surface_variant):
        assert contrast_ratio(fill, str(text)) >= 4.5
    assert contrast_ratio(fill, str(scheme.surface)) >= 1.25  # it shows


def _blend(color: str, under: str, opacity: float) -> str:
    channels = [
        round(
            opacity * int(color[i : i + 2], 16)
            + (1 - opacity) * int(under[i : i + 2], 16)
        )
        for i in (1, 3, 5)
    ]
    return "#" + "".join(f"{c:02X}" for c in channels)


# ------------------------------------------------------------------ the day lists


async def test_one_tab_per_day_the_room_has_sessions_today_marked(
    render: Render,
) -> None:
    room = await render(VIEW)
    labels = [str(room.node(f"room.day_tab.{i}").content) for i in range(3)]
    assert len(room.nodes("room.day_tab.3")) == 0
    spoken = [
        cast(ft.Text, t).semantics_label
        for i in range(3)
        for t in descendants(room.node(f"room.day_tab.{i}"))
        if isinstance(t, ft.Text)
    ]
    assert spoken == ["Friday, May 15", "Saturday, May 16, today", "Sunday, May 17"]
    assert labels  # each tab has its label


async def test_a_picked_day_survives_a_re_render(render: Render) -> None:
    """The picked day is state that on_change sets: a star tap keeps the tab (D-194)."""
    room = await render(VIEW)
    assert room.tabs.selected_index == 1  # today, Saturday
    room.session.apply_patch(room.tabs._i, {"selected_index": 0})  # as Flutter does
    await room.session.dispatch_event(room.tabs._i, "change", 0)
    await room.settle()
    await room.favorites.toggle(room.services[0].storage, HUMANS)
    await room.settle()
    assert room.tabs.selected_index == 0


async def test_the_room_s_rows_leave_out_its_name(render: Render) -> None:
    """The page's title names the room: the rows say the time alone (#101's comment)."""
    room = await render(VIEW)
    assert room.titles[-1] == "Grand Ballroom A"
    assert phrase_of(room, HUMANS).endswith("10:30 to 11:00 AM. Justin Lee."), (
        phrase_of(room, HUMANS)
    )
    assert "Grand Ballroom A" not in phrase_of(room, HUMANS)
    row = room.node(f"room.session.{HUMANS}")
    assert "Grand Ballroom A" not in texts(row)


async def test_a_row_given_elsewhere_keeps_its_place(render: Render) -> None:
    room = await render(VIEW)
    assert "Pacific Ballroom - Arena" in phrase_of(room, LIGHTNING)


async def test_a_row_pushes_its_session_on_top_of_the_room(render: Render) -> None:
    room = await render(VIEW)
    tap = room.node(f"room.session.{HUMANS}")
    box = next(c for c in room.session.index.values() if _holds(c, tap))
    await room.session.dispatch_event(box._i, "click", None)
    await room.settle()
    assert room.pushed == [f"{VIEW}/session/{HUMANS}"]


def _holds(control: Any, node: ft.Semantics) -> bool:
    return (
        isinstance(control, ft.Container)
        and control.on_click is not None
        and control.content is node
    )


# ------------------------------------------------------------------ now in this room


async def test_now_in_this_room_names_the_session_on_and_opens_it(
    render: Render,
) -> None:
    room = await render(VIEW, now=SATURDAY_MORNING)
    now = room.node("room.now")
    tile = cast(ft.ListTile, now.content)
    assert isinstance(tile.title, ft.Text)
    assert tile.title.value.startswith("Python for Humans")
    assert tile.title.max_lines == 3
    assert texts(cast(ft.Control, tile.subtitle)) == ["10:30–11:00\N{NO-BREAK SPACE}AM"]
    assert any(
        isinstance(c, ft.Semantics)
        and c.header
        and c.heading_level == 3  # in the day, beside its slots (D-211)
        and texts(c) == ["Now in this room"]
        for c in room.session.index.values()
    )
    tile.on_click()  # type: ignore[misc]
    assert room.pushed == [f"{VIEW}/session/{HUMANS}"]


async def test_a_divider_closes_now_in_this_room(render: Render) -> None:
    """Else the day's first slot reads as the section's second item (D-194)."""
    room = await render(VIEW, now=SATURDAY_MORNING)
    today = room.day_lists()[1]
    # The outermost column between the tile and today's list: NowInRoom's own.
    columns: list[ft.Column] = []
    parent = room.node("room.now").parent
    while parent is not None and parent is not today:
        if isinstance(parent, ft.Column):
            columns.append(parent)
        parent = parent.parent
    assert parent is today
    assert isinstance(columns[-1].controls[-1], ft.Divider)


async def test_now_in_this_room_says_where_a_streamed_session_is_given(
    render: Render,
) -> None:
    """Time and place are two texts in a wrapping row, as a row's meta (D-184)."""
    room = await render(VIEW, now=datetime(2026, 5, 16, 8, 30, tzinfo=PACIFIC))
    tile = cast(ft.ListTile, room.node("room.now").content)
    subtitle = cast(ft.Control, tile.subtitle)
    assert texts(subtitle) == [
        "8:00–9:00\N{NO-BREAK SPACE}AM\N{NO-BREAK SPACE}·",
        "Pacific Ballroom - Arena",
    ]
    (line,) = [c for c in descendants(subtitle) if isinstance(c, ft.Row)]
    assert line.wrap
    time, place = cast(list[ft.Text], line.controls)
    spoken = [time.semantics_label, place.semantics_label or place.value]
    assert " ".join(spoken) == "8:00 to 9:00 AM, Pacific Ballroom - Arena"


async def test_with_several_on_the_latest_is_named_and_the_rest_counted(
    render: Render,
) -> None:
    room = await render(
        "/map/room/room-102c",
        slug="room-102c",
        now=datetime(2026, 5, 16, 16, 30, tzinfo=PACIFIC),
    )
    tile = cast(ft.ListTile, room.node("room.now").content)
    assert cast(ft.Text, tile.title).value == "Organizing IRL meetups"
    assert texts(cast(ft.Control, tile.subtitle)) == [
        "4:00–5:00\N{NO-BREAK SPACE}PM",
        "and 1\N{NO-BREAK SPACE}more",
    ]


async def test_now_in_this_room_heads_today_s_list_only(render: Render) -> None:
    """It scrolls away with today's slots, so at large text they keep the screen."""
    room = await render(highlighted(SUNDAY_TALK))  # Sunday shows; today is Saturday
    heads = [lst.controls[0] for lst in room.day_lists()]
    assert [isinstance(head, ft.Component) for head in heads] == [False, True, False]
    assert len(room.nodes("room.now")) == 1


async def test_now_in_this_room_follows_the_clock_on_the_minute_tick(
    render: Render, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Developer fake clock moves it, with no touch (D-175, D-187)."""
    monkeypatch.setattr(status_strip, "TICK_SECONDS", 0.01)
    room = await render(VIEW, now=SATURDAY_MORNING)
    assert len(room.nodes("room.now")) == 1
    clock.set_test_now(datetime(2026, 5, 16, 11, 5, tzinfo=PACIFIC))  # talk over
    await room.until(lambda: room.nodes("room.now") == [])
    clock.set_test_now(datetime(2026, 5, 16, 11, 20, tzinfo=PACIFIC))  # the next one
    await room.until(lambda: len(room.nodes("room.now")) == 1)
    tile = cast(ft.ListTile, room.node("room.now").content)
    assert cast(ft.Text, tile.title).value.startswith("Don’t Write Polars Code")


async def test_the_minute_tick_re_renders_only_now_in_this_room(
    render: Render, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A leaf component on ``use_minute()``: the day lists are not built again (D-194)."""
    monkeypatch.setattr(status_strip, "TICK_SECONDS", 0.01)
    built: list[int] = []
    original = room_days.day_list

    def counted(*args: Any, **kwargs: Any) -> ft.ListView:
        built.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(screen, "day_list", counted)  # room.py imports the name
    room = await render(VIEW, now=SATURDAY_MORNING)
    before = len(built)
    assert before == 3  # one per day
    clock.set_test_now(datetime(2026, 5, 16, 11, 5, tzinfo=PACIFIC))  # talk over
    await room.until(lambda: room.nodes("room.now") == [])
    assert len(built) == before


@pytest.mark.parametrize(
    "now",
    [
        datetime(2026, 5, 16, 11, 5, tzinfo=PACIFIC),  # between two talks
        datetime(2026, 5, 12, 12, tzinfo=PACIFIC),  # before the conference
        datetime(2026, 10, 13, 12, tzinfo=PACIFIC),  # off season
    ],
)
async def test_with_nothing_on_there_is_no_now_section(
    render: Render, now: datetime
) -> None:
    room = await render(VIEW, now=now)
    assert room.nodes("room.now") == []
    assert not any(
        isinstance(c, ft.Text) and c.value == "Now in this room"
        for c in room.session.index.values()
    )


# ------------------------------------------------------------------ not found


async def test_an_unknown_room_names_the_thing_and_offers_the_rooms(
    render: Render,
) -> None:
    room = await render("/map/room/bogus", slug="bogus")
    assert room.titles[-1] == "Not found"
    state = room.node("room.not_found")
    assert "This room isn't in the current schedule" in texts(state)
    (button,) = [
        c for c in room.session.index.values() if isinstance(c, ft.FilledTonalButton)
    ]
    assert button.content == "All rooms"
    await room.session.dispatch_event(button._i, "click", None)
    await room.settle()
    assert room.pushed == ["/map"]
