"""Tests for the Now tab (#95; SCHED-25, SCHED-26; D-14, D-179, ux.md §5.1).

What is on and what is next is ``core.agenda`` (``test_agenda.py``); here, what Now makes
of it at fixed times of the 2026 feed: the header's words in every season, the sections
each season shows, the next-session card, the elapsed bars, the minute tick and the
resume, and the states without data.

The words are pure (``season()``, ``header_copy()``, ``up_next_when()``) and run on
their own. The screen runs in a real Flet session, as the session rows' tests do
(``tests/sessions.py`` names the Flet internals the harness uses), with the
clock held by the test: Flet's scheduler re-renders what changed, so a test sees which
row bodies ran (D-153). How Now looks, wraps at 200 % and reads to TalkBack and
VoiceOver is checked on devices (the PR).
"""

import asyncio
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

import flet as ft
import pytest
from flet.components.component import Component
from flet.controls.context import _context_page
from flet.messaging.session import Session

from pycon_us import clock
from pycon_us.config import load_year
from pycon_us.core.agenda import Phase, now_next
from pycon_us.core.models import ConferenceData
from pycon_us.favorites import Favorites, FavoritesCtx
from pycon_us.prefs import Prefs, PrefsCtx
from pycon_us.screens import now as screen
from pycon_us.screens.now_header import (
    GOLD,
    HeaderCopy,
    Season,
    StatusHeader,
    header_copy,
    header_phrase,
    season,
    spoken,
    up_next_when,
)
from pycon_us.services import Services, ServicesCtx
from pycon_us.services.storage import Storage
from pycon_us.state import Conference, ConferenceCtx, ViewMemory
from pycon_us.ui import session_rows as rows
from pycon_us.ui import status_strip
from tests.fakes import (
    MemoryClipboard,
    MemoryHaptics,
    MemoryLauncher,
    MemoryPrefs,
    MemorySemantics,
)
from tests.feeds import processed
from tests.sessions import connection
from tests.test_theme import contrast_ratio

YEAR = load_year(2026)
INFO = YEAR.conference
PACIFIC = ZoneInfo("America/Los_Angeles")

TALK = "142"
"""Python for Humans, 10:30-11:00 AM on Saturday, May 16, in Grand Ballroom A."""

AT_11 = ("105", "4", "9113", "9040", "9072", "15", "102", "41", "9059", "9086")
"""What is on at 11:10 AM on Friday, May 15, in the Schedule's order: the 11:00 talks
(30 min) and open spaces (1 h)."""

OPEN_SPACE = "9086"
"""pytest for system tests, an open space at 11:00 AM on Friday: last of AT_11, and
hidden on the Schedule by default (D-20)."""

KEYNOTE = "153"
"""Lin Qiao's keynote, 9:45-10:30 AM on Friday: alone until the 10:00 open spaces."""


JOB_FAIR = "178"
"""The Job Fair & Community Showcase on Sunday: its row says 9:30 AM, its slot is the
10:00 one (DATA-11), and it ends at 1:00 PM."""


def may(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 5, day, hour, minute, tzinfo=PACIFIC)


@pytest.fixture(scope="module")
def data() -> ConferenceData:
    return processed(2026)


# ------------------------------------------------------------------ the words


