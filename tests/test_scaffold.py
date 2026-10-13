"""Tests for the shared chrome: ``AppScaffold`` and ``SectionHeader`` (#76).

``AppScaffold``'s bottom bar and its tab switches are here too (#75); the bar's own
parts are in ``test_navigation.py``, and the status strip's in
``test_status_strip.py`` (D-200).

The builders run outside a renderer: the hooks they call (``ft.use_view_path``,
``ft.use_effect`` and the store hooks) are replaced by ``Hooks``, and a fake page is
bound as Flet binds a session's page. What the controls look like, and that Flutter
marks the title as a header, is checked on devices (the PR).
"""

import asyncio
import inspect
import logging
from collections.abc import Callable, Iterator
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import flet as ft
import pytest
from flet.components.component import Renderer

from pycon_us.config import YearData, load_year
from pycon_us.locations import TAB_ROOTS
from pycon_us.services import Services
from pycon_us.services.storage import Storage
from pycon_us.state import Conference, ViewMemory
from pycon_us.ui import scaffold
from pycon_us.ui.navigation import TABS, Tab
from pycon_us.ui.scaffold import (
    AppScaffold,
    SectionHeader,
    Shown,
    search_button,
)
from tests.fakes import (
    FakePage,
    Hooks,
    MemoryClipboard,
    MemoryHaptics,
    MemoryLauncher,
    MemoryPrefs,
    MemorySemantics,
    bound,
)


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
    monkeypatch.setattr(scaffold, "use_services", lambda: svc)
    monkeypatch.setattr(scaffold, "use_conference", lambda: conference)
    # ``Shown``'s body runs inline: no renderer here.
    monkeypatch.setattr(scaffold, "Shown", inspect.unwrap(Shown))
    return hooks


def view_at(hooks: Hooks, page: FakePage, view_path: str, **kwargs: Any) -> ft.View:
    """Build the View of view_path while page.route addresses it (the top View)."""
    hooks.view_path = view_path
    page.route = page.route if kwargs.pop("below", False) else view_path
    kwargs.setdefault("title", "Title")
    return AppScaffold(body=ft.Text("body"), **kwargs)


def app_bar(view: ft.View) -> ft.AppBar:
    assert isinstance(view.appbar, ft.AppBar)
    return view.appbar


def click(button: ft.IconButton) -> None:
    """Call a button's handler as Flet does: without the event when it takes none."""
    assert button.on_click is not None
    cast(Callable[[], None], button.on_click)()


def back_arrow(view: ft.View) -> ft.IconButton:
    leading = app_bar(view).leading
    assert isinstance(leading, ft.IconButton)
    return leading


# ------------------------------------------------------------------ AppScaffold


def test_the_title_is_left_aligned_and_is_the_page_s_level_1_heading(
    hooks: Hooks, page: FakePage
) -> None:
    bar = app_bar(view_at(hooks, page, "/schedule/session/42"))
    title = bar.title
    assert isinstance(title, ft.Semantics)
    # Flutter's header flag alone is no heading for a screen reader: the level is.
    assert (title.header, title.heading_level, title.identifier) == (True, 1, None)
    assert isinstance(title.content, ft.Text)
    assert title.content.value == "Title"
    assert bar.center_title is False  # iOS would centre it (D-10)
    assert bar.exclude_header_semantics is False  # Flutter marks the title a header
    assert bar.adaptive is not True  # Material only (D-10)


def test_an_empty_title_is_no_heading(hooks: Hooks, page: FakePage) -> None:
    """A detail page's bar is empty: its own title in the page is its heading."""
    view = view_at(hooks, page, "/schedule/session/42", title="")
    title = app_bar(view).title
    assert isinstance(title, ft.Text) and title.value == ""


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
    assert title.heading_level == 1  # the root's heading (D-208)
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


# ------------------------------------------------------------------ SectionHeader


def test_a_section_header_is_a_level_2_heading_in_the_title_small_style() -> None:
    header = SectionHeader("Days")
    assert isinstance(header, ft.Semantics)
    # A section under the page's title; without a level no screen reader stops (F40).
    assert header.header is True and header.heading_level == 2
    assert isinstance(header.content, ft.Container)
    text = header.content.content
    assert isinstance(text, ft.Text)
    assert text.value == "Days"
    assert text.theme_style == ft.TextThemeStyle.TITLE_SMALL


def test_a_section_header_s_mark_sits_before_its_text_and_says_nothing() -> None:
    """Now's Happening now has a live dot (#95); the heading still reads its text."""
    dot = ft.Container(width=8, height=8, border_radius=4)
    header = SectionHeader("Happening now", level=2, leading=dot)
    assert isinstance(header, ft.Semantics)
    assert header.header is True and header.heading_level == 2
    assert header.label is None  # the text is the heading's name
    assert isinstance(header.content, ft.Container)
    row = header.content.content
    assert isinstance(row, ft.Row)
    first, text = row.controls
    assert first is dot
    assert isinstance(text, ft.Text) and text.value == "Happening now"
    # The row's room, so a long heading wraps at large text instead of overflowing.
    assert text.expand is True


def test_a_section_header_can_say_its_text_another_way() -> None:
    """A "·" reads as a pause, as Now's header phrase reads it (#95)."""
    header = SectionHeader("Up next · 11:30 AM", level=2, spoken="Up next, 11:30 AM")
    assert isinstance(header, ft.Semantics)
    assert isinstance(header.content, ft.Container)
    text = header.content.content
    assert isinstance(text, ft.Text)
    assert text.value == "Up next · 11:30 AM"
    assert text.semantics_label == "Up next, 11:30 AM"
    plain = SectionHeader("Days")
    assert isinstance(plain, ft.Semantics) and isinstance(plain.content, ft.Container)
    assert isinstance(plain.content.content, ft.Text)
    assert plain.content.content.semantics_label is None
