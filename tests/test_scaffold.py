"""Tests for the shared chrome: ``AppScaffold``, ``StatusStrip`` and ``SectionHeader`` (#76).

The builders run outside a renderer: the hooks they call (``ft.use_view_path``,
``ft.use_effect`` and the store hooks) are replaced by ``Hooks``, and a fake page is
bound as Flet binds a session's page. What the controls look like, and that Flutter
marks the title as a header, is checked on devices (the PR).
"""

import inspect
import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
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
from pycon_us.services import Services
from pycon_us.services.storage import Storage
from pycon_us.state import Conference, Status, ViewMemory
from pycon_us.theme import DARK_TOKENS
from pycon_us.ui import scaffold
from pycon_us.ui.scaffold import (
    AppScaffold,
    SectionHeader,
    Shown,
    StatusStrip,
    search_button,
    strip_line,
)
from tests.fakes import FakePage, MemoryPrefs, MemorySemantics, bound

PACIFIC = ZoneInfo("America/Los_Angeles")


@pytest.fixture(scope="module")
def year() -> YearData:
    return load_year(2026)


@pytest.fixture
def svc(year: YearData, tmp_path: Path) -> Services:
    storage = Storage(prefs=MemoryPrefs(), directory=tmp_path, year=2026)
    return Services(
        year=year, storage=storage, memory=ViewMemory(), semantics=MemorySemantics()
    )


@dataclass
class Hooks:
    """The hooks the builders call, answered by the test instead of a renderer."""

    view_path: str = "/now"
    effects: list[tuple[Callable[[], Any], list[Any] | None]] = field(
        default_factory=list
    )

    def use_effect(self, setup: Callable[[], Any], dependencies: Any = None) -> None:
        self.effects.append((setup, dependencies))


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


def render_strip() -> ft.Semantics:
    strip = inspect.unwrap(StatusStrip)()  # the body, without @ft.component
    assert isinstance(strip, ft.Semantics)
    return strip


def strip_parts(strip: ft.Semantics) -> tuple[ft.Text, ft.TextButton, ft.ProgressBar]:
    box = strip.content
    assert isinstance(box, ft.Container)
    column = box.content
    assert isinstance(column, ft.Column)
    padded, progress = column.controls
    assert isinstance(padded, ft.Container)
    assert isinstance(padded.content, ft.Row)
    _, text, button = padded.content.controls
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


def test_while_refreshing_the_strip_shows_progress_and_disables_refresh(
    hooks: Hooks, page: FakePage, conference: Conference, fake_now: datetime
) -> None:
    conference.fetched_at = fake_now
    conference.refreshing = True
    text, button, progress = strip_parts(render_strip())
    assert text.value == "Updating the schedule…"
    assert button.disabled is True
    assert progress.visible is True
    assert progress.value is None  # indeterminate


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
