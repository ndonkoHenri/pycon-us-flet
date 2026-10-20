"""Tests for the Developer screen's Data section: refresh, clear, share the log, reset (#107).

``DataActions`` runs outside a renderer, as ``Developer`` does in ``test_developer.py``:
its hooks are replaced and a fake page is bound. The feed fetch is replaced too, so no
test reaches the network. How the section looks, the share sheet and a reset on a
device are checked on devices (the PR).
"""

import asyncio
import inspect
import logging
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import flet as ft
import pytest

from pycon_us import clock
from pycon_us import prefs as prefs_module
from pycon_us.config import load_year
from pycon_us.favorites import Favorites
from pycon_us.memory import ViewMemory
from pycon_us.prefs import Prefs
from pycon_us.screens import developer_data
from pycon_us.screens.developer_data import (
    CLEARED,
    LOG_NOT_FOUND,
    LOG_OFFERED,
    LOG_SHARED,
    NO_LOG,
    NOT_SHARED,
    RESET_INCOMPLETE,
    DataActions,
    refreshed,
    reset_app,
    schedule_line,
)
from pycon_us.screens.developer_ui import (
    NBSP,
    confirmation,
    reset_losses,
    snapshot_day,
)
from pycon_us.services import Services, api, errors
from pycon_us.services.storage import Storage
from pycon_us.state import Conference
from pycon_us.theme import LIGHT_TOKENS
from tests.fakes import (
    FakePage,
    MemoryClipboard,
    MemoryHaptics,
    MemoryLauncher,
    MemoryPaths,
    MemoryPrefs,
    MemorySemantics,
    MemoryShare,
    bound,
)
from tests.feeds import recorded

DEV_FEED = "http://127.0.0.1:8000/conference-2026.json"


@pytest.fixture(autouse=True)
def real_time() -> Iterator[None]:
    """Each test starts on real time, without error details, and leaves them so."""
    clock.start_fake_clock(None)
    errors.show_details(False)
    yield
    clock.start_fake_clock(None)
    errors.show_details(False)


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """No test reaches the network: every fetch finds no answer. Returns the URLs asked."""
    asked: list[str] = []

    async def fetch(url: str, **_: Any) -> bytes:
        asked.append(url)
        raise api.NetworkError("ConnectError: offline")

    monkeypatch.setattr(api, "fetch_feed", fetch)
    return asked


@pytest.fixture
def page() -> Iterator[FakePage]:
    """A fake page, bound as the session's page until the test ends."""
    fake = FakePage()
    with bound(fake):
        yield fake


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
        share=MemoryShare(),
        paths=MemoryPaths(),
    )


@pytest.fixture
def stored(svc: Services) -> dict[str, Any]:
    """What SharedPreferences holds, as the fake keeps it."""
    return cast(MemoryPrefs, svc.storage.prefs).values


@pytest.fixture
def prefs(monkeypatch: pytest.MonkeyPatch) -> Prefs:
    """Loaded preferences with Developer unlocked, as in a packaged build."""
    monkeypatch.setattr(prefs_module, "DEVELOPER_ALWAYS", False)  # a packaged build
    return Prefs(dev={"unlocked": True}, loaded=True)


@pytest.fixture
async def conference(svc: Services) -> Conference:
    """A Conference store that has published the bundled 2026 snapshot."""
    store = Conference()
    await store.load_local(svc.storage, svc.year)  # the bundled snapshot
    return store


@pytest.fixture
def favorites() -> Favorites:
    """Three saved sessions, loaded."""
    return Favorites(ids=frozenset({"1", "2", "3"}), loaded=True)


@pytest.fixture
def packaged(monkeypatch: pytest.MonkeyPatch) -> Callable[[bool], None]:
    """Make the section see a packaged build, or not."""

    def set_packaged(on: bool) -> None:
        monkeypatch.setattr(developer_data, "is_embedded", lambda: on)

    set_packaged(True)
    return set_packaged