def copy_at(data: ConferenceData, now: datetime, **kwargs: Any) -> tuple[str, ...]:
    """The header's season, title and subtitle at ``now``, on a Pacific device."""
    copy = header_copy(
        now_next(data, now),
        now,
        data,
        INFO,
        use_24h=kwargs.get("use_24h", False),
        device_offset=now.astimezone(PACIFIC).utcoffset(),
    )
    assert copy.note is None  # the device shows conference time
    return copy.season, copy.title, copy.subtitle


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (
            datetime(2026, 4, 20, 9, tzinfo=PACIFIC),
            (Season.COUNTDOWN, "Starts in 23 days", "May 13–19 · Long Beach, CA"),
        ),
        (
            may(12, 23, 59),
            (Season.COUNTDOWN, "Starts tomorrow", "May 13–19 · Long Beach, CA"),
        ),
        # The first morning, before its first start: already the conference.
        (
            may(13, 7),
            (
                Season.CONFERENCE,
                "Day 1 of 5 · Wednesday",
                "First up today at 7:30 AM",
            ),
        ),
        (
            may(15, 6),
            (Season.CONFERENCE, "Day 3 of 5 · Friday", "First up today at 7:30 AM"),
        ),
        (
            may(15, 11, 10),
            (Season.CONFERENCE, "Day 3 of 5 · Friday", "Long Beach Convention Center"),
        ),
        (
            may(15, 21),
            (Season.CONFERENCE, "Day 3 of 5 · Friday", "That's a wrap for today"),
        ),
        # After the last end, the last evening is still the last day.
        (
            may(17, 21),
            (Season.CONFERENCE, "Day 5 of 5 · Sunday", "That's a wrap for today"),
        ),
        (
            may(18, 10),
            (
                Season.SPRINTS,
                "Sprints · Monday",
                "The sprints run until Tuesday, May 19",
            ),
        ),
        (
            may(19, 10),
            (Season.SPRINTS, "Sprints · Tuesday", "The last day of the sprints"),
        ),
        (
            may(25, 10),
            (Season.OVER, "See you next year", "Thanks for coming."),
        ),
    ],
)
def test_the_header_says_where_the_conference_stands(
    data: ConferenceData, now: datetime, expected: tuple[str, ...], machine_tz: str
) -> None:
    assert copy_at(data, now) == expected


def test_the_seasons_follow_the_phases_and_the_year_s_dates(
    data: ConferenceData,
) -> None:
    assert season(Phase.BEFORE, may(12, 12).date(), data, INFO) is Season.COUNTDOWN
    assert season(Phase.BEFORE, may(13, 7).date(), data, INFO) is Season.CONFERENCE
    for phase in (Phase.BEFORE_DAY, Phase.DAY, Phase.AFTER_DAY):
        assert season(phase, may(15, 12).date(), data, INFO) is Season.CONFERENCE
    assert season(Phase.AFTER, may(17, 23).date(), data, INFO) is Season.CONFERENCE
    assert season(Phase.AFTER, may(18, 0).date(), data, INFO) is Season.SPRINTS
    assert season(Phase.AFTER, may(19, 23).date(), data, INFO) is Season.SPRINTS
    assert season(Phase.AFTER, may(20, 0).date(), data, INFO) is Season.OVER


def test_the_first_start_follows_the_device_s_clock_format(
    data: ConferenceData,
) -> None:
    _, _, subtitle = copy_at(data, may(15, 6), use_24h=True)
    assert subtitle == "First up today at 07:30"


def test_the_header_names_pacific_time_on_a_device_elsewhere(
    data: ConferenceData,
) -> None:
    now = may(15, 11, 10)
    kiritimati = now.astimezone(ZoneInfo("Pacific/Kiritimati")).utcoffset()
    copy = header_copy(
        now_next(data, now), now, data, INFO, use_24h=False, device_offset=kiritimati
    )
    assert copy.note == "Times are Pacific Time (PDT)"


@pytest.mark.parametrize(
    "now",
    [datetime(2026, 4, 20, 9, tzinfo=PACIFIC), may(18, 10), may(25, 10)],
    ids=["countdown", "sprints", "over"],
)
def test_the_zone_note_shows_only_in_the_season_with_times(
    data: ConferenceData, now: datetime
) -> None:
    """The countdown, the sprints and the end show dates only: no zone to name."""
    kiritimati = now.astimezone(ZoneInfo("Pacific/Kiritimati")).utcoffset()
    copy = header_copy(
        now_next(data, now), now, data, INFO, use_24h=False, device_offset=kiritimati
    )
    assert copy.season is not Season.CONFERENCE
    assert copy.note is None


def test_a_screen_reader_hears_pauses_and_ranges_in_words() -> None:
    assert spoken("Up next · 11:30 AM") == "Up next, 11:30 AM"
    assert spoken("Join a project · May 18–19") == "Join a project, May 18 to 19"
    assert spoken("Wed, May 13 – Sun, May 17") == "Wed, May 13 to Sun, May 17"


