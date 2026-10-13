"""Tests for session detail (SESS-01..03; ux.md §5.5): header, When and where, the star.

``SessionDetail`` runs in a real Flet session, as the rows do in ``test_session_rows.py``:
the store providers are written out above it, ``AppScaffold`` is replaced by a column
that keeps the title, the actions and the body, and taps are dispatched clicks. The
sessions are the recorded 2026 feed's. How the screen looks, at 200 % text and in dark
mode, is checked on devices (the PR); here, what it says and what a tap does.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, cast
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
from pycon_us.prefs import Prefs, PrefsCtx
from pycon_us.screens import session as screen
from pycon_us.services import Services, ServicesCtx
from pycon_us.services.storage import Storage
from pycon_us.state import Conference, ConferenceCtx, ViewMemory
from pycon_us.theme import LIGHT_TOKENS, TokensCtx
from pycon_us.ui.badges import REMOVED, UNDO
from tests.fakes import (
    MemoryClipboard,
    MemoryHaptics,
    MemoryLauncher,
    MemoryPrefs,
    MemorySemantics,
)
from tests.feeds import processed
from tests.trees import descendants, texts

YEAR = load_year(2026)
PACIFIC = ZoneInfo("America/Los_Angeles")
VIEW = "/schedule/session/x"
"""The View path the screen is rendered at: links push on top of it."""

TALK = "142"
"""Python for Humans, Sat May 16 10:30-11:00 AM, Grand Ballroom A; a public page."""

TUTORIAL = "19"
"""A tutorial: registration required."""

LIGHTNING = "175"
"""Lightning talks: shown in the Arena, streamed to four rooms (D-124)."""

KEYNOTE = "176"
"""A keynote: no public page in the feed."""

BREAK = (
    "break-Room 103ABC, Room 104AB, Room 104C, Grand Ballroom A, Grand Ballroom B"
    "-2026-05-16T10:05:00-07:00"
)
"""A break in five rooms with no one place to show (DATA-16)."""


@dataclass
class Detail:
    """A Flet session showing one ``SessionDetail``."""

    session: Session
    conference: Conference
    favorites: Favorites
    launcher: MemoryLauncher
    pushed: list[str]
    titles: list[str]

    def nodes(self, identifier: str) -> list[ft.Semantics]:
        return [
            c
            for c in self.session.index.values()
            if isinstance(c, ft.Semantics) and c.identifier == identifier
        ]

    def node(self, identifier: str) -> ft.Semantics:
        (found,) = self.nodes(identifier)
        return found

    def text(self, identifier: str) -> list[str]:
        return words(self.node(identifier))

    async def settle(self) -> None:
        for _ in range(20):
            await asyncio.sleep(0)

    async def click(self, control: ft.Control) -> None:
        await self.session.dispatch_event(control._i, "click", None)
        await self.settle()

    @property
    def snack_bars(self) -> list[ft.SnackBar]:
        return [
            d for d in self.session.page._dialogs.controls if isinstance(d, ft.SnackBar)
        ]


type Render = Callable[[str], Awaitable[Detail]]


@pytest.fixture
async def render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Render]:
    """Return render(session_id): the detail of that session at ``VIEW``."""
    shown: list[tuple[Session, Services]] = []
    titles: list[str] = []

    def scaffold(
        *, title: str, body: ft.Control, actions: list[ft.Control] | None = None
    ) -> ft.Control:
        titles.append(title)
        return ft.Column([ft.Row(actions or []), body])

    monkeypatch.setattr(screen, "AppScaffold", scaffold)
    monkeypatch.setattr(ft, "use_view_path", lambda: VIEW)

    async def show(session_id: str) -> Detail:
        storage = Storage(prefs=MemoryPrefs(), directory=tmp_path, year=2026)
        launcher = MemoryLauncher()
        svc = Services(
            year=YEAR,
            storage=storage,
            memory=ViewMemory(),
            semantics=MemorySemantics(),
            haptics=MemoryHaptics(),
            launcher=launcher,
            clipboard=MemoryClipboard(),
        )
        conference = Conference(data=processed(2026), source="bundled", version=1)
        favorites, prefs = Favorites(), Prefs(loaded=True)
        await favorites.load(storage)

        @ft.component
        def Root() -> ft.Control:
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
                                lambda: screen.SessionDetail(session_id),
                            ),
                        ),
                    ),
                ),
            )

        flet_session = Session(_connection())
        page = flet_session.page
        pushed: list[str] = []
        monkeypatch.setattr(page, "navigate", pushed.append)
        # Bound as Flet binds it while a handler runs; the test runs in a context of
        # its own (a task), so the binding goes with it.
        _context_page.set(page)  # pyright: ignore[reportArgumentType]
        shown.append((flet_session, svc))
        page.render(Root)
        flet_session.get_page_patch()
        detail = Detail(flet_session, conference, favorites, launcher, pushed, titles)
        await detail.settle()
        return detail

    try:
        yield show
    finally:
        for flet_session, svc in shown:
            svc.close()  # the status line's ticks end (D-147)
            flet_session.close()
        await asyncio.sleep(0)
        clock.set_test_now(None)


def _connection() -> Connection:
    """A connection to no client, as Flet's own component tests use."""
    conn = Connection()
    conn.pubsubhub = PubSubHub()
    conn.send_message = lambda message: None  # pyright: ignore[reportAttributeAccessIssue]
    return conn