class Rendered:
    """``DataActions`` rendered by hand: its state, the dialog it portals, its controls."""

    def __init__(self) -> None:
        """Start with no state values and no dialog shown."""
        self.values: list[Any] = []
        self.index = 0
        self.dialogs: list[ft.DialogControl | None] = []

    def use_state(self, initial: Any) -> tuple[Any, Callable[[Any], None]]:
        """Answer ``ft.use_state`` by call order, as Flet's renderer does."""
        if self.index == len(self.values):
            self.values.append(initial() if callable(initial) else initial)
        index = self.index
        self.index += 1

        def set_value(value: Any) -> None:
            self.values[index] = value

        return self.values[index], set_value

    @property
    def dialog(self) -> ft.AlertDialog | None:
        """The confirmation the last render showed, or None."""
        last = self.dialogs[-1]
        assert last is None or isinstance(last, ft.AlertDialog)
        return last


@pytest.fixture
def rendered() -> Rendered:
    """A fresh hand renderer for ``DataActions``."""
    return Rendered()


@pytest.fixture
def minutes() -> list[int]:
    """The ``use_minute()`` calls: one per render."""
    return []


@pytest.fixture
def render(
    monkeypatch: pytest.MonkeyPatch,
    rendered: Rendered,
    svc: Services,
    prefs: Prefs,
    conference: Conference,
    favorites: Favorites,
    packaged: Callable[[bool], None],
    page: FakePage,
    minutes: list[int],
) -> Callable[[], ft.Column]:
    """Render ``DataActions`` and return its column."""
    monkeypatch.setattr(ft, "use_state", rendered.use_state)
    monkeypatch.setattr(ft, "use_dialog", rendered.dialogs.append)
    monkeypatch.setattr(developer_data, "use_services", lambda: svc)
    monkeypatch.setattr(developer_data, "use_conference", lambda: conference)
    monkeypatch.setattr(developer_data, "use_prefs", lambda: prefs)
    monkeypatch.setattr(developer_data, "use_favorites", lambda: favorites)
    monkeypatch.setattr(developer_data, "use_tokens", lambda: LIGHT_TOKENS)
    # The minute tick needs a renderer; its own tests are test_status_strip_ticks.py's.
    monkeypatch.setattr(developer_data, "use_minute", lambda: minutes.append(0) or 0)

    def render() -> ft.Column:
        rendered.index = 0
        column = inspect.unwrap(DataActions)()
        assert isinstance(column, ft.Column)
        return column

    return render


def identified(root: ft.Control) -> dict[str, ft.Control]:
    """The control under each identifier below ``root``."""
    found: dict[str, ft.Control] = {}

    def visit(control: Any) -> None:
        if isinstance(control, ft.Semantics) and control.identifier:
            found[control.identifier] = cast(ft.Control, control.content)
        for name in ("content", "controls", "actions"):
            child = getattr(control, name, None)
            for item in child if isinstance(child, list) else [child]:
                if isinstance(item, ft.Control):
                    visit(item)

    visit(root)
    return found


def row(column: ft.Column, identifier: str) -> ft.ListTile:
    """The list tile under ``identifier`` in the column."""
    tile = identified(column)[identifier]
    assert isinstance(tile, ft.ListTile)
    return tile


def subtitle(column: ft.Column, identifier: str) -> str:
    """The subtitle's words of the row under ``identifier``."""
    return str(cast(ft.Text, row(column, identifier).subtitle).value)


async def tap(render: Callable[[], ft.Column], identifier: str) -> None:
    """Tap a row as Flutter would: a no-argument handler, maybe a coroutine."""
    result = cast(Callable[[], Any], row(render(), identifier).on_click)()
    if inspect.isawaitable(result):
        await result


async def press(dialog: ft.AlertDialog | None, identifier: str) -> None:
    """Press a confirmation's button."""
    assert dialog is not None
    button = identified(dialog)[identifier]
    assert isinstance(button, ft.TextButton)
    result = cast(Callable[[], Any], button.on_click)()
    if inspect.isawaitable(result):
        await result


def outcome(column: ft.Column) -> str | None:
    """The words of the line under the rows, or None while it is hidden."""
    line = next(
        c
        for c in column.controls
        if isinstance(c, ft.Semantics) and c.identifier == "developer.data_outcome"
    )
    assert line.live_region is True
    if not line.visible:
        return None
    text = cast(ft.Row, cast(ft.Container, line.content).content).controls[1]
    assert isinstance(text, ft.Text)
    return str(text.value)


def said(page: FakePage) -> list[str]:
    """The words of every SnackBar the page has shown, in order."""
    return [
        str(cast(ft.Text, d.content).value)
        for d in page.dialogs
        if isinstance(d, ft.SnackBar)
    ]


