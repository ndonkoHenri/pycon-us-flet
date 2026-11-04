"""Tests for Settings' Data section: Refresh now, Schedule changes, the zone row (#422, #438).

`DataSection` runs outside a renderer, as `DataActions` does in
`test_developer_data.py`: its hooks are replaced, and the feed fetch too, so no test
reaches the network. How the section looks and reads is checked on devices (the PR).
"""

import asyncio
import inspect
from collections.abc import Callable, Iterator
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
from pycon_us.favorites import Favorites
from pycon_us.memory import ViewMemory
from pycon_us.screens import settings_data
from pycon_us.screens.settings import RADIO_WIDTH
from pycon_us.screens.settings_data import DataSection
from pycon_us.services import Services, api, feed_api
from pycon_us.services.storage import Storage
from pycon_us.state import Conference
from pycon_us.theme import LIGHT_TOKENS
from pycon_us.ui.actions import KEPT
from tests.fake_page import FakePage, bound
from tests.fakes import (
    MemoryClipboard,
    MemoryHaptics,
    MemoryLauncher,
    MemoryPrefs,
    MemorySemantics,
)
from tests.feeds import recorded

DURING = datetime.fromisoformat("2026-05-15T10:00:00-07:00")
"""A moment of the 2026 conference, in Pacific Daylight Time."""


@pytest.fixture(autouse=True)
def real_time() -> Iterator[None]:
    """Each test starts on real time and leaves it so."""
    clock.start_fake_clock(None)
    yield
    clock.start_fake_clock(None)


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test reaches the network: every fetch finds no answer, as in airplane mode."""

    async def fetch(url: str, **_: Any) -> bytes:
        raise api.NetworkError("ConnectError: offline")

    monkeypatch.setattr(feed_api, "fetch_feed", fetch)


@pytest.fixture
def online(monkeypatch: pytest.MonkeyPatch) -> None:
    """The feed answers with the recorded 2026 feed."""

    async def serve(url: str, **_: Any) -> bytes:
        return recorded(2026)

    monkeypatch.setattr(feed_api, "fetch_feed", serve)


@pytest.fixture
def svc(tmp_path: Path) -> Services:
    """The 2026 services over in-memory fakes and a temporary directory."""
    return Services(
        year=load_year(2026),
        storage=Storage(prefs=MemoryPrefs(), directory=tmp_path, year=2026),
        memory=ViewMemory(),
        semantics=MemorySemantics(),
        haptics=MemoryHaptics(),
        launcher=MemoryLauncher(),
        clipboard=MemoryClipboard(),
    )


@pytest.fixture
async def conference(svc: Services) -> Conference:
    """A Conference store that has published the bundled 2026 snapshot, as offline."""
    store = Conference()
    await store.load_local(svc.storage, svc.year)
    return store


@pytest.fixture
def minutes() -> list[int]:
    """The `use_minute()` calls: one per render."""
    return []


@pytest.fixture
def change_log() -> ChangeLog:
    """The session's `ChangeLog`: empty unless a test records a batch in it."""
    return ChangeLog()


@pytest.fixture
def favorites() -> Favorites:
    """The saved sessions: none unless a test saves some."""
    return Favorites()


@pytest.fixture
def render(
    monkeypatch: pytest.MonkeyPatch,
    svc: Services,
    conference: Conference,
    change_log: ChangeLog,
    favorites: Favorites,
    minutes: list[int],
) -> Callable[[], ft.Column]:
    """Render `DataSection` by hand, its one state kept across renders: its column."""
    state: list[Any] = []

    def use_state(initial: Any) -> tuple[Any, Callable[[Any], None]]:
        if not state:
            state.append(initial)
        return state[0], lambda value: state.__setitem__(0, value)

    monkeypatch.setattr(ft, "use_state", use_state)
    monkeypatch.setattr(settings_data, "use_services", lambda: svc)
    monkeypatch.setattr(settings_data, "use_conference", lambda: conference)
    monkeypatch.setattr(settings_data, "use_tokens", lambda: LIGHT_TOKENS)
    monkeypatch.setattr(settings_data, "use_change_log", lambda: change_log)
    monkeypatch.setattr(settings_data, "use_favorites", lambda: favorites)
    monkeypatch.setattr(ft, "use_view_path", lambda: "/more/settings")
    # The minute tick needs a renderer; its own tests are test_status_strip_ticks.py's.
    monkeypatch.setattr(settings_data, "use_minute", lambda: minutes.append(0) or 0)

    def render() -> ft.Column:
        column = inspect.unwrap(DataSection)(RADIO_WIDTH)
        assert isinstance(column, ft.Column)
        return column

    return render