def test_the_header_reads_as_one_phrase(data: ConferenceData) -> None:
    now = datetime(2026, 4, 20, 9, tzinfo=PACIFIC)
    copy = header_copy(
        now_next(data, now),
        now,
        data,
        INFO,
        use_24h=False,
        device_offset=now.utcoffset(),
    )
    assert header_phrase(INFO.name, copy) == (
        "PyCon US 2026. Starts in 23 days. May 13 to 19, Long Beach, CA."
    )


def test_up_next_names_its_day_when_it_is_not_today(data: ConferenceData) -> None:
    def when(now: datetime) -> str:
        slot = now_next(data, now).up_next
        assert slot is not None
        return up_next_when(slot, now, INFO, use_24h=False)

    assert when(may(15, 11, 10)) == "11:30 AM"
    assert when(may(15, 21)) == "tomorrow at 7:00 AM"
    assert when(may(12, 12)) == "tomorrow at 7:30 AM"
    assert when(datetime(2026, 5, 1, 12, tzinfo=PACIFIC)) == "Wed, May 13 at 7:30 AM"


def test_gold_reads_on_the_header_s_indigo() -> None:
    """Gold is for icons on the indigo only: 6.2:1, as ux.md §3.1 computes it."""
    assert contrast_ratio(GOLD, "#3B3EA9") >= 6.0


@pytest.mark.parametrize(
    ("dark", "fill", "ink"),
    [
        (False, ft.Colors.PRIMARY, ft.Colors.ON_PRIMARY),
        # The dark primary is a pale indigo; its container is the brand's (D-190).
        (True, ft.Colors.PRIMARY_CONTAINER, ft.Colors.ON_PRIMARY_CONTAINER),
    ],
)
def test_the_header_is_the_brand_indigo_in_both_schemes(
    dark: bool, fill: ft.Colors, ink: ft.Colors
) -> None:
    copy = HeaderCopy(Season.CONFERENCE, "Day 3 of 5 · Friday", "Long Beach")
    header = StatusHeader("PyCon US 2026", copy, dark=dark)
    assert isinstance(header, ft.Semantics)
    card = header.content
    assert isinstance(card, ft.Container)
    assert card.bgcolor == fill
    texts = [c for c in _walk(card) if isinstance(c, ft.Text)]
    assert texts and all(text.color == ink for text in texts)
    (icon,) = [c for c in _walk(card) if isinstance(c, ft.Icon)]
    assert icon.color == GOLD


# ------------------------------------------------------------------ the screen


@dataclass
class Ticks:
    """Stands in for ``Services.run_every``: keeps each loop's action to call by hand."""

    actions: list[Callable[[], object]] = field(default_factory=list)

    async def run_every(self, seconds: float, action: Callable[[], object]) -> None:
        self.actions.append(action)


@dataclass
class Shown:
    """A Flet session showing ``Now``, and what it did."""

    session: Session
    svc: Services
    favorites: Favorites
    clock: list[datetime]
    ticks: Ticks
    pushed: list[str] = field(default_factory=list)
    renders: list[str] = field(default_factory=list)
    """The session ids whose row bodies ran, in order."""
    token: Any = None

    @property
    def body(self) -> ft.ListView:
        (body,) = [c for c in self.session.index.values() if isinstance(c, ft.ListView)]
        return body

    def all(self) -> list[ft.Control]:
        """Every control on screen, in reading order, components entered."""
        return list(_walk(self.body))

    def node(self, identifier: str) -> ft.Semantics:
        found = [
            c
            for c in self.all()
            if isinstance(c, ft.Semantics) and c.identifier == identifier
        ]
        assert len(found) == 1, identifier
        return found[0]

    def has(self, identifier: str) -> bool:
        return any(
            isinstance(c, ft.Semantics) and c.identifier == identifier
            for c in self.all()
        )

    def headings(self) -> list[str]:
        """The section headings (level 2) under the status header, in order."""
        return [
            _texts(c)[0]
            for c in self.all()
            if isinstance(c, ft.Semantics)
            and c.header
            and c.heading_level == 2
            and c.identifier != "now.header"
        ]

    def rows(self, prefix: str = "now.session.") -> list[str]:
        """The session rows' keys, in order: ``now.session.<key>``."""
        return [
            str(c.identifier).removeprefix(prefix)
            for c in self.all()
            if isinstance(c, ft.Semantics) and str(c.identifier).startswith(prefix)
        ]

    def texts(self) -> list[str]:
        return _texts(self.body)

    async def settle(self) -> None:
        for _ in range(20):
            await asyncio.sleep(0)

    async def click(self, control: ft.Control) -> None:
        await self.session.dispatch_event(control._i, "click", None)
        await self.settle()

    async def at(self, now: datetime) -> None:
        """Move the clock to ``now`` and run every minute tick, as a minute passing."""
        self.clock[0] = now
        for action in self.ticks.actions:
            action()
        await self.settle()