def words(control: ft.Control) -> list[str]:
    """The visible text under ``control`` in reading order, components and tiles included.

    Unlike ``trees.texts``, it reads a ``ListTile``'s string title and what a component
    (the status line) rendered.
    """
    found: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, ft.Control) and node.visible is False:
            return
        if isinstance(node, ft.Text):
            found.append(str(node.value))
        if isinstance(node, str):
            found.append(node)
            return
        if isinstance(node, ft.Component):
            body = node._b
            for child in body if isinstance(body, list) else [body]:
                walk(child)
        for name in ("content", "leading", "title", "subtitle", "trailing"):
            child = getattr(node, name, None)
            if isinstance(child, (ft.Control, str)) and not isinstance(node, ft.Text):
                walk(child)
        for child in getattr(node, "controls", None) or ():
            walk(child)

    walk(control)
    return found


def at(text: str) -> datetime:
    """An instant in conference time, e.g. ``at("2026-05-16 10:05")``."""
    return datetime.fromisoformat(text).replace(tzinfo=PACIFIC)


# ------------------------------------------------------------------ header (SESS-01)


async def test_the_title_is_the_page_s_selectable_heading(render: Render) -> None:
    detail = await render(TALK)
    title = detail.node("session.title")
    assert (title.header, title.heading_level) == (True, 1)
    text = cast(ft.Text, title.content)
    assert text.value.startswith("Python for Humans")  # pyright: ignore[reportOptionalMemberAccess]
    assert (text.theme_style, text.selectable) == (
        ft.TextThemeStyle.HEADLINE_SMALL,
        True,
    )
    assert detail.titles[-1] == ""  # the heading names the page, not the app bar


async def test_the_badges_come_before_the_title(render: Render) -> None:
    detail = await render(TUTORIAL)
    header = detail.node("session.title").parent
    assert isinstance(header, ft.Column)
    badges = header.controls[0]
    assert isinstance(badges, ft.Row) and badges.wrap
    assert texts(badges) == ["Tutorial", "Registration required"]


# ------------------------------------------------------------------ when (SESS-01)


@pytest.mark.parametrize(
    ("now", "label", "spoken"),
    [
        ("2026-05-16 10:05", "Starts in 25 min", "Starts in 25 minutes"),
        ("2026-05-16 08:25", "Starts in 2 h 5 min", "Starts in 2 hours 5 minutes"),
        ("2026-05-16 10:30", "Happening now", "Happening now"),
        ("2026-05-16 10:59", "Happening now", "Happening now"),
        ("2026-05-16 11:00", "Ended", "Ended"),  # at the end it is over (D-179)
        ("2026-05-18 09:00", "Ended", "Ended"),
    ],
)
async def test_the_time_tile_says_where_the_session_stands(
    render: Render, now: str, label: str, spoken: str
) -> None:
    clock.set_test_now(at(now))
    detail = await render(TALK)
    status = [
        node
        for node in detail.session.index.values()
        if isinstance(node, ft.Text) and node.value == label
    ]
    assert [node.semantics_label for node in status] == [spoken]
    assert label in detail.text("session.when")


