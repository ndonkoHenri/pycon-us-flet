"""Tests for the shared chrome: ``AppScaffold``, ``StatusStrip`` and ``SectionHeader`` (#76).

``AppScaffold``'s bottom bar and its tab switches are here too (#75); the bar's own
parts are in ``test_navigation.py``.

The builders run outside a renderer: the hooks they call (``ft.use_view_path``,
``ft.use_effect`` and the store hooks) are replaced by ``Hooks``, and a fake page is
bound as Flet binds a session's page. What the controls look like, and that Flutter
marks the title as a header, is checked on devices (the PR).
"""

import asyncio
import inspect
import logging
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from zoneinfo import ZoneInfo

import flet as ft
import pytest
from flet.components.component import Renderer

from pycon_us import clock
from pycon_us.config import YearData, load_year
from pycon_us.locations import TAB_ROOTS
from pycon_us.screens import my_schedule, now
from pycon_us.services import Services, api
from pycon_us.services.storage import Storage
from pycon_us.state import Conference, Status, ViewMemory
from pycon_us.theme import DARK_TOKENS
from pycon_us.ui import scaffold
from pycon_us.ui.navigation import TABS, Tab
from pycon_us.ui.scaffold import (
    AppScaffold,
    SectionHeader,
    Shown,
    StatusStrip,
    search_button,
    strip_line,
)
from tests.fakes import (
    FakePage,
    MemoryClipboard,
    MemoryHaptics,
    MemoryLauncher,
    MemoryPrefs,
    MemorySemantics,
    bound,
)

PACIFIC = ZoneInfo("America/Los_Angeles")


@pytest.fixture(scope="module")
def year() -> YearData:
    return load_year(2026)


@pytest.fixture
def svc(year: YearData, tmp_path: Path) -> Services:
    storage = Storage(prefs=MemoryPrefs(), directory=tmp_path, year=2026)
    return Services(
        year=year,
        storage=storage,
        memory=ViewMemory(),
        semantics=MemorySemantics(),
        haptics=MemoryHaptics(),
        launcher=MemoryLauncher(),
        clipboard=MemoryClipboard(),
    )


@dataclass
class Hooks:
    """The hooks the builders call, answered by the test instead of a renderer."""

    view_path: str = "/now"
    effects: list[tuple[Callable[[], Any], list[Any] | None]] = field(
        default_factory=list
    )
    cleanups: list[Callable[[], Any] | None] = field(default_factory=list)
    state: Any = None
    renders: int = 0
    """How many re-renders a state setter asked for: only for a changed value."""

    def use_effect(
        self,
        setup: Callable[[], Any],
        dependencies: Any = None,
        cleanup: Callable[[], Any] | None = None,
    ) -> None:
        self.effects.append((setup, dependencies))
        self.cleanups.append(cleanup)

    def use_state(self, initial: Any) -> tuple[Any, Callable[[Any], None]]:
        """One state per test, set as Flet's setter sets it: unchanged, no render."""
        if self.state is None:
            self.state = initial() if callable(initial) else initial

        def set_state(value: Any) -> None:
            if value != self.state:
                self.state = value
                self.renders += 1

        return self.state, set_state


@pytest.fixture
def page() -> Iterator[FakePage]:
    fake = FakePage()
    with bound(fake):
        yield fake


@pytest.fixture
def conference() -> Conference:
    return Conference()


@pytest.fixture
def hooks(
    monkeypatch: pytest.MonkeyPatch, svc: Services, conference: Conference
) -> Hooks:
    hooks = Hooks()
    monkeypatch.setattr(ft, "use_view_path", lambda: hooks.view_path)
    monkeypatch.setattr(ft, "use_effect", hooks.use_effect)
    monkeypatch.setattr(ft, "use_state", hooks.use_state)
    monkeypatch.setattr(scaffold, "use_services", lambda: svc)
    monkeypatch.setattr(scaffold, "use_conference", lambda: conference)
    monkeypatch.setattr(scaffold, "use_tokens", lambda: DARK_TOKENS)
    # ``Shown``'s body runs inline, as ``StatusStrip``'s does below: no renderer here.
    monkeypatch.setattr(scaffold, "Shown", inspect.unwrap(Shown))
    return hooks