# ------------------------------------------------------------------ the rows


def test_each_action_carries_the_identifier_ui_flows_use(
    render: Callable[[], ft.Column],
) -> None:
    """The section's identifiers are exactly its four rows' and the outcome line's."""
    assert set(identified(render())) == {
        "developer.refresh_now",
        "developer.clear_cache",
        "developer.share_log",
        "developer.reset_app",
        "developer.data_outcome",
    }


def test_each_action_is_one_node_with_its_identifier(
    render: Callable[[], ft.Column],
) -> None:
    """Each of the four rows is a MergeSemantics over its identified tile: one node.

    A bare Semantics(identifier) around a control is an empty extra node for TalkBack;
    merged, the row is one button node that carries it (D-190).
    """
    rows = [c for c in render().controls if isinstance(c, ft.MergeSemantics)]
    assert len(rows) == 4
    for merged in rows:
        inner = merged.content
        assert isinstance(inner, ft.Semantics) and inner.identifier
        assert isinstance(inner.content, ft.ListTile)


async def test_a_disabled_row_s_node_says_it_is_disabled(
    render: Callable[[], ft.Column],
) -> None:
    """A disabled row's identifier node is disabled too, and an enabled row's is not.

    Flet's Semantics says "enabled" from its own ``disabled``, and the merged node kept
    it: Android dumped Clear cached feed, disabled, as enabled="true" (F42, #239). The
    row's identifier node takes the tile's state (D-214).
    """
    nodes = [
        cast(ft.Semantics, merged.content)
        for merged in render().controls
        if isinstance(merged, ft.MergeSemantics)
    ]
    rows = {node.identifier: node for node in nodes}
    assert row(render(), "developer.clear_cache").disabled is True  # no cache yet
    assert rows["developer.clear_cache"].disabled is True
    assert rows["developer.reset_app"].disabled is False


def test_reset_app_reads_as_destructive(render: Callable[[], ft.Column]) -> None:
    """Reset app's icon and title are in the error colour, and the row is enabled."""
    tile = row(render(), "developer.reset_app")
    assert isinstance(tile.leading, ft.Icon) and tile.leading.color == ft.Colors.ERROR
    assert isinstance(tile.title, ft.Text) and tile.title.color == ft.Colors.ERROR
    assert tile.disabled is False


def test_refresh_now_says_what_the_schedule_on_screen_is(
    render: Callable[[], ft.Column],
) -> None:
    """Refresh now's subtitle names the bundled snapshot the fixture published."""
    assert subtitle(render(), "developer.refresh_now").startswith(
        "Bundled with the app, updated "
    )