def _children(control: Any) -> list[Any]:
    if isinstance(control, Component):
        body = control._b
        return body if isinstance(body, list) else [body]
    found: list[Any] = []
    for name in ("content", "leading", "title", "subtitle", "trailing"):
        child = getattr(control, name, None)
        if isinstance(child, ft.BaseControl):
            found.append(child)
    found.extend(getattr(control, "controls", None) or ())
    return found


def _walk(control: Any) -> Iterator[Any]:
    yield control
    for child in _children(control):
        if child is not None:
            yield from _walk(child)


def _texts(control: Any) -> list[str]:
    """The texts under ``control`` in reading order, plain strings too: a ``ListTile``'s
    title, a button's label."""
    found: list[str] = []
    for c in _walk(control):
        if isinstance(c, ft.Text):
            found.append(str(c.value))
        for name in ("title", "subtitle", "content"):
            if isinstance(text := getattr(c, name, None), str):
                found.append(text)
    return found


async def show(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    now: datetime,
    *,
    conference: Conference | None = None,
    saved: tuple[str, ...] = (),
    ticks: Ticks | None = None,
) -> Shown:
    """Render Now at ``now`` in a new Flet session, with ``saved`` in My schedule."""
    prefs_service = MemoryPrefs()
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
    if conference is None:
        conference = Conference(
            data=processed(2026),
            source="bundled",
            version=1,
            fetched_at=now,  # fresh: no strip
        )
    favorites = Favorites()
    await favorites.load(storage)
    if saved:
        await favorites.add_many(storage, saved)
    held = [now]
    ticker = ticks or Ticks()
    result = Shown(Session(connection()), svc, favorites, held, ticker)

    def counted(name: str) -> Callable[..., str]:
        phrase = getattr(rows, name)

        def count(*args: Any, **kwargs: Any) -> str:
            result.renders.append(args[-1].session.id)
            return phrase(*args, **kwargs)

        return count

    monkeypatch.setattr(rows, "spoken_phrase", counted("spoken_phrase"))
    monkeypatch.setattr(rows, "notice_phrase", counted("notice_phrase"))
    monkeypatch.setattr(clock, "now", lambda: held[0])
    monkeypatch.setattr(ft, "use_view_path", lambda: "/now")
    # The scaffold and the strip are tested on their own (test_scaffold.py,
    # test_status_strip.py); here the screen's body. A real strip would also start
    # refreshes: the network.
    monkeypatch.setattr(screen, "AppScaffold", lambda **kwargs: kwargs["body"])
    if screen.StatusStrip is status_strip.StatusStrip:
        monkeypatch.setattr(screen, "StatusStrip", lambda **_: ft.Text("strip"))
    if ticks is None:
        monkeypatch.setattr(Services, "run_every", ticker.run_every)

    @ft.component
    def Root() -> ft.Control:
        return ServicesCtx(
            svc,
            lambda: ConferenceCtx(
                conference,
                lambda: PrefsCtx(
                    Prefs(loaded=True), lambda: FavoritesCtx(favorites, screen.Now)
                ),
            ),
        )

    page = result.session.page
    monkeypatch.setattr(page, "navigate", result.pushed.append)
    result.token = _context_page.set(page)  # pyright: ignore[reportArgumentType]
    page.render(Root)
    result.session.get_page_patch()
    await result.settle()
    return result


async def close(shown: Shown) -> None:
    shown.svc.close()  # real ticking loops end with the session (D-147)
    shown.session.close()
    await shown.settle()
    # Set, not reset: a test's renders run in its own context, not the fixture's.
    _context_page.set(None)  # pyright: ignore[reportArgumentType]