def view_at(hooks: Hooks, page: FakePage, view_path: str, **kwargs: Any) -> ft.View:
    """Build the View of view_path while page.route addresses it (the top View)."""
    hooks.view_path = view_path
    page.route = page.route if kwargs.pop("below", False) else view_path
    return AppScaffold(title="Title", body=ft.Text("body"), **kwargs)


def app_bar(view: ft.View) -> ft.AppBar:
    assert isinstance(view.appbar, ft.AppBar)
    return view.appbar


def click(button: ft.IconButton) -> None:
    """Call a button's handler as Flet does: without the event when it takes none."""
    assert button.on_click is not None
    cast(Callable[[], None], button.on_click)()


def press(button: ft.TextButton) -> asyncio.Task[None]:
    """Run a button's async handler as Flet does, as a task of the event loop."""
    assert button.on_click is not None
    return asyncio.create_task(cast(Callable[[], Any], button.on_click)())


def back_arrow(view: ft.View) -> ft.IconButton:
    leading = app_bar(view).leading
    assert isinstance(leading, ft.IconButton)
    return leading


# ------------------------------------------------------------------ AppScaffold


def test_the_title_is_left_aligned_and_stays_a_screen_reader_header(
    hooks: Hooks, page: FakePage
) -> None:
    bar = app_bar(view_at(hooks, page, "/schedule/session/42"))
    assert isinstance(bar.title, ft.Text)
    assert bar.title.value == "Title"
    assert bar.center_title is False  # iOS would centre it (D-10)
    assert bar.exclude_header_semantics is False  # Flutter marks the title a header
    assert bar.adaptive is not True  # Material only (D-10)


def test_a_pushed_view_has_the_material_back_arrow_to_its_parent(
    hooks: Hooks, page: FakePage
) -> None:
    view = view_at(hooks, page, "/schedule/session/42/speaker/17")
    arrow = back_arrow(view)
    assert arrow.icon == ft.Icons.ARROW_BACK
    assert arrow.tooltip == "Back"  # its accessible name (D-27)
    assert app_bar(view).automatically_imply_leading is False  # no iOS chevron
    assert view.route == "/schedule/session/42/speaker/17"

    click(arrow)
    assert page.navigated == ["/schedule/session/42"]


def test_the_back_arrow_on_search_returns_to_its_opener(
    hooks: Hooks, page: FakePage, svc: Services
) -> None:
    svc.memory.search_base = "/map?highlight=7"
    arrow = back_arrow(view_at(hooks, page, "/search"))
    click(arrow)
    assert page.navigated == ["/map?highlight=7"]


@pytest.mark.parametrize("root", ["/schedule", "/my-schedule", "/map", "/more"])
async def test_back_on_a_root_other_than_now_goes_to_now(
    hooks: Hooks, page: FakePage, root: str
) -> None:
    view = view_at(hooks, page, root)
    assert app_bar(view).leading is None
    assert view.route == "/"  # roots share one View key (D-142)
    assert view.can_pop is False
    assert view.on_confirm_pop is not None

    confirmed: list[bool] = []

    async def confirm_pop(should_pop: bool) -> None:
        confirmed.append(should_pop)

    event = SimpleNamespace(control=SimpleNamespace(confirm_pop=confirm_pop))
    await cast(Any, view.on_confirm_pop)(event)
    assert page.navigated == ["/now"]
    assert confirmed == [False]


def test_back_on_now_is_left_to_the_system(hooks: Hooks, page: FakePage) -> None:
    view = view_at(hooks, page, "/now")
    assert app_bar(view).leading is None
    assert view.route == "/"
    assert view.can_pop is True
    assert view.on_confirm_pop is None


def test_the_body_sits_in_a_safe_area_and_the_actions_in_the_app_bar(
    hooks: Hooks, page: FakePage
) -> None:
    action = ft.IconButton(ft.Icons.SEARCH, tooltip="Search")
    view = view_at(hooks, page, "/now", actions=[action])
    assert app_bar(view).actions == [action]
    assert view.padding == 0
    (safe,) = view.controls
    assert isinstance(safe, ft.SafeArea)
    assert safe.expand is True
    assert isinstance(safe.content, ft.Text)
    assert safe.adaptive is not True


