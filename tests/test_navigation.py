"""Tests for the bottom bar and the re-tap scroll (#75; D-13, D-27, D-144).

The bar's own parts, then how it sits on ``AppScaffold``'s Views and what a tap does,
built outside a renderer with the fixtures of ``tests/chrome.py`` (#264). What the
bar looks like, that a re-tap scrolls a real list and what TalkBack and VoiceOver read
are checked on devices (the PR).
"""

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any, cast

import flet as ft
import pytest

from pycon_us.locations import TAB_ROOTS
from pycon_us.prefs import Prefs
from pycon_us.ui import navigation
from pycon_us.ui.navigation import (
    RETAP_SCROLL_MS,
    TABS,
    Tab,
    navigation_bar,
    use_scroll_to_top,
)
from tests import chrome
from tests.chrome import app_bar, back_arrow, view_at
from tests.fakes import FakePage, Hooks

# The harness's fixtures, under this module's names, where pytest looks them up.
year, svc, page, conference, hooks = (
    chrome.year,
    chrome.svc,
    chrome.page,
    chrome.conference,
    chrome.hooks,
)


async def ignore(e: ft.Event[ft.NavigationBar]) -> None:
    """A tab handler for bars whose taps these tests don't make."""


def test_the_bar_has_the_five_tab_roots_in_order_with_their_labels() -> None:
    """The bar's tabs are the five tab roots, in order, with their labels."""
    assert tuple(tab.root for tab in TABS) == TAB_ROOTS
    assert [tab.label for tab in TABS] == [
        "Now",
        "Schedule",
        "My schedule",
        "Map",
        "More",
    ]


def test_each_tab_has_an_app_nav_identifier_for_ui_tests() -> None:
    """Each tab carries an ``app.nav.<tab>`` identifier."""
    assert [tab.identifier for tab in TABS] == [
        "app.nav.now",
        "app.nav.schedule",
        "app.nav.my_schedule",
        "app.nav.map",
        "app.nav.more",
    ]


def test_each_tab_root_s_title_has_a_screen_identifier_for_ui_tests() -> None:
    """Each tab names its root title's identifier, ``<screen>.title``."""
    assert [tab.title_identifier for tab in TABS] == [
        "now.title",
        "schedule.title",
        "my_schedule.title",
        "map.title",
        "more.title",
    ]


@pytest.mark.parametrize("root", TAB_ROOTS)
def test_the_bar_is_material_with_labels_always_shown_and_its_root_selected(
    root: str,
) -> None:
    """On each root the bar is Material, shows every label and selects that root."""
    bar = navigation_bar(root, ignore)
    assert bar.label_behavior == ft.NavigationBarLabelBehavior.ALWAYS_SHOW
    assert bar.adaptive is not True  # never Cupertino (D-10)
    assert bar.selected_index == TAB_ROOTS.index(root)


def tagged(icon: ft.IconDataOrControl | None) -> tuple[str | None, ft.IconData]:
    """The identifier and the icon of a destination's tagged icon."""
    assert isinstance(icon, ft.Semantics)
    assert isinstance(icon.content, ft.Icon)
    assert icon.label is None  # no name of its own: the destination's label is it
    return icon.identifier, cast(ft.IconData, icon.content.icon)


def test_each_destination_is_labelled_and_outlined_until_selected() -> None:
    """Each destination has its tab's label and id, outlined until selected."""
    bar = navigation_bar("/now", ignore)
    for tab, destination in zip(TABS, bar.destinations, strict=True):
        assert destination.label == tab.label  # the accessible name
        assert tagged(destination.icon) == (tab.identifier, tab.icon)
        assert tagged(destination.selected_icon) == (tab.identifier, tab.selected_icon)
    filled = {tab.selected_icon for tab in TABS} - {ft.Icons.MORE_HORIZ}
    assert not filled & {tab.icon for tab in TABS}  # outlined off, filled on (D-27)


# ------------------------------------------------------------------ use_scroll_to_top


class FakeList:
    """A mounted ``ListView``: records where it was asked to scroll."""

    def __init__(self) -> None:
        """Start with no scroll asked for."""
        self.scrolls: list[dict[str, Any]] = []

    async def scroll_to(self, **kwargs: Any) -> None:
        """Record the arguments of a scroll request."""
        self.scrolls.append(kwargs)