@pytest.fixture
async def render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Callable[..., Any]]:
    """Render Now at a time; every session shown is closed at the end."""
    shown: list[Shown] = []

    async def render(now: datetime, **kwargs: Any) -> Shown:
        result = await show(tmp_path, monkeypatch, now, **kwargs)
        shown.append(result)
        return result

    yield render
    for result in shown:
        await close(result)


def header(shown: Shown) -> str:
    return str(shown.node("now.header").label)


async def test_before_the_conference_it_counts_down_and_lists_the_key_dates(
    render: Callable[..., Any],
) -> None:
    shown = await render(datetime(2026, 4, 20, 9, tzinfo=PACIFIC))
    assert header(shown).startswith("PyCon US 2026. Starts in 23 days.")
    assert shown.headings() == ["Key dates"]
    texts = shown.texts()
    for line in (
        "Tutorials and talks",
        "Wed, May 13 – Sun, May 17",
        "Sprints",
        "Mon, May 18 – Tue, May 19",
        "Long Beach Convention Center",
        "Long Beach, CA",
    ):
        assert line in texts
    assert shown.rows() == []  # nothing is on or next for weeks
    button = shown.node("now.build_schedule").content
    assert isinstance(button, ft.FilledTonalButton)
    await shown.click(button)
    assert shown.pushed == ["/schedule"]


async def test_the_header_is_the_first_heading_under_the_page_s_title(
    render: Callable[..., Any],
) -> None:
    shown = await render(may(15, 11, 10))
    node = shown.node("now.header")
    # Level 2: the bar's "Now" is the page's one level-1 heading (F40, D-211).
    assert node.header is True and node.heading_level == 2
    assert node.exclude_semantics is True  # read once, as its phrase
    assert shown.body.controls[0] is node


async def test_on_a_conference_day_it_shows_what_is_on_then_what_is_next(
    render: Callable[..., Any],
) -> None:
    shown = await render(may(15, 11, 10))
    assert shown.headings() == [
        "Your next session",
        "Happening now",
        "Up next · 11:30 AM",
    ]
    assert shown.rows() == [*AT_11, "27"]
    assert "Starts in 20 min" in shown.texts()
    assert "See the rest of today in Schedule" in shown.texts()


async def test_up_next_s_heading_reads_its_dot_as_a_pause(
    render: Callable[..., Any],
) -> None:
    shown = await render(may(15, 11, 10))
    (heading,) = [
        c
        for c in shown.all()
        if isinstance(c, ft.Text) and c.value == "Up next · 11:30 AM"
    ]
    assert heading.semantics_label == "Up next, 11:30 AM"


async def test_happening_now_ignores_the_schedule_s_filters(
    render: Callable[..., Any],
) -> None:
    """Open spaces are hidden on the Schedule by default (D-20), never here."""
    shown = await render(may(15, 11, 10))
    assert "Open Space" in Prefs().excluded_tracks
    assert OPEN_SPACE in shown.rows()


async def test_saved_sessions_come_first_in_happening_now(
    render: Callable[..., Any],
) -> None:
    shown = await render(may(15, 11, 10), saved=(OPEN_SPACE, "9072"))
    (mine,) = shown.rows("now.next.session.")  # one of the two, in the card
    (other,) = {OPEN_SPACE, "9072"} - {mine}
    happening = shown.rows()[: len(AT_11) - 1]
    assert happening == [other, *(i for i in AT_11 if i not in (mine, other))]


async def test_each_session_on_shows_and_says_how_much_has_passed(
    render: Callable[..., Any],
) -> None:
    shown = await render(may(15, 11, 10))
    talk = shown.node("now.session.4")  # 11:00-11:30: 10 of 30 minutes
    assert str(talk.label).endswith(" 33 percent elapsed.")
    bars = [c for c in _walk(talk) if isinstance(c, ft.ProgressBar)]
    assert [bar.value for bar in bars] == [0.33]
    assert bars[0].bar_height == 3
    open_space = shown.node(f"now.session.{OPEN_SPACE}")  # 11:00-12:00
    assert str(open_space.label).endswith(" 16 percent elapsed.")
    # Up next has not started: no bar.
    up_next = shown.node("now.session.27")
    assert not [c for c in _walk(up_next) if isinstance(c, ft.ProgressBar)]
    assert "elapsed" not in str(up_next.label)