def test_only_the_top_view_records_where_a_new_session_returns(
    hooks: Hooks, page: FakePage, svc: Services
) -> None:
    page.route = "/schedule/session/42?highlight=1"
    view_at(hooks, page, "/schedule", below=True)
    assert svc.memory.last_location == ""

    hooks.view_path = "/schedule/session/42"
    AppScaffold(title="Session", body=ft.Text("body"))
    assert svc.memory.last_location == "/schedule/session/42?highlight=1"


async def test_the_content_line_is_logged_once_per_feed_version(
    hooks: Hooks,
    page: FakePage,
    conference: Conference,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger=scaffold.__name__)
    conference.source, conference.version = "bundled", 1
    view_at(hooks, page, "/now")
    view_at(hooks, page, "/schedule")  # a tab switch mounts another screen
    conference.source, conference.version = "network", 2  # a refresh published
    view_at(hooks, page, "/schedule")

    assert [deps for _, deps in hooks.effects] == [[1], [1], [2]]
    for setup, _ in hooks.effects:
        await setup()
    lines = [r.getMessage() for r in caplog.records if r.name == scaffold.__name__]
    assert lines == [
        "Content shown: bundled feed, version 1",
        "Content shown: network feed, version 2",
    ]


class SlowPrefs(MemoryPrefs):
    """SharedPreferences whose replies wait until the test releases them."""

    def init(self) -> None:
        super().init()
        self.release = asyncio.Event()

    async def _invoke_method(
        self,
        method_name: str,
        arguments: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        await self.release.wait()
        return await super()._invoke_method(method_name, arguments, timeout)


@pytest.fixture
def slow_prefs() -> SlowPrefs:
    return SlowPrefs()  # before ``page``: a service registers with a bound page


async def test_a_newer_version_does_not_cancel_the_line_of_the_one_shown_before(
    slow_prefs: SlowPrefs,
    hooks: Hooks,
    page: FakePage,
    svc: Services,
    conference: Conference,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    caplog.set_level(logging.INFO, logger=scaffold.__name__)
    storage = Storage(prefs=slow_prefs, directory=tmp_path, year=2026)
    slow_svc = replace(svc, storage=storage)
    monkeypatch.setattr(scaffold, "use_services", lambda: slow_svc)
    conference.source, conference.version = "cache", 1
    view_at(hooks, page, "/now")
    ((setup, _),) = hooks.effects

    # Flet cancels the run in progress when the network version re-runs the effect.
    run = asyncio.create_task(setup())
    await asyncio.sleep(0)  # the run reaches the round trip
    run.cancel()
    with pytest.raises(asyncio.CancelledError):
        await run
    slow_prefs.release.set()
    for _ in range(5):  # the shielded round trip returns, then logs
        await asyncio.sleep(0)

    lines = [r.getMessage() for r in caplog.records if r.name == scaffold.__name__]
    assert lines == ["Content shown: cache feed, version 1"]


def test_only_a_leaf_component_reads_the_feed_so_a_refresh_skips_the_screen(
    hooks: Hooks, page: FakePage, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(scaffold, "Shown", Shown)  # the real component
    reads: list[str] = []
    monkeypatch.setattr(scaffold, "use_conference", lambda: reads.append("read"))
    body = ft.Text("body")
    hooks.view_path = page.route = "/more"

    with Renderer().with_context():  # what calling a component needs, as in a render
        view = AppScaffold(title="More", body=body)

    (safe,) = view.controls
    assert isinstance(safe, ft.SafeArea)
    shown = safe.content
    assert isinstance(shown, ft.Component)
    assert shown.fn is inspect.unwrap(Shown)
    assert shown.args == (body,)
    assert reads == []  # the screen's own render never subscribed to Conference


def test_shown_hands_back_the_same_body(hooks: Hooks, conference: Conference) -> None:
    body = ft.Text("body")
    assert inspect.unwrap(Shown)(body) is body
    assert [deps for _, deps in hooks.effects] == [[conference.version]]


def test_search_records_its_opener_with_the_query_then_opens(
    page: FakePage,
) -> None:
    memory = ViewMemory()
    page.route = "/map?highlight=7"
    button = search_button(memory, "rooms")
    assert button.tooltip == "Search"
    click(button)
    assert memory.search_base == "/map?highlight=7"
    assert page.navigated == ["/search?scope=rooms"]


# ------------------------------------------------------------------ the bottom bar (#75)


def bar_of(view: ft.View) -> ft.NavigationBar:
    assert isinstance(view.navigation_bar, ft.NavigationBar)
    return view.navigation_bar


async def tap_tab(view: ft.View, root: str) -> None:
    """Tap a destination as Flutter reports it: selected first, then ``on_change``."""
    bar = bar_of(view)
    bar.selected_index = TAB_ROOTS.index(root)
    await cast(Any, bar.on_change)(SimpleNamespace(control=bar))


@pytest.mark.parametrize("root", TAB_ROOTS)
def test_every_tab_root_shows_the_bar_with_its_own_tab_selected(
    hooks: Hooks, page: FakePage, root: str
) -> None:
    bar = bar_of(view_at(hooks, page, root))
    assert TABS[bar.selected_index].root == root


@pytest.mark.parametrize("tab", TABS)
def test_a_root_s_title_carries_its_screen_identifier_for_ui_tests(
    hooks: Hooks, page: FakePage, tab: Tab
) -> None:
    title = app_bar(view_at(hooks, page, tab.root)).title
    assert isinstance(title, ft.Semantics)
    assert title.identifier == tab.title_identifier
    assert title.label is None  # the text names the node, once (D-166)
    assert isinstance(title.content, ft.Text)
    assert title.content.value == "Title"


@pytest.mark.parametrize(
    "location",
    [
        "/now/session/42",
        "/schedule/session/42/speaker/17",
        "/more/speakers",
        "/more/tracks/python",
        "/search",
        "/search/session/42",
    ],
)
def test_pushed_views_show_the_back_arrow_and_no_bar(
    hooks: Hooks, page: FakePage, location: str
) -> None:
    view = view_at(hooks, page, location)
    assert view.navigation_bar is None  # it moved with the page (D-144)
    back_arrow(view)


@pytest.mark.parametrize("target", ["/now", "/my-schedule", "/map", "/more"])
async def test_tapping_another_tab_shows_its_root(
    hooks: Hooks, page: FakePage, target: str
) -> None:
    retaps: list[str] = []

    async def retap() -> None:
        retaps.append("schedule")

    await tap_tab(view_at(hooks, page, "/schedule", on_retap=retap), target)
    assert page.navigated == [target]
    assert retaps == []


async def test_re_tapping_the_active_tab_runs_the_root_s_retap_and_stays(
    hooks: Hooks, page: FakePage
) -> None:
    retaps: list[str] = []

    async def retap() -> None:
        retaps.append("map")

    await tap_tab(view_at(hooks, page, "/map", on_retap=retap), "/map")
    assert retaps == ["map"]
    assert page.navigated == []


async def test_re_tapping_a_root_without_a_retap_action_does_nothing(
    hooks: Hooks, page: FakePage
) -> None:
    await tap_tab(view_at(hooks, page, "/now"), "/now")
    assert page.navigated == []
    assert page.dialogs == []


async def test_a_retap_that_fails_is_reported_and_the_bar_keeps_working(
    hooks: Hooks, page: FakePage
) -> None:
    async def retap() -> None:
        raise RuntimeError("the list is gone")

    view = view_at(hooks, page, "/more", on_retap=retap)
    await tap_tab(view, "/more")
    assert len(page.dialogs) == 1  # "Something went wrong" (D-163), not a crash
    await tap_tab(view, "/now")
    assert page.navigated == ["/now"]


# ------------------------------------------------------------------ StatusStrip

FETCHED = datetime(2026, 5, 12, 10, 42, tzinfo=PACIFIC)  # a Tuesday


@pytest.mark.parametrize(
    ("status", "fetched_at", "line"),
    [
        ("fresh", FETCHED, None),
        ("refreshing", FETCHED, "Updating the schedule…"),
        ("stale", FETCHED, "Updated 9 hours ago"),
        ("stale", None, "No schedule yet"),
        ("offline", FETCHED, "Offline · schedule from Tue, May 12, 10:42 AM"),
        ("problem", FETCHED, "Couldn't update · schedule from Tue, May 12, 10:42 AM"),
        ("offline", None, "Offline · no schedule yet"),
        ("problem", None, "Couldn't update · no schedule yet"),
    ],
)
def test_the_strip_says_why_the_data_is_not_fresh(
    status: Status, fetched_at: datetime | None, line: str | None
) -> None:
    now = FETCHED + timedelta(hours=9, minutes=5)
    assert strip_line(status, fetched_at, now, PACIFIC, use_24h=False) == line


def test_the_strip_writes_times_in_conference_time_and_the_device_format() -> None:
    fetched_utc = FETCHED.astimezone(ZoneInfo("UTC"))
    line = strip_line("offline", fetched_utc, FETCHED, PACIFIC, use_24h=True)
    assert line == "Offline · schedule from Tue, May 12, 10:42"


def render_strip(*, auto_refresh: bool = False) -> ft.Semantics:
    # The body, without @ft.component.
    strip = inspect.unwrap(StatusStrip)(auto_refresh=auto_refresh)
    assert isinstance(strip, ft.Semantics)
    return strip


def icon_of(strip: ft.Semantics) -> ft.Icon:
    """The strip's icon, beside its line."""
    box = cast(ft.Container, strip.content)
    padded = cast(ft.Container, cast(ft.Column, box.content).controls[0])
    line_row = cast(ft.Row, cast(ft.Row, padded.content).controls[0])
    icon = line_row.controls[0]
    assert isinstance(icon, ft.Icon)
    return icon


@dataclass(eq=False)
class StripRenders:
    """Renders the strip at every change of the store, as a subscribed strip does.

    The test keeps it: an observable holds its listeners weakly.
    """

    conference: Conference
    strips: list[ft.Semantics] = field(default_factory=list)

    def __post_init__(self) -> None:
        assert isinstance(self.conference, ft.Observable)
        self.conference.subscribe(self)

    def __call__(self, _sender: object, _name: str | None) -> None:
        self.strips.append(render_strip())


def strip_parts(strip: ft.Semantics) -> tuple[ft.Text, ft.TextButton, ft.ProgressBar]:
    box = strip.content
    assert isinstance(box, ft.Container)
    column = box.content
    assert isinstance(column, ft.Column)
    padded, slot = column.controls
    assert isinstance(slot, ft.Container)
    assert slot.height == 2  # kept while the bar hides: nothing moves (ux.md §3.9)
    progress = slot.content
    assert isinstance(padded, ft.Container)
    assert isinstance(padded.content, ft.Row)
    # Room around a line that wraps at 200 % text (ux.md §3.9).
    assert padded.padding == ft.Padding.only(left=16, top=4, right=8, bottom=4)
    line_row, button = padded.content.controls
    assert isinstance(line_row, ft.Row)
    # The icon tops the line, so a line that wraps keeps it beside its first line.
    assert line_row.vertical_alignment == ft.CrossAxisAlignment.START
    assert padded.content.vertical_alignment == ft.CrossAxisAlignment.CENTER
    icon, text = line_row.controls
    assert isinstance(icon, ft.Icon)
    assert isinstance(text, ft.Text)
    assert isinstance(button, ft.TextButton)
    assert isinstance(progress, ft.ProgressBar)
    return text, button, progress


@pytest.fixture
def fake_now(monkeypatch: pytest.MonkeyPatch) -> datetime:
    """Two days before the conference, so a 25 h old feed is stale (D-32)."""
    now = datetime(2026, 5, 11, 12, 0, tzinfo=PACIFIC)
    monkeypatch.setattr(clock, "now", lambda: now)
    return now


def test_the_strip_is_hidden_while_the_data_is_fresh(
    hooks: Hooks, page: FakePage, conference: Conference, fake_now: datetime
) -> None:
    conference.fetched_at = fake_now - timedelta(hours=1)
    strip = render_strip()
    assert strip.visible is False


def test_a_stale_strip_is_a_live_region_with_refresh(
    hooks: Hooks, page: FakePage, conference: Conference, fake_now: datetime
) -> None:
    conference.fetched_at = fake_now - timedelta(hours=25)
    strip = render_strip()
    text, button, progress = strip_parts(strip)
    assert strip.visible is True
    assert strip.live_region is True
    assert strip.identifier == "app.status"
    assert text.value == "Updated 1 day ago"
    assert button.disabled is False
    assert button.on_click is not None
    assert progress.visible is False


async def test_while_a_refresh_the_user_asked_for_runs_it_says_so_and_disables_refresh(
    hooks: Hooks,
    page: FakePage,
    conference: Conference,
    fake_now: datetime,
    network: Network,
) -> None:
    conference.fetched_at = fake_now - timedelta(hours=25)
    tap = press(strip_parts(render_strip())[1])  # Refresh
    await network.arrived.wait()

    strip = render_strip()
    text, button, progress = strip_parts(strip)
    assert strip.visible is True
    assert text.value == "Updating the schedule…"
    assert icon_of(strip).color == ft.Colors.ON_SURFACE_VARIANT
    assert button.disabled is True
    assert progress.visible is True
    assert progress.value is None  # indeterminate
    network.released.set()
    await tap


async def test_an_automatic_refresh_over_fresh_data_keeps_the_strip_hidden(
    hooks: Hooks,
    page: FakePage,
    conference: Conference,
    svc: Services,
    fake_now: datetime,
    network: Network,
) -> None:
    conference.fetched_at = fake_now - timedelta(hours=1)
    conference.start_refresh_if_due(svc.storage, svc.year)
    await network.arrived.wait()

    assert conference.refreshing
    assert render_strip().visible is False  # nothing appears, nothing moves (D-181)


def looks(strip: ft.Semantics) -> tuple[object, ...]:
    """What a sighted user and a screen reader get from the strip, but its bar."""
    text, button, _ = strip_parts(strip)
    icon = icon_of(strip)
    return strip.visible, icon.icon, icon.color, text.value, button.disabled


async def test_an_automatic_refresh_over_an_offline_strip_shows_only_the_bar(
    hooks: Hooks,
    page: FakePage,
    conference: Conference,
    svc: Services,
    fake_now: datetime,
    network: Network,
) -> None:
    conference.fetched_at = datetime(2026, 5, 11, 10, 42, tzinfo=PACIFIC)
    conference.problem = "offline"  # the last refresh got no answer
    network.error = api.NetworkError("ConnectError: still offline")
    offline = looks(render_strip())
    assert offline == (
        True,
        ft.Icons.CLOUD_OFF_OUTLINED,
        DARK_TOKENS.warning,
        "Offline · schedule from Mon, May 11, 10:42 AM",
        False,
    )
    renders = StripRenders(conference)

    task = conference.start_refresh_if_due(svc.storage, svc.year)  # the 15-min tick
    assert task is not None
    await network.arrived.wait()
    during = render_strip()
    network.released.set()
    await task
    after = render_strip()

    # Line, icon and button never changed, so the live region announces nothing new;
    # only the bar came and went, in its fixed slot (D-181).
    assert {looks(strip) for strip in [during, after, *renders.strips]} == {offline}
    assert strip_parts(during)[2].visible is True
    assert strip_parts(after)[2].visible is False
    assert [strip_parts(strip)[2].visible for strip in renders.strips] == [True, False]


async def test_refresh_during_a_quiet_refresh_joins_it_and_says_so_at_once(
    hooks: Hooks,
    page: FakePage,
    conference: Conference,
    svc: Services,
    fake_now: datetime,
    network: Network,
) -> None:
    conference.fetched_at = fake_now - timedelta(hours=25)
    quiet = conference.start_refresh_if_due(svc.storage, svc.year)
    assert quiet is not None
    await network.arrived.wait()
    strip = render_strip()
    assert strip_parts(strip)[0].value == "Updated 1 day ago"
    renders = StripRenders(conference)

    tap = press(strip_parts(strip)[1])  # Refresh, while the quiet refresh runs
    await asyncio.sleep(0)  # the handler runs up to its wait

    (joined,) = renders.strips  # the tap re-renders the strip at once
    text, button, progress = strip_parts(joined)
    assert text.value == "Updating the schedule…"
    assert button.disabled is True
    assert progress.visible is True
    assert conference._task is quiet
    network.released.set()
    await tap
    assert quiet.done()
    assert network.requests == 1  # one request for both (D-145)


# ------------------------------------------------------------------ the strip's ticks


@dataclass
class Clock:
    """``clock.now()`` for a test, moved by hand."""

    now: datetime

    def move(self, delta: timedelta) -> None:
        self.now += delta


@pytest.fixture
def moving_clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    fake = Clock(datetime(2026, 5, 11, 12, 0, 30, tzinfo=PACIFIC))
    monkeypatch.setattr(clock, "now", lambda: fake.now)
    return fake


@dataclass
class Loops:
    """Stands in for ``Services.run_every``: records each loop instead of running it."""

    started: list[tuple[float, Callable[[], object]]] = field(default_factory=list)

    # A bound method set on the class is not bound again: no `self` of Services.
    async def run_every(self, seconds: float, action: Callable[[], object]) -> None:
        self.started.append((seconds, action))


@pytest.fixture
def loops(monkeypatch: pytest.MonkeyPatch) -> Loops:
    fake = Loops()
    monkeypatch.setattr(Services, "run_every", fake.run_every)
    return fake


async def mounted_strip(
    hooks: Hooks, loops: Loops, **kwargs: Any
) -> Callable[[], object]:
    """Render the strip and run its effect as a mount does; return the tick."""
    render_strip(**kwargs)
    setup, _ = hooks.effects[-1]
    await setup()
    ((seconds, tick),) = loops.started
    assert seconds == scaffold.TICK_SECONDS == 60
    return tick


def test_the_ticks_stop_when_the_strip_unmounts(hooks: Hooks, page: FakePage) -> None:
    render_strip(auto_refresh=True)
    (_, dependencies), cleanup = hooks.effects[-1], hooks.cleanups[-1]
    assert dependencies == [True]
    # Flet cancels an effect's task on unmount only when it has a cleanup (F2), and a
    # cleanup returned by a sync setup is lost at the next render (F39).
    assert cleanup is scaffold.stop_ticks


async def test_a_tick_re_renders_the_strip_only_when_the_minute_changed(
    hooks: Hooks, page: FakePage, loops: Loops, moving_clock: Clock
) -> None:
    tick = await mounted_strip(hooks, loops)
    tick()  # at mount: the same minute as the render
    assert hooks.renders == 0
    moving_clock.move(timedelta(seconds=60))
    tick()
    assert hooks.renders == 1


async def test_a_tick_shows_the_strip_once_the_data_turns_stale(
    hooks: Hooks,
    page: FakePage,
    conference: Conference,
    loops: Loops,
    moving_clock: Clock,
) -> None:
    conference.fetched_at = moving_clock.now - timedelta(
        hours=23, minutes=59, seconds=30
    )
    tick = await mounted_strip(hooks, loops)
    assert render_strip().visible is False
    moving_clock.move(timedelta(seconds=60))
    tick()
    assert hooks.renders == 1
    strip = render_strip()  # the re-render the tick asked for
    text, _, _ = strip_parts(strip)
    assert strip.visible is True
    assert text.value == "Updated 1 day ago"


async def test_use_minute_re_renders_its_component_only_when_the_minute_changes(
    hooks: Hooks, page: FakePage, loops: Loops, moving_clock: Clock
) -> None:
    """The Map's "Now:" lines keep up on the strip's loop (#100, D-175)."""
    assert scaffold.use_minute() == scaffold.current_minute()
    (setup, dependencies), cleanup = hooks.effects[-1], hooks.cleanups[-1]
    assert dependencies == []
    assert cleanup is scaffold.stop_ticks  # what makes Flet cancel it on unmount (F2)
    await setup()
    ((seconds, tick),) = loops.started
    assert seconds == scaffold.TICK_SECONDS
    tick()  # at mount: the same minute as the render
    assert hooks.renders == 0
    moving_clock.move(timedelta(seconds=60))
    tick()
    assert hooks.renders == 1
    assert hooks.state == scaffold.current_minute()


class Network:
    """Stands in for ``api.fetch_feed``: counts requests, each held until released.

    Released, it answers with an empty body, which ``feed.process`` rejects: a failed
    refresh, which is enough to end it; or it raises ``error`` when one is set.
    """

    def __init__(self) -> None:
        self.requests = 0
        self.arrived = asyncio.Event()
        self.released = asyncio.Event()
        self.error: Exception | None = None

    async def fetch_feed(self, url: str, **_: object) -> bytes:
        self.requests += 1
        self.arrived.set()
        await self.released.wait()
        if self.error is not None:
            raise self.error
        return b""


@pytest.fixture
def network(monkeypatch: pytest.MonkeyPatch) -> Iterator[Network]:
    fake = Network()
    monkeypatch.setattr(api, "fetch_feed", fake.fetch_feed)
    yield fake
    fake.released.set()  # a held refresh ends with the test


async def test_on_now_and_schedule_a_tick_starts_a_refresh_when_one_is_due(
    hooks: Hooks,
    page: FakePage,
    conference: Conference,
    loops: Loops,
    moving_clock: Clock,
    network: Network,
) -> None:
    tick = await mounted_strip(hooks, loops, auto_refresh=True)
    tick()  # nothing has started in this session yet
    first = conference._task
    assert first is not None
    network.released.set()
    await first
    assert network.requests == 1

    moving_clock.move(timedelta(minutes=14, seconds=59))
    tick()
    assert conference._task is first  # not yet due

    moving_clock.move(timedelta(seconds=1))  # 15 min after it began (D-40)
    tick()
    second = conference._task
    assert second is not None and second is not first
    await second
    assert network.requests == 2


async def test_elsewhere_a_tick_never_refreshes(
    hooks: Hooks,
    page: FakePage,
    conference: Conference,
    loops: Loops,
    moving_clock: Clock,
) -> None:
    tick = await mounted_strip(hooks, loops)  # My schedule's strip
    tick()
    moving_clock.move(timedelta(hours=2))
    tick()
    assert conference._task is None


@pytest.mark.parametrize(
    ("screen", "auto_refresh"),
    # The Schedule places its own strip: tests/test_schedule.py checks it.
    [(now.Now, True), (my_schedule.MySchedule, False)],
)
def test_only_now_and_schedule_refresh_every_15_minutes(
    hooks: Hooks,
    page: FakePage,
    svc: Services,
    conference: Conference,
    monkeypatch: pytest.MonkeyPatch,
    screen: Callable[[], Any],
    auto_refresh: bool,
) -> None:
    module = sys.modules[screen.__module__]
    bodies: list[dict[str, Any]] = []

    def stub_body(controls: list[ft.Control], **kwargs: Any) -> dict[str, Any]:
        bodies.append(kwargs)
        return kwargs

    monkeypatch.setattr(module, "stub_body", stub_body)
    monkeypatch.setattr(module, "AppScaffold", lambda **kwargs: kwargs)
    monkeypatch.setattr(module, "use_scroll_to_top", lambda: (ft.Ref(), None))
    for name, fake in (("use_services", svc), ("use_conference", conference)):
        if hasattr(module, name):
            monkeypatch.setattr(module, name, lambda fake=fake: fake)

    inspect.unwrap(screen)()

    ((kwargs),) = bodies
    assert kwargs["status"] is True
    assert kwargs.get("auto_refresh", False) is auto_refresh


# ------------------------------------------------------------------ SectionHeader


def test_a_section_header_is_a_heading_in_the_title_small_style() -> None:
    header = SectionHeader("Days")
    assert isinstance(header, ft.Semantics)
    assert header.header is True
    assert isinstance(header.content, ft.Container)
    text = header.content.content
    assert isinstance(text, ft.Text)
    assert text.value == "Days"
    assert text.theme_style == ft.TextThemeStyle.TITLE_SMALL