def test_refresh_now_s_age_follows_the_clock_while_the_screen_is_open(
    render: Callable[[], ft.Column],
    conference: Conference,
    minutes: list[int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-198: the minute tick re-renders the section, so "updated ..." stays current."""
    fetched_at = conference.fetched_at
    assert fetched_at is not None
    monkeypatch.setattr(clock, "now", lambda: fetched_at)
    assert subtitle(render(), "developer.refresh_now") == (
        "Bundled with the app, updated just now"
    )
    monkeypatch.setattr(clock, "now", lambda: fetched_at + timedelta(hours=3))
    assert subtitle(render(), "developer.refresh_now") == (
        "Bundled with the app, updated 3 hours ago"
    )
    assert len(minutes) == 2  # on the tick at every render (D-70: never conditional)


async def test_refresh_now_asks_for_a_refresh_and_says_how_it_ended(
    render: Callable[[], ft.Column],
    conference: Conference,
    monkeypatch: pytest.MonkeyPatch,
    page: FakePage,
) -> None:
    """Refresh now says in place, not in a SnackBar, how each refresh ended.

    Offline, the bundled schedule stays; with the feed answering, the schedule and the
    row's subtitle come from the feed.
    """
    await tap(render, "developer.refresh_now")
    assert outcome(render()) == (
        "No answer from the feed: the app keeps the schedule it has."
    )
    assert conference.source == "bundled"  # kept

    async def serve(url: str, **_: Any) -> bytes:
        return recorded(2026)

    monkeypatch.setattr(api, "fetch_feed", serve)
    await tap(render, "developer.refresh_now")
    assert conference.source == "network"
    assert outcome(render()) == "Schedule updated from the feed."
    assert subtitle(render(), "developer.refresh_now") == (
        "From the feed, updated just now"
    )
    assert page.dialogs == []  # in place, not a SnackBar (D-29, D-210)


async def test_refresh_now_is_disabled_while_an_asked_for_refresh_runs(
    render: Callable[[], ft.Column],
    conference: Conference,
    svc: Services,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refresh now is disabled, with a ring, only while a refresh it asked for runs.

    A quiet refresh leaves the row enabled; its own refresh says "Updating the
    schedule…" until it ends.
    """
    release = asyncio.Event()

    async def hold(url: str, **_: Any) -> bytes:
        await release.wait()
        return recorded(2026)

    monkeypatch.setattr(api, "fetch_feed", hold)
    conference.start_refresh(svc.storage, svc.year)  # quiet: the row stays enabled
    await asyncio.sleep(0)
    assert row(render(), "developer.refresh_now").disabled is False
    asked = asyncio.create_task(tap(render, "developer.refresh_now"))
    await asyncio.sleep(0)
    tile = row(render(), "developer.refresh_now")
    assert tile.disabled is True  # D-181: as every Refresh button
    assert subtitle(render(), "developer.refresh_now") == "Updating the schedule…"
    assert isinstance(tile.trailing, ft.ProgressRing)  # something moves (ux.md §4)
    release.set()
    await asked
    tile = row(render(), "developer.refresh_now")
    assert tile.disabled is False
    assert tile.trailing is None


async def test_a_reset_during_an_asked_for_refresh_ends_the_tap_without_an_outcome(
    render: Callable[[], ft.Column],
    svc: Services,
    prefs: Prefs,
    conference: Conference,
    favorites: Favorites,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A reset during an asked-for refresh cancels the tap, which shows no outcome."""
    release = asyncio.Event()

    async def hold(url: str, **_: Any) -> bytes:
        await release.wait()
        return recorded(2026)

    monkeypatch.setattr(api, "fetch_feed", hold)
    asked = asyncio.create_task(tap(render, "developer.refresh_now"))
    await asyncio.sleep(0)
    async with asyncio.timeout(5):
        await reset_app(svc, conference, prefs, favorites)
    # The tap awaited the refresh that the reset cancelled: it ends cancelled too
    # (Conference.reset()), not with a claim that the schedule was updated.
    await asyncio.wait({asked})
    assert asked.cancelled()
    assert outcome(render()) is None
    release.set()


# ------------------------------------------------------------------ Clear cached feed


async def test_clear_cached_feed_is_disabled_without_a_cache(
    render: Callable[[], ft.Column],
) -> None:
    """Without a cache, Clear cached feed is disabled and says why, readably."""
    tile = row(render(), "developer.clear_cache")
    assert tile.disabled is True
    assert subtitle(render(), "developer.clear_cache") == (
        "No cached schedule on this device"
    )
    # Why it is off stays readable: not at the disabled 38 % (ux.md principle 8).
    assert cast(ft.Text, tile.subtitle).color == ft.Colors.ON_SURFACE_VARIANT


async def test_clear_cached_feed_asks_first_and_cancel_keeps_the_cache(
    render: Callable[[], ft.Column], rendered: Rendered, svc: Services
) -> None:
    """Clear cached feed asks in a modal dialog first, and Cancel keeps the cache."""
    await svc.storage.write_feed(recorded(2026))
    assert subtitle(render(), "developer.clear_cache") == (
        "The next start shows the bundled schedule"
    )
    await tap(render, "developer.clear_cache")
    render()
    dialog = rendered.dialog
    assert dialog is not None and dialog.modal is True
    assert dialog.title == ft.Text("Clear the cached schedule?")
    assert svc.storage.feed_path.exists()  # nothing deleted before the answer
    await press(dialog, "developer.clear_cache.cancel")
    render()
    assert rendered.dialog is None
    assert svc.storage.feed_path.exists()
    assert dialog.on_dismiss is not None  # Back cancels too


async def test_clear_cached_feed_deletes_the_cache_and_keeps_the_session_s_data(
    render: Callable[[], ft.Column],
    rendered: Rendered,
    svc: Services,
    conference: Conference,
) -> None:
    """Confirming the clear deletes the cache file but not the session's data.

    The outcome line says it was cleared, and the row is disabled again.
    """
    await svc.storage.write_feed(recorded(2026))
    version = conference.version
    await tap(render, "developer.clear_cache")
    render()
    await press(rendered.dialog, "developer.clear_cache.confirm")
    column = render()
    assert rendered.dialog is None
    assert not svc.storage.feed_path.exists()  # the next start: the snapshot (D-39)
    assert conference.version == version  # this session keeps what it shows
    assert outcome(column) == CLEARED[0]
    assert row(column, "developer.clear_cache").disabled is True


def test_the_clear_confirmation_names_the_bundled_schedule_s_day() -> None:
    """The clear confirmation names the day of the schedule bundled with the app.

    It also says the schedule on screen stays until the app is closed.
    """
    dialog = confirmation(
        "clear",
        saved=0,
        packaged=True,
        snapshot_day="Mon, Oct 12",
        on_confirm=lambda: None,
        on_cancel=lambda: None,
    )
    assert dialog is not None
    text = cast(ft.Text, cast(ft.Column, dialog.content).controls[0]).value
    assert "the schedule bundled with the app (Mon, Oct 12)" in str(text)
    assert "You keep seeing it until you close the app" in str(text)


def test_the_bundled_schedule_s_day_never_wraps_in_its_middle(svc: Services) -> None:
    """The bundled schedule's day joins its three words with no-break spaces."""
    day = snapshot_day(svc.year.conference)
    assert day and " " not in day  # "(Sun, Oct" / "11)" on a phone before
    assert day.replace(NBSP, " ").count(" ") == 2  # e.g. "Sun, Oct 11"


# ------------------------------------------------------------------ Share log


def test_share_log_is_off_outside_a_packaged_build_and_says_why(
    render: Callable[[], ft.Column], packaged: Callable[[bool], None]
) -> None:
    """Outside a packaged build, Share log is disabled and says where the log is."""
    packaged(False)
    tile = row(render(), "developer.share_log")
    assert tile.disabled is True
    assert subtitle(render(), "developer.share_log") == (
        "Not a packaged build: the log is in the terminal that runs it"
    )


async def test_share_log_shares_the_console_log_file(
    render: Callable[[], ft.Column], svc: Services, tmp_path: Path
) -> None:
    """Share log shares the console log file alone, then says it was shared."""
    log = tmp_path / "console.log"
    log.write_text("12:00:00.000 INFO pycon_us.app: started\n")
    cast(MemoryPaths, svc.paths).console_log = str(log)
    await tap(render, "developer.share_log")
    [files] = cast(MemoryShare, svc.share).shared
    assert [file.path for file in files] == [str(log)]
    assert outcome(render()) == LOG_SHARED[0]


@pytest.mark.parametrize(
    ("status", "says"),
    [
        (ft.ShareResultStatus.DISMISSED, None),
        # Some Android targets report neither: the sheet had the log either way.
        (ft.ShareResultStatus.UNAVAILABLE, LOG_OFFERED[0]),
    ],
)
async def test_a_dismissed_share_sheet_says_nothing(
    render: Callable[[], ft.Column],
    svc: Services,
    tmp_path: Path,
    status: ft.ShareResultStatus,
    says: str | None,
) -> None:
    """A dismissed share says nothing; an unavailable status says the log was offered.

    Either way, Share log stays usable.
    """
    log = tmp_path / "console.log"
    log.write_text("a line\n")
    cast(MemoryPaths, svc.paths).console_log = str(log)
    cast(MemoryShare, svc.share).status = status
    await tap(render, "developer.share_log")
    assert outcome(render()) == says
    assert row(render(), "developer.share_log").disabled is False  # usable again


@pytest.mark.parametrize("content", [None, ""])
async def test_without_a_log_there_is_nothing_to_share(
    render: Callable[[], ft.Column],
    svc: Services,
    tmp_path: Path,
    content: str | None,
) -> None:
    """A missing or empty log file shares nothing and says there is no log."""
    log = tmp_path / "console.log"
    if content is not None:
        log.write_text(content)
    cast(MemoryPaths, svc.paths).console_log = str(log)
    await tap(render, "developer.share_log")
    assert cast(MemoryShare, svc.share).shared == []
    assert outcome(render()) == NO_LOG[0]


async def test_a_share_that_fails_says_so_and_logs_only_the_error_s_class(
    render: Callable[[], ft.Column],
    svc: Services,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failed share says so and logs only the error's class, never the log's path.

    A log whose file name cannot be read says the log was not found.
    """
    log = tmp_path / "console.log"
    log.write_text("a line\n")
    cast(MemoryPaths, svc.paths).console_log = str(log)
    # Flet's invoke error repeats the call's arguments, the path included (D-72).
    cast(MemoryShare, svc.share).error = RuntimeError(f"share_files({log}) failed")
    with caplog.at_level(logging.WARNING):
        await tap(render, "developer.share_log")
    assert outcome(render()) == NOT_SHARED[0]
    assert [r.getMessage() for r in caplog.records] == [
        "Could not share the log: RuntimeError"
    ]
    cast(MemoryPaths, svc.paths).error = TimeoutError("get_console_log_filename")
    await tap(render, "developer.share_log")
    assert outcome(render()) == LOG_NOT_FOUND[0]


# ------------------------------------------------------------------ Reset app


def test_reset_lists_exactly_what_is_lost() -> None:
    """Reset lists the settings, saved sessions, cache and Developer options it loses.

    With nothing saved it says none, and outside a packaged build Developer does not
    lock again (D-73).
    """
    assert reset_losses(3, packaged=True) == (
        "Your settings: Appearance and the schedule's filters",
        "Your saved sessions in My schedule: 3",
        "The cached schedule: the app shows the bundled one until it refreshes",
        "Developer options: the fake clock and the feed URL, and Developer locks again",
    )
    losses = reset_losses(0, packaged=False)  # Developer is always there (D-73)
    assert losses[1] == "Your saved sessions in My schedule: none"
    assert losses[3] == "Developer options: the fake clock and the feed URL"


async def test_reset_app_asks_first_and_its_dialog_lists_the_losses(
    render: Callable[[], ft.Column],
    rendered: Rendered,
    stored: dict[str, Any],
) -> None:
    """Reset app first asks in a dialog listing the losses; Cancel deletes nothing."""
    stored["pycon.theme"] = "dark"
    await tap(render, "developer.reset_app")
    render()
    dialog = rendered.dialog
    assert dialog is not None and dialog.modal is True and dialog.scrollable is True
    assert dialog.title == ft.Text("Reset the app?")
    # Its icon in error, as the row that opened it: one destructive accent.
    assert dialog.icon == ft.Icon(ft.Icons.RESTART_ALT, color=ft.Colors.ERROR)
    lines = [
        str(cast(ft.Text, cast(ft.Row, line).controls[1]).value)
        for line in cast(ft.Column, dialog.content).controls[1:]
    ]
    assert lines == list(reset_losses(3, packaged=True))
    await press(dialog, "developer.reset_app.cancel")
    render()
    assert rendered.dialog is None
    assert stored["pycon.theme"] == "dark"  # nothing deleted


async def test_reset_app_clears_storage_and_every_store_as_after_a_fresh_install(
    render: Callable[[], ft.Column],
    rendered: Rendered,
    svc: Services,
    stored: dict[str, Any],
    prefs: Prefs,
    conference: Conference,
    favorites: Favorites,
    page: FakePage,
    offline: list[str],
) -> None:
    """Confirming the reset leaves storage and every store as after a fresh install.

    The session has been used: settings, favourites of two years, the Developer options,
    a cache, a fake clock, a feed URL and remembered places. Only another app's key is
    left; the device facts stay and Developer locks again. Then, as at a start, a quiet
    refresh of the year's feed runs, the app goes to Welcome, as a first start does
    (D-287), and says "App reset".
    """
    stored.update(
        {
            "pycon.theme": "dark",
            "pycon.onboarded": True,
            "pycon.excluded_tracks": [],
            "pycon.2026.favorites": ["1", "2", "3"],
            "pycon.2025.favorites": ["9"],
            "pycon.dev": '{"unlocked": true}',
            "flutter.not_ours": "kept",
        }
    )
    await svc.storage.write_feed(recorded(2026))
    await prefs.save(svc.storage, theme="dark", onboarded=True, excluded_tracks=())
    prefs.os_dark = True
    clock.start_fake_clock(datetime(2026, 5, 15, 16, tzinfo=UTC))
    errors.show_details(True)
    await conference.set_feed_url(DEV_FEED, svc.storage)
    svc.memory.last_location = "/more/developer"
    svc.memory.schedule_offsets[date(2026, 5, 15)] = 1200.0
    svc.memory.jumped_on = date(2026, 5, 15)

    await tap(render, "developer.reset_app")
    render()
    await press(rendered.dialog, "developer.reset_app.confirm")

    # On the device: nothing of the app's is left.
    assert stored == {"flutter.not_ours": "kept"}
    assert not svc.storage.feed_path.exists()
    # In memory, without a restart.
    assert abs(clock.now() - datetime.now(UTC)) < timedelta(seconds=5)
    assert errors._details is False
    assert (prefs.theme, prefs.onboarded, prefs.excluded_tracks, prefs.dev) == (
        "system",
        False,
        ("Open Space",),
        {},
    )
    assert prefs.developer is False  # a packaged build: locked again
    assert prefs.os_dark is True and prefs.loaded is True  # device facts stay
    assert favorites.ids == frozenset()
    assert svc.memory == ViewMemory()
    assert conference.source == "bundled"
    assert conference._feed_url is None
    # Then, as at a start: a quiet refresh of the year's feed, and the index route.
    await asyncio.sleep(0)
    assert offline == [svc.year.conference.feed_url]
    assert page.navigated == ["/welcome"]
    assert said(page) == ["App reset"]


async def test_a_reset_that_cannot_delete_everything_says_so(
    render: Callable[[], ft.Column],
    rendered: Rendered,
    svc: Services,
    stored: dict[str, Any],
    favorites: Favorites,
    page: FakePage,
) -> None:
    """A reset that cannot delete everything still resets the session and says so.

    It goes to Welcome, as a full reset does (D-120, D-287).
    """
    stored["pycon.2026.favorites"] = ["1"]
    cast(MemoryPrefs, svc.storage.prefs).fail_removes = True
    await tap(render, "developer.reset_app")
    render()
    await press(rendered.dialog, "developer.reset_app.confirm")
    assert favorites.ids == frozenset()  # the session is reset all the same (D-120)
    assert page.navigated == ["/welcome"]
    assert said(page) == [RESET_INCOMPLETE]


async def test_reset_cancels_a_refresh_from_a_developer_feed_before_it_caches_it(
    svc: Services,
    prefs: Prefs,
    conference: Conference,
    favorites: Favorites,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reset cancels a refresh from a Developer feed before that feed is cached.

    The new refresh then asks for the year's feed, and its own outcome stands.
    """
    release = asyncio.Event()
    asked: list[str] = []

    async def hold(url: str, **_: Any) -> bytes:
        asked.append(url)
        if url != DEV_FEED:
            raise api.NetworkError("ConnectError: offline")
        await release.wait()
        return recorded(2026)

    monkeypatch.setattr(api, "fetch_feed", hold)
    await conference.set_feed_url(DEV_FEED, svc.storage)
    running = conference.start_refresh(svc.storage, svc.year)
    await asyncio.sleep(0)
    async with asyncio.timeout(5):  # without the cancel it waits for the feed forever
        assert await reset_app(svc, conference, prefs, favorites) is True
    assert running.cancelled()
    release.set()
    await asyncio.sleep(0.05)
    assert not svc.storage.feed_path.exists()  # the test feed was never cached
    assert conference.source == "bundled"
    assert asked == [DEV_FEED, svc.year.conference.feed_url]  # then the year's feed
    assert conference.problem == "offline"  # the new refresh's own outcome


# ------------------------------------------------------------------ the words


def test_refresh_now_says_how_the_refresh_ended() -> None:
    """A refresh's outcome says the schedule was updated, or why it was kept."""
    assert refreshed(None) == ("Schedule updated from the feed.", True)
    assert refreshed("offline")[1] is False
    assert refreshed("server") == (
        "The feed's answer couldn't be used: the app keeps the schedule it has.",
        False,
    )


def test_the_schedule_line_names_the_source_and_its_age() -> None:
    """The schedule line names the source and its age, or says there is none yet."""
    now = datetime(2026, 5, 15, 12, tzinfo=UTC)
    three_hours = now - timedelta(hours=3)
    assert schedule_line("cache", three_hours, now) == (
        "From the cache, updated 3 hours ago"
    )
    assert (
        schedule_line("bundled", now, now) == "Bundled with the app, updated just now"
    )
    assert schedule_line("none", None, now) == "No schedule yet"
