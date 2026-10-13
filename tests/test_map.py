"""Tests for the Map tab's rooms list (#100; ROOM-01, D-188, ux.md §5.8).

``Map`` runs outside a renderer: its hooks and ``AppScaffold`` are replaced, and a fake
page is bound as Flet binds a session's page. What is on in a room is
``core.rooms.room_list`` (``test_rooms.py``); here, what the screen makes of it, its
states without data, and where a tap goes. How the list looks and reads is checked on
devices (the PR).
"""

import inspect
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from zoneinfo import ZoneInfo

import flet as ft
import pytest

from pycon_us import clock
from pycon_us.config import load_year
from pycon_us.core.models import ConferenceData
from pycon_us.locations import PAGES, drill_href
from pycon_us.screens import map as map_screen
from pycon_us.screens.map import Map, now_lines, room_row
from pycon_us.services import Services
from pycon_us.services.storage import Storage
from pycon_us.state import ViewMemory
from pycon_us.theme import LIGHT_TOKENS
from tests.fakes import (
    FakePage,
    MemoryClipboard,
    MemoryHaptics,
    MemoryLauncher,
    MemoryPrefs,
    MemorySemantics,
    bound,
)
from tests.feeds import processed
from tests.trees import descendants, texts

STRIP = ft.Text("strip")
"""What the test's ``StatusStrip`` stands in for."""

PACIFIC = ZoneInfo("America/Los_Angeles")
DURING = datetime(2026, 5, 15, 11, 10, tzinfo=PACIFIC)  # a talk in Room 103ABC
BEFORE = datetime(2026, 5, 12, 12, tzinfo=PACIFIC)


@pytest.fixture(scope="module")
def data() -> ConferenceData:
    return processed(2026)


@pytest.fixture
def page() -> Iterator[FakePage]:
    fake = FakePage()
    with bound(fake):
        yield fake


@pytest.fixture
def svc(tmp_path: Path) -> Services:
    storage = Storage(prefs=MemoryPrefs(), directory=tmp_path, year=2026)
    return Services(
        year=load_year(2026),
        storage=storage,
        memory=ViewMemory(),
        semantics=MemorySemantics(),
        haptics=MemoryHaptics(),
        launcher=MemoryLauncher(),
        clipboard=MemoryClipboard(),
    )


class FakeConference(SimpleNamespace):
    """The parts of ``Conference`` the Map reads, and its refresh, recorded."""

    def __init__(self, data: ConferenceData | None, problem: str | None = None):
        super().__init__(data=data, problem=problem, refreshing=False, refreshes=0)

    async def refresh(self, *args: object, **kwargs: object) -> None:
        self.refreshes += 1


async def retap() -> None:
    """The root's re-tap action, as ``use_scroll_to_top()`` would return it."""


@pytest.fixture
def minutes() -> list[int]:
    """The ``use_minute()`` calls: one per render."""
    return []


@pytest.fixture
def render(
    monkeypatch: pytest.MonkeyPatch,
    svc: Services,
    page: FakePage,
    minutes: list[int],
) -> Callable[..., dict[str, Any]]:
    """Render ``Map`` once at ``now`` and return what it passed to ``AppScaffold``."""
    monkeypatch.setattr(map_screen, "use_scroll_to_top", lambda: (ft.Ref(), retap))
    monkeypatch.setattr(map_screen, "use_services", lambda: svc)
    monkeypatch.setattr(map_screen, "use_tokens", lambda: LIGHT_TOKENS)
    monkeypatch.setattr(map_screen, "use_minute", lambda: minutes.append(0) or 0)
    monkeypatch.setattr(map_screen, "AppScaffold", lambda **kwargs: kwargs)
    # Stand-ins for the components, which need a renderer; their own tests check them.
    monkeypatch.setattr(map_screen, "StatusStrip", lambda: STRIP)
    monkeypatch.setattr(map_screen, "SkeletonList", lambda label: ft.Text(label))
    monkeypatch.setattr(ft, "use_view_path", lambda: "/map")

    def render(conference: FakeConference, now: datetime = DURING) -> dict[str, Any]:
        monkeypatch.setattr(map_screen, "use_conference", lambda: conference)
        monkeypatch.setattr(clock, "now", lambda: now)
        return cast(dict[str, Any], inspect.unwrap(Map)())

    return render


def rows_of(scaffold: dict[str, Any]) -> list[ft.Control]:
    body = scaffold["body"]
    assert isinstance(body, ft.ListView)
    return list(body.controls)


def headers(rows: list[ft.Control]) -> list[str]:
    return [
        texts(row)[0] for row in rows if isinstance(row, ft.Semantics) and row.header
    ]


def tiles(rows: list[ft.Control]) -> dict[str, ft.ListTile]:
    """Each room row's ``ListTile``, by its semantics identifier."""
    found: dict[str, ft.ListTile] = {}
    for row in rows:
        if isinstance(row, ft.MergeSemantics) and isinstance(row.content, ft.Semantics):
            tile = row.content.content
            assert isinstance(tile, ft.ListTile)
            found[str(row.content.identifier)] = tile
    return found