async def test_between_two_slots_it_says_nothing_is_on(
    render: Callable[..., Any],
) -> None:
    shown = await render(may(15, 7, 45))  # registration opened at 7:30 (a notice)
    assert shown.headings() == [
        "Your next session",
        "Happening now",
        "Up next · 8:00 AM",
    ]
    assert "Nothing in session right now" in shown.texts()


async def test_before_a_day_starts_it_shows_what_is_first_up(
    render: Callable[..., Any],
) -> None:
    shown = await render(may(15, 6))
    assert "First up today at 7:30 AM" in header(shown)
    assert shown.headings() == ["Your next session", "Up next · 7:30 AM"]


async def test_after_a_day_it_wraps_up_and_points_at_tomorrow(
    render: Callable[..., Any],
) -> None:
    shown = await render(may(15, 21))
    assert "That's a wrap for today" in header(shown)
    assert shown.headings() == ["Your next session", "Up next · tomorrow at 7:00 AM"]
    # The Schedule opens on today: the link does not promise tomorrow.
    assert "Open the schedule" in shown.texts()
    assert "See the rest of today in Schedule" not in shown.texts()


async def test_in_the_evening_saved_sessions_are_for_a_later_day(
    render: Callable[..., Any],
) -> None:
    """At 9 PM "nothing in the next 3 hours" is true but odd: the day is over."""
    shown = await render(may(15, 21), saved=(TALK,))  # tomorrow morning
    tile = shown.node("now.next_session")
    assert _texts(tile)[:2] == [
        "Nothing more saved for today",
        "See your saved sessions in My schedule",
    ]


async def test_after_the_last_session_the_sprints_are_next(
    render: Callable[..., Any],
) -> None:
    for now in (may(17, 21), may(18, 10)):
        shown = await render(now)
        assert shown.headings() == []
        assert shown.rows() == []
        sprints = shown.node("now.sprints")
        assert _texts(sprints) == ["Sprints", "Join a project · May 18–19"]
        (subtitle,) = [c for c in _walk(sprints) if isinstance(c, ft.Text)]
        assert subtitle.semantics_label == "Join a project, May 18 to 19"


async def test_in_the_last_slot_of_the_conference_the_schedule_is_still_linked(
    render: Callable[..., Any], data: ConferenceData
) -> None:
    """Without Sunday's 8 PM notice, the 5:05 PM Closing is the last slot: no Up next,
    but the day still runs, so the card's tile and the Schedule link stay."""
    sunday = data.days[-1]
    trimmed = replace(
        data, days=(*data.days[:-1], replace(sunday, groups=sunday.groups[:-1]))
    )
    now = may(17, 17, 10)
    assert now_next(trimmed, now).phase is Phase.DAY
    assert now_next(trimmed, now).up_next is None
    conference = Conference(data=trimmed, source="bundled", version=1, fetched_at=now)
    shown = await render(now, conference=conference)
    assert shown.headings() == ["Your next session", "Happening now"]
    assert _texts(shown.node("now.next_session"))[0] == "Nothing saved yet"
    assert "See the rest of today in Schedule" in shown.texts()


async def test_after_the_sprints_it_says_see_you_next_year(
    render: Callable[..., Any],
) -> None:
    shown = await render(may(25, 10))
    assert header(shown).startswith("PyCon US 2026. See you next year.")
    assert not shown.has("now.sprints")
    assert _texts(shown.node("now.schedule")) == ["Look back at the schedule"]


# ------------------------------------------------------------------ your next session