def identified(root: ft.Control) -> dict[str, ft.Control]:
    """The control under each identifier below `root`."""
    found: dict[str, ft.Control] = {}

    def visit(control: Any) -> None:
        if isinstance(control, ft.Semantics) and control.identifier:
            found[control.identifier] = cast(ft.Control, control.content)
        for name in ("content", "controls"):
            child = getattr(control, name, None)
            for item in child if isinstance(child, list) else [child]:
                if isinstance(item, ft.Control):
                    visit(item)

    visit(root)
    return found


def refresh_row(column: ft.Column) -> ft.ListTile:
    """Refresh now's tile."""
    tile = identified(column)["settings.data.refresh"]
    assert isinstance(tile, ft.ListTile)
    return tile


def schedule_said(column: ft.Column) -> str:
    """Refresh now's second line: the schedule's source and age."""
    return str(cast(ft.Text, refresh_row(column).subtitle).value)


async def tap_refresh(render: Callable[[], ft.Column]) -> None:
    """Tap Refresh now as Flutter would: a no-argument coroutine handler."""
    await cast(Callable[[], Any], refresh_row(render()).on_click)()


def outcome(column: ft.Column) -> str | None:
    """The words of the line under Refresh now, or None while it is hidden."""
    line = next(
        c
        for c in column.controls
        if isinstance(c, ft.Semantics) and c.identifier == "settings.data.outcome"
    )
    assert line.live_region is True  # a screen reader says how it ended
    if not line.visible:
        return None
    text = cast(ft.Row, cast(ft.Container, line.content).content).controls[1]
    assert isinstance(text, ft.Text)
    return str(text.value)


def zone_row(column: ft.Column) -> ft.ListTile | None:
    """The zone row's tile, or None when the section has none."""
    tile = identified(column).get("settings.data.zone")
    assert tile is None or isinstance(tile, ft.ListTile)
    return tile


def test_the_section_is_a_level_2_heading_named_data(
    render: Callable[[], ft.Column],
) -> None:
    """The section opens with "Data", a level-2 heading (D-211)."""
    heading = render().controls[0]
    assert isinstance(heading, ft.Semantics)
    assert heading.header and heading.heading_level == 2
    assert isinstance(heading.content, ft.Container)
    assert cast(ft.Text, heading.content.content).value == "Data"


def test_refresh_now_is_one_node_named_for_flows_lined_up_with_appearance(
    render: Callable[[], ft.Column],
) -> None:
    """Refresh now is one merged node; its icon sits in Settings' 48 dp slot."""
    column = render()
    merged = column.controls[1]
    assert isinstance(merged, ft.MergeSemantics)  # one node (D-214)
    tile = refresh_row(column)
    assert cast(ft.Text, tile.title).value == "Refresh now"
    assert isinstance(tile.leading, ft.Container)
    assert tile.leading.width == RADIO_WIDTH  # its title starts where Appearance's do
    assert outcome(column) is None  # nothing said before a tap


def test_a_first_start_offline_names_the_bundled_snapshot_and_its_age(
    render: Callable[[], ft.Column], svc: Services, minutes: list[int]
) -> None:
    """Before any refresh, the line names the bundled snapshot; the minute moves it."""
    captured = svc.year.conference.snapshot_captured_at
    assert captured is not None
    clock.start_fake_clock(captured + timedelta(days=3, minutes=1))
    assert schedule_said(render()) == "Bundled with the app, updated 3 days ago"
    assert minutes  # it ticks with the minute, so the age keeps up


async def test_a_refresh_that_lands_elsewhere_updates_the_line(
    render: Callable[[], ft.Column],
    svc: Services,
    conference: Conference,
    online: None,
) -> None:
    """A refresh not asked for here (a quiet one) still updates the line when it lands."""
    await conference.start_refresh(svc.storage, svc.year)
    assert schedule_said(render()) == "From the feed, updated just now"
    assert outcome(render()) is None  # not this row's refresh: nothing to say


async def test_refresh_now_with_the_feed_answering_says_so_in_place(
    render: Callable[[], ft.Column], conference: Conference, online: None
) -> None:
    """Refresh now loads the feed and says so under the row, not in a SnackBar."""
    await tap_refresh(render)
    assert conference.source == "network"
    assert outcome(render()) == "Schedule updated from the feed."
    assert schedule_said(render()) == "From the feed, updated just now"


