"""Tests for the shared chrome: ``AppScaffold`` and ``SectionHeader`` (#76).

``AppScaffold``'s bottom bar and its tab switches are tested in ``test_navigation.py``
with the bar's own parts (#75), ``Shown`` and the content line in ``test_shown.py``,
and the status strip in ``test_status_strip.py`` (D-200).

The builders run outside a renderer, with the fixtures of ``tests/chrome.py``:
the hooks they call (``ft.use_view_path``, ``ft.use_effect`` and the store hooks) are
replaced by ``Hooks``, and a fake page is bound as Flet binds a session's page. What
the controls look like, and that Flutter marks the title as a header, is checked on
devices (the PR).
"""

from types import SimpleNamespace
from typing import Any, cast

import flet as ft
import pytest

from pycon_us.memory import ViewMemory
from pycon_us.services import Services
from pycon_us.ui.scaffold import AppScaffold, SectionHeader, search_button
from tests import chrome
from tests.chrome import app_bar, back_arrow, body_of, click, merged_button, view_at
from tests.fakes import FakePage, Hooks

# The harness's fixtures, under this module's names, where pytest looks them up.
year, svc, page, conference, hooks = (
    chrome.year,
    chrome.svc,
    chrome.page,
    chrome.conference,
    chrome.hooks,
)


# ------------------------------------------------------------------ AppScaffold


def test_the_title_is_left_aligned_and_is_the_page_s_level_1_heading(
    hooks: Hooks, page: FakePage
) -> None:
    """The bar's title is a left-aligned level-1 heading, in a Material-only bar."""
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
    """A pushed view's bar leads with Material's Back arrow, to the parent route."""
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
    """Search's Back arrow returns to the route that opened it, query included."""
    svc.memory.search_base = "/map?highlight=7"
    arrow = back_arrow(view_at(hooks, page, "/search"))
    click(arrow)
    assert page.navigated == ["/map?highlight=7"]


@pytest.mark.parametrize("root", ["/schedule", "/my-schedule", "/map", "/more"])
async def test_back_on_a_root_other_than_now_goes_to_now(
    hooks: Hooks, page: FakePage, root: str
) -> None:
    """Back on a root tab other than Now goes to Now instead of closing the app.

    The root has no arrow and cannot pop by itself: it declines the pop it is asked
    about.
    """
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


@pytest.mark.parametrize(
    "view_path",
    ["/more/developer", "/schedule/session/42", "/search", "/more/sprints"],
)
async def test_back_on_a_pushed_view_is_left_to_flutters_navigator(
    hooks: Hooks, page: FakePage, view_path: str
) -> None:
    """With a handler, Flet leaves Back to the Navigator, which closes a dialog first.

    Without one, Flet pops a View that can pop by itself, and the dialog open over it
    with it (F46, D-208, #235). The handler lets any pop it is asked about through:
    the pop then reaches ``main.py``'s ``on_view_pop``, which navigates.
    """
    view = view_at(hooks, page, view_path)
    assert view.can_pop is True  # the iOS edge swipe and predictive Back stay (D-148)
    assert view.on_confirm_pop is not None

    confirmed: list[bool] = []

    async def confirm_pop(should_pop: bool) -> None:
        confirmed.append(should_pop)

    event = SimpleNamespace(control=SimpleNamespace(confirm_pop=confirm_pop))
    await cast(Any, view.on_confirm_pop)(event)
    assert confirmed == [True]
    assert page.navigated == []


@pytest.mark.parametrize("location", ["/nope", "/now/session/42/nope"])
async def test_back_on_an_unknown_location_goes_to_now(
    hooks: Hooks, page: FakePage, location: str
) -> None:
    """An unknown location's one-View stack declines Back and goes to Now (D-270).

    After a cold link it is the only View, so a pop it let through would close the
    app; its arrow goes to Now too, not one level up, and it takes the roots' shared
    key, so Now replaces it without a transition (D-142).
    """
    view = view_at(hooks, page, location, unknown=True)
    assert view.route == "/"
    assert view.can_pop is False
    assert view.navigation_bar is None  # not a tab root (D-144)

    confirmed: list[bool] = []

    async def confirm_pop(should_pop: bool) -> None:
        confirmed.append(should_pop)

    event = SimpleNamespace(control=SimpleNamespace(confirm_pop=confirm_pop))
    await cast(Any, view.on_confirm_pop)(event)
    assert (page.navigated, confirmed) == (["/now"], [False])

    click(back_arrow(view))
    assert page.navigated == ["/now", "/now"]


def test_back_on_now_is_left_to_the_system(hooks: Hooks, page: FakePage) -> None:
    """Now has no Back arrow and no pop handler, so its Back is the system's."""
    view = view_at(hooks, page, "/now")
    assert app_bar(view).leading is None
    assert view.route == "/"
    assert view.can_pop is True
    assert view.on_confirm_pop is None


def test_the_body_sits_in_a_safe_area_and_the_actions_in_the_app_bar(
    hooks: Hooks, page: FakePage
) -> None:
    """The body fills a Material safe area, unpadded; the actions sit in the bar."""
    action = ft.IconButton(ft.Icons.SEARCH, tooltip="Search")
    view = view_at(hooks, page, "/now", actions=[action])
    assert app_bar(view).actions == [action]
    assert view.padding == 0
    _, safe, _, _ = view.controls  # between the lines HC shows (D-306)
    assert isinstance(safe, ft.SafeArea)
    assert safe.expand is True
    assert isinstance(body_of(view), ft.Text)
    assert safe.adaptive is not True


def test_the_gutter_probe_sits_under_the_body_taking_no_space(
    hooks: Hooks, page: FakePage
) -> None:
    """D-216: every screen measures the slots' layout, so it is known before a list."""
    view = view_at(hooks, page, "/now")
    _, safe, probe, _ = view.controls  # between the lines HC shows (D-306)
    assert isinstance(safe, ft.SafeArea) and safe.expand is True
    assert probe.key == "probe"
    assert view.spacing == 0  # the View's column puts no gap above the probe


def test_only_the_top_view_records_where_a_new_session_returns(
    hooks: Hooks, page: FakePage, svc: Services
) -> None:
    """Only the top view records where a new session returns, with the query."""
    page.route = "/schedule/session/42?highlight=1"
    view_at(hooks, page, "/schedule", below=True)
    assert svc.memory.last_location == ""

    hooks.view_path = "/schedule/session/42"
    AppScaffold(title="Session", body=ft.Text("body"))
    assert svc.memory.last_location == "/schedule/session/42?highlight=1"


def test_search_records_its_opener_with_the_query_then_opens(
    page: FakePage,
) -> None:
    """The Search button records its opener's route, then opens search in its scope."""
    memory = ViewMemory()
    page.route = "/map?highlight=7"
    button = merged_button(search_button(memory, "places"))
    assert button.tooltip == "Search"  # its name, in its own node (D-234)
    click(button)
    assert memory.search_base == "/map?highlight=7"
    assert page.navigated == ["/search?scope=places"]


# ------------------------------------------------------------------ SectionHeader


def test_a_section_header_is_a_level_2_heading_in_the_title_small_style() -> None:
    """A section header is a level-2 heading over its text, in the TITLE_SMALL style."""
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