async def test_your_next_session_is_the_saved_one_due_with_its_star_and_room(
    render: Callable[..., Any],
) -> None:
    shown = await render(may(16, 9), saved=(TALK,))  # it starts in 1 h 30 min
    (card,) = [c for c in shown.all() if isinstance(c, ft.Card)]
    assert shown.rows("now.next.session.") == [TALK]
    assert not shown.has("now.next_session")  # the tile's: nothing to explain
    assert any(
        isinstance(c, ft.Semantics) and c.identifier == f"now.next.favorite.{TALK}"
        for c in _walk(card)
    )
    assert "Starts in 1 h 30 min" in _texts(card)
    # Not on yet: no bar.
    assert not [c for c in _walk(card) if isinstance(c, ft.ProgressBar)]
    show_room = shown.node("now.show_room").content
    assert isinstance(show_room, ft.TextButton)
    await shown.click(show_room)
    assert shown.pushed == [f"/now/room/grand-ballroom-a?highlight={TALK}"]


async def test_the_card_s_status_is_a_stop_of_its_own(
    render: Callable[..., Any],
) -> None:
    """Row, status, star and "Show room": four stops (ux.md §5.1)."""
    shown = await render(may(16, 9), saved=(TALK,))
    (card,) = [c for c in shown.all() if isinstance(c, ft.Card)]
    (status,) = [
        c
        for c in _walk(card)
        if isinstance(c, ft.Text) and c.value == "Starts in 1 h 30 min"
    ]
    assert status.semantics_label == "Starts in 1 hour 30 minutes"
    # Not in the row's merged node: the row's phrase does not say it.
    assert "Starts in" not in str(shown.node(f"now.next.session.{TALK}").label)
    # At large text "Show room" moves under the status whole.
    (actions,) = [
        c for c in _walk(card) if isinstance(c, ft.Row) and status in _walk(c)
    ][-1:]
    assert actions.wrap is True
    # Stretched across the card, so the button sits at its end on one line.
    assert actions.alignment == ft.MainAxisAlignment.SPACE_BETWEEN
    (column,) = [c for c in _walk(card) if isinstance(c, ft.Column)][:1]
    assert column.horizontal_alignment == ft.CrossAxisAlignment.STRETCH


async def test_your_session_on_is_in_the_card_with_its_bar_not_twice(
    render: Callable[..., Any],
) -> None:
    shown = await render(may(15, 11, 10), saved=(OPEN_SPACE,))
    assert shown.rows("now.next.session.") == [OPEN_SPACE]
    card = shown.node(f"now.next.session.{OPEN_SPACE}")
    assert str(card.label).endswith(" 16 percent elapsed.")
    assert [c.value for c in _walk(card) if isinstance(c, ft.ProgressBar)] == [0.16]
    assert shown.rows()[: len(AT_11) - 1] == [i for i in AT_11 if i != OPEN_SPACE]


async def test_your_next_session_is_not_repeated_in_up_next(
    render: Callable[..., Any],
) -> None:
    """The 11:30 talk is alone in its slot: the card says when, Up next is left out."""
    shown = await render(may(15, 11, 10), saved=("27",))
    assert shown.rows("now.next.session.") == ["27"]
    assert "27" not in shown.rows()
    assert shown.texts().count("Starts in 20 min") == 1  # the card's status
    assert shown.headings() == ["Your next session", "Happening now"]
    assert "See the rest of today in Schedule" in shown.texts()


async def test_up_next_lists_the_rest_of_its_slot_but_your_session(
    render: Callable[..., Any],
) -> None:
    shown = await render(may(15, 10, 50), saved=("4",))
    assert shown.rows("now.next.session.") == ["4"]
    assert "Up next · 11:00 AM" in shown.headings()
    assert shown.rows()[-(len(AT_11) - 1) :] == [i for i in AT_11 if i != "4"]


async def test_the_card_s_bar_follows_the_time_its_row_shows(
    render: Callable[..., Any],
) -> None:
    """The Job Fair shows 9:30 though its slot is 10:00 (DATA-11): on from 9:30 (D-186)."""
    shown = await render(may(17, 9, 45), saved=(JOB_FAIR,))
    card = shown.node(f"now.next.session.{JOB_FAIR}")
    assert str(card.label).endswith(" 7 percent elapsed.")
    assert [c.value for c in _walk(card) if isinstance(c, ft.ProgressBar)] == [0.07]