async def test_refresh_now_in_airplane_mode_keeps_the_schedule_and_the_cache(
    render: Callable[[], ft.Column],
    svc: Services,
    conference: Conference,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Offline, Refresh now says it couldn't refresh; the data and the cache stay."""

    async def serve(url: str, **_: Any) -> bytes:
        return recorded(2026)

    with monkeypatch.context() as patch:  # online once, to save a cache
        patch.setattr(feed_api, "fetch_feed", serve)
        await tap_refresh(render)
    assert svc.storage.feed_path.exists()
    cached = svc.storage.feed_path.read_bytes()
    fetched, data = conference.fetched_at, conference.data
    await tap_refresh(render)  # airplane mode: no answer
    assert outcome(render()) == f"Couldn't refresh: no answer from the feed. {KEPT}"
    assert conference.data is data and conference.fetched_at == fetched  # kept
    assert svc.storage.feed_path.read_bytes() == cached  # never cleared (D-32)
    assert schedule_said(render()) == "From the feed, updated just now"


async def test_refresh_now_is_disabled_with_a_ring_while_its_refresh_runs(
    render: Callable[[], ft.Column], monkeypatch: pytest.MonkeyPatch
) -> None:
    """While its refresh runs the row is disabled, says so and shows a ring (D-181)."""
    release = asyncio.Event()

    async def hold(url: str, **_: Any) -> bytes:
        await release.wait()
        return recorded(2026)

    monkeypatch.setattr(feed_api, "fetch_feed", hold)
    asked = asyncio.create_task(tap_refresh(render))
    for _ in range(10):  # until the refresh it asked for has started
        await asyncio.sleep(0)
    tile = refresh_row(render())
    assert tile.disabled is True
    assert schedule_said(render()) == "Updating the schedule…"
    assert isinstance(tile.trailing, ft.ProgressRing)  # something moves (ux.md §4)
    release.set()
    await asked
    tile = refresh_row(render())
    assert tile.disabled is False and tile.trailing is None


def test_the_zone_row_shows_only_while_the_device_s_zone_differs(
    render: Callable[[], ft.Column], machine_tz: str
) -> None:
    """On Pacific Time no zone row; 22 hours away, it names both zones (D-35)."""
    clock.start_fake_clock(DURING)
    row = zone_row(render())
    if machine_tz == "America/Los_Angeles":
        assert row is None
        return
    assert row is not None
    assert row.title == "Times are Pacific Time (PDT)"
    assert row.subtitle == "This device is on UTC+14:00"
    assert row.on_click is None  # nothing to change: read, not tapped


# ------------------------------------------------------------------ Schedule changes

TALK = "142"
"""A 2026 session, saved in the tests that save one."""


def moved(session: str, at: datetime, *, seen: bool = False) -> Batch:
    """A batch detected `at` that moved `session` from Room 104A to Room 103ABC."""
    start = datetime.fromisoformat("2026-05-16T10:30:00-07:00")
    end = start + timedelta(minutes=30)
    old = Listing("Python for Humans", start, end, "Room 104A")
    new = Listing("Python for Humans", start, end, "Room 103ABC")
    return Batch(at, (Change(session, ChangeKind.ROOM, old, new),), seen=seen)


def changes_row(column: ft.Column) -> ft.ListTile:
    """Schedule changes' tile."""
    tile = identified(column)["settings.data.changes"]
    assert isinstance(tile, ft.ListTile)
    return tile


def changes_said(column: ft.Column) -> str:
    """Schedule changes' second line."""
    return str(cast(ft.Text, changes_row(column).subtitle).value)


def test_schedule_changes_sits_under_refresh_now_and_opens_on_settings(
    render: Callable[[], ft.Column],
) -> None:
    """The row pushes the year's list on Settings' View, so Back returns there (D-255)."""
    column = render()
    ids = list(identified(column))
    assert ids.index("settings.data.changes") > ids.index("settings.data.refresh")
    tile = changes_row(column)
    assert cast(ft.Text, tile.title).value == "Schedule changes"
    assert changes_said(column) == settings_data.CHANGES_LINE
    page = FakePage()
    with bound(page):
        cast(Callable[[], None], tile.on_click)()
    assert page.navigated == ["/more/settings/changes/2026"]


def test_schedule_changes_counts_unseen_changes_to_saved_sessions(
    render: Callable[[], ft.Column],
    change_log: ChangeLog,
    favorites: Favorites,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """While Now's card would show, the row says how many saved sessions changed."""
    monkeypatch.setattr(clock, "now", lambda: DURING)
    change_log.batches = (moved(TALK, DURING - timedelta(hours=1)),)
    assert changes_said(render()) == settings_data.CHANGES_LINE  # not saved
    favorites.ids = frozenset({TALK})
    assert changes_said(render()) == "1 saved session changed"
    change_log.batches = (moved(TALK, DURING - timedelta(hours=1), seen=True),)
    assert changes_said(render()) == settings_data.CHANGES_LINE