def subtitle_lines(tile: ft.ListTile) -> list[str]:
    assert isinstance(tile.subtitle, ft.Control)
    return texts(tile.subtitle)


def empty_state(rows: list[ft.Control], identifier: str) -> ft.Semantics:
    (state,) = [
        node
        for row in rows
        for node in descendants(row)
        if isinstance(node, ft.Semantics) and node.identifier == identifier
    ]
    return state


def button_of(rows: list[ft.Control]) -> ft.FilledTonalButton:
    (button,) = [
        node
        for row in rows
        for node in descendants(row)
        if isinstance(node, ft.FilledTonalButton)
    ]
    return button


# ------------------------------------------------------------------ the list


def test_rooms_come_first_then_the_other_locations_under_their_headings(
    render: Callable[..., dict[str, Any]], data: ConferenceData
) -> None:
    rows = rows_of(render(FakeConference(data)))
    assert headers(rows) == ["Rooms", "Other locations"]
    keys = list(tiles(rows))
    assert keys[:3] == [
        "map.room.expo-hall-ab",
        "map.room.expo-hall-c",
        "map.room.grand-ballroom-a",
    ]
    assert keys[-3:] == [
        "map.room.elsewhere",
        "map.room.lobby",
        "map.room.out-front-of-hyatt-regency",
    ]
    # The second heading sits right above the first other location.
    other = next(
        i for i, row in enumerate(rows) if headers([row]) == ["Other locations"]
    )
    assert tiles(rows[other + 1 : other + 2]).keys() == {"map.room.elsewhere"}
    assert len(keys) == len(data.rooms)


def test_each_row_names_its_room_and_counts_its_sessions(
    render: Callable[..., dict[str, Any]], data: ConferenceData
) -> None:
    rows = tiles(rows_of(render(FakeConference(data), now=BEFORE)))
    tile = rows["map.room.room-103abc"]
    assert tile.title == "Room 103ABC"
    assert subtitle_lines(tile) == ["26 sessions"]
    assert isinstance(tile.leading, ft.Icon)
    assert tile.leading.icon == ft.Icons.PLACE_OUTLINED
    assert subtitle_lines(rows["map.room.lobby"]) == ["1 session"]


def test_a_tap_pushes_the_room_s_detail_on_the_map(
    render: Callable[..., dict[str, Any]], data: ConferenceData, page: FakePage
) -> None:
    tile = tiles(rows_of(render(FakeConference(data))))[
        "map.room.pacific-ballroom-arena"
    ]
    assert tile.on_click is not None
    cast(Callable[[], None], tile.on_click)()
    assert page.navigated == [drill_href("/map", "room", "pacific-ballroom-arena")]
    assert page.navigated == ["/map/room/pacific-ballroom-arena"]


def test_while_a_session_is_on_its_room_says_now_in_the_live_colour(
    render: Callable[..., dict[str, Any]], data: ConferenceData
) -> None:
    tile = tiles(rows_of(render(FakeConference(data))))["map.room.room-103abc"]
    count, now = subtitle_lines(tile)
    assert count == "26 sessions"  # the count keeps its place under the name
    assert now.startswith("Now: Mind the gap! Why static typing")
    (line,) = [
        n for n in descendants(tile) if isinstance(n, ft.Text) and n.value == now
    ]
    assert line.color == LIGHT_TOKENS.live


def test_before_the_conference_no_room_says_now(
    render: Callable[..., dict[str, Any]], data: ConferenceData
) -> None:
    rows = tiles(rows_of(render(FakeConference(data), now=BEFORE)))
    assert all(
        not any(line.startswith("Now:") for line in subtitle_lines(t))
        for t in rows.values()
    )


def test_the_now_lines_follow_the_clock(
    render: Callable[..., dict[str, Any]], data: ConferenceData
) -> None:
    """The fake clock (D-73) and each minute's re-render (D-175) move the lines."""
    at_11_10 = tiles(rows_of(render(FakeConference(data))))["map.room.room-103abc"]
    later = datetime(2026, 5, 15, 11, 50, tzinfo=PACIFIC)
    at_11_50 = tiles(rows_of(render(FakeConference(data), now=later)))[
        "map.room.room-103abc"
    ]
    assert subtitle_lines(at_11_10)[1] != subtitle_lines(at_11_50)[1]
    assert subtitle_lines(at_11_50)[1].startswith("Now: PEP 750")


def test_the_screen_ticks_with_the_minute(
    render: Callable[..., dict[str, Any]], data: ConferenceData, minutes: list[int]
) -> None:
    render(FakeConference(data))
    render(FakeConference(None))  # every branch: hooks are unconditional (D-70)
    assert len(minutes) == 2


@pytest.mark.parametrize(
    ("names", "expected"),
    [
        ((), []),
        (("Lunch",), ["Now: Lunch"]),
        (
            ("Organizing IRL meetups", "Board Games"),
            ["Now: Organizing IRL meetups", "and 1 more"],
        ),
        (("A", "B", "C"), ["Now: A", "and 2 more"]),
    ],
)
def test_the_now_lines_name_one_session_and_count_the_others(
    names: tuple[str, ...], expected: list[str]
) -> None:
    entry = SimpleNamespace(on_now=tuple(SimpleNamespace(name=n) for n in names))
    assert now_lines(cast(Any, entry)) == expected