@pytest.fixture
def prefs(monkeypatch: pytest.MonkeyPatch) -> Prefs:
    """Default ``Prefs`` for ``navigation``, with ``use_memo`` building at once."""
    prefs = Prefs()
    monkeypatch.setattr(navigation, "use_prefs", lambda: prefs)
    # One render, outside a renderer: use_memo just builds the value.
    monkeypatch.setattr(ft, "use_memo", lambda build, deps: build())
    return prefs


def mounted() -> tuple[FakeList, Callable[[], Any]]:
    """Call ``use_scroll_to_top()`` and mount a ``FakeList`` on its ref."""
    list_ref, scroll_to_top = use_scroll_to_top()
    fake = FakeList()
    list_ref.current = cast(ft.ListView, fake)
    return fake, scroll_to_top


async def test_a_retap_scrolls_the_root_s_list_to_the_top(prefs: Prefs) -> None:
    """A re-tap scrolls the mounted list to offset 0 over ``RETAP_SCROLL_MS``."""
    fake, scroll_to_top = mounted()
    await scroll_to_top()
    assert fake.scrolls == [{"offset": 0, "duration": RETAP_SCROLL_MS}]


async def test_under_reduced_motion_the_retap_jumps_to_the_top(prefs: Prefs) -> None:
    """Under reduced motion the re-tap scrolls to the top with no duration."""
    prefs.reduce_motion = True
    fake, scroll_to_top = mounted()
    await scroll_to_top()
    assert fake.scrolls == [{"offset": 0, "duration": 0}]  # D-34


async def test_a_retap_before_the_list_is_built_does_nothing(prefs: Prefs) -> None:
    """A re-tap before the list is mounted returns without an error."""
    list_ref, scroll_to_top = use_scroll_to_top()
    assert list_ref.current is None
    await scroll_to_top()  # no error, nothing to scroll


# ------------------------------------------------------------------ the bottom bar (#75)


def bar_of(view: ft.View) -> ft.NavigationBar:
    """The ``NavigationBar`` of ``view``."""
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
    """Each tab root's View has the bar with that root's tab selected."""
    bar = bar_of(view_at(hooks, page, root))
    assert TABS[bar.selected_index].root == root


@pytest.mark.parametrize("tab", TABS)
def test_a_root_s_title_carries_its_screen_identifier_for_ui_tests(
    hooks: Hooks, page: FakePage, tab: Tab
) -> None:
    """A root's title is a level-1 heading with its screen id and no label."""
    title = app_bar(view_at(hooks, page, tab.root)).title
    assert isinstance(title, ft.Semantics)
    assert title.identifier == tab.title_identifier
    assert title.heading_level == 1  # the root's heading (D-211)
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
    """Pushed Views show a back arrow and no bottom bar."""
    view = view_at(hooks, page, location)
    assert view.navigation_bar is None  # it moved with the page (D-144)
    back_arrow(view)


@pytest.mark.parametrize("target", ["/now", "/my-schedule", "/map", "/more"])
async def test_tapping_another_tab_shows_its_root(
    hooks: Hooks, page: FakePage, target: str
) -> None:
    """Tapping another tab navigates to its root without the retap action."""
    retaps: list[str] = []

    async def retap() -> None:
        retaps.append("schedule")

    await tap_tab(view_at(hooks, page, "/schedule", on_retap=retap), target)
    assert page.navigated == [target]
    assert retaps == []


async def test_re_tapping_the_active_tab_runs_the_root_s_retap_and_stays(
    hooks: Hooks, page: FakePage
) -> None:
    """Re-tapping the active tab runs its root's retap action and stays."""
    retaps: list[str] = []

    async def retap() -> None:
        retaps.append("map")

    await tap_tab(view_at(hooks, page, "/map", on_retap=retap), "/map")
    assert retaps == ["map"]
    assert page.navigated == []


async def test_re_tapping_a_root_without_a_retap_action_does_nothing(
    hooks: Hooks, page: FakePage
) -> None:
    """A re-tap on a root without a retap action navigates nowhere and shows nothing."""
    await tap_tab(view_at(hooks, page, "/now"), "/now")
    assert page.navigated == []
    assert page.dialogs == []


async def test_a_retap_that_fails_is_reported_and_the_bar_keeps_working(
    hooks: Hooks, page: FakePage
) -> None:
    """A retap that raises shows one error dialog, and the bar still navigates."""

    async def retap() -> None:
        raise RuntimeError("the list is gone")

    view = view_at(hooks, page, "/more", on_retap=retap)
    await tap_tab(view, "/more")
    assert len(page.dialogs) == 1  # "Something went wrong" (D-163), not a crash
    await tap_tab(view, "/now")
    assert page.navigated == ["/now"]