async def test_when_only_your_session_is_on_the_card_says_so(
    render: Callable[..., Any],
) -> None:
    """A keynote is alone in its slot: no Happening now section to say "nothing"."""
    shown = await render(may(15, 9, 50), saved=(KEYNOTE,))
    assert shown.rows("now.next.session.") == [KEYNOTE]
    assert "Happening now" not in shown.headings()
    assert "Nothing in session right now" not in shown.texts()
    (card,) = [c for c in shown.all() if isinstance(c, ft.Card)]
    assert "Happening now" in _texts(card)  # the card's status says it


async def test_with_nothing_saved_it_says_how_to_save_a_session(
    render: Callable[..., Any],
) -> None:
    shown = await render(may(16, 9))
    tile = shown.node("now.next_session")
    assert _texts(tile)[:2] == [
        "Nothing saved yet",
        "Tap the star on a session, and your next one shows here",
    ]


async def test_with_nothing_saved_soon_it_points_at_my_schedule(
    render: Callable[..., Any],
) -> None:
    shown = await render(may(15, 9), saved=(TALK,))  # tomorrow
    tile = shown.node("now.next_session")
    assert _texts(tile)[0] == "Nothing saved for the next 3 hours"
    (list_tile,) = [c for c in _walk(tile) if isinstance(c, ft.ListTile)]
    assert list_tile.on_click is not None
    cast(Callable[[], None], list_tile.on_click)()
    assert shown.pushed == ["/my-schedule"]


async def test_a_row_pushes_its_session_over_now(
    render: Callable[..., Any],
) -> None:
    """Back from the detail pops to Now (D-17): the detail is pushed on /now."""
    shown = await render(may(15, 11, 10))
    tappable = shown.node("now.session.4").parent
    assert isinstance(tappable, ft.Container)
    await shown.click(tappable)
    assert shown.pushed == ["/now/session/4"]


# ------------------------------------------------------------------ time passing


async def test_a_minute_moves_the_bars_and_re_renders_only_their_rows(
    render: Callable[..., Any],
) -> None:
    shown = await render(may(15, 11, 10))
    shown.renders.clear()
    await shown.at(may(15, 11, 11))
    assert str(shown.node("now.session.4").label).endswith(" 36 percent elapsed.")
    assert "27" not in shown.renders  # Up next did not change (D-153)
    assert "4" in shown.renders


async def test_the_minute_tick_turns_the_day_into_its_evening(
    render: Callable[..., Any],
) -> None:
    shown = await render(may(15, 19, 59))
    await shown.at(may(15, 21))
    assert "That's a wrap for today" in header(shown)


async def test_a_resume_recomputes_at_once(
    render: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """In the background nothing ticks; the return catches up at once (D-40, D-175)."""
    monkeypatch.setattr(status_strip, "TICK_SECONDS", 0.01)
    shown = await render(may(15, 11, 10), ticks=Ticks())  # the real loop
    shown.svc.foreground.clear()  # pause
    shown.clock[0] = may(15, 21)
    await asyncio.sleep(0.05)
    await shown.settle()
    assert "Long Beach Convention Center" in header(shown)  # still the morning
    shown.svc.foreground.set()  # resume
    await asyncio.sleep(0)
    await shown.settle()
    assert "That's a wrap for today" in header(shown)


async def test_the_strip_refreshes_the_feed_while_now_shows(
    render: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    strips: list[bool] = []

    def strip(*, auto_refresh: bool = False) -> ft.Control:
        strips.append(auto_refresh)
        return ft.Text("strip")

    monkeypatch.setattr(screen, "StatusStrip", strip)
    shown = await render(may(15, 11, 10))
    assert strips and all(strips)  # the 15-min refresh runs here (D-175)
    assert shown.body.controls[1] is not None


# ------------------------------------------------------------------ without data


async def test_without_data_it_shows_the_skeleton_until_the_first_fetch_fails(
    render: Callable[..., Any],
) -> None:
    loading = await render(may(15, 11, 10), conference=Conference())
    assert any(
        isinstance(c, ft.Semantics) and c.label == "Loading schedule"
        for c in loading.all()
    )
    failed = await render(may(15, 11, 10), conference=Conference(problem="offline"))
    state = failed.node("now.no_data")
    assert "Can't load the schedule" in _texts(state)
    assert "Connect to the internet and try again." in _texts(state)