def test_a_long_title_s_ellipsis_never_hides_the_other_sessions(page: FakePage) -> None:
    """The cut is the title's alone: "and 1 more" is a line of its own (ux.md §5.8)."""
    long = "Getting Started with Celery: Building Your First Background Task System"
    entry = SimpleNamespace(
        room=SimpleNamespace(
            name="Room 102C", slug="room-102c", session_ids=("1",) * 4
        ),
        on_now=(SimpleNamespace(name=long), SimpleNamespace(name="Board games")),
    )
    row = room_row(cast(Any, entry), "/map", live=LIGHT_TOKENS.live)
    tile = tiles([row])["map.room.room-102c"]
    assert subtitle_lines(tile) == ["4 sessions", f"Now: {long}", "and 1 more"]
    assert isinstance(tile.subtitle, ft.Column)
    lines = [n for n in descendants(tile.subtitle) if isinstance(n, ft.Text)]
    count, title, more = lines
    # The title is cut as a session row's title is (three lines, ux.md §3.6) ...
    assert (title.max_lines, title.overflow) == (3, ft.TextOverflow.ELLIPSIS)
    # ... and neither the count nor the other sessions' line can be cut.
    assert count.max_lines is None and more.max_lines is None
    assert title.color == more.color == LIGHT_TOKENS.live


def test_the_app_bar_searches_rooms_and_a_retap_scrolls_to_the_top(
    render: Callable[..., dict[str, Any]],
    data: ConferenceData,
    page: FakePage,
    svc: Services,
) -> None:
    scaffold = render(FakeConference(data))
    assert scaffold["title"] == "Map"
    assert scaffold["on_retap"] is retap
    (search,) = scaffold["actions"]
    assert isinstance(search, ft.IconButton)
    assert search.tooltip == "Search"
    page.route = "/map"
    cast(Callable[[], None], search.on_click)()
    assert page.navigated == ["/search?scope=rooms"]
    assert svc.memory.search_base == "/map"


def test_the_map_has_no_control_for_the_p2_panes(
    render: Callable[..., dict[str, Any]], data: ConferenceData, page: FakePage
) -> None:
    """Floor plans, the expo and the job fair are P2 (MAP-01): no dead controls."""
    rows = rows_of(render(FakeConference(data)))
    for tile in tiles(rows).values():
        cast(Callable[[], None], tile.on_click)()
    assert all(location.startswith("/map/room/") for location in page.navigated)
    assert not any(
        isinstance(n, ft.Tabs | ft.TabBar) for r in rows for n in descendants(r)
    )
    assert "/map" in PAGES


# ------------------------------------------------------------------ without data


def test_without_data_the_skeleton_shows_until_the_first_fetch_fails(
    render: Callable[..., dict[str, Any]],
) -> None:
    rows = rows_of(render(FakeConference(None)))
    assert rows[0] is STRIP  # it says "No schedule yet", then "Updating the schedule…"
    assert texts(rows[1]) == ["Loading rooms"]  # the skeleton's spoken label
    assert len(rows) == 2


@pytest.mark.parametrize(
    ("problem", "body"),
    [
        ("offline", "Connect to the internet and try again."),
        ("server", "The schedule couldn't be read. Try again in a few minutes."),
    ],
)
async def test_after_a_failed_first_fetch_the_rooms_can_be_tried_again(
    render: Callable[..., dict[str, Any]], problem: str, body: str
) -> None:
    conference = FakeConference(None, problem=problem)
    rows = rows_of(render(conference))
    assert texts(empty_state(rows, "map.no_data")) == ["Can't load the rooms", body]
    button = button_of(rows)
    assert button.content == "Try again"
    assert not button.disabled
    await cast(Callable[[], Any], button.on_click)()
    assert conference.refreshes == 1


def test_a_retry_keeps_the_state_with_its_button_disabled(
    render: Callable[..., dict[str, Any]],
) -> None:
    conference = FakeConference(None, problem="offline")
    conference.refreshing = True
    rows = rows_of(render(conference))
    empty_state(rows, "map.no_data")  # still there: a screen reader keeps its place
    assert button_of(rows).disabled


def test_a_schedule_without_rooms_says_so_and_offers_the_schedule(
    render: Callable[..., dict[str, Any]], page: FakePage
) -> None:
    empty = ConferenceData(
        sessions={},
        speakers={},
        days=(),
        rooms={},
        posters=(),
        sprints=(),
        job_listings=(),
        dropped={},
        skipped=(),
        content={},
    )
    rows = rows_of(render(FakeConference(empty)))
    assert texts(empty_state(rows, "map.no_rooms")) == [
        "No rooms yet",
        "Rooms appear here once the schedule lists them.",
    ]
    cast(Callable[[], None], button_of(rows).on_click)()
    assert page.navigated == ["/schedule"]