async def test_the_day_before_there_is_no_countdown(render: Render) -> None:
    clock.set_test_now(at("2026-05-15 18:00"))
    detail = await render(TALK)
    lines = detail.text("session.when")
    # The date says when; the range never breaks inside (no-break space, word joiner).
    assert lines[0] == "Saturday, May 16 · 10:30–\u206011:00\u00a0AM"
    assert not any(line.startswith("Starts") for line in lines)
    title = next(
        t for t in descendants(detail.node("session.when")) if isinstance(t, ft.Text)
    )
    assert title.semantics_label == "Saturday, May 16, 10:30 to 11:00 AM"


async def test_the_status_follows_the_clock_on_the_minute_tick(
    render: Render, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-40: the line re-renders itself as time passes, under the fake clock too."""
    clock.set_test_now(at("2026-05-16 10:29"))
    ticks: list[Callable[[], object]] = []

    async def run_every(self: Services, seconds: float, action: Callable[[], object]):
        ticks.append(action)
        action()

    monkeypatch.setattr(Services, "run_every", run_every)
    detail = await render(TALK)
    assert "Starts in 1 min" in detail.text("session.when")
    clock.set_test_now(at("2026-05-16 10:31"))
    (tick,) = ticks
    tick()
    await detail.settle()
    assert "Happening now" in detail.text("session.when")


async def test_a_device_in_another_zone_gets_the_pacific_time_note(
    render: Render, machine_tz: str
) -> None:
    """D-35: say the times are conference time when the device's clock differs."""
    detail = await render(TALK)
    note = "Times are Pacific Time (PDT)"
    expected = machine_tz != "America/Los_Angeles"
    assert (note in detail.text("session.when")) is expected


# ------------------------------------------------------------------ where (SESS-02)


async def test_the_room_tile_pushes_the_room_with_the_session_highlighted(
    render: Render,
) -> None:
    detail = await render(TALK)
    room = detail.node("session.room")
    assert words(room) == ["Grand Ballroom A"]
    tile = next(n for n in descendants(room) if isinstance(n, ft.ListTile))
    await detail.click(tile)
    assert detail.pushed == [f"{VIEW}/room/grand-ballroom-a?highlight={TALK}"]
    assert detail.nodes("session.other_rooms") == []  # one room, nothing folded


async def test_a_streamed_session_folds_its_other_rooms(render: Render) -> None:
    detail = await render(LIGHTNING)
    assert words(detail.node("session.room")) == ["Pacific Ballroom - Arena"]
    folded = detail.node("session.other_rooms").content
    assert isinstance(folded, ft.ExpansionTile)
    assert cast(ft.Text, folded.title).value == "+4 more rooms"
    rooms = folded.controls or []
    assert [words(room) for room in rooms] == [
        ["Room 103ABC"],
        ["Room 104AB"],
        ["Grand Ballroom A"],
        ["Grand Ballroom B"],
    ]
    tile = next(n for n in descendants(rooms[0]) if isinstance(n, ft.ListTile))
    await detail.click(tile)
    assert detail.pushed == [f"{VIEW}/room/room-103abc?highlight={LIGHTNING}"]


async def test_a_break_in_many_rooms_lists_them_without_one_place(
    render: Render,
) -> None:
    detail = await render(BREAK)
    assert detail.nodes("session.room") == []
    folded = cast(ft.ExpansionTile, detail.node("session.other_rooms").content)
    assert cast(ft.Text, folded.title).value == "In 5 rooms"


async def test_reduced_motion_opens_the_rooms_without_animation(
    render: Render, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Prefs, "motion_ms", lambda self, ms: 0)
    detail = await render(LIGHTNING)
    folded = cast(ft.ExpansionTile, detail.node("session.other_rooms").content)
    assert cast(ft.AnimationStyle, folded.animation_style).duration == 0


# ------------------------------------------------------------------ registration


async def test_a_tutorial_says_it_needs_registration_and_links_the_dashboard(
    render: Render,
) -> None:
    detail = await render(TUTORIAL)
    assert detail.text("session.registration") == [
        "Registration required",
        screen.REGISTRATION_TEXT,
    ]
    link = detail.node("session.registration.link")
    tile = next(n for n in descendants(link) if isinstance(n, ft.ListTile))
    await detail.click(tile)
    assert detail.launcher.launched == [
        (YEAR.conference.registration_url, ft.LaunchMode.IN_APP_BROWSER_VIEW)
    ]


async def test_a_talk_needs_no_registration_card(render: Render) -> None:
    detail = await render(TALK)
    assert detail.nodes("session.registration") == []


# ------------------------------------------------------------------ app bar (SESS-03)


async def test_the_star_saves_and_undo_brings_it_back(render: Render) -> None:
    detail = await render(TALK)
    star = cast(ft.IconButton, detail.node("session.favorite").content)
    await detail.click(star)
    assert detail.favorites.ids == {TALK}
    star = cast(ft.IconButton, detail.node("session.favorite").content)
    assert star.icon == ft.Icons.STAR
    await detail.click(star)
    (snack,) = detail.snack_bars
    assert cast(ft.Text, snack.content).value == REMOVED
    action = cast(ft.SnackBarAction, snack.action)
    assert action.label == UNDO
    await cast(Callable[[], Any], action.on_click)()
    await detail.settle()
    assert detail.favorites.ids == {TALK}


async def test_the_overflow_opens_the_public_page(render: Render) -> None:
    detail = await render(TALK)
    menu = cast(ft.PopupMenuButton, detail.node("session.overflow").content)
    assert menu.tooltip == "More options"
    (item,) = menu.items
    assert item.content == "Open on us.pycon.org"
    await detail.click(item)
    assert detail.launcher.launched == [
        (
            "https://us.pycon.org/2026/schedule/presentation/142/",
            ft.LaunchMode.IN_APP_BROWSER_VIEW,
        )
    ]


async def test_a_break_has_no_star_as_its_row_has_none(render: Render) -> None:
    """D-31: breaks and notices are not saved to My schedule."""
    detail = await render(BREAK)
    assert detail.nodes("session.favorite") == []


async def test_a_session_without_a_public_page_has_no_overflow(render: Render) -> None:
    """D-60: no dead controls; Add to calendar joins the menu in P2."""
    detail = await render(KEYNOTE)
    assert detail.nodes("session.overflow") == []
    assert detail.nodes("session.favorite")  # the star is always there


# ------------------------------------------------------------------ states


async def test_an_unknown_id_names_the_session_and_offers_the_schedule(
    render: Render,
) -> None:
    detail = await render("no-such-session")
    assert detail.text("session.not_found") == [screen.NOT_FOUND]
    button = next(
        n for n in detail.session.index.values() if isinstance(n, ft.FilledTonalButton)
    )
    assert button.content == "Open schedule"
    await detail.click(button)
    assert detail.pushed == ["/schedule"]
    assert detail.nodes("session.favorite") == []


async def test_a_session_a_refresh_drops_keeps_its_content_under_a_note(
    render: Render,
) -> None:
    detail = await render(TALK)
    assert detail.nodes("session.removed") == []
    data = cast(ConferenceData, detail.conference.data)
    newer = replace(
        data, sessions={k: v for k, v in data.sessions.items() if k != TALK}
    )
    detail.conference.data, detail.conference.version = newer, 2
    await detail.settle()
    note = detail.node("session.removed")
    assert note.live_region  # announced: it appears while the page is open
    assert words(note)[0] == screen.REMOVED
    assert detail.nodes("session.title")  # the content stays
    assert detail.nodes("session.favorite")  # and the star still works
